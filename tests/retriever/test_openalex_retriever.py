from omegaconf import open_dict

from zotero_arxiv_daily.retriever.openalex_retriever import OpenAlexRetriever
import zotero_arxiv_daily.retriever.openalex_retriever as openalex_retriever


def test_openalex_historical_retrieval_deduplicates_and_decodes_abstract(config, monkeypatch):
    calls = []
    work = {
        "id": "https://openalex.org/W123",
        "doi": "https://doi.org/10.1000/example",
        "title": "Historical vision paper",
        "authorships": [{"author": {"display_name": "Test Author"}}],
        "primary_location": {"landing_page_url": "https://arxiv.org/abs/2607.00001"},
        "best_oa_location": {"pdf_url": "https://arxiv.org/pdf/2607.00001"},
        "abstract_inverted_index": {"Vision": [0], "paper": [1]},
        "publication_date": "2026-07-01",
    }

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"results": [work]}

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()

    with open_dict(config):
        config.source.openalex.date = "2026-07-01"
        config.source.openalex.queries = ["computer vision", "object detection"]
        config.source.openalex.request_delay_seconds = 0
        config.source.openalex.conversion_delay_seconds = 0

    monkeypatch.setattr(openalex_retriever.requests, "get", fake_get)
    papers = OpenAlexRetriever(config).retrieve_papers()

    assert len(calls) == 2
    assert len(papers) == 1
    assert papers[0].title == "Historical vision paper"
    assert papers[0].abstract == "Vision paper"
    assert papers[0].authors == ["Test Author"]
    assert "from_publication_date:2026-07-01" in calls[0][1]["params"]["filter"]
    assert "locations.source.id:S4306400194" in calls[0][1]["params"]["filter"]
    assert calls[0][1]["params"]["mailto"] == "test@example.com"


def test_openalex_historical_retrieval_skips_missing_abstract(config, monkeypatch):
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"results": [{"id": "W1", "title": "No abstract"}]}

    with open_dict(config):
        config.source.openalex.date = "2026-07-01"
        config.source.openalex.queries = ["computer vision"]
        config.source.openalex.request_delay_seconds = 0
        config.source.openalex.conversion_delay_seconds = 0

    monkeypatch.setattr(openalex_retriever.requests, "get", lambda *args, **kwargs: FakeResponse())
    assert OpenAlexRetriever(config).retrieve_papers() == []
