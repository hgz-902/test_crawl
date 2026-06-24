# Prompt Record - Orchestration Button Lifecycle

- Recorded at: 2026-05-19 17:32:36 KST
- Scope: settings save / monitoring start / monitoring stop lifecycle alignment

## Original Prompt

너는 기존 크롤링 오케스트레이션 수정 결과물을 다시 점검하고, 아래 테스트에서 발견된 설정 저장/모니터링 시작/모니터링 종료 동작 불일치를 수정해야 한다.

작업 경로:
C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp

대상 프로젝트:
- 기존 JSON config 기반 크롤러
- 기존 configs/*.json, workflow_records.json, outputs, runtime, orchestration_state 구조를 최대한 활용할 것
- 사이트별 크롤러 소스코드를 새로 늘리지 말 것
- 변경은 가능한 한 orchestration/web/scheduler/script/UI 계층에 한정할 것

중요:
- 이번 사용자 프롬프트도 즉시 prompt 기록 파일에 저장하라.
- 기존 prompt 기록을 덮어쓰지 말고 반드시 누적 구조로 저장하라.
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
- tests 하위 orchestration/scheduler/web 관련 테스트
- .gitignore

수정 요청. 설정 저장 / 모니터링 시작 / 모니터링 종료의 책임을 명확히 분리

현재 오케스트레이션 페이지에서 세 버튼의 역할이 헷갈리거나, 실제 동작이 의도와 다르게 보인다.

원하는 정확한 동작은 아래와 같다.

## 1. 설정 저장

`설정 저장` 버튼을 누르면 말 그대로 JSON 파일에 설정만 저장되어야 한다.

필수 동작:
- 현재 UI에 입력된 항목 선택 여부, cron/실행 주기, 키워드, 메일 수신자, 발신자, 메일 발송 허용 여부 등 설정을 JSON 파일에 저장한다.
- 예: `orchestration_state/settings.json`
- Windows Task Scheduler를 생성하지 않는다.
- Windows Task Scheduler를 수정하지 않는다.
- Windows Task Scheduler를 삭제하지 않는다.
- 크롤링을 실행하지 않는다.
- scheduled runner를 실행하지 않는다.
- scheduler registry를 실제 scheduler 상태처럼 바꾸면 안 된다.
- 기존에 이미 떠 있는 scheduler를 건드리지 않는다.

즉, 설정 저장은 “desired settings 저장”만 해야 한다.

## 2. 모니터링 시작

`모니터링 시작` 버튼을 누르면, 이미 저장된 설정 또는 현재 UI에서 저장된 설정을 기준으로 scheduler가 실행되어야 한다.

필수 동작:
- 현재 UI 설정을 먼저 JSON settings에 저장하거나, 이미 저장된 settings를 명확히 사용하라.
- 그 settings 기준으로 Windows Task Scheduler 작업을 생성/재생성/활성화하라.
- enabled로 선택된 crawler config만 scheduler에 등록되어야 한다.
- 각 scheduler task는 저장된 cron/실행 주기를 사용해야 한다.
- scheduler task는 `scripts/Run-OrchestrationJob.ps1` 또는 scheduled runner를 통해 페이지와 독립적으로 실행되어야 한다.
- 페이지를 닫아도 task는 정상 동작해야 한다.
- scheduler registry는 실제 생성된 task 상태와 일관되게 갱신되어야 한다.
- 모니터링 시작 후 UI에는 등록된 scheduler 목록이 보여야 한다.

주의:
- 모니터링 시작 전에 설정 검증을 하라.
- invalid cron 또는 invalid config가 있으면 settings 저장/scheduler 생성 여부를 명확히 정하고, 오류 메시지를 보여줘라.
- 다른 project/clone의 scheduler는 절대 건드리지 마라.
- managed task namespace 또는 prefix를 사용하라.

## 3. 모니터링 종료

`모니터링 종료` 버튼을 누르면 저장된 설정은 유지한 채 scheduler만 모두 종료되어야 한다.

필수 동작:
- `orchestration_state/settings.json`의 설정은 유지되어야 한다.
- 사용자가 저장한 enabled jobs, cron, keywords, recipients, sender 등은 삭제되면 안 된다.
- outputs, workflow_records.json, runtime history도 삭제하면 안 된다.
- 이 프로젝트가 관리하는 scheduler task만 종료해야 한다.
- scheduler task가 더 이상 주기적으로 실행되지 않아야 한다.
- 종료 방식은 아래 중 하나로 명확히 선택하라.
  - task를 disable/end 한다.
  - 또는 task를 delete 한다.
- 어떤 방식을 선택하든 UI와 registry는 실제 상태와 일치해야 한다.
- 만약 task를 delete한다면:
  - scheduler_registry.json에서는 해당 task가 제거되거나 stopped/deleted 상태로 표시되어야 한다.
  - settings.json은 그대로 유지되어야 한다.
- 만약 task를 disable한다면:
  - scheduler_registry.json과 UI에 disabled/stopped 상태가 표시되어야 한다.
  - 다시 모니터링 시작 시 enable/recreate 되어야 한다.
- `scripts/Stop-OrchestrationJobs.ps1`가 있다면 이 스크립트 또는 동일한 공통 stop 로직과 확실히 연결되어야 한다.
- stop route와 ps1이 서로 다른 기준으로 동작하면 안 된다.
- 모니터링 종료 후에도 scheduler가 다음 주기에 실행되는 상태는 실패로 간주한다.

## 4. 모니터링 종료 후 다시 모니터링 시작

모니터링 종료 후에도 저장된 settings는 남아 있어야 한다.

그 상태에서 다시 `모니터링 시작` 버튼을 누르면:
- 저장된 settings 기준으로 scheduler task가 다시 생성/활성화되어야 한다.
- 사용자가 다시 항목을 처음부터 설정하지 않아도 되어야 한다.
- enabled jobs와 cron 설정이 그대로 반영되어야 한다.
- UI는 다시 등록된 scheduler 목록을 보여야 한다.

즉, 정상 lifecycle은 아래와 같아야 한다.

1. 설정 저장
   - settings.json 저장
   - scheduler 변화 없음

2. 모니터링 시작
   - settings.json 기준 scheduler 생성/활성화
   - registry/UI 갱신

3. 모니터링 종료
   - settings.json 유지
   - scheduler 종료/삭제/비활성화
   - registry/UI 갱신

4. 모니터링 시작
   - 기존 settings.json 기준 scheduler 재생성/재활성화
   - registry/UI 갱신

검증 요구사항:

자동 테스트:
- 설정 저장 route 테스트
  - settings 저장됨
  - scheduler sync/stop/delete 호출 안 됨
  - run_batch 호출 안 됨
- 모니터링 시작 route 테스트
  - settings 기준 scheduler sync 호출
  - enabled job만 등록
  - registry 갱신
- 모니터링 종료 route 테스트
  - settings.json 내용은 유지
  - scheduler stop/delete/disable 호출
  - outputs/workflow_records/history 삭제 안 됨
  - registry/UI 상태 갱신
- 모니터링 종료 후 재시작 테스트
  - 같은 settings 기준으로 scheduler가 다시 생성/활성화됨
- `scripts/Stop-OrchestrationJobs.ps1` 또는 공통 stop logic 테스트
  - 이 프로젝트 namespace task만 대상으로 함
  - 다른 namespace task는 건드리지 않음

실제 또는 준실제 테스트:
- 로컬 웹 UI 실행
- settings.json을 확인하면서 테스트
- 설정 저장 클릭 후:
  - settings.json 변경 확인
  - scheduler task가 생성/삭제/변경되지 않았는지 확인
- 모니터링 시작 클릭 후:
  - scheduler task 생성 확인
  - registry/UI 표시 확인
- 모니터링 종료 클릭 후:
  - settings.json 유지 확인
  - scheduler task가 삭제/비활성/중단되었는지 확인
  - 다음 주기 실행이 발생하지 않는 상태인지 확인
- 다시 모니터링 시작 클릭 후:
  - 같은 settings 기준으로 scheduler task가 다시 생성/활성화되는지 확인
- smoke test task는 반드시 테스트 후 정리하라.
- 실제 Gmail 발송은 사용자 명시 승인 없이는 하지 마라.

최종 보고 형식:
1. 수정한 파일 목록
2. 설정 저장 동작
3. 모니터링 시작 동작
4. 모니터링 종료 동작
5. 모니터링 종료 후 재시작 동작
6. settings.json 유지 여부
7. scheduler_registry.json 갱신 방식
8. Stop-OrchestrationJobs.ps1 또는 stop logic 연결 방식
9. 테스트 결과
10. 실제 또는 준실제 scheduler lifecycle 검증 결과
11. prompt 누적 저장 경로
12. git push 여부
13. push record 경로
14. 남은 리스크

주의:
- `.env`, Gmail 앱 비밀번호, SMTP_PASSWORD, NAVER_CLIENT_SECRET, KAKAO_REST_API_KEY 등 secret은 절대 커밋하지 마라.
- push 전 staged diff에서 secret이 없는지 반드시 확인하라.
- `git add .` 사용 금지. 수정한 파일만 선택적으로 stage하라.
- main/master에 push하지 마라.
