from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from email.header import decode_header
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
import json
import logging
import re

from bs4 import BeautifulSoup
from bs4.element import Tag
from lxml import html as lxml_html
import requests

from crawler_app.document_extractors import extract_text_from_bytes


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)


@dataclass(slots=True)
class ConfigListItem:
    values: dict[str, Any]
    post_date: date | None
    detail_url: str


@dataclass(slots=True)
class ConfigDetailItem:
    values: dict[str, Any]
    attachments: list[dict[str, Any]]


class ConfigValidationError(ValueError):
    """Raised when a crawler JSON config is missing required settings."""


def load_crawler_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigValidationError(f"Failed to read config file: {config_path} ({exc})") from exc
    except json.JSONDecodeError as exc:
        raise ConfigValidationError(f"Invalid JSON config: {config_path} ({exc})") from exc

    validate_crawler_config(config)
    return config


def validate_crawler_config(config: dict[str, Any]) -> None:
    for key in ("name", "start_url", "list", "detail"):
        if key not in config:
            raise ConfigValidationError(f"Missing required config key: {key}")

    list_config = _require_mapping(config["list"], "list")
    detail_config = _require_mapping(config["detail"], "detail")
    _require_mapping(list_config.get("item_selector"), "list.item_selector")
    _require_mapping(list_config.get("fields"), "list.fields")
    _require_mapping(detail_config.get("fields"), "detail.fields")

    attachments = detail_config.get("attachments")
    if attachments is not None:
        attachment_config = _require_mapping(attachments, "detail.attachments")
        _require_mapping(attachment_config.get("item_selector"), "detail.attachments.item_selector")


def parse_list_page(html_text: str, config: dict[str, Any]) -> list[ConfigListItem]:
    list_config = _require_mapping(config["list"], "list")
    soup = BeautifulSoup(html_text, "html.parser")
    item_selector = _require_mapping(list_config["item_selector"], "list.item_selector")
    fields = _require_mapping(list_config["fields"], "list.fields")
    base_url = str(config.get("base_url") or config["start_url"])

    items: list[ConfigListItem] = []
    for node in select_nodes(soup, item_selector):
        node = _apply_parent_levels(node, int(item_selector.get("parent_levels") or 0))
        values: dict[str, Any] = {}
        for field_name, field_config in fields.items():
            values[field_name] = extract_field(
                node,
                _require_mapping(field_config, f"list.fields.{field_name}"),
                values,
                base_url,
            )

        detail_url = str(values.get("detail_url") or "")
        if not detail_url:
            continue
        post_date = _coerce_date(values.get("date"))
        items.append(ConfigListItem(values=values, post_date=post_date, detail_url=detail_url))

    if list_config.get("latest_date_only"):
        dated_items = [item for item in items if item.post_date is not None]
        if dated_items:
            latest_date = max(item.post_date for item in dated_items if item.post_date is not None)
            items = [item for item in dated_items if item.post_date == latest_date]

    items.sort(key=lambda item: (item.post_date or date.min, str(item.values.get("post_id") or "")), reverse=True)
    return items


def parse_detail_page(html_text: str, config: dict[str, Any], list_item: ConfigListItem) -> ConfigDetailItem:
    detail_config = _require_mapping(config["detail"], "detail")
    soup = BeautifulSoup(html_text, "html.parser")
    base_url = str(config.get("base_url") or list_item.detail_url)
    container_selector = detail_config.get("container")
    container: Any = soup
    if container_selector:
        selected = select_first(soup, _require_mapping(container_selector, "detail.container"))
        if selected is not None:
            container = selected

    values = dict(list_item.values)
    for field_name, field_config in _require_mapping(detail_config["fields"], "detail.fields").items():
        field_mapping = _require_mapping(field_config, f"detail.fields.{field_name}")
        field_context = soup if field_mapping.get("scope") == "document" else container
        extracted = extract_field(
            field_context,
            field_mapping,
            values,
            base_url,
        )
        if extracted not in (None, ""):
            values[field_name] = extracted

    attachments = parse_attachments(container, detail_config.get("attachments"), values, base_url)
    return ConfigDetailItem(values=values, attachments=attachments)


def parse_attachments(
    container: Any,
    attachments_config: Any,
    values: dict[str, Any],
    base_url: str,
) -> list[dict[str, Any]]:
    if not attachments_config:
        return []

    config = _require_mapping(attachments_config, "detail.attachments")
    nodes = select_nodes(container, _require_mapping(config["item_selector"], "detail.attachments.item_selector"))
    attachments: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for node in nodes:
        attachment: dict[str, Any] = {}
        for field_name, field_config in config.items():
            if field_name == "item_selector":
                continue
            attachment[field_name] = extract_field(
                node,
                _require_mapping(field_config, f"detail.attachments.{field_name}"),
                {**values, **attachment},
                base_url,
            )

        download_url = str(attachment.get("download_url") or "")
        if not download_url or download_url in seen_urls:
            continue
        seen_urls.add(download_url)
        attachments.append(attachment)

    return attachments


def select_nodes(context: Any, selector: dict[str, Any]) -> list[Any]:
    selector_type = str(selector.get("type") or "css").lower()
    value = str(selector.get("value") or "")
    if not value:
        return []

    if selector_type == "css":
        if not hasattr(context, "select"):
            context = BeautifulSoup(_node_to_html(context), "html.parser")
        return list(context.select(value))

    if selector_type == "xpath":
        root = _to_lxml(context)
        result = root.xpath(value)
        return [node for node in result if node is not None]

    raise ConfigValidationError(f"Unsupported selector type: {selector_type}")


def select_first(context: Any, selector: dict[str, Any]) -> Any | None:
    nodes = select_nodes(context, selector)
    return nodes[0] if nodes else None


def _apply_parent_levels(node: Any, parent_levels: int) -> Any:
    current = node
    for _ in range(parent_levels):
        parent = getattr(current, "parent", None)
        if parent is None:
            break
        current = parent
    return current


def extract_field(context: Any, field_config: dict[str, Any], values: dict[str, Any], base_url: str) -> Any:
    if "template" in field_config:
        try:
            return str(field_config["template"]).format(**values)
        except KeyError as exc:
            raise ConfigValidationError(f"Template references missing field: {exc}") from exc

    target = context
    selector = field_config.get("selector")
    if selector:
        selected = select_first(context, _require_mapping(selector, "selector"))
        if selected is None:
            return None
        target = selected

    raw_value = _extract_raw_value(target, str(field_config.get("attr") or "text"))

    if field_config.get("html_to_text") and raw_value:
        raw_value = html_to_text(str(raw_value))

    if raw_value is not None and field_config.get("regex"):
        match = re.search(str(field_config["regex"]), str(raw_value), flags=re.IGNORECASE | re.DOTALL)
        raw_value = match.group(1) if match else None

    if raw_value is not None and field_config.get("urljoin"):
        raw_value = urljoin(base_url, str(raw_value))

    if raw_value is not None and field_config.get("date_format"):
        return datetime.strptime(str(raw_value).strip(), str(field_config["date_format"])).date()

    return _clean_text(str(raw_value)) if isinstance(raw_value, str) else raw_value


def html_to_text(value: str) -> str:
    decoded = unescape(value)
    soup = BeautifulSoup(decoded, "html.parser")
    return _clean_text(soup.get_text("\n", strip=True))


def download_and_extract_attachment(
    session: requests.Session,
    output_dir: Path,
    detail_values: dict[str, Any],
    attachment: dict[str, Any],
    timeout: int,
) -> dict[str, Any]:
    post_date = _coerce_date(detail_values.get("date")) or date.today()
    post_id = str(detail_values.get("post_id") or "post")
    post_title = str(detail_values.get("title") or "")
    detail_url = str(detail_values.get("detail_url") or "")
    attachment_name = str(attachment.get("file_name") or "attachment")
    attachment_url = str(attachment.get("download_url") or "")

    record: dict[str, Any] = {
        "post_id": post_id,
        "post_date": post_date.isoformat(),
        "post_title": post_title,
        "detail_url": detail_url,
        "department": detail_values.get("department"),
        "contact": detail_values.get("contact"),
        "body_text": detail_values.get("body_text") or "",
        "attachment_name": attachment_name,
        "attachment_url": attachment_url,
        "download_file_path": None,
        "saved_file_path": None,
        "metadata_file_path": None,
        "text_length": 0,
        "extract_success": False,
        "error": None,
    }

    response = session.get(attachment_url, timeout=timeout)
    response.raise_for_status()
    file_bytes = response.content
    downloaded_name = resolve_download_file_name(
        response.headers.get("Content-Disposition"),
        attachment_name,
        attachment_url,
    )

    raw_path = build_output_path(output_dir, post_date, post_id, downloaded_name, "downloads")
    raw_path.write_bytes(file_bytes)
    record["download_file_path"] = str(raw_path)
    record["attachment_name"] = downloaded_name

    file_type = Path(downloaded_name).suffix.lower().lstrip(".")
    extract_result = extract_text_from_bytes(
        file_bytes=file_bytes,
        file_type=file_type,
        file_name=downloaded_name,
        source_url=attachment_url,
        source_path=str(raw_path),
    )

    metadata = {
        "detail": json_safe(detail_values),
        "attachment": json_safe(attachment),
        "download_file_path": str(raw_path),
        "extract_result": extract_result.to_dict(),
    }

    if extract_result.success:
        text_path = build_output_path(output_dir, post_date, post_id, downloaded_name, "texts", ".txt")
        text_path.write_text(extract_result.text, encoding="utf-8")
        record["saved_file_path"] = str(text_path)
        record["text_length"] = extract_result.text_length
        record["extract_success"] = True
    else:
        record["error"] = extract_result.error

    metadata_path = build_output_path(output_dir, post_date, post_id, downloaded_name, "metadata", ".json")
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    record["metadata_file_path"] = str(metadata_path)
    return record


def build_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def build_output_path(
    output_dir: Path,
    post_date: date,
    post_id: str,
    file_name: str,
    category: str,
    force_suffix: str | None = None,
) -> Path:
    target_dir = output_dir / category / post_date.strftime("%Y%m%d")
    target_dir.mkdir(parents=True, exist_ok=True)

    source_path = Path(file_name)
    stem = safe_name(source_path.stem)
    suffix_token = source_path.suffix.lower().lstrip(".")
    if force_suffix is not None and suffix_token:
        stem = f"{stem}_{suffix_token}"

    suffix = force_suffix if force_suffix is not None else source_path.suffix
    return target_dir / f"{post_date.strftime('%Y%m%d')}_{safe_name(post_id)}_{stem}{suffix}"


def resolve_download_file_name(
    content_disposition: str | None,
    fallback_name: str,
    download_url: str,
) -> str:
    if content_disposition:
        match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', content_disposition, flags=re.IGNORECASE)
        if match:
            encoded_name = match.group(1)
            try:
                return encoded_name.encode("latin1").decode("utf-8")
            except UnicodeError:
                decoded_parts = decode_header(encoded_name)
                return "".join(
                    part.decode(charset or "utf-8") if isinstance(part, bytes) else part
                    for part, charset in decoded_parts
                )

    if Path(fallback_name).suffix:
        return fallback_name

    parsed_name = Path(urlparse(download_url).path).name
    if parsed_name and "." in parsed_name and not parsed_name.lower().endswith(".do"):
        return parsed_name
    return fallback_name or parsed_name or "attachment"


def _extract_raw_value(node: Any, attr: str) -> Any:
    if attr == "text":
        if isinstance(node, Tag):
            return _clean_text(node.get_text(" ", strip=True))
        if isinstance(node, str):
            return _clean_text(node)
        if hasattr(node, "text_content"):
            return _clean_text(node.text_content())
        return _clean_text(str(node))

    if isinstance(node, Tag):
        return node.get(attr)
    if hasattr(node, "get"):
        return node.get(attr)
    return None


def _to_lxml(context: Any) -> Any:
    if callable(getattr(context, "xpath", None)):
        return context
    return lxml_html.fromstring(_node_to_html(context))


def _node_to_html(context: Any) -> str:
    if isinstance(context, str):
        return context
    return str(context)


def _coerce_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not value:
        return None
    text = str(value).strip()
    for date_format in ("%Y-%m-%d", "%Y.%m.%d.", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            pass
    return None


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigValidationError(f"Config value must be an object: {name}")
    return value


def _clean_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def safe_name(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]+', "_", value).strip().rstrip(".")
    return cleaned or "file"


def json_safe(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value
