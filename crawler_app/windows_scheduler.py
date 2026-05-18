from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
import csv
import hashlib
import io
import json
import os
import subprocess

from crawler_app.orchestration import APP_ROOT, RegisteredJob, normalize_interval


TASK_FOLDER = r"\CrawlerOrchestration"
TASK_PREFIX = "crawler_"
RUNNER_SCRIPT = APP_ROOT / "scripts" / "Run-OrchestrationJob.ps1"
DEFAULT_LAUNCHER_DIR = Path(os.environ.get("LOCALAPPDATA") or APP_ROOT / "runtime") / "CrawlerOrchestration"
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
        schedule_args = _schedule_args(job_settings.get("interval"))
        launcher_path = write_task_launcher(
            project_root,
            job.job_id,
            launcher_dir=launcher_dir,
            allow_email_send=bool(settings.get("allow_email_send", False)),
        )
        task_command = build_task_action(launcher_path)
        _checked_run(
            runner,
            [
                "schtasks.exe",
                "/Create",
                "/F",
                "/TN",
                managed_task_name(job.job_id),
                "/TR",
                task_command,
                *schedule_args,
            ],
        )
        created.append(managed_task_name(job.job_id))

    write_scheduler_registry(settings, jobs, registry_path=registry_path)
    return SchedulerSyncResult(status="synced", deleted=deleted, created=created)


def list_managed_tasks(*, command_runner: CommandRunner | None = None) -> list[str]:
    runner = command_runner or _run_command
    result = _checked_run(runner, ["schtasks.exe", "/Query", "/FO", "CSV"])
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
    result = _checked_run(runner, ["schtasks.exe", "/Query", "/FO", "CSV", "/V"])
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
    result = _checked_run(runner, ["schtasks.exe", "/Query", "/FO", "CSV"])
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
    script = (
        "Get-ScheduledTask -TaskPath '\\CrawlerOrchestration\\' -ErrorAction SilentlyContinue | "
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
    result = _checked_run(runner, ["powershell.exe", "-NoProfile", "-Command", script])
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
        if "cannot find" in message.casefold() or "not exist" in message.casefold():
            remove_scheduler_registry_entry(normalized, registry_path=registry_path)
            return SchedulerDeleteResult(status="not_found", task_name=normalized, skipped_reason=message)
        raise RuntimeError(message or "Windows Task Scheduler delete failed.")
    _delete_launcher_for_task(normalized, Path(launcher_dir))
    remove_scheduler_registry_entry(normalized, registry_path=registry_path)
    return SchedulerDeleteResult(status="deleted", task_name=normalized)


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
        tasks.append(
            {
                "task_name": managed_task_name(job.job_id),
                "job_id": job.job_id,
                "config_name": job.config_name,
                "config_path": job.config_path,
                "output_dir": job.output_dir,
                "search_terms_count": len(job.search_terms),
                "filter_terms_count": len(job.filter_terms),
                "interval": normalize_interval(job_settings.get("interval")),
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


def managed_task_name(job_id: str) -> str:
    digest = hashlib.sha1(job_id.encode("utf-8")).hexdigest()[:12]
    return f"{TASK_FOLDER}\\{TASK_PREFIX}{digest}"


def write_task_launcher(
    project_root: str | Path,
    job_id: str = "",
    *,
    launcher_dir: str | Path = DEFAULT_LAUNCHER_DIR,
    allow_email_send: bool = False,
) -> Path:
    root = str(Path(project_root).resolve())
    script = str(RUNNER_SCRIPT.resolve())
    launcher_root = Path(launcher_dir)
    launcher_root.mkdir(parents=True, exist_ok=True)
    launcher_name = Path(managed_task_name(job_id)).name if job_id else f"{TASK_PREFIX}batch"
    launcher_path = launcher_root / f"{launcher_name}.ps1"
    allow_email_arg = " -AllowEmailSend" if allow_email_send else ""
    job_arg = f" -JobId {_ps_quote(job_id)}" if job_id else ""
    launcher_path.write_text(
        "\n".join(
            [
                '$ErrorActionPreference = "Stop"',
                f"Set-Location -LiteralPath {_ps_quote(root)}",
                f"& {_ps_quote(script)} -ProjectRoot {_ps_quote(root)}{job_arg}{allow_email_arg}",
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


def _interval_delta(unit: str, value: int) -> timedelta:
    if unit == "minutes":
        return timedelta(minutes=value)
    if unit == "hours":
        return timedelta(hours=value)
    return timedelta(days=value)


def _run_command(args: list[str]) -> SchedulerCommandResult:
    completed = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    return SchedulerCommandResult(completed.returncode, completed.stdout, completed.stderr)


def _checked_run(runner: CommandRunner, args: list[str]) -> SchedulerCommandResult:
    result = runner(args)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "Windows Task Scheduler command failed.").strip()
        raise RuntimeError(message)
    return result
