from __future__ import annotations

import asyncio
import io
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import json
import re
import uuid
from urllib.parse import quote, quote_plus, urlparse
import zipfile

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
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
    list_managed_task_details,
    load_scheduler_registry,
    managed_task_name,
    stop_managed_tasks_with_script,
    sync_windows_scheduled_tasks,
    validate_windows_schedule_settings,
)
from crawler_app.workflow import preview_workflow_config
from crawler_app.news_ingestion import sync_news_ui_output_dir
from crawler_app.news_ui_api import init_news_ui_database, router as news_ui_router
from crawler_app.workflow_records_api import build_workflow_records_response
from crawler_app.workflow_records_rollup_scheduler import WorkflowRecordsRollupScheduler
from crawlers.configurable_crawler import ConfigurableCrawler


BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
LOG_DIR = BASE_DIR / "logs"
ORCHESTRATION_STORE = OrchestrationStateStore()
DISPLAY_TIMEZONE = timezone(timedelta(hours=9), "KST")
ORCHESTRATION_FLASH_COOKIE = "crawler_orchestration_flash"
ORCHESTRATION_FLASH_DIR = BASE_DIR / "orchestration_state" / "flash"
ORCHESTRATION_SCHEDULER_LOCK = asyncio.Lock()
WORKFLOW_RECORDS_ROLLUP_SCHEDULER = WorkflowRecordsRollupScheduler(project_root=BASE_DIR)

app = FastAPI(title="Crawler Config Manager")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(news_ui_router)


# workflow records rollup 스케줄러를 시작한다.
@app.on_event("startup")
async def start_workflow_records_rollup_scheduler() -> None:
    init_news_ui_database(BASE_DIR)
    WORKFLOW_RECORDS_ROLLUP_SCHEDULER.start()


# workflow records rollup 스케줄러를 중지한다.
@app.on_event("shutdown")
async def stop_workflow_records_rollup_scheduler() -> None:
    WORKFLOW_RECORDS_ROLLUP_SCHEDULER.stop()


# workflow records API HTTP 요청을 받아 응답을 반환한다.
@app.post("/api/workflow-records")
@app.post("/api/workflow-records/search")
async def workflow_records_api_route(request: Request) -> dict[str, Any]:
    try:
        payload = await _request_payload(request)
        return build_workflow_records_response(payload, outputs_root=BASE_DIR / "outputs")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# index 값을 계산해 반환한다.
@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {"configs": list_configs()},
    )


# parquet 변환 페이지를 렌더링한다.
@app.get("/parquet-converter", response_class=HTMLResponse)
async def parquet_converter_page(request: Request) -> HTMLResponse:
    rows, error = _parquet_converter_rows()
    return templates.TemplateResponse(
        request,
        "parquet_converter.html",
        {"parquet_rows": rows, "error": error},
    )


# parquet 파일 하나를 원본 bytes로 변환해 다운로드한다.
@app.get("/parquet-converter/download")
async def parquet_converter_download_route(path: str) -> Response:
    item = _read_parquet_conversion_item(path)
    return Response(
        content=item["content_bytes"],
        media_type="application/octet-stream",
        headers={"Content-Disposition": _content_disposition(str(item["source_file_name"]))},
    )


# 선택된 parquet 파일들을 원본 파일 ZIP으로 변환해 다운로드한다.
@app.post("/parquet-converter/download-zip")
async def parquet_converter_download_zip_route(request: Request) -> StreamingResponse:
    _assert_same_origin_post(request)
    form = await request.form()
    selected_paths = [str(value) for value in form.getlist("paths") if str(value).strip()]
    if not selected_paths:
        raise HTTPException(status_code=400, detail="선택된 parquet 파일이 없습니다.")

    buffer = io.BytesIO()
    used_names: set[str] = set()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for selected_path in selected_paths:
            item = _read_parquet_conversion_item(selected_path)
            archive_name = _zip_member_name(item, used_names)
            archive.writestr(archive_name, item["content_bytes"])
    buffer.seek(0)
    filename = f"parquet_originals_{datetime.now(DISPLAY_TIMEZONE):%Y%m%d_%H%M%S}.zip"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": _content_disposition(filename)},
    )


# orchestration 페이지 값을 계산해 반환한다.
@app.get("/orchestration", response_class=HTMLResponse)
async def orchestration_page(request: Request) -> HTMLResponse:
    settings, jobs = settings_for_registered_jobs(store=ORCHESTRATION_STORE)
    flash = _consume_orchestration_flash(request)
    scheduler_rows, scheduler_error = _scheduler_context(settings, jobs, include_details=False)
    response = templates.TemplateResponse(
        request,
        "orchestration.html",
        {
            "jobs": _display_jobs(jobs, settings, scheduler_rows),
            "settings": settings,
            "history": _display_history(ORCHESTRATION_STORE.load_history(limit=10)),
            "last_batch": _display_batch(flash.get("last_batch")),
            "message": flash.get("message"),
            "error": flash.get("error"),
            "smtp_ready": _smtp_ready(),
            "scheduler_rows": scheduler_rows,
            "scheduler_error": scheduler_error,
            "saved_schedule_rows": _saved_schedule_rows(settings, jobs),
        },
    )
    if flash:
        response.delete_cookie(ORCHESTRATION_FLASH_COOKIE)
    return response


# orchestration 스케줄러 상태 HTTP 요청을 받아 응답을 반환한다.
@app.get("/orchestration/schedulers/status")
async def orchestration_scheduler_status_route() -> dict[str, Any]:
    settings, jobs = settings_for_registered_jobs(store=ORCHESTRATION_STORE)
    scheduler_rows, scheduler_error = _scheduler_context(settings, jobs, include_details=True)
    return {"scheduler_rows": scheduler_rows, "scheduler_error": scheduler_error}


# orchestration action HTTP 요청을 받아 응답을 반환한다.
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
    if action == "stop_monitoring":
        return await stop_orchestration_monitoring_route(request)
    if action == "delete_scheduler":
        return await delete_orchestration_scheduler_route(request)

    return _redirect_orchestration(error="알 수 없는 오케스트레이션 작업입니다.")


# orchestration route를 저장한다.
@app.post("/orchestration/save", response_class=HTMLResponse)
async def save_orchestration_route(request: Request) -> Response:
    _assert_same_origin_post(request)
    form = await request.form()
    settings, jobs = settings_for_registered_jobs(store=ORCHESTRATION_STORE)
    try:
        updated = _settings_from_form(form, jobs, settings, reset_next_run=False)
        validate_windows_schedule_settings(updated, jobs)
    except ValueError as exc:
        return _redirect_orchestration(error=f"Cron 설정 오류: {exc}")
    ORCHESTRATION_STORE.save_settings(updated)
    return _redirect_orchestration(message="오케스트레이션 설정을 저장했습니다. 스케줄러와 크롤링 실행은 변경하지 않았습니다.")


# orchestration route를 실행한다.
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
            crawl_result_log_name="orchestration_manual",
        )
        batch_dict = batch_to_dict(batch)
    except Exception as exc:
        error = str(exc)

    return _redirect_orchestration(
        message="수동 실행을 완료했습니다. 스케줄러 설정은 변경하지 않았습니다." if batch_dict else None,
        error=error,
        last_batch=batch_dict,
    )


# orchestration 스케줄러 route를 현재 설정과 동기화한다.
@app.post("/orchestration/schedulers/sync", response_class=HTMLResponse)
async def sync_orchestration_scheduler_route(request: Request) -> Response:
    _assert_same_origin_post(request)
    if ORCHESTRATION_SCHEDULER_LOCK.locked():
        return _redirect_orchestration(message="모니터링 시작/종료 작업이 이미 처리 중입니다. 잠시 후 다시 확인해 주세요.")
    async with ORCHESTRATION_SCHEDULER_LOCK:
        form = await request.form()
        settings, jobs = settings_for_registered_jobs(store=ORCHESTRATION_STORE)
        try:
            updated = _settings_from_form(form, jobs, settings, reset_next_run=True)
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


# orchestration monitoring route를 중지한다.
@app.post("/orchestration/schedulers/stop", response_class=HTMLResponse)
async def stop_orchestration_monitoring_route(request: Request) -> Response:
    _assert_same_origin_post(request)
    if ORCHESTRATION_SCHEDULER_LOCK.locked():
        return _redirect_orchestration(message="모니터링 시작/종료 작업이 이미 처리 중입니다. 잠시 후 다시 확인해 주세요.")
    async with ORCHESTRATION_SCHEDULER_LOCK:
        settings, jobs = settings_for_registered_jobs(store=ORCHESTRATION_STORE)
        try:
            result = await asyncio.to_thread(stop_managed_tasks_with_script, delete_tasks=True)
            for job in jobs:
                job_settings = settings.get("jobs", {}).get(job.job_id, {})
                if isinstance(job_settings, dict):
                    ORCHESTRATION_STORE.save_job_state(
                        job.job_id,
                        {
                            "last_run_at": job_settings.get("last_run_at"),
                            "next_run_at": "",
                            "last_status": job_settings.get("last_status"),
                        },
                    )
            if result.status == "skipped":
                message = f"모니터링 종료를 건너뛰었습니다({result.skipped_reason})."
            elif result.errors:
                message = None
                error = "모니터링 종료 중 일부 작업에서 오류가 발생했습니다: " + "; ".join(result.errors)
                return _redirect_orchestration(error=error)
            else:
                message = f"모니터링을 종료했습니다. 종료 {len(result.ended)}개 / 삭제 {len(result.deleted)}개."
        except Exception as exc:
            return _redirect_orchestration(error=f"모니터링 종료 실패: {exc}")
    return _redirect_orchestration(message=message)


# orchestration 스케줄러 route를 삭제한다.
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
        delete_results = []
        for candidate in _task_names_for_delete(task_name, job_id):
            delete_results.append(await asyncio.to_thread(delete_managed_task, candidate))
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
        if any(result.status == "deleted" for result in delete_results):
            message = "선택한 스케줄러를 삭제했습니다."
        else:
            message = None
    except Exception as exc:
        error = f"스케줄러 삭제 실패: {exc}"
    return _redirect_orchestration(message=message if not error else None, error=error)


# new 설정 값을 계산해 반환한다.
@app.get("/configs/new", response_class=HTMLResponse)
async def new_config(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "editor.html",
        {"mode": "new", "config": default_config(), "config_id": "", "error": None},
    )


# edit 설정 값을 계산해 반환한다.
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


# 설정 route를 저장한다.
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


# 설정 route를 삭제한다.
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


# 미리보기 설정 HTTP 요청을 받아 응답을 반환한다.
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


# 설정 route를 실행한다.
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
    await asyncio.to_thread(_sync_news_ui_from_result, result)
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


# 크롤링 결과 output_dir을 뉴스 검토 UI용 SQLite DB에 동기화한다.
def _sync_news_ui_from_result(result: Any) -> None:
    output_dir = result.metadata.get("output_dir") if isinstance(result.metadata, dict) else None
    if not output_dir:
        return
    try:
        summary = sync_news_ui_output_dir(project_root=BASE_DIR, output_dir=output_dir)
        result.metadata["news_ui_sync"] = summary.to_dict()
    except Exception as exc:  # noqa: BLE001 - 크롤링 결과 페이지를 DB 동기화 실패로 막지 않는다.
        result.metadata["news_ui_sync_error"] = f"{type(exc).__name__}: {exc}"


# default 설정 값을 계산해 반환한다.
def default_config(name: str = "") -> dict[str, Any]:
    config_name = name or "new_site"
    return {
        "name": config_name,
        "category": "",
        "crawling_type": "",
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


# 안전한 json 값을 계산해 반환한다.
def _safe_json(value: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


# 요청 payload 값을 계산해 반환한다.
async def _request_payload(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "").lower()
    if "application/json" in content_type:
        try:
            payload = await request.json()
        except json.JSONDecodeError as exc:
            raise ValueError("request body must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("request body must be an object")
        return payload
    form = await request.form()
    return {key: form.get(key) for key in form.keys()}


# redirect orchestration 값을 계산해 반환한다.
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


# consume orchestration flash 값을 계산해 반환한다.
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


# settings form 값을 계산해 반환한다.
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


# orchestration 응답를 템플릿/화면 표시용 값으로 렌더링한다.
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
    scheduler_rows, scheduler_error = _scheduler_context(settings, jobs, include_details=False)
    return templates.TemplateResponse(
        request,
        "orchestration.html",
        {
            "jobs": _display_jobs(jobs, settings, scheduler_rows),
            "settings": settings,
            "history": _display_history(ORCHESTRATION_STORE.load_history(limit=10)),
            "last_batch": _display_batch(last_batch),
            "message": message,
            "error": error,
            "smtp_ready": _smtp_ready(),
            "scheduler_rows": scheduler_rows,
            "scheduler_error": scheduler_error,
            "saved_schedule_rows": _saved_schedule_rows(settings, jobs),
        },
        status_code=status_code,
    )


# persist job schedule 상태 값을 계산해 반환한다.
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


# interval delta 값을 계산해 반환한다.
def _interval_delta(interval: dict[str, Any]) -> timedelta:
    normalized = normalize_interval(interval)
    value = int(normalized["value"])
    unit = normalized["unit"]
    if unit == "minutes":
        return timedelta(minutes=value)
    if unit == "days":
        return timedelta(days=value)
    return timedelta(hours=value)


# lines 값을 계산해 반환한다.
def _lines(value: Any) -> list[str]:
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]


# smtp ready 값을 계산해 반환한다.
def _smtp_ready() -> bool:
    import os

    return bool(os.environ.get("SMTP_HOST") and os.environ.get("SMTP_PASSWORD"))


# 스케줄러 context 값을 계산해 반환한다.
def _scheduler_context(settings: dict[str, Any], jobs: list[Any], *, include_details: bool = True) -> tuple[list[dict[str, Any]], str]:
    try:
        registry_entries = load_scheduler_registry()
        task_details = list_managed_task_details() if include_details else []
    except Exception as exc:
        return [], str(exc)
    return _scheduler_rows(settings, jobs, registry_entries, task_details), ""


# display job 목록 값을 계산해 반환한다.
def _display_jobs(jobs: list[Any], settings: dict[str, Any], scheduler_rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    displayed: list[dict[str, Any]] = []
    settings_jobs = settings.get("jobs", {}) if isinstance(settings.get("jobs"), dict) else {}
    scheduler_by_job = {row.get("job_id"): row for row in scheduler_rows or []}
    for job in jobs:
        job_settings = settings_jobs.get(job.job_id, {})
        if not isinstance(job_settings, dict):
            job_settings = {}
        scheduler_row = scheduler_by_job.get(job.job_id)
        if scheduler_row:
            schedule_status = "등록됨" if job_settings.get("enabled") else "등록됨/설정 비활성"
        elif job_settings.get("enabled"):
            schedule_status = "미등록"
        else:
            schedule_status = "비활성"
        displayed.append(
            {
                "job_id": job.job_id,
                "config_name": job.config_name,
                "config_path": job.config_path,
                "output_dir": job.output_dir,
                "search_terms": list(job.search_terms),
                "filter_terms": list(job.filter_terms),
                "settings": job_settings,
                "schedule_status": schedule_status,
                "last_run_at_display": _format_display_time(job_settings.get("last_run_at")),
                "next_run_at_display": _format_display_time(job_settings.get("next_run_at")),
            }
        )
    return displayed


# 스케줄러 rows 값을 계산해 반환한다.
def _scheduler_rows(
    settings: dict[str, Any],
    jobs: list[Any],
    registry_entries: list[dict[str, Any]],
    task_details: list[Any],
) -> list[dict[str, Any]]:
    jobs_by_id = {job.job_id: job for job in jobs}
    details_by_task = {detail.task_name: detail for detail in task_details}
    rows: list[dict[str, Any]] = []
    seen_tasks: set[str] = set()
    entries_by_job: dict[str, list[dict[str, Any]]] = {}
    ungrouped_entries: list[dict[str, Any]] = []
    for entry in registry_entries:
        job_id = str(entry.get("job_id") or "").strip()
        if job_id:
            entries_by_job.setdefault(job_id, []).append(entry)
        else:
            ungrouped_entries.append(entry)

    for job_id, grouped_entries in entries_by_job.items():
        entry = grouped_entries[0]
        job = jobs_by_id.get(job_id)
        job_settings = settings.get("jobs", {}).get(job_id, {}) if job_id else {}
        task_names = [str(candidate.get("task_name") or "").strip() for candidate in grouped_entries]
        task_names = [candidate for candidate in task_names if candidate]
        if not task_names:
            task_names = [managed_task_name(job_id)]
        task_details_for_job = [details_by_task[task_name] for task_name in task_names if task_name in details_by_task]
        nearest_next_run = _nearest_scheduler_time([detail.next_run_time for detail in task_details_for_job], prefer_future=True)
        latest_last_run = _nearest_scheduler_time([detail.last_run_time for detail in task_details_for_job], prefer_future=False)
        representative_detail = _representative_detail(task_details_for_job, latest_last_run)
        representative_last_result = representative_detail.last_result if representative_detail is not None else ""
        interval = normalize_interval(job_settings.get("interval"))
        seen_tasks.update(task_names)
        rows.append(
            {
                "task_name": managed_task_name(job_id),
                "task_names": task_names,
                "task_count": len(task_names),
                "task_label": managed_task_name(job_id),
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
                "scheduler_status": _summarize_scheduler_status(task_details_for_job),
                "scheduler_last_run_at": latest_last_run,
                "scheduler_last_run_at_display": _format_display_time(latest_last_run),
                "scheduler_next_run_at": nearest_next_run,
                "scheduler_next_run_at_display": _format_display_time(nearest_next_run),
                "scheduler_last_result": representative_last_result,
                "task_action_path": _summarize_task_action_path([detail.task_to_run for detail in task_details_for_job]),
                "app_last_run_at": str(job_settings.get("last_run_at") or "") if isinstance(job_settings, dict) else "",
                "app_last_run_at_display": _format_display_time(job_settings.get("last_run_at") if isinstance(job_settings, dict) else ""),
                "app_last_status": str(job_settings.get("last_status") or "") if isinstance(job_settings, dict) else "",
                "app_last_status_display": _app_status_display(job_settings.get("last_status") if isinstance(job_settings, dict) else ""),
                "allow_email_send": bool(entry.get("allow_email_send", settings.get("allow_email_send"))),
                "scheduler_last_result_display": _format_scheduler_last_result(representative_last_result),
            }
        )
    for entry in ungrouped_entries:
        task_name = str(entry.get("task_name") or "").strip()
        if not task_name:
            continue
        detail = details_by_task.get(task_name)
        seen_tasks.add(task_name)
        rows.append(
            {
                "task_name": task_name,
                "task_names": [task_name],
                "task_count": 1,
                "task_label": task_name,
                "job_id": "",
                "config_name": str(entry.get("config_name") or "(설정 파일 없음)"),
                "output_dir": str(entry.get("output_dir") or ""),
                "search_terms_count": int(entry.get("search_terms_count") or 0),
                "filter_terms_count": int(entry.get("filter_terms_count") or 0),
                "cron": str(entry.get("cron") or ""),
                "interval": normalize_interval(entry.get("interval")),
                "enabled": False,
                "registered_at": str(entry.get("registered_at") or ""),
                "registered_at_display": _format_display_time(entry.get("registered_at")),
                "scheduler_status": detail.status if detail is not None else "등록 기록만 있음",
                "scheduler_last_run_at": detail.last_run_time if detail is not None else "",
                "scheduler_last_run_at_display": _format_display_time(detail.last_run_time) if detail is not None else "",
                "scheduler_next_run_at": detail.next_run_time if detail is not None else "",
                "scheduler_next_run_at_display": _format_display_time(detail.next_run_time) if detail is not None else "",
                "scheduler_last_result": detail.last_result if detail is not None else "",
                "scheduler_last_result_display": _format_scheduler_last_result(detail.last_result if detail is not None else ""),
                "task_action_path": detail.task_to_run if detail is not None else "",
                "app_last_run_at": "",
                "app_last_run_at_display": "",
                "app_last_status": "",
                "app_last_status_display": None,
                "allow_email_send": bool(entry.get("allow_email_send", settings.get("allow_email_send"))),
            }
        )
    for detail in task_details:
        if detail.task_name in seen_tasks:
            continue
        rows.append(
            {
                "task_name": detail.task_name,
                "task_names": [detail.task_name],
                "task_count": 1,
                "task_label": detail.task_name,
                "job_id": "",
                "config_name": "(등록 기록 없음)",
                "output_dir": "",
                "search_terms_count": 0,
                "filter_terms_count": 0,
                "cron": "",
                "interval": normalize_interval(None),
                "enabled": False,
                "registered_at": "",
                "registered_at_display": "",
                "scheduler_status": detail.status,
                "scheduler_last_run_at": detail.last_run_time,
                "scheduler_last_run_at_display": _format_display_time(detail.last_run_time),
                "scheduler_next_run_at": detail.next_run_time,
                "scheduler_next_run_at_display": _format_display_time(detail.next_run_time),
                "scheduler_last_result": detail.last_result,
                "scheduler_last_result_display": _format_scheduler_last_result(detail.last_result),
                "task_action_path": detail.task_to_run,
                "app_last_run_at": "",
                "app_last_run_at_display": "",
                "app_last_status": "",
                "app_last_status_display": None,
                "allow_email_send": bool(settings.get("allow_email_send")),
            }
        )
    return rows


# task 이름 목록 delete 값을 계산해 반환한다.
def _task_names_for_delete(task_name: str, job_id: str) -> list[str]:
    if job_id:
        matching = [
            str(entry.get("task_name") or "").strip()
            for entry in load_scheduler_registry()
            if str(entry.get("job_id") or "").strip() == job_id
        ]
        matching = [candidate for candidate in matching if candidate]
        if matching:
            return matching
    normalized = str(task_name or "").strip()
    return [normalized] if normalized else []


# nearest 스케줄러 시간 값을 계산해 반환한다.
def _nearest_scheduler_time(values: list[Any], *, prefer_future: bool) -> str:
    parsed_values: list[tuple[datetime, str]] = []
    for value in values:
        parsed = _parse_display_datetime(value)
        if parsed is not None:
            parsed_values.append((parsed, str(value)))
    if not parsed_values:
        return ""
    if prefer_future:
        now = datetime.now(timezone.utc)
        future_values = [(parsed, raw) for parsed, raw in parsed_values if parsed >= now]
        candidates = future_values or parsed_values
        return min(candidates, key=lambda item: item[0])[1]
    return max(parsed_values, key=lambda item: item[0])[1]


# representative detail 값을 계산해 반환한다.
def _representative_detail(details: list[Any], latest_last_run: str) -> Any | None:
    if not details:
        return None
    if latest_last_run:
        for detail in details:
            if str(detail.last_run_time or "") == latest_last_run:
                return detail
    return details[0]


# summarize 스케줄러 상태 값을 계산해 반환한다.
def _summarize_scheduler_status(details: list[Any]) -> str:
    statuses = [str(detail.status or "").strip() for detail in details if str(detail.status or "").strip()]
    if not statuses:
        return "등록 기록만 있음"
    unique_statuses = sorted(set(statuses))
    if len(unique_statuses) == 1:
        return unique_statuses[0]
    return "혼합 상태"


# summarize task action 경로 값을 계산해 반환한다.
def _summarize_task_action_path(paths: list[Any]) -> str:
    cleaned = [str(path or "").strip() for path in paths if str(path or "").strip()]
    if not cleaned:
        return ""
    unique_paths = sorted(set(cleaned))
    if len(unique_paths) == 1:
        return unique_paths[0]
    return f"여러 실행 경로({len(unique_paths)}개)"


# saved schedule rows 값을 계산해 반환한다.
def _saved_schedule_rows(settings: dict[str, Any], jobs: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    settings_jobs = settings.get("jobs", {}) if isinstance(settings.get("jobs"), dict) else {}
    for job in jobs:
        job_settings = settings_jobs.get(job.job_id, {})
        if not isinstance(job_settings, dict) or not job_settings.get("enabled"):
            continue
        rows.append(
            {
                "job_id": job.job_id,
                "config_name": job.config_name,
                "output_dir": job.output_dir,
                "cron": str(job_settings.get("cron") or "0 * * * *"),
                "saved_status": "저장됨",
                "last_run_at_display": _format_display_time(job_settings.get("last_run_at")),
                "next_run_at_display": _format_display_time(job_settings.get("next_run_at")),
                "last_status": str(job_settings.get("last_status") or ""),
                "last_status_display": _app_status_display(job_settings.get("last_status")),
                "search_terms_count": len(job.search_terms),
                "filter_terms_count": len(job.filter_terms),
            }
        )
    return rows


# display 이력 값을 계산해 반환한다.
def _display_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    displayed: list[dict[str, Any]] = []
    for entry in history:
        if not isinstance(entry, dict):
            continue
        row = dict(entry)
        row["finished_at_display"] = _format_display_time(row.get("finished_at"))
        row["started_at_display"] = _format_display_time(row.get("started_at"))
        row["status_display"] = _batch_status_display(row)
        results = []
        for result in row.get("results") or []:
            if not isinstance(result, dict):
                continue
            result_row = dict(result)
            result_row["status_display"] = _app_status_display(result_row.get("status"), failed=bool(result_row.get("error")))
            results.append(result_row)
        if results:
            row["results"] = results
        displayed.append(row)
    return displayed


# batch 실행 결과를 화면 표시용 값으로 보강한다.
def _display_batch(batch: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(batch, dict):
        return None
    displayed = dict(batch)
    displayed["status_display"] = _batch_status_display(displayed)
    results = []
    for result in displayed.get("results") or []:
        if not isinstance(result, dict):
            continue
        result_row = dict(result)
        result_row["status_display"] = _app_status_display(result_row.get("status"), failed=bool(result_row.get("error")))
        results.append(result_row)
    displayed["results"] = results
    return displayed


# app 상태 문자열을 운영자가 읽기 쉬운 표시값으로 변환한다.
def _app_status_display(status: Any, *, failed: bool = False) -> dict[str, str]:
    normalized = str(status or "").strip()
    normalized_lower = normalized.casefold()
    if failed or normalized_lower == "failed":
        return {"label": "실패", "note": ""}
    if normalized_lower in {"duplicate_stopped", "duplicated_stopped"}:
        return {"label": "성공", "note": "duplicated_stopped"}
    if normalized_lower == "succeeded":
        return {"label": "성공", "note": ""}
    if normalized_lower == "skipped_not_due":
        return {"label": "건너뜀", "note": ""}
    if normalized_lower == "skipped_running":
        return {"label": "건너뜀", "note": "already_running"}
    return {"label": normalized, "note": ""}


# batch 이력 상태를 성공/실패 중심 표시값으로 변환한다.
def _batch_status_display(entry: dict[str, Any]) -> dict[str, str]:
    failed = int(entry.get("failed") or 0)
    duplicate_stopped = int(entry.get("duplicate_stopped") or 0)
    status = str(entry.get("status") or "")
    if failed > 0 or status == "failed":
        return {"label": "실패", "note": ""}
    if duplicate_stopped > 0:
        return {"label": "성공", "note": "duplicated_stopped"}
    if status == "completed":
        return {"label": "완료", "note": ""}
    return _app_status_display(status)


# display 시간를 표시용 문자열로 변환한다.
def _format_display_time(value: Any) -> str:
    if not value:
        return ""
    if _is_scheduler_empty_time(value):
        return ""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        parsed = _parse_scheduler_time(value)
        if parsed is None:
            return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=DISPLAY_TIMEZONE)
    if parsed.year <= 1900:
        return ""
    return parsed.astimezone(DISPLAY_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")


# display 일시를 파싱한다.
def _parse_display_datetime(value: Any) -> datetime | None:
    if not value or _is_scheduler_empty_time(value):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        parsed = _parse_scheduler_time(value)
        if parsed is None:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=DISPLAY_TIMEZONE)
    if parsed.year <= 1900:
        return None
    return parsed.astimezone(timezone.utc)


# 스케줄러 empty 시간 여부를 판정한다.
def _is_scheduler_empty_time(value: Any) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return True
    lowered = raw.casefold()
    return lowered in {"n/a", "never", "none", "-"} or raw.startswith("11/30/1999") or raw.startswith("1899") or raw.startswith("0001")


# 스케줄러 시간를 파싱한다.
def _parse_scheduler_time(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    korean_parsed = _parse_korean_ampm_time(raw)
    if korean_parsed is not None:
        return korean_parsed
    for fmt in (
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %I:%M:%S %p",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


# korean ampm 시간를 파싱한다.
def _parse_korean_ampm_time(raw: str) -> datetime | None:
    import re

    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})\s+(오전|오후)\s+(\d{1,2}):(\d{2}):(\d{2})$", raw)
    if not match:
        return None
    year, month, day, ampm, hour, minute, second = match.groups()
    hour_value = int(hour)
    if ampm == "오후" and hour_value < 12:
        hour_value += 12
    if ampm == "오전" and hour_value == 12:
        hour_value = 0
    return datetime(int(year), int(month), int(day), hour_value, int(minute), int(second))


# 스케줄러 last 결과를 표시용 문자열로 변환한다.
def _format_scheduler_last_result(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw or raw.casefold() in {"n/a", "never", "none", "-"}:
        return "-"
    normalized = raw.lower()
    code_map = {
        "0": "성공",
        "0x0": "성공",
        "267008": "-",
        "0x41300": "-",
        "267009": "실행 중",
        "0x41301": "실행 중",
        "267010": "비활성",
        "0x41302": "비활성",
        "267011": "-",
        "0x41303": "-",
        "267012": "실행 종료됨",
        "0x41304": "실행 종료됨",
        "267014": "실행 종료됨",
        "0x41306": "실행 종료됨",
    }
    if normalized in code_map:
        return code_map[normalized]
    if raw.isdigit():
        return f"실패(코드: {raw})"
    if normalized.startswith("0x"):
        return f"실패(코드: {raw})"
    return raw


# 참/거짓 값을 계산해 반환한다.
def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


# outputs/*/tran/*.parquet 목록을 화면 표시용 row로 만든다.
def _parquet_converter_rows() -> tuple[list[dict[str, Any]], str | None]:
    outputs_root = BASE_DIR / "outputs"
    if not outputs_root.exists():
        return [], None

    rows: list[dict[str, Any]] = []
    error: str | None = None
    for parquet_path in sorted(outputs_root.glob("*/tran/*.parquet")):
        relative_path = parquet_path.relative_to(outputs_root)
        row = {
            "path": relative_path.as_posix(),
            "output_name": relative_path.parts[0],
            "parquet_file_name": parquet_path.name,
            "parquet_size": parquet_path.stat().st_size,
            "source_file_name": "",
            "source_relative_path": "",
            "tran_kind": _kind_from_parquet_name(parquet_path.name),
            "collected_at": "",
            "exported_at": "",
            "downloadable": False,
            "error": "",
        }
        try:
            item = _read_parquet_conversion_item(relative_path.as_posix())
            row.update(
                {
                    "source_file_name": item["source_file_name"],
                    "source_relative_path": item["source_relative_path"],
                    "tran_kind": item["tran_kind"],
                    "collected_at": item["collected_at"],
                    "exported_at": item["exported_at"],
                    "downloadable": True,
                }
            )
        except Exception as exc:  # noqa: BLE001 - 화면에는 깨진 parquet도 오류 row로 보여준다.
            row["error"] = str(exc)
            error = "일부 parquet 파일을 읽지 못했습니다. 오류 행을 확인해 주세요."
        rows.append(row)
    return rows, error


# parquet 파일 하나를 읽어 원본 다운로드에 필요한 값을 반환한다.
def _read_parquet_conversion_item(relative_path: str | Path) -> dict[str, Any]:
    parquet_path = _resolve_parquet_converter_path(relative_path)
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="pyarrow가 설치되어 있지 않아 parquet을 읽을 수 없습니다.") from exc

    try:
        table = pq.read_table(parquet_path)
    except Exception as exc:  # noqa: BLE001 - parquet 라이브러리 오류를 HTTP 오류로 변환한다.
        raise HTTPException(status_code=400, detail=f"parquet 파일을 읽을 수 없습니다: {exc}") from exc

    rows = table.to_pylist()
    if len(rows) != 1:
        raise HTTPException(status_code=400, detail="지원하지 않는 parquet row 구조입니다.")
    row = rows[0]
    content = row.get("content_bytes")
    if not isinstance(content, (bytes, bytearray)):
        raise HTTPException(status_code=400, detail="parquet에 content_bytes가 없습니다.")

    outputs_root = (BASE_DIR / "outputs").resolve()
    relative = parquet_path.relative_to(outputs_root)
    tran_kind = str(row.get("tran_kind") or _kind_from_parquet_name(parquet_path.name))
    source_file_name = _safe_download_file_name(row.get("source_file_name") or "download.bin")
    download_bytes = bytes(content)
    if tran_kind == "metadata":
        source_file_name = _safe_download_file_name(source_file_name or "workflow_records.json")
        download_bytes = _metadata_download_bytes(row, download_bytes)
    return {
        "path": relative.as_posix(),
        "output_name": relative.parts[0],
        "parquet_stem": parquet_path.stem,
        "parquet_file_name": parquet_path.name,
        "source_relative_path": str(row.get("source_relative_path") or ""),
        "source_file_name": source_file_name,
        "tran_kind": tran_kind,
        "collected_at": str(row.get("collected_at") or ""),
        "exported_at": str(row.get("exported_at") or ""),
        "content_bytes": download_bytes,
    }


# metadata parquet 다운로드에 원본 workflow_records와 매칭 manifest를 함께 보존한다.
def _metadata_download_bytes(row: dict[str, Any], content: bytes) -> bytes:
    workflow_records: Any
    try:
        workflow_records = json.loads(content.decode("utf-8"))
    except Exception:
        workflow_records = content.decode("utf-8", errors="replace")

    manifest: Any = []
    manifest_text = row.get("tran_manifest_json")
    if isinstance(manifest_text, str) and manifest_text.strip():
        try:
            manifest = json.loads(manifest_text)
        except json.JSONDecodeError:
            manifest = manifest_text

    payload = {
        "workflow_records": workflow_records,
        "tran_manifest": manifest,
        "source_relative_path": str(row.get("source_relative_path") or ""),
        "source_file_name": str(row.get("source_file_name") or "workflow_records.json"),
        "tran_kind": str(row.get("tran_kind") or "metadata"),
        "collected_at": str(row.get("collected_at") or ""),
        "exported_at": str(row.get("exported_at") or ""),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


# parquet 변환 화면에서 허용된 outputs 상대경로를 실제 파일로 해석한다.
def _resolve_parquet_converter_path(relative_path: str | Path) -> Path:
    raw = str(relative_path or "").strip().replace("\\", "/")
    if not raw:
        raise HTTPException(status_code=400, detail="parquet 경로가 비어 있습니다.")
    if raw.startswith("/") or raw.startswith("//") or re.match(r"^[A-Za-z]:", raw):
        raise HTTPException(status_code=400, detail="outputs 기준 상대경로만 사용할 수 있습니다.")
    parts = [part for part in raw.split("/") if part]
    if any(part == ".." for part in parts):
        raise HTTPException(status_code=400, detail="상위 경로 접근은 허용되지 않습니다.")
    if len(parts) != 3 or parts[1] != "tran" or not parts[2].endswith(".parquet"):
        raise HTTPException(status_code=400, detail="outputs/<name>/tran/*.parquet 형식만 지원합니다.")

    outputs_root = (BASE_DIR / "outputs").resolve()
    candidate = (outputs_root / Path(*parts)).resolve()
    try:
        candidate.relative_to(outputs_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="outputs 밖의 파일은 접근할 수 없습니다.") from exc
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="parquet 파일을 찾을 수 없습니다.")
    return candidate


# parquet 파일명 prefix에서 kind를 추정한다.
def _kind_from_parquet_name(file_name: str) -> str:
    prefix = str(file_name or "").split("_", 1)[0].casefold()
    if prefix in {"metadata", "download", "text", "file"}:
        return prefix
    return "file"


# HTTP 다운로드용 Content-Disposition 값을 만든다.
def _content_disposition(file_name: str) -> str:
    safe_name = _safe_download_file_name(file_name)
    ascii_fallback = safe_name.encode("ascii", "ignore").decode("ascii") or "download.bin"
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(safe_name)}"


# 브라우저/ZIP에서 위험한 파일명 문자를 제거한다.
def _safe_download_file_name(file_name: Any) -> str:
    raw = Path(str(file_name or "download.bin").replace("\\", "/")).name.strip()
    cleaned = re.sub(r"[\x00-\x1f<>:\"/\\|?*]+", "_", raw).strip(" .")
    return cleaned or "download.bin"


# ZIP 내부 경로를 output/parquet_stem/source_file_name 형태로 만든다.
def _zip_member_name(item: dict[str, Any], used_names: set[str]) -> str:
    output_name = _safe_zip_segment(item.get("output_name") or "output")
    parquet_stem = _safe_zip_segment(item.get("parquet_stem") or "parquet")
    source_file_name = _safe_download_file_name(item.get("source_file_name") or "download.bin")
    base = f"{output_name}/{parquet_stem}/{source_file_name}"
    candidate = base
    suffix = 1
    while candidate in used_names:
        stem = Path(source_file_name).stem or "download"
        ext = Path(source_file_name).suffix
        candidate = f"{output_name}/{parquet_stem}/{stem}_{suffix:03d}{ext}"
        suffix += 1
    used_names.add(candidate)
    return candidate


# ZIP 경로 segment에서 구분자와 위험 문자를 제거한다.
def _safe_zip_segment(value: Any) -> str:
    cleaned = re.sub(r"[\x00-\x1f<>:\"/\\|?*]+", "_", str(value or "")).strip(" .")
    return cleaned or "item"


# assert same origin post 값을 계산해 반환한다.
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
