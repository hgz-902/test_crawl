# Threat Model

Scope:
- Crawler orchestration settings, workflow records, keyword notification email, and local web UI.

Sensitive assets:
- SMTP password or Gmail app password.
- API keys already used by Naver/Daum environment variables.
- Local runtime outputs that may contain collected article/report text.

Primary risks:
- Secret accidentally saved in JSON settings, README, logs, push history, or git diff.
- SMTP errors logging password-bearing connection strings.
- Email notification sending unexpected crawler content to recipients.
- Duplicate logic deleting or overwriting durable `workflow_records.json`.
- UI triggering long-running crawls unintentionally.

Controls:
- Read SMTP credentials only from environment variables.
- Store only non-secret notification settings such as recipients and keywords.
- Dry-run mail if SMTP password is absent.
- Do not print SMTP password or full env values.
- Do not auto-register Windows Task Scheduler tasks.
- Keep duplicate state additive and avoid deleting workflow records.
