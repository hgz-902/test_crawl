# Crawler Orchestrator

사이트별로 분리된 크롤러를 공통 오케스트레이터에서 실행하고, 실행 결과를 로그로 남기는 기본 구조입니다.

## 구조

- `crawlers/`: JSON 워크플로우 크롤러 래퍼
- `crawler_app/base.py`: 공통 크롤러 인터페이스와 결과 모델
- `crawler_app/orchestrator.py`: 크롤러 자동 발견 및 실행
- `crawler_app/document_extractors.py`: PDF/HWPX 첨부파일 텍스트 추출 공통 모듈
- `logs/orchestrator.log`: 텍스트 로그
- `logs/crawl_results.jsonl`: 크롤러별 실행 결과 JSONL 로그

## 실행

```bash
pip install -r requirements.txt
python main.py
python main.py --crawler configurable --config "configs/기후에너지환경부_보도자료.json"
uvicorn crawler_app.web:app --reload
python -m uvicorn crawler_app.web:app --reload --host 127.0.0.1 --port 3000
```

## JSON 설정 기반 크롤러

`configurable` 크롤러는 사이트별 Python 코드를 새로 만들지 않고 JSON 설정 파일에 URL과 DOM 선택 규칙을 정의해서 실행합니다.

```bash
python main.py --crawler configurable --config "configs/기후에너지환경부_보도자료.json"
```

설정 파일은 아래 정보를 관리합니다.

- `start_url`: 목록 페이지 URL. `{search_term}`를 넣으면 검색어별로 다른 주소를 만들 수 있다.
- `base_url`: 상대 URL을 절대 URL로 바꿀 때 사용할 기준 URL
- `output_dir`: 다운로드 원본, 추출 텍스트, 메타데이터 저장 위치
- 저장 파일명에는 `record_key` prefix가 붙고, 결과 스냅샷(`workflow_records.json`)으로 레코드와 파일의 매핑을 추적할 수 있다.
- `filter_terms`가 있으면 결과는 `output_dir/filter` 와 `output_dir/nonfilter` 로 분리 저장된다. 필터가 없으면 전체 결과를 `output_dir/filter` 에 저장한다.
- `notes`: 해당 크롤러의 특이사항, 예외 처리 메모, xpath 주의점
- `search_terms`: 여러 검색어를 순차 실행할 때 사용할 검색어 목록
- `filter_terms`: 수집이 끝난 뒤 결과 레코드 전체에서 한 번만 적용할 필터 키워드 목록
- `steps[].action = parser`: RSS 같은 구조화 응답을 파싱하는 step
- `steps[].attr = google`: `parser` step에서 Google News RSS 파서를 선택한다.
- `steps[].attr = naver`: `parser` step에서 Naver News Search API 파서를 선택한다.
- `parser` step에서는 `xpath`, `open_mode`, `wait_state`, `loop` 관련 필드를 사용하지 않는다.
- `steps[0].loop`: 목록/반복 영역을 시작하는 step 반복 사용 여부. 켜면 `xpath` + `xpath_2` 두 앵커를 입력하며, `loop_limit`를 비우면 최대까지 반복한다.
- `steps[0].xpath`: 반복 DOM 내부에서 실행할 첫 번째 단계 XPath
- `steps[].loop`: step 단위 반복 사용 여부. 2번 이후 step에서 켜면 현재 페이지 안의 반복 요소를 순회한다. `xpath` + `xpath_2` 두 앵커를 입력하며, `loop_limit`를 비우면 최대까지 반복한다.
- `steps[].loop_limit`: 반복 step의 최대 횟수. 비우면 `max until first miss`
- `download` step: XPath가 여러 요소에 매칭되면 각 요소를 순회하며 모두 다운로드
- 필터는 실행이 모두 끝난 뒤 레코드 단위로 한 번만 적용하며, 매칭 결과는 `filter`, 비매칭 결과는 `nonfilter` 아래에 별도 저장된다.
- `list`: 목록 item selector와 제목/날짜/상세 URL 생성 규칙
- `detail`: 상세 페이지의 본문/담당부서/연락처/첨부파일 selector

DOM 선택 규칙은 CSS selector와 XPath를 모두 지원합니다.

```json
{
  "selector": {
    "type": "css",
    "value": "h3 a"
  },
  "attr": "text"
}
```

```json
{
  "selector": {
    "type": "xpath",
    "value": ".//li[span[contains(text(), '담당부서')]]"
  },
  "attr": "text",
  "regex": "담당부서\\s*(.+)"
}
```

지원하는 주요 필드 옵션은 다음과 같습니다.

- `attr: "text"`: 선택된 요소의 텍스트 추출
- `attr: "html"`: 선택된 요소의 HTML 원문 추출
- `attr: "href"` 같은 속성명: HTML attribute 추출
- `regex`: 추출값에서 첫 번째 capture group 사용
- `template`: 앞서 추출된 필드값으로 값 생성
- `urljoin: true`: 상대 URL을 `base_url` 기준 절대 URL로 변환
- `date_format`: 날짜 문자열을 날짜로 파싱
- `html_to_text: true`: HTML 문자열을 텍스트로 변환
- `scope: "document"`: 상세 컨테이너가 아니라 문서 전체에서 selector 실행

### Naver News API 예시

Naver News Search API는 환경변수 `NAVER_CLIENT_ID`와 `NAVER_CLIENT_SECRET`가 필요합니다.
루트의 `.env.example` 를 참고해 `.env` 파일을 만들면 자동으로 읽습니다.
Naver API parser는 UI와 CLI 모두에서 안전한 실행 범위를 요구합니다. `page_limit`은 최대 10, `loop_limit`은 1~100 사이로 명시해야 합니다.

```bash
python main.py --crawler configurable --config "configs/네이버.json"
```

```json
{
  "name": "네이버뉴스",
  "start_url": "https://openapi.naver.com/v1/search/news.json?query={search_term}&display=20&start=1&sort=date",
  "output_dir": "outputs/naver_news",
  "search_terms": ["SK이노베이션", "최태원", "유가전망"],
  "steps": [
    {
      "name": "naver_news_api",
      "action": "parser",
      "attr": "naver",
      "page_limit": 1,
      "loop_limit": 20
    }
  ]
}
```

## 첨부파일 텍스트 추출

공통 모듈로 PDF와 HWPX 파일에서 텍스트를 추출할 수 있습니다.

```python
from crawler_app.document_extractors import extract_text_from_bytes

attachment_bytes = download_attachment_somehow()
extract_result = extract_text_from_bytes(
    file_bytes=attachment_bytes,
    file_type="hwpx",
    file_name="press_release.hwpx",
    source_url="https://example.com/file.hwpx",
)

if extract_result.success:
    attachment = {
        "file_name": extract_result.file_name,
        "file_type": extract_result.file_type,
        "text": extract_result.text,
        "text_length": extract_result.text_length,
    }
else:
    attachment = {
        "file_name": extract_result.file_name,
        "file_type": extract_result.file_type,
        "error": extract_result.error,
    }
```

`DocumentExtractResult`는 아래 정보를 공통으로 반환합니다.

- `success`: 추출 성공 여부
- `text`: 추출된 본문 텍스트
- `text_length`: 추출된 텍스트 길이
- `page_count`: PDF 페이지 수
- `metadata`: 추출 과정 메타데이터
- `error`: 실패 사유

주의사항:

- PDF 추출은 `pypdf` 의존성이 필요합니다.
- 현재 PDF는 텍스트 레이어가 있는 파일만 지원합니다.
- 구형 `hwp`는 아직 지원하지 않고 `hwpx`만 지원합니다.

## Crawler Orchestration

This feature is a common operations layer for existing `configs/*.json` crawlers. It does not add new site-specific crawler code. It keeps the existing JSON config workflow, `workflow_records.json`, outputs, and logging structure as the source of crawler behavior.

### Run The UI

```powershell
python -m uvicorn crawler_app.web:app --host 127.0.0.1 --port 3000
```

Open `http://127.0.0.1:3000/orchestration`.

### News Review API Test URLs

Run the web app, then open these URLs in a browser or API client.

Flat list:

- Latest first: `http://127.0.0.1:3000/api/news?user_id=unknown&sort_by=published_at&sort_order=desc&page=1&page_size=20`
- Oldest first: `http://127.0.0.1:3000/api/news?user_id=unknown&sort_by=published_at&sort_order=asc&page=1&page_size=20`
- Negative first: `http://127.0.0.1:3000/api/news?user_id=unknown&sort_by=sentiment_negative&sort_order=desc&page=1&page_size=20`

Grouped list:

- Latest first: `http://127.0.0.1:3000/api/news/grouped?user_id=unknown&sort_by=published_at&sort_order=desc&page=1&page_size=20`
- Oldest first: `http://127.0.0.1:3000/api/news/grouped?user_id=unknown&sort_by=published_at&sort_order=asc&page=1&page_size=20`
- Negative first: `http://127.0.0.1:3000/api/news/grouped?user_id=unknown&sort_by=sentiment_negative&sort_order=desc&page=1&page_size=20`

`sentiment_negative` sorts by `negative > neutral > positive > empty/other`, then newest first inside each sentiment group.

`/api/news` and `/api/news/grouped` include `has_analysis` on each item. Passing `has_analysis=true` filters the list to articles with confirmed AI analysis saved through `/analysis/save`; this filter is combined with the existing query parameters.

The orchestration page supports:

- Selecting registered crawler configs.
- Setting each selected crawler schedule as a five-field cron expression.
- Editing keyword terms.
- Editing notification recipients.
- Switching between the `설정 LIST / 배치 config` tab and the `등록된 스케줄 / 스케줄 결과 보기` tab without leaving the page.
- Saving local orchestration settings.
- Running selected crawler jobs manually without changing scheduler registration.
- Viewing recent run history, duplicate-stopped jobs, and mail dry-run/sent status.

Settings and run history are stored in local runtime files:

- `orchestration_state/settings.json`
- `orchestration_state/run_history.json`

`orchestration_state/` is ignored by git because it is machine-local runtime state.

### Duplicate Stop Policy

Before a batch run, the orchestration layer reads the configured output directory for the current crawler and builds duplicate state from `latest.json` plus any live `workflow_records.json` snapshots.

Duplicate keys use normalized `final_url` only. Title-based duplicate checks are intentionally not used.

`latest.json` is the boundary file used after `workflow_records.json` has been rolled up:

- `records` keeps the newest boundary per search/filter group.
- Numeric `search_terms` are treated as page parameters and share boundaries by `filter_term`.
- Normal search terms keep boundaries by `search_term`.
- Naver, Daum, and Google additionally keep `api_recent_records`, a source-wide recent URL index used to catch API articles that were already collected but are not the newest item of their search/filter group.

When a previous-run duplicate boundary is found, the current search term is stopped as `duplicate_stopped` and the next search term or selected crawler job can continue. When the duplicate appears only inside the same active run, the item is skipped and the current search term continues.

### Schedule Semantics

Each enabled job stores:

- `last_run_at`
- `next_run_at`
- `last_status`

The UI stores orchestration settings in `orchestration_state/settings.json`, while runtime state is kept per crawler under `orchestration_state/jobs/<job_id>.json`. This avoids concurrent Windows scheduled jobs overwriting one shared status file. `next_run_at` is calculated from each row's cron expression when monitoring is started and after a crawl starts.

The orchestration page separates settings, one-off runs, and background monitoring:

- `설정 저장` validates the cron settings and saves JSON settings only. It does not create, update, delete, or run Windows Scheduler tasks.
- `수동 실행` runs the currently selected jobs once with `force_due=True`. It does not change scheduler registration.
- `모니터링 시작` validates the current settings, saves them, deletes/recreates this clone's managed Windows Scheduler tasks, and shows the registered schedule list.
- `모니터링 종료` calls the checked-in `scripts/Stop-OrchestrationJobs.ps1` path, stops this clone's managed scheduled tasks, deletes their scheduler registrations, and clears the local scheduler registry. It preserves selected/enabled settings so `모니터링 시작` can recreate tasks from the saved JSON schedule. It never deletes `outputs/` or `workflow_records.json`.

### Keyword Mail Notification

Default keywords:

- `SK`
- `최태원`

Default recipients:

- `bloodknihts@gmail.com`
- `superknihts@nate.com`

SMTP credentials are never stored in code, config, README, logs, or UI settings. They are read only from environment variables:

```powershell
$env:SMTP_HOST="smtp.gmail.com"
$env:SMTP_PORT="587"
$env:SMTP_USER="bloodknihts@gmail.com"
$env:SMTP_FROM="bloodknihts@gmail.com"
$env:SMTP_PASSWORD="<Gmail app password>"
```

If `SMTP_PASSWORD` is missing, keyword notification runs in dry-run mode and records the dry-run result instead of sending mail. Even when SMTP credentials exist, the UI sends real mail only when the operator checks the saved "actual email send" option. Manual runs and scheduled runs re-read the saved setting before each run. Real Gmail sending should only be tested after the user provides an app password.

### Windows Task Scheduler

When `모니터링 시작` is pressed on Windows, the app synchronizes Windows Task Scheduler:

1. Deletes only tasks managed by this clone under `\CrawlerOrchestration\<project_namespace>\crawler_*`.
2. Recreates one task per enabled crawler config.
3. Converts each enabled row's five-field cron expression to the closest supported Windows Task Scheduler command:
   - `*/5 * * * *` -> every 5 minutes
   - `0 */2 * * *` -> every 2 hours
   - `0 3 * * *` -> daily at 03:00
   - `0 0 */2 * *` -> every 2 days at 00:00
   - `0 9 * * MON` -> weekly on Monday at 09:00
4. Runs `scripts/Run-OrchestrationJob.ps1 -JobId <job_id>`, which loads local `.env` values into the scheduled process and executes that crawler through `crawler_app.scheduled_runner`.

Unsupported cron forms are rejected before settings are saved to the scheduler. Each scheduled task uses its registered Windows trigger and runs with `force_due=True`; the trigger itself is the cadence source of truth. Different crawler tasks can run at the same time, while the same crawler is protected by a per-job lock under `orchestration_state/locks/<job_id>.lock`. Each crawler still follows the same item-level sequence: crawl, stop on a previous-run duplicate within the current search term, continue the next search term or next job, compare keywords, then send or dry-run email according to the saved setting.

To stop this clone's monitoring jobs from PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Stop-OrchestrationJobs.ps1 -ProjectRoot . -DeleteTasks
```

Use PowerShell `-WhatIf` with the script to preview the scoped task actions before stopping or deleting them.
The web UI uses the same script path for `모니터링 종료`, so manual and UI stop behavior stay aligned.

Secrets must stay out of git. Use Windows user environment variables or an ignored local `.env` file:

```powershell
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=bloodknihts@gmail.com
SMTP_FROM=bloodknihts@gmail.com
SMTP_PASSWORD=<Gmail app password>
NAVER_CLIENT_ID=<Naver client id>
NAVER_CLIENT_SECRET=<Naver client secret>
KAKAO_REST_API_KEY=<Kakao REST API key>
```

Scheduled run logs are written under `runtime/scheduled-task/`, which is ignored by git.

### Workflow Records Rollup

When the crawler web server is running (`python -m uvicorn crawler_app.web:app --host 127.0.0.1 --port 3000`), a Python background scheduler inside the server process rolls `outputs/*/filter/workflow_records.json` at the configured daily time. The rollup uses the same `crawler_app.workflow_records_rollup.rollup_workflow_records()` function as the manual PowerShell script, so file locking, archive placement, latest-first archive sorting, and keep-count pruning stay consistent.

The default rollup time is defined by `DEFAULT_ROLLUP_TIME` in `crawler_app/workflow_records_rollup.py`. The running web server rereads that source value on each scheduler check, so changing and saving the constant can take effect without restarting the server. A rollup is only skipped when the same `date + rollup time` has already run; changing the time later in the day allows that new daily boundary to run once. Rollup archives are stored under each crawler's `outputs/<crawler>/filter/rollup/` folder, and server-side rollup logs are written under `runtime/scheduled-task/`.

If the web server is not running at the configured time, the Python scheduler cannot run. For a manual one-off rollup, run `python -m crawler_app.workflow_records_rollup` from the project virtual environment.

### Validation

```powershell
python -m unittest discover -s tests
python -m uvicorn crawler_app.web:app --host 127.0.0.1 --port 3000
```

Then verify `/orchestration` in a browser by saving settings and running a small selected batch. Without SMTP credentials, mail notification should report dry-run.

## Workflow Records API

The app exposes a POST API that reads the current and rolled `workflow_records.json` files and returns records in the same record shape stored on disk.

Endpoint:

```text
POST /api/workflow-records
POST /api/workflow-records/search
```

Example single-day request:

```json
{
  "date": "2026-05-29",
  "source_name": "naver_news",
  "page": 1,
  "page_size": 20
}
```

Example range request across all sources:

```json
{
  "from_date": "2026-05-01",
  "to_date": "2026-05-29",
  "page": 1,
  "page_size": 20
}
```

Rules:

- `date` reads one rollup date. If it is today, the live `outputs/<source>/filter/workflow_records.json` file is used.
- `from_date` and `to_date` read matching rollup files for past dates and the live file when today's date is included.
- `source_name` is optional. When omitted, all `outputs/<source>/` folders are searched.
- Default pagination is `page=1`, `page_size=20`; `page_size` is capped at 100.
- `sort_by` defaults to `pub_date`, and `published_at` is accepted as an alias.
