# 오케스트레이션 운영 UI와 스케줄러 백그라운드화

- Date/Time: 2026-05-19 16:32:54 KST
- Repository: C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp
- Branch: dev/crawler-current
- Remote target: origin dev/crawler-current (`https://github.com/K-Ternag/crawlService.git`)
- Commit message: `오케스트레이션 운영 UI와 스케줄러 실행 구조 개선`
- Push command: `git push origin dev/crawler-current:dev/crawler-current`

## 요청 작업 / Slice

기존 JSON config 기반 크롤러 구조를 최대한 보존하면서, 오케스트레이션 운영 UI와 Windows Task Scheduler 기반 백그라운드 실행 구조를 개선했다. 사이트별 크롤러 소스는 늘리지 않고, 공통 orchestration/web/scheduler/script/UI 계층 중심으로 수정했다.

## 변경 파일

- `README.md`
- `crawler_app/orchestration.py`
- `crawler_app/scheduled_runner.py`
- `crawler_app/web.py`
- `crawler_app/windows_scheduler.py`
- `scripts/Stop-OrchestrationJobs.ps1`
- `static/app.js`
- `static/styles.css`
- `templates/layout.html`
- `templates/orchestration.html`
- `tests/test_scheduled_runner.py`
- `tests/test_web.py`
- `tests/test_windows_scheduler.py`
- `prompt.md`
- `prompts/20260519_143900_orchestration_tabs_stop_followup.md`

## 변경 이유

- 오케스트레이션 페이지가 설정/트리거 UI로만 동작하고, 실제 예약 실행은 페이지 생명주기와 분리되어야 했다.
- `설정 저장`이 scheduler sync와 실행까지 암묵적으로 수행하던 구조는 운영자에게 혼란을 줄 수 있어, 저장/수동 실행/모니터링 시작/모니터링 종료를 명확히 분리해야 했다.
- Windows Task Scheduler에 등록된 작업 상태와 최근 실행 결과를 운영자가 한 화면에서 확인하고, 필요 시 이 프로젝트 namespace의 task만 종료/삭제할 수 있어야 했다.
- 실패 로그에는 config/job/path/stage/exception 정보가 남아야 사람이 원인을 추적할 수 있다.
- 후속 점검에서 기존 anchor/button식 화면 이동이 아닌 실제 tab panel 전환과, Windows Scheduler sentinel 시간/원시 result code 정리가 필요했다.
- 탭 클릭이 사용자 브라우저에서 동작하지 않는 현상이 있어, static JS cache busting과 페이지 내 fallback tab handler를 추가했다.

## 설계 판단 및 Tradeoff

- 설정 저장은 `orchestration_state/settings.json`만 갱신하도록 분리했다. 장점은 저장과 실행 부작용이 분리되어 운영자가 예측하기 쉽다는 점이고, 단점은 스케줄 반영에는 별도 `모니터링 시작` 클릭이 필요하다는 점이다.
- 모니터링 시작은 현재 settings 기준으로 managed scheduler task를 재생성한다. 안전성은 높지만 전체 재생성 방식이라 task 수가 많으면 시간이 걸릴 수 있다. 변경분만 반영하는 diff sync는 후속 최적화 후보로 남겼다.
- 모니터링 종료는 web route가 독자 구현하지 않고 `scripts/Stop-OrchestrationJobs.ps1` 경로를 호출하도록 맞췄다. 이렇게 해야 사용자가 터미널에서 쓰는 정지 로직과 UI 정지 로직이 어긋나지 않는다.
- task 범위는 project-root hash namespace로 제한했다. 다른 clone/project task를 건드리지 않는 쪽을 우선했다.
- 스케줄 상태 표시는 registry + 실제 Windows Task Scheduler 상세 조회를 병합한다. 운영 가시성은 좋아졌지만 페이지 로딩 시 Windows 조회 비용이 생긴다. 최근 성능 점검상 lazy-load/cache가 후속 개선 후보다.
- prompt 기록은 `prompt.md` + `prompts/*.md` 누적 구조로 유지했다. 단, 사용자가 명시적으로 기록 금지한 후속 진단/수정 요청은 기록하지 않았다.

## 구현 요약

- `crawler_app/web.py`: `/orchestration` 단일 POST action 분기, PRG 패턴, 저장/실행/모니터링 시작/종료 분리, scheduler row 병합, Last Run/Last Result 표시 정규화.
- `crawler_app/windows_scheduler.py`: managed task namespace, scheduler registry, 실제 task 상세 조회, checked-in stop script 연동 보강.
- `scripts/Stop-OrchestrationJobs.ps1`: 현재 project-root namespace의 task만 stop/delete. outputs와 workflow_records는 삭제하지 않음.
- `crawler_app/scheduled_runner.py`: 최신 settings 읽기, disabled job skip, 실행 시작/요약 로그 출력.
- `crawler_app/orchestration.py`: 실패 metadata에 config name/job id/config path/stage/exception 정보 보강.
- `templates/orchestration.html`, `static/app.js`, `static/styles.css`, `templates/layout.html`: 운영 설정 상단 이동, 실제 tab UI, tab fallback, cache busting.
- `README.md`: 운영 동작과 SMTP 예시 보완.
- `tests/*`: web route, scheduler, scheduled runner, tab structure, display normalization, stop/start lifecycle 검증 추가.

## 검증 결과

- `./.venv/Scripts/python.exe -m unittest tests.test_web -q`
  - Result: PASS, 31 tests OK
- `./.venv/Scripts/python.exe -m unittest discover -s tests -q`
  - Result: PASS, 167 tests OK
- Browser/UI 검수
  - `http://127.0.0.1:3000/orchestration`에서 탭 UI 확인.
  - `등록된 스케줄 / 스케줄 결과 보기` 클릭 시 해당 panel이 표시되고 `설정 LIST / 배치 config` panel이 숨겨지는 것 확인.
  - `app.js?v=20260519-tabs` cache busting 적용 확인.
- Windows Scheduler 확인
  - project namespace task 조회/삭제/재생성/종료 smoke 흐름을 앞선 검수에서 확인.
  - 페이지 진입은 Windows Scheduler 상세 조회 및 history 로딩 때문에 1.7~4.2초가 걸릴 수 있음을 확인했으며, 이는 이번 커밋의 수정 대상이 아니라 후속 최적화 후보로 남김.

## 제외 파일 / Ignore Hygiene

- `configs/*.json`: UI/테스트 과정에서 검색어/filter/loop_limit 상태가 바뀐 파일. 이번 커밋 범위는 공통 orchestration/web/scheduler/script/UI 계층이므로 제외.
- `.env`, `.venv/`, `outputs/`, `orchestration_state/`, `runtime/`, `logs/`, `qa-artifacts/`, `imsi/`, `__pycache__/`: local runtime/test/secret artifacts로 `.gitignore` 대상.
- latest ad-hoc performance diagnosis prompt: 사용자 지시에 따라 prompt 기록 및 push record 원문 포함 대상에서 제외.

## 남은 리스크

- 오케스트레이션 페이지 진입 시 Windows Scheduler 상세 조회와 큰 history JSON 로딩 때문에 사용자가 2~5초 로딩을 체감할 수 있다. `scheduler detail lazy-load/cache`, `recent history summary index`, `diff sync`가 후속 개선 후보다.
- 모니터링 시작은 현재 전체 managed task 삭제 후 재생성 방식이라 enabled 항목 수가 많으면 느릴 수 있다.
- Windows Task Scheduler와 PowerShell 정책/권한/PATH가 다른 서버에서 다르면 등록/실행/종료 smoke를 다시 확인해야 한다.
- 실제 Gmail 발송은 사용자 명시 승인 없이는 재검증하지 않았다.
- config JSON 변경은 이번 커밋에 포함하지 않는다. UI 테스트 중 바뀐 실행 설정 상태로 보이며, 사이트별 설정 변경 commit이 필요하면 별도 slice로 다룬다.

## Cumulative Prompt / Request Flow

### Prompt 1: prompt.md 저장 원문

```text
너는 크롤링 프로그램의 기존 구조를 최대한 보존하면서, 오케스트레이션 운영 UI와 백그라운드 스케줄러 실행 구조를 수정해야 한다.

작업 경로:
C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp

대상 프로젝트:
- 기존 JSON config 기반 크롤러
- 사이트별 크롤러 소스코드를 새로 늘리지 말 것
- 기존 configs/*.json, workflow_records.json, outputs, runtime, orchestration_state 구조를 최대한 활용할 것
- 변경은 공통 orchestration/web/scheduler/script/UI 계층에 한정할 것
- 일반 사이트별 크롤러 로직은 이번 작업 범위가 아니다

중요한 선행 규칙:
- 사용자가 앞으로 적는 작업 프롬프트는 즉시 `prompt.md` 또는 프로젝트 내 적절한 프롬프트 기록 파일에 먼저 저장하라.
- 저장 후 작업을 시작하라.
- 이후 Git Push Change Log 스킬을 이용해 push할 때, 어떤 프롬프트 내용에 의해 수정이 진행되었는지 push record에 반드시 정리하라.
- 이때 프롬프트는 요약이 아니라 전문을 포함하라.
- 단, 프롬프트 안에 secret이 포함되어 있다면 `prompt.md`와 push record에는 `[REDACTED_SECRET]`로 마스킹하라.
- `.env`, Gmail 앱 비밀번호, SMTP_PASSWORD, NAVER_CLIENT_SECRET, KAKAO_REST_API_KEY 등 secret은 절대 prompt.md, README, push record, 로그, 커밋에 넣지 마라.

먼저 해야 할 일:
1. 현재 사용자 프롬프트 전문을 `prompt.md`에 저장하라.
2. 기존 구조를 파악하라.
3. 수정 전 pre-edit gate를 아래 형식으로 보고하라.
4. 그 다음 구현하라.

pre-edit gate 형식:

- classification: non-trivial
- reason
- source-code change needed: yes/no
- source-code change scope
- files likely to change
- validation plan
- risks

먼저 확인할 파일:
- README.md
- main.py
- crawler_app/orchestration.py
- crawler_app/web.py
- crawler_app/windows_scheduler.py 또는 scheduler 관련 파일
- crawler_app/scheduled_runner.py가 있으면 확인
- scripts/Run-OrchestrationJob.ps1 또는 오케스트레이션 실행용 ps1 파일
- 기존 scripts 하위 scheduler/runner 관련 ps1 파일
- templates/orchestration.html 또는 오케스트레이션 UI 템플릿
- static/*.css
- tests 하위 orchestration/scheduler/web 관련 테스트
- .gitignore

요구사항 1. 페이지와 분리된 백그라운드 실행 구조

현재 오케스트레이션 페이지에서 설정 후, 해당 페이지에서 다른 URL로 이동하거나 아예 페이지를 닫아도 설정된 스케줄러 및 작업은 정상적으로 수행되어야 한다.

구현 기준:
- 오케스트레이션 페이지는 설정/트리거 UI일 뿐이어야 한다.
- 실제 수행 프로세스는 웹 페이지 생명주기와 분리되어야 한다.
- 설정은 JSON 파일 등에 저장하라.
  - 예: `orchestration_state/settings.json`
- Windows Task Scheduler 또는 별도 scheduled runner가 저장된 설정을 읽어 백그라운드에서 실행해야 한다.
- scheduled runner는 실행 시점에 최신 settings를 다시 읽어야 한다.
- stale launcher argument 때문에 오래된 enabled job 목록, 오래된 이메일 발송 허용값, 오래된 recipients를 쓰면 안 된다.
- launcher에 특정 job id가 들어 있어도 현재 settings에서 disabled면 실행하지 않는 것이 안전하다.
- 실행 로그는 `runtime/scheduled-task/` 또는 기존 runtime log 경로에 남겨라.
- output, workflow_records.json, 기존 수집 기록은 유지해야 한다.

요구사항 2. 기존 “설정 저장과 동시에 실행/스케줄링” 옵션 제거, “모니터링 시작” 버튼 추가

제거할 것:
- “설정 저장과 동시에 선택 항목을 실행하고, 저장 시점 기준으로 주기별 스케줄링”
- 유사한 force_due/immediate-run-on-save 옵션
- 설정 저장 버튼이 scheduler를 자동 생성/수정/삭제하는 동작

새 동작:
- `설정 저장`
  - JSON 설정만 저장
  - Windows Scheduler 생성/수정/삭제하지 않음
  - 크롤링 실행하지 않음
- `수동 실행`
  - 선택된 항목을 지금 1회 실행
  - Scheduler 설정은 변경하지 않음
- `모니터링 시작`
  - 현재 UI 설정을 저장
  - 기존 이 프로젝트가 관리하는 scheduler task를 삭제 또는 재생성
  - 선택된 항목별 scheduler task를 생성
  - 생성된 task 목록과 상태를 페이지에 표시

주의:
- scheduler sync 전에 설정 검증을 먼저 하라.
- 검증 실패 시 settings를 저장하거나 scheduler를 변경하지 말고 사용자에게 명확한 오류를 보여줘라.
- 다른 clone/project의 scheduler는 건드리지 마라.
- managed task name에는 project-root 기반 namespace 또는 이에 준하는 안전한 식별자를 사용하라.

요구사항 3. 강제 종료용 ps1 추가 및 “모니터링 종료” 버튼 연동

현재 오케스트레이션 관련 ps1 파일 중 실행용 파일은 있는데 종료용 파일이 없다.

해야 할 일:
- 사용자가 오케스트레이션 스케줄러/실행 작업을 강제 종료할 수 있는 PowerShell 파일을 추가하라.
- 예시 파일명:
  - `scripts/Stop-OrchestrationJobs.ps1`
  - 또는 기존 naming convention에 맞는 이름
- 기능:
  - 이 프로젝트가 관리하는 Windows Task Scheduler 작업만 대상으로 할 것
  - 다른 프로젝트/다른 clone의 scheduler task를 종료하지 말 것
  - project-root hash namespace 또는 기존 managed task prefix를 사용해 범위를 제한할 것
  - 실행 중인 scheduled task는 `/End` 또는 적절한 PowerShell API로 종료할 것
  - 옵션으로 scheduler task 삭제까지 가능하게 하라
  - 기본 동작은 “실행 중 작업 종료” 또는 “모니터링 종료에 필요한 안전한 정지”로 정의하라
  - 예:
    - `-DeleteTasks` 옵션이 있으면 종료 후 task 삭제
    - `-WhatIf` 또는 dry-run 성격의 옵션 지원 가능하면 추가
  - launcher/log/runtime 파일 삭제는 별도 옵션으로만 처리하라
  - outputs, workflow_records.json은 절대 삭제하지 마라
- UI 연동:
  - 오케스트레이션 페이지에 `모니터링 종료` 버튼을 추가하라.
  - `모니터링 종료` 버튼을 누르면 이 프로젝트가 관리하는 scheduler task를 종료하고, 필요 시 삭제한다.
  - 종료 결과를 페이지에 표시하라.
  - 종료 후 등록된 스케줄 목록이 갱신되어야 한다.
- 테스트:
  - 실제 Windows 환경이면 테스트용 namespaced task를 생성한 뒤 stop ps1 또는 stop route로 종료/삭제 smoke test를 수행하라.
  - 실제 task 생성이 어렵다면 command mock/fake 기반 테스트를 추가하라.
  - 다른 namespace task는 건드리지 않는 테스트를 추가하라.

요구사항 4. 오퍼레이션 관련 UI 요소 상단 이동

오케스트레이션 페이지의 UI 위치를 바꿔라.

상단에 배치할 것:
- 키워드
- 메일 수신자
- 발신자
- 실행 옵션
- 실제 메일 발송 허용 또는 dry-run 표시
- 설정 저장
- 수동 실행
- 모니터링 시작
- 모니터링 종료
- 모니터링/스케줄러 상태 요약

그 아래 또는 탭 내부에 배치할 것:
- crawler config 목록
- 항목별 선택 여부
- 항목별 실행 주기/cron
- 최근 실행 상태
- 다음 실행 또는 scheduler 기준 상태
- output 경로
- 검색어/필터 개수
- 스케줄 등록 여부

UI 기준:
- landing page처럼 만들지 말고 운영 도구 화면처럼 구성하라.
- 기존 디자인 스타일을 최대한 유지하라.
- 테이블 줄이 끊겨 보이거나 input 때문에 행 높이가 깨지지 않게 하라.
- 버튼과 설정 영역이 아래로 밀려 있어 운영자가 찾기 어렵지 않게 하라.
- 브라우저에서 직접 확인하고 screenshot 또는 QA artifact를 남겨라.

요구사항 5. 설정 LIST 화면과 스케줄/결과 화면 구성

오케스트레이션 페이지를 정보 성격에 따라 2개 화면 또는 2개 탭으로 분리하라.

가능하면 탭으로 구성하라.

탭 또는 화면 구성:

1. `설정 LIST` 또는 `배치 config`
   - 등록된 crawler config 목록 표시
   - 선택 여부 표시
   - 실행 주기/cron 표시
   - 검색어 수 표시
   - 필터 수 표시
   - output 경로 표시
   - 스케줄 등록 여부 표시
     - 예: 등록됨 / 미등록 / 비활성 / 오류
   - 최근 실행 상태 요약 표시

2. `등록된 스케줄 / 스케줄 결과 보기`
   - 등록된 스케줄과 스케줄 실행 결과를 같은 화면 안에 함께 표시해야 한다.
   - 이 둘을 별도 탭이나 별도 페이지로 나누지 마라.
   - 화면 안에서는 섹션을 나눠도 된다.

   포함할 내용:

   A. 등록된 스케줄 영역
   - 현재 Windows Task Scheduler에 등록된 managed task 목록 표시
   - task name
   - job id
   - config name
   - cron 또는 schedule
   - registered_at
   - status
   - last run
   - next run
   - last result
   - task action path 가능하면 표시
   - 모니터링 종료 후 갱신되어야 함

   B. 스케줄 결과 보기 영역
   - 최근 batch/job 실행 이력 표시
   - 성공/실패/중복중단/스킵 카운트
   - 실패 사유
   - log file path 가능하면 표시
   - keyword mail notification 결과
   - dry-run/real-send 여부

운영자가 “설정할 항목 목록”과 “현재 등록된 스케줄 및 실행 결과”를 명확히 구분할 수 있어야 한다.

즉, 최종 구조는 다음 중 하나여야 한다.

- 탭 1: 설정 LIST / 배치 config
- 탭 2: 등록된 스케줄 + 스케줄 결과 보기


요구사항 6. 성공/실패 로그 상세화

크롤링은 성공 로그와 실패 로그가 중요하다.

해야 할 일:
- 실패 시 사람이 확인할 수 있는 상세 메시지를 남겨라.
- 최소 포함:
  - config name
  - job id
  - config path
  - stage 또는 실행 단계
  - exception type
  - exception message
  - 가능하면 URL 또는 현재 step name
- scheduled runner 로그에 최소 아래를 남겨라:
  - batch id
  - job id
  - config name
  - started_at
  - finished_at
  - status
  - item count
  - duplicate stopped 여부
  - error summary
  - log file path
- UI 최근 실행 결과에도 실패 사유가 너무 짧게 잘리지 않게 표시하라.
- JSON history에도 error metadata를 남겨라.
- 단, secret, SMTP_PASSWORD, API key, token은 절대 로그에 출력하지 마라.

요구사항 7. prompt.md와 Git Push Change Log

이번 프롬프트부터 반드시 `prompt.md`에 저장하라.

push 전:
- Git Push Change Log 스킬을 사용하라.
- push record는 `docs/push-history/` 아래 Markdown으로 남겨라.
- push record에 반드시 포함:
  - Cumulative Prompt / Request Flow
  - 이번 수정의 원본 프롬프트 전문
  - 왜 수정했는지
  - 어떤 파일을 수정했는지
  - 설계 판단
  - 보류한 대안
  - 검증 결과
  - 남은 리스크
- secret이 포함된 프롬프트는 redaction 후 저장/기록하라.

검증 요구사항:

자동 테스트:
- web route 테스트
  - 설정 저장은 scheduler sync와 run을 호출하지 않음
  - 수동 실행은 run만 호출하고 scheduler sync는 호출하지 않음
  - 모니터링 시작은 설정 검증 후 scheduler sync 호출
  - 모니터링 종료는 managed scheduler stop/delete 호출
  - invalid 설정이면 저장/sync 하지 않음
- scheduler 테스트
  - managed task name namespace 검증
  - stop ps1 또는 stop logic이 이 프로젝트 task만 대상으로 하는지 검증
  - delete option 동작 검증
  - 다른 namespace task는 건드리지 않음
- scheduled runner 테스트
  - 페이지 없이 settings를 읽어 실행
  - disabled job은 실행하지 않음
  - saved allow_email_send 설정을 사용
- logging 테스트
  - 실패 결과에 config/job/path/stage/exception 정보 포함

실제 또는 준실제 테스트:
- 로컬 웹 UI 실행
- 브라우저에서 오케스트레이션 페이지 확인
- 설정 저장, 수동 실행, 모니터링 시작, 모니터링 종료 버튼 존재 확인
- 설정 LIST / 등록된 스케줄 / 스케줄 결과 보기 화면 또는 탭 확인
- 가능하면 Windows Task Scheduler create/query/end/delete smoke test 수행
- smoke test task는 반드시 테스트 후 삭제하라
- 실제 Gmail 발송은 사용자 명시 승인 없이는 하지 마라

최종 보고 형식:
1. 수정한 파일 목록
2. 각 요구사항별 수정 내용
3. 설정 저장/수동 실행/모니터링 시작/모니터링 종료 동작 차이
4. 추가한 종료 ps1 사용법
5. 백그라운드 실행 구조
6. 설정 LIST / 등록된 스케줄 / 스케줄 결과 보기 구성
7. 성공/실패 로그 개선 내용
8. prompt.md 저장 여부와 경로
9. 테스트 결과
10. 브라우저/UI 검수 결과
11. git push 여부
12. push record 경로
13. 남은 리스크

주의:
- `.env`, Gmail 앱 비밀번호, SMTP_PASSWORD, NAVER_CLIENT_SECRET, KAKAO_REST_API_KEY 등 secret은 절대 커밋하지 마라.
- push 전 staged diff에서 secret이 없는지 반드시 확인하라.
- `git add .` 사용 금지. 수정한 파일만 선택적으로 stage하라.
- main/master에 push하지 마라.

---

## Prompt Record Index - 2026-05-19 14:39 KST

- title: Orchestration Tabs And Monitoring Stop Follow-up
- full prompt: `prompts/20260519_143900_orchestration_tabs_stop_followup.md`
- note: Prompt history is now cumulative. `prompt.md` keeps the prior full prompt plus this index entry; new full prompts are stored under `prompts/` without overwriting previous prompt records.

```

### Prompt 2: prompts/20260519_143900_orchestration_tabs_stop_followup.md 저장 원문

```text
# Prompt Record - 2026-05-19 14:39 KST - Orchestration Tabs And Monitoring Stop Follow-up

너는 기존 크롤링 오케스트레이션 수정 결과물을 다시 점검하고, 아래 테스트에서 발견된 미반영/오동작 사항을 수정해야 한다.

작업 경로:
C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp

대상 프로젝트:
- 기존 JSON config 기반 크롤러
- 사이트별 크롤러 소스코드를 새로 늘리지 말 것
- 기존 configs/*.json, workflow_records.json, outputs, runtime, orchestration_state 구조를 최대한 활용할 것
- 변경은 공통 orchestration/web/scheduler/script/UI 계층에 한정할 것

중요:
- 이번 사용자 프롬프트도 즉시 prompt 기록 파일에 저장하라.
- 단, 기존 prompt 기록을 덮어쓰지 말고 반드시 누적 구조로 저장하라.
- 예:
  - `prompt.md`에 날짜/시간/작업 제목별 섹션을 append
  - 또는 `prompts/YYYYMMDD_HHMMSS_<topic>.md`처럼 개별 파일로 누적 저장
- Git Push Change Log 스킬을 이용해 push할 때, 어떤 프롬프트 내용에 의해 수정이 진행되었는지 push record에 반드시 정리하라.
- 이때 이번 프롬프트 전문도 포함하라.
- secret이 포함된 프롬프트는 `[REDACTED_SECRET]`로 마스킹하라.
- `.env`, Gmail 앱 비밀번호, SMTP_PASSWORD, NAVER_CLIENT_SECRET, KAKAO_REST_API_KEY 등 secret은 절대 prompt 기록, README, push record, 로그, 커밋에 넣지 마라.

먼저 해야 할 일:
1. 이번 프롬프트 전문을 누적형 prompt 기록에 저장하라.
2. 현재 구현 상태를 확인하라.
3. 수정 전 pre-edit gate를 아래 형식으로 보고하라.
4. 그 다음 구현하라.

pre-edit gate 형식:

- classification: non-trivial
- reason
- source-code change needed: yes/no
- source-code change scope
- files likely to change
- validation plan
- risks

먼저 확인할 파일:
- README.md
- prompt.md 또는 prompts/ 하위 prompt 기록 파일
- crawler_app/orchestration.py
- crawler_app/web.py
- crawler_app/windows_scheduler.py 또는 scheduler 관련 파일
- crawler_app/scheduled_runner.py
- scripts/Run-OrchestrationJob.ps1
- scripts/Stop-OrchestrationJobs.ps1
- templates/orchestration.html 또는 오케스트레이션 UI 템플릿
- static/*.css
- orchestration_state/settings.json 구조
- orchestration_state/scheduler_registry.json 구조
- runtime/scheduled-task/ 로그 구조
- tests 하위 orchestration/scheduler/web 관련 테스트
- .gitignore

수정 요청 1. 버튼식 페이지 이동이 아니라 실제 탭 UI로 구성

현재 “탭으로 구성” 요청을 했더니 각 화면으로 가는 버튼이 생기고 페이지 내 anchor 이동만 하는 구조가 되었다.

원하는 동작:
- 같은 페이지, 같은 공간 안에서 탭으로 화면이 전환되어야 한다.
- 단순 anchor link나 페이지 내 이동 버튼이 아니라 실제 tab UI여야 한다.
- 예:
  - 탭 1: `설정 LIST / 배치 config`
  - 탭 2: `등록된 스케줄 / 스케줄 결과 보기`
- 탭을 클릭하면 같은 위치의 content panel이 바뀌어야 한다.
- URL hash를 사용해도 되지만, UI는 탭처럼 보여야 한다.
- 접근성 가능하면 고려:
  - `role="tablist"`
  - `role="tab"`
  - `role="tabpanel"`
  - selected/active 상태 표시
- 브라우저에서 직접 확인하라.
- 테스트 또는 QA artifact에 탭 전환 전/후 상태를 남겨라.

수정 요청 2. 등록된 스케줄 화면의 비정상 시간/Last Result 표시 정리

등록된 스케줄 / 스케줄 결과 보기 화면에서 새로 만든 스케줄러의 최근 실행 시간이 다음처럼 터무니없는 값으로 표시된다.

예:
- `11/30/1999 00:00:00`

이 값은 사용자가 보기에는 잘못된 정보이므로 표시하지 말아야 한다.

수정 기준:
- Windows Task Scheduler가 아직 실행되지 않은 task에 대해 반환하는 sentinel/default date는 UI에 그대로 표시하지 마라.
- `11/30/1999 00:00:00`, `1899`, `0001`, `N/A`, 빈 문자열 등 “실제 실행 시간 아님”으로 판단되는 값은 `-` 또는 빈 칸으로 표시하라.
- Last Result에 `267011` 같은 숫자가 표시되는데, 사용자가 의미를 알 수 없다.
- Last Result가 성공/실패를 적는 란이라면 다음처럼 표시하라.
  - 아직 실행 안 됨: 빈 칸 또는 `-`
  - 성공: `성공`
  - 실패: `실패`
  - 그 외 코드가 있다면 코드만 던지지 말고 `실패(코드: 267011)`처럼 의미를 붙여라.
- Last Result가 실제로 Windows Task Scheduler result code라면, 최소한 자주 나오는 값에 대해 사람이 읽을 수 있는 label을 붙여라.
- UI에는 raw code를 그대로 노출하지 말고, 필요하면 tooltip이나 상세 영역에만 보조 정보로 보여줘라.
- 테스트에 sentinel last_run_time과 raw last_result code normalization 케이스를 추가하라.

수정 요청 3. 모니터링 종료 버튼이 Stop-OrchestrationJobs.ps1과 실제로 연동되는지 확인 및 보장

모니터링 종료 버튼이 확실하게 `scripts\Run-OrchestrationJob.ps1`의 동작과 반대되는 정지/종료 동작을 수행하는지 확인이 필요하다.

확인/수정 기준:
- `모니터링 시작`은 scheduler task를 생성하고 `scripts\Run-OrchestrationJob.ps1`를 통해 백그라운드 실행을 등록하는 역할이다.
- `모니터링 종료`는 이 프로젝트가 관리하는 scheduler task의 실행을 멈추는 역할이어야 한다.
- `모니터링 종료` 버튼이 실제로 `scripts\Stop-OrchestrationJobs.ps1` 또는 그와 동일한 공통 stop 로직을 호출하도록 하라.
- web route가 scheduler stop logic을 직접 구현하고 ps1과 따로 놀면 안 된다.
- stop ps1과 web route가 같은 core logic을 공유하거나, web route가 ps1을 명확히 호출해야 한다.
- 이 동작을 테스트로 증명하라.
- 테스트에는 다음이 포함되어야 한다.
  - 모니터링 종료 route 호출 시 Stop-OrchestrationJobs.ps1 또는 공통 stop command 호출
  - 이 프로젝트 namespace의 task만 대상으로 함
  - 다른 namespace task는 건드리지 않음

수정 요청 4. 모니터링 종료 후 스케줄러 상태와 재시작 구조 확인

현재 모니터링 종료 버튼을 눌러도 등록된 스케줄은 삭제되지 않는 것으로 보인다.

확인해야 할 동작:
- 모니터링 종료의 의도는 최소한 “스케줄러 실행이 멈추는 것”이다.
- 스케줄러 task를 삭제하지 않더라도 disabled/end 상태가 되어 실제 주기 실행이 다시 발생하지 않아야 한다.
- 만약 task를 삭제하지 않는 구조라면:
  - 다시 `모니터링 시작`을 눌렀을 때 정상적으로 재활성화/재생성되어야 한다.
  - JSON settings에 남아있는 스케줄 설정을 기준으로 다시 작동해야 한다.
- 만약 task를 삭제하는 구조라면:
  - registry JSON 또는 scheduler_registry.json의 등록 정보도 일관되게 갱신되어야 한다.
  - UI에서 등록된 스케줄이 제거되었거나 비활성 상태로 표시되어야 한다.
- 현재 “모니터링 종료를 눌렀는데도 오케스트레이션에서 설정했던 스케줄러가 계속 동작하는 것 같다”는 문제가 있다.
- 따라서 반드시 실제 Windows Task Scheduler 상태 기준으로 다음을 확인하라.
  - 종료 전 task 존재/상태
  - 종료 직후 task 상태 또는 삭제 여부
  - 다음 주기에 실제 실행되는지 여부
  - 다시 모니터링 시작 후 정상 재등록/재실행 가능 여부
- 테스트 가능한 범위:
  - fake command runner 기반 unit test
  - 실제 Windows schtasks smoke test
- smoke test를 할 경우 테스트용 task는 반드시 삭제하라.
- outputs나 workflow_records.json은 모니터링 종료로 삭제하면 안 된다.

수정 요청 5. 모니터링 종료를 눌렀는데도 스케줄러가 계속 동작하는 문제 해결

이 문제는 반드시 수정해야 한다.

요구 동작:
- `모니터링 종료`를 누르면 이 프로젝트가 관리하는 모든 오케스트레이션 scheduler task가 더 이상 주기적으로 실행되지 않아야 한다.
- task를 삭제하지 않는다면 disable/end 해야 한다.
- task를 삭제한다면 registry/UI도 삭제 상태를 반영해야 한다.
- “종료”라는 버튼명이면 사용자는 이후 크롤링이 자동 실행되지 않는다고 기대한다.
- 따라서 종료 후에도 scheduled task가 다음 주기에 실행되는 상태는 실패로 간주한다.
- 구현 후 실제 또는 fake test로 다음을 증명하라.
  - stop 호출 전 enabled task 존재
  - stop 호출 후 다음 run이 발생하지 않는 상태
  - UI에 종료/비활성/삭제 상태 표시
  - monitoring start를 다시 누르면 settings 기준으로 정상 재생성

수정 요청 6. prompt 기록은 갱신이 아니라 누적 구조로 변경

현재 프롬프트 저장이 누적이 아니라 갱신 구조로 보인다.

문제:
- 앞으로도 계속 수정/보완 작업이 진행될 텐데, prompt.md가 매번 덮어쓰기라면 git push 전에 어떤 프롬프트로 어떤 수정이 진행됐는지 잊어버릴 수 있다.

수정 기준:
- prompt 기록은 반드시 누적 구조여야 한다.
- 선택 가능한 방식:
  1. `prompt.md`에 append
     - 각 요청마다 날짜/시간, 제목, 원문 프롬프트를 섹션으로 추가
  2. `prompts/` 디렉터리 아래 요청별 파일 생성
     - 예: `prompts/20260519_001500_monitoring_stop_tabs.md`
  3. 둘 다 사용
     - `prompt.md`는 index/summary
     - `prompts/*.md`는 원문 전문
- Git Push Change Log 작성 시, 이번 작업과 관련된 prompt 원문 전문을 push record에 포함하라.
- 이전 prompt 기록을 삭제하거나 덮어쓰지 마라.
- secret이 포함된 prompt는 redaction하라.
- prompt 기록 방식에 대한 테스트 또는 최소한 파일 존재/append 확인을 수행하라.

검증 요구사항:

자동 테스트:
- tab UI 렌더링 테스트
  - tablist/tab/tabpanel 또는 동등한 active panel 구조 확인
- scheduler display normalization 테스트
  - `11/30/1999 00:00:00` → `-`
  - unknown raw last result code → `실패(코드: N)` 또는 사람이 읽을 수 있는 문구
  - never-run task → 빈 칸 또는 `-`
- monitoring stop route 테스트
  - stop ps1 또는 공통 stop logic 호출 확인
  - managed namespace만 대상
  - 다른 namespace는 대상 아님
- monitoring stop/start lifecycle 테스트
  - stop 후 task가 실행되지 않는 상태로 바뀜
  - start 후 settings 기준으로 재생성/재활성화
- prompt 기록 테스트 또는 확인
  - 기존 prompt 기록이 덮어써지지 않고 새 요청이 append/create 됨

실제 또는 준실제 테스트:
- 로컬 웹 UI 실행
- 브라우저에서 오케스트레이션 페이지 확인
- 탭 1과 탭 2가 같은 공간에서 전환되는지 확인
- 등록된 스케줄 / 스케줄 결과 보기 화면에서 sentinel 시간과 raw result code가 정리되어 보이는지 확인
- 모니터링 시작 후 scheduler task 생성 확인
- 모니터링 종료 후 scheduler task가 삭제/비활성/중단되어 다음 주기 실행이 발생하지 않는 상태인지 확인
- 다시 모니터링 시작 후 정상 재등록되는지 확인
- 실제 Gmail 발송은 사용자 명시 승인 없이는 하지 마라

최종 보고 형식:
1. 수정한 파일 목록
2. 각 수정 요청별 반영 내용
3. 탭 UI가 버튼식 anchor 이동이 아니라 실제 탭 구조임을 확인한 증거
4. Last Run / Last Result 표시 정리 방식
5. 모니터링 종료 버튼이 어떤 로직/ps1과 연결되는지
6. 모니터링 종료 후 scheduler task 상태
7. 모니터링 시작 재실행 가능 여부
8. prompt 누적 저장 방식과 저장 경로
9. 테스트 결과
10. 브라우저/UI 검수 결과
11. git push 여부
12. push record 경로
13. 남은 리스크

주의:
- `.env`, Gmail 앱 비밀번호, SMTP_PASSWORD, NAVER_CLIENT_SECRET, KAKAO_REST_API_KEY 등 secret은 절대 커밋하지 마라.
- push 전 staged diff에서 secret이 없는지 반드시 확인하라.
- `git add .` 사용 금지. 수정한 파일만 선택적으로 stage하라.
- main/master에 push하지 마라.

```
