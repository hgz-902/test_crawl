# Git Push Change Log - 인베스트조선 뉴스 수집 설정 추가

- Date: 2026-05-14 20:38:06 +09:00
- Repository: C:\AI_JOB\firstproject\crawler_project\crawlService-main
- Branch: dev/crawler-current
- Upstream: origin/dev/crawler-current
- Commit message: 인베스트조선 뉴스 수집 설정 추가
- Approved push target: origin/dev/crawler-current

## Request

인베스트조선을 `최태원`, `SK` 검색어로 수집할 수 있게 만들고, 다음 push 전까지 실제 실행과 UI 검수를 완료한다. 또한 일반적인 뉴스형 사이트의 특이사항 notes는 API/RSS/유료구독 같은 예외가 없으면 간단히 남긴다.

## Changed Files

```text
DECISION_RULING.md
RUN_CONTEXT.md
TASK_CONTRACT.md
TASK_PLAN.md
configs/더벨.json
configs/마켓인사이트.json
configs/인베스트조선.json
docs/push-history/20260514_203806_dev-crawler-current_인베스트조선-뉴스-수집-설정-추가.md
```

## Diff Stat

```text
DECISION_RULING.md        | 31 +++++++++++++++++++++++++++++++
RUN_CONTEXT.md            | 29 +++++++++++++++++++++++++++++
TASK_CONTRACT.md          | 47 +++++++++++++++++++++++++++++++++++++++++++++++
TASK_PLAN.md              | 34 ++++++++++++++++++++++++++++++++++
configs/더벨.json         |  4 ++--
configs/마켓인사이트.json |  4 ++--
configs/인베스트조선.json | new file
```

## Why These Changes Were Made

인베스트조선은 API/RSS형이 아니라 일반 HTML 뉴스 검색 결과와 기사 상세 페이지를 가진 사이트다. 기존 연합뉴스형 generic 실행단계 구조로 처리할 수 있으므로, 새 provider parser나 shared source-code 변경 없이 config만 추가하는 방식이 가장 안전했다.

더벨과 마켓인사이트 notes는 사용자가 확인할 때 긴 내부 판단 문장이 방해가 될 수 있어, 실제 예외만 짧게 알리는 형태로 정리했다. 더벨은 유료/로그인으로 본문 전체 수집이 제한될 수 있으므로 그 점만 남겼고, 마켓인사이트는 일반 연합뉴스형 실행단계 구조라는 점만 남겼다.

## Design Notes And Tradeoffs

### Existing Code Changed Because

이번 slice에서는 shared source code를 변경하지 않았다. 인베스트조선의 검색 URL, 목록 XPath, 제목 XPath, 본문 XPath, body cleanup은 모두 기존 workflow config 기능으로 표현할 수 있었다.

### Idea Or Constraint Behind The Change

새 뉴스형 사이트는 먼저 원본 연합뉴스형 구조를 기준으로 config/XPath-only 적용 가능성을 확인한다. 인베스트조선은 검색 URL에 `q`와 `pn` 파라미터가 있고, 기사 목록이 반복 가능한 `ul.search-list > li` 구조라 `open_detail.loop_mode=pagination`으로 충분했다.

### Advantages

- 개발팀이 민감하게 보는 shared source churn을 만들지 않는다.
- 사용자는 UI에서 시작 URL, 검색어, page count, XPath를 계속 수정할 수 있다.
- 기존 generic 뉴스 저장 구조와 호환된다.
- 특이사항 notes가 짧아져 운영자가 예외 여부를 빠르게 볼 수 있다.

### Disadvantages Or Costs

- HTML 구조가 바뀌면 config XPath를 수정해야 한다.
- generic 뉴스 저장 구조는 원본 연합뉴스 기준을 따르므로 `filter\workflow_records.json`은 run-versioned manifest가 아니다.
- 인베스트조선 본문 하단 위젯 제거는 config `exclude_xpath`에 의존한다.

### Alternatives Considered Or Deferred

- provider parser 신규 작성: 불필요해서 배제했다. API/RSS/유료회원 특수 구조가 아니라 기존 실행단계로 충분하다.
- source-code body cleanup 추가: 인베스트조선 전용 노이즈는 config `exclude_xpath`로 제거 가능하므로 배제했다.
- output 누적 구조 변경: 사용자 요청으로 generic 뉴스 저장 구조 변경은 보류된 상태라 이번 slice에서도 건드리지 않았다.

### Collection Or Runtime Structure Notes

- start URL: `https://www.investchosun.com/svc/news/search.html?q={search_term}&pn={page_number}`
- search terms: `최태원`, `SK`
- steps: `open_detail`, `extract_title`, `extract_body`
- pagination: `open_detail.loop_mode=pagination`, `pagination_mode=page_number`, `loop_limit=2`
- storage: generic Yonhap-style `filter\<NNN_search_term>\texts\YYYYMMDD` plus `filter\workflow_records.json`

## Implementation Summary

- Added `configs\인베스트조선.json`.
- Configured direct repeatable article-link XPath:
  - `//ul[contains(@class, 'search-list')]/li[n]/div[contains(@class, 'list_detail')]/dl/dt/a`
- Configured detail extraction:
  - title: `//div[contains(@class, 'art_title')]/div[contains(@class, 'title')]`
  - body: `//div[@id='article']`
- Added config-level `exclude_xpath` for image expansion and ranking/recommendation blocks.
- Recorded task contract, plan, run context, and ruling.
- Shortened TheBell and MarketInsight notes to the new concise style.

## Validation

- Live proof:
  - `qa-artifacts\investchosun-live-20260514-v2\summary.json`
  - success true
  - 40 records total
  - `최태원` 20 records
  - `SK` 20 records
  - pages `[1, 2]`
  - 80 extracted title/body files
  - 0 downloads
- Body cleanup proof:
  - `이미지 크게보기` hits: 0
  - `많이 본 뉴스` hits: 0
- UI proof:
  - `qa-artifacts\investchosun-ui-20260514\editor-3020.png`
  - `qa-artifacts\investchosun-ui-20260514\ui_result.json`
  - editor has `open_detail`, `extract_title`, `extract_body`
  - Naver/Daum provider panels absent
- Commands:
  - `.venv\Scripts\python.exe -m unittest discover -s tests`: 127 tests pass
  - `node --check static\app.js`: pass
  - `configs\인베스트조선.json` workflow validation: pass

## Remaining Risks

- InvestChosun HTML may drift; update XPath in the UI if list or detail structure changes.
- Generic news manifest remains origin-compatible but not run-versioned.
- User-owned push/merge process must still target `dev/crawler-current`, not `main`.

## Files Intentionally Excluded

```text
configs/산업부_보도자료.json
pr_body.md
qa-artifacts/
outputs/
logs/
.env
.venv/
```

`configs/산업부_보도자료.json` and `pr_body.md` are currently present in the worktree but are not part of this InvestChosun/news-notes push set.

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
