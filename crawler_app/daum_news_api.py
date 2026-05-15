from __future__ import annotations

from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
import json
import os
import re

import requests


DAUM_NEWS_API_ATTR = "daum"
KAKAO_REST_API_KEY_ENV = "KAKAO_REST_API_KEY"
KAKAO_DAUM_WEB_API_HOST = "dapi.kakao.com"
KAKAO_DAUM_WEB_API_PATH = "/v2/search/web"
DAUM_WEB_SEARCH_MAX_PAGE = 50
DAUM_WEB_SEARCH_MAX_SIZE = 50
DEFAULT_PAGE_LIMIT = 1
DEFAULT_PAGE_SIZE = 50
DEFAULT_NEWS_DOMAINS = ("news.daum.net", "v.daum.net")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)


def fetch_daum_news_api_items(
    api_url: str,
    timeout: float = 30.0,
    *,
    page_limit: int = DEFAULT_PAGE_LIMIT,
    item_limit: int | None = None,
    allowed_domains: tuple[str, ...] = DEFAULT_NEWS_DOMAINS,
) -> tuple[list[dict[str, Any]], str]:
    _validate_daum_api_url(api_url)
    session = requests.Session()
    session.trust_env = False
    session.headers.update(_headers())

    page_size = _resolve_page_size(api_url, item_limit=item_limit)
    effective_page_limit = _resolve_page_limit(page_limit=page_limit)
    page_urls = build_daum_web_search_page_urls(api_url, page_limit=effective_page_limit, size=page_size)

    discovered: list[dict[str, Any]] = []
    final_url = api_url
    for page_url in page_urls:
        _validate_daum_api_url(page_url)
        response = session.get(page_url, timeout=timeout, allow_redirects=False)
        response.raise_for_status()
        if 300 <= response.status_code < 400:
            raise ValueError("Daum Web Search API redirected unexpectedly; aborting to avoid credential leakage.")
        _validate_daum_api_url(response.url)
        final_url = response.url
        discovered.extend(parse_daum_web_search_items(response.content, allowed_domains=allowed_domains))

    deduped: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for item in discovered:
        post_id = str(item.get("post_id") or item.get("detail_url") or "").strip()
        if post_id and post_id in seen_keys:
            continue
        if post_id:
            seen_keys.add(post_id)
        deduped.append(item)
        if item_limit is not None and len(deduped) >= item_limit:
            break

    return deduped, final_url


def build_daum_web_search_page_urls(
    api_url: str,
    *,
    page_limit: int = DEFAULT_PAGE_LIMIT,
    size: int = DEFAULT_PAGE_SIZE,
) -> list[str]:
    parsed = urlparse(api_url)
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    query_map = dict(pairs)

    base_page = _safe_int(query_map.get("page"), default=1, minimum=1)
    size_value = max(1, min(DAUM_WEB_SEARCH_MAX_SIZE, int(size)))
    effective_page_limit = max(1, min(DAUM_WEB_SEARCH_MAX_PAGE, int(page_limit)))

    urls: list[str] = []
    for offset in range(effective_page_limit):
        page = base_page + offset
        updated_query = _replace_or_append_query_pairs(pairs, {"page": str(page), "size": str(size_value)})
        urls.append(urlunparse(parsed._replace(query=urlencode(updated_query, doseq=True))))
    return urls


def parse_daum_web_search_items(
    payload_bytes: bytes,
    *,
    allowed_domains: tuple[str, ...] = DEFAULT_NEWS_DOMAINS,
) -> list[dict[str, Any]]:
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Failed to parse Daum Web Search API JSON: {exc}") from exc

    documents = payload.get("documents") if isinstance(payload, dict) else None
    if not isinstance(documents, list):
        return []

    normalized: list[dict[str, Any]] = []
    for raw_document in documents:
        if not isinstance(raw_document, dict):
            continue
        item = _normalize_item(raw_document, allowed_domains=allowed_domains)
        if item is None:
            continue
        normalized.append(item)

    return normalized


def save_daum_news_api_items(
    output_dir: Path,
    *,
    search_term: str | None,
    api_url: str,
    final_url: str,
    items: list[dict[str, Any]],
    file_name: str = "daum_news_api.json",
    filter_terms: list[str] | None = None,
    allowed_domains: tuple[str, ...] = DEFAULT_NEWS_DOMAINS,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "search_term": search_term,
        "api_url": api_url,
        "final_url": final_url,
        "item_count": len(items),
        "filter_terms": filter_terms or [],
        "source_provider": "kakao_daum_web_search",
        "source_note": "Filtered to Daum News domains (news.daum.net, v.daum.net).",
        "allowed_domains": list(allowed_domains),
        "items": items,
    }
    output_path = output_dir / file_name
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def _headers() -> dict[str, str]:
    rest_api_key = os.environ.get(KAKAO_REST_API_KEY_ENV, "").strip()
    if not rest_api_key:
        raise ValueError("KAKAO_REST_API_KEY must be set in the environment to call the Kakao Daum Web Search API.")

    return {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.6",
        "Authorization": f"KakaoAK {rest_api_key}",
    }


def _validate_daum_api_url(api_url: str) -> None:
    parsed = urlparse(api_url)
    if parsed.scheme != "https" or parsed.netloc.lower() != KAKAO_DAUM_WEB_API_HOST:
        raise ValueError("Daum Web Search API URL must use https://dapi.kakao.com.")
    if parsed.path.rstrip("/") != KAKAO_DAUM_WEB_API_PATH:
        raise ValueError("Daum parser URL must use /v2/search/web.")


def _resolve_page_size(api_url: str, *, item_limit: int | None) -> int:
    parsed = urlparse(api_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    requested_size = _safe_int(query.get("size"), default=0, minimum=0)
    if requested_size <= 0:
        requested_size = min(item_limit or DEFAULT_PAGE_SIZE, DEFAULT_PAGE_SIZE)
    return max(1, min(DAUM_WEB_SEARCH_MAX_SIZE, requested_size))


def _resolve_page_limit(*, page_limit: int) -> int:
    return max(1, min(DAUM_WEB_SEARCH_MAX_PAGE, int(page_limit)))


def _replace_or_append_query_pairs(
    pairs: list[tuple[str, str]],
    updates: dict[str, str],
) -> list[tuple[str, str]]:
    replaced: set[str] = set()
    updated_pairs: list[tuple[str, str]] = []
    for key, value in pairs:
        if key in updates:
            updated_pairs.append((key, updates[key]))
            replaced.add(key)
        else:
            updated_pairs.append((key, value))
    for key, value in updates.items():
        if key not in replaced:
            updated_pairs.append((key, value))
    return updated_pairs


def _normalize_item(raw_document: dict[str, Any], *, allowed_domains: tuple[str, ...]) -> dict[str, Any] | None:
    raw_url = _clean_text(str(raw_document.get("url") or ""))
    if not raw_url:
        return None

    parsed = urlparse(raw_url)
    normalized_host = parsed.netloc.lower().strip()
    if normalized_host.startswith("www."):
        normalized_host = normalized_host[4:]

    if not _is_allowed_domain(normalized_host, allowed_domains):
        return None

    title = _clean_text(str(raw_document.get("title") or ""))
    description = _clean_text(str(raw_document.get("contents") or ""))
    pub_date = _clean_text(str(raw_document.get("datetime") or ""))
    post_id = raw_url or f"{title}|{pub_date}"
    return {
        "post_id": post_id,
        "title": title,
        "detail_url": raw_url,
        "link": raw_url,
        "pubDate": pub_date,
        "description": description,
        "source_domain": normalized_host,
        "source_api": "kakao_daum_web_search",
        "source_filter_domains": list(allowed_domains),
    }


def _is_allowed_domain(host: str, allowed_domains: tuple[str, ...]) -> bool:
    if not host:
        return False
    for allowed in allowed_domains:
        normalized_allowed = allowed.lower().strip()
        if host == normalized_allowed or host.endswith(f".{normalized_allowed}"):
            return True
    return False


def _clean_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _safe_int(value: str | None, *, default: int, minimum: int) -> int:
    try:
        parsed = int(str(value or "").strip())
    except (TypeError, ValueError):
        return default
    if parsed < minimum:
        return minimum
    return parsed
