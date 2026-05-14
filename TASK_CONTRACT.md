# Task Contract

## Universal Shared Goal
Deliver a crawler improvement path that becomes actually runnable and verifiable, or clearly identify blockers with evidence, until the user can inspect the UI and code locally.

## Project Shared Goal
Reuse the existing config-driven crawler architecture while preparing a staged Alpha implementation program for:
- target-site parameter crawling verification
- site-specific batch interval and block-prevention policy
- batch JOB orchestrator UI
- automatic JOB execution
- email delivery immediately after report generation
- Git commit readiness from VS Code terminal

## Expected Deliverables
- Alpha task docs:
  - `TASK_CLASSIFICATION.md`
  - `TASK_CONTRACT.md`
  - `TASK_PLAN.md`
  - `RUN_CONTEXT.md`
  - `DECISION_RULING.md`
- Working local Python environment in `.venv`
- Existing tests executed with result recorded
- Existing FastAPI UI launched for user inspection
- Project opened in VS Code

## Project Team Binding
- Alpha runtime: Codex multi-agent harness
- Codex main session: orchestrator, local environment verifier, local UI truth owner
- OpenClaw: legacy fallback only; not used in this slice

## Role-Specific Small Goals
- developer: reserved for approved feature implementation after this setup slice
- reviewer: reserved for findings-first review of implementation changes
- QA: reserved for breaking UI/API/job/scheduler/email flows after implementation
- auditor: reserved for operational/security review of scheduling, email credentials, logs, and rollback
- orchestrator: record contract, prepare environment, verify local UI, and keep final ruling

## Connection Goals
- Keep site-specific behavior in `configs/*.json` where possible.
- Keep common crawler source free of site-specific hardcoding.
- Prefer durable docs and proof artifacts over long chat memory.
- Follow `SOURCE_CHANGE_GUARDRAIL.md` before any crawler source, UI, storage, parser/provider, or schema behavior change.
- When original behavior is needed, compare against `C:\AI_JOB\firstproject\crawler_project\origin\crawlService-main`, not against memory or the edited working tree.

## Preferred Context Package
- Root Alpha hot docs already read.
- Product read set:
  - `README.md`
  - `USEGUID.md`
  - `main.py`
  - `requirements.txt`
  - `crawler_app/`
  - `crawlers/`
  - representative `configs/*.json`
  - `tests/`
  - `SOURCE_CHANGE_GUARDRAIL.md`

## Source Change Guardrail
- Default for new crawler sites is config/XPath-only onboarding.
- News-style sites use original Yonhap behavior as the baseline.
- Government/attachment-style sites use `산업부_보도자료` as the baseline.
- Naver and Daum are API-backed exceptions.
- Shared source changes require a recorded reason, origin comparison, tradeoff notes, expected blast radius, and validation plan before editing.
- Every push that includes source-code changes must use `$git-push-change-log`.

## Active Risk References
- external-site blocking and rate limits
- Naver API credentials
- email credential leakage and duplicate delivery
- scheduler restart safety
- local Git repository absence
- Playwright browser dependency availability

## Preferred Commands
- create environment: `python -m venv .venv`
- install dependencies: `.venv\Scripts\python -m pip install -r requirements.txt`
- install browser runtime if needed: `.venv\Scripts\python -m playwright install chromium`
- test: `.venv\Scripts\python -m unittest discover -s tests`
- run UI: `.venv\Scripts\python -m uvicorn crawler_app.web:app --host 127.0.0.1 --port 3000`

## Slice Plan
1. Environment and baseline slice.
2. Target-site execution verification slice.
3. Site policy slice.
4. JOB model and orchestrator slice.
5. JOB UI slice.
6. Automatic execution slice.
7. Report and email slice.
8. Integration QA and audit slice.

## Superseded Slice: Naver News API Discovery

### User Goal
For Naver News, search `최태원`, collect bounded official Search News API results, and save each news item as its own JSON file.

### Constraints
- Do not scrape Naver search result pages.
- Use the official Naver Search News API for result discovery.
- Store provided API credentials in a local ignored credential file.
- Do not print secrets in logs or final reports.
- Keep the current config-driven crawler architecture.
- Add safe limits so this slice does not repeat the overly broad crawl incident.

### Expected Deliverables For This Slice
- Local ignored API credential file.
- Naver API config for `최태원`, two pages, bounded result count.
- Code that supports Naver API pagination without publisher-page body fetching.
- Individual JSON files per article plus a manifest.
- Unit tests for pagination, API field normalization, and individual output.
- Live verification using the provided credentials, with secrets redacted from reports.

## Active Slice: Naver API Editor UI And API-Only Output

### User Goal
Make the Naver News API crawler configurable from the existing editor UI instead of requiring manual start URL and step editing. Users should be able to save multiple search terms, choose latest/relevance order, choose how many latest news items to collect per search term, and keep the current implementation API-only. Full article body collection is deferred to a later publisher-parser slice.

### Expected Deliverables For This Slice
- A Naver News API settings panel in `templates/editor.html` and `static/app.js`.
- The panel generates the existing config structure:
  - `start_url` using `https://openapi.naver.com/v1/search/news.json`
  - `search_terms`
  - parser step with `action=parser`, `attr=naver`
  - `loop_limit`, `page_limit`
- Existing generic workflow editor remains usable for non-Naver configs.
- Article body collection is explicitly deferred rather than partially scraped from publisher pages.
- Tests cover generated Naver config behavior and API-only output.
- Browser proof shows the Naver panel is visible and usable.

### Role-Specific Small Goals
- developer: implement UI/config generation and body cleanup with focused tests.
- reviewer: find structural regressions, brittle UI/config coupling, and maintainability issues.
- QA: verify multi-search-term config, latest count limits, saved JSON payload, UI rendering, and body cleanup edge cases.
- auditor: verify secret isolation, overbroad crawl safety, data retention/logging, and hostile HTML risks.

## Active Slice: Daum News API-Oriented Collection

### User Goal
Make Daum news collection work well for the crawler product. Initial example search terms are `최태원` and `SK`.

### Discovery Result
- Direct Daum news search HTML access redirected to `captcha.search.daum.net`, so broad HTML scraping is not a stable collection path.
- Official Kakao Developers Daum Search documentation lists Web, Video, Image, Blog, Book, and Cafe APIs, but no news-specific public API.
- The implementation path is therefore Kakao Daum Web Search API (`https://dapi.kakao.com/v2/search/web`) filtered to Daum news hosts, with the REST API key read from environment only.

### Constraints
- Do not scrape Daum search-result HTML as the primary path.
- Do not fetch article bodies or publisher pages in this slice.
- Do not expose Kakao REST API keys in the UI, configs, logs, or final reports.
- Keep one user-facing news count field only.
- Bound API paging and record count to avoid broad crawls.
- If `KAKAO_REST_API_KEY` is missing, implementation and offline tests may pass, but live Daum API validation must be reported as blocked.

### Expected Deliverables For This Slice
- Daum provider parser/runtime module.
- `다음` config with search terms `최태원` and `SK`.
- Daum-only editor panel shown only for config `다음`.
- Workflow and UI safety validation for Daum limits.
- Unit/web tests covering parsing, paging, env key use, config save, and UI scoping.
- Local UI/browser proof that the Daum editor is visible and other configs are not polluted.

### Role-Specific Small Goals
- developer: implement the Daum provider path, config, UI, and focused tests without touching Git push.
- reviewer: find structural regressions, duplicated provider logic, hidden UI/config coupling, and maintainability issues.
- QA: verify count semantics, multiple search terms, missing-key behavior, UI scoping, parser validation, and regression against Naver/generic editor flows.
- auditor: verify credential isolation, external request bounds, captcha/scraping risk, logs/artifacts, and user-owned Git push boundary.

## Active Slice: Google News RSS Collection

### User Goal
Make Google News search collection work in the existing crawler product before the user performs git push. Initial verification terms are `Chey Tae-won` and `SK`.

### Existing Developer Note To Preserve
- Google News RSS is the intended source.
- Runtime path is `action=parser`, `attr=google`.
- Google News RSS does not require an API key for this slice.

### Constraints
- Do not introduce a Google API credential requirement unless the RSS path stops satisfying the product need.
- Do not scrape Google search result HTML.
- Do not fetch article bodies or publisher pages in this slice; store RSS item fields only.
- Keep one bounded per-term item count through parser `loop_limit`.
- Keep outputs cumulative under dated run directories and avoid overwriting prior runs.
- Block non-Google RSS URLs and output paths outside the crawler project.
- Do not run git push; the user owns push execution.

### Expected Deliverables For This Slice
- `configs\구글.json` configured for Google News RSS with `Chey Tae-won` and `SK`.
- Google RSS parser output under `<output_dir>\<NNN_search_term>\items\YYYYMMDD_n`.
- Per-item JSON files plus a run manifest for each search term.
- Workflow-level manifest under `<output_dir>\runs\YYYYMMDD_n\workflow_records.json`.
- Tests for URL allowlisting, output containment, run directory rotation, loop limits, and filtered compatibility.
- Live RSS proof with the current saved config value for `loop_limit`.

### Role-Specific Small Goals
- developer: implement the Google RSS config/output slice without changing Git push ownership.
- reviewer: check parser routing, config shape, cumulative output, no-secret behavior, and filtered-flow compatibility.
- QA: verify tests, live RSS proof, search terms, item counts, and output paths.
- auditor: verify external URL bounds, output path containment, retention/artifact risks, and unrelated dirty files.

## Superseded Slice: TheBell Uniform HTML Collection

### User Goal
Make TheBell collection work in the existing crawler product before the user performs git push. Initial verification terms are `최태원` and `SK`. The crawler should collect all article links from the configured number of TheBell search result pages, then visit each article URL and save title/body JSON item files.

### Discovery Result
- TheBell integrated search uses `https://www.thebell.co.kr/search/search.asp`.
- The search form supports GET parameters including `keyword`, `page`, `ord=NEWSDATE`, `section=ALL`, `kind_cd=GAAP1`, and `year_cd=Y`.
- Search results are in `div.searchResult div.newsList`, with article links shaped like `/front/newsview.asp?code=00&key=...`.
- Article details expose title metadata in `div.viewHead` and article body in `div.viewSection`; some articles include login/paywall prompts that must not be stored as article body.

### Constraints
- Do not use an API key for TheBell unless later evidence shows an official API is required.
- Do not collect by article count in this slice; user-facing limit is page count per search term.
- Keep search URL variables visible with `{search_term}`.
- Do not mix right-rail/ranking/recommended links into search result collection.
- Remove login/paywall/navigation/script/share boilerplate from extracted article text.
- If full body is blocked, save accessible text and explicit status metadata instead of pretending the body is complete.
- Preserve cumulative output directories under `<output_dir>\<NNN_search_term>\items\YYYYMMDD_n`.
- Do not run git push; the user owns push execution.

### Expected Deliverables For This Slice
- TheBell provider parser module and workflow attr `thebell`.
- `configs\더벨.json` with search terms `최태원` and `SK`.
- TheBell-only editor panel shown only for TheBell configs.
- One UI setting: `검색어당 가져올 페이지 수`.
- Per-item JSON files plus a run manifest for each search term.
- Unit tests for search-page link extraction, article body cleanup, page URL generation, workflow parser routing, preview skip, and UI scoping.
- Live proof using the local saved config, with artifact paths recorded.

### Completion Note
- 2026-05-14: superseded by the generic execution-step TheBell path and the origin Yonhap storage restore.
- Proof paths:
  - `qa-artifacts\thebell-live-20260514`
  - `qa-artifacts\thebell-ui-20260514\thebell-editor-3002.png`
  - `qa-artifacts\thebell-ui-20260514\generic-editor-3002.png`
- Remaining governance items are operational: retention, crawl delay/backoff, robots/terms review, and careful staging around unrelated dirty files.

### Role-Specific Small Goals
- developer: implement provider parser, config, UI, and tests without changing Git push ownership.
- reviewer: check parser scoping, duplicate/right-rail link exclusion, output path shape, and provider coupling.
- QA: verify page-count semantics, two search terms, JSON item contents, UI panel behavior, and regression tests.
- auditor: verify external request bounds, paywall/login text handling, retention/artifact risks, and user-owned Git push boundary.
