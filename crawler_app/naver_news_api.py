from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from xml.etree import ElementTree as ET
import json
import os
import re

import requests


NAVER_NEWS_API_ATTR = "naver"
NAVER_CLIENT_ID_ENV = "NAVER_CLIENT_ID"
NAVER_CLIENT_SECRET_ENV = "NAVER_CLIENT_SECRET"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)
DEFAULT_PAGE_LIMIT = 1
NAVER_API_HOST = "openapi.naver.com"
NAVER_DISPLAY_MAX = 100
KST = timezone(timedelta(hours=9))


# Naver news 검색 페이지 URL 목록을 생성해 반환한다.
def build_naver_news_search_page_urls(
    api_url: str,
    *,
    page_limit: int = DEFAULT_PAGE_LIMIT,
    display: int | None = None,
) -> list[str]:
    parsed = urlparse(api_url)
    pairs = parse_qsl(parsed.query, keep_blank_values=True)

    query_map = dict(pairs)
    display_override = display
    display = _resolve_display_count(query_map.get("display"), override=display_override)
    if page_limit <= 1:
        if display_override is not None and str(query_map.get("display")) != str(display):
            return [urlunparse(parsed._replace(query=urlencode(_replace_or_append_query_pairs(pairs, {"display": str(display)}), doseq=True)))]
        return [api_url]

    start_raw = query_map.get("start", "1")
    try:
        start = int(start_raw)
    except ValueError:
        start = 1

    start = max(1, start)
    urls: list[str] = []
    for index in range(page_limit):
        page_start = start + (index * display)
        updates = {"start": str(page_start)}
        if display_override is not None:
            updates["display"] = str(display)
        updated_pairs = _replace_or_append_query_pairs(pairs, updates)
        urls.append(urlunparse(parsed._replace(query=urlencode(updated_pairs, doseq=True))))
    return urls


# Naver News API에서 검색 결과 item 목록을 가져온다.
def fetch_naver_news_api_items(
    api_url: str,
    timeout: float = 30.0,
    *,
    page_limit: int = DEFAULT_PAGE_LIMIT,
    item_limit: int | None = None,
) -> tuple[list[dict[str, Any]], str]:
    _validate_naver_api_url(api_url)
    api_session = requests.Session()
    api_session.trust_env = False
    api_session.headers.update(_headers())
    discovered: list[dict[str, Any]] = []
    final_url = api_url
    display = item_limit if item_limit is not None else None

    for page_url in build_naver_news_search_page_urls(api_url, page_limit=max(1, page_limit), display=display):
        _validate_naver_api_url(page_url)
        response = api_session.get(page_url, timeout=timeout)
        response.raise_for_status()
        final_url = response.url
        discovered.extend(
            parse_naver_news_api_items(
                response.content,
                base_url=response.url,
                content_type=response.headers.get("Content-Type", ""),
            )
        )

    deduped: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for item in discovered:
        post_id = str(item.get("post_id") or item.get("detail_url") or item.get("link") or "").strip()
        if post_id and post_id in seen_keys:
            continue
        if post_id:
            seen_keys.add(post_id)
        deduped.append(item)
        if item_limit is not None and len(deduped) >= item_limit:
            break

    return deduped, final_url


# Naver news API item 목록을 파싱한다.
def parse_naver_news_api_items(xml_or_json_bytes: bytes, *, base_url: str = "", content_type: str = "") -> list[dict[str, Any]]:
    payload = xml_or_json_bytes.strip()
    if not payload:
        return []

    if _looks_like_json(content_type, payload):
        return _parse_json_items(payload)
    return _parse_xml_items(payload, base_url=base_url)


# Naver API item 목록을 item별 JSON 파일로 저장한다.
def save_naver_news_api_items(
    output_dir: Path,
    *,
    search_term: str | None,
    api_url: str,
    final_url: str,
    items: list[dict[str, Any]],
    file_name: str = "naver_news_api.json",
    filter_terms: list[str] | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    date_label, time_label = _korean_timestamp_labels()
    items_dir = output_dir / "items" / date_label
    items_dir.mkdir(parents=True, exist_ok=True)

    item_files: list[str] = []
    for index, item in enumerate(items, start=1):
        item_name = _batch_item_file_name("NAVER", date_label, time_label, index)
        item_path = items_dir / item_name
        item_payload = dict(item)
        item_payload.setdefault("search_term", search_term)
        item_payload.setdefault("item_index", index)
        item_payload.setdefault("source_provider", "naver_news_api")
        item_payload.setdefault("api_url", api_url)
        item_payload.setdefault("final_url", final_url)
        item_path.write_text(json.dumps(item_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        item_files.append(f"items/{date_label}/{item_name}")

    payload = {
        "search_term": search_term,
        "api_url": api_url,
        "final_url": final_url,
        "item_count": len(items),
        "filter_terms": filter_terms or [],
        "item_files": item_files,
        "source_provider": "naver_news_api",
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
    client_id = os.environ.get(NAVER_CLIENT_ID_ENV, "").strip()
    client_secret = os.environ.get(NAVER_CLIENT_SECRET_ENV, "").strip()
    if not client_id or not client_secret:
        raise ValueError(
            "NAVER_CLIENT_ID and NAVER_CLIENT_SECRET must be set in the environment to call the Naver News API."
        )

    return {
        "User-Agent": USER_AGENT,
        "Accept": "application/json,application/xml,text/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.6",
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }


# Naver API URL의 유효성을 검증한다.
def _validate_naver_api_url(api_url: str) -> None:
    parsed = urlparse(api_url)
    if parsed.scheme != "https" or parsed.netloc.lower() != NAVER_API_HOST:
        raise ValueError("Naver News API URL must use https://openapi.naver.com.")


# display count를 실제 실행 값으로 해석한다.
def _resolve_display_count(raw_display: str | None, *, override: int | None = None) -> int:
    raw_value = override if override is not None else raw_display
    try:
        value = int(raw_value) if raw_value is not None else 10
    except (TypeError, ValueError):
        value = 10
    return max(1, min(NAVER_DISPLAY_MAX, value))


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


# 응답 payload가 JSON 형식인지 판정한다.
def _looks_like_json(content_type: str, payload: bytes) -> bool:
    lowered = content_type.lower()
    if "json" in lowered:
        return True
    return payload[:1] in {b"{", b"["}


# json item 목록을 파싱한다.
def _parse_json_items(payload: bytes) -> list[dict[str, Any]]:
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Failed to parse Naver News API JSON: {exc}") from exc

    items_data = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items_data, list):
        return []

    items: list[dict[str, Any]] = []
    for raw_item in items_data:
        if not isinstance(raw_item, dict):
            continue
        items.append(_normalize_item(raw_item))

    items.sort(key=_naver_news_item_sort_key)
    return items


# xml item 목록을 파싱한다.
def _parse_xml_items(payload: bytes, *, base_url: str = "") -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ValueError(f"Failed to parse Naver News API XML: {exc}") from exc

    items: list[dict[str, Any]] = []
    for item in _iter_elements_by_local_name(root, "item"):
        raw_item = {
            "title": _child_text(item, "title"),
            "originallink": _child_text(item, "originallink"),
            "link": _child_text(item, "link"),
            "description": _child_text(item, "description"),
            "pubDate": _child_text(item, "pubDate"),
        }
        normalized = _normalize_item(raw_item, base_url=base_url)
        items.append(normalized)

    items.sort(key=_naver_news_item_sort_key)
    return items


# item을 표준 형태로 정규화한다.
def _normalize_item(item: dict[str, Any], *, base_url: str = "") -> dict[str, Any]:
    title = _clean_text(str(item.get("title") or ""))
    originallink = _clean_text(str(item.get("originallink") or ""))
    link = _clean_text(str(item.get("link") or ""))
    description = _clean_text(str(item.get("description") or ""))
    pub_date = _clean_text(str(item.get("pubDate") or ""))

    detail_url = urljoin(base_url or link or originallink, link or originallink) if (link or originallink) else ""
    post_id = detail_url or originallink or link or title
    return {
        "post_id": post_id,
        "title": title,
        "detail_url": detail_url,
        "link": detail_url,
        "originallink": originallink,
        "pubDate": pub_date,
        "description": description,
    }


# XML에서 지정 local name의 element를 순회한다.
def _iter_elements_by_local_name(root: ET.Element, local_name: str) -> list[ET.Element]:
    matches: list[ET.Element] = []
    for element in root.iter():
        if _local_name(element.tag) == local_name:
            matches.append(element)
    return matches


# 자식 텍스트 값을 계산해 반환한다.
def _child_text(element: ET.Element, local_name: str) -> str:
    child = _find_child(element, local_name)
    if child is None:
        return ""
    return _clean_text("".join(child.itertext()))


# 지정 local name을 가진 자식 element를 찾는다.
def _find_child(element: ET.Element, local_name: str) -> ET.Element | None:
    for child in list(element):
        if _local_name(child.tag) == local_name:
            return child
    return None


# XML/HTML tag의 local name을 반환한다.
def _local_name(tag: Any) -> str:
    if not isinstance(tag, str):
        return ""
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


# 텍스트를 정리한다.
def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", value))).strip()


# Naver news item sort key 값을 계산해 반환한다.
def _naver_news_item_sort_key(item: dict[str, Any]) -> float:
    pub_date = str(item.get("pubDate") or "").strip()
    if not pub_date:
        return float("inf")

    try:
        dt = parsedate_to_datetime(pub_date)
    except (TypeError, ValueError, IndexError):
        return float("inf")

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    try:
        return -dt.timestamp()
    except (OverflowError, OSError, ValueError):
        return float("inf")
