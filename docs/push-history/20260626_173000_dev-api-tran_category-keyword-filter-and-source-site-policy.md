# dev/API+Tran 카테고리 키워드 필터 API 및 출처명 저장 정책 보강

## 목적

개발팀 UI의 왼쪽 사이드바 카테고리(SK, SKI, SKE 등)를 클릭했을 때, 서버가 해당 카테고리에 저장된 키워드 목록을 기준으로 기사 목록을 반환할 수 있도록 로컬 SQLite 기반 뉴스 UI API를 보강했다.

동시에 최근 논의된 출처명 저장 정책을 반영했다. 일반 크롤러는 설정명 기반 언론사명을 저장하고, API형 수집기는 각 API 또는 원문 URL에서 확보 가능한 값을 기준으로 `source_site`를 저장한다.

## 누적 요청 흐름

- 개발팀이 제공한 Databricks 기반 `GET /api/news`, `GET /api/news/grouped`, `GET /api/filter-options`, `GET /api/stats`, read/favorite API를 로컬 크롤링 서버에 이관했다.
- 이후 UI 사진과 요구사항을 기준으로 왼쪽 사이드바 카테고리(SK 등)에 매핑되는 키워드 목록을 조회, 저장, 추가, 삭제할 API가 필요해졌다.
- 카테고리 클릭 시 프론트가 긴 키워드 배열을 직접 넘기는 방식은 URL 길이, 동기화, 보안/일관성 측면에서 불리하므로, 프론트는 `category_code=SK`만 넘기고 서버가 SQLite에서 키워드를 조회해 `/api/news` 필터에 적용하는 방식으로 결정했다.
- `search_term`은 더 이상 뉴스 UI API에서 사용하지 않기로 하여 SQLite 컬럼과 API 파라미터를 `filter_term` 중심으로 정리했다.
- 개발팀 요청에 따라 push 대상에서 `tests/` 폴더는 제외하고, 소스와 운영 코드 중심으로 반영한다.

## 변경 파일

### `crawler_app/news_sqlite_store.py`

- SQLite 스키마에 `monitoring_category_keywords` 테이블을 추가했다.
- 기존 `crawl_articles.search_term` 컬럼이 있는 DB는 자동으로 `filter_term` 컬럼으로 마이그레이션하도록 보강했다.
- `crawl_filter_options`도 `filter_term` 기준으로 갱신하도록 변경했다.
- 카테고리 키워드 CRUD helper를 추가했다.
- `/api/news`, `/api/news/grouped`, `/api/stats`에서 쓰는 공통 WHERE 생성 로직에 `category_code` 필터를 추가했다.
- `category_code`가 들어오면 서버가 `monitoring_category_keywords`에서 키워드 목록을 조회하고, `crawl_articles.filter_term`에 OR 조건으로 적용한다.

### `crawler_app/news_ui_api.py`

- 뉴스 목록 API에서 `search_term` 파라미터를 제거하고 `filter_term`, `category_code`, `keyword_group` 기반으로 정리했다.
- `GET /api/news`, `GET /api/news/grouped`, `GET /api/stats`에 `category_code`를 추가했다.
- 카테고리 키워드 관리 API를 추가했다.
  - `GET /api/category-keywords`
  - `GET /api/category-keywords/{category_code}`
  - `PUT /api/category-keywords/{category_code}`
  - `POST /api/category-keywords/{category_code}/keywords`
  - `DELETE /api/category-keywords/keywords/{keyword_id}`
  - `DELETE /api/category-keywords/{category_code}`
- 키워드 ID 기반 PATCH 수정 API는 제거했다. 사용자가 ID를 직접 다루기 번거롭기 때문에 수정은 `PUT`으로 카테고리 전체 목록을 교체하는 방식으로 통일했다.

### `crawler_app/news_ingestion.py`

- `workflow_records.json` 적재 시 SQLite의 `crawl_articles.filter_term`에는 workflow record의 `filter_term`만 저장하도록 변경했다.
- `search_term`은 뉴스 UI API 기준으로 더 이상 저장/노출하지 않는다.
- `source_site` 저장 정책을 보강했다.
  - 일반 크롤러: workflow 설정의 `config_name`을 저장한다.
  - Google API: API 결과의 `source` 값을 저장한다.
  - Naver API: `originallink`에서 원문 도메인을 추출해 저장한다.
  - Daum API: 보강 수집된 `source_name`이 있으면 해당 값을 저장하고, 없으면 기존 fallback을 사용한다.

### `crawler_app/daum_news_api.py`

- Daum 검색 API 결과만으로는 언론사 도메인/출처명이 부족한 경우가 있어, 결과 URL의 상세 페이지를 best-effort로 조회해 출처 정보를 보강한다.
- 보강 수집은 별도 공개 `requests.Session`을 사용하며 Kakao Authorization 헤더를 전송하지 않는다.
- 환경변수로 제어 가능하다.
  - `DAUM_NEWS_ENRICH_SOURCE=0`: Daum 출처 보강 비활성화
  - `DAUM_NEWS_ENRICH_TIMEOUT_SECONDS`: 상세 페이지 조회 timeout
- 추출 필드 예:
  - `source_name`
  - `source_cp_id`

## DB 변경사항

### `crawl_articles`

기존 뉴스 UI API의 `search_term` 컬럼을 `filter_term`으로 대체했다.

주요 컬럼 의미:

- `article_id`: 기사 고유 ID
- `source_site`: 화면에 표시할 출처명 또는 언론사/도메인
- `source_config_name`: 크롤러 설정명
- `canonical_url`: 기사 URL
- `title`: 제목
- `published_at`, `first_seen_at`, `last_seen_at`: 기사 시각
- `filter_term`: 해당 기사가 매칭된 필터어 목록 문자열

기존 DB에 `search_term`만 있으면 초기화 시 다음 성격의 마이그레이션이 실행된다.

```sql
ALTER TABLE crawl_articles ADD COLUMN filter_term TEXT;
UPDATE crawl_articles
SET filter_term = search_term
WHERE filter_term IS NULL OR filter_term = '';
```

SQLite는 컬럼 rename/drop이 환경별로 부담될 수 있으므로, 운영 호환성을 위해 기존 `search_term` 컬럼이 남아 있어도 API에서는 사용하지 않는다.

### `crawl_filter_options`

검색어 옵션 그룹은 `search_term` 대신 `filter_term`으로 생성된다.

```sql
INSERT OR REPLACE INTO crawl_filter_options(option_id, option_group, option_name, updated_at)
SELECT ..., 'filter_term', filter_term, ...
FROM crawl_articles
WHERE filter_term IS NOT NULL AND filter_term != '';
```

### `monitoring_category_keywords`

왼쪽 사이드바 카테고리별 키워드를 저장하는 신규 테이블이다.

```sql
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
```

인덱스:

```sql
CREATE INDEX IF NOT EXISTS idx_monitoring_category_keywords_group_category
ON monitoring_category_keywords(keyword_group, category_code, sort_order);
```

## API 사용 방법

### 카테고리 키워드 전체 조회

```http
GET /api/category-keywords
```

응답 예:

```json
{
  "items": [
    {
      "category_code": "SK",
      "keyword_group": "PR",
      "keywords": [
        {"keyword_id": "...", "keyword": "최태원", "sort_order": 0},
        {"keyword_id": "...", "keyword": "SK", "sort_order": 1}
      ]
    }
  ]
}
```

실행 쿼리 성격:

```sql
SELECT keyword_id, keyword_group, category_code, keyword, sort_order, created_at, updated_at
FROM monitoring_category_keywords
WHERE keyword_group = ?
ORDER BY category_code ASC, sort_order ASC, keyword ASC;
```

### 특정 카테고리 키워드 조회

```http
GET /api/category-keywords/SK
```

실행 쿼리 성격:

```sql
SELECT keyword_id, keyword_group, category_code, keyword, sort_order, created_at, updated_at
FROM monitoring_category_keywords
WHERE keyword_group = ? AND category_code = ?
ORDER BY sort_order ASC, keyword ASC;
```

### 특정 카테고리 키워드 전체 저장/교체

```http
PUT /api/category-keywords/SK
Content-Type: application/json

{
  "keywords": ["최태원", "Chey Tae-won", "Tony Chey", "SK", "대한상의"]
}
```

실행 쿼리 성격:

```sql
DELETE FROM monitoring_category_keywords
WHERE keyword_group = ? AND category_code = ?;

INSERT INTO monitoring_category_keywords
(keyword_id, keyword_group, category_code, keyword, sort_order, created_at, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?);
```

이 API는 화면에서 사용자가 SK 키워드 목록을 수정한 뒤 저장할 때 사용한다.

### 특정 카테고리에 키워드 추가

```http
POST /api/category-keywords/SK/keywords
Content-Type: application/json

{
  "keywords": ["상법", "대한상공회의소"]
}
```

실행 쿼리 성격:

```sql
SELECT COALESCE(MAX(sort_order), -1) AS max_order
FROM monitoring_category_keywords
WHERE keyword_group = ? AND category_code = ?;

INSERT OR IGNORE INTO monitoring_category_keywords
(keyword_id, keyword_group, category_code, keyword, sort_order, created_at, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?);
```

중복 키워드는 `UNIQUE(keyword_group, category_code, keyword)` 제약으로 무시된다.

### 키워드 1개 삭제

```http
DELETE /api/category-keywords/keywords/{keyword_id}
```

실행 쿼리 성격:

```sql
SELECT keyword_group, category_code
FROM monitoring_category_keywords
WHERE keyword_id = ?;

DELETE FROM monitoring_category_keywords
WHERE keyword_id = ?;

SELECT keyword_id
FROM monitoring_category_keywords
WHERE keyword_group = ? AND category_code = ?
ORDER BY sort_order ASC, keyword ASC;

UPDATE monitoring_category_keywords
SET sort_order = ?, updated_at = ?
WHERE keyword_id = ?;
```

삭제 후 남은 키워드의 `sort_order`를 다시 정렬한다.

### 카테고리 전체 삭제

```http
DELETE /api/category-keywords/SK
```

실행 쿼리 성격:

```sql
DELETE FROM monitoring_category_keywords
WHERE keyword_group = ? AND category_code = ?;
```

### 카테고리 기반 뉴스 조회

```http
GET /api/news?user_id=unknown&category_code=SK&page=1&page_size=20
```

서버 처리 흐름:

1. `monitoring_category_keywords`에서 `keyword_group='PR'`, `category_code='SK'` 키워드 목록을 조회한다.
2. 조회된 키워드를 `crawl_articles.filter_term`에 OR 조건으로 적용한다.
3. 조건에 맞는 기사 목록을 반환한다.

실행 쿼리 성격:

```sql
SELECT keyword
FROM monitoring_category_keywords
WHERE keyword_group = ? AND category_code = ?
ORDER BY sort_order ASC, keyword ASC;
```

키워드가 `["최태원", "SK"]`라면 기사 목록 WHERE에 다음 조건이 추가된다.

```sql
AND (
  LOWER(a.filter_term) LIKE LOWER('%최태원%')
  OR LOWER(a.filter_term) LIKE LOWER('%SK%')
)
```

그 뒤 기존 목록 조회 쿼리가 실행된다.

```sql
SELECT a.article_id, a.title, a.source_site AS source_name,
       a.filter_term, a.canonical_url AS url, ...
FROM crawl_articles a
LEFT JOIN user_article_state s ON ...
LEFT JOIN article_sentiment sen ON ...
WHERE a.title IS NOT NULL AND a.title != ''
  AND (...)
ORDER BY ...
LIMIT ? OFFSET ?;
```

### 카테고리 기반 유사 기사 조회

```http
GET /api/news/grouped?user_id=unknown&category_code=SK&page=1&page_size=20
```

실행 쿼리 성격:

- `/api/news`와 같은 category WHERE를 적용한다.
- `article_clusters`를 JOIN해 대표 기사만 반환한다.
- 유사 기사가 있는 cluster는 별도 배치 쿼리로 `similar_articles`를 채운다.

```sql
WITH filtered AS (... category filter ...),
representatives AS (
  SELECT * FROM filtered WHERE is_representative = 1
),
cluster_counts AS (
  SELECT cluster_id, COUNT(*) - 1 AS similar_count
  FROM filtered
  WHERE cluster_id IS NOT NULL
  GROUP BY cluster_id
)
SELECT ...
FROM representatives r
LEFT JOIN cluster_counts cc ON r.cluster_id = cc.cluster_id;
```

### 카테고리 기반 통계 조회

```http
GET /api/stats?user_id=unknown&category_code=SK
```

실행 쿼리 성격:

```sql
SELECT
  COUNT(*) AS total,
  SUM(CASE WHEN COALESCE(s.is_read, 0) = 0 THEN 1 ELSE 0 END) AS unread,
  SUM(CASE WHEN COALESCE(s.is_read, 0) = 1 THEN 1 ELSE 0 END) AS read,
  SUM(CASE WHEN COALESCE(s.is_favorite, 0) = 1 THEN 1 ELSE 0 END) AS favorite
FROM crawl_articles a
LEFT JOIN user_article_state s
  ON a.article_id = s.article_id AND s.user_id = ?
WHERE a.title IS NOT NULL AND a.title != ''
  AND (... category filter ...);
```

## 설계 판단

- 프론트가 `/api/news`에 키워드 배열을 직접 넘기는 방식은 채택하지 않았다.
  - URL 길이가 길어질 수 있다.
  - 카테고리별 키워드 정의가 프론트와 서버 사이에 중복된다.
  - UI 설정 화면에서 저장한 값과 목록 조회 시점의 값이 어긋날 수 있다.
- 대신 서버가 `category_code`를 받아 내부 DB에서 키워드를 조회한다.
  - UI는 `SK`, `SKI`, `SKE` 같은 코드만 관리하면 된다.
  - 키워드 변경은 별도 API로 저장되며 다음 조회부터 즉시 반영된다.
- 현재 필터 기준은 `title`이나 본문이 아니라 `filter_term`으로 고정했다.
  - 개발팀 요청에 따라 카테고리 검색은 수집/필터링 단계에서 매칭된 필터어 기준으로 판단한다.
  - 기사 본문 전체 검색은 이번 범위에서 제외했다.
- `keyword_group`은 기본값 `PR`로 유지했다.
  - 장래에 PR/CR/GR/CSR 같은 그룹이 UI에 열리면 같은 테이블을 확장해 사용할 수 있다.

## 검증

테스트 워크스페이스 `crawler-tran-flat-test`에서 아래 검증을 수행했다.

```powershell
.\.venv\Scripts\python.exe -m py_compile .\crawler_app\news_sqlite_store.py .\crawler_app\news_ui_api.py .\crawler_app\news_ingestion.py .\crawler_app\daum_news_api.py
.\.venv\Scripts\python.exe -m unittest tests.test_news_ui_api -v
.\.venv\Scripts\python.exe -m unittest tests.test_workflow -v
```

결과:

- `py_compile`: 통과
- `tests.test_news_ui_api`: 3개 테스트 통과
- `tests.test_workflow`: 83개 테스트 통과
- SQLite 초기화 시 `monitoring_category_keywords` 테이블 생성 확인
- 새 DB 기준 카테고리 키워드 초기 count가 0인 상태 확인

## 보안 및 비밀값 점검

- `.env`, 토큰, 쿠키, 비밀번호 파일은 포함하지 않았다.
- Daum 상세 페이지 보강 요청은 Kakao API 인증 헤더를 재사용하지 않는다.
- OpenAI, Kakao, Naver, Daum API key 값은 코드와 push-history에 포함하지 않았다.

## 남은 리스크 및 운영 메모

- 이미 떠 있는 `uvicorn` 서버는 코드를 자동 반영하지 않는다. 배포 후 서버 재시작이 필요하다.
- Daum 출처 보강은 결과 1건당 상세 페이지 요청을 추가할 수 있으므로, 운영 중 지연이 크면 `DAUM_NEWS_ENRICH_SOURCE=0`으로 비활성화할 수 있다.
- 카테고리 필터는 `filter_term` 기준이다. 사용자가 기대하는 “본문에 SK가 포함된 기사” 검색과는 의미가 다르다.
- `keyword_group`은 현재 PR 기본값만 실사용한다. 그룹 UI가 생기면 API 파라미터와 화면 정책을 추가로 합의해야 한다.
- `tests/` 폴더는 사용자 요청에 따라 push 대상에서 제외했다. 로컬 검증은 테스트 워크스페이스에서 수행했으며, 이 저장소에는 운영 소스 중심으로 반영한다.
