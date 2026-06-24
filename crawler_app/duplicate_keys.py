from __future__ import annotations

import logging
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


LOGGER = logging.getLogger(__name__)
PARSER_DUPLICATE_MARKERS = {
    "naver",
    "naver_news_api",
    "daum",
    "kakao_daum_web_search",
    "google",
    "google_news_rss",
}
# record의 최종 URL을 정규화해 중복 판정 key를 만든다.
def duplicate_key_for_record(record: dict[str, Any]) -> str:
    url = normalize_duplicate_url(_record_primary_url(record))
    if not url:
        LOGGER.debug(
            "Workflow duplicate key skipped because final_url is missing: record_key=%s output_file=%s",
            record.get("record_key") or "-",
            record.get("output_file") or "-",
        )
    return url


# record에서 사용할 수 있는 중복 판정 key 목록을 만든다.
def duplicate_keys_for_record(record: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    primary_key = duplicate_key_for_record(record)
    if primary_key:
        keys.append(primary_key)
    google_description_key = _google_description_key(record)
    if google_description_key:
        keys.append(google_description_key)
    return keys


# 중복 비교용 URL을 안전하게 정규화한다.
def normalize_duplicate_url(value: str) -> str:
    raw = canonicalize_article_url(value)
    if not raw:
        return ""
    parts = urlsplit(raw)
    if parts.scheme or parts.netloc:
        path = parts.path
        if path != "/":
            path = path.rstrip("/")
        return urlunsplit((parts.scheme.casefold(), parts.netloc.casefold(), path, parts.query, ""))
    return raw.split("#", 1)[0].rstrip("/")


# 기사 URL을 비교 가능한 canonical URL로 정리한다.
def canonicalize_article_url(value: str, page_query_params: Iterable[str] | None = None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    if not (parts.scheme or parts.netloc):
        return raw.split("#", 1)[0].rstrip("/")

    query = parts.query
    if page_query_params and query:
        query = _remove_query_params(query, {str(name).casefold() for name in page_query_params if str(name).strip()})

    path = parts.path
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((parts.scheme.casefold(), parts.netloc.casefold(), path, query, ""))


# 쿼리 params를 제거한다.
def _remove_query_params(query: str, names_to_remove: set[str]) -> str:
    kept = [
        (name, value)
        for name, value in parse_qsl(query, keep_blank_values=True)
        if name.casefold() not in names_to_remove
    ]
    return urlencode(kept, doseq=True)


# record extracts 값을 계산해 반환한다.
def _record_extracts(record: dict[str, Any]) -> dict[str, Any]:
    extracts = record.get("extracts")
    return extracts if isinstance(extracts, dict) else {}


# 중복 판정에 사용할 대표 URL을 반환한다.
def _record_primary_url(record: dict[str, Any]) -> str:
    if _is_parser_record(record):
        for field_name in ("detail_url", "originallink", "link", "url", "final_url"):
            value = _record_url_field(record, field_name)
            if value:
                return value
    return _record_url_field(record, "final_url")


# parser record 여부를 판정한다.
def _is_parser_record(record: dict[str, Any]) -> bool:
    return any(marker.casefold() in PARSER_DUPLICATE_MARKERS for marker in _parser_markers(record))


# Google parser record 여부를 판정한다.
def _is_google_parser_record(record: dict[str, Any]) -> bool:
    return any(marker.casefold() in {"google", "google_news_rss"} for marker in _parser_markers(record))


# Google RSS description 기반 보조 중복 key를 만든다.
def _google_description_key(record: dict[str, Any]) -> str:
    if not _is_google_parser_record(record):
        return ""
    extracts = _record_extracts(record)
    description = _first_text(record.get("description")) or _first_text(extracts.get("description"))
    normalized = " ".join(description.split()).strip().casefold()
    return f"google_description:{normalized}" if normalized else ""


# parser marker 문자열을 반환한다.
def _parser_markers(record: dict[str, Any]) -> list[str]:
    extracts = _record_extracts(record)
    markers = [
        record.get("parser_name"),
        extracts.get("parser_name"),
        extracts.get("source_provider"),
        extracts.get("source_api"),
    ]
    for step in record.get("steps") or []:
        if isinstance(step, dict):
            markers.append(step.get("attr"))
    return [str(marker or "") for marker in markers if str(marker or "").strip()]


# record URL field 값을 계산해 반환한다.
def _record_url_field(record: dict[str, Any], field_name: str) -> str:
    value = _first_text(record.get(field_name))
    if value:
        return value
    extracts = _record_extracts(record)
    value = _first_text(extracts.get(field_name))
    if value:
        return value
    for step in record.get("steps") or []:
        if not isinstance(step, dict):
            continue
        if field_name == "final_url":
            value = _first_text(step.get("url_after"))
        else:
            value = _first_text(step.get(field_name))
        if value:
            return value
    return ""


# first 텍스트 값을 계산해 반환한다.
def _first_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value).strip()
    if isinstance(value, list):
        for item in value:
            text = _first_text(item)
            if text:
                return text
    return ""
