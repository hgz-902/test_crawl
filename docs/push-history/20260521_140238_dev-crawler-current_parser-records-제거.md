# parser_records 제거 및 nonfilter workflow_records 통일

- 일시: 2026-05-21 14:02:38 KST
- 저장소: `C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp`
- 브랜치: `dev/crawler-current`
- 원격: `origin https://github.com/K-Ternag/crawlService.git`
- 커밋 메시지 예정: `parser_records 제거 및 workflow 기록 통일`
- push 대상: `origin/dev/crawler-current`

## 요청 / 작업 단위

- `parser_records.json`은 더 이상 사용하지 않기로 결정했다.
- 관련 코드를 먼저 제거한다.
- parser/API형 항목도 API가 아닌 항목들과 동일하게 `nonfilter/workflow_records.json`을 남기도록 되돌린다.
- filter/nonfilter 관련 중복 진단 프로세스 자체는 더 수정하지 않고 현재 방식대로 유지한다.

## 변경 파일

- `crawler_app/workflow.py`

## 변경 내용

- parser/API형 nonfilter snapshot 저장 파일명을 `parser_records.json`에서 `workflow_records.json`으로 변경했다.
- 기존 중복 index 생성 함수가 `parser_records.json`을 함께 읽던 분기를 제거했다.
- 중복 index는 이제 `output_dir` 아래의 `workflow_records.json`만 읽는다.
- 따라서 기존 정책대로 `filter/workflow_records.json`, `nonfilter/workflow_records.json` 양쪽을 읽되, 별도 `parser_records.json` 파일은 저장/조회하지 않는다.

## 설계 판단

- `parser_records.json`은 parser/API형 nonfilter 기록을 별도로 보존하기 위한 중간 산출물이었지만, 저장 구조가 일반 크롤러와 달라져 운영자가 이해하기 어려웠다.
- 일반 항목과 parser/API 항목의 기록 파일명을 `workflow_records.json`으로 통일하면, filter/nonfilter의 기록 구조가 같아지고 이후 진단 기준도 단순해진다.
- 중복 진단 로직은 `workflow_records.json`을 기준으로 유지하므로, 기존 filter/nonfilter 중복 판단 흐름은 건드리지 않는다.
- 과거 outputs에 남아 있는 `parser_records.json` 파일은 자동 삭제하지 않는다. 이번 변경은 새 실행과 코드 경로에서 더 이상 생성/참조하지 않게 하는 범위다.

## 보류한 대안

- 과거 outputs의 `parser_records.json` 자동 삭제: 사용자가 둔 산출물일 수 있고, 이번 요청은 코드 제거와 신규 저장 방식 변경이므로 보류했다.
- filter/nonfilter 중복 진단 범위 재설계: 사용자가 “더 수정하지 않고 지금 그대로”라고 지정했기 때문에 이번 commit에서 제외했다.

## 검증

- `rg -n "parser_records" crawler_app tests`
  - 결과: 코드/테스트 경로에서 기존 명칭 참조 없음
- `.\.venv\Scripts\python.exe -m unittest tests.test_workflow.WorkflowDownloadTests.test_filter_split_removes_unclassified_root_parser_outputs tests.test_workflow.WorkflowDownloadTests.test_run_workflow_config_stops_current_parser_term_on_previous_workflow_record_duplicate tests.test_orchestration.OrchestrationTests.test_duplicate_key_uses_detail_url_for_parser_workflow_records`
  - 결과: `Ran 3 tests ... OK`
- `.\.venv\Scripts\python.exe -m unittest discover -s tests`
  - 결과: `Ran 184 tests ... OK`

## 의도적으로 제외한 파일

다음 dirty 파일은 이번 변경의 commit 대상에서 제외한다.

- `configs/구글.json`
- `configs/기후에너지부_보도자료.json`
- `configs/네이버뉴스.json`
- `configs/다음.json`
- `configs/마켓인사이트.json`
- `configs/시그널.json`
- `configs/연합뉴스.json`
- `tests/test_orchestration.py`
- `tests/test_workflow.py`

테스트 파일은 검증 보강용 변경이 포함되어 있으나, 현재 `$git-push-change-log` 규칙상 `tests/`는 기본적으로 stage하지 않는다. config 변경은 별도 작업 흐름의 dirty 상태로 보고 이번 parser_records 제거 commit에는 포함하지 않는다.

## ignore 확인

`git status --short --ignored` 기준으로 다음 로컬 산출물/비밀/런타임 파일은 ignored 상태임을 확인했다.

- `.env`
- `.venv/`
- harness/session 문서
- `outputs/`
- `orchestration_state/`
- `runtime/`
- `logs/`
- `qa-artifacts/`
- `imsi/`
- `__pycache__/`

## 남은 리스크

- 기존 로컬 outputs에 이미 생성된 `parser_records.json` 파일은 남아 있을 수 있다. 새 코드에서는 읽거나 새로 만들지 않는다.
- filter/nonfilter 양쪽 `workflow_records.json`을 모두 중복 기준에 포함하는 정책은 그대로 유지된다. 필터 조건 변경 시 nonfilter 기록이 재분류를 막는 문제는 별도 정책 결정이 필요하다.
