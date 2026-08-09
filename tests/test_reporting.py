from types import SimpleNamespace

import pytest

from tests.canned_responses import make_sample_paper
from zotero_arxiv_daily.reporting import (
    WEEKLY_SECTIONS,
    build_daily_report,
    build_weekly_report,
    daily_report_to_markdown,
    generate_weekly_analysis,
    render_weekly_email,
    write_daily_report,
    write_weekly_report,
)


def _daily_report():
    selected = make_sample_paper(
        title="<Vision Paper>",
        url="https://example.com/paper?a=1&b=2",
        score=9.1,
        tldr="【核心结论】有证据约束的中文分析。",
    )
    shortlist = [selected] + [
        make_sample_paper(title=f"Candidate {index}", score=8 - index / 10)
        for index in range(2, 11)
    ]
    return build_daily_report("2026-07-01", 489, shortlist, [selected])


def test_build_daily_report_records_top_ten_and_selected_analysis():
    report = _daily_report()

    assert report["candidateCount"] == 489
    assert report["shortlistCount"] == 10
    assert report["selectedCount"] == 1
    assert report["shortlist"][0]["selected"] is True
    assert report["shortlist"][1]["analysis"] is None
    assert report["papers"][0]["evidenceScope"] == "full_text"


def test_daily_report_markdown_contains_selection_trace():
    markdown = daily_report_to_markdown(_daily_report())

    assert "Top 10 筛选轨迹" in markdown
    assert "检索 489 篇" in markdown
    assert "【核心结论】" in markdown


def test_write_daily_report_creates_json_and_markdown(tmp_path):
    json_path, markdown_path = write_daily_report(tmp_path, _daily_report())

    assert json_path.exists()
    assert markdown_path.exists()
    assert '"schemaVersion": 1' in json_path.read_text(encoding="utf-8")
    assert "每日论文报告 2026-07-01" in markdown_path.read_text(encoding="utf-8")


def test_generate_weekly_analysis_uses_responses_api_and_validates_sections():
    summary = "\n".join(f"{section}\n有据可查的综合结论 [D01-P01]。" for section in WEEKLY_SECTIONS)
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(output_text=summary)

    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    result = generate_weekly_analysis(
        client,
        {
            "api_style": "responses",
            "weekly_max_output_tokens": 6000,
            "generation_kwargs": {"model": "gpt-5.6-sol", "max_output_tokens": 5000},
        },
        "2026-07-01",
        "2026-07-07",
        [_daily_report()],
    )

    assert result == summary
    assert captured["model"] == "gpt-5.6-sol"
    assert captured["max_output_tokens"] == 6000
    assert "[D01-P01]" in captured["input"]


def test_generate_weekly_analysis_rejects_missing_sections():
    client = SimpleNamespace(
        responses=SimpleNamespace(
            create=lambda **kwargs: SimpleNamespace(output_text="【本周概览】只有一节")
        )
    )

    with pytest.raises(RuntimeError, match="missing required sections"):
        generate_weekly_analysis(
            client,
            {
                "api_style": "responses",
                "generation_kwargs": {"model": "gpt-5.6-sol"},
            },
            "2026-07-01",
            "2026-07-07",
            [_daily_report()],
        )


def test_weekly_report_outputs_escape_generated_html(tmp_path):
    summary = "\n".join(
        f"{section}\n结论 [D01-P01]。" for section in WEEKLY_SECTIONS
    ) + "\n<script>alert(1)</script>"
    weekly = build_weekly_report(
        "2026-07-01", "2026-07-07", [_daily_report()], summary
    )

    html = render_weekly_email(weekly)
    json_path, markdown_path = write_weekly_report(tmp_path, weekly)

    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;Vision Paper&gt;" in html
    assert json_path.exists()
    assert markdown_path.exists()
    assert "证据索引" in markdown_path.read_text(encoding="utf-8")
