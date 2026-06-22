# 코드 요약 주석 및 API recent URL pub_date 보존 정책

- 일시: 2026-06-01 14:45:16 KST
- repository: `C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp`
- local branch: `codex/advancement-latest-dedupe-20260528`
- remote target: `origin/codex/advancement-latest-dedupe-20260528`
- commit message: `코드 요약 주석과 API recent URL 보존 정책 정리`

## 요청 / 작업 단위

- 운영 코드 전체의 `class`, `def`, `async def`, JavaScript `function` 정의 위에 사용자가 바로 이해할 수 있는 짧은 한국어 요약 주석을 추가한다.
- 주석은 docstring이 아니라 일반 주석으로만 작성하여 런타임 동작과 introspection 결과를 바꾸지 않는다.
- API형 크롤러의 `api_recent_records`는 `seen_at` 추가를 보류하고, 기사 `pub_date` 기준 최근 1시간 내 URL만 유지한다.
- push 전 `naver_news_문제_18시26분_...` 형태의 문제 재현 폴더가 git에 포함되지 않게 확인한다.

## 변경 파일

### 코드 요약 주석 추가

- `main.py`
- `crawler_app/base.py`
- `crawler_app/config_store.py`
- `crawler_app/configurable.py`
- `crawler_app/daum_news_api.py`
- `crawler_app/discovery.py`
- `crawler_app/document_extractors.py`
- `crawler_app/duplicate_keys.py`
- `crawler_app/file_lock.py`
- `crawler_app/google_news_rss.py`
- `crawler_app/logging_utils.py`
- `crawler_app/naver_news_api.py`
- `crawler_app/orchestration.py`
- `crawler_app/orchestrator.py`
- `crawler_app/runtime_maintenance.py`
- `crawler_app/scheduled_runner.py`
- `crawler_app/web.py`
- `crawler_app/windows_scheduler.py`
- `crawler_app/workflow.py`
- `crawler_app/workflow_records_api.py`
- `crawler_app/workflow_records_rollup.py`
- `crawler_app/workflow_records_rollup_scheduler.py`
- `crawlers/configurable_crawler.py`
- `static/app.js`

### API recent URL 보존 정책

- `crawler_app/workflow.py`
  - `API_RECENT_PUB_DATE_RETENTION = timedelta(hours=1)` 추가
  - `_merge_api_recent_records()`가 `pub_date` 기준 최근 1시간 이내 record만 `api_recent_records`에 유지하도록 변경
  - URL dedupe와 최대 2000개 보조 상한은 유지
  - `seen_at` 필드는 이번 변경에서 추가하지 않음

### Push history

- `docs/push-history/20260601_144516_codex-advancement-latest-dedupe-20260528_code-comments-api-recent-pubdate-retention.md`

## 변경 이유

### 코드 요약 주석

현재 크롤러는 config 실행, orchestration, scheduler, rollup, workflow records API가 서로 연결되어 있어 처음 코드를 보는 사람이 함수 역할을 따라가기 어렵다. 기존 함수명만으로는 `workflow.py`와 scheduler/orchestration 계층의 책임 경계가 한눈에 드러나지 않으므로, 정의 바로 위에 짧은 설명을 달아 코드 탐색 비용을 낮춘다.

주석 방식은 docstring 대신 일반 주석을 선택했다. 이렇게 하면 Python `__doc__` 값이나 런타임 동작을 바꾸지 않고 읽기성만 개선할 수 있다.

### API recent URL 보존 정책

API형 크롤러는 네이버/다음/구글처럼 검색 API나 RSS가 같은 URL을 반복적으로 반환할 수 있다. 기존 `latest.json`의 그룹별 최신 경계만으로는 검색어/필터 조합이 달라진 URL 반복을 충분히 막기 어려워 `api_recent_records`를 보조 URL index로 사용한다.

다만 이 index가 계속 커질 수 있으므로, 이번 변경에서는 사용자가 보류한 `seen_at` 구조 변경 없이 기존 `pub_date`만 활용해 최근 1시간 기사 URL만 유지한다. 이 방식은 저장 구조 변경이 작고, 현재 latest snapshot의 필드 구조와 호환된다.

## 설계 판단 / tradeoff

- 장점:
  - 모든 운영 코드의 함수/클래스 역할을 빠르게 파악할 수 있다.
  - docstring이 아니므로 런타임 동작을 바꾸지 않는다.
  - `api_recent_records`는 최근 1시간 기사 URL만 유지되어 불필요한 오래된 URL 보존을 줄인다.
  - `seen_at` 필드 추가 없이 기존 구조와 호환된다.

- 단점:
  - 주석 diff가 크다.
  - `pub_date` 기준 1시간 제한은 기사 발행 시간이 오래된 API 결과를 recent index에 오래 보존하지 않는다.
  - `pub_date`가 없거나 파싱 불가능한 API record는 recent URL index에 들어가지 않는다.

- 보류한 대안:
  - `seen_at` 필드 추가: 수집 시각 기준으로 더 정확하지만, 저장 형식 변경이 커서 이번에는 보류했다.
  - 별도 recent URL cache 파일 생성: 파일이 늘어나고 latest.json과의 책임이 갈라져 이번에는 채택하지 않았다.
  - 단순 2000개 제한 유지: 파일 크기 완화에는 도움이 되지만 시간 기준 정리 요구를 만족하지 못한다.

## 검증 결과

- `python -m compileall main.py crawler_app crawlers`
  - 통과
- `.venv\Scripts\python.exe -m compileall main.py crawler_app crawlers`
  - 통과
- `node --check static/app.js`
  - 통과
- `.venv\Scripts\python.exe -m unittest tests.test_workflow.WorkflowDownloadTests.test_api_recent_records_keep_only_one_hour_by_pub_date`
  - 통과
- `.venv\Scripts\python.exe -m unittest tests.test_workflow`
  - 통과, 96 tests OK
- `git diff --check`
  - 통과

## 제외한 파일 / ignore 확인

- `naver_news_문제_18시26분_SK하이닉스 2배 ETF/`
  - `.gitignore`의 `naver_news_문제*/` 규칙으로 ignore됨을 확인
- `.env`, `outputs/`, `runtime/`, `qa-artifacts/`
  - 기존 ignore 규칙 유지
- `tests/test_orchestration.py`, `tests/test_windows_scheduler.py`, `tests/test_workflow.py`
  - 로컬 dirty 상태가 있으나, 스킬 기준에 따라 테스트 파일은 기본적으로 push 대상에서 제외
  - 이번 검증을 위해 `tests/test_workflow.py`에는 로컬 테스트 보강이 남아 있으나 커밋에는 포함하지 않음
- `docs/codex-app/CRAWLER_BEHAVIOR_CONTRACT.md`
  - 로컬 Codex 작업 문서이며 `docs/codex-app/` ignore 대상이라 push하지 않음

## 누적 프롬프트 / 변경 흐름 추가 기록

- 사용자는 현재 크롤러 구조를 코드 기준으로 파악하고, 수정 전에 지켜야 할 동작 계약을 정리해 달라고 요청했다.
  - 결과: 실행 경로, workflow 공유 지점, scheduler/rollup/API/중복 정책을 정리한 로컬 문서를 만들었으나 `docs/codex-app/` ignore 대상이라 push하지 않았다.
- 사용자는 각 함수/클래스 정의가 어떤 기능인지 코드에서 바로 이해할 수 있도록 짧은 주석을 달아 달라고 요청했다.
  - 결과: 운영 소스 전체에 일반 한국어 요약 주석을 추가했다.
- 사용자는 API형 크롤러의 `api_recent_records`가 언제 삭제되는지 확인했고, 2000개 제한 대신 시간 기준 정리를 검토했다.
  - 결과: `seen_at`은 보류하고, 기사 `pub_date` 기준 최근 1시간 내 URL만 `api_recent_records`에 유지하도록 구현했다.
- 사용자는 `naver_news_문제_18시26분_...` 형태의 재현 폴더를 push 전에 ignore하라고 요청했다.
  - 결과: 기존 `.gitignore`의 `naver_news_문제*/` 규칙으로 이미 ignore되는 것을 확인했다.

## 남은 리스크

- `api_recent_records`가 `pub_date` 기준으로 정리되므로, API가 오래된 기사를 반복 반환하면 1시간 보존 정책만으로는 장기 중복 방지가 약할 수 있다.
- 수집 시각 기준 정리가 다시 필요해지면 `seen_at` 필드 추가를 재검토해야 한다.
- 주석은 동작을 바꾸지 않지만 diff가 커서 코드 리뷰 시 핵심 기능 변경인 `workflow.py`의 recent URL 보존 정책과 분리해서 확인하는 것이 좋다.
