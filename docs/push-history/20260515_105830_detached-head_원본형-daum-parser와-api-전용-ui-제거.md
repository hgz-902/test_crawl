# Git Push Change Log - 원본형 Daum parser와 API 전용 UI 제거

- Date: 2026-05-15 10:58:30 +09:00
- Repository: C:\AI_JOB\firstproject\crawler_project\crawler-push-worktree
- Branch: (detached HEAD)
- Upstream: (none)
- Commit message: 원본형 Daum parser 및 실행단계 UI 복구
- Approved push target: origin dev/crawler-current

## Request

원본 코드 기준으로 Naver/Daum/Google 특수 parser 구조를 실행 단계 attr 방식에 맞추고, 이전 Naver/Daum 전용 UI 패널 및 site-specific pagination/output 실험을 제거했습니다. Daum은 Kakao Web Search API parser attr=daum으로 추가했습니다.

## Changed Files

~~~text
 M .env.example
 M configs/네이버뉴스.json
 M configs/다음.json
 M crawler_app/daum_news_api.py
 M crawler_app/web.py
 M crawler_app/workflow.py
 M static/app.js
 M static/styles.css
 M templates/editor.html
 M tests/test_daum_news_api.py
 M tests/test_web.py
 M tests/test_workflow.py
~~~

## Diff Stat

~~~text
 .env.example                 |   2 +-
 configs/네이버뉴스.json      |   8 +-
 configs/다음.json            |  82 +-----
 crawler_app/daum_news_api.py |  39 +--
 crawler_app/web.py           | 185 +------------
 crawler_app/workflow.py      | 539 +++-----------------------------------
 static/app.js                | 136 +---------
 static/styles.css            |   4 -
 templates/editor.html        |  71 +----
 tests/test_daum_news_api.py  |  32 +--
 tests/test_web.py            | 451 --------------------------------
 tests/test_workflow.py       | 608 ++++---------------------------------------
 12 files changed, 128 insertions(+), 2029 deletions(-)
warning: in the working copy of '.env.example', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'configs/네이버뉴스.json', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'configs/다음.json', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'crawler_app/daum_news_api.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'crawler_app/web.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'crawler_app/workflow.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'static/app.js', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'static/styles.css', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'templates/editor.html', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/test_daum_news_api.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/test_web.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/test_workflow.py', LF will be replaced by CRLF the next time Git touches it
~~~

## Staged Diff Stat

~~~text
 .env.example                                       |   2 +-
 configs/네이버뉴스.json                            |   8 +-
 configs/다음.json                                  |  82 +--
 crawler_app/daum_news_api.py                       |  39 +-
 crawler_app/web.py                                 | 185 +------
 crawler_app/workflow.py                            | 539 ++----------------
 docs/push-history/20260515_105830_detached-head_원본형-daum-parser와-api-전용-ui-제거.md | 130 +++++
 static/app.js                                      | 136 +----
 static/styles.css                                  |   4 -
 templates/editor.html                              |  71 +--
 tests/test_daum_news_api.py                        |  32 +-
 tests/test_web.py                                  | 451 ---------------
 tests/test_workflow.py                             | 608 ++-------------------
 13 files changed, 258 insertions(+), 2029 deletions(-)
~~~

## Why These Changes Were Made

이전 branch에는 Naver/Daum 전용 편집 패널, provider별 run safety, page_limit/loop_limit 확장, site-specific pagination/output 실험이 섞여 있었다. 개발 기준은 특수 API/RSS형도 실행 단계에서 action=parser와 attr 값으로 관리하는 것이므로, 원본 코드의 일반 편집 흐름으로 되돌리고 Daum만 승인된 특수 parser attr로 연결했다.

## Design Notes And Tradeoffs

전용 provider UI 패널은 개발팀이 요구한 실행 단계 기반 흐름과 어긋나므로 제거했습니다. Naver/Daum/Google만 특수 parser source를 허용하고, 사용자는 기존 실행 단계에서 action=parser 및 attr=google/naver/daum을 선택하는 방식으로 맞췄습니다. Daum은 공식 뉴스 전용 API가 아니라 Kakao Web Search API라서 URL 검증, 리다이렉트 차단, Daum 뉴스 도메인 필터를 둔 얇은 parser 모듈로 제한했습니다.

### Existing Code Changed Because

기존 branch의 전용 UI 패널은 "Naver/Daum/Google도 실행 단계 attr로 관리한다"는 기준과 충돌했다. `crawler_app/web.py`, `static/app.js`, `templates/editor.html`, 관련 web tests는 원본형 편집 화면으로 되돌리고, parser attr 목록에 `daum`만 추가했다.

### Idea Or Constraint Behind The Change

일반 뉴스/정부자료 사이트는 XPath와 설정만으로 동작해야 하며, Naver/Daum/Google만 구조화 응답 parser 예외로 둔다. Daum은 Kakao Web Search API를 사용하되, UI는 별도 API 패널이 아니라 실행 단계 `Kakao_api` / `attr=daum`으로 관리한다.

### Advantages

설정 방식이 Google/Naver/Daum 모두 실행 단계 중심으로 통일된다. 전용 패널과 provider-specific safety code가 제거되어 앞으로 사이트별 UI 분기가 늘어나는 위험이 줄어든다. Daum API 키는 `.env`의 `KAKAO_REST_API_KEY`로만 참조한다.

### Disadvantages Or Costs

이전 branch의 편의 UI와 pagination/output 실험을 제거하는 큰 diff가 발생했다. Daum은 뉴스 전용 API가 아니라 카카오 웹 검색 결과를 Daum 뉴스 도메인으로 필터링하는 방식이므로, 실제 다음 검색 UI와 결과가 1:1로 일치하지 않을 수 있다.

### Alternatives Considered Or Deferred

Naver/Daum 전용 UI 패널을 유지하는 방안은 실행 단계 중심 기준과 충돌해 제외했다. output 중복 감지 후 중단 기능은 공통 source change가 필요하므로 이번 승인 범위 밖으로 보류했다. 일반 사이트 pagination 재구현도 이번 reset 기준상 보류했다.

### Collection Or Runtime Structure Notes

Daum parser는 `https://dapi.kakao.com/v2/search/web`만 허용하고 리다이렉트를 차단한다. `news.daum.net`, `v.daum.net` 도메인만 저장하며, 저장 형식은 Google/Naver parser와 같은 단일 JSON payload 구조를 따른다.

## Implementation Summary

원본 코드 기준으로 Naver/Daum/Google 특수 parser 구조를 실행 단계 attr 방식에 맞추고, 이전 Naver/Daum 전용 UI 패널 및 site-specific pagination/output 실험을 제거했습니다. Daum은 Kakao Web Search API parser attr=daum으로 추가했습니다.

## Validation

C:\AI_JOB\firstproject\crawler_project\crawlService-main\.venv\Scripts\python.exe -m unittest discover -s tests => Ran 93 tests OK. Daum live check with existing .env KAKAO_REST_API_KEY => success True, parser_item_count 1, output daum_news_api.json, title/url present. Browser UI check on http://127.0.0.1:3002/configs/다음 => Daum/Naver API panels absent, 실행 단계 visible, Kakao_api parser attr daum selected.

## Remaining Risks

Daum은 카카오 웹 검색 API를 news.daum.net/v.daum.net 도메인 필터로 사용하는 구조라 다음 뉴스 전용 API와 결과가 다를 수 있습니다. 기존 branch의 rejected UI/pagination/output 실험을 원본형으로 되돌리는 큰 diff가 포함됩니다. 기존 output 중복 감지/중단 정책은 아직 공통 source change 승인을 받지 않아 구현하지 않았습니다.

## Files Intentionally Excluded

기존 주 작업 폴더 `C:\AI_JOB\firstproject\crawler_project\crawlService-main`에 남아 있던 이전 세션 dirty files는 staging하지 않았다. 깨끗한 detached worktree에서 이번 reset/Daum parser 변경만 커밋한다. `.env`, outputs, logs, API key 값은 포함하지 않는다.

## Remote

~~~text
origin	https://github.com/K-Ternag/crawlService (fetch)
origin	https://github.com/K-Ternag/crawlService (push)
~~~

## Push Command

~~~powershell
git push origin HEAD:dev/crawler-current
~~~

## Push Result

TODO
