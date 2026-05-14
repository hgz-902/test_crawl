from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from crawler_app.naver_news_api import (
    build_naver_news_search_page_urls,
    fetch_naver_news_api_items,
    save_naver_news_api_items,
)


class _FakeResponse:
    def __init__(self, *, url: str, body: bytes = b"", status_code: int = 200, headers: dict[str, str] | None = None):
        self.url = url
        self.content = body
        self.status_code = status_code
        self.headers = headers or {"Content-Type": "application/json"}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class _FakeSession:
    def __init__(self, responses: dict[str, _FakeResponse]):
        self.responses = responses
        self.headers: dict[str, str] = {}
        self.calls: list[str] = []
        self.trust_env = True

    def get(self, url: str, timeout: float | None = None) -> _FakeResponse:
        self.calls.append(url)
        response = self.responses.get(url)
        if response is None:
            raise requests.RequestException("missing mocked response")
        return response


class NaverNewsApiTests(unittest.TestCase):
    def test_build_naver_news_search_page_urls_generates_two_pages(self) -> None:
        base = "https://openapi.naver.com/v1/search/news.json?query=%EC%B5%9C%ED%83%9C%EC%9B%90&display=10&start=1&sort=date"
        urls = build_naver_news_search_page_urls(base, page_limit=2)
        self.assertEqual(
            urls,
            [
                "https://openapi.naver.com/v1/search/news.json?query=%EC%B5%9C%ED%83%9C%EC%9B%90&display=10&start=1&sort=date",
                "https://openapi.naver.com/v1/search/news.json?query=%EC%B5%9C%ED%83%9C%EC%9B%90&display=10&start=11&sort=date",
            ],
        )

    def test_build_naver_news_search_page_urls_adds_missing_start(self) -> None:
        base = "https://openapi.naver.com/v1/search/news.json?query=x&display=10&sort=date"
        urls = build_naver_news_search_page_urls(base, page_limit=2)
        self.assertEqual(urls[0], "https://openapi.naver.com/v1/search/news.json?query=x&display=10&sort=date&start=1")
        self.assertEqual(urls[1], "https://openapi.naver.com/v1/search/news.json?query=x&display=10&sort=date&start=11")

    def test_fetch_naver_news_api_items_collects_pages_without_detail_fetch(self) -> None:
        api_1 = "https://openapi.naver.com/v1/search/news.json?query=%EC%B5%9C%ED%83%9C%EC%9B%90&display=10&start=1&sort=date"
        api_2 = "https://openapi.naver.com/v1/search/news.json?query=%EC%B5%9C%ED%83%9C%EC%9B%90&display=10&start=11&sort=date"
        publisher_1 = "https://publisher.example.com/a1"
        publisher_2 = "https://publisher.example.com/a2"
        responses = {
            api_1: _FakeResponse(
                url=api_1,
                body=json.dumps({"items": [{"title": "기사1", "originallink": publisher_1, "link": "https://n.news.naver.com/a1"}]}).encode("utf-8"),
            ),
            api_2: _FakeResponse(
                url=api_2,
                body=json.dumps({"items": [{"title": "기사2", "originallink": publisher_2, "link": "https://n.news.naver.com/a2"}]}).encode("utf-8"),
            ),
        }
        fake_session = _FakeSession(responses)

        with patch.dict("os.environ", {"NAVER_CLIENT_ID": "id", "NAVER_CLIENT_SECRET": "secret"}, clear=False):
            with patch("crawler_app.naver_news_api.requests.Session", return_value=fake_session):
                items, final_url = fetch_naver_news_api_items(api_1, timeout=2.0, page_limit=2)

        self.assertEqual(final_url, api_2)
        self.assertEqual(len(items), 2)
        self.assertEqual(fake_session.calls, [api_1, api_2])
        self.assertEqual(items[0]["title"], "기사1")
        self.assertEqual(items[0]["originallink"], publisher_1)
        self.assertNotIn("detail", items[0])
        self.assertNotIn("detail_body", items[0])

    def test_fetch_naver_news_api_items_applies_item_limit(self) -> None:
        api_1 = "https://openapi.naver.com/v1/search/news.json?query=x&display=10&start=1"
        responses = {
            api_1: _FakeResponse(
                url=api_1,
                body=json.dumps(
                    {
                        "items": [
                            {"title": "기사1", "originallink": "https://example.com/a1", "link": "https://n.news.naver.com/a1"},
                            {"title": "기사2", "originallink": "https://example.com/a2", "link": "https://n.news.naver.com/a2"},
                        ]
                    }
                ).encode("utf-8"),
            ),
        }
        fake_session = _FakeSession(responses)

        with patch.dict("os.environ", {"NAVER_CLIENT_ID": "id", "NAVER_CLIENT_SECRET": "secret"}, clear=False):
            with patch("crawler_app.naver_news_api.requests.Session", return_value=fake_session):
                items, _ = fetch_naver_news_api_items(api_1, timeout=2.0, item_limit=1)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "기사1")

    def test_fetch_naver_news_api_items_rejects_non_naver_api_url(self) -> None:
        with patch.dict("os.environ", {"NAVER_CLIENT_ID": "id", "NAVER_CLIENT_SECRET": "secret"}, clear=False):
            with self.assertRaises(ValueError):
                fetch_naver_news_api_items("https://example.com/search/news.json?query=x")

    def test_fetch_naver_news_api_items_uses_env_client_headers(self) -> None:
        response = _FakeResponse(
            body=b'{"items": []}',
            url="https://openapi.naver.com/v1/search/news.json?query=%EC%A3%BC%EC%8B%9D",
        )
        session = _FakeSession({"https://openapi.naver.com/v1/search/news.json?query=%EC%A3%BC%EC%8B%9D": response})

        with patch.dict(
            "os.environ",
            {
                "NAVER_CLIENT_ID": "client-id",
                "NAVER_CLIENT_SECRET": "client-secret",
            },
            clear=False,
        ), patch("crawler_app.naver_news_api.requests.Session", return_value=session):
            items, final_url = fetch_naver_news_api_items(
                "https://openapi.naver.com/v1/search/news.json?query=%EC%A3%BC%EC%8B%9D"
            )

        self.assertEqual(items, [])
        self.assertEqual(final_url, response.url)
        self.assertEqual(session.headers["X-Naver-Client-Id"], "client-id")
        self.assertEqual(session.headers["X-Naver-Client-Secret"], "client-secret")
        self.assertEqual(session.calls[0], "https://openapi.naver.com/v1/search/news.json?query=%EC%A3%BC%EC%8B%9D")

    def test_save_naver_news_api_items_writes_manifest_and_per_item_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "naver"
            items = [
                {"post_id": "1", "title": "A", "description": "descA"},
                {"post_id": "2", "title": "B", "description": "descB"},
            ]
            manifest = save_naver_news_api_items(
                output_dir,
                search_term="최태원",
                api_url="https://openapi.naver.com/v1/search/news.json?query=%EC%B5%9C%ED%83%9C%EC%9B%90",
                final_url="https://openapi.naver.com/v1/search/news.json?query=%EC%B5%9C%ED%83%9C%EC%9B%90",
                items=items,
            )
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(payload["item_count"], 2)
            self.assertEqual(len(payload["item_files"]), 2)
            for file_path in payload["item_files"]:
                loaded = json.loads(Path(file_path).read_text(encoding="utf-8"))
                self.assertIn("post_id", loaded)
                self.assertNotIn("detail_body", loaded)


if __name__ == "__main__":
    unittest.main()
