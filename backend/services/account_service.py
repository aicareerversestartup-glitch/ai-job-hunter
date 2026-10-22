"""Account deletion and data export (required for public app stores and data-protection laws)."""
from __future__ import annotations

import os
import shutil
import stat
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, select

from backend.config import get_settings
from backend.models import (AISettings, Application, BonusCredit, ApplicationEvent, AuditLog, DiscoveryRun, InboxSettings, Job,
                            JobMatch, JobSource, MasterCV, Profile, User)


def export_user_data(session: Session, user: User) -> dict:
    def dump(rows, exclude=frozenset()):
        return [r.model_dump(mode="json", exclude=set(exclude)) for r in rows]

    apps = session.exec(select(Application).where(Application.user_id == user.id)).all()
    app_ids = [a.id for a in apps]
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "account": {"email": user.email, "full_name": user.full_name, "created_at": user.created_at.isoformat()},
        "profile": dump(session.exec(select(Profile).where(Profile.user_id == user.id)).all()),
        "master_cvs": dump(session.exec(select(MasterCV).where(MasterCV.user_id == user.id)).all(), {"stored_path"}),
        "jobs": dump(session.exec(select(Job).where(Job.user_id == user.id)).all(), {"raw"}),
        "matches": dump(session.exec(select(JobMatch).where(JobMatch.user_id == user.id)).all()),
        "applications": dump(apps),
        "application_events": dump(session.exec(select(ApplicationEvent).where(
            ApplicationEvent.application_id.in_(app_ids))).all()) if app_ids else [],
        "job_sources": dump(session.exec(select(JobSource).where(JobSource.user_id == user.id)).all()),
        "ai_settings": dump(session.exec(select(AISettings).where(AISettings.user_id == user.id)).all(),
                            {"api_key_encrypted"}),
        "inbox_settings": dump(session.exec(select(InboxSettings).where(InboxSettings.user_id == user.id)).all(),
                               {"password_encrypted", "seen_message_ids"}),
    }


def _remove_tree(path: Path) -> None:
    if not path.exists():
        return

    def make_writable(func, p, _exc):
        os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
        func(p)

    shutil.rmtree(path, onerror=make_writable)


def delete_account(session: Session, user: User) -> None:
    """Permanently delete the user and everything they stored. Audit rows are kept without the user id."""
    uid = user.id
    apps = session.exec(select(Application).where(Application.user_id == uid)).all()
    app_ids = [a.id for a in apps]
    if app_ids:
        for e in session.exec(select(ApplicationEvent).where(ApplicationEvent.application_id.in_(app_ids))).all():
            session.delete(e)
    session.flush()
    for model in (Application, JobMatch):
        for row in session.exec(select(model).where(model.user_id == uid)).all():
            session.delete(row)
    session.flush()
    for model in (Job, JobSource, DiscoveryRun, AISettings, InboxSettings, Profile, BonusCredit):
        for row in session.exec(select(model).where(model.user_id == uid)).all():
            session.delete(row)
    session.flush()
    cvs = session.exec(select(MasterCV).where(MasterCV.user_id == uid)).all()
    for cv in sorted(cvs, key=lambda c: -c.version):  # children before parents
        session.delete(cv)
        session.flush()
    for invited in session.exec(select(User).where(User.referred_by == uid)).all():
        invited.referred_by = None
        session.add(invited)
    for log in session.exec(select(AuditLog).where(AuditLog.user_id == uid)).all():
        log.user_id = None
        log.details = {}
        session.add(log)
    session.delete(user)
    session.commit()

    settings = get_settings()
    _remove_tree(settings.master_cv_dir / str(uid))
    _remove_tree(settings.uploads_dir / str(uid))
    for app_id in app_ids:
        _remove_tree(settings.generated_dir / f"application-{app_id}")
        shot = settings.generated_dir / "screenshots" / f"application-{app_id}.png"
        if shot.exists():
            shot.unlink()
