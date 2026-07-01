from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
import re
import sqlite3
import uuid


KST = timezone(timedelta(hours=9))
DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
DIRECT_SK_PATTERN = re.compile(r"(?<![A-Za-z0-9가-힣])SK(?![A-Za-z0-9가-힣])", re.IGNORECASE)
ALLOWED_SORTS = {
    "published_at": "published_at",
    "title": "title",
    "source_name": "source_site",
    "filter_term": "filter_term",
    "is_read": "is_read",
    "is_favorite": "is_favorite",
    "is_major": "is_active",
}
CATEGORY_PRIORITY = {
    "SKI": 1,
    "SKE": 2,
    "SKGC": 3,
    "SKEN": 4,
    "SKEO": 5,
    "SKO": 6,
    "SKIET": 7,
    "E&S": 8,
    "SK": 99,
}


# 뉴스 UI SQLite DB의 기본 경로를 반환한다.
def default_db_path(project_root: str | Path) -> Path:
    return Path(project_root) / "runtime" / "news_ui" / "news_ui.sqlite3"


# SQLite 연결을 열고 row_factory를 설정한다.
@contextmanager
def connect(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=60.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=60000")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# 뉴스 UI API가 사용할 SQLite schema를 생성한다.
def init_db(db_path: str | Path) -> None:
    with connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS crawl_articles (
                article_id TEXT PRIMARY KEY,
                record_key TEXT,
                source_site TEXT NOT NULL,
                source_config_name TEXT,
                canonical_url TEXT NOT NULL,
                title TEXT,
                published_at TEXT,
                first_seen_at TEXT,
                last_seen_at TEXT,
                created_at TEXT,
                updated_at TEXT,
                is_active INTEGER DEFAULT 1,
                crawl_date TEXT,
                group_date TEXT,
                filter_term TEXT,
                UNIQUE(source_site, canonical_url)
            );

            CREATE TABLE IF NOT EXISTS article_clusters (
                article_id TEXT PRIMARY KEY,
                cluster_id TEXT NOT NULL,
                group_date TEXT NOT NULL,
                is_representative INTEGER NOT NULL,
                priority_score INTEGER NOT NULL,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS article_sentiment (
                article_id TEXT PRIMARY KEY,
                sentiment TEXT,
                confidence REAL,
                model_name TEXT,
                analyzed_at TEXT,
                action_plan TEXT,
                impact TEXT,
                prompt_used TEXT,
                action_source TEXT,
                analyzed_by TEXT,
                confirmed_by TEXT,
                confirmed_at TEXT,
                sentiment_source TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS user_article_state (
                user_id TEXT NOT NULL,
                article_id TEXT NOT NULL,
                is_read INTEGER DEFAULT 0,
                read_at TEXT,
                is_favorite INTEGER DEFAULT 0,
                favorite_at TEXT,
                updated_at TEXT,
                PRIMARY KEY(user_id, article_id)
            );

            CREATE TABLE IF NOT EXISTS article_action_log (
                event_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                article_id TEXT NOT NULL,
                actor_type TEXT NOT NULL,
                action_type TEXT NOT NULL,
                event_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS crawl_filter_options (
                option_group TEXT NOT NULL,
                option_name TEXT NOT NULL,
                PRIMARY KEY(option_group, option_name)
            );

            CREATE TABLE IF NOT EXISTS article_title_embeddings (
                article_id TEXT NOT NULL,
                title_hash TEXT NOT NULL,
                model_name TEXT NOT NULL,
                embedding_json TEXT NOT NULL,
                updated_at TEXT,
                PRIMARY KEY(article_id, title_hash, model_name)
            );

            CREATE TABLE IF NOT EXISTS monitoring_category_keywords (
                keyword_id TEXT PRIMARY KEY,
                keyword_group TEXT NOT NULL DEFAULT 'PR',
                category_code TEXT NOT NULL,
                keyword TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(keyword_group, category_code, keyword)
            );

            CREATE INDEX IF NOT EXISTS idx_crawl_articles_group_date ON crawl_articles(group_date);
            CREATE INDEX IF NOT EXISTS idx_crawl_articles_source ON crawl_articles(source_site);
            CREATE INDEX IF NOT EXISTS idx_article_clusters_cluster ON article_clusters(cluster_id);
            CREATE INDEX IF NOT EXISTS idx_article_title_embeddings_model ON article_title_embeddings(model_name);
            CREATE INDEX IF NOT EXISTS idx_monitoring_category_keywords_group_category
                ON monitoring_category_keywords(keyword_group, category_code, sort_order);
            """
        )
        _migrate_crawl_articles_filter_term(conn)
        _migrate_article_sentiment(conn)


# 기존 API 테스트를 위해 모든 뉴스 UI 데이터를 비운다.
def clear_news_data(conn: sqlite3.Connection) -> None:
    for table in (
        "article_action_log",
        "user_article_state",
        "article_sentiment",
        "article_clusters",
        "crawl_filter_options",
        "article_title_embeddings",
        "crawl_articles",
    ):
        conn.execute(f"DELETE FROM {table}")


# 기사 1건을 안정 article_id 기준으로 upsert한다.
def upsert_article(conn: sqlite3.Connection, article: dict[str, Any]) -> None:
    now = now_kst()
    conn.execute(
        """
        INSERT INTO crawl_articles (
            article_id, record_key, source_site, source_config_name, canonical_url, title,
            published_at, first_seen_at, last_seen_at, created_at, updated_at,
            is_active, crawl_date, group_date, filter_term
        )
        VALUES (
            :article_id, :record_key, :source_site, :source_config_name, :canonical_url, :title,
            :published_at, :first_seen_at, :last_seen_at, :created_at, :updated_at,
            :is_active, :crawl_date, :group_date, :filter_term
        )
        ON CONFLICT(article_id) DO UPDATE SET
            record_key = excluded.record_key,
            source_site = excluded.source_site,
            source_config_name = excluded.source_config_name,
            canonical_url = excluded.canonical_url,
            title = excluded.title,
            published_at = COALESCE(excluded.published_at, crawl_articles.published_at),
            first_seen_at = COALESCE(crawl_articles.first_seen_at, excluded.first_seen_at),
            last_seen_at = excluded.last_seen_at,
            updated_at = excluded.updated_at,
            is_active = excluded.is_active,
            crawl_date = excluded.crawl_date,
            group_date = excluded.group_date,
            filter_term = excluded.filter_term
        """,
        {
            "article_id": article["article_id"],
            "record_key": article.get("record_key"),
            "source_site": article["source_site"],
            "source_config_name": article.get("source_config_name"),
            "canonical_url": article["canonical_url"],
            "title": article.get("title"),
            "published_at": article.get("published_at"),
            "first_seen_at": article.get("first_seen_at") or now,
            "last_seen_at": article.get("last_seen_at") or now,
            "created_at": article.get("created_at") or now,
            "updated_at": article.get("updated_at") or now,
            "is_active": 1 if article.get("is_active", True) else 0,
            "crawl_date": article.get("crawl_date"),
            "group_date": article.get("group_date"),
            "filter_term": article.get("filter_term"),
        },
    )


# source/filter_term 필터 옵션 테이블을 현재 기사 기준으로 재생성한다.
def rebuild_filter_options(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM crawl_filter_options")
    conn.execute(
        """
        INSERT OR IGNORE INTO crawl_filter_options(option_group, option_name)
        SELECT 'source', source_site
        FROM crawl_articles
        WHERE source_site IS NOT NULL AND source_site != ''
        """
    )
    for row in conn.execute(
        """
        SELECT filter_term
        FROM crawl_articles
        WHERE filter_term IS NOT NULL AND filter_term != ''
        """
    ):
        for term in _split_option_terms(row["filter_term"]):
            conn.execute(
                """
                INSERT OR IGNORE INTO crawl_filter_options(option_group, option_name)
                VALUES ('filter_term', ?)
                """,
                (term,),
            )


# joined filter_term 값을 UI 옵션용 개별 term으로 분리한다.
def _split_option_terms(value: str | None) -> list[str]:
    terms: list[str] = []
    for term in str(value or "").split(","):
        stripped = term.strip()
        if stripped and stripped not in terms:
            terms.append(stripped)
    return terms


# 기존 SQLite DB의 search_term 컬럼을 filter_term으로 마이그레이션한다.
def _migrate_crawl_articles_filter_term(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(crawl_articles)").fetchall()}
    if "filter_term" not in columns and "search_term" in columns:
        conn.execute("ALTER TABLE crawl_articles RENAME COLUMN search_term TO filter_term")
        columns.remove("search_term")
        columns.add("filter_term")
    elif "filter_term" in columns and "search_term" in columns:
        conn.execute(
            """
            UPDATE crawl_articles
            SET filter_term = search_term
            WHERE (filter_term IS NULL OR filter_term = '')
                AND search_term IS NOT NULL
                AND search_term != ''
            """
        )
    conn.execute("DROP INDEX IF EXISTS idx_crawl_articles_search_term")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_crawl_articles_filter_term ON crawl_articles(filter_term)")
    conn.execute("UPDATE OR IGNORE crawl_filter_options SET option_group = 'filter_term' WHERE option_group = 'search_term'")
    conn.execute("DELETE FROM crawl_filter_options WHERE option_group = 'search_term'")


# 개발팀이 공유한 article_sentiment 확장 컬럼을 기존 SQLite DB에도 안전하게 추가한다.
def _migrate_article_sentiment(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(article_sentiment)").fetchall()}
    expected = {
        "article_id": "TEXT PRIMARY KEY",
        "sentiment": "TEXT",
        "confidence": "REAL",
        "model_name": "TEXT",
        "analyzed_at": "TEXT",
        "action_plan": "TEXT",
        "impact": "TEXT",
        "prompt_used": "TEXT",
        "action_source": "TEXT",
        "analyzed_by": "TEXT",
        "confirmed_by": "TEXT",
        "confirmed_at": "TEXT",
        "sentiment_source": "TEXT",
        "updated_at": "TEXT",
    }
    for column, definition in expected.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE article_sentiment ADD COLUMN {column} {definition}")


# 모니터링 카테고리 키워드 설정 목록을 조회한다.
def list_category_keywords(conn: sqlite3.Connection, keyword_group: str = "PR") -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT keyword_id, keyword_group, category_code, keyword, sort_order, created_at, updated_at
        FROM monitoring_category_keywords
        WHERE keyword_group = ?
        ORDER BY category_code ASC, sort_order ASC, keyword ASC
        """,
        (_keyword_group(keyword_group),),
    ).fetchall()
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        category = row["category_code"]
        bucket = grouped.setdefault(
            category,
            {"keyword_group": row["keyword_group"], "category_code": category, "keywords": []},
        )
        bucket["keywords"].append(_category_keyword_item(row))
    return list(grouped.values())


# 단일 카테고리의 키워드 설정을 조회한다.
def get_category_keywords(conn: sqlite3.Connection, category_code: str, keyword_group: str = "PR") -> dict[str, Any]:
    group = _keyword_group(keyword_group)
    category = _category_code(category_code)
    rows = conn.execute(
        """
        SELECT keyword_id, keyword_group, category_code, keyword, sort_order, created_at, updated_at
        FROM monitoring_category_keywords
        WHERE keyword_group = ? AND category_code = ?
        ORDER BY sort_order ASC, keyword ASC
        """,
        (group, category),
    ).fetchall()
    return {"keyword_group": group, "category_code": category, "keywords": [_category_keyword_item(row) for row in rows]}


# 단일 카테고리의 키워드를 리스트 전체 교체 방식으로 저장한다.
def replace_category_keywords(
    conn: sqlite3.Connection,
    category_code: str,
    keywords: list[str],
    keyword_group: str = "PR",
) -> dict[str, Any]:
    group = _keyword_group(keyword_group)
    category = _category_code(category_code)
    normalized_keywords = _normalize_keywords(keywords)
    now = now_kst()
    conn.execute(
        "DELETE FROM monitoring_category_keywords WHERE keyword_group = ? AND category_code = ?",
        (group, category),
    )
    for index, keyword in enumerate(normalized_keywords, start=1):
        conn.execute(
            """
            INSERT INTO monitoring_category_keywords(
                keyword_id, keyword_group, category_code, keyword, sort_order, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (uuid.uuid4().hex, group, category, keyword, index, now, now),
        )
    return get_category_keywords(conn, category, group)


# 단일 카테고리에 키워드를 추가한다. 기존 키워드는 중복 추가하지 않는다.
def add_category_keywords(
    conn: sqlite3.Connection,
    category_code: str,
    keywords: list[str],
    keyword_group: str = "PR",
) -> dict[str, Any]:
    group = _keyword_group(keyword_group)
    category = _category_code(category_code)
    normalized_keywords = _normalize_keywords(keywords)
    now = now_kst()
    next_order = _next_keyword_sort_order(conn, group, category)
    for offset, keyword in enumerate(normalized_keywords):
        conn.execute(
            """
            INSERT OR IGNORE INTO monitoring_category_keywords(
                keyword_id, keyword_group, category_code, keyword, sort_order, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (uuid.uuid4().hex, group, category, keyword, next_order + offset, now, now),
        )
    return get_category_keywords(conn, category, group)


# 키워드 1건을 삭제한다.
def delete_category_keyword(conn: sqlite3.Connection, keyword_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT keyword_group, category_code
        FROM monitoring_category_keywords
        WHERE keyword_id = ?
        """,
        (keyword_id,),
    ).fetchone()
    if row is None:
        raise KeyError("keyword not found")
    conn.execute("DELETE FROM monitoring_category_keywords WHERE keyword_id = ?", (keyword_id,))
    _renumber_category_keywords(conn, row["keyword_group"], row["category_code"])
    return get_category_keywords(conn, row["category_code"], row["keyword_group"])


# 카테고리의 키워드 전체를 삭제한다.
def delete_category_keywords(conn: sqlite3.Connection, category_code: str, keyword_group: str = "PR") -> dict[str, Any]:
    group = _keyword_group(keyword_group)
    category = _category_code(category_code)
    conn.execute(
        "DELETE FROM monitoring_category_keywords WHERE keyword_group = ? AND category_code = ?",
        (group, category),
    )
    return {"keyword_group": group, "category_code": category, "keywords": []}


def _category_keyword_item(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "keyword_id": row["keyword_id"],
        "keyword": row["keyword"],
        "sort_order": row["sort_order"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _normalize_keywords(keywords: list[str]) -> list[str]:
    normalized: list[str] = []
    for raw in keywords:
        keyword = _keyword(raw)
        folded = keyword.casefold()
        if all(existing.casefold() != folded for existing in normalized):
            normalized.append(keyword)
    return normalized


def _keyword(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("keyword must not be blank")
    if len(text) > 200:
        raise ValueError("keyword must be 200 characters or shorter")
    return text


def _keyword_group(value: str) -> str:
    text = str(value or "PR").strip().upper()
    if not text:
        return "PR"
    if len(text) > 40:
        raise ValueError("keyword_group must be 40 characters or shorter")
    return text


def _category_code(value: str) -> str:
    text = str(value or "").strip().upper()
    if not text:
        raise ValueError("category_code must not be blank")
    if len(text) > 40:
        raise ValueError("category_code must be 40 characters or shorter")
    return text


def _next_keyword_sort_order(conn: sqlite3.Connection, keyword_group: str, category_code: str) -> int:
    row = conn.execute(
        """
        SELECT COALESCE(MAX(sort_order), 0) + 1 AS next_order
        FROM monitoring_category_keywords
        WHERE keyword_group = ? AND category_code = ?
        """,
        (keyword_group, category_code),
    ).fetchone()
    return int(row["next_order"] or 1)


def _renumber_category_keywords(conn: sqlite3.Connection, keyword_group: str, category_code: str) -> None:
    rows = conn.execute(
        """
        SELECT keyword_id
        FROM monitoring_category_keywords
        WHERE keyword_group = ? AND category_code = ?
        ORDER BY sort_order ASC, keyword ASC
        """,
        (keyword_group, category_code),
    ).fetchall()
    now = now_kst()
    for index, row in enumerate(rows, start=1):
        conn.execute(
            """
            UPDATE monitoring_category_keywords
            SET sort_order = ?, updated_at = ?
            WHERE keyword_id = ?
            """,
            (index, now, row["keyword_id"]),
        )


# 감성분석이 아직 없는 기사 제목들을 조회한다.
def unanalyzed_article_titles(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT a.article_id, a.title
        FROM crawl_articles a
        LEFT JOIN article_sentiment s ON a.article_id = s.article_id
        WHERE s.article_id IS NULL
            AND a.title IS NOT NULL
            AND a.title != ''
        ORDER BY COALESCE(a.published_at, a.first_seen_at), a.article_id
        """
    ).fetchall()
    return [dict(row) for row in rows]


# 배치 감성분석 결과를 article_sentiment에 upsert한다.
def upsert_batch_sentiments(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    now = now_kst()
    conn.executemany(
        """
        INSERT INTO article_sentiment(
            article_id, sentiment, confidence, model_name, analyzed_at, sentiment_source, updated_at
        )
        VALUES (
            :article_id, :sentiment, :confidence, :model_name, :analyzed_at, :sentiment_source, :updated_at
        )
        ON CONFLICT(article_id) DO UPDATE SET
            sentiment = excluded.sentiment,
            confidence = excluded.confidence,
            model_name = excluded.model_name,
            analyzed_at = excluded.analyzed_at,
            sentiment_source = excluded.sentiment_source,
            updated_at = excluded.updated_at
        """,
        [
            {
                "article_id": row["article_id"],
                "sentiment": row["sentiment"],
                "confidence": row["confidence"],
                "model_name": row.get("model_name") or "knu_sentiment_dict_v1",
                "analyzed_at": row.get("analyzed_at") or now,
                "sentiment_source": row.get("sentiment_source") or "batch",
                "updated_at": row.get("updated_at") or now,
            }
            for row in rows
        ],
    )
    return len(rows)


# 특정 날짜의 기존 cluster를 지우고 새 그룹핑 결과를 저장한다.
def replace_clusters(conn: sqlite3.Connection, group_date: str, assignments: list[Any]) -> None:
    now = now_kst()
    conn.execute("DELETE FROM article_clusters WHERE group_date = ?", (group_date,))
    conn.executemany(
        """
        INSERT INTO article_clusters(article_id, cluster_id, group_date, is_representative, priority_score, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                assignment.article_id,
                assignment.cluster_id,
                group_date,
                1 if assignment.is_representative else 0,
                assignment.priority_score,
                now,
            )
            for assignment in assignments
        ],
    )


# 특정 보도일의 기사 rows를 그룹핑용으로 조회한다.
def article_rows_for_grouping(conn: sqlite3.Connection, group_date: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT article_id, title, source_site, published_at, first_seen_at
        FROM crawl_articles
        WHERE group_date = ? AND title IS NOT NULL AND title != '' AND is_active = 1
        ORDER BY COALESCE(published_at, first_seen_at), article_id
        """,
        (group_date,),
    ).fetchall()
    return [dict(row) for row in rows]


# 현재 기사 테이블에 존재하는 모든 그룹핑 대상 날짜를 반환한다.
def all_article_group_dates(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT group_date
        FROM crawl_articles
        WHERE group_date IS NOT NULL AND group_date != ''
        ORDER BY group_date
        """
    ).fetchall()
    return [str(row["group_date"]) for row in rows]


# 필터 콤보박스 옵션을 반환한다.
def filter_options(conn: sqlite3.Connection) -> dict[str, list[str]]:
    sources = [
        row["option_name"]
        for row in conn.execute(
            "SELECT option_name FROM crawl_filter_options WHERE option_group = 'source' ORDER BY option_name"
        )
    ]
    terms = [
        row["option_name"]
        for row in conn.execute(
            "SELECT option_name FROM crawl_filter_options WHERE option_group = 'filter_term' ORDER BY option_name"
        )
    ]
    return {"sources": sources, "filter_terms": terms}


# flat 뉴스 목록 API 응답을 조회한다.
def list_news(conn: sqlite3.Connection, query: dict[str, Any]) -> dict[str, Any]:
    query = {**query, "_conn": conn}
    where_sql, params = _where_clause(query)
    sort_sql = _sort_sql(query)
    page, page_size, offset = _page(query)
    category_index = _category_keyword_index(conn, query)
    total = conn.execute(f"SELECT COUNT(*) AS cnt FROM crawl_articles a LEFT JOIN user_article_state s ON a.article_id = s.article_id AND s.user_id = ? {where_sql}", [query["user_id"], *params]).fetchone()["cnt"]
    rows = conn.execute(
        f"""
        SELECT {ARTICLE_SELECT_COLUMNS}
        FROM crawl_articles a
        LEFT JOIN user_article_state s ON a.article_id = s.article_id AND s.user_id = ?
        LEFT JOIN article_sentiment sen ON a.article_id = sen.article_id
        {where_sql}
        ORDER BY {sort_sql}, a.article_id ASC
        LIMIT ? OFFSET ?
        """,
        [query["user_id"], *params, page_size, offset],
    ).fetchall()
    return {
        "totalCount": int(total or 0),
        "page": page,
        "pageSize": page_size,
        "items": [_api_item(row, category_index=category_index) for row in rows],
    }


# 그룹 뉴스 목록 API 응답을 조회한다.
def list_news_grouped(conn: sqlite3.Connection, query: dict[str, Any]) -> dict[str, Any]:
    query = {**query, "_conn": conn}
    where_sql, params = _where_clause(query)
    sort_sql = _sort_sql(query)
    page, page_size, offset = _page(query)
    category_index = _category_keyword_index(conn, query)
    base_params = [query["user_id"], *params]
    representative_where = f"{where_sql} AND (c.article_id IS NULL OR c.is_representative = 1)"
    total = conn.execute(
        f"""
        SELECT COUNT(*) AS cnt
        FROM crawl_articles a
        LEFT JOIN user_article_state s ON a.article_id = s.article_id AND s.user_id = ?
        LEFT JOIN article_clusters c ON a.article_id = c.article_id
        {representative_where}
        """,
        base_params,
    ).fetchone()["cnt"]
    rows = conn.execute(
        f"""
        SELECT {ARTICLE_SELECT_COLUMNS}, c.cluster_id
        FROM crawl_articles a
        LEFT JOIN user_article_state s ON a.article_id = s.article_id AND s.user_id = ?
        LEFT JOIN article_sentiment sen ON a.article_id = sen.article_id
        LEFT JOIN article_clusters c ON a.article_id = c.article_id
        {representative_where}
        ORDER BY {sort_sql}, a.article_id ASC
        LIMIT ? OFFSET ?
        """,
        [*base_params, page_size, offset],
    ).fetchall()
    items = [_api_item(row, category_index=category_index) for row in rows]
    for item, row in zip(items, rows):
        item["cluster_id"] = row["cluster_id"]
        similar_articles = _similar_articles(conn, row["cluster_id"], query, category_index=category_index) if row["cluster_id"] else []
        item["similar_count"] = len(similar_articles)
        item["similar_articles"] = similar_articles
    summary_counts = _grouped_summary_counts(conn, query, where_sql, params)
    total_articles = conn.execute("SELECT COUNT(*) AS cnt FROM crawl_articles WHERE title IS NOT NULL AND title != ''").fetchone()["cnt"]
    return {
        "totalCount": int(total or 0),
        "totalArticles": int(total_articles or 0),
        "directMentionCount": summary_counts["directMentionCount"],
        "negativeCount": summary_counts["negativeCount"],
        "page": page,
        "pageSize": page_size,
        "items": items,
    }


# grouped API의 필터 전체 대상 기사 기준 요약 집계를 계산한다.
def _grouped_summary_counts(
    conn: sqlite3.Connection,
    query: dict[str, Any],
    where_sql: str,
    params: list[Any],
) -> dict[str, int]:
    rows = conn.execute(
        f"""
        SELECT a.title, sen.sentiment
        FROM crawl_articles a
        LEFT JOIN user_article_state s ON a.article_id = s.article_id AND s.user_id = ?
        LEFT JOIN article_sentiment sen ON a.article_id = sen.article_id
        {where_sql}
        """,
        [query["user_id"], *params],
    ).fetchall()
    return {
        "directMentionCount": sum(1 for row in rows if _mentions_direct_sk(row["title"])),
        "negativeCount": sum(1 for row in rows if str(row["sentiment"] or "").lower() == "negative"),
    }


# 통계 카드 API 응답을 조회한다.
def stats(conn: sqlite3.Connection, query: dict[str, Any]) -> dict[str, int]:
    query = {**query, "_conn": conn}
    where_sql, params = _where_clause(query, include_state_filters=False)
    row = conn.execute(
        f"""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN COALESCE(s.is_read, 0) = 0 THEN 1 ELSE 0 END) AS unread,
            SUM(CASE WHEN COALESCE(s.is_read, 0) = 1 THEN 1 ELSE 0 END) AS read,
            SUM(CASE WHEN COALESCE(s.is_favorite, 0) = 1 THEN 1 ELSE 0 END) AS favorite
        FROM crawl_articles a
        LEFT JOIN user_article_state s ON a.article_id = s.article_id AND s.user_id = ?
        {where_sql}
        """,
        [query["user_id"], *params],
    ).fetchone()
    return {
        "total": int(row["total"] or 0),
        "unread": int(row["unread"] or 0),
        "read": int(row["read"] or 0),
        "favorite": int(row["favorite"] or 0),
    }


# read/favorite 상태를 upsert하고 action log를 남긴다.
def update_user_state(conn: sqlite3.Connection, user_id: str, article_id: str, field: str, value: bool) -> dict[str, Any]:
    if field not in {"read", "favorite"}:
        raise ValueError("field must be read or favorite")
    now = now_kst()
    bool_value = 1 if value else 0
    state_col = "is_read" if field == "read" else "is_favorite"
    at_col = "read_at" if field == "read" else "favorite_at"
    conn.execute(
        f"""
        INSERT INTO user_article_state(user_id, article_id, {state_col}, {at_col}, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id, article_id) DO UPDATE SET
            {state_col} = excluded.{state_col},
            {at_col} = excluded.{at_col},
            updated_at = excluded.updated_at
        """,
        (user_id, article_id, bool_value, now if value else None, now),
    )
    action = field if value else f"un{field}"
    conn.execute(
        """
        INSERT INTO article_action_log(event_id, user_id, article_id, actor_type, action_type, event_at)
        VALUES (?, ?, ?, 'user', ?, ?)
        """,
        (uuid.uuid4().hex, user_id, article_id, action, now),
    )
    return {"status": "ok", state_col: value}


# LLM 분석 대상 기사 기본 정보를 조회한다.
def article_for_analysis(conn: sqlite3.Connection, article_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT article_id, title, canonical_url
        FROM crawl_articles
        WHERE article_id = ?
        """,
        (article_id,),
    ).fetchone()
    return dict(row) if row else None


# 사용자가 확인한 LLM 분석 결과를 article_sentiment에 저장한다.
def save_article_analysis(conn: sqlite3.Connection, article_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    now = now_kst()
    user_id = str(payload.get("user_id") or "")
    sentiment = str(payload.get("sentiment_label") or "neutral")
    if sentiment not in {"positive", "neutral", "negative"}:
        sentiment = "neutral"
    action_source = str(payload.get("action_source") or "llm")
    if action_source not in {"llm", "user_modified"}:
        action_source = "llm"
    sentiment_source = str(payload.get("sentiment_source") or "llm")
    if sentiment_source not in {"llm", "user_modified", "batch"}:
        sentiment_source = "llm"
    conn.execute(
        """
        INSERT INTO article_sentiment(
            article_id, sentiment, confidence, model_name, analyzed_at,
            action_plan, impact, prompt_used, action_source, analyzed_by,
            confirmed_by, confirmed_at, sentiment_source, updated_at
        )
        VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(article_id) DO UPDATE SET
            sentiment = excluded.sentiment,
            confidence = excluded.confidence,
            model_name = excluded.model_name,
            analyzed_at = excluded.analyzed_at,
            action_plan = excluded.action_plan,
            impact = excluded.impact,
            prompt_used = excluded.prompt_used,
            action_source = excluded.action_source,
            analyzed_by = excluded.analyzed_by,
            confirmed_by = excluded.confirmed_by,
            confirmed_at = excluded.confirmed_at,
            sentiment_source = excluded.sentiment_source,
            updated_at = excluded.updated_at
        """,
        (
            article_id,
            sentiment,
            str(payload.get("model_name") or "llm"),
            now,
            str(payload.get("action_plan") or ""),
            str(payload.get("impact") or ""),
            str(payload.get("prompt_used") or ""),
            action_source,
            user_id,
            user_id,
            now,
            sentiment_source,
            now,
        ),
    )
    conn.execute(
        """
        INSERT INTO article_action_log(event_id, user_id, article_id, actor_type, action_type, event_at)
        VALUES (?, ?, ?, 'user', 'analysis_confirmed', ?)
        """,
        (uuid.uuid4().hex, user_id, article_id, now),
    )
    return {"status": "ok", "confirmed_by": user_id}


# 저장된 LLM 분석 결과를 조회한다.
def article_analysis(conn: sqlite3.Connection, article_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT article_id,
            sentiment AS sentiment_label,
            prompt_used,
            action_plan,
            impact,
            action_source,
            sentiment_source,
            analyzed_by,
            confirmed_by,
            confirmed_at,
            updated_at
        FROM article_sentiment
        WHERE article_id = ?
            AND action_plan IS NOT NULL
            AND action_plan != ''
        LIMIT 1
        """,
        (article_id,),
    ).fetchone()
    return dict(row) if row else None


ARTICLE_SELECT_COLUMNS = """
    a.article_id,
    a.title,
    a.source_site AS source_name,
    a.filter_term,
    a.published_at,
    a.canonical_url AS url,
    a.is_active AS is_major,
    COALESCE(s.is_read, 0) AS is_read,
    s.read_at,
    COALESCE(s.is_favorite, 0) AS is_favorite,
    s.favorite_at,
    sen.sentiment,
    sen.confidence AS sentiment_confidence
"""


# cluster_id에 속한 대표 제외 유사 기사를 현재 목록 필터 안에서 조회한다.
def _similar_articles(
    conn: sqlite3.Connection,
    cluster_id: str,
    query: dict[str, Any],
    *,
    category_index: dict[str, list[str]],
) -> list[dict[str, Any]]:
    where_sql, params = _where_clause(query)
    rows = conn.execute(
        f"""
        SELECT {ARTICLE_SELECT_COLUMNS}
        FROM article_clusters c
        JOIN crawl_articles a ON c.article_id = a.article_id
        LEFT JOIN user_article_state s ON a.article_id = s.article_id AND s.user_id = ?
        LEFT JOIN article_sentiment sen ON a.article_id = sen.article_id
        {where_sql}
            AND c.cluster_id = ?
            AND c.is_representative = 0
        ORDER BY COALESCE(a.published_at, a.first_seen_at) DESC, a.article_id ASC
        """,
        [query["user_id"], *params, cluster_id],
    ).fetchall()
    return [_api_item(row, category_index=category_index) for row in rows]


# 공통 필터 SQL과 파라미터를 만든다.
def _where_clause(query: dict[str, Any], *, include_state_filters: bool = True) -> tuple[str, list[Any]]:
    clauses = ["a.title IS NOT NULL", "a.title != ''"]
    params: list[Any] = []
    if query.get("from_date"):
        clauses.append("COALESCE(a.published_at, a.first_seen_at) >= ?")
        params.append(str(query["from_date"]))
    if query.get("to_date"):
        clauses.append("COALESCE(a.published_at, a.first_seen_at) <= ?")
        params.append(f"{query['to_date']} 23:59:59")
    if query.get("title"):
        clauses.append("LOWER(a.title) LIKE LOWER(?)")
        params.append(f"%{query['title']}%")
    if query.get("source"):
        clauses.append("LOWER(a.source_site) LIKE LOWER(?)")
        params.append(f"%{query['source']}%")
    filter_term = query.get("filter_term")
    if filter_term:
        clauses.append("LOWER(a.filter_term) LIKE LOWER(?)")
        params.append(f"%{filter_term}%")
    category_code = str(query.get("category_code") or "").strip()
    if category_code:
        category_keywords = _category_filter_keywords(query)
        if category_keywords:
            keyword_clauses = []
            for keyword in category_keywords:
                keyword_clauses.append("LOWER(a.filter_term) LIKE LOWER(?)")
                params.append(f"%{keyword}%")
            clauses.append("(" + " OR ".join(keyword_clauses) + ")")
        else:
            clauses.append("1 = 0")
    if query.get("major_only"):
        clauses.append("a.is_active = 1")
    if include_state_filters:
        if query.get("read_status") == "read":
            clauses.append("COALESCE(s.is_read, 0) = 1")
        elif query.get("read_status") == "unread":
            clauses.append("COALESCE(s.is_read, 0) = 0")
        if query.get("favorite_status") == "favorite":
            clauses.append("COALESCE(s.is_favorite, 0) = 1")
        elif query.get("favorite_status") == "nonfavorite":
            clauses.append("COALESCE(s.is_favorite, 0) = 0")
    return "WHERE " + " AND ".join(clauses), params


# category_code 필터에 사용할 키워드를 설정 테이블에서 조회한다.
def _category_filter_keywords(query: dict[str, Any]) -> list[str]:
    conn = query.get("_conn")
    if not isinstance(conn, sqlite3.Connection):
        return []
    category = str(query.get("category_code") or "").strip()
    if not category:
        return []
    group = str(query.get("keyword_group") or "PR").strip() or "PR"
    rows = conn.execute(
        """
        SELECT keyword
        FROM monitoring_category_keywords
        WHERE keyword_group = ? AND category_code = ?
        ORDER BY sort_order ASC, keyword ASC
        """,
        (_keyword_group(group), _category_code(category)),
    ).fetchall()
    return [row["keyword"] for row in rows]


# sort 파라미터를 안전한 SQL 조각으로 바꾼다.
def _sort_sql(query: dict[str, Any]) -> str:
    sort_by = ALLOWED_SORTS.get(str(query.get("sort_by") or "published_at"), "published_at")
    sort_order = "ASC" if str(query.get("sort_order") or "").lower() == "asc" else "DESC"
    return f"{sort_by} {sort_order}"


# 페이지네이션 파라미터를 계산한다.
def _page(query: dict[str, Any]) -> tuple[int, int, int]:
    page = max(int(query.get("page") or DEFAULT_PAGE), 1)
    page_size = min(max(int(query.get("page_size") or DEFAULT_PAGE_SIZE), 1), MAX_PAGE_SIZE)
    return page, page_size, (page - 1) * page_size


# SQLite row를 프론트엔드 호환 API item으로 변환한다.
def _api_item(row: sqlite3.Row, *, category_index: dict[str, list[str]] | None = None) -> dict[str, Any]:
    filter_term = row["filter_term"]
    return {
        "article_id": row["article_id"],
        "title": row["title"],
        "source_name": row["source_name"],
        "filter_term": filter_term,
        "category_code": _category_code_for_filter_term(filter_term, category_index or {}),
        "published_at": row["published_at"],
        "url": row["url"],
        "is_major": bool(row["is_major"]),
        "is_read": bool(row["is_read"]),
        "read_at": row["read_at"],
        "is_favorite": bool(row["is_favorite"]),
        "favorite_at": row["favorite_at"],
        "sentiment": row["sentiment"],
        "sentiment_confidence": row["sentiment_confidence"],
    }


# 현재 요청 keyword_group 기준으로 category keyword index를 만든다.
def _category_keyword_index(conn: sqlite3.Connection, query: dict[str, Any]) -> dict[str, list[str]]:
    group = str(query.get("keyword_group") or "PR").strip() or "PR"
    rows = conn.execute(
        """
        SELECT category_code, keyword
        FROM monitoring_category_keywords
        WHERE keyword_group = ?
        ORDER BY category_code ASC, sort_order ASC, keyword ASC
        """,
        (_keyword_group(group),),
    ).fetchall()
    index: dict[str, list[str]] = {}
    for row in rows:
        keyword = _normalize_term(row["keyword"])
        category = _category_code(row["category_code"])
        if keyword:
            index.setdefault(keyword, [])
            if category not in index[keyword]:
                index[keyword].append(category)
    return index


# filter_term 토큰과 category keyword의 정확 일치만 사용해 대표 category_code를 계산한다.
def _category_code_for_filter_term(filter_term: str | None, category_index: dict[str, list[str]]) -> str | None:
    if not category_index:
        return None
    scores: dict[str, int] = {}
    for token in _split_filter_term_tokens(filter_term):
        for category in category_index.get(token, []):
            scores[category] = scores.get(category, 0) + 1
    if not scores:
        return None
    return sorted(scores, key=lambda category: (-scores[category], CATEGORY_PRIORITY.get(category.upper(), 50), category))[0]


def _split_filter_term_tokens(value: str | None) -> list[str]:
    tokens: list[str] = []
    for term in str(value or "").split(","):
        normalized = _normalize_term(term)
        if normalized and normalized not in tokens:
            tokens.append(normalized)
    return tokens


def _normalize_term(value: Any) -> str:
    return str(value or "").strip().lower()


def _mentions_direct_sk(title: str | None) -> bool:
    return bool(DIRECT_SK_PATTERN.search(str(title or "")))


# 현재 한국 시간을 문자열로 반환한다.
def now_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
