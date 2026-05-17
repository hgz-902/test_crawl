# Windows Task Scheduler 동기화 추가

## 목적

오케스트레이션 페이지에서 설정을 저장할 때 Windows Task Scheduler 작업이 실제로 생성되도록 변경했다. 사용자가 저장할 때마다 기존 오케스트레이션 예약 작업을 삭제하고, 현재 설정에 맞춰 다시 생성해야 한다는 요구를 반영한다.

## 변경 내용

- `crawler_app/windows_scheduler.py`
  - `\CrawlerOrchestration\crawler_*` 작업만 관리 대상으로 제한
  - 기존 관리 작업 종료 시도 후 삭제
  - enabled crawler config마다 새 Scheduled Task 생성
  - 분/시간/일 단위 interval을 `schtasks` 옵션으로 변환
  - 긴 OneDrive 한글 경로가 `/TR` 261자 제한에 걸리지 않도록 `%LOCALAPPDATA%\CrawlerOrchestration\crawler_<hash>.ps1` launcher를 생성
- `scripts/Run-OrchestrationJob.ps1`
  - scheduled task에서 호출되는 짧은 launcher 대상
  - 프로젝트 `.env`를 프로세스 환경변수로 로드
  - `crawler_app.scheduled_runner`로 단일 job 실행
- `crawler_app/scheduled_runner.py`
  - scheduler가 호출하는 Python entrypoint
  - 단일 job을 `force_due=True`로 실행
- `/orchestration/save`
  - 설정 저장 직후 Windows Task Scheduler 동기화 실행
  - 실패 시 500과 오류 메시지 표시
- README와 테스트 보강

## 설계 판단

- 삭제 대상은 `\CrawlerOrchestration\crawler_*` prefix로 한정해 다른 Windows 작업을 건드리지 않는다.
- 사용자가 명시한 요구가 "삭제 후 재생성"이므로 `Register-ScheduledTask -Force`식 overwrite 대신 delete/recreate를 사용했다.
- `/TR` 길이 제한과 한글 경로 인코딩 문제 때문에 `.cmd`가 아니라 UTF-8 BOM이 포함된 짧은 `.ps1` launcher를 사용한다.
- 첫 실행 시각은 `저장 시각 + 설정 interval`로 잡는다. 저장 직후 1분 뒤 즉시 실행되는 동작은 사용자 기대와 달라서 배제했다.

## 검증

- `python -m unittest tests.test_windows_scheduler tests.test_web tests.test_orchestration` 통과
- `python -m unittest discover -s tests` 결과 119 tests OK
- 실제 Windows Task Scheduler 동기화 실행:
  - 기존 관리 작업 9개 삭제
  - 새 관리 작업 9개 생성
  - 샘플 작업 `\CrawlerOrchestration\crawler_3a072197ebe2`의 `Task To Run`이 `%LOCALAPPDATA%` 아래 짧은 launcher `.ps1`을 가리키는 것 확인
  - 샘플 작업 `Next Run Time`이 저장 시각 기준 1시간 뒤로 설정됨을 확인

## 비밀정보 점검

- task action과 launcher에는 SMTP/API 비밀값을 직접 쓰지 않는다.
- 비밀값은 Windows 환경변수 또는 git ignored `.env`에서 scheduled process로만 로드한다.
- `attach/`, `.env`, `runtime/`, `outputs/`, `orchestration_state/`, `imsi/`는 커밋 대상에서 제외한다.

## 남은 리스크

- 작업은 현재 Windows 사용자 `super`의 interactive-only task로 생성된다.
- PC가 꺼져 있거나 사용자가 로그인하지 않은 상태에서 실행되어야 하면 Task Scheduler 계정/로그온 정책을 별도로 조정해야 한다.
- scheduled run이 실제 메일을 보내므로 `.env`/환경변수의 SMTP 설정과 수신자 설정을 운영 전에 다시 확인해야 한다.
