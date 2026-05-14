# Run Context

## Run Identity
- run_id: `crawler-alpha-20260513-env-ui`
- alpha_session_key: `alpha-crawler-20260513`
- alpha_topic_instance_key: `crawler-improvement-baseline-20260513`
- alpha_worker_namespace: `crawler-alpha`

## Budget Guardrail
- Avoid broad markdown rereads.
- Prefer current docs and targeted `rg`.
- Do not run broad live crawls without a site policy slice.

## Expensive-Step Warning
- `pip install` and Playwright browser install can take time and network.
- Live crawling may hit external websites and should wait for policy and explicit slice scope.

## Hold Threshold
- Hold if dependency installation fails.
- Hold if no local port can be opened.
- Hold if VS Code command is unavailable and no obvious local fallback exists.
- Hold before initializing Git unless the user explicitly approves repository creation.

## Local-Only Setup Waiver
- why safe to keep local: this slice only creates planning artifacts, installs dependencies into local `.venv`, runs existing tests, starts the existing UI, and opens VS Code.
- why developer worker is not needed: no product behavior, crawler code, config semantics, scheduler, email, or UI feature implementation is being changed.
- waived risks: implementation-specific reviewer/QA/auditor findings are deferred until product code changes begin.
- waiver record: this `RUN_CONTEXT.md`.
- final ruling default if wrong: `rework`.

## Checkpoint
- current goal: make the crawler project inspectable and runnable locally.
- completed: task docs created, `.venv` created, dependencies installed, tests passed, UI started, VS Code opened.
- not done: Git repository initialization or commit workflow; product feature implementation; live target-site crawl verification.
- next action: decide whether to initialize Git in this folder or attach it to another repository, then start Slice 1 implementation with Alpha worker flow.
- related paths: `C:\AI_JOB\firstproject\crawler_project\crawlService-main`
- validation: `python main.py --help` passes in `.venv`; `python -m unittest discover -s tests` passes 76 tests; UI returns HTTP 200 on `http://127.0.0.1:3000/`.

## PreToolUse Guard
- command: `python -m venv .venv; .venv\Scripts\python -m pip install -r requirements.txt`
- status: `review`
- reason: dependency installation can fetch packages from the network.
- justification: the user explicitly requested local environment confirmation and remediation; dependencies will be installed into the project-local `.venv`, not global Python.
- decision: proceed.
- command: `.venv\Scripts\python -m playwright install chromium`
- status: `review` expected due browser runtime download
- justification: the crawler uses Playwright and representative site verification will require a browser runtime; install is local Playwright-managed runtime for this development machine.
- decision: proceed.

## Environment Result
- Python: `3.12.10`
- Virtual environment: `.venv`
- Dependency fix applied:
  - added `httpx>=0.28.0,<1` to `requirements.txt` because FastAPI/Starlette `TestClient` requires it.
- Compatibility fix applied:
  - updated `crawler_app/web.py` `TemplateResponse` calls to the current request-first signature required by installed FastAPI/Starlette.
- Playwright dry-run shows Chromium runtime location:
  - `C:\Users\ThinkBook\AppData\Local\ms-playwright\chromium-1217`
- Git status:
  - `C:\AI_JOB\firstproject` is not a Git repository.
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main` is not a Git repository.
  - Git init/commit setup is held until explicit repository decision.
- UI:
  - running at `http://127.0.0.1:3000/`
  - server pid: `26980`
- VS Code:
  - opened with `code C:\AI_JOB\firstproject\crawler_project\crawlService-main`.

## Emergency Stop
- date: 2026-05-13
- reason: user started a UI crawl and observed unexpectedly broad crawling scope.
- action: stopped the local uvicorn/crawler process tree rooted at pids `5752` and `26980`, including Playwright driver and Chromium child processes.
- verification:
  - no remaining `crawlService-main` or `crawler_app.web` process except VS Code and the checking shell.
  - port `3000` is no longer listening.
- note: VS Code was left open intentionally.

## Superseded Slice: Naver News API Collection
- date: 2026-05-14
- run_id: `crawler-alpha-20260514-naver-api`
- alpha_session_key: `alpha-crawler-20260514-naver`
- alpha_topic_instance_key: `crawler-naver-news-api-20260514`
- alpha_worker_namespace: `crawler-alpha-naver`

## Alpha Pre-Edit Gate: Naver News API Collection
- classification: non-trivial
- reason: API credential loading, live Naver API pagination, JSON artifact generation, config changes, and tests are affected.
- Alpha wave required: yes
- waiver: none
- next action: Alpha developer worker implements bounded slice; reviewer, QA, and auditor inspect findings before final ruling.

## External Source Confirmation
- Naver official Search News API docs confirmed:
  - endpoint: `https://openapi.naver.com/v1/search/news.json`
  - method: GET
  - parameters: `query`, `display`, `start`, `sort`
  - `display` max: 100
  - `start` max: 1000
  - headers: `X-Naver-Client-Id`, `X-Naver-Client-Secret`
- Source: `https://developers.naver.com/docs/serviceapi/search/news/news.md`

## Naver Slice Checkpoint
- current goal: collect Naver News API results for `최태원` through page 2 and save each API item as a JSON file.
- completed: local `.env` credential loading, bounded Naver config, two-page pagination, per-item JSON output, API host validation, UI safety guard, compact logging, strict Naver parser option validation, unit tests, live CLI verification, and Playwright UI screenshots.
- not done: Git repository initialization, recurring JOB scheduler, automatic report email, cancel button, and long-term article-retention policy.
- next action: decide Git repository strategy or start the next Alpha slice for batch JOB orchestration/rate policy.
- related paths:
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\crawler_app\naver_news_api.py`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\crawler_app\workflow.py`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\crawler_app\web.py`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\crawler_app\logging_utils.py`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\configs\네이버뉴스_최태원_2페이지.json`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\tests\test_naver_news_api.py`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\tests\test_workflow.py`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\qa-artifacts\naver-news-ui-20260514`
- validation:
  - `python -m unittest discover -s tests` passed 87 tests.
  - live CLI run `20260514T012241Z` returned 20 items and 20 per-item JSON files; its former article-body extraction evidence is superseded by the later API-only decision.
  - Playwright UI screenshots captured home and config pages.
- ruling: conditional pass, with remaining risks recorded in `DECISION_RULING.md`.

## Naver Editor UI Rework Checkpoint
- current goal: make Naver API settings appear only on the existing `네이버` editor and preserve all other site editors, using `기후에너지부_보도자료` as the reference generic editor.
- completed:
  - scoped `Naver News API` panel to config id/name `네이버`.
  - confirmed `기후에너지부_보도자료` does not render the Naver panel.
  - converted `configs\네이버.json` to official Naver Search News API config with `{search_term}`, multiple `search_terms`, `display=20`, and `loop_limit=20`.
  - mapped UI latest-news count to both API `display` and parser `loop_limit`.
  - removed accidental QA-created `configs\new_site.json`.
  - added tests for panel scoping and Naver API field handling.
  - added run confirmation on the index page.
- not done:
  - Git repository initialization.
  - streaming response-size cap.
  - full JOB/scheduler/email/cancel UI.
- next action: decide Git strategy or proceed to JOB/rate policy slice.
- validation:
  - `python -m unittest discover -s tests` passed 94 tests.
  - Playwright confirmed `/configs/네이버` has Naver panel and `/configs/기후에너지부_보도자료` does not.
- ruling: conditional pass.

## Pause Checkpoint: Naver UI Credentials/Display
- date: 2026-05-14
- status: paused on user request
- current goal: allow users to configure Naver API display, search terms, and related Naver options from the existing `네이버` editor UI. Credential editing from the UI was later removed.
- completed:
  - superseded: Naver credential fields were temporarily shown only on `네이버`, then removed again so credentials stay in `.env` / process environment.
  - API `display` is configurable separately from `loop_limit`.
  - Secret value is not rendered in the editor HTML.
  - Non-Naver reference editor `기후에너지부_보도자료` does not show the Naver panel.
  - Fixed panel initialization so opening and saving the editor preserves Naver API fields.
  - Restored `configs\네이버.json` to the intended bounded API-only config.
- validation completed:
  - `node --check static\app.js`
  - `.venv\Scripts\python.exe -m py_compile crawler_app\naver_news_api.py crawler_app\web.py tests\test_naver_news_api.py tests\test_web.py`
  - `.venv\Scripts\python.exe -m unittest tests.test_naver_news_api tests.test_web -v`
  - `.venv\Scripts\python.exe -m unittest discover -s tests` passed 97 tests.
- blocker:
  - live UI run `POST /configs/네이버/run` currently fails with `AttributeError: 'NoneType' object has no attribute 'get'`.
  - direct `ConfigurableCrawler(config_path='configs/네이버.json').crawl()` reproduces the same failure.
  - diagnostics show Naver parser path is selected, but no parser items are produced before the error is recorded.
- next one action:
  - on resume, capture the focused traceback around `_run_parser_workflow` / `_fetch_parser_items`, then fix the `NoneType.get` source and add a regression test.
- related paths:
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\crawler_app\web.py`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\templates\editor.html`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\static\app.js`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\crawler_app\naver_news_api.py`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\crawler_app\workflow.py`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\configs\네이버.json`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\tests\test_web.py`
- ruling: hold.

## Resume Completion: Naver UI Credentials/Display
- date: 2026-05-14
- status: completed with conditional pass.
- completed after resume:
  - captured focused traceback for the live UI failure.
  - fixed `BeautifulSoup` node `attrs=None` handling in Naver body cleanup.
  - added regression coverage for missing node attrs.
  - added regression coverage that `display` can differ from `loop_limit` through the save route.
  - restarted the local UI server on `http://127.0.0.1:3000/`.
  - reran direct crawler and live UI run.
- validation:
  - `node --check static\app.js`: pass.
  - `.venv\Scripts\python.exe -m py_compile crawler_app\naver_news_api.py crawler_app\web.py tests\test_naver_news_api.py tests\test_web.py`: pass.
  - `.venv\Scripts\python.exe -m unittest tests.test_naver_news_api tests.test_web -v`: 25 tests pass.
  - `.venv\Scripts\python.exe -m unittest discover -s tests`: 99 tests pass.
  - direct `ConfigurableCrawler(config_path='configs/네이버.json').crawl()`: success, 40 items.
  - live UI `POST /configs/네이버/run`: HTTP 200, success true, 40 items.
- proof:
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\qa-artifacts\naver-ui-credentials-display-20260514\result-summary.json`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\qa-artifacts\naver-ui-credentials-display-20260514\naver-run-result.html`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\qa-artifacts\naver-ui-credentials-display-20260514\naver-editor-credentials-display.png`
- output inspection:
  - total item JSON files: 40.
  - secret was not present in editor HTML and was not found outside `.env` in local scan.
- next one action:
  - keep current Naver implementation API-only; schedule publisher-page body collection as a separate future slice only if explicitly approved.
- ruling: conditional pass.

## Naver API-Only Output Decision
- date: 2026-05-14
- status: completed with conditional pass.
- user decision:
  - remove current article-body extraction from production code.
  - remember article body extraction as a future feature.
- current goal:
  - Naver runs should store official Naver News API fields and normalized local metadata only.
- completed:
  - removed active article-page fetch and HTML body extraction path from `crawler_app\naver_news_api.py`.
  - removed article-body parameters from Naver workflow execution.
  - removed Naver article-body controls from `templates\editor.html` and `static\app.js`.
  - removed article-body settings from `configs\네이버.json` and `configs\네이버뉴스_최태원_2페이지.json`.
  - added normalization stripping for stale Naver article-body fields.
  - updated tests to API-only expectations.
- validation:
  - `node --check static\app.js`: pass.
  - modified Python compile check: pass.
  - focused Naver/workflow/web tests: 85 tests pass.
  - full test suite: 90 tests pass.
  - live UI Naver run: success true, 40 item JSON files.
  - stale generated outputs/logs/QA artifacts sanitized to remove historical article-body fields.
  - broad `네이버뉴스` UI run intentionally blocked with HTTP 400 until a bounded `loop_limit` is configured.
- proof:
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\qa-artifacts\naver-api-only-20260514\result-summary.json`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\qa-artifacts\naver-api-only-20260514\naver-run-result.html`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\qa-artifacts\naver-api-only-20260514\naver-editor-api-only.png`
- output inspection:
  - article-body field hits: 0.
  - article body field hits: 0.
  - empty `description` count in latest verified run: 0.
  - editor article-body controls present: false.
  - stale article-body scan across `outputs`, `logs`, and `qa-artifacts`: no hits.
  - broad `네이버뉴스` blocked: true.

## Naver API-Only Final Cleanup Checkpoint
- date: 2026-05-14
- status: completed.
- current goal: resolve final reviewer/auditor blockers by removing stale Naver body-collection settings from old QA artifacts and correcting stale state docs.
- completed:
  - sanitized old Naver QA payload artifacts so they no longer carry deprecated body-collection options.
  - corrected `TASK_CONTRACT.md`, `TASK_PLAN.md`, `RUN_CONTEXT.md`, `GUI_QA_RESULT.md`, and `DECISION_RULING.md` so the active Naver slice is API-only and publisher-page body collection is deferred.
  - kept the legacy generic URL alias field untouched because it is shared by non-Naver crawler schemas and is only a URL alias, not body extraction.
- next one action:
  - rerun tests and final Alpha reviewer/QA/auditor checks.
- validation:
  - pending in this checkpoint.
- ruling:
  - pending final worker pass.

## Naver CLI Safety Cleanup Checkpoint
- date: 2026-05-14
- status: completed.
- current goal: make Naver API run bounds consistent across UI and CLI/orchestrator paths.
- completed:
  - added workflow validation requiring Naver `loop_limit` and enforcing `page_limit<=10`, `loop_limit<=100`.
  - updated README Naver CLI example to use the bounded `configs\네이버.json` and document required bounds.
  - added regression tests for missing and too-broad Naver CLI limits.
- next one action:
  - final report to user.
- validation:
  - `node --check static\app.js`: pass.
  - Python compile check for changed Naver/workflow/web/test files: pass.
  - focused workflow/web/Naver tests: 88 tests pass.
  - full test suite: 93 tests pass.
  - broad legacy `configs\네이버뉴스.json` CLI run: blocked before crawl with `steps[1].loop_limit is required for Naver News API.`
- ruling:
  - pass. Final auditor confirmed the prior CLI broad-run blocker is resolved.
- future slice:
  - article body extraction should return only as a separate publisher-policy slice with per-domain parsers, explicit allowlists, and retention/copyright policy.
- ruling: conditional pass.

## Naver Credential UI Removal Checkpoint
- date: 2026-05-14
- status: completed.
- current goal: remove Naver Client ID / Client Secret editing from the UI and rely on `.env` / process environment only.
- completed:
  - removed Client ID and Client Secret fields from the Naver editor panel.
  - removed web-layer `.env` read/write helpers and save-route credential handling.
  - added save-route and workflow-normalization scrubbing for stale `naver_client_id` / `naver_client_secret` payload keys.
  - kept `crawler_app\naver_news_api.py` runtime credential loading from `os.environ`; app startup loads `.env` through `crawler_app\__init__.py`.
  - updated tests to assert credentials are not rendered in the Naver editor.
- validation:
  - `node --check static\app.js`: pass.
  - Python compile check for changed web/test files: pass.
  - focused web/Naver/workflow tests: 87 tests pass.
  - full test suite: 92 tests pass.
  - live editor HTML check on `http://127.0.0.1:3000/configs/네이버`: Naver panel present, credential fields absent, API display and per-search-term latest-news count present.
  - direct crafted POST with stale credential keys: route returned 303 and saved config contained neither key.
- API parameter note:
  - Naver official docs define `display` as one-request result count, default 10 and max 100; this product also uses `loop_limit` as the saved item cap per search term.
- ruling:
  - pass. Reviewer, QA, and auditor returned PASS after stale-payload credential scrubbing.

## Naver Single Count UI Checkpoint
- date: 2026-05-14
- status: completed.
- current goal: remove confusing duplicate news-count controls so the user sets exactly one count per search term.
- completed:
  - removed separate `API display` and `검색어당 최신 뉴스 개수` fields from the Naver editor.
  - added one `검색어당 가져올 뉴스 개수` field.
  - updated `static\app.js` so the single count writes both URL `display` and parser `loop_limit`.
  - hid the generic `실행 단계` section on the Naver editor so its parser `limit` input cannot appear as a second count field.
  - updated workflow normalization so stale mismatched payloads sync URL `display` from `loop_limit`.
  - updated tests for single-count UI and normalization behavior.
- validation:
  - `node --check static\app.js`: pass.
  - Python compile check with bytecode disabled: pass.
  - focused web/workflow/Naver tests: 87 tests pass.
  - full test suite: 92 tests pass.
  - live editor HTML check: Naver panel present, `검색어당 가져올 뉴스 개수` present, generic `실행 단계` and parser `loop_limit` input absent, `API display` and old separate latest-count field absent.
  - JS payload probe: count `1` produced `display=1` and `loop_limit=1`; count `100` produced `display=100` and `loop_limit=100`.
- ruling:
  - pass. Reviewer, QA, and auditor returned PASS after hiding the generic parser limit on the Naver editor.

## Git Push Setup Checkpoint
- date: 2026-05-14
- status: completed.
- current goal: configure the crawler product folder so the user can review Git state and run any push/merge command manually from VS Code.
- completed:
  - initialized Git repository in `C:\AI_JOB\firstproject\crawler_project\crawlService-main`.
  - set branch to `main`.
  - added remote `origin` initially as `https://github.com/hgz-902/test_crawl`; later corrected `origin` to `https://github.com/K-Ternag/crawlService`.
  - hardened `.gitignore` for `.env`, `.venv`, logs, outputs, QA artifacts, `$outDir`, and Office temporary `~$*` files.
  - created initial local commit `Initial crawler project`.
  - verified GitHub CLI auth is active for account `hgz-902`.
- validation:
  - `git status --short --branch`: clean on `main` before this checkpoint update.
  - actual remote `https://github.com/K-Ternag/crawlService` is not empty and is not history-compatible with local `main`.
  - `git ls-files` check found no `.env`, `.venv`, logs, outputs, QA artifacts, `$outDir`, or Office temp files tracked.
  - secret scan found no real Naver key values in tracked source; only `.env.example` placeholders mention `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET`.
- next user action:
  - review the local/remote divergence and choose a branch/merge strategy; Codex should not directly run `git push` in the crawler-site delivery loop.
- ruling:
  - pass. Git is configured for manual user operation; direct push is intentionally outside the Codex process flow.

## Origin Main Comparison Server Checkpoint
- date: 2026-05-14
- status: completed.
- current goal: run the user's origin-main copy at `C:\AI_JOB\firstproject\crawler_project\origin\crawlService-main` on port 3001 for direct visual comparison.
- completed:
  - started the origin-main copy with the existing crawler virtualenv on `http://127.0.0.1:3001/`.
  - patched only the origin copy's `crawler_app\web.py` template-response call style for compatibility with the currently installed FastAPI/Starlette version.
  - updated process memory so Codex does not directly run `git push`; the user owns push/merge execution.
- not done:
  - no origin-main repository merge, rebase, force push, or product behavior change was performed.
- next one action:
  - user opens `http://127.0.0.1:3001/` and compares the origin UI with the current local crawler UI.
- related files/paths:
  - `C:\AI_JOB\firstproject\crawler_project\origin\crawlService-main\crawler_app\web.py`
  - `C:\AI_JOB\firstproject\MEMORY.md`
  - `C:\AI_JOB\firstproject\memory\2026-05-14.md`
- validation result or blocker:
  - `GET /` returned 200 with title `설정 목록`.
  - `GET /configs/네이버` returned 200 with title `Workflow 설정`.
  - screenshot proof saved under `C:\AI_JOB\firstproject\crawler_project\crawlService-main\qa-artifacts\origin-main-3001-20260514`.
  - local `main` and `origin/main` still have no merge base; Git push remains manual-user territory.

## Test Naver Config Removal Checkpoint
- date: 2026-05-14
- status: completed.
- current goal: remove the temporary `네이버뉴스_최태원_2페이지` crawler config before starting the next crawler target.
- completed:
  - deleted `C:\AI_JOB\firstproject\crawler_project\crawlService-main\configs\네이버뉴스_최태원_2페이지.json`.
- not done:
  - no runtime code, UI logic, Naver production config, or Git push was changed.
- next one action:
  - proceed to the next target-site crawler slice after the user chooses the target.
- related files/paths:
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\configs\네이버뉴스_최태원_2페이지.json`
- validation result or blocker:
  - file no longer exists.
  - `GET http://127.0.0.1:3000/` returned 200 and did not contain `네이버뉴스_최태원_2페이지`.

## Daum News Slice Checkpoint
- date: 2026-05-14
- status: in_progress.
- current goal: implement and verify a bounded Daum news collection target for search terms `최태원` and `SK`.
- completed:
  - confirmed direct Daum news search HTML request redirects to CAPTCHA, so direct search-result scraping is not a stable primary path.
  - confirmed official Kakao Daum Search public docs list Web, Video, Image, Blog, Book, and Cafe APIs, not a news-specific endpoint.
  - selected implementation path: Kakao Daum Web Search API filtered to Daum news hosts, with `KAKAO_REST_API_KEY` read from environment.
  - spawned Alpha developer worker for implementation.
- not done:
  - implementation handoff, reviewer/QA/auditor judgment, tests, browser proof, and live API validation.
- next one action:
  - integrate developer worker output and run focused tests.
- related files/paths:
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main`
  - expected new runtime module: `crawler_app\daum_news_api.py`
  - expected config: `configs\다음.json`
- validation result or blocker:
  - current external blocker for live API smoke: `KAKAO_REST_API_KEY` has not yet been confirmed in the environment.

## Daum News Slice Final Checkpoint
- date: 2026-05-14
- status: completed.
- current goal: deliver a Daum news collection target that works from the UI with search terms `최태원` and `SK`.
- completed:
  - saved the user-provided Kakao REST API key into ignored local `.env`.
  - implemented Daum parser support using Kakao Daum Web Search API, with query hint `site:v.daum.net` and explicit filtering to `news.daum.net` / `v.daum.net`.
  - added `configs\다음.json` with search terms `최태원` and `SK`, `sort=recency`, and one count field mapped to `loop_limit=20`.
  - added Daum-only editor UI panel and JavaScript config generation.
  - kept Daum credentials out of UI/configs/logged headers; root and nested stale credential fields are stripped during normalization/save.
  - hardened Daum API calls with no redirect following and post-response URL validation.
  - disabled Daum API preview fetches to avoid accidental quota use.
  - changed Daum per-term manifests to store relative item file paths.
- not done:
  - no git push was run; user owns push/merge execution.
  - no article body scraping was added.
- next one action:
  - user can inspect `http://127.0.0.1:3000/configs/다음` and run the Daum crawler from the UI.
- related files/paths:
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\crawler_app\daum_news_api.py`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\configs\다음.json`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\qa-artifacts\daum-news-ui-20260514`
- validation result or blocker:
  - `node --check static\app.js`: pass.
  - `.venv\Scripts\python.exe -m unittest discover -s tests`: 106 tests pass.
  - live UI run `POST /configs/다음/run`: success, 40 items total (`최태원`: 20, `SK`: 20).
  - latest live run HTML saved to `qa-artifacts\daum-news-ui-20260514\daum-run-live-final.html`.
  - tracked-source secret scan found no provided Kakao key outside ignored `.env`.
  - Alpha developer, reviewer, QA, and auditor worker flow completed; final reviewer/QA/audit passed after rework.

## API Count Semantics Rework Checkpoint
- date: 2026-05-14
- status: completed.
- current goal: make Naver/Daum news count behavior unambiguous from the UI by exposing one count field and using fixed provider fetch parameters internally.
- completed:
  - Naver fixed fetch parameters: `display=100`, `start=1`, `page_limit=1`; user-facing count maps only to `loop_limit`.
  - Daum fixed fetch parameters: `size=50`, `page=1`, `page_limit=2`; user-facing count maps only to `loop_limit`.
  - fixed Daum runtime so `loop_limit <= 50` no longer shrinks the fixed two-page fetch down to one page.
  - fixed Naver sort persistence by saving `sort` in the parser step as well as the URL.
  - made the Naver editor panel detect Naver API URL/step configs, including renamed or stale configs such as `네이버뉴스`.
  - updated `configs\네이버뉴스.json` with fixed `display=100`, `page_limit=1`, and bounded `loop_limit=30`.
  - changed Naver and Daum preview behavior to skip external API calls.
  - stripped provider credentials from preview rerender payloads.
  - changed Naver manifest `item_files` to relative `items\item_####.json` paths.
- not done:
  - no git push was run; user owns push/merge execution.
- next one action:
  - user can inspect `http://127.0.0.1:3000/configs/네이버`, `http://127.0.0.1:3000/configs/네이버뉴스`, and `http://127.0.0.1:3000/configs/다음`.
- related files/paths:
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\crawler_app\workflow.py`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\crawler_app\web.py`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\crawler_app\daum_news_api.py`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\crawler_app\naver_news_api.py`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\static\app.js`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\templates\editor.html`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\qa-artifacts\api-count-fixed-20260514`
- validation result or blocker:
  - `node --check static\app.js`: pass.
  - `.venv\Scripts\python.exe -m unittest discover -s tests`: 112 tests pass.
  - browser UI proof: Naver and Daum editors each show exactly one provider count field and no cross-provider panel pollution.
  - bounded live Naver smoke: success, 3 saved records, runtime URL `display=100&start=1&sort=sim`, preview skipped external API.
  - bounded live Daum smoke: success, 3 saved records, runtime URL `page=1&size=50`, final URL `page=2&size=50`, preview skipped external API.
  - tracked-source/QA-artifact secret scan found no provided real API keys outside ignored `.env`.

## Naver/Daum Cumulative Output Checkpoint
- date: 2026-05-14
- status: completed.
- current goal: prevent Naver/Daum API result JSON files from being reset or overwritten on repeated runs.
- completed:
  - changed Naver provider saves to write each run under `<term_dir>\items\YYYYMMDD_n`.
  - changed Daum provider saves to write each run under `<term_dir>\items\YYYYMMDD_n`.
  - changed workflow-level API manifests to write under `<output_dir>\runs\YYYYMMDD_n\workflow_records.json`.
  - for Naver/Daum API parser runs, kept reported output paths under the root `<output_dir>\<NNN_search_term>\items\YYYYMMDD_n` shape instead of `filter\<term>`.
  - added UI run safety that blocks `output_dir` paths resolving outside the crawler project folder.
- not done:
  - no retention/quota cleanup policy was added; accumulated runs are intentionally preserved.
  - no git push was run; user owns push/merge execution.
- next one action:
  - user can run Naver/Daum again from the UI and inspect the new dated run folder under the matching search-term directory.
- related files/paths:
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\crawler_app\naver_news_api.py`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\crawler_app\daum_news_api.py`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\crawler_app\workflow.py`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\crawler_app\web.py`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\qa-artifacts\cumulative-output-20260514-after-review`
- validation result or blocker:
  - `.venv\Scripts\python.exe -m unittest discover -s tests`: 116 tests pass.
  - proof script confirmed:
    - `qa-artifacts\cumulative-output-20260514-after-review\naver\002_SK\items\20260514_3\naver_news_api.json`
    - `qa-artifacts\cumulative-output-20260514-after-review\daum\002_SK\items\20260514_3\daum_news_api.json`
    - `qa-artifacts\cumulative-output-20260514-after-review\naver\runs\20260514_3\workflow_records.json`
    - `qa-artifacts\cumulative-output-20260514-after-review\daum\runs\20260514_3\workflow_records.json`
  - tracked-source secret scan found no provided real API keys outside ignored `.env`.
