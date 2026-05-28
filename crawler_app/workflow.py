from __future__ import annotations

import asyncio
import base64
import hashlib
import shutil
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from email.header import decode_header
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qsl, quote_plus, unquote, urljoin, urlparse, urlsplit
import json
import re
import sys
import time

from lxml import html as lxml_html
import requests

from crawler_app.daum_news_api import DAUM_NEWS_API_ATTR, fetch_daum_news_api_items, save_daum_news_api_items
from crawler_app.duplicate_keys import canonicalize_article_url, duplicate_keys_for_record, normalize_duplicate_url
from crawler_app.google_news_rss import GOOGLE_NEWS_RSS_ATTR, fetch_google_news_rss_items, save_google_news_rss_items
from crawler_app.naver_news_api import (
    NAVER_NEWS_API_ATTR,
    fetch_naver_news_api_items,
    save_naver_news_api_items,
)


SUPPORTED_ACTIONS = {"click", "goto", "download", "extract", "parser"}
SUPPORTED_LOOP_MODES = {"items", "pagination"}
SUPPORTED_PAGINATION_MODES = {"next_button", "page_number"}
SUPPORTED_OPEN_MODES = {"auto", "same_tab", "popup"}
SUPPORTED_PARSER_ATTRS = {DAUM_NEWS_API_ATTR, GOOGLE_NEWS_RSS_ATTR, NAVER_NEWS_API_ATTR}
SUPPORTED_ATTRS = {"href", "src", "text", "html", *SUPPORTED_PARSER_ATTRS}
STEP_ATTR_ALLOWED_VALUES = {
    "click": set(),
    "goto": {"href", "src"},
    "download": {"href", "src"},
    "extract": {"href", "src", "text", "html"},
    "parser": set(SUPPORTED_PARSER_ATTRS),
}
SUPPORTED_WAIT_STATES = {"attached", "visible", "hidden", "detached"}
DEFAULT_TIMEOUT_MS = 30000
DEFAULT_STEP_WAIT_MS = 10000
BOARD_LOOP_MAX_ITEMS = 1000
MAX_WORKFLOW_RECORD_LINES = 20_000
KST = timezone(timedelta(hours=9))
NUMERIC_SEARCH_TERM_RE = re.compile(r"^\d+$")
BOARD_CONTAINER_CHILD_XPATHS = {
    "ol": ("./li",),
    "tbody": ("./tr",),
    "table": ("./tbody/tr", "./tr"),
    "ul": ("./li",),
}
BOARD_ITEM_SEGMENT_RE = re.compile(r"^(?P<tag>[\w:-]+)\[(?P<index>\d+)\]$")
BOARD_PATH_SEGMENT_RE = re.compile(r"^(?P<tag>[\w:-]+)(?:\[(?P<index>\d+)\])?$")
BOARD_TRAILING_NUMBER_SEGMENT_RE = re.compile(r"^(?P<prefix>.*?)(?P<index>\d+)(?P<suffix>[^0-9]*)$")
ITEM_NUMBER_PLACEHOLDER = "{item_number}"
PARSER_RECORD_DATE_FIELDS = (
    ("extracts", "pubDate"),
    ("extracts", "published_at"),
    ("extracts", "date"),
    ("published_at",),
    ("created_at",),
    ("crawled_at",),
)


@dataclass(slots=True)
class WorkflowExecution:
    config_name: str
    output_dir: Path
    records: list[dict[str, Any]] = field(default_factory=list)
    downloaded_files: list[str] = field(default_factory=list)
    extracted_files: list[str] = field(default_factory=list)
    generated_files: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.error is None and all(record.get("success", False) for record in self.records)


RecordPolicy = Callable[[dict[str, Any]], Any]


class WorkflowRecordPolicyStop(RuntimeError):
    """Raised internally when an optional record policy asks to stop a workflow."""

    def __init__(
        self,
        reason: str = "record_policy_stopped",
        metadata: dict[str, Any] | None = None,
        records: list[dict[str, Any]] | None = None,
        generated_files: list[str] | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.metadata = metadata or {}
        self.records = records or []
        self.generated_files = generated_files or []


@dataclass(slots=True)
class LatestDuplicateIndex:
    normal_by_search: dict[str, set[str]] = field(default_factory=dict)
    numeric_by_filter: dict[str, set[str]] = field(default_factory=dict)
    all_keys: set[str] = field(default_factory=set)

    @property
    def has_records(self) -> bool:
        return bool(self.all_keys)


def _build_record_key(search_term_index: int | None, item_index: int | None) -> str:
    term_number = (search_term_index + 1) if isinstance(search_term_index, int) else 1
    item_label = f"item{item_index + 1:03d}" if isinstance(item_index, int) else "single"
    return f"term{term_number:03d}_{item_label}"


def _build_stable_record_key(config: dict[str, Any], record: dict[str, Any]) -> str:
    prefix = _record_key_prefix(config, record)
    identity = f"{_record_identity_for_key(record)}|{datetime.now(KST).strftime('%Y%m%d')}"
    digest = hashlib.blake2b(identity.encode("utf-8"), digest_size=8).digest()
    token = base64.b32encode(digest).decode("ascii").rstrip("=")
    return f"{prefix}-{token}"


def _record_key_prefix(config: dict[str, Any], record: dict[str, Any]) -> str:
    parser_name = _record_parser_name(record)
    if parser_name in {NAVER_NEWS_API_ATTR, "naver_news_api"}:
        return "NAVER"
    if parser_name in {DAUM_NEWS_API_ATTR, "kakao_daum_web_search"}:
        return "DAUM"
    if parser_name in {GOOGLE_NEWS_RSS_ATTR, "google_news_rss"}:
        return "GOOGLE"
    output_name = Path(str(config.get("output_dir") or config.get("name") or "crawler")).name
    normalized = re.sub(r"[^A-Za-z0-9]+", "", output_name).upper()
    return (normalized or "CRAWLER")[:12]


def _record_identity_for_key(record: dict[str, Any]) -> str:
    for key in duplicate_keys_for_record(record):
        normalized = normalize_duplicate_url(key)
        if normalized:
            return normalized
    extracts = record.get("extracts") if isinstance(record.get("extracts"), dict) else {}
    candidates = [
        record.get("final_url"),
        extracts.get("detail_url"),
        extracts.get("originallink"),
        extracts.get("link"),
        extracts.get("extract_title"),
        extracts.get("title"),
        record.get("start_url"),
    ]
    for candidate in candidates:
        text = str(candidate or "").strip()
        if text:
            return normalize_duplicate_url(text) or text
    return json.dumps(record, ensure_ascii=False, sort_keys=True)


def _record_parser_name(record: dict[str, Any]) -> str:
    extracts = record.get("extracts") if isinstance(record.get("extracts"), dict) else {}
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
        text = str(candidate or "").strip().casefold()
        if text:
            return text
    return ""


def _build_artifact_prefix(record_key: str, step_index: int, step_name: str) -> str:
    return safe_name(f"{record_key}_step{step_index:02d}_{step_name}")


def _record_output_path(output_dir: Path, record_key: str, step_index: int, step_name: str, file_name: str) -> Path:
    prefix = _build_artifact_prefix(record_key, step_index, step_name)
    return output_dir / safe_name(f"{prefix}_{file_name}")


def _result_category_root(output_dir: Path, category: str) -> Path:
    return output_dir / category


def _relocate_path(path: str, source_root: Path, target_root: Path) -> str:
    source_path = Path(path)
    try:
        relative_path = source_path.relative_to(source_root)
    except ValueError:
        return str(source_path)

    target_path = target_root / relative_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if source_path.exists() and source_path.resolve() != target_path.resolve():
        source_path.replace(target_path)
    return str(target_path)


def _relocate_record_file_lists(
    records: list[dict[str, Any]],
    source_root: Path,
    target_root: Path,
) -> None:
    for record in records:
        if not isinstance(record, dict):
            continue
        if record.get("output_file"):
            record["output_file"] = _relocate_path(str(record["output_file"]), source_root, target_root)

        for key in ("downloaded_files", "extracted_files"):
            raw_values = record.get(key)
            if isinstance(raw_values, str):
                raw_values = [raw_values]
            if not isinstance(raw_values, list):
                continue
            record[key] = [
                _relocate_path(str(value), source_root, target_root)
                for value in raw_values
                if str(value).strip()
            ]

        steps = record.get("steps")
        if not isinstance(steps, list):
            continue
        for step in steps:
            if not isinstance(step, dict):
                continue
            for key in ("downloaded_file", "extracted_file"):
                if step.get(key):
                    step[key] = _relocate_path(str(step[key]), source_root, target_root)
            for key in ("downloaded_files", "extracted_files"):
                raw_values = step.get(key)
                if isinstance(raw_values, str):
                    raw_values = [raw_values]
                if not isinstance(raw_values, list):
                    continue
                step[key] = [
                    _relocate_path(str(value), source_root, target_root)
                    for value in raw_values
                    if str(value).strip()
                ]


def _cleanup_empty_dirs(root: Path, protected_roots: list[Path] | tuple[Path, ...] = ()) -> None:
    protected = tuple(protected_roots)
    for path in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if any(path == protected_root or protected_root in path.parents for protected_root in protected):
            continue
        try:
            if not any(path.iterdir()):
                path.rmdir()
        except FileNotFoundError:
            continue
        except OSError:
            continue


@dataclass(slots=True)
class BoardRepeatSpec:
    item_xpath: str | None
    item_tag: str | None


@dataclass(slots=True)
class BoardLoopSpec:
    anchor_xpath_1: str
    anchor_xpath_2: str
    root_xpath: str
    item_segment_template: str
    item_tag: str | None
    suffix_segments: tuple[str, ...]
    start_index: int

    def render_item_segment(self, item_number: int) -> str:
        return self.item_segment_template.replace(ITEM_NUMBER_PLACEHOLDER, str(item_number))

    def render_anchor_xpath(self, item_number: int) -> str:
        return _join_xpath(self.root_xpath, [self.render_item_segment(item_number)] + list(self.suffix_segments))

    def render_item_root_xpath(self, item_number: int) -> str:
        return _join_xpath(self.root_xpath, [self.render_item_segment(item_number)])


@dataclass(slots=True)
class PaginationLoopSpec:
    pagination_mode: str
    xpath: str
    start_page: int = 1

    def render_xpath(self, page_number: int) -> str:
        if self.pagination_mode == "page_number":
            return self.xpath.replace("{page_number}", str(page_number))
        return self.xpath


class WorkflowConfigError(ValueError):
    """Raised when an XPath workflow config is invalid."""


def load_workflow_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise WorkflowConfigError(f"Failed to read config file: {config_path} ({exc})") from exc
    except json.JSONDecodeError as exc:
        raise WorkflowConfigError(f"Invalid JSON config: {config_path} ({exc})") from exc

    config = normalize_workflow_config(config)
    validate_workflow_config(config)
    return config


def normalize_workflow_config(config: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(config)
    steps = normalized.get("steps")
    if not isinstance(steps, list):
        return normalized

    for step in steps:
        if not isinstance(step, dict):
            continue

        action = str(step.get("action") or "").strip().lower()
        if action:
            step["action"] = action

        if "open_mode" in step and step.get("open_mode") not in (None, ""):
            step["open_mode"] = str(step["open_mode"]).strip().lower()

        if "attr" in step and step.get("attr") not in (None, ""):
            step["attr"] = str(step["attr"]).strip().lower()

        if "loop_mode" in step and step.get("loop_mode") not in (None, ""):
            step["loop_mode"] = str(step["loop_mode"]).strip().lower()

        if "pagination_mode" in step and step.get("pagination_mode") not in (None, ""):
            pagination_mode = str(step["pagination_mode"]).strip().lower()
            if pagination_mode == "submit_form":
                pagination_mode = "page_number"
            step["pagination_mode"] = pagination_mode

        if action == "click" and str(step.get("open_mode") or "").strip().lower() == "goto":
            step["action"] = "goto"
            step.pop("open_mode", None)
            if not str(step.get("attr") or "").strip():
                step["attr"] = "href"
            continue

        if action != "click":
            step.pop("open_mode", None)

        if action == "click":
            step.pop("attr", None)
        elif action == "goto":
            step.pop("open_mode", None)
            if not str(step.get("attr") or "").strip():
                step["attr"] = "href"
        elif action in {"download", "extract"}:
            step.pop("open_mode", None)
        elif action == "parser":
            step.pop("xpath", None)
            step.pop("xpath_2", None)
            step.pop("exclude_xpath", None)
            step.pop("loop_mode", None)
            step.pop("pagination_mode", None)
            step.pop("value", None)
            step.pop("open_mode", None)
            step.pop("wait_state", None)
            step.pop("loop", None)
            if not str(step.get("attr") or "").strip():
                step["attr"] = _infer_parser_attr_from_start_url(str(normalized.get("start_url") or "")) or GOOGLE_NEWS_RSS_ATTR

    return normalized


def validate_workflow_config(config: dict[str, Any]) -> None:
    for key in ("name", "start_url", "output_dir", "steps"):
        if not config.get(key):
            raise WorkflowConfigError(f"Missing required config key: {key}")

    if config.get("renderer", "playwright") != "playwright":
        raise WorkflowConfigError("Only renderer='playwright' is supported.")

    parse_pause_seconds = config.get("parse_pause_seconds")
    if parse_pause_seconds not in (None, ""):
        try:
            parsed_pause = int(parse_pause_seconds)
        except (TypeError, ValueError) as exc:
            raise WorkflowConfigError("parse_pause_seconds must be a non-negative integer.") from exc
        if parsed_pause < 0:
            raise WorkflowConfigError("parse_pause_seconds must be a non-negative integer.")

    timeout_ms = config.get("timeout_ms")
    if timeout_ms not in (None, ""):
        try:
            parsed_timeout_ms = int(timeout_ms)
        except (TypeError, ValueError) as exc:
            raise WorkflowConfigError("timeout_ms must be a non-negative integer.") from exc
        if parsed_timeout_ms < 0:
            raise WorkflowConfigError("timeout_ms must be a non-negative integer.")

    step_wait_ms = config.get("step_wait_ms")
    if step_wait_ms not in (None, ""):
        try:
            parsed_step_wait_ms = int(step_wait_ms)
        except (TypeError, ValueError) as exc:
            raise WorkflowConfigError("step_wait_ms must be a non-negative integer.") from exc
        if parsed_step_wait_ms < 0:
            raise WorkflowConfigError("step_wait_ms must be a non-negative integer.")

    search_terms = config.get("search_terms")
    if search_terms not in (None, ""):
        if not isinstance(search_terms, list):
            raise WorkflowConfigError("search_terms must be a list of strings.")
        for index, term in enumerate(search_terms, start=1):
            if term is None:
                continue
            if not isinstance(term, str):
                raise WorkflowConfigError(f"search_terms[{index}] must be a string.")

    filter_terms = config.get("filter_terms")
    if filter_terms not in (None, ""):
        if not isinstance(filter_terms, list):
            raise WorkflowConfigError("filter_terms must be a list of strings.")
        for index, term in enumerate(filter_terms, start=1):
            if term is None:
                continue
            if not isinstance(term, str):
                raise WorkflowConfigError(f"filter_terms[{index}] must be a string.")

    board = config.get("board") or {}
    if board.get("enabled"):
        list_xpath = str(board.get("list_xpath") or "").strip()
        loop_anchor_1 = str(board.get("loop_anchor_xpath_1") or "").strip()
        loop_anchor_2 = str(board.get("loop_anchor_xpath_2") or "").strip()
        if not list_xpath and not (loop_anchor_1 and loop_anchor_2):
            raise WorkflowConfigError("board.list_xpath is required when board.enabled=true.")
        if int(board.get("limit") or 0) <= 0:
            raise WorkflowConfigError("board.limit must be greater than 0.")
        if bool(loop_anchor_1) ^ bool(loop_anchor_2):
            raise WorkflowConfigError("board.loop_anchor_xpath_1 and board.loop_anchor_xpath_2 must be set together.")
        if loop_anchor_1 and loop_anchor_2 and _build_board_loop_spec(loop_anchor_1, loop_anchor_2) is None:
            raise WorkflowConfigError("board.loop_anchor_xpath_1 and board.loop_anchor_xpath_2 must define one repeating index.")
        item_tag = str(board.get("item_tag") or "").strip()
        item_xpath = str(board.get("item_xpath") or "").strip()
        if item_tag and item_xpath:
            inferred_tag = _xpath_last_segment_tag(item_xpath)
            if inferred_tag and inferred_tag != item_tag:
                raise WorkflowConfigError("board.item_tag must match the last tag in board.item_xpath.")

    steps = config.get("steps")
    if not isinstance(steps, list) or not steps:
        raise WorkflowConfigError("steps must contain at least one step.")

    parser_name = _config_parser_name(config)
    if parser_name is not None and len(steps) != 1:
        raise WorkflowConfigError("steps must contain exactly one step when action=parser.")

    primary_loop_step_index = _config_primary_loop_step_index(config)
    click_loop_step_indexes = _config_click_loop_step_indexes(config)
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise WorkflowConfigError(f"steps[{index}] must be an object.")
        action = step.get("action")
        if action not in SUPPORTED_ACTIONS:
            raise WorkflowConfigError(f"steps[{index}].action must be one of {sorted(SUPPORTED_ACTIONS)}.")
        if action == "parser":
            attr = str(step.get("attr") or "").strip().lower()
            if attr not in SUPPORTED_PARSER_ATTRS:
                raise WorkflowConfigError(f"steps[{index}].attr must be one of {sorted(STEP_ATTR_ALLOWED_VALUES['parser'])}.")
            if str(step.get("xpath") or "").strip():
                raise WorkflowConfigError(f"steps[{index}].xpath is not supported for parser.")
            if str(step.get("xpath_2") or "").strip():
                raise WorkflowConfigError(f"steps[{index}].xpath_2 is not supported for parser.")
            if str(step.get("exclude_xpath") or "").strip():
                raise WorkflowConfigError(f"steps[{index}].exclude_xpath is not supported for parser.")
            if str(step.get("value") or "").strip():
                raise WorkflowConfigError(f"steps[{index}].value is not supported for parser.")
            if str(step.get("open_mode") or "").strip():
                raise WorkflowConfigError(f"steps[{index}].open_mode is not supported for parser.")
            if str(step.get("wait_state") or "").strip():
                raise WorkflowConfigError(f"steps[{index}].wait_state is not supported for parser.")
            if step.get("loop"):
                raise WorkflowConfigError(f"steps[{index}].loop is not supported for parser.")
            loop_limit = step.get("loop_limit")
            if loop_limit not in (None, ""):
                try:
                    parsed_limit = int(loop_limit)
                except (TypeError, ValueError) as exc:
                    raise WorkflowConfigError(f"steps[{index}].loop_limit must be a non-negative integer.") from exc
                if parsed_limit < 0:
                    raise WorkflowConfigError(f"steps[{index}].loop_limit must be a non-negative integer.")
            continue
        if not step.get("xpath"):
            raise WorkflowConfigError(f"steps[{index}].xpath is required.")
        open_mode = step.get("open_mode")
        if open_mode not in (None, ""):
            open_mode_value = str(open_mode).strip().lower()
            if action != "click":
                raise WorkflowConfigError(f"steps[{index}].open_mode is only supported for click.")
            if open_mode_value not in SUPPORTED_OPEN_MODES:
                raise WorkflowConfigError(f"steps[{index}].open_mode must be one of {sorted(SUPPORTED_OPEN_MODES)}.")
        attr = str(step.get("attr") or "").strip().lower()
        if attr and attr not in SUPPORTED_ATTRS:
            raise WorkflowConfigError(f"steps[{index}].attr must be one of {sorted(SUPPORTED_ATTRS)}.")
        allowed_attrs = STEP_ATTR_ALLOWED_VALUES.get(str(action), set())
        if action == "click":
            if attr:
                raise WorkflowConfigError(f"steps[{index}].attr is not supported for click.")
        elif action == "goto":
            if attr and attr not in allowed_attrs:
                raise WorkflowConfigError(f"steps[{index}].attr must be one of {sorted(allowed_attrs)}.")
        elif action in {"download", "extract"}:
            if attr and attr not in allowed_attrs:
                raise WorkflowConfigError(f"steps[{index}].attr must be one of {sorted(allowed_attrs)}.")
        loop_mode = _step_loop_mode(step)
        if step.get("loop"):
            if loop_mode == "pagination":
                if index != 1:
                    raise WorkflowConfigError("steps[2:] loop_mode=pagination is only supported for the first step.")
                pagination_mode = str(step.get("pagination_mode") or "").strip().lower()
                if not pagination_mode:
                    raise WorkflowConfigError(f"steps[{index}].pagination_mode is required when loop_mode=pagination.")
                if pagination_mode not in SUPPORTED_PAGINATION_MODES:
                    raise WorkflowConfigError(
                        f"steps[{index}].pagination_mode must be one of {sorted(SUPPORTED_PAGINATION_MODES)}."
                    )
                if not str(step.get("xpath") or "").strip():
                    raise WorkflowConfigError(f"steps[{index}].xpath is required when loop_mode=pagination.")
                if pagination_mode == "page_number" and "{page_number}" not in str(step.get("xpath") or ""):
                    raise WorkflowConfigError(
                        f"steps[{index}].xpath must include {{page_number}} when pagination_mode=page_number."
                    )
                if action != "click":
                    raise WorkflowConfigError(f"steps[{index}].loop is only supported for click when loop_mode=pagination.")
            else:
                if not step.get("xpath_2"):
                    raise WorkflowConfigError(f"steps[{index}].xpath_2 is required when loop=true.")
                if _build_board_loop_spec(str(step.get("xpath") or ""), str(step.get("xpath_2") or "")) is None:
                    raise WorkflowConfigError(f"steps[{index}] loop anchors must define one repeating index.")
                if action == "click":
                    if index not in click_loop_step_indexes:
                        raise WorkflowConfigError(f"steps[{index}].loop is only supported for click in steps 1 and 2.")
                elif action not in {"download", "extract"}:
                    raise WorkflowConfigError(f"steps[{index}].loop is only supported for click, download, or extract.")
        loop_limit = step.get("loop_limit")
        if loop_limit not in (None, ""):
            try:
                parsed_limit = int(loop_limit)
            except (TypeError, ValueError) as exc:
                raise WorkflowConfigError(f"steps[{index}].loop_limit must be a non-negative integer.") from exc
            if parsed_limit < 0:
                raise WorkflowConfigError(f"steps[{index}].loop_limit must be a non-negative integer.")
        wait_state = step.get("wait_state")
        if wait_state and wait_state not in SUPPORTED_WAIT_STATES:
            raise WorkflowConfigError(
                f"steps[{index}].wait_state must be one of {sorted(SUPPORTED_WAIT_STATES)}."
            )


def preview_workflow_config(config: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    config = normalize_workflow_config(config)
    validate_workflow_config(config)
    parser_name = _config_parser_name(config)
    if parser_name is not None:
        return _preview_parser_workflow(config, parser_name, timeout)
    session = requests.Session()
    session.trust_env = False
    session.headers.update(_headers())
    response = session.get(str(config["start_url"]), timeout=timeout)
    response.raise_for_status()
    root = lxml_html.fromstring(response.text)

    search_terms = _config_search_terms(config)
    board = config.get("board") or {}
    first_step_xpath = str((config.get("steps") or [{}])[0].get("xpath") or "") if config.get("steps") else ""
    loop_spec = _config_primary_loop_spec(config)
    pagination_spec = _config_primary_pagination_spec(config)
    legacy_board_enabled = bool(board.get("enabled"))
    board_enabled = bool(loop_spec or pagination_spec or legacy_board_enabled)
    configured_repeat = bool(
        str(board.get("loop_anchor_xpath_1") or "").strip()
        and str(board.get("loop_anchor_xpath_2") or "").strip()
    ) or bool(str(board.get("item_tag") or "").strip() or str(board.get("item_xpath") or "").strip())
    list_matches = root.xpath(str(board.get("list_xpath") or "")) if legacy_board_enabled and not loop_spec else []
    board_repeat_spec = _build_board_repeat_spec(
        str(board.get("list_xpath") or ""),
        str(board.get("item_tag") or ""),
        str(board.get("item_xpath") or ""),
        first_step_xpath,
    )
    if pagination_spec is not None:
        board_items = [1]
        if pagination_spec.pagination_mode == "page_number":
            board_items = [1]
            for page_number in range(2, BOARD_LOOP_MAX_ITEMS + 1):
                if not root.xpath(pagination_spec.render_xpath(page_number)):
                    break
                board_items.append(page_number)
    elif loop_spec is not None:
        loop_steps = config.get("steps") or []
        primary_loop_step = next((step for step in loop_steps if isinstance(step, dict) and step.get("loop") and _step_loop_mode(step) == "items"), None)
        exclude_xpath = str(primary_loop_step.get("exclude_xpath") or "").strip() if isinstance(primary_loop_step, dict) else ""
        board_items = _preview_board_loop_items(root, loop_spec, exclude_xpath=exclude_xpath)
    else:
        board_items, board_repeat_spec = _preview_board_items(
            root,
            list_matches,
            str(board.get("list_xpath") or ""),
            board_repeat_spec,
            first_step_xpath,
            configured_repeat,
        )

    step_counts: list[dict[str, Any]] = []
    for index, step in enumerate(config["steps"], start=1):
        xpath = str(step["xpath"])
        if step.get("loop") and _step_loop_mode(step) == "items" and step.get("xpath_2"):
            step_loop_spec = _build_board_loop_spec(xpath, str(step.get("xpath_2") or ""))
            exclude_xpath = str(step.get("exclude_xpath") or "").strip()
            count = len(_preview_board_loop_items(root, step_loop_spec, exclude_xpath=exclude_xpath)) if step_loop_spec else 0
            loop_limit = _step_loop_limit(step)
            if loop_limit is not None:
                count = min(count, loop_limit)
            error = None if step_loop_spec else "Invalid loop anchors."
            step_counts.append(
                {
                    "name": step.get("name") or "",
                    "xpath": xpath,
                    "action": step["action"],
                    "wait_state": step.get("wait_state") or "auto",
                    "loop_limit": loop_limit,
                    "loop_mode": _step_loop_mode(step),
                    "count": count,
                    "error": error,
                }
            )
            continue
        if step.get("loop") and _step_loop_mode(step) == "pagination":
            loop_limit = _step_loop_limit(step)
            count = len(board_items) if board_items else 0
            if loop_limit is not None:
                count = min(count, loop_limit)
            step_counts.append(
                {
                    "name": step.get("name") or "",
                    "xpath": xpath,
                    "action": step["action"],
                    "wait_state": step.get("wait_state") or "auto",
                    "loop_limit": loop_limit,
                    "loop_mode": "pagination",
                    "pagination_mode": step.get("pagination_mode") or "",
                    "count": count,
                    "error": None,
                }
            )
            continue
        context = board_items[0] if board_items else root
        try:
            count = len(context.xpath(xpath))
            error = None
        except Exception as exc:
            count = 0
            error = str(exc)
        step_counts.append(
            {
                "name": step.get("name") or "",
                "xpath": xpath,
                "action": step["action"],
                "wait_state": step.get("wait_state") or "auto",
                "count": count,
                "error": error,
            }
        )

    return {
        "start_url": config["start_url"],
        "search_terms": search_terms,
        "search_term_count": len(search_terms),
        "board_enabled": board_enabled,
        "list_count": len(board_items) if board_items else None,
        "board_item_xpath": board_repeat_spec.item_xpath if board_repeat_spec else None,
        "board_item_tag": board_repeat_spec.item_tag if board_repeat_spec else None,
        "board_loop_anchor_xpath_1": loop_spec.anchor_xpath_1 if loop_spec else None,
        "board_loop_anchor_xpath_2": loop_spec.anchor_xpath_2 if loop_spec else None,
        "board_pagination_mode": pagination_spec.pagination_mode if pagination_spec else None,
        "board_pagination_xpath": pagination_spec.xpath if pagination_spec else None,
        "board_loop_root_xpath": loop_spec.root_xpath if loop_spec else None,
        "board_loop_item_tag": loop_spec.item_tag if loop_spec else None,
        "step_counts": step_counts,
    }


def run_workflow_config(config: dict[str, Any], record_policy: RecordPolicy | None = None) -> WorkflowExecution:
    config = normalize_workflow_config(config)
    validate_workflow_config(config)

    output_dir = Path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    execution = WorkflowExecution(config_name=str(config["name"]), output_dir=output_dir)
    search_terms = _config_search_terms(config)
    parser_name = _config_parser_name(config)
    effective_record_policy = record_policy
    direct_record_policy_state: dict[str, Any] = {}
    if parser_name is None and record_policy is None:
        effective_record_policy = _build_direct_workflow_record_policy(output_dir, config, direct_record_policy_state)
    timeout_ms = int(config.get("timeout_ms") or DEFAULT_TIMEOUT_MS)
    step_wait_ms = int(config.get("step_wait_ms") or DEFAULT_STEP_WAIT_MS)
    parse_pause_seconds = _config_parse_pause_seconds(config)
    if parser_name is not None:
        effective_terms = search_terms or [None]
        execution.diagnostics = {
            "start_url": config["start_url"],
            "renderer": "parser",
            "parser_name": parser_name,
            "timeout_ms": timeout_ms,
            "step_wait_ms": step_wait_ms,
            "parse_pause_seconds": parse_pause_seconds,
            "search_terms": search_terms,
            "search_term_count": len(effective_terms),
            "steps_count": len(config.get("steps") or []),
            "parser_item_count": 0,
        }
        try:
            _run_parser_workflow(
                execution=execution,
                config=config,
                parser_name=parser_name,
                timeout_ms=timeout_ms,
                record_policy=record_policy,
            )
        except WorkflowRecordPolicyStop as exc:
            _mark_record_policy_stop(execution, exc)
        except Exception as exc:
            execution.error = str(exc)
            execution.diagnostics["error_type"] = type(exc).__name__
            execution.diagnostics["error"] = str(exc)
        _finalize_workflow_execution(execution, config)
        _apply_workflow_result_filters(execution, config)
        return execution

    _ensure_windows_subprocess_policy()
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "playwright is not installed. Install requirements and run: python -m playwright install chromium"
        ) from exc

    board = config.get("board") or {}
    configured_repeat = bool(
        str(board.get("loop_anchor_xpath_1") or "").strip()
        and str(board.get("loop_anchor_xpath_2") or "").strip()
    ) or bool(str(board.get("item_tag") or "").strip() or str(board.get("item_xpath") or "").strip())
    primary_loop_step_index = _config_primary_loop_step_index(config)
    primary_loop_mode = _config_primary_loop_mode(config)
    click_loop_step_indexes = _config_click_loop_step_indexes(config)
    primary_loop_spec = _config_primary_loop_spec(config)
    primary_pagination_spec = _config_primary_pagination_spec(config)
    primary_loop_limit = _config_primary_loop_limit(config)
    board_repeat_spec = _config_board_repeat_spec(config)
    ignore_https_errors = _config_bool(config.get("ignore_https_errors"))
    execution.diagnostics = {
        "start_url": config["start_url"],
        "renderer": config.get("renderer", "playwright"),
        "headless": bool(config.get("headless", True)),
        "ignore_https_errors": ignore_https_errors,
        "timeout_ms": timeout_ms,
        "step_wait_ms": step_wait_ms,
        "parse_pause_seconds": parse_pause_seconds,
        "search_terms": search_terms,
        "search_term_count": len(search_terms),
        "primary_loop_step_index": primary_loop_step_index,
        "primary_loop_mode": primary_loop_mode,
        "board_enabled": bool(primary_loop_spec or primary_pagination_spec or board.get("enabled")),
        "board_list_xpath": board.get("list_xpath") or "",
        "board_item_xpath": board.get("item_xpath") or "",
        "board_item_tag": board.get("item_tag") or "",
        "board_loop_anchor_xpath_1": board.get("loop_anchor_xpath_1") or "",
        "board_loop_anchor_xpath_2": board.get("loop_anchor_xpath_2") or "",
        "board_pagination_mode": primary_pagination_spec.pagination_mode if primary_pagination_spec else "",
        "board_pagination_xpath": primary_pagination_spec.xpath if primary_pagination_spec else "",
        "board_limit": board.get("limit"),
        "board_item_count": None,
        "steps_count": len(config.get("steps") or []),
        "click_loop_step_indexes": click_loop_step_indexes,
    }

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=bool(config.get("headless", True)))
        context = browser.new_context(
            accept_downloads=True,
            ignore_https_errors=ignore_https_errors,
        )
        try:
            for search_term_index, search_term in enumerate(search_terms or [None]):
                try:
                    term_output_dir = _search_term_output_dir(output_dir, search_term, search_term_index, len(search_terms) or 1)
                    if primary_loop_mode == "pagination" and len(click_loop_step_indexes) == 2 and click_loop_step_indexes[0] == primary_loop_step_index:
                        records = _run_nested_pagination_click_loops(
                            browser=context,
                            config=config,
                            search_term=search_term,
                            search_term_index=search_term_index,
                            search_term_count=len(search_terms) or 1,
                            output_dir=term_output_dir,
                            timeout_ms=timeout_ms,
                            step_wait_ms=step_wait_ms,
                            parse_pause_seconds=parse_pause_seconds,
                            page_loop_step_index=click_loop_step_indexes[0],
                            item_loop_step_index=click_loop_step_indexes[1],
                            record_policy=effective_record_policy,
                        )
                        execution.records.extend(records)
                        execution.downloaded_files.extend(
                            path for record in records for path in record.get("downloaded_files", [])
                        )
                        execution.extracted_files.extend(
                            path for record in records for path in record.get("extracted_files", [])
                        )
                    elif primary_loop_mode == "pagination":
                        page_numbers = _resolve_item_numbers_for_term(
                            browser=context,
                            config=config,
                            search_term=search_term,
                            search_term_index=search_term_index,
                            search_term_count=len(search_terms) or 1,
                            output_dir=term_output_dir,
                            timeout_ms=timeout_ms,
                            step_wait_ms=step_wait_ms,
                            parse_pause_seconds=parse_pause_seconds,
                            primary_loop_step_index=primary_loop_step_index,
                            primary_loop_spec=None,
                            primary_pagination_spec=primary_pagination_spec,
                            board_repeat_spec=board_repeat_spec,
                            configured_repeat=configured_repeat,
                        )
                        page_count = len(page_numbers)
                        execution.diagnostics.setdefault("search_term_runs", []).append(
                            {
                                "search_term_index": search_term_index,
                                "search_term": search_term,
                                "board_item_count": page_count,
                                "empty": page_count == 0,
                            }
                        )
                        execution.diagnostics["board_item_count"] = page_count
                        if page_count <= 0:
                            continue
                        limit = page_count
                        if primary_loop_limit is not None:
                            limit = min(limit, primary_loop_limit)
                        for index, page_number in enumerate(page_numbers[:limit]):
                            record = _run_one_item(
                                context,
                                config,
                                index,
                                timeout_ms,
                                step_wait_ms,
                                parse_pause_seconds=parse_pause_seconds,
                                board_pagination_spec=primary_pagination_spec,
                                board_repeat_spec=board_repeat_spec,
                                search_term=search_term,
                                search_term_index=search_term_index,
                                search_term_count=len(search_terms) or 1,
                                output_dir_override=term_output_dir,
                                primary_loop_step_index=primary_loop_step_index,
                                board_item_number=page_number,
                                board_page_number=page_number,
                            )
                            if _append_execution_record(execution, record, effective_record_policy):
                                execution.downloaded_files.extend(record.get("downloaded_files", []))
                                execution.extracted_files.extend(record.get("extracted_files", []))
                    elif len(click_loop_step_indexes) == 2:
                        records = _run_nested_click_loops(
                            browser=context,
                            config=config,
                            search_term=search_term,
                            search_term_index=search_term_index,
                            search_term_count=len(search_terms) or 1,
                            output_dir=term_output_dir,
                            timeout_ms=timeout_ms,
                            step_wait_ms=step_wait_ms,
                            parse_pause_seconds=parse_pause_seconds,
                            page_loop_step_index=click_loop_step_indexes[0],
                            item_loop_step_index=click_loop_step_indexes[1],
                            record_policy=effective_record_policy,
                        )
                        execution.records.extend(records)
                        execution.downloaded_files.extend(
                            path for record in records for path in record.get("downloaded_files", [])
                        )
                        execution.extracted_files.extend(
                            path for record in records for path in record.get("extracted_files", [])
                        )
                    elif primary_loop_step_index is not None or board.get("enabled"):
                        board_item_numbers = _resolve_item_numbers_for_term(
                            browser=context,
                            config=config,
                            search_term=search_term,
                            search_term_index=search_term_index,
                            search_term_count=len(search_terms) or 1,
                            output_dir=term_output_dir,
                            timeout_ms=timeout_ms,
                            step_wait_ms=step_wait_ms,
                            parse_pause_seconds=parse_pause_seconds,
                            primary_loop_step_index=primary_loop_step_index,
                            primary_loop_spec=primary_loop_spec,
                            primary_pagination_spec=primary_pagination_spec,
                            board_repeat_spec=board_repeat_spec,
                            configured_repeat=configured_repeat,
                        )
                        board_item_count = len(board_item_numbers)
                        execution.diagnostics.setdefault("search_term_runs", []).append(
                            {
                                "search_term_index": search_term_index,
                                "search_term": search_term,
                                "board_item_count": board_item_count,
                                "empty": board_item_count == 0,
                            }
                        )
                        execution.diagnostics["board_item_count"] = board_item_count
                        if board_item_count <= 0:
                            continue
                        limit = board_item_count
                        if primary_loop_limit is not None:
                            limit = min(limit, primary_loop_limit)
                        elif board.get("enabled"):
                            limit = min(limit, int(board.get("limit") or board_item_count))

                        for index, item_number in enumerate(board_item_numbers[:limit]):
                            record = _run_one_item(
                                context,
                                config,
                                index,
                                timeout_ms,
                                step_wait_ms,
                                parse_pause_seconds=parse_pause_seconds,
                                board_loop_spec=primary_loop_spec,
                                board_repeat_spec=board_repeat_spec,
                                search_term=search_term,
                                search_term_index=search_term_index,
                                search_term_count=len(search_terms) or 1,
                                output_dir_override=term_output_dir,
                                primary_loop_step_index=primary_loop_step_index,
                                board_item_number=item_number,
                            )
                            if _append_execution_record(execution, record, effective_record_policy):
                                execution.downloaded_files.extend(record.get("downloaded_files", []))
                                execution.extracted_files.extend(record.get("extracted_files", []))
                    else:
                        record = _run_one_item(
                            context,
                            config,
                            None,
                            timeout_ms,
                            step_wait_ms,
                            parse_pause_seconds=parse_pause_seconds,
                            search_term=search_term,
                            search_term_index=search_term_index,
                            search_term_count=len(search_terms) or 1,
                            output_dir_override=term_output_dir,
                            primary_loop_step_index=primary_loop_step_index,
                        )
                        if _append_execution_record(execution, record, effective_record_policy):
                            execution.downloaded_files.extend(record.get("downloaded_files", []))
                            execution.extracted_files.extend(record.get("extracted_files", []))
                except WorkflowRecordPolicyStop as exc:
                    _mark_record_policy_stop(execution, exc)
                    if _stop_remaining_search_terms(exc):
                        break
                    continue
        except Exception as exc:
            execution.error = str(exc)
            execution.diagnostics["error_type"] = type(exc).__name__
            execution.diagnostics["error"] = str(exc)
        finally:
            try:
                context.close()
            except Exception:
                pass
            browser.close()

    if direct_record_policy_state:
        execution.diagnostics["previous_duplicate_index_count"] = direct_record_policy_state.get("previous_duplicate_index_count", 0)
        execution.diagnostics["latest_duplicate_index_count"] = direct_record_policy_state.get("latest_duplicate_index_count", 0)
        same_run_duplicate_skipped_count = int(direct_record_policy_state.get("same_run_duplicate_skipped_count") or 0)
        if same_run_duplicate_skipped_count:
            execution.diagnostics["same_run_duplicate_skipped_count"] = (
                int(execution.diagnostics.get("same_run_duplicate_skipped_count") or 0) + same_run_duplicate_skipped_count
            )
        latest_cross_group_duplicate_skipped_count = int(
            direct_record_policy_state.get("latest_cross_group_duplicate_skipped_count") or 0
        )
        if latest_cross_group_duplicate_skipped_count:
            execution.diagnostics["latest_cross_group_duplicate_skipped_count"] = (
                int(execution.diagnostics.get("latest_cross_group_duplicate_skipped_count") or 0)
                + latest_cross_group_duplicate_skipped_count
            )
    _finalize_workflow_execution(execution, config)
    _apply_workflow_result_filters(execution, config)
    return execution


def _resolve_item_numbers_for_term(
    browser: Any,
    config: dict[str, Any],
    search_term: str | None,
    search_term_index: int,
    search_term_count: int,
    output_dir: Path,
    timeout_ms: int,
    step_wait_ms: int,
    parse_pause_seconds: int,
    primary_loop_step_index: int | None,
    primary_loop_spec: BoardLoopSpec | None,
    primary_pagination_spec: PaginationLoopSpec | None,
    board_repeat_spec: BoardRepeatSpec | None,
    configured_repeat: bool,
) -> list[int]:
    page = _new_workflow_page(browser)
    board = config.get("board") or {}
    steps = config.get("steps") or []
    try:
        page.goto(
            _render_template_value(str(config["start_url"]), search_term, url_encode=True),
            wait_until="domcontentloaded",
            timeout=timeout_ms,
        )
        if primary_loop_step_index and primary_loop_step_index > 1:
            prefix_steps = steps[: primary_loop_step_index - 1]
            for step_index, step in enumerate(prefix_steps, start=1):
                step_log, next_page = _run_step(
                    page,
                    None,
                    step,
                    step_index,
                    output_dir,
                    timeout_ms,
                    step_wait_ms,
                    None,
                    search_term=search_term,
                    search_term_index=search_term_index,
                    search_term_count=search_term_count,
                    primary_loop_step_index=primary_loop_step_index,
                    parse_pause_seconds=parse_pause_seconds,
                )
                if next_page is not page and step_log.get("open_mode") != "popup":
                    page.close()
                    page = next_page
                elif next_page is not page:
                    page = next_page
                if not step_log["success"]:
                    raise RuntimeError(step_log["error"])

        if primary_loop_spec is not None:
            try:
                page.locator(f"xpath={primary_loop_spec.anchor_xpath_1}").first.wait_for(
                    state="attached",
                    timeout=timeout_ms,
                )
            except Exception:
                pass

        try:
            if primary_pagination_spec is not None:
                page_numbers = _resolve_pagination_page_numbers(page, primary_pagination_spec, loop_limit=_config_primary_loop_limit(config))
                return page_numbers
            if primary_loop_spec is not None:
                exclude_xpath = ""
                if primary_loop_step_index and primary_loop_step_index > 0:
                    primary_loop_step = steps[primary_loop_step_index - 1] if len(steps) >= primary_loop_step_index else None
                    if isinstance(primary_loop_step, dict):
                        exclude_xpath = str(primary_loop_step.get("exclude_xpath") or "").strip()
                return _resolve_board_loop_item_numbers(page, primary_loop_spec, exclude_xpath=exclude_xpath)

            first_step_xpath = str((steps[0].get("xpath") or "") if steps and isinstance(steps[0], dict) else "")
            board_item_count, _ = _resolve_board_items(
                page,
                str(board.get("list_xpath") or ""),
                board_repeat_spec,
                first_step_xpath,
                configured_repeat,
            )
            return list(range(board_item_count))
        except RuntimeError:
            return []
    finally:
        page.close()


def _resolve_item_count_for_term(
    browser: Any,
    config: dict[str, Any],
    search_term: str | None,
    search_term_index: int,
    search_term_count: int,
    output_dir: Path,
    timeout_ms: int,
    step_wait_ms: int,
    parse_pause_seconds: int,
    primary_loop_step_index: int | None,
    primary_loop_spec: BoardLoopSpec | None,
    board_repeat_spec: BoardRepeatSpec | None,
    configured_repeat: bool,
) -> int:
    return len(
        _resolve_item_numbers_for_term(
            browser=browser,
            config=config,
            search_term=search_term,
            search_term_index=search_term_index,
            search_term_count=search_term_count,
            output_dir=output_dir,
            timeout_ms=timeout_ms,
            step_wait_ms=step_wait_ms,
            parse_pause_seconds=parse_pause_seconds,
            primary_loop_step_index=primary_loop_step_index,
            primary_loop_spec=primary_loop_spec,
            primary_pagination_spec=None,
            board_repeat_spec=board_repeat_spec,
            configured_repeat=configured_repeat,
        )
    )


def _finalize_workflow_execution(execution: WorkflowExecution, config: dict[str, Any]) -> None:
    if execution.error is not None or execution.records:
        return
    if execution.diagnostics.get("record_policy_stopped"):
        return

    has_loop_config = _config_primary_loop_step_index(config) is not None or bool((config.get("board") or {}).get("enabled"))
    has_parser_config = _config_parser_name(config) is not None
    if not has_loop_config and not has_parser_config:
        return

    if has_parser_config:
        message = f"No items matched configured parser for {config.get('name') or 'workflow'}."
    else:
        message = f"No items matched configured loop for {config.get('name') or 'workflow'}."
    execution.error = message
    execution.diagnostics["error_type"] = "NoItemsMatchedError"
    execution.diagnostics["error"] = message


def _apply_workflow_result_filters(execution: WorkflowExecution, config: dict[str, Any]) -> None:
    filter_terms = _config_filter_terms(config)
    source_records = list(execution.records)
    raw_records, duplicate_skipped = _dedupe_execution_records(source_records)
    raw_generated_files = list(execution.generated_files) + list(execution.downloaded_files) + list(execution.extracted_files)
    raw_generated_files.extend(_collect_record_files(source_records, "downloaded_files"))
    raw_generated_files.extend(_collect_record_files(source_records, "extracted_files"))
    raw_generated_files.extend(_collect_record_output_files(source_records))
    filter_enabled = bool(filter_terms)
    matched_root = _result_category_root(execution.output_dir, "filter")
    nonfilter_root = None
    if execution.diagnostics.get("record_policy_stopped") and not raw_records:
        execution.diagnostics["filter_terms"] = filter_terms
        execution.diagnostics["raw_record_count"] = len(source_records)
        execution.diagnostics["deduped_record_count"] = 0
        execution.diagnostics["matched_record_count"] = 0
        execution.diagnostics["nonfilter_record_count"] = 0
        execution.diagnostics["filter_output_skipped"] = "duplicate_stopped_without_new_records"
        protected_roots = [matched_root, *([nonfilter_root] if nonfilter_root is not None else [])]
        _delete_unclassified_output_files(
            execution.output_dir,
            protected_roots=protected_roots,
            candidate_files=raw_generated_files,
        )
        _remove_nonfilter_output_dir(execution.output_dir)
        _cleanup_empty_dirs(execution.output_dir, protected_roots=protected_roots)
        execution.records = []
        execution.downloaded_files = []
        execution.extracted_files = []
        return
    if duplicate_skipped:
        execution.diagnostics["same_run_duplicate_skipped_count"] = (
            int(execution.diagnostics.get("same_run_duplicate_skipped_count") or 0) + duplicate_skipped
        )
    matched_records, nonfilter_records = _split_records_by_filter_terms(raw_records, filter_terms)

    execution.diagnostics["filter_terms"] = filter_terms
    execution.diagnostics["raw_record_count"] = len(source_records)
    execution.diagnostics["deduped_record_count"] = len(raw_records)
    execution.diagnostics["matched_record_count"] = len(matched_records)
    execution.diagnostics["nonfilter_record_count"] = len(nonfilter_records)
    execution.diagnostics["filter_enabled"] = filter_enabled
    execution.diagnostics["filter_output_dir"] = str(matched_root)
    if filter_enabled:
        execution.diagnostics["nonfilter_output_suppressed"] = True

    execution.records = matched_records
    execution.downloaded_files = _collect_record_files(matched_records, "downloaded_files")
    execution.extracted_files = _collect_record_files(matched_records, "extracted_files")

    parser_name = _config_parser_name(config)
    if parser_name is not None:
        _save_filtered_parser_outputs(
            execution=execution,
            config=config,
            matched_records=matched_records,
            nonfilter_records=nonfilter_records,
            filter_terms=filter_terms,
            matched_root=matched_root,
            nonfilter_root=nonfilter_root,
        )
    else:
        if filter_enabled:
            _relocate_record_file_lists(matched_records, execution.output_dir, matched_root)
            execution.downloaded_files = _collect_record_files(matched_records, "downloaded_files")
            execution.extracted_files = _collect_record_files(matched_records, "extracted_files")
        elif matched_records:
            _relocate_record_file_lists(matched_records, execution.output_dir, matched_root)
            execution.downloaded_files = _collect_record_files(matched_records, "downloaded_files")
            execution.extracted_files = _collect_record_files(matched_records, "extracted_files")

    protected_roots = [matched_root, *([nonfilter_root] if nonfilter_root is not None else [])]
    _delete_unclassified_output_files(
        execution.output_dir,
        protected_roots=protected_roots,
        candidate_files=raw_generated_files,
    )
    _remove_nonfilter_output_dir(execution.output_dir)
    _cleanup_empty_dirs(execution.output_dir, protected_roots=protected_roots)

    matched_path = _save_workflow_record_snapshot(
        matched_root,
        config,
        matched_records,
        filter_terms=filter_terms,
        file_name="workflow_records.json",
    )
    execution.diagnostics["matched_records_file"] = str(matched_path)
    execution.diagnostics["manifest_file"] = str(matched_path)
    latest_path = _save_latest_record_snapshot(
        matched_root,
        config,
        matched_records=matched_records,
        nonfilter_records=nonfilter_records,
        filter_terms=filter_terms,
    )
    execution.diagnostics["latest_records_file"] = str(latest_path)


def _delete_unclassified_output_files(output_dir: Path, protected_roots: list[Path], candidate_files: list[str]) -> None:
    normalized_protected = [root.resolve() for root in protected_roots if root is not None]
    if not output_dir.exists():
        return
    candidates: set[Path] = set()
    for value in candidate_files:
        path = Path(value)
        if not path.is_absolute():
            path = path if path.exists() else output_dir / path
        candidates.add(path)
        if path.parent.exists() and output_dir.resolve() in path.parent.resolve().parents:
            candidates.update(candidate for candidate in path.parent.rglob("*") if candidate.is_file())
    for path in candidates:
        if not path.is_file():
            continue
        resolved = path.resolve()
        if output_dir.resolve() not in resolved.parents:
            continue
        if any(resolved == root or root in resolved.parents for root in normalized_protected):
            continue
        try:
            path.unlink()
        except FileNotFoundError:
            continue


def _remove_nonfilter_output_dir(output_dir: Path) -> None:
    nonfilter_root = output_dir / "nonfilter"
    try:
        if nonfilter_root.is_dir():
            shutil.rmtree(nonfilter_root)
    except FileNotFoundError:
        return


def _save_filtered_parser_outputs(
    *,
    execution: WorkflowExecution,
    config: dict[str, Any],
    matched_records: list[dict[str, Any]],
    nonfilter_records: list[dict[str, Any]],
    filter_terms: list[str],
    matched_root: Path,
    nonfilter_root: Path | None,
) -> None:
    parser_name = _config_parser_name(config)
    runs = execution.diagnostics.get("search_term_runs") or []
    parser_runs: dict[int, dict[str, Any]] = {}
    for run in runs:
        if not isinstance(run, dict):
            continue
        index = int(run.get("search_term_index") or 0)
        parser_runs[index] = run

    matched_by_term = _group_records_by_search_term(matched_records)
    matched_files: list[str] = []
    nonfilter_files: list[str] = []
    for search_term_index, run in parser_runs.items():
        search_term = run.get("search_term")
        api_url = str(run.get("rss_url") or run.get("api_url") or _render_template_value(str(config["start_url"]), search_term, url_encode=True))
        final_url = str(run.get("final_url") or api_url)
        output_dir = _search_term_output_dir(matched_root, search_term, search_term_index, len(parser_runs) or 1)
        matched_items = [dict(record.get("extracts") or {}) for record in matched_by_term.get(search_term_index, [])]
        matched_path = _save_parser_items(
            parser_name=parser_name or GOOGLE_NEWS_RSS_ATTR,
            output_dir=output_dir,
            search_term=search_term,
            source_url=api_url,
            final_url=final_url,
            items=matched_items,
            filter_terms=filter_terms,
        )
        _assign_parser_record_output_files(matched_by_term.get(search_term_index, []), matched_path)
        _rename_parser_record_output_files(matched_by_term.get(search_term_index, []), matched_path)
        matched_files.append(str(matched_path))
        run["output_file"] = str(matched_path)

    execution.extracted_files = matched_files
    execution.diagnostics["matched_output_files"] = matched_files
    execution.diagnostics["nonfilter_output_files"] = nonfilter_files


def _fetch_parser_items(
    parser_name: str,
    source_url: str,
    *,
    timeout: float,
    item_limit: int | None = None,
) -> tuple[list[dict[str, Any]], str]:
    if parser_name == DAUM_NEWS_API_ATTR:
        return fetch_daum_news_api_items(source_url, timeout=timeout, item_limit=item_limit)
    if parser_name == GOOGLE_NEWS_RSS_ATTR:
        return fetch_google_news_rss_items(source_url, timeout=timeout)
    if parser_name == NAVER_NEWS_API_ATTR:
        return fetch_naver_news_api_items(source_url, timeout=timeout, item_limit=item_limit)
    raise RuntimeError(f"Unsupported parser attr: {parser_name}")


def _save_parser_items(
    *,
    parser_name: str,
    output_dir: Path,
    search_term: str | None,
    source_url: str,
    final_url: str,
    items: list[dict[str, Any]],
    filter_terms: list[str] | None = None,
) -> Path:
    if parser_name == DAUM_NEWS_API_ATTR:
        return save_daum_news_api_items(
            output_dir,
            search_term=search_term,
            api_url=source_url,
            final_url=final_url,
            items=items,
            filter_terms=filter_terms,
        )
    if parser_name == GOOGLE_NEWS_RSS_ATTR:
        return save_google_news_rss_items(
            output_dir,
            search_term=search_term,
            rss_url=source_url,
            final_url=final_url,
            items=items,
            filter_terms=filter_terms,
        )
    if parser_name == NAVER_NEWS_API_ATTR:
        return save_naver_news_api_items(
            output_dir,
            search_term=search_term,
            api_url=source_url,
            final_url=final_url,
            items=items,
            filter_terms=filter_terms,
        )
    raise RuntimeError(f"Unsupported parser attr: {parser_name}")


def _assign_parser_record_output_files(records: list[dict[str, Any]], manifest_path: Path) -> None:
    item_files = _parser_manifest_item_files(manifest_path)
    for index, record in enumerate(records):
        output_path = manifest_path
        if index < len(item_files):
            candidate = Path(item_files[index])
            output_path = candidate if candidate.is_absolute() else manifest_path.parent / candidate
        record["output_file"] = str(output_path)
        for step in record.get("steps") or []:
            if isinstance(step, dict):
                step["output_file"] = str(output_path)


def _rename_parser_record_output_files(records: list[dict[str, Any]], manifest_path: Path) -> None:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    item_files: list[str] = []
    for record in records:
        output_file = str(record.get("output_file") or "")
        if not output_file:
            continue
        path = Path(output_file)
        if not path.exists():
            item_files.append(_relative_parser_item_file(manifest_path, path))
            continue
        record_key = safe_name(str(record.get("record_key") or path.stem))
        target = _unique_path(path.with_name(f"{record_key}.json"))
        if target != path:
            try:
                path.rename(target)
            except OSError:
                target = path
        _write_parser_item_record_key(target, str(record.get("record_key") or ""))
        record["output_file"] = str(target)
        for step in record.get("steps") or []:
            if isinstance(step, dict):
                step["output_file"] = str(target)
        item_files.append(_relative_parser_item_file(manifest_path, target))
    if isinstance(payload, dict) and item_files:
        payload["item_files"] = item_files
        manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _relative_parser_item_file(manifest_path: Path, item_path: Path) -> str:
    try:
        return item_path.relative_to(manifest_path.parent).as_posix()
    except ValueError:
        return str(item_path)


def _write_parser_item_record_key(path: Path, record_key: str) -> None:
    if not record_key:
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if isinstance(payload, dict):
        payload["record_key"] = record_key
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _parser_manifest_item_files(manifest_path: Path) -> list[str]:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    raw_files = payload.get("item_files") if isinstance(payload, dict) else None
    if not isinstance(raw_files, list):
        return []
    return [str(value) for value in raw_files if str(value or "").strip()]


def _split_records_by_filter_terms(
    records: list[dict[str, Any]],
    filter_terms: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not filter_terms:
        return list(records), []

    matched: list[dict[str, Any]] = []
    nonfilter: list[dict[str, Any]] = []
    for record in records:
        if _record_matches_filter_terms(record, filter_terms):
            matched.append(record)
        else:
            nonfilter.append(record)
    return matched, nonfilter


def _dedupe_execution_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    skipped = 0
    for record in records:
        keys = duplicate_keys_for_record(record)
        if any(key in seen for key in keys):
            skipped += 1
            continue
        for key in keys:
            seen.add(key)
        deduped.append(record)
    return deduped, skipped


def _record_matches_filter_terms(record: dict[str, Any], filter_terms: list[str]) -> bool:
    blob = _record_filter_blob(record)
    if not blob:
        return False
    return any(term.lower() in blob for term in filter_terms)


def _record_filter_blob(value: Any) -> str:
    parts: list[str] = []
    metadata_keys = {
        "search_term",
        "search_term_index",
        "search_term_count",
        "start_url",
        "final_url",
        "url_before",
        "url_after",
        "rss_url",
        "api_url",
        "config_name",
        "output_dir",
        "parser_name",
        "post_id",
        "item_index",
        "source",
        "source_name",
        "source_provider",
        "source_api",
        "api_metadata",
        "record_key",
        "output_file",
        "downloaded_file",
        "downloaded_files",
        "extracted_file",
        "extracted_files",
        "url",
        "link",
        "detail_url",
        "originallink",
        "api_url",
        "rss_url",
        "xpath",
        "resolved_xpath",
        "attr",
        "action",
        "name",
        "success",
        "error",
        "duration_seconds",
        "matched_count",
        "pubDate",
        "pub_date",
        "published_at",
        "date",
        "datetime",
    }
    direct_content_keys = {
        "extract_title",
        "title",
        "description",
        "body",
        "content",
        "text",
        "summary",
        "desc",
        "value",
    }

    def visit_content(item: Any, key: str | None = None) -> None:
        if item is None:
            return
        if key in metadata_keys:
            return
        if isinstance(item, str):
            cleaned = " ".join(item.split()).strip().lower()
            if cleaned:
                parts.append(cleaned)
            return
        if isinstance(item, dict):
            for sub_key, sub_value in item.items():
                visit_content(sub_value, str(sub_key))
            return
        if isinstance(item, list):
            for sub_value in item:
                visit_content(sub_value, key)
            return
        cleaned = " ".join(str(item).split()).strip().lower()
        if cleaned:
            parts.append(cleaned)

    if not isinstance(value, dict):
        visit_content(value)
        return " \n".join(parts)

    for key in direct_content_keys:
        if key in value:
            visit_content(value.get(key), key)

    extracts = value.get("extracts")
    if isinstance(extracts, dict):
        visit_content(extracts)

    steps = value.get("steps")
    if isinstance(steps, list):
        for step in steps:
            if isinstance(step, dict) and "value" in step:
                visit_content(step.get("value"), "value")

    return " \n".join(parts)


def _collect_record_files(records: list[dict[str, Any]], key: str) -> list[str]:
    collected: list[str] = []
    seen: set[str] = set()
    for record in records:
        raw_values = record.get(key) or []
        if isinstance(raw_values, str):
            raw_values = [raw_values]
        if not isinstance(raw_values, list):
            continue
        for value in raw_values:
            path = str(value)
            if path and path not in seen:
                seen.add(path)
                collected.append(path)
    return collected


def _collect_record_output_files(records: list[dict[str, Any]]) -> list[str]:
    collected: list[str] = []
    seen: set[str] = set()
    for record in records:
        value = str(record.get("output_file") or "")
        if value and value not in seen:
            seen.add(value)
            collected.append(value)
    return collected


def _apply_stable_record_key(
    record: dict[str, Any],
    config: dict[str, Any],
    *,
    rename_files: bool = False,
) -> None:
    old_key = str(record.get("record_key") or "")
    new_key = _build_stable_record_key(config, record)
    if not new_key or new_key == old_key:
        return
    record["record_key"] = new_key
    for step in record.get("steps") or []:
        if isinstance(step, dict):
            step["record_key"] = new_key
    if rename_files:
        _rename_record_artifacts(record, old_key, new_key)


def _rename_record_artifacts(record: dict[str, Any], old_key: str, new_key: str) -> None:
    if not old_key or not new_key or old_key == new_key:
        return
    for key in ("downloaded_files", "extracted_files"):
        value = record.get(key)
        if isinstance(value, list):
            record[key] = [_rename_record_artifact_path(path, old_key, new_key) for path in value]
        elif isinstance(value, str):
            record[key] = _rename_record_artifact_path(value, old_key, new_key)
    if record.get("output_file"):
        record["output_file"] = _rename_record_artifact_path(str(record["output_file"]), old_key, new_key)
    for step in record.get("steps") or []:
        if not isinstance(step, dict):
            continue
        for key in ("downloaded_files", "extracted_files"):
            value = step.get(key)
            if isinstance(value, list):
                step[key] = [_rename_record_artifact_path(path, old_key, new_key) for path in value]
            elif isinstance(value, str):
                step[key] = _rename_record_artifact_path(value, old_key, new_key)
        for key in ("downloaded_file", "extracted_file", "output_file"):
            if step.get(key):
                step[key] = _rename_record_artifact_path(str(step[key]), old_key, new_key)


def _rename_record_artifact_path(path_value: Any, old_key: str, new_key: str) -> str:
    path_text = str(path_value or "")
    if not path_text:
        return ""
    path = Path(path_text)
    old_safe = safe_name(old_key)
    new_safe = safe_name(new_key)
    if old_safe not in path.name:
        return path_text
    target_name = path.name.replace(old_safe, new_safe, 1)
    target = path.with_name(target_name)
    try:
        if path.exists():
            target = _unique_path(target)
            path.rename(target)
            return str(target)
    except OSError:
        return path_text
    return str(target)


def _group_records_by_search_term(records: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for record in records:
        index = record.get("search_term_index")
        if not isinstance(index, int):
            try:
                index = int(index)
            except (TypeError, ValueError):
                index = 0
        grouped.setdefault(index, []).append(record)
    return grouped


def _save_workflow_record_snapshot(
    output_dir: Path,
    config: dict[str, Any],
    records: list[dict[str, Any]],
    *,
    filter_terms: list[str],
    file_name: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / file_name
    existing_payload = _read_existing_workflow_record_snapshot(output_path)
    if existing_payload:
        existing_records = existing_payload.get("records") if isinstance(existing_payload.get("records"), list) else []
        records = _merge_workflow_record_snapshot_records(existing_records, records)
    if file_name == "workflow_records.json":
        snapshot_records: list[dict[str, Any]] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            snapshot_records.append(_workflow_record_snapshot_record(config, record, filter_terms=filter_terms))
        records = snapshot_records
    payload = {
        "config_name": config.get("name"),
        "item_count": len(records),
        "records": records,
    }
    if file_name == "workflow_records.json":
        payload = _limit_workflow_record_snapshot_lines(payload)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def _save_latest_record_snapshot(
    output_dir: Path,
    config: dict[str, Any],
    *,
    matched_records: list[dict[str, Any]],
    nonfilter_records: list[dict[str, Any]],
    filter_terms: list[str],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "latest.json"
    existing_payload = _read_existing_workflow_record_snapshot(output_path)
    existing_records = []
    if existing_payload:
        raw_existing = existing_payload.get("records")
        if isinstance(raw_existing, list):
            existing_records = [record for record in raw_existing if isinstance(record, dict)]

    current_entries: list[dict[str, str]] = []
    for record in matched_records:
        terms = _matched_filter_terms(record, filter_terms) if filter_terms else [""]
        for term in terms:
            current_entries.append(_latest_record_entry(config, record, filter_term=term))
    for record in nonfilter_records:
        current_entries.append(_latest_record_entry(config, record, filter_term="nonfilter"))

    records = _merge_latest_records(existing_records, current_entries)
    payload = {
        "config_name": config.get("name"),
        "item_count": len(records),
        "records": records,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def _latest_record_entry(config: dict[str, Any], record: dict[str, Any], *, filter_term: str) -> dict[str, str]:
    return {
        "search_term": str(record.get("search_term") or ""),
        "filter_term": str(filter_term or ""),
        "final_url": _record_final_url(config, record),
    }


def _merge_latest_records(
    existing_records: list[dict[str, Any]],
    current_records: list[dict[str, str]],
) -> list[dict[str, str]]:
    merged: dict[tuple[str, str], dict[str, str]] = {}
    order: list[tuple[str, str]] = []
    for record in current_records:
        key = _latest_record_group_key(record)
        if key in merged:
            continue
        merged[key] = _normalize_latest_record(record)
        order.append(key)
    for record in existing_records:
        key = _latest_record_group_key(record)
        if key in merged:
            continue
        merged[key] = _normalize_latest_record(record)
        order.append(key)
    return [merged[key] for key in order]


def _latest_record_group_key(record: dict[str, Any]) -> tuple[str, str]:
    search_term = str(record.get("search_term") or "")
    search_key = "__numeric_page_param__" if NUMERIC_SEARCH_TERM_RE.fullmatch(search_term.strip()) else search_term
    return search_key, str(record.get("filter_term") or "")


def _normalize_latest_record(record: dict[str, Any]) -> dict[str, str]:
    return {
        "search_term": str(record.get("search_term") or ""),
        "filter_term": str(record.get("filter_term") or ""),
        "final_url": str(record.get("final_url") or ""),
    }


def build_latest_duplicate_index(
    snapshot_roots: list[str | Path] | tuple[str | Path, ...],
    config: dict[str, Any] | None = None,
) -> LatestDuplicateIndex:
    index = LatestDuplicateIndex()
    for record in iter_latest_records(snapshot_roots):
        prepared = _record_for_duplicate_index(config, record)
        keys = duplicate_keys_for_record(prepared)
        if not keys:
            continue
        search_term = str(record.get("search_term") or "")
        filter_term = str(record.get("filter_term") or "")
        target = (
            index.numeric_by_filter.setdefault(filter_term, set())
            if _is_numeric_search_term(search_term)
            else index.normal_by_search.setdefault(search_term, set())
        )
        for key in keys:
            target.add(key)
            index.all_keys.add(key)
    return index


def iter_latest_records(snapshot_roots: list[str | Path] | tuple[str | Path, ...]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for root_value in snapshot_roots:
        root = Path(root_value)
        if root.is_file():
            paths = [root] if root.name == "latest.json" else []
        elif root.exists():
            paths = list(root.rglob("latest.json"))
        else:
            paths = []
        for path in paths:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            raw_records = payload.get("records") if isinstance(payload, dict) else payload
            if isinstance(raw_records, list):
                records.extend(record for record in raw_records if isinstance(record, dict))
    return records


def latest_duplicate_decision_for_record(
    record: dict[str, Any],
    latest_index: LatestDuplicateIndex,
    *,
    filter_terms: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any] | None:
    if not latest_index.has_records:
        return None
    keys = duplicate_keys_for_record(record)
    if not keys:
        return None

    search_term = str(record.get("search_term") or "")
    if _is_numeric_search_term(search_term):
        candidate_filters = _latest_filter_candidates_for_record(record, list(filter_terms or []))
        for filter_term in candidate_filters:
            duplicate_key = next((key for key in keys if key in latest_index.numeric_by_filter.get(filter_term, set())), "")
            if duplicate_key:
                return _latest_duplicate_stop_decision(duplicate_key, latest_scope="numeric_filter")
    else:
        duplicate_key = next((key for key in keys if key in latest_index.normal_by_search.get(search_term, set())), "")
        if duplicate_key:
            return _latest_duplicate_stop_decision(duplicate_key, latest_scope="search_term")

    duplicate_key = next((key for key in keys if key in latest_index.all_keys), "")
    if duplicate_key:
        return {
            "include": False,
            "stop": False,
            "reason": "latest_cross_group_duplicate_skipped",
            "metadata": {
                "duplicate_key": duplicate_key,
                "latest": True,
                "stop_scope": "none",
            },
        }
    return None


def _latest_filter_candidates_for_record(record: dict[str, Any], filter_terms: list[str]) -> list[str]:
    if not filter_terms:
        return [""]
    matched = _matched_filter_terms(record, filter_terms)
    if matched:
        return matched
    return ["nonfilter", ""]


def _latest_duplicate_stop_decision(duplicate_key: str, *, latest_scope: str) -> dict[str, Any]:
    stop_scope = "numeric_page_sequence" if latest_scope == "numeric_filter" else "search_term"
    return {
        "include": False,
        "stop": True,
        "reason": "duplicate_boundary_stopped",
        "metadata": {
            "duplicate_key": duplicate_key,
            "stop_scope": stop_scope,
            "boundary": True,
            "latest": True,
            "latest_scope": latest_scope,
        },
    }


def _is_numeric_search_term(value: Any) -> bool:
    return bool(NUMERIC_SEARCH_TERM_RE.fullmatch(str(value or "").strip()))


def _duplicate_stop_scope_for_record(record: dict[str, Any]) -> str:
    return "numeric_page_sequence" if _is_numeric_search_term(record.get("search_term")) else "search_term"


def _stop_remaining_search_terms(exc: WorkflowRecordPolicyStop) -> bool:
    return str(exc.metadata.get("stop_scope") or "") in {"numeric_page_sequence", "workflow", "config"}


def _workflow_record_snapshot_record(
    config: dict[str, Any],
    record: dict[str, Any],
    *,
    filter_terms: list[str],
) -> dict[str, Any]:
    if not str(record.get("record_key") or "").strip():
        record = dict(record)
        record["record_key"] = _build_stable_record_key(config, record)
    return {
        "record_key": str(record.get("record_key") or ""),
        "search_term": str(record.get("search_term") or ""),
        "filter_term": ", ".join(_matched_filter_terms(record, filter_terms)),
        "extract_title": _record_title(record),
        "description": _record_description(record),
        "pub_date": _record_pub_date(record),
        "final_url": _record_final_url(config, record),
    }


def _matched_filter_terms(record: dict[str, Any], filter_terms: list[str]) -> list[str]:
    blob = _record_filter_blob(record)
    if not blob:
        return []
    return [term for term in filter_terms if str(term or "").strip().lower() in blob]


def _record_extracts(record: dict[str, Any]) -> dict[str, Any]:
    extracts = record.get("extracts")
    return extracts if isinstance(extracts, dict) else {}


def _record_title(record: dict[str, Any]) -> str:
    extracts = _record_extracts(record)
    return _first_record_text(
        record.get("extract_title"),
        record.get("title"),
        extracts.get("extract_title"),
        extracts.get("title"),
    )


def _record_description(record: dict[str, Any]) -> str:
    extracts = _record_extracts(record)
    return _first_record_text(
        record.get("description"),
        record.get("desc"),
        record.get("summary"),
        extracts.get("description"),
        extracts.get("desc"),
        extracts.get("summary"),
    )


def _record_pub_date(record: dict[str, Any]) -> str:
    extracts = _record_extracts(record)
    value = _first_record_text(
        record.get("pub_date"),
        record.get("pubDate"),
        record.get("published_at"),
        record.get("date"),
        record.get("datetime"),
        extracts.get("pub_date"),
        extracts.get("pubDate"),
        extracts.get("published_at"),
        extracts.get("date"),
        extracts.get("datetime"),
    )
    return value or format_datetime(datetime.now(KST))


def _record_final_url(config: dict[str, Any], record: dict[str, Any]) -> str:
    extracts = _record_extracts(record)
    return canonicalize_article_url(
        _first_record_text(
            extracts.get("detail_url"),
            record.get("detail_url"),
            extracts.get("originallink"),
            record.get("originallink"),
            extracts.get("link"),
            record.get("link"),
            record.get("final_url"),
            extracts.get("final_url"),
        ),
        page_query_params=_config_search_term_query_params(config, str(record.get("search_term") or "")),
    )


def _config_search_term_query_params(config: dict[str, Any], search_term: str) -> set[str]:
    if not NUMERIC_SEARCH_TERM_RE.fullmatch(str(search_term or "").strip()):
        return set()
    try:
        query_items = parse_qsl(urlsplit(str(config.get("start_url") or "")).query, keep_blank_values=True)
    except ValueError:
        return set()
    params: set[str] = set()
    for name, value in query_items:
        if "{search_term}" in str(value):
            params.add(str(name))
    return params


def _first_record_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        if isinstance(value, list):
            text = _first_record_text(*value)
        else:
            text = str(value).strip()
        if text:
            return text
    return ""


def _limit_workflow_record_snapshot_lines(payload: dict[str, Any], max_lines: int = MAX_WORKFLOW_RECORD_LINES) -> dict[str, Any]:
    records = payload.get("records")
    if not isinstance(records, list) or max_lines <= 0:
        return payload
    if _workflow_record_snapshot_line_count(payload) <= max_lines:
        payload["item_count"] = len(records)
        return payload

    low = 0
    high = len(records)
    best = 0
    while low <= high:
        mid = (low + high) // 2
        candidate = dict(payload)
        candidate_records = records[:mid]
        candidate["records"] = candidate_records
        candidate["item_count"] = len(candidate_records)
        if _workflow_record_snapshot_line_count(candidate) <= max_lines:
            best = mid
            low = mid + 1
        else:
            high = mid - 1

    limited_payload = dict(payload)
    limited_records = records[:best]
    limited_payload["records"] = limited_records
    limited_payload["item_count"] = len(limited_records)
    return limited_payload


def _workflow_record_snapshot_line_count(payload: dict[str, Any]) -> int:
    return len(json.dumps(payload, ensure_ascii=False, indent=2).splitlines())


def _read_existing_workflow_record_snapshot(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _merge_workflow_record_snapshot_records(
    existing_records: list[dict[str, Any]],
    new_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    existing = [record for record in existing_records if isinstance(record, dict)]
    existing_keys = {key for record in existing for key in duplicate_keys_for_record(record)}
    seen = set(existing_keys)
    prepend_records: list[dict[str, Any]] = []
    for record in new_records:
        if not isinstance(record, dict):
            continue
        keys = duplicate_keys_for_record(record)
        if any(key in seen for key in keys):
            continue
        for key in keys:
            seen.add(key)
        prepend_records.append(record)
    return _sort_parser_api_records_latest_first(prepend_records) + existing


def _sort_parser_api_records_latest_first(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not records or not all(_is_parser_api_record(record) for record in records):
        return records
    indexed_records = [(index, record, _parser_record_datetime(record)) for index, record in enumerate(records)]
    indexed_records.sort(
        key=lambda item: (
            0 if item[2] is not None else 1,
            -(item[2].timestamp() if item[2] is not None else 0),
            item[0],
        )
    )
    return [record for _, record, _ in indexed_records]


def _is_parser_api_record(record: dict[str, Any]) -> bool:
    parser_candidates = [
        record.get("parser_name"),
        record.get("extracts", {}).get("parser_name") if isinstance(record.get("extracts"), dict) else "",
        record.get("extracts", {}).get("source_provider") if isinstance(record.get("extracts"), dict) else "",
        record.get("extracts", {}).get("source_api") if isinstance(record.get("extracts"), dict) else "",
    ]
    for step in record.get("steps") or []:
        if isinstance(step, dict):
            parser_candidates.append(step.get("attr"))
    return any(str(candidate or "").casefold() in SUPPORTED_PARSER_ATTRS for candidate in parser_candidates)


def _parser_record_datetime(record: dict[str, Any]) -> datetime | None:
    for field_path in PARSER_RECORD_DATE_FIELDS:
        value: Any = record
        for key in field_path:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(key)
        parsed = _parse_record_datetime(value)
        if parsed is not None:
            return parsed
    return None


def _parse_record_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    normalized = text
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    try:
        parsed = parsedate_to_datetime(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def _build_existing_workflow_duplicate_indexes(
    output_dir: Path,
    config: dict[str, Any] | None = None,
) -> tuple[set[str], set[str]]:
    all_keys: set[str] = set()
    boundary_keys: set[str] = set()
    if not output_dir.exists():
        return all_keys, boundary_keys
    for path in output_dir.rglob("workflow_records.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        records = payload.get("records") if isinstance(payload, dict) else []
        if not isinstance(records, list):
            continue
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                continue
            keys = duplicate_keys_for_record(_record_for_duplicate_index(config, record))
            for key in keys:
                all_keys.add(key)
            if index == 0:
                for key in keys:
                    boundary_keys.add(key)
    return all_keys, boundary_keys


def _build_existing_workflow_duplicate_index(output_dir: Path) -> set[str]:
    all_keys, _ = _build_existing_workflow_duplicate_indexes(output_dir)
    return all_keys


def _record_for_duplicate_index(config: dict[str, Any] | None, record: dict[str, Any]) -> dict[str, Any]:
    if config is None:
        return record
    prepared = dict(record)
    prepared["final_url"] = _record_final_url(config, prepared)
    return prepared


def _build_direct_workflow_record_policy(output_dir: Path, config: dict[str, Any], state: dict[str, Any]) -> RecordPolicy:
    previous_duplicate_index, boundary_duplicate_index = _build_existing_workflow_duplicate_indexes(output_dir, config)
    latest_duplicate_index = build_latest_duplicate_index([output_dir], config)
    filter_terms = _config_filter_terms(config)
    same_run_seen: set[str] = set()
    state["previous_duplicate_index_count"] = len(previous_duplicate_index)
    state["previous_boundary_duplicate_index_count"] = len(boundary_duplicate_index)
    state["latest_duplicate_index_count"] = len(latest_duplicate_index.all_keys)
    state["same_run_duplicate_skipped_count"] = 0
    state["latest_cross_group_duplicate_skipped_count"] = 0

    def record_policy(record: dict[str, Any]) -> dict[str, Any]:
        keys = duplicate_keys_for_record(record)
        if latest_duplicate_index.has_records:
            latest_decision = latest_duplicate_decision_for_record(record, latest_duplicate_index, filter_terms=filter_terms)
            if latest_decision is not None:
                if not latest_decision.get("stop"):
                    state["latest_cross_group_duplicate_skipped_count"] = (
                        int(state.get("latest_cross_group_duplicate_skipped_count") or 0) + 1
                    )
                return latest_decision
        else:
            boundary_duplicate_key = next((key for key in keys if key in boundary_duplicate_index), "")
            if boundary_duplicate_key:
                return {
                    "include": False,
                    "stop": True,
                    "reason": "duplicate_boundary_stopped",
                    "metadata": {
                        "duplicate_key": boundary_duplicate_key,
                        "stop_scope": _duplicate_stop_scope_for_record(record),
                        "boundary": True,
                    },
                }

            duplicate_key = next((key for key in keys if key in previous_duplicate_index), "")
            if duplicate_key:
                return {
                    "include": False,
                    "stop": True,
                    "reason": "duplicate_stopped",
                    "metadata": {"duplicate_key": duplicate_key, "stop_scope": _duplicate_stop_scope_for_record(record)},
                }

        same_run_duplicate_key = next((key for key in keys if key in same_run_seen), "")
        if same_run_duplicate_key:
            state["same_run_duplicate_skipped_count"] = int(state.get("same_run_duplicate_skipped_count") or 0) + 1
            return {
                "include": False,
                "stop": False,
                "reason": "same_run_duplicate_skipped",
                "metadata": {"duplicate_key": same_run_duplicate_key},
            }

        for key in keys:
            same_run_seen.add(key)
        return {"include": True, "stop": False}

    return record_policy


def _run_parser_workflow(
    execution: WorkflowExecution,
    config: dict[str, Any],
    parser_name: str,
    timeout_ms: int,
    record_policy: RecordPolicy | None = None,
) -> None:
    if parser_name not in SUPPORTED_PARSER_ATTRS:
        raise RuntimeError(f"Unsupported parser attr: {parser_name}")

    search_terms = _config_search_terms(config)
    steps = config.get("steps") or []
    parser_step = next((step for step in steps if isinstance(step, dict)), None)
    if not isinstance(parser_step, dict):
        raise RuntimeError("Parser workflow requires at least one step.")

    effective_terms = search_terms or [None]
    total_items = 0
    item_limit = _step_loop_limit(parser_step)
    existing_duplicate_index: set[str] = set()
    boundary_duplicate_index: set[str] = set()
    latest_duplicate_index = LatestDuplicateIndex()
    filter_terms = _config_filter_terms(config)
    if record_policy is None:
        existing_duplicate_index, boundary_duplicate_index = _build_existing_workflow_duplicate_indexes(execution.output_dir, config)
        latest_duplicate_index = build_latest_duplicate_index([execution.output_dir], config)
    same_run_seen: set[str] = set()
    same_run_duplicate_skipped_count = 0
    latest_cross_group_duplicate_skipped_count = 0
    for search_term_index, search_term in enumerate(effective_terms):
        term_output_dir = _search_term_output_dir(
            execution.output_dir,
            search_term,
            search_term_index,
            len(effective_terms),
        )
        source_url = _render_template_value(str(config["start_url"]), search_term, url_encode=True)
        items, final_url = _fetch_parser_items(
            parser_name,
            source_url,
            timeout=timeout_ms / 1000,
            item_limit=item_limit,
        )
        if item_limit is not None:
            items = items[:item_limit]
        accepted_items: list[dict[str, Any]] = []
        accepted_records: list[dict[str, Any]] = []
        stop_exc: WorkflowRecordPolicyStop | None = None
        for item_index, item in enumerate(items):
            record_key = _build_record_key(search_term_index, item_index)
            record = _build_parser_record(
                parser_name=parser_name,
                parser_step=parser_step,
                item=item,
                item_index=item_index,
                record_key=record_key,
                search_term=search_term,
                search_term_index=search_term_index,
                search_term_count=len(effective_terms),
                rss_url=source_url,
                final_url=final_url,
                output_file="",
            )
            _apply_stable_record_key(record, config)
            if record_policy is None:
                keys = duplicate_keys_for_record(record)
                if latest_duplicate_index.has_records:
                    latest_decision = latest_duplicate_decision_for_record(record, latest_duplicate_index, filter_terms=filter_terms)
                    if latest_decision is not None:
                        if latest_decision.get("stop"):
                            stop_exc = WorkflowRecordPolicyStop(
                                reason=str(latest_decision.get("reason") or "duplicate_boundary_stopped"),
                                metadata=dict(latest_decision.get("metadata") or {}),
                                records=accepted_records,
                            )
                            break
                        latest_cross_group_duplicate_skipped_count += 1
                        continue
                else:
                    boundary_duplicate_key = next((key for key in keys if key in boundary_duplicate_index), "")
                    if boundary_duplicate_key:
                        stop_exc = WorkflowRecordPolicyStop(
                            reason="duplicate_boundary_stopped",
                            metadata={
                                "duplicate_key": boundary_duplicate_key,
                                "stop_scope": _duplicate_stop_scope_for_record(record),
                                "boundary": True,
                            },
                            records=accepted_records,
                        )
                        break
                    duplicate_key = next((key for key in keys if key in existing_duplicate_index), "")
                    if duplicate_key:
                        stop_exc = WorkflowRecordPolicyStop(
                            reason="duplicate_stopped",
                            metadata={"duplicate_key": duplicate_key, "stop_scope": _duplicate_stop_scope_for_record(record)},
                            records=accepted_records,
                        )
                        break
                same_run_duplicate_key = next((key for key in keys if key in same_run_seen), "")
                if same_run_duplicate_key:
                    same_run_duplicate_skipped_count += 1
                    continue
                for key in keys:
                    same_run_seen.add(key)
                include, stop, reason, metadata = True, False, "record_policy_stopped", {}
            else:
                include, stop, reason, metadata = _record_policy_decision(record_policy, record)
            if include:
                accepted_items.append(item)
                accepted_records.append(record)
            if stop:
                stop_exc = WorkflowRecordPolicyStop(reason=reason, metadata=metadata, records=accepted_records)
                break

        total_items += len(accepted_items)
        output_path: Path | None = None
        if accepted_items:
            output_path = _save_parser_items(
                parser_name=parser_name,
                output_dir=term_output_dir,
                search_term=search_term,
                source_url=source_url,
                final_url=final_url,
                items=accepted_items,
            )
            _assign_parser_record_output_files(accepted_records, output_path)
            _rename_parser_record_output_files(accepted_records, output_path)
            execution.extracted_files.append(str(output_path))
        execution.diagnostics.setdefault("search_term_runs", []).append(
            {
                "search_term_index": search_term_index,
                "search_term": search_term,
                "item_count": len(accepted_items),
                "empty": len(accepted_items) == 0,
                "rss_url": source_url,
                "api_url": source_url if parser_name in {DAUM_NEWS_API_ATTR, NAVER_NEWS_API_ATTR} else "",
                "final_url": final_url,
                "output_file": str(output_path) if output_path is not None else "",
                "fetched_item_count": len(items),
            }
        )
        execution.records.extend(accepted_records)
        if stop_exc is not None:
            _mark_record_policy_stop(execution, stop_exc)
            if _stop_remaining_search_terms(stop_exc):
                break
            continue

    execution.diagnostics["parser_item_count"] = total_items
    if same_run_duplicate_skipped_count:
        execution.diagnostics["same_run_duplicate_skipped_count"] = (
            int(execution.diagnostics.get("same_run_duplicate_skipped_count") or 0) + same_run_duplicate_skipped_count
        )
    if latest_cross_group_duplicate_skipped_count:
        execution.diagnostics["latest_cross_group_duplicate_skipped_count"] = (
            int(execution.diagnostics.get("latest_cross_group_duplicate_skipped_count") or 0)
            + latest_cross_group_duplicate_skipped_count
        )


def _build_parser_record(
    *,
    parser_name: str,
    parser_step: dict[str, Any],
    item: dict[str, Any],
    item_index: int,
    record_key: str,
    search_term: str | None,
    search_term_index: int,
    search_term_count: int,
    rss_url: str,
    final_url: str,
    output_file: str,
) -> dict[str, Any]:
    title = str(item.get("title") or item.get("detail_url") or item.get("link") or "")
    step_log: dict[str, Any] = {
        "index": 1,
        "name": parser_step.get("name") or f"{parser_name}_parser",
        "record_key": record_key,
        "item_index": item_index,
        "search_term": search_term,
        "search_term_index": search_term_index,
        "search_term_count": search_term_count,
        "xpath": "",
        "resolved_xpath": "",
        "action": "parser",
        "open_mode": "",
        "loop": False,
        "attr": parser_name,
        "value": title,
        "xpath_2": "",
        "loop_limit": _step_loop_limit(parser_step),
        "exclude_xpath": "",
        "wait_state": "",
        "wait_timeout_ms": 0,
        "url_before": rss_url,
        "url_after": final_url,
        "matched_count": 1,
        "duration_seconds": 0,
        "success": True,
        "error": None,
        "downloaded_files": [],
    }
    return {
        "record_key": record_key,
        "item_index": item_index,
        "search_term": search_term,
        "search_term_index": search_term_index,
        "search_term_count": search_term_count,
        "success": True,
        "steps": [step_log],
        "extracts": dict(item),
        "downloaded_files": [],
        "extracted_files": [],
        "output_file": output_file,
        "error": None,
        "start_url": rss_url,
        "final_url": final_url,
        "parser_name": parser_name,
    }


def _preview_parser_workflow(config: dict[str, Any], parser_name: str, timeout: int) -> dict[str, Any]:
    search_terms = _config_search_terms(config)
    effective_terms = search_terms or [None]
    start_url = str(config["start_url"])
    search_term_runs: list[dict[str, Any]] = []
    total_count = 0
    steps = config.get("steps") or []
    parser_step = next((step for step in steps if isinstance(step, dict)), {})
    item_limit = _step_loop_limit(parser_step)

    for search_term_index, search_term in enumerate(effective_terms):
        source_url = _render_template_value(start_url, search_term, url_encode=True)
        items, final_url = _fetch_parser_items(parser_name, source_url, timeout=timeout, item_limit=item_limit)
        if item_limit is not None:
            items = items[:item_limit]
        total_count += len(items)
        search_term_runs.append(
            {
                "search_term_index": search_term_index,
                "search_term": search_term,
                "item_count": len(items),
                "empty": len(items) == 0,
                "rss_url": source_url,
                "api_url": source_url if parser_name in {DAUM_NEWS_API_ATTR, NAVER_NEWS_API_ATTR} else "",
                "final_url": final_url,
            }
        )

    first_step = (config.get("steps") or [{}])[0]
    return {
        "start_url": start_url,
        "search_terms": search_terms,
        "search_term_count": len(effective_terms),
        "parser_name": parser_name,
        "parser_enabled": True,
        "parser_item_count": total_count,
        "search_term_runs": search_term_runs,
        "step_counts": [
            {
                "name": first_step.get("name") or "parser",
                "xpath": "",
                "action": "parser",
                "wait_state": "auto",
                "loop_limit": item_limit,
                "count": total_count,
                "error": None,
            }
        ],
    }


def _record_policy_decision(record_policy: RecordPolicy | None, record: dict[str, Any]) -> tuple[bool, bool, str, dict[str, Any]]:
    if record_policy is None:
        return True, False, "", {}

    decision = record_policy(record)
    if decision is None:
        return True, False, "", {}
    if isinstance(decision, bool):
        return decision, not decision, "record_policy_stopped", {}
    if isinstance(decision, dict):
        include = bool(decision.get("include", True))
        stop = bool(decision.get("stop", False))
        reason = str(decision.get("reason") or "record_policy_stopped")
        metadata = decision.get("metadata")
        return include, stop, reason, metadata if isinstance(metadata, dict) else {}

    return bool(decision), False, "", {}


def _append_record(records: list[dict[str, Any]], record: dict[str, Any], record_policy: RecordPolicy | None) -> bool:
    include, stop, reason, metadata = _record_policy_decision(record_policy, record)
    if include:
        records.append(record)
    if stop:
        raise WorkflowRecordPolicyStop(
            reason=reason,
            metadata=metadata,
            records=list(records),
            generated_files=_record_generated_files(record),
        )
    return include


def _append_execution_record(
    execution: WorkflowExecution,
    record: dict[str, Any],
    record_policy: RecordPolicy | None,
) -> bool:
    execution.generated_files.extend(record.get("downloaded_files", []))
    execution.generated_files.extend(record.get("extracted_files", []))
    return _append_record(execution.records, record, record_policy)


def _mark_record_policy_stop(execution: WorkflowExecution, exc: WorkflowRecordPolicyStop) -> None:
    execution.generated_files.extend(exc.generated_files)
    for record in exc.records:
        if record not in execution.records:
            execution.records.append(record)
            execution.downloaded_files.extend(record.get("downloaded_files", []))
            execution.extracted_files.extend(record.get("extracted_files", []))
            execution.generated_files.extend(_record_generated_files(record))
    execution.diagnostics["record_policy_stopped"] = True
    execution.diagnostics["record_policy_stop_reason"] = exc.reason
    execution.diagnostics["record_policy_stop_metadata"] = exc.metadata


def _record_generated_files(record: dict[str, Any]) -> list[str]:
    files: list[str] = []
    for key in ("downloaded_files", "extracted_files"):
        raw = record.get(key)
        if isinstance(raw, list):
            files.extend(str(value) for value in raw if value)
    output_file = record.get("output_file")
    if output_file:
        files.append(str(output_file))
    return files


def _run_nested_click_loops(
    browser: Any,
    config: dict[str, Any],
    search_term: str | None,
    search_term_index: int,
    search_term_count: int,
    output_dir: Path,
    timeout_ms: int,
    step_wait_ms: int,
    parse_pause_seconds: int,
    page_loop_step_index: int,
    item_loop_step_index: int,
    record_policy: RecordPolicy | None = None,
) -> list[dict[str, Any]]:
    steps = config.get("steps") or []
    page_loop_step = steps[page_loop_step_index - 1]
    item_loop_step = steps[item_loop_step_index - 1]
    page_loop_spec = _build_board_loop_spec(str(page_loop_step.get("xpath") or ""), str(page_loop_step.get("xpath_2") or ""))
    item_loop_spec = _build_board_loop_spec(str(item_loop_step.get("xpath") or ""), str(item_loop_step.get("xpath_2") or ""))
    if page_loop_spec is None or item_loop_spec is None:
        return []

    prefix_steps = steps[: page_loop_step_index - 1]
    page_count = _resolve_page_loop_count(
        browser=browser,
        config=config,
        prefix_steps=prefix_steps,
        page_loop_spec=page_loop_spec,
        search_term=search_term,
        search_term_index=search_term_index,
        search_term_count=search_term_count,
        output_dir=output_dir,
        timeout_ms=timeout_ms,
        step_wait_ms=step_wait_ms,
        parse_pause_seconds=parse_pause_seconds,
        page_loop_step_index=page_loop_step_index,
    )
    page_limit = _step_loop_limit(page_loop_step)
    if page_limit is not None:
        page_count = min(page_count, page_limit)

    records: list[dict[str, Any]] = []
    for page_index in range(page_count):
        page = _new_workflow_page(browser)
        try:
            page.goto(
                _render_template_value(str(config["start_url"]), search_term, url_encode=True),
                wait_until="domcontentloaded",
                timeout=timeout_ms,
            )
            for step_index, step in enumerate(prefix_steps, start=1):
                step_log, next_page = _run_step(
                    page,
                    None,
                    step,
                    step_index,
                    output_dir,
                    timeout_ms,
                    step_wait_ms,
                    None,
                    search_term=search_term,
                    search_term_index=search_term_index,
                    search_term_count=search_term_count,
                    primary_loop_step_index=page_loop_step_index,
                    parse_pause_seconds=parse_pause_seconds,
                )
                if next_page is not page and step_log.get("open_mode") != "popup":
                    page.close()
                    page = next_page
                elif next_page is not page:
                    page = next_page
                if not step_log["success"]:
                    raise RuntimeError(step_log["error"])

            page_loop_step_log, next_page = _run_step(
                page,
                None,
                page_loop_step,
                page_loop_step_index,
                output_dir,
                timeout_ms,
                step_wait_ms,
                page_index,
                search_term=search_term,
                search_term_index=search_term_index,
                search_term_count=search_term_count,
                board_loop_spec=page_loop_spec,
                primary_loop_step_index=page_loop_step_index,
                parse_pause_seconds=parse_pause_seconds,
            )
            if next_page is not page and page_loop_step_log.get("open_mode") != "popup":
                page.close()
                page = next_page
            elif next_page is not page:
                page = next_page
            if not page_loop_step_log["success"]:
                raise RuntimeError(page_loop_step_log["error"])

            listing_url = page.url
            item_exclude_xpath = str(item_loop_step.get("exclude_xpath") or "").strip()
            item_numbers = _resolve_board_loop_item_numbers(page, item_loop_spec, exclude_xpath=item_exclude_xpath)
            item_limit = _step_loop_limit(item_loop_step)
            if item_limit is not None:
                item_numbers = item_numbers[:item_limit]
        finally:
            page.close()

        if not item_numbers:
            continue

        for item_index, item_number in enumerate(item_numbers):
            record = _run_one_item(
                browser,
                config,
                item_index,
                timeout_ms,
                step_wait_ms,
                parse_pause_seconds=parse_pause_seconds,
                search_term=search_term,
                search_term_index=search_term_index,
                search_term_count=search_term_count,
                output_dir_override=output_dir,
                primary_loop_step_index=item_loop_step_index,
                start_url_override=listing_url,
                start_step_index=item_loop_step_index,
                board_loop_spec=item_loop_spec,
                board_item_number=item_number,
            )
            record["steps"].insert(0, dict(page_loop_step_log))
            _append_record(records, record, record_policy)

    return records


def _run_nested_pagination_click_loops(
    browser: Any,
    config: dict[str, Any],
    search_term: str | None,
    search_term_index: int,
    search_term_count: int,
    output_dir: Path,
    timeout_ms: int,
    step_wait_ms: int,
    parse_pause_seconds: int,
    page_loop_step_index: int,
    item_loop_step_index: int,
    record_policy: RecordPolicy | None = None,
) -> list[dict[str, Any]]:
    steps = config.get("steps") or []
    page_loop_step = steps[page_loop_step_index - 1]
    item_loop_step = steps[item_loop_step_index - 1]
    page_pagination_spec = _config_primary_pagination_spec(config)
    item_loop_spec = _build_board_loop_spec(str(item_loop_step.get("xpath") or ""), str(item_loop_step.get("xpath_2") or ""))
    if page_pagination_spec is None or item_loop_spec is None:
        return []

    prefix_steps = steps[: page_loop_step_index - 1]
    page_numbers = _resolve_item_numbers_for_term(
        browser=browser,
        config=config,
        search_term=search_term,
        search_term_index=search_term_index,
        search_term_count=search_term_count,
        output_dir=output_dir,
        timeout_ms=timeout_ms,
        step_wait_ms=step_wait_ms,
        parse_pause_seconds=parse_pause_seconds,
        primary_loop_step_index=page_loop_step_index,
        primary_loop_spec=None,
        primary_pagination_spec=page_pagination_spec,
        board_repeat_spec=None,
        configured_repeat=False,
    )
    page_limit = _step_loop_limit(page_loop_step)
    if page_limit is not None:
        page_numbers = page_numbers[:page_limit]

    records: list[dict[str, Any]] = []
    for page_index, page_number in enumerate(page_numbers):
        page = _new_workflow_page(browser)
        try:
            page.goto(
                _render_template_value(str(config["start_url"]), search_term, url_encode=True),
                wait_until="domcontentloaded",
                timeout=timeout_ms,
            )
            for step_index, step in enumerate(prefix_steps, start=1):
                step_log, next_page = _run_step(
                    page,
                    None,
                    step,
                    step_index,
                    output_dir,
                    timeout_ms,
                    step_wait_ms,
                    None,
                    search_term=search_term,
                    search_term_index=search_term_index,
                    search_term_count=search_term_count,
                    primary_loop_step_index=page_loop_step_index,
                    parse_pause_seconds=parse_pause_seconds,
                )
                if next_page is not page and step_log.get("open_mode") != "popup":
                    page.close()
                    page = next_page
                elif next_page is not page:
                    page = next_page
                if not step_log["success"]:
                    raise RuntimeError(step_log["error"])

            page_loop_step_log, next_page = _run_step(
                page,
                None,
                page_loop_step,
                page_loop_step_index,
                output_dir,
                timeout_ms,
                step_wait_ms,
                page_index,
                search_term=search_term,
                search_term_index=search_term_index,
                search_term_count=search_term_count,
                board_pagination_spec=page_pagination_spec,
                primary_loop_step_index=page_loop_step_index,
                board_page_number=page_number,
                parse_pause_seconds=parse_pause_seconds,
            )
            if next_page is not page and page_loop_step_log.get("open_mode") != "popup":
                page.close()
                page = next_page
            elif next_page is not page:
                page = next_page
            if not page_loop_step_log["success"]:
                raise RuntimeError(page_loop_step_log["error"])

            listing_url = page.url
            item_exclude_xpath = str(item_loop_step.get("exclude_xpath") or "").strip()
            item_numbers = _resolve_board_loop_item_numbers(page, item_loop_spec, exclude_xpath=item_exclude_xpath)
            item_limit = _step_loop_limit(item_loop_step)
            if item_limit is not None:
                item_numbers = item_numbers[:item_limit]
        finally:
            page.close()

        if not item_numbers:
            continue

        for item_index, item_number in enumerate(item_numbers):
            record = _run_one_item(
                browser,
                config,
                item_index,
                timeout_ms,
                step_wait_ms,
                parse_pause_seconds=parse_pause_seconds,
                search_term=search_term,
                search_term_index=search_term_index,
                search_term_count=search_term_count,
                output_dir_override=output_dir,
                primary_loop_step_index=item_loop_step_index,
                start_url_override=listing_url,
                start_step_index=item_loop_step_index,
                board_loop_spec=item_loop_spec,
                board_item_number=item_number,
            )
            record["steps"].insert(0, dict(page_loop_step_log))
            _append_record(records, record, record_policy)

    return records


def _resolve_page_loop_count(
    browser: Any,
    config: dict[str, Any],
    prefix_steps: list[dict[str, Any]],
    page_loop_spec: BoardLoopSpec,
    search_term: str | None,
    search_term_index: int,
    search_term_count: int,
    output_dir: Path,
    timeout_ms: int,
    step_wait_ms: int,
    parse_pause_seconds: int,
    page_loop_step_index: int,
) -> int:
    page = _new_workflow_page(browser)
    try:
        page.goto(
            _render_template_value(str(config["start_url"]), search_term, url_encode=True),
            wait_until="domcontentloaded",
            timeout=timeout_ms,
        )
        for step_index, step in enumerate(prefix_steps, start=1):
            step_log, next_page = _run_step(
                page,
                None,
                step,
                step_index,
                output_dir,
                timeout_ms,
                step_wait_ms,
                None,
                search_term=search_term,
                search_term_index=search_term_index,
                search_term_count=search_term_count,
                primary_loop_step_index=page_loop_step_index,
                parse_pause_seconds=parse_pause_seconds,
            )
            if next_page is not page and step_log.get("open_mode") != "popup":
                page.close()
                page = next_page
            elif next_page is not page:
                page = next_page
            if not step_log["success"]:
                raise RuntimeError(step_log["error"])
        return _resolve_board_loop_items(page, page_loop_spec)
    finally:
        page.close()


def _run_one_item(
    browser: Any,
    config: dict[str, Any],
    item_index: int | None,
    timeout_ms: int,
    step_wait_ms: int,
    board_loop_spec: BoardLoopSpec | None = None,
    board_pagination_spec: PaginationLoopSpec | None = None,
    board_repeat_spec: BoardRepeatSpec | None = None,
    search_term: str | None = None,
    search_term_index: int | None = None,
    search_term_count: int | None = None,
    output_dir_override: Path | None = None,
    primary_loop_step_index: int | None = None,
    board_item_number: int | None = None,
    board_page_number: int | None = None,
    start_url_override: str | None = None,
    start_step_index: int = 1,
    parse_pause_seconds: int = 0,
) -> dict[str, Any]:
    page = _new_workflow_page(browser)
    output_dir = output_dir_override or Path(config["output_dir"])
    board = config.get("board") or {}
    start_url = str(start_url_override or _render_template_value(str(config["start_url"]), search_term, url_encode=True))
    record_key = _build_record_key(search_term_index, item_index)
    record: dict[str, Any] = {
        "record_key": record_key,
        "item_index": item_index,
        "search_term": search_term,
        "search_term_index": search_term_index,
        "search_term_count": search_term_count,
        "success": True,
        "steps": [],
        "extracts": {},
        "downloaded_files": [],
        "extracted_files": [],
        "error": None,
        "start_url": start_url,
        "final_url": None,
    }

    try:
        page.goto(start_url, wait_until="domcontentloaded", timeout=timeout_ms)
        scope = None
        for step_index, step in enumerate(config["steps"][start_step_index - 1 :], start=start_step_index):
            step_item_index = item_index if item_index is not None and step_index == primary_loop_step_index else None
            step_board_item_number = board_item_number if board_item_number is not None and step_index == primary_loop_step_index else None
            if step_item_index is not None:
                if board_loop_spec is not None:
                    item_number = step_board_item_number if step_board_item_number is not None else board_loop_spec.start_index + step_item_index
                    scope = page.locator(f"xpath={board_loop_spec.render_item_root_xpath(item_number)}")
                elif board_pagination_spec is not None:
                    scope = None
                else:
                    scope, board_repeat_spec = _select_board_item_scope(
                        page,
                        str(board["list_xpath"]),
                        step_item_index,
                        board_repeat_spec=board_repeat_spec,
                        strict_repeat_spec=bool(str(board.get("item_tag") or "").strip() or str(board.get("item_xpath") or "").strip()),
                    )
            step_log, next_page = _run_step(
                page,
                scope,
                step,
                step_index,
                output_dir,
                timeout_ms,
                step_wait_ms,
                board_item_number=step_board_item_number,
                item_index=step_item_index,
                board_list_xpath=str(board["list_xpath"]) if board_repeat_spec else None,
                board_loop_spec=board_loop_spec,
                board_pagination_spec=board_pagination_spec,
                board_repeat_spec=board_repeat_spec,
                search_term=search_term,
                search_term_index=search_term_index,
                search_term_count=search_term_count,
                primary_loop_step_index=primary_loop_step_index,
                board_page_number=board_page_number if step_index == primary_loop_step_index else None,
                parse_pause_seconds=parse_pause_seconds,
                record_key=record_key,
            )
            if next_page is not page and step_log.get("open_mode") != "popup":
                page.close()
                page = next_page
            elif next_page is not page:
                page = next_page
            record["steps"].append(step_log)
            if step_log.get("extract_name"):
                record["extracts"][step_log["extract_name"]] = step_log.get("value")
            if step_log.get("extracted_files"):
                record["extracted_files"].extend(step_log["extracted_files"])
            if step_log.get("downloaded_files"):
                record["downloaded_files"].extend(step_log["downloaded_files"])
            elif step_log.get("downloaded_file"):
                record["downloaded_files"].append(step_log["downloaded_file"])
            if not step_log["success"]:
                raise RuntimeError(step_log["error"])
            if step["action"] in {"click", "goto"}:
                scope = None
    except Exception as exc:
        record["success"] = False
        record["error"] = str(exc)
    finally:
        record["final_url"] = canonicalize_article_url(
            page.url,
            page_query_params=_config_search_term_query_params(config, str(search_term or "")),
        )
        _apply_stable_record_key(record, config, rename_files=True)
        page.close()

    return record


def _run_step(
    page: Any,
    scope: Any,
    step: dict[str, Any],
    step_index: int,
    output_dir: Path,
    timeout_ms: int,
    step_wait_ms: int,
    item_index: int | None,
    board_item_number: int | None = None,
    board_list_xpath: str | None = None,
    board_loop_spec: BoardLoopSpec | None = None,
    board_pagination_spec: PaginationLoopSpec | None = None,
    board_repeat_spec: BoardRepeatSpec | None = None,
    search_term: str | None = None,
    search_term_index: int | None = None,
    search_term_count: int | None = None,
    primary_loop_step_index: int | None = None,
    board_page_number: int | None = None,
    parse_pause_seconds: int = 0,
    record_key: str | None = None,
) -> tuple[dict[str, Any], Any]:
    action = str(step["action"])
    open_mode = _step_open_mode(step) if action == "click" else "same_tab"
    step_has_loop = bool(step.get("loop"))
    loop_enabled = bool(step_has_loop and primary_loop_step_index is not None and step_index != primary_loop_step_index)
    loop_spec = _build_board_loop_spec(str(step["xpath"]), str(step.get("xpath_2") or "")) if step_has_loop else None
    loop_limit = _step_loop_limit(step) if step_has_loop else None
    loop_mode = _step_loop_mode(step) if step_has_loop else "items"
    if step_has_loop and loop_spec is None:
        if loop_mode != "pagination":
            raise RuntimeError("Loop step requires two anchor XPaths that differ by one repeating index.")
    if loop_enabled and action not in {"download", "extract"}:
        raise RuntimeError("Loop step is only supported for download or extract.")
    exclude_xpath = str(step.get("exclude_xpath") or "").strip()
    step_item_index: int | None = None
    step_item_tag: str | None = None
    step_list_xpath = board_list_xpath
    step_start_index = 1
    if item_index is not None and step_index == primary_loop_step_index:
        if board_loop_spec is not None:
            step_item_index = item_index
            step_list_xpath = board_loop_spec.root_xpath
            step_start_index = board_loop_spec.start_index
        elif board_repeat_spec is not None:
            step_item_index = item_index
            step_item_tag = board_repeat_spec.item_tag
    xpath = _resolve_step_xpath(
        str(step["xpath"]),
        step_item_index,
        step_item_tag,
        step_list_xpath,
        start_index=step_start_index,
        board_loop_spec=board_loop_spec,
        board_item_number=board_item_number,
    )
    attr = step.get("attr")
    wait_timeout_ms = int(step.get("wait_timeout_ms") or step_wait_ms)
    wait_state = _step_wait_state(step)
    started = time.monotonic()
    step_log: dict[str, Any] = {
        "index": step_index,
        "name": step.get("name") or f"step_{step_index}",
        "record_key": record_key or _build_record_key(search_term_index, item_index),
        "item_index": item_index,
        "search_term": search_term,
        "search_term_index": search_term_index,
        "search_term_count": search_term_count,
        "xpath": xpath,
        "resolved_xpath": xpath,
        "action": action,
        "open_mode": open_mode,
        "loop": step_has_loop,
        "loop_mode": loop_mode if step_has_loop else "",
        "attr": attr or "",
        "xpath_2": step.get("xpath_2") or "",
        "loop_limit": loop_limit,
        "exclude_xpath": exclude_xpath,
        "wait_state": wait_state,
        "wait_timeout_ms": wait_timeout_ms,
        "url_before": page.url,
        "url_after": None,
        "matched_count": 0,
        "duration_seconds": 0,
        "success": False,
        "error": None,
        "downloaded_files": [],
    }

    active_page = page
    try:
        if step_has_loop and loop_mode == "pagination" and board_pagination_spec is not None and step_index == primary_loop_step_index:
            target_page_number = int(board_page_number or 1)
            step_log["pagination_mode"] = board_pagination_spec.pagination_mode
            step_log["pagination_target_page"] = target_page_number
            if target_page_number <= 1:
                step_log["success"] = True
                step_log["url_after"] = active_page.url
                step_log["duration_seconds"] = round(time.monotonic() - started, 3)
                return step_log, active_page

            resolved_xpath = board_pagination_spec.render_xpath(target_page_number)
            step_log["resolved_xpath"] = resolved_xpath
            click_count = 1 if board_pagination_spec.pagination_mode == "page_number" else max(target_page_number - 1, 1)
            for _ in range(click_count):
                locator_group = _locator(page, scope, resolved_xpath)
                if wait_state not in {"hidden", "detached"}:
                    try:
                        locator_group.first.wait_for(state=wait_state, timeout=wait_timeout_ms)
                    except Exception:
                        pass
                locators = _filtered_locators(locator_group, exclude_xpath)
                if not locators:
                    raise RuntimeError("No elements matched after applying exclude_xpath.")
                locator = locators[0]
                locator.wait_for(state=wait_state, timeout=wait_timeout_ms)
                step_log["matched_count"] = len(locators)
                if action != "click":
                    raise RuntimeError("Pagination loop is only supported for click steps.")
                if open_mode == "popup":
                    with page.expect_popup(timeout=timeout_ms) as popup_info:
                        locator.click(timeout=timeout_ms)
                    active_page = popup_info.value
                    _attach_dialog_handler(active_page)
                    try:
                        active_page.wait_for_load_state("domcontentloaded", timeout=wait_timeout_ms)
                    except Exception:
                        pass
                elif open_mode == "auto" and _locator_targets_new_tab(locator):
                    with page.expect_popup(timeout=timeout_ms) as popup_info:
                        locator.click(timeout=timeout_ms)
                    active_page = popup_info.value
                    _attach_dialog_handler(active_page)
                    try:
                        active_page.wait_for_load_state("domcontentloaded", timeout=wait_timeout_ms)
                    except Exception:
                        pass
                else:
                    locator.click(timeout=timeout_ms)
                    _wait_after_action(page, timeout_ms)
            step_log["success"] = True
            step_log["url_after"] = active_page.url
            step_log["duration_seconds"] = round(time.monotonic() - started, 3)
            return step_log, active_page

        if loop_enabled and loop_spec is not None:
            if action == "download":
                downloaded_paths = _download_loop_step(
                    page,
                    step,
                    output_dir,
                    timeout_ms,
                    loop_spec,
                    exclude_xpath=exclude_xpath,
                    record_key=step_log["record_key"],
                    step_index=step_index,
                )
                step_log["matched_count"] = len(downloaded_paths)
                step_log["downloaded_files"] = [str(path) for path in downloaded_paths]
                step_log["downloaded_file"] = step_log["downloaded_files"][0] if step_log["downloaded_files"] else None
            elif action == "extract":
                if parse_pause_seconds > 0:
                    time.sleep(parse_pause_seconds)
                step_log["parse_pause_seconds"] = parse_pause_seconds
                extracted_values, extracted_paths = _extract_loop_step(
                    page,
                    step,
                    step_index,
                    output_dir,
                    loop_spec,
                    exclude_xpath=exclude_xpath,
                    record_key=step_log["record_key"],
                )
                step_log["matched_count"] = len(extracted_values)
                step_log["extract_name"] = step.get("name") or f"step_{step_index}"
                step_log["value"] = extracted_values
                step_log["extracted_files"] = [str(path) for path in extracted_paths]
                step_log["extracted_file"] = step_log["extracted_files"][0] if step_log["extracted_files"] else None
            step_log["success"] = True
            return step_log, active_page

        locator_group = _locator(page, scope, xpath)
        if wait_state not in {"hidden", "detached"}:
            try:
                locator_group.first.wait_for(state=wait_state, timeout=wait_timeout_ms)
            except Exception:
                pass
        locators = _filtered_locators(locator_group, exclude_xpath)
        if not locators:
            if wait_state not in {"hidden", "detached"}:
                try:
                    locator_group.first.wait_for(state=wait_state, timeout=wait_timeout_ms)
                except Exception:
                    pass
                locators = _filtered_locators(locator_group, exclude_xpath)
        if not locators:
            raise RuntimeError("No elements matched after applying exclude_xpath.")
        locator = locators[0]
        locator.wait_for(state=wait_state, timeout=wait_timeout_ms)
        step_log["matched_count"] = len(locators)

        if action == "click":
            if open_mode == "popup":
                with page.expect_popup(timeout=timeout_ms) as popup_info:
                    locator.click(timeout=timeout_ms)
                active_page = popup_info.value
                _attach_dialog_handler(active_page)
                try:
                    active_page.wait_for_load_state("domcontentloaded", timeout=wait_timeout_ms)
                except Exception:
                    pass
            elif open_mode == "auto" and _locator_targets_new_tab(locator):
                with page.expect_popup(timeout=timeout_ms) as popup_info:
                    locator.click(timeout=timeout_ms)
                active_page = popup_info.value
                _attach_dialog_handler(active_page)
                try:
                    active_page.wait_for_load_state("domcontentloaded", timeout=wait_timeout_ms)
                except Exception:
                    pass
            else:
                locator.click(timeout=timeout_ms)
                _wait_after_action(page, timeout_ms)
        elif action == "goto":
            target_url = _step_url(page, locator, step)
            page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
            step_log["value"] = target_url
        elif action == "download":
            downloaded_path = _download_step(
                page,
                locator,
                step,
                output_dir,
                timeout_ms,
                record_key=step_log["record_key"],
                step_index=step_index,
            )
            step_log["downloaded_file"] = str(downloaded_path)
        elif action == "extract":
            if parse_pause_seconds > 0:
                time.sleep(parse_pause_seconds)
            step_log["parse_pause_seconds"] = parse_pause_seconds
            value = _step_value(locator, step)
            extracted_paths = _save_extract_outputs(
                output_dir,
                item_index,
                step_index,
                step,
                value,
                page_title=_page_title(page),
                is_html=str(step.get("attr") or "").lower() == "html",
                record_key=step_log["record_key"],
            )
            step_log["extract_name"] = step.get("name") or f"step_{step_index}"
            step_log["value"] = value
            step_log["extracted_files"] = [str(path) for path in extracted_paths]
            step_log["extracted_file"] = step_log["extracted_files"][0]
        step_log["success"] = True
    except Exception as exc:
        step_log["error"] = _format_step_error(step_log, exc)
    finally:
        step_log["url_after"] = active_page.url
        step_log["duration_seconds"] = round(time.monotonic() - started, 3)

    return step_log, active_page


def _format_step_error(step_log: dict[str, Any], exc: Exception) -> str:
    return (
        f"Step failed | item={step_log.get('item_index')} | "
        f"step={step_log.get('index')}:{step_log.get('name')} | "
        f"action={step_log.get('action')} | attr={step_log.get('attr') or '-'} | "
        f"xpath={step_log.get('xpath')} | wait_state={step_log.get('wait_state')} | "
        f"wait_timeout_ms={step_log.get('wait_timeout_ms')} | "
        f"matched_count={step_log.get('matched_count')} | "
        f"url_before={step_log.get('url_before')} | cause={exc}"
    )


def _step_wait_state(step: dict[str, Any]) -> str:
    if step.get("wait_state"):
        return str(step["wait_state"])

    action = str(step.get("action") or "")
    if action == "click":
        return "visible"
    if action == "download":
        return "attached" if step.get("attr") else "visible"
    return "attached"


def _config_parse_pause_seconds(config: dict[str, Any]) -> int:
    raw_value = config.get("parse_pause_seconds")
    if raw_value in (None, ""):
        return 0
    try:
        parsed_value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise WorkflowConfigError("parse_pause_seconds must be a non-negative integer.") from exc
    if parsed_value < 0:
        raise WorkflowConfigError("parse_pause_seconds must be a non-negative integer.")
    return parsed_value


def _step_open_mode(step: dict[str, Any]) -> str:
    raw_mode = str(step.get("open_mode") or "auto").strip().lower()
    if raw_mode not in SUPPORTED_OPEN_MODES:
        raise RuntimeError(f"open_mode must be one of {sorted(SUPPORTED_OPEN_MODES)}.")
    return raw_mode


def _locator_targets_new_tab(locator: Any) -> bool:
    try:
        target = str(locator.get_attribute("target") or "").strip().lower()
    except Exception:
        return False
    return target == "_blank"


def _step_loop_limit(step: dict[str, Any]) -> int | None:
    raw_limit = step.get("loop_limit")
    if raw_limit in (None, ""):
        return None

    try:
        limit = int(raw_limit)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("loop_limit must be a non-negative integer.") from exc

    if limit < 0:
        raise RuntimeError("loop_limit must be a non-negative integer.")
    return limit or None


def _config_primary_loop_step_index(config: dict[str, Any]) -> int | None:
    steps = config.get("steps") or []
    for index, step in enumerate(steps, start=1):
        if isinstance(step, dict) and step.get("loop"):
            return index
    return None


def _step_loop_mode(step: dict[str, Any]) -> str:
    raw_mode = str(step.get("loop_mode") or "").strip().lower()
    if raw_mode in SUPPORTED_LOOP_MODES:
        return raw_mode
    if str(step.get("pagination_mode") or "").strip().lower() in SUPPORTED_PAGINATION_MODES:
        return "pagination"
    if str(step.get("xpath_2") or "").strip():
        return "items"
    return "items"


def _config_click_loop_step_indexes(config: dict[str, Any]) -> tuple[int, ...]:
    steps = config.get("steps") or []
    indexes: list[int] = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            continue
        if step.get("loop") and str(step.get("action") or "") == "click":
            indexes.append(index)
            if len(indexes) == 2:
                break
    return tuple(indexes)


def _config_search_terms(config: dict[str, Any]) -> list[str]:
    raw_terms = config.get("search_terms")
    if not raw_terms:
        return []
    terms: list[str] = []
    for term in raw_terms:
        if term is None:
            continue
        cleaned = str(term).strip()
        if cleaned:
            terms.append(cleaned)
    return terms


def _config_filter_terms(config: dict[str, Any]) -> list[str]:
    raw_terms = config.get("filter_terms")
    if not raw_terms:
        return []
    terms: list[str] = []
    for term in raw_terms:
        if term is None:
            continue
        cleaned = str(term).strip()
        if cleaned:
            terms.append(cleaned)
    return terms


def _config_parser_name(config: dict[str, Any]) -> str | None:
    steps = config.get("steps") or []
    parser_names = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        action = str(step.get("action") or "").strip().lower()
        if action == "parser":
            attr = str(step.get("attr") or "").strip().lower()
            if not attr:
                attr = _infer_parser_attr_from_start_url(str(config.get("start_url") or "")) or GOOGLE_NEWS_RSS_ATTR
            parser_names.append(attr)

    if not parser_names:
        return None
    if len(steps) != 1:
        raise WorkflowConfigError("steps must contain exactly one step when action=parser.")

    parser_name = parser_names[0]
    if parser_name not in SUPPORTED_PARSER_ATTRS:
        raise WorkflowConfigError(f"steps[1].attr must be one of {sorted(STEP_ATTR_ALLOWED_VALUES['parser'])}.")
    return parser_name


def _infer_parser_attr_from_start_url(start_url: str) -> str | None:
    lowered = start_url.strip().lower()
    if "dapi.kakao.com/v2/search/web" in lowered:
        return DAUM_NEWS_API_ATTR
    if "openapi.naver.com/v1/search/news" in lowered:
        return NAVER_NEWS_API_ATTR
    if "news.google.com/rss/search" in lowered:
        return GOOGLE_NEWS_RSS_ATTR
    return None


def _config_primary_loop_spec(config: dict[str, Any]) -> BoardLoopSpec | None:
    steps = config.get("steps") or []
    for step in steps:
        if isinstance(step, dict) and step.get("loop") and _step_loop_mode(step) == "items" and step.get("xpath_2"):
            spec = _build_board_loop_spec(str(step.get("xpath") or ""), str(step.get("xpath_2") or ""))
            if spec is not None:
                return spec
            break

    board = config.get("board") or {}
    if board.get("enabled"):
        spec = _build_board_loop_spec(
            str(board.get("loop_anchor_xpath_1") or ""),
            str(board.get("loop_anchor_xpath_2") or ""),
        )
        if spec is not None:
            return spec
    return None


def _config_primary_pagination_spec(config: dict[str, Any]) -> PaginationLoopSpec | None:
    steps = config.get("steps") or []
    for step in steps:
        if isinstance(step, dict) and step.get("loop") and _step_loop_mode(step) == "pagination":
            pagination_mode = str(step.get("pagination_mode") or "").strip().lower()
            if pagination_mode == "submit_form":
                pagination_mode = "page_number"
            xpath = str(step.get("xpath") or "").strip()
            if not xpath:
                return None
            start_page = 1
            raw_start_page = step.get("pagination_start_page")
            if raw_start_page not in (None, ""):
                try:
                    start_page = int(raw_start_page)
                except (TypeError, ValueError):
                    start_page = 1
                if start_page <= 0:
                    start_page = 1
            return PaginationLoopSpec(
                pagination_mode=pagination_mode,
                xpath=xpath,
                start_page=start_page,
            )
    return None


def _config_primary_loop_mode(config: dict[str, Any]) -> str | None:
    steps = config.get("steps") or []
    for step in steps:
        if isinstance(step, dict) and step.get("loop"):
            return _step_loop_mode(step)
    return None


def _config_primary_loop_limit(config: dict[str, Any]) -> int | None:
    steps = config.get("steps") or []
    for step in steps:
        if isinstance(step, dict) and step.get("loop"):
            return _step_loop_limit(step)

    board = config.get("board") or {}
    if board.get("enabled"):
        raw_limit = board.get("limit")
        if raw_limit in (None, ""):
            return None
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("board.limit must be a positive integer.") from exc
        if limit <= 0:
            return None
        return limit
    return None


def _search_term_output_dir(
    base_output_dir: Path,
    search_term: str | None,
    search_term_index: int,
    search_term_count: int,
) -> Path:
    label = safe_name(search_term or "default")
    return base_output_dir / f"{search_term_index + 1:03d}_{label}"


def _config_board_repeat_spec(config: dict[str, Any]) -> BoardRepeatSpec | None:
    board = config.get("board") or {}
    list_xpath = str(board.get("list_xpath") or "")
    item_tag = str(board.get("item_tag") or "")
    item_xpath = str(board.get("item_xpath") or "")
    steps = config.get("steps") or []
    first_step_xpath = str((steps[0].get("xpath") or "") if steps and isinstance(steps[0], dict) else "")
    if not list_xpath and not item_tag and not item_xpath:
        return None
    return _build_board_repeat_spec(list_xpath, item_tag, item_xpath, first_step_xpath)


def _locator(page: Any, scope: Any, xpath: str) -> Any:
    if scope is not None and xpath.startswith("."):
        return scope.locator(f"xpath={xpath}")
    return page.locator(f"xpath={xpath}")


def _locator_matches_exclude(locator: Any, exclude_xpath: str) -> bool:
    if not exclude_xpath:
        return False
    try:
        if locator.locator(f"xpath={exclude_xpath}").count() > 0:
            return True
    except Exception:
        pass

    try:
        return bool(
            locator.evaluate(
                """(el, xpath) => {
                    const doc = el.ownerDocument || document;
                    const snapshot = doc.evaluate(
                        xpath,
                        doc,
                        null,
                        XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
                        null,
                    );
                    for (let i = 0; i < snapshot.snapshotLength; i += 1) {
                        const node = snapshot.snapshotItem(i);
                        if (node && (node === el || el.contains(node))) {
                            return true;
                        }
                    }
                    return false;
                }""",
                exclude_xpath,
            )
        )
    except Exception:
        return False


def _locator_is_disabled(locator: Any) -> bool:
    try:
        return bool(
            locator.evaluate(
                """(el) => {
                    if (!el) return false;
                    if (el.disabled) return true;
                    const ariaDisabled = el.getAttribute && el.getAttribute("aria-disabled");
                    if (ariaDisabled && ariaDisabled.toLowerCase() === "true") return true;
                    const className = (el.className || "").toString().toLowerCase();
                    return className.includes("disabled");
                }"""
            )
        )
    except Exception:
        return False


def _filtered_locators(locator_group: Any, exclude_xpath: str) -> list[Any]:
    total = int(locator_group.count())
    locators: list[Any] = []
    for index in range(total):
        locator = locator_group.nth(index)
        if _locator_matches_exclude(locator, exclude_xpath):
            continue
        locators.append(locator)
    return locators


def _preview_node_matches_exclude(node: Any, exclude_xpath: str) -> bool:
    if not exclude_xpath:
        return False
    try:
        return bool(node.xpath(exclude_xpath))
    except Exception:
        return False


def _resolve_step_xpath(
    xpath: str,
    item_index: int | None,
    board_item_tag: str | None,
    board_list_xpath: str | None = None,
    start_index: int = 1,
    board_loop_spec: BoardLoopSpec | None = None,
    board_item_number: int | None = None,
) -> str:
    if item_index is None:
        return xpath

    if board_loop_spec is not None:
        item_number = board_item_number if board_item_number is not None else item_index + board_loop_spec.start_index
        resolved = _replace_loop_item_segment(xpath, item_number, board_loop_spec)
        if resolved != xpath:
            return resolved

    if not board_item_tag:
        return xpath

    if not board_list_xpath:
        return _replace_first_indexed_segment(xpath, item_index + start_index)

    return _replace_matching_indexed_segment(xpath, item_index + start_index, board_item_tag, board_list_xpath)


def _board_repeat_step_index(
    step_index: int,
    item_index: int | None,
    board_repeat_spec: BoardRepeatSpec | None,
) -> int | None:
    if item_index is None or board_repeat_spec is None:
        return None
    if step_index != 1:
        return None
    return item_index


def _resolve_board_items(
    page: Any,
    list_xpath: str,
    repeat_spec: BoardRepeatSpec | None,
    first_step_xpath: str,
    strict_repeat_spec: bool = False,
) -> tuple[int, BoardRepeatSpec | None]:
    if repeat_spec is None:
        if not isinstance(first_step_xpath, str):
            first_step_xpath = ""
        repeat_spec = _infer_board_repeat_spec(list_xpath, first_step_xpath)
    if repeat_spec is not None:
        matched_count = page.locator(f"xpath={repeat_spec.item_xpath}").count()
        if matched_count > 0:
            return matched_count, repeat_spec
        if strict_repeat_spec:
            raise RuntimeError(
                f"Configured board item XPath did not match any nodes: {repeat_spec.item_xpath}"
            )

    list_locator = page.locator(f"xpath={list_xpath}")
    matched_count = list_locator.count()
    if matched_count <= 0:
        raise RuntimeError(f"No board list items matched list_xpath={list_xpath}.")

    if matched_count > 1:
        item_tag = _locator_tag_name(list_locator.first)
        return matched_count, BoardRepeatSpec(item_xpath=None, item_tag=item_tag)

    root = list_locator.first
    item_tag = _locator_tag_name(root)
    child_locators = _child_board_locators(root, item_tag)
    child_count = child_locators.count()
    if child_count > 0:
        child_tag = _locator_tag_name(child_locators.first)
        return child_count, BoardRepeatSpec(item_xpath=None, item_tag=child_tag)

    return 1, BoardRepeatSpec(item_xpath=None, item_tag=item_tag)


def _select_board_item_scope(
    page: Any,
    list_xpath: str,
    item_index: int,
    board_repeat_spec: BoardRepeatSpec | None = None,
    strict_repeat_spec: bool = False,
) -> tuple[Any, BoardRepeatSpec | None]:
    if board_repeat_spec is not None and board_repeat_spec.item_xpath:
        item_locator = page.locator(f"xpath={board_repeat_spec.item_xpath}")
        if item_locator.count() > 0:
            return item_locator.nth(item_index), board_repeat_spec
        if strict_repeat_spec:
            raise RuntimeError(
                f"Configured board item XPath did not match any nodes: {board_repeat_spec.item_xpath}"
            )

    list_locator = page.locator(f"xpath={list_xpath}")
    matched_count = list_locator.count()
    if matched_count <= 0:
        raise RuntimeError(f"No board list items matched list_xpath={list_xpath}.")

    if matched_count > 1:
        item_tag = _locator_tag_name(list_locator.first)
        return list_locator.nth(item_index), BoardRepeatSpec(item_xpath=None, item_tag=item_tag)

    root = list_locator.first
    item_tag = _locator_tag_name(root)
    child_locators = _child_board_locators(root, item_tag)
    child_count = child_locators.count()
    if child_count > 0:
        child_tag = _locator_tag_name(child_locators.first)
        return child_locators.nth(item_index), BoardRepeatSpec(item_xpath=None, item_tag=child_tag)

    return root, BoardRepeatSpec(item_xpath=None, item_tag=item_tag)


def _child_board_locators(container: Any, container_tag: str | None) -> Any:
    selectors = BOARD_CONTAINER_CHILD_XPATHS.get((container_tag or "").lower())
    if not selectors:
        return container.locator("xpath=.//*")

    for selector in selectors:
        child_locators = container.locator(f"xpath={selector}")
        if child_locators.count() > 0:
            return child_locators
    return container.locator(f"xpath={selectors[0]}")


def _locator_tag_name(locator: Any) -> str | None:
    try:
        tag_name = locator.evaluate("(el) => el.tagName.toLowerCase()")
    except Exception:
        return None
    return str(tag_name).lower() if tag_name else None


def _preview_node_tag(node: Any) -> str | None:
    return getattr(node, "tag", None).lower() if getattr(node, "tag", None) else None


def _preview_board_items(
    root: Any,
    list_matches: list[Any],
    list_xpath: str,
    repeat_spec: BoardRepeatSpec | None,
    first_step_xpath: str,
    strict_repeat_spec: bool = False,
) -> tuple[list[Any], BoardRepeatSpec | None]:
    if not list_matches:
        return [], None

    if repeat_spec is None:
        repeat_spec = _infer_board_repeat_spec(list_xpath, first_step_xpath)
    if repeat_spec is not None:
        matched_nodes = root.xpath(repeat_spec.item_xpath)
        if matched_nodes:
            return matched_nodes, repeat_spec
        if strict_repeat_spec:
            raise RuntimeError(f"Configured board item XPath did not match any nodes: {repeat_spec.item_xpath}")

    if len(list_matches) > 1:
        tag_name = _preview_node_tag(list_matches[0])
        return list_matches, BoardRepeatSpec(item_xpath=None, item_tag=tag_name)

    root_node = list_matches[0]
    root_tag = _preview_node_tag(root_node)
    child_nodes = _preview_child_nodes(root_node, root_tag)
    if child_nodes:
        child_tag = _preview_node_tag(child_nodes[0])
        return child_nodes, BoardRepeatSpec(item_xpath=None, item_tag=child_tag)

    return [root_node], BoardRepeatSpec(item_xpath=None, item_tag=root_tag)


def _resolve_board_loop_item_numbers(
    page: Any,
    loop_spec: BoardLoopSpec,
    exclude_xpath: str = "",
) -> list[int]:
    item_numbers: list[int] = []
    for item_number in range(loop_spec.start_index, loop_spec.start_index + BOARD_LOOP_MAX_ITEMS):
        anchor_locator = page.locator(f"xpath={loop_spec.render_anchor_xpath(item_number)}")
        if anchor_locator.count() <= 0:
            break
        if exclude_xpath:
            item_locator = page.locator(f"xpath={loop_spec.render_item_root_xpath(item_number)}")
            if item_locator.count() > 0 and _locator_matches_exclude(item_locator.first, exclude_xpath):
                continue
        item_numbers.append(item_number)
    return item_numbers


def _resolve_board_loop_items(page: Any, loop_spec: BoardLoopSpec, exclude_xpath: str = "") -> int:
    return len(_resolve_board_loop_item_numbers(page, loop_spec, exclude_xpath=exclude_xpath))


def _resolve_pagination_page_numbers(page: Any, pagination_spec: PaginationLoopSpec, loop_limit: int | None = None) -> list[int]:
    page_numbers: list[int] = []
    max_pages = loop_limit if loop_limit is not None else BOARD_LOOP_MAX_ITEMS
    if pagination_spec.pagination_mode == "page_number":
        page_numbers.append(pagination_spec.start_page)
        for page_number in range(pagination_spec.start_page + 1, pagination_spec.start_page + max_pages):
            anchor_locator = page.locator(f"xpath={pagination_spec.render_xpath(page_number)}")
            if anchor_locator.count() <= 0:
                break
            page_numbers.append(page_number)
        return page_numbers

    page_numbers.append(1)
    current_page = page
    for next_page_number in range(2, 2 + max_pages):
        locator = current_page.locator(f"xpath={pagination_spec.xpath}")
        if locator.count() <= 0:
            break
        locator = locator.first
        if _locator_is_disabled(locator):
            break
        try:
            before_url = current_page.url
            locator.click(timeout=DEFAULT_STEP_WAIT_MS)
            _wait_after_action(current_page, DEFAULT_STEP_WAIT_MS)
            after_url = current_page.url
        except Exception:
            break
        if after_url == before_url:
            break
        page_numbers.append(next_page_number)
    return page_numbers


def _preview_board_loop_item_numbers(root: Any, loop_spec: BoardLoopSpec, exclude_xpath: str = "") -> list[int]:
    item_numbers: list[int] = []
    for item_number in range(loop_spec.start_index, loop_spec.start_index + BOARD_LOOP_MAX_ITEMS):
        anchor_nodes = root.xpath(loop_spec.render_anchor_xpath(item_number))
        if not anchor_nodes:
            break
        if exclude_xpath:
            root_nodes = root.xpath(loop_spec.render_item_root_xpath(item_number))
            if root_nodes and _preview_node_matches_exclude(root_nodes[0], exclude_xpath):
                continue
        item_numbers.append(item_number)
    return item_numbers


def _preview_board_loop_items(root: Any, loop_spec: BoardLoopSpec, exclude_xpath: str = "") -> list[Any]:
    items: list[Any] = []
    for item_number in _preview_board_loop_item_numbers(root, loop_spec, exclude_xpath=exclude_xpath):
        matched_nodes = root.xpath(loop_spec.render_anchor_xpath(item_number))
        if matched_nodes:
            items.append(matched_nodes[0])
    return items


def _build_board_loop_spec(anchor_xpath_1: str, anchor_xpath_2: str) -> BoardLoopSpec | None:
    if not anchor_xpath_1 or not anchor_xpath_2:
        return None
    return _infer_board_loop_spec(anchor_xpath_1, anchor_xpath_2)


def _infer_board_loop_spec(anchor_xpath_1: str, anchor_xpath_2: str) -> BoardLoopSpec | None:
    prefix_1, segments_1 = _split_xpath_segments(anchor_xpath_1)
    prefix_2, segments_2 = _split_xpath_segments(anchor_xpath_2)
    if prefix_1 != prefix_2 or len(segments_1) != len(segments_2) or not segments_1:
        return None

    diffs: list[tuple[int, str, str]] = []
    for index, (segment_1, segment_2) in enumerate(zip(segments_1, segments_2)):
        if segment_1 == segment_2:
            continue
        diffs.append((index, segment_1, segment_2))

    if len(diffs) != 1:
        return None

    diff_index, segment_1, segment_2 = diffs[0]
    match_1 = BOARD_ITEM_SEGMENT_RE.match(segment_1)
    match_2 = BOARD_ITEM_SEGMENT_RE.match(segment_2)
    item_segment_template: str | None = None
    item_tag: str | None = None
    start_index: int | None = None

    if match_1 and match_2:
        tag_1 = match_1.group("tag").lower()
        tag_2 = match_2.group("tag").lower()
        if tag_1 != tag_2:
            return None

        index_1 = int(match_1.group("index"))
        index_2 = int(match_2.group("index"))
        if index_1 <= 0 or index_2 <= 0:
            return None
        if index_2 != index_1 + 1:
            return None

        item_segment_template = f"{match_1.group('tag')}[{ITEM_NUMBER_PLACEHOLDER}]"
        item_tag = tag_1
        start_index = index_1
    else:
        suffix_1 = _split_trailing_numeric_suffix(segment_1)
        suffix_2 = _split_trailing_numeric_suffix(segment_2)
        if suffix_1 is None or suffix_2 is None:
            return None

        prefix_1_text, index_1, suffix_1_text = suffix_1
        prefix_2_text, index_2, suffix_2_text = suffix_2
        if prefix_1_text != prefix_2_text or suffix_1_text != suffix_2_text:
            return None
        if index_1 <= 0 or index_2 <= 0:
            return None
        if index_2 != index_1 + 1:
            return None

        item_segment_template = f"{prefix_1_text}{ITEM_NUMBER_PLACEHOLDER}{suffix_1_text}"
        start_index = index_1

    root_xpath = _join_xpath_segments(prefix_1, segments_1[:diff_index])
    suffix_segments = tuple(segments_1[diff_index + 1 :])
    return BoardLoopSpec(
        anchor_xpath_1=anchor_xpath_1,
        anchor_xpath_2=anchor_xpath_2,
        root_xpath=root_xpath,
        item_segment_template=item_segment_template,
        item_tag=item_tag,
        suffix_segments=suffix_segments,
        start_index=start_index,
    )


def _split_xpath_segments(xpath: str) -> tuple[str, list[str]]:
    for prefix in (".//", "//", "./", "/"):
        if xpath.startswith(prefix):
            body = xpath[len(prefix) :]
            return prefix, [segment for segment in body.split("/") if segment]
    return "", [segment for segment in xpath.split("/") if segment]


def _join_xpath_segments(prefix: str, segments: list[str]) -> str:
    if not segments:
        return prefix
    body = "/".join(segments)
    return f"{prefix}{body}" if prefix else body


def _preview_child_nodes(node: Any, node_tag: str | None) -> list[Any]:
    selectors = BOARD_CONTAINER_CHILD_XPATHS.get((node_tag or "").lower())
    if not selectors:
        return []

    for selector in selectors:
        children = node.xpath(selector)
        if children:
            return children
    return []


def _infer_board_repeat_spec(list_xpath: str, step_xpath: str) -> BoardRepeatSpec | None:
    base = list_xpath.rstrip("/")
    if not base or not step_xpath.startswith(base):
        return None

    suffix = step_xpath[len(base) :]
    if not suffix or not suffix.startswith("/"):
        return None

    segments = [segment for segment in suffix.split("/") if segment]
    anchor_segments: list[str] = []
    for segment in segments:
        match = BOARD_PATH_SEGMENT_RE.match(segment)
        if not match:
            return None
        anchor_segments.append(match.group("tag"))
        if match.group("index"):
            item_xpath = _join_xpath(base, anchor_segments)
            return BoardRepeatSpec(item_xpath=item_xpath, item_tag=match.group("tag").lower())

    return None


def _build_board_repeat_spec(
    list_xpath: str,
    item_tag: str,
    item_xpath: str,
    first_step_xpath: str,
) -> BoardRepeatSpec | None:
    if item_xpath:
        tag = item_tag or _xpath_last_segment_tag(item_xpath)
        return BoardRepeatSpec(item_xpath=item_xpath, item_tag=tag)

    if item_tag:
        return BoardRepeatSpec(item_xpath=_join_xpath(list_xpath, [item_tag]), item_tag=item_tag)

    if first_step_xpath:
        return _infer_board_repeat_spec(list_xpath, first_step_xpath)

    return None


def _replace_matching_indexed_segment(xpath: str, item_number: int, item_tag: str, list_xpath: str) -> str:
    if item_number <= 0:
        return xpath

    prefix = list_xpath.rstrip("/")
    if not xpath.startswith(prefix):
        return xpath

    suffix = xpath[len(prefix) :]
    if not suffix.startswith("/"):
        return xpath

    segments = [segment for segment in suffix.split("/") if segment]
    matching_indexes = [
        index
        for index, segment in enumerate(segments)
        if _segment_tag(segment) == item_tag and _segment_has_index(segment)
    ]
    if len(matching_indexes) != 1:
        raise RuntimeError(
            f"Could not resolve repeat item index for item_tag={item_tag} under list_xpath={list_xpath}."
        )

    segment_index = matching_indexes[0]
    segment_tag = _segment_tag(segments[segment_index])
    segments[segment_index] = f"{segment_tag}[{item_number}]"
    return f"{prefix}/{'/'.join(segments)}"


def _replace_first_indexed_segment(xpath: str, item_number: int) -> str:
    if item_number <= 0:
        return xpath

    for prefix in (".//", "//", "/"):
        if not xpath.startswith(prefix):
            continue

        body = xpath[len(prefix) :]
        segments = body.split("/")
        for index, segment in enumerate(segments):
            match = BOARD_ITEM_SEGMENT_RE.match(segment)
            if not match:
                continue
            segments[index] = f"{match.group('tag')}[{item_number}]"
            return prefix + "/".join(segments)
        return xpath

    return xpath


def _segment_tag(segment: str) -> str | None:
    match = BOARD_PATH_SEGMENT_RE.match(segment)
    if not match:
        return None
    return match.group("tag").lower()


def _segment_has_index(segment: str) -> bool:
    match = BOARD_PATH_SEGMENT_RE.match(segment)
    return bool(match and match.group("index"))


def _xpath_last_segment_tag(xpath: str) -> str | None:
    segments = [segment for segment in xpath.rstrip("/").split("/") if segment]
    if not segments:
        return None
    return _segment_tag(segments[-1])


def _join_xpath(base: str, segments: list[str]) -> str:
    if not segments:
        return base
    body = "/".join(segments)
    if not base:
        return body
    if base in {"/", "//", "./", ".//"} or base.endswith("/"):
        return f"{base}{body}"
    return f"{base}/{body}"


def _split_trailing_numeric_suffix(segment: str) -> tuple[str, int, str] | None:
    match = BOARD_TRAILING_NUMBER_SEGMENT_RE.match(segment)
    if not match:
        return None

    prefix = match.group("prefix")
    suffix = match.group("suffix")
    if not prefix:
        return None

    index = int(match.group("index"))
    return prefix, index, suffix


def _replace_loop_item_segment(xpath: str, item_number: int, loop_spec: BoardLoopSpec) -> str:
    if item_number <= 0:
        return xpath

    xpath_prefix, xpath_segments = _split_xpath_segments(xpath)
    root_prefix, root_segments = _split_xpath_segments(loop_spec.root_xpath)
    if xpath_prefix != root_prefix or len(xpath_segments) <= len(root_segments):
        return xpath

    if xpath_segments[: len(root_segments)] != root_segments:
        return xpath

    item_segment_index = len(root_segments)
    xpath_segments[item_segment_index] = loop_spec.render_item_segment(item_number)
    return _join_xpath_segments(xpath_prefix, xpath_segments)


def _child_board_xpath(list_xpath: str, container_tag: str | None, child_tag: str | None) -> str:
    tags = [tag for tag in (container_tag, child_tag) if tag]
    if not tags:
        return list_xpath
    return _join_xpath(list_xpath, tags)


def _step_value(locator: Any, step: dict[str, Any]) -> str:
    attr = str(step.get("attr") or "href")
    if attr == "text":
        return locator.inner_text().strip()
    if attr == "html":
        return locator.inner_html().strip()
    return (locator.get_attribute(attr) or "").strip()


def _render_template_value(template: str, search_term: str | None, *, url_encode: bool = False) -> str:
    rendered = str(template)
    if "{search_term}" in rendered:
        replacement = quote_plus(search_term or "") if url_encode else (search_term or "")
        rendered = rendered.replace("{search_term}", replacement)
    return rendered


def _step_url(page: Any, locator: Any, step: dict[str, Any]) -> str:
    value = _step_value(locator, step)
    if not value:
        raise RuntimeError(f"No value found for attr={step.get('attr') or 'href'}.")
    return urljoin(page.url, value)


def _page_title(page: Any) -> str:
    try:
        value = page.title()
    except Exception:
        return ""
    return str(value or "").strip()


def _save_extract_outputs(
    output_dir: Path,
    item_index: int | None,
    step_index: int,
    step: dict[str, Any],
    value: Any,
    *,
    page_title: str = "",
    is_html: bool = False,
    record_key: str | None = None,
) -> list[Path]:
    target_dir = output_dir / "texts" / date.today().strftime("%Y%m%d")
    target_dir.mkdir(parents=True, exist_ok=True)

    item_label = f"item_{item_index + 1}" if item_index is not None else "single"
    step_label = str(step.get("name") or f"step_{step_index}").strip()
    title_label = str(page_title or "").strip()
    raw_value = "" if value is None else str(value)
    saved_paths: list[Path] = []
    stem_parts = [record_key or "record", item_label, step_label]
    if title_label:
        stem_parts.append(title_label)
    file_stem = safe_name("_".join(stem_parts))

    text_path = _unique_path(target_dir / f"{file_stem}.txt")
    text_path.write_text(_html_to_text(raw_value) if is_html else raw_value, encoding="utf-8")
    saved_paths.append(text_path)

    if is_html:
        html_path = _unique_path(target_dir / f"{file_stem}.html")
        html_path.write_text(raw_value, encoding="utf-8")
        saved_paths.append(html_path)

    return saved_paths


def _html_to_text(value: str) -> str:
    try:
        node = lxml_html.fromstring(value)
        return node.text_content().strip()
    except Exception:
        return value.strip()


def _download_step(
    page: Any,
    locator: Any,
    step: dict[str, Any],
    output_dir: Path,
    timeout_ms: int,
    *,
    record_key: str | None = None,
    step_index: int | None = None,
) -> Path:
    attr = step.get("attr")
    if attr:
        target_url = _step_url(page, locator, step)
        if str(target_url).lstrip().lower().startswith("javascript:"):
            return _download_via_click(
                page,
                locator,
                output_dir,
                timeout_ms,
                record_key=record_key,
                step_index=step_index,
                step_name=str(step.get("name") or "download"),
            )
        response = page.context.request.get(target_url, timeout=timeout_ms)
        if not response.ok:
            raise RuntimeError(f"Download request failed: HTTP {response.status}")
        return _save_response_body(
            response,
            target_url,
            output_dir,
            record_key=record_key,
            step_index=step_index,
            step_name=str(step.get("name") or "download"),
        )

    return _download_via_click(
        page,
        locator,
        output_dir,
        timeout_ms,
        record_key=record_key,
        step_index=step_index,
        step_name=str(step.get("name") or "download"),
    )


def _download_multiple_step(
    page: Any,
    locator_group: Any,
    step: dict[str, Any],
    output_dir: Path,
    timeout_ms: int,
    *,
    record_key: str | None = None,
    step_index: int | None = None,
) -> list[Path]:
    downloaded_paths: list[Path] = []
    seen_targets: set[str] = set()
    total = int(locator_group.count())

    for index in range(total):
        locator = locator_group.nth(index)
        target = _download_target_key(page, locator, step)
        if target and target in seen_targets:
            continue
        if target:
            seen_targets.add(target)
        downloaded_paths.append(
            _download_step(
                page,
                locator,
                step,
                output_dir,
                timeout_ms,
                record_key=record_key,
                step_index=step_index,
            )
        )

    return downloaded_paths


def _download_loop_step(
    page: Any,
    step: dict[str, Any],
    output_dir: Path,
    timeout_ms: int,
    loop_spec: BoardLoopSpec,
    exclude_xpath: str = "",
    *,
    record_key: str | None = None,
    step_index: int | None = None,
) -> list[Path]:
    downloaded_paths: list[Path] = []
    seen_targets: set[str] = set()
    item_numbers = _resolve_board_loop_item_numbers(page, loop_spec, exclude_xpath=exclude_xpath)
    loop_limit = _step_loop_limit(step)
    if loop_limit is not None:
        item_numbers = item_numbers[:loop_limit]

    for item_number in item_numbers:
        locator = page.locator(f"xpath={loop_spec.render_anchor_xpath(item_number)}").first
        target = _download_target_key(page, locator, step)
        if target and target in seen_targets:
            continue
        if target:
            seen_targets.add(target)
        downloaded_paths.append(
            _download_step(
                page,
                locator,
                step,
                output_dir,
                timeout_ms,
                record_key=record_key,
                step_index=step_index,
            )
        )

    return downloaded_paths


def _extract_loop_step(
    page: Any,
    step: dict[str, Any],
    step_index: int,
    output_dir: Path,
    loop_spec: BoardLoopSpec,
    exclude_xpath: str = "",
    *,
    record_key: str | None = None,
) -> tuple[list[str], list[Path]]:
    values: list[str] = []
    saved_paths: list[Path] = []
    item_numbers = _resolve_board_loop_item_numbers(page, loop_spec, exclude_xpath=exclude_xpath)
    loop_limit = _step_loop_limit(step)
    if loop_limit is not None:
        item_numbers = item_numbers[:loop_limit]
    is_html = str(step.get("attr") or "").lower() == "html"

    for offset, item_number in enumerate(item_numbers):
        locator = page.locator(f"xpath={loop_spec.render_anchor_xpath(item_number)}").first
        value = _step_value(locator, step)
        values.append(value)
        saved_paths.extend(
            _save_extract_outputs(
                output_dir,
                offset,
                step_index,
                step,
                value,
                page_title=_page_title(page),
                is_html=is_html,
                record_key=record_key,
            )
        )

    return values, saved_paths


def _download_via_click(
    page: Any,
    locator: Any,
    output_dir: Path,
    timeout_ms: int,
    *,
    record_key: str | None = None,
    step_index: int | None = None,
    step_name: str = "download",
) -> Path:
    href = str(locator.get_attribute("href") or "").strip()
    try:
        with page.expect_download(timeout=timeout_ms) as download_info:
            locator.click(timeout=timeout_ms)
        download = download_info.value
        target_path = _unique_path(
            _record_output_path(
                _download_dir(output_dir),
                record_key or "record",
                step_index or 1,
                step_name,
                download.suggested_filename,
            )
        )
        download.save_as(str(target_path))
        return target_path
    except Exception as exc:
        if href.lower().startswith("javascript:"):
            raise RuntimeError(
                "javascript href did not trigger a browser download after click. "
                "Use action=click for this link or update the site-specific download handler."
            ) from exc

        target_url = _step_url(page, locator, {"attr": "href"})
        response = page.context.request.get(target_url, timeout=timeout_ms)
        if not response.ok:
            raise RuntimeError(f"Download request failed: HTTP {response.status}")
        return _save_response_body(
            response,
            target_url,
            output_dir,
            record_key=record_key,
            step_index=step_index,
            step_name=step_name,
        )


def _download_target_key(page: Any, locator: Any, step: dict[str, Any]) -> str:
    attr = str(step.get("attr") or "").strip()
    if attr:
        try:
            value = _step_url(page, locator, step)
        except Exception:
            value = ""
        return value.strip()

    try:
        href = str(locator.get_attribute("href") or "").strip()
    except Exception:
        href = ""
    return urljoin(page.url, href) if href else ""


def _ensure_windows_subprocess_policy() -> None:
    if sys.platform != "win32":
        return
    policy = asyncio.get_event_loop_policy()
    if not isinstance(policy, asyncio.WindowsProactorEventLoopPolicy):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


def _config_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off", ""}:
            return False
    return bool(value)


def _new_workflow_page(browser: Any) -> Any:
    page = browser.new_page()
    _attach_dialog_handler(page)
    return page


def _attach_dialog_handler(page: Any) -> None:
    def _handle_dialog(dialog: Any) -> None:
        try:
            dialog.accept()
        except Exception:
            try:
                dialog.dismiss()
            except Exception:
                pass

    try:
        page.on("dialog", _handle_dialog)
    except Exception:
        pass


def _wait_after_action(page: Any, timeout_ms: int) -> None:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=min(timeout_ms, 10000))
    except Exception:
        pass


def _download_dir(output_dir: Path) -> Path:
    target = output_dir / "downloads" / date.today().strftime("%Y%m%d")
    target.mkdir(parents=True, exist_ok=True)
    return target


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for index in range(1, 10000):
        candidate = parent / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not build unique path for {path}")


def _file_name_from_url(url: str) -> str:
    name = unquote(Path(urlparse(url).path).name)
    return safe_name(name or "download.bin")


def _save_response_body(
    response: Any,
    url: str,
    output_dir: Path,
    *,
    record_key: str | None = None,
    step_index: int | None = None,
    step_name: str = "download",
) -> Path:
    file_name = _file_name_from_headers(response.headers) or _file_name_from_url(url)
    target_path = _unique_path(_record_output_path(_download_dir(output_dir), record_key or "record", step_index or 1, step_name, file_name))
    target_path.write_bytes(response.body())
    return target_path


def _file_name_from_headers(headers: dict[str, str]) -> str | None:
    disposition = headers.get("content-disposition") or headers.get("Content-Disposition")
    if not disposition:
        return None

    star_match = re.search(r"filename\*=([^']*)''([^;]+)", disposition, flags=re.IGNORECASE)
    if star_match:
        return safe_name(unquote(star_match.group(2).strip().strip('"')))

    match = re.search(r'filename="?([^";]+)"?', disposition, flags=re.IGNORECASE)
    if not match:
        return None

    raw_name = match.group(1).strip()
    try:
        decoded = raw_name.encode("latin1").decode("utf-8")
        return safe_name(unquote(decoded))
    except UnicodeError:
        parts = decode_header(raw_name)
        decoded = "".join(
            part.decode(charset or "utf-8") if isinstance(part, bytes) else part
            for part, charset in parts
        )
        return safe_name(unquote(decoded))


def _headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
        )
    }


def safe_name(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]+', "_", str(value)).strip().rstrip(".")
    if len(cleaned) > 160:
        path = Path(cleaned)
        suffix = path.suffix
        stem_limit = max(1, 160 - len(suffix))
        cleaned = f"{path.stem[:stem_limit]}{suffix}"
    return cleaned or "file"
