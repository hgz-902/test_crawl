from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from crawler_app.config_store import list_configs
from crawler_app.file_lock import FileLock
from crawler_app.news_grouping import build_article_clusters
from crawler_app.news_sentiment import analyze_unanalyzed_articles
from crawler_app.news_sqlite_store import (
    KST,
    all_article_group_dates,
    article_rows_for_grouping,
    clear_news_data,
    connect,
    default_db_path,
    init_db,
    rebuild_filter_options,
    replace_clusters,
    update_source_config_categories,
    upsert_article,
)


WORKFLOW_RECORDS_NAME = "workflow_records.json"
ROLLUP_GLOB = "workflow_records_*.json"
GOOGLE_PARSER_NAMES = {"google", "google_news_rss"}
NAVER_PARSER_NAMES = {"naver", "naver_news_api"}
DAUM_PARSER_NAMES = {"daum", "daum_news_api", "kakao_daum_web_search"}


# 적재 결과 요약을 담는 데이터 객체다.
@dataclass
class NewsIngestionSummary:
    db_path: str
    files_read: int = 0
    records_seen: int = 0
    articles_upserted: int = 0
    sentiments_written: int = 0
    group_dates: set[str] = field(default_factory=set)
    clusters_written: int = 0
    errors: list[str] = field(default_factory=list)
    lock_wait_seconds: float = 0.0
    total_duration_seconds: float = 0.0
    read_duration_seconds: float = 0.0
    sentiment_duration_seconds: float = 0.0
    grouping_duration_seconds: float = 0.0
    grouping_duration_by_date: dict[str, float] = field(default_factory=dict)
    grouping_scope: str = "touched_dates"
    grouping_scope_effective: str = "touched_dates"

    # CLI/API 로그에 쓸 dict로 변환한다.
    def to_dict(self) -> dict[str, Any]:
        return {
            "db_path": self.db_path,
            "files_read": self.files_read,
            "records_seen": self.records_seen,
            "articles_upserted": self.articles_upserted,
            "sentiments_written": self.sentiments_written,
            "group_dates": sorted(self.group_dates),
            "clusters_written": self.clusters_written,
            "errors": self.errors,
            "lock_wait_seconds": round(self.lock_wait_seconds, 4),
            "total_duration_seconds": round(self.total_duration_seconds, 4),
            "read_duration_seconds": round(self.read_duration_seconds, 4),
            "sentiment_duration_seconds": round(self.sentiment_duration_seconds, 4),
            "grouping_duration_seconds": round(self.grouping_duration_seconds, 4),
            "grouping_duration_by_date": {
                date: round(duration, 4) for date, duration in sorted(self.grouping_duration_by_date.items())
            },
            "grouping_scope": self.grouping_scope,
            "grouping_scope_effective": self.grouping_scope_effective,
        }


# 프로젝트 outputs를 SQLite 뉴스 UI DB로 적재하고 같은 날짜 기사 그룹핑을 갱신한다.
def sync_news_ui_database(
    *,
    project_root: str | Path,
    db_path: str | Path | None = None,
    outputs_root: str | Path | None = None,
    source_output_dirs: Iterable[str | Path] | None = None,
    rebuild: bool = False,
    progress: bool = False,
) -> NewsIngestionSummary:
    root = Path(project_root)
    database_path = Path(db_path or os.getenv("NEWS_UI_DB_PATH") or default_db_path(root))
    outputs = Path(outputs_root or root / "outputs")
    summary = NewsIngestionSummary(db_path=str(database_path))
    total_started = time.perf_counter()
    lock_started = time.perf_counter()
    lock_timeout = float(os.getenv("NEWS_UI_SYNC_LOCK_TIMEOUT_SECONDS") or "180")
    _progress(progress, f"waiting for DB lock: {database_path}")
    with FileLock(database_path, timeout_seconds=lock_timeout, stale_seconds=900, poll_seconds=0.2):
        summary.lock_wait_seconds = time.perf_counter() - lock_started
        _progress(progress, f"DB lock acquired after {summary.lock_wait_seconds:.2f}s")
        init_db(database_path)
        with connect(database_path) as conn:
            if rebuild:
                _progress(progress, "clearing existing news UI data")
                clear_news_data(conn)
            categories_by_config = _config_categories_by_name(root)
            _progress(progress, f"loaded config categories: {len(categories_by_config)} configs")
            read_started = time.perf_counter()
            record_files = _workflow_record_files(outputs, source_output_dirs=source_output_dirs)
            _progress(progress, f"workflow record files: {len(record_files)}")
            for file_index, records_file in enumerate(record_files, start=1):
                summary.files_read += 1
                _progress(progress, f"reading file {file_index}/{len(record_files)}: {records_file}")
                try:
                    payload = json.loads(records_file.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    summary.errors.append(f"{records_file}: {type(exc).__name__}: {exc}")
                    _progress(progress, f"skipped invalid file: {records_file} ({type(exc).__name__})")
                    continue
                config_name = _payload_config_name(payload, records_file)
                config_category = _payload_config_category(payload, config_name, categories_by_config)
                records = payload.get("records") if isinstance(payload, dict) else None
                if not isinstance(records, list):
                    _progress(progress, f"skipped file without records list: {records_file}")
                    continue
                for record_index, record in enumerate(records, start=1):
                    if not isinstance(record, dict):
                        continue
                    summary.records_seen += 1
                    article = _article_from_record(
                        record,
                        config_name=config_name,
                        config_category=config_category,
                        records_file=records_file,
                    )
                    if not article:
                        continue
                    upsert_article(conn, article)
                    summary.articles_upserted += 1
                    if article.get("group_date"):
                        summary.group_dates.add(str(article["group_date"]))
                    if progress and record_index % 100 == 0:
                        _progress(
                            progress,
                            f"processed {record_index}/{len(records)} records in {records_file.name}; "
                            f"articles_upserted={summary.articles_upserted}",
                        )
            updated_categories = update_source_config_categories(conn, categories_by_config)
            _progress(progress, f"backfilled source_config_category rows: {updated_categories}")
            rebuild_filter_options(conn)
            _progress(progress, "rebuilt filter options")
            summary.read_duration_seconds = time.perf_counter() - read_started
            sentiment_started = time.perf_counter()
            _progress(progress, "starting sentiment analysis")
            summary.sentiments_written = analyze_unanalyzed_articles(conn)
            summary.sentiment_duration_seconds = time.perf_counter() - sentiment_started
            _progress(
                progress,
                f"sentiment analysis done: written={summary.sentiments_written}, "
                f"elapsed={summary.sentiment_duration_seconds:.2f}s",
            )
            grouping_started = time.perf_counter()
            group_dates, effective_scope = _group_dates_for_scope(conn, summary.group_dates)
            summary.grouping_scope = _text(os.getenv("NEWS_GROUPING_SCOPE")) or "touched_dates"
            summary.grouping_scope_effective = effective_scope
            _progress(progress, f"starting grouping: {len(group_dates)} dates ({effective_scope})")
            for date_index, group_date in enumerate(group_dates, start=1):
                date_started = time.perf_counter()
                rows = article_rows_for_grouping(conn, group_date)
                _progress(progress, f"grouping date {date_index}/{len(group_dates)}: {group_date} ({len(rows)} rows)")
                assignments = build_article_clusters(rows, cache_conn=conn)
                replace_clusters(conn, group_date, assignments)
                summary.grouping_duration_by_date[group_date] = time.perf_counter() - date_started
                summary.clusters_written += len(assignments)
            summary.grouping_duration_seconds = time.perf_counter() - grouping_started
            _progress(progress, f"grouping done: clusters={summary.clusters_written}, elapsed={summary.grouping_duration_seconds:.2f}s")
    summary.total_duration_seconds = time.perf_counter() - total_started
    _write_last_sync_summary(database_path, summary)
    _progress(progress, f"sync done: elapsed={summary.total_duration_seconds:.2f}s")
    return summary


# 운영 scope에 맞춰 실제 그룹핑할 날짜 목록을 결정한다.
def _group_dates_for_scope(conn: Any, touched_dates: set[str]) -> tuple[list[str], str]:
    requested = _text(os.getenv("NEWS_GROUPING_SCOPE")).lower() or "touched_dates"
    if requested == "all_dates":
        return all_article_group_dates(conn), "all_dates"
    if requested == "incremental":
        return sorted(touched_dates), "touched_dates_incremental_safe"
    return sorted(touched_dates), "touched_dates"


# 실험/모니터링이 마지막 SQLite 동기화 소요 시간을 읽을 수 있도록 요약 파일을 남긴다.
def _write_last_sync_summary(database_path: Path, summary: NewsIngestionSummary) -> None:
    try:
        summary_path = database_path.parent / "last_sync_summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


# 단일 crawler output_dir만 뉴스 UI DB에 반영한다.
def sync_news_ui_output_dir(*, project_root: str | Path, output_dir: str | Path) -> NewsIngestionSummary:
    root = Path(project_root)
    raw_output_dir = Path(output_dir)
    source_dir = raw_output_dir if raw_output_dir.is_absolute() else root / raw_output_dir
    return sync_news_ui_database(project_root=root, source_output_dirs=[source_dir], rebuild=False)


def _progress(enabled: bool, message: str) -> None:
    if enabled:
        print(f"[news_ingestion] {now_progress()} {message}", flush=True)


def now_progress() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")


def _config_categories_by_name(project_root: Path) -> dict[str, str]:
    return {
        config.name: str(config.category or "")
        for config in list_configs(project_root / "configs")
    }


# workflow record 하나를 crawl_articles row로 정규화한다.
def _article_from_record(
    record: dict[str, Any],
    *,
    config_name: str,
    config_category: str,
    records_file: Path,
) -> dict[str, Any] | None:
    final_url = _record_text(record, "final_url", "url", "canonical_url")
    if not final_url:
        return None
    title = _record_text(record, "extract_title", "title")
    if not title:
        title = _record_text(record.get("extracts") if isinstance(record.get("extracts"), dict) else {}, "extract_title", "title")
    if not title:
        return None
    published = _parse_datetime(_record_text(record, "pub_date", "published_at", "pubDate"))
    now = datetime.now(KST)
    first_seen = published or _file_mtime(records_file) or now
    group_date = (published or first_seen).astimezone(KST).date().isoformat()
    crawl_date = first_seen.astimezone(KST).date().isoformat()
    source_site = _source_site(record, final_url, config_name)
    canonical_url = final_url.strip()
    article_id = _article_id(source_site, canonical_url)
    return {
        "article_id": article_id,
        "record_key": _record_text(record, "record_key"),
        "source_site": source_site,
        "source_config_name": config_name,
        "source_config_category": config_category,
        "canonical_url": canonical_url,
        "title": title,
        "published_at": _format_dt(published),
        "first_seen_at": _format_dt(first_seen),
        "last_seen_at": _format_dt(now),
        "created_at": _format_dt(first_seen),
        "updated_at": _format_dt(now),
        "is_active": True,
        "crawl_date": crawl_date,
        "group_date": group_date,
        "filter_term": _record_text(record, "filter_term"),
    }


# outputs 아래 workflow_records.json 및 rollup 파일을 찾는다.
def _workflow_record_files(outputs_root: Path, *, source_output_dirs: Iterable[str | Path] | None) -> list[Path]:
    roots: list[Path]
    if source_output_dirs:
        roots = []
        for raw in source_output_dirs:
            path = Path(raw)
            roots.append(path if path.is_absolute() else outputs_root / path)
    else:
        roots = [outputs_root]
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        files.extend(sorted(root.rglob(WORKFLOW_RECORDS_NAME)))
        files.extend(sorted(root.rglob(ROLLUP_GLOB)))
    return [path for path in files if path.is_file() and _is_filter_workflow_record(path)]


# filter 하위의 workflow record 파일만 적재 대상으로 본다.
def _is_filter_workflow_record(path: Path) -> bool:
    lowered_parts = {part.lower() for part in path.parts}
    return "filter" in lowered_parts and "tran" not in lowered_parts


# payload 또는 경로에서 config/source 이름을 결정한다.
def _payload_config_name(payload: Any, records_file: Path) -> str:
    if isinstance(payload, dict):
        for key in ("config_name", "source_config_name", "source_name"):
            value = _text(payload.get(key))
            if value:
                return value
    try:
        outputs_index = [part.lower() for part in records_file.parts].index("outputs")
        return records_file.parts[outputs_index + 1]
    except (ValueError, IndexError):
        return records_file.parent.name


def _payload_config_category(payload: Any, config_name: str, categories_by_config: dict[str, str]) -> str:
    if isinstance(payload, dict):
        value = _text(payload.get("category"))
        if value:
            return value
    return categories_by_config.get(config_name, "")


# record와 URL에서 UI 표시용 source_site 값을 결정한다.
def _source_site(record: dict[str, Any], final_url: str, config_name: str) -> str:
    parser_name = _record_parser_name(record)
    if parser_name in GOOGLE_PARSER_NAMES:
        return (
            _record_text(record, "source")
            or _domain(_record_text(record, "source_url"))
            or _domain(final_url)
            or config_name
            or "unknown"
        )
    if parser_name in NAVER_PARSER_NAMES:
        return _source_domain_from_record(record, final_url, prefer_original=True) or config_name or "unknown"
    if parser_name in DAUM_PARSER_NAMES:
        return (
            _source_domain_from_record(record, final_url, prefer_original=True)
            or _record_text(record, "source_name")
            or config_name
            or "unknown"
        )
    return config_name or "unknown"


# API item 안에서 언론사를 구분할 수 있는 도메인을 찾는다.
def _source_domain_from_record(record: dict[str, Any], final_url: str, *, prefer_original: bool) -> str:
    platform_domains = {
        "n.news.naver.com",
        "news.naver.com",
        "v.daum.net",
        "news.daum.net",
        "m.media.daum.net",
    }
    keys = ("originallink", "source_url", "source_domain", "detail_url", "link", "url") if prefer_original else ()
    for key in keys:
        value = _record_text(record, key)
        domain = _domain(value) if "://" in value else _text(value).lower()
        if domain and domain not in platform_domains:
            return domain
    fallback_domain = _domain(final_url)
    if fallback_domain not in platform_domains:
        return fallback_domain
    return ""


# workflow/parser record에서 수집 방식 이름을 정규화한다.
def _record_parser_name(record: dict[str, Any]) -> str:
    extracts = record.get("extracts") if isinstance(record.get("extracts"), dict) else {}
    for value in (
        record.get("parser_name"),
        extracts.get("parser_name"),
        extracts.get("source_provider"),
        extracts.get("source_api"),
    ):
        text = _text(value).lower()
        if text:
            return text
    return ""


# URL에서 host를 정규화한다.
def _domain(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if "@" in host:
        host = host.rsplit("@", 1)[-1]
    return host.split(":", 1)[0]


# record나 nested dict에서 첫 번째 텍스트 값을 찾는다.
def _record_text(record: Any, *keys: str) -> str:
    if not isinstance(record, dict):
        return ""
    for key in keys:
        value = record.get(key)
        if value is None and key == "pub_date":
            value = record.get("pubDate")
        text = _text(value)
        if text:
            return text
    extracts = record.get("extracts")
    if isinstance(extracts, dict):
        for key in keys:
            text = _text(extracts.get(key))
            if text:
                return text
    return ""


# 다양한 기사 날짜 문자열을 KST datetime으로 파싱한다.
def _parse_datetime(value: str) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=KST)
        return parsed.astimezone(KST)
    except ValueError:
        pass
    try:
        parsed = parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=KST)
        return parsed.astimezone(KST)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


# 파일 수정 시간을 KST datetime으로 반환한다.
def _file_mtime(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).astimezone(KST)
    except OSError:
        return None


# article_id 생성 규칙을 한 곳에 고정한다.
def _article_id(source_site: str, canonical_url: str) -> str:
    seed = f"{source_site.strip().lower()}|{canonical_url.strip()}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


# datetime을 SQLite/API 문자열로 변환한다.
def _format_dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")


# 값에서 공백 제거 문자열을 얻는다.
def _text(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item).strip() for item in value if str(item or "").strip())
    return str(value or "").strip()


# CLI 인자를 구성한다.
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build or update the local SQLite news UI database.")
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--outputs-root", default="")
    parser.add_argument("--db-path", default="")
    parser.add_argument("--source-output-dir", action="append", default=[])
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--progress", action="store_true")
    return parser


# CLI에서 workflow_records 적재와 사전 그룹핑을 실행한다.
def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    summary = sync_news_ui_database(
        project_root=args.project_root,
        db_path=args.db_path or None,
        outputs_root=args.outputs_root or None,
        source_output_dirs=args.source_output_dir or None,
        rebuild=args.rebuild,
        progress=args.progress,
    )
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
