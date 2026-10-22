"""Interview email tracking settings and detections."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from backend.api.deps import current_user
from backend.applications import state_machine as sm
from backend.db import get_session
from backend.integrations.inbox import PROVIDER_HOSTS
from backend.models import Application, ApplicationEvent, InboxSettings, Job, User
from backend.security.crypto import encrypt_secret
from backend.services import application_service as svc
from backend.services.inbox_service import check_inbox

router = APIRouter(prefix="/api/inbox", tags=["inbox"])


class InboxIn(BaseModel):
    provider: str = "gmail"
    host: str = Field(default="", max_length=200)
    port: int = 993
    username: str = Field(default="", max_length=320)
    password: str | None = Field(default=None, max_length=200)  # None keeps the stored app password
    enabled: bool = True


def _record(session: Session, user: User) -> InboxSettings | None:
    return session.exec(select(InboxSettings).where(InboxSettings.user_id == user.id)).first()


def _out(r: InboxSettings | None) -> dict:
    if r is None:
        return {"configured": False, "provider": "gmail", "host": "", "port": 993, "username": "", "enabled": False,
                "has_password": False, "last_checked_at": None, "last_status": "", "last_error": ""}
    return {"configured": bool(r.username), "provider": r.provider, "host": r.host, "port": r.port,
            "username": r.username, "enabled": r.enabled, "has_password": bool(r.password_encrypted),
            "last_checked_at": r.last_checked_at, "last_status": r.last_status, "last_error": r.last_error}


@router.get("/settings")
def get_settings_(user: User = Depends(current_user), session: Session = Depends(get_session)):
    return _out(_record(session, user))


@router.put("/settings")
def save_settings(body: InboxIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    if body.provider not in PROVIDER_HOSTS and body.provider != "other":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown email provider.")
    if body.provider == "other" and not body.host:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Enter the IMAP server address.")
    r = _record(session, user) or InboxSettings(user_id=user.id)
    r.provider, r.username, r.enabled = body.provider, body.username.strip(), body.enabled
    r.host, r.port = (body.host.strip(), body.port) if body.provider == "other" else ("", 993)
    if body.password is not None:
        r.password_encrypted = encrypt_secret(body.password.replace(" ", ""))
    session.add(r)
    session.commit()
    session.refresh(r)
    return _out(r)


@router.delete("/settings")
def delete_settings(user: User = Depends(current_user), session: Session = Depends(get_session)):
    r = _record(session, user)
    if r:
        session.delete(r)
        session.commit()
    return {"ok": True}


@router.post("/check")
def check_now(user: User = Depends(current_user), session: Session = Depends(get_session)):
    return check_inbox(session, user.id)


@router.get("/detections")
def detections(user: User = Depends(current_user), session: Session = Depends(get_session)):
    rows = session.exec(select(ApplicationEvent, Application, Job)
                        .join(Application, Application.id == ApplicationEvent.application_id)
                        .join(Job, Job.id == Application.job_id)
                        .where(Application.user_id == user.id, ApplicationEvent.kind == "email")
                        .order_by(ApplicationEvent.occurred_at.desc()).limit(100)).all()
    return [{"event_id": e.id, "application_id": a.id, "company": j.company, "title": j.title,
             "status": a.status, "occurred_at": e.occurred_at, **e.details} for e, a, j in rows]


class ResolveIn(BaseModel):
    apply: bool = True


@router.post("/detections/{event_id}/resolve")
def resolve(event_id: int, body: ResolveIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    event = session.get(ApplicationEvent, event_id)
    app = session.get(Application, event.application_id) if event else None
    if event is None or app is None or app.user_id != user.id or event.kind != "email":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    target = (event.details or {}).get("suggested_status")
    event.details = {**event.details, "resolved": True, "applied": bool(body.apply and target),
                     "resolved_at": datetime.now(timezone.utc).isoformat()}
    session.add(event)
    if body.apply and target:
        try:
            if app.status in (sm.APPROVED, sm.NEEDS_USER, sm.SUBMITTING):  # they replied, so it was submitted
                svc.mark_submitted(session, user.id, app, "manual")
            if target != app.status:
                svc.record_outcome(session, user.id, app, status=target, kind="status_change",
                                   title=f"From email: {event.details.get('subject', '')}"[:300])
        except (sm.TransitionError, ValueError) as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    session.commit()
    return {"ok": True}
