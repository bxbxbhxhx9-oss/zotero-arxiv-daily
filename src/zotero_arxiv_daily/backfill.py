import logging
import os
import sys
from datetime import date, timedelta
from time import sleep

import dotenv
import hydra
from loguru import logger
from omegaconf import DictConfig, open_dict

from zotero_arxiv_daily.executor import Executor


def parse_date_range(start_value: str, end_value: str) -> list[date]:
    start = date.fromisoformat(start_value)
    end = date.fromisoformat(end_value)
    if end < start:
        raise ValueError("BACKFILL_END_DATE must not be earlier than BACKFILL_START_DATE")
    dates = [start + timedelta(days=offset) for offset in range((end - start).days + 1)]
    if len(dates) > 31:
        raise ValueError("A backfill run is limited to 31 calendar days")
    return dates


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {value!r}")


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
    dates = parse_date_range(
        os.environ.get("BACKFILL_START_DATE", "2026-07-01"),
        os.environ.get("BACKFILL_END_DATE", "2026-07-31"),
    )
    max_papers = int(os.environ.get("BACKFILL_MAX_PAPERS", "5"))
    max_results = int(os.environ.get("BACKFILL_MAX_RESULTS", "500"))
    email_delay = float(os.environ.get("BACKFILL_EMAIL_DELAY_SECONDS", "8"))
    send_empty = parse_bool(os.environ.get("BACKFILL_SEND_EMPTY", "false"))

    if not 1 <= max_papers <= 20:
        raise ValueError("BACKFILL_MAX_PAPERS must be between 1 and 20")
    if max_results < max_papers:
        raise ValueError("BACKFILL_MAX_RESULTS must be at least BACKFILL_MAX_PAPERS")
    if email_delay < 0:
        raise ValueError("BACKFILL_EMAIL_DELAY_SECONDS must not be negative")

    with open_dict(config):
        config.source.openalex.date = dates[0].isoformat()
        config.source.openalex.max_results = max_results
        config.executor.source = ["openalex"]
        config.executor.max_paper_num = max_papers
        config.executor.send_empty = send_empty

    configure_logging(bool(config.executor.debug))
    logger.info(
        f"Starting arXiv backfill for {dates[0]} through {dates[-1]} "
        f"with at most {max_papers} papers per day"
    )

    executor = Executor(config)
    corpus = executor.filter_corpus(executor.fetch_zotero_corpus())
    if not corpus:
        raise RuntimeError("No Zotero papers are available for reranking")

    emails_sent = 0
    papers_sent = 0
    failures: list[tuple[date, str]] = []
    for index, report_date in enumerate(dates):
        with open_dict(config):
            config.source.openalex.date = report_date.isoformat()
        logger.info(f"Backfilling Daily arXiv {report_date}")
        try:
            paper_count = executor.run(corpus=corpus, report_date=report_date.isoformat())
            papers_sent += paper_count
            if paper_count > 0 or send_empty:
                emails_sent += 1
        except Exception as exc:
            logger.exception(f"Backfill failed for {report_date}: {exc}")
            failures.append((report_date, str(exc)))
        if index < len(dates) - 1 and email_delay > 0:
            sleep(email_delay)

    logger.info(
        f"Backfill complete: {papers_sent} papers across {emails_sent} emails; "
        f"{len(failures)} failed dates"
    )
    if failures:
        details = "; ".join(f"{day}: {error}" for day, error in failures)
        raise RuntimeError(f"Backfill failed for {len(failures)} dates: {details}")


if __name__ == "__main__":
    main()
