# Git Push Change Log - 크롤러 뉴스 수집 개선 및 소스 변경 가드레일

- Date: 2026-05-14 19:00:28 +09:00
- Repository: C:\AI_JOB\firstproject\crawler_project\crawlService-main
- Branch: dev/crawler-current
- Upstream: origin/dev/crawler-current
- Commit message: docs: 크롤러 뉴스 수집 변경 이력과 가드레일 정리
- Approved push target: origin/dev/crawler-current

## Request

네이버/다음 API 기반 뉴스 수집, 구글 RSS 수집/정제, 더벨 실행단계형 뉴스 수집, 그리고 향후 크롤러 소스 변경 가드레일을 하나의 push 설명으로 정리한다.

## Changed Files

~~~text
 M DECISION_RULING.md
 M RUN_CONTEXT.md
 M TASK_CLASSIFICATION.md
 M TASK_CONTRACT.md
 M TASK_PLAN.md
 M configs/다음.json
 M crawler_app/workflow.py
 M tests/test_web.py
 M tests/test_workflow.py
?? SOURCE_CHANGE_GUARDRAIL.md
?? configs/더벨.json
?? docs/push-history/20260514_190028_dev-crawler-current_크롤러-뉴스-수집-개선-및-소스-변경-가드레일.md
~~~

Intentionally excluded dirty files:

~~~text
 M configs/산업부_보도자료.json
?? pr_body.md
~~~

## Diff Stat

~~~text
 DECISION_RULING.md                                 | 170 +++++++++++++++++++
 RUN_CONTEXT.md                                     | 181 +++++++++++++++++++++
 SOURCE_CHANGE_GUARDRAIL.md                         |  70 ++++++++
 TASK_CLASSIFICATION.md                             |  16 ++
 TASK_CONTRACT.md                                   |  55 +++++++
 TASK_PLAN.md                                       | 120 ++++++++++++++
 configs/다음.json                                  |  72 +++++++-
 configs/더벨.json                                  |  49 ++++++
 crawler_app/workflow.py                            |  56 ++++++-
 ..._크롤러-뉴스-수집-개선-및-소스-변경-가드레일.md | 175 ++++++++++++++++++++
 tests/test_web.py                                  |  99 +++++++++++
 tests/test_workflow.py                             |  37 +++++
 12 files changed, 1092 insertions(+), 8 deletions(-)
~~~

## Staged Diff Stat

~~~text
 DECISION_RULING.md                                 | 170 +++++++++++++++++++
 RUN_CONTEXT.md                                     | 181 +++++++++++++++++++++
 SOURCE_CHANGE_GUARDRAIL.md                         |  70 ++++++++
 TASK_CLASSIFICATION.md                             |  16 ++
 TASK_CONTRACT.md                                   |  55 +++++++
 TASK_PLAN.md                                       | 120 ++++++++++++++
 configs/다음.json                                  |  72 +++++++-
 configs/더벨.json                                  |  49 ++++++
 crawler_app/workflow.py                            |  56 ++++++-
 ..._크롤러-뉴스-수집-개선-및-소스-변경-가드레일.md | 175 ++++++++++++++++++++
 tests/test_web.py                                  |  99 +++++++++++
 tests/test_workflow.py                             |  37 +++++
 12 files changed, 1092 insertions(+), 8 deletions(-)
~~~

## Why These Changes Were Made

이번 브랜치는 크롤러 제품에서 네이버/다음/구글/더벨 뉴스 수집 경로를 정리한 브랜치다. 이번 push record는 현재 추가 커밋뿐 아니라 이미 `dev/crawler-current`에 포함된 네이버/다음 API 수집 및 구글 RSS 수집 변경 맥락까지 함께 설명하기 위해 작성했다.

추가 커밋의 직접 이유는 다음과 같다.

- 더벨은 처음에 별도 provider/parser로 구현하는 방향을 검토했으나, 개발팀의 소스 변경 민감도와 사용자 요구를 반영해 기존 실행 단계 UI를 유지하는 방식으로 되돌렸다.
- 더벨은 뉴스형 HTML 사이트이므로 `download_file`이 아니라 `open_detail`, `extract_title`, `extract_body` 실행 단계와 XPath 설정으로 관리해야 한다.
- 더벨 및 향후 뉴스형 실행단계 사이트는 원본 `연합뉴스` 저장 구조와 맞춰야 한다.
- 본문 추출 시 로그인/유료 안내 같은 descendant noise만 제거할 수 있도록 `exclude_xpath` 적용 방식을 보강했다.
- 반복 실행 시 relocation이 기존 target 파일을 덮어쓰지 않도록 보강했다.
- 앞으로 크롤링 사이트가 많아질 예정이므로, 소스코드 수정은 원본 비교와 이유 기록 없이는 진행하지 않도록 `SOURCE_CHANGE_GUARDRAIL.md`를 추가했다.

## Design Notes And Tradeoffs

이번 push record는 이번 커밋뿐 아니라 dev/crawler-current에 포함된 네이버/다음 및 구글 변경 맥락까지 함께 설명한다. 개발팀의 소스코드 변경 민감도를 반영해 새 사이트는 config/XPath 우선으로 처리하고, 원본 비교는 C:\AI_JOB\firstproject\crawler_project\origin\crawlService-main 기준으로 고정했다. 네이버/다음은 API-backed exception, 구글은 origin-existing RSS/platform-backed parser exception, 더벨은 generic execution-step news site로 분류한다.

### Existing Code Changed Because

- `crawler_app/workflow.py`의 relocation은 generic 실행단계 결과를 `filter` 아래로 옮길 때 기존 파일을 덮어쓸 수 있었다. 개발팀이 저장 경로와 결과 누락에 민감하므로, 이미 target root에 있는 파일은 그대로 두고 동일 경로 충돌 시 unique path를 쓰도록 보강했다.
- `crawler_app/workflow.py`의 `exclude_xpath`는 기존에는 locator 후보 자체를 제외하는 방식이어서, 더벨처럼 본문 컨테이너 안의 로그인/유료 안내 descendant만 제거해야 하는 경우에 적합하지 않았다. 본문 컨테이너는 유지하면서 내부 제외 노드만 제거하도록 `_step_value` 쪽에서 처리했다.
- parser record의 `api_url`/`search_url` 필드는 네이버/다음 API와 구글 RSS가 섞여 보이지 않도록 정리했다. API가 아닌 Google RSS에는 `api_url`을 비워 둔다.
- `tests/test_web.py`와 `tests/test_workflow.py`는 더벨이 provider panel이 아니라 기존 실행 단계 UI를 유지한다는 점, relocation 충돌 방지, descendant noise 제거를 고정하기 위해 추가했다.

### Idea Or Constraint Behind The Change

- 기본 아이디어는 "새 사이트는 config/XPath 우선, 소스 변경은 예외"다.
- 원본 기준은 항상 `C:\AI_JOB\firstproject\crawler_project\origin\crawlService-main`로 고정한다.
- 뉴스형 HTML 사이트는 원본 `연합뉴스` 구조를 기준으로 한다.
- 정부자료/첨부파일형 사이트는 `산업부_보도자료` 구조를 기준으로 한다.
- 네이버/다음은 API-backed exception이다.
- 구글은 API는 아니지만 원본에도 이미 존재하는 RSS/platform-backed parser exception이다.
- 더벨은 API나 RSS가 아니라 HTML 뉴스형이므로 기존 실행 단계와 XPath 관리가 맞다.

### Advantages

- 더벨을 별도 parser/UI로 늘리지 않아 소스 변경 범위를 줄인다.
- 향후 뉴스형 사이트는 XPath/config 중심으로 추가할 수 있다.
- 더벨 본문에서 로그인/유료 안내를 제거하면서도 기사 본문 컨테이너 자체는 유지한다.
- 저장 경로는 원본 연합뉴스와 맞춰 개발팀이 예측하기 쉽다.
- push record와 guardrail이 앞으로 "왜 코드를 바꿨는지"를 추적할 수 있게 한다.

### Disadvantages Or Costs

- 더벨의 여러 페이지 수집이나 고급 paging은 현재 실행 단계 UI 범위에서는 별도 승인 없이 넣지 않는다.
- generic `workflow_records.json`은 원본 호환성을 위해 run-versioned가 아니므로, manifest는 최신 실행으로 갱신된다.
- `exclude_xpath` descendant cleanup은 HTML 조각 파싱을 추가로 수행하므로 매우 큰 본문에서는 비용이 조금 늘 수 있다.
- 구글 RSS는 여전히 parser 예외로 남아 있어 HTML 뉴스형과 저장 구조가 다르다. 다만 이는 원본 구조를 따른 결정이다.

### Alternatives Considered Or Deferred

- 더벨 전용 provider/parser와 전용 editor panel: 처음 검토했지만 사용자 요구와 소스 변경 최소화 원칙에 맞지 않아 철회했다.
- 더벨 generic 결과를 `items\YYYYMMDD_n`으로 저장: 누적성은 좋지만 원본 연합뉴스 저장 구조와 달라 철회했다.
- 구글 RSS를 XPath-only로 전환: RSS XML이 현재 generic HTML preview/execution 경로와 맞지 않고, 원본도 parser path를 쓰므로 보류했다.
- 산업부_보도자료 설정 변경 포함: 이번 뉴스/API/RSS/가드레일 push와 직접 관련이 없고 정부자료 기준 config를 오염시킬 수 있어 제외했다.

### Collection Or Runtime Structure Notes

- 네이버: 공식 Naver Search News API를 사용하며, `.env`/환경변수에서 credential을 읽는다. UI에는 Client ID/Secret을 노출하지 않는다. 본문 전문 수집은 publisher parser/allowlist/retention 정책이 생길 때까지 제외한다.
- 다음: Kakao Daum Web Search API를 사용하고 `site:v.daum.net` 힌트와 Daum news host filter로 뉴스성 결과를 좁힌다. 뉴스 전용 API가 아니므로 결과 품질 리스크가 있다.
- 구글: Google News RSS를 사용하며 API key는 필요 없다. RSS `description`은 본문 전문이 아니라 feed snippet이다. HTML/source label은 정제하고 `source`는 별도 필드로 유지한다.
- 더벨: `section=NEWS` 검색 URL과 실행 단계 `open_detail`, `extract_title`, `extract_body`를 사용한다. 기사 목록/본문 XPath가 바뀌면 UI에서 XPath를 갱신한다.
- 향후 사이트: `SOURCE_CHANGE_GUARDRAIL.md`에 따라 config/XPath-only가 가능한지 먼저 판단한다.

## Implementation Summary

- 기존 브랜치 포함 변경 요약:
  - 네이버 API 기반 뉴스 수집 및 UI 설정 정리.
  - 다음 API 기반 뉴스 수집 및 UI 설정 정리.
  - 구글 RSS 수집, per-item JSON 저장, RSS description 정제.
- 이번 추가 커밋 변경 요약:
  - `configs\다음.json` 검색어 목록과 notes 보강.
  - `configs\더벨.json` 추가. 더벨은 provider parser가 아니라 기존 실행 단계 UI로 관리한다.
  - `crawler_app\workflow.py` relocation 충돌 방지와 extract descendant cleanup 보강.
  - `tests\test_web.py`, `tests\test_workflow.py`에 더벨 실행단계/relocation/body cleanup regression 추가.
  - `SOURCE_CHANGE_GUARDRAIL.md` 추가.
  - Alpha task docs에 더벨 superseded 결정, 연합뉴스 저장 구조 복원, Google RSS 예외 판정, source-change guardrail 기록.

## Validation

.venv\Scripts\python.exe -m unittest discover -s tests: 124 tests pass; node --check static\app.js: pass

## Remaining Risks

네이버/다음은 API 품질과 제공 필드에 의존한다. 구글 RSS는 본문 전문이 아니라 RSS description만 제공한다. 더벨은 HTML/XPath 변경 시 UI에서 XPath 갱신이 필요하다. 산업부_보도자료 local dirty file과 pr_body.md는 이번 staging에서 제외한다.

## Files Intentionally Excluded

- `configs\산업부_보도자료.json`: 현재 local dirty 상태지만 이번 push 범위가 아니다. 또한 이 파일은 정부자료/첨부파일형 기준 config라서 별도 승인 없이 포함하면 개발팀 기준선을 흔들 수 있다.
- `pr_body.md`: 이전 Google PR 본문 초안이며, 이번 push record와 중복되고 커밋 산출물로 관리할 필요가 없다.
- `.env`, outputs, qa-artifacts, screenshots: secrets 또는 generated/bulky artifacts라서 stage하지 않는다.

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

Not run yet. User approval is required before network push.
