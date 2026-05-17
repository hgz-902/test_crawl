from __future__ import annotations

import asyncio
from dataclasses import asdict
from pathlib import Path
from typing import Any
import json
from urllib.parse import quote_plus, urlparse

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
from crawler_app.logging_utils import configure_logger, log_result
from crawler_app.orchestration import (
    OrchestrationStateStore,
    batch_to_dict,
    normalize_interval,
    run_batch,
    settings_for_registered_jobs,
)
from crawler_app.windows_scheduler import sync_windows_scheduled_tasks
from crawler_app.workflow import preview_workflow_config
from crawlers.configurable_crawler import ConfigurableCrawler


BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
LOG_DIR = BASE_DIR / "logs"
ORCHESTRATION_STORE = OrchestrationStateStore()

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


@app.get("/orchestration", response_class=HTMLResponse)
async def orchestration_page(request: Request) -> HTMLResponse:
    settings, jobs = settings_for_registered_jobs(store=ORCHESTRATION_STORE)
    return templates.TemplateResponse(
        request,
        "orchestration.html",
        {
            "jobs": jobs,
            "settings": settings,
            "history": ORCHESTRATION_STORE.load_history(limit=10),
            "last_batch": None,
            "message": None,
            "error": None,
            "smtp_ready": _smtp_ready(),
        },
    )


@app.post("/orchestration/save", response_class=HTMLResponse)
async def save_orchestration_route(request: Request) -> HTMLResponse:
    _assert_same_origin_post(request)
    form = await request.form()
    settings, jobs = settings_for_registered_jobs(store=ORCHESTRATION_STORE)
    updated = _settings_from_form(form, jobs, settings)
    saved = ORCHESTRATION_STORE.save_settings(updated)
    scheduler_message = ""
    error = None
    status_code = 200
    try:
        scheduler_result = await asyncio.to_thread(sync_windows_scheduled_tasks, saved, jobs)
        if scheduler_result.status == "synced":
            scheduler_message = f" Windows Task Scheduler 작업 {len(scheduler_result.created)}개를 재생성했습니다."
        elif scheduler_result.status == "skipped":
            scheduler_message = f" Windows Task Scheduler 동기화는 건너뛰었습니다({scheduler_result.skipped_reason})."
    except Exception as exc:
        error = f"Windows Task Scheduler 동기화 실패: {exc}"
        status_code = 500
    return templates.TemplateResponse(
        request,
        "orchestration.html",
        {
            "jobs": jobs,
            "settings": saved,
            "history": ORCHESTRATION_STORE.load_history(limit=10),
            "last_batch": None,
            "message": f"오케스트레이션 설정을 저장했습니다.{scheduler_message}" if not error else None,
            "error": error,
            "smtp_ready": _smtp_ready(),
        },
        status_code=status_code,
    )


@app.post("/orchestration/run", response_class=HTMLResponse)
async def run_orchestration_route(request: Request) -> HTMLResponse:
    _assert_same_origin_post(request)
    form = await request.form()
    settings, jobs = settings_for_registered_jobs(store=ORCHESTRATION_STORE)
    updated = _settings_from_form(form, jobs, settings)
    saved = ORCHESTRATION_STORE.save_settings(updated)
    selected = [job.job_id for job in jobs if saved["jobs"].get(job.job_id, {}).get("enabled")]
    force_due = _truthy(form.get("force_due"))
    allow_email_send = _truthy(form.get("allow_email_send"))
    error = None
    batch_dict: dict[str, Any] | None = None
    try:
        batch = await asyncio.to_thread(
            run_batch,
            selected,
            store=ORCHESTRATION_STORE,
            force_due=force_due,
            allow_email_send=allow_email_send,
        )
        batch_dict = batch_to_dict(batch)
    except Exception as exc:
        error = str(exc)

    return templates.TemplateResponse(
        request,
        "orchestration.html",
        {
            "jobs": jobs,
            "settings": saved,
            "history": ORCHESTRATION_STORE.load_history(limit=10),
            "last_batch": batch_dict,
            "message": "수동 배치 실행이 완료되었습니다." if batch_dict else None,
            "error": error,
            "smtp_ready": _smtp_ready(),
        },
        status_code=500 if error else 200,
    )


@app.get("/configs/new", response_class=HTMLResponse)
async def new_config(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "editor.html",
        {"mode": "new", "config": default_config(), "config_id": "", "error": None},
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
        {"mode": "edit", "config": config, "config_id": name, "error": error},
    )


@app.post("/configs", response_class=HTMLResponse)
async def save_config_route(
    request: Request,
    payload: str = Form(...),
    original_id: str = Form(""),
) -> HTMLResponse:
    try:
        config = json.loads(payload)
        if original_id:
            path = save_config_as(config, original_id)
        else:
            path = save_config(config)
        return RedirectResponse(url=f"/?focus={quote_plus(path.stem)}", status_code=303)
    except Exception as exc:
        config = _safe_json(payload) or default_config()
        return templates.TemplateResponse(
            request,
            "editor.html",
            {"mode": "edit", "config": config, "config_id": original_id, "error": str(exc)},
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
        },
        status_code=400 if error else 200,
    )


@app.post("/configs/{name}/run", response_class=HTMLResponse)
async def run_config_route(request: Request, name: str) -> HTMLResponse:
    config_path = config_name_to_path(name)
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
    recent_data = result_dict.get("data", [])[:20]
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


def _settings_from_form(form: Any, jobs: list[Any], current: dict[str, Any]) -> dict[str, Any]:
    enabled = set(form.getlist("enabled_jobs"))
    updated = {
        "keywords": _lines(form.get("keywords")),
        "recipients": _lines(form.get("recipients")),
        "sender": str(form.get("sender") or current.get("sender") or ""),
        "jobs": {},
        "created_at": current.get("created_at"),
    }
    for job in jobs:
        previous = current.get("jobs", {}).get(job.job_id, {})
        if not isinstance(previous, dict):
            previous = {}
        interval = normalize_interval(
            {
                "value": form.get(f"interval_value__{job.job_id}"),
                "unit": form.get(f"interval_unit__{job.job_id}"),
            }
        )
        previous_interval = normalize_interval(previous.get("interval"))
        next_run_at = str(previous.get("next_run_at") or "")
        if next_run_at and interval != previous_interval:
            next_run_at = ""
        updated["jobs"][job.job_id] = {
            "enabled": job.job_id in enabled,
            "interval": interval,
            "last_run_at": str(previous.get("last_run_at") or ""),
            "next_run_at": next_run_at,
            "last_status": str(previous.get("last_status") or ""),
        }
    return updated


def _lines(value: Any) -> list[str]:
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]


def _smtp_ready() -> bool:
    import os

    return bool(os.environ.get("SMTP_HOST") and os.environ.get("SMTP_PASSWORD"))


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _assert_same_origin_post(request: Request) -> None:
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    source = origin or referer
    if not source:
        return
    parsed = urlparse(source)
    if not parsed.netloc:
        return
    request_host = request.url.netloc.lower()
    if parsed.netloc.lower() != request_host:
        raise HTTPException(status_code=403, detail="Cross-origin orchestration posts are not allowed.")
