import json

import pytest

from zotero_arxiv_daily.weekly import load_daily_reports


def _write_daily(root, report_date):
    daily_dir = root / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "schemaVersion": 1,
        "type": "daily",
        "date": report_date,
        "papers": [{"title": f"Paper {report_date}"}],
    }
    (daily_dir / f"{report_date}.json").write_text(
        json.dumps(report), encoding="utf-8"
    )


def test_load_daily_reports_requires_and_orders_every_date(tmp_path):
    _write_daily(tmp_path, "2026-07-02")
    _write_daily(tmp_path, "2026-07-01")
    _write_daily(tmp_path, "2026-07-03")

    reports = load_daily_reports(tmp_path, "2026-07-01", "2026-07-03")

    assert [report["date"] for report in reports] == [
        "2026-07-01",
        "2026-07-02",
        "2026-07-03",
    ]


def test_load_daily_reports_rejects_missing_date(tmp_path):
    _write_daily(tmp_path, "2026-07-01")
    _write_daily(tmp_path, "2026-07-03")

    with pytest.raises(RuntimeError, match="2026-07-02"):
        load_daily_reports(tmp_path, "2026-07-01", "2026-07-03")


def test_load_daily_reports_rejects_more_than_seven_days(tmp_path):
    with pytest.raises(ValueError, match="7 calendar days"):
        load_daily_reports(tmp_path, "2026-07-01", "2026-07-08")
