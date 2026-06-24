from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
import hashlib
import json
from math import sqrt
import os
import re
import sqlite3
from typing import Any


DEFAULT_GROUPING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_GROUPING_THRESHOLD = 0.86
DEFAULT_LEXICAL_GUARD = 0.42
DEFAULT_MIN_TOKEN_JACCARD = 0.18
DEFAULT_MIN_SHARED_TOKENS = 2
DEFAULT_SEQUENCE_GUARD = 0.78
DEFAULT_REQUIRE_FIRST_TOKEN_MATCH = True
DEFAULT_REQUIRE_SLASH_SIGNATURE_MATCH = True
DEFAULT_SLASH_SIGNATURE_SEGMENTS = 2
BLOCKING_PROFILES = {
    "loose": {
        "require_first_token": False,
        "require_slash_signature": False,
        "min_shared_tokens": 1,
        "lexical_guard": 0.35,
        "min_token_jaccard": 0.10,
        "sequence_guard": 0.70,
    },
    "current": {
        "require_first_token": DEFAULT_REQUIRE_FIRST_TOKEN_MATCH,
        "require_slash_signature": DEFAULT_REQUIRE_SLASH_SIGNATURE_MATCH,
        "min_shared_tokens": DEFAULT_MIN_SHARED_TOKENS,
        "lexical_guard": DEFAULT_LEXICAL_GUARD,
        "min_token_jaccard": DEFAULT_MIN_TOKEN_JACCARD,
        "sequence_guard": DEFAULT_SEQUENCE_GUARD,
    },
    "strict": {
        "require_first_token": True,
        "require_slash_signature": True,
        "min_shared_tokens": 3,
        "lexical_guard": 0.50,
        "min_token_jaccard": 0.25,
        "sequence_guard": 0.82,
    },
}
MAJOR_SOURCE_PRIORITY = {
    "연합뉴스": 1,
    "yna.co.kr": 1,
    "조선일보": 2,
    "chosun.com": 2,
    "중앙일보": 2,
    "joongang.co.kr": 2,
    "동아일보": 2,
    "donga.com": 2,
}
TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]+")


# 기사 그룹핑 결과를 저장 계층에 넘기기 위한 데이터 객체다.
@dataclass(frozen=True)
class ArticleClusterAssignment:
    article_id: str
    cluster_id: str
    is_representative: bool
    priority_score: int


# 제목끼리 같은 기사 후보인지 판단하는 표면 유사도 지표다.
@dataclass(frozen=True)
class LexicalMetrics:
    token_jaccard: float
    sequence_ratio: float
    shared_token_count: int
    first_token_matches: bool
    slash_signature_matches: bool


# 같은 날짜의 기사 제목들을 유사도 기준으로 사전 그룹핑한다.
def build_article_clusters(
    rows: list[dict[str, Any]],
    *,
    threshold: float | None = None,
    cache_conn: sqlite3.Connection | None = None,
) -> list[ArticleClusterAssignment]:
    threshold_value = threshold if threshold is not None else _float_env("NEWS_GROUPING_THRESHOLD", DEFAULT_GROUPING_THRESHOLD)
    candidates = [row for row in rows if _text(row.get("article_id")) and _text(row.get("title"))]
    if not candidates:
        return []

    titles = [_text(row.get("title")) for row in candidates]
    vectors = _encode_rows(candidates, titles, cache_conn=cache_conn)
    clusters: list[list[int]] = []
    for index, row in enumerate(candidates):
        target_cluster: list[int] | None = None
        best_score = 0.0
        for cluster in clusters:
            representative = cluster[0]
            score = _same_story_similarity(
                vectors[index],
                vectors[representative],
                titles[index],
                titles[representative],
            )
            if score >= threshold_value and score > best_score:
                target_cluster = cluster
                best_score = score
        if target_cluster is None:
            clusters.append([index])
        else:
            target_cluster.append(index)

    assignments: list[ArticleClusterAssignment] = []
    for cluster in clusters:
        representative_index = _representative_index([candidates[index] for index in cluster])
        representative_row = candidates[cluster[representative_index]]
        cluster_id = _text(representative_row.get("article_id"))
        for offset, index in enumerate(cluster):
            row = candidates[index]
            article_id = _text(row.get("article_id"))
            priority_score = source_priority(row.get("source_site"))
            assignments.append(
                ArticleClusterAssignment(
                    article_id=article_id,
                    cluster_id=cluster_id,
                    is_representative=offset == representative_index,
                    priority_score=priority_score,
                )
            )
    return assignments


# 기사 출처의 대표 선정 우선순위를 계산한다.
def source_priority(source_site: Any) -> int:
    source = _text(source_site).lower()
    for key, priority in MAJOR_SOURCE_PRIORITY.items():
        if key.lower() in source:
            return priority
    return 99


# 같은 기사 묶음으로 볼 최종 유사도를 계산한다.
def _same_story_similarity(left_vector: Any, right_vector: Any, left_title: str, right_title: str) -> float:
    metrics = _lexical_metrics(left_title, right_title)
    if not _passes_lexical_guard(metrics):
        return 0.0
    return _similarity(left_vector, right_vector)


# 환경변수로 지정된 임베딩 모드에 맞춰 제목 벡터를 만든다.
def _encode_rows(rows: list[dict[str, Any]], titles: list[str], *, cache_conn: sqlite3.Connection | None) -> list[Any]:
    mode = _embedding_mode()
    if mode == "lexical":
        return [_lexical_vector(title) for title in titles]
    if mode == "cached" and cache_conn is not None:
        return _encode_titles_cached(rows, titles, cache_conn)
    return _encode_titles_model(titles)


# sentence-transformers가 있으면 사용하고, 없으면 로컬 lexical vector로 대체한다.
def _encode_titles_model(titles: list[str]) -> list[Any]:
    if _text(os.getenv("NEWS_GROUPING_PROVIDER")).lower() != "lexical":
        try:
            model_name = _text(os.getenv("NEWS_GROUPING_MODEL")) or DEFAULT_GROUPING_MODEL
            device = _text(os.getenv("NEWS_GROUPING_DEVICE")) or None
            model = _sentence_transformer_model(model_name, device or "")
            vectors = model.encode(titles, normalize_embeddings=True, show_progress_bar=False)
            return [list(vector) for vector in vectors]
        except Exception:
            if _text(os.getenv("NEWS_GROUPING_REQUIRE_MODEL")).lower() in {"1", "true", "yes"}:
                raise
    return [_lexical_vector(title) for title in titles]


# SQLite 캐시에 없는 제목 임베딩만 모델로 계산한다.
def _encode_titles_cached(rows: list[dict[str, Any]], titles: list[str], conn: sqlite3.Connection) -> list[Any]:
    model_name = _text(os.getenv("NEWS_GROUPING_MODEL")) or DEFAULT_GROUPING_MODEL
    vectors: list[Any | None] = [None] * len(titles)
    missing: list[tuple[int, str, str, str]] = []
    for index, (row, title) in enumerate(zip(rows, titles)):
        article_id = _text(row.get("article_id"))
        title_hash = _title_hash(title)
        cached = conn.execute(
            """
            SELECT embedding_json
            FROM article_title_embeddings
            WHERE article_id = ? AND title_hash = ? AND model_name = ?
            """,
            (article_id, title_hash, model_name),
        ).fetchone()
        if cached:
            try:
                vectors[index] = json.loads(cached["embedding_json"])
                continue
            except (TypeError, json.JSONDecodeError):
                pass
        missing.append((index, article_id, title_hash, title))
    if missing:
        encoded = _encode_titles_model([item[3] for item in missing])
        rows_to_cache = []
        for vector, (index, article_id, title_hash, _title) in zip(encoded, missing):
            vectors[index] = vector
            if isinstance(vector, dict):
                continue
            rows_to_cache.append(
                (article_id, title_hash, model_name, json.dumps([float(value) for value in vector]), _now_kst())
            )
        if rows_to_cache:
            conn.executemany(
                """
                INSERT INTO article_title_embeddings(article_id, title_hash, model_name, embedding_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(article_id, title_hash, model_name) DO UPDATE SET
                    embedding_json = excluded.embedding_json,
                    updated_at = excluded.updated_at
                """,
                rows_to_cache,
            )
    return [vector if vector is not None else _lexical_vector(title) for vector, title in zip(vectors, titles)]


# sentence-transformers 모델을 프로세스 안에서 재사용한다.
@lru_cache(maxsize=4)
def _sentence_transformer_model(model_name: str, device: str) -> Any:
    from sentence_transformers import SentenceTransformer  # type: ignore

    return SentenceTransformer(model_name, device=device or None)


# 제목의 표면 유사도 지표를 계산한다.
def _lexical_metrics(left_title: str, right_title: str) -> LexicalMetrics:
    left_sequence = _significant_tokens(left_title)
    right_sequence = _significant_tokens(right_title)
    left_tokens = set(left_sequence)
    right_tokens = set(right_sequence)
    jaccard = 0.0
    if left_tokens and right_tokens:
        jaccard = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    sequence = SequenceMatcher(None, left_title, right_title).ratio()
    return LexicalMetrics(
        token_jaccard=jaccard,
        sequence_ratio=sequence,
        shared_token_count=len(left_tokens & right_tokens),
        first_token_matches=bool(left_sequence and right_sequence and left_sequence[0] == right_sequence[0]),
        slash_signature_matches=_slash_signature_matches(left_title, right_title),
    )


# 환경변수로 조절되는 표면 유사도 guard를 통과하는지 판단한다.
def _passes_lexical_guard(metrics: LexicalMetrics) -> bool:
    profile = _blocking_profile()
    require_first_token = _bool_env("NEWS_GROUPING_REQUIRE_FIRST_TOKEN_MATCH", bool(profile["require_first_token"]))
    if require_first_token and not metrics.first_token_matches:
        return False
    require_slash_signature = _bool_env(
        "NEWS_GROUPING_REQUIRE_SLASH_SIGNATURE_MATCH", bool(profile["require_slash_signature"])
    )
    if require_slash_signature and not metrics.slash_signature_matches:
        return False
    min_shared_tokens = _int_env("NEWS_GROUPING_MIN_SHARED_TOKENS", int(profile["min_shared_tokens"]))
    if metrics.shared_token_count < min_shared_tokens:
        return False
    lexical_guard = _float_env("NEWS_GROUPING_LEXICAL_GUARD", float(profile["lexical_guard"]))
    min_jaccard = _float_env("NEWS_GROUPING_MIN_TOKEN_JACCARD", float(profile["min_token_jaccard"]))
    sequence_guard = _float_env("NEWS_GROUPING_SEQUENCE_GUARD", float(profile["sequence_guard"]))
    return (
        metrics.token_jaccard >= min_jaccard
        or metrics.sequence_ratio >= sequence_guard
        or max(metrics.token_jaccard, metrics.sequence_ratio) >= lexical_guard
    )


# 외부 모델이 없을 때 제목을 토큰 빈도 벡터로 바꾼다.
def _lexical_vector(title: str) -> dict[str, float]:
    tokens = _significant_tokens(title)
    vector: dict[str, float] = {}
    for token in tokens:
        vector[token] = vector.get(token, 0.0) + 1.0
    return vector


# 제목을 동적 핵심 토큰으로 분해한다.
def _significant_tokens(title: str) -> list[str]:
    tokens: list[str] = []
    for raw_token in TOKEN_RE.findall(title):
        for token in _expanded_tokens(raw_token):
            if token.isdigit():
                continue
            if len(token) < 2 and not token.isascii():
                continue
            tokens.append(token)
    return tokens


# SK온처럼 영문+한글이 붙은 토큰은 영문 접두어와 원 토큰을 함께 후보화한다.
def _expanded_tokens(raw_token: str) -> list[str]:
    token = raw_token.strip().lower()
    if not token:
        return []
    match = re.match(r"^([a-z]+)([가-힣]+)$", token)
    if match:
        return [match.group(1), token, match.group(2)]
    match = re.match(r"^([가-힣]+)([a-z]+)$", token)
    if match:
        return [match.group(1), token, match.group(2)]
    return [token]


# 슬래시로 구조화된 제목은 앞쪽 세그먼트가 같은지 확인한다.
def _slash_signature_matches(left_title: str, right_title: str) -> bool:
    left_signature = _slash_signature(left_title)
    right_signature = _slash_signature(right_title)
    if not left_signature and not right_signature:
        return True
    if not left_signature or not right_signature:
        return False
    return left_signature == right_signature


# 슬래시 구조 제목의 비교용 세그먼트 signature를 만든다.
def _slash_signature(title: str) -> tuple[str, ...]:
    if "/" not in title:
        return ()
    segment_count = max(_int_env("NEWS_GROUPING_SLASH_SIGNATURE_SEGMENTS", DEFAULT_SLASH_SIGNATURE_SEGMENTS), 1)
    segments = []
    for segment in title.split("/")[:segment_count]:
        normalized = " ".join(_significant_tokens(segment))
        if normalized:
            segments.append(normalized)
    return tuple(segments)


# sentence embedding 또는 lexical vector 간 유사도를 계산한다.
def _similarity(left: Any, right: Any) -> float:
    if isinstance(left, dict) and isinstance(right, dict):
        cosine = _dict_cosine(left, right)
        joined_left = " ".join(left.keys())
        joined_right = " ".join(right.keys())
        sequence = SequenceMatcher(None, joined_left, joined_right).ratio()
        return max(cosine, sequence)
    dot = sum(float(a) * float(b) for a, b in zip(left, right))
    left_norm = sqrt(sum(float(a) * float(a) for a in left))
    right_norm = sqrt(sum(float(b) * float(b) for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


# dict 기반 벡터의 cosine 유사도를 계산한다.
def _dict_cosine(left: dict[str, float], right: dict[str, float]) -> float:
    common = set(left) & set(right)
    dot = sum(left[key] * right[key] for key in common)
    left_norm = sqrt(sum(value * value for value in left.values()))
    right_norm = sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


# 클러스터 내 대표 기사 index를 선정한다.
def _representative_index(rows: list[dict[str, Any]]) -> int:
    sortable = []
    for index, row in enumerate(rows):
        sortable.append(
            (
                source_priority(row.get("source_site")),
                _text(row.get("published_at")) or _text(row.get("first_seen_at")),
                _text(row.get("article_id")),
                index,
            )
        )
    sortable.sort()
    return sortable[0][3]


# 환경변수 float 값을 읽는다.
def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, ""))
    except ValueError:
        return default


# 환경변수 int 값을 읽는다.
def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, ""))
    except ValueError:
        return default


# 환경변수 bool 값을 읽는다.
def _bool_env(name: str, default: bool) -> bool:
    value = _text(os.getenv(name)).lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


# 값에서 공백 제거 문자열을 얻는다.
def _text(value: Any) -> str:
    return str(value or "").strip()


# 제목 후보 필터 기본값은 운영 오분류를 줄이기 위해 strict 프로필을 사용한다.
def _blocking_profile() -> dict[str, bool | int | float]:
    mode = _text(os.getenv("NEWS_GROUPING_BLOCKING_MODE")).lower() or "strict"
    return BLOCKING_PROFILES.get(mode, BLOCKING_PROFILES["strict"])


# E축 실험용 임베딩 모드를 읽는다.
def _embedding_mode() -> str:
    explicit = _text(os.getenv("NEWS_GROUPING_EMBEDDING_MODE")).lower()
    if explicit in {"lexical", "model", "cached"}:
        return explicit
    provider = _text(os.getenv("NEWS_GROUPING_PROVIDER")).lower()
    if provider == "lexical":
        return "lexical"
    return "model"


# 제목 캐시 키를 만든다.
def _title_hash(title: str) -> str:
    return hashlib.sha256(title.strip().encode("utf-8")).hexdigest()


# SQLite 캐시 갱신 시각 문자열을 만든다.
def _now_kst() -> str:
    from datetime import datetime, timedelta, timezone

    return datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S")
