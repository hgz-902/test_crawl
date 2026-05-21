# Git Push Change Log - 9개 사이트 크롤링 검수 결과 및 workflow 기록 보완

- Date: 2026-05-21 12:36:35 +09:00
- Repository: C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp
- Branch: dev/crawler-current
- Upstream: origin/dev/crawler-current
- Commit message: 9개 사이트 검수 결과 및 workflow 기록 보완
- Approved push target: origin/dev/crawler-current

## Request

프롬프트 전문은 별도 포함하지 않음. 사용자가 이번 push record에는 변경사항 대신 9개 사이트 검수 결과와 결정 필요 사항을 기록하도록 요청함.

## Changed Files

~~~text
 M configs/구글.json
 M configs/기후에너지부_보도자료.json
 M configs/네이버뉴스.json
 M configs/다음.json
 M configs/마켓인사이트.json
 M configs/산업부_보도자료.json
 M configs/시그널.json
 M configs/연합뉴스.json
 M configs/인베스트조선.json
 M crawler_app/orchestration.py
 M crawler_app/workflow.py
 M tests/test_orchestration.py    # intentionally excluded
 M tests/test_workflow.py         # intentionally excluded
?? prompts/20260521_105737_workflow_records_prepend_order.md # intentionally excluded
~~~

## Diff Stat

~~~text
 configs/구글.json                  |  5 ++-
 configs/기후에너지부_보도자료.json |  8 ++--
 configs/네이버뉴스.json            |  5 ++-
 configs/다음.json                  |  6 +--
 configs/마켓인사이트.json          | 10 ++---
 configs/산업부_보도자료.json       |  8 ++--
 configs/시그널.json                |  6 +--
 configs/연합뉴스.json              |  3 +-
 configs/인베스트조선.json          |  6 +--
 crawler_app/orchestration.py       | 15 +------
 crawler_app/workflow.py            | 85 +++++++++++++++++++++++++++++++++++---
 tests/test_orchestration.py        |  2 +-
 tests/test_workflow.py             | 74 ++++++++++++++++++++++++++++++++-
 13 files changed, 186 insertions(+), 47 deletions(-)
warning: in the working copy of 'crawler_app/orchestration.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'crawler_app/workflow.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/test_orchestration.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/test_workflow.py', LF will be replaced by CRLF the next time Git touches it
~~~

## Staged Diff Stat

~~~text

~~~

## Why These Changes Were Made

9개 사이트에 대해 테스트 모두 완료했습니다. 기본적인 검색과 중복 진단 제거 및 스킵, workflow_records 에 최신 순으로 위에서부터 정렬되는 건 잘 됩니다.
아래는 결정해야하는 사항입니다.

1. 현재 중복 진단 로직이 nonfilter 폴더의 workflow_records.json까지 참조하는 것으로 보여, 해당 파일을 중복 판단 기준에 포함할지 여부를 결정해야 합니다.
nonfilter 수집 자료도 데이터 저장소에 넣어야 한다면 nonfilter 수집 자료는 보존하되, 필터링된 수집 로직의 중복 진단에는 nonfilter/workflow_records.json을 제외하는 방향이 더 안전해 보입니다.
만약 데이터 저장소에 넣지 않을 것이라면, nonfilter 폴더는 제거해도 되지 않을까 싶습니다.

2. 검색어 또는 필터링 조건이 변경될 때 기존 workflow_records.json의 filter_terms가 마지막 실행값으로 덮어써져, 실제 records와 메타데이터가 불일치할 수 있습니다.
따라서 검색어/필터링 조건별로 저장 경로를 분리하거나, 각 record에 수집 당시 조건을 함께 저장하는 방식으로 수정이 필요합니다.

3. 최신기사 정리 기준도 조건별로 분리할지, 전체 수집 데이터를 통합해서 정리할지 명확히 결정해야 합니다. 왜냐하면 필터링 값과 검색어 값이 바뀌면 최신 기사가 쌓이듯, 이전의 수집 자료 위쪽에 쌓이기 때문입니다.

## Design Notes And Tradeoffs



### Existing Code Changed Because

workflow_records.json이 기존 records 뒤에 새 records를 붙이면 사용자가 최신 수집분을 위에서 확인하기 어렵고, duplicate-stop snapshot 복구 경로와 일반 저장 경로의 병합 순서도 달라질 수 있어 공통 병합 함수를 같은 원칙으로 맞췄습니다.

### Idea Or Constraint Behind The Change

기본 원칙은 새로 수집된 non-duplicate records를 기존 records 앞쪽에 누적하는 것입니다. 다만 네이버/구글/다음 같은 parser/API형은 pubDate 등 신뢰 가능한 날짜 필드가 있으므로 새 실행 내부 records에 한해 최신순 정렬을 적용했습니다.

### Advantages

- 사용자가 workflow_records.json을 열었을 때 최신 수집 자료를 바로 위에서 확인할 수 있습니다.
- 기존 records의 상대 순서를 유지해 과거 기록을 불필요하게 재정렬하지 않습니다.
- 중복 제거 기준은 기존 URL/detail_url/Google description 기반 로직을 그대로 유지합니다.

### Disadvantages Or Costs

- filter_terms 메타데이터는 snapshot 단위로 남기 때문에 필터 조건이 바뀐 뒤 기존 records와 메타데이터가 불일치할 수 있습니다.
- nonfilter records를 중복 판단에 계속 포함할 경우, 필터 조건 변경 후 기존 nonfilter 자료를 새 filter 자료로 재분류하지 못할 수 있습니다.

### Alternatives Considered Or Deferred

- 전체 records를 날짜 기준으로 강제 재정렬하는 방안은 일반 사이트 날짜 필드가 없거나 불안정해 보류했습니다.
- nonfilter/workflow_records.json을 중복 인덱스에서 제외하는 방안은 데이터 저장소 정책 결정이 필요해 이번 커밋에서는 보류했습니다.
- 검색어/필터 조건별 저장 경로 분리 또는 record별 조건 메타데이터 추가는 별도 설계 결정 후 처리할 사항으로 남겼습니다.

### Collection Or Runtime Structure Notes

현재 일반 사이트는 item을 순차 수집하고, 수집 완료 후 filter/nonfilter 분리와 workflow_records 저장을 수행합니다. 중복 판단은 record append 시점에 기존 workflow_records.json 인덱스를 참고하며, 현재 구조에서는 filter와 nonfilter snapshot이 모두 중복 판단 후보가 될 수 있습니다.

## Implementation Summary

- 9개 사이트 검수 과정에서 조정된 config 값을 함께 반영합니다.
- workflow_records 신규 non-duplicate records가 기존 records 앞쪽에 누적되도록 공통 병합 로직을 보완했습니다.
- duplicate-stop snapshot 복구 병합도 workflow 병합 함수와 같은 순서를 사용하도록 맞췄습니다.
- parser/API형 records는 새 실행 내부에서 날짜 필드가 있을 때 최신순으로 정렬되게 했습니다.

## Validation

python -m unittest discover -s tests: Ran 184 tests OK. 사용자가 9개 사이트 기본 검색, 중복 진단 제거/스킵, workflow_records 최신순 누적을 검수 완료.

## Remaining Risks

nonfilter workflow_records를 중복 판단 기준에 포함할지, 검색어/필터 조건별 기록 분리 정책, 최신기사 정리 기준은 추가 결정 필요.

## Files Intentionally Excluded

- tests/test_orchestration.py: 검증 중 수정된 테스트 파일이나, 스킬 규칙에 따라 tests/는 기본 push 대상에서 제외.
- tests/test_workflow.py: 검증 중 수정된 테스트 파일이나, 스킬 규칙에 따라 tests/는 기본 push 대상에서 제외.
- prompts/20260521_105737_workflow_records_prepend_order.md: 이번 push record에 프롬프트 전문을 포함하지 말라는 사용자 요청에 맞춰 제외.
- .env, .venv, logs, outputs, runtime, orchestration_state, qa-artifacts, imsi, harness/session-local docs: .gitignore로 제외되는 로컬/검증/비밀/런타임 산출물.

## Remote

~~~text
origin	https://github.com/K-Ternag/crawlService.git (fetch)
origin	https://github.com/K-Ternag/crawlService.git (push)
~~~

## Push Command

~~~powershell
git push origin dev/crawler-current
~~~

## Push Result

Pending at commit time. Push command will be executed immediately after commit; final result will be reported in the chat.
