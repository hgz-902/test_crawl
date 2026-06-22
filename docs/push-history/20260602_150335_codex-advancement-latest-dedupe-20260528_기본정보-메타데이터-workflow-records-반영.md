# 기본정보 메타데이터 workflow_records 반영

- 작성 시각: 2026-06-02 15:03:35 +09:00
- 저장소 경로: `C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp`
- 브랜치: `codex/advancement-latest-dedupe-20260528`
- 원격 대상: `origin/codex/advancement-latest-dedupe-20260528`
- 커밋 메시지: `기본정보 메타데이터를 workflow records에 반영`

## 요청 / 작업 프롬프트

크롤러 설정 UI의 기본정보 영역에 운영 분류 메타데이터를 입력할 수 있는 필드를 추가한다. 사용자가 입력한 `category`와 `crawling_type`은 config JSON에 그대로 저장되어야 하며, 크롤링 완료 후 생성되는 `workflow_records.json`의 top-level 메타데이터에도 `config_name` 바로 아래에 동일한 키와 값으로 기록되어야 한다. 이 변경은 개별 사이트 크롤러 로직이나 XPath 실행 단계에는 영향을 주지 않고, 설정 저장 및 workflow record snapshot 생성 계층에만 한정한다.

## 변경 파일

- `templates/editor.html`
- `crawler_app/web.py`
- `crawler_app/workflow.py`

## 변경 이유

운영자가 크롤러별 분류 체계와 수집 유형을 설정 화면에서 직접 관리하고, 이후 `workflow_records.json`을 데이터 저장소/API/운영 확인의 메타데이터로 사용할 때 각 records 묶음이 어떤 카테고리와 크롤링 타입에서 나온 것인지 즉시 식별할 수 있어야 한다.

기존 구조에서는 `workflow_records.json` top-level에 `config_name`, `item_count`, `records`만 있어서, 같은 소스라도 PR/공시/뉴스/보도자료 등 운영 분류를 파일만 보고 구분하기 어려웠다.

## 설계 판단

- `category`, `crawling_type`은 record별 필드가 아니라 config 실행 단위의 메타데이터이므로 `workflow_records.json` top-level에 둔다.
- JSON 키 순서는 운영자가 파일을 직접 열었을 때 읽기 쉽도록 `config_name`, `category`, `crawling_type`, `item_count`, `records` 순서로 유지한다.
- UI 저장은 기존 `data-path` 기반 payload builder를 재사용한다. 별도 저장 로직을 새로 만들지 않아 코드 분기를 늘리지 않는다.
- 신규 config 생성 시 빈 값 기본값을 제공해 기존 config와 신규 config가 모두 동일한 키를 가질 수 있게 했다.
- 기존 크롤러 실행 단계, 중복 진단, latest/rollup/tran 구조는 변경하지 않았다.

## 보류한 대안

- 각 record 안에 `category`, `crawling_type`을 반복 저장하는 방식은 보류했다. 현재 요구는 `workflow_records.json`의 상단 메타데이터이며, record마다 같은 값을 반복하면 파일 크기와 중복 필드가 늘어난다.
- 설정 목록 테이블에 카테고리/크롤링 타입을 표시하는 UI 확장은 이번 요청 범위 밖으로 보류했다.
- 기존 모든 config JSON에 즉시 `category`, `crawling_type`을 일괄 주입하는 변경은 보류했다. 사용자가 UI에서 직접 관리할 수 있는 입력칸과 신규 기본값만 추가했다.

## 구현 요약

- `templates/editor.html`
  - 기본정보 영역에 `카테고리`, `크롤링 타입` 입력칸 추가
  - 각각 `data-path="category"`, `data-path="crawling_type"`로 기존 payload 저장 흐름 사용

- `crawler_app/web.py`
  - `default_config()`에 `category`, `crawling_type` 빈 문자열 기본값 추가

- `crawler_app/workflow.py`
  - `_write_workflow_record_snapshot_unlocked()`에서 `workflow_records.json` payload에 `category`, `crawling_type` top-level 메타데이터 추가

## 검증 결과

- `.\.venv\Scripts\python.exe -m compileall main.py crawler_app crawlers`
  - 통과
- `.\.venv\Scripts\python.exe -m unittest tests.test_workflow.WorkflowDownloadTests.test_apply_workflow_result_filters_splits_records_and_writes_snapshots`
  - 통과
- 임시 config 저장 확인
  - `save_config()` 후 `get_config()`에서 `category`, `crawling_type` 보존 확인
- `git diff --check -- crawler_app/web.py crawler_app/workflow.py templates/editor.html tests/test_workflow.py`
  - 통과
- secret scan
  - 이번 staged 대상 diff에서 secret/API key/SMTP password 없음

## 의도적으로 제외한 파일

이번 커밋에는 기본정보 메타데이터 반영과 직접 관련된 운영 소스만 포함한다.

- 제외: `configs/*.json`
  - 현재 작업 전부터 다수 설정 파일 변경이 남아 있으며 이번 요청 범위가 아님
- 제외: `tests/*.py`
  - validation-only 로컬 변경 및 이전 작업의 dirty 변경이 섞여 있어 스킬 기준에 따라 기본적으로 stage하지 않음
- 제외: `crawler_app/runtime_maintenance.py`, `crawler_app/workflow_records_rollup.py`
  - 이번 작업 범위와 무관한 기존 dirty 변경
- 제외: `.env`, `.venv/`, `logs/`, `outputs/`, `runtime/`, `orchestration_state/`, `qa-artifacts/`, `imsi/`, `__pycache__/`
  - 로컬 실행/비밀/산출물/캐시성 파일이며 ignore 대상

## 남은 리스크

- 기존 config 파일에는 `category`, `crawling_type` 값이 비어 있을 수 있다. 운영자가 UI에서 값을 입력하거나 향후 별도 config 정리 작업으로 채워야 한다.
- 설정 목록 화면에는 아직 이 두 값이 표시되지 않는다. 사용자가 목록에서 즉시 보고 싶다면 별도 UI 확장이 필요하다.
- 기존 rollup된 `workflow_records_*.json`에는 과거 생성 시점의 top-level 구조가 유지된다. 이번 변경은 이후 새로 생성되는 live `workflow_records.json`부터 적용된다.

## 누적 프롬프트 / 변경 흐름 추가 기록

- 현재 반영 작업:
  - 크롤러 설정 기본정보에 `category`, `crawling_type` 입력 필드를 추가한다.
  - 사용자가 입력한 값을 config JSON 저장 흐름에 보존한다.
  - 크롤링 완료 후 `workflow_records.json` top-level에서 `config_name` 바로 아래에 `category`, `crawling_type`을 기록한다.
  - 개별 사이트 크롤러, XPath, 중복 진단, latest/rollup/tran 구조는 변경하지 않는다.

