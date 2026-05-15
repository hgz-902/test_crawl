from __future__ import annotations

import asyncio
import logging
import json
from pathlib import Path
import tempfile
import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

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
        self.assertNotIn("Daum News API", naver_response.text)
        self.assertNotIn("Daum News API", generic_response.text)

    def test_editor_shows_naver_api_panel_for_renamed_naver_api_config(self) -> None:
        naver_news_config = {
            "name": "네이버뉴스",
            "start_url": "https://openapi.naver.com/v1/search/news.json?query={search_term}&display=100&start=1&sort=date",
            "output_dir": "outputs/naver-news",
            "timeout_ms": 30000,
            "renderer": "playwright",
            "headless": True,
            "ignore_https_errors": False,
            "search_terms": ["최태원"],
            "filter_terms": [],
            "steps": [{"name": "naver_news_api", "action": "parser", "attr": "naver", "page_limit": 1, "loop_limit": 10}],
        }

        with TestClient(web.app) as client, patch.object(web, "get_config", return_value=naver_news_config):
            response = client.get("/configs/%EB%84%A4%EC%9D%B4%EB%B2%84%EB%89%B4%EC%8A%A4")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Naver News API", response.text)
        self.assertIn("data-naver-count", response.text)
        self.assertNotIn("실행 단계", response.text)

    def test_editor_shows_daum_api_panel_only_for_daum_config(self) -> None:
        daum_config = {
            "name": "다음",
            "start_url": "https://dapi.kakao.com/v2/search/web?query={search_term}&sort=recency&page=1&size=50",
            "output_dir": "outputs/daum",
            "timeout_ms": 30000,
            "renderer": "playwright",
            "headless": True,
            "ignore_https_errors": False,
            "search_terms": ["최태원", "SK"],
            "filter_terms": [],
            "steps": [
                {
                    "name": "daum_news_api",
                    "action": "parser",
                    "attr": "daum",
                    "sort": "recency",
                    "page_limit": 2,
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
            return daum_config if name == "다음" else generic_config

        with TestClient(web.app) as client, patch.object(web, "get_config", side_effect=fake_get_config):
            daum_response = client.get("/configs/%EB%8B%A4%EC%9D%8C")
            generic_response = client.get("/configs/%EA%B8%B0%ED%9B%84%EC%97%90%EB%84%88%EC%A7%80%EB%B6%80_%EB%B3%B4%EB%8F%84%EC%9E%90%EB%A3%8C")

        self.assertEqual(daum_response.status_code, 200)
        self.assertEqual(generic_response.status_code, 200)
        self.assertIn("Daum News API", daum_response.text)
        self.assertIn("data-daum-count", daum_response.text)
        self.assertIn("검색어당 가져올 뉴스 개수", daum_response.text)
        self.assertNotIn("Naver News API", daum_response.text)
        self.assertNotIn("실행 단계", daum_response.text)
        self.assertNotIn("Daum News API", generic_response.text)
        self.assertIn("실행 단계", generic_response.text)

    def test_editor_shows_workflow_steps_for_thebell_config(self) -> None:
        thebell_config = {
            "name": "더벨",
            "start_url": "https://www.thebell.co.kr/search/search.asp?keyword={search_term}&page=1&ord=NEWSDATE",
            "output_dir": "outputs/thebell",
            "timeout_ms": 60000,
            "renderer": "playwright",
            "headless": True,
            "ignore_https_errors": False,
            "search_terms": ["최태원", "SK"],
            "filter_terms": [],
            "steps": [
                {
                    "name": "open_detail",
                    "xpath": "//div[contains(@class, 'newsList')]/ul/li[1]/dl/dt/a",
                    "xpath_2": "//div[contains(@class, 'newsList')]/ul/li[2]/dl/dt/a",
                    "loop": True,
                    "loop_mode": "items",
                    "action": "click",
                    "open_mode": "same_tab",
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
            return thebell_config if name == "더벨" else generic_config

        with TestClient(web.app) as client, patch.object(web, "get_config", side_effect=fake_get_config):
            thebell_response = client.get("/configs/%EB%8D%94%EB%B2%A8")
            generic_response = client.get("/configs/%EA%B8%B0%ED%9B%84%EC%97%90%EB%84%88%EC%A7%80%EB%B6%80_%EB%B3%B4%EB%8F%84%EC%9E%90%EB%A3%8C")

        self.assertEqual(thebell_response.status_code, 200)
        self.assertEqual(generic_response.status_code, 200)
        self.assertIn("실행 단계", thebell_response.text)
        self.assertIn("open_detail", thebell_response.text)
        self.assertIn("loop", thebell_response.text)
        self.assertNotIn("Naver News API", thebell_response.text)
        self.assertNotIn("Daum News API", thebell_response.text)
        self.assertNotIn("data-thebell-page-limit", thebell_response.text)
        self.assertNotIn("TheBell", generic_response.text)
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

    def test_preview_strips_provider_credentials_before_rerender(self) -> None:
        payload = {
            "name": "네이버뉴스",
            "start_url": "https://openapi.naver.com/v1/search/news.json?query={search_term}&display=100&start=1&sort=date",
            "output_dir": "outputs/naver-news",
            "search_terms": ["최태원"],
            "naver_client_id": "real-client-id",
            "naver_client_secret": "real-client-secret",
            "kakao_rest_api_key": "real-kakao-key",
            "steps": [{"name": "naver_news_api", "action": "parser", "attr": "naver", "page_limit": 1, "loop_limit": 10}],
        }

        with TestClient(web.app) as client:
            response = client.post(
                "/configs/%EB%84%A4%EC%9D%B4%EB%B2%84%EB%89%B4%EC%8A%A4/preview",
                data={"payload": json.dumps(payload, ensure_ascii=False)},
            )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("real-client-id", response.text)
        self.assertNotIn("real-client-secret", response.text)
        self.assertNotIn("real-kakao-key", response.text)

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
        self.assertIn("display=100", saved_configs[0]["start_url"])
        self.assertEqual(saved_step["display"], 100)
        self.assertEqual(saved_step["page_limit"], 1)
        self.assertEqual(saved_step["loop_limit"], 5)
        self.assertNotIn("naver_client_id", saved_configs[0])
        self.assertNotIn("naver_client_secret", saved_configs[0])
        self.assertNotIn("fetch_detail", saved_step)
        self.assertNotIn("allowed_detail_domains", saved_step)

    def test_save_naver_config_preserves_similarity_sort(self) -> None:
        payload = {
            "name": "네이버",
            "start_url": "https://openapi.naver.com/v1/search/news.json?query={search_term}&display=100&start=1&sort=sim",
            "output_dir": "outputs/naver",
            "search_terms": ["최태원"],
            "steps": [
                {
                    "name": "naver_news_api",
                    "action": "parser",
                    "attr": "naver",
                    "sort": "sim",
                    "display": 100,
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
        self.assertIn("sort=sim", saved_configs[0]["start_url"])
        self.assertEqual(saved_configs[0]["steps"][0]["sort"], "sim")

    def test_save_daum_config_strips_credentials_and_uses_single_news_count(self) -> None:
        payload = {
            "name": "다음",
            "start_url": "https://dapi.kakao.com/v2/search/web?query={search_term}&sort=recency&page=1&size=50",
            "output_dir": "outputs/daum",
            "search_terms": ["최태원", "SK"],
            "kakao_rest_api_key": "stale-key",
            "steps": [
                {
                    "name": "daum_news_api",
                    "action": "parser",
                    "attr": "daum",
                    "sort": "recency",
                    "page_limit": 2,
                    "loop_limit": 75,
                }
            ],
        }
        saved_configs: list[dict[str, Any]] = []

        def fake_save_config_as(config: dict[str, Any], _name: str) -> Path:
            saved_configs.append(config)
            return Path("configs/다음.json")

        with patch.object(web, "save_config_as", side_effect=fake_save_config_as):
            with TestClient(web.app) as client:
                response = client.post(
                    "/configs",
                    data={
                        "payload": json.dumps(payload, ensure_ascii=False),
                        "original_id": "다음",
                    },
                    follow_redirects=False,
                )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(len(saved_configs), 1)
        saved_step = saved_configs[0]["steps"][0]
        self.assertEqual(saved_step["attr"], "daum")
        self.assertEqual(saved_step["loop_limit"], 75)
        self.assertEqual(saved_step["page_limit"], 2)
        self.assertIn("size=50", saved_configs[0]["start_url"])
        self.assertIn("page=1", saved_configs[0]["start_url"])
        self.assertNotIn("kakao_rest_api_key", saved_configs[0])

    def test_save_thebell_config_preserves_workflow_steps(self) -> None:
        payload = {
            "name": "더벨",
            "start_url": "https://www.thebell.co.kr/search/search.asp?keyword={search_term}&page=9&ord=NEWSDATE",
            "output_dir": "outputs/thebell",
            "search_terms": ["최태원", "SK"],
            "steps": [
                {
                    "name": "open_detail",
                    "xpath": "//div[contains(@class, 'newsList')]/ul/li[1]/dl/dt/a",
                    "xpath_2": "//div[contains(@class, 'newsList')]/ul/li[2]/dl/dt/a",
                    "loop": True,
                    "loop_mode": "items",
                    "action": "click",
                    "open_mode": "same_tab",
                }
            ],
        }
        saved_configs: list[dict[str, Any]] = []

        def fake_save_config_as(config: dict[str, Any], _name: str) -> Path:
            saved_configs.append(config)
            return Path("configs/더벨.json")

        with patch.object(web, "save_config_as", side_effect=fake_save_config_as):
            with TestClient(web.app) as client:
                response = client.post(
                    "/configs",
                    data={
                        "payload": json.dumps(payload, ensure_ascii=False),
                        "original_id": "더벨",
                    },
                    follow_redirects=False,
                )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(len(saved_configs), 1)
        saved_step = saved_configs[0]["steps"][0]
        self.assertEqual(saved_step["name"], "open_detail")
        self.assertEqual(saved_step["action"], "click")
        self.assertEqual(saved_step["loop_mode"], "items")
        self.assertIn("xpath_2", saved_step)
        self.assertNotEqual(saved_step.get("attr"), "thebell")
        self.assertIn("page=9", saved_configs[0]["start_url"])

    def test_naver_run_safety_blocks_missing_loop_limit(self) -> None:
        config = {
            "name": "네이버뉴스",
            "start_url": "https://openapi.naver.com/v1/search/news.json?query={search_term}&display=100&start=1&sort=date",
            "output_dir": "outputs/naver_news",
            "steps": [{"name": "naver_news_api", "action": "parser", "attr": "naver"}],
        }

        self.assertEqual(web._run_safety_error(config), "Naver UI runs require loop_limit between 1 and 100.")

    def test_naver_run_safety_blocks_non_fixed_page_limit(self) -> None:
        config = {
            "name": "네이버뉴스",
            "start_url": "https://openapi.naver.com/v1/search/news.json?query={search_term}&display=100&start=1&sort=date",
            "output_dir": "outputs/naver_news",
            "steps": [{"name": "naver_news_api", "action": "parser", "attr": "naver", "page_limit": 2, "loop_limit": 10}],
        }

        self.assertEqual(web._run_safety_error(config), "Naver UI runs require page_limit=1.")

    def test_daum_run_safety_blocks_missing_loop_limit(self) -> None:
        config = {
            "name": "다음",
            "start_url": "https://dapi.kakao.com/v2/search/web?query={search_term}&sort=recency&page=1&size=50",
            "output_dir": "outputs/daum",
            "steps": [{"name": "daum_news_api", "action": "parser", "attr": "daum"}],
        }

        self.assertEqual(web._run_safety_error(config), "Daum UI runs require loop_limit between 1 and 100.")

    def test_daum_run_safety_blocks_non_fixed_page_limit(self) -> None:
        config = {
            "name": "다음",
            "start_url": "https://dapi.kakao.com/v2/search/web?query={search_term}&sort=recency&page=1&size=50",
            "output_dir": "outputs/daum",
            "steps": [{"name": "daum_news_api", "action": "parser", "attr": "daum", "page_limit": 1, "loop_limit": 10}],
        }

        self.assertEqual(web._run_safety_error(config), "Daum UI runs require page_limit=2.")

    def test_web_run_safety_blocks_output_dir_outside_project(self) -> None:
        config = {
            "name": "다음",
            "start_url": "https://dapi.kakao.com/v2/search/web?query={search_term}&sort=recency&page=1&size=50",
            "output_dir": str(Path(tempfile.gettempdir()) / "crawler-outside-project"),
            "steps": [{"name": "daum_news_api", "action": "parser", "attr": "daum", "page_limit": 2, "loop_limit": 10}],
        }

        self.assertEqual(web._run_safety_error(config), "UI runs require output_dir under the crawler project folder.")

    def test_config_run_route_uses_job_scheduler(self) -> None:
        fake_scheduler = type(
            "FakeScheduler",
            (),
            {
                "start": lambda self: None,
                "stop": AsyncMock(),
                "run_job": AsyncMock(
                    return_value={
                        "crawler_name": "configurable",
                        "success": True,
                        "items_count": 1,
                        "message": "ok",
                        "error": None,
                        "metadata": {},
                        "data": [{"item_index": 0}],
                    }
                ),
            },
        )()
        fake_configs = [
            ConfigSummary(
                name="test",
                path=Path("configs/test.json"),
                start_url="https://example.com",
                output_dir="outputs/test",
                search_terms=[],
                filter_terms=[],
                notes="",
                created_at="",
            )
        ]

        with patch.object(web, "job_scheduler", fake_scheduler), patch.object(web, "list_configs", return_value=fake_configs):
            with TestClient(web.app) as client:
                response = client.post("/configs/test/run")

        self.assertEqual(response.status_code, 200)
        fake_scheduler.run_job.assert_awaited_once_with("test", trigger="manual")

    def test_cross_origin_post_is_rejected(self) -> None:
        with TestClient(web.app) as client:
            response = client.post("/jobs", headers={"Origin": "https://evil.example"})

        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
