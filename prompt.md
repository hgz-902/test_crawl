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
