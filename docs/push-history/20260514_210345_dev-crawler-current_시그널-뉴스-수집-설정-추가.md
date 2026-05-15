# Git Push Change Log - 시그널 뉴스 수집 설정 추가

- Date: 2026-05-14 21:03:45 +09:00
- Repository: C:\AI_JOB\firstproject\crawler_project\crawlService-main
- Branch: dev/crawler-current
- Upstream: origin/dev/crawler-current
- Commit message: 시그널 뉴스 수집 설정 추가
- Approved push target: origin/dev/crawler-current

## Request

시그널을 기존 크롤러 프로그램에서 실행할 수 있게 만들고, 실제 실행 실패 원인까지 확인해 `items`와 `pagination` 모드가 모두 동작하는 상태로 push 직전까지 준비한다.

## Changed Files

```text
DECISION_RULING.md
RUN_CONTEXT.md
TASK_CONTRACT.md
TASK_PLAN.md
configs/시그널.json
docs/push-history/20260514_210345_dev-crawler-current_시그널-뉴스-수집-설정-추가.md
```

## Diff Stat

```text
DECISION_RULING.md | Signal ruling and failure diagnosis
RUN_CONTEXT.md     | Signal checkpoint and mode proof
TASK_CONTRACT.md   | Signal contract and risk references
TASK_PLAN.md       | Signal plan, validation, and follow-up
configs/시그널.json | new Signal crawler config
docs/push-history/20260514_210345_dev-crawler-current_시그널-뉴스-수집-설정-추가.md | this push record
```

## Why These Changes Were Made

시그널은 API/RSS형이 아니라 검색 결과 HTML과 기사 상세 HTML을 가진 뉴스형 사이트다. 원본 연합뉴스형 실행단계 구조로 처리할 수 있어 shared source code, UI source, parser provider, storage contract를 변경하지 않고 config만 추가했다.

처음 검수한 `pagination` 모드는 성공했지만, 사용자 실행 후 실패 로그를 확인하니 저장된 설정이 `items` 모드가 되었을 때 시작 URL의 `page={page_number}` placeholder가 치환되지 않아 검색 결과가 0건이 되었다. `items` 모드는 현재 시작 URL의 한 페이지에서 N개를 수집하는 모드이므로 시작 URL은 실제 접근 가능한 `page=1`이어야 한다. 그래서 Signal 시작 URL을 `https://signal.sedaily.com/search?word={search_term}&page=1`로 조정했다. 이렇게 하면 `items`는 1페이지에서 동작하고, `pagination`은 workflow가 `page` query parameter를 1, 2, 3으로 바꿔 동작한다.

## Design Notes And Tradeoffs

### Existing Code Changed Because

이번 slice에서는 shared source code를 변경하지 않았다. 필요한 변경은 모두 `configs\시그널.json`과 상태 문서에 한정했다.

### Idea Or Constraint Behind The Change

새 HTML 뉴스 사이트는 먼저 원본 연합뉴스형 실행단계 구조로 표현 가능한지 확인한다. 시그널은 `word` 검색어 파라미터와 `page` 페이지 파라미터가 있고, 결과 목록이 `ul.news_list > li` 구조라 generic `open_detail` loop로 충분했다.

### Advantages

- 기존 generic workflow를 그대로 사용하므로 source churn이 없다.
- UI에서 XPath, 검색어, mode, limit을 계속 수정할 수 있다.
- `page=1` 시작 URL 덕분에 `items`와 `pagination` 모두 동작한다.
- 회원 전용 항목은 config `exclude_xpath`로 건너뛰어 가입/결제 안내문이 본문으로 저장되는 일을 피한다.

### Disadvantages Or Costs

- 회원 전용 기사는 현재 config에서 수집 대상에서 제외된다.
- 시그널 HTML 구조가 바뀌면 XPath를 UI에서 수정해야 한다.
- generic 뉴스 저장 구조는 원본 연합뉴스 기준을 따르므로 `filter\workflow_records.json`은 run-versioned manifest가 아니다.
- 현재 저장된 config에는 `최태원`, `SK` 외 추가 SK-family 검색어가 포함되어 있으나, 전체 live proof는 초기 요청 기준인 `최태원`, `SK` 모드 검증으로 수행했다.

### Alternatives Considered Or Deferred

- provider parser 신규 작성: 불필요해서 배제했다. API/RSS/전용 JSON endpoint가 필요한 구조가 아니었다.
- source-code에서 `{page_number}`를 items 모드에도 치환: 기존 semantics를 바꾸는 shared behavior change라 배제했다. items 모드는 한 페이지 N개 수집, pagination 모드는 페이지 순회라는 기존 구분을 유지하는 편이 안전하다.
- 회원 전용 기사 로그인 처리: credentials/session 정책이 필요하므로 이번 slice에서는 제외했다.

### Collection Or Runtime Structure Notes

- start URL: `https://signal.sedaily.com/search?word={search_term}&page=1`
- initial proof terms: `최태원`, `SK`
- current config may include additional SK-family terms configured in the UI.
- steps: `open_detail`, `extract_title`, `extract_body`
- default mode: `open_detail.loop_mode=pagination`, `pagination_mode=page_number`, `loop_limit=2`
- items compatibility: same start URL works as concrete page 1 when mode is changed to `items`
- storage: generic Yonhap-style `filter\<NNN_search_term>\texts\YYYYMMDD` plus `filter\workflow_records.json`

## Implementation Summary

- Added `configs\시그널.json`.
- Configured result link XPath:
  - `//ul[contains(@class, 'news_list')]/li[n]/div/dl/dt/a`
- Configured detail extraction:
  - title: `//*[@id='mainTitle']`
  - body: `//div[contains(@class, 'view_con')]`
- Added `open_detail.exclude_xpath` to skip locked/member-only search results.
- Added `extract_body.exclude_xpath` to remove article image and paid preview blocks.
- Changed start URL from pagination-placeholder style to concrete `page=1` so `items` mode and `pagination` mode both work.
- Recorded plan, contract, run context, ruling, and the user-run failure diagnosis.

## Validation

- Live proof:
  - `qa-artifacts\signal-live-20260514\summary.json`
  - success true
  - 33 accessible records total
  - `최태원` 14 records
  - `SK` 19 records
  - 66 extracted title/body files
  - 0 downloads
- Body cleanup proof:
  - `회원 전용기사` hits: 0
  - `signal 이 기사는` hits: 0
  - `가장 많이 읽은` hits: 0
- Mode proof after user-run failure diagnosis:
  - `qa-artifacts\signal-mode-check-20260514\summary.json`
  - `items`: success, 6 records
  - `pagination`: success, 33 records, pages `[1, 2]`
- UI proof:
  - `qa-artifacts\signal-ui-20260514\editor-3020.png`
  - `qa-artifacts\signal-ui-20260514\ui_result.json`
  - editor has `open_detail`, `extract_title`, `extract_body`
  - Naver/Daum provider panels absent
- Commands:
  - `.venv\Scripts\python.exe -m unittest discover -s tests`: 127 tests pass
  - `node --check static\app.js`: pass
  - `configs\시그널.json` workflow validation: pass

## Remaining Risks

- Signal HTML may drift; update XPath in the UI if list or detail structure changes.
- Some Signal articles are member-only and intentionally skipped.
- Current Signal config includes additional SK-family search terms beyond the initial `최태원`, `SK` proof terms; those extra terms should be spot-checked if they become operationally important.
- User-owned push/merge process must still target `dev/crawler-current`, not `main`.

## Files Intentionally Excluded

```text
configs/산업부_보도자료.json
configs/인베스트조선.json
pr_body.md
qa-artifacts/
outputs/
logs/
.env
.venv/
```

`configs/산업부_보도자료.json`, `configs/인베스트조선.json`, and `pr_body.md` are currently present in the worktree but are not part of this Signal push set.

## Remote

```text
origin	https://github.com/K-Ternag/crawlService (fetch)
origin	https://github.com/K-Ternag/crawlService (push)
```

## Push Command

```powershell
git push origin dev/crawler-current:dev/crawler-current
```

## Push Result

Not pushed by Codex in this turn. User owns the push execution unless they explicitly request direct push.
