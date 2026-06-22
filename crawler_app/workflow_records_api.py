from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any


KST = timezone(timedelta(hours=9))
MAX_PAGE_SIZE = 100
DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20
ROLLUP_FILE_RE = re.compile(r"^workflow_records_(?P<stamp>\d{8})_\d{6}(?:_\d+)?\.json$")
SAFE_SOURCE_NAME_RE = re.compile(r"^[^\\/:\*\?\"<>\|]+$")


# workflow records 쿼리 정보를 담는 데이터 객체다.
@dataclass(frozen=True)
class WorkflowRecordsQuery:
    date_value: date | None
    from_date: date | None
    to_date: date | None
    source_name: str
    page: int
    page_size: int
    sort_by: str
    sort_order: str


# workflow records 조회 요청을 페이지네이션 응답 형태로 만든다.
def build_workflow_records_response(payload: dict[str, Any], *, outputs_root: str | Path, now: datetime | None = None) -> dict[str, Any]:
    query = parse_workflow_records_query(payload)
    records = query_workflow_records(query, outputs_root=outputs_root, now=now)
    total_count = len(records)
    start_index = (query.page - 1) * query.page_size
    end_index = start_index + query.page_size
    return {
        "totalCount": total_count,
        "page": query.page,
        "pageSize": query.page_size,
        "items": records[start_index:end_index],
    }


# workflow records 쿼리를 파싱한다.
def parse_workflow_records_query(payload: dict[str, Any]) -> WorkflowRecordsQuery:
    if not isinstance(payload, dict):
        raise ValueError("request body must be an object")

    raw_date = _text(payload.get("date"))
    raw_from_date = _text(payload.get("from_date"))
    raw_to_date = _text(payload.get("to_date"))
    if raw_date and (raw_from_date or raw_to_date):
        raise ValueError("use either date or from_date/to_date, not both")

    date_value = _parse_ymd(raw_date, field_name="date") if raw_date else None
    from_date = _parse_ymd(raw_from_date, field_name="from_date") if raw_from_date else None
    to_date = _parse_ymd(raw_to_date, field_name="to_date") if raw_to_date else None
    if (from_date and not to_date) or (to_date and not from_date):
        raise ValueError("from_date and to_date must be provided together")
    if from_date and to_date and from_date > to_date:
        raise ValueError("from_date must be earlier than or equal to to_date")

    source_name = _text(payload.get("source_name"))
    if source_name and not SAFE_SOURCE_NAME_RE.match(source_name):
        raise ValueError("source_name contains invalid path characters")

    page = _positive_int(payload.get("page"), default=DEFAULT_PAGE, field_name="page")
    page_size = _positive_int(payload.get("page_size"), default=DEFAULT_PAGE_SIZE, field_name="page_size")
    if page_size > MAX_PAGE_SIZE:
        page_size = MAX_PAGE_SIZE

    sort_by = _normalize_sort_by(_text(payload.get("sort_by")) or "pub_date")
    sort_order = (_text(payload.get("sort_order")) or "desc").lower()
    if sort_order not in {"asc", "desc"}:
        raise ValueError("sort_order must be asc or desc")

    return WorkflowRecordsQuery(
        date_value=date_value,
        from_date=from_date,
        to_date=to_date,
        source_name=source_name,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )


# workflow records를 조회한다.
def query_workflow_records(query: WorkflowRecordsQuery, *, outputs_root: str | Path, now: datetime | None = None) -> list[dict[str, Any]]:
    root = Path(outputs_root)
    if not root.exists():
        return []
    today = (now or datetime.now(KST)).astimezone(KST).date()
    start_date, end_date = _query_date_range(query, today=today)
    source_dirs = _source_dirs(root, query.source_name)

    records: list[dict[str, Any]] = []
    for source_dir in source_dirs:
        filter_dir = source_dir / "filter"
        if start_date <= today <= end_date:
            records.extend(_read_records(filter_dir / "workflow_records.json"))
        rollup_dir = filter_dir / "rollup"
        for archive in sorted(rollup_dir.glob("workflow_records_*.json")) if rollup_dir.exists() else []:
            archive_date = _rollup_file_date(archive)
            if archive_date is None or archive_date == today:
                continue
            if start_date <= archive_date <= end_date:
                records.extend(_read_records(archive))
    return _sort_records(records, sort_by=query.sort_by, sort_order=query.sort_order)


# 날짜 range를 조회한다.
def _query_date_range(query: WorkflowRecordsQuery, *, today: date) -> tuple[date, date]:
    if query.date_value:
        return query.date_value, query.date_value
    if query.from_date and query.to_date:
        return query.from_date, query.to_date
    return today, today


# source dirs 값을 계산해 반환한다.
def _source_dirs(root: Path, source_name: str) -> list[Path]:
    if source_name:
        source_dir = root / source_name
        try:
            source_dir.relative_to(root)
        except ValueError:
            return []
        return [source_dir] if source_dir.is_dir() else []
    return sorted(path for path in root.iterdir() if path.is_dir())


# rollup 파일 날짜 값을 계산해 반환한다.
def _rollup_file_date(path: Path) -> date | None:
    match = ROLLUP_FILE_RE.match(path.name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group("stamp"), "%Y%m%d").date()
    except ValueError:
        return None


# records를 읽어 반환한다.
def _read_records(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    raw_records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(raw_records, list):
        return []
    return [dict(record) for record in raw_records if isinstance(record, dict)]


# records를 정렬한다.
def _sort_records(records: list[dict[str, Any]], *, sort_by: str, sort_order: str) -> list[dict[str, Any]]:
    indexed = [(index, record, _sort_value(record, sort_by)) for index, record in enumerate(records)]
    present = [item for item in indexed if item[2] is not None]
    missing = [item for item in indexed if item[2] is None]
    present.sort(key=lambda item: (_comparable_sort_value(item[2]), item[0]), reverse=sort_order == "desc")
    missing.sort(key=lambda item: item[0])
    indexed = present + missing
    return [record for _, record, _ in indexed]


# value를 정렬한다.
def _sort_value(record: dict[str, Any], sort_by: str) -> Any:
    value = record.get(sort_by)
    if sort_by == "pub_date":
        return _parse_record_datetime(value)
    if value is None:
        return None
    return str(value)


# comparable sort value 값을 계산해 반환한다.
def _comparable_sort_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.timestamp()
    return value


# record 일시를 파싱한다.
def _parse_record_datetime(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    try:
        parsed = parsedate_to_datetime(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


# sort를 표준 형태로 정규화한다.
def _normalize_sort_by(value: str) -> str:
    aliases = {
        "published_at": "pub_date",
        "publishedAt": "pub_date",
        "title": "extract_title",
        "url": "final_url",
    }
    normalized = aliases.get(value, value)
    allowed = {"record_key", "search_term", "filter_term", "extract_title", "description", "pub_date", "final_url"}
    if normalized not in allowed:
        raise ValueError(f"unsupported sort_by: {value}")
    return normalized


# ymd를 파싱한다.
def _parse_ymd(value: str, *, field_name: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field_name} must use YYYY-MM-DD") from exc


# positive 정수 값을 계산해 반환한다.
def _positive_int(value: Any, *, default: int, field_name: str) -> int:
    if value is None or str(value).strip() == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a positive integer") from exc
    if parsed < 1:
        raise ValueError(f"{field_name} must be a positive integer")
    return parsed


# 텍스트 값을 계산해 반환한다.
def _text(value: Any) -> str:
    return str(value or "").strip()
