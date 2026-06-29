# 카테고리 키워드 관리 및 뉴스 조회 확장 API 정의서

작성일: 2026-06-29  
대상 브랜치: `dev/API+Tran`

## 1. 작성 범위

본 문서는 가장 최근 개발 요청으로 추가/변경된 API만 정리한다.

범위는 다음 2가지다.

1. 사이드바 카테고리별 키워드 관리 API
2. 기존 뉴스 조회 API의 `category_code` 기반 필터 확장

기존에 이미 있던 읽음/즐겨찾기/분석 저장/필터 옵션 API는 본 문서의 상세 정의 대상이 아니다.

## 2. 관련 파일

| 구분 | 파일 | 역할 |
|---|---|---|
| API 라우터 | `crawler_app/news_ui_api.py` | FastAPI endpoint 정의 |
| SQLite 저장/조회 로직 | `crawler_app/news_sqlite_store.py` | 카테고리 키워드 CRUD 및 뉴스 조회 조건 처리 |
| API 라우터 연결 | `crawler_app/web.py` | `news_ui_router`를 FastAPI 앱에 include |

## 3. DB 변경 사항

### 신규 테이블: `monitoring_category_keywords`

카테고리별 검색 키워드를 저장한다.

주요 컬럼:

| 컬럼 | 설명 |
|---|---|
| `keyword_id` | 키워드 고유 ID |
| `keyword_group` | 키워드 그룹. 현재 기본값은 `PR` |
| `category_code` | 사이드바 카테고리 코드. 예: `SK`, `SKI`, `SKE` |
| `keyword` | 실제 검색 키워드 |
| `sort_order` | 표시 순서 |
| `created_at` | 생성 시각 |
| `updated_at` | 수정 시각 |

중복 방지 기준:

```text
keyword_group + category_code + keyword
```

## 4. 신규 API: 카테고리 키워드 관리

### 4.1 전체 카테고리 키워드 조회

```http
GET /api/category-keywords?keyword_group=PR
```

기능:

- 저장된 전체 카테고리 키워드 목록을 조회한다.
- `keyword_group`은 생략 가능하며 기본값은 `PR`이다.

응답 예시:

```json
[
  {
    "keyword_group": "PR",
    "category_code": "SK",
    "keywords": [
      {
        "keyword_id": "abc123",
        "keyword": "최태원",
        "sort_order": 1,
        "created_at": "2026-06-29 10:00:00",
        "updated_at": "2026-06-29 10:00:00"
      }
    ]
  }
]
```

UI 적용:

- 관리자/설정 화면에서 전체 카테고리 목록을 한 번에 불러올 때 사용한다.

### 4.2 단일 카테고리 키워드 조회

```http
GET /api/category-keywords/{category_code}?keyword_group=PR
```

예:

```http
GET /api/category-keywords/SK?keyword_group=PR
```

기능:

- 특정 카테고리에 저장된 키워드만 조회한다.

응답 예시:

```json
{
  "keyword_group": "PR",
  "category_code": "SK",
  "keywords": [
    {
      "keyword_id": "abc123",
      "keyword": "최태원",
      "sort_order": 1,
      "created_at": "2026-06-29 10:00:00",
      "updated_at": "2026-06-29 10:00:00"
    },
    {
      "keyword_id": "def456",
      "keyword": "Chey Tae-won",
      "sort_order": 2,
      "created_at": "2026-06-29 10:00:00",
      "updated_at": "2026-06-29 10:00:00"
    }
  ]
}
```

UI 적용:

- 관리자 화면에서 `SK`를 선택했을 때 기존 저장값을 표시한다.

### 4.3 단일 카테고리 키워드 전체 저장/교체

```http
PUT /api/category-keywords/{category_code}?keyword_group=PR
Content-Type: application/json
```

예:

```http
PUT /api/category-keywords/SK?keyword_group=PR
```

요청 body:

```json
{
  "keywords": ["최태원", "Chey Tae-won", "Tony Chey", "SK", "대한상의"]
}
```

기능:

- 해당 카테고리의 기존 키워드를 모두 삭제한다.
- 요청 body의 `keywords` 배열로 다시 저장한다.
- 운영 UI의 “저장” 버튼에는 이 API를 쓰는 것을 권장한다.

DB 처리:

1. `monitoring_category_keywords`에서 해당 `keyword_group`, `category_code` 데이터 삭제
2. 요청받은 키워드 배열을 순서대로 insert

응답:

- 저장 후 해당 카테고리의 최신 키워드 목록을 반환한다.

### 4.4 단일 카테고리 키워드 추가

```http
POST /api/category-keywords/{category_code}/keywords?keyword_group=PR
Content-Type: application/json
```

예:

```http
POST /api/category-keywords/SK/keywords?keyword_group=PR
```

요청 body:

```json
{
  "keywords": ["SK그룹", "대한상의"]
}
```

기능:

- 기존 목록은 유지하고 새 키워드만 추가한다.
- 이미 존재하는 키워드는 중복 저장하지 않는다.

DB 처리:

- `INSERT OR IGNORE`로 키워드 추가

응답:

- 추가 후 해당 카테고리의 최신 키워드 목록을 반환한다.

UI 적용:

- 태그 입력형 UI에서 “추가” 버튼을 둘 경우 사용한다.
- 전체 저장 방식만 쓸 경우 이 API는 선택 사항이다.

### 4.5 키워드 1건 삭제

```http
DELETE /api/category-keywords/keywords/{keyword_id}
```

기능:

- `keyword_id` 기준으로 키워드 1건을 삭제한다.
- 삭제 후 같은 카테고리의 정렬 순서를 다시 정리한다.

응답:

- 삭제 후 해당 카테고리의 최신 키워드 목록을 반환한다.

UI 적용:

- 키워드 태그 옆 `x` 버튼에 연결한다.

### 4.6 단일 카테고리 키워드 전체 삭제

```http
DELETE /api/category-keywords/{category_code}?keyword_group=PR
```

예:

```http
DELETE /api/category-keywords/SK?keyword_group=PR
```

기능:

- 해당 카테고리의 키워드를 모두 삭제한다.

응답 예시:

```json
{
  "keyword_group": "PR",
  "category_code": "SK",
  "keywords": []
}
```

UI 적용:

- 관리자 화면의 “전체 삭제” 버튼에 연결한다.

## 5. 기존 API 변경: 뉴스 조회 카테고리 필터 확장

### 5.1 변경 대상 API

```http
GET /api/news
GET /api/news/grouped
GET /api/stats
```

위 API들은 기존 API이며, 신규 API가 아니라 파라미터가 확장되었다.

### 5.2 추가 파라미터

| 파라미터 | 기본값 | 설명 |
|---|---|---|
| `category_code` | 없음 | 사이드바 카테고리 코드. 예: `SK` |
| `keyword_group` | `PR` | 카테고리 키워드 그룹 |

### 5.3 동작 방식

프론트엔드는 키워드 배열을 직접 넘기지 않는다.

예를 들어 사이드바에서 `SK`를 클릭하면 다음처럼 호출한다.

```http
GET /api/news?user_id=unknown&category_code=SK&keyword_group=PR&page=1&page_size=20
```

서버 내부 처리:

1. `monitoring_category_keywords`에서 `keyword_group='PR'`, `category_code='SK'` 키워드 조회
2. 조회된 키워드를 `crawl_articles.filter_term`에 OR 조건으로 적용
3. 조건에 맞는 기사 목록 반환

예를 들어 `SK`에 아래 키워드가 저장되어 있다면:

```json
["최태원", "Chey Tae-won", "Tony Chey", "SK", "대한상의"]
```

내부적으로 다음 조건과 유사하게 동작한다.

```sql
LOWER(a.filter_term) LIKE LOWER('%최태원%')
OR LOWER(a.filter_term) LIKE LOWER('%Chey Tae-won%')
OR LOWER(a.filter_term) LIKE LOWER('%Tony Chey%')
OR LOWER(a.filter_term) LIKE LOWER('%SK%')
OR LOWER(a.filter_term) LIKE LOWER('%대한상의%')
```

### 5.4 `/api/news` 사용 예시

```http
GET /api/news?user_id=unknown&category_code=SK&keyword_group=PR&page=1&page_size=20
```

응답은 기존 `/api/news`와 동일한 형태다.

```json
{
  "totalCount": 10,
  "page": 1,
  "pageSize": 20,
  "items": [
    {
      "article_id": "article-id",
      "title": "기사 제목",
      "source_name": "연합뉴스",
      "filter_term": "SK",
      "published_at": "2026-06-29 10:30:00",
      "url": "https://example.com/news/1",
      "is_major": true,
      "is_read": false,
      "read_at": null,
      "is_favorite": false,
      "favorite_at": null,
      "sentiment": "neutral",
      "sentiment_confidence": 0.5
    }
  ]
}
```

### 5.5 `/api/news/grouped` 사용 예시

```http
GET /api/news/grouped?user_id=unknown&category_code=SK&keyword_group=PR&page=1&page_size=20
```

기능:

- 카테고리 조건으로 필터링한 뒤 유사 기사 그룹 대표 목록을 반환한다.
- 기존 grouped API 응답 구조는 유지한다.

### 5.6 `/api/stats` 사용 예시

```http
GET /api/stats?user_id=unknown&category_code=SK&keyword_group=PR
```

기능:

- 카테고리 조건이 적용된 상태에서 전체/미확인/확인/즐겨찾기 수를 반환한다.

## 6. UI 적용 방식

### 6.1 관리자 설정 화면

1. 사용자가 카테고리 `SK` 선택
2. `GET /api/category-keywords/SK?keyword_group=PR` 호출
3. 기존 키워드를 UI에 표시
4. 사용자가 키워드 목록 수정
5. 저장 시 `PUT /api/category-keywords/SK?keyword_group=PR` 호출

### 6.2 사이드바 카테고리 클릭

1. 사용자가 왼쪽 사이드바에서 `SK` 클릭
2. 프론트엔드는 `/api/news`에 `category_code=SK`만 전달
3. 서버가 SK에 저장된 키워드 목록을 조회
4. 서버가 `filter_term` 기준으로 해당 키워드들을 OR 검색
5. 결과 기사를 테이블에 표시

### 6.3 유사 기사 토글이 켜져 있을 때

1. 사용자가 `SK` 클릭
2. 유사 기사 토글 ON이면 `/api/news/grouped?category_code=SK` 호출
3. 서버가 동일한 카테고리 필터를 적용한 뒤 대표 기사와 유사 기사 목록 반환

## 7. 주의 사항

1. 이번 신규 API의 핵심은 카테고리별 키워드 관리다.
2. `/api/news`, `/api/news/grouped`, `/api/stats`는 신규 API가 아니라 기존 API의 파라미터 확장이다.
3. `search_term`은 더 이상 사용하지 않고 `filter_term`을 기준으로 조회한다.
4. `category_code` 검색은 제목/본문 검색이 아니라 `crawl_articles.filter_term` 검색이다.
5. 카테고리에 키워드가 저장되어 있지 않으면 `category_code` 조회 결과는 0건이다.
6. 프론트엔드에서 키워드 배열을 직접 `/api/news`에 넘기지 않는다. 키워드 배열은 서버 DB에 저장하고, 조회 시 `category_code`만 넘긴다.

