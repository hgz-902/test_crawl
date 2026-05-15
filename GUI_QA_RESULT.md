# GUI QA Result

## Result
- status: pass
- date: 2026-05-14
- slice: Naver News API Collection

## Evidence
- Server:
  - URL: `http://127.0.0.1:3000/`
  - port `3000` listening with pid `9612`
- Browser QA:
  - Playwright Chromium installed with `.venv\Scripts\python.exe -m playwright install chromium`
  - home page screenshot: `C:\AI_JOB\firstproject\crawler_project\crawlService-main\qa-artifacts\naver-news-ui-20260514\home.png`
  - config page screenshot: `C:\AI_JOB\firstproject\crawler_project\crawlService-main\qa-artifacts\naver-news-ui-20260514\config.png`
- Browser checks:
  - home page title: `설정 목록`
  - home page contains config name `네이버뉴스_최태원_2페이지`
  - config page title: `Workflow 설정`
  - config page HTML contains `openapi.naver.com/v1/search/news.json`
  - config page HTML contains `loop_limit` and `20`
- User-visible launch:
  - opened `http://127.0.0.1:3000/` with Windows `Start-Process`
  - opened VS Code on `C:\AI_JOB\firstproject\crawler_project\crawlService-main`

## Notes
- The in-app Browser tool was not exposed after tool discovery, so GUI truth was captured with Playwright from the project `.venv`.
- This GUI check did not trigger another UI crawl. Live crawling proof was performed through the bounded CLI config and recorded in `DECISION_RULING.md`.

## Naver Editor Scope QA
- status: pass
- date: 2026-05-14
- reason: after user correction, the Naver News API panel must appear only on the existing `네이버` config editor and not on unrelated editors.
- Browser QA artifacts:
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\qa-artifacts\naver-editor-scope-20260514\naver.png`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\qa-artifacts\naver-editor-scope-20260514\mcee.png`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\qa-artifacts\naver-editor-scope-20260514\naver-payload.json`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\qa-artifacts\naver-editor-scope-20260514\result.json`
- Checks:
  - `/configs/네이버` contains `Naver News API` panel.
  - `/configs/기후에너지부_보도자료` does not contain `Naver News API` panel.
  - generated `네이버` payload supports multiple search terms and maps latest-news count to both `display` and `loop_limit`.
  - no UI crawl was triggered during this QA.

## Naver Credentials/Display UI QA Pause Result
- status: hold
- date: 2026-05-14
- reason: editor UI checks passed, but live Naver UI run failed and needs a follow-up fix.
- Browser/UI checks passed:
  - superseded: `/configs/네이버` temporarily showed credential fields; current UI removes Client ID / Client Secret fields and keeps API display/latest-count controls only.
  - `/configs/기후에너지부_보도자료` does not show the Naver News API panel.
  - editor HTML does not contain stored credential values.
  - opening `/configs/네이버` and clicking `저장` preserves Naver API fields.
- Tool limitation:
  - the in-app browser driver could not type into HTML `input[type=number]` fields due its number-input fill/type limitation, so display-value change/save was additionally checked through the same `/configs` POST path and unit coverage.
- Validation:
  - `node --check static\app.js` passed.
  - `.venv\Scripts\python.exe -m unittest discover -s tests` passed 97 tests.
- Live-run blocker:
  - UI run path `/configs/네이버/run` currently returns failed result with `AttributeError: 'NoneType' object has no attribute 'get'`.
  - This is the first task to resume.

## Naver Credentials/Display UI QA Resume Result
- status: conditional pass
- date: 2026-05-14
- reason: live UI run succeeds after the runtime cleanup fix; remaining issue is allowlist policy coverage, not UI execution failure.
- Evidence:
  - result summary: `C:\AI_JOB\firstproject\crawler_project\crawlService-main\qa-artifacts\naver-ui-credentials-display-20260514\result-summary.json`
  - UI run HTML: `C:\AI_JOB\firstproject\crawler_project\crawlService-main\qa-artifacts\naver-ui-credentials-display-20260514\naver-run-result.html`
  - editor screenshot: `C:\AI_JOB\firstproject\crawler_project\crawlService-main\qa-artifacts\naver-ui-credentials-display-20260514\naver-editor-credentials-display.png`
  - index screenshot: `C:\AI_JOB\firstproject\crawler_project\crawlService-main\qa-artifacts\naver-ui-credentials-display-20260514\naver-index.png`
- Checks:
  - superseded: `/configs/네이버` temporarily showed credential status; current UI keeps API display/latest-count controls and removes credential fields.
  - `/configs/기후에너지부_보도자료` remains free of the Naver panel.
  - live UI run returns HTTP 200 and success true.
  - workflow record count: 40.
  - item JSON files: 40.
  - legacy article-body extraction results are superseded by the API-only decision.
  - stored credentials are not rendered in editor HTML.
  - local scan found no credential values outside `.env`.
- Validation:
  - `node --check static\app.js` passed.
  - `.venv\Scripts\python.exe -m unittest discover -s tests` passed 99 tests.

## Naver API-Only UI QA Result
- status: conditional pass
- date: 2026-05-14
- reason: user decided to defer article body extraction; current UI/API path now saves Naver API results only.
- Evidence:
  - result summary: `C:\AI_JOB\firstproject\crawler_project\crawlService-main\qa-artifacts\naver-api-only-20260514\result-summary.json`
  - UI run HTML: `C:\AI_JOB\firstproject\crawler_project\crawlService-main\qa-artifacts\naver-api-only-20260514\naver-run-result.html`
  - editor screenshot: `C:\AI_JOB\firstproject\crawler_project\crawlService-main\qa-artifacts\naver-api-only-20260514\naver-editor-api-only.png`
- Checks:
  - `/configs/네이버` shows Naver API display controls; credential controls were later removed.
  - `/configs/네이버` no longer shows article-body controls.
  - live UI run returns HTTP 200 and success true.
  - item JSON files: 40.
  - article-body field hits: 0.
  - article body field hits: 0.
  - empty `description` count in latest verified run: 0.
  - stale article-body scan across `outputs`, `logs`, and `qa-artifacts`: no hits after cleanup.
  - broad `네이버뉴스` run returns HTTP 400 and is blocked until bounded `loop_limit` is configured.
- Validation:
  - `node --check static\app.js` passed.
  - `.venv\Scripts\python.exe -m unittest discover -s tests` passed 91 tests.
