from __future__ import annotations

from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from xml.etree import ElementTree as ET
import json
import re

import requests


GOOGLE_NEWS_RSS_ATTR = "google"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)


def fetch_google_news_rss_items(rss_url: str, timeout: float = 30.0) -> tuple[list[dict[str, Any]], str]:
    session = requests.Session()
    session.trust_env = False
    session.headers.update(_headers())
    response = session.get(rss_url, timeout=timeout)
    response.raise_for_status()
    items = parse_google_news_rss_items(response.content, base_url=response.url)
    return items, response.url


def parse_google_news_rss_items(xml_bytes: bytes, *, base_url: str = "") -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ValueError(f"Failed to parse Google News RSS XML: {exc}") from exc

    items: list[dict[str, Any]] = []
    for item in _iter_elements_by_local_name(root, "item"):
        title = _child_text(item, "title")
        link = _child_text(item, "link")
        guid = _child_text(item, "guid")
        pub_date = _child_text(item, "pubDate")
        description = _child_text(item, "description")
        source = _child_text(item, "source")
        source_url = _child_attr(item, "source", "url")

        detail_url = urljoin(base_url or link, link) if link else ""
        post_id = guid or detail_url or link or title
        items.append(
            {
                "post_id": post_id,
                "title": title,
                "detail_url": detail_url,
                "link": detail_url,
                "pubDate": pub_date,
                "source": source,
                "source_url": source_url,
                "description": description,
                "guid": guid,
            }
        )

    items.sort(key=_google_news_rss_item_sort_key)
    return items


def save_google_news_rss_items(
    output_dir: Path,
    *,
    search_term: str | None,
    rss_url: str,
    final_url: str,
    items: list[dict[str, Any]],
    file_name: str = "google_news_rss.json",
    filter_terms: list[str] | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "search_term": search_term,
        "rss_url": rss_url,
        "final_url": final_url,
        "item_count": len(items),
        "filter_terms": filter_terms or [],
        "items": items,
    }
    output_path = output_dir / file_name
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def _headers() -> dict[str, str]:
    return {
        "User-Agent": USER_AGENT,
        "Accept": "application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.6",
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


def _child_attr(element: ET.Element, local_name: str, attr_name: str) -> str:
    child = _find_child(element, local_name)
    if child is None:
        return ""
    return _clean_text(child.attrib.get(attr_name, ""))


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
    return re.sub(r"\s+", " ", value).strip()


def _google_news_rss_item_sort_key(item: dict[str, Any]) -> float:
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
