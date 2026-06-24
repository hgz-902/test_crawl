# SQLite 뉴스 API와 Parquet 전환 UI 통합

- Created at: 2026-06-24 14:10:42
- Branch: dev/API+Tran
- Base branch: origin/dev/crawler-tran

## Purpose

`dev/crawler-tran`에 이미 반영된 flat Parquet 변환/전환 UI 흐름 위에, 개발팀이 공유한 Databricks 기반 뉴스 검토 API를 로컬 Windows 크롤링 서버에서 사용할 수 있는 SQLite 기반 API로 이관한다.

## Why This Change Was Needed

- 개발팀 공유 API는 Databricks SQL, Delta table, Vector Search를 전제로 했기 때문에 로컬 크롤링 서버에 그대로 붙일 수 없었다.
- UI는 `/api/news`, `/api/news/grouped`, `/api/stats`, `/api/filter-options`, read/favorite 상태 변경 API를 호출하므로 크롤링 서버에도 동일 shape의 API가 필요했다.
- 유사 기사 그룹핑은 API 호출 시 실시간 계산하면 느려지므로, 크롤링 결과 저장/동기화 시점에 미리 계산해 `article_clusters`에 저장해야 했다.
- Parquet 전환 기능은 `outputs/*/tran/*.parquet`를 UI에서 원본 파일로 복원 다운로드해야 하므로, 기존 `dev/crawler-tran`의 flat parquet 구조와 함께 유지되어야 했다.

## What Changed

### SQLite 뉴스 API 계층

- `crawler_app/news_sqlite_store.py`
  - Databricks의 `crawl_articles`, `article_clusters`, `article_sentiment`, `user_article_state`, `article_action_log`, `crawl_filter_options` 구조를 SQLite schema로 이식했다.
  - `/api/news`, `/api/news/grouped`, `/api/stats`, `/api/filter-options`가 사용할 query와 read/favorite upsert 함수를 제공한다.
  - `article_title_embeddings` 캐시 테이블을 추가해 향후 캐시형 그룹핑 운영이 가능하게 했다.

- `crawler_app/news_ui_api.py`
  - FastAPI router로 뉴스 검토 UI API를 제공한다.
  - 구현 API:
    - `GET /api/filter-options`
    - `GET /api/news`
    - `GET /api/news/grouped`
    - `GET /api/stats`
    - `PATCH /api/news/{article_id}/read`
    - `PATCH /api/news/{article_id}/favorite`
    - `POST /api/news/{article_id}/analysis/save`
    - `GET /api/news/{article_id}/analysis`
  - 직접 LLM 호출 API인 `POST /api/news/{article_id}/analyze`는 사내 모델 사용 예정이라 포함하지 않았다.

- `crawler_app/news_ingestion.py`
  - `outputs/**/filter/workflow_records*.json`에서 기사 레코드를 읽어 SQLite `crawl_articles`에 upsert한다.
  - source/search term 필터 옵션을 재구성한다.
  - 제목 기반 감성 분석과 같은 날짜 기준 유사 기사 그룹핑을 사전 계산한다.
  - 기본 grouping scope는 `touched_dates`로, 새로 영향받은 날짜만 재그룹핑한다.

- `crawler_app/news_grouping.py`
  - Databricks Vector Search 대신 로컬 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` 또는 lexical fallback으로 제목 유사도를 계산한다.
  - 운영 기본값은 검증 후보 C05에 해당하는 설정으로 둔다.
    - `NEWS_GROUPING_THRESHOLD` 기본값: `0.86`
    - 후보 필터 기본값: `strict`
    - `min_shared_tokens=3`, `lexical_guard=0.50`, `min_token_jaccard=0.25`, `sequence_guard=0.82`
  - 같은 날짜 기사끼리만 그룹핑하며 날짜 교차 묶음을 방지한다.

- `crawler_app/news_sentiment.py`
  - 개발팀의 KNU 계열 제목 키워드 기반 긍정/부정 사전 분석을 로컬 함수로 분리했다.
  - 미분석 기사 제목에 대해 `positive`, `neutral`, `negative`와 confidence를 저장할 수 있게 했다.

### 크롤링 서버 연결

- `crawler_app/web.py`
  - `news_ui_api` router를 FastAPI 앱에 include한다.
  - 서버 startup 시 SQLite schema를 준비한다.
  - 수동 크롤링 완료 후 해당 output_dir을 뉴스 UI DB에 동기화하고 결과 metadata에 `news_ui_sync`를 남긴다.

- `crawler_app/orchestration.py`
  - 오케스트레이션/스케줄러 실행 완료 후 output_dir을 SQLite 뉴스 UI DB에 동기화한다.
  - 동기화 실패가 크롤링 성공/실패 판정을 뒤집지 않도록 `news_ui_sync_error`에 기록한다.
  - 로컬 공통 `.env` 경로는 `CRAWLER_SHARED_ENV_FILE`로 override 가능하게 했다.

- `crawler_app/workflow.py`
  - parser형 수집에서 검색어 1개 실패가 전체 job을 중단하지 않도록 실패한 검색어를 diagnostics에 기록하고 다음 검색어를 계속 처리한다.
  - filter output to tran parquet 흐름은 `dev/crawler-tran`의 flat 구조를 유지한다.

- `crawler_app/google_news_rss.py`
  - Google RSS 요청에 retry/backoff를 추가해 일시적 SSL/네트워크 실패가 전체 수집 실패로 번지는 가능성을 줄였다.
  - `GOOGLE_NEWS_RSS_RETRIES`, `GOOGLE_NEWS_RSS_BACKOFF_SECONDS`로 조정 가능하다.

### 설정 파일

- `configs/*.json`
  - 이전 설정 목록에서 사라졌던 검색어/필터 목록을 현재 워크스페이스 기준으로 복구했다.
  - 마켓인사이트/인베스트조선처럼 페이지 번호를 `search_terms`로 쓰는 설정은 `1`, `2`, `3`을 넣었다.
  - 네이버/다음/구글 등 API형 설정은 확장된 SK 계열사/사업 키워드를 유지한다.

### 의존성

- `requirements.txt`
  - `sentence-transformers>=3.0.0,<4` 추가.
  - 직접 OpenAI 호출 API는 포함하지 않으므로 `openai` 의존성은 추가하지 않았다.

### 문서

- `docs/news-ui-api-change-rationale.md`
  - Databricks API를 SQLite 로컬 API로 이관한 이유, 구조, tradeoff, 남은 리스크를 기록했다.

- `docs/news-ui-api-validation-evidence.md`
  - compile/test 검증 결과와 보안/외부 호출 판단을 기록했다.

- `docs/parquet-converter-menu-change-rationale.md`
  - Parquet 전환 메뉴의 목적과 path guard, 단일/ZIP 다운로드 흐름을 기록한다.

- `docs/tran-flat-parquet-change-rationale.md`
  - flat tran parquet 구조, metadata manifest, 원본 파일 매칭 설계를 기록한다.

### 테스트

- `tests/test_news_ui_api.py`
  - SQLite ingest, grouped API, read/favorite 상태 변경, analysis save/get, 그룹핑 guard를 검증한다.

- `tests/test_tran_parquet_export.py`
  - flat parquet 파일명, metadata manifest, rollup/latest 제외, 원본 매칭 정보를 검증한다.

- `tests/test_web.py`
  - Parquet converter 목록/단일 다운로드/ZIP 다운로드/path traversal 차단을 검증한다.

## Design Judgment

- SQLite를 v1 저장소로 선택했다. 로컬 Windows 크롤링 서버에서 바로 실행 가능하고, 개발팀이 요구한 API shape 검증에 충분하다.
- API 호출 시 그룹핑 계산을 하지 않고, 수집 결과 DB 동기화 시점에 `article_clusters`를 미리 만든다.
- 제목 기준 유사도만 사용한다. 개발팀 요청에 맞춰 본문은 그룹핑 입력에서 제외했다.
- 운영 기본 grouping은 C05 실험 결과를 반영해 `threshold=0.86`, `strict blocking`, `model embedding`, `touched_dates`로 둔다.
- 직접 LLM 호출 API는 사내 모델 예정이라는 개발팀 방향에 따라 제외하고, 분석 결과 저장/조회 API만 유지한다.

## Alternatives Considered Or Deferred

- Databricks SQL/Vector Search 직접 유지: 로컬 서버 성능 및 의존성 문제로 제외.
- API 요청 시 실시간 그룹핑: UI 응답 시간이 길어져 제외.
- lexical-only 그룹핑: 매우 빠르지만 유사 기사 recall이 낮아 기본값에서 제외.
- cached embedding 기본값: DB를 장기 누적 운영할 때 유리하지만, 현재 기본 운영 검증은 cold 기준 C05가 더 안정적이라 기본값에서는 제외. 환경변수로 전환 가능하다.
- PostgreSQL: SQLite로 기능/shape 검증 후 동시성·성능 문제가 확인될 때 검토한다.

## Validation

```powershell
C:\AI_JOB\firstproject\crawler_project\crawler-tran-flat-test\.venv\Scripts\python.exe -m compileall crawler_app
C:\AI_JOB\firstproject\crawler_project\crawler-tran-flat-test\.venv\Scripts\python.exe -m unittest tests.test_news_ui_api -v
C:\AI_JOB\firstproject\crawler_project\crawler-tran-flat-test\.venv\Scripts\python.exe -m unittest tests.test_web.ParquetConverterRouteTests -v
C:\AI_JOB\firstproject\crawler_project\crawler-tran-flat-test\.venv\Scripts\python.exe -m unittest tests.test_tran_parquet_export -v
```

Result:

- PASS: `compileall crawler_app`
- PASS: `tests.test_news_ui_api` 2 tests
- PASS: `tests.test_web.ParquetConverterRouteTests` 4 tests
- PASS: `tests.test_tran_parquet_export` 1 test

Secret scan:

- 실제 credential 값은 발견되지 않았다.
- 발견 항목은 `.env.example` placeholder, 환경변수 이름, 테스트용 dummy secret 문자열, 기존 push-history 보안 설명 문구다.

## Remaining Risks

- 실제 프론트엔드가 공유받은 코드와 다른 필드를 추가로 요구할 수 있다.
- SQLite는 v1 로컬 검증용이다. 장기 동시 운영에서 lock/성능 문제가 나오면 PostgreSQL 또는 별도 batch worker로 분리해야 한다.
- `sentence-transformers` 모델은 최초 실행 시 다운로드 시간이 발생할 수 있다.
- `source_site`의 언론사명 추출은 URL/domain/source_name 기반 best-effort라 일부 Google News redirect는 추가 개선 여지가 있다.

## Cumulative Prompt / Request Flow

1. 개발팀 공유 Databricks API 4종과 보조 함수/schema를 분석했다.
2. 로컬/Windows 크롤링 서버에서는 Databricks가 느리므로 SQLite 기반 API로 이관하는 방향을 정했다.
3. 유사 기사 그룹핑은 같은 날짜 제목 기준으로 미리 계산하는 구조로 확정했다.
4. 24개 그룹핑 케이스를 실험했고, 운영 기본값은 C05 설정으로 결정했다.
5. 기존 Parquet flat 변환 및 Parquet 전환 UI가 들어간 `dev/crawler-tran` 기반으로 새 `dev/API+Tran` 브랜치를 만들었다.
6. `crawler-tran-flat-test`의 구현 결과를 push 전용 클론에 선별 반영하고, 실험 산출물/runner/qa-artifacts는 제외했다.

## Repo State Snapshot

### git status --short before staging

```text
 M configs/*.json
 M crawler_app/google_news_rss.py
 M crawler_app/orchestration.py
 M crawler_app/web.py
 M crawler_app/workflow.py
 M requirements.txt
?? crawler_app/news_grouping.py
?? crawler_app/news_ingestion.py
?? crawler_app/news_sentiment.py
?? crawler_app/news_sqlite_store.py
?? crawler_app/news_ui_api.py
?? docs/news-ui-api-change-rationale.md
?? docs/news-ui-api-validation-evidence.md
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
- [x] No unrelated dirty files were staged.
- [x] No `.env`, API key, token, password, app password, cookie, or sensitive log is staged.
- [x] Push record is included in the same commit.
- [x] Validation results are recorded honestly.
- [x] Remaining risks are recorded honestly.

