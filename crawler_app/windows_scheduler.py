from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
import csv
import hashlib
import io
import json
import locale
import os
import subprocess
import xml.etree.ElementTree as ET

from crawler_app.orchestration import APP_ROOT, RegisteredJob, normalize_cron_expression, normalize_interval


PROJECT_NAMESPACE = hashlib.sha1(str(APP_ROOT.resolve()).casefold().encode("utf-8")).hexdigest()[:12]
TASK_FOLDER = rf"\CrawlerOrchestration\{PROJECT_NAMESPACE}"
TASK_PREFIX = "crawler_"
MAX_SPLIT_TASKS_PER_JOB = 48
RUNNER_SCRIPT = APP_ROOT / "scripts" / "Run-OrchestrationJob.ps1"
STOP_SCRIPT = APP_ROOT / "scripts" / "Stop-OrchestrationJobs.ps1"
DEFAULT_LAUNCHER_DIR = Path(os.environ.get("LOCALAPPDATA") or APP_ROOT / "runtime") / "CrawlerOrchestration" / PROJECT_NAMESPACE
DEFAULT_SCHEDULER_REGISTRY_PATH = APP_ROOT / "orchestration_state" / "scheduler_registry.json"


@dataclass(slots=True)
class SchedulerCommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(slots=True)
class SchedulerSyncResult:
    status: str
    deleted: list[str] = field(default_factory=list)
    created: list[str] = field(default_factory=list)
    skipped_reason: str = ""


@dataclass(slots=True)
class SchedulerTaskInfo:
    task_name: str
    next_run_time: str = ""
    status: str = ""
    last_run_time: str = ""
    last_result: str = ""
    task_to_run: str = ""
    schedule_type: str = ""
    repeat_every: str = ""


@dataclass(slots=True)
class SchedulerDeleteResult:
    status: str
    task_name: str
    skipped_reason: str = ""


@dataclass(slots=True)
class SchedulerStopResult:
    status: str
    ended: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped_reason: str = ""


@dataclass(slots=True)
class SchedulerTaskPlan:
    task_name: str
    schedule_args: list[str]
    launcher_path: Path | None = None
    strategy: str = "single_schtasks"
    variant: str = ""


CommandRunner = Callable[[list[str]], SchedulerCommandResult]


def sync_windows_scheduled_tasks(
    settings: dict[str, Any],
    jobs: Iterable[RegisteredJob],
    *,
    project_root: str | Path = APP_ROOT,
    command_runner: CommandRunner | None = None,
    is_windows: bool | None = None,
    launcher_dir: str | Path = DEFAULT_LAUNCHER_DIR,
    registry_path: str | Path = DEFAULT_SCHEDULER_REGISTRY_PATH,
) -> SchedulerSyncResult:
    """Replace this app's Windows scheduled tasks with the current UI settings."""
    validate_windows_schedule_settings(settings, jobs)
    if is_windows is None:
        is_windows = os.name == "nt"
    if not is_windows:
        return SchedulerSyncResult(status="skipped", skipped_reason="not_windows")

    runner = command_runner or _run_command
    existing_tasks = list_managed_tasks(command_runner=runner)
    deleted: list[str] = []
    for task_name in existing_tasks:
        runner(["schtasks.exe", "/End", "/TN", task_name])
        _checked_run(runner, ["schtasks.exe", "/Delete", "/TN", task_name, "/F"])
        deleted.append(task_name)

    _delete_managed_launchers(Path(launcher_dir))
    created: list[str] = []
    job_settings_by_id = settings.get("jobs") if isinstance(settings.get("jobs"), dict) else {}
    for job in jobs:
        job_settings = job_settings_by_id.get(job.job_id)
        if not isinstance(job_settings, dict) or not job_settings.get("enabled"):
            continue
        for plan in _schedule_task_plans_from_job_settings(job.job_id, job_settings):
            launcher_path = write_task_launcher(
                project_root,
                job.job_id,
                launcher_dir=launcher_dir,
                allow_email_send=bool(settings.get("allow_email_send", False)),
                task_name=plan.task_name,
            )
            task_command = build_task_action(launcher_path)
            _checked_run(
                runner,
                [
                    "schtasks.exe",
                    "/Create",
                    "/F",
                    "/TN",
                    plan.task_name,
                    "/TR",
                    task_command,
                    *plan.schedule_args,
                ],
            )
            created.append(plan.task_name)

    write_scheduler_registry(settings, jobs, registry_path=registry_path)
    return SchedulerSyncResult(status="synced", deleted=deleted, created=created)


def validate_windows_schedule_settings(settings: dict[str, Any], jobs: Iterable[RegisteredJob]) -> None:
    """Validate enabled job cron expressions before mutating Windows Task Scheduler."""
    job_settings_by_id = settings.get("jobs") if isinstance(settings.get("jobs"), dict) else {}
    for job in jobs:
        job_settings = job_settings_by_id.get(job.job_id)
        if not isinstance(job_settings, dict) or not job_settings.get("enabled"):
            continue
        try:
            _schedule_task_plans_from_job_settings(job.job_id, job_settings)
        except ValueError as exc:
            raise ValueError(f"{job.config_name} cron 설정을 Windows Task Scheduler로 변환할 수 없습니다: {exc}") from exc


def list_managed_tasks(*, command_runner: CommandRunner | None = None) -> list[str]:
    runner = command_runner or _run_command
    result = runner(["schtasks.exe", "/Query", "/FO", "CSV"])
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        if not message or _is_task_not_found_message(message):
            return []
        raise RuntimeError(message or "Windows Task Scheduler command failed.")
    task_names: list[str] = []
    reader = csv.DictReader(io.StringIO(result.stdout))
    for row in reader:
        task_name = str(row.get("TaskName") or "").strip()
        if task_name.startswith(f"{TASK_FOLDER}\\{TASK_PREFIX}"):
            task_names.append(task_name)
    return task_names


def list_managed_task_details(*, command_runner: CommandRunner | None = None) -> list[SchedulerTaskInfo]:
    if command_runner is None and os.name == "nt":
        details = _powershell_task_details(_run_command)
        if details:
            return details
    runner = command_runner or _run_command
    result = runner(["schtasks.exe", "/Query", "/FO", "CSV", "/V"])
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        if not message or _is_task_not_found_message(message):
            return []
        raise RuntimeError(message or "Windows Task Scheduler command failed.")
    details: list[SchedulerTaskInfo] = []
    reader = csv.DictReader(io.StringIO(result.stdout))
    for row in reader:
        task_name = str(row.get("TaskName") or "").strip()
        if not task_name.startswith(f"{TASK_FOLDER}\\{TASK_PREFIX}"):
            continue
        details.append(
            SchedulerTaskInfo(
                task_name=task_name,
                next_run_time=str(row.get("Next Run Time") or "").strip(),
                status=str(row.get("Status") or "").strip(),
                last_run_time=str(row.get("Last Run Time") or "").strip(),
                last_result=str(row.get("Last Result") or "").strip(),
                task_to_run=str(row.get("Task To Run") or "").strip(),
                schedule_type=str(row.get("Schedule Type") or "").strip(),
                repeat_every=str(row.get("Repeat: Every") or "").strip(),
            )
        )
    if not details:
        details = _basic_task_details(runner)
    if not details:
        details = _powershell_task_details(runner)
    return details


def _basic_task_details(runner: CommandRunner) -> list[SchedulerTaskInfo]:
    result = runner(["schtasks.exe", "/Query", "/FO", "CSV"])
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        if not message or _is_task_not_found_message(message):
            return []
        raise RuntimeError(message or "Windows Task Scheduler command failed.")
    details: list[SchedulerTaskInfo] = []
    reader = csv.DictReader(io.StringIO(result.stdout))
    for row in reader:
        task_name = str(row.get("TaskName") or "").strip()
        if not task_name.startswith(f"{TASK_FOLDER}\\{TASK_PREFIX}"):
            continue
        details.append(
            SchedulerTaskInfo(
                task_name=task_name,
                next_run_time=str(row.get("Next Run Time") or "").strip(),
                status=str(row.get("Status") or "").strip(),
            )
        )
    return details


def _powershell_task_details(runner: CommandRunner) -> list[SchedulerTaskInfo]:
    task_path = TASK_FOLDER if TASK_FOLDER.endswith("\\") else TASK_FOLDER + "\\"
    script = (
        f"Get-ScheduledTask -TaskPath '{task_path}' -ErrorAction SilentlyContinue | "
        "Sort-Object TaskName | ForEach-Object { "
        "$info = Get-ScheduledTaskInfo -TaskPath $_.TaskPath -TaskName $_.TaskName; "
        "[PSCustomObject]@{"
        "TaskName=($_.TaskPath + $_.TaskName);"
        "NextRunTime=[string]$info.NextRunTime;"
        "Status=[string]$_.State;"
        "LastRunTime=[string]$info.LastRunTime;"
        "LastResult=[string]$info.LastTaskResult"
        "} } | ConvertTo-Json -Compress"
    )
    result = runner(["powershell.exe", "-NoProfile", "-Command", script])
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        if not message or _is_task_not_found_message(message):
            return []
        raise RuntimeError(message or "Windows Task Scheduler command failed.")
    try:
        payload = json.loads(result.stdout) if result.stdout.strip() else []
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return []
    details: list[SchedulerTaskInfo] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        task_name = str(row.get("TaskName") or "").strip()
        if not task_name.startswith(f"{TASK_FOLDER}\\{TASK_PREFIX}"):
            continue
        details.append(
            SchedulerTaskInfo(
                task_name=task_name,
                next_run_time=str(row.get("NextRunTime") or "").strip(),
                status=str(row.get("Status") or "").strip(),
                last_run_time=str(row.get("LastRunTime") or "").strip(),
                last_result=str(row.get("LastResult") or "").strip(),
            )
        )
    return details


def delete_managed_task(
    task_name: str,
    *,
    command_runner: CommandRunner | None = None,
    launcher_dir: str | Path = DEFAULT_LAUNCHER_DIR,
    registry_path: str | Path = DEFAULT_SCHEDULER_REGISTRY_PATH,
) -> SchedulerDeleteResult:
    normalized = str(task_name or "").strip()
    if not normalized.startswith(f"{TASK_FOLDER}\\{TASK_PREFIX}"):
        raise ValueError("Only managed crawler orchestration tasks can be deleted.")
    runner = command_runner or _run_command
    runner(["schtasks.exe", "/End", "/TN", normalized])
    result = runner(["schtasks.exe", "/Delete", "/TN", normalized, "/F"])
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        if _is_task_not_found_message(message):
            remove_scheduler_registry_entry(normalized, registry_path=registry_path)
            return SchedulerDeleteResult(status="not_found", task_name=normalized, skipped_reason=message)
        raise RuntimeError(message or "Windows Task Scheduler delete failed.")
    _delete_launcher_for_task(normalized, Path(launcher_dir))
    remove_scheduler_registry_entry(normalized, registry_path=registry_path)
    return SchedulerDeleteResult(status="deleted", task_name=normalized)


def stop_managed_tasks(
    *,
    delete_tasks: bool = False,
    command_runner: CommandRunner | None = None,
    is_windows: bool | None = None,
    launcher_dir: str | Path = DEFAULT_LAUNCHER_DIR,
    registry_path: str | Path = DEFAULT_SCHEDULER_REGISTRY_PATH,
) -> SchedulerStopResult:
    """Stop this project namespace's scheduled tasks, optionally deleting them."""
    if is_windows is None:
        is_windows = os.name == "nt"
    if not is_windows:
        return SchedulerStopResult(status="skipped", skipped_reason="not_windows")

    runner = command_runner or _run_command
    tasks = list_managed_tasks(command_runner=runner)
    ended: list[str] = []
    deleted: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []
    for task_name in tasks:
        end_result = runner(["schtasks.exe", "/End", "/TN", task_name])
        if end_result.returncode == 0:
            ended.append(task_name)
        else:
            message = (end_result.stderr or end_result.stdout or "").strip()
            skipped.append(f"{task_name}: {message or 'not running'}")
        if not delete_tasks:
            continue
        delete_result = runner(["schtasks.exe", "/Delete", "/TN", task_name, "/F"])
        if delete_result.returncode == 0:
            deleted.append(task_name)
            _delete_launcher_for_task(task_name, Path(launcher_dir))
            remove_scheduler_registry_entry(task_name, registry_path=registry_path)
            continue
        message = (delete_result.stderr or delete_result.stdout or "").strip()
        if _is_task_not_found_message(message):
            deleted.append(task_name)
            _delete_launcher_for_task(task_name, Path(launcher_dir))
            remove_scheduler_registry_entry(task_name, registry_path=registry_path)
        else:
            errors.append(f"{task_name}: {message or 'Windows Task Scheduler delete failed.'}")
    if delete_tasks and not errors:
        _write_scheduler_registry([], registry_path=registry_path)
    return SchedulerStopResult(
        status="failed" if errors else "stopped",
        ended=ended,
        deleted=deleted,
        skipped=skipped,
        errors=errors,
    )


def stop_managed_tasks_with_script(
    *,
    delete_tasks: bool = True,
    project_root: str | Path = APP_ROOT,
    command_runner: CommandRunner | None = None,
    is_windows: bool | None = None,
    registry_path: str | Path = DEFAULT_SCHEDULER_REGISTRY_PATH,
) -> SchedulerStopResult:
    """Run the checked-in stop script used by the UI's monitoring stop button."""
    if is_windows is None:
        is_windows = os.name == "nt"
    if not is_windows:
        return SchedulerStopResult(status="skipped", skipped_reason="not_windows")
    runner = command_runner or _run_command
    args = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(STOP_SCRIPT.resolve()),
        "-ProjectRoot",
        str(Path(project_root).resolve()),
    ]
    if delete_tasks:
        args.append("-DeleteTasks")
    result = runner(args)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        return SchedulerStopResult(status="failed", errors=[message or "Stop-OrchestrationJobs.ps1 failed."])
    if delete_tasks:
        _write_scheduler_registry([], registry_path=registry_path)
    stdout_lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return SchedulerStopResult(
        status="stopped",
        ended=[line for line in stdout_lines if line.startswith("Stopped ")],
        deleted=[line for line in stdout_lines if line.startswith("Deleted ")],
        skipped=[line for line in stdout_lines if line.startswith("Skipped ") or line.startswith("No managed")],
    )


def load_scheduler_registry(
    *,
    registry_path: str | Path = DEFAULT_SCHEDULER_REGISTRY_PATH,
) -> list[dict[str, Any]]:
    try:
        payload = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    entries = payload.get("tasks")
    return [entry for entry in entries if isinstance(entry, dict)] if isinstance(entries, list) else []


def write_scheduler_registry(
    settings: dict[str, Any],
    jobs: Iterable[RegisteredJob],
    *,
    registry_path: str | Path = DEFAULT_SCHEDULER_REGISTRY_PATH,
) -> list[dict[str, Any]]:
    job_settings_by_id = settings.get("jobs") if isinstance(settings.get("jobs"), dict) else {}
    tasks: list[dict[str, Any]] = []
    allow_email_send = bool(settings.get("allow_email_send", False))
    for job in jobs:
        job_settings = job_settings_by_id.get(job.job_id)
        if not isinstance(job_settings, dict) or not job_settings.get("enabled"):
            continue
        for plan in _schedule_task_plans_from_job_settings(job.job_id, job_settings):
            tasks.append(
                {
                    "task_name": plan.task_name,
                    "job_id": job.job_id,
                    "config_name": job.config_name,
                    "config_path": job.config_path,
                    "output_dir": job.output_dir,
                    "search_terms_count": len(job.search_terms),
                    "filter_terms_count": len(job.filter_terms),
                    "interval": normalize_interval(job_settings.get("interval")),
                    "cron": normalize_cron_expression(job_settings.get("cron") or ""),
                    "schedule_strategy": plan.strategy,
                    "task_variant": plan.variant,
                    "allow_email_send": allow_email_send,
                    "registered_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
            )
    _write_scheduler_registry(tasks, registry_path=registry_path)
    return tasks


def remove_scheduler_registry_entry(
    task_name: str,
    *,
    registry_path: str | Path = DEFAULT_SCHEDULER_REGISTRY_PATH,
) -> None:
    normalized = str(task_name or "").strip()
    tasks = [entry for entry in load_scheduler_registry(registry_path=registry_path) if entry.get("task_name") != normalized]
    _write_scheduler_registry(tasks, registry_path=registry_path)


def _write_scheduler_registry(tasks: list[dict[str, Any]], *, registry_path: str | Path) -> None:
    path = Path(registry_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(
        json.dumps({"updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tasks": tasks}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)


def managed_task_name(job_id: str, variant: str = "") -> str:
    digest = hashlib.sha1(job_id.encode("utf-8")).hexdigest()[:12]
    suffix = f"_{safe_task_suffix(variant)}" if variant else ""
    return f"{TASK_FOLDER}\\{TASK_PREFIX}{digest}{suffix}"


def safe_task_suffix(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value or "").strip())
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    return cleaned[:24] or "variant"


def write_task_launcher(
    project_root: str | Path,
    job_id: str = "",
    *,
    launcher_dir: str | Path = DEFAULT_LAUNCHER_DIR,
    allow_email_send: bool = False,
    task_name: str = "",
    cron_gate: bool = False,
) -> Path:
    root = str(Path(project_root).resolve())
    script = str(RUNNER_SCRIPT.resolve())
    launcher_root = Path(launcher_dir)
    launcher_root.mkdir(parents=True, exist_ok=True)
    launcher_name = Path(task_name or managed_task_name(job_id)).name if job_id else f"{TASK_PREFIX}batch"
    launcher_path = launcher_root / f"{launcher_name}.ps1"
    allow_email_arg = " -AllowEmailSend" if allow_email_send else ""
    job_arg = f" -JobId {_ps_quote(job_id)}" if job_id else ""
    cron_gate_arg = " -CronGate" if cron_gate else ""
    launcher_path.write_text(
        "\n".join(
            [
                '$ErrorActionPreference = "Stop"',
                f"Set-Location -LiteralPath {_ps_quote(root)}",
                f"& {_ps_quote(script)} -ProjectRoot {_ps_quote(root)}{job_arg}{allow_email_arg}{cron_gate_arg}",
                "exit $LASTEXITCODE",
                "",
            ]
        ),
        encoding="utf-8-sig",
    )
    return launcher_path


def build_task_action(launcher_path: str | Path) -> str:
    launcher = str(Path(launcher_path).resolve())
    return f'powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{launcher}"'


def _delete_managed_launchers(launcher_dir: Path) -> None:
    if not launcher_dir.exists():
        return
    for path in list(launcher_dir.glob(f"{TASK_PREFIX}*.cmd")) + list(launcher_dir.glob(f"{TASK_PREFIX}*.ps1")):
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _delete_launcher_for_task(task_name: str, launcher_dir: Path) -> None:
    if not launcher_dir.exists():
        return
    launcher_stem = Path(task_name).name
    for suffix in (".cmd", ".ps1"):
        try:
            (launcher_dir / f"{launcher_stem}{suffix}").unlink()
        except FileNotFoundError:
            pass


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _schedule_args(interval: Any) -> list[str]:
    normalized = normalize_interval(interval)
    unit = normalized["unit"]
    raw_value = normalized["value"]
    value = str(raw_value)
    start_time = (datetime.now() + _interval_delta(unit, raw_value)).strftime("%H:%M")
    if unit == "minutes":
        return ["/SC", "MINUTE", "/MO", value, "/ST", start_time]
    if unit == "hours":
        return ["/SC", "HOURLY", "/MO", value, "/ST", start_time]
    return ["/SC", "DAILY", "/MO", value, "/ST", start_time]


def _schedule_args_from_job_settings(job_settings: dict[str, Any]) -> list[str]:
    cron_expr = str(job_settings.get("cron") or "").strip()
    if cron_expr:
        return cron_to_schtasks_args(cron_expr)
    return _schedule_args(job_settings.get("interval"))


def _schedule_task_plans_from_job_settings(job_id: str, job_settings: dict[str, Any]) -> list[SchedulerTaskPlan]:
    cron_expr = str(job_settings.get("cron") or "").strip()
    if not cron_expr:
        return [SchedulerTaskPlan(task_name=managed_task_name(job_id), schedule_args=_schedule_args(job_settings.get("interval")))]
    plans = cron_to_schtasks_task_plans(cron_expr, job_id=job_id)
    if plans:
        return plans
    return [SchedulerTaskPlan(task_name=managed_task_name(job_id), schedule_args=cron_to_schtasks_args(cron_expr))]


def cron_to_schtasks_task_plans(cron_expr: str, *, job_id: str) -> list[SchedulerTaskPlan]:
    """Return one or more concrete schtasks plans for a supported cron expression."""
    expression = normalize_cron_expression(cron_expr)
    try:
        return [
            SchedulerTaskPlan(
                task_name=managed_task_name(job_id),
                schedule_args=cron_to_schtasks_args(expression),
                strategy="single_schtasks",
            )
        ]
    except ValueError as original_error:
        split = _split_cron_to_single_schtasks_expressions(expression)
        if not split:
            raise original_error
        return [
            SchedulerTaskPlan(
                task_name=managed_task_name(job_id, variant=variant),
                schedule_args=cron_to_schtasks_args(split_expr),
                strategy="split_schtasks",
                variant=variant,
            )
            for variant, split_expr in split
        ]


def cron_to_schtasks_args(cron_expr: str) -> list[str]:
    parts = _cron_parts(cron_expr)
    minute, hour, day_of_month, month, day_of_week = parts
    if month != "*":
        raise ValueError("month field is not supported. Use '*' for month.")

    if minute == "*" and hour == "*" and day_of_month == "*" and day_of_week == "*":
        return ["/SC", "MINUTE", "/MO", "1", "/ST", _format_time(datetime.now().hour, datetime.now().minute)]

    if minute.startswith("*/") and hour == "*" and day_of_month == "*" and day_of_week == "*":
        step = _parse_step(minute, "minute")
        return ["/SC", "MINUTE", "/MO", str(step), "/ST", _format_time(datetime.now().hour, 0)]

    if minute.startswith("*/"):
        raise ValueError("minute intervals are supported only when hour, day-of-month, and day-of-week are '*'.")
    minute_value = _parse_single_number(minute, "minute", 0, 59)
    if day_of_month != "*" and day_of_week != "*":
        raise ValueError("cron day-of-month and day-of-week cannot both be specific in this scheduler.")

    if minute_value is None:
        raise ValueError("minute field must be a number, or */N for all-day minute intervals.")

    if hour.startswith("*/") and day_of_month == "*" and day_of_week == "*":
        step = _parse_step(hour, "hour")
        return ["/SC", "HOURLY", "/MO", str(step), "/ST", _format_time(datetime.now().hour, minute_value)]

    if hour.startswith("*/"):
        raise ValueError("hour intervals are supported only when day-of-month and day-of-week are '*'.")
    hour_value = _parse_single_number(hour, "hour", 0, 23, allow_any=True)

    if hour == "*" and day_of_month == "*" and day_of_week == "*":
        return ["/SC", "HOURLY", "/MO", "1", "/ST", _format_time(datetime.now().hour, minute_value)]

    if hour_value is None:
        raise ValueError("hour field must be '*' or a number.")

    if day_of_month == "*" and day_of_week == "*":
        return ["/SC", "DAILY", "/MO", "1", "/ST", _format_time(hour_value, minute_value)]

    if day_of_week != "*":
        weekdays = _parse_weekdays(day_of_week)
        return ["/SC", "WEEKLY", "/MO", "1", "/D", ",".join(weekdays), "/ST", _format_time(hour_value, minute_value)]

    if day_of_month.startswith("*/"):
        day_step = _parse_step(day_of_month, "day-of-month")
        return ["/SC", "DAILY", "/MO", str(day_step), "/ST", _format_time(hour_value, minute_value)]

    day_value = _parse_single_number(day_of_month, "day_of_month", 1, 31)
    if day_value is None:
        raise ValueError("day-of-month field must be '*' or a number between 1 and 31.")
    return ["/SC", "MONTHLY", "/MO", "1", "/D", str(day_value), "/ST", _format_time(hour_value, minute_value)]


def _parse_single_number(value: str, field_name: str, min_value: int, max_value: int, allow_any: bool = False) -> int | None:
    if value == "*":
        return None if allow_any else None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} field must be a number.") from exc
    if parsed < min_value or parsed > max_value:
        raise ValueError(f"{field_name} field must be between {min_value} and {max_value}.")
    return parsed


def _parse_step(value: str, field_name: str) -> int:
    if not value.startswith("*/"):
        raise ValueError(f"{field_name} interval must use */N format.")
    try:
        parsed = int(value[2:])
    except ValueError as exc:
        raise ValueError(f"{field_name} interval must be a number in */N.") from exc
    if parsed <= 0:
        raise ValueError(f"{field_name} interval must be greater than 0.")
    return parsed


def _parse_weekdays(value: str) -> list[str]:
    mapping = {
        "0": "SUN",
        "7": "SUN",
        "1": "MON",
        "2": "TUE",
        "3": "WED",
        "4": "THU",
        "5": "FRI",
        "6": "SAT",
        "SUN": "SUN",
        "MON": "MON",
        "TUE": "TUE",
        "WED": "WED",
        "THU": "THU",
        "FRI": "FRI",
        "SAT": "SAT",
    }
    weekdays: list[str] = []
    for token in [item.strip().upper() for item in value.split(",") if item.strip()]:
        if "-" in token:
            start, end = token.split("-", 1)
            start_mapped = mapping.get(start)
            end_mapped = mapping.get(end)
            if start_mapped is None or end_mapped is None:
                raise ValueError("day-of-week field must be 0-7 or SUN..SAT (comma separated).")
            order = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]
            start_index = order.index(start_mapped)
            end_index = order.index(end_mapped)
            if start_index > end_index:
                raise ValueError("day-of-week ranges cannot wrap around the week.")
            for mapped in order[start_index : end_index + 1]:
                if mapped not in weekdays:
                    weekdays.append(mapped)
            continue
        mapped = mapping.get(token)
        if mapped is None:
            raise ValueError("day-of-week field must be 0-7 or SUN..SAT (comma separated).")
        if mapped not in weekdays:
            weekdays.append(mapped)
    if not weekdays:
        raise ValueError("day-of-week field is empty.")
    return weekdays


def _cron_parts(cron_expr: str) -> list[str]:
    parts = [part.strip() for part in str(cron_expr or "").split() if part.strip()]
    if len(parts) != 5:
        raise ValueError("cron must have 5 fields like '*/5 * * * *' or '0 3 * * *'.")
    return parts


def _split_cron_to_single_schtasks_expressions(cron_expr: str) -> list[tuple[str, str]]:
    minute, hour, day_of_month, month, day_of_week = _cron_parts(cron_expr)
    if month != "*" or day_of_month != "*":
        return []
    minute_values = _finite_cron_values(minute, minimum=0, maximum=59)
    hour_values = _finite_cron_values(hour, minimum=0, maximum=23)
    if minute_values is None and hour_values is None:
        return []
    if minute_values is None:
        return []
    hours = hour_values if hour_values is not None else [None]
    variants: list[tuple[str, str]] = []
    for minute_value in minute_values:
        for hour_value in hours:
            split_hour = "*" if hour_value is None else str(hour_value)
            variant = f"m{minute_value:02d}" if hour_value is None else f"h{hour_value:02d}m{minute_value:02d}"
            variants.append((variant, f"{minute_value} {split_hour} {day_of_month} {month} {day_of_week}"))
    if len(variants) > MAX_SPLIT_TASKS_PER_JOB:
        raise ValueError(
            f"cron expands to {len(variants)} Windows tasks; maximum supported without tick-runner strategy is {MAX_SPLIT_TASKS_PER_JOB}."
        )
    return variants


def _finite_cron_values(field: str, *, minimum: int, maximum: int) -> list[int] | None:
    if field == "*" or field.startswith("*/"):
        return None
    values: list[int] = []
    for part in field.split(","):
        token = part.strip()
        if not token:
            raise ValueError("cron field contains an empty token.")
        if "-" in token:
            start_raw, end_raw = token.split("-", 1)
            start = int(start_raw)
            end = int(end_raw)
            if start < minimum or end > maximum or start > end:
                raise ValueError(f"cron range must be between {minimum} and {maximum}.")
            values.extend(range(start, end + 1))
            continue
        value = int(token)
        if value < minimum or value > maximum:
            raise ValueError(f"cron value must be between {minimum} and {maximum}.")
        values.append(value)
    deduped = sorted(set(values))
    return deduped


def cron_to_tick_runner_args(cron_expr: str) -> list[str]:
    normalize_cron_expression(cron_expr)
    return ["/SC", "MINUTE", "/MO", "1", "/ST", _format_time(datetime.now().hour, datetime.now().minute)]


def cron_schedule_strategy_report(cron_expr: str) -> dict[str, Any]:
    expression = normalize_cron_expression(cron_expr)
    report: dict[str, Any] = {"cron": expression, "strategies": {}}
    try:
        single = cron_to_schtasks_args(expression)
        report["strategies"]["single_schtasks"] = {
            "supported": True,
            "task_count": 1,
            "trigger_count": 1,
            "runner_invocations_per_hour": _estimate_invocations_per_hour(expression),
            "schedule_args": single,
        }
    except ValueError as exc:
        report["strategies"]["single_schtasks"] = {"supported": False, "reason": str(exc)}

    try:
        split = _split_cron_to_single_schtasks_expressions(expression)
        report["strategies"]["split_schtasks"] = {
            "supported": bool(split),
            "task_count": len(split) if split else 0,
            "trigger_count": len(split) if split else 0,
            "runner_invocations_per_hour": _estimate_invocations_per_hour(expression),
        }
    except ValueError as exc:
        report["strategies"]["split_schtasks"] = {"supported": False, "reason": str(exc)}

    multi_trigger_specs = cron_to_multi_trigger_specs(expression)
    report["strategies"]["multi_trigger_task"] = {
        "supported": bool(multi_trigger_specs),
        "registration_path": "spec_only",
        "task_count": 1,
        "trigger_count": len(multi_trigger_specs),
        "runner_invocations_per_hour": _estimate_invocations_per_hour(expression),
    }
    report["strategies"]["tick_runner"] = {
        "supported": True,
        "task_count": 1,
        "trigger_count": 1,
        "runner_invocations_per_hour": 60,
        "schedule_args": cron_to_tick_runner_args(expression),
    }
    report["recommended"] = _recommend_cron_strategy(report)
    return report


def cron_to_multi_trigger_specs(cron_expr: str) -> list[dict[str, Any]]:
    """Build trigger specs for one Windows task with multiple triggers.

    This is a side-by-side implementation surface for comparing the "one task,
    many triggers" strategy. Registration is intentionally kept separate from
    the current schtasks sync path because multi-trigger registration requires a
    PowerShell ScheduledTasks/COM or XML task definition path.
    """
    expression = normalize_cron_expression(cron_expr)
    if not _multi_trigger_supported(expression):
        return []
    minute, hour, _day_of_month, _month, day_of_week = _cron_parts(expression)
    minute_values = _finite_cron_values(minute, minimum=0, maximum=59) or list(range(60))
    hour_values = _finite_cron_values(hour, minimum=0, maximum=23)
    day_values = _parse_weekdays(day_of_week) if day_of_week != "*" else []
    specs: list[dict[str, Any]] = []
    if hour_values is None:
        for minute_value in minute_values:
            specs.append(
                {
                    "type": "weekly" if day_values else "daily",
                    "at": _format_time(0, minute_value),
                    "days_of_week": day_values,
                    "repetition_interval": "PT1H",
                    "repetition_duration": "P1D",
                }
            )
        return specs
    for hour_value in hour_values:
        for minute_value in minute_values:
            specs.append(
                {
                    "type": "weekly" if day_values else "daily",
                    "at": _format_time(hour_value, minute_value),
                    "days_of_week": day_values,
                }
            )
    return specs


def build_multi_trigger_task_xml(cron_expr: str, task_command: str) -> str:
    specs = cron_to_multi_trigger_specs(cron_expr)
    if not specs:
        raise ValueError("cron expression cannot be represented as a bounded multi-trigger task.")
    task = ET.Element("Task", {"version": "1.4", "xmlns": "http://schemas.microsoft.com/windows/2004/02/mit/task"})
    registration = ET.SubElement(task, "RegistrationInfo")
    ET.SubElement(registration, "Description").text = "Crawler orchestration scheduled task"
    triggers = ET.SubElement(task, "Triggers")
    for spec in specs:
        trigger = ET.SubElement(triggers, "CalendarTrigger")
        ET.SubElement(trigger, "StartBoundary").text = f"2000-01-01T{spec['at']}:00"
        ET.SubElement(trigger, "Enabled").text = "true"
        if spec.get("repetition_interval"):
            repetition = ET.SubElement(trigger, "Repetition")
            ET.SubElement(repetition, "Interval").text = str(spec["repetition_interval"])
            ET.SubElement(repetition, "Duration").text = str(spec["repetition_duration"])
            ET.SubElement(repetition, "StopAtDurationEnd").text = "false"
        if spec.get("days_of_week"):
            weekly = ET.SubElement(trigger, "ScheduleByWeek")
            days = ET.SubElement(weekly, "DaysOfWeek")
            for day in spec["days_of_week"]:
                ET.SubElement(days, _windows_xml_weekday_name(str(day)))
            ET.SubElement(weekly, "WeeksInterval").text = "1"
        else:
            daily = ET.SubElement(trigger, "ScheduleByDay")
            ET.SubElement(daily, "DaysInterval").text = "1"
    settings = ET.SubElement(task, "Settings")
    ET.SubElement(settings, "MultipleInstancesPolicy").text = "IgnoreNew"
    ET.SubElement(settings, "DisallowStartIfOnBatteries").text = "false"
    ET.SubElement(settings, "StopIfGoingOnBatteries").text = "false"
    ET.SubElement(settings, "AllowHardTerminate").text = "true"
    ET.SubElement(settings, "StartWhenAvailable").text = "true"
    ET.SubElement(settings, "Enabled").text = "true"
    ET.SubElement(settings, "Hidden").text = "false"
    actions = ET.SubElement(task, "Actions", {"Context": "Author"})
    exec_action = ET.SubElement(actions, "Exec")
    command, arguments = _split_task_command(task_command)
    ET.SubElement(exec_action, "Command").text = command
    if arguments:
        ET.SubElement(exec_action, "Arguments").text = arguments
    return ET.tostring(task, encoding="unicode")


def _split_task_command(task_command: str) -> tuple[str, str]:
    command = str(task_command or "").strip()
    if not command:
        raise ValueError("task command is empty.")
    if command.startswith('"'):
        end = command.find('"', 1)
        if end > 0:
            return command[1:end], command[end + 1 :].strip()
    parts = command.split(maxsplit=1)
    return parts[0], parts[1] if len(parts) > 1 else ""


def _windows_xml_weekday_name(value: str) -> str:
    return {
        "SUN": "Sunday",
        "MON": "Monday",
        "TUE": "Tuesday",
        "WED": "Wednesday",
        "THU": "Thursday",
        "FRI": "Friday",
        "SAT": "Saturday",
    }[value]


def _multi_trigger_supported(cron_expr: str) -> bool:
    minute, hour, day_of_month, month, _day_of_week = _cron_parts(cron_expr)
    if month != "*" or day_of_month != "*":
        return False
    if minute == "*" or minute.startswith("*/") or hour.startswith("*/"):
        return False
    return _multi_trigger_count(cron_expr) <= MAX_SPLIT_TASKS_PER_JOB


def _multi_trigger_count(cron_expr: str) -> int:
    minute, hour, _day_of_month, _month, _day_of_week = _cron_parts(cron_expr)
    minute_values = _finite_cron_values(minute, minimum=0, maximum=59) or list(range(60))
    hour_values = _finite_cron_values(hour, minimum=0, maximum=23)
    if hour_values is None:
        return len(minute_values)
    return len(minute_values) * len(hour_values)


def _estimate_invocations_per_hour(cron_expr: str) -> int:
    minute, hour, _day_of_month, _month, _day_of_week = _cron_parts(cron_expr)
    minute_values = _finite_cron_values(minute, minimum=0, maximum=59)
    if minute_values is not None:
        return len(minute_values)
    if minute == "*":
        return 60
    if minute.startswith("*/"):
        step = _parse_step(minute, "minute")
        return max(1, 60 // step)
    return 1


def _recommend_cron_strategy(report: dict[str, Any]) -> str:
    strategies = report.get("strategies") if isinstance(report.get("strategies"), dict) else {}
    if strategies.get("single_schtasks", {}).get("supported"):
        return "single_schtasks"
    if strategies.get("split_schtasks", {}).get("supported"):
        return "split_schtasks"
    if strategies.get("multi_trigger_task", {}).get("supported"):
        return "multi_trigger_task"
    return "tick_runner"


def _format_time(hour: int, minute: int) -> str:
    return f"{hour:02d}:{minute:02d}"


def _interval_delta(unit: str, value: int) -> timedelta:
    if unit == "minutes":
        return timedelta(minutes=value)
    if unit == "hours":
        return timedelta(hours=value)
    return timedelta(days=value)


def _run_command(args: list[str]) -> SchedulerCommandResult:
    completed = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding=_windows_command_encoding(),
        errors="replace",
        check=False,
    )
    return SchedulerCommandResult(completed.returncode, completed.stdout, completed.stderr)


def _windows_command_encoding() -> str:
    if os.name == "nt" and hasattr(locale, "getencoding"):
        return locale.getencoding() or "utf-8"
    return locale.getpreferredencoding(False) or "utf-8"


def _is_task_not_found_message(message: str) -> bool:
    normalized = message.casefold()
    return (
        "cannot find" in normalized
        or "not exist" in normalized
        or "not found" in normalized
        or "찾을 수" in message
        or "찾을수" in message
        or "없습니다" in message
    )


def _checked_run(runner: CommandRunner, args: list[str]) -> SchedulerCommandResult:
    result = runner(args)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "Windows Task Scheduler command failed.").strip()
        raise RuntimeError(message)
    return result
