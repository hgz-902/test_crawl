# Orchestration Alpha State

run_id: codexapp-crawler-orchestration-20260515

classification: non-trivial

Reason:
- Adds cross-cutting runtime behavior: job selection, interval metadata, duplicate stop policy, keyword notifications, SMTP dry-run/real-send boundaries, UI state, tests, and documentation.

Allowed scope:
- Common orchestration code.
- Optional common workflow policy hook.
- FastAPI route wiring.
- Operation UI template and supporting CSS.
- Tests and documentation.

Out of scope:
- New site-specific crawler code.
- Per-site parser exceptions beyond existing Google/Naver/Daum structures.
- Automatic Windows Task Scheduler registration.
- Storing SMTP passwords or app passwords in files.

Validation plan:
- `python -m unittest discover -s tests`
- `python -m uvicorn crawler_app.web:app --host 127.0.0.1 --port 3000`
- Browser-open `/orchestration`.
- Save orchestration settings.
- Manual batch run.
- Duplicate stops only the current selected job while the next job continues.
- Keyword match and SMTP dry-run result recorded.
- Verify `.env`, passwords, tokens, and secrets are absent from diffs.

Ruling:
- Initial: conditional pass pending implementation, tests, UI proof, and Alpha reviewer/QA/auditor judgment.

## 2026-05-16 Cross-Agent Hardening

Peer review inputs addressed:
- Parser duplicate records are policy-filtered before parser output JSON is saved.
- Batch runs now honor `next_run_at` unless the operator checks one-run force execution.
- Real SMTP send requires the per-run `allow_email_send` checkbox; otherwise matched notifications stay dry-run even when SMTP env vars exist.
- Normal UI duplicate indexes are scoped per config output root while still reading existing `workflow_records.json` snapshots.
- Orchestration/layout Korean UI text was rewritten cleanly.

Validation:
- `python -m unittest discover -s tests`: 114 tests passed.
- `git diff --check`: passed with CRLF conversion warnings only.
- Browser/Playwright proof: `qa-artifacts/orchestration-hardening-20260516/result.json`.
- Local server: `http://127.0.0.1:3000/orchestration`, PID stored in `runtime/local-web/uvicorn-3000.pid`.
- Added regression tests for per-config duplicate scope and orchestration template mojibake markers.

Ruling:
- Pass for the bounded hardening pass.
- Remaining risk: automatic Windows Task Scheduler registration is still intentionally deferred.
