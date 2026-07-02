from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
import smtplib
import uuid

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - dependency is declared, fallback keeps imports safe.
    load_dotenv = None

from crawler_app.base import CrawlResult
from crawler_app.config_store import CONFIG_DIR, config_file_stem, list_configs
from crawler_app.duplicate_keys import duplicate_key_for_record, duplicate_keys_for_record
from crawler_app.logging_utils import log_result
from crawler_app.news_ingestion import sync_news_ui_output_dir
from crawler_app.runtime_maintenance import cleanup_runtime_files
from crawler_app.workflow import (
    LatestDuplicateIndex,
    build_latest_duplicate_index,
    latest_duplicate_decision_for_record,
    _merge_record_term_arrays,
    _merge_terms_into_existing_workflow_records,
    _merge_workflow_record_snapshot_records,
    load_workflow_config,
    run_workflow_config,
)


APP_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SHARED_ENV_PATH = Path(r"C:\Users\ThinkBook\Desktop\업무\00. HGZ\.env")
DEFAULT_STATE_DIR = APP_ROOT / "orchestration_state"
DEFAULT_SETTINGS_PATH = DEFAULT_STATE_DIR / "settings.json"
DEFAULT_HISTORY_PATH = DEFAULT_STATE_DIR / "run_history.json"
DEFAULT_JOB_STATE_DIR = DEFAULT_STATE_DIR / "jobs"
DEFAULT_JOB_HISTORY_DIR = DEFAULT_STATE_DIR / "history"
DEFAULT_JOB_LOCK_DIR = DEFAULT_STATE_DIR / "locks"
DEFAULT_KEYWORDS = ["SK", "최태원"]
DEFAULT_RECIPIENTS = ["bloodknihts@gmail.com", "superknihts@nate.com"]
DEFAULT_SENDER = "bloodknihts@gmail.com"
SCHEDULE_TIMEZONE = timezone(timedelta(hours=9), "KST")
RUN_LOCK_STALE_AFTER = timedelta(hours=12)
INTERVAL_UNITS = {"minutes", "hours", "days"}
DEFAULT_CRON_EXPRESSION = "0 * * * *"

Runner = Callable[[Path, Callable[[dict[str, Any]], dict[str, Any]]], Any]


# registered job 관련 데이터를 표현하는 객체다.
@dataclass(slots=True)
class RegisteredJob:
    job_id: str
    config_name: str
    config_path: str
    output_dir: str
    search_terms: list[str] = field(default_factory=list)
    filter_terms: list[str] = field(default_factory=list)


# job run 결과 정보를 담는 데이터 객체다.
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


# batch run 결과 정보를 담는 데이터 객체다.
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


# orchestration 상태 store의 상태와 실행 동작을 관리한다.
class OrchestrationStateStore:
    # 객체 생성 시 필요한 초기 상태를 설정한다.
    def __init__(
        self,
        settings_path: str | Path = DEFAULT_SETTINGS_PATH,
        history_path: str | Path = DEFAULT_HISTORY_PATH,
    ) -> None:
        self.settings_path = Path(settings_path)
        self.history_path = Path(history_path)

    # settings를 로드한다.
    def load_settings(self) -> dict[str, Any]:
        payload = _read_json_object(self.settings_path)
        settings = default_settings()
        if payload:
            settings.update({key: value for key, value in payload.items() if key != "jobs"})
            if isinstance(payload.get("jobs"), dict):
                settings["jobs"] = payload["jobs"]
        return normalize_settings(settings)

    # settings를 저장한다.
    def save_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        normalized = normalize_settings(settings)
        normalized["updated_at"] = utc_timestamp()
        _write_json(self.settings_path, normalized)
        return normalized

    # 이력을 로드한다.
    def load_history(self, limit: int | None = None) -> list[dict[str, Any]]:
        history = self._load_global_history() + self._load_job_histories()
        history.sort(key=lambda entry: str(entry.get("finished_at") or entry.get("started_at") or ""))
        if limit is not None and limit >= 0:
            return history[-limit:]
        return history

    # append 이력 값을 계산해 반환한다.
    def append_history(self, entry: dict[str, Any]) -> None:
        history = self._load_global_history()
        history.append(entry)
        _write_json(self.history_path, history)

    # job 상태를 로드한다.
    def load_job_state(self, job_id: str) -> dict[str, Any]:
        return _read_json_object(self.job_state_path(job_id))

    # job 상태를 저장한다.
    def save_job_state(self, job_id: str, state: dict[str, Any]) -> dict[str, Any]:
        normalized = {
            "job_id": config_file_stem(job_id),
            "cron": normalize_cron_expression(state.get("cron") or "") if state.get("cron") else "",
            "last_run_at": _clean_optional_timestamp(state.get("last_run_at")),
            "next_run_at": _clean_optional_timestamp(state.get("next_run_at")),
            "last_status": str(state.get("last_status") or ""),
            "updated_at": utc_timestamp(),
        }
        _write_json(self.job_state_path(job_id), normalized)
        return normalized

    # append job 이력 값을 계산해 반환한다.
    def append_job_history(self, job_id: str, entry: dict[str, Any]) -> None:
        path = self.job_history_path(job_id)
        history = _read_json(path, default=[])
        if not isinstance(history, list):
            history = []
        history.append(entry)
        _write_json(path, history)

    # job 상태 경로 값을 계산해 반환한다.
    def job_state_path(self, job_id: str) -> Path:
        base = DEFAULT_JOB_STATE_DIR if self.settings_path == DEFAULT_SETTINGS_PATH else self.settings_path.parent / "jobs"
        return base / f"{config_file_stem(job_id)}.json"

    # job 이력 경로 값을 계산해 반환한다.
    def job_history_path(self, job_id: str) -> Path:
        base = DEFAULT_JOB_HISTORY_DIR if self.history_path == DEFAULT_HISTORY_PATH else self.history_path.parent / "history"
        return base / f"{config_file_stem(job_id)}.json"

    # job lock 경로 값을 계산해 반환한다.
    def job_lock_path(self, job_id: str) -> Path:
        base = DEFAULT_JOB_LOCK_DIR if self.settings_path == DEFAULT_SETTINGS_PATH else self.settings_path.parent / "locks"
        return base / f"{config_file_stem(job_id)}.lock"

    # global 이력을 로드한다.
    def _load_global_history(self) -> list[dict[str, Any]]:
        payload = _read_json(self.history_path, default=[])
        return payload if isinstance(payload, list) else []

    # job histories를 로드한다.
    def _load_job_histories(self) -> list[dict[str, Any]]:
        base = DEFAULT_JOB_HISTORY_DIR if self.history_path == DEFAULT_HISTORY_PATH else self.history_path.parent / "history"
        if not base.exists():
            return []
        entries: list[dict[str, Any]] = []
        for path in base.glob("*.json"):
            payload = _read_json(path, default=[])
            if isinstance(payload, list):
                entries.extend(entry for entry in payload if isinstance(entry, dict))
        return entries


# utc timestamp 값을 계산해 반환한다.
def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# orchestration env를 로드한다.
def load_orchestration_env() -> None:
    if load_dotenv is None:
        return
    load_dotenv(APP_ROOT / ".env", override=False)
    shared_env = Path(os.environ.get("CRAWLER_SHARED_ENV_FILE") or DEFAULT_SHARED_ENV_PATH)
    if shared_env.exists():
        load_dotenv(shared_env, override=False)


# default sender 값을 계산해 반환한다.
def default_sender() -> str:
    return os.environ.get("SMTP_FROM") or DEFAULT_SENDER


# default settings 값을 계산해 반환한다.
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


# settings를 표준 형태로 정규화한다.
def normalize_settings(settings: dict[str, Any]) -> dict[str, Any]:
    keywords = _clean_string_list(settings.get("keywords")) or list(DEFAULT_KEYWORDS)
    recipients = _clean_string_list(settings.get("recipients")) or list(DEFAULT_RECIPIENTS)
    jobs = settings.get("jobs") if isinstance(settings.get("jobs"), dict) else {}
    normalized_jobs: dict[str, Any] = {}
    for raw_job_id, raw_job in jobs.items():
        job_id = config_file_stem(str(raw_job_id))
        if not isinstance(raw_job, dict):
            raw_job = {}
        cron = normalize_cron_expression(raw_job.get("cron") or _legacy_interval_to_cron(raw_job.get("interval")))
        normalized_jobs[job_id] = {
            "enabled": bool(raw_job.get("enabled", False)),
            "cron": cron,
            "interval": normalize_interval(raw_job.get("interval")),
            "last_run_at": _clean_optional_timestamp(raw_job.get("last_run_at")),
            "next_run_at": _clean_optional_timestamp(raw_job.get("next_run_at")),
            "last_status": str(raw_job.get("last_status") or ""),
        }

    return {
        "keywords": keywords,
        "recipients": recipients,
        "sender": str(settings.get("sender") or default_sender()),
        "allow_email_send": bool(settings.get("allow_email_send", False)),
        "jobs": normalized_jobs,
        "created_at": str(settings.get("created_at") or utc_timestamp()),
        "updated_at": str(settings.get("updated_at") or utc_timestamp()),
    }


# interval를 표준 형태로 정규화한다.
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


# cron expression를 표준 형태로 정규화한다.
def normalize_cron_expression(value: Any) -> str:
    cron = str(value or "").strip()
    if not cron:
        return DEFAULT_CRON_EXPRESSION
    fields = cron.split()
    if len(fields) != 5:
        raise ValueError("Cron expression must contain exactly five fields: minute hour day month weekday.")
    for field, minimum, maximum, label in (
        (fields[0], 0, 59, "minute"),
        (fields[1], 0, 23, "hour"),
        (fields[2], 1, 31, "day"),
        (fields[3], 1, 12, "month"),
        (fields[4], 0, 7, "weekday"),
    ):
        _validate_cron_field(field, minimum, maximum, label)
    return " ".join(fields)


# next cron run 값을 계산해 반환한다.
def next_cron_run(cron: Any, *, after: datetime | None = None) -> datetime:
    expression = normalize_cron_expression(cron)
    minute_field, hour_field, day_field, month_field, weekday_field = expression.split()
    base = after or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=SCHEDULE_TIMEZONE)
    candidate = base.astimezone(SCHEDULE_TIMEZONE).replace(second=0, microsecond=0) + timedelta(minutes=1)
    deadline = candidate + timedelta(days=366)
    while candidate <= deadline:
        weekday = (candidate.weekday() + 1) % 7
        if (
            _cron_field_matches(minute_field, candidate.minute)
            and _cron_field_matches(hour_field, candidate.hour)
            and _cron_field_matches(day_field, candidate.day)
            and _cron_field_matches(month_field, candidate.month)
            and (_cron_field_matches(weekday_field, weekday) or (weekday == 0 and _cron_field_matches(weekday_field, 7)))
        ):
            return candidate.astimezone(timezone.utc)
        candidate += timedelta(minutes=1)
    raise ValueError(f"Could not resolve next run time within one year for cron expression: {expression}")


# cron matches 일시 값을 계산해 반환한다.
def cron_matches_datetime(cron: Any, candidate: datetime | None = None) -> bool:
    expression = normalize_cron_expression(cron)
    minute_field, hour_field, day_field, month_field, weekday_field = expression.split()
    value = candidate or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=SCHEDULE_TIMEZONE)
    value = value.astimezone(SCHEDULE_TIMEZONE).replace(second=0, microsecond=0)
    weekday = (value.weekday() + 1) % 7
    return (
        _cron_field_matches(minute_field, value.minute)
        and _cron_field_matches(hour_field, value.hour)
        and _cron_field_matches(day_field, value.day)
        and _cron_field_matches(month_field, value.month)
        and (_cron_field_matches(weekday_field, weekday) or (weekday == 0 and _cron_field_matches(weekday_field, 7)))
    )


# legacy interval cron 값을 계산해 반환한다.
def _legacy_interval_to_cron(interval: Any) -> str:
    normalized = normalize_interval(interval)
    value = int(normalized["value"])
    unit = normalized["unit"]
    if unit == "minutes":
        return f"*/{value} * * * *" if value > 1 else "* * * * *"
    if unit == "hours":
        return f"0 */{value} * * *" if value > 1 else "0 * * * *"
    return f"0 0 */{value} * *" if value > 1 else "0 0 * * *"


# cron field 유효성을 검증한다.
def _validate_cron_field(field: str, minimum: int, maximum: int, label: str) -> None:
    for part in field.split(","):
        if not part:
            raise ValueError(f"Invalid empty {label} cron field.")
        if part == "*":
            continue
        if part.startswith("*/"):
            _validate_cron_number(part[2:], 1, maximum, label)
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            start_number = _weekday_name_to_number(start) if label == "weekday" else None
            end_number = _weekday_name_to_number(end) if label == "weekday" else None
            if label == "weekday" and start_number is not None and end_number is not None:
                if start_number > end_number:
                    raise ValueError(f"Invalid {label} cron range: {part!r}")
                continue
            _validate_cron_number(start, minimum, maximum, label)
            _validate_cron_number(end, minimum, maximum, label)
            if int(start) > int(end):
                raise ValueError(f"Invalid {label} cron range: {part!r}")
            continue
        if label == "weekday" and _weekday_name_to_number(part) is not None:
            continue
        _validate_cron_number(part, minimum, maximum, label)


# cron 번호 유효성을 검증한다.
def _validate_cron_number(value: str, minimum: int, maximum: int, label: str) -> None:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {label} cron value: {value!r}") from exc
    if number < minimum or number > maximum:
        raise ValueError(f"Invalid {label} cron value {number}; expected {minimum}-{maximum}.")


# cron field matches 값을 계산해 반환한다.
def _cron_field_matches(field: str, value: int) -> bool:
    for part in field.split(","):
        if part == "*":
            return True
        if part.startswith("*/"):
            step = int(part[2:])
            if value % step == 0:
                return True
            continue
        weekday_number = _weekday_name_to_number(part)
        if weekday_number is not None:
            if weekday_number == value:
                return True
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            start_number = _weekday_name_to_number(start)
            end_number = _weekday_name_to_number(end)
            if start_number is not None and end_number is not None:
                if start_number <= value <= end_number:
                    return True
                continue
            if int(start) <= value <= int(end):
                return True
            continue
        if int(part) == value:
            return True
    return False


# weekday 이름 번호 값을 계산해 반환한다.
def _weekday_name_to_number(value: str) -> int | None:
    return {
        "SUN": 0,
        "MON": 1,
        "TUE": 2,
        "WED": 3,
        "THU": 4,
        "FRI": 5,
        "SAT": 6,
    }.get(str(value or "").strip().upper())


# registered 설정 job 목록 값을 계산해 반환한다.
def registered_config_jobs(config_dir: str | Path = CONFIG_DIR) -> list[RegisteredJob]:
    jobs: list[RegisteredJob] = []
    for summary in list_configs(config_dir):
        jobs.append(
            RegisteredJob(
                job_id=config_file_stem(Path(summary.path).stem),
                config_name=summary.name,
                config_path=str(Path(summary.path)),
                output_dir=summary.output_dir,
                search_terms=list(summary.search_terms),
                filter_terms=list(summary.filter_terms),
            )
        )
    return jobs


# settings job 목록을 현재 설정과 동기화한다.
def sync_settings_jobs(settings: dict[str, Any], jobs: Iterable[RegisteredJob]) -> dict[str, Any]:
    settings = normalize_settings(settings)
    configured_jobs = settings.setdefault("jobs", {})
    for job in jobs:
        configured_jobs.setdefault(
            job.job_id,
            {"enabled": False, "interval": {"value": 1, "unit": "hours"}, "cron": DEFAULT_CRON_EXPRESSION},
        )
        configured_jobs[job.job_id]["interval"] = normalize_interval(configured_jobs[job.job_id].get("interval"))
        configured_jobs[job.job_id]["cron"] = normalize_cron_expression(
            configured_jobs[job.job_id].get("cron") or _legacy_interval_to_cron(configured_jobs[job.job_id].get("interval"))
        )
        configured_jobs[job.job_id]["enabled"] = bool(configured_jobs[job.job_id].get("enabled", False))
    return settings


# apply job runtime 상태 값을 계산해 반환한다.
def apply_job_runtime_state(settings: dict[str, Any], store: OrchestrationStateStore) -> dict[str, Any]:
    settings = normalize_settings(settings)
    for job_id, job_settings in settings.get("jobs", {}).items():
        state = store.load_job_state(job_id)
        if not state:
            continue
        for key in ("last_run_at", "last_status"):
            value = state.get(key)
            if value:
                job_settings[key] = value
        state_cron = str(state.get("cron") or "").strip()
        if state_cron and state_cron == str(job_settings.get("cron") or "").strip():
            next_run_at = state.get("next_run_at")
            if next_run_at:
                job_settings["next_run_at"] = next_run_at
    return settings


# 선택된 오케스트레이션 job들을 설정에 따라 실행한다.
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
    parallel: bool = False,
    crawl_result_log_name: str | None = None,
) -> BatchRunResult:
    load_orchestration_env()
    store = store or OrchestrationStateStore()
    config_jobs = registered_config_jobs(config_dir)
    settings = apply_job_runtime_state(sync_settings_jobs(store.load_settings(), config_jobs), store)
    jobs_by_id = {job.job_id: job for job in registered_config_jobs(config_dir)}
    selected = _resolve_selected_job_ids(selected_job_ids, jobs_by_id)
    batch_id = uuid.uuid4().hex
    started_at = utc_timestamp()

    # selected를 실행한다.
    def run_selected(job_id: str) -> JobRunResult:
        return _run_selected_job(
            job_id,
            store=store,
            jobs_by_id=jobs_by_id,
            settings=settings,
            runner=runner,
            snapshot_roots=snapshot_roots,
            send_notifications=send_notifications,
            force_due=force_due,
            allow_email_send=allow_email_send,
            crawl_result_log_name=crawl_result_log_name,
        )

    if parallel and len(selected) > 1:
        indexed_results: dict[int, JobRunResult] = {}
        with ThreadPoolExecutor(max_workers=len(selected)) as executor:
            future_to_index = {executor.submit(run_selected, job_id): index for index, job_id in enumerate(selected)}
            for future in as_completed(future_to_index):
                indexed_results[future_to_index[future]] = future.result()
        results = [indexed_results[index] for index in sorted(indexed_results)]
    else:
        results = [run_selected(job_id) for job_id in selected]

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
    _cleanup_runtime_after_run(store)
    return batch


# runtime after run를 정리한다.
def _cleanup_runtime_after_run(store: OrchestrationStateStore) -> None:
    try:
        cleanup_runtime_files(
            app_root=APP_ROOT,
            state_dir=store.settings_path.parent,
            history_path=store.history_path,
        )
    except Exception:
        return


# selected job ids를 실제 실행 값으로 해석한다.
def _resolve_selected_job_ids(selected_job_ids: Iterable[str], jobs_by_id: dict[str, RegisteredJob]) -> list[str]:
    selected: list[str] = []
    normalized_lookup = {config_file_stem(job_id): job_id for job_id in jobs_by_id}
    for raw_job_id in selected_job_ids:
        job_id = str(raw_job_id)
        if job_id in jobs_by_id:
            selected.append(job_id)
            continue
        normalized = config_file_stem(job_id)
        resolved = normalized_lookup.get(normalized)
        if resolved:
            selected.append(resolved)
    return selected


# selected job를 실행한다.
def _run_selected_job(
    job_id: str,
    *,
    store: OrchestrationStateStore,
    jobs_by_id: dict[str, RegisteredJob],
    settings: dict[str, Any],
    runner: Runner | None,
    snapshot_roots: Iterable[str | Path] | None,
    send_notifications: bool,
    force_due: bool,
    allow_email_send: bool,
    crawl_result_log_name: str | None,
) -> JobRunResult:
    job = jobs_by_id[job_id]
    job_settings = settings["jobs"].get(job_id, {})
    due, due_metadata = _job_due_status(job_settings)
    if not force_due and not due:
        result = _skipped_not_due_result(job, due_metadata)
        _log_job_to_crawl_results(result, crawl_result_log_name)
        _append_job_result_history(store, result)
        return result

    lock_path = store.job_lock_path(job_id)
    if not _acquire_run_lock(lock_path):
        result = _skipped_running_result(job)
        _log_job_to_crawl_results(result, crawl_result_log_name)
        _append_job_result_history(store, result)
        return result

    try:
        if snapshot_roots is not None:
            roots = list(snapshot_roots)
        else:
            roots = _snapshot_roots_for_jobs([job])
        duplicate_index, boundary_duplicate_index = build_duplicate_indexes(roots)
        latest_duplicate_index = build_latest_duplicate_index(roots)
        result = run_job(
            job,
            settings=settings,
            duplicate_index=duplicate_index,
            boundary_duplicate_index=boundary_duplicate_index,
            latest_duplicate_index=latest_duplicate_index,
            runner=runner,
            send_notifications=send_notifications,
            allow_email_send=allow_email_send,
        )
        _log_job_to_crawl_results(result, crawl_result_log_name)
        _update_job_runtime_state(store, job_id, job_settings, result)
        _append_job_result_history(store, result)
        return result
    finally:
        _release_run_lock(lock_path)


# acquire run lock 값을 계산해 반환한다.
def _acquire_run_lock(lock_path: Path) -> bool:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if _lock_is_stale(lock_path):
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
    payload = {
        "pid": os.getpid(),
        "created_at": utc_timestamp(),
    }
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(str(lock_path), flags)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return True


# release run lock 값을 계산해 반환한다.
def _release_run_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass


# 오케스트레이션 job 결과를 기존 crawl_results.jsonl 형식으로 남긴다.
def _log_job_to_crawl_results(result: JobRunResult, crawler_name: str | None) -> None:
    if not crawler_name:
        return
    started_at = _parse_timestamp(result.started_at) or datetime.now(timezone.utc)
    finished_at = _parse_timestamp(result.finished_at) or started_at
    metadata = dict(result.metadata or {})
    metadata.setdefault("config_name", result.config_name)
    metadata.setdefault("config_path", result.config_path)
    metadata.setdefault("job_id", result.job_id)
    crawl_result = CrawlResult(
        crawler_name=crawler_name,
        success=result.success,
        started_at=started_at,
        finished_at=finished_at,
        items_count=result.items_count,
        message=result.status,
        data=result.records,
        metadata=metadata,
        error=result.error,
    )
    try:
        log_result(APP_ROOT / "logs", crawl_result)
    except Exception as exc:
        result.metadata["crawl_result_log_error"] = f"{type(exc).__name__}: {exc}"


# lock is stale 값을 계산해 반환한다.
def _lock_is_stale(lock_path: Path) -> bool:
    payload = _read_json_object(lock_path)
    created_at = _parse_timestamp(payload.get("created_at"))
    if created_at is None:
        return True
    if datetime.now(timezone.utc) - created_at > RUN_LOCK_STALE_AFTER:
        return True
    return not _lock_process_is_alive(payload.get("pid"))


# lock 파일에 기록된 프로세스가 아직 살아 있는지 확인한다.
def _lock_process_is_alive(pid_value: Any) -> bool:
    try:
        pid = int(pid_value)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


# skipped running 결과 값을 계산해 반환한다.
def _skipped_running_result(job: RegisteredJob) -> JobRunResult:
    now = utc_timestamp()
    return JobRunResult(
        job_id=job.job_id,
        config_name=job.config_name,
        config_path=job.config_path,
        status="skipped_running",
        success=True,
        items_count=0,
        records=[],
        notification={"status": "skipped", "reason": "already_running"},
        started_at=now,
        finished_at=now,
        metadata={"reason": "already_running"},
    )


# append job 결과 이력 값을 계산해 반환한다.
def _append_job_result_history(store: OrchestrationStateStore, result: JobRunResult) -> None:
    batch = BatchRunResult(
        batch_id=uuid.uuid4().hex,
        status="failed" if result.status == "failed" else "completed",
        total=1,
        succeeded=1 if result.status == "succeeded" else 0,
        failed=1 if result.status == "failed" else 0,
        duplicate_stopped=1 if result.status == "duplicate_stopped" else 0,
        skipped_not_due=1 if result.status == "skipped_not_due" else 0,
        results=[result],
        started_at=result.started_at,
        finished_at=result.finished_at,
    )
    store.append_job_history(result.job_id, batch_to_dict(batch))


# update job runtime 상태 값을 계산해 반환한다.
def _update_job_runtime_state(
    store: OrchestrationStateStore,
    job_id: str,
    job_settings: dict[str, Any],
    result: JobRunResult,
) -> None:
    started = _parse_timestamp(result.started_at) or datetime.now(timezone.utc)
    cron = job_settings.get("cron") or _legacy_interval_to_cron(job_settings.get("interval"))
    store.save_job_state(
        job_id,
        {
            "cron": cron,
            "last_run_at": started.isoformat(timespec="seconds"),
            "next_run_at": next_cron_run(cron, after=started).isoformat(timespec="seconds"),
            "last_status": result.status,
        },
    )


# settings registered job 목록 값을 계산해 반환한다.
def settings_for_registered_jobs(
    *,
    store: OrchestrationStateStore | None = None,
    config_dir: str | Path = CONFIG_DIR,
) -> tuple[dict[str, Any], list[RegisteredJob]]:
    load_orchestration_env()
    store = store or OrchestrationStateStore()
    jobs = registered_config_jobs(config_dir)
    settings = apply_job_runtime_state(sync_settings_jobs(store.load_settings(), jobs), store)
    return settings, jobs


# 단일 오케스트레이션 job에 중복 정책과 알림을 적용해 실행한다.
def run_job(
    job: RegisteredJob,
    *,
    settings: dict[str, Any],
    duplicate_index: set[str],
    boundary_duplicate_index: set[str] | None = None,
    latest_duplicate_index: LatestDuplicateIndex | None = None,
    runner: Runner | None = None,
    send_notifications: bool = True,
    allow_email_send: bool = False,
) -> JobRunResult:
    started_at = utc_timestamp()
    seen: set[str] = set()
    boundary_duplicate_index = boundary_duplicate_index or set()
    latest_duplicate_index = latest_duplicate_index or LatestDuplicateIndex()
    duplicate: dict[str, Any] = {}
    same_run_duplicate_skipped_count = 0
    latest_cross_group_duplicate_skipped_count = 0
    same_run_record_by_key: dict[str, dict[str, Any]] = {}
    job_config = load_workflow_config(Path(job.config_path))
    job_output_dir = Path(job.output_dir)
    if not job_output_dir.is_absolute():
        job_output_dir = APP_ROOT / job_output_dir

    # scope record를 중지한다.
    def stop_scope_for_record(record: dict[str, Any]) -> str:
        return "numeric_page_sequence" if str(record.get("search_term") or "").strip().isdigit() else "search_term"

    # record policy 값을 계산해 반환한다.
    def record_policy(record: dict[str, Any]) -> dict[str, Any]:
        nonlocal same_run_duplicate_skipped_count, latest_cross_group_duplicate_skipped_count
        keys = duplicate_keys_for_record(record)
        if latest_duplicate_index.has_records:
            latest_decision = latest_duplicate_decision_for_record(
                record,
                latest_duplicate_index,
                filter_terms=job.filter_terms,
            )
            if latest_decision is not None:
                _merge_terms_into_existing_workflow_records(job_output_dir, job_config, record, filter_terms=job.filter_terms)
                if latest_decision.get("stop"):
                    duplicate.update(
                        {
                            "key": (latest_decision.get("metadata") or {}).get("duplicate_key"),
                            "record": record,
                            "boundary": True,
                            "latest": True,
                        }
                    )
                else:
                    latest_cross_group_duplicate_skipped_count += 1
                return latest_decision
        else:
            boundary_duplicate_key = next((key for key in keys if key in boundary_duplicate_index), "")
            if boundary_duplicate_key:
                _merge_terms_into_existing_workflow_records(job_output_dir, job_config, record, filter_terms=job.filter_terms)
                duplicate.update({"key": boundary_duplicate_key, "record": record, "boundary": True})
                return {
                    "include": False,
                    "stop": True,
                    "reason": "duplicate_boundary_stopped",
                    "metadata": {
                        "duplicate_key": boundary_duplicate_key,
                        "stop_scope": stop_scope_for_record(record),
                        "boundary": True,
                    },
                }
            duplicate_key = next((key for key in keys if key in duplicate_index), "")
            if duplicate_key:
                _merge_terms_into_existing_workflow_records(job_output_dir, job_config, record, filter_terms=job.filter_terms)
                duplicate.update({"key": duplicate_key, "record": record})
                return {
                    "include": False,
                    "stop": True,
                    "reason": "duplicate_stopped",
                    "metadata": {"duplicate_key": duplicate_key, "stop_scope": stop_scope_for_record(record)},
                }
        same_run_duplicate_key = next((key for key in keys if key in seen), "")
        if same_run_duplicate_key:
            duplicate_record = same_run_record_by_key.get(same_run_duplicate_key)
            if duplicate_record is not None:
                _merge_record_term_arrays(duplicate_record, record, filter_terms=job.filter_terms)
            same_run_duplicate_skipped_count += 1
            return {
                "include": False,
                "stop": False,
                "reason": "same_run_duplicate_skipped",
                "metadata": {"duplicate_key": same_run_duplicate_key},
            }
        for key in keys:
            seen.add(key)
            same_run_record_by_key[key] = record
        return {"include": True, "stop": False}

    try:
        raw_result = (runner or default_workflow_runner)(Path(job.config_path), record_policy)
        normalized = normalize_runner_result(raw_result)
        records = normalized["records"]
        metadata = dict(normalized.get("metadata", {}))
        if same_run_duplicate_skipped_count:
            metadata["same_run_duplicate_skipped_count"] = same_run_duplicate_skipped_count
        if latest_cross_group_duplicate_skipped_count:
            metadata["latest_cross_group_duplicate_skipped_count"] = latest_cross_group_duplicate_skipped_count
        metadata.setdefault("config_name", job.config_name)
        metadata.setdefault("job_id", job.job_id)
        metadata.setdefault("config_path", job.config_path)
        metadata.setdefault("stage", metadata.get("stage") or metadata.get("step_name") or "workflow")
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
        _sync_news_ui_from_job_output(job, metadata)
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
            metadata=metadata,
        )
    except Exception as exc:
        error_message = (
            f"{job.config_name} ({job.job_id}) failed during orchestration run "
            f"for config {job.config_path}: {type(exc).__name__}: {exc}"
        )
        return JobRunResult(
            job_id=job.job_id,
            config_name=job.config_name,
            config_path=job.config_path,
            status="failed",
            success=False,
            items_count=0,
            records=[],
            error=error_message,
            started_at=started_at,
            finished_at=utc_timestamp(),
            metadata={
                "config_name": job.config_name,
                "job_id": job.job_id,
                "config_path": job.config_path,
                "stage": "workflow",
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )


# 오케스트레이션/스케줄러 실행 결과를 뉴스 검토 UI용 SQLite DB에 반영한다.
def _sync_news_ui_from_job_output(job: RegisteredJob, metadata: dict[str, Any]) -> None:
    output_dir = metadata.get("output_dir") or job.output_dir
    if not output_dir:
        return
    try:
        summary = sync_news_ui_output_dir(project_root=APP_ROOT, output_dir=str(output_dir))
        metadata["news_ui_sync"] = summary.to_dict()
    except Exception as exc:  # noqa: BLE001 - 뉴스 UI 동기화 실패가 크롤링 성공을 실패로 바꾸면 안 된다.
        metadata["news_ui_sync_error"] = f"{type(exc).__name__}: {exc}"


# config 파일을 로드해 공통 workflow 실행 함수로 위임한다.
def default_workflow_runner(config_path: Path, record_policy: Callable[[dict[str, Any]], dict[str, Any]]) -> Any:
    config = load_workflow_config(config_path)
    snapshots = _read_workflow_snapshots(Path(config["output_dir"]))
    result = run_workflow_config(config, record_policy=record_policy)
    metadata = normalize_runner_result(result).get("metadata", {})
    if metadata.get("record_policy_stop_reason") == "duplicate_stopped":
        _merge_or_restore_workflow_snapshots(Path(config["output_dir"]), snapshots)
    return result


# runner 결과를 표준 형태로 정규화한다.
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


# 제목 candidate 값을 계산해 반환한다.
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


# URL candidate 값을 계산해 반환한다.
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


# duplicate index를 생성해 반환한다.
def build_duplicate_index(snapshot_roots: Iterable[str | Path]) -> set[str]:
    duplicate_index, _ = build_duplicate_indexes(snapshot_roots)
    return duplicate_index


# duplicate index 목록을 생성해 반환한다.
def build_duplicate_indexes(snapshot_roots: Iterable[str | Path]) -> tuple[set[str], set[str]]:
    index: set[str] = set()
    boundary_index: set[str] = set()
    for records in iter_snapshot_record_groups(snapshot_roots):
        for record_index, record in enumerate(records):
            keys = duplicate_keys_for_record(record)
            for key in keys:
                index.add(key)
            if record_index == 0:
                for key in keys:
                    boundary_index.add(key)
    return index, boundary_index


# snapshot records를 순회한다.
def iter_snapshot_records(snapshot_roots: Iterable[str | Path]) -> Iterable[dict[str, Any]]:
    for records in iter_snapshot_record_groups(snapshot_roots):
        yield from records


# snapshot record groups를 순회한다.
def iter_snapshot_record_groups(snapshot_roots: Iterable[str | Path]) -> Iterable[list[dict[str, Any]]]:
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
            records: list[dict[str, Any]] = []
            for record in raw_records:
                if isinstance(record, dict):
                    records.append(record)
            if records:
                yield records


# 수집 records에서 알림 대상 키워드 매칭 결과를 찾는다.
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


# 키워드 매칭 결과를 dry-run 또는 SMTP 메일로 보고한다.
def notify_keyword_matches(
    matches: list[dict[str, Any]],
    *,
    settings: dict[str, Any],
    job: RegisteredJob | None = None,
    allow_send: bool = True,
) -> dict[str, Any]:
    load_orchestration_env()
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


# batch dict 값을 계산해 반환한다.
def batch_to_dict(batch: BatchRunResult) -> dict[str, Any]:
    payload = asdict(batch)
    payload["results"] = [asdict(result) for result in batch.results]
    return payload


# snapshot roots job 목록 값을 계산해 반환한다.
def _snapshot_roots_for_jobs(jobs: Iterable[RegisteredJob]) -> list[Path]:
    roots = []
    for job in jobs:
        if job.output_dir:
            output_dir = Path(job.output_dir)
            roots.append(output_dir if output_dir.is_absolute() else APP_ROOT / output_dir)
    return roots


# workflow snapshots를 읽어 반환한다.
def _read_workflow_snapshots(output_dir: Path) -> dict[Path, dict[str, Any]]:
    snapshots: dict[Path, dict[str, Any]] = {}
    if not output_dir.exists():
        return snapshots
    for path in output_dir.rglob("workflow_records.json"):
        payload = _read_json(path, default={})
        if isinstance(payload, dict):
            snapshots[path] = payload
    return snapshots


# 기존 값과 새 restore workflow snapshots를 병합한다.
def _merge_or_restore_workflow_snapshots(output_dir: Path, before: dict[Path, dict[str, Any]]) -> None:
    after_paths = set(output_dir.rglob("workflow_records.json")) if output_dir.exists() else set()
    for path, old_payload in before.items():
        if path not in after_paths:
            _write_json(path, old_payload)
            continue
        new_payload = _read_json(path, default={})
        if not isinstance(new_payload, dict):
            _write_json(path, old_payload)
            continue
        merged_payload = dict(new_payload)
        old_records = old_payload.get("records") if isinstance(old_payload.get("records"), list) else []
        new_records = new_payload.get("records") if isinstance(new_payload.get("records"), list) else []
        merged_payload["records"] = _merge_records_by_duplicate_key(old_records, new_records)
        merged_payload["item_count"] = len(merged_payload["records"])
        _write_json(path, merged_payload)


# 기존 값과 새 records duplicate key를 병합한다.
def _merge_records_by_duplicate_key(
    existing_records: list[dict[str, Any]],
    new_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return _merge_workflow_record_snapshot_records(existing_records, new_records)


# job due 상태 값을 계산해 반환한다.
def _job_due_status(job_settings: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    next_run_at = _parse_timestamp(job_settings.get("next_run_at"))
    now = datetime.now(timezone.utc)
    if next_run_at is None:
        return True, {"due_reason": "no_next_run_at"}
    if next_run_at <= now:
        return True, {"due_reason": "next_run_at_reached", "next_run_at": next_run_at.isoformat(timespec="seconds")}
    return False, {"due_reason": "not_due", "next_run_at": next_run_at.isoformat(timespec="seconds")}


# skipped not due 결과 값을 계산해 반환한다.
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


# interval delta 값을 계산해 반환한다.
def _interval_to_delta(interval: dict[str, Any]) -> timedelta:
    normalized = normalize_interval(interval)
    value = int(normalized["value"])
    unit = normalized["unit"]
    if unit == "minutes":
        return timedelta(minutes=value)
    if unit == "days":
        return timedelta(days=value)
    return timedelta(hours=value)


# timestamp를 파싱한다.
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


# optional timestamp를 정리한다.
def _clean_optional_timestamp(value: Any) -> str:
    parsed = _parse_timestamp(value)
    return parsed.isoformat(timespec="seconds") if parsed is not None else ""


# 알림 본문 값을 계산해 반환한다.
def _notification_body(matches: list[dict[str, Any]], *, job: RegisteredJob | None) -> str:
    lines = []
    site_name = job.config_name if job is not None else "Unknown site"
    if job is not None:
        lines.append(f"Site: {site_name}")
    lines.append(f"Matched records: {len(matches)}")
    for index, match in enumerate(matches[:20], start=1):
        record = match["record"]
        topic = _record_topic_candidate(record, match)
        description = description_candidate(record) or title_candidate(record) or "(no description)"
        url = url_candidate(record) or "(no url)"
        lines.append(f"{index}. {site_name} > {topic}")
        lines.append(f"   desc: {_truncate_notification_text(description)}")
        lines.append(f"   URL: {url}")
    return "\n".join(lines)


# description candidate 값을 계산해 반환한다.
def description_candidate(record: dict[str, Any]) -> str:
    extracts = record.get("extracts")
    if isinstance(extracts, dict):
        for key in ("description", "desc", "summary", "extract_description", "extract_summary", "body", "extract_body"):
            value = _first_text(extracts.get(key))
            if value:
                return value

    for key in ("description", "desc", "summary", "body"):
        value = _first_text(record.get(key))
        if value:
            return value

    return ""


# record topic candidate 값을 계산해 반환한다.
def _record_topic_candidate(record: dict[str, Any], match: dict[str, Any]) -> str:
    search_term = _first_text(record.get("search_term"))
    if search_term:
        return search_term
    keywords = _clean_string_list(match.get("keywords"))
    return ", ".join(keywords) if keywords else "(no search/filter term)"


# truncate 알림 텍스트 값을 계산해 반환한다.
def _truncate_notification_text(value: str, limit: int = 500) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


# json object를 읽어 반환한다.
def _read_json_object(path: Path) -> dict[str, Any]:
    payload = _read_json(path, default={})
    return payload if isinstance(payload, dict) else {}


# json를 읽어 반환한다.
def _read_json(path: Path, *, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


# json를 파일에 기록한다.
def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(path)


# string list를 정리한다.
def _clean_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_values = [value]
    elif isinstance(value, Iterable):
        raw_values = list(value)
    else:
        raw_values = []
    return [str(item).strip() for item in raw_values if str(item).strip()]


# first 텍스트 값을 계산해 반환한다.
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


# 텍스트 values를 순회한다.
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
