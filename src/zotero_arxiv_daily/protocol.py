from dataclasses import dataclass
from typing import Optional, TypeVar
from datetime import datetime
import re
import tiktoken
from openai import OpenAI
from loguru import logger
import json
RawPaperItem = TypeVar('RawPaperItem')

ANALYSIS_SECTIONS = [
    "【核心结论】",
    "【研究问题与背景】",
    "【方法拆解】",
    "【创新性分析】",
    "【实验证据】",
    "【复现性检查】",
    "【局限与风险】",
    "【可信度结论】",
]

ANALYSIS_INSTRUCTIONS = """你是一名严谨的计算机视觉论文审稿人。请仅依据所提供的论文证据，用中文进行逐篇分析。

硬性规则：
1. 不得把作者的主张写成已被独立证实的事实。
2. 未提供或无法从证据判断的内容必须明确写“未报告”或“无法判断”，不得补全或猜测。
3. 创新性分析必须区分“作者声称的创新”“证据支持的创新”和“尚无法验证的创新”。
4. 实验证据必须检查数据集、基线、指标、消融、统计波动或多随机种子；缺失项要明确指出。
5. 复现性必须检查代码、数据、超参数、训练算力和模型权重是否可获得。
6. 不使用宣传性判断；没有对照证据时，不得声称方法具有突破性。
7. 输出必须包含下列八个标题，顺序固定，不要使用 Markdown 表格或代码块：
【核心结论】
【研究问题与背景】
【方法拆解】
【创新性分析】
【实验证据】
【复现性检查】
【局限与风险】
【可信度结论】

每一部分应简洁但具体；全文约 1000 至 1800 个中文字符。可信度结论给出“高/中/低”及理由，并注明分析依据是全文还是仅摘要。"""

@dataclass
class Paper:
    source: str
    title: str
    authors: list[str]
    abstract: str
    url: str
    pdf_url: Optional[str] = None
    full_text: Optional[str] = None
    tldr: Optional[str] = None
    affiliations: Optional[list[str]] = None
    score: Optional[float] = None

    def _sample_full_text(self, max_tokens: int) -> str:
        if not self.full_text:
            return ""
        enc = tiktoken.encoding_for_model("gpt-4o")
        tokens = enc.encode(self.full_text)
        if len(tokens) <= max_tokens:
            return self.full_text

        chunk_size = max_tokens // 4
        starts = [
            0,
            max(0, len(tokens) // 3 - chunk_size // 2),
            max(0, len(tokens) * 2 // 3 - chunk_size // 2),
            len(tokens) - chunk_size,
        ]
        chunks = [enc.decode(tokens[start:start + chunk_size]) for start in starts]
        return "\n\n[论文不同位置的证据片段]\n\n".join(chunks)

    def _generate_tldr_with_llm(self, openai_client:OpenAI,llm_params:dict) -> str:
        max_input_tokens = int(llm_params.get("analysis_max_input_tokens", 12000))
        evidence_scope = "全文证据片段" if self.full_text else "仅摘要"
        prompt = (
            f"证据范围：{evidence_scope}\n\n"
            f"论文标题：{self.title}\n\n"
            f"作者：{', '.join(self.authors)}\n\n"
            f"摘要：{self.abstract}\n\n"
        )
        sampled_full_text = self._sample_full_text(max_input_tokens)
        if sampled_full_text:
            prompt += f"全文证据片段：\n{sampled_full_text}\n\n"

        if not self.full_text and not self.abstract:
            logger.warning(f"Neither full text nor abstract is provided for {self.url}")
            return "Failed to generate TLDR. Neither full text nor abstract is provided"

        generation_kwargs = dict(llm_params.get("generation_kwargs", {}))
        api_style = str(llm_params.get("api_style", "chat_completions"))
        if api_style == "responses":
            legacy_max_tokens = generation_kwargs.pop("max_tokens", None)
            if legacy_max_tokens is not None and "max_output_tokens" not in generation_kwargs:
                generation_kwargs["max_output_tokens"] = legacy_max_tokens
            response = openai_client.responses.create(
                instructions=ANALYSIS_INSTRUCTIONS,
                input=prompt,
                **generation_kwargs,
            )
            tldr = response.output_text
        elif api_style == "chat_completions":
            response_max_tokens = generation_kwargs.pop("max_output_tokens", None)
            if response_max_tokens is not None and "max_tokens" not in generation_kwargs:
                generation_kwargs["max_tokens"] = response_max_tokens
            response = openai_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": ANALYSIS_INSTRUCTIONS},
                    {"role": "user", "content": prompt},
                ],
                **generation_kwargs,
            )
            tldr = response.choices[0].message.content
        else:
            raise ValueError(f"Unsupported llm.api_style: {api_style}")

        if not tldr or not tldr.strip():
            raise RuntimeError("LLM returned an empty analysis")
        if llm_params.get("require_chinese", False) and not re.search(r"[\u4e00-\u9fff]", tldr):
            raise RuntimeError("LLM analysis does not contain Chinese text")
        if llm_params.get("require_structured_analysis", False):
            missing = [section for section in ANALYSIS_SECTIONS if section not in tldr]
            if missing:
                raise RuntimeError(f"LLM analysis is missing required sections: {missing}")
        return tldr
    
    def generate_tldr(self, openai_client:OpenAI,llm_params:dict) -> str:
        try:
            tldr = self._generate_tldr_with_llm(openai_client,llm_params)
            self.tldr = tldr
            return tldr
        except Exception as e:
            logger.warning(f"Failed to generate rigorous analysis of {self.url}: {e}")
            if llm_params.get("fail_on_error", False):
                raise RuntimeError(f"Rigorous analysis failed for {self.url}: {e}") from e
            tldr = self.abstract
            self.tldr = tldr
            return tldr

    def _generate_affiliations_with_llm(self, openai_client:OpenAI,llm_params:dict) -> Optional[list[str]]:
        if self.full_text is not None:
            prompt = f"Given the beginning of a paper, extract the affiliations of the authors in a python list format, which is sorted by the author order. If there is no affiliation found, return an empty list '[]':\n\n{self.full_text}"
            # use gpt-4o tokenizer for estimation
            enc = tiktoken.encoding_for_model("gpt-4o")
            prompt_tokens = enc.encode(prompt)
            prompt_tokens = prompt_tokens[:2000]  # truncate to 2000 tokens
            prompt = enc.decode(prompt_tokens)
            affiliations = openai_client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": "You are an assistant who perfectly extracts affiliations of authors from a paper. You should return a python list of affiliations sorted by the author order, like [\"TsingHua University\",\"Peking University\"]. If an affiliation is consisted of multi-level affiliations, like 'Department of Computer Science, TsingHua University', you should return the top-level affiliation 'TsingHua University' only. Do not contain duplicated affiliations. If there is no affiliation found, you should return an empty list [ ]. You should only return the final list of affiliations, and do not return any intermediate results.",
                    },
                    {"role": "user", "content": prompt},
                ],
                **llm_params.get('generation_kwargs', {})
            )
            affiliations = affiliations.choices[0].message.content

            affiliations = re.search(r'\[.*?\]', affiliations, flags=re.DOTALL).group(0)
            affiliations = json.loads(affiliations)
            affiliations = list(set(affiliations))
            affiliations = [str(a) for a in affiliations]

            return affiliations
    
    def generate_affiliations(self, openai_client:OpenAI,llm_params:dict) -> Optional[list[str]]:
        try:
            affiliations = self._generate_affiliations_with_llm(openai_client,llm_params)
            self.affiliations = affiliations
            return affiliations
        except Exception as e:
            logger.warning(f"Failed to generate affiliations of {self.url}: {e}")
            self.affiliations = None
            return None
@dataclass
class CorpusPaper:
    title: str
    abstract: str
    added_date: datetime
    paths: list[str]
