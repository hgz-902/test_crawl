from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET
import json
import os
import re
import time

import requests

from crawler_app.article_body_extractor import enrich_items_with_article_body


GOOGLE_NEWS_RSS_ATTR = "google"
GOOGLE_NEWS_RSS_ALLOWED_HOST = "news.google.com"
KST = timezone(timedelta(hours=9))
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)


# Google News RSS 피드에서 item 목록을 가져온다.
def fetch_google_news_rss_items(rss_url: str, timeout: float = 30.0) -> tuple[list[dict[str, Any]], str]:
    validate_google_news_rss_url(rss_url)
    session = requests.Session()
    session.trust_env = False
    session.headers.update(_headers())
    retries = max(_int_env("GOOGLE_NEWS_RSS_RETRIES", 5), 1)
    base_sleep = max(_float_env("GOOGLE_NEWS_RSS_BACKOFF_SECONDS", 1.0), 0.0)
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = session.get(rss_url, timeout=timeout, allow_redirects=False)
            break
        except requests.RequestException as exc:
            last_exc = exc
            if attempt >= retries:
                raise
            time.sleep(min(base_sleep * attempt, 8.0))
    else:
        if last_exc:
            raise last_exc
        raise RuntimeError("Google News RSS request failed without exception.")
    if response.is_redirect:
        raise ValueError("Google News RSS redirects are not followed.")
    response.raise_for_status()
    items = parse_google_news_rss_items(response.content, base_url=response.url)
    return items, response.url


# Google news RSS URL의 유효성을 검증한다.
def validate_google_news_rss_url(rss_url: str) -> None:
    parsed = urlparse(str(rss_url or "").strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme.lower() != "https" or host != GOOGLE_NEWS_RSS_ALLOWED_HOST:
        raise ValueError("Google News RSS parser only supports https://news.google.com RSS URLs.")


# Google news RSS item 목록을 파싱한다.
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
        description = _child_html_text(item, "description")
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


# Google RSS item 목록을 item별 JSON 파일로 저장한다.
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
    enrich_items_with_article_body(
        items,
        platform="google",
        timeout=30.0,
        url_selector=lambda item: str(item.get("detail_url") or item.get("link") or ""),
    )
    date_label, time_label = _korean_timestamp_labels()
    items_dir = output_dir / "items" / date_label
    items_dir.mkdir(parents=True, exist_ok=True)

    item_files: list[str] = []
    for index, item in enumerate(items, start=1):
        item_name = _batch_item_file_name("GOOGLE", date_label, time_label, index)
        item_path = items_dir / item_name
        item_payload = dict(item)
        item_payload.setdefault("search_term", search_term)
        item_payload.setdefault("item_index", index)
        item_payload.setdefault("source_provider", "google_news_rss")
        item_payload.setdefault("rss_url", rss_url)
        item_payload.setdefault("final_url", final_url)
        item_path.write_text(json.dumps(item_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        item_files.append(f"items/{date_label}/{item_name}")

    payload = {
        "search_term": search_term,
        "rss_url": rss_url,
        "final_url": final_url,
        "item_count": len(items),
        "filter_terms": filter_terms or [],
        "item_files": item_files,
        "source_provider": "google_news_rss",
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
    return {
        "User-Agent": USER_AGENT,
        "Accept": "application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.6",
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


# 자식 HTML 텍스트 값을 계산해 반환한다.
def _child_html_text(element: ET.Element, local_name: str) -> str:
    child = _find_child(element, local_name)
    if child is None:
        return ""
    return _clean_html_text("".join(child.itertext()))


# 자식 element의 attribute 값을 읽는다.
def _child_attr(element: ET.Element, local_name: str, attr_name: str) -> str:
    child = _find_child(element, local_name)
    if child is None:
        return ""
    return _clean_text(child.attrib.get(attr_name, ""))


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
    return re.sub(r"\s+", " ", value).strip()


# HTML 텍스트를 정리한다.
def _clean_html_text(value: str) -> str:
    decoded = unescape(value)
    without_source_label = re.sub(r"<font\b[^>]*>.*?</font>", " ", decoded, flags=re.IGNORECASE | re.DOTALL)
    without_tags = re.sub(r"<[^>]+>", " ", without_source_label)
    return _clean_text(unescape(without_tags))


# Google news RSS item sort key 값을 계산해 반환한다.
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


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, ""))
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, ""))
    except ValueError:
        return default
