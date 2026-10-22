"""Common interface for job sources.

Only official/public APIs and feeds are used. Sources that forbid automated access in their
terms (e.g. LinkedIn, Indeed, Naukri, Glassdoor) are intentionally not implemented; jobs from those
sites can be added manually by URL/paste in the UI.
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from backend.jobs.normalizer import NormalizedJob

log = logging.getLogger(__name__)


class SourceError(RuntimeError):
    pass


@dataclass
class SearchQuery:
    keywords: list[str] = field(default_factory=list)  # target roles
    countries: list[str] = field(default_factory=list)
    cities: list[str] = field(default_factory=list)
    remote_only: bool = False
    max_results: int = 200


class JobSourceClient(ABC):
    kind: str = "base"
    display_name: str = "Base"
    needs_identifier: bool = False  # True for company-board sources (Greenhouse token, Lever slug, …)
    identifier_help: str = ""
    terms_note: str = ""

    def __init__(self, identifier: str = "", *, user_agent: str = "AIJobHunter/1.0", timeout: float = 25.0,
                 credentials: dict | None = None):
        self.identifier = identifier.strip()
        self.user_agent = user_agent
        self.timeout = timeout
        self.credentials = credentials or {}

    @abstractmethod
    def fetch(self, query: SearchQuery) -> list[NormalizedJob]:
        """Return normalized postings. Must not raise for individual bad records."""

    # -- HTTP --------------------------------------------------------------------------------
    def get_json(self, url: str, params: dict | None = None, attempts: int = 3):
        return self._get(url, params, attempts).json()

    def get_text(self, url: str, params: dict | None = None, attempts: int = 3) -> str:
        return self._get(url, params, attempts).text

    def _get(self, url: str, params: dict | None, attempts: int):
        import httpx

        last = ""
        for attempt in range(attempts):
            try:
                response = httpx.get(url, params=params, timeout=self.timeout, follow_redirects=True,
                                     headers={"User-Agent": self.user_agent, "Accept": "application/json, */*"})
            except httpx.HTTPError as exc:
                last = str(exc)
            else:
                if response.status_code == 404:
                    raise SourceError(f"{self.display_name}: not found ({url}). Check the identifier.")
                if response.status_code in (401, 403):
                    raise SourceError(f"{self.display_name}: access denied (HTTP {response.status_code}).")
                if response.status_code < 300:
                    return response
                last = f"HTTP {response.status_code}"
                if response.status_code not in (429, 500, 502, 503, 504):
                    break
                retry_after = response.headers.get("Retry-After", "")
                if retry_after.isdigit():
                    time.sleep(min(int(retry_after), 30))
                    continue
            time.sleep(2 ** attempt)
        raise SourceError(f"{self.display_name}: request failed ({last}).")

    @staticmethod
    def safe_build(builder, record) -> NormalizedJob | None:
        try:
            return builder(record)
        except Exception as exc:  # one malformed posting must not break the whole run
            log.debug("Skipping malformed record: %s", exc)
            return None
