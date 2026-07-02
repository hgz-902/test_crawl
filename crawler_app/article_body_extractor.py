from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from html import unescape
from typing import Any, Callable
from urllib.parse import urljoin, urlparse
import json
import os
import re
import subprocess
import sys

import requests


BODY_EXTRACTOR_NAME = "newspaper3k"
BODY_EXTRACT_ENV = "SEARCH_NEWS_BODY_EXTRACT"
BODY_EXTRACT_TIMEOUT_ENV = "SEARCH_NEWS_BODY_TIMEOUT_SECONDS"
BODY_EXTRACT_MAX_WORKERS_ENV = "SEARCH_NEWS_BODY_MAX_WORKERS"
GOOGLE_NEWS_DECODE_TIMEOUT_ENV = "GOOGLE_NEWS_DECODE_TIMEOUT_SECONDS"
GOOGLE_NEWS_DECODER_ENV = "GOOGLE_NEWS_DECODER"
DEFAULT_BODY_EXTRACT_TIMEOUT = 7.0
DEFAULT_BODY_EXTRACT_MAX_WORKERS = 3
DEFAULT_GOOGLE_NEWS_DECODE_TIMEOUT = 6.0
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class ArticleBodyResult:
    body: str
    body_url: str
    body_extract_status: str
    body_extract_error: str
    body_char_count: int
    body_extractor: str

    def as_item_fields(self) -> dict[str, Any]:
        return {
            "body": self.body,
            "body_url": self.body_url,
            "body_extract_status": self.body_extract_status,
            "body_extract_error": self.body_extract_error,
            "body_char_count": self.body_char_count,
            "body_extractor": self.body_extractor,
        }


def enrich_items_with_article_body(
    items: list[dict[str, Any]],
    *,
    platform: str,
    timeout: float,
    url_selector: Callable[[dict[str, Any]], str],
) -> None:
    if not _body_extract_enabled() or not items:
        return
    effective_timeout = _body_extract_timeout(timeout)
    max_workers = _body_extract_max_workers(len(items))

    def enrich_one(index: int, item: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        try:
            source_url = str(url_selector(item) or "").strip()
            if not source_url:
                return index, _failed_result("", "missing_body_url").as_item_fields()
            result = extract_article_body(source_url, platform=platform, timeout=effective_timeout)
            return index, result.as_item_fields()
        except Exception as exc:  # noqa: BLE001 - per-item extraction failures stay local to the item.
            return index, _failed_result("", _safe_error(exc)).as_item_fields()

    if max_workers <= 1:
        for index, item in enumerate(items):
            _, fields = enrich_one(index, item)
            item.update(fields)
        return

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(enrich_one, index, item) for index, item in enumerate(items)]
        for future in as_completed(futures):
            index, fields = future.result()
            items[index].update(fields)


def extract_article_body(url: str, *, platform: str = "", timeout: float = 8.0) -> ArticleBodyResult:
    source_url = str(url or "").strip()
    if not source_url:
        return _failed_result("", "missing_body_url")

    body_url = resolve_google_news_url(source_url, timeout=timeout) if _is_google_news_url(source_url) else source_url
    body = ""
    error = ""
    try:
        body = _extract_with_newspaper(body_url, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - body extraction failure must not fail crawling.
        error = _safe_error(exc)

    cleaned = _clean_body(body)
    if cleaned:
        return ArticleBodyResult(
            body=cleaned,
            body_url=body_url,
            body_extract_status="success",
            body_extract_error="",
            body_char_count=len(cleaned),
            body_extractor=BODY_EXTRACTOR_NAME,
        )
    return ArticleBodyResult(
        body="",
        body_url=body_url,
        body_extract_status="failed",
        body_extract_error=error or "empty_body",
        body_char_count=0,
        body_extractor=BODY_EXTRACTOR_NAME,
    )


def resolve_google_news_url(url: str, *, timeout: float = 8.0) -> str:
    source_url = str(url or "").strip()
    if not source_url:
        return ""
    if not _is_google_news_url(source_url):
        return source_url

    if _google_news_decoder_enabled():
        decoded_url = _resolve_google_news_with_decoder(source_url)
        if decoded_url:
            return decoded_url

    try:
        response = requests.get(
            source_url,
            timeout=timeout,
            allow_redirects=True,
            headers=_public_headers(),
        )
        response.raise_for_status()
    except requests.RequestException:
        return source_url

    final_url = str(response.url or "").strip()
    if final_url and not _is_google_news_url(final_url):
        return final_url

    html = response.text or ""
    for candidate in _google_original_url_candidates(html, base_url=final_url or source_url):
        if candidate and not _is_google_news_url(candidate):
            return candidate
    return final_url or source_url


def _resolve_google_news_with_decoder(url: str) -> str:
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import json, sys\n"
                    "from googlenewsdecoder import gnewsdecoder\n"
                    "print(json.dumps(gnewsdecoder(sys.argv[1], interval=0), ensure_ascii=False))\n"
                ),
                url,
            ],
            capture_output=True,
            text=True,
            timeout=_google_news_decode_timeout(),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""

    if completed.returncode != 0 or not completed.stdout.strip():
        return ""
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return ""
    if not isinstance(result, dict) or not result.get("status"):
        return ""
    decoded = str(result.get("decoded_url") or "").strip()
    if decoded and not _is_google_news_url(decoded):
        return decoded
    return ""


def _extract_with_newspaper(url: str, *, timeout: float) -> str:
    try:
        from newspaper import Article, Config  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001 - dependency availability is reported as extraction failure.
        raise RuntimeError("newspaper3k dependency is not available") from exc

    config = Config()
    config.browser_user_agent = USER_AGENT
    config.request_timeout = timeout
    article = Article(url, language="ko", config=config)
    article.download()
    article.parse()
    return article.text or ""


def _google_original_url_candidates(html: str, *, base_url: str) -> list[str]:
    candidates: list[str] = []
    patterns = [
        r'<link\s+[^>]*rel=["\']canonical["\'][^>]*href=["\']([^"\']+)["\']',
        r'<meta\s+[^>]*(?:property|name)=["\']og:url["\'][^>]*content=["\']([^"\']+)["\']',
        r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>',
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, html, flags=re.IGNORECASE):
            candidate = _clean_url(match.group(1), base_url=base_url)
            if candidate:
                candidates.append(candidate)
    return _dedupe_preserve_order(candidates)


def _clean_url(value: str, *, base_url: str) -> str:
    text = unescape(str(value or "")).strip()
    if not text or text.startswith(("javascript:", "mailto:", "#")):
        return ""
    return urljoin(base_url, text)


def _is_google_news_url(url: str) -> bool:
    host = (urlparse(str(url or "")).hostname or "").lower()
    return host == "news.google.com"


def _clean_body(value: str) -> str:
    paragraphs = [re.sub(r"\s+", " ", line).strip() for line in str(value or "").splitlines()]
    return "\n".join(line for line in paragraphs if line).strip()


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _failed_result(url: str, error: str) -> ArticleBodyResult:
    return ArticleBodyResult(
        body="",
        body_url=url,
        body_extract_status="failed",
        body_extract_error=error,
        body_char_count=0,
        body_extractor=BODY_EXTRACTOR_NAME,
    )


def _safe_error(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}"
    return text[:500]


def _public_headers() -> dict[str, str]:
    return {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.6",
    }


def _body_extract_enabled() -> bool:
    raw = os.getenv(BODY_EXTRACT_ENV)
    if raw is None:
        return True
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _body_extract_timeout(api_timeout: float) -> float:
    try:
        configured = float(os.getenv(BODY_EXTRACT_TIMEOUT_ENV, ""))
    except ValueError:
        configured = 0.0
    if configured > 0:
        return configured
    return max(2.0, min(float(api_timeout), DEFAULT_BODY_EXTRACT_TIMEOUT))


def _body_extract_max_workers(item_count: int) -> int:
    try:
        configured = int(os.getenv(BODY_EXTRACT_MAX_WORKERS_ENV, ""))
    except ValueError:
        configured = 0
    workers = configured if configured > 0 else DEFAULT_BODY_EXTRACT_MAX_WORKERS
    return max(1, min(workers, max(item_count, 1)))


def _google_news_decode_timeout() -> float:
    try:
        configured = float(os.getenv(GOOGLE_NEWS_DECODE_TIMEOUT_ENV, ""))
    except ValueError:
        configured = 0.0
    if configured > 0:
        return configured
    return DEFAULT_GOOGLE_NEWS_DECODE_TIMEOUT


def _google_news_decoder_enabled() -> bool:
    raw = os.getenv(GOOGLE_NEWS_DECODER_ENV)
    if raw is None:
        return True
    return raw.strip().lower() not in {"0", "false", "no", "off"}
