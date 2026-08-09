"""Tests for zotero_arxiv_daily.protocol: Paper.generate_tldr, Paper.generate_affiliations."""

import pytest

from tests.canned_responses import make_sample_paper, make_stub_openai_client
from zotero_arxiv_daily.protocol import ANALYSIS_SECTIONS


@pytest.fixture()
def llm_params():
    return {
        "language": "English",
        "generation_kwargs": {"model": "gpt-4o-mini", "max_tokens": 16384},
    }


# ---------------------------------------------------------------------------
# generate_tldr
# ---------------------------------------------------------------------------


def test_tldr_returns_response(llm_params):
    client = make_stub_openai_client()
    paper = make_sample_paper()
    result = paper.generate_tldr(client, llm_params)
    assert result == "Hello! How can I assist you today?"
    assert paper.tldr == result


def test_tldr_without_abstract_or_fulltext(llm_params):
    client = make_stub_openai_client()
    paper = make_sample_paper(abstract="", full_text=None)
    result = paper.generate_tldr(client, llm_params)
    assert "Failed to generate TLDR" in result


def test_tldr_falls_back_to_abstract_on_error(llm_params):
    paper = make_sample_paper()

    # Client whose create() raises
    from types import SimpleNamespace

    broken_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kw: (_ for _ in ()).throw(RuntimeError("API down")))
        )
    )
    result = paper.generate_tldr(broken_client, llm_params)
    assert result == paper.abstract


def test_tldr_truncates_long_prompt(llm_params):
    client = make_stub_openai_client()
    paper = make_sample_paper(full_text="word " * 10000)
    result = paper.generate_tldr(client, llm_params)
    assert result is not None


def test_responses_api_generates_required_chinese_analysis():
    from types import SimpleNamespace

    analysis = "\n".join(f"{section}\n有证据约束的中文分析。" for section in ANALYSIS_SECTIONS)
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(output_text=analysis)

    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    paper = make_sample_paper()
    params = {
        "api_style": "responses",
        "fail_on_error": True,
        "require_chinese": True,
        "require_structured_analysis": True,
        "generation_kwargs": {
            "model": "gpt-5.6",
            "max_tokens": 16384,
            "max_output_tokens": 2000,
        },
    }

    assert paper.generate_tldr(client, params) == analysis
    assert captured["model"] == "gpt-5.6"
    assert captured["max_output_tokens"] == 2000
    assert "max_tokens" not in captured


def test_strict_analysis_raises_instead_of_falling_back():
    from types import SimpleNamespace

    client = SimpleNamespace(
        responses=SimpleNamespace(
            create=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("API down"))
        )
    )
    paper = make_sample_paper()

    with pytest.raises(RuntimeError, match="Rigorous analysis failed"):
        paper.generate_tldr(
            client,
            {
                "api_style": "responses",
                "fail_on_error": True,
                "generation_kwargs": {"model": "gpt-5.6"},
            },
        )


# ---------------------------------------------------------------------------
# generate_affiliations
# ---------------------------------------------------------------------------


def test_affiliations_returns_parsed_list(llm_params):
    client = make_stub_openai_client()
    paper = make_sample_paper()
    result = paper.generate_affiliations(client, llm_params)
    assert isinstance(result, list)
    assert "TsingHua University" in result
    assert "Peking University" in result


def test_affiliations_none_without_fulltext(llm_params):
    client = make_stub_openai_client()
    paper = make_sample_paper(full_text=None)
    result = paper.generate_affiliations(client, llm_params)
    assert result is None


def test_affiliations_deduplicates(llm_params):
    """The stub returns two distinct affiliations, so no dedup needed.
    But confirm the set() dedup in the code doesn't break anything.
    """
    client = make_stub_openai_client()
    paper = make_sample_paper()
    result = paper.generate_affiliations(client, llm_params)
    assert len(result) == len(set(result))


def test_affiliations_malformed_llm_output(llm_params):
    """LLM returns affiliations without JSON brackets. Should fall back gracefully."""
    from types import SimpleNamespace

    def create_no_brackets(**kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="TsingHua University, Peking University"),
                )
            ]
        )

    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create_no_brackets)
        )
    )
    paper = make_sample_paper()
    result = paper.generate_affiliations(client, llm_params)
    # re.search for [...] will fail -> AttributeError -> caught -> returns None
    assert result is None


def test_affiliations_error_returns_none(llm_params):
    from types import SimpleNamespace

    broken_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")))
        )
    )
    paper = make_sample_paper()
    result = paper.generate_affiliations(broken_client, llm_params)
    assert result is None
    assert paper.affiliations is None
