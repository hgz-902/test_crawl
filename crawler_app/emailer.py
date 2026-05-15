from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
import os
import smtplib
from typing import Any


DEFAULT_COMPLETION_RECIPIENT = "bloodknihts@gmail.com"
EMAIL_ENABLED_ENV = "CRAWLER_COMPLETION_EMAIL_ENABLED"


@dataclass(slots=True)
class EmailStatus:
    sent: bool
    reason: str


def smtp_is_configured(env: dict[str, str] | None = None) -> bool:
    values = env if env is not None else os.environ
    enabled = values.get(EMAIL_ENABLED_ENV, "").strip().lower() in {"1", "true", "yes", "on"}
    return enabled and bool(values.get("SMTP_HOST") and values.get("SMTP_PORT") and values.get("SMTP_FROM"))


def send_completion_email(
    *,
    config_id: str,
    trigger: str,
    result: dict[str, Any],
    recipient: str = DEFAULT_COMPLETION_RECIPIENT,
    env: dict[str, str] | None = None,
) -> EmailStatus:
    values = env if env is not None else os.environ
    if values.get(EMAIL_ENABLED_ENV, "").strip().lower() not in {"1", "true", "yes", "on"}:
        return EmailStatus(sent=False, reason="email_disabled")
    if not smtp_is_configured(values):
        return EmailStatus(sent=False, reason="smtp_not_configured")

    host = values["SMTP_HOST"]
    port = int(values["SMTP_PORT"])
    sender = values["SMTP_FROM"]
    username = values.get("SMTP_USERNAME") or ""
    password = values.get("SMTP_PASSWORD") or ""
    use_tls = values.get("SMTP_USE_TLS", "true").strip().lower() not in {"0", "false", "no", "off"}

    success = bool(result.get("success"))
    subject_status = "SUCCESS" if success else "FAILED"
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = f"Crawler job {subject_status}: {config_id}"
    message.set_content(
        "\n".join(
            [
                f"Config: {config_id}",
                f"Trigger: {trigger}",
                f"Success: {success}",
                f"Items: {result.get('items_count', 0)}",
                f"Started: {result.get('started_at', '')}",
                f"Finished: {result.get('finished_at', '')}",
                f"Message: {result.get('message', '')}",
                f"Error: {result.get('error') or ''}",
            ]
        )
    )

    with smtplib.SMTP(host, port, timeout=20) as smtp:
        if use_tls:
            smtp.starttls()
        if username or password:
            smtp.login(username, password)
        smtp.send_message(message)
    return EmailStatus(sent=True, reason="sent")
