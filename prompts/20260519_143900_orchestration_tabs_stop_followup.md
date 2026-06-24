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
