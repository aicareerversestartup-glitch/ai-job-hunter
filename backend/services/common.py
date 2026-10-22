"""Shared service helpers: audit log, AI provider resolution, profile/CV loading."""
from __future__ import annotations

from sqlmodel import Session, select

from backend.ai.providers.base import AIConfig, LLMProvider
from backend.ai.providers.http_providers import get_provider
from backend.config import get_settings
from backend.cv.profile import CandidateProfile
from backend.cv.schema import CVData
from backend.cv.truthfulness import FactBase
from backend.jobs.matcher import JobPreferences
from backend.models import AISettings, AuditLog, MasterCV, Profile
from backend.security.crypto import decrypt_secret


class NotReadyError(RuntimeError):
    """Raised when a step needs something the user has not set up yet (e.g. a verified CV)."""


def audit(session: Session, user_id: int | None, action: str, entity: str = "", entity_id: int | None = None,
          **details) -> None:
    session.add(AuditLog(user_id=user_id, action=action, entity=entity, entity_id=entity_id, details=details))


def get_ai_provider(session: Session, user_id: int) -> LLMProvider:
    record = session.exec(select(AISettings).where(AISettings.user_id == user_id)).first()
    settings = get_settings()
    if record and record.provider and record.provider != "none":
        config = AIConfig(provider=record.provider, model=record.model, base_url=record.base_url,
                          api_key=decrypt_secret(record.api_key_encrypted), temperature=record.temperature)
    else:
        # The server's own AI key costs money per call: Pro users get it; free users only if the operator allows.
        from backend.models import User
        from backend.services.billing import is_pro

        user = session.get(User, user_id)
        if user is not None and (is_pro(user) or settings.server_ai_for_free_users):
            config = AIConfig(provider=settings.ai_provider, model=settings.ai_model, api_key=settings.ai_api_key,
                              base_url=settings.ai_base_url)
        else:
            config = AIConfig(provider="none")
    return get_provider(config)


def get_profile(session: Session, user_id: int) -> tuple[CandidateProfile, JobPreferences]:
    record = session.exec(select(Profile).where(Profile.user_id == user_id)).first()
    if record is None:
        return CandidateProfile(), JobPreferences()
    return CandidateProfile.model_validate(record.data or {}), JobPreferences.model_validate(record.preferences or {})


def get_active_cv(session: Session, user_id: int, *, require_verified: bool = True) -> MasterCV:
    query = select(MasterCV).where(MasterCV.user_id == user_id, MasterCV.is_active == True)  # noqa: E712
    record = session.exec(query.order_by(MasterCV.version.desc())).first()
    if record is None:
        raise NotReadyError("Upload your Master CV first.")
    if require_verified and record.status != "verified":
        raise NotReadyError("Review and verify your Master CV before matching or tailoring.")
    return record


def build_facts(cv_record: MasterCV, profile: CandidateProfile) -> tuple[CVData, FactBase]:
    cv = CVData.model_validate(cv_record.data)
    facts = FactBase(cv, profile.evidence_text(), profile.work_authorized_countries,
                     profile.needs_sponsorship_countries)
    return cv, facts


def apply_cv_roles(prefs: JobPreferences, cv: CVData | None) -> JobPreferences:
    """Add roles suggested from the CV (unless the user switched them off or removed them)."""
    from backend.jobs.role_suggest import suggest_roles
    from backend.utils.text import normalize_key

    if cv is None or not prefs.include_cv_roles:
        prefs.cv_roles = []
        return prefs
    excluded = {normalize_key(r) for r in prefs.excluded_cv_roles}
    yours = {normalize_key(r) for r in prefs.target_roles}
    prefs.cv_roles = [r["title"] for r in suggest_roles(cv)
                      if normalize_key(r["title"]) not in excluded and normalize_key(r["title"]) not in yours]
    return prefs
