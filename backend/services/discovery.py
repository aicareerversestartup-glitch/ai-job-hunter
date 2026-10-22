"""Discovery pipeline: sources → normalize → dedupe → quality/fraud → match → store."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from backend.cv.schema import CVData
from backend.cv.truthfulness import FactBase
from backend.integrations.base import SearchQuery, SourceError
from backend.integrations.registry import create_client
from backend.jobs.dedupe import JobKey, dedupe
from backend.jobs.fraud import assess_job
from backend.jobs.matcher import JobPreferences, priority, quick_relevance, score_job
from backend.jobs.normalizer import NormalizedJob, normalize_company, normalize_title
from backend.models import DiscoveryRun, Job, JobMatch, JobSource, MasterCV
from backend.services.common import NotReadyError, apply_cv_roles, audit, build_facts, get_active_cv, get_profile
from backend.utils.text import normalize_key, token_set

log = logging.getLogger(__name__)
RELEVANCE_THRESHOLD = 0.34
RECENT_DAYS = 45


def default_sources(session: Session, user_id: int) -> list[JobSource]:
    """Keyword sources that need no setup, created on first use so discovery works out of the box."""
    existing = session.exec(select(JobSource).where(JobSource.user_id == user_id)).all()
    if existing:
        return existing
    created = [JobSource(user_id=user_id, kind="remotive", label="Remotive (remote jobs)"),
               JobSource(user_id=user_id, kind="arbeitnow", label="Arbeitnow (Europe)")]
    for s in created:
        session.add(s)
    session.commit()
    return created


def job_to_normalized(job: Job) -> NormalizedJob:
    return NormalizedJob(source=job.source, source_job_id=job.source_job_id, url=job.url, apply_url=job.apply_url,
                         title=job.title, company=job.company, location=job.location, country=job.country,
                         remote_type=job.remote_type, employment_type=job.employment_type, seniority=job.seniority,
                         department=job.department, description_text=job.description_text, posted_at=job.posted_at,
                         salary_min=job.salary_min, salary_max=job.salary_max, salary_currency=job.salary_currency,
                         salary_period=job.salary_period, company_domain=job.company_domain)


def _fetch_source(source: JobSource, query: SearchQuery) -> tuple[int | None, list[NormalizedJob], str]:
    try:
        client = create_client(source.kind, source.identifier)
        return source.id, client.fetch(query), ""
    except SourceError as exc:
        return source.id, [], str(exc)
    except Exception as exc:  # unexpected payload changes etc.
        log.exception("Source %s failed", source.kind)
        return source.id, [], f"Unexpected error: {exc}"


def _passes_filters(job: NormalizedJob, prefs: JobPreferences, now: datetime,
                    countries: list[str] | None = None) -> bool:
    if quick_relevance(job, prefs) < RELEVANCE_THRESHOLD:
        return False
    if job.posted_at and (now - job.posted_at) > timedelta(days=RECENT_DAYS):
        return False
    wanted = countries if countries is not None else prefs.preferred_countries
    if wanted and job.country and job.remote_type != "remote" and not prefs.willing_to_relocate:
        if job.country not in wanted:
            return False
    if prefs.remote_preference == "remote_only" and job.remote_type in ("onsite", "hybrid"):
        return False
    return True


def store_job(session: Session, user_id: int, nj: NormalizedJob, cv_record: MasterCV | None,
              cv: CVData | None, facts: FactBase | None, prefs: JobPreferences) -> Job:
    quality = assess_job(nj)
    job = Job(user_id=user_id, source=nj.source, source_job_id=nj.source_job_id, fingerprint=nj.fingerprint,
              url=nj.url, apply_url=nj.apply_url, title=nj.title, company=nj.company, location=nj.location,
              country=nj.country, remote_type=nj.remote_type, employment_type=nj.employment_type,
              seniority=nj.seniority, department=nj.department, description_text=nj.description_text,
              posted_at=nj.posted_at, salary_min=nj.salary_min, salary_max=nj.salary_max,
              salary_currency=nj.salary_currency, salary_period=nj.salary_period, company_domain=nj.company_domain,
              quality=quality.as_dict(), risk_level=quality.risk_level, raw=nj.raw)
    session.add(job)
    session.flush()
    if cv_record is not None and cv is not None:
        upsert_match(session, user_id, job, nj, cv_record, cv, facts, prefs)
    return job


def upsert_match(session: Session, user_id: int, job: Job, nj: NormalizedJob, cv_record: MasterCV, cv: CVData,
                 facts: FactBase | None, prefs: JobPreferences) -> JobMatch:
    result = score_job(nj, cv, prefs, facts)
    order = priority(nj, result.score, prefs)
    match = session.exec(select(JobMatch).where(JobMatch.job_id == job.id,
                                                JobMatch.master_cv_id == cv_record.id)).first()
    if match is None:
        match = JobMatch(user_id=user_id, job_id=job.id, master_cv_id=cv_record.id, score=result.score)
    match.score = result.score
    match.priority = order["rank"] if not result.dealbreakers else 900000 + (100 - result.score)
    match.recommendation = result.recommendation
    match.result = {**result.as_dict(), "priority": order}
    session.add(match)
    return match


def run_discovery(session: Session, user_id: int, trigger: str = "manual") -> DiscoveryRun:
    profile, prefs = get_profile(session, user_id)
    try:
        cv_record = get_active_cv(session, user_id)
        cv, facts = build_facts(cv_record, profile)
    except NotReadyError:
        cv_record, cv, facts = None, None, None  # discovery still works; matching waits for a verified CV
    apply_cv_roles(prefs, cv)
    if not prefs.all_roles():
        raise NotReadyError("Upload and verify your CV, or add at least one target role in your profile.")

    run = DiscoveryRun(user_id=user_id, trigger=trigger)
    session.add(run)
    session.commit()
    session.refresh(run)

    sources = [s for s in default_sources(session, user_id) if s.enabled]
    query = SearchQuery(keywords=prefs.all_roles(), countries=prefs.preferred_countries,
                        cities=prefs.preferred_cities, remote_only=prefs.remote_preference == "remote_only")
    collected: list[NormalizedJob] = []
    errors: list[dict] = []
    stats = {"sources": len(sources), "fetched": 0, "relevant": 0, "new": 0, "duplicates": 0, "high_risk": 0}
    by_id = {s.id: s for s in sources}
    now = datetime.now(timezone.utc)
    def query_for(source: JobSource) -> SearchQuery:
        countries = (source.options or {}).get("countries")
        if countries:
            return SearchQuery(keywords=query.keywords, countries=countries, cities=query.cities,
                               remote_only=query.remote_only)
        return query

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_fetch_source, s, query_for(s)) for s in sources]
        for future in as_completed(futures):
            source_id, jobs, error = future.result()
            source = by_id[source_id]
            source.last_run_at = now
            source.last_status = "error" if error else "ok"
            source.last_error = error
            source.last_count = len(jobs)
            session.add(source)
            if error:
                errors.append({"source": source.label or source.kind, "error": error})
            stats["fetched"] += len(jobs)
            source_countries = (source.options or {}).get("countries") or None
            collected += [j for j in jobs if _passes_filters(j, prefs, now, source_countries)]
    stats["relevant"] = len(collected)

    existing_rows = session.exec(select(Job).where(Job.user_id == user_id)).all()
    existing_keys = [JobKey(j.source, j.source_job_id, j.fingerprint, normalize_company(j.company), normalize_title(j.title),
                            normalize_key(j.location), frozenset(token_set(j.description_text[:4000])))
                     for j in existing_rows]
    by_fp = {j.fingerprint: j for j in existing_rows}
    result = dedupe(collected, existing_keys)
    for dup, key in result.duplicates:
        stats["duplicates"] += 1
        original = by_fp.get(key.fingerprint)
        if original is not None:
            original.last_seen_at = now
            seen = {(d.get("source"), d.get("url")) for d in original.also_seen_on}
            if (dup.source, dup.url) not in seen and (dup.source, dup.source_job_id) != (original.source,
                                                                                        original.source_job_id):
                original.also_seen_on = original.also_seen_on + [{"source": dup.source, "url": dup.url}]
            session.add(original)
    for nj in result.unique:
        job = store_job(session, user_id, nj, cv_record, cv, facts, prefs)
        stats["new"] += 1
        stats["high_risk"] += job.risk_level == "high"

    run.status = "completed" if len(errors) < len(sources) or not sources else "failed"
    run.finished_at = datetime.now(timezone.utc)
    run.stats, run.errors = stats, errors
    session.add(run)
    audit(session, user_id, "discovery.run", "discovery_run", run.id, **stats)
    session.commit()
    session.refresh(run)
    return run


def rescore_all(session: Session, user_id: int) -> int:
    """Recompute matches after the CV or preferences change."""
    profile, prefs = get_profile(session, user_id)
    cv_record = get_active_cv(session, user_id)
    cv, facts = build_facts(cv_record, profile)
    apply_cv_roles(prefs, cv)
    jobs = session.exec(select(Job).where(Job.user_id == user_id, Job.status != "dismissed")).all()
    for job in jobs:
        upsert_match(session, user_id, job, job_to_normalized(job), cv_record, cv, facts, prefs)
    session.commit()
    return len(jobs)

