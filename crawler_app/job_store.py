from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
import json

from crawler_app.config_store import ConfigSummary


DEFAULT_INTERVAL_MINUTES = 60
MIN_INTERVAL_MINUTES = 5


@dataclass(slots=True)
class JobView:
    config_id: str
    config: ConfigSummary
    enabled: bool
    interval_minutes: int
    running: bool
    last_status: str
    last_run_at: str
    last_finished_at: str
    last_message: str
    last_error: str
    last_items_count: int
    next_run_at: str


class JobStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            parsed = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        jobs = parsed.get("jobs") if isinstance(parsed, dict) else None
        if not isinstance(jobs, dict):
            return {}
        return {
            str(config_id): dict(value)
            for config_id, value in jobs.items()
            if isinstance(value, dict)
        }

    def save(self, jobs: dict[str, dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"jobs": jobs, "updated_at": _iso_now()}
        temp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp_path.replace(self.path)

    def append_history(self, payload: dict[str, Any]) -> None:
        history_path = self.path.with_suffix(".jsonl")
        history_path.parent.mkdir(parents=True, exist_ok=True)
        record = dict(payload)
        record["recorded_at"] = _iso_now()
        with history_path.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(record, ensure_ascii=False) + "\n")

    def list_jobs(self, configs: Iterable[ConfigSummary]) -> list[JobView]:
        stored = self.load()
        views: list[JobView] = []
        for config in configs:
            config_id = config.path.stem
            job = self._normalized_job(stored.get(config_id, {}))
            views.append(
                JobView(
                    config_id=config_id,
                    config=config,
                    enabled=bool(job["enabled"]),
                    interval_minutes=int(job["interval_minutes"]),
                    running=bool(job["running"]),
                    last_status=str(job["last_status"]),
                    last_run_at=str(job["last_run_at"]),
                    last_finished_at=str(job["last_finished_at"]),
                    last_message=str(job["last_message"]),
                    last_error=str(job["last_error"]),
                    last_items_count=int(job["last_items_count"]),
                    next_run_at=str(job["next_run_at"]),
                )
            )
        return views

    def update_settings(self, config_ids: Iterable[str], enabled_ids: set[str], intervals: dict[str, int]) -> None:
        stored = self.load()
        now = utc_now()
        active_ids = {str(config_id) for config_id in config_ids}
        stored = {config_id: value for config_id, value in stored.items() if config_id in active_ids}
        for config_id in active_ids:
            job = self._normalized_job(stored.get(config_id, {}))
            was_enabled = bool(job["enabled"])
            old_interval = int(job["interval_minutes"])
            enabled = config_id in enabled_ids
            interval = max(MIN_INTERVAL_MINUTES, int(intervals.get(config_id, DEFAULT_INTERVAL_MINUTES)))
            job["enabled"] = enabled
            job["interval_minutes"] = interval
            job["updated_at"] = now.isoformat()
            if enabled and (not was_enabled or old_interval != interval or not job.get("next_run_at")):
                job["next_run_at"] = (now + timedelta(minutes=interval)).isoformat()
            if not enabled:
                job["next_run_at"] = ""
            stored[config_id] = job
        self.save(stored)

    def remove(self, config_id: str) -> None:
        stored = self.load()
        if config_id in stored:
            del stored[config_id]
            self.save(stored)

    def recover_interrupted_runs(self, active_config_ids: Iterable[str] | None = None) -> None:
        active_ids = {str(config_id) for config_id in active_config_ids} if active_config_ids is not None else None
        stored = self.load()
        now = utc_now()
        changed = False
        for config_id, raw_job in list(stored.items()):
            if active_ids is not None and config_id not in active_ids:
                del stored[config_id]
                changed = True
                continue
            job = self._normalized_job(raw_job)
            if not job["running"]:
                continue
            job["running"] = False
            job["last_status"] = "failed"
            job["last_finished_at"] = now.isoformat()
            job["last_message"] = "Recovered interrupted run after app restart."
            job["last_error"] = "interrupted_run_recovered"
            job["next_run_at"] = (now + timedelta(minutes=int(job["interval_minutes"]))).isoformat() if job["enabled"] else ""
            job["updated_at"] = now.isoformat()
            stored[config_id] = job
            changed = True
        if changed:
            self.save(stored)

    def due_config_ids(self, now: datetime | None = None, active_config_ids: Iterable[str] | None = None) -> list[str]:
        current = now or utc_now()
        active_ids = {str(config_id) for config_id in active_config_ids} if active_config_ids is not None else None
        due: list[str] = []
        stored = self.load()
        changed = False
        for config_id, raw_job in list(stored.items()):
            if active_ids is not None and config_id not in active_ids:
                del stored[config_id]
                changed = True
                continue
            job = self._normalized_job(raw_job)
            if not job["enabled"] or job["running"]:
                continue
            next_run_at = parse_iso(job["next_run_at"])
            if next_run_at is None:
                job["next_run_at"] = (current + timedelta(minutes=int(job["interval_minutes"]))).isoformat()
                stored[config_id] = job
                changed = True
                continue
            if next_run_at <= current:
                due.append(config_id)
        if changed:
            self.save(stored)
        return due

    def mark_started(self, config_id: str, started_at: datetime | None = None) -> None:
        stored = self.load()
        job = self._normalized_job(stored.get(config_id, {}))
        now = started_at or utc_now()
        job["running"] = True
        job["last_status"] = "running"
        job["last_run_at"] = now.isoformat()
        job["last_message"] = "Running"
        job["last_error"] = ""
        job["next_run_at"] = ""
        job["updated_at"] = now.isoformat()
        stored[config_id] = job
        self.save(stored)

    def mark_finished(self, config_id: str, result: dict[str, Any], finished_at: datetime | None = None) -> None:
        stored = self.load()
        job = self._normalized_job(stored.get(config_id, {}))
        now = finished_at or utc_now()
        interval = int(job["interval_minutes"])
        job["running"] = False
        job["last_status"] = "success" if result.get("success") else "failed"
        job["last_finished_at"] = now.isoformat()
        job["last_message"] = str(result.get("message") or "")
        job["last_error"] = str(result.get("error") or "")
        job["last_items_count"] = int(result.get("items_count") or 0)
        job["next_run_at"] = (now + timedelta(minutes=interval)).isoformat() if job["enabled"] else ""
        job["updated_at"] = now.isoformat()
        stored[config_id] = job
        self.save(stored)

    def _normalized_job(self, job: dict[str, Any]) -> dict[str, Any]:
        interval = _safe_int(job.get("interval_minutes"), DEFAULT_INTERVAL_MINUTES)
        return {
            "enabled": bool(job.get("enabled", False)),
            "interval_minutes": max(MIN_INTERVAL_MINUTES, interval),
            "running": bool(job.get("running", False)),
            "last_status": str(job.get("last_status") or "never"),
            "last_run_at": str(job.get("last_run_at") or ""),
            "last_finished_at": str(job.get("last_finished_at") or ""),
            "last_message": str(job.get("last_message") or ""),
            "last_error": str(job.get("last_error") or ""),
            "last_items_count": _safe_int(job.get("last_items_count"), 0),
            "next_run_at": str(job.get("next_run_at") or ""),
            "updated_at": str(job.get("updated_at") or ""),
        }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _iso_now() -> str:
    return utc_now().isoformat()


def _safe_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback
