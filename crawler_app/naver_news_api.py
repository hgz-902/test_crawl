from __future__ import annotations

from datetime import timezone
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


def build_naver_news_search_page_urls(api_url: str, *, page_limit: int = DEFAULT_PAGE_LIMIT) -> list[str]:
    if page_limit <= 1:
        return [api_url]

    parsed = urlparse(api_url)
    pairs = parse_qsl(parsed.query, keep_blank_values=True)

    query_map = dict(pairs)
    start_raw = query_map.get("start", "1")
    display_raw = query_map.get("display", "10")
    try:
        start = int(start_raw)
    except ValueError:
        start = 1
    try:
        display = int(display_raw)
    except ValueError:
        display = 10

    start = max(1, start)
    display = max(1, display)
    urls: list[str] = []
    for index in range(page_limit):
        page_start = start + (index * display)
        updated_pairs = [(key, str(page_start) if key == "start" else value) for key, value in pairs]
        if "start" not in query_map:
            updated_pairs.append(("start", str(page_start)))
        urls.append(urlunparse(parsed._replace(query=urlencode(updated_pairs, doseq=True))))
    return urls


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

    for page_url in build_naver_news_search_page_urls(api_url, page_limit=max(1, page_limit)):
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


def parse_naver_news_api_items(xml_or_json_bytes: bytes, *, base_url: str = "", content_type: str = "") -> list[dict[str, Any]]:
    payload = xml_or_json_bytes.strip()
    if not payload:
        return []

    if _looks_like_json(content_type, payload):
        return _parse_json_items(payload)
    return _parse_xml_items(payload, base_url=base_url)


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
    items_dir = output_dir / "items"
    items_dir.mkdir(parents=True, exist_ok=True)

    item_files: list[str] = []
    for index, item in enumerate(items, start=1):
        item_name = f"item_{index:04d}.json"
        item_path = items_dir / item_name
        item_path.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
        item_files.append(str(item_path))

    payload = {
        "search_term": search_term,
        "api_url": api_url,
        "final_url": final_url,
        "item_count": len(items),
        "filter_terms": filter_terms or [],
        "item_files": item_files,
    }
    output_path = output_dir / file_name
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path




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


def _validate_naver_api_url(api_url: str) -> None:
    parsed = urlparse(api_url)
    if parsed.scheme != "https" or parsed.netloc.lower() != NAVER_API_HOST:
        raise ValueError("Naver News API URL must use https://openapi.naver.com.")


def _looks_like_json(content_type: str, payload: bytes) -> bool:
    lowered = content_type.lower()
    if "json" in lowered:
        return True
    return payload[:1] in {b"{", b"["}


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


def _iter_elements_by_local_name(root: ET.Element, local_name: str) -> list[ET.Element]:
    matches: list[ET.Element] = []
    for element in root.iter():
        if _local_name(element.tag) == local_name:
            matches.append(element)
    return matches


def _child_text(element: ET.Element, local_name: str) -> str:
    child = _find_child(element, local_name)
    if child is None:
        return ""
    return _clean_text("".join(child.itertext()))


def _find_child(element: ET.Element, local_name: str) -> ET.Element | None:
    for child in list(element):
        if _local_name(child.tag) == local_name:
            return child
    return None


def _local_name(tag: Any) -> str:
    if not isinstance(tag, str):
        return ""
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", value))).strip()


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
