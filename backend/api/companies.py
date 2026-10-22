"""Target companies: add a company + countries, and the app finds where it posts jobs."""
from __future__ import annotations

import logging
import threading

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from backend.api.deps import current_user
from backend.db import get_session, session_scope
from backend.integrations.companies import detect_company_boards, load_registry, registry_entry
from backend.jobs.normalizer import normalize_company
from backend.models import JobSource, Profile, User
from backend.services.common import audit

router = APIRouter(prefix="/api/companies", tags=["companies"])
log = logging.getLogger(__name__)


class CompanyIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    countries: list[str] = Field(default_factory=list, max_length=15)


def _prefs_record(session: Session, user: User) -> Profile:
    record = session.exec(select(Profile).where(Profile.user_id == user.id)).first()
    if record is None:
        record = Profile(user_id=user.id, data={"full_name": user.full_name, "email": user.email}, preferences={})
        session.add(record)
        session.flush()
    return record


def _company_sources(session: Session, user_id: int, name: str) -> list[JobSource]:
    key = normalize_company(name)
    rows = session.exec(select(JobSource).where(JobSource.user_id == user_id)).all()
    return [r for r in rows if normalize_company((r.options or {}).get("company", "")) == key]


def _detect_in_background(user_id: int, name: str, countries: list[str]) -> None:
    def work():
        try:
            boards = detect_company_boards(name)
        except Exception:
            log.exception("Board detection failed for %s", name)
            boards = []
        with session_scope() as s:
            existing = {(r.kind, r.identifier) for r in s.exec(select(JobSource).where(JobSource.user_id == user_id))}
            for b in boards:
                if (b["kind"], b["identifier"]) in existing:
                    continue
                s.add(JobSource(user_id=user_id, kind=b["kind"], identifier=b["identifier"],
                                label=f"{name} ({b['kind'].title()} board)",
                                options={"company": name, "countries": countries}))
            for src in s.exec(select(JobSource).where(JobSource.user_id == user_id,
                                                      JobSource.kind == "company_search")):
                if normalize_company((src.options or {}).get("company", "")) == normalize_company(name):
                    src.options = {**src.options, "detection": "done", "boards_found": len(boards)}
                    s.add(src)

    threading.Thread(target=work, daemon=True, name=f"detect-{name}").start()


def _add(session: Session, user: User, name: str, countries: list[str]) -> dict:
    entry = registry_entry(name)
    canonical = entry["name"] if entry else name.strip()
    countries = [c.strip() for c in countries if c.strip()] or (entry or {}).get("hubs", [])
    record = _prefs_record(session, user)
    prefs = dict(record.preferences or {})
    targets = [t for t in prefs.get("target_companies", [])
               if normalize_company(t.get("name", "")) != normalize_company(canonical)]
    targets.append({"name": canonical, "countries": countries})
    record.preferences = {**prefs, "target_companies": targets}
    session.add(record)
    sources = _company_sources(session, user.id, canonical)
    for src in sources:
        src.options = {**(src.options or {}), "countries": countries}
        session.add(src)
    if not any(s.kind == "company_search" for s in sources):
        session.add(JobSource(user_id=user.id, kind="company_search", identifier=canonical,
                              label=f"{canonical} (job-search APIs)",
                              options={"company": canonical, "countries": countries, "detection": "running"}))
    return {"name": canonical, "countries": countries}


@router.get("/catalog")
def catalog(user: User = Depends(current_user)):
    """Companies from your list with their official careers pages."""
    return load_registry()


@router.get("")
def list_companies(user: User = Depends(current_user), session: Session = Depends(get_session)):
    record = _prefs_record(session, user)
    out = []
    for target in (record.preferences or {}).get("target_companies", []):
        entry = registry_entry(target["name"]) or {}
        sources = _company_sources(session, user.id, target["name"])
        out.append({**target, "careers_url": entry.get("careers_url", ""), "industry": entry.get("industry", ""),
                    "sponsorship_note": entry.get("sponsorship_note", ""), "suggested_roles": entry.get("roles", []),
                    "sources": [{"id": s.id, "kind": s.kind, "identifier": s.identifier, "enabled": s.enabled,
                                 "last_status": s.last_status, "last_error": s.last_error, "last_count": s.last_count,
                                 "detection": (s.options or {}).get("detection", "")} for s in sources]})
    return out


@router.post("")
def add_company(body: CompanyIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    result = _add(session, user, body.name, body.countries)
    audit(session, user.id, "company.added", name=result["name"], countries=result["countries"])
    session.commit()
    _detect_in_background(user.id, result["name"], result["countries"])
    return result


@router.post("/add-all-from-list")
def add_all(user: User = Depends(current_user), session: Session = Depends(get_session)):
    """Add every company from data/companies.json with its hub countries."""
    added = [_add(session, user, entry["name"], entry.get("hubs", [])) for entry in load_registry()]
    session.commit()
    for item in added:
        _detect_in_background(user.id, item["name"], item["countries"])
    return {"added": len(added)}


@router.delete("/{name}")
def remove_company(name: str, user: User = Depends(current_user), session: Session = Depends(get_session)):
    record = _prefs_record(session, user)
    prefs = dict(record.preferences or {})
    prefs["target_companies"] = [t for t in prefs.get("target_companies", [])
                                 if normalize_company(t.get("name", "")) != normalize_company(name)]
    record.preferences = prefs
    session.add(record)
    for src in _company_sources(session, user.id, name):
        session.delete(src)
    session.commit()
    return {"ok": True}

