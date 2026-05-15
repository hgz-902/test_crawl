from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from crawler_app.daum_news_api import (
    build_daum_web_search_page_urls,
    fetch_daum_news_api_items,
    parse_daum_web_search_items,
    save_daum_news_api_items,
)


class _FakeResponse:
    def __init__(self, *, url: str, body: bytes = b"", status_code: int = 200) -> None:
        self.url = url
        self.content = body
        self.status_code = status_code
        self.headers = {"Content-Type": "application/json"}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class _FakeSession:
    def __init__(self, responses: dict[str, _FakeResponse]) -> None:
        self.responses = responses
        self.headers: dict[str, str] = {}
        self.calls: list[str] = []
        self.trust_env = True

    def get(self, url: str, timeout: float | None = None, allow_redirects: bool = True) -> _FakeResponse:
        self.calls.append(url)
        response = self.responses.get(url)
        if response is None:
            raise requests.RequestException(f"missing mocked response: {url}")
        return response


class DaumNewsApiTests(unittest.TestCase):
    def test_build_daum_web_search_page_urls_generates_bounded_pages(self) -> None:
        base = "https://dapi.kakao.com/v2/search/web?query=%EC%B5%9C%ED%83%9C%EC%9B%90&sort=recency&page=1&size=20"

        urls = build_daum_web_search_page_urls(base, page_limit=2, size=50)

        self.assertEqual(
            urls,
            [
                "https://dapi.kakao.com/v2/search/web?query=%EC%B5%9C%ED%83%9C%EC%9B%90&sort=recency&page=1&size=50",
                "https://dapi.kakao.com/v2/search/web?query=%EC%B5%9C%ED%83%9C%EC%9B%90&sort=recency&page=2&size=50",
            ],
        )

    def test_parse_daum_web_search_items_filters_to_daum_news_domains(self) -> None:
        payload = {
            "documents": [
                {
                    "title": "<b>최태원</b> 기사",
                    "contents": "요약 <b>본문</b>",
                    "url": "https://v.daum.net/v/202605140001",
                    "datetime": "2026-05-14T09:00:00.000+09:00",
                },
                {
                    "title": "외부 문서",
                    "contents": "제외",
                    "url": "https://example.com/news/1",
                    "datetime": "2026-05-14T10:00:00.000+09:00",
                },
                {
                    "title": "뉴스 다음",
                    "contents": "포함",
                    "url": "https://news.daum.net/breakingnews/economic/1",
                    "datetime": "2026-05-14T10:30:00.000+09:00",
                },
            ]
        }

        items = parse_daum_web_search_items(json.dumps(payload).encode("utf-8"))

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["source_domain"], "v.daum.net")
        self.assertEqual(items[0]["title"], "최태원 기사")
        self.assertEqual(items[0]["description"], "요약 본문")
        self.assertEqual(items[0]["source_api"], "kakao_daum_web_search")
        self.assertEqual(items[1]["source_domain"], "news.daum.net")

    def test_fetch_daum_news_api_items_uses_env_auth_and_item_limit(self) -> None:
        page_1 = "https://dapi.kakao.com/v2/search/web?query=SK&sort=recency&page=1&size=1"
        page_2 = "https://dapi.kakao.com/v2/search/web?query=SK&sort=recency&page=2&size=1"
        responses = {
            page_1: _FakeResponse(
                url=page_1,
                body=json.dumps(
                    {
                        "documents": [
                            {
                                "title": "SK 1",
                                "contents": "요약1",
                                "url": "https://v.daum.net/v/1",
                                "datetime": "2026-05-14T09:00:00.000+09:00",
                            }
                        ]
                    }
                ).encode("utf-8"),
            ),
            page_2: _FakeResponse(
                url=page_2,
                body=json.dumps(
                    {
                        "documents": [
                            {
                                "title": "SK 2",
                                "contents": "요약2",
                                "url": "https://v.daum.net/v/2",
                                "datetime": "2026-05-14T10:00:00.000+09:00",
                            }
                        ]
                    }
                ).encode("utf-8"),
            ),
        }
        fake_session = _FakeSession(responses)

        with patch.dict("os.environ", {"KAKAO_REST_API_KEY": "rest-key"}, clear=False):
            with patch("crawler_app.daum_news_api.requests.Session", return_value=fake_session):
                items, final_url = fetch_daum_news_api_items(page_1, timeout=2.0, page_limit=2, item_limit=1)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "SK 1")
        self.assertEqual(final_url, page_2)
        self.assertEqual(fake_session.headers["Authorization"], "KakaoAK rest-key")
        self.assertEqual(fake_session.calls, [page_1, page_2])

    def test_fetch_daum_news_api_items_rejects_redirects(self) -> None:
        api_url = "https://dapi.kakao.com/v2/search/web?query=SK&sort=recency&page=1&size=1"
        fake_session = _FakeSession({api_url: _FakeResponse(url="https://example.com/redirected", status_code=302)})

        with patch.dict("os.environ", {"KAKAO_REST_API_KEY": "rest-key"}, clear=False):
            with patch("crawler_app.daum_news_api.requests.Session", return_value=fake_session):
                with self.assertRaises(ValueError):
                    fetch_daum_news_api_items(api_url, timeout=2.0, page_limit=1, item_limit=1)

    def test_fetch_daum_news_api_items_rejects_non_kakao_url(self) -> None:
        with patch.dict("os.environ", {"KAKAO_REST_API_KEY": "rest-key"}, clear=False):
            with self.assertRaises(ValueError):
                fetch_daum_news_api_items("https://example.com/v2/search/web?query=x")

    def test_save_daum_news_api_items_writes_provider_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "daum"
            manifest = save_daum_news_api_items(
                output_dir,
                search_term="SK",
                api_url="https://dapi.kakao.com/v2/search/web?query=SK",
                final_url="https://dapi.kakao.com/v2/search/web?query=SK",
                items=[{"post_id": "1", "title": "A", "description": "desc"}],
            )

            payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(manifest.name, "daum_news_api.json")
            self.assertEqual(payload["item_count"], 1)
            self.assertEqual(payload["source_provider"], "kakao_daum_web_search")
            self.assertEqual(payload["allowed_domains"], ["news.daum.net", "v.daum.net"])
            self.assertEqual(payload["items"][0]["title"], "A")


if __name__ == "__main__":
    unittest.main()
