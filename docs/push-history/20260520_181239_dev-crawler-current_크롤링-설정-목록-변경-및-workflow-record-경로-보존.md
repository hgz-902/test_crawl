# Git Push Change Log - 크롤링 설정 목록 변경 및 workflow record 경로 보존

- Date: 2026-05-20 18:12:39 +09:00
- Repository: C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp
- Branch: dev/crawler-current
- Remote target: origin/dev/crawler-current
- Commit message: 크롤링 설정 목록 변경 및 workflow record 경로 보존
- Approved push target: https://github.com/K-Ternag/crawlService.git / dev/crawler-current

## Request

크롤링 설정 목록에 들어가는 설정 내용을 조금씩 바꿨으니 모두 push해야 한다는 요청에 따라, 변경된 config 파일 전체와 인베스트조선 최신 기사 목록 설정 변경, 원격 병합 후 발견된 workflow_records.json `output_file` 보존 호환 수정을 함께 커밋한다.

## Changed Files

```text
configs/구글.json
configs/기후에너지부_보도자료.json
configs/네이버뉴스.json
configs/다음.json
configs/마켓인사이트.json
configs/산업부_보도자료.json
configs/시그널.json
configs/연합뉴스.json
configs/인베스트조선.json
crawler_app/workflow.py
prompts/20260520_175101_investchosun_latest_list_config.md
docs/push-history/20260520_181239_dev-crawler-current_크롤링-설정-목록-변경-및-workflow-record-경로-보존.md
```

## Why These Changes Were Made

설정 목록에서 크롤링 대상별 검색어, 필터, 수집 개수, 제목 추출 단계 등이 운영 테스트 기준으로 조정됐다. 이번 요청에서는 이 설정 변경을 모두 push해야 한다고 명시했으므로, 이전 push에서 제외했던 config 변경까지 포함한다.

추가로 다른 로컬에서 올라온 새 코드가 `workflow_records.json` 저장 시 record key를 제한하면서 parser item의 실제 JSON 파일 경로인 `output_file`이 빠지는 회귀가 있었다. Daum API 테스트에서 `workflow_records.json`의 `records[0].output_file`이 없어 실패했기 때문에, snapshot 허용 필드에 `output_file`을 되돌려 record와 실제 item 파일 경로가 계속 연결되게 했다.

## Design Notes And Tradeoffs

### Existing Code Changed Because

- 원격 병합 후 workflow snapshot 필터링이 `output_file`을 제외해 parser/API item별 JSON 파일 추적성이 깨졌다.
- 인베스트조선 홈 URL은 대표 기사와 관련 과거 기사 묶음이 섞여 최신 기사 20개 기준에 맞지 않았다.
- 설정 목록의 config 변경은 사용자가 이번 push에 포함하라고 명시했다.

### Idea Or Constraint Behind The Change

- config 기반 크롤러 구조를 유지하고, 사이트별 소스코드는 늘리지 않는다.
- 인베스트조선은 홈이 아니라 전체 기사 목록 `svc/news/list.html?catid=2`를 사용한다.
- 인베스트조선 전체 기사 목록은 1페이지당 10개만 노출되므로, `loop_limit=20`이어도 실제 수집은 10개에서 멈추는 구조를 notes에 명시한다.
- parser/API 계열 records는 `workflow_records.json` 안에서도 실제 item JSON 경로를 추적할 수 있어야 한다.

### Advantages

- 설정 목록 UI에서 저장한 변경이 원격 repo에 반영된다.
- 인베스트조선은 관련 과거 기사 대신 최신 기사 목록 1페이지의 10개를 안정적으로 수집한다.
- `workflow_records.json`과 실제 item JSON 파일 경로 연결이 유지된다.

### Disadvantages Or Costs

- 일부 config의 검색어/필터 목록은 기존 대량 운영 키워드에서 좁은 테스트/운영 확인 키워드로 축소됐다. 이번에는 사용자가 모두 push하라고 했으므로 포함했다.
- 인베스트조선 최신 20개를 실제 20개로 수집하려면 pagination 2페이지 수집이 필요하다. 이번 설정은 사용자 결정대로 1페이지 최대 10개 수집을 택했다.

### Alternatives Considered Or Deferred

- 인베스트조선 홈 URL 유지: 관련 과거 기사 섞임 때문에 배제했다.
- 인베스트조선 pagination 2페이지 수집: 사용자가 “20개를 적어도 10개만 가져오게 하면 된다”고 정리했으므로 보류했다.
- 테스트 파일 수정/추가: `$git-push-change-log` 최신 규칙에 따라 테스트 파일은 기본 push 대상에서 제외했다.

### Collection Or Runtime Structure Notes

- `configs/네이버뉴스.json`, `configs/다음.json`, `configs/구글.json`은 parser/API/RSS 실행 구조를 유지한다.
- 일반 사이트 configs는 기존 Playwright 설정 기반 실행 구조를 유지한다.
- 정부 보도자료 계열은 제목 추출 단계가 추가되고 필터/limit가 조정됐다.
- `workflow_records.json`에는 `output_file`이 남아 parser item JSON 파일과 추적 가능해야 한다.

## Implementation Summary

- Config 변경
  - 네이버뉴스/구글/다음 검색어 조정.
  - 시그널/마켓인사이트/인베스트조선 필터 조정.
  - 연합뉴스 search_terms와 loop 설정 조정.
  - 산업부/기후에너지부 보도자료 search_terms, filter_terms, loop_limit, extract_title 단계 조정.
  - 인베스트조선 시작 URL을 전체 기사 목록으로 변경하고 최신 기사 XPath로 교체.
- `crawler_app/workflow.py`
  - `workflow_records.json` 저장 시 허용 record key에 `output_file` 추가.
- Prompt 기록
  - 인베스트조선 최신 목록 설정 변경 요청을 `prompts/20260520_175101_investchosun_latest_list_config.md`에 저장.

## Cumulative Prompt / Request Flow

### 2026-05-20 - 원격 변경 병합

다른 로컬에서 새 코드가 올라왔다는 요청에 따라 `origin/dev/crawler-current`를 fetch/fast-forward했다. 병합 후 Daum API test에서 `workflow_records.json`의 `output_file` 누락 회귀가 발견되어, `workflow.py`에 `output_file` 허용 필드 복구를 적용했다.

### 2026-05-20 - 인베스트조선 최신 기사 목록 검토

인베스트조선에서 검색어 없이 최신 기사를 가져올 때 3개만 수집되는 원인을 조사했다. 홈 URL은 대표 기사 + 관련 과거 기사 묶음이 섞이는 구조였고, 전체 기사 목록 URL이 최신 기사 1페이지를 안정적으로 제공하는 것으로 확인했다.

### 2026-05-20 17:51 KST - 인베스트조선 설정 변경

원문 prompt는 `prompts/20260520_175101_investchosun_latest_list_config.md`에 저장했다. 사용자는 최신 기사가 1페이지당 10개라면 item limit에 20을 적어도 10개만 가져오게 하면 된다고 정리했고, 이에 따라 인베스트조선 시작 URL과 XPath를 전체 기사 목록 기준으로 변경했다.

### 2026-05-20 - 설정 변경 전체 push 요청

사용자가 크롤링 설정 목록에서 바뀐 설정 내용도 모두 push되어야 한다고 명시했다. 이에 따라 이전에는 제외했던 config dirty 변경도 이번 commit 대상에 포함했다.

## Validation

Config validation:

```powershell
.\.venv\Scripts\python.exe - <<'PY'
from crawler_app.workflow import validate_workflow_config, normalize_workflow_config
# changed config 9개 load/normalize/validate
PY
```

Result:

```text
OK configs/구글.json 구글
OK configs/기후에너지부_보도자료.json 기후에너지부_보도자료
OK configs/네이버뉴스.json 네이버뉴스
OK configs/다음.json 다음
OK configs/마켓인사이트.json 마켓인사이트
OK configs/산업부_보도자료.json 산업부_보도자료
OK configs/시그널.json 시그널
OK configs/연합뉴스.json 연합뉴스
OK configs/인베스트조선.json 인베스트조선
```

Unit tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 181 tests in 2.036s
OK
```

인베스트조선 실제/준실제 검증:

```text
imsi\investchosun_latest_list_config_20260520_175152\summary.json
```

확인:

```text
board_item_count = 10
raw_record_count = 10
deduped_record_count = 10
```

## Remaining Risks

- config 검색어/필터가 운영 대량 키워드에서 좁은 테스트/확인 키워드로 축소된 항목이 있다. 이번 요청에서 모두 push하라고 했으므로 포함했다.
- 인베스트조선은 전체 기사 목록 1페이지 기준 최대 10개만 수집한다. 최신 20개 전체 수집은 향후 pagination 설정이 필요하다.
- 정부 사이트는 이전에 headless 해제 필요 특이사항이 있었고, 환경/네트워크 상태에 따라 실제 브라우저 실행 검증이 추가로 필요할 수 있다.

## Files Intentionally Excluded

```text
tests/*.py
.env
.venv/
outputs/
orchestration_state/
runtime/
logs/
qa-artifacts/
imsi/
__pycache__/
.pytest_cache/
```

## Remote

```text
origin	https://github.com/K-Ternag/crawlService.git (fetch)
origin	https://github.com/K-Ternag/crawlService.git (push)
```

## Push Command

```powershell
git push origin dev/crawler-current
```

## Push Result

Pending at record creation time.
