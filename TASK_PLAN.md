# Task Plan

## Current Slice: Environment And UI Bring-Up

### Completion Criteria
- Proposed implementation slices are recorded in task docs.
- A local `.venv` exists and dependencies are installed.
- Existing unit tests have been run and the result is recorded.
- Existing web UI is running on localhost for inspection.
- The project folder is opened in VS Code.
- Git repository state is checked and recorded.

### Steps
1. Record Alpha task contract and run context.
2. Create or reuse `.venv`.
3. Install `requirements.txt`.
4. Install Playwright Chromium if app/test startup requires it.
5. Run existing tests.
6. Start FastAPI UI on an available localhost port.
7. Open project folder in VS Code.
8. Record decision ruling and remaining risks.

## Future Implementation Slices

### Slice 1: Target-Site Parameter Crawling Verification
- Verify representative configs from CLI and UI.
- Capture output/log paths and failure modes.
- Avoid broad live crawling until rate policy is defined.

### Slice 2: Site-Specific Batch Interval And Block-Prevention Policy
- Add a general policy layer, preferably config-driven.
- Include interval, cooldown, retry, timeout, user-agent, max records, and block-detection fields.
- Keep site-specific rules out of common code unless generally reusable.

### Slice 3: Batch JOB Orchestrator Model
- Add job definitions, run state, run history, status, and report artifact references.
- Decide file-backed JSON versus SQLite before implementation.

### Slice 4: JOB Orchestrator UI
- Add job list/view/create/edit/run-now screens.
- Show running, success, failed, skipped, and blocked states.

### Slice 5: JOB Automatic Execution
- Choose Windows Task Scheduler or in-app scheduler.
- Include restart behavior, missed-run policy, and duplicate-run prevention.

### Slice 6: Report Then Email
- Generate report after a run.
- Send email only through env-gated credentials.
- Include dry-run mode, duplicate-send protection, and failure logging.

### Slice 7: Git Commit Readiness
- Confirm whether to initialize a repo in `crawlService-main` or move it under an existing repo.
- Verify VS Code terminal can run `git status`, `git add`, and `git commit` after user config is available.

### Slice 8: Integration QA And Audit
- Run unit tests, CLI smoke, UI browser QA, scheduler dry-run, and email dry-run.
- Record final `DECISION_RULING.md`.

## Superseded Implementation Plan: Naver News API Collection

### Status
- 2026-05-14: completed with conditional pass.
- Live run `20260514T012241Z` collected 20 Naver News items for `최태원` across 2 pages and wrote 20 per-item JSON files. Its article-body extraction path is now superseded by the API-only decision.
- Remaining conditions are Git repository setup, article-retention policy, and future JOB/scheduler/email slices.

### Completion Criteria
- `최태원` Naver News API config collects two API pages safely.
- Each API item is saved to an individual JSON file.
- Each JSON includes search metadata and official API title/description/link fields, plus normalized local identifiers.
- Existing tests pass.
- A live run succeeds or records concrete API/content blockers without exposing secrets.

### Steps
1. Create ignored local API credential file and load it from app startup.
2. Extend Naver API parser to support bounded pagination and configurable API result count.
3. Defer publisher-page body extraction to a later slice.
4. Save each Naver article as a separate JSON file under a dated output folder and write a manifest.
5. Add/update a bounded `configs/네이버뉴스_최태원_2페이지.json`.
6. Add tests for parser pagination/API normalization/output files.
7. Run live verification and inspect produced JSON files.

## Active Implementation Plan: Naver API Editor UI And Body Cleanup

### Completion Criteria
- A user can open a config in the UI and select/use Naver News API settings without manually editing the start URL and parser step.
- A user can enter multiple search terms and a latest-news count per term.
- The UI can set sort order and bounded API result count.
- The generated config remains compatible with the existing Naver parser path.
- Article body extraction is deferred to a later publisher-parser slice.
- Tests and browser QA pass.

### Steps
1. Add a Naver settings panel to the editor UI.
2. Add JavaScript to detect existing Naver configs and generate/update Naver parser config fields.
3. Add body cleanup helpers and tests for boilerplate removal.
4. Add UI/web tests for saved Naver settings payload where practical.
5. Run unit tests, browser screenshot QA, and a bounded smoke check.
6. Update ruling and remaining risks.

## Active Implementation Plan: Naver API-Only Output

### Status
- 2026-05-14: completed with conditional pass.

### User Decision
- Article-body HTML extraction should be deferred.
- Current production code should save only the official Naver News API result fields and local normalized metadata.

### Completed
- Removed active Naver publisher-page fetch path from `crawler_app\naver_news_api.py`.
- Removed Naver article-body options from workflow execution.
- Removed Naver article-body controls from the editor UI.
- Updated `configs\네이버.json` and `configs\네이버뉴스_최태원_2페이지.json` to API-only collection.
- Added normalization guard so stale Naver article-body fields are stripped from legacy configs/payloads.
- Updated tests to assert API-only behavior and absence of article-body fields.

### Validation
- `node --check static\app.js`: pass.
- Python compile check for modified source/tests: pass.
- `.venv\Scripts\python.exe -m unittest tests.test_naver_news_api tests.test_workflow tests.test_web -v`: 85 tests pass.
- `.venv\Scripts\python.exe -m unittest discover -s tests`: 90 tests pass.
- live UI run `/configs/네이버/run`: success true, 40 item JSON files, no article-body fields, empty `description` count 0 for the verified run.
- stale generated outputs/logs/QA artifacts were sanitized so broad scans no longer find historical article-body field names.
- broad legacy `네이버뉴스` remains intentionally blocked by the UI safety guard until a bounded `loop_limit` is configured.

### Future Slice
- Article body collection may return later as a separate domain-policy slice with per-publisher parsers, explicit allowlists, retention/copyright policy, and separate QA.

## Active Implementation Plan: Daum News API-Oriented Collection

### Completion Criteria
- `다음` appears in the crawler UI as a configurable Daum news collection target.
- The Daum editor has a Daum-only settings panel and does not add Daum controls to unrelated configs.
- A user can set multiple search terms and one count field; `1` means one item per term and `100` means up to 100 items per term.
- Runtime uses `KAKAO_REST_API_KEY` from `.env` / process environment and does not expose the key in UI/config/logs.
- Runtime uses Kakao Daum Web Search API and filters results to Daum news hosts because Daum news search HTML redirects to CAPTCHA and no public news-specific API was found.
- Tests and browser proof pass; live API proof is either completed with a provided key or blocked with a precise missing-key reason.

### Steps
1. Add Daum provider module for Kakao Daum Web Search API parsing/paging/saving.
2. Add workflow parser attr `daum`, validation, source URL inference, and output metadata.
3. Add Daum-only editor panel and JavaScript config generation.
4. Add `configs\다음.json` with search terms `최태원` and `SK`.
5. Add focused parser/workflow/web tests.
6. Run unit tests and local UI browser proof.
7. Run live API smoke only if `KAKAO_REST_API_KEY` is available; otherwise mark validation as blocked by missing credential.
8. Run reviewer, QA, and auditor roles before final ruling.

## Pause Checkpoint: Naver UI Credentials/Display And Runtime Regression

### Status
- 2026-05-14: paused by user request.
- Do not continue implementation until the user explicitly resumes.
- Current ruling for this active slice is `hold`, not pass.

### Completed In This Turn
- Superseded: Naver-only editor credential fields and web-layer `.env` write helpers were temporarily added, then removed again. Current Naver credentials are read only from `.env` / process environment by runtime code.
- Added Naver-only editor UI fields for API `display` separate from `loop_limit`.
- Confirmed the Naver panel appears on `/configs/네이버`.
- Confirmed the Naver panel does not appear on `/configs/기후에너지부_보도자료`.
- Confirmed the rendered Naver editor does not expose stored credentials.
- Fixed a UI-save regression where opening and saving the Naver editor could reset Naver API fields; the editor now embeds initial config JSON and initializes the Naver panel from it.
- Restored `configs\네이버.json` to bounded API-only settings.
- Validation passed:
  - `node --check static\app.js`
  - `.venv\Scripts\python.exe -m py_compile crawler_app\naver_news_api.py crawler_app\web.py tests\test_naver_news_api.py tests\test_web.py`
  - `.venv\Scripts\python.exe -m unittest tests.test_naver_news_api tests.test_web -v`
  - `.venv\Scripts\python.exe -m unittest discover -s tests` passed 97 tests.

### Current Blocker
- Live UI run through `POST /configs/네이버/run` failed:
  - success: `False`
  - items: `0`
  - error: `'NoneType' object has no attribute 'get'`
  - artifact path: `qa-artifacts\naver-ui-credentials-display-20260514\naver-run-result.html` may be missing because the PowerShell request treated HTTP 500 as an exception before writing the file.
- Direct `ConfigurableCrawler(config_path='configs/네이버.json').crawl()` reproduced the same failure.
- Diagnostics show parser path reached `parser_name=naver`, `search_terms=['최태원', 'SK하이닉스']`, but `parser_item_count=0` before the `AttributeError`.

### Next Action On Resume
1. Reproduce with a focused traceback or temporary narrow instrumentation around `_run_parser_workflow` / `_fetch_parser_items`.
2. Fix the `NoneType.get` source without changing broad crawler behavior.
3. Add a regression test for the failing `configs\네이버.json` shape.
4. Rerun full tests and live UI run.
5. Only then move `DECISION_RULING.md` back from `hold` to `conditional pass` or `pass`.

### Resume Result
- status: conditional pass.
- completed:
  - focused traceback captured the `attrs=None` crash inside Naver HTML cleanup.
  - runtime fix added in `crawler_app\naver_news_api.py`.
  - regression tests added for missing attrs and distinct `display`/`loop_limit` save behavior.
  - full test suite now passes 99 tests.
  - direct crawler and live UI run both succeed with 40 records.
- remaining follow-up:
  - design a later publisher-parser body collection slice with explicit allowlists, retention policy, and copyright posture.

## Active Implementation Plan: Google News RSS Collection

### Status
- 2026-05-14: completed, pending user-owned git push.

### Completion Criteria
- `구글` config uses Google News RSS with `action=parser`, `attr=google`.
- Search terms are `Chey Tae-won` and `SK`.
- No API key is required or stored for Google RSS.
- `loop_limit` controls the per-term saved item count.
- Outputs accumulate under `<output_dir>\<NNN_search_term>\items\YYYYMMDD_n`.
- Google parser accepts only `https://news.google.com` RSS URLs.
- Workflow output paths stay under the crawler project directory.

### Completed
- Updated `configs\구글.json` for English/US Google News RSS search terms `Chey Tae-won` and `SK`.
- Added Google RSS per-item JSON saves and dated run manifest directories.
- Kept Google no-filter output in the same root term path shape used by API providers, while preserving filtered-flow compatibility.
- Added Google RSS host validation and disabled RSS redirects.
- Added workflow-level `output_dir` containment.
- Added regression tests for Google URL rejection, output directory rejection, dated run allocation, loop limits, direct output path, and filtered path compatibility.

### Validation
- `node --check static\app.js`: pass.
- `.venv\Scripts\python.exe -m unittest tests.test_workflow -v`: 80 tests pass.
- `.venv\Scripts\python.exe -m unittest discover -s tests`: 119 tests pass.
- Earlier live Google RSS proof with config `loop_limit=20`: success, 40 total records, 20 for `Chey Tae-won` and 20 for `SK`.
- Follow-up live proof with the current saved config `loop_limit=5`: success, 10 total records, 5 for `Chey Tae-won` and 5 for `SK`; description fields had 0 HTML tag hits, 0 HTML entity hits, and 0 source-name suffix hits.
- Proof files:
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\qa-artifacts\google-news-rss-20260514-full\google\001_Chey Tae-won\items\20260514_1\google_news_rss.json`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\qa-artifacts\google-news-rss-20260514-full\google\002_SK\items\20260514_1\google_news_rss.json`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\qa-artifacts\google-news-rss-20260514-full\google\runs\20260514_1\workflow_records.json`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\qa-artifacts\google-rss-description-cleanup-current-config-20260514-v2\google\001_Chey Tae-won\items\20260514_1\google_news_rss.json`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\qa-artifacts\google-rss-description-cleanup-current-config-20260514-v2\google\002_SK\items\20260514_1\google_news_rss.json`
  - `C:\AI_JOB\firstproject\crawler_project\crawlService-main\qa-artifacts\google-rss-description-cleanup-current-config-20260514-v2\google\runs\20260514_1\workflow_records.json`

### Remaining Follow-Up
- No article body collection is included; publisher body parsing would be a separate per-domain policy slice.
- RSS `description` is cleaned to plain text only; Google RSS usually provides headline/snippet/source-style text, not full publisher article bodies.
- Retention/cleanup for accumulated RSS outputs remains a future operations slice.
- User will run git push manually.

## Superseded Historical Plan: TheBell Uniform HTML Collection

### Status
- 2026-05-14: superseded. This was the first parser-provider approach and is no longer the active TheBell implementation plan.
- Current TheBell follows the later generic execution-step plan and the Generic News Storage Restore plan below.

### Completion Criteria
- `더벨` config uses TheBell search with `action=parser`, `attr=thebell`.
- Search terms are `최태원` and `SK`.
- User-facing collection size is page count per search term, not article count.
- Each configured search result page is fetched, search-result article links are deduplicated, and each article URL is visited.
- Each saved item JSON contains title, article URL, visible body text, and status metadata when body access is limited.
- The TheBell editor panel appears only for TheBell configs.
- Tests, live proof, reviewer, QA, and auditor checks pass before final ruling.

### Steps
1. Completed: added TheBell provider module for search pagination, result-link extraction, article-detail parsing, and dated output saves.
2. Completed: added workflow parser attr `thebell`, validation, preview skip, and record metadata.
3. Completed: added TheBell-only editor panel and JavaScript config generation using `page_limit`.
4. Completed: added `configs\더벨.json` with search terms `최태원` and `SK`.
5. Completed: added focused parser/workflow/web tests.
6. Completed: unit tests and local live proof with `page_limit=1`.
7. Completed: reviewer, QA, and auditor workers returned conditional pass.
8. Not done by design: git push; user owns push execution.

### Validation
- `node --check static\app.js`: pass.
- `.venv\Scripts\python.exe -m py_compile crawler_app\thebell_news.py crawler_app\workflow.py crawler_app\web.py tests\test_thebell_news.py tests\test_workflow.py tests\test_web.py`: pass.
- `.venv\Scripts\python.exe -m unittest discover -s tests`: 136 tests pass.
- live proof: `qa-artifacts\thebell-live-20260514`, 10 records total, 5 for `최태원`, 5 for `SK`, no login/paywall/script phrase hits in saved body fields.
- UI proof: `qa-artifacts\thebell-ui-20260514\thebell-editor-3002.png` and `generic-editor-3002.png`; stale earlier screenshots without `-3002` should not be used as current proof.

### Superseded By
- Active TheBell UI/config now uses generic execution steps: `open_detail`, `extract_title`, `extract_body`.
- Active TheBell output now follows Yonhap-style generic-news storage: `filter\<NNN_search_term>\texts\YYYYMMDD`.
- `configs\다음.json`, `configs\산업부_보도자료.json`, and `pr_body.md` are unrelated dirty/untracked files and should not be staged as part of a TheBell-only commit unless the user intentionally includes them.

## Active Implementation Plan Update: TheBell Execution Steps

### Status
- 2026-05-14: completed; this update supersedes the earlier active TheBell parser-panel plan for the user-facing config.

### Completion Criteria
- `더벨` editor shows generic 실행 단계.
- TheBell workflow has no `download_file` step.
- TheBell workflow uses editable XPath steps for detail click, title extraction, and body extraction.
- UI does not expose a TheBell-specific parser panel or `thebell` parser attr option.
- Live proof confirms downloaded file count is zero and title/body extracts are produced.

### Completed
- Rewrote `configs\더벨.json` to `open_detail`, `extract_title`, `extract_body`.
- Removed TheBell special panel wiring from editor save/render code.
- Removed `thebell` from the parser attr UI choices.
- Added extract-step descendant cleanup support through `exclude_xpath`.
- Updated focused web/workflow tests.

### Validation
- `node --check static\app.js`: pass.
- `.venv\Scripts\python.exe -m py_compile crawler_app\workflow.py crawler_app\web.py tests\test_workflow.py tests\test_web.py`: pass.
- focused TheBell editor/save and extract cleanup tests: pass.
- `.venv\Scripts\python.exe -m unittest discover -s tests`: 123 tests pass after removing superseded TheBell parser tests.
- live proof: `qa-artifacts\thebell-workflow-steps-20260514`, 5 records for `최태원`, downloaded files `0`, extracted title/body files `10`.
- UI proof: `qa-artifacts\thebell-workflow-ui-20260514\thebell-editor.png`; actual rows were `open_detail`, `extract_title`, `extract_body`.

### Remaining Follow-Up
- For future HTML news sites, start from execution steps and add `download_file` only for sites with real attachments.

## Active Implementation Plan Update: TheBell Output Accumulation And Items Limit

### Status
- 2026-05-14: completed with conditional pass.

### Completion Criteria
- TheBell output follows the current storage contract after origin comparison.
- Generic execution-step manifests follow the current storage contract after origin comparison.
- `items` mode is proven to collect up to the configured item count on the current page.
- TheBell UI remains the same 3-step shape as before the correction.

### Completed
- First tested per-search-term `items\YYYYMMDD_n` run directories, then superseded that approach after the user asked to match the origin Yonhap storage structure.
- Kept artifact relocation collision-safe so repeated extracted text files are not overwritten inside the Yonhap-style target path.
- Generic workflow manifests now remain at the origin-compatible `filter\workflow_records.json`.
- Changed TheBell config to minimal NEWS search while keeping only `open_detail`, `extract_title`, and `extract_body`.
- Added focused tests for safe relocation and text extraction.

### Validation
- URL comparison proof: provided/no-date/minimal NEWS URLs produced 10 items; old ALL URL produced 5.
- `items` live proof: 10 records, 20 extracted title/body files.
- final storage proof: TheBell writes extracted text under the Yonhap-style `filter\<NNN_search_term>\texts\YYYYMMDD` path.
- UI proof: `qa-artifacts\thebell-output-items-ui-20260514\thebell-editor-items.png`.
- `node --check static\app.js`: pass.
- Python compile check: pass.
- latest `.venv\Scripts\python.exe -m unittest discover -s tests`: 124 tests pass.

### Remaining Follow-Up
- `items` mode is current-page only; multi-page collection should be handled only after explicit approval for an added UI/config step.
- Future site slices should document whether limit means current-page item count, page count, or API item count.

## Active Implementation Plan Update: Generic News Storage Restore

### Status
- 2026-05-14: completed with conditional pass.

### Completion Criteria
- News-style generic execution-step crawlers match origin Yonhap storage structure.
- TheBell no longer uses the temporary `items\YYYYMMDD_n` generic path.
- Government/attachment crawlers keep `산업부_보도자료` as the reference pattern.

### Completed
- Checked origin Yonhap workflow/config.
- Restored generic text extraction path to `filter\<NNN_search_term>\texts\YYYYMMDD`.
- Restored generic manifest path to `filter\workflow_records.json`.
- Kept no-overwrite relocation behavior for repeated runs.

### Validation
- TheBell live proof: 10 records saved under `qa-artifacts\thebell-yonhap-path-20260514\filter\001_최태원\texts\20260514`.
- Manifest path: `qa-artifacts\thebell-yonhap-path-20260514\filter\workflow_records.json`.
- `.venv\Scripts\python.exe -m unittest discover -s tests`: 124 tests pass.
- `node --check static\app.js`: pass.

## Active Implementation Plan Update: MarketInsight News Config

### Status
- 2026-05-14: completed with pass.

### Completion Criteria
- `마켓인사이트` config is added with a bounded shared workflow fix for the existing `open_detail` pagination mode.
- Config uses the existing news execution-step pattern.
- Search terms are `최태원` and `SK`.
- Live proof confirms page-number pagination, search result detail pages, and title/body text files.
- UI editor shows generic 실행 단계, not provider-specific API/RSS panels.

### Plan
1. Completed: checked `SOURCE_CHANGE_GUARDRAIL.md` and origin `연합뉴스` baseline.
2. Completed: inspected MarketInsight search URL and result/detail HTML structure.
3. Completed: added `configs\마켓인사이트.json`.
4. Completed: fixed shared workflow handling so `open_detail` pagination mode treats `loop_limit` as page count.
5. Completed: UI/editor proof.
6. Completed: full tests and final ruling.

### Validation
- smoke proof: `qa-artifacts\marketinsight-smoke-20260514`, 4 records across `최태원` and `SK` with title/body extracts.
- full live proof: `qa-artifacts\marketinsight-live-20260514`, 30 records, 60 extracted title/body files, 0 downloaded files, no workflow errors.
- pagination proof: `qa-artifacts\marketinsight-open-detail-pagination-20260514`, 60 records, 120 extracted title/body files, 0 downloaded files, no workflow errors.
- pagination evidence: `open_detail` was the only click loop, page 1 started at `page=1`, and page 2 started at `page=2`.
- full live manifest: `qa-artifacts\marketinsight-live-20260514\filter\workflow_records.json`.
- UI proof: `qa-artifacts\marketinsight-ui-20260514\home.png` and `qa-artifacts\marketinsight-ui-20260514\editor.png`.
- UI result JSON confirmed `마켓인사이트` appears in the list, editor opens, generic execution-step config is present, and Naver/Daum-specific panels are absent.
- pagination UI proof: `qa-artifacts\marketinsight-open-detail-pagination-ui-20260514\editor-3020.png` and `qa-artifacts\marketinsight-open-detail-pagination-ui-20260514\ui_result.json`; the editor contains only `open_detail`, `extract_title`, and `extract_body`, with `open_detail` set to `pagination/page_number/limit=2`.
- `.venv\Scripts\python.exe -m unittest discover -s tests`: 127 tests pass.
- `node --check static\app.js`: pass.

### Remaining Follow-Up
- Current config collects up to 2 MarketInsight search result pages per search term; users change the page count through the `open_detail` step `loop_limit` when mode is `pagination`.
- Per-page item count is inferred from the `open_detail` XPath pair rather than a separate item-limit field in this mode.
- Output accumulation source-code changes were considered, then canceled by user request; generic storage remains the previous `filter\<NNN_search_term>\texts\YYYYMMDD` plus `filter\workflow_records.json` shape.

## Active Implementation Plan Update: InvestChosun News Config

### Status
- 2026-05-14: completed with pass, pending user-owned push.

### Completion Criteria
- `인베스트조선` config is added as a generic HTML news execution-step site.
- No shared source code or UI source is changed for this site slice.
- Search terms are `최태원` and `SK`.
- `open_detail.loop_mode=pagination`, `pagination_mode=page_number`, and `loop_limit=2` collect pages 1 and 2 per search term.
- Title/body text is extracted from article detail pages.
- Obvious non-article body descendants such as image expand blocks and ranking/news recommendation blocks are excluded by config.
- UI editor shows generic 실행 단계 and no Naver/Daum provider panel.

### Completed
- Checked `SOURCE_CHANGE_GUARDRAIL.md` and origin `연합뉴스` baseline.
- Confirmed InvestChosun search URL: `https://www.investchosun.com/svc/news/search.html?q={search_term}&pn={page_number}`.
- Added `configs\인베스트조선.json`.
- Used direct list XPath `li > div.list_detail > dl > dt > a` so the workflow loop-index inference can resolve 10 articles per page.
- Added `exclude_xpath` to `extract_body` to remove `center_img` and `ranking` blocks without changing shared source code.

### Validation
- live proof: `qa-artifacts\investchosun-live-20260514-v2`, 40 records total, 20 for `최태원`, 20 for `SK`, 80 title/body extracted files, 0 downloads, no workflow errors.
- pagination proof: first URL `q=최태원&pn=1`, last URL `q=SK&pn=2`, recorded pages `[1, 2]`.
- body cleanup proof: `이미지 크게보기` hits `0`, `많이 본 뉴스` hits `0` in the verified v2 run.
- UI proof: `qa-artifacts\investchosun-ui-20260514\editor-3020.png` and `ui_result.json`; editor has `open_detail`, `extract_title`, and `extract_body`; Naver/Daum panels absent.
- `.venv\Scripts\python.exe -m unittest discover -s tests`: 127 tests pass.
- `node --check static\app.js`: pass.

### Remaining Follow-Up
- InvestChosun HTML may drift; update config XPath from the UI if result/detail structures change.
- Generic news output keeps Yonhap-style `filter\<NNN_search_term>\texts\YYYYMMDD` storage plus `filter\workflow_records.json`.
- No git push was run; user owns push execution.
