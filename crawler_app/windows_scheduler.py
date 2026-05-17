from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable
import csv
import hashlib
import io
import os
import subprocess

from crawler_app.orchestration import APP_ROOT, RegisteredJob, normalize_interval


TASK_FOLDER = r"\CrawlerOrchestration"
TASK_PREFIX = "crawler_"
RUNNER_SCRIPT = APP_ROOT / "scripts" / "Run-OrchestrationJob.ps1"
DEFAULT_LAUNCHER_DIR = Path(os.environ.get("LOCALAPPDATA") or APP_ROOT / "runtime") / "CrawlerOrchestration"


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


CommandRunner = Callable[[list[str]], SchedulerCommandResult]


def sync_windows_scheduled_tasks(
    settings: dict[str, Any],
    jobs: Iterable[RegisteredJob],
    *,
    project_root: str | Path = APP_ROOT,
    command_runner: CommandRunner | None = None,
    is_windows: bool | None = None,
    launcher_dir: str | Path = DEFAULT_LAUNCHER_DIR,
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
    jobs_by_id = {job.job_id: job for job in jobs}
    created: list[str] = []
    for job_id, job_settings in (settings.get("jobs") or {}).items():
        if not isinstance(job_settings, dict) or not job_settings.get("enabled"):
            continue
        job = jobs_by_id.get(job_id)
        if job is None:
            continue
        task_name = managed_task_name(job.job_id)
        schedule_args = _schedule_args(job_settings.get("interval"))
        launcher_path = write_task_launcher(project_root, job.job_id, launcher_dir=launcher_dir)
        task_command = build_task_action(launcher_path)
        _checked_run(
            runner,
            [
                "schtasks.exe",
                "/Create",
                "/F",
                "/TN",
                task_name,
                "/TR",
                task_command,
                *schedule_args,
            ],
        )
        created.append(task_name)

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


def managed_task_name(job_id: str) -> str:
    digest = hashlib.sha1(job_id.encode("utf-8")).hexdigest()[:12]
    return f"{TASK_FOLDER}\\{TASK_PREFIX}{digest}"


def write_task_launcher(project_root: str | Path, job_id: str, *, launcher_dir: str | Path = DEFAULT_LAUNCHER_DIR) -> Path:
    root = str(Path(project_root).resolve())
    script = str(RUNNER_SCRIPT.resolve())
    launcher_root = Path(launcher_dir)
    launcher_root.mkdir(parents=True, exist_ok=True)
    launcher_path = launcher_root / f"{Path(managed_task_name(job_id)).name}.ps1"
    launcher_path.write_text(
        "\n".join(
            [
                '$ErrorActionPreference = "Stop"',
                f"Set-Location -LiteralPath {_ps_quote(root)}",
                f"& {_ps_quote(script)} -ProjectRoot {_ps_quote(root)} -JobId {_ps_quote(job_id)} -AllowEmailSend",
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
