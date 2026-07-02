from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from crawler_app.news_sqlite_store import (
    add_category_keywords,
    article_analysis,
    connect,
    default_db_path,
    delete_category_keyword,
    delete_category_keywords,
    filter_options,
    get_category_keywords,
    init_db,
    list_category_keywords,
    list_news,
    list_news_grouped,
    replace_category_keywords,
    save_article_analysis,
    stats,
    update_user_state,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
router = APIRouter()
DEFAULT_LLM_MODEL = "gpt-4o-mini"


# read/favorite 상태 변경 요청 body를 검증한다.
class StateUpdate(BaseModel):
    user_id: str
    value: bool


class SaveAnalysisRequest(BaseModel):
    user_id: str
    prompt_used: str
    sentiment_label: str
    sentiment_display: str | None = None
    action_plan: str
    impact: str
    action_source: str = "llm"
    sentiment_source: str = "llm"


class CategoryKeywordsRequest(BaseModel):
    keywords: list[str]


# 뉴스 UI API용 SQLite DB 경로를 반환한다.
def news_ui_db_path(project_root: str | Path = PROJECT_ROOT) -> Path:
    return Path(os.getenv("NEWS_UI_DB_PATH") or default_db_path(project_root))


# 뉴스 UI API용 SQLite schema를 준비한다.
def init_news_ui_database(project_root: str | Path = PROJECT_ROOT) -> None:
    init_db(news_ui_db_path(project_root))


# UI 콤보박스용 출처/검색어 옵션을 반환한다.
@router.get("/api/filter-options")
def get_filter_options(config_category: str = Query("PR")) -> dict[str, list[str]]:
    try:
        init_news_ui_database()
        with connect(news_ui_db_path()) as conn:
            return filter_options(conn, _query_dict(locals()))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"DB Error: {exc}") from exc


# 모니터링 카테고리별 키워드 설정 전체를 조회한다.
@router.get("/api/category-keywords")
def get_category_keyword_list(keyword_group: str = Query("PR")) -> list[dict[str, Any]]:
    try:
        init_news_ui_database()
        with connect(news_ui_db_path()) as conn:
            return list_category_keywords(conn, keyword_group)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"DB Error: {exc}") from exc


# 단일 카테고리의 키워드 목록을 조회한다.
@router.get("/api/category-keywords/{category_code}")
def get_category_keyword_detail(category_code: str, keyword_group: str = Query("PR")) -> dict[str, Any]:
    try:
        init_news_ui_database()
        with connect(news_ui_db_path()) as conn:
            return get_category_keywords(conn, category_code, keyword_group)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"DB Error: {exc}") from exc


# 단일 카테고리의 키워드 목록을 전체 교체 저장한다.
@router.put("/api/category-keywords/{category_code}")
def put_category_keywords(
    category_code: str,
    body: CategoryKeywordsRequest,
    keyword_group: str = Query("PR"),
) -> dict[str, Any]:
    try:
        init_news_ui_database()
        with connect(news_ui_db_path()) as conn:
            return replace_category_keywords(conn, category_code, body.keywords, keyword_group)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"DB Error: {exc}") from exc


# 단일 카테고리에 키워드를 추가한다.
@router.post("/api/category-keywords/{category_code}/keywords")
def post_category_keywords(
    category_code: str,
    body: CategoryKeywordsRequest,
    keyword_group: str = Query("PR"),
) -> dict[str, Any]:
    try:
        init_news_ui_database()
        with connect(news_ui_db_path()) as conn:
            return add_category_keywords(conn, category_code, body.keywords, keyword_group)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"DB Error: {exc}") from exc


# 키워드 1건을 삭제한다.
@router.delete("/api/category-keywords/keywords/{keyword_id}")
def delete_category_keyword_item(keyword_id: str) -> dict[str, Any]:
    try:
        init_news_ui_database()
        with connect(news_ui_db_path()) as conn:
            return delete_category_keyword(conn, keyword_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"DB Error: {exc}") from exc


# 단일 카테고리의 키워드 목록 전체를 삭제한다.
@router.delete("/api/category-keywords/{category_code}")
def delete_category_keyword_group(category_code: str, keyword_group: str = Query("PR")) -> dict[str, Any]:
    try:
        init_news_ui_database()
        with connect(news_ui_db_path()) as conn:
            return delete_category_keywords(conn, category_code, keyword_group)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"DB Error: {exc}") from exc


# 그룹 없는 뉴스 목록을 반환한다.
@router.get("/api/news")
def get_news(
    user_id: str = Query(...),
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    title: str | None = Query(None),
    source: str | None = Query(None),
    filter_term: str | None = Query(None),
    config_category: str = Query("PR"),
    category_code: str | None = Query(None),
    keyword_group: str = Query("PR"),
    read_status: str = Query("all"),
    favorite_status: str = Query("all"),
    major_only: bool = Query(False),
    has_analysis: bool = Query(False),
    sort_by: str = Query("published_at"),
    sort_order: str = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    try:
        init_news_ui_database()
        with connect(news_ui_db_path()) as conn:
            return list_news(conn, _query_dict(locals()))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"DB Error: {exc}") from exc


# 유사 기사 그룹 대표 목록과 접힌 유사 기사들을 반환한다.
@router.get("/api/news/grouped")
def get_news_grouped(
    user_id: str = Query(...),
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    title: str | None = Query(None),
    source: str | None = Query(None),
    filter_term: str | None = Query(None),
    config_category: str = Query("PR"),
    category_code: str | None = Query(None),
    keyword_group: str = Query("PR"),
    read_status: str = Query("all"),
    favorite_status: str = Query("all"),
    major_only: bool = Query(False),
    has_analysis: bool = Query(False),
    sort_by: str = Query("published_at"),
    sort_order: str = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    try:
        init_news_ui_database()
        with connect(news_ui_db_path()) as conn:
            return list_news_grouped(conn, _query_dict(locals()))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"DB Error: {exc}") from exc


# 현재 필터 기준 전체/읽음/미읽음/즐겨찾기 집계를 반환한다.
@router.get("/api/stats")
def get_stats(
    user_id: str = Query(...),
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    title: str | None = Query(None),
    source: str | None = Query(None),
    filter_term: str | None = Query(None),
    config_category: str = Query("PR"),
    category_code: str | None = Query(None),
    keyword_group: str = Query("PR"),
) -> dict[str, int]:
    try:
        init_news_ui_database()
        with connect(news_ui_db_path()) as conn:
            return stats(conn, _query_dict(locals()))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"DB Error: {exc}") from exc


# 기사 읽음/미읽음 상태를 변경한다.
@router.patch("/api/news/{article_id}/read")
def toggle_read(article_id: str, body: StateUpdate) -> dict[str, Any]:
    return _toggle_state(article_id, body, "read")


# 기사 즐겨찾기 상태를 변경한다.
@router.patch("/api/news/{article_id}/favorite")
def toggle_favorite(article_id: str, body: StateUpdate) -> dict[str, Any]:
    return _toggle_state(article_id, body, "favorite")


# 사용자가 확인한 분석 결과를 article_sentiment에 저장한다.
@router.post("/api/news/{article_id}/analysis/save")
def save_analysis(article_id: str, body: SaveAnalysisRequest) -> dict[str, Any]:
    try:
        init_news_ui_database()
        with connect(news_ui_db_path()) as conn:
            return save_article_analysis(
                conn,
                article_id,
                {
                    **body.model_dump(),
                    "model_name": os.getenv("NEWS_LLM_MODEL") or DEFAULT_LLM_MODEL,
                },
            )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"DB Error: {exc}") from exc


# 저장된 분석 결과를 조회한다.
@router.get("/api/news/{article_id}/analysis")
def get_analysis(article_id: str, user_id: str = Query(...)) -> dict[str, Any] | None:
    _ = user_id
    try:
        init_news_ui_database()
        with connect(news_ui_db_path()) as conn:
            return article_analysis(conn, article_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"DB Error: {exc}") from exc


# 상태 변경을 SQLite에 저장하고 API 응답을 만든다.
def _toggle_state(article_id: str, body: StateUpdate, field: str) -> dict[str, Any]:
    try:
        init_news_ui_database()
        with connect(news_ui_db_path()) as conn:
            return update_user_state(conn, body.user_id, article_id, field, body.value)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"DB Error: {exc}") from exc


# FastAPI locals()에서 내부 값을 제거해 store query dict로 바꾼다.
def _query_dict(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if key not in {"conn", "exc"}}
