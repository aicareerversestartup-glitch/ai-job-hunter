"""Periodic background discovery (APScheduler). Runs in the API process by default, or in the
separate worker container (``python -m backend.worker``) with RUN_SCHEDULER=false on the API."""
from __future__ import annotations

import logging

from sqlmodel import select

from backend.config import get_settings
from backend.db import session_scope
from backend.models import Profile, User

log = logging.getLogger(__name__)
_scheduler = None


def discover_for_all_users() -> None:
    from backend.services.common import NotReadyError
    from backend.services.discovery import run_discovery

    with session_scope() as session:
        user_ids = [u.id for u in session.exec(select(User).where(User.is_active == True)).all()]  # noqa: E712
    for user_id in user_ids:
        try:
            with session_scope() as session:
                profile = session.exec(select(Profile).where(Profile.user_id == user_id)).first()
                if not profile:
                    continue
                if (profile.preferences or {}).get("auto_discovery", True) is False:
                    continue
                run = run_discovery(session, user_id, trigger="schedule")
                log.info("Scheduled discovery for user %s: %s", user_id, run.stats)
        except NotReadyError:
            continue
        except Exception:
            log.exception("Scheduled discovery failed for user %s", user_id)


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    from apscheduler.schedulers.background import BackgroundScheduler

    hours = max(1, get_settings().discovery_interval_hours)
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(discover_for_all_users, "interval", hours=hours, id="discovery", max_instances=1,
                       coalesce=True, misfire_grace_time=3600)
    from backend.services.inbox_service import check_all_users

    _scheduler.add_job(check_all_users, "interval", minutes=max(15, get_settings().inbox_check_minutes), id="inbox",
                       max_instances=1, coalesce=True)
    _scheduler.start()
    log.info("Discovery scheduler started (every %s h)", hours)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
