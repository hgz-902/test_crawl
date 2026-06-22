# Scheduled Task 로그 및 종료코드 안정화

## 기본 정보

- Date/time: 2026-05-18 16:51 KST
- Repository path: `C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp`
- Branch: `dev/crawler-current`
- Remote target: `https://github.com/K-Ternag/crawlService/tree/dev/crawler-current`
- Commit message: `스케줄러 로그와 종료코드 캡처 안정화`

## 요청 / 작업 범위

다른 로컬 환경에서 크롤링, 중복판정, 메일 발송, 앱 history 기록은 정상인데 Windows Task Scheduler의 `LastTaskResult`가 `1`로 남고 `runtime/scheduled-task/*.log` 파일이 0바이트로 남는 현상이 보고됐다.

이번 변경은 크롤러 본체나 사이트별 config 실행 구조가 아니라, Windows Task Scheduler가 호출하는 PowerShell wrapper의 로그/종료코드 캡처를 안정화하는 작업이다.

## 변경 파일

- `scripts/Run-OrchestrationJob.ps1`
- `tests/test_windows_scheduler.py`
- `docs/push-history/20260518_dev-crawler-current_scheduled-task-log-exit-code-fix.md`

## 변경 이유

앱의 `orchestration_state/history/*.json`에는 정상 결과가 기록되는데 Windows Task Scheduler만 실패로 보이는 경우, 실패 지점은 크롤링 로직이 아니라 다음 실행 경로에 있을 가능성이 높다.

```text
Windows Task Scheduler
-> app-generated launcher ps1
-> scripts/Run-OrchestrationJob.ps1
-> python -m crawler_app.scheduled_runner
```

기존 `Run-OrchestrationJob.ps1`은 Python 실행 줄에만 `*> $logPath` redirect를 걸고, 마지막에 `$LASTEXITCODE`를 반환했다. 이 구조에서는 Python 실행 전 단계나 PowerShell wrapper 단계에서 문제가 생기면 0바이트 로그가 남을 수 있고, `$LASTEXITCODE`가 실제 Python 종료코드인지 확인하기 어렵다.

## 설계 판단과 tradeoff

- PowerShell 스크립트 시작 시점부터 로그를 남기도록 바꿨다.
  - 장점: `.env` 로드 전 실패, 작업 폴더 문제, Python path 문제도 로그에 남는다.
  - 단점: 로그가 기존보다 조금 더 장황해진다.
- Python 실행은 `Start-Process`와 stdout/stderr 임시 파일 redirect로 바꿨다.
  - 장점: Python stdout/stderr를 분리해 캡처하고, 프로세스 종료코드를 `$process.ExitCode`로 명확히 얻는다.
  - 단점: 임시 stdout/stderr 파일을 만들었다가 정리하는 단계가 추가된다.
- 최종 종료코드는 `$exitCode` 변수로만 반환한다.
  - 장점: PowerShell 내부 명령의 `$LASTEXITCODE` 오염 가능성을 줄인다.
  - 단점: wrapper 자체 예외는 명시적으로 `exitCode=1`로 처리한다.
- 크롤러 본체나 `scheduled_runner.py`의 성공/실패 판단은 바꾸지 않았다.
  - `duplicate_stopped`는 기존처럼 정상 계열이며, batch failed가 없으면 scheduled runner는 exit 0을 반환한다.

## 구현 요약

- `Run-OrchestrationJob.ps1`
  - `Write-RunLog` 함수 추가
  - 시작 시점부터 ProjectRoot, JobId, AllowEmailSend, PowerShell 버전 기록
  - `.env` 로드 여부와 entry count 기록
  - Python path와 arguments 기록
  - `Start-Process -Wait -PassThru`로 Python 실행
  - `-RedirectStandardOutput`, `-RedirectStandardError`로 stdout/stderr 캡처 후 main log에 병합
  - PowerShell wrapper 예외를 catch해 로그에 남기고 `exitCode=1` 반환
  - 마지막에 항상 `Scheduled orchestration task finished. exit_code=<n>` 기록 후 `exit <n>`
- `tests/test_windows_scheduler.py`
  - runner script가 `Start-Process`, stdout/stderr redirect, Python exit code log, final exit code log를 포함하는지 확인하도록 테스트 갱신

## 검증 결과

- `.\.venv\Scripts\python.exe -m unittest tests.test_windows_scheduler tests.test_web`
  - 결과: `Ran 30 tests ... OK`
- `.\.venv\Scripts\python.exe -m unittest discover -s tests`
  - 결과: `Ran 137 tests ... OK`
- 직접 PowerShell script probe
  - dummy `crawler_app.scheduled_runner`가 `duplicate_stopped` JSON을 출력하고 exit 0 반환
  - `Run-OrchestrationJob.ps1` 직접 실행 결과 exit code 0
  - log size 1033 bytes
  - Python stdout과 final `exit_code=0` 기록 확인
- 실제 Windows Task Scheduler probe
  - app-generated UTF-8 BOM launcher 사용
  - Task Scheduler `LastTaskResult=0`
  - log size 1053 bytes
  - 한국어 `산업부_보도자료` job id가 log filename/content에 정상 표시
  - `Python process finished. exit_code=0`, `Scheduled orchestration task finished. exit_code=0` 확인
- 검수용 Task Scheduler 작업과 임시 파일은 삭제 완료
- `git diff --check`
  - whitespace error 없음
  - Windows 작업 복사본의 LF -> CRLF 경고만 표시

## 의도적으로 제외한 파일

다음 파일/폴더는 로컬 실행 산출물, 비밀정보, 캐시, 하네스 세션 문서이므로 stage하지 않는다.

- `.env`
- `.venv/`
- `outputs/`
- `orchestration_state/`
- `runtime/`
- `logs/`
- `qa-artifacts/`
- `crawler_app/__pycache__/`
- `crawlers/__pycache__/`
- `tests/__pycache__/`
- `DECISION_RULING.md`
- `RUN_CONTEXT.md`
- `TASK_CONTRACT.md`
- `TASK_PLAN.md`
- `TASK_CLASSIFICATION.md`
- `GUI_QA_PLAN.md`
- `GUI_QA_RESULT.md`
- `ORCHESTRATION_ALPHA_STATE.md`
- `THREAT_MODEL.md`
- `SECURITY_TEST_CHECKLIST.md`
- `SOURCE_CHANGE_GUARDRAIL.md`

## 누적 프롬프트 / 변경 흐름 추가 기록

- 사용자는 다른 로컬에서 workflow records 최신 2개 제거 후 스케줄러가 신규 항목을 다시 수집하는 동작을 확인했다.
  - 확인된 정상 동작: 시그널/인베스트조선은 최신 2건 재수집 및 메일 sent, 산업부 보도자료는 일부 재수집 및 keyword no match 처리.
- 동시에 Windows Task Scheduler의 `LastTaskResult=1`과 0바이트 scheduled log가 남는 이상점이 확인됐다.
  - 판단: 크롤링/중복판정/메일 로직이 아니라 scheduled PowerShell wrapper의 로그/종료코드 관측 문제가 원인 계열이다.
- 사용자는 수정 후 직접 최종 검수까지 요청했다.
  - 조치: PowerShell wrapper를 시작 로그, stdout/stderr 캡처, 명시적 Python exit code 반환 구조로 변경했다.
  - 조치: 실제 Windows Task Scheduler probe로 `LastTaskResult=0`과 non-empty log를 확인했다.

## 남은 리스크

- 실제 산업부/기후에너지부 같은 `headless=false` 크롤러는 Windows Task Scheduler 실행 계정/로그온 상태의 영향을 받을 수 있다.
- 이번 수정은 wrapper 로그와 종료코드 캡처 안정화이며, Windows가 비대화형 세션에서 headed browser 실행을 제한하는 환경 문제까지 제거하는 것은 아니다.
- 운영 PC에서 여전히 `LastTaskResult`가 1이면 새 로그의 시작/파이썬/최종 exit code 구간을 기준으로 어느 단계에서 실패했는지 추가 판단해야 한다.

## Push Command

```powershell
git push -u origin dev/crawler-current:dev/crawler-current
```

## Push Result

TODO
