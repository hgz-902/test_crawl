# 뉴스 API category_code 응답과 뉴스 리뷰 UI 프로토타입 추가

- Created at: 2026-07-01 10:59:00
- Branch: dev/API+Tran

## Purpose

개발팀 UI 연동 요청에 맞춰 뉴스 목록 API 응답 item마다 기사별 `category_code`를 내려주고, 동일한 API를 바로 확인할 수 있는 독립 뉴스 리뷰 UI 프로토타입을 정적 파일로 포함한다.

## Why This Change Was Needed

기존 `/api/news?category_code=SKO` 같은 요청은 카테고리 필터로는 동작했지만, 전체 조회나 grouped 조회의 각 기사 item에는 실제 분류값이 없었다. 프론트엔드가 선택 카테고리를 그대로 표시하거나 임시 문자열 추론을 하면 전체 조회에서 모두 `SK`처럼 보이거나, `SK`와 `E&S`가 같이 적용되는 기사에서 의도와 다른 분류가 표시될 수 있었다.

## What Changed

- `crawler_app/news_sqlite_store.py`
  - `/api/news` 응답 item에 `category_code`를 추가했다.
  - `/api/news/grouped` 대표 기사 item과 `similar_articles` item에 `category_code`를 추가했다.
  - `monitoring_category_keywords`를 요청당 1회 조회해 keyword index를 만들고, 각 기사 `filter_term`과 정확 토큰 매칭으로 대표 카테고리를 계산한다.
  - 복수 카테고리 매칭 시 매칭 키워드 수, 구체 카테고리 우선순위, 문자열 정렬 순으로 대표값을 결정한다.
  - 기존 `category_code` query parameter 필터 동작은 유지했다.
- `static/news_review_ui/index.html`
  - 독립 뉴스 리뷰 UI 프로토타입 페이지를 추가했다.
- `static/news_review_ui/app.js`
  - `/api/news`, `/api/news/grouped`, `/api/stats`, `/api/filter-options`, `/api/category-keywords...`를 호출해 화면을 구성한다.
  - 사이드바 특정 카테고리를 선택한 상태에서는 화면 분류 표시에서 선택 카테고리를 우선한다.
  - 전체 조회에서는 API 응답의 item별 `category_code`를 우선 사용한다.
- `static/news_review_ui/styles.css`
  - 독립 뉴스 리뷰 화면 스타일을 추가했다.
- `news-ui-api-interface-definition.md`
  - `category_code` 응답 필드, grouped similar item 적용 범위, 계산 규칙, UI 프로토타입 경로와 사용 API를 보완했다.

## Design Judgment

프론트엔드가 긴 키워드 목록을 직접 넘기거나 자체 추론으로 분류를 결정하는 방식은 URL 길이, 동기화, 표시 일관성 문제가 있다. 따라서 카테고리 기준표는 SQLite의 `monitoring_category_keywords`에 두고, 서버가 `filter_term` 기준으로 기사별 대표 `category_code`를 계산하도록 했다.

필터링은 기존 호환을 위해 `LIKE` 조건을 유지했다. 반면 응답용 `category_code` 계산은 `SK`가 `SK온`, `SK하이닉스`를 과도하게 잡지 않도록 쉼표 분리 토큰의 정확 일치만 사용한다.

## Alternatives Considered Or Deferred

- `category_codes: []`처럼 복수 카테고리 배열을 응답하는 방식은 이번 요청 범위를 넘어 보류했다.
- 제목/본문 기반 분류는 오탐과 비용이 커서 제외했다. 현재 기준은 `filter_term`이다.
- 카테고리 키워드 seed 데이터를 코드에 하드코딩하는 방식은 운영 UI/API에서 관리해야 할 데이터라서 제외했다.
- UI 프로토타입은 기존 크롤러/오케스트레이션 화면에 통합하지 않고 `/static/news_review_ui/index.html` 독립 페이지로 제공했다.

## API Interface Notes

### GET /api/news

기존 응답 item에 아래 필드가 추가된다.

```json
{
  "filter_term": "SK온, 배터리",
  "category_code": "SKO"
}
```

### GET /api/news/grouped

대표 기사 item과 `similar_articles`의 각 item에 동일하게 `category_code`가 포함된다.

### GET /api/news?category_code=SKO

기존처럼 `monitoring_category_keywords`에서 `SKO` 키워드를 조회해 `crawl_articles.filter_term`에 필터를 적용한다. 응답의 `category_code`는 요청값 echo가 아니라 기사별 계산값이다.

### 정적 UI

```http
GET /static/news_review_ui/index.html
```

## Data And Operation Notes

- `monitoring_category_keywords`가 비어 있으면 `/api/news` 응답의 `category_code`는 `null`이 될 수 있다.
- 카테고리 키워드가 비어 있는 카테고리를 클릭하면 해당 `category_code` 필터 결과는 0건이 될 수 있다.
- 운영 전 `GET/PUT /api/category-keywords/{category_code}`로 `SK`, `SKO`, `E&S` 등 필요한 키워드 seed를 저장해야 한다.

## Validation

- `python -m compileall crawler_app`: 통과
- `C:\AI_JOB\firstproject\crawler_project\crawler-tran-flat-test\.venv\Scripts\python.exe -m unittest tests.test_news_ui_api -v`: 통과
- `node --check static\news_review_ui\app.js`: 통과
- `git diff --check`: 공백 오류 없음. LF/CRLF 경고만 확인됨.

## Remaining Risks

- 카테고리 seed 데이터는 코드에 포함하지 않았다. 새 환경에서 DB만 생성된 상태라면 category keyword가 비어 있어 `category_code`가 `null`로 내려올 수 있다.
- UI 프로토타입은 독립 정적 페이지이며, 최종 개발팀 UI와 동일한 화면 구조를 보장하지 않는다.
- 응답용 대표 카테고리는 단일값이다. 여러 카테고리를 동시에 보여야 하는 요구가 생기면 별도 응답 필드가 필요하다.

## Cumulative Prompt / Request Flow

개발팀은 전체 조회에서도 기사별 `category_code`를 받을 수 있는지 문의했다. 초기에는 선택 카테고리를 그대로 표시하는 해석도 검토했지만, 전체 조회에서 기사별 분류가 필요하다는 요구로 정리했다. 이에 따라 서버가 `filter_term`과 카테고리 키워드 기준표를 이용해 item별 대표 `category_code`를 계산하도록 구현했다. 이후 API 코드가 있는 워크스페이스에 독립 뉴스 리뷰 UI 정적 파일을 배합하고, 인터페이스 정의서와 push-history에 API/DB/UI 사용 방식을 보강했다.

## Repo State Snapshot

### git status --short

```text
 M crawler_app/news_sqlite_store.py
 M news-ui-api-interface-definition.md
?? static/news_review_ui/
```

### git branch --show-current

```text
dev/API+Tran
```

### git remote -v

```text
origin  https://github.com/K-Ternag/crawlService.git (fetch)
origin  https://github.com/K-Ternag/crawlService.git (push)
```

## Pre-Commit Checklist

- [x] Only task-related files are staged.
- [x] No unrelated dirty files are staged.
- [x] No `.env`, API key, token, password, cookie, or sensitive log is included.
- [x] Push record is included in the same commit.
- [x] Validation results are recorded.
- [x] Remaining risks are recorded.
