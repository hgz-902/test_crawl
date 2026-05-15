# Security Test Checklist

## 2026-05-15 Batch Job Orchestrator And Email Slice

- [x] Scheduler does not run disabled jobs.
- [x] Run-now path respects existing crawl safety checks.
- [x] Same job cannot run concurrently.
- [x] SMTP password is never rendered in HTML or stored in job JSON/history.
- [x] Email send is skipped when SMTP is not configured or explicitly disabled.
- [x] Unit tests do not send real email.
- [x] Job interval has a sane lower bound.
- [x] Job state/history writes use UTF-8 JSON and tolerate missing files.
- [x] UI shows last run, next run, and error status without exposing secrets.
- [x] Interrupted/running jobs are recovered after app restart.
- [x] Deleted/stale config jobs are pruned from scheduler state.
- [x] Unsafe cross-origin POSTs are rejected.
