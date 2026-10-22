"""Master CV lifecycle: upload (immutable original), parse, review, verify, version."""
from __future__ import annotations

import hashlib
import os
import stat
from datetime import datetime, timezone

from sqlmodel import Session, select

from backend.ai.generation import check_cv_against_text, extract_cv_structure
from backend.config import get_settings
from backend.cv.parser import CVParseError, extract_text
from backend.cv.schema import CVData
from backend.models import MasterCV
from backend.security.guards import safe_filename
from backend.services.common import audit, get_ai_provider


def store_original(user_id: int, filename: str, data: bytes) -> tuple[str, str]:
    """Write the upload once, content-addressed, and make it read-only. Never overwritten."""
    settings = get_settings()
    digest = hashlib.sha256(data).hexdigest()
    folder = settings.master_cv_dir / str(user_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{digest[:16]}_{safe_filename(filename, 'cv')}"
    if not path.exists():
        path.write_bytes(data)
        os.chmod(path, stat.S_IREAD | stat.S_IRGRP)
    return str(path), digest


def upload_master_cv(session: Session, user_id: int, filename: str, data: bytes) -> MasterCV:
    settings = get_settings()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise CVParseError(f"File is larger than {settings.max_upload_mb} MB.")
    extracted = extract_text(filename, data)
    if len(extracted.text) < 80:
        raise CVParseError("Could not read enough text from this file. Try a DOCX or a text-based PDF.")
    path, digest = store_original(user_id, filename, data)
    structured, notes = extract_cv_structure(extracted.text, get_ai_provider(session, user_id))
    notes = (extracted.warnings or []) + notes

    previous = session.exec(select(MasterCV).where(MasterCV.user_id == user_id, MasterCV.is_active == True)).all()  # noqa: E712
    version = 1 + max((p.version for p in session.exec(select(MasterCV).where(MasterCV.user_id == user_id))),
                      default=0)
    for p in previous:
        p.is_active = False
        if p.status != "verified":
            p.status = "superseded"
        session.add(p)
    record = MasterCV(user_id=user_id, version=version, original_filename=filename, stored_path=path, sha256=digest,
                      raw_text=extracted.text, parsed_data=structured.model_dump(), data=structured.model_dump(),
                      parse_method=extracted.method, parse_notes=notes)
    session.add(record)
    session.flush()
    audit(session, user_id, "master_cv.uploaded", "master_cv", record.id, filename=filename, sha256=digest)
    session.commit()
    session.refresh(record)
    return record


def update_master_cv_data(session: Session, user_id: int, record: MasterCV, data: CVData) -> MasterCV:
    """Save the user's corrections. A verified version is frozen, so edits create a new version
    that references the same original file."""
    warnings = check_cv_against_text(data, record.raw_text)
    if record.status == "verified":
        record.is_active = False
        session.add(record)
        record = MasterCV(user_id=user_id, version=record.version + 1, parent_id=record.id,
                          original_filename=record.original_filename, stored_path=record.stored_path,
                          sha256=record.sha256, raw_text=record.raw_text, parsed_data=record.parsed_data,
                          data=data.model_dump(), parse_method=record.parse_method, parse_notes=[])
    else:
        record.data = data.model_dump()
    record.parse_notes = [n for n in record.parse_notes if not n.startswith("Not found in the original file")]
    if warnings:
        # The user may legitimately add facts their file omitted; they are the source of truth,
        # but we flag them so it is a conscious decision.
        record.parse_notes = record.parse_notes + [
            "Not found in the original file (you added these — make sure they are accurate): "
            + "; ".join(warnings[:10])]
    session.add(record)
    session.flush()
    audit(session, user_id, "master_cv.edited", "master_cv", record.id, added_values=warnings[:20])
    session.commit()
    session.refresh(record)
    return record


def verify_master_cv(session: Session, user_id: int, record: MasterCV) -> MasterCV:
    data = CVData.model_validate(record.data)
    problems = []
    if not data.experience and not data.education:
        problems.append("Add at least one experience or education entry.")
    for i, exp in enumerate(data.experience):
        if "not detected" in exp.employer or "not detected" in exp.title:
            problems.append(f"Experience #{i + 1}: fill in the employer and title.")
    for i, edu in enumerate(data.education):
        if "not detected" in edu.institution:
            problems.append(f"Education #{i + 1}: fill in the institution.")
    from backend.cv.bullet_coach import has_placeholders

    blanks = [b for e in data.experience for b in e.bullets if has_placeholders(b)]
    if has_placeholders(data.summary) or blanks:
        problems.append(f"Fill in or remove the blanks ([__], [KPI], [how]…) in {len(blanks) or 1} line(s) first. "
                        "Only use your real numbers.")
    if problems:
        raise ValueError(" ".join(problems))
    record.status = "verified"
    record.verified_at = datetime.now(timezone.utc)
    record.is_active = True
    session.add(record)
    audit(session, user_id, "master_cv.verified", "master_cv", record.id, version=record.version)
    session.commit()
    session.refresh(record)
    return record
