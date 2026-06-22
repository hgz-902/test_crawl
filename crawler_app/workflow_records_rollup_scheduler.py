from __future__ import annotations

import ast
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any, Callable

from crawler_app.workflow_records_rollup import (
    DEFAULT_KEEP_COUNT,
    DEFAULT_ROLLUP_TIME,
    KST,
    rollup_workflow_records,
)


DEFAULT_CHECK_INTERVAL_SECONDS = 30.0
DEFAULT_ROLLUP_TIME_SOURCE = Path(__file__).with_name("workflow_records_rollup.py")
RollupRunKey = tuple[date, str]


# workflow records rollup 스케줄러의 상태와 실행 동작을 관리한다.
class WorkflowRecordsRollupScheduler:
    """Run workflow_records rollup inside the web server process."""

    # 객체 생성 시 필요한 초기 상태를 설정한다.
    def __init__(
        self,
        *,
        project_root: str | Path,
        rollup_time: str | None = None,
        rollup_time_source: str | Path | None = DEFAULT_ROLLUP_TIME_SOURCE,
        keep_count: int = DEFAULT_KEEP_COUNT,
        check_interval_seconds: float = DEFAULT_CHECK_INTERVAL_SECONDS,
        rollup_func: Callable[..., dict[str, Any]] = rollup_workflow_records,
        now_func: Callable[[], datetime] | None = None,
    ) -> None:
        self.project_root = Path(project_root)
        self.rollup_time = rollup_time or DEFAULT_ROLLUP_TIME
        self.rollup_time_source = Path(rollup_time_source) if rollup_time_source is not None else None
        self.keep_count = keep_count
        self.check_interval_seconds = max(1.0, float(check_interval_seconds))
        self._rollup_func = rollup_func
        self._now_func = now_func or (lambda: datetime.now(KST))
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._lock = Lock()
        self._last_run_key: RollupRunKey | None = None

    # running 값을 계산해 반환한다.
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # 값를 시작한다.
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

    # 값를 중지한다.
    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)

    # once if due를 실행한다.
    def run_once_if_due(self, now: datetime | None = None) -> dict[str, Any] | None:
        current_time = _ensure_kst(now or self._now_func())
        rollup_time = self._current_rollup_time()
        if not _is_due(current_time, rollup_time, self._last_run_key):
            return None
        summary = self._execute_rollup(current_time, rollup_time=rollup_time)
        self._last_run_key = _run_key(current_time, rollup_time)
        return summary

    # loop를 실행한다.
    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            now = _ensure_kst(self._now_func())
            self.run_once_if_due(now)
            rollup_time = self._current_rollup_time()
            next_run = next_rollup_datetime(now, rollup_time, last_run_key=self._last_run_key)
            wait_seconds = max(1.0, min(self.check_interval_seconds, (next_run - now).total_seconds()))
            self._stop_event.wait(wait_seconds)

    # current rollup 시간 값을 계산해 반환한다.
    def _current_rollup_time(self) -> str:
        if self.rollup_time_source is None:
            return self.rollup_time
        self.rollup_time = read_default_rollup_time_from_source(
            self.rollup_time_source,
            fallback=self.rollup_time,
        )
        return self.rollup_time

    # execute rollup 값을 계산해 반환한다.
    def _execute_rollup(self, current_time: datetime, *, rollup_time: str) -> dict[str, Any]:
        try:
            summary = self._rollup_func(
                outputs_root=self.project_root / "outputs",
                now=current_time,
                keep_count=self.keep_count,
            )
            self._write_log(current_time, rollup_time=rollup_time, summary=summary)
            return summary
        except Exception as exc:
            summary = {"errors": [{"error": str(exc), "exception_type": type(exc).__name__}]}
            self._write_log(current_time, rollup_time=rollup_time, summary=summary)
            return summary

    # log를 파일에 기록한다.
    def _write_log(self, current_time: datetime, *, rollup_time: str, summary: dict[str, Any]) -> None:
        log_dir = self.project_root / "runtime" / "scheduled-task"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{current_time.strftime('%Y%m%d_%H%M%S')}-workflow-records-rollup-python.log"
        payload = {
            "started_at": current_time.isoformat(),
            "rollup_time": rollup_time,
            "keep_count": self.keep_count,
            "summary": summary,
        }
        log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# 소스 파일에서 기본 workflow records rollup 시간을 읽는다.
def read_default_rollup_time_from_source(source_path: str | Path, *, fallback: str = DEFAULT_ROLLUP_TIME) -> str:
    """Read DEFAULT_ROLLUP_TIME from source without restarting the web server."""
    path = Path(source_path)
    try:
        module = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return fallback
    for node in module.body:
        value_node: ast.AST | None = None
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "DEFAULT_ROLLUP_TIME" for target in node.targets
        ):
            value_node = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "DEFAULT_ROLLUP_TIME":
            value_node = node.value
        if value_node is None:
            continue
        try:
            value = ast.literal_eval(value_node)
        except (ValueError, TypeError):
            return fallback
        if isinstance(value, str):
            try:
                parse_rollup_time(value)
            except ValueError:
                return fallback
            return value
    return fallback


# 기준 시각 이후의 다음 rollup 실행 시각을 계산한다.
def next_rollup_datetime(
    now: datetime,
    rollup_time: str = DEFAULT_ROLLUP_TIME,
    *,
    last_run_date: date | None = None,
    last_run_key: RollupRunKey | None = None,
) -> datetime:
    current_time = _ensure_kst(now)
    hour, minute = parse_rollup_time(rollup_time)
    candidate = current_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
    run_key = _run_key(current_time, rollup_time)
    already_ran_today = last_run_key == run_key or (last_run_key is None and last_run_date == current_time.date())
    if candidate <= current_time and not already_ran_today:
        return current_time
    if candidate <= current_time or already_ran_today:
        candidate += timedelta(days=1)
    return candidate


# HH:MM 형식의 rollup 시간을 시와 분으로 파싱한다.
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


# due 여부를 판정한다.
def _is_due(now: datetime, rollup_time: str, last_run_key: RollupRunKey | None) -> bool:
    current_time = _ensure_kst(now)
    if last_run_key == _run_key(current_time, rollup_time):
        return False
    hour, minute = parse_rollup_time(rollup_time)
    due_at = current_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return current_time >= due_at


# key를 실행한다.
def _run_key(current_time: datetime, rollup_time: str) -> RollupRunKey:
    hour, minute = parse_rollup_time(rollup_time)
    normalized_time = f"{hour:02d}:{minute:02d}"
    return (_ensure_kst(current_time).date(), normalized_time)


# kst가 준비된 상태인지 보장한다.
def _ensure_kst(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=KST)
    return value.astimezone(KST)
