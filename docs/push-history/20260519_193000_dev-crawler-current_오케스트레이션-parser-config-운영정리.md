# 오케스트레이션, parser 저장 구조, config 운영 정리

- Date/Time: 2026-05-19 19:30:00 KST
- Repository: `C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp`
- Branch: `dev/crawler-current`
- Remote target: `origin dev/crawler-current` (`https://github.com/K-Ternag/crawlService.git`)
- Commit message: `오케스트레이션 parser 저장 구조와 config 운영 정리`
- Push command: `git push origin dev/crawler-current:dev/crawler-current`

## 요청 작업 / Slice

기존 JSON config 기반 크롤러 구조를 유지하면서 오케스트레이션 운영 UI, 스케줄러 lifecycle, parser/API형 저장 구조, 운영 대상 config 목록을 정리했다. 일반 사이트별 크롤러 소스는 늘리지 않고, 공통 orchestration/web/scheduler/workflow/parser 저장 계층과 config JSON 중심으로 수정했다.

## 변경 파일

### 공통 runtime / orchestration / UI

- `crawler_app/orchestration.py`
- `crawler_app/web.py`
- `crawler_app/logging_utils.py`
- `crawler_app/runtime_maintenance.py`
- `static/app.js`
- `templates/orchestration.html`

### Parser/API 저장 구조

- `crawler_app/workflow.py`
- `crawler_app/naver_news_api.py`
- `crawler_app/google_news_rss.py`
- `crawler_app/daum_news_api.py`

### Config 정리

- 유지/수정: `configs/구글.json`, `configs/기후에너지부_보도자료.json`, `configs/네이버뉴스.json`, `configs/다음.json`, `configs/마켓인사이트.json`, `configs/산업부_보도자료.json`, `configs/시그널.json`, `configs/연합뉴스.json`, `configs/인베스트조선.json`
- 유지: `configs/dart.json`, `configs/더벨.json`, `configs/에프앤가이드.json`
- 제거: 요청한 운영 대상 12개 외 config JSON

### 테스트 / 기록

- `tests/test_daum_news_api.py`
- `tests/test_google_news_rss.py`
- `tests/test_naver_news_api.py`
- `tests/test_orchestration.py`
- `tests/test_runtime_maintenance.py`
- `tests/test_web.py`
- `tests/test_workflow.py`
- `prompts/20260519_170359_parser_storage_orchestration_performance.md`
- `prompts/20260519_173236_orchestration_button_lifecycle.md`
- `prompts/20260519_175951_schedule_tab_order.md`

## 변경 이유

- 네이버/구글/다음 parser/API형 결과가 다른 크롤러와 다르게 반복 실행마다 보기 어려운 경로로 쌓이거나, item별 추적성이 약한 부분을 보완해야 했다.
- 오케스트레이션 페이지 진입이 느린 원인은 Windows Task Scheduler 상세 조회가 GET 경로에서 동기적으로 실행되는 구조였기 때문에, 페이지 렌더와 scheduler 상세 조회를 분리해야 했다.
- 설정 저장, 모니터링 시작, 모니터링 종료의 책임이 섞이면 운영자가 저장만 했는데 scheduler가 바뀌는지 판단하기 어렵다. 따라서 settings 저장과 scheduler sync/stop을 분리했다.
- 설정 저장만 했거나 모니터링 종료 후에도 저장된 desired monitoring settings를 운영자가 볼 수 있어야 했다. 단, 이를 실제 Windows Scheduler 등록 목록처럼 가짜 표시하면 안 된다.
- 운영 대상 crawler config를 사용자가 지정한 12개로 줄여 UI 목록과 오케스트레이션 범위를 정리해야 했다.
- 네이버/구글/다음은 다시 검색어 목록 기준으로 검색해야 했고, parser/API 저장 결과도 일반 크롤러의 `texts/YYYYMMDD`와 비슷하게 `items/YYYYMMDD` 구조를 따라야 했다.

## 설계 판단 및 Tradeoff

- `/orchestration` GET은 registry만 빠르게 읽고, 실제 Windows Scheduler 상세 상태는 `/orchestration/schedulers/status` lazy endpoint로 분리했다. 장점은 페이지 첫 렌더가 빨라지는 점이고, 단점은 scheduler 상세 상태가 JS refresh 이후 채워지는 점이다.
- `설정 저장`은 `settings.json`만 갱신하고 scheduler sync/run/stop을 호출하지 않도록 유지했다. 장점은 버튼 의미가 명확하다는 점이고, 단점은 저장 후 실제 예약 반영에는 `모니터링 시작`이 별도로 필요하다는 점이다.
- `모니터링 종료`는 settings를 지우지 않고 managed scheduler task만 stop/delete하도록 했다. 저장된 enabled jobs/cron/recipients/sender는 남기므로 다시 `모니터링 시작`을 누르면 같은 설정으로 재등록할 수 있다.
- 저장된 모니터링 설정은 `등록된 스케줄 / 스케줄 결과 보기` 탭 안에 별도 섹션으로 표시했다. 실제 scheduler 영역을 위에 두고 saved settings를 아래에 두어, 현재 실제 등록 상태를 먼저 보게 했다.
- 네이버/구글/다음 item 파일은 stable hash 파일명을 유지하되 날짜 폴더만 `items/YYYYMMDD/`로 추가했다. 장점은 같은 날짜 반복 실행 시 파일명이 안정적이고 사람이 날짜별 산출물을 찾기 쉽다는 점이다. 단점은 날짜가 바뀌면 같은 item도 다른 날짜 폴더에 남을 수 있으나, workflow_records 중복 정책이 재수집 여부를 통제한다.
- config 제거는 local 복구 가능성을 위해 작업 중 `imsi/configs_removed_...`로 이동했지만, `imsi/`는 ignore 대상이므로 commit에는 운영 대상 외 config 삭제만 반영된다.
- runtime 누적 파일은 실행 직후 자동 정리 유틸로 관리한다. 운영 산출물인 `outputs/`와 `workflow_records.json`은 삭제 대상이 아니다.

## 구현 요약

- `crawler_app/web.py`
  - scheduler 상세 조회 lazy endpoint 추가.
  - orchestration GET에서 blocking scheduler detail 조회 제거.
  - 설정 저장/모니터링 시작/모니터링 종료 책임 분리.
  - 저장된 monitoring settings 표시 모델 추가.
- `templates/orchestration.html`, `static/app.js`
  - 탭 화면 유지.
  - 등록된 스케줄 영역과 저장된 모니터링 설정 영역 분리.
  - scheduler 상세 상태 lazy refresh 지원.
- `crawler_app/orchestration.py`, `crawler_app/logging_utils.py`, `crawler_app/runtime_maintenance.py`
  - runtime/scheduled-task, flash, history 계열 누적 파일 자동 정리 보조.
- `crawler_app/workflow.py`
  - parser item별 저장 파일을 workflow record output_file과 연결.
  - filter/nonfilter 분리 후 parser output manifest와 item file 경로 보존.
- `crawler_app/naver_news_api.py`, `crawler_app/google_news_rss.py`, `crawler_app/daum_news_api.py`
  - item별 JSON 저장.
  - `items/YYYYMMDD/item_<hash>.json` 경로 사용.
  - 한국 시간 기준 날짜 라벨 적용.
- `configs/*.json`
  - 네이버뉴스/구글/다음은 검색어 목록 기반 URL로 복구.
  - 운영 대상 외 config 삭제.
  - 일부 config는 테스트/운영 기준에 맞춘 headless, search/filter, loop_limit 설정 유지.
- `tests/*`
  - parser item별 저장, 날짜 폴더, duplicate/workflow record, scheduler lifecycle, lazy scheduler status, runtime cleanup 테스트 추가/수정.

## 검증 결과

- `.\.venv\Scripts\python.exe -m unittest tests.test_naver_news_api tests.test_google_news_rss tests.test_daum_news_api`
  - Result: PASS, 17 tests OK
- `.\.venv\Scripts\python.exe -m unittest tests.test_workflow.WorkflowDownloadTests.test_run_workflow_config_parses_naver_news_api_without_playwright tests.test_workflow.WorkflowDownloadTests.test_run_workflow_config_parses_daum_news_api_without_playwright tests.test_workflow.WorkflowDownloadTests.test_run_workflow_config_parses_google_news_rss_without_playwright tests.test_workflow.WorkflowDownloadTests.test_run_workflow_config_parses_google_news_rss_without_search_terms_uses_indexed_dir tests.test_workflow.WorkflowDownloadTests.test_filter_split_removes_unclassified_root_parser_outputs`
  - Result: PASS, 5 tests OK
- `.\.venv\Scripts\python.exe -m unittest discover -s tests`
  - Result: PASS, 174 tests OK
- 임시 경로 저장 smoke
  - Naver: `items/20260519/item_*.json` 생성 확인.
  - Google: `items/20260519/item_*.json` 생성 확인.
  - Daum: `items/20260519/item_*.json` 생성 확인.
- Config list 확인
  - `list_configs()` 기준 운영 대상 12개만 표시됨.

## Ignore Hygiene / 제외 파일

- `.env`, `.env.*`: secret 파일. `.env.example`만 tracking 허용.
- `.venv/`, `__pycache__/`, `.pytest_cache/`: local runtime/cache.
- `outputs/`, `orchestration_state/`, `runtime/`, `logs/`, `qa-artifacts/`: 실행 산출물과 local scheduler/history/log.
- `imsi/`: 제거한 config의 local 복구용 이동 위치. commit 대상 아님.
- Harness/session docs: `TASK_CONTRACT.md`, `TASK_PLAN.md`, `RUN_CONTEXT.md`, `DECISION_RULING.md`, `GUI_QA_*`, `THREAT_MODEL.md`, `SECURITY_TEST_CHECKLIST.md`, `SOURCE_CHANGE_GUARDRAIL.md` 등은 `.gitignore`로 제외.
- 사용자가 명시적으로 기록하지 말라고 한 후속 prompt 원문은 push record와 prompt 기록에 포함하지 않았다.

## Secret 점검

- diff에서 확인된 `NAVER_CLIENT_SECRET`, `KAKAO_REST_API_KEY`, `SMTP_PASSWORD`는 환경변수 이름 또는 설명 문자열이다.
- 실제 secret 값, Gmail 앱 비밀번호, API key 값은 staged/push 대상에 포함하지 않는다.

## 남은 리스크

- 실제 Windows Task Scheduler는 서버 권한, PowerShell 정책, Python PATH 차이에 따라 재검증이 필요하다.
- 네이버/다음 API는 환경변수가 없으면 실행 실패한다. 키 값은 `.env` 또는 운영 환경변수로만 제공해야 한다.
- Google RSS, Naver API, Kakao API의 외부 응답 형식이나 rate limit이 바뀌면 parser/API 계층 검증이 필요하다.
- 날짜 폴더는 한국 시간 기준으로 생성된다. 자정 전후 실행 시 산출물이 날짜별로 갈릴 수 있다.
- 운영 대상 외 config를 삭제했으므로, 나중에 다시 필요하면 local `imsi/configs_removed_*` 또는 git history에서 복구해야 한다.
- 실제 Gmail 발송은 이번 push 준비 단계에서 수행하지 않았다.

## Cumulative Prompt / Request Flow

### Recorded request: parser/API 저장 방식과 오케스트레이션 성능 개선

- Prompt record: `prompts/20260519_170359_parser_storage_orchestration_performance.md`
- 결과:
  - 다음 API 결과를 item별 파일로 저장.
  - 네이버/구글/다음 반복 실행 시 불필요한 날짜 suffix 경로 증식 방지.
  - `/orchestration` GET에서 Windows Scheduler 상세 조회를 분리하여 첫 렌더 blocking을 줄임.

### Recorded request: 설정 저장 / 모니터링 시작 / 모니터링 종료 책임 분리

- Prompt record: `prompts/20260519_173236_orchestration_button_lifecycle.md`
- 결과:
  - 설정 저장은 settings JSON만 갱신.
  - 모니터링 시작은 enabled settings 기준 scheduler sync.
  - 모니터링 종료는 settings를 유지하고 scheduler task만 stop/delete.
  - 종료 후 다시 시작하면 저장된 settings로 scheduler 재생성 가능.

### Recorded request: 스케줄 탭 내 섹션 순서 조정

- Prompt record: `prompts/20260519_175951_schedule_tab_order.md`
- 결과:
  - 실제 `등록된 스케줄 영역`을 `저장된 모니터링 설정` 위에 표시.

### User-directed follow-up requests with prompt recording explicitly disabled

사용자가 원문 기록 금지를 명시한 요청들은 prompt 전문을 저장하지 않았다. 다만 코드 변경 이력 관리를 위해 아래 기술적 결과만 기록한다.

- 운영 대상 config를 12개로 축소:
  - 시그널, 마켓인사이트, 다음, 인베스트조선, 연합뉴스, 네이버뉴스, 산업부_보도자료, 구글, 기후에너지부_보도자료, dart, 더벨, 에프앤가이드만 유지.
- 네이버뉴스/구글/다음을 검색어 기준 검색 구조로 복구:
  - `search_terms`를 다시 채우고 `{search_term}` URL 템플릿 사용.
- 네이버/구글/다음 parser item 저장 경로를 일반 크롤러 산출물 구조에 맞춤:
  - `005_SK/items/YYYYMMDD/item_*.json` 형태.

## Commit / Push

- Commit message: `오케스트레이션 parser 저장 구조와 config 운영 정리`
- Push command: `git push origin dev/crawler-current:dev/crawler-current`
- Commit hash: pending
- Push result: pending
