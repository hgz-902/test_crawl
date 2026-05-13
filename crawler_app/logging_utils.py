from __future__ import annotations

import json
import logging
from pathlib import Path

from crawler_app.base import CrawlResult


def configure_logger(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("crawler_orchestrator")

    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_dir / "orchestrator.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger


def append_jsonl(log_dir: Path, filename: str, payload: dict) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / filename).open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload, ensure_ascii=False) + "\n")


def log_result(log_dir: Path, result: CrawlResult) -> None:
    append_jsonl(log_dir, "crawl_results.jsonl", result.to_dict())
