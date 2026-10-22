from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlmodel import Session, select

from backend.ai.providers.base import LLMError
from backend.ai.providers.http_providers import PROVIDERS
from backend.api.deps import current_user
from backend.applications import state_machine as sm
from backend.config import get_settings
from backend.db import get_session
from backend.models import AISettings, Application, ApplicationEvent, Job, JobMatch, MasterCV, User
from backend.schemas.api import AISettingsIn, AISettingsOut
from backend.security.crypto import decrypt_secret, encrypt_secret, mask_secret
from backend.security.guards import UnsafeURLError, validate_public_url
from backend.services.common import audit, get_ai_provider

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/settings/ai", response_model=AISettingsOut)
def get_ai(user: User = Depends(current_user), session: Session = Depends(get_session)):
    record = session.exec(select(AISettings).where(AISettings.user_id == user.id)).first()
    if record and record.provider != "none":
        return AISettingsOut(provider=record.provider, model=record.model, base_url=record.base_url,
                             api_key_masked=mask_secret(decrypt_secret(record.api_key_encrypted)),
                             temperature=record.temperature, source="user")
    s = get_settings()
    return AISettingsOut(provider=s.ai_provider, model=s.ai_model, base_url=s.ai_base_url,
                         api_key_masked=mask_secret(s.ai_api_key), temperature=0.2, source="server-default")


@router.put("/settings/ai", response_model=AISettingsOut)
def save_ai(body: AISettingsIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    if body.provider not in PROVIDERS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Provider must be one of: {', '.join(PROVIDERS)}")
    if body.base_url and body.provider not in ("ollama", "openai_compatible"):
        try:
            validate_public_url(body.base_url, resolve=False)
        except UnsafeURLError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    record = session.exec(select(AISettings).where(AISettings.user_id == user.id)).first() or AISettings(user_id=user.id)
    record.provider, record.model, record.base_url = body.provider, body.model.strip(), body.base_url.strip()
    record.temperature = body.temperature
    if body.api_key is not None:
        record.api_key_encrypted = encrypt_secret(body.api_key.strip())
    record.updated_at = datetime.now(timezone.utc)
    session.add(record)
    audit(session, user.id, "settings.ai_updated", provider=body.provider, model=body.model)
    session.commit()
    return get_ai(user, session)


@router.post("/settings/ai/test")
def test_ai(user: User = Depends(current_user), session: Session = Depends(get_session)):
    provider = get_ai_provider(session, user.id)
    if not provider.available:
        return {"ok": False, "message": "No AI provider is configured (the app works without one)."}
    try:
        reply = provider.complete("Reply with the single word: ready", "Are you ready?", max_tokens=10, temperature=0)
    except LLMError as exc:
        return {"ok": False, "message": str(exc)}
    return {"ok": True, "message": f"{provider.name} responded: {reply.strip()[:60]}"}


@router.get("/dashboard")
def dashboard(user: User = Depends(current_user), session: Session = Depends(get_session)):
    cv = session.exec(select(MasterCV).where(MasterCV.user_id == user.id, MasterCV.is_active == True)  # noqa: E712
                      .order_by(MasterCV.version.desc())).first()
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    jobs_total = session.exec(select(func.count()).select_from(Job).where(Job.user_id == user.id)).one()
    jobs_week = session.exec(select(func.count()).select_from(Job).where(Job.user_id == user.id,
                                                                         Job.discovered_at >= week_ago)).one()
    strong = 0
    if cv:
        strong = session.exec(select(func.count()).select_from(JobMatch).join(Job, Job.id == JobMatch.job_id).where(
            JobMatch.user_id == user.id, JobMatch.master_cv_id == cv.id, JobMatch.score >= 75,
            Job.status.in_(["new", "shortlisted"]), Job.risk_level != "high")).one()
    counts = dict(session.exec(select(Application.status, func.count()).where(Application.user_id == user.id)
                               .group_by(Application.status)).all())
    submitted_like = sum(counts.get(s, 0) for s in sm.TRACKING_STATES)
    interviewed_ids = set(session.exec(select(ApplicationEvent.application_id).join(
        Application, Application.id == ApplicationEvent.application_id).where(
        Application.user_id == user.id, ApplicationEvent.kind == "interview")).all())
    interviewed_ids |= set(session.exec(select(Application.id).where(
        Application.user_id == user.id, Application.status.in_([sm.INTERVIEWING, sm.OFFER, sm.ACCEPTED]))).all())
    pending_emails = sum(1 for e in session.exec(select(ApplicationEvent).join(
        Application, Application.id == ApplicationEvent.application_id).where(
        Application.user_id == user.id, ApplicationEvent.kind == "email")).all()
        if not (e.details or {}).get("resolved") and (e.details or {}).get("suggested_status"))
    week_old = datetime.now(timezone.utc) - timedelta(days=7)
    follow_ups_due = 0
    for app_row in session.exec(select(Application).where(Application.user_id == user.id,
                                                          Application.status == sm.SUBMITTED)).all():
        submitted = app_row.submitted_at
        if submitted and (submitted if submitted.tzinfo else submitted.replace(tzinfo=timezone.utc)) <= week_old:
            kinds = {e.kind for e in session.exec(select(ApplicationEvent).where(
                ApplicationEvent.application_id == app_row.id)).all()}
            if not kinds & {"email", "interview", "follow_up"}:
                follow_ups_due += 1
    responded = sum(counts.get(s, 0) for s in (sm.INTERVIEWING, sm.OFFER, sm.ACCEPTED, sm.REJECTED, sm.IN_REVIEW))
    return {
        "cv_status": cv.status if cv else "missing",
        "jobs_total": jobs_total, "jobs_this_week": jobs_week, "strong_matches": strong,
        "applications_by_status": counts,
        "awaiting_review": counts.get(sm.READY, 0), "needs_action": counts.get(sm.NEEDS_USER, 0),
        "submitted": submitted_like, "interviews": counts.get(sm.INTERVIEWING, 0),
        "offers": counts.get(sm.OFFER, 0) + counts.get(sm.ACCEPTED, 0),
        "response_rate": round(responded / submitted_like * 100) if submitted_like else None,
        "interview_rate": round(len(interviewed_ids) / submitted_like * 100) if submitted_like else None,
        "interviewed": len(interviewed_ids), "follow_ups_due": follow_ups_due, "pending_emails": pending_emails,
    }
