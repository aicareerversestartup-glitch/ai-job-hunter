from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from backend.api.deps import current_user, get_owned
from backend.applications import state_machine as sm
from backend.config import get_settings
from backend.db import get_session
from backend.models import Application, ApplicationEvent, Job, JobMatch, MasterCV, User
from backend.schemas.api import (ApplyIn, ApproveIn, CreateApplicationIn, FormatIn, OutcomeIn, ReviewUpdateIn,
                                SubmittedIn)
from backend.services import application_service as svc
from backend.services.common import NotReadyError

router = APIRouter(prefix="/api/applications", tags=["applications"])

OUTCOME_STATES = {sm.IN_REVIEW, sm.INTERVIEWING, sm.OFFER, sm.ACCEPTED, sm.REJECTED, sm.WITHDRAWN, sm.DISCARDED}


def _errors(fn):
    from backend.services.billing import LimitReached

    try:
        return fn()
    except LimitReached as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc))
    except NotReadyError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    except sm.TransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


def _detail(session: Session, app: Application) -> dict:
    job = session.get(Job, app.job_id)
    match = session.exec(select(JobMatch).where(JobMatch.job_id == app.job_id,
                                                JobMatch.master_cv_id == app.master_cv_id)).first()
    master = session.get(MasterCV, app.master_cv_id)
    events = session.exec(select(ApplicationEvent).where(ApplicationEvent.application_id == app.id)
                          .order_by(ApplicationEvent.occurred_at)).all()
    data = app.model_dump()
    data["job"] = job.model_dump(exclude={"raw"}) if job else None
    data["match"] = match.result if match else None
    data["master_cv"] = master.data if master else None
    data["events"] = [e.model_dump() for e in events]
    data["approval_valid"] = bool(app.approved_snapshot) and app.approved_snapshot == svc.current_snapshot(app)
    data["approval_blockers"] = sm.approval_blockers(cv_guard=app.cv_guard, cover_guard=app.cover_guard,
                                                     answers=app.answers, confirmed=True)
    data["auto_submit_available"] = get_settings().allow_auto_submit
    data["apply_assist_available"] = get_settings().apply_assist_enabled
    return data


@router.get("")
def list_applications(user: User = Depends(current_user), session: Session = Depends(get_session)):
    rows = session.exec(select(Application, Job).join(Job, Job.id == Application.job_id)
                        .where(Application.user_id == user.id).order_by(Application.updated_at.desc())).all()
    return [{"id": a.id, "status": a.status, "match_score": a.match_score, "job_id": j.id, "title": j.title,
             "company": j.company, "location": j.location, "apply_url": a.apply_url, "created_at": a.created_at,
             "updated_at": a.updated_at, "submitted_at": a.submitted_at,
             "needs_attention": a.status in (sm.READY, sm.NEEDS_USER)} for a, j in rows]


@router.post("")
def create_application(body: CreateApplicationIn, user: User = Depends(current_user),
                       session: Session = Depends(get_session)):
    job = get_owned(session, Job, body.job_id, user)
    app = _errors(lambda: svc.create_draft(session, user.id, job, body.questions))
    return _detail(session, app)


class PrepareIn(BaseModel):
    count: int = Field(default=10, ge=1, le=25)


@router.post("/prepare-top")
def prepare_top(body: PrepareIn, user: User = Depends(current_user)):
    return _errors(lambda: svc.prepare_top(user.id, body.count))


@router.get("/prepare-top/status")
def prepare_status(user: User = Depends(current_user)):
    return svc.batch_status(user.id)


@router.get("/{app_id}")
def get_application(app_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    return _detail(session, get_owned(session, Application, app_id, user))


@router.put("/{app_id}/review")
def update_review(app_id: int, body: ReviewUpdateIn, user: User = Depends(current_user),
                  session: Session = Depends(get_session)):
    app = get_owned(session, Application, app_id, user)
    app = _errors(lambda: svc.update_review(
        session, user.id, app, tailored_cv=body.tailored_cv.model_dump() if body.tailored_cv else None,
        cover_letter=body.cover_letter, answers=body.answers, notes=body.notes))
    return _detail(session, app)


@router.post("/{app_id}/regenerate")
def regenerate(app_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    app = get_owned(session, Application, app_id, user)
    return _detail(session, _errors(lambda: svc.regenerate(session, user.id, app)))


@router.put("/{app_id}/format")
def set_format(app_id: int, body: FormatIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    app = get_owned(session, Application, app_id, user)
    app = _errors(lambda: svc.set_format(session, user.id, app, body.model_dump()))
    return _detail(session, app)


@router.post("/{app_id}/approve")
def approve(app_id: int, body: ApproveIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    app = get_owned(session, Application, app_id, user)
    app = _errors(lambda: svc.approve(session, user.id, app, confirmed=body.confirm_reviewed,
                                      auto_submit=body.auto_submit))
    return _detail(session, app)


@router.post("/{app_id}/apply")
def apply(app_id: int, body: ApplyIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    app = get_owned(session, Application, app_id, user)
    app = _errors(lambda: svc.start_apply(session, user.id, app, body.mode))
    return _detail(session, app)


@router.post("/{app_id}/submitted")
def mark_submitted(app_id: int, body: SubmittedIn, user: User = Depends(current_user),
                   session: Session = Depends(get_session)):
    app = get_owned(session, Application, app_id, user)
    app = _errors(lambda: svc.mark_submitted(session, user.id, app, body.method, body.submitted_at))
    return _detail(session, app)


@router.post("/{app_id}/events")
def add_event(app_id: int, body: OutcomeIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    app = get_owned(session, Application, app_id, user)
    if body.status and body.status not in OUTCOME_STATES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Use the approval/apply actions for that status.")
    app = _errors(lambda: svc.record_outcome(session, user.id, app, status=body.status, kind=body.kind,
                                             occurred_at=body.occurred_at, title=body.title, notes=body.notes,
                                             location=body.location))
    return _detail(session, app)


class ReportIn(BaseModel):
    part: str = Field(max_length=40)  # cv | cover_letter | answer | follow_up
    reason: str = Field(max_length=2000)


@router.post("/{app_id}/report")
def report_content(app_id: int, body: ReportIn, user: User = Depends(current_user),
                   session: Session = Depends(get_session)):
    """Report AI-generated content that is wrong, offensive or harmful (app-store AI content policy)."""
    from backend.services.common import audit
    from backend.utils.mailer import send_email

    app = get_owned(session, Application, app_id, user)
    audit(session, user.id, "content.reported", "application", app.id, part=body.part, reason=body.reason[:500],
          method=app.generation_method)
    session.commit()
    support = get_settings().support_email
    if support:
        send_email(support, f"Content report: application {app.id}",
                   f"Part: {body.part}\nReason: {body.reason}\nGeneration: {app.generation_method}")
    return {"ok": True, "message": "Thanks. The report was recorded and will be reviewed."}


@router.get("/{app_id}/follow-up")
def follow_up(app_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    return svc.follow_up(session, user.id, get_owned(session, Application, app_id, user))


@router.post("/{app_id}/follow-up/sent")
def follow_up_sent(app_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    app = get_owned(session, Application, app_id, user)
    app = _errors(lambda: svc.record_outcome(session, user.id, app, status=None, kind="follow_up",
                                             title="Follow-up email sent"))
    return _detail(session, app)


@router.get("/{app_id}/documents/{kind}")
def download_document(app_id: int, kind: str, user: User = Depends(current_user),
                      session: Session = Depends(get_session)):
    app = get_owned(session, Application, app_id, user)
    if kind not in {"cv_docx", "cv_pdf", "cover_docx", "cover_pdf"}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown document.")
    path = svc.export_documents(app)[kind]
    return FileResponse(path, filename=path.name)


@router.get("/{app_id}/screenshot")
def screenshot(app_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    app = get_owned(session, Application, app_id, user)
    shot = ((app.blocker or {}).get("last_outcome") or {}).get("screenshot")
    root = (get_settings().generated_dir / "screenshots").resolve()
    if not shot or not Path(shot).resolve().is_relative_to(root) or not Path(shot).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No screenshot.")
    return FileResponse(shot, media_type="image/png")
