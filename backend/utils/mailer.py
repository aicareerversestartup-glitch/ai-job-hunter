"""Minimal transactional email (password reset). Uses SMTP settings from the environment."""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from backend.config import get_settings

log = logging.getLogger(__name__)


def email_configured() -> bool:
    s = get_settings()
    return bool(s.smtp_host and (s.smtp_from or s.smtp_user))


def send_email(to: str, subject: str, body: str) -> bool:
    s = get_settings()
    if not email_configured():
        log.warning("SMTP not configured; email to %s not sent: %s", to, subject)
        return False
    msg = EmailMessage()
    msg["From"] = s.smtp_from or s.smtp_user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as smtp:
            smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError) as exc:
        log.error("Sending email failed: %s", exc)
        return False
