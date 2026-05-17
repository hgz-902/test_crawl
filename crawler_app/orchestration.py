from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Callable, Iterable
import json
import os
import re
import smtplib
import uuid

from crawler_app.config_store import CONFIG_DIR, config_file_stem, list_configs
from crawler_app.workflow import load_workflow_config, run_workflow_config


APP_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE_DIR = APP_ROOT / "orchestration_state"
DEFAULT_SETTINGS_PATH = DEFAULT_STATE_DIR / "settings.json"
DEFAULT_HISTORY_PATH = DEFAULT_STATE_DIR / "run_history.json"
DEFAULT_KEYWORDS = ["SK", "최태원"]
DEFAULT_RECIPIENTS = ["bloodknihts@gmail.com", "superknihts@nate.com"]
DEFAULT_SENDER = "bloodknihts@gmail.com"
INTERVAL_UNITS = {"minutes", "hours", "days"}

Runner = Callable[[Path, Callable[[dict[str, Any]], dict[str, Any]]], Any]


@dataclass(slots=True)
class RegisteredJob:
    job_id: str
    config_name: str
    config_path: str
    output_dir: str
    search_terms: list[str] = field(default_factory=list)
    filter_terms: list[str] = field(default_factory=list)


@dataclass(slots=True)
class JobRunResult:
    job_id: str
    config_name: str
    config_path: str
    status: str
    success: bool
    items_count: int
    records: list[dict[str, Any]] = field(default_factory=list)
    duplicate_key: str | None = None
    duplicate_record: dict[str, Any] | None = None
    keyword_matches: list[dict[str, Any]] = field(default_factory=list)
    notification: dict[str, Any] | None = None
    error: str | None = None
    started_at: str = ""
    finished_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BatchRunResult:
    batch_id: str
    status: str
    total: int
    succeeded: int
    failed: int
    duplicate_stopped: int
    skipped_not_due: int
    results: list[JobRunResult]
    started_at: str
    finished_at: str


class OrchestrationStateStore:
    def __init__(
        self,
        settings_path: str | Path = DEFAULT_SETTINGS_PATH,
        history_path: str | Path = DEFAULT_HISTORY_PATH,
    ) -> None:
        self.settings_path = Path(settings_path)
        self.history_path = Path(history_path)

    def load_settings(self) -> dict[str, Any]:
        payload = _read_json_object(self.settings_path)
        settings = default_settings()
        if payload:
            settings.update({key: value for key, value in payload.items() if key != "jobs"})
            if isinstance(payload.get("jobs"), dict):
                settings["jobs"] = payload["jobs"]
        return normalize_settings(settings)

    def save_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        normalized = normalize_settings(settings)
        normalized["updated_at"] = utc_timestamp()
        _write_json(self.settings_path, normalized)
        return normalized

    def load_history(self, limit: int | None = None) -> list[dict[str, Any]]:
        payload = _read_json(self.history_path, default=[])
        history = payload if isinstance(payload, list) else []
        if limit is not None and limit >= 0:
            return history[-limit:]
        return history

    def append_history(self, entry: dict[str, Any]) -> None:
        history = self.load_history()
        history.append(entry)
        _write_json(self.history_path, history)


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_sender() -> str:
    return os.environ.get("SMTP_FROM") or DEFAULT_SENDER


def default_settings() -> dict[str, Any]:
    now = utc_timestamp()
    return {
        "keywords": list(DEFAULT_KEYWORDS),
        "recipients": list(DEFAULT_RECIPIENTS),
        "sender": default_sender(),
        "jobs": {},
        "created_at": now,
        "updated_at": now,
    }


def normalize_settings(settings: dict[str, Any]) -> dict[str, Any]:
    keywords = _clean_string_list(settings.get("keywords")) or list(DEFAULT_KEYWORDS)
    recipients = _clean_string_list(settings.get("recipients")) or list(DEFAULT_RECIPIENTS)
    jobs = settings.get("jobs") if isinstance(settings.get("jobs"), dict) else {}
    normalized_jobs: dict[str, Any] = {}
    for raw_job_id, raw_job in jobs.items():
        job_id = config_file_stem(str(raw_job_id))
        if not isinstance(raw_job, dict):
            raw_job = {}
        normalized_jobs[job_id] = {
            "enabled": bool(raw_job.get("enabled", False)),
            "interval": normalize_interval(raw_job.get("interval")),
            "last_run_at": _clean_optional_timestamp(raw_job.get("last_run_at")),
            "next_run_at": _clean_optional_timestamp(raw_job.get("next_run_at")),
            "last_status": str(raw_job.get("last_status") or ""),
        }

    return {
        "keywords": keywords,
        "recipients": recipients,
        "sender": str(settings.get("sender") or default_sender()),
        "jobs": normalized_jobs,
        "created_at": str(settings.get("created_at") or utc_timestamp()),
        "updated_at": str(settings.get("updated_at") or utc_timestamp()),
    }


def normalize_interval(interval: Any) -> dict[str, Any]:
    if not isinstance(interval, dict):
        interval = {}
    value = interval.get("value", 1)
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = 1
    if value <= 0:
        value = 1
    unit = str(interval.get("unit") or "hours").strip().lower()
    if unit not in INTERVAL_UNITS:
        unit = "hours"
    return {"value": value, "unit": unit}


def registered_config_jobs(config_dir: str | Path = CONFIG_DIR) -> list[RegisteredJob]:
    jobs: list[RegisteredJob] = []
    for summary in list_configs(config_dir):
        jobs.append(
            RegisteredJob(
                job_id=Path(summary.path).stem,
                config_name=summary.name,
                config_path=str(Path(summary.path)),
                output_dir=summary.output_dir,
                search_terms=list(summary.search_terms),
                filter_terms=list(summary.filter_terms),
            )
        )
    return jobs


def sync_settings_jobs(settings: dict[str, Any], jobs: Iterable[RegisteredJob]) -> dict[str, Any]:
    settings = normalize_settings(settings)
    configured_jobs = settings.setdefault("jobs", {})
    for job in jobs:
        configured_jobs.setdefault(
            job.job_id,
            {"enabled": False, "interval": {"value": 1, "unit": "hours"}},
        )
        configured_jobs[job.job_id]["interval"] = normalize_interval(configured_jobs[job.job_id].get("interval"))
        configured_jobs[job.job_id]["enabled"] = bool(configured_jobs[job.job_id].get("enabled", False))
    return settings


def run_batch(
    selected_job_ids: Iterable[str],
    *,
    store: OrchestrationStateStore | None = None,
    config_dir: str | Path = CONFIG_DIR,
    runner: Runner | None = None,
    snapshot_roots: Iterable[str | Path] | None = None,
    send_notifications: bool = True,
    force_due: bool = False,
    allow_email_send: bool = False,
) -> BatchRunResult:
    store = store or OrchestrationStateStore()
    settings = sync_settings_jobs(store.load_settings(), registered_config_jobs(config_dir))
    jobs_by_id = {job.job_id: job for job in registered_config_jobs(config_dir)}
    selected = [config_file_stem(job_id) for job_id in selected_job_ids]
    selected = [job_id for job_id in selected if job_id in jobs_by_id]

    if snapshot_roots is not None:
        shared_index = build_duplicate_index(list(snapshot_roots))
        duplicate_indexes = {job_id: set(shared_index) for job_id in selected}
    else:
        duplicate_indexes = {
            job_id: build_duplicate_index(_snapshot_roots_for_jobs([jobs_by_id[job_id]]))
            for job_id in selected
        }
    batch_id = uuid.uuid4().hex
    started_at = utc_timestamp()
    results: list[JobRunResult] = []

    for job_id in selected:
        job = jobs_by_id[job_id]
        due, due_metadata = _job_due_status(settings["jobs"].get(job_id, {}))
        if not force_due and not due:
            results.append(_skipped_not_due_result(job, due_metadata))
            continue

        duplicate_index = duplicate_indexes.setdefault(job_id, set())
        result = run_job(
            job,
            settings=settings,
            duplicate_index=duplicate_index,
            runner=runner,
            send_notifications=send_notifications,
            allow_email_send=allow_email_send,
        )
        results.append(result)
        for record in result.records:
            key = duplicate_key_for_record(record)
            if key:
                duplicate_index.add(key)
        _update_job_schedule_after_run(settings, job_id, result)

    finished_at = utc_timestamp()
    succeeded = sum(1 for result in results if result.status == "succeeded")
    duplicate_stopped = sum(1 for result in results if result.status == "duplicate_stopped")
    skipped_not_due = sum(1 for result in results if result.status == "skipped_not_due")
    failed = sum(1 for result in results if result.status == "failed")
    status = "failed" if failed else "completed"
    batch = BatchRunResult(
        batch_id=batch_id,
        status=status,
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        duplicate_stopped=duplicate_stopped,
        skipped_not_due=skipped_not_due,
        results=results,
        started_at=started_at,
        finished_at=finished_at,
    )
    store.save_settings(settings)
    store.append_history(batch_to_dict(batch))
    return batch


def settings_for_registered_jobs(
    *,
    store: OrchestrationStateStore | None = None,
    config_dir: str | Path = CONFIG_DIR,
) -> tuple[dict[str, Any], list[RegisteredJob]]:
    store = store or OrchestrationStateStore()
    jobs = registered_config_jobs(config_dir)
    settings = sync_settings_jobs(store.load_settings(), jobs)
    return settings, jobs


def run_job(
    job: RegisteredJob,
    *,
    settings: dict[str, Any],
    duplicate_index: set[str],
    runner: Runner | None = None,
    send_notifications: bool = True,
    allow_email_send: bool = False,
) -> JobRunResult:
    started_at = utc_timestamp()
    seen: set[str] = set()
    duplicate: dict[str, Any] = {}

    def record_policy(record: dict[str, Any]) -> dict[str, Any]:
        key = duplicate_key_for_record(record)
        if key and (key in duplicate_index or key in seen):
            duplicate.update({"key": key, "record": record})
            return {
                "include": False,
                "stop": True,
                "reason": "duplicate_stopped",
                "metadata": {"duplicate_key": key},
            }
        if key:
            seen.add(key)
        return {"include": True, "stop": False}

    try:
        raw_result = (runner or default_workflow_runner)(Path(job.config_path), record_policy)
        normalized = normalize_runner_result(raw_result)
        records = normalized["records"]
        keyword_matches = records_matching_keywords(records, settings.get("keywords", []))
        notification = (
            notify_keyword_matches(
                keyword_matches,
                settings=settings,
                job=job,
                allow_send=allow_email_send,
            )
            if send_notifications
            else {"status": "skipped", "reason": "notifications_disabled"}
        )
        status = "duplicate_stopped" if duplicate else ("succeeded" if normalized["success"] else "failed")
        success = status in {"succeeded", "duplicate_stopped"}
        return JobRunResult(
            job_id=job.job_id,
            config_name=job.config_name,
            config_path=job.config_path,
            status=status,
            success=success,
            items_count=len(records),
            records=records,
            duplicate_key=duplicate.get("key"),
            duplicate_record=duplicate.get("record"),
            keyword_matches=keyword_matches,
            notification=notification,
            error=normalized.get("error") if status == "failed" else None,
            started_at=started_at,
            finished_at=utc_timestamp(),
            metadata=normalized.get("metadata", {}),
        )
    except Exception as exc:
        return JobRunResult(
            job_id=job.job_id,
            config_name=job.config_name,
            config_path=job.config_path,
            status="failed",
            success=False,
            items_count=0,
            records=[],
            error=str(exc),
            started_at=started_at,
            finished_at=utc_timestamp(),
        )


def default_workflow_runner(config_path: Path, record_policy: Callable[[dict[str, Any]], dict[str, Any]]) -> Any:
    config = load_workflow_config(config_path)
    return run_workflow_config(config, record_policy=record_policy)


def normalize_runner_result(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        records = result.get("records", result.get("data", []))
        return {
            "success": bool(result.get("success", True)),
            "records": records if isinstance(records, list) else [],
            "error": result.get("error"),
            "metadata": result.get("metadata", {}),
        }
    records = getattr(result, "records", [])
    diagnostics = getattr(result, "diagnostics", {})
    return {
        "success": bool(getattr(result, "success", True)),
        "records": records if isinstance(records, list) else [],
        "error": getattr(result, "error", None),
        "metadata": diagnostics if isinstance(diagnostics, dict) else {},
    }


def title_candidate(record: dict[str, Any]) -> str:
    extracts = record.get("extracts")
    if isinstance(extracts, dict):
        for key in ("title", "extract_title"):
            value = _first_text(extracts.get(key))
            if value:
                return value
        for key, value in extracts.items():
            if "title" in str(key).casefold():
                text = _first_text(value)
                if text:
                    return text

    for key in ("title", "extract_title"):
        value = _first_text(record.get(key))
        if value:
            return value

    for step in record.get("steps") or []:
        if not isinstance(step, dict):
            continue
        value = _first_text(step.get("value"))
        if value and (step.get("action") == "parser" or "title" in str(step.get("name") or "").casefold()):
            return value
    return ""


def url_candidate(record: dict[str, Any]) -> str:
    extracts = record.get("extracts")
    if isinstance(extracts, dict):
        for key in ("detail_url", "link", "originallink", "url"):
            value = _first_text(extracts.get(key))
            if value:
                return value
    for key in ("final_url", "start_url"):
        value = _first_text(record.get(key))
        if value:
            return value
    return ""


def duplicate_key_for_record(record: dict[str, Any]) -> str:
    title = _normalize_key_part(title_candidate(record))
    url = _normalize_key_part(url_candidate(record))
    if title and url:
        return f"{title} | {url}"
    if title:
        return title
    return url


def build_duplicate_index(snapshot_roots: Iterable[str | Path]) -> set[str]:
    index: set[str] = set()
    for record in iter_snapshot_records(snapshot_roots):
        key = duplicate_key_for_record(record)
        if key:
            index.add(key)
    return index


def iter_snapshot_records(snapshot_roots: Iterable[str | Path]) -> Iterable[dict[str, Any]]:
    for root_value in snapshot_roots:
        root = Path(root_value)
        paths: list[Path]
        if root.is_file():
            paths = [root]
        elif root.exists():
            paths = list(root.rglob("workflow_records.json"))
        else:
            paths = []
        for path in paths:
            payload = _read_json(path, default={})
            raw_records = payload.get("records") if isinstance(payload, dict) else payload
            if not isinstance(raw_records, list):
                continue
            for record in raw_records:
                if isinstance(record, dict):
                    yield record


def records_matching_keywords(records: Iterable[dict[str, Any]], keywords: Iterable[str]) -> list[dict[str, Any]]:
    normalized_keywords = [keyword.casefold() for keyword in _clean_string_list(keywords)]
    if not normalized_keywords:
        return []
    matches: list[dict[str, Any]] = []
    for record in records:
        haystack = "\n".join(_iter_text_values(record)).casefold()
        matched = [keyword for keyword in normalized_keywords if keyword in haystack]
        if matched:
            matches.append({"record": record, "keywords": matched})
    return matches


def notify_keyword_matches(
    matches: list[dict[str, Any]],
    *,
    settings: dict[str, Any],
    job: RegisteredJob | None = None,
    allow_send: bool = True,
) -> dict[str, Any]:
    recipients = _clean_string_list(settings.get("recipients")) or list(DEFAULT_RECIPIENTS)
    sender = os.environ.get("SMTP_FROM") or str(settings.get("sender") or DEFAULT_SENDER)
    result = {
        "status": "skipped" if not matches else "dry_run",
        "matched_count": len(matches),
        "recipients": recipients,
        "sender": sender,
    }
    if not matches:
        result["reason"] = "no_keyword_matches"
        return result

    if not allow_send:
        result["reason"] = "real_send_not_allowed"
        return result

    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT") or "587")
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    if not password:
        result["reason"] = "smtp_credentials_missing"
        return result
    if not host:
        result["reason"] = "missing_smtp_host"
        return result

    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    subject_job = f" {job.config_name}" if job is not None else ""
    message["Subject"] = f"Crawler keyword match{subject_job}: {len(matches)}"
    message.set_content(_notification_body(matches, job=job))

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=20) as smtp:
                if user:
                    smtp.login(user, password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=20) as smtp:
                smtp.starttls()
                if user:
                    smtp.login(user, password)
                smtp.send_message(message)
    except Exception as exc:
        result["status"] = "failed"
        result["reason"] = type(exc).__name__
        return result

    result["status"] = "sent"
    return result


def batch_to_dict(batch: BatchRunResult) -> dict[str, Any]:
    payload = asdict(batch)
    payload["results"] = [asdict(result) for result in batch.results]
    return payload


def _snapshot_roots_for_jobs(jobs: Iterable[RegisteredJob]) -> list[Path]:
    roots = []
    for job in jobs:
        if job.output_dir:
            output_dir = Path(job.output_dir)
            roots.append(output_dir if output_dir.is_absolute() else APP_ROOT / output_dir)
    return roots


def _job_due_status(job_settings: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    next_run_at = _parse_timestamp(job_settings.get("next_run_at"))
    now = datetime.now(timezone.utc)
    if next_run_at is None:
        return True, {"due_reason": "no_next_run_at"}
    if next_run_at <= now:
        return True, {"due_reason": "next_run_at_reached", "next_run_at": next_run_at.isoformat(timespec="seconds")}
    return False, {"due_reason": "not_due", "next_run_at": next_run_at.isoformat(timespec="seconds")}


def _skipped_not_due_result(job: RegisteredJob, metadata: dict[str, Any]) -> JobRunResult:
    now = utc_timestamp()
    return JobRunResult(
        job_id=job.job_id,
        config_name=job.config_name,
        config_path=job.config_path,
        status="skipped_not_due",
        success=True,
        items_count=0,
        records=[],
        notification={"status": "skipped", "reason": "not_due"},
        started_at=now,
        finished_at=now,
        metadata=metadata,
    )


def _update_job_schedule_after_run(settings: dict[str, Any], job_id: str, result: JobRunResult) -> None:
    jobs = settings.setdefault("jobs", {})
    job_settings = jobs.setdefault(job_id, {"enabled": True, "interval": {"value": 1, "unit": "hours"}})
    interval = normalize_interval(job_settings.get("interval"))
    finished = _parse_timestamp(result.finished_at) or datetime.now(timezone.utc)
    job_settings["last_run_at"] = finished.isoformat(timespec="seconds")
    job_settings["next_run_at"] = (finished + _interval_to_delta(interval)).isoformat(timespec="seconds")
    job_settings["last_status"] = result.status
    job_settings["interval"] = interval


def _interval_to_delta(interval: dict[str, Any]) -> timedelta:
    normalized = normalize_interval(interval)
    value = int(normalized["value"])
    unit = normalized["unit"]
    if unit == "minutes":
        return timedelta(minutes=value)
    if unit == "days":
        return timedelta(days=value)
    return timedelta(hours=value)


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _clean_optional_timestamp(value: Any) -> str:
    parsed = _parse_timestamp(value)
    return parsed.isoformat(timespec="seconds") if parsed is not None else ""


def _notification_body(matches: list[dict[str, Any]], *, job: RegisteredJob | None) -> str:
    lines = []
    if job is not None:
        lines.append(f"Job: {job.config_name} ({job.job_id})")
    lines.append(f"Matched records: {len(matches)}")
    for index, match in enumerate(matches[:20], start=1):
        record = match["record"]
        title = title_candidate(record) or "(no title)"
        url = url_candidate(record) or "(no url)"
        keywords = ", ".join(match["keywords"])
        lines.append(f"{index}. [{keywords}] {title} {url}")
    return "\n".join(lines)


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = _read_json(path, default={})
    return payload if isinstance(payload, dict) else {}


def _read_json(path: Path, *, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(path)


def _clean_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_values = [value]
    elif isinstance(value, Iterable):
        raw_values = list(value)
    else:
        raw_values = []
    return [str(item).strip() for item in raw_values if str(item).strip()]


def _normalize_key_part(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _first_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value).strip()
    if isinstance(value, list):
        for item in value:
            text = _first_text(item)
            if text:
                return text
    return ""


def _iter_text_values(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        if value.strip():
            yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_text_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_text_values(item)
