from __future__ import annotations

import json
import logging
from pathlib import Path

from crawler_app.base import CrawlResult
from crawler_app.runtime_maintenance import cleanup_runtime_files


# 파일/콘솔 출력용 logger를 구성한다.
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


# dict payload를 JSONL 로그 파일 끝에 추가한다.
def append_jsonl(log_dir: Path, filename: str, payload: dict) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / filename).open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload, ensure_ascii=False) + "\n")


# 크롤 결과를 로그 파일에 기록한다.
def log_result(log_dir: Path, result: CrawlResult) -> None:
    payload = result.to_dict()
    payload["data"] = [
        {
            "record_key": record.get("record_key"),
            "success": record.get("success"),
            "item_index": record.get("item_index"),
            "search_term": record.get("search_term"),
            "output_file": record.get("output_file"),
            "error": record.get("error"),
            "title": (record.get("extracts") or {}).get("title") if isinstance(record.get("extracts"), dict) else None,
        }
        for record in result.data
        if isinstance(record, dict)
    ]
    append_jsonl(log_dir, "crawl_results.jsonl", payload)
    try:
        cleanup_runtime_files(app_root=log_dir.parent)
    except Exception:
        return
