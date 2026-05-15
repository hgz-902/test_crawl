# Git Push Change Log - 연합뉴스 최신뉴스 수집 설정 개선

- Date: 2026-05-15 09:35:55 +09:00
- Repository: C:\AI_JOB\firstproject\crawler_project\crawlService-main
- Branch: dev/crawler-current
- Upstream: origin/dev/crawler-current
- Commit message: 연합뉴스 최신뉴스 수집 설정 개선
- Approved push target: `origin dev/crawler-current:dev/crawler-current`

## Request

연합뉴스 기존 설정을 최신뉴스 목록 직접 수집 구조로 갱신했다. 검색어 없이 page=1..20 최신뉴스 목록을 돌며 기사 상세 제목과 본문을 저장하고, 사용자가 UI에서 items/pagination 모드를 계속 조정할 수 있게 concrete page=1 시작 URL을 사용했다.

## Changed Files

~~~text
 M DECISION_RULING.md
 M RUN_CONTEXT.md
 M TASK_CLASSIFICATION.md
 M TASK_CONTRACT.md
 M TASK_PLAN.md
 M configs/더벨.json
 M configs/산업부_보도자료.json
 M configs/연합뉴스.json
 M configs/인베스트조선.json
?? pr_body.md
~~~

## Diff Stat

~~~text
 DECISION_RULING.md           | 31 +++++++++++++++++++++++++++++
 RUN_CONTEXT.md               | 33 +++++++++++++++++++++++++++++++
 TASK_CLASSIFICATION.md       |  8 ++++++++
 TASK_CONTRACT.md             | 47 ++++++++++++++++++++++++++++++++++++++++++++
 TASK_PLAN.md                 | 33 +++++++++++++++++++++++++++++++
 configs/더벨.json            |  4 ++--
 configs/산업부_보도자료.json |  9 ++++-----
 configs/연합뉴스.json        | 33 ++++++++++++++++++++-----------
 configs/인베스트조선.json    | 14 +++++++++++--
 9 files changed, 192 insertions(+), 20 deletions(-)
warning: in the working copy of 'DECISION_RULING.md', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'RUN_CONTEXT.md', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'TASK_CLASSIFICATION.md', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'TASK_CONTRACT.md', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'TASK_PLAN.md', LF will be replaced by CRLF the next time Git touches it
~~~

## Staged Diff Stat

~~~text

~~~

## Why These Changes Were Made

연합뉴스는 이번 slice에서 별도 검색어 없이 최신뉴스 목록 URL에 있는 모든 기사 목록을 수집해야 했다. 기존 원본 설정은 `https://www.yna.co.kr/news`에서 `items` 모드로 3건만 추출하는 예시형 설정이어서, 페이지가 있는 최신뉴스 전체 수집 요구를 만족하지 못했다.

사용자는 `items`와 `pagination` 설정을 UI에서 계속 조정할 수 있어야 하므로, 시작 URL을 `{page_number}` placeholder가 들어간 URL로 저장하지 않고 concrete page 1 URL로 저장했다. 이렇게 하면 `items` 모드는 1페이지를 그대로 쓰고, `pagination` 모드는 기존 workflow의 page query rewrite 기능으로 `page=1..20`을 순회한다.

## Design Notes And Tradeoffs

Source-change guardrail applied: this was kept config-only after checking the origin Yonhap baseline. The key design choice was to use the existing generic news execution-step workflow instead of adding a provider parser or shared source change. The article list XPath indexes article-bearing li[@data-cid] rows because raw li[n] hits non-article/ad gaps and stopped loop inference early.

### Existing Code Changed Because

공유 Python/JS 소스코드는 변경하지 않았다. 이번 변경은 기존 연합뉴스 config와 Alpha 상태 문서만 갱신했다.

설정 구조는 바뀌었다. 기존 `download_text` 단일 추출은 제목/본문 분리가 어렵고 최신뉴스 전체 페이지 검수 결과를 설명하기 불편했다. 그래서 다른 일반 뉴스형 사이트와 같은 `open_detail`, `extract_title`, `extract_body` 구조로 맞췄다.

### Idea Or Constraint Behind The Change

핵심 제약은 "검색어 없이 최신뉴스 목록 페이지 전체를 크롤링하되, 사용자가 UI에서 item/pagination 모드를 바꿀 수 있어야 한다"는 점이었다.

또 하나의 현장 제약은 연합뉴스 목록 DOM 안에 광고/비기사 row가 섞여 있다는 점이었다. raw `li[n]` XPath는 5번째 기사 뒤의 비기사 row에서 loop inference가 끊겼다. 그래서 실제 기사 row에 붙은 `li[@data-cid][n]`를 반복 기준으로 사용했다.

### Advantages

- 소스코드 변경 없이 config/XPath만으로 요구사항을 충족한다.
- 기존 generic news workflow와 storage shape를 유지한다.
- `items` 모드는 page 1에서 지정 건수만 수집하고, `pagination` 모드는 `loop_limit=20`을 페이지 수로 해석해 전체 페이지를 수집한다.
- 제목과 본문이 별도 파일로 남아 QA와 후속 검토가 쉬워진다.
- 본문 추출에서 기자 구독 UI, aside, 저작권/제보 문구를 config `exclude_xpath`로 제거하므로 사이트 구조 변경 시 UI에서 조정할 수 있다.

### Disadvantages Or Costs

- 현재 마지막 페이지 20은 2026-05-15 live DOM 기준이다. 연합뉴스가 최신뉴스 보관/페이지 정책을 바꾸면 `loop_limit` 재확인이 필요하다.
- XPath가 연합뉴스 HTML 구조에 의존하므로 사이트 개편 시 UI에서 수정해야 한다.
- 20페이지 전체 검수는 기사 500건 상세를 실제로 열기 때문에 실행 시간이 길다.

### Alternatives Considered Or Deferred

- provider parser 또는 공유 workflow source 변경은 보류했다. 기존 generic execution-step 구조로 충분히 처리 가능했고, 소스코드 변경을 최소화하는 팀 원칙에 맞지 않았다.
- `{page_number}` placeholder를 시작 URL에 넣는 방식은 보류했다. 이전 Signal 작업에서 확인했듯이 placeholder URL은 사용자가 `items` 모드로 바꿨을 때 깨질 수 있다.
- raw `li[n]` XPath는 보류했다. 연합뉴스 목록 중간의 비기사 row 때문에 5건까지만 수집되는 문제가 확인됐다.

### Collection Or Runtime Structure Notes

- 저장 구조는 원본 연합뉴스형 generic news 구조를 유지한다: `<output_dir>\filter\<NNN_default>\texts\YYYYMMDD` 및 `<output_dir>\filter\workflow_records.json`.
- 검색어 목록은 비워둔다. 이 slice는 검색 결과가 아니라 최신뉴스 listing 자체를 수집한다.
- `open_detail.loop_limit=20`은 현재 연합뉴스 최신뉴스의 페이지 수다.
- UI proof에서 Naver/Daum provider-specific panel이 나타나지 않는 것을 확인했다.

## Implementation Summary

연합뉴스 기존 설정을 최신뉴스 목록 직접 수집 구조로 갱신했다. 검색어 없이 page=1..20 최신뉴스 목록을 돌며 기사 상세 제목과 본문을 저장하고, 사용자가 UI에서 items/pagination 모드를 계속 조정할 수 있게 concrete page=1 시작 URL을 사용했다.

## Validation

연합뉴스 전체 live proof: qa-artifacts\yonhap-live-20260515\summary.json, 500 records across pages 1..20, 500 title files, 500 body files, no workflow errors. Items-mode proof: qa-artifacts\yonhap-items-mode-20260515\summary.json, 3 records from page 1. UI proof: qa-artifacts\yonhap-ui-20260515\ui_result.json and editor-3020.png. Regression: .venv\Scripts\python.exe -m unittest discover -s tests => 127 tests pass; node --check static\app.js => pass.

## Remaining Risks

Yonhap latest-news page count is currently 20 and may change if Yonhap changes retention/pagination. HTML/XPath may drift. Generic workflow_records.json remains origin-compatible but not run-versioned.

## Files Intentionally Excluded

- `configs/더벨.json`: 기존 dirty file, 이번 연합뉴스 slice 범위 밖.
- `configs/산업부_보도자료.json`: 기존 dirty file, 이번 연합뉴스 slice 범위 밖.
- `configs/인베스트조선.json`: 기존 dirty file, 이번 연합뉴스 slice 범위 밖.
- `pr_body.md`: 기존 untracked PR helper file, 이번 연합뉴스 slice 범위 밖.
- `qa-artifacts/yonhap-*`: live proof output and screenshots are validation artifacts, not intended for this commit unless separately requested.
- Workspace memory files outside this product repo: session memory was updated for continuity but is not part of the product git repository.

## Remote

~~~text
origin	https://github.com/K-Ternag/crawlService (fetch)
origin	https://github.com/K-Ternag/crawlService (push)
~~~

## Push Command

~~~powershell
git push origin dev/crawler-current:dev/crawler-current
~~~

## Push Result

Not pushed yet in this preparation step. The commit is prepared locally; user owns the final push unless explicitly requested otherwise.
