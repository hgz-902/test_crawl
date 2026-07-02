from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
import json
import os
import re

import requests

from crawler_app.article_body_extractor import enrich_items_with_article_body


DAUM_NEWS_API_ATTR = "daum"
KAKAO_REST_API_KEY_ENV = "KAKAO_REST_API_KEY"
KAKAO_DAUM_WEB_API_HOST = "dapi.kakao.com"
KAKAO_DAUM_WEB_API_PATH = "/v2/search/web"
DAUM_SOURCE_ENRICH_ENV = "DAUM_NEWS_ENRICH_SOURCE"
DAUM_SOURCE_ENRICH_TIMEOUT_ENV = "DAUM_NEWS_ENRICH_TIMEOUT_SECONDS"
DAUM_WEB_SEARCH_MAX_PAGE = 50
DAUM_WEB_SEARCH_MAX_SIZE = 50
DEFAULT_PAGE_LIMIT = 1
DEFAULT_PAGE_SIZE = 50
DEFAULT_NEWS_DOMAINS = ("news.daum.net", "v.daum.net")
KST = timezone(timedelta(hours=9))
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)


# Kakao Daum Web Search API에서 Daum 뉴스 item 목록을 가져온다.
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

    if _bool_env(DAUM_SOURCE_ENRICH_ENV, default=True):
        _enrich_items_with_daum_detail_source(deduped, timeout=_source_enrich_timeout(timeout))

    return deduped, final_url


# Daum web 검색 페이지 URL 목록을 생성해 반환한다.
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


# Daum web 검색 item 목록을 파싱한다.
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


# Daum API item 목록을 item별 JSON 파일로 저장한다.
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
    enrich_items_with_article_body(
        items,
        platform="daum",
        timeout=30.0,
        url_selector=lambda item: str(item.get("detail_url") or item.get("link") or ""),
    )
    date_label, time_label = _korean_timestamp_labels()
    items_dir = output_dir / "items" / date_label
    items_dir.mkdir(parents=True, exist_ok=True)

    item_files: list[str] = []
    for index, item in enumerate(items, start=1):
        item_name = _batch_item_file_name("DAUM", date_label, time_label, index)
        item_path = items_dir / item_name
        item_payload = dict(item)
        item_payload.setdefault("search_term", search_term)
        item_payload.setdefault("item_index", index)
        item_payload.setdefault("source_provider", "kakao_daum_web_search")
        item_payload.setdefault("api_url", api_url)
        item_payload.setdefault("final_url", final_url)
        item_payload.setdefault("allowed_domains", list(allowed_domains))
        item_path.write_text(json.dumps(item_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        item_files.append(f"items/{date_label}/{item_name}")

    payload = {
        "search_term": search_term,
        "api_url": api_url,
        "final_url": final_url,
        "item_count": len(items),
        "filter_terms": filter_terms or [],
        "source_provider": "kakao_daum_web_search",
        "source_note": "Filtered to Daum News domains (news.daum.net, v.daum.net).",
        "allowed_domains": list(allowed_domains),
        "item_files": item_files,
        "items": items,
    }
    output_path = output_dir / file_name
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


# batch item 파일 이름 값을 계산해 반환한다.
def _batch_item_file_name(prefix: str, date_label: str, time_label: str, item_index: int) -> str:
    return f"{prefix}_{date_label}_{time_label}_{item_index}.json"


# korean timestamp 라벨 값을 계산해 반환한다.
def _korean_timestamp_labels() -> tuple[str, str]:
    now = datetime.now(KST)
    return now.strftime("%Y%m%d"), now.strftime("%H%M%S")


# item 식별자 값을 계산해 반환한다.
def _item_identity(item: dict[str, Any]) -> str:
    for key in ("post_id", "detail_url", "originallink", "link", "guid", "title"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return json.dumps(item, ensure_ascii=False, sort_keys=True)


# 외부 요청에 사용할 HTTP 헤더를 만든다.
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


# Daum API URL의 유효성을 검증한다.
def _validate_daum_api_url(api_url: str) -> None:
    parsed = urlparse(api_url)
    if parsed.scheme != "https" or parsed.netloc.lower() != KAKAO_DAUM_WEB_API_HOST:
        raise ValueError("Daum Web Search API URL must use https://dapi.kakao.com.")
    if parsed.path.rstrip("/") != KAKAO_DAUM_WEB_API_PATH:
        raise ValueError("Daum parser URL must use /v2/search/web.")


# 페이지 size를 실제 실행 값으로 해석한다.
def _resolve_page_size(api_url: str, *, item_limit: int | None) -> int:
    parsed = urlparse(api_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    requested_size = _safe_int(query.get("size"), default=0, minimum=0)
    if requested_size <= 0:
        requested_size = min(item_limit or DEFAULT_PAGE_SIZE, DEFAULT_PAGE_SIZE)
    return max(1, min(DAUM_WEB_SEARCH_MAX_SIZE, requested_size))


# 페이지 limit를 실제 실행 값으로 해석한다.
def _resolve_page_limit(*, page_limit: int) -> int:
    return max(1, min(DAUM_WEB_SEARCH_MAX_PAGE, int(page_limit)))


# 쿼리 파라미터 목록에서 지정 값을 교체하거나 추가한다.
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


# item을 표준 형태로 정규화한다.
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
        "source_platform_domain": normalized_host,
        "source_api": "kakao_daum_web_search",
        "source_filter_domains": list(allowed_domains),
    }


# allowed domain 여부를 판정한다.
def _is_allowed_domain(host: str, allowed_domains: tuple[str, ...]) -> bool:
    if not host:
        return False
    for allowed in allowed_domains:
        normalized_allowed = allowed.lower().strip()
        if host == normalized_allowed or host.endswith(f".{normalized_allowed}"):
            return True
    return False


# 텍스트를 정리한다.
def _clean_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", unescape(text)).strip()


# Daum 상세 페이지에서 매체명을 보강한다. 원문 URL은 없는 경우가 많아 source_name을 우선 남긴다.
def _enrich_items_with_daum_detail_source(items: list[dict[str, Any]], *, timeout: float) -> None:
    if not items:
        return
    session = requests.Session()
    session.trust_env = False
    session.headers.update(_public_headers())
    cache: dict[str, dict[str, str]] = {}
    for item in items:
        detail_url = str(item.get("detail_url") or item.get("link") or "").strip()
        if not detail_url:
            continue
        if detail_url not in cache:
            cache[detail_url] = _fetch_daum_detail_source(session, detail_url, timeout=timeout)
        source = cache[detail_url]
        if not source:
            continue
        for key, value in source.items():
            if value and not item.get(key):
                item[key] = value


# Daum 상세 HTML에서 확인 가능한 매체 식별값을 추출한다.
def _fetch_daum_detail_source(session: requests.Session, url: str, *, timeout: float) -> dict[str, str]:
    try:
        response = session.get(url, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
    except requests.RequestException:
        return {}
    html = response.text or ""
    source_name = (
        _meta_content(html, "og:article:author")
        or _alex_action_attr(html, "data-cp-name")
        or _cp_object_value(html, "cpKorName")
        or _site_name_media(html)
    )
    source_cp_id = _alex_action_attr(html, "data-cp-id") or _cp_object_value(html, "cpId")
    result: dict[str, str] = {}
    if source_name:
        result["source_name"] = source_name
    if source_cp_id:
        result["source_cp_id"] = source_cp_id
    return result


# 공개 상세 페이지 요청용 헤더다. Kakao API Authorization을 절대 재사용하지 않는다.
def _public_headers() -> dict[str, str]:
    return {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.6",
    }


def _meta_content(html: str, property_name: str) -> str:
    pattern = rf'<meta\s+[^>]*property=["\']{re.escape(property_name)}["\'][^>]*content=["\']([^"\']+)["\']'
    match = re.search(pattern, html, flags=re.IGNORECASE)
    return _clean_text(match.group(1)) if match else ""


def _alex_action_attr(html: str, attr_name: str) -> str:
    meta_match = re.search(r'<meta\s+[^>]*name=["\']alex-action["\'][^>]*>', html, flags=re.IGNORECASE)
    if not meta_match:
        return ""
    attr_match = re.search(rf'{re.escape(attr_name)}=["\']([^"\']+)["\']', meta_match.group(0), flags=re.IGNORECASE)
    return _clean_text(attr_match.group(1)) if attr_match else ""


def _cp_object_value(html: str, key: str) -> str:
    match = re.search(rf'{re.escape(key)}\s*:\s*(?:Number\()?["\']([^"\']+)["\']', html)
    if not match:
        return ""
    return _decode_js_string(match.group(1))


def _site_name_media(html: str) -> str:
    value = _meta_content(html, "og:site_name")
    if "|" not in value:
        return ""
    return _clean_text(value.rsplit("|", 1)[-1])


def _decode_js_string(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return _clean_text(value)


def _bool_env(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _source_enrich_timeout(api_timeout: float) -> float:
    try:
        configured = float(os.environ.get(DAUM_SOURCE_ENRICH_TIMEOUT_ENV, ""))
    except ValueError:
        configured = 0.0
    if configured > 0:
        return configured
    return max(2.0, min(float(api_timeout), 8.0))


# 문자열 값을 최소값 이상 정수로 안전하게 변환한다.
def _safe_int(value: str | None, *, default: int, minimum: int) -> int:
    try:
        parsed = int(str(value or "").strip())
    except (TypeError, ValueError):
        return default
    if parsed < minimum:
        return minimum
    return parsed
