# Threat Model

## 2026-05-15 Batch Job Orchestrator And Email Slice

### Scope
- In-app scheduler for existing crawler configs.
- Persistent local job state and run history.
- Manual run-now and automatic interval execution.
- Completion email notification to `bloodknihts@gmail.com`.

### Assets
- Local `.env` credentials for providers and SMTP.
- Local crawler configs under `configs`.
- Runtime outputs, logs, and job history.
- Operator email address and completion metadata.

### Threats
- Accidental broad crawling if a previously risky config is enabled on a short interval.
- Duplicate concurrent runs for the same config.
- Secrets leaking into UI, logs, JSON history, or tests.
- SMTP credentials being committed or displayed.
- Unintended real email during unit tests.
- External site pressure from overly frequent intervals.
- Job state corruption if the app stops while writing JSON.

### Mitigations
- Reuse existing run-safety checks before scheduled/manual job execution.
- Default jobs are disabled until the operator enables them.
- Enforce a minimum interval and per-job in-process lock.
- Store SMTP settings only in environment variables.
- Do not send mail unless SMTP env vars explicitly enable it.
- Log completion email result without exposing credentials.
- Tests must patch crawler/email paths and avoid real network email.

