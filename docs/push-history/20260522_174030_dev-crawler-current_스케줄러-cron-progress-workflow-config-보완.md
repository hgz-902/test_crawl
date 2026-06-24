# 2026-05-22 dev/crawler-current 스케줄러 cron/progress/workflow/config 보완

## 기본 정보

- 일시: 2026-05-22 17:40 KST
- repository: `C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp`
- branch: `dev/crawler-current`
- remote: `origin https://github.com/K-Ternag/crawlService.git`
- push target: `origin dev/crawler-current`
- commit message: `오케스트레이션 스케줄러와 크롤러 설정 보완`

## 요청 / 작업 범위

- Windows Task Scheduler가 Linux cron의 특정 분 목록 표현식을 안전하게 처리하도록 보완.
- split scheduler가 여러 Windows task로 생성되더라도 UI에서는 크롤러 항목당 하나로 집계 표시.
- 모니터링 시작/종료 반복 클릭으로 같은 task를 중복 삭제하려는 race condition 방어.
- 모든 주요 form 실행 중 전역 progress overlay 표시.
- `workflow_records.json`이 무제한 커지지 않도록 20,000줄 이하 rolling window 저장 정책 적용.
- 신규 크롤링 설정 후보 추가 및 기존 모니터링 대상 설정/키워드 정리.

## 변경 파일

### 소스 / UI / 스크립트

- `crawler_app/orchestration.py`
- `crawler_app/scheduled_runner.py`
- `crawler_app/web.py`
- `crawler_app/windows_scheduler.py`
- `crawler_app/workflow.py`
- `scripts/Stop-OrchestrationJobs.ps1`
- `static/app.js`
- `static/styles.css`
- `templates/layout.html`
- `templates/orchestration.html`

### 설정 / 운영 자료

- `attach/모니터링 사이트 및 키워드.xlsx`
- `configs/구글.json`
- `configs/기후에너지부_보도자료.json`
- `configs/네이버뉴스.json`
- `configs/다음.json`
- `configs/마켓인사이트.json`
- `configs/산업부_보도자료.json`
- `configs/시그널.json`
- `configs/연합뉴스.json`
- `configs/인베스트조선.json`
- `configs/theminjoo.json`
- `configs/국무회의_브리핑.json`
- `configs/국민의힘_보도자료.json`
- `configs/국회의안정보시스템.json`
- `configs/정책브리핑_보도자료.json`

### 프롬프트 기록

- `prompts/20260522_132353_scheduler_cron_split_ui_grouping.md`
- `prompts/20260522_132917_scheduler_start_stop_duplicate_request_guard.md`
- `prompts/20260522_140733_workflow_records_line_limit.md`
- `prompts/20260522_141748_workflow_records_rolling_window_policy.md`
- `prompts/20260522_144305_global_progress_overlay.md`

## 설계 판단

### Cron 특정 분 목록 처리

Windows Task Scheduler는 Linux crontab의 모든 표현식을 그대로 지원하지 않는다. 기존에 정상 동작하던 `* * * * *`, `*/5 * * * *`, `*/10 * * * *` 같은 표현식은 단일 task로 유지하고, `1,6,11,16 * * * *`처럼 특정 분 목록이 있는 경우에만 분 개수만큼 task를 분리 생성하도록 했다.

장점:
- 기존 단일 task 동작을 불필요하게 바꾸지 않는다.
- 특정 분 목록은 Windows Task Scheduler가 이해할 수 있는 단위로 분해된다.
- registry에 `schedule_strategy`, `task_variant`를 남겨 UI/삭제 로직이 split task를 추적할 수 있다.

단점 / tradeoff:
- 특정 분 목록이 많으면 실제 Windows task 수가 늘어난다.
- 이를 완화하기 위해 UI는 job 기준으로 집계 표시한다.

보류한 대안:
- Windows Task Scheduler를 1분 tick으로만 두고 Python runner에서 cron match를 판단하는 방식은 task 수를 줄일 수 있지만, 매분 runner가 뜨는 구조라 운영 부하와 로그 소음이 커질 수 있어 이번 기본 구현에서 제외했다.

### 등록된 스케줄 UI 집계

split task가 실제로 여러 개 생성되더라도 운영자가 봐야 하는 단위는 크롤러 항목이다. 따라서 `job_id` 기준으로 registry task를 묶고, 다음 실행 시간은 split task들의 next run 중 가장 가까운 값으로 표시한다. Task 컬럼은 Windows Scheduler 경로가 보이도록 대표 task name을 유지하되 `_m11` 같은 세부 suffix는 숨긴다.

### 모니터링 시작/종료 중복 요청 방어

중복 클릭으로 동일 task를 여러 stop 요청이 동시에 삭제하면 `Unregister-ScheduledTask`가 ObjectNotFound를 낼 수 있다. 방어는 3층으로 구성했다.

- frontend: submit 직후 모니터링 시작/종료 버튼 disable 및 hidden action 보존.
- backend: start/stop route에 `asyncio.Lock` 적용.
- PowerShell: 이미 삭제된 task는 오류가 아니라 삭제 완료에 준해 처리.

### workflow_records rolling window

`workflow_records.json`은 운영 중 계속 커질 수 있으므로 저장 직전 JSON line count가 20,000줄을 넘지 않도록 제한한다. 최신 record prepend 정책은 유지하고, 제한 초과 시 하단의 오래된 record부터 제거한다.

tradeoff:
- 오래된 record가 제거되면 그 오래된 URL은 중복 index에서 사라질 수 있다.
- 그러나 파일 크기와 write 성능을 유지하기 위한 의도된 운영 정책이다.

### 전역 progress overlay

크롤링, 미리보기, 설정 저장, 모니터링 시작/종료 등은 서버 처리 중 정확한 percent를 알기 어렵다. 따라서 공통 layout에 비확정형 progress overlay를 두고 form submit 시 기능별 메시지를 표시한다. confirm 취소 또는 중복 submit 방어로 요청이 막힌 경우에는 overlay가 뜨지 않도록 했다.

## 구현 요약

- `windows_scheduler.py`
  - cron split plan 도입.
  - split task naming과 registry metadata 추가.
  - scheduler detail XML/action parsing 보완.
  - job 기준 split task 삭제 지원.

- `web.py`
  - 모니터링 시작/종료 lock 적용.
  - scheduler row를 `job_id` 기준으로 집계.
  - split task의 nearest next run, latest last run, representative result 표시.
  - scheduler 삭제 시 같은 job의 split task 전체 삭제.

- `scheduled_runner.py`
  - `--cron-gate` 옵션 추가.
  - saved settings를 기준으로 현재 cron과 맞지 않으면 실행 skip.

- `workflow.py`
  - `workflow_records.json` 저장 전 20,000줄 제한 적용.

- `orchestration.py`
  - orchestration snapshot merge/write 경로에서도 `workflow_records.json` line limit 재사용.
  - cron range matching 보완.

- `Stop-OrchestrationJobs.ps1`
  - 이미 삭제된 task는 idempotent하게 처리.

- `static/app.js`, `static/styles.css`, `templates/layout.html`
  - 전역 progress overlay 추가.
  - 모니터링 시작/종료 버튼 pending/disabled 스타일 추가.

- `templates/orchestration.html`
  - split task를 하나의 대표 row로 표시하고 task 묶음 수를 보조 표시.

- `configs/*.json`
  - 모니터링 대상 검색어/필터/페이지 설정 정리.
  - 신규 설정 추가: 민주당 모두발언, 국민의힘 보도자료, 국무회의 브리핑, 국회의안정보시스템, 정책브리핑 보도자료.

## 누적 프롬프트 / 변경 흐름 추가 기록

- Cron 특정 분 실행 보완:
  - `* * * * *`, `*/5 * * * *`, `*/10 * * * *`는 기존처럼 단일 task 유지.
  - `1,6,11,16 * * * *` 등 특정 분 목록은 분 개수만큼 Windows task 생성.
  - UI에서는 split task를 항목당 하나로 집계 표시.

- 모니터링 시작/종료 반복 클릭 방어:
  - 빠른 반복 클릭으로 이미 삭제된 task를 다시 삭제하는 오류를 방지.
  - frontend disable, backend lock, PowerShell idempotent delete를 함께 적용.

- workflow_records 크기 제한:
  - 20,000줄 초과 시 최신 record를 유지하고 오래된 record를 하단에서 제거하는 rolling window 적용.
  - workflow 직접 저장과 orchestration snapshot merge 저장 모두 같은 제한 적용.

- 전역 progress overlay:
  - 크롤링/설정/스케줄러 작업 대기 중 사용자가 완료 여부를 볼 수 있도록 비확정형 progress overlay 추가.

- 크롤링 설정 추가/정리:
  - 신규 정당/정부 사이트 설정 후보를 추가했다.
  - 정책브리핑 보도자료는 상세 본문 XPath가 `content_body`가 아니라 실제 상세 DOM 기준 영역이어야 해서 설정이 조정되었다.

## 검증 결과

명령:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_workflow tests.test_orchestration tests.test_scheduled_runner tests.test_windows_scheduler tests.test_web
```

결과:

```text
Ran 179 tests in 3.445s
OK
```

추가 확인:
- `git status --short --ignored`로 `.env`, `.venv/`, `outputs/`, `orchestration_state/`, `runtime/`, `logs/`, `qa-artifacts/`, cache 계열이 ignored 상태임을 확인했다.
- 정책브리핑 보도자료 실패 원인은 기존 `download_text` XPath가 실제 상세 DOM에 없는 `//*[@id="content_body"]`였기 때문으로 확인했다.

## 의도적으로 제외한 파일

규칙에 따라 테스트 파일 변경은 이번 stage에서 제외한다.

- `tests/test_orchestration.py`
- `tests/test_scheduled_runner.py`
- `tests/test_web.py`
- `tests/test_windows_scheduler.py`
- `tests/test_workflow.py`

로컬/생성/비밀/캐시 산출물은 stage하지 않는다.

- `.env`
- `.venv/`
- `outputs/`
- `orchestration_state/`
- `runtime/`
- `logs/`
- `qa-artifacts/`
- `imsi/`
- `__pycache__/`
- `.pytest_cache/`
- `attach/~$모니터링 사이트 및 키워드.xlsx`
- `codex_app_agents.md`
- `docs/codex-app/`

## 남은 리스크

- split scheduler는 특정 분 목록이 길수록 Windows task 수가 증가한다. 현재는 `MAX_SPLIT_TASKS_PER_JOB`로 과도한 분할을 제한한다.
- 새로 추가된 사이트 설정은 사이트 DOM 변경에 취약하다. XPath는 소스코드가 아니라 운영자 설정으로 관리되어야 한다.
- `workflow_records.json` rolling window로 인해 아주 오래된 중복 기록은 의도적으로 제거될 수 있다.
- 정책브리핑류 사이트는 본문보다 첨부파일에 실제 내용이 들어있는 경우가 있어 다운로드 성공 여부까지 별도 운영 검수가 필요하다.

## push 정보

- push command: `git push origin dev/crawler-current`
- push result: pending
