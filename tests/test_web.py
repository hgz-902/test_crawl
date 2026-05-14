from __future__ import annotations

import asyncio
import logging
import json
from pathlib import Path
import tempfile
import unittest
from typing import Any
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
        self.assertIn("외부 사이트 접속과 파일 저장이 발생할 수 있습니다.", response.text)

    def test_editor_shows_naver_api_panel_only_for_naver_config(self) -> None:
        naver_config = {
            "name": "네이버",
            "start_url": "https://openapi.naver.com/v1/search/news.json?query={search_term}&display=20&start=1&sort=date",
            "output_dir": "outputs/naver",
            "timeout_ms": 30000,
            "renderer": "playwright",
            "headless": False,
            "ignore_https_errors": False,
            "search_terms": ["최태원"],
            "filter_terms": [],
            "steps": [
                {
                    "name": "naver_news_api",
                    "action": "parser",
                    "attr": "naver",
                    "loop_limit": 20,
                }
            ],
        }
        generic_config = {
            "name": "기후에너지부_보도자료",
            "start_url": "https://example.com?pagerOffset={search_term}",
            "output_dir": "outputs/mcee",
            "timeout_ms": 30000,
            "renderer": "playwright",
            "headless": False,
            "ignore_https_errors": False,
            "search_terms": ["0", "10"],
            "filter_terms": ["전력"],
            "steps": [{"name": "open_detail", "xpath": "//a[1]", "action": "click"}],
        }

        def fake_get_config(name: str):
            return naver_config if name == "네이버" else generic_config

        with TestClient(web.app) as client, patch.object(web, "get_config", side_effect=fake_get_config):
            naver_response = client.get("/configs/%EB%84%A4%EC%9D%B4%EB%B2%84")
            generic_response = client.get("/configs/%EA%B8%B0%ED%9B%84%EC%97%90%EB%84%88%EC%A7%80%EB%B6%80_%EB%B3%B4%EB%8F%84%EC%9E%90%EB%A3%8C")

        self.assertEqual(naver_response.status_code, 200)
        self.assertEqual(generic_response.status_code, 200)
        self.assertIn("Naver News API", naver_response.text)
        self.assertNotIn("Naver News API", generic_response.text)
        self.assertIn('id="initial-config-json"', naver_response.text)
        self.assertIn("검색어당 가져올 뉴스 개수", naver_response.text)
        self.assertIn("data-naver-count", naver_response.text)
        self.assertNotIn("data-naver-display", naver_response.text)
        self.assertNotIn("data-naver-loop-limit", naver_response.text)
        self.assertNotIn("API display", naver_response.text)
        self.assertNotIn("실행 단계", naver_response.text)
        self.assertNotIn("fetch detail", naver_response.text)
        self.assertNotIn("allowed_detail_domains", naver_response.text)
        self.assertIn("검색어 목록", generic_response.text)
        self.assertIn("실행 단계", generic_response.text)

    def test_editor_does_not_render_naver_credentials(self) -> None:
        naver_config = web.default_config("네이버")

        with patch.object(web, "get_config", return_value=naver_config):
            with TestClient(web.app) as client:
                response = client.get("/configs/%EB%84%A4%EC%9D%B4%EB%B2%84")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('name="naver_client_id"', response.text)
        self.assertNotIn('name="naver_client_secret"', response.text)
        self.assertNotIn("Secret configured", response.text)

    def test_save_naver_config_uses_single_news_count(self) -> None:
        payload = {
            "name": "네이버",
            "start_url": "https://openapi.naver.com/v1/search/news.json?query={search_term}&display=5&start=1&sort=date",
            "output_dir": "outputs/naver",
            "search_terms": ["최태원", "SK하이닉스"],
            "naver_client_id": "stale-id",
            "naver_client_secret": "stale-secret",
            "steps": [
                {
                    "name": "naver_news_api",
                    "action": "parser",
                    "attr": "naver",
                    "display": 5,
                    "page_limit": 1,
                    "loop_limit": 5,
                }
            ],
        }
        saved_configs: list[dict[str, Any]] = []

        def fake_save_config_as(config: dict[str, Any], _name: str) -> Path:
            saved_configs.append(config)
            return Path("configs/네이버.json")

        with patch.object(web, "save_config_as", side_effect=fake_save_config_as):
            with TestClient(web.app) as client:
                response = client.post(
                    "/configs",
                    data={
                        "payload": json.dumps(payload, ensure_ascii=False),
                        "original_id": "네이버",
                    },
                    follow_redirects=False,
                )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(len(saved_configs), 1)
        saved_step = saved_configs[0]["steps"][0]
        self.assertIn("display=5", saved_configs[0]["start_url"])
        self.assertEqual(saved_step["display"], 5)
        self.assertEqual(saved_step["loop_limit"], 5)
        self.assertNotIn("naver_client_id", saved_configs[0])
        self.assertNotIn("naver_client_secret", saved_configs[0])
        self.assertNotIn("fetch_detail", saved_step)
        self.assertNotIn("allowed_detail_domains", saved_step)

    def test_naver_run_safety_blocks_missing_loop_limit(self) -> None:
        config = {
            "name": "네이버뉴스",
            "start_url": "https://openapi.naver.com/v1/search/news.json?query={search_term}&display=100&start=1&sort=date",
            "output_dir": "outputs/naver_news",
            "steps": [{"name": "naver_news_api", "action": "parser", "attr": "naver"}],
        }

        self.assertEqual(web._run_safety_error(config), "Naver UI runs require loop_limit between 1 and 100.")

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


if __name__ == "__main__":
    unittest.main()
