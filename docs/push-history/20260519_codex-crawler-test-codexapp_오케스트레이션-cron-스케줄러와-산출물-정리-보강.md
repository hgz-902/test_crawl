# 오케스트레이션 cron 스케줄러와 산출물 정리 보강

## 대상
- Repository: `https://github.com/hgz-902/test_crawl`
- Branch: `codex/crawler-test-codexapp`
- Workspace: `C:\Users\super\OneDrive\바탕 화면\업무\AI JOB\20260318_firstproject\crawler_test_codexapp`

## 목적
오케스트레이션 페이지와 배치 실행 계층을 실제 운영 요구에 맞게 보강했다. 핵심 요구는 다음과 같았다.

- filter/nonfilter 분리 후 상위 output 경로에 임시 수집 산출물이 남지 않게 한다.
- 페이지를 닫아도 Windows Task Scheduler와 scheduled runner가 독립적으로 실행되게 한다.
- 이전 실행 중복과 같은 실행 중복을 다르게 처리한다.
- 설정 저장, 수동 실행, 모니터링 시작을 분리한다.
- 분/시간/일 UI 대신 cron 형식으로 실행 주기를 설정한다.
- 실패 로그에는 사람이 확인 가능한 상세 메시지를 남긴다.

## 주요 변경
- `crawler_app/workflow.py`
  - `WorkflowExecution.generated_files`를 추가해 record policy에서 제외된 산출물도 cleanup 대상으로 추적한다.
  - project-relative output path와 output-root-relative path를 구분해 실제 생성 파일을 올바르게 삭제한다.
  - filter/nonfilter 분리 이후 현재 실행에서 생성된 root-level 산출물은 삭제하고, 사람이 둔 unrelated 파일은 보존한다.
  - previous-run duplicate stop은 현재 검색어에만 적용되고 다음 검색어는 계속 진행한다.
  - same-run duplicate는 stop이 아니라 skip으로 처리한다.
- `crawler_app/orchestration.py`
  - cron 정규화 및 다음 실행 시간 계산을 추가했다.
  - 한국어 job id를 먼저 exact match하고, legacy normalized id는 fallback으로만 사용한다.
  - 실패 메시지에 config name, job id, config path, exception type/message를 포함한다.
- `crawler_app/windows_scheduler.py`
  - project-root hash namespace를 사용해 clone별 scheduled task와 launcher를 격리한다.
  - cron subset을 Windows Task Scheduler 인자로 변환한다.
  - scheduler sync 전에 cron 변환 가능성을 검증한다.
- `crawler_app/scheduled_runner.py`
  - scheduled task가 실행될 때 저장된 settings를 다시 읽는다.
  - stale launcher flag보다 현재 저장된 `allow_email_send` 값을 사용한다.
  - explicit job id도 현재 enabled job만 실행한다.
- `crawler_app/web.py`, `templates/orchestration.html`, `static/styles.css`
  - 설정 저장, 수동 실행, 모니터링 시작 버튼을 분리한다.
  - 운영 설정 영역을 페이지 상단으로 이동한다.
  - cron 입력 UI를 추가하고 기존 force_due성 실행 옵션을 제거한다.
  - scheduler 상태 표시 영역을 제공한다.
- `README.md`
  - 새 운영 방식, cron 입력, scheduler sync, SMTP 환경변수, 검증 방법을 갱신한다.
- tests
  - cron 변환, scheduler sync, scheduled runner, duplicate scope, filter cleanup, 한국어 job id, web route 분리 테스트를 추가/갱신한다.

## 왜 이 방식인가
- 사이트별 crawler 코드를 늘리지 않고 기존 JSON config 기반 workflow를 유지하기 위해 공통 workflow/orchestration 계층에서 처리했다.
- Windows Server 운영 가능성을 고려해 DB 대신 JSON settings와 Windows Task Scheduler를 사용했다.
- 실제 scheduler는 페이지 생명주기와 분리되어야 하므로 web process는 설정 저장과 scheduler sync trigger만 담당한다.
- filter/nonfilter 밖 산출물 삭제는 위험하므로 현재 실행에서 생성된 파일만 추적해 삭제한다.

## 보류한 대안
- 전체 Linux crontab 문법 지원: Windows Task Scheduler 변환 위험 때문에 safe subset만 지원한다.
- DB 도입: 현재 단계에서는 JSON 상태 파일이 충분하고 원본 구조 변경이 커서 보류한다.
- 실제 이메일 자동 발송 테스트: 외부 발송 부작용이 있으므로 사용자의 명시 지시 없이 수행하지 않았다.

## 검증
- `python -m unittest discover -s tests`
  - Result: `151 tests OK`
- `python imsi\scenario_tests\orchestration_scenario_20260518.py`
  - Result: PASS
  - Evidence: `qa-artifacts/orchestration-20260518-scenarios/scenario_result.json`
- 실제 시그널 크롤링 1회 실행
  - Result: `duplicate_stopped`
  - `outputs/signal` top-level directory: `filter` only
- 실제 9개 항목 batch 실행, notifications disabled
  - Evidence: `qa-artifacts/orchestration-20260519-live-nine/batch_result.json`
  - Summary: total 9, failed 0, duplicate_stopped 9
  - 9개 output 모두 filter/nonfilter 밖 top-level output directory count 0
- 실제 Windows Scheduler smoke
  - Created/query/deleted namespaced task successfully.

## Secret Check
- `.env`, `imsi/`, `outputs/`, `qa-artifacts/`, `runtime/` are ignored.
- Staged/pushed files must not contain Gmail app password, SMTP password, Naver secret, Kakao API key, token, or `.env`.
- README contains only placeholder environment variable names.

## 남은 리스크
- cron은 Windows Task Scheduler로 안전하게 변환 가능한 subset만 지원한다.
- 실제 Gmail 발송은 외부 발송이므로 이번 push 전에는 수행하지 않았다.
- 기존 legacy scheduler task가 새 namespace 밖에 있으면 자동 삭제하지 않는다.
