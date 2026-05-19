# Git Push Change Log - 오케스트레이션 cron 스케줄러와 중복 처리 안정화

- Date: 2026-05-19 13:35:42 +09:00
- Repository: C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp
- Branch: dev/crawler-current
- Upstream: origin/dev/crawler-current
- Commit message: 오케스트레이션 cron 스케줄러와 중복 처리 안정화
- Approved push target: origin dev/crawler-current -> dev/crawler-current

## Request

오케스트레이션 UI를 cron 기반 스케줄 설정으로 바꾸고, Windows Task Scheduler 동기화/삭제/표시 흐름, workflow_records 중복 처리, filter/nonfilter 산출물 cleanup, POST-Redirect-GET 사용자 흐름을 안정화했다.

## Changed Files

~~~text
 M README.md
 M configs/구글.json
 M configs/기후에너지부_보도자료.json
 M configs/네이버.json
 M configs/다음.json
 M configs/마켓인사이트.json
 M configs/산업부_보도자료.json
 M configs/시그널.json
 M configs/인베스트조선.json
 M crawler_app/orchestration.py
 M crawler_app/scheduled_runner.py
 M crawler_app/web.py
 M crawler_app/windows_scheduler.py
 M crawler_app/workflow.py
 M static/styles.css
 M templates/orchestration.html
 M tests/test_orchestration.py
 M tests/test_web.py
 M tests/test_windows_scheduler.py
 M tests/test_workflow.py
?? tests/test_scheduled_runner.py
?? docs/push-history/20260519_133542_dev-crawler-current_오케스트레이션-cron-스케줄러와-중복-처리-안정화.md
~~~

## Diff Stat

~~~text
 README.md                          |  28 ++-
 configs/구글.json                  |  30 ++-
 configs/기후에너지부_보도자료.json |   4 +-
 configs/네이버.json                |   9 +-
 configs/다음.json                  |  74 ++++++-
 configs/마켓인사이트.json          |  14 +-
 configs/산업부_보도자료.json       |   4 +-
 configs/시그널.json                |  14 +-
 configs/인베스트조선.json          |  14 +-
 crawler_app/orchestration.py       | 144 ++++++++++++-
 crawler_app/scheduled_runner.py    |   9 +-
 crawler_app/web.py                 | 265 ++++++++++++++++-------
 crawler_app/windows_scheduler.py   | 184 +++++++++++++++-
 crawler_app/workflow.py            | 375 +++++++++++++++++++-------------
 static/styles.css                  |  15 ++
 templates/orchestration.html       | 223 ++++++++++---------
 tests/test_orchestration.py        |  44 ++++
 tests/test_web.py                  | 430 +++++++++++++++++++++++++++++++------
 tests/test_windows_scheduler.py    |  93 ++++++--
 tests/test_workflow.py             | 148 +++++++++++++
 20 files changed, 1653 insertions(+), 468 deletions(-)
warning: in the working copy of 'README.md', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'crawler_app/orchestration.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'crawler_app/web.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'crawler_app/windows_scheduler.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'crawler_app/workflow.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'templates/orchestration.html', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/test_orchestration.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/test_web.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/test_windows_scheduler.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/test_workflow.py', LF will be replaced by CRLF the next time Git touches it
~~~

## Staged Diff Stat

~~~text

~~~

## Why These Changes Were Made

운영자는 여러 크롤링 항목을 각각 다른 주기로 관리해야 하며, 개발팀은 Linux crontab처럼 명확한 주기 표현과 사람이 확인 가능한 성공/실패 로그를 요구했다. 기존 분/시간/일 interval 입력은 세밀한 일정 표현이 부족했고, Windows Task Scheduler와 앱 내부 상태가 서로 다른 기준으로 다음 실행 시간을 다루면 실제 운영 시 혼동이 생겼다.

또한 기존 workflow_records 기반 중복 처리는 "이전 실행에서 이미 본 기사"와 "같은 실행 안에서 검색어가 겹쳐 다시 나온 기사"를 충분히 분리하지 못했다. 운영 의도는 기존 기록과 중복되면 현재 검색어만 멈추고 다음 검색어/다음 크롤러는 계속 진행하는 것이므로, 중복 판정 범위와 stop 범위를 명확히 해야 했다.

산출물도 filter/nonfilter 최종 결과만 남아야 운영자가 확인하기 쉽다. 기존 root 임시 디렉터리가 남으면 개발팀이 경로/형식 변경에 민감해하는 상황에서 실제 결과물의 기준이 흐려진다. 그래서 이번 실행에서 생성한 파일만 추적해 정리하고, 사람이 둔 파일이나 최종 workflow_records는 보존하는 방향으로 구현했다.

마지막으로 오케스트레이션 페이지에서 POST 결과를 바로 HTML로 반환하면 F5 새로고침 때 브라우저의 "양식 다시 제출 확인"이 뜬다. 사용자가 보기에는 불필요한 팝업이므로 POST-Redirect-GET 패턴으로 바꿔 저장/삭제 후 최종 URL을 항상 `/orchestration`에 두도록 했다.

## Design Notes And Tradeoffs

기존 분/시간/일 interval UI는 운영팀이 원하는 crontab형 표현을 담기 어렵고, Windows Scheduler와 앱 상태가 같은 파일을 동시에 쓰는 문제가 있었다. 사이트별 크롤러 코드는 유지하고 공통 workflow/orchestration/scheduler 계층에서 해결했다.

### Existing Code Changed Because

공통 workflow/orchestration/scheduler 계층에서 해결해야 하는 요구였다. 사이트별 크롤러 소스코드를 늘리면 이후 사이트가 많아질수록 개발팀이 원한 "설정과 XPath/파라미터 중심 운영"에서 멀어진다. 따라서 사이트별 crawler 구현은 건드리지 않고, 설정 저장/스케줄링/중복 판정/산출물 정리/웹 응답 흐름만 수정했다.

### Idea Or Constraint Behind The Change

핵심 아이디어는 "각 크롤러 config는 그대로 실행하되, 운영 계층이 실행 주기와 중복 기준, 결과 정리를 책임진다"는 것이다. 이전 실행 duplicate index와 현재 실행 seen set을 분리하고, Windows 스케줄러는 이 clone의 namespace 아래 작업만 관리한다. 웹 UI는 저장 후 직접 HTML을 반환하지 않고 flash state를 남긴 뒤 GET 화면으로 돌아온다.

### Advantages

- 운영자가 `*/5 * * * *`, `0 3 * * *` 같은 익숙한 cron 문자열로 주기를 입력할 수 있다.
- Windows Task Scheduler에는 프로젝트 namespace별 작업이 생성되어 다른 clone이나 다른 프로젝트 작업을 덜 건드린다.
- 이전 실행 중복은 현재 검색어만 멈추고, 같은 실행 안 중복은 skip만 하므로 배치 전체가 불필요하게 중단되지 않는다.
- filter/nonfilter 밖의 실행 임시 산출물이 정리되어 실제 확인해야 할 결과 경로가 단순해진다.
- POST-Redirect-GET으로 저장/삭제 후 F5 새로고침이 같은 작업을 반복하지 않는다.
- schtasks 출력 인코딩을 Windows ANSI locale로 읽어 한글 오류 메시지 mojibake를 줄인다.

### Disadvantages Or Costs

- cron 전체 문법을 모두 지원하지 않는다. Windows Task Scheduler로 안전하게 바꿀 수 있는 subset만 허용한다.
- flash 메시지 처리를 위해 `orchestration_state/flash` 임시 파일과 쿠키를 사용한다. 이 폴더는 로컬 runtime state라 git에는 포함하지 않는다.
- 각 항목별 Windows 스케줄러가 동시에 실행될 수 있으므로, 같은 항목은 lock으로 보호하지만 서로 다른 사이트 간 네트워크 부하는 운영 설정으로 조절해야 한다.
- 정부 사이트 계열은 headless/네트워크 reset 영향을 계속 받을 수 있다.

### Alternatives Considered Or Deferred

- 기존 interval UI 유지: 개발팀 요구인 crontab식 주기 표현과 맞지 않아 배제했다.
- cron 전체 문법 구현: Windows Task Scheduler 변환 안정성이 떨어져 deferred 처리했다.
- POST 후 HTML 직접 반환 유지: F5 재제출 팝업이 사용자 경험을 해치므로 배제했다.
- URL query에 메시지 표시: URL이 지저분해지고 메시지가 남아 refresh 때 반복될 수 있어 flash 파일/쿠키 방식으로 바꿨다.
- 사이트별 crawler 코드 수정: 현재 요구는 공통 orchestration/workflow 계층 문제라 사이트별 코드 변경 없이 처리했다.

### Collection Or Runtime Structure Notes

- 설정은 `orchestration_state/settings.json`, 항목별 상태는 `orchestration_state/jobs/<job_id>.json`, 스케줄러 등록 표시용 registry는 `orchestration_state/scheduler_registry.json`에 남는다. 이들은 모두 로컬 runtime state로 git ignore 대상이다.
- Windows 작업은 `\CrawlerOrchestration\<project_namespace>\crawler_*` 아래 생성된다.
- 예약 실행은 `scripts/Run-OrchestrationJob.ps1`을 통해 `.venv` Python과 `.env` 값을 사용한다.
- 산출물은 최종적으로 `outputs/<crawler>/filter`와 필요한 경우 `outputs/<crawler>/nonfilter` 아래 남는다.
- `workflow_records.json`은 이전 실행 중복 판정의 기준이며, title+URL 계열 키를 우선 사용한다.

## Implementation Summary

오케스트레이션 UI를 cron 기반 스케줄 설정으로 바꾸고, Windows Task Scheduler 동기화/삭제/표시 흐름, workflow_records 중복 처리, filter/nonfilter 산출물 cleanup, POST-Redirect-GET 사용자 흐름을 안정화했다.

## Validation

python -m unittest discover -s tests => Ran 160 tests OK. 실제 /orchestration 라우트에서 설정 저장/삭제 POST가 303으로 /orchestration에 redirect되고 새로고침 시 메시지가 반복되지 않음을 확인. 실제 Windows Task Scheduler 생성/삭제 후 관리 스케줄러 0개 확인.

## Remaining Risks

정부 사이트 계열은 네트워크 reset 가능성이 남아 있으며, cron은 Windows Task Scheduler로 안전 변환 가능한 subset만 지원한다.

## Files Intentionally Excluded

- `.env`, `.env.*`: Gmail 앱 비밀번호, Naver/Kakao API key 등 secret 보관 파일. `.env.example`만 placeholder로 추적한다.
- `outputs/`: 실제 크롤링 결과물.
- `orchestration_state/`: 로컬 오케스트레이션 설정, scheduler registry, flash, job state.
- `qa-artifacts/`: 로컬 검증 결과.
- `runtime/`, `logs/`: Windows scheduled task 로그와 앱 로그.
- `.venv/`, `__pycache__/`, `.pytest_cache/`: 로컬 실행/캐시.
- 하네스 세션 문서: `TASK_CONTRACT.md`, `TASK_PLAN.md`, `RUN_CONTEXT.md`, `DECISION_RULING.md`, `GUI_QA_RESULT.md` 등.

## Remote

~~~text
origin	https://github.com/K-Ternag/crawlService.git (fetch)
origin	https://github.com/K-Ternag/crawlService.git (push)
~~~

## Push Command

~~~powershell
git push origin dev/crawler-current:dev/crawler-current
~~~

## Push Result

Pending at record creation time.

## 누적 프롬프트 / 변경 흐름 추가 기록

- 이전 원본 경로 재개 기준: 기존 crawler config와 원본형 실행 단계 구조를 최대한 보존하고, Naver/Daum/Google 같은 API/RSS형 예외만 별도 parser 경로로 인정했다. 이번 커밋은 이 기준을 유지하며 사이트별 crawler 소스가 아니라 공통 workflow/orchestration/scheduler 계층을 수정한다.
- 오케스트레이션 기능 요구: 선택한 크롤링 항목별 실행 주기, workflow_records 기반 중복 중단, 키워드 메일 알림, Windows 서버 운영 가능성을 고려한 스케줄링 UI가 필요했다. 구현 결과는 JSON settings + Windows Task Scheduler + per-job runtime state 구조다.
- 개발팀 스타일 반영: 소스 변경 이유와 tradeoff를 push record에 남기고, 크롤러별 설정/출력 구조 변화에 예민하게 대응한다. 이번 기록에는 왜 interval UI, 중복 처리, cleanup, PRG 흐름을 바꿨는지 함께 남긴다.
- cron 요구 반영: "몇 분마다" 대신 `0 3 * * *`, `*/5 * * * *` 같은 5필드 cron 입력으로 변경했다. Windows Scheduler로 안전 변환 가능한 subset만 허용하며, 불가능한 표현은 저장/동기화 전에 오류로 보여준다.
- 로그/실패 메시지 보완: scheduled runner와 orchestration failure에 config명, job_id, config path, exception type을 포함하도록 해 운영자가 어떤 항목이 왜 실패했는지 더 빨리 확인할 수 있게 했다.
- 중복 처리 보완: 이전 workflow_records와 중복되면 현재 검색어만 stop하고 다음 검색어/다음 항목은 계속한다. 같은 실행 안 중복은 skip만 한다.
- output cleanup 보완: filter/nonfilter 최종 결과만 남기고, 이번 실행에서 만든 root 임시 산출물은 cleanup한다. 사람이 직접 둔 파일과 최종 workflow_records는 삭제하지 않는다.
- 사용자 관점 UI 검증 반영: Codex가 만든 Windows 스케줄러를 사용자가 UI에서 삭제할 수 있어야 하며, 삭제 실패 메시지가 mojibake로 보이면 안 된다. 실제 UI save/delete 라우트로 생성/삭제를 검증했고, 최종 관리 스케줄러 0개를 확인했다.
- F5 재제출 팝업 제거: POST 결과 HTML 직접 반환을 POST-Redirect-GET으로 바꿔 저장/삭제 후 최종 URL을 `/orchestration`으로 유지하고, 새로고침 때 브라우저의 양식 재제출 경고가 뜨지 않게 했다.
