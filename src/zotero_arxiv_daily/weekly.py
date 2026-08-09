import json
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import dotenv
import hydra
from loguru import logger
from omegaconf import DictConfig
from openai import OpenAI

from zotero_arxiv_daily.reporting import (
    build_weekly_report,
    generate_weekly_analysis,
    render_weekly_email,
    write_weekly_report,
)
from zotero_arxiv_daily.utils import send_email


def load_daily_reports(
    input_root: str | Path, start_date: str, end_date: str
) -> list[dict]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if end < start:
        raise ValueError("WEEKLY_END_DATE must not be earlier than WEEKLY_START_DATE")
    expected_dates = [
        (start + timedelta(days=offset)).isoformat()
        for offset in range((end - start).days + 1)
    ]
    if len(expected_dates) > 7:
        raise ValueError("A weekly report is limited to 7 calendar days")

    daily_dir = Path(input_root) / "daily"
    reports_by_date = {}
    for path in daily_dir.glob("*.json"):
        report = json.loads(path.read_text(encoding="utf-8"))
        report_date = report.get("date")
        if report.get("type") == "daily" and report_date in expected_dates:
            if report_date in reports_by_date:
                raise ValueError(f"Duplicate daily report for {report_date}")
            reports_by_date[report_date] = report

    missing = [report_date for report_date in expected_dates if report_date not in reports_by_date]
    if missing:
        raise RuntimeError(f"Missing daily report artifacts: {', '.join(missing)}")
    return [reports_by_date[report_date] for report_date in expected_dates]


def configure_logging(debug: bool) -> None:
    logger.remove()
    logger.add(
        sys.stdout,
        level="DEBUG" if debug else "INFO",
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
    )
    for logger_name in logging.root.manager.loggerDict:
        if "zotero_arxiv_daily" not in logger_name:
            logging.getLogger(logger_name).setLevel(logging.WARNING)


@hydra.main(version_base=None, config_path="../../config", config_name="default")
def main(config: DictConfig) -> None:
    dotenv.load_dotenv()
    start_date = os.environ["WEEKLY_START_DATE"]
    end_date = os.environ["WEEKLY_END_DATE"]
    input_root = os.environ.get("WEEKLY_INPUT_DIR", "reports")
    output_root = os.environ.get("WEEKLY_OUTPUT_DIR", input_root)
    configure_logging(bool(config.executor.debug))

    daily_reports = load_daily_reports(input_root, start_date, end_date)
    paper_count = sum(len(report.get("papers", [])) for report in daily_reports)
    if paper_count == 0:
        raise RuntimeError("Weekly report artifacts do not contain selected papers")
    logger.info(
        f"Generating weekly synthesis for {start_date} through {end_date} "
        f"from {paper_count} archived paper analyses"
    )

    client = OpenAI(
        api_key=config.llm.api.key,
        base_url=config.llm.api.base_url,
        timeout=float(config.llm.get("weekly_timeout_seconds", 600)),
        max_retries=int(config.llm.get("weekly_max_retries", 2)),
    )
    summary = generate_weekly_analysis(
        client, config.llm, start_date, end_date, daily_reports
    )
    report = build_weekly_report(start_date, end_date, daily_reports, summary)
    write_weekly_report(output_root, report)
    subject = f"计算机视觉论文周报 {start_date.replace('-', '/')}-{end_date.replace('-', '/')}"
    send_email(config, render_weekly_email(report), subject=subject)
    logger.info("Weekly email sent successfully")


if __name__ == "__main__":
    main()
