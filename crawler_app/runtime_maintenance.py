from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import json
import re


APP_ROOT = Path(__file__).resolve().parent.parent


# runtime retention policy 정보를 담는 데이터 객체다.
@dataclass(frozen=True, slots=True)
class RuntimeRetentionPolicy:
    global_history_entries: int = 100
    job_history_entries: int = 30
    scheduled_log_days: int = 7
    scheduled_log_keep_per_job: int = 3
    scheduled_tmp_days: int = 1
    app_log_days: int = 14
    crawl_results_jsonl_lines: int = 1000
    flash_hours: int = 1


# runtime 파일 목록을 정리한다.
def cleanup_runtime_files(
    *,
    app_root: str | Path = APP_ROOT,
    state_dir: str | Path | None = None,
    history_path: str | Path | None = None,
    policy: RuntimeRetentionPolicy | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Trim machine-local runtime files without touching crawler outputs."""

    root = Path(app_root)
    policy = policy or RuntimeRetentionPolicy()
    current_time = _ensure_aware(now or datetime.now(timezone.utc))
    state_root = Path(state_dir) if state_dir is not None else root / "orchestration_state"
    global_history_path = Path(history_path) if history_path is not None else state_root / "run_history.json"

    summary = {
        "policy": asdict(policy),
        "trimmed_json_files": [],
        "trimmed_jsonl_files": [],
        "deleted_files": [],
        "errors": [],
    }

    _trim_json_array(global_history_path, policy.global_history_entries, summary)
    history_dir = global_history_path.parent / "history"
    if history_dir.exists():
        for path in history_dir.glob("*.json"):
            _trim_json_array(path, policy.job_history_entries, summary)

    _delete_old_files(root / "logs", ("*.log",), timedelta(days=policy.app_log_days), current_time, summary)
    _trim_jsonl(root / "logs" / "crawl_results.jsonl", policy.crawl_results_jsonl_lines, summary)
    _delete_old_scheduled_task_files(root / "runtime" / "scheduled-task", policy, current_time, summary)
    _delete_old_files(global_history_path.parent / "flash", ("*.json",), timedelta(hours=policy.flash_hours), current_time, summary)
    return summary


# trim json array 값을 계산해 반환한다.
def _trim_json_array(path: Path, keep_count: int, summary: dict[str, Any]) -> None:
    if keep_count <= 0 or not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        summary["errors"].append({"path": str(path), "error": str(exc)})
        return
    if not isinstance(payload, list) or len(payload) <= keep_count:
        return
    trimmed = payload[-keep_count:]
    _write_json(path, trimmed)
    summary["trimmed_json_files"].append({"path": str(path), "before": len(payload), "after": len(trimmed)})


# trim jsonl 값을 계산해 반환한다.
def _trim_jsonl(path: Path, keep_lines: int, summary: dict[str, Any]) -> None:
    if keep_lines <= 0 or not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        summary["errors"].append({"path": str(path), "error": str(exc)})
        return
    if len(lines) <= keep_lines:
        return
    trimmed = lines[-keep_lines:]
    path.write_text("\n".join(trimmed) + "\n", encoding="utf-8")
    summary["trimmed_jsonl_files"].append({"path": str(path), "before": len(lines), "after": len(trimmed)})


# old scheduled task 파일 목록을 삭제한다.
def _delete_old_scheduled_task_files(
    log_dir: Path,
    policy: RuntimeRetentionPolicy,
    now: datetime,
    summary: dict[str, Any],
) -> None:
    if not log_dir.exists():
        return
    _delete_old_files(log_dir, ("*.stdout.tmp", "*.stderr.tmp"), timedelta(days=policy.scheduled_tmp_days), now, summary)

    log_files = [path for path in log_dir.glob("*.log") if path.is_file()]
    keep_paths = _latest_scheduled_logs_by_job(log_files, policy.scheduled_log_keep_per_job)
    cutoff = now - timedelta(days=policy.scheduled_log_days)
    for path in log_files:
        if path in keep_paths:
            continue
        if _file_mtime(path) < cutoff:
            _delete_file(path, summary)


# latest scheduled logs job 값을 계산해 반환한다.
def _latest_scheduled_logs_by_job(paths: list[Path], keep_count: int) -> set[Path]:
    if keep_count <= 0:
        return set()
    grouped: dict[str, list[Path]] = {}
    for path in paths:
        grouped.setdefault(_scheduled_log_group(path), []).append(path)
    keep: set[Path] = set()
    for group_paths in grouped.values():
        keep.update(sorted(group_paths, key=_file_mtime, reverse=True)[:keep_count])
    return keep


# scheduled log group 값을 계산해 반환한다.
def _scheduled_log_group(path: Path) -> str:
    stem = path.stem
    match = re.match(r"^\d{8}_\d{6}-(.+)$", stem)
    return match.group(1) if match else stem


# old 파일 목록을 삭제한다.
def _delete_old_files(
    directory: Path,
    patterns: tuple[str, ...],
    max_age: timedelta,
    now: datetime,
    summary: dict[str, Any],
) -> None:
    if not directory.exists():
        return
    cutoff = now - max_age
    for pattern in patterns:
        for path in directory.glob(pattern):
            if path.is_file() and _file_mtime(path) < cutoff:
                _delete_file(path, summary)


# 파일을 삭제한다.
def _delete_file(path: Path, summary: dict[str, Any]) -> None:
    try:
        path.unlink()
        summary["deleted_files"].append(str(path))
    except FileNotFoundError:
        return
    except OSError as exc:
        summary["errors"].append({"path": str(path), "error": str(exc)})


# 파일 mtime 값을 계산해 반환한다.
def _file_mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


# aware가 준비된 상태인지 보장한다.
def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


# json를 파일에 기록한다.
def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(path)
