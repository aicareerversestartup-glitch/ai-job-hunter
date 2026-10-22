"""Registry of available job sources."""
from __future__ import annotations

from backend.config import get_settings
from backend.integrations.aggregators import AdzunaSource, ArbeitnowSource, RemotiveSource, RSSSource
from backend.integrations.ats_boards import AshbySource, GreenhouseSource, LeverSource, WorkableSource
from backend.integrations.base import JobSourceClient, SourceError
from backend.integrations.companies import CompanySearchSource, SmartRecruitersSource

SOURCE_CLASSES: dict[str, type[JobSourceClient]] = {
    cls.kind: cls for cls in (GreenhouseSource, LeverSource, AshbySource, WorkableSource, SmartRecruitersSource,
                              CompanySearchSource, RemotiveSource, ArbeitnowSource, AdzunaSource, RSSSource)
}


def create_client(kind: str, identifier: str = "") -> JobSourceClient:
    cls = SOURCE_CLASSES.get(kind)
    if cls is None:
        raise SourceError(f"Unknown source type {kind!r}.")
    if cls.needs_identifier and not identifier:
        raise SourceError(f"{cls.display_name} needs an identifier: {cls.identifier_help}")
    settings = get_settings()
    credentials = {}
    if kind == "adzuna":
        credentials = {"app_id": settings.adzuna_app_id, "app_key": settings.adzuna_app_key}
    elif kind == "company_search":
        credentials = {"adzuna_app_id": settings.adzuna_app_id, "adzuna_app_key": settings.adzuna_app_key,
                       "jooble_key": settings.jooble_api_key}
    return cls(identifier, user_agent=settings.http_user_agent, credentials=credentials)


def describe_sources() -> list[dict]:
    return [{"kind": c.kind, "name": c.display_name, "needs_identifier": c.needs_identifier,
             "identifier_help": c.identifier_help, "terms_note": c.terms_note} for c in SOURCE_CLASSES.values()]
