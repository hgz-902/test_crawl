from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from crawler_app.base import CrawlResult, utc_now
from crawler_app.config_store import ConfigSummary, list_configs, save_config, get_config
from crawler_app import config_store
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
            items_count=1,
            message="ok",
            data=[{"item_index": 0}],
            metadata={"output_dir": "outputs/test-site"},
        )


class WebLoggingTests(unittest.TestCase):
    def test_default_config_includes_notes_field(self) -> None:
        config = web.default_config()

        self.assertIn("notes", config)
        self.assertEqual(config["notes"], "")
        self.assertIn("filter_terms", config)
        self.assertEqual(config["filter_terms"], [])

    def test_list_configs_includes_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_dir = Path(tmp_dir)
            config_path = config_dir / "sample.json"
            config_path.write_text(
                """
{
  "name": "sample",
  "start_url": "https://example.com",
  "output_dir": "outputs/sample",
  "search_terms": ["SK", "유가"],
  "filter_terms": ["정유"],
  "notes": "특이사항 예시",
  "steps": [
    {"name": "open", "xpath": "//a[1]", "action": "click"}
  ]
}
""".strip(),
                encoding="utf-8",
            )

            configs = list_configs(config_dir)

            self.assertEqual(len(configs), 1)
            self.assertEqual(configs[0].notes, "특이사항 예시")
            self.assertEqual(configs[0].search_terms, ["SK", "유가"])
            self.assertEqual(configs[0].filter_terms, ["정유"])

    def test_list_configs_sorts_by_created_at_desc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_dir = Path(tmp_dir)
            (config_dir / "b.json").write_text(
                """
{
  "name": "b",
  "start_url": "https://example.com/b",
  "output_dir": "outputs/b",
  "created_at": "2026-04-27T09:10:00+09:00",
  "steps": [
    {"name": "open", "xpath": "//a[1]", "action": "click"}
  ]
}
""".strip(),
                encoding="utf-8",
            )
            (config_dir / "a.json").write_text(
                """
{
  "name": "a",
  "start_url": "https://example.com/a",
  "output_dir": "outputs/a",
  "created_at": "2026-04-27T09:00:00+09:00",
  "steps": [
    {"name": "open", "xpath": "//a[1]", "action": "click"}
  ]
}
""".strip(),
                encoding="utf-8",
            )

            configs = list_configs(config_dir)

            self.assertEqual([config.name for config in configs], ["b", "a"])

    def test_save_config_adds_created_and_updated_at(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_dir = Path(tmp_dir)
            config = {
                "name": "sample",
                "start_url": "https://example.com",
                "output_dir": "outputs/sample",
                "steps": [
                    {"name": "open", "xpath": "//a[1]", "action": "click"},
                ],
            }

            with patch.object(config_store, "_timestamp_now", side_effect=["2026-04-27T10:00:00+09:00"]):
                path = save_config(config, config_dir)

            saved = get_config("sample", config_dir)
            self.assertEqual(path, config_dir / "sample.json")
            self.assertEqual(saved["created_at"], "2026-04-27T10:00:00+09:00")
            self.assertEqual(saved["updated_at"], "2026-04-27T10:00:00+09:00")

            updated_config = dict(saved)
            updated_config["notes"] = "수정됨"
            with patch.object(
                config_store,
                "_timestamp_now",
                side_effect=["2026-04-27T10:05:00+09:00"],
            ):
                save_config(updated_config, config_dir)

            resaved = get_config("sample", config_dir)
            self.assertEqual(resaved["created_at"], "2026-04-27T10:00:00+09:00")
            self.assertEqual(resaved["updated_at"], "2026-04-27T10:05:00+09:00")
            self.assertEqual(resaved["notes"], "수정됨")

    def test_index_page_shows_note_icon_and_popup(self) -> None:
        fake_configs = [
            ConfigSummary(
                name="sample",
                path=Path("configs/sample.json"),
                start_url="https://example.com",
                output_dir="outputs/sample",
                search_terms=["SK", "유가"],
                filter_terms=["정유"],
                notes="특이사항 예시",
                created_at="2026-04-27T09:00:00+09:00",
            )
        ]

        with TestClient(web.app) as client, patch.object(web, "list_configs", return_value=fake_configs):
            response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("📝", response.text)
        self.assertIn("🔎", response.text)
        self.assertIn("⛶", response.text)
        self.assertIn("특이사항 예시", response.text)
        self.assertIn("note-popover", response.text)

    def test_web_run_writes_orchestrator_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            log_dir = tmp_path / "logs"
            config_path = tmp_path / "config.json"
            config_path.write_text("{}", encoding="utf-8")

            logger = logging.getLogger("crawler_orchestrator")
            original_handlers = list(logger.handlers)
            for handler in original_handlers:
                logger.removeHandler(handler)

            try:
                logger = web.configure_logger(log_dir)
                with patch.object(web, "LOG_DIR", log_dir), patch.object(web, "ConfigurableCrawler", FakeCrawler), patch.object(
                    web, "config_name_to_path", return_value=config_path
                ):
                    with TestClient(web.app) as client:
                        response = client.post("/configs/test/run")

                self.assertIsNotNone(response)
                orchestrator_log = log_dir / "orchestrator.log"
                crawl_results = log_dir / "crawl_results.jsonl"
                self.assertTrue(orchestrator_log.exists())
                self.assertTrue(crawl_results.exists())

                log_text = orchestrator_log.read_text(encoding="utf-8")
                self.assertIn("Web run started | config=test", log_text)
                self.assertIn("Web run finished | config=test | success=True", log_text)
            finally:
                for handler in list(logger.handlers):
                    logger.removeHandler(handler)
                    handler.close()
                for handler in original_handlers:
                    logger.addHandler(handler)

    def test_orchestration_page_renders_jobs(self) -> None:
        fake_job = type(
            "FakeJob",
            (),
            {
                "job_id": "sample",
                "config_name": "Sample",
                "config_path": "configs/sample.json",
                "output_dir": "outputs/sample",
                "search_terms": ["SK"],
                "filter_terms": [],
            },
        )()
        settings = {
            "keywords": ["SK"],
            "recipients": ["to@example.com"],
            "sender": "from@example.com",
            "jobs": {
                "sample": {
                    "enabled": True,
                    "interval": {"value": 15, "unit": "minutes"},
                    "last_run_at": "2026-05-18T05:00:00+00:00",
                    "next_run_at": "2026-05-18T06:00:00+00:00",
                }
            },
        }

        fake_registry = [
            {
                "task_name": web.managed_task_name("sample"),
                "job_id": "sample",
                "config_name": "Sample",
                "interval": {"value": 15, "unit": "minutes"},
                "allow_email_send": False,
                "registered_at": "2026-05-18T06:49:00+00:00",
            }
        ]

        with patch.dict(os.environ, {"SMTP_HOST": "", "SMTP_PASSWORD": ""}), TestClient(web.app) as client, patch.object(
            web, "settings_for_registered_jobs", return_value=(settings, [fake_job])
        ), patch.object(web.ORCHESTRATION_STORE, "load_history", return_value=[]), patch.object(
            web, "load_scheduler_registry", return_value=fake_registry
        ):
            response = client.get("/orchestration")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Sample", response.text)
        self.assertIn("SMTP dry-run", response.text)
        self.assertIn("등록된 스케줄 / 스케줄 결과 보기", response.text)
        self.assertIn("2026-05-18 14:00:00", response.text)
        self.assertIn("2026-05-18 15:49:00", response.text)
        self.assertIn("2026-05-18 15:00:00", response.text)
        self.assertNotIn("2026-05-18T05:00:00+00:00", response.text)
        self.assertNotIn("2026-05-18T06:00:00+00:00", response.text)
        self.assertNotIn("2026-05-18T06:49:00+00:00", response.text)

    def test_orchestration_page_displays_recent_history_finished_at_in_kst(self) -> None:
        settings = {
            "keywords": ["SK"],
            "recipients": ["to@example.com"],
            "sender": "from@example.com",
            "jobs": {},
        }
        history = [
            {
                "batch_id": "batch-1",
                "status": "completed",
                "total": 1,
                "succeeded": 1,
                "duplicate_stopped": 0,
                "skipped_not_due": 0,
                "failed": 0,
                "finished_at": "2026-05-18T06:49:00+00:00",
            }
        ]

        with TestClient(web.app) as client, patch.object(
            web, "settings_for_registered_jobs", return_value=(settings, [])
        ), patch.object(web.ORCHESTRATION_STORE, "load_history", return_value=history), patch.object(
            web, "load_scheduler_registry", return_value=[]
        ):
            response = client.get("/orchestration")

        self.assertEqual(response.status_code, 200)
        self.assertIn("2026-05-18 15:49:00", response.text)
        self.assertNotIn("2026-05-18T06:49:00+00:00", response.text)

    def test_orchestration_page_does_not_fake_scheduler_rows_from_enabled_settings(self) -> None:
        fake_job = type(
            "FakeJob",
            (),
            {
                "job_id": "sample",
                "config_name": "Sample",
                "config_path": "configs/sample.json",
                "output_dir": "outputs/sample",
                "search_terms": ["SK"],
                "filter_terms": [],
            },
        )()
        settings = {
            "keywords": ["SK"],
            "recipients": ["to@example.com"],
            "sender": "from@example.com",
            "jobs": {"sample": {"enabled": True, "interval": {"value": 15, "unit": "minutes"}}},
        }

        with patch.dict(os.environ, {"SMTP_HOST": "", "SMTP_PASSWORD": ""}), TestClient(web.app) as client, patch.object(
            web, "settings_for_registered_jobs", return_value=(settings, [fake_job])
        ), patch.object(web.ORCHESTRATION_STORE, "load_history", return_value=[]), patch.object(
            web, "load_scheduler_registry", return_value=[]
        ), patch.object(
            web, "list_managed_task_details", return_value=[]
        ):
            response = client.get("/orchestration")

        self.assertEqual(response.status_code, 200)
        self.assertIn("현재 등록된 오케스트레이션 스케줄러가 없습니다", response.text)
        self.assertNotIn(web.managed_task_name("sample"), response.text)

    def test_orchestration_templates_do_not_contain_known_mojibake_markers(self) -> None:
        markers = ("?ㅼ", "理", "諛", "湲", "以묐", "醫", "遺?")
        for template_name in ("layout.html", "orchestration.html"):
            template_text = (web.TEMPLATE_DIR / template_name).read_text(encoding="utf-8")
            for marker in markers:
                self.assertNotIn(marker, template_text, f"{template_name} contains mojibake marker {marker!r}")

    def test_orchestration_template_posts_actions_to_same_page(self) -> None:
        layout_text = (web.TEMPLATE_DIR / "layout.html").read_text(encoding="utf-8")
        template_text = (web.TEMPLATE_DIR / "orchestration.html").read_text(encoding="utf-8")

        self.assertIn("app.js') }}?v=20260519-tabs", layout_text)
        self.assertIn('action="/orchestration"', template_text)
        self.assertIn('role="tablist"', template_text)
        self.assertIn('role="tab"', template_text)
        self.assertIn('role="tabpanel"', template_text)
        self.assertIn('data-tab-target="config-list"', template_text)
        self.assertIn('data-tab-target="schedule-results"', template_text)
        self.assertIn('document.querySelectorAll("[data-tab-target]")', template_text)
        self.assertIn('name="action" value="save"', template_text)
        self.assertIn('name="action" value="run"', template_text)
        self.assertIn('name="action" value="sync"', template_text)
        self.assertIn('name="action" value="stop_monitoring"', template_text)
        self.assertIn('name="action" value="delete_scheduler"', template_text)
        self.assertNotIn('name="force_due"', template_text)
        self.assertNotIn('formaction="/orchestration/save"', template_text)
        self.assertNotIn('formaction="/orchestration/run"', template_text)
        self.assertNotIn('action="/orchestration/schedulers/delete"', template_text)

    def test_prompt_history_is_cumulative(self) -> None:
        prompt_index = (web.BASE_DIR / "prompt.md").read_text(encoding="utf-8")
        prompt_record = web.BASE_DIR / "prompts" / "20260519_143900_orchestration_tabs_stop_followup.md"

        self.assertTrue(prompt_record.exists())
        self.assertIn("Prompt Record Index - 2026-05-19 14:39 KST", prompt_index)
        self.assertIn("수정 요청 1. 버튼식 페이지 이동이 아니라 실제 탭 UI로 구성", prompt_record.read_text(encoding="utf-8"))

    def test_orchestration_post_redirects_to_get_page_and_flash_is_one_time(self) -> None:
        fake_job = type(
            "FakeJob",
            (),
            {
                "job_id": "sample",
                "config_name": "Sample",
                "config_path": "configs/sample.json",
                "output_dir": "outputs/sample",
                "search_terms": [],
                "filter_terms": [],
            },
        )()
        settings = {
            "keywords": ["SK"],
            "recipients": ["to@example.com"],
            "sender": "from@example.com",
            "allow_email_send": False,
            "jobs": {"sample": {"enabled": False, "cron": "0 * * * *", "interval": {"value": 1, "unit": "hours"}}},
        }

        with TestClient(web.app) as client, patch.object(
            web, "settings_for_registered_jobs", return_value=(settings, [fake_job])
        ), patch.object(web.ORCHESTRATION_STORE, "save_settings", side_effect=lambda payload: payload), patch.object(
            web.ORCHESTRATION_STORE, "save_job_state", return_value={}
        ), patch.object(web.ORCHESTRATION_STORE, "load_history", return_value=[]), patch.object(
            web, "sync_windows_scheduled_tasks", return_value=type("SyncResult", (), {"status": "skipped", "skipped_reason": "test", "created": [], "deleted": []})()
        ), patch.object(web, "load_scheduler_registry", return_value=[]):
            response = client.post(
                "/orchestration",
                data={
                    "action": "save",
                    "enabled_jobs": "sample",
                    "cron__sample": "*/10 * * * *",
                    "keywords": "SK",
                    "recipients": "to@example.com",
                    "sender": "from@example.com",
                },
                follow_redirects=False,
            )
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers["location"], "/orchestration")

            get_response = client.get("/orchestration")
            self.assertEqual(get_response.status_code, 200)
            self.assertIn("오케스트레이션 설정을 저장했습니다", get_response.text)

            refresh_response = client.get("/orchestration")
            self.assertEqual(refresh_response.status_code, 200)
            self.assertNotIn("오케스트레이션 설정을 저장했습니다", refresh_response.text)

    def test_orchestration_save_persists_form_settings(self) -> None:
        fake_job = type(
            "FakeJob",
            (),
            {
                "job_id": "sample",
                "config_name": "Sample",
                "config_path": "configs/sample.json",
                "output_dir": "outputs/sample",
                "search_terms": [],
                "filter_terms": [],
            },
        )()
        settings = {
            "keywords": ["SK"],
            "recipients": ["to@example.com"],
            "sender": "from@example.com",
            "allow_email_send": False,
            "jobs": {"sample": {"enabled": False, "interval": {"value": 1, "unit": "hours"}}},
        }
        saved_payloads: list[dict[str, object]] = []

        def fake_save(payload: dict[str, object]) -> dict[str, object]:
            saved_payloads.append(payload)
            return payload

        with TestClient(web.app) as client, patch.object(
            web, "settings_for_registered_jobs", return_value=(settings, [fake_job])
        ), patch.object(web.ORCHESTRATION_STORE, "save_settings", side_effect=fake_save), patch.object(
            web, "sync_windows_scheduled_tasks", return_value=type("SyncResult", (), {"status": "skipped", "skipped_reason": "test", "created": [], "deleted": []})()
        ), patch.object(
            web.ORCHESTRATION_STORE, "load_history", return_value=[]
        ):
            response = client.post(
                "/orchestration/save",
                data={
                    "enabled_jobs": "sample",
                    "cron__sample": "*/30 * * * *",
                    "keywords": "SK\ncarbon",
                    "recipients": "to@example.com",
                    "sender": "from@example.com",
                    "allow_email_send": "1",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(saved_payloads[0]["keywords"], ["SK", "carbon"])
        self.assertTrue(saved_payloads[0]["allow_email_send"])
        self.assertTrue(saved_payloads[0]["jobs"]["sample"]["enabled"])
        self.assertEqual(saved_payloads[0]["jobs"]["sample"]["cron"], "*/30 * * * *")

    def test_orchestration_save_writes_real_store(self) -> None:
        fake_job = type(
            "FakeJob",
            (),
            {
                "job_id": "sample",
                "config_name": "Sample",
                "config_path": "configs/sample.json",
                "output_dir": "outputs/sample",
                "search_terms": [],
                "filter_terms": [],
            },
        )()

        with tempfile.TemporaryDirectory() as tmp_dir:
            store = web.OrchestrationStateStore(
                settings_path=Path(tmp_dir) / "settings.json",
                history_path=Path(tmp_dir) / "history.json",
            )
            settings = store.load_settings()
            with TestClient(web.app) as client, patch.object(web, "ORCHESTRATION_STORE", store), patch.object(
                web, "settings_for_registered_jobs", return_value=(settings, [fake_job])
            ), patch.object(
                web, "sync_windows_scheduled_tasks", return_value=type("SyncResult", (), {"status": "skipped", "skipped_reason": "test", "created": [], "deleted": []})()
            ):
                response = client.post(
                    "/orchestration/save",
                    data={
                        "enabled_jobs": "sample",
                        "cron__sample": "*/7 * * * *",
                        "keywords": "SK\ncarbon",
                        "recipients": "to@example.com",
                        "sender": "from@example.com",
                    },
                )

            reloaded = store.load_settings()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(reloaded["keywords"], ["SK", "carbon"])
            self.assertTrue(reloaded["jobs"]["sample"]["enabled"])
            self.assertEqual(reloaded["jobs"]["sample"]["cron"], "*/7 * * * *")

    def test_orchestration_save_rejects_invalid_cron_without_saving(self) -> None:
        fake_job = type(
            "FakeJob",
            (),
            {
                "job_id": "sample",
                "config_name": "Sample",
                "config_path": "configs/sample.json",
                "output_dir": "outputs/sample",
                "search_terms": [],
                "filter_terms": [],
            },
        )()
        settings = {
            "keywords": ["SK"],
            "recipients": ["to@example.com"],
            "sender": "from@example.com",
            "allow_email_send": False,
            "jobs": {"sample": {"enabled": False, "cron": "0 * * * *", "interval": {"value": 1, "unit": "hours"}}},
        }

        with TestClient(web.app) as client, patch.object(
            web, "settings_for_registered_jobs", return_value=(settings, [fake_job])
        ), patch.object(web.ORCHESTRATION_STORE, "save_settings") as save_settings, patch.object(
            web.ORCHESTRATION_STORE, "load_history", return_value=[]
        ):
            response = client.post(
                "/orchestration/save",
                data={
                    "enabled_jobs": "sample",
                    "cron__sample": "not cron",
                    "keywords": "SK",
                    "recipients": "to@example.com",
                    "sender": "from@example.com",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Cron 설정 오류", response.text)
        save_settings.assert_not_called()

    def test_orchestration_save_clears_stale_next_run_when_cron_changes(self) -> None:
        fake_job = type(
            "FakeJob",
            (),
            {
                "job_id": "sample",
                "config_name": "Sample",
                "config_path": "configs/sample.json",
                "output_dir": "outputs/sample",
                "search_terms": [],
                "filter_terms": [],
            },
        )()
        settings = {
            "keywords": ["SK"],
            "recipients": ["to@example.com"],
            "sender": "from@example.com",
            "allow_email_send": False,
            "jobs": {
                "sample": {
                    "enabled": True,
                    "cron": "0 * * * *",
                    "interval": {"value": 1, "unit": "hours"},
                    "next_run_at": "2026-05-18T10:00:00+00:00",
                }
            },
        }
        saved_payloads: list[dict[str, object]] = []

        def fake_save(payload: dict[str, object]) -> dict[str, object]:
            saved_payloads.append(payload)
            return payload

        with TestClient(web.app) as client, patch.object(
            web, "settings_for_registered_jobs", return_value=(settings, [fake_job])
        ), patch.object(web.ORCHESTRATION_STORE, "save_settings", side_effect=fake_save), patch.object(
            web, "sync_windows_scheduled_tasks", return_value=type("SyncResult", (), {"status": "skipped", "skipped_reason": "test", "created": [], "deleted": []})()
        ), patch.object(
            web.ORCHESTRATION_STORE, "load_history", return_value=[]
        ):
            response = client.post(
                "/orchestration/save",
                data={
                    "enabled_jobs": "sample",
                    "cron__sample": "*/15 * * * *",
                    "keywords": "SK",
                    "recipients": "to@example.com",
                    "sender": "from@example.com",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(saved_payloads[0]["jobs"]["sample"]["next_run_at"], "2026-05-18T10:00:00+00:00")
        self.assertEqual(saved_payloads[0]["jobs"]["sample"]["next_run_at"], "")

    def test_orchestration_save_does_not_sync_scheduler_or_run_batch(self) -> None:
        fake_job = type(
            "FakeJob",
            (),
            {
                "job_id": "sample",
                "config_name": "Sample",
                "config_path": "configs/sample.json",
                "output_dir": "outputs/sample",
                "search_terms": [],
                "filter_terms": [],
            },
        )()
        settings = {
            "keywords": ["SK"],
            "recipients": ["to@example.com"],
            "sender": "from@example.com",
            "allow_email_send": False,
            "jobs": {"sample": {"enabled": False, "interval": {"value": 1, "unit": "hours"}}},
        }

        with TestClient(web.app) as client, patch.object(
            web,
            "settings_for_registered_jobs",
            return_value=(settings, [fake_job]),
        ), patch.object(web.ORCHESTRATION_STORE, "save_settings", side_effect=lambda payload: payload), patch.object(
            web, "sync_windows_scheduled_tasks"
        ) as sync_tasks, patch.object(web, "run_batch") as run_batch_mock, patch.object(
            web.ORCHESTRATION_STORE, "load_history", return_value=[]
        ):
            response = client.post(
                "/orchestration/save",
                data={
                    "enabled_jobs": "sample",
                    "cron__sample": "*/10 * * * *",
                    "keywords": "SK",
                    "recipients": "to@example.com",
                    "sender": "from@example.com",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("스케줄러와 크롤링 실행은 변경하지 않았습니다", response.text)
        sync_tasks.assert_not_called()
        run_batch_mock.assert_not_called()

    def test_orchestration_save_ignores_scheduler_sync_failure_because_save_only_writes_settings(self) -> None:
        fake_job = type(
            "FakeJob",
            (),
            {
                "job_id": "sample",
                "config_name": "Sample",
                "config_path": "configs/sample.json",
                "output_dir": "outputs/sample",
                "search_terms": [],
                "filter_terms": [],
            },
        )()
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = web.OrchestrationStateStore(
                settings_path=Path(tmp_dir) / "settings.json",
                history_path=Path(tmp_dir) / "history.json",
            )
            settings = store.load_settings()
            with TestClient(web.app) as client, patch.object(web, "ORCHESTRATION_STORE", store), patch.object(
                web, "settings_for_registered_jobs", return_value=(settings, [fake_job])
            ), patch.object(
                web,
                "sync_windows_scheduled_tasks",
                side_effect=RuntimeError("scheduler denied"),
            ):
                response = client.post(
                    "/orchestration/save",
                    data={
                        "enabled_jobs": "sample",
                        "cron__sample": "*/15 * * * *",
                        "keywords": "SK",
                        "recipients": "to@example.com",
                        "sender": "from@example.com",
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertIn("스케줄러와 크롤링 실행은 변경하지 않았습니다", response.text)

    def test_orchestration_monitoring_start_syncs_scheduler(self) -> None:
        fake_job = type(
            "FakeJob",
            (),
            {
                "job_id": "sample",
                "config_name": "Sample",
                "config_path": "configs/sample.json",
                "output_dir": "outputs/sample",
                "search_terms": [],
                "filter_terms": [],
            },
        )()
        settings = {
            "keywords": ["SK"],
            "recipients": ["to@example.com"],
            "sender": "from@example.com",
            "allow_email_send": True,
            "jobs": {"sample": {"enabled": False, "cron": "0 * * * *", "interval": {"value": 1, "unit": "hours"}}},
        }

        with TestClient(web.app) as client, patch.object(
            web, "settings_for_registered_jobs", return_value=(settings, [fake_job])
        ), patch.object(web.ORCHESTRATION_STORE, "save_settings", side_effect=lambda payload: payload), patch.object(
            web.ORCHESTRATION_STORE, "load_history", return_value=[]
        ), patch.object(
            web,
            "sync_windows_scheduled_tasks",
            return_value=type("SyncResult", (), {"status": "synced", "created": ["task"], "deleted": [], "skipped_reason": ""})(),
        ) as sync_tasks:
            response = client.post(
                "/orchestration/schedulers/sync",
                data={
                    "enabled_jobs": "sample",
                    "cron__sample": "*/5 * * * *",
                    "keywords": "SK",
                    "recipients": "to@example.com",
                    "sender": "from@example.com",
                    "allow_email_send": "1",
                },
            )

        self.assertEqual(response.status_code, 200)
        sync_tasks.assert_called_once()
        self.assertIn("모니터링을 시작했습니다", response.text)

    def test_orchestration_monitoring_start_rejects_unsupported_cron_before_save(self) -> None:
        fake_job = type(
            "FakeJob",
            (),
            {
                "job_id": "sample",
                "config_name": "Sample",
                "config_path": "configs/sample.json",
                "output_dir": "outputs/sample",
                "search_terms": [],
                "filter_terms": [],
            },
        )()
        settings = {
            "keywords": ["SK"],
            "recipients": ["to@example.com"],
            "sender": "from@example.com",
            "allow_email_send": True,
            "jobs": {"sample": {"enabled": False, "cron": "0 * * * *", "interval": {"value": 1, "unit": "hours"}}},
        }

        with TestClient(web.app) as client, patch.object(
            web, "settings_for_registered_jobs", return_value=(settings, [fake_job])
        ), patch.object(web.ORCHESTRATION_STORE, "save_settings") as save_settings, patch.object(
            web.ORCHESTRATION_STORE, "load_history", return_value=[]
        ), patch.object(web, "sync_windows_scheduled_tasks") as sync_tasks:
            response = client.post(
                "/orchestration/schedulers/sync",
                data={
                    "enabled_jobs": "sample",
                    "cron__sample": "0 0 1 1 *",
                    "keywords": "SK",
                    "recipients": "to@example.com",
                    "sender": "from@example.com",
                    "allow_email_send": "1",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("모니터링 시작 실패", response.text)
        save_settings.assert_not_called()
        sync_tasks.assert_not_called()

    def test_orchestration_monitoring_start_rejects_cross_origin_post(self) -> None:
        with TestClient(web.app) as client:
            response = client.post(
                "/orchestration/schedulers/sync",
                headers={"Origin": "https://attacker.example"},
                data={},
            )

        self.assertEqual(response.status_code, 403)

    def test_orchestration_monitoring_stop_calls_stop_script_and_keeps_job_enabled_for_restart(self) -> None:
        fake_job = type(
            "FakeJob",
            (),
            {
                "job_id": "sample",
                "config_name": "Sample",
                "config_path": "configs/sample.json",
                "output_dir": "outputs/sample",
                "search_terms": [],
                "filter_terms": [],
            },
        )()
        settings = {
            "keywords": ["SK"],
            "recipients": ["to@example.com"],
            "sender": "from@example.com",
            "allow_email_send": False,
            "jobs": {"sample": {"enabled": True, "cron": "*/5 * * * *", "next_run_at": "2026-05-18T01:00:00+00:00"}},
        }
        saved_payloads: list[dict[str, object]] = []

        def fake_save(payload: dict[str, object]) -> dict[str, object]:
            saved_payloads.append(payload)
            return payload

        stop_result = type("StopResult", (), {"status": "stopped", "ended": ["task"], "deleted": ["task"], "skipped": [], "errors": [], "skipped_reason": ""})()
        with TestClient(web.app) as client, patch.object(
            web, "settings_for_registered_jobs", return_value=(settings, [fake_job])
        ), patch.object(web.ORCHESTRATION_STORE, "save_settings", side_effect=fake_save), patch.object(
            web.ORCHESTRATION_STORE, "save_job_state", return_value={}
        ), patch.object(web.ORCHESTRATION_STORE, "load_history", return_value=[]), patch.object(
            web, "stop_managed_tasks_with_script", return_value=stop_result
        ) as stop_tasks:
            response = client.post("/orchestration", data={"action": "stop_monitoring"})

        self.assertEqual(response.status_code, 200)
        stop_tasks.assert_called_once_with(delete_tasks=True)
        self.assertTrue(saved_payloads[0]["jobs"]["sample"]["enabled"])
        self.assertEqual(saved_payloads[0]["jobs"]["sample"]["next_run_at"], "")
        self.assertIn("모니터링을 종료했습니다", response.text)

    def test_scheduler_display_normalizes_never_run_time_and_last_result_code(self) -> None:
        fake_job = type(
            "FakeJob",
            (),
            {
                "job_id": "sample",
                "config_name": "Sample",
                "config_path": "configs/sample.json",
                "output_dir": "outputs/sample",
                "search_terms": [],
                "filter_terms": [],
            },
        )()
        settings = {
            "keywords": [],
            "recipients": [],
            "sender": "",
            "allow_email_send": False,
            "jobs": {"sample": {"enabled": True, "cron": "*/5 * * * *"}},
        }
        registry = [{"task_name": web.managed_task_name("sample"), "job_id": "sample", "config_name": "Sample", "cron": "*/5 * * * *"}]
        detail = type(
            "TaskInfo",
            (),
            {
                "task_name": web.managed_task_name("sample"),
                "next_run_time": "2026-05-19 오후 3:10:00",
                "status": "Ready",
                "last_run_time": "11/30/1999 00:00:00",
                "last_result": "267011",
                "task_to_run": "powershell.exe -File launcher.ps1",
            },
        )()

        with TestClient(web.app) as client, patch.object(web, "settings_for_registered_jobs", return_value=(settings, [fake_job])), patch.object(
            web.ORCHESTRATION_STORE, "load_history", return_value=[]
        ), patch.object(web, "load_scheduler_registry", return_value=registry), patch.object(
            web, "list_managed_task_details", return_value=[detail]
        ):
            response = client.get("/orchestration")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("11/30/1999", response.text)
        self.assertNotIn(">267011<", response.text)
        self.assertIn("2026-05-19 15:10:00", response.text)

    def test_orchestration_run_passes_force_due_and_email_permission(self) -> None:
        fake_job = type(
            "FakeJob",
            (),
            {
                "job_id": "sample",
                "config_name": "Sample",
                "config_path": "configs/sample.json",
                "output_dir": "outputs/sample",
                "search_terms": [],
                "filter_terms": [],
            },
        )()
        settings = {
            "keywords": ["SK"],
            "recipients": ["to@example.com"],
            "sender": "from@example.com",
            "allow_email_send": False,
            "jobs": {
                "sample": {
                    "enabled": False,
                    "interval": {"value": 1, "unit": "hours"},
                    "last_run_at": "2026-05-16T00:00:00+00:00",
                    "next_run_at": "2026-05-16T01:00:00+00:00",
                    "last_status": "succeeded",
                }
            },
        }
        run_calls: list[dict[str, object]] = []

        def fake_run_batch(selected, **kwargs):
            run_calls.append({"selected": list(selected), **kwargs})
            return type(
                "FakeBatch",
                (),
                {
                    "batch_id": "b1",
                    "status": "completed",
                    "total": 1,
                    "succeeded": 1,
                    "failed": 0,
                    "duplicate_stopped": 0,
                    "skipped_not_due": 0,
                    "results": [],
                    "started_at": "2026-05-16T00:00:00+00:00",
                    "finished_at": "2026-05-16T00:00:01+00:00",
                },
            )()

        with TestClient(web.app) as client, patch.object(
            web,
            "settings_for_registered_jobs",
            return_value=(settings, [fake_job]),
        ), patch.object(web.ORCHESTRATION_STORE, "save_settings", side_effect=lambda payload: payload), patch.object(
            web.ORCHESTRATION_STORE, "load_history", return_value=[]
        ), patch.object(web, "run_batch", side_effect=fake_run_batch), patch.object(
            web,
            "batch_to_dict",
            return_value={
                "batch_id": "b1",
                "status": "completed",
                "total": 1,
                "succeeded": 1,
                "failed": 0,
                "duplicate_stopped": 0,
                "skipped_not_due": 0,
                "results": [],
            },
        ):
            response = client.post(
                "/orchestration/run",
                data={
                    "enabled_jobs": "sample",
                    "interval_value__sample": "5",
                    "interval_unit__sample": "minutes",
                    "keywords": "SK",
                    "recipients": "to@example.com",
                    "sender": "from@example.com",
                    "force_due": "1",
                    "allow_email_send": "1",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(run_calls[0]["selected"], ["sample"])
        self.assertTrue(run_calls[0]["force_due"])
        self.assertTrue(run_calls[0]["allow_email_send"])

    def test_orchestration_run_forces_selected_jobs_even_without_force_checkbox(self) -> None:
        fake_job = type(
            "FakeJob",
            (),
            {
                "job_id": "sample",
                "config_name": "Sample",
                "config_path": "configs/sample.json",
                "output_dir": "outputs/sample",
                "search_terms": [],
                "filter_terms": [],
            },
        )()
        settings = {
            "keywords": ["SK"],
            "recipients": ["to@example.com"],
            "sender": "from@example.com",
            "allow_email_send": False,
            "jobs": {"sample": {"enabled": True, "interval": {"value": 10, "unit": "minutes"}}},
        }
        run_calls: list[dict[str, object]] = []

        def fake_run_batch(selected, **kwargs):
            run_calls.append({"selected": list(selected), **kwargs})
            return type(
                "FakeBatch",
                (),
                {
                    "batch_id": "b1",
                    "status": "completed",
                    "total": 1,
                    "succeeded": 1,
                    "failed": 0,
                    "duplicate_stopped": 0,
                    "skipped_not_due": 0,
                    "results": [],
                    "started_at": "2026-05-16T00:00:00+00:00",
                    "finished_at": "2026-05-16T00:00:01+00:00",
                },
            )()

        with TestClient(web.app) as client, patch.object(
            web,
            "settings_for_registered_jobs",
            return_value=(settings, [fake_job]),
        ), patch.object(web.ORCHESTRATION_STORE, "save_settings", side_effect=lambda payload: payload), patch.object(
            web.ORCHESTRATION_STORE, "save_job_state", return_value={}
        ), patch.object(web.ORCHESTRATION_STORE, "load_history", return_value=[]), patch.object(
            web, "run_batch", side_effect=fake_run_batch
        ), patch.object(
            web,
            "batch_to_dict",
            return_value={
                "batch_id": "b1",
                "status": "completed",
                "total": 1,
                "succeeded": 1,
                "failed": 0,
                "duplicate_stopped": 0,
                "skipped_not_due": 0,
                "results": [],
            },
        ):
            response = client.post(
                "/orchestration/run",
                data={
                    "enabled_jobs": "sample",
                    "interval_value__sample": "10",
                    "interval_unit__sample": "minutes",
                    "keywords": "SK",
                    "recipients": "to@example.com",
                    "sender": "from@example.com",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(run_calls[0]["selected"], ["sample"])
        self.assertTrue(run_calls[0]["force_due"])

    def test_orchestration_run_rejects_cross_origin_post(self) -> None:
        with TestClient(web.app) as client:
            response = client.post(
                "/orchestration/run",
                headers={"Origin": "https://attacker.example"},
                data={},
            )

        self.assertEqual(response.status_code, 403)

    def test_orchestration_save_rejects_cross_origin_post(self) -> None:
        with TestClient(web.app) as client:
            response = client.post(
                "/orchestration/save",
                headers={"Origin": "https://attacker.example"},
                data={},
            )

        self.assertEqual(response.status_code, 403)

    def test_orchestration_scheduler_delete_removes_task_and_disables_job(self) -> None:
        fake_job = type(
            "FakeJob",
            (),
            {
                "job_id": "sample",
                "config_name": "Sample",
                "config_path": "configs/sample.json",
                "output_dir": "outputs/sample",
                "search_terms": [],
                "filter_terms": [],
            },
        )()
        settings = {
            "keywords": ["SK"],
            "recipients": ["to@example.com"],
            "sender": "from@example.com",
            "allow_email_send": False,
            "jobs": {
                "sample": {
                    "enabled": True,
                    "interval": {"value": 15, "unit": "minutes"},
                    "next_run_at": "2026-05-18T06:04:00+00:00",
                    "last_status": "succeeded",
                }
            },
        }
        saved_payloads: list[dict[str, object]] = []

        def fake_save(payload: dict[str, object]) -> dict[str, object]:
            saved_payloads.append(payload)
            return payload

        with TestClient(web.app) as client, patch.object(
            web, "settings_for_registered_jobs", return_value=(settings, [fake_job])
        ), patch.object(web.ORCHESTRATION_STORE, "save_settings", side_effect=fake_save), patch.object(
            web.ORCHESTRATION_STORE, "save_job_state", return_value={}
        ), patch.object(web.ORCHESTRATION_STORE, "load_history", return_value=[]), patch.object(
            web, "delete_managed_task", return_value=type("DeleteResult", (), {"status": "deleted", "skipped_reason": ""})()
        ) as delete_task, patch.object(web, "load_scheduler_registry", return_value=[]):
            response = client.post(
                "/orchestration/schedulers/delete",
                data={"task_name": web.managed_task_name("sample"), "job_id": "sample"},
            )

        self.assertEqual(response.status_code, 200)
        delete_task.assert_called_once_with(web.managed_task_name("sample"))
        self.assertFalse(saved_payloads[0]["jobs"]["sample"]["enabled"])
        self.assertEqual(saved_payloads[0]["jobs"]["sample"]["next_run_at"], "")
        self.assertIn("선택한 스케줄러를 삭제했습니다", response.text)

    def test_orchestration_scheduler_delete_suppresses_already_missing_message(self) -> None:
        fake_job = type(
            "FakeJob",
            (),
            {
                "job_id": "sample",
                "config_name": "Sample",
                "config_path": "configs/sample.json",
                "output_dir": "outputs/sample",
                "search_terms": [],
                "filter_terms": [],
            },
        )()
        settings = {
            "keywords": ["SK"],
            "recipients": ["to@example.com"],
            "sender": "from@example.com",
            "allow_email_send": False,
            "jobs": {
                "sample": {
                    "enabled": True,
                    "interval": {"value": 15, "unit": "minutes"},
                    "next_run_at": "2026-05-18T06:04:00+00:00",
                    "last_status": "succeeded",
                }
            },
        }

        with TestClient(web.app) as client, patch.object(
            web, "settings_for_registered_jobs", return_value=(settings, [fake_job])
        ), patch.object(web.ORCHESTRATION_STORE, "save_settings", side_effect=lambda payload: payload), patch.object(
            web.ORCHESTRATION_STORE, "save_job_state", return_value={}
        ), patch.object(web.ORCHESTRATION_STORE, "load_history", return_value=[]), patch.object(
            web,
            "delete_managed_task",
            return_value=type("DeleteResult", (), {"status": "not_found", "skipped_reason": "오류: 지정된 파일을 찾을 수 없습니다."})(),
        ), patch.object(web, "load_scheduler_registry", return_value=[]):
            response = client.post(
                "/orchestration/schedulers/delete",
                data={"task_name": web.managed_task_name("sample"), "job_id": "sample"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("선택한 스케줄러가 이미 없습니다", response.text)
        self.assertNotIn("오류: 지정된 파일을 찾을 수 없습니다.", response.text)

    def test_orchestration_scheduler_delete_rejects_cross_origin_post(self) -> None:
        with TestClient(web.app) as client:
            response = client.post(
                "/orchestration/schedulers/delete",
                headers={"Origin": "https://attacker.example"},
                data={"task_name": web.managed_task_name("sample")},
            )

        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
