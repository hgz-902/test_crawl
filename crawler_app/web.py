from __future__ import annotations

import asyncio
from dataclasses import asdict
from pathlib import Path
from typing import Any
import json
from urllib.parse import quote_plus
from urllib.parse import urlparse

from fastapi import FastAPI, Form, HTTPException, Request
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
from crawler_app.emailer import smtp_is_configured
from crawler_app.job_store import DEFAULT_INTERVAL_MINUTES, JobStore
from crawler_app.logging_utils import configure_logger, log_result
from crawler_app.run_safety import read_config_for_safety, run_safety_error
from crawler_app.scheduler import BackgroundJobScheduler
from crawler_app.workflow import (
    normalize_workflow_config,
    preview_workflow_config,
)
from crawlers.configurable_crawler import ConfigurableCrawler


BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
LOG_DIR = BASE_DIR / "logs"
JOB_STORE_PATH = BASE_DIR / "crawler_jobs.json"

app = FastAPI(title="Crawler Config Manager")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
job_store = JobStore(JOB_STORE_PATH)
job_scheduler = BackgroundJobScheduler(store=job_store, base_dir=BASE_DIR, log_dir=LOG_DIR)


@app.middleware("http")
async def reject_cross_origin_unsafe_requests(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        host = request.headers.get("host", "")
        origin = request.headers.get("origin", "")
        referer = request.headers.get("referer", "")
        if origin and _netloc(origin) != host:
            return Response("Cross-origin form posts are not allowed.", status_code=403)
        if not origin and referer and _netloc(referer) != host:
            return Response("Cross-origin form posts are not allowed.", status_code=403)
    return await call_next(request)


@app.on_event("startup")
async def start_job_scheduler() -> None:
    start = getattr(job_scheduler, "start", None)
    if callable(start):
        start()


@app.on_event("shutdown")
async def stop_job_scheduler() -> None:
    stop = getattr(job_scheduler, "stop", None)
    if callable(stop):
        await stop()

@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {"configs": list_configs()},
    )


@app.get("/jobs", response_class=HTMLResponse)
async def jobs_page(request: Request) -> HTMLResponse:
    jobs = job_store.list_jobs(list_configs())
    return templates.TemplateResponse(
        request,
        "jobs.html",
        {
            "jobs": jobs,
            "default_interval_minutes": DEFAULT_INTERVAL_MINUTES,
            "smtp_configured": smtp_is_configured(),
            "saved": request.query_params.get("saved") == "1",
            "ran": request.query_params.get("ran") or "",
        },
    )


@app.post("/jobs")
async def save_jobs_route(request: Request) -> Response:
    form = await request.form()
    configs = list_configs()
    config_ids = [config.path.stem for config in configs]
    enabled_ids = {str(value) for value in form.getlist("enabled")}
    intervals: dict[str, int] = {}
    for config_id in config_ids:
        raw_interval = str(form.get(f"interval_{config_id}") or DEFAULT_INTERVAL_MINUTES)
        try:
            intervals[config_id] = int(raw_interval)
        except ValueError:
            intervals[config_id] = DEFAULT_INTERVAL_MINUTES
    job_store.update_settings(config_ids, enabled_ids, intervals)
    return RedirectResponse(url="/jobs?saved=1", status_code=303)


@app.post("/jobs/{config_id}/run")
async def run_job_now_route(config_id: str) -> Response:
    known_ids = {config.path.stem for config in list_configs()}
    if config_id not in known_ids:
        raise HTTPException(status_code=404, detail="Unknown crawler config.")
    await job_scheduler.run_job(config_id, trigger="manual")
    return RedirectResponse(url=f"/jobs?ran={quote_plus(config_id)}", status_code=303)


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
        job_store.remove(name)
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
    known_ids = {config.path.stem for config in list_configs()}
    if name not in known_ids:
        raise HTTPException(status_code=404, detail="Unknown crawler config.")
    result_dict = await job_scheduler.run_job(name, trigger="manual")
    recent_data = [_compact_record_for_ui(record) for record in result_dict.get("data", [])[:20]]
    return templates.TemplateResponse(
        request,
        "result.html",
        {
            "name": name,
            "result": result_dict,
            "recent_data": recent_data,
        },
        status_code=200 if result_dict.get("success") else 500,
    )


def _netloc(url: str) -> str:
    return urlparse(url).netloc


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
    return read_config_for_safety(config_path)


def _run_safety_error(config: dict[str, Any]) -> str | None:
    return run_safety_error(config, BASE_DIR)


def _output_dir_safety_error(config: dict[str, Any]) -> str | None:
    from crawler_app.run_safety import output_dir_safety_error

    return output_dir_safety_error(config, BASE_DIR)


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
