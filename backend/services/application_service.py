"""Application workflow: draft generation, review edits, approval, apply sessions, tracking."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlmodel import Session, select

from backend.ai.generation import DEFAULT_QUESTIONS, answer_questions, tailor_cv, write_cover_letter
from backend.applications import state_machine as sm
from backend.automation.apply_assistant import ApplyAssistant, ApplyBundle, ApplyOutcome, split_name
from backend.config import get_settings
from backend.cv import formatted_renderer
from backend.cv.formats import FORMATS, STYLES, code_for_country, resolve_layout
from backend.cv.profile import CandidateProfile
from backend.cv.renderer import text_to_docx, text_to_pdf
from backend.cv.schema import CVData
from backend.cv.truthfulness import check_cv, check_free_text
from backend.db import session_scope
from backend.jobs.matcher import MatchResult, score_job
from backend.models import Application, ApplicationEvent, Job, JobMatch
from backend.services.common import apply_cv_roles, audit, build_facts, get_active_cv, get_ai_provider, get_profile
from backend.services.discovery import job_to_normalized

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _event(session: Session, app: Application, kind: str, from_status: str = "", to_status: str = "",
           occurred_at: datetime | None = None, **details) -> None:
    session.add(ApplicationEvent(application_id=app.id, kind=kind, from_status=from_status, to_status=to_status,
                                 details=details, occurred_at=occurred_at or _now()))


def transition(session: Session, app: Application, target: str, **details) -> None:
    sm.check_transition(app.status, target)
    previous = app.status
    app.status = target
    app.updated_at = _now()
    session.add(app)
    _event(session, app, "status_change", previous, target, **details)


def create_draft(session: Session, user_id: int, job: Job, questions: list[str] | None = None) -> Application:
    existing = session.exec(select(Application).where(Application.user_id == user_id, Application.job_id == job.id,
                                                      Application.status != sm.DISCARDED)).first()
    if existing:
        return existing
    from backend.services.billing import check_draft_allowed

    check_draft_allowed(session, user_id)  # raises LimitReached (a ValueError) with an upgrade hint
    if job.risk_level == "high" and not (job.quality or {}).get("user_override"):
        raise ValueError("This posting was flagged as high fraud risk. Review the flags before applying; "
                         "if you are sure it is genuine, mark it as reviewed first.")
    app = Application(user_id=user_id, job_id=job.id, master_cv_id=0, apply_url=job.apply_url or job.url,
                      cv_format=default_format(job))
    _generate(session, user_id, app, job, questions or list(DEFAULT_QUESTIONS))
    session.add(app)
    session.flush()
    _event(session, app, "status_change", "", sm.DRAFT)
    transition(session, app, sm.READY)
    audit(session, user_id, "application.drafted", "application", app.id, job_id=job.id)
    session.commit()
    session.refresh(app)
    return app


def _generate(session: Session, user_id: int, app: Application, job: Job, questions: list[str]) -> None:
    profile, prefs = get_profile(session, user_id)
    cv_record = get_active_cv(session, user_id)
    master, facts = build_facts(cv_record, profile)
    provider = get_ai_provider(session, user_id)
    apply_cv_roles(prefs, master)
    nj = job_to_normalized(job)
    stored = session.exec(select(JobMatch).where(JobMatch.job_id == job.id,
                                                 JobMatch.master_cv_id == cv_record.id)).first()
    match = MatchResult(**stored.result) if stored and stored.result else score_job(nj, master, prefs, facts)

    cv_doc = tailor_cv(master, nj, match, facts, provider)
    letter = write_cover_letter(master, profile, nj, match, facts, provider)
    answers = answer_questions(questions, master, profile, nj, facts, provider)

    app.master_cv_id = cv_record.id
    app.match_score = match.score
    app.tailored_cv = cv_doc.content.model_dump()
    app.cv_guard = cv_doc.guard.as_dict()
    app.cover_letter = letter.content
    app.cover_guard = letter.guard.as_dict()
    app.answers = answers
    app.generation_notes = cv_doc.notes + letter.notes
    app.generation_method = {"cv": cv_doc.method, "cover_letter": letter.method,
                             "provider": getattr(provider, "name", "none")}
    if match.score < prefs.min_apply_score:
        app.generation_notes = [f"Match score {match.score} is below your minimum of {prefs.min_apply_score}. "
                                "Interview chances are usually low for weaker matches; applying to stronger "
                                "matches gives a better interview rate."] + app.generation_notes
    if not app.cv_format:
        app.cv_format = default_format(job)
    app.format_notes = render_cv_files(app, profile)[2]
    app.approved_at, app.approved_snapshot = None, ""
    app.updated_at = _now()


def regenerate(session: Session, user_id: int, app: Application) -> Application:
    if app.status not in sm.EDITABLE:
        raise sm.TransitionError("Only applications that have not been submitted can be regenerated.")
    job = session.get(Job, app.job_id)
    questions = [a["question"] for a in app.answers] or list(DEFAULT_QUESTIONS)
    _generate(session, user_id, app, job, questions)
    if app.status != sm.READY:
        transition(session, app, sm.READY, reason="regenerated")
    session.add(app)
    session.commit()
    session.refresh(app)
    return app


def update_review(session: Session, user_id: int, app: Application, *, tailored_cv: dict | None = None,
                  cover_letter: str | None = None, answers: list[dict] | None = None,
                  notes: str | None = None) -> Application:
    """User edits during review. Everything is re-checked; any change after approval revokes it."""
    if app.status not in sm.EDITABLE:
        raise sm.TransitionError("This application can no longer be edited.")
    profile, _ = get_profile(session, user_id)
    cv_record = get_active_cv(session, user_id)
    _, facts = build_facts(cv_record, profile)
    job = session.get(Job, app.job_id)
    allowed = f"{job.title}\n{job.company}\n{job.location}\n{job.description_text}"
    changed = False
    if tailored_cv is not None:
        cv = CVData.model_validate(tailored_cv)
        app.tailored_cv = cv.model_dump()
        app.cv_guard = check_cv(cv, facts).as_dict()
        changed = True
    if cover_letter is not None:
        app.cover_letter = cover_letter
        app.cover_guard = check_free_text(cover_letter, facts, "cover_letter", allowed).as_dict()
        changed = True
    if answers is not None:
        checked = []
        for item in answers:
            text = (item.get("answer") or "").strip()
            report = check_free_text(text, facts, "answer", allowed) if text else None
            checked.append({"question": item.get("question", ""), "answer": text,
                            "needs_user_input": not text and not item.get("skip"),
                            "skip": bool(item.get("skip")), "source": item.get("source") or "user",
                            "guard": report.as_dict() if report else {"passed": True, "violations": []}})
        app.answers = checked
        changed = True
    if notes is not None:
        app.notes = notes
    if changed and app.status in (sm.APPROVED, sm.NEEDS_USER):
        app.approved_at, app.approved_snapshot = None, ""
        transition(session, app, sm.READY, reason="edited after approval")
    app.updated_at = _now()
    session.add(app)
    session.commit()
    session.refresh(app)
    return app


def current_snapshot(app: Application) -> str:
    return sm.snapshot_hash(tailored_cv=app.tailored_cv, cover_letter=app.cover_letter, answers=app.answers,
                            apply_url=app.apply_url, cv_format=app.cv_format)


def approve(session: Session, user_id: int, app: Application, *, confirmed: bool, auto_submit: bool = False) -> Application:
    answer_guards_ok = all((a.get("guard") or {}).get("passed", True) for a in app.answers)
    problems = sm.approval_blockers(cv_guard=app.cv_guard, cover_guard=app.cover_guard, answers=app.answers,
                                    confirmed=confirmed)
    if not answer_guards_ok:
        problems.append("One or more answers contain unverified claims.")
    if problems:
        raise ValueError(" ".join(problems))
    transition(session, app, sm.APPROVED, auto_submit=auto_submit)
    app.approved_at = _now()
    app.approved_snapshot = current_snapshot(app)
    app.blocker = {"auto_submit_requested": bool(auto_submit)}
    audit(session, user_id, "application.approved", "application", app.id, snapshot=app.approved_snapshot,
          auto_submit=auto_submit)
    session.commit()
    session.refresh(app)
    return app


def render_cv_files(app: Application, profile: CandidateProfile) -> tuple[bytes, bytes, list[str]]:
    cv = CVData.model_validate(app.tailored_cv)
    fmt, style = resolve_layout(app.cv_format or {}, profile.custom_layouts)
    docx_bytes, pdf_bytes, rendered = formatted_renderer.render(cv, fmt, style, profile,
                                                                (app.cv_format or {}).get("job_country", ""))
    return docx_bytes, pdf_bytes, rendered.removed


def export_documents(app: Application, profile: CandidateProfile | None = None) -> dict[str, Path]:
    """Write the approved documents to disk (used for upload and for the user's downloads)."""
    if profile is None:
        with session_scope() as s:
            profile, _ = get_profile(s, app.user_id)
    folder = get_settings().generated_dir / f"application-{app.id}"
    folder.mkdir(parents=True, exist_ok=True)
    cv = CVData.model_validate(app.tailored_cv)
    base = (cv.contact.full_name or "CV").title().replace(" ", "_")
    paths = {
        "cv_docx": folder / f"{base}_CV.docx",
        "cv_pdf": folder / f"{base}_CV.pdf",
        "cover_docx": folder / f"{base}_Cover_Letter.docx",
        "cover_pdf": folder / f"{base}_Cover_Letter.pdf",
    }
    docx_bytes, pdf_bytes, _ = render_cv_files(app, profile)
    paths["cv_docx"].write_bytes(docx_bytes)
    paths["cv_pdf"].write_bytes(pdf_bytes)
    paths["cover_docx"].write_bytes(text_to_docx(app.cover_letter))
    paths["cover_pdf"].write_bytes(text_to_pdf(app.cover_letter))
    return paths


def default_format(job: Job) -> dict:
    return {"country_code": code_for_country(job.country), "style": "modern", "custom_layout_id": "",
            "date_precision": "month", "layout": "chronological", "job_country": job.country}


def set_format(session: Session, user_id: int, app: Application, cv_format: dict) -> Application:
    if app.status not in sm.EDITABLE:
        raise sm.TransitionError("The format can't change after the application was sent.")
    profile, _ = get_profile(session, user_id)
    code = (cv_format.get("country_code") or "").upper()
    if code not in FORMATS:
        raise ValueError("Unknown country format.")
    if cv_format.get("style", "modern") not in STYLES:
        raise ValueError("Unknown style.")
    custom = cv_format.get("custom_layout_id") or ""
    if custom and not any(c.get("id") == custom for c in profile.custom_layouts):
        raise ValueError("Unknown sample layout.")
    if cv_format.get("date_precision", "month") not in ("month", "year"):
        raise ValueError("Dates must be 'month' or 'year'.")
    if cv_format.get("layout", "chronological") not in ("chronological", "hybrid"):
        raise ValueError("Layout must be 'chronological' or 'hybrid'.")
    app.cv_format = {"country_code": code, "style": cv_format.get("style", "modern"), "custom_layout_id": custom,
                     "date_precision": cv_format.get("date_precision", "month"),
                     "layout": cv_format.get("layout", "chronological"),
                     "job_country": (app.cv_format or {}).get("job_country", "")}
    _, _, removed = render_cv_files(app, profile)
    app.format_notes = removed
    if app.status in (sm.APPROVED, sm.NEEDS_USER):
        app.approved_at, app.approved_snapshot = None, ""
        transition(session, app, sm.READY, reason="format changed after approval")
    app.updated_at = _now()
    session.add(app)
    session.commit()
    session.refresh(app)
    return app


def start_apply(session: Session, user_id: int, app: Application, mode: str = "assist") -> Application:
    """DRAFT → REVIEW → APPROVAL must already have happened, for exactly this content."""
    if app.status not in (sm.APPROVED, sm.NEEDS_USER):
        raise sm.TransitionError("Approve the application before applying.")
    if not app.approved_snapshot or app.approved_snapshot != current_snapshot(app):
        raise sm.TransitionError("The application changed after approval. Review and approve it again.")
    if mode not in ("manual", "assist", "submit"):
        raise ValueError("Unknown apply mode.")
    if mode != "manual" and not get_settings().apply_assist_enabled:
        raise ValueError("Form filling only works in the desktop version. Open the application page and use "
                         "your approved CV, letter and answers.")
    if app.status == sm.NEEDS_USER:
        transition(session, app, sm.APPROVED, reason="retry")
    transition(session, app, sm.SUBMITTING, mode=mode)
    session.commit()

    profile, _ = get_profile(session, user_id)
    cv = CVData.model_validate(app.tailored_cv)
    paths = export_documents(app, profile)
    first, last = split_name(profile.full_name or cv.contact.full_name)
    bundle = ApplyBundle(
        application_id=app.id, apply_url=app.apply_url, first_name=first, last_name=last,
        email=profile.email or cv.contact.email, phone=profile.phone or cv.contact.phone,
        location=profile.location or cv.contact.location, linkedin=profile.linkedin_url,
        website=profile.portfolio_url or profile.github_url, cv_path=paths["cv_pdf"],
        cover_letter_text=app.cover_letter, cover_letter_path=paths["cover_pdf"],
        answers=[a for a in app.answers if a.get("answer")],
        auto_submit=bool((app.blocker or {}).get("auto_submit_requested")),
    )
    settings = get_settings()
    assistant = ApplyAssistant(profile_dir=settings.data_dir / "browser-profile",
                               screenshots_dir=settings.generated_dir / "screenshots",
                               headless=settings.playwright_headless, allow_auto_submit=settings.allow_auto_submit)
    app_id = app.id

    def record(outcome: ApplyOutcome) -> None:
        with session_scope() as s:
            a = s.get(Application, app_id)
            if a is None or a.status != sm.SUBMITTING:
                return
            a.blocker = {**(a.blocker or {}), "last_outcome": outcome.as_dict()}
            if outcome.status == "submitted":
                a.submitted_at = _now()
                a.submission_method = "automated"
                transition(s, a, sm.SUBMITTED, method="automated", url=outcome.final_url)
                job = s.get(Job, a.job_id)
                if job:
                    job.status = "applied"
                    s.add(job)
            else:
                transition(s, a, sm.NEEDS_USER, outcome=outcome.status, message=outcome.message)
            audit(s, a.user_id, f"application.apply.{outcome.status}", "application", a.id,
                  message=outcome.message, blocker=outcome.blocker)

    if mode == "manual":
        record(assistant.run(bundle, "manual"))
    else:
        threading.Thread(target=assistant.run, args=(bundle, mode, record), daemon=True,
                         name=f"apply-{app.id}").start()
    session.refresh(app)
    return app


def mark_submitted(session: Session, user_id: int, app: Application, method: str = "manual",
                   submitted_at: datetime | None = None) -> Application:
    if app.status not in (sm.APPROVED, sm.NEEDS_USER, sm.SUBMITTING):
        raise sm.TransitionError("Only approved applications can be marked as submitted.")
    if app.approved_snapshot != current_snapshot(app):
        raise sm.TransitionError("The application changed after approval. Approve it again first.")
    app.submitted_at = submitted_at or _now()
    app.submission_method = method
    transition(session, app, sm.SUBMITTED, method=method)
    job = session.get(Job, app.job_id)
    if job:
        job.status = "applied"
        session.add(job)
    audit(session, user_id, "application.submitted", "application", app.id, method=method)
    session.commit()
    session.refresh(app)
    return app


def record_outcome(session: Session, user_id: int, app: Application, *, status: str | None, kind: str,
                   occurred_at: datetime | None = None, **details) -> Application:
    """Interviews, rejections, offers, notes."""
    if status and status != app.status:
        transition(session, app, status, **details)
    if kind != "status_change" or not status:
        _event(session, app, kind, app.status, app.status, occurred_at=occurred_at, **details)
    audit(session, user_id, f"application.{kind}", "application", app.id, status=status)
    session.commit()
    session.refresh(app)
    return app


FOLLOW_UP_AFTER_DAYS = 7


def follow_up(session: Session, user_id: int, app: Application) -> dict:
    """A short, factual follow-up email for applications with no reply after a week."""
    job = session.get(Job, app.job_id)
    profile, _ = get_profile(session, user_id)
    cv = CVData.model_validate(app.tailored_cv)
    events = session.exec(select(ApplicationEvent).where(ApplicationEvent.application_id == app.id)).all()
    heard_back = any(e.kind in ("email", "interview") for e in events) or app.status not in (sm.SUBMITTED,)
    followed = [e for e in events if e.kind == "follow_up"]
    days = (_now() - _aware(app.submitted_at)).days if app.submitted_at else 0
    due = bool(app.submitted_at) and days >= FOLLOW_UP_AFTER_DAYS and not heard_back and not followed
    name = profile.full_name or cv.contact.full_name.title()
    latest = cv.experience[0] if cv.experience else None
    sent_on = _aware(app.submitted_at).strftime("%d %B %Y") if app.submitted_at else "recently"
    lines = [f"Dear Hiring Team,", "",
             f"I applied for the {job.title} position at {job.company} on {sent_on} and wanted to confirm my "
             f"continued interest in the role."]
    if latest:
        lines.append(f"In my current work as {latest.title} at {latest.employer}, I have been doing the kind of work "
                     f"the role describes, and I would welcome the chance to discuss how I could contribute.")
    lines += ["", "Please let me know if you need anything further from me.", "", "Kind regards,", name]
    if profile.phone or cv.contact.phone:
        lines.append(profile.phone or cv.contact.phone)
    return {"due": due, "days_since_submitted": days, "already_followed_up": bool(followed),
            "subject": f"Following up: {job.title} application", "body": "\n".join(lines)}


def _aware(value: datetime | None) -> datetime:
    if value is None:
        return _now()
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def pick_top_jobs(session: Session, user_id: int, count: int) -> tuple[list[Job], dict]:
    """Best jobs to prepare next, in the user's priority order: country list first, their roles first,
    then CV-suggested roles, then match score. Skips weak matches, dealbreakers, risky and snippet-only
    postings, and jobs that already have an application."""
    _, prefs = get_profile(session, user_id)
    cv_record = get_active_cv(session, user_id)
    taken = set(session.exec(select(Application.job_id).where(Application.user_id == user_id,
                                                              Application.status != sm.DISCARDED)).all())
    rows = session.exec(select(Job, JobMatch).join(JobMatch, JobMatch.job_id == Job.id)
                        .where(Job.user_id == user_id, JobMatch.master_cv_id == cv_record.id,
                               Job.status.in_(["new", "shortlisted"]))
                        .order_by(JobMatch.priority.asc())).all()
    skipped = {"low_score": 0, "dealbreaker": 0, "high_risk": 0, "snippet_only": 0}
    picked: list[Job] = []
    for job, match in rows:
        if job.id in taken:
            continue
        if match.result.get("dealbreakers"):
            skipped["dealbreaker"] += 1
        elif match.score < prefs.min_apply_score:
            skipped["low_score"] += 1
        elif job.risk_level == "high" and not (job.quality or {}).get("user_override"):
            skipped["high_risk"] += 1
        elif (job.raw or {}).get("snippet_only"):
            skipped["snippet_only"] += 1
        else:
            picked.append(job)
        if len(picked) >= count:
            break
    return picked, skipped


_batch_status: dict[int, dict] = {}
_batch_lock = threading.Lock()


def batch_status(user_id: int) -> dict:
    with _batch_lock:
        return dict(_batch_status.get(user_id, {"running": False}))


def prepare_top(user_id: int, count: int) -> dict:
    """Draft applications for the top jobs in the background. Every draft still needs approval."""
    with _batch_lock:
        if _batch_status.get(user_id, {}).get("running"):
            raise ValueError("Already preparing applications.")
    from backend.models import User
    from backend.services.billing import status as plan_status

    with session_scope() as s:
        st = plan_status(s, s.get(User, user_id))
        remaining = max(0, st["drafts_per_day"] - st["drafts_used_today"])
        if remaining == 0:
            raise ValueError("You've used today's applications. Watch a short ad for more, or go Pro.")
        jobs, skipped = pick_top_jobs(s, user_id, min(count, remaining))
        job_ids = [j.id for j in jobs]
    status = {"running": True, "total": len(job_ids), "done": 0, "created": [], "errors": [], "skipped": skipped}
    with _batch_lock:
        _batch_status[user_id] = status

    def work():
        for job_id in job_ids:
            try:
                with session_scope() as s:
                    job = s.get(Job, job_id)
                    app = create_draft(s, user_id, job)
                    status["created"].append(app.id)
            except Exception as exc:  # one failure must not stop the rest
                log.warning("Could not draft job %s: %s", job_id, exc)
                status["errors"].append({"job_id": job_id, "error": str(exc)[:200]})
            finally:
                status["done"] += 1
        status["running"] = False

    threading.Thread(target=work, daemon=True, name=f"prepare-{user_id}").start()
    return dict(status)
