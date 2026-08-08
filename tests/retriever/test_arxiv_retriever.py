"""Tests for ArxivRetriever."""

import time
from types import SimpleNamespace

import feedparser
import pytest

from zotero_arxiv_daily.retriever.arxiv_retriever import ArxivRetriever, _run_with_hard_timeout
import zotero_arxiv_daily.retriever.arxiv_retriever as arxiv_retriever
from omegaconf import open_dict


def _sleep_and_return(value: str, delay_seconds: float) -> str:
    time.sleep(delay_seconds)
    return value


def _raise_runtime_error() -> None:
    raise RuntimeError("boom")


def test_arxiv_retriever(config, mock_feedparser, monkeypatch):
    monkeypatch.setattr("zotero_arxiv_daily.retriever.base.sleep", lambda _: None)

    # The RSS fixture gives us paper IDs.  After feedparser, the code calls
    # arxiv.Client().results(search) which makes real HTTP requests.  We mock
    # the arxiv Client so the test stays offline.
    new_entries = [
        e for e in mock_feedparser.entries
        if e.get("arxiv_announce_type", "new") == "new"
    ]
    paper_ids = [e.id.removeprefix("oai:arXiv.org:") for e in new_entries]

    # Build fake ArxivResult-like objects matching each RSS entry
    fake_results = []
    for entry in new_entries:
        pid = entry.id.removeprefix("oai:arXiv.org:")
        fake_results.append(SimpleNamespace(
            title=entry.title,
            authors=[SimpleNamespace(name="Test Author")],
            summary="Test abstract",
            pdf_url=f"https://arxiv.org/pdf/{pid}",
            entry_id=f"https://arxiv.org/abs/{pid}",
            source_url=lambda pid=pid: f"https://arxiv.org/e-print/{pid}",
        ))

    class FakeClient:
        def __init__(self, **kw):
            pass
        def results(self, search):
            return iter(fake_results)

    monkeypatch.setattr(arxiv_retriever.arxiv, "Client", FakeClient)

    # Skip file downloads in convert_to_paper
    monkeypatch.setattr(arxiv_retriever, "extract_text_from_html", lambda paper: None)
    monkeypatch.setattr(arxiv_retriever, "extract_text_from_pdf", lambda paper: None)
    monkeypatch.setattr(arxiv_retriever, "extract_text_from_tar", lambda paper: None)

    retriever = ArxivRetriever(config)
    papers = retriever.retrieve_papers()

    assert len(papers) == len(new_entries)
    assert set(p.title for p in papers) == set(e.title for e in new_entries)


def test_arxiv_retriever_historical_date_uses_metadata_only(config, monkeypatch):
    captured = {}
    fake_result = SimpleNamespace(
        title="Historical paper",
        authors=[SimpleNamespace(name="Test Author")],
        summary="Historical abstract",
        pdf_url="https://arxiv.org/pdf/2607.00001",
        entry_id="https://arxiv.org/abs/2607.00001",
        primary_category="cs.CV",
    )

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client"] = kwargs

        def results(self, search):
            captured["search"] = search
            return iter([fake_result])

    def fake_search(**kwargs):
        captured["search_kwargs"] = kwargs
        return SimpleNamespace(**kwargs)

    with open_dict(config):
        config.source.arxiv.date = "2026-07-01"
        config.source.arxiv.metadata_only = True
        config.source.arxiv.include_cross_list = True
        config.source.arxiv.conversion_delay_seconds = 0

    monkeypatch.setattr(arxiv_retriever.arxiv, "Client", FakeClient)
    monkeypatch.setattr(arxiv_retriever.arxiv, "Search", fake_search)
    monkeypatch.setattr(
        arxiv_retriever,
        "extract_text_from_tar",
        lambda _: pytest.fail("metadata-only retrieval must not download source archives"),
    )

    papers = ArxivRetriever(config).retrieve_papers()

    assert len(papers) == 1
    assert papers[0].full_text is None
    assert "cat:cs.CV" in captured["search_kwargs"]["query"]
    assert "submittedDate:[202607010000 TO 202607012359]" in captured["search_kwargs"]["query"]


def test_arxiv_retriever_rejects_invalid_historical_date(config):
    with open_dict(config):
        config.source.arxiv.date = "2026/07/01"

    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        ArxivRetriever(config)._retrieve_raw_papers()


def test_run_with_hard_timeout_returns_value():
    result = _run_with_hard_timeout(
        _sleep_and_return, ("done", 0.01), timeout=1, operation="test op", paper_title="paper"
    )
    assert result == "done"


def test_run_with_hard_timeout_returns_none_on_timeout(monkeypatch):
    warnings: list[str] = []
    monkeypatch.setattr(arxiv_retriever, "logger", SimpleNamespace(warning=warnings.append))
    result = _run_with_hard_timeout(
        _sleep_and_return, ("done", 1.0), timeout=0.01, operation="test op", paper_title="paper"
    )
    assert result is None
    assert "timed out" in warnings[0]


def test_run_with_hard_timeout_returns_none_on_failure(monkeypatch):
    warnings: list[str] = []
    monkeypatch.setattr(arxiv_retriever, "logger", SimpleNamespace(warning=warnings.append))
    result = _run_with_hard_timeout(
        _raise_runtime_error, (), timeout=1, operation="test op", paper_title="paper"
    )
    assert result is None
    assert "boom" in warnings[0]
