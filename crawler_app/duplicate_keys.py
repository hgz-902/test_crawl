from __future__ import annotations

import logging
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


LOGGER = logging.getLogger(__name__)
def duplicate_key_for_record(record: dict[str, Any]) -> str:
    url = normalize_duplicate_url(_record_url_field(record, "final_url"))
    if not url:
        LOGGER.debug(
            "Workflow duplicate key skipped because final_url is missing: record_key=%s output_file=%s",
            record.get("record_key") or "-",
            record.get("output_file") or "-",
        )
    return url


def duplicate_keys_for_record(record: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    primary_key = duplicate_key_for_record(record)
    if primary_key:
        keys.append(primary_key)
    return keys


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


def _remove_query_params(query: str, names_to_remove: set[str]) -> str:
    kept = [
        (name, value)
        for name, value in parse_qsl(query, keep_blank_values=True)
        if name.casefold() not in names_to_remove
    ]
    return urlencode(kept, doseq=True)


def _record_extracts(record: dict[str, Any]) -> dict[str, Any]:
    extracts = record.get("extracts")
    return extracts if isinstance(extracts, dict) else {}


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
