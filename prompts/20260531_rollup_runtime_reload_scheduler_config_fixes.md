# 2026-05-31 rollup runtime reload 및 scheduler/config 안정화 보완 프롬프트

## 개발 보완 요청

현재 크롤러 오케스트레이션 제품의 `dev/crawler-current` 브랜치에서 scheduler, config resolution, scheduled runner 로그 출력, workflow records rollup 동작을 운영 관점에서 보완하라. 이번 작업은 UI 확장이 아니라 기존 운영 흐름을 안정화하는 소스 보완 작업이다.

## 배경

운영자가 오케스트레이션 화면에서 여러 크롤러를 분 단위로 분산 실행하고 있으며, 각 실행 결과는 `outputs/<crawler>/filter`, `outputs/<crawler>/tran`, `outputs/<crawler>/filter/rollup` 흐름으로 저장된다. 최근 관측 중 다음 문제가 확인되었다.

- 공백이나 원본 파일명 stem이 포함된 config가 일부 경로에서 정확히 해석되지 않는다.
- 오케스트레이션 job id가 config 파일명과 다르게 정규화될 경우, UI의 선택 항목과 scheduler registry의 항목 연결이 불안정해질 수 있다.
- Windows scheduler registry 저장 시 `Path` 객체가 JSON 직렬화되지 않아 registry write 단계에서 실패할 수 있다.
- scheduled runner가 CP949 stdout 환경에서 한글이나 특수문자를 포함한 JSON summary를 출력할 때 인코딩 오류가 날 수 있다.
- `workflow_records_rollup.py`의 `DEFAULT_ROLLUP_TIME`을 바꾼 뒤 서버를 재시작하지 않으면, 이미 생성된 rollup scheduler 객체가 변경된 시간을 읽지 못한다.
- 기존 rollup scheduler는 하루 실행 여부를 날짜만으로 판단해, 같은 날 11:00 rollup 이후 18:00으로 시간을 변경해도 두 번째 rollup을 허용하지 않는다.

## 요구사항

### 1. Config 파일 해석 안정화

- `config_name_to_path()`는 먼저 사용자가 전달한 이름이 실제 config 파일 stem과 정확히 일치하는지 확인해야 한다.
- 정확히 일치하는 `<stem>.json`이 있으면 sanitized fallback보다 그 파일을 우선한다.
- 기존 sanitized config stem fallback은 유지한다.
- 이 변경은 공백 포함 config, 영문 긴 config, 한글 config 모두에서 기존 동작을 깨지 않아야 한다.

### 2. 오케스트레이션 job id 정규화

- `registered_config_jobs()`에서 job id는 config file stem을 기준으로 안정적으로 정규화한다.
- UI saved settings, scheduler registry, config file resolution이 서로 같은 job id 기준으로 연결되도록 한다.
- config display name과 job id는 혼동하지 않는다.

### 3. Windows scheduler registry JSON 저장 보완

- scheduler registry에 기록되는 `job_id`, `config_name`, `config_path`, `output_dir` 등 path-like 또는 외부 입력 기반 값은 JSON 저장 전에 문자열로 변환한다.
- registry write 실패가 scheduler sync 전체 실패로 이어지지 않도록 직렬화 가능한 구조를 보장한다.
- Windows Scheduler task 생성/삭제 계약 자체는 바꾸지 않는다.

### 4. Scheduled runner 출력 인코딩 보완

- 예약 실행 로그가 CP949 환경에서도 실패하지 않도록 `scheduled_runner` 시작 시 stdout/stderr를 UTF-8, `errors="replace"`로 재설정한다.
- 출력 payload의 의미나 JSON schema는 바꾸지 않는다.
- real email send 정책, saved settings 기반 실행 정책, scheduler 등록 정책은 건드리지 않는다.

### 5. Rollup 시간 런타임 반영

- UI에는 아직 rollup time 설정 화면을 추가하지 않는다.
- 운영자는 당분간 `crawler_app/workflow_records_rollup.py`의 `DEFAULT_ROLLUP_TIME` 코드 상수만 수정하여 rollup 시간을 바꾼다.
- 실행 중인 웹 서버의 rollup scheduler는 매 체크마다 `workflow_records_rollup.py` source에서 `DEFAULT_ROLLUP_TIME` 값을 다시 읽어야 한다.
- source 파일을 읽을 수 없거나 값이 잘못된 경우에는 직전 정상 rollup time 또는 fallback 값을 유지한다.
- 값 검증은 기존 `HH:MM` 24시간 형식을 따른다.

### 6. 같은 날 rollup 재실행 기준 변경

- rollup 중복 실행 방지는 날짜만으로 판단하지 말고 `date + rollup_time` 기준으로 판단한다.
- 예를 들어 오늘 11:00에 rollup이 실행된 뒤 운영자가 `DEFAULT_ROLLUP_TIME = "18:00"`으로 바꾸면, 오늘 18:00에는 다시 1회 rollup이 실행되어야 한다.
- 같은 `date + rollup_time` 조합은 반복 체크되어도 한 번만 실행되어야 한다.
- 운영자가 이미 지난 시간으로 변경했고, 오늘 그 `date + rollup_time` 조합이 아직 실행된 적 없다면 다음 scheduler 체크에서 1회 catch-up 실행을 허용한다.
- 이 정책은 기존 rollup archive placement, file lock, keep-count pruning, latest-first archive sorting을 바꾸면 안 된다.

### 7. Cron 분산 설정 반영

- 오케스트레이션 config의 cron 값을 분 단위로 분산해 한 시각에 모든 crawler가 몰리지 않도록 한다.
- 기존 owner-controlled 값의 의미를 임의로 바꾸지 말고, 이번 요청에서 승인된 schedule 분산만 반영한다.
- outputs, runtime, orchestration_state, qa-artifacts, `.env`, `.venv`는 commit 대상에서 제외한다.

## 검증 기준

- 관련 unit test를 추가하거나 기존 테스트로 보강해 다음을 증명한다.
  - `DEFAULT_ROLLUP_TIME` source 변경이 scheduler 재시작 없이 반영된다.
  - 같은 날짜라도 rollup time이 달라지면 새 boundary로 1회 실행된다.
  - 이미 지난 새 rollup time은 아직 실행된 적 없으면 catch-up 1회가 가능하다.
  - 잘못된 source 값은 fallback을 사용한다.
  - scheduled runner가 CP949 stdout 상황에서도 JSON summary를 출력할 수 있다.
  - scheduler registry path-like 값이 JSON 직렬화 가능하다.
- 최소 검증 명령:
  - `python -m unittest tests.test_workflow_records_rollup_scheduler tests.test_web tests.test_scheduled_runner`
  - `python -m compileall -q crawler_app tests`
- 테스트 파일이 repository 정책상 ignore 대상이면, 로컬 검증에는 사용하되 push 대상에는 포함하지 않는다.

## 배포 및 기록 요구

- 변경 이유, 대안, 검증 결과, 남은 리스크를 `docs/push-history/`에 기록한다.
- source 변경 프롬프트는 `prompts/` 아래에 별도 Markdown 파일로 남긴다.
- secret, `.env`, outputs, runtime log, scheduler registry, qa artifacts는 push하지 않는다.
- 원격 push 대상은 `hgz-902/test_crawl`의 `dev/crawler-current` 브랜치다.
