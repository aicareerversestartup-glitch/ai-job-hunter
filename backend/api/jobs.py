from __future__ import annotations

import threading

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlmodel import Session, select

from backend.api.deps import current_user, get_owned
from backend.config import get_settings
from backend.db import get_session, session_scope
from backend.integrations.base import SourceError
from backend.integrations.manual import ManualImportError, fetch_allowed, job_from_html, job_from_text
from backend.integrations.registry import SOURCE_CLASSES, describe_sources
from backend.jobs.jd_sections import split_jd
from backend.models import DiscoveryRun, Job, JobMatch, JobSource, User
from backend.schemas.api import ImportUrlIn, JobPatch, ManualJobIn, SourceIn, SourcePatch
from backend.security.guards import UnsafeURLError, validate_public_url
from backend.services.common import NotReadyError, apply_cv_roles, audit, build_facts, get_active_cv, get_profile
from backend.services.discovery import default_sources, rescore_all, run_discovery, store_job

router = APIRouter(prefix="/api", tags=["jobs"])
_running: set[int] = set()
_lock = threading.Lock()


# ---------------------------------------------------------------------------------- sources
@router.get("/sources/catalog")
def source_catalog(user: User = Depends(current_user)):
    return describe_sources()


@router.get("/sources")
def list_sources(user: User = Depends(current_user), session: Session = Depends(get_session)):
    return default_sources(session, user.id)


@router.post("/sources")
def add_source(body: SourceIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    cls = SOURCE_CLASSES.get(body.kind)
    if cls is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown source type.")
    if cls.needs_identifier and not body.identifier.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, cls.identifier_help)
    if body.kind == "rss":
        try:
            validate_public_url(body.identifier)
        except UnsafeURLError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    default_sources(session, user.id)
    source = JobSource(user_id=user.id, kind=body.kind, identifier=body.identifier.strip(),
                       label=body.label or (f"{cls.display_name}: {body.identifier}" if body.identifier
                                            else cls.display_name), enabled=body.enabled)
    session.add(source)
    session.commit()
    session.refresh(source)
    return source


@router.patch("/sources/{source_id}")
def patch_source(source_id: int, body: SourcePatch, user: User = Depends(current_user),
                 session: Session = Depends(get_session)):
    source = get_owned(session, JobSource, source_id, user)
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(source, key, value)
    session.add(source)
    session.commit()
    session.refresh(source)
    return source


@router.delete("/sources/{source_id}")
def delete_source(source_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    session.delete(get_owned(session, JobSource, source_id, user))
    session.commit()
    return {"ok": True}


# -------------------------------------------------------------------------------- discovery
@router.post("/discovery/run")
def start_discovery(user: User = Depends(current_user), session: Session = Depends(get_session)):
    _, prefs = get_profile(session, user.id)
    try:
        get_active_cv(session, user.id)
        has_cv = True
    except NotReadyError:
        has_cv = False
    if not prefs.target_roles and not (has_cv and prefs.include_cv_roles):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Upload and verify your CV, or add at least one target role in your profile.")
    from backend.services.billing import LimitReached, check_search_allowed

    try:
        check_search_allowed(session, session.get(User, user.id))
    except LimitReached as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc))
    with _lock:
        if user.id in _running:
            raise HTTPException(status.HTTP_409_CONFLICT, "A search is already running.")
        _running.add(user.id)

    def work(user_id: int):
        try:
            with session_scope() as s:
                run_discovery(s, user_id)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Discovery failed")
        finally:
            with _lock:
                _running.discard(user_id)

    threading.Thread(target=work, args=(user.id,), daemon=True).start()
    return {"started": True}


@router.get("/discovery/runs")
def discovery_runs(user: User = Depends(current_user), session: Session = Depends(get_session)):
    runs = session.exec(select(DiscoveryRun).where(DiscoveryRun.user_id == user.id)
                        .order_by(DiscoveryRun.started_at.desc()).limit(20)).all()
    return {"running": user.id in _running, "runs": runs}


# ------------------------------------------------------------------------------------- jobs
def _job_row(job: Job, match: JobMatch | None, full: bool = False) -> dict:
    data = job.model_dump(exclude={"raw"} if full else {"raw", "description_text"})
    data["snippet_only"] = bool((job.raw or {}).get("snippet_only"))
    if full:
        data["jd_sections"] = split_jd(job.description_text)
    else:
        data["description_preview"] = job.description_text[:280]
    data["match"] = None if match is None else {
        "score": match.score, "recommendation": match.recommendation,
        **({"result": match.result} if full else {
            "missing_count": len([m for m in match.result.get("missing_requirements", [])
                                  if m.get("importance") == "required"]),
            "matched_skills": match.result.get("matched_skills", [])[:6],
            "dealbreakers": match.result.get("dealbreakers", []),
            "priority": match.result.get("priority", {})}),
    }
    return data


@router.get("/jobs")
def list_jobs(
    user: User = Depends(current_user), session: Session = Depends(get_session),
    status_filter: str | None = Query(None, alias="status"), min_score: int = 0, include_high_risk: bool = False,
    q: str = "", remote: str | None = None, country: str | None = None, sort: str = "priority",
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
):
    try:
        cv_id = get_active_cv(session, user.id).id
    except NotReadyError:
        cv_id = -1
    query = select(Job, JobMatch).join(JobMatch, (JobMatch.job_id == Job.id) & (JobMatch.master_cv_id == cv_id),
                                       isouter=True).where(Job.user_id == user.id)
    if status_filter:
        query = query.where(Job.status == status_filter)
    else:
        query = query.where(Job.status != "dismissed")
    if not include_high_risk:
        query = query.where(Job.risk_level != "high")
    if min_score:
        query = query.where(JobMatch.score >= min_score)
    if q:
        like = f"%{q.lower()}%"
        query = query.where(or_(func.lower(Job.title).like(like), func.lower(Job.company).like(like),
                                func.lower(Job.location).like(like)))
    if remote:
        query = query.where(Job.remote_type == remote)
    if country:
        query = query.where(Job.country == country)
    total = session.exec(select(func.count()).select_from(query.subquery())).one()
    order = {"priority": (JobMatch.priority.asc().nulls_last(), Job.discovered_at.desc()),
             "score": (JobMatch.score.desc().nulls_last(), Job.discovered_at.desc()),
             "newest": (Job.discovered_at.desc(),), "posted": (Job.posted_at.desc().nulls_last(),)}.get(
        sort, (JobMatch.score.desc().nulls_last(),))
    rows = session.exec(query.order_by(*order).offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "page": page, "page_size": page_size, "items": [_job_row(j, m) for j, m in rows]}


@router.get("/jobs/{job_id}")
def job_detail(job_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    job = get_owned(session, Job, job_id, user)
    match = None
    try:
        cv_id = get_active_cv(session, user.id).id
        match = session.exec(select(JobMatch).where(JobMatch.job_id == job.id, JobMatch.master_cv_id == cv_id)).first()
    except NotReadyError:
        pass
    return _job_row(job, match, full=True)


@router.patch("/jobs/{job_id}")
def patch_job(job_id: int, body: JobPatch, user: User = Depends(current_user), session: Session = Depends(get_session)):
    job = get_owned(session, Job, job_id, user)
    if body.status:
        job.status = body.status
    if body.override_risk is not None:
        job.quality = {**job.quality, "user_override": body.override_risk}
        audit(session, user.id, "job.risk_override", "job", job.id, value=body.override_risk)
    session.add(job)
    session.commit()
    return {"ok": True}


def _store_manual(session: Session, user: User, nj) -> dict:
    existing = session.exec(select(Job).where(Job.user_id == user.id, Job.fingerprint == nj.fingerprint)).first()
    if existing:
        return {"id": existing.id, "duplicate": True}
    profile, prefs = get_profile(session, user.id)
    try:
        cv_record = get_active_cv(session, user.id)
        cv, facts = build_facts(cv_record, profile)
    except NotReadyError:
        cv_record = cv = facts = None
    apply_cv_roles(prefs, cv)
    job = store_job(session, user.id, nj, cv_record, cv, facts, prefs)
    session.commit()
    return {"id": job.id, "duplicate": False}


@router.post("/jobs/manual")
def add_manual_job(body: ManualJobIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    try:
        nj = job_from_text(title=body.title, company=body.company, description=body.description, url=body.url,
                           location=body.location, apply_url=body.apply_url)
    except ManualImportError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    return _store_manual(session, user, nj)


@router.post("/jobs/import-url")
def import_job_url(body: ImportUrlIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    import httpx

    try:
        url = validate_public_url(body.url)
    except UnsafeURLError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    if not fetch_allowed(url):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "This site does not allow automated access. Open the posting yourself and use "
                            "'Paste a job' with the title and description.")
    try:
        response = httpx.get(url, timeout=20, follow_redirects=True,
                             headers={"User-Agent": get_settings().http_user_agent})
        validate_public_url(str(response.url))
        response.raise_for_status()
        nj = job_from_html(response.text[:3_000_000], str(response.url))
    except (httpx.HTTPError, UnsafeURLError, SourceError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Could not fetch that page: {exc}")
    except ManualImportError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    return _store_manual(session, user, nj)


@router.post("/jobs/rescore")
def rescore(user: User = Depends(current_user), session: Session = Depends(get_session)):
    try:
        return {"rescored": rescore_all(session, user.id)}
    except NotReadyError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
