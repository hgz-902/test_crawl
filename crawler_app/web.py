from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import json
import uuid
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
    next_cron_run,
    normalize_interval,
    normalize_cron_expression,
    run_batch,
    settings_for_registered_jobs,
)
from crawler_app.windows_scheduler import (
    delete_managed_task,
    load_scheduler_registry,
    managed_task_name,
    sync_windows_scheduled_tasks,
    validate_windows_schedule_settings,
)
from crawler_app.workflow import preview_workflow_config
from crawlers.configurable_crawler import ConfigurableCrawler


BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
LOG_DIR = BASE_DIR / "logs"
ORCHESTRATION_STORE = OrchestrationStateStore()
DISPLAY_TIMEZONE = timezone(timedelta(hours=9), "KST")
ORCHESTRATION_FLASH_COOKIE = "crawler_orchestration_flash"
ORCHESTRATION_FLASH_DIR = BASE_DIR / "orchestration_state" / "flash"

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
    flash = _consume_orchestration_flash(request)
    scheduler_rows, scheduler_error = _scheduler_context(settings, jobs)
    response = templates.TemplateResponse(
        request,
        "orchestration.html",
        {
            "jobs": _display_jobs(jobs, settings),
            "settings": settings,
            "history": _display_history(ORCHESTRATION_STORE.load_history(limit=10)),
            "last_batch": flash.get("last_batch"),
            "message": flash.get("message"),
            "error": flash.get("error"),
            "smtp_ready": _smtp_ready(),
            "scheduler_rows": scheduler_rows,
            "scheduler_error": scheduler_error,
        },
    )
    if flash:
        response.delete_cookie(ORCHESTRATION_FLASH_COOKIE)
    return response


@app.post("/orchestration", response_class=HTMLResponse)
async def orchestration_action_route(request: Request) -> Response:
    _assert_same_origin_post(request)
    form = await request.form()
    action = str(form.get("action") or "").strip()
    if action == "save":
        return await save_orchestration_route(request)
    if action == "run":
        return await run_orchestration_route(request)
    if action == "sync":
        return await sync_orchestration_scheduler_route(request)
    if action == "delete_scheduler":
        return await delete_orchestration_scheduler_route(request)

    return _redirect_orchestration(error="알 수 없는 오케스트레이션 작업입니다.")


@app.post("/orchestration/save", response_class=HTMLResponse)
async def save_orchestration_route(request: Request) -> Response:
    _assert_same_origin_post(request)
    form = await request.form()
    settings, jobs = settings_for_registered_jobs(store=ORCHESTRATION_STORE)
    try:
        updated = _settings_from_form(form, jobs, settings, reset_next_run=True)
        validate_windows_schedule_settings(updated, jobs)
    except ValueError as exc:
        return _redirect_orchestration(error=f"Cron 설정 오류: {exc}")
    saved = ORCHESTRATION_STORE.save_settings(updated)
    _persist_job_schedule_state(saved, jobs)
    scheduler_message = ""
    error = None
    status_code = 200
    batch_dict: dict[str, Any] | None = None
    try:
        scheduler_result = await asyncio.to_thread(sync_windows_scheduled_tasks, saved, jobs)
        if scheduler_result.status == "synced":
            scheduler_message = f" Windows Task Scheduler 작업 {len(scheduler_result.created)}개를 재생성했습니다."
        elif scheduler_result.status == "skipped":
            scheduler_message = f" Windows Task Scheduler 동기화는 건너뛰었습니다({scheduler_result.skipped_reason})."
        if _truthy(form.get("force_due")):
            selected = [job.job_id for job in jobs if saved["jobs"].get(job.job_id, {}).get("enabled")]
            batch = await asyncio.to_thread(
                run_batch,
                selected,
                store=ORCHESTRATION_STORE,
                force_due=True,
                allow_email_send=bool(saved.get("allow_email_send", False)),
                parallel=True,
            )
            batch_dict = batch_to_dict(batch)
    except Exception as exc:
        error = f"Windows Task Scheduler 동기화 또는 즉시 실행 실패: {exc}"
        status_code = 500
    message = f"오케스트레이션 설정을 저장했습니다.{scheduler_message}"
    if batch_dict:
        message += " 즉시 실행을 완료했습니다."
    return _redirect_orchestration(message=message if not error else None, error=error, last_batch=batch_dict)


@app.post("/orchestration/run", response_class=HTMLResponse)
async def run_orchestration_route(request: Request) -> Response:
    _assert_same_origin_post(request)
    form = await request.form()
    settings, jobs = settings_for_registered_jobs(store=ORCHESTRATION_STORE)
    try:
        updated = _settings_from_form(form, jobs, settings, reset_next_run=False)
    except ValueError as exc:
        return _redirect_orchestration(error=f"Cron 설정 오류: {exc}")
    saved = ORCHESTRATION_STORE.save_settings(updated)
    _persist_job_schedule_state(saved, jobs)
    selected = [job.job_id for job in jobs if saved["jobs"].get(job.job_id, {}).get("enabled")]
    allow_email_send = bool(saved.get("allow_email_send", False))
    error = None
    batch_dict: dict[str, Any] | None = None
    try:
        batch = await asyncio.to_thread(
            run_batch,
            selected,
            store=ORCHESTRATION_STORE,
            force_due=True,
            allow_email_send=allow_email_send,
            parallel=True,
        )
        batch_dict = batch_to_dict(batch)
    except Exception as exc:
        error = str(exc)

    return _redirect_orchestration(
        message="수동 실행을 완료했습니다. 스케줄러 설정은 변경하지 않았습니다." if batch_dict else None,
        error=error,
        last_batch=batch_dict,
    )


@app.post("/orchestration/schedulers/sync", response_class=HTMLResponse)
async def sync_orchestration_scheduler_route(request: Request) -> Response:
    _assert_same_origin_post(request)
    form = await request.form()
    settings, jobs = settings_for_registered_jobs(store=ORCHESTRATION_STORE)
    try:
        updated = _settings_from_form(form, jobs, settings, reset_next_run=False)
        validate_windows_schedule_settings(updated, jobs)
        saved = ORCHESTRATION_STORE.save_settings(updated)
        _persist_job_schedule_state(saved, jobs)
        scheduler_result = await asyncio.to_thread(sync_windows_scheduled_tasks, saved, jobs)
        if scheduler_result.status == "synced":
            message = f"모니터링을 시작했습니다. Windows Task Scheduler 작업을 재생성했습니다(생성 {len(scheduler_result.created)}개 / 삭제 {len(scheduler_result.deleted)}개)."
        else:
            message = f"Windows Task Scheduler 동기화를 건너뛰었습니다({scheduler_result.skipped_reason})."
        error = None
        status_code = 200
    except Exception as exc:
        message = None
        error = f"모니터링 시작 실패: {exc}"
    return _redirect_orchestration(message=message, error=error)


@app.post("/orchestration/schedulers/delete", response_class=HTMLResponse)
async def delete_orchestration_scheduler_route(request: Request) -> Response:
    _assert_same_origin_post(request)
    form = await request.form()
    task_name = str(form.get("task_name") or "")
    job_id = str(form.get("job_id") or "")
    settings, jobs = settings_for_registered_jobs(store=ORCHESTRATION_STORE)
    message = None
    error = None
    try:
        result = await asyncio.to_thread(delete_managed_task, task_name)
        if job_id and job_id in settings.get("jobs", {}):
            settings["jobs"][job_id]["enabled"] = False
            settings["jobs"][job_id]["next_run_at"] = ""
            settings = ORCHESTRATION_STORE.save_settings(settings)
            ORCHESTRATION_STORE.save_job_state(
                job_id,
                {
                    "last_run_at": settings["jobs"][job_id].get("last_run_at"),
                    "next_run_at": "",
                    "last_status": settings["jobs"][job_id].get("last_status"),
                },
            )
        if result.status == "deleted":
            message = "선택한 스케줄러를 삭제했습니다."
        else:
            message = None
    except Exception as exc:
        error = f"스케줄러 삭제 실패: {exc}"
    return _redirect_orchestration(message=message if not error else None, error=error)


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


def _redirect_orchestration(
    *,
    message: str | None = None,
    error: str | None = None,
    last_batch: dict[str, Any] | None = None,
) -> RedirectResponse:
    response = RedirectResponse(url="/orchestration", status_code=303)
    payload = {key: value for key, value in {"message": message, "error": error, "last_batch": last_batch}.items() if value}
    if payload:
        flash_id = uuid.uuid4().hex
        ORCHESTRATION_FLASH_DIR.mkdir(parents=True, exist_ok=True)
        (ORCHESTRATION_FLASH_DIR / f"{flash_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        response.set_cookie(
            ORCHESTRATION_FLASH_COOKIE,
            flash_id,
            max_age=300,
            httponly=True,
            samesite="lax",
        )
    return response


def _consume_orchestration_flash(request: Request) -> dict[str, Any]:
    flash_id = str(request.cookies.get(ORCHESTRATION_FLASH_COOKIE) or "")
    if len(flash_id) != 32 or any(char not in "0123456789abcdef" for char in flash_id):
        return {}
    path = ORCHESTRATION_FLASH_DIR / f"{flash_id}.json"
    payload: dict[str, Any] = {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            payload = loaded
    except (OSError, json.JSONDecodeError):
        payload = {}
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    return payload


def _settings_from_form(form: Any, jobs: list[Any], current: dict[str, Any], *, reset_next_run: bool) -> dict[str, Any]:
    enabled = set(form.getlist("enabled_jobs"))
    schedule_base = datetime.now(timezone.utc)
    updated = {
        "keywords": _lines(form.get("keywords")),
        "recipients": _lines(form.get("recipients")),
        "sender": str(form.get("sender") or current.get("sender") or ""),
        "allow_email_send": _truthy(form.get("allow_email_send")),
        "jobs": {},
        "created_at": current.get("created_at"),
    }
    for job in jobs:
        previous = current.get("jobs", {}).get(job.job_id, {})
        if not isinstance(previous, dict):
            previous = {}
        previous_cron = normalize_cron_expression(previous.get("cron") or "")
        cron_expr = normalize_cron_expression(form.get(f"cron__{job.job_id}") or previous_cron)
        interval = normalize_interval(previous.get("interval"))
        previous_interval = normalize_interval(previous.get("interval"))
        next_run_at = str(previous.get("next_run_at") or "")
        if reset_next_run and job.job_id in enabled:
            next_run_at = next_cron_run(cron_expr, after=schedule_base).isoformat(timespec="seconds")
        elif next_run_at and (interval != previous_interval or cron_expr != previous_cron):
            next_run_at = ""
        updated["jobs"][job.job_id] = {
            "enabled": job.job_id in enabled,
            "cron": cron_expr,
            "interval": interval,
            "last_run_at": str(previous.get("last_run_at") or ""),
            "next_run_at": next_run_at,
            "last_status": str(previous.get("last_status") or ""),
        }
    return updated


def _render_orchestration_response(
    request: Request,
    *,
    settings: dict[str, Any],
    jobs: list[Any],
    error: str | None = None,
    message: str | None = None,
    last_batch: dict[str, Any] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    scheduler_rows, scheduler_error = _scheduler_context(settings, jobs)
    return templates.TemplateResponse(
        request,
        "orchestration.html",
        {
            "jobs": _display_jobs(jobs, settings),
            "settings": settings,
            "history": _display_history(ORCHESTRATION_STORE.load_history(limit=10)),
            "last_batch": last_batch,
            "message": message,
            "error": error,
            "smtp_ready": _smtp_ready(),
            "scheduler_rows": scheduler_rows,
            "scheduler_error": scheduler_error,
        },
        status_code=status_code,
    )


def _persist_job_schedule_state(settings: dict[str, Any], jobs: list[Any]) -> None:
    for job in jobs:
        job_settings = settings.get("jobs", {}).get(job.job_id, {})
        if not isinstance(job_settings, dict) or not job_settings.get("enabled"):
            continue
        ORCHESTRATION_STORE.save_job_state(
            job.job_id,
            {
                "last_run_at": job_settings.get("last_run_at"),
                "next_run_at": job_settings.get("next_run_at"),
                "last_status": job_settings.get("last_status"),
            },
        )


def _interval_delta(interval: dict[str, Any]) -> timedelta:
    normalized = normalize_interval(interval)
    value = int(normalized["value"])
    unit = normalized["unit"]
    if unit == "minutes":
        return timedelta(minutes=value)
    if unit == "days":
        return timedelta(days=value)
    return timedelta(hours=value)


def _lines(value: Any) -> list[str]:
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]


def _smtp_ready() -> bool:
    import os

    return bool(os.environ.get("SMTP_HOST") and os.environ.get("SMTP_PASSWORD"))


def _scheduler_context(settings: dict[str, Any], jobs: list[Any]) -> tuple[list[dict[str, Any]], str]:
    try:
        registry_entries = load_scheduler_registry()
    except Exception as exc:
        return [], str(exc)
    return _scheduler_rows(settings, jobs, registry_entries), ""


def _display_jobs(jobs: list[Any], settings: dict[str, Any]) -> list[dict[str, Any]]:
    displayed: list[dict[str, Any]] = []
    settings_jobs = settings.get("jobs", {}) if isinstance(settings.get("jobs"), dict) else {}
    for job in jobs:
        job_settings = settings_jobs.get(job.job_id, {})
        if not isinstance(job_settings, dict):
            job_settings = {}
        displayed.append(
            {
                "job_id": job.job_id,
                "config_name": job.config_name,
                "config_path": job.config_path,
                "output_dir": job.output_dir,
                "search_terms": list(job.search_terms),
                "filter_terms": list(job.filter_terms),
                "settings": job_settings,
                "last_run_at_display": _format_display_time(job_settings.get("last_run_at")),
                "next_run_at_display": _format_display_time(job_settings.get("next_run_at")),
            }
        )
    return displayed


def _scheduler_rows(settings: dict[str, Any], jobs: list[Any], registry_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    jobs_by_id = {job.job_id: job for job in jobs}
    rows: list[dict[str, Any]] = []
    for entry in registry_entries:
        job_id = str(entry.get("job_id") or "")
        job = jobs_by_id.get(job_id)
        job_settings = settings.get("jobs", {}).get(job_id, {}) if job_id else {}
        interval = normalize_interval(job_settings.get("interval"))
        rows.append(
            {
                "task_name": str(entry.get("task_name") or managed_task_name(job_id)),
                "job_id": job_id,
                "config_name": job.config_name if job is not None else str(entry.get("config_name") or "(설정 파일 없음)"),
                "output_dir": job.output_dir if job is not None else str(entry.get("output_dir") or ""),
                "search_terms_count": len(job.search_terms) if job is not None else int(entry.get("search_terms_count") or 0),
                "filter_terms_count": len(job.filter_terms) if job is not None else int(entry.get("filter_terms_count") or 0),
                "cron": str(job_settings.get("cron") or entry.get("cron") or ""),
                "interval": interval or normalize_interval(entry.get("interval")),
                "enabled": bool(job_settings.get("enabled")) if isinstance(job_settings, dict) else False,
                "registered_at": str(entry.get("registered_at") or ""),
                "registered_at_display": _format_display_time(entry.get("registered_at")),
                "app_last_run_at": str(job_settings.get("last_run_at") or "") if isinstance(job_settings, dict) else "",
                "app_last_run_at_display": _format_display_time(job_settings.get("last_run_at") if isinstance(job_settings, dict) else ""),
                "app_last_status": str(job_settings.get("last_status") or "") if isinstance(job_settings, dict) else "",
                "allow_email_send": bool(entry.get("allow_email_send", settings.get("allow_email_send"))),
            }
        )
    return rows


def _display_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    displayed: list[dict[str, Any]] = []
    for entry in history:
        if not isinstance(entry, dict):
            continue
        row = dict(entry)
        row["finished_at_display"] = _format_display_time(row.get("finished_at"))
        row["started_at_display"] = _format_display_time(row.get("started_at"))
        displayed.append(row)
    return displayed


def _format_display_time(value: Any) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(DISPLAY_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")


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

