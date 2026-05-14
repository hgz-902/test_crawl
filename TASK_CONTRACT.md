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
