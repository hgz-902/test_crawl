# Security Test Checklist

- [x] `.env`, `.env.*`, SMTP password, Gmail app password, API keys, tokens, and cookies are absent from `git diff`.
- [x] SMTP password is read only from `SMTP_PASSWORD`.
- [x] Mail dry-run works without `SMTP_PASSWORD`.
- [x] Mail result does not include secret values.
- [x] UI settings file stores recipients and keywords only, not passwords.
- [x] Real SMTP send requires an explicit per-run operator checkbox.
- [x] Duplicate handling does not delete `workflow_records.json`.
- [x] Parser duplicate handling filters records before saving parser output JSON.
- [x] Manual batch run failure in one job does not stop the whole batch.
- [x] Cross-origin orchestration POST requests are rejected.
- [x] Push preparation warns: "Gmail 앱 비밀번호 / SMTP 비밀번호가 커밋 대상에 들어가지 않았는지 확인해야 합니다."

Evidence:
- `python -m unittest discover -s tests`: 114 tests passed after orchestration hardening and expert-review regression tests.
- Scoped secret scan found no concrete SMTP password/API key; README contains only a placeholder for `SMTP_PASSWORD`.
- `orchestration_state/` and `attach/` are ignored in `.gitignore`.
- Real SMTP verification was attempted with credentials provided in ignored `attach/gmail.txt`; result was `sent`, and the password was not printed or written to tracked files.
- 2026-05-16 browser proof confirmed `/orchestration` renders clean Korean text and exposes force-run/email-send checkboxes.
