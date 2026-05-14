from __future__ import annotations

import asyncio
from dataclasses import asdict
from pathlib import Path
from typing import Any
import json
from urllib.parse import quote_plus

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import requests

from crawler_app.config_store import (
    config_name_to_path,
    delete_config,
    get_config,
    list_configs,
    save_config,
    save_config_as,
)
from crawler_app.logging_utils import configure_logger, log_result
from crawler_app.workflow import (
    DAUM_NEWS_API_FIXED_PAGE_LIMIT,
    DAUM_NEWS_API_MAX_LOOP_LIMIT,
    NAVER_NEWS_API_FIXED_PAGE_LIMIT,
    NAVER_NEWS_API_MAX_LOOP_LIMIT,
    normalize_workflow_config,
    preview_workflow_config,
)
from crawlers.configurable_crawler import ConfigurableCrawler


BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
LOG_DIR = BASE_DIR / "logs"

app = FastAPI(title="Crawler Config Manager")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {"configs": list_configs()},
    )


@app.get("/configs/new", response_class=HTMLResponse)
async def new_config(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "editor.html",
        {
            "mode": "new",
            "config": default_config(),
            "config_id": "",
            "error": None,
            "show_naver_api_panel": False,
            "show_daum_api_panel": False,
        },
    )


@app.get("/configs/{name}", response_class=HTMLResponse)
async def edit_config(request: Request, name: str) -> HTMLResponse:
    try:
        config = get_config(name)
        error = None
    except Exception as exc:
        config = default_config(name)
        error = str(exc)
    return templates.TemplateResponse(
        request,
        "editor.html",
        {
            "mode": "edit",
            "config": config,
            "config_id": name,
            "error": error,
            "show_naver_api_panel": _show_naver_api_panel(name, config),
            "show_daum_api_panel": _show_daum_api_panel(name, config),
        },
    )


@app.post("/configs", response_class=HTMLResponse)
async def save_config_route(
    request: Request,
    payload: str = Form(...),
    original_id: str = Form(""),
) -> HTMLResponse:
    try:
        config = json.loads(payload)
        _strip_provider_credential_fields(config)
        if isinstance(config, dict):
            config = normalize_workflow_config(config)
        if original_id:
            path = save_config_as(config, original_id)
        else:
            path = save_config(config)
        return RedirectResponse(url=f"/?focus={quote_plus(path.stem)}", status_code=303)
    except Exception as exc:
        config = _safe_json(payload) or default_config()
        _strip_provider_credential_fields(config)
        return templates.TemplateResponse(
            request,
            "editor.html",
            {
                "mode": "edit",
                "config": config,
                "config_id": original_id,
                "error": str(exc),
                "show_naver_api_panel": _show_naver_api_panel(original_id, config),
                "show_daum_api_panel": _show_daum_api_panel(original_id, config),
            },
            status_code=400,
        )


@app.post("/configs/{name}/delete")
async def delete_config_route(request: Request, name: str) -> Response:
    try:
        delete_config(name)
        return RedirectResponse(url="/", status_code=303)
    except OSError as exc:
        return templates.TemplateResponse(
            request,
            "index.html",
            {"configs": list_configs(), "error": f"Failed to delete config: {exc}"},
            status_code=500,
        )


@app.post("/configs/{name}/preview", response_class=HTMLResponse)
async def preview_config_route(request: Request, name: str, payload: str = Form(...)) -> HTMLResponse:
    config = _safe_json(payload) or default_config(name)
    _strip_provider_credential_fields(config)
    error: str | None = None
    try:
        preview = preview_workflow_config(config)
    except Exception as exc:
        preview = {"step_counts": []}
        error = str(exc)

    return templates.TemplateResponse(
        request,
        "editor.html",
        {
            "mode": "edit",
            "config": config,
            "config_id": name,
            "error": error,
            "preview": preview,
            "show_naver_api_panel": _show_naver_api_panel(name, config),
            "show_daum_api_panel": _show_daum_api_panel(name, config),
        },
        status_code=400 if error else 200,
    )


@app.post("/configs/{name}/run", response_class=HTMLResponse)
async def run_config_route(request: Request, name: str) -> HTMLResponse:
    config_path = config_name_to_path(name)
    config = _read_config_for_safety(config_path)
    safety_error = _run_safety_error(config)
    if safety_error:
        return templates.TemplateResponse(
            request,
            "result.html",
            {
                "name": name,
                "result": {
                    "crawler_name": "configurable",
                    "success": False,
                    "items_count": 0,
                    "message": "Run blocked by safety guard.",
                    "error": safety_error,
                    "metadata": {
                        "config_name": name,
                        "config_path": str(config_path),
                        "diagnostics": {"safety_error": safety_error},
                    },
                    "data": [],
                },
                "recent_data": [],
            },
            status_code=400,
        )
    logger = configure_logger(LOG_DIR)
    logger.info("Web run started | config=%s | config_path=%s", name, config_path)
    crawler = ConfigurableCrawler(config_path=config_path)
    result = await asyncio.to_thread(crawler.crawl)
    log_result(LOG_DIR, result)
    logger.info(
        "Web run finished | config=%s | success=%s | items=%s | output_dir=%s",
        name,
        result.success,
        result.items_count,
        result.metadata.get("output_dir"),
    )
    result_dict = result.to_dict()
    recent_data = [_compact_record_for_ui(record) for record in result_dict.get("data", [])[:20]]
    return templates.TemplateResponse(
        request,
        "result.html",
        {
            "name": name,
            "result": result_dict,
            "recent_data": recent_data,
        },
        status_code=200 if result.success else 500,
    )


def default_config(name: str = "") -> dict[str, Any]:
    config_name = name or "new_site"
    return {
        "name": config_name,
        "notes": "",
        "start_url": "",
        "output_dir": f"outputs/{config_name}",
        "renderer": "playwright",
        "timeout_ms": 30000,
        "headless": True,
        "ignore_https_errors": False,
        "search_terms": [],
        "filter_terms": [],
        "steps": [
            {"name": "open_detail", "xpath": "//a[1]", "action": "click", "attr": "", "wait_state": "visible"},
            {
                "name": "download_file",
                "xpath": "//a[contains(@href, 'download')]",
                "action": "download",
                "attr": "",
                "wait_state": "attached",
            },
        ],
    }


def _safe_json(value: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _read_config_for_safety(config_path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _run_safety_error(config: dict[str, Any]) -> str | None:
    output_error = _output_dir_safety_error(config)
    if output_error:
        return output_error

    steps = config.get("steps") or []
    first_step = steps[0] if steps and isinstance(steps[0], dict) else {}
    parser_attr = str(first_step.get("attr") or "").strip().lower()
    if parser_attr == "naver":
        try:
            page_limit = int(first_step.get("page_limit") or NAVER_NEWS_API_FIXED_PAGE_LIMIT)
            loop_limit = int(first_step.get("loop_limit") or 0)
        except (TypeError, ValueError):
            return "Naver UI runs require numeric page_limit and loop_limit."
        if page_limit != NAVER_NEWS_API_FIXED_PAGE_LIMIT:
            return f"Naver UI runs require page_limit={NAVER_NEWS_API_FIXED_PAGE_LIMIT}."
        if loop_limit <= 0 or loop_limit > NAVER_NEWS_API_MAX_LOOP_LIMIT:
            return f"Naver UI runs require loop_limit between 1 and {NAVER_NEWS_API_MAX_LOOP_LIMIT}."
    if parser_attr == "daum":
        try:
            page_limit = int(first_step.get("page_limit") or DAUM_NEWS_API_FIXED_PAGE_LIMIT)
            loop_limit = int(first_step.get("loop_limit") or 0)
        except (TypeError, ValueError):
            return "Daum UI runs require numeric page_limit and loop_limit."
        if page_limit != DAUM_NEWS_API_FIXED_PAGE_LIMIT:
            return f"Daum UI runs require page_limit={DAUM_NEWS_API_FIXED_PAGE_LIMIT}."
        if loop_limit <= 0 or loop_limit > DAUM_NEWS_API_MAX_LOOP_LIMIT:
            return f"Daum UI runs require loop_limit between 1 and {DAUM_NEWS_API_MAX_LOOP_LIMIT}."
    return None


def _output_dir_safety_error(config: dict[str, Any]) -> str | None:
    raw_output_dir = str(config.get("output_dir") or "").strip()
    if not raw_output_dir:
        return None
    output_path = Path(raw_output_dir)
    if not output_path.is_absolute():
        output_path = BASE_DIR / output_path
    try:
        resolved_output = output_path.resolve()
        resolved_base = BASE_DIR.resolve()
    except OSError:
        return "UI runs require a valid output_dir path."
    if resolved_output == resolved_base or resolved_base in resolved_output.parents:
        return None
    return "UI runs require output_dir under the crawler project folder."


def _show_naver_api_panel(config_id: str, config: dict[str, Any]) -> bool:
    config_name = (config_id or str(config.get("name") or "")).strip()
    if config_name == "네이버":
        return True
    if "openapi.naver.com/v1/search/news" in str(config.get("start_url") or "").lower():
        return True
    steps = config.get("steps") or []
    return any(
        isinstance(step, dict)
        and str(step.get("action") or "").strip().lower() == "parser"
        and str(step.get("attr") or "").strip().lower() == "naver"
        for step in steps
    )


def _show_daum_api_panel(config_id: str, config: dict[str, Any]) -> bool:
    config_name = (config_id or str(config.get("name") or "")).strip()
    if config_name == "다음":
        return True
    if "dapi.kakao.com/v2/search/web" in str(config.get("start_url") or "").lower():
        return True
    steps = config.get("steps") or []
    return any(
        isinstance(step, dict)
        and str(step.get("action") or "").strip().lower() == "parser"
        and str(step.get("attr") or "").strip().lower() == "daum"
        for step in steps
    )


def _strip_provider_credential_fields(config: dict[str, Any]) -> None:
    config.pop("naver_client_id", None)
    config.pop("naver_client_secret", None)
    config.pop("kakao_rest_api_key", None)


def _compact_record_for_ui(record: Any) -> Any:
    if not isinstance(record, dict):
        return record
    extracts = record.get("extracts") if isinstance(record.get("extracts"), dict) else {}
    return {
        "record_key": record.get("record_key"),
        "item_index": record.get("item_index"),
        "search_term": record.get("search_term"),
        "success": record.get("success"),
        "output_file": record.get("output_file"),
        "error": record.get("error"),
        "extracts": {
            "title": extracts.get("title"),
            "detail_url": extracts.get("detail_url"),
            "originallink": extracts.get("originallink"),
            "pubDate": extracts.get("pubDate"),
            "description": extracts.get("description"),
        },
        "steps": record.get("steps", []),
    }
