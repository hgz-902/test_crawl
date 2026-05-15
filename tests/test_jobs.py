from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
import logging

from fastapi.testclient import TestClient

from crawler_app.base import CrawlResult, utc_now
from crawler_app.config_store import ConfigSummary
from crawler_app.emailer import send_completion_email, smtp_is_configured
from crawler_app.emailer import EmailStatus
from crawler_app.job_store import JobStore, MIN_INTERVAL_MINUTES
from crawler_app.scheduler import BackgroundJobScheduler
from crawler_app import web


class FakeCrawler:
    def __init__(self, config_path: str | Path | None = None) -> None:
        self.config_path = Path(config_path) if config_path else None

    def crawl(self) -> CrawlResult:
        started_at = utc_now()
        return CrawlResult(
            crawler_name="configurable",
            success=True,
            started_at=started_at,
            finished_at=utc_now(),
            items_count=2,
            message="ok",
            data=[{"item_index": 0}, {"item_index": 1}],
            metadata={"output_dir": "outputs/sample"},
        )


class RaisingCrawler:
    def __init__(self, config_path: str | Path | None = None) -> None:
        self.config_path = Path(config_path) if config_path else None

    def crawl(self) -> CrawlResult:
        raise RuntimeError("boom")


def fake_config_summary() -> ConfigSummary:
    return ConfigSummary(
        name="sample",
        path=Path("configs/sample.json"),
        start_url="https://example.com/list",
        output_dir="outputs/sample",
        search_terms=["SK"],
        filter_terms=[],
        notes="",
        created_at="2026-05-15T09:00:00+09:00",
    )


class JobStoreTests(unittest.TestCase):
    def test_update_settings_clamps_interval_and_lists_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = JobStore(Path(tmp_dir) / "crawler_jobs.json")

            store.update_settings(["sample"], {"sample"}, {"sample": 0})
            jobs = store.list_jobs([fake_config_summary()])

            self.assertEqual(len(jobs), 1)
            self.assertTrue(jobs[0].enabled)
            self.assertEqual(jobs[0].interval_minutes, MIN_INTERVAL_MINUTES)
            self.assertNotEqual(jobs[0].next_run_at, "")

    def test_append_history_writes_jsonl_without_secret_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = JobStore(Path(tmp_dir) / "crawler_jobs.json")

            store.append_history({"config_id": "sample", "metadata": {"completion_email": {"sent": False}}})

            history_path = Path(tmp_dir) / "crawler_jobs.jsonl"
            record = json.loads(history_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(record["config_id"], "sample")
            self.assertNotIn("SMTP_PASSWORD", json.dumps(record))

    def test_recover_interrupted_runs_marks_running_job_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = JobStore(Path(tmp_dir) / "crawler_jobs.json")
            store.update_settings(["sample"], {"sample"}, {"sample": 5})
            store.mark_started("sample")

            store.recover_interrupted_runs(["sample"])
            jobs = store.list_jobs([fake_config_summary()])

            self.assertFalse(jobs[0].running)
            self.assertEqual(jobs[0].last_status, "failed")
            self.assertEqual(jobs[0].last_error, "interrupted_run_recovered")
            self.assertNotEqual(jobs[0].next_run_at, "")

    def test_due_config_ids_prunes_deleted_configs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = JobStore(Path(tmp_dir) / "crawler_jobs.json")
            store.update_settings(["sample"], {"sample"}, {"sample": 5})

            due = store.due_config_ids(active_config_ids=[])

            self.assertEqual(due, [])
            self.assertEqual(store.load(), {})

    def test_enabled_interval_change_reschedules_next_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = JobStore(Path(tmp_dir) / "crawler_jobs.json")
            store.update_settings(["sample"], {"sample"}, {"sample": 60})
            first_next_run = store.list_jobs([fake_config_summary()])[0].next_run_at

            store.update_settings(["sample"], {"sample"}, {"sample": 5})
            updated_job = store.list_jobs([fake_config_summary()])[0]

            self.assertEqual(updated_job.interval_minutes, 5)
            self.assertNotEqual(updated_job.next_run_at, first_next_run)


class EmailerTests(unittest.TestCase):
    def test_email_is_disabled_until_explicitly_enabled(self) -> None:
        env = {"SMTP_HOST": "smtp.example.com", "SMTP_PORT": "587", "SMTP_FROM": "crawler@example.com"}

        self.assertFalse(smtp_is_configured(env))
        status = send_completion_email(config_id="sample", trigger="manual", result={"success": True}, env=env)
        self.assertFalse(status.sent)
        self.assertEqual(status.reason, "email_disabled")


class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_job_uses_configurable_crawler_and_records_email_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            config_dir = base_dir / "configs"
            config_dir.mkdir()
            (config_dir / "sample.json").write_text(
                json.dumps(
                    {
                        "name": "sample",
                        "start_url": "https://example.com",
                        "output_dir": str(base_dir / "outputs" / "sample"),
                        "steps": [{"name": "open", "xpath": "//a[1]", "action": "click"}],
                    }
                ),
                encoding="utf-8",
            )
            store = JobStore(base_dir / "crawler_jobs.json")
            scheduler = BackgroundJobScheduler(store=store, base_dir=base_dir, log_dir=base_dir / "logs")

            with patch("crawler_app.scheduler.ConfigurableCrawler", FakeCrawler), patch(
                "crawler_app.scheduler.send_completion_email", return_value=EmailStatus(sent=False, reason="email_disabled")
            ), patch("crawler_app.scheduler.configure_logger", return_value=logging.getLogger("test_jobs")), patch(
                "crawler_app.scheduler.log_result"
            ):
                result = await scheduler.run_job("sample", trigger="manual")

            self.assertTrue(result["success"])
            self.assertEqual(result["items_count"], 2)
            self.assertEqual(result["metadata"]["completion_email"]["reason"], "email_disabled")
            self.assertTrue((base_dir / "crawler_jobs.jsonl").exists())

    async def test_missing_config_is_blocked_without_crawler_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            store = JobStore(base_dir / "crawler_jobs.json")
            scheduler = BackgroundJobScheduler(store=store, base_dir=base_dir, log_dir=base_dir / "logs")

            with patch("crawler_app.scheduler.ConfigurableCrawler", FakeCrawler):
                result = await scheduler.run_job("missing", trigger="manual")

            self.assertFalse(result["success"])
            self.assertEqual(result["error"], "Config file does not exist.")

    async def test_unexpected_crawler_exception_marks_job_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            config_dir = base_dir / "configs"
            config_dir.mkdir()
            (config_dir / "sample.json").write_text(
                json.dumps(
                    {
                        "name": "sample",
                        "start_url": "https://example.com",
                        "output_dir": str(base_dir / "outputs" / "sample"),
                        "steps": [{"name": "open", "xpath": "//a[1]", "action": "click"}],
                    }
                ),
                encoding="utf-8",
            )
            store = JobStore(base_dir / "crawler_jobs.json")
            scheduler = BackgroundJobScheduler(store=store, base_dir=base_dir, log_dir=base_dir / "logs")

            with patch("crawler_app.scheduler.ConfigurableCrawler", RaisingCrawler), patch(
                "crawler_app.scheduler.send_completion_email", return_value=EmailStatus(sent=False, reason="email_disabled")
            ), patch("crawler_app.scheduler.configure_logger", return_value=logging.getLogger("test_jobs")), patch(
                "crawler_app.scheduler.log_result"
            ):
                result = await scheduler.run_job("sample", trigger="manual")

            jobs = store.list_jobs([fake_config_summary()])
            self.assertFalse(result["success"])
            self.assertIn("RuntimeError: boom", result["error"])
            self.assertFalse(jobs[0].running)
            self.assertEqual(jobs[0].last_status, "failed")
            self.assertTrue((base_dir / "crawler_jobs.jsonl").exists())


class JobsPageTests(unittest.TestCase):
    def test_jobs_page_renders_config_controls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = JobStore(Path(tmp_dir) / "crawler_jobs.json")
            with patch.object(web, "job_store", store), patch.object(web, "list_configs", return_value=[fake_config_summary()]), patch.object(
                web, "smtp_is_configured", return_value=False
            ):
                with TestClient(web.app) as client:
                    response = client.get("/jobs")

        self.assertEqual(response.status_code, 200)
        self.assertIn("배치 JOB 오케스트레이터", response.text)
        self.assertIn("sample", response.text)
        self.assertIn("interval_sample", response.text)
        self.assertIn("완료 이메일 비활성화", response.text)

    def test_run_now_route_delegates_to_scheduler(self) -> None:
        class FakeScheduler:
            def __init__(self) -> None:
                self.run_job = AsyncMock(return_value={"success": True})

            def start(self) -> None:
                return None

            async def stop(self) -> None:
                return None

        fake_scheduler = FakeScheduler()

        with patch.object(web, "job_scheduler", fake_scheduler), patch.object(web, "list_configs", return_value=[fake_config_summary()]):
            with TestClient(web.app) as client:
                response = client.post("/jobs/sample/run", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("/jobs?ran=sample", response.headers["location"])
        fake_scheduler.run_job.assert_awaited_once_with("sample", trigger="manual")

    def test_run_now_route_rejects_unknown_config(self) -> None:
        fake_scheduler = type("FakeScheduler", (), {"start": lambda self: None, "stop": AsyncMock(), "run_job": AsyncMock()})()

        with patch.object(web, "job_scheduler", fake_scheduler), patch.object(web, "list_configs", return_value=[]):
            with TestClient(web.app) as client:
                response = client.post("/jobs/missing/run", follow_redirects=False)

        self.assertEqual(response.status_code, 404)
        fake_scheduler.run_job.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
