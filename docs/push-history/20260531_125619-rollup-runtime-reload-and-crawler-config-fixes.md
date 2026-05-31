# 롤업 시간 런타임 재읽기와 크롤러 설정 보완

- Created at: 2026-05-31 12:56:19
- Branch: dev/crawler-current
- Push target: https://github.com/hgz-902/test_crawl/tree/dev/crawler-current

## Purpose

오케스트레이션 운영 중 확인된 scheduler/config/rollup 문제를 보완하고, 현재 제품 설정을 `hgz-902/test_crawl`의 `dev/crawler-current` 브랜치로 게시한다.

## Why This Change Was Needed

- 일부 config 파일명이 공백이나 원본 stem을 포함할 때 설정 파일을 정확히 찾지 못하는 문제가 있었다.
- Windows scheduler registry 저장 시 `Path` 값이 JSON 직렬화되지 않아 registry write 단계에서 실패할 수 있었다.
- scheduled runner가 CP949 stdout 환경에서 한글/특수문자 JSON 로그를 출력하다가 실패할 수 있었다.
- `workflow_records_rollup.py`의 `DEFAULT_ROLLUP_TIME`을 서버 실행 중 바꿔도 이미 생성된 rollup scheduler 객체가 새 값을 읽지 못했다.
- 하루 1회 rollup 가드가 날짜만 기준으로 되어 있어, 같은 날 11:00 실행 후 18:00으로 변경한 운영자의 의도를 반영할 수 없었다.
- 여러 크롤러 config의 cron 값을 분산해 동시 부하를 줄이고, 설정 파일 해석을 안정화할 필요가 있었다.

## What Changed

- `crawler_app/config_store.py`: config stem을 우선 정확히 매칭해 공백 포함 config 파일을 안정적으로 찾도록 보완.
- `crawler_app/orchestration.py`: 등록 job id가 config file stem 기준으로 정규화되도록 조정.
- `crawler_app/windows_scheduler.py`: scheduler registry JSON 저장 시 path-like 필드를 문자열로 변환.
- `crawler_app/scheduled_runner.py`: stdout/stderr 인코딩을 UTF-8로 재설정해 scheduled log 출력 실패를 방지.
- `crawler_app/workflow_records_rollup.py`: 현재 코드 기준 rollup 기본 시각을 `10:43`으로 설정.
- `crawler_app/workflow_records_rollup_scheduler.py`: 실행 중인 서버가 매 체크마다 `DEFAULT_ROLLUP_TIME` source 값을 다시 읽고, `date + rollup_time` 단위로 실행 여부를 판단하도록 변경.
- `configs/*.json`: 오케스트레이션 cron 분산 및 일부 config path/설정 보완 사항을 반영.
- `README.md`: rollup 시간이 source constant 변경만으로 런타임 반영되는 새 동작을 문서화.

## Design Judgment

- UI 설정 화면은 아직 추가하지 않고, 사용자가 요청한 대로 당장은 `DEFAULT_ROLLUP_TIME` 코드 상수 수정만으로 운영 시간을 바꾸는 방식을 유지했다.
- scheduler가 source file을 읽는 방식은 설정 UI/JSON schema를 늘리지 않으면서도 서버 재시작 없는 운영 반영을 가능하게 한다.
- 같은 날짜 중복 방지는 날짜만 보지 않고 `date + rollup_time`을 기준으로 바꿨다. 이로써 같은 날 다른 시간으로 변경한 운영 의도가 보존된다.
- 이미 지난 시각으로 바꾼 경우에는 해당 `date + rollup_time`이 실행된 적 없으면 다음 체크에서 1회 catch-up 실행되도록 했다.

## Alternatives Considered Or Deferred

- 오케스트레이션 UI에 rollup time 입력을 추가하는 방안은 사용자가 아직 원하지 않아 보류했다.
- 별도 `rollup_settings.json` 파일을 추가하는 방안도 가능하지만, 현재 요청은 코드 상수만 바꾸는 운영 흐름이므로 보류했다.
- Windows Task Scheduler 기반 별도 rollup task로 전환하는 방안은 현재 웹 서버 내부 scheduler 계약과 다르므로 이번 변경에서 제외했다.

## Validation

- `.venv\Scripts\python.exe -m unittest tests.test_workflow_records_rollup_scheduler tests.test_web tests.test_scheduled_runner` 통과.
- `.venv\Scripts\python.exe -m compileall -q crawler_app tests` 통과.
- scheduler registry 및 runtime log는 수동 관측으로 확인했으며, real email send는 수행하지 않았다.

## Remaining Risks

- 이번 변경 코드 자체는 현재 실행 중인 오래된 서버 프로세스에는 자동 반영되지 않는다. 한 번 재시작한 뒤부터는 `DEFAULT_ROLLUP_TIME` 변경이 서버 재시작 없이 반영된다.
- `tests/`는 `.gitignore` 정책상 새 테스트 파일을 추가 stage하지 않는다. 로컬 검증용 신규 테스트는 작업트리에 존재하지만 이번 push 대상에는 포함하지 않는다.
- 현재 `origin`은 `K-Ternag/crawlService`로 설정되어 있으므로, push는 사용자가 지정한 `hgz-902/test_crawl` URL로 직접 수행한다.
- 일부 기존 tracked test 변경은 이전 검증 목적 변경으로 남아 있으나, 사용자의 기존 hygiene 지시를 따라 push 대상에서 제외한다.

## Cumulative Prompt / Request Flow

- 오케스트레이션 설정 분산 cron 적용 요청.
- 41번 이후 config file resolution 문제 확인 및 보완 요청.
- Windows scheduler registry JSON write 실패와 CP949 scheduled runner 출력 실패 보완.
- 모니터링 중 rollup이 기대 시간에 다시 실행되지 않는 원인 파악.
- UI 구현 없이 코드 상수 변경만으로 rollup 시간이 런타임 반영되도록 수정 요청.
- 최종적으로 `hgz-902/test_crawl`의 `dev/crawler-current` 브랜치로 push 요청.

## Repo State Snapshot

### git branch --show-current

```text
dev/crawler-current
```

### git remote -v

```text
origin  https://github.com/K-Ternag/crawlService (fetch)
origin  https://github.com/K-Ternag/crawlService (push)
```

### Intended staged scope

```text
README.md
docs/push-history/20260531_125619-rollup-runtime-reload-and-crawler-config-fixes.md
configs/*.json changed in this session
crawler_app/config_store.py
crawler_app/orchestration.py
crawler_app/scheduled_runner.py
crawler_app/windows_scheduler.py
crawler_app/workflow_records_rollup.py
crawler_app/workflow_records_rollup_scheduler.py
```

### Explicitly excluded

```text
tests/test_scheduled_runner.py
tests/test_windows_scheduler.py
tests/test_workflow_records_rollup_scheduler.py
outputs/
runtime/
orchestration_state/
qa-artifacts/
.env
.venv
```

## Pre-Commit Checklist

- [x] Only task-related source/config/docs files are intended for staging.
- [x] No `.env`, API key, token, password, app password, cookie, or sensitive log is intentionally staged.
- [x] Push record is included in the same commit.
- [x] Validation results are recorded honestly.
- [x] Remaining risks are recorded honestly.
