from datetime import date
from time import sleep

from loguru import logger
import requests

from .base import BaseRetriever, register_retriever
from ..protocol import Paper


OPENALEX_API_URL = "https://api.openalex.org/works"


def decode_abstract(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    positioned_words: dict[int, str] = {}
    for word, positions in index.items():
        for position in positions:
            positioned_words[int(position)] = word
    return " ".join(positioned_words[position] for position in sorted(positioned_words))


@register_retriever("openalex")
class OpenAlexRetriever(BaseRetriever):
    def __init__(self, config):
        super().__init__(config)
        if not self.retriever_config.get("date"):
            raise ValueError("source.openalex.date must be specified for historical retrieval")

    def _request_query(self, query: str, target_date: str) -> list[dict]:
        source_id = str(self.retriever_config.get("source_id", "S4306400194"))
        per_page = int(self.retriever_config.get("per_page", 100))
        params = {
            "search": query,
            "filter": (
                f"from_publication_date:{target_date},"
                f"to_publication_date:{target_date},"
                f"locations.source.id:{source_id}"
            ),
            "per-page": str(per_page),
            "sort": "relevance_score:desc",
            "select": (
                "id,doi,title,authorships,primary_location,best_oa_location,"
                "abstract_inverted_index,publication_date"
            ),
            "mailto": str(self.config.email.sender),
        }
        headers = {"User-Agent": "zotero-arxiv-daily-historical-backfill/1.0"}
        last_error: Exception | None = None
        for attempt in range(5):
            try:
                response = requests.get(
                    OPENALEX_API_URL,
                    params=params,
                    headers=headers,
                    timeout=30,
                )
                if response.status_code == 429 or response.status_code >= 500:
                    response.raise_for_status()
                response.raise_for_status()
                return list(response.json().get("results", []))
            except requests.RequestException as exc:
                last_error = exc
                if attempt < 4:
                    wait_seconds = 2 ** attempt
                    logger.warning(
                        f"OpenAlex request failed for {query!r}; retrying in {wait_seconds}s: {exc}"
                    )
                    sleep(wait_seconds)
        raise RuntimeError(f"OpenAlex request failed for {query!r}: {last_error}")

    def _retrieve_raw_papers(self) -> list[dict]:
        target_date = str(self.retriever_config.date)
        try:
            date.fromisoformat(target_date)
        except ValueError as exc:
            raise ValueError(
                f"source.openalex.date must use YYYY-MM-DD format, got {target_date!r}"
            ) from exc

        queries = [str(query) for query in self.retriever_config.get("queries", [])]
        if not queries:
            raise ValueError("source.openalex.queries must contain at least one query")
        request_delay = float(self.retriever_config.get("request_delay_seconds", 0.25))
        max_results = int(self.retriever_config.get("max_results", 500))

        works: dict[str, dict] = {}
        failures: list[str] = []
        for index, query in enumerate(queries):
            try:
                for work in self._request_query(query, target_date):
                    identity = str(work.get("id") or work.get("doi") or work.get("title") or "")
                    if identity:
                        works.setdefault(identity.lower(), work)
            except Exception as exc:
                logger.warning(f"Skipping failed OpenAlex query {query!r}: {exc}")
                failures.append(query)
            if index < len(queries) - 1 and request_delay > 0:
                sleep(request_delay)

        if len(failures) == len(queries):
            raise RuntimeError("All OpenAlex historical queries failed")
        logger.info(
            f"Retrieved {len(works)} unique OpenAlex arXiv records for {target_date} "
            f"from {len(queries) - len(failures)}/{len(queries)} queries"
        )
        return list(works.values())[:max_results]

    def convert_to_paper(self, raw_paper: dict) -> Paper | None:
        title = str(raw_paper.get("title") or "").strip()
        abstract = decode_abstract(raw_paper.get("abstract_inverted_index"))
        if not title or not abstract:
            return None
        authors = [
            str(authorship.get("author", {}).get("display_name"))
            for authorship in raw_paper.get("authorships", [])
            if authorship.get("author", {}).get("display_name")
        ]
        primary_location = raw_paper.get("primary_location") or {}
        best_oa_location = raw_paper.get("best_oa_location") or {}
        url = (
            primary_location.get("landing_page_url")
            or raw_paper.get("doi")
            or raw_paper.get("id")
            or ""
        )
        return Paper(
            source=self.name,
            title=title,
            authors=authors,
            abstract=abstract,
            url=str(url),
            pdf_url=best_oa_location.get("pdf_url"),
            full_text=None,
        )
