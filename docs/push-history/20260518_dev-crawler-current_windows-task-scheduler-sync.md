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

---

## 2026-05-18 추가 변경 기록 - 오케스트레이션 병렬 스케줄러와 관리 UI

- Date: 2026-05-18 KST
- Repository: `C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp`
- Branch: `codex/crawler-test-codexapp`
- Remote target: `origin/codex/crawler-test-codexapp` (`https://github.com/hgz-902/test_crawl.git`)
- Commit message: `오케스트레이션 병렬 스케줄러와 관리 UI 개선`
- Approved push target: `https://github.com/hgz-902/test_crawl/tree/codex/crawler-test-codexapp`

### 요청 / 작업 단위

1. 오케스트레이션 설정 저장 시 항목별 Windows Task Scheduler 작업을 만들고, 저장 시점 기준 주기로 예약 실행되게 한다.
2. 선택 항목을 설정 저장과 동시에 실행할 수 있게 하고, 여러 항목은 항목별 스케줄러/메일링을 병렬로 수행하게 한다.
3. 중복 판정은 기존 `workflow_records.json`와 비교해 기존 기록과 중복되면 해당 크롤러만 중단하고, 같은 실행 내 중복은 skip만 하고 계속 수집한다.
4. 키워드 매칭 시 실제 메일 발송 허용 설정이 켜져 있을 때만 예약 실행에서도 메일을 보낸다.
5. 등록된 스케줄러를 오케스트레이션 페이지에서 표로 확인하고, 필요 시 개별 삭제할 수 있게 한다.
6. 스케줄러 표 로딩이 느려져 Windows 상세 조회 대신 로컬 registry JSON을 읽는 구조로 바꾼다.
7. 최근 실행과 등록 기록은 한국 시간 기준으로 표시한다.
8. push 전 하네스 문서, QA 산출물, runtime/log/output/cache, `.env` 등 소스와 무관한 로컬 파일을 ignore하거나 untrack한다.

### 변경 파일

- `.env.example`
- `.gitignore`
- `README.md`
- `configs/*.json` 중 테스트 범위 조절 및 headless 설정이 필요한 항목
- `crawler_app/orchestration.py`
- `crawler_app/scheduled_runner.py`
- `crawler_app/web.py`
- `crawler_app/windows_scheduler.py`
- `scripts/Run-OrchestrationJob.ps1`
- `static/styles.css`
- `templates/orchestration.html`
- `tests/test_orchestration.py`
- `tests/test_web.py`
- `tests/test_windows_scheduler.py`
- `docs/push-history/20260518_dev-crawler-current_windows-task-scheduler-sync.md`
- git 추적 해제: `DECISION_RULING.md`, `RUN_CONTEXT.md`, `TASK_CONTRACT.md`, `TASK_PLAN.md`, `TASK_CLASSIFICATION.md`, `GUI_QA_PLAN.md`, `GUI_QA_RESULT.md`, `ORCHESTRATION_ALPHA_STATE.md`, `THREAT_MODEL.md`, `SECURITY_TEST_CHECKLIST.md`, `SOURCE_CHANGE_GUARDRAIL.md`

### 변경 이유

기존 오케스트레이션은 선택 항목을 순차 배치로 처리하는 성격이 강했다. 개발 중 실제 검수에서 7개 이상 항목을 한 배치에서 순차 실행하면 10분 주기보다 첫 수행이 길어질 수 있고, 공유 상태 파일을 동시에 쓰는 위험도 확인됐다. 사용자가 원하는 운영 방식은 “크롤러 항목마다 하나의 스케줄러가 있고, 각 항목은 자기 상태/메일링/중복판정을 독립적으로 처리하는 구조”였다.

따라서 단일 batch task 중심에서 항목별 task, 항목별 state/history/lock, registry 기반 스케줄러 표시 구조로 바꿨다. 이 변경은 사이트별 크롤링 코드를 늘리는 것이 아니라 오케스트레이션 운영 계층을 강화하는 변경이다.

### 설계 판단과 tradeoff

- 항목별 Windows Task Scheduler를 사용했다.
  - 장점: 각 크롤러가 독립 주기로 실행되고, 긴 크롤러가 다른 항목 실행을 막지 않는다.
  - 비용: Windows Task Scheduler에 여러 작업이 생기므로 관리 UI와 삭제 기능이 필요하다.
- 상태 파일을 항목별로 분리했다.
  - 장점: 병렬 실행 중 한 공유 상태 파일을 동시에 쓰는 문제를 피한다.
  - 비용: `orchestration_state/jobs`, `history`, `locks`처럼 로컬 상태 폴더가 늘어난다. 이 폴더들은 git ignore 대상이다.
- 스케줄러 표는 Windows 상세 조회 대신 registry JSON을 읽는다.
  - 장점: `/orchestration` 로딩 시간이 약 10초대에서 1초 미만으로 줄었다.
  - 비용: Windows Task Scheduler를 외부에서 직접 수정하면 registry와 실제 작업이 어긋날 수 있다. 앱 UI를 통해 생성/삭제하는 운영을 전제로 한다.
- `-AllowEmailSend`는 저장된 UI 설정이 켜진 경우에만 launcher에 포함한다.
  - 장점: SMTP 비밀번호가 있어도 사용자가 허용하지 않으면 dry-run을 유지한다.
  - 비용: 저장된 설정이 운영 정책이므로, 실제 발송 전 설정 확인이 필요하다.
- `.venv\Scripts\python.exe`를 먼저 사용하고 없을 때만 `python` fallback을 둔다.
  - 장점: 개발/운영 환경에서 의존성 꼬임을 줄인다.
  - 비용: `.venv`가 없는 배포 환경은 여전히 PATH 정책에 의존한다.

### 구현 요약

- `orchestration.py`
  - 항목별 job state/history/lock 추가
  - 병렬 실행 옵션 추가
  - 기존 기록과 중복 시 해당 job만 `duplicate_stopped`
  - 같은 실행 내 중복은 skip 후 계속 수집
  - `.env` 로드, SMTP 발송 허용 플래그 반영
  - 메일 본문을 `사이트 > 검색어/필터 > desc / URL` 구조로 정리
- `windows_scheduler.py`
  - enabled job마다 `\CrawlerOrchestration\crawler_<hash>` 작업 생성
  - launcher 생성 시 job id와 email send 허용 플래그 전달
  - 스케줄러 registry JSON 저장/삭제
  - 관리 작업 prefix 이외 삭제 방지
- `web.py`
  - 설정 저장 시 스케줄러 동기화와 선택 항목 즉시 실행
  - 수동 실행은 항상 선택 항목을 즉시 실행
  - 스케줄러 목록/삭제 route 추가
  - 스케줄러 표는 registry 기반으로 렌더링
  - 최근 실행/등록 기록은 KST 표시
- `templates/orchestration.html`, `static/styles.css`
  - 등록된 스케줄러 표와 삭제 버튼 추가
  - 실행 옵션 문구를 저장 시점 기준 스케줄링으로 명확화
- `.gitignore`, `.env.example`
  - 하네스/QA/runtime/local state ignore 보강
  - SMTP placeholder 예시 추가

### 검증 결과

- `.\.venv\Scripts\python.exe -m unittest discover -s tests`
  - 결과: `Ran 136 tests ... OK`
- 실제 오케스트레이션 화면 검수:
  - `/orchestration` 응답 시간: 약 10.7초에서 약 0.7~0.8초로 감소
  - 등록된 스케줄러 표 6행, 삭제 버튼 6개 표시 확인
  - 최근 실행/등록 기록이 KST로 표시되는 것 확인
- 실제 Windows Task Scheduler 확인:
  - 삭제된 `시그널`, `인베스트조선`, `연합뉴스` 작업은 목록에서 제거됨
  - 15:19 실행 로그에는 남은 6개 항목만 생성됨
- 실제 메일 발송 검수:
  - SMTP 앱 비밀번호가 설정된 상태에서 키워드 매칭 메일 발송 확인
  - push 대상에는 실제 SMTP 비밀번호를 포함하지 않음

### 의도적으로 제외한 파일

- `.env`: API key, SMTP password 등 로컬 비밀정보
- `.venv/`: 로컬 Python 환경
- `outputs/`: 크롤링 결과물
- `orchestration_state/`: 로컬 설정, job state/history/lock, scheduler registry
- `runtime/`, `logs/`: 실행 로그와 dev server/scheduled task 로그
- `qa-artifacts/`: 브라우저 검수 스크린샷과 테스트 산출물
- `__pycache__/`, `.pytest_cache/`: Python cache
- 하네스/session-local 문서 11개는 로컬 파일을 유지하고 git 추적만 해제한다.

### 누적 프롬프트 / 변경 흐름 추가 기록

- 이전 반영 작업: Naver/Daum/Google은 API/RSS형 예외로 관리하고, 일반 뉴스형 사이트는 가능하면 기존 설정 기반 workflow를 유지한다.
- 이전 반영 작업: 원본 경로 기반 개발 원칙에 따라 하네스 문서와 실행 산출물은 소스 push에서 제외한다.
- 현재 반영 작업: 오케스트레이션 페이지에서 여러 크롤러를 선택하고 주기를 설정해 배치/예약 실행한다.
- 현재 반영 작업: 항목별 Windows Task Scheduler를 만들고 삭제/재생성 범위는 `\CrawlerOrchestration\crawler_*`로 제한한다.
- 현재 반영 작업: 공유 상태 파일 동시쓰기 위험을 줄이기 위해 job별 state/history/lock을 사용한다.
- 현재 반영 작업: 스케줄러 관리 표를 추가하되, 느린 Windows 상세 조회 대신 registry JSON을 사용한다.
- 현재 반영 작업: 등록된 스케줄러 삭제 버튼을 추가하고, 삭제 시 UI 설정에서도 해당 job을 비활성화한다.
- 현재 반영 작업: 시간 표시는 사용자 운영 기준에 맞춰 한국 시간으로 변환한다.
- 현재 반영 작업: push 전 ignore hygiene gate를 적용해 하네스/QA/runtime/local 파일을 stage하지 않는다.

### 남은 리스크

- Windows Task Scheduler 작업은 현재 사용자 계정/로그온 정책에 의존한다.
- 앱 UI 밖에서 Windows Task Scheduler 작업을 직접 수정하면 registry 표시와 실제 작업이 어긋날 수 있다.
- `.venv`가 없는 배포 환경에서는 launcher가 `python` fallback을 사용하므로 PATH 정책 점검이 필요하다.
- 실제 메일 발송은 저장된 UI 설정과 SMTP 환경변수에 따라 예약 실행에서도 발생한다. 이는 현재 의도된 운영 동작이다.

### Push Command

```powershell
git push -u origin codex/crawler-test-codexapp:codex/crawler-test-codexapp
```

### Push Result

TODO
