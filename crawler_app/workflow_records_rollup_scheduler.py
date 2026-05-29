from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any, Callable
import json

from crawler_app.workflow_records_rollup import (
    DEFAULT_KEEP_COUNT,
    DEFAULT_ROLLUP_TIME,
    KST,
    rollup_workflow_records,
)


DEFAULT_CHECK_INTERVAL_SECONDS = 30.0


class WorkflowRecordsRollupScheduler:
    """Run workflow_records rollup inside the web server process."""

    def __init__(
        self,
        *,
        project_root: str | Path,
        rollup_time: str = DEFAULT_ROLLUP_TIME,
        keep_count: int = DEFAULT_KEEP_COUNT,
        check_interval_seconds: float = DEFAULT_CHECK_INTERVAL_SECONDS,
        rollup_func: Callable[..., dict[str, Any]] = rollup_workflow_records,
        now_func: Callable[[], datetime] | None = None,
    ) -> None:
        self.project_root = Path(project_root)
        self.rollup_time = rollup_time
        self.keep_count = keep_count
        self.check_interval_seconds = max(1.0, float(check_interval_seconds))
        self._rollup_func = rollup_func
        self._now_func = now_func or (lambda: datetime.now(KST))
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._lock = Lock()
        self._last_run_date: date | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        with self._lock:
            if self.running:
                return
            self._stop_event.clear()
            self._thread = Thread(
                target=self._run_loop,
                name="workflow-records-rollup-scheduler",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)

    def run_once_if_due(self, now: datetime | None = None) -> dict[str, Any] | None:
        current_time = _ensure_kst(now or self._now_func())
        if not _is_due(current_time, self.rollup_time, self._last_run_date):
            return None
        summary = self._execute_rollup(current_time)
        self._last_run_date = current_time.date()
        return summary

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            now = _ensure_kst(self._now_func())
            self.run_once_if_due(now)
            next_run = next_rollup_datetime(now, self.rollup_time, last_run_date=self._last_run_date)
            wait_seconds = max(1.0, min(self.check_interval_seconds, (next_run - now).total_seconds()))
            self._stop_event.wait(wait_seconds)

    def _execute_rollup(self, current_time: datetime) -> dict[str, Any]:
        try:
            summary = self._rollup_func(
                outputs_root=self.project_root / "outputs",
                now=current_time,
                keep_count=self.keep_count,
            )
            self._write_log(current_time, summary=summary)
            return summary
        except Exception as exc:
            summary = {"errors": [{"error": str(exc), "exception_type": type(exc).__name__}]}
            self._write_log(current_time, summary=summary)
            return summary

    def _write_log(self, current_time: datetime, *, summary: dict[str, Any]) -> None:
        log_dir = self.project_root / "runtime" / "scheduled-task"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{current_time.strftime('%Y%m%d_%H%M%S')}-workflow-records-rollup-python.log"
        payload = {
            "started_at": current_time.isoformat(),
            "rollup_time": self.rollup_time,
            "keep_count": self.keep_count,
            "summary": summary,
        }
        log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def next_rollup_datetime(
    now: datetime,
    rollup_time: str = DEFAULT_ROLLUP_TIME,
    *,
    last_run_date: date | None = None,
) -> datetime:
    current_time = _ensure_kst(now)
    hour, minute = parse_rollup_time(rollup_time)
    candidate = current_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= current_time or last_run_date == current_time.date():
        candidate += timedelta(days=1)
    return candidate


def parse_rollup_time(value: str) -> tuple[int, int]:
    parts = str(value or "").strip().split(":")
    if len(parts) != 2:
        raise ValueError("Rollup time must be HH:MM.")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError as exc:
        raise ValueError("Rollup time must be HH:MM.") from exc
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("Rollup time must be a valid 24-hour HH:MM value.")
    return hour, minute


def _is_due(now: datetime, rollup_time: str, last_run_date: date | None) -> bool:
    current_time = _ensure_kst(now)
    if last_run_date == current_time.date():
        return False
    hour, minute = parse_rollup_time(rollup_time)
    due_at = current_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return current_time >= due_at


def _ensure_kst(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=KST)
    return value.astimezone(KST)
