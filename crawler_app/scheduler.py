from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crawler_app.base import CrawlResult
from crawler_app.config_store import config_name_to_path, list_configs
from crawler_app.emailer import EmailStatus, send_completion_email
from crawler_app.job_store import JobStore
from crawler_app.logging_utils import configure_logger, log_result
from crawler_app.run_safety import read_config_for_safety, run_safety_error
from crawlers.configurable_crawler import ConfigurableCrawler


class BackgroundJobScheduler:
    def __init__(
        self,
        *,
        store: JobStore,
        base_dir: Path,
        log_dir: Path,
        poll_seconds: float = 10.0,
        max_concurrency: int = 2,
        shutdown_timeout_seconds: float = 10.0,
    ) -> None:
        self.store = store
        self.base_dir = base_dir
        self.log_dir = log_dir
        self.poll_seconds = poll_seconds
        self.shutdown_timeout_seconds = shutdown_timeout_seconds
        self._task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event | None = None
        self._locks: dict[str, asyncio.Lock] = {}
        self._run_tasks: set[asyncio.Task[dict[str, Any]]] = set()
        self._semaphore = asyncio.Semaphore(max_concurrency)

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self.store.recover_interrupted_runs(_active_config_ids())
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._stop_event:
            self._stop_event.set()
        if self._task:
            await self._task
        if self._run_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._run_tasks, return_exceptions=True),
                    timeout=self.shutdown_timeout_seconds,
                )
            except asyncio.TimeoutError:
                for task in list(self._run_tasks):
                    task.cancel()

    async def _loop(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            for config_id in self.store.due_config_ids(active_config_ids=_active_config_ids()):
                task = asyncio.create_task(self.run_job(config_id, trigger="scheduled"))
                self._run_tasks.add(task)
                task.add_done_callback(self._run_tasks.discard)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_seconds)
            except asyncio.TimeoutError:
                pass

    async def run_job(self, config_id: str, *, trigger: str) -> dict[str, Any]:
        lock = self._locks.setdefault(config_id, asyncio.Lock())
        if lock.locked():
            return {"success": False, "message": "Job is already running.", "items_count": 0, "error": "already_running"}

        async with lock:
            async with self._semaphore:
                return await self._run_job_locked(config_id, trigger)

    async def _run_job_locked(self, config_id: str, trigger: str) -> dict[str, Any]:
        started_at = utc_now()
        self.store.mark_started(config_id, started_at)
        try:
            result = await self._execute_config(config_id, started_at)
        except Exception as exc:
            result = _exception_result(config_id, started_at, exc)
        result_dict = result.to_dict()
        finished_at = utc_now()
        self.store.mark_finished(config_id, result_dict, finished_at)
        email_status = await self._send_completion_email(config_id, trigger, result_dict)
        result_dict["metadata"] = dict(result_dict.get("metadata") or {})
        result_dict["metadata"]["completion_email"] = {
            "sent": email_status.sent,
            "reason": email_status.reason,
        }
        self.store.append_history(
            {
                "config_id": config_id,
                "trigger": trigger,
                "success": bool(result_dict.get("success")),
                "items_count": int(result_dict.get("items_count") or 0),
                "started_at": result_dict.get("started_at"),
                "finished_at": result_dict.get("finished_at"),
                "message": result_dict.get("message"),
                "error": result_dict.get("error"),
                "metadata": {
                    "output_dir": (result_dict.get("metadata") or {}).get("output_dir"),
                    "completion_email": result_dict["metadata"]["completion_email"],
                },
            }
        )
        return result_dict

    async def _execute_config(self, config_id: str, started_at: datetime) -> CrawlResult:
        config_path = config_name_to_path(config_id)
        if not config_path.is_absolute():
            config_path = self.base_dir / config_path
        if not config_path.exists():
            return _blocked_result(config_id, config_path, started_at, "Config file does not exist.")
        config = read_config_for_safety(config_path)
        safety_error = run_safety_error(config, self.base_dir)
        if safety_error:
            return _blocked_result(config_id, config_path, started_at, safety_error)

        logger = configure_logger(self.log_dir)
        logger.info("Job run started | config=%s | config_path=%s", config_id, config_path)
        crawler = ConfigurableCrawler(config_path=config_path)
        result = await asyncio.to_thread(crawler.crawl)
        log_result(self.log_dir, result)
        logger.info(
            "Job run finished | config=%s | success=%s | items=%s | output_dir=%s",
            config_id,
            result.success,
            result.items_count,
            result.metadata.get("output_dir"),
        )
        return result

    async def _send_completion_email(self, config_id: str, trigger: str, result: dict[str, Any]) -> EmailStatus:
        try:
            return await asyncio.to_thread(send_completion_email, config_id=config_id, trigger=trigger, result=result)
        except Exception as exc:
            return EmailStatus(sent=False, reason=f"email_error:{exc}")


def _active_config_ids() -> set[str]:
    return {config.path.stem for config in list_configs()}


def _blocked_result(config_id: str, config_path: Path, started_at: datetime, safety_error: str) -> CrawlResult:
    return CrawlResult(
        crawler_name="configurable",
        success=False,
        started_at=started_at,
        finished_at=utc_now(),
        items_count=0,
        message="Run blocked by safety guard.",
        data=[],
        metadata={
            "config_name": config_id,
            "config_path": str(config_path),
            "diagnostics": {"safety_error": safety_error},
        },
        error=safety_error,
    )


def _exception_result(config_id: str, started_at: datetime, exc: Exception) -> CrawlResult:
    return CrawlResult(
        crawler_name="configurable",
        success=False,
        started_at=started_at,
        finished_at=utc_now(),
        items_count=0,
        message="Job execution failed.",
        data=[],
        metadata={"config_name": config_id},
        error=f"{type(exc).__name__}: {exc}",
    )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
