from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlsplit, urlunsplit


LOGGER = logging.getLogger(__name__)
DETAIL_URL_DUPLICATE_PARSERS = {"daum", "google", "naver"}
DETAIL_URL_DUPLICATE_PROVIDERS = {"kakao_daum_web_search", "google_news_rss", "naver_news_api"}
GOOGLE_DUPLICATE_PARSERS = {"google", "google_news_rss"}
GOOGLE_DESCRIPTION_KEY_PREFIX = "google_description:"


def duplicate_key_for_record(record: dict[str, Any]) -> str:
    field_name = "detail_url" if _uses_detail_url_duplicate_key(record) else "final_url"
    url = normalize_duplicate_url(_record_url_field(record, field_name))
    if not url:
        LOGGER.debug(
            "Workflow duplicate key skipped because %s is missing: parser=%s record_key=%s output_file=%s",
            field_name,
            _record_parser_name(record) or "-",
            record.get("record_key") or "-",
            record.get("output_file") or "-",
        )
    return url


def duplicate_keys_for_record(record: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    primary_key = duplicate_key_for_record(record)
    if primary_key:
        keys.append(primary_key)
    secondary_key = google_description_duplicate_key_for_record(record)
    if secondary_key:
        keys.append(secondary_key)
    return keys


def google_description_duplicate_key_for_record(record: dict[str, Any]) -> str:
    if not _is_google_record(record):
        return ""
    description = normalize_duplicate_text(_record_description_field(record))
    if not description:
        LOGGER.debug(
            "Google description duplicate key skipped because description is missing: record_key=%s output_file=%s",
            record.get("record_key") or "-",
            record.get("output_file") or "-",
        )
        return ""
    return f"{GOOGLE_DESCRIPTION_KEY_PREFIX}{description}"


def normalize_duplicate_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    if parts.scheme or parts.netloc:
        path = parts.path
        if path != "/":
            path = path.rstrip("/")
        return urlunsplit((parts.scheme.casefold(), parts.netloc.casefold(), path, parts.query, ""))
    return raw.split("#", 1)[0].rstrip("/")


def normalize_duplicate_text(value: str) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _record_extracts(record: dict[str, Any]) -> dict[str, Any]:
    extracts = record.get("extracts")
    return extracts if isinstance(extracts, dict) else {}


def _record_parser_name(record: dict[str, Any]) -> str:
    extracts = _record_extracts(record)
    candidates: list[Any] = [
        record.get("parser_name"),
        extracts.get("parser_name"),
        extracts.get("source_provider"),
        extracts.get("source_api"),
    ]
    for step in record.get("steps") or []:
        if isinstance(step, dict):
            candidates.append(step.get("attr"))
    for candidate in candidates:
        text = _first_text(candidate).casefold()
        if text:
            return text
    return ""


def _uses_detail_url_duplicate_key(record: dict[str, Any]) -> bool:
    parser_name = _record_parser_name(record)
    return parser_name in DETAIL_URL_DUPLICATE_PARSERS or parser_name in DETAIL_URL_DUPLICATE_PROVIDERS


def _is_google_record(record: dict[str, Any]) -> bool:
    return _record_parser_name(record) in GOOGLE_DUPLICATE_PARSERS


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


def _record_description_field(record: dict[str, Any]) -> str:
    extracts = _record_extracts(record)
    for key in ("description", "desc", "summary"):
        value = _first_text(extracts.get(key))
        if value:
            return value
    for key in ("description", "desc", "summary"):
        value = _first_text(record.get(key))
        if value:
            return value
    return ""


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
