from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from crawler_app.file_lock import FileLock, FileLockTimeout


APP_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUTS_ROOT = APP_ROOT / "outputs"
DEFAULT_KEEP_COUNT = 20
DEFAULT_ROLLUP_TIME = "12:52"
KST = timezone(timedelta(hours=9))


def rollup_workflow_records(
    *,
    outputs_root: str | Path = DEFAULT_OUTPUTS_ROOT,
    now: datetime | None = None,
    keep_count: int = DEFAULT_KEEP_COUNT,
    lock_timeout_seconds: float = 1.0,
    stale_lock_seconds: float = 300.0,
) -> dict[str, Any]:
    root = Path(outputs_root)
    current_time = _ensure_kst(now or datetime.now(KST))
    summary: dict[str, Any] = {
        "outputs_root": str(root),
        "rolled_count": 0,
        "deleted_old_count": 0,
        "rolled": [],
        "deleted_old": [],
        "skipped": [],
        "errors": [],
    }
    if not root.exists():
        summary["skipped"].append({"reason": "outputs_root_missing", "path": str(root)})
        return summary

    for source_path in sorted(root.rglob("workflow_records.json")):
        if not source_path.is_file() or _is_rollup_archive_path(root, source_path):
            continue
        try:
            with FileLock(source_path, timeout_seconds=lock_timeout_seconds, stale_seconds=stale_lock_seconds):
                if not source_path.exists():
                    summary["skipped"].append({"reason": "source_missing_after_lock", "path": str(source_path)})
                    continue
                archive_path = _archive_path_for_workflow_records(root, source_path, current_time)
                archive_path.parent.mkdir(parents=True, exist_ok=True)
                if archive_path.exists():
                    archive_path = _unique_archive_path(archive_path)
                _write_sorted_archive_and_remove_source(source_path, archive_path)
            summary["rolled_count"] += 1
            summary["rolled"].append({"source": str(source_path), "archive": str(archive_path)})
            deleted = _prune_rollup_archives(archive_path.parent, keep_count=keep_count)
            summary["deleted_old_count"] += len(deleted)
            summary["deleted_old"].extend(str(path) for path in deleted)
        except FileLockTimeout as exc:
            summary["skipped"].append({"reason": "lock_timeout", "path": str(source_path), "error": str(exc)})
        except OSError as exc:
            summary["errors"].append({"path": str(source_path), "error": str(exc)})
    return summary


def _archive_path_for_workflow_records(outputs_root: Path, source_path: Path, current_time: datetime) -> Path:
    stamp = current_time.strftime("%Y%m%d_%H%M%S")
    return source_path.parent / "rollup" / f"workflow_records_{stamp}.json"


def _write_sorted_archive_and_remove_source(source_path: Path, archive_path: Path) -> None:
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        source_path.replace(archive_path)
        return
    if isinstance(payload, dict):
        payload = _sort_workflow_records_payload_latest_first(payload)
        archive_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        source_path.unlink()
        return
    source_path.replace(archive_path)


def _sort_workflow_records_payload_latest_first(payload: dict[str, Any]) -> dict[str, Any]:
    records = payload.get("records")
    if not isinstance(records, list) or len(records) < 2:
        return payload
    sorted_records = _sort_records_latest_first([record for record in records if isinstance(record, dict)])
    if len(sorted_records) != len(records):
        return payload
    sorted_payload = dict(payload)
    sorted_payload["records"] = sorted_records
    sorted_payload["item_count"] = len(sorted_records)
    return sorted_payload


def _sort_records_latest_first(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed_records = [(index, record, _record_datetime(record)) for index, record in enumerate(records)]
    indexed_records.sort(
        key=lambda item: (
            0 if item[2] is not None else 1,
            -(item[2].timestamp() if item[2] is not None else 0),
            item[0],
        )
    )
    return [record for _, record, _ in indexed_records]


def _record_datetime(record: dict[str, Any]) -> datetime | None:
    field_paths = (
        ("pub_date",),
        ("published_at",),
        ("created_at",),
        ("crawled_at",),
        ("extracts", "pubDate"),
        ("extracts", "published_at"),
        ("extracts", "date"),
    )
    for field_path in field_paths:
        value: Any = record
        for key in field_path:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(key)
        parsed = _parse_datetime(value)
        if parsed is not None:
            return parsed
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    normalized = text
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
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


def _is_rollup_archive_path(outputs_root: Path, path: Path) -> bool:
    try:
        relative_parts = path.relative_to(outputs_root).parts
    except ValueError:
        return False
    return "rollup" in relative_parts[1:]


def _unique_archive_path(path: Path) -> Path:
    for index in range(2, 10_000):
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise OSError(f"Could not allocate unique rollup archive path: {path}")


def _prune_rollup_archives(directory: Path, *, keep_count: int) -> list[Path]:
    if keep_count <= 0:
        return []
    archives = sorted(
        [path for path in directory.glob("workflow_records_*.json") if path.is_file()],
        key=lambda path: (path.stat().st_mtime, path.name),
        reverse=True,
    )
    deleted: list[Path] = []
    for path in archives[keep_count:]:
        try:
            path.unlink()
            deleted.append(path)
        except FileNotFoundError:
            continue
    return deleted


def _ensure_kst(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=KST)
    return value.astimezone(KST)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Roll workflow_records.json files into dated archives.")
    parser.add_argument("--outputs-root", default=str(DEFAULT_OUTPUTS_ROOT))
    parser.add_argument("--keep-count", type=int, default=DEFAULT_KEEP_COUNT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    summary = rollup_workflow_records(outputs_root=args.outputs_root, keep_count=args.keep_count)
    print("WORKFLOW_RECORDS_ROLLUP_SUMMARY " + json.dumps(summary, ensure_ascii=False))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if summary.get("errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
