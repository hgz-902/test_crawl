# Git Push Change Log - 마켓인사이트 pagination 수집 개선

- Date: 2026-05-14 20:18:23 +09:00
- Repository: C:\AI_JOB\firstproject\crawler_project\crawlService-main
- Branch: dev/crawler-current
- Upstream: origin/dev/crawler-current
- Commit message: 마켓인사이트 pagination 수집 개선
- Approved push target: origin/dev/crawler-current

## Request

요청 및 판단 흐름:

- 마켓인사이트 검색 결과에서 `최태원`, `SK`를 예시로 기사 URL에 접근해 제목과 본문을 수집하는 크롤러 항목이 필요했다.
- 처음에는 일반 뉴스형 config-only 접근으로 시작했고, 이후 사용자가 직접 실행하면서 pagination 동작이 기대와 다르다는 점을 확인했다.
- 사용자가 원한 것은 별도 `page` 실행 단계를 추가하는 것이 아니라, 기존 `open_detail` 행의 mode를 `pagination`으로 선택하고 limit에 페이지 수를 넣으면 1페이지부터 해당 페이지까지 모두 수집되는 동작이었다.
- output 누적 구조 변경도 검토했지만, 이번 변경에서는 취소하고 기존 generic 저장 구조를 유지하기로 했다.
- `next_button`은 남겨두되, URL page 파라미터가 명확한 사이트에 더 적합한 `page_number`를 기본값으로 바꿨다.

## Changed Files

~~~text
 M DECISION_RULING.md
 M RUN_CONTEXT.md
 M TASK_PLAN.md
 M configs/산업부_보도자료.json
 M crawler_app/workflow.py
 M static/app.js
 M templates/editor.html
 M tests/test_workflow.py
?? configs/마켓인사이트.json
?? pr_body.md
~~~

## Diff Stat

~~~text
 DECISION_RULING.md           |  35 +++++++++++++
 RUN_CONTEXT.md               |  39 +++++++++++++++
 TASK_PLAN.md                 |  37 ++++++++++++++
 configs/산업부_보도자료.json |   9 ++--
 crawler_app/workflow.py      | 116 +++++++++++++++++++++++++++++++++++++++++-
 static/app.js                |   6 +--
 templates/editor.html        |   4 +-
 tests/test_workflow.py       | 117 +++++++++++++++++++++++++++++++++++++++++++
 8 files changed, 351 insertions(+), 12 deletions(-)
warning: in the working copy of 'DECISION_RULING.md', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'RUN_CONTEXT.md', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'TASK_PLAN.md', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'crawler_app/workflow.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'static/app.js', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'templates/editor.html', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/test_workflow.py', LF will be replaced by CRLF the next time Git touches it
~~~

## Staged Diff Stat

~~~text

~~~

## Why These Changes Were Made

기존 UI는 실행 단계의 `open_detail` 행에서 `items`와 `pagination` 모드를 선택할 수 있게 되어 있었지만, workflow 엔진은 `open_detail.pagination`을 "limit만큼 페이지를 돌며 각 페이지의 아이템을 수집"하는 의미로 처리하지 못했다. 이 때문에 사용자가 UI에서 pagination을 선택해도 원하는 페이지 수집 흐름이 나오지 않았다.

마켓인사이트는 `https://marketinsight.hankyung.com/search?keyword={search_term}`에 `page=1`, `page=2`를 붙여 페이지 이동이 가능한 사이트이므로, `page_number` 기반 pagination이 가장 단순하고 검증 가능한 구조였다.

## Design Notes And Tradeoffs

기존 UI에는 open_detail 행에서 items/pagination mode를 선택하는 기능이 있었지만, 원본 next_button 구조는 별도 page 단계와 item 단계가 분리된 테스트 중심 흐름이었다. 사용자가 기대한 동작은 open_detail 하나에서 pagination을 선택하고 limit을 페이지 수로 입력하면 1..N 페이지의 기사 목록을 모두 수집하는 것이므로, 별도 page 단계를 추가하는 대안은 철회했다. page_number는 URL page 파라미터가 명확한 사이트에서 사용자가 이해하기 쉽고 XPath 변경만으로 대응하기 좋아 기본값으로 삼았다. next_button은 AJAX/버튼형 사이트를 위해 유지하지만 기본값에서는 제외했다.

### Existing Code Changed Because

`run_workflow_config`의 기존 pagination 경로는 "pagination step"과 "item step"이 분리된 구조를 전제로 했다. 그러나 UI가 이미 `open_detail` 자체의 mode 선택을 제공하고 있으므로, `open_detail`이 `xpath/xpath_2`를 가진 pagination loop일 때는 별도 page step 없이 page URL을 순회하고 각 페이지의 item XPath를 반복해야 했다.

### Idea Or Constraint Behind The Change

마켓인사이트처럼 URL page 파라미터가 있는 뉴스형 사이트는 소스코드를 사이트별로 늘리지 않고, 시작 URL과 XPath config만으로 운영하는 것이 유지보수 비용이 낮다. 그래서 공통 workflow에 "paginated item loop"를 추가하고, config는 기존 3단계 모양인 `open_detail`, `extract_title`, `extract_body`를 유지했다.

### Advantages

- 사용자가 UI에서 보던 기존 실행 단계 모델을 유지한다.
- 별도 `page` 행을 추가하지 않아 설정 화면이 단순하다.
- `open_detail.loop_limit`이 페이지 수라는 의미로 일관된다.
- HTML 구조가 바뀌면 기사 목록/제목/본문 XPath만 UI에서 바꾸면 된다.
- `next_button`은 제거하지 않아 버튼형 사이트 대응 여지를 남긴다.

### Disadvantages Or Costs

- 공통 workflow에 새 분기와 테스트가 추가됐다.
- `open_detail.pagination`의 현재 구현은 `page_number`에 초점을 맞췄고, `next_button`은 기존 분리형 pagination 흐름을 유지한다.
- generic 실행 결과 manifest는 기존처럼 `filter\workflow_records.json`에 저장되므로 반복 실행 시 manifest가 덮일 수 있다.

### Alternatives Considered Or Deferred

- 별도 `page` 실행 단계를 추가하는 방법: 사용자가 원한 UI 흐름과 달라 철회했다.
- output을 `runs\YYYYMMDD_n` 형태로 누적하는 방법: 검토했지만 이번 변경에서는 취소하고 기존 저장 구조를 유지했다.
- `next_button`을 제거하는 방법: 기능을 바로 제거하면 기존/미래 버튼형 사이트 대응이 줄어들어 유지했다.
- 사이트별 전용 parser를 만드는 방법: 마켓인사이트는 일반 HTML 뉴스형 사이트라 과한 변경으로 판단했다.

### Collection Or Runtime Structure Notes

- `open_detail.loop_mode=pagination`, `pagination_mode=page_number`, `loop_limit=N`이면 내부적으로 `page=1..N` URL을 생성해 각 페이지를 연다.
- 각 페이지에서 `open_detail.xpath`와 `open_detail.xpath_2`로 반복 item XPath를 추론해 기사 상세로 들어간다.
- 상세 페이지에서 `extract_title`, `extract_body`를 실행해 텍스트 산출물을 저장한다.
- 현재 `configs\마켓인사이트.json`에는 `최태원`, `SK` 외에 SK 계열/대한상의 검색어가 포함되어 있다. 이는 현재 config 파일 상태를 그대로 포함한 것이며, 필요하면 push 전 검색어 목록만 조정할 수 있다.

## Implementation Summary

- `configs\마켓인사이트.json` 추가.
- `crawler_app/workflow.py`에 `open_detail` 기반 paginated item loop 경로 추가.
- `static/app.js`, `templates/editor.html`에서 pagination 기본값을 `page_number`로 변경.
- workflow 단위 테스트 3건 추가.
- Alpha 상태 문서에 판단, 검증, 리스크 기록.

## Validation

node --check static\app.js: pass. .venv\Scripts\python.exe -m unittest discover -s tests: 127 tests pass. Live proof qa-artifacts\marketinsight-open-detail-pagination-20260514: 60 records, 120 title/body extracts, 0 downloads, no errors. UI proof qa-artifacts\marketinsight-open-detail-pagination-ui-20260514: open_detail/extract_title/extract_body 3단계, open_detail pagination/page_number/limit=2 확인.

## Remaining Risks

마켓인사이트 HTML 구조가 바뀌면 기사 목록/제목/본문 XPath를 UI에서 갱신해야 한다. generic workflow_records.json은 기존 구조처럼 반복 실행 시 덮어써질 수 있다. next_button은 유지했지만 이번 검증의 주 경로는 page_number다.

## Files Intentionally Excluded

- `configs/산업부_보도자료.json`: 이번 마켓인사이트/pagination 변경과 별개인 기존 dirty file.
- `pr_body.md`: 이번 커밋 대상이 아닌 기존 PR 본문 초안 파일.
- `qa-artifacts/**`: 라이브/GUI 검수 증거는 경로만 기록하고 산출물 파일 자체는 커밋하지 않음.
- `outputs/**`: 실제 크롤링 출력물은 커밋하지 않음.
- `.env` 및 credential 파일: 포함하지 않음.

## Remote

~~~text
origin	https://github.com/K-Ternag/crawlService (fetch)
origin	https://github.com/K-Ternag/crawlService (push)
~~~

## Push Command

~~~powershell
git push origin dev/crawler-current
~~~

## Push Result

Not pushed by Codex. User will push manually after reviewing the local commit.
