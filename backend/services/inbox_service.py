"""Check the user's inbox and record interview/rejection/offer emails on their applications."""
from __future__ import annotations

import imaplib
import logging
import socket
from datetime import datetime, timezone

from sqlmodel import Session, select

from backend.applications import state_machine as sm
from backend.integrations.inbox import PROVIDER_HOSTS, default_since, detect, fetch_messages
from backend.models import Application, ApplicationEvent, InboxSettings, Job
from backend.security.crypto import decrypt_secret
from backend.services.common import audit

log = logging.getLogger(__name__)
TRACKED = sm.TRACKING_STATES | {sm.APPROVED, sm.NEEDS_USER, sm.SUBMITTING}


def check_inbox(session: Session, user_id: int) -> dict:
    settings = session.exec(select(InboxSettings).where(InboxSettings.user_id == user_id)).first()
    if settings is None or not settings.enabled or not settings.username:
        return {"checked": 0, "found": 0, "message": "Inbox tracking is not set up."}
    host, port = settings.host or PROVIDER_HOSTS.get(settings.provider, ("", 993))[0], settings.port or 993
    rows = session.exec(select(Application, Job).join(Job, Job.id == Application.job_id)
                        .where(Application.user_id == user_id, Application.status.in_(list(TRACKED)))).all()
    apps = [{"id": a.id, "company": j.company, "company_domain": j.company_domain, "title": j.title}
            for a, j in rows]
    now = datetime.now(timezone.utc)
    try:
        messages = fetch_messages(host, port, settings.username, decrypt_secret(settings.password_encrypted),
                                  default_since(settings.last_checked_at))
    except (imaplib.IMAP4.error, OSError, socket.timeout) as exc:
        settings.last_status, settings.last_error = "error", _friendly(exc)
        settings.last_checked_at = now
        session.add(settings)
        session.commit()
        return {"checked": 0, "found": 0, "message": settings.last_error}

    seen = set(settings.seen_message_ids or [])
    detections = [d for d in detect(messages, apps) if d.message.message_id not in seen] if apps else []
    by_id = {a.id: a for a, _ in rows}
    for d in detections:
        app = by_id[d.application_id]
        suggestion = d.suggested_status
        can_move = suggestion != app.status and suggestion in sm.TRANSITIONS.get(app.status, set())
        session.add(ApplicationEvent(
            application_id=app.id, kind="email", from_status=app.status, to_status=app.status,
            occurred_at=d.message.received_at or now,
            details={"title": f"Email: {d.classification}", "classification": d.classification,
                     "subject": d.message.subject, "from": d.message.sender, "evidence": d.evidence,
                     "message_id": d.message.message_id, "suggested_status": suggestion if can_move else "",
                     "resolved": False}))
        seen.add(d.message.message_id)
    settings.seen_message_ids = list(seen)[-2000:]
    settings.last_checked_at = now
    settings.last_status, settings.last_error = "ok", ""
    session.add(settings)
    audit(session, user_id, "inbox.checked", messages=len(messages), detections=len(detections))
    session.commit()
    return {"checked": len(messages), "found": len(detections),
            "message": f"Read {len(messages)} recent emails, found {len(detections)} about your applications."}


def _friendly(exc: Exception) -> str:
    text = str(exc)
    if "AUTHENTICATIONFAILED" in text.upper() or "invalid credentials" in text.lower():
        return ("Sign-in failed. Use an app password, not your normal password (Gmail: Google Account → Security → "
                "2-Step Verification → App passwords).")
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "The mail server did not respond. Try again later."
    return f"Could not read the inbox: {text[:200]}"


def check_all_users() -> None:
    from backend.db import session_scope

    with session_scope() as session:
        user_ids = [s.user_id for s in session.exec(select(InboxSettings).where(InboxSettings.enabled == True))]  # noqa: E712
    for user_id in user_ids:
        try:
            with session_scope() as session:
                check_inbox(session, user_id)
        except Exception:
            log.exception("Inbox check failed for user %s", user_id)
