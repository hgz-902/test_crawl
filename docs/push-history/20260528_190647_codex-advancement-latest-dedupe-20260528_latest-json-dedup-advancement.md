# Git Push Change Log - latest-json-dedup-advancement

- Date: 2026-05-28 19:06:47 +09:00
- Repository: C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp
- Branch: codex/advancement-latest-dedupe-20260528
- Upstream: (none)
- Commit message: latest.json 중복 정책 및 workflow 기록 구조 고도화
- Approved push target: origin codex/advancement-latest-dedupe-20260528

## Request

workflow_records 스키마 평탄화, latest.json 기반 경계 중복 정책, nonfilter 저장 억제, 숫자형 페이지 파라미터 중복 시 전체 페이지 시퀀스 중단을 반영한다.

## Changed Files

~~~text
 M configs/구글.json
 M configs/네이버뉴스.json
 M configs/다음.json
 M configs/산업부_보도자료.json
 M configs/시그널.json
 M configs/연합뉴스.json
 M crawler_app/duplicate_keys.py
 M crawler_app/orchestration.py
 M crawler_app/workflow.py
 M tests/test_orchestration.py
 M tests/test_workflow.py
?? prompts/20260528_145422_workflow_records_schema_and_unique_key.md
?? prompts/20260528_153650_latest_json_and_nonfilter_suppression.md
?? prompts/20260528_163025_latest_json_duplicate_policy.md
~~~

## Diff Stat

~~~text
 configs/구글.json             |   6 +-
 configs/네이버뉴스.json       |  11 +-
 configs/다음.json             |   6 +-
 configs/산업부_보도자료.json  |   2 +-
 configs/시그널.json           |   2 +-
 configs/연합뉴스.json         |   7 +-
 crawler_app/duplicate_keys.py |  49 ++-
 crawler_app/orchestration.py  | 103 +++++-
 crawler_app/workflow.py       | 840 ++++++++++++++++++++++++++++++++++++------
 tests/test_orchestration.py   | 163 +++++++-
 tests/test_workflow.py        | 457 +++++++++++++++++++++--
 11 files changed, 1463 insertions(+), 183 deletions(-)
warning: in the working copy of 'crawler_app/duplicate_keys.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'crawler_app/orchestration.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'crawler_app/workflow.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/test_orchestration.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/test_workflow.py', LF will be replaced by CRLF the next time Git touches it
~~~

## Staged Diff Stat

~~~text
configs/구글.json                                  |   6 +-
configs/네이버뉴스.json                            |  11 +-
configs/다음.json                                  |   6 +-
configs/산업부_보도자료.json                       |   2 +-
configs/시그널.json                                |   2 +-
configs/연합뉴스.json                              |   7 +-
crawler_app/duplicate_keys.py                      |  49 +-
crawler_app/orchestration.py                       | 103 ++-
crawler_app/workflow.py                            | 840 ++++++++++++++++++---
docs/push-history/20260528_190647_codex-advancement-latest-dedupe-20260528_latest-json-dedup-advancement.md | 175 +++++
prompts/20260528_145422_workflow_records_schema_and_unique_key.md | 13 +
prompts/20260528_153650_latest_json_and_nonfilter_suppression.md | 12 +
prompts/20260528_163025_latest_json_duplicate_policy.md | 11 +
13 files changed, 1085 insertions(+), 152 deletions(-)
~~~

## Why These Changes Were Made

크롤링 결과가 반복 실행될수록 `workflow_records.json`이 커지고, 기존 record 구조가 검색어/필터/최종 URL 기준으로 운영자가 필요한 자료를 찾기에 과도하게 무거웠다. 또한 최신 경계 중복 판단을 전체 기록에만 의존하면 페이지 파라미터형 수집과 일반 검색어형 수집의 중단 범위를 구분하기 어려웠다.

이번 변경은 `workflow_records.json`을 저장소 메타데이터로 쓰기 좋은 최소 구조로 평탄화하고, 별도의 `latest.json`을 최신 경계 중복 판단용 인덱스로 도입하기 위한 것이다. 특히 숫자형 search term을 페이지 파라미터로 쓰는 사이트에서는 최신 경계 중복을 만나면 현재 페이지만이 아니라 남은 페이지 순회 전체를 멈춰야 하므로 공통 workflow stop scope를 보완했다.

## Design Notes And Tradeoffs

기존 workflow_records 전체 기록만으로는 검색어/필터/페이지 파라미터별 최신 경계 판단과 저장소 메타데이터 사용을 안정적으로 만족하기 어려웠다. latest.json을 경계 인덱스로 추가하고, 실제 저장 record는 최소 메타데이터 중심으로 평탄화했다.

### Existing Code Changed Because

기존 구조는 `extracts` 내부에 title/body/date/url 등 다양한 값이 섞여 있었고, parser/API형 항목과 일반 HTML형 항목의 record shape도 달랐다. 이 상태에서는 `workflow_records.json`을 사람이 확인하거나 데이터 저장소용 메타데이터로 재사용하기 어렵다.

또한 기존 중복 진단은 전체 workflow record 또는 같은-run seen set 중심이라, 최신 경계 URL과 같은-run 중복 URL을 서로 다른 정책으로 다루기 어려웠다. 최신 경계 URL은 수집 중단 기준이고, 같은 실행 안에서 앞 검색어가 이미 수집한 URL은 skip 기준이어야 한다.

### Idea Or Constraint Behind The Change

- `workflow_records.json` record는 `record_key`, `search_term`, `filter_term`, `extract_title`, `description`, `pub_date`, `final_url`만 남겨 가볍게 유지한다.
- `record_key`는 source prefix와 URL 기반 짧은 fingerprint로 만들어 파일명과 record를 연결한다.
- `latest.json`은 검색어/필터별 최신 `final_url`만 보관해 다음 실행의 경계 중복 판단에 사용한다.
- 숫자형 search term은 일반 검색어가 아니라 페이지 파라미터로 취급한다.
- nonfilter 산출물은 저장하지 않되, nonfilter 최신 경계 URL은 `latest.json`에 남긴다.

### Advantages

- workflow record가 저장소 메타데이터로 쓰기 쉬운 형태가 된다.
- 오래된 records 전체를 훑는 비용과 운영자 확인 부담을 줄일 수 있다.
- 숫자형 페이지 파라미터, 빈 검색어, 일반 검색어의 중복 중단 범위를 분리할 수 있다.
- 필터 매칭이 record_key나 파일 경로 같은 메타데이터에 오염되지 않고 실제 콘텐츠 필드 중심으로 작동한다.
- parser/API형과 일반 HTML형이 같은 `latest.json` 경계 정책을 공유한다.

### Disadvantages Or Costs

- 기존 outputs에 남아 있는 구버전 `workflow_records.json`과 새 평탄화 record가 섞인 상태에서는 운영 전 정리/백업 판단이 필요하다.
- `latest.json`이 새로운 경계 source of truth가 되므로, 수동 테스트 때 `workflow_records.json`만 수정하면 기대 결과와 다를 수 있다.
- tests 변경은 이번 push 정책상 커밋에서 제외하므로 원격 브랜치에는 자동 테스트 fixture 보강이 포함되지 않는다.

### Alternatives Considered Or Deferred

- 전체 `workflow_records.json`만 계속 중복 판단 기준으로 쓰는 방식은 파일 크기와 경계 판단 범위 문제가 남아 보류했다.
- nonfilter 전체 산출물을 계속 저장하는 방식은 저장 공간과 운영자 확인 부담이 커서 보류했다.
- 제목 기반 중복 판단은 오탐/누락 가능성이 있어 사용하지 않았다.
- 모든 사이트를 날짜 기준으로 재정렬하는 방식은 일반 HTML 사이트의 날짜 필드 신뢰도가 낮아 사용하지 않았다.

### Collection Or Runtime Structure Notes

- 네이버/다음/구글 parser/API형은 `detail_url` 계열 URL을 최종 URL 기준으로 정규화한다.
- 일반 HTML형은 `final_url`을 기준으로 중복 판단한다.
- pageIndex 등 search term이 들어간 페이지 파라미터는 article URL 정규화 시 제거해, 글이 다음 페이지로 밀려도 같은 글로 판단되게 했다.
- 연합뉴스처럼 `search_terms=["1","2"]`가 페이지 번호인 경우 latest 경계 중복을 만나면 `numeric_page_sequence` scope로 남은 페이지 순회를 중단한다.

## Implementation Summary

workflow_records 스키마 평탄화, latest.json 기반 경계 중복 정책, nonfilter 저장 억제, 숫자형 페이지 파라미터 중복 시 전체 페이지 시퀀스 중단을 반영한다.

## Intended Staged Files

~~~text
configs/구글.json
configs/네이버뉴스.json
configs/다음.json
configs/산업부_보도자료.json
configs/시그널.json
configs/연합뉴스.json
crawler_app/duplicate_keys.py
crawler_app/orchestration.py
crawler_app/workflow.py
prompts/20260528_145422_workflow_records_schema_and_unique_key.md
prompts/20260528_153650_latest_json_and_nonfilter_suppression.md
prompts/20260528_163025_latest_json_duplicate_policy.md
docs/push-history/20260528_190647_codex-advancement-latest-dedupe-20260528_latest-json-dedup-advancement.md
~~~

## Validation

python -m unittest discover -s tests: 193 tests OK; python -m compileall crawler_app tests: OK; 연합뉴스 latest.json 기준 stop_scope numeric_page_sequence 확인.

## Remaining Risks

기존 outputs와 workflow_records.json이 새 스키마와 섞여 있을 수 있어 운영 전 기존 산출물 정리/백업 정책 확인이 필요하다. tests/ 변경은 스킬 정책상 이번 커밋에서 제외한다.

## Files Intentionally Excluded

- `tests/test_workflow.py`, `tests/test_orchestration.py`: 로컬 검증 fixture 보강 파일. 현재 `git-push-change-log` 운영 규칙상 tests 변경은 명시 요청 없이는 push하지 않는다.
- `.env`, `.venv/`, `outputs/`, `runtime/`, `logs/`, `qa-artifacts/`, `orchestration_state/`, `imsi/`, `docs/codex-app/`, `codex_app_agents.md`: 로컬 실행/하네스/비밀정보/산출물로 `.gitignore` 대상이다.

## 누적 프롬프트 / 변경 흐름 추가 기록

- workflow_records 구조 보완: `extracts` 내부 값을 평탄화하고, 각 record에는 `record_key`, `search_term`, `filter_term`, `extract_title`, `description`, `pub_date`, `final_url`만 남기도록 요청됨. `pubDate`는 `pub_date`로 통일하고, 일반 사이트는 수집 시각을 KST email-date 형식으로 기록한다.
- record_key 및 파일명 연결: URL 정규화 후 source prefix와 짧은 fingerprint를 조합한 고유 record_key를 생성하고, 관련 text/item 파일명에도 같은 key를 적용하도록 요청됨.
- filter 오염 방지: record_key나 파일 경로에 포함된 문자열 때문에 필터가 오탐되지 않도록 실제 콘텐츠 필드 중심으로 필터 판정하게 수정함.
- latest.json 도입: `workflow_records.json`과 같은 depth에 `latest.json`을 추가하고, 검색어/필터별 최신 `final_url`만 보관해 이후 중복 경계 판단에 사용하도록 요청됨.
- nonfilter 저장 억제: nonfilter 전체 산출물은 저장하지 않고, nonfilter 최신 경계 URL만 `latest.json`에 남기도록 요청됨.
- latest.json 중복 정책: 숫자형 search term은 페이지 파라미터로 보고 필터별 latest record 중 하나라도 final_url이 일치하면 수집 중단, 일반 검색어는 search_term별 latest boundary로 판단, 같은 실행 안의 다른 일반 검색어 중복은 skip만 하도록 요청됨.
- 연합뉴스형 페이지 순회 보완: 숫자형 페이지 파라미터에서 1페이지 경계 중복 후 2페이지로 넘어가면 안 되므로 `numeric_page_sequence` stop scope를 추가함.

## Remote

~~~text
hgz	https://github.com/hgz-902/test_crawl.git (fetch)
hgz	https://github.com/hgz-902/test_crawl.git (push)
origin	https://github.com/K-Ternag/crawlService.git (fetch)
origin	https://github.com/K-Ternag/crawlService.git (push)
~~~

## Push Command

~~~powershell
git push -u origin codex/advancement-latest-dedupe-20260528:codex/advancement-latest-dedupe-20260528
~~~

## Push Result

Pending before commit/push.
