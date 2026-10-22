"""Company + country search.

For each target company we try, in order:
1. Its public applicant-tracking board (Greenhouse, Lever, Ashby, Workable, SmartRecruiters), detected
   automatically from the company name. Best data: full description, direct apply link.
2. Official job-search APIs filtered to that company and country: Adzuna (needs a free key) and
   Jooble (needs a free key, covers the Gulf and more countries).
3. The company's official careers page (from ``data/companies.json``), shown in the UI. Large
   employers often run their own portals without a public API; paste a job link from there and
   it is imported from the page's structured data.
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

from backend.integrations.aggregators import ADZUNA_COUNTRIES
from backend.integrations.base import JobSourceClient, SearchQuery, SourceError
from backend.jobs.normalizer import NormalizedJob, build_job, normalize_company
from backend.utils.text import sha256_text, strip_html

log = logging.getLogger(__name__)
REGISTRY_PATH = Path(__file__).resolve().parents[2] / "data" / "companies.json"


@lru_cache(maxsize=1)
def load_registry() -> list[dict]:
    if not REGISTRY_PATH.exists():
        return []
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8")).get("companies", [])


def registry_entry(name: str) -> dict | None:
    key = normalize_company(name)
    for entry in load_registry():
        names = [entry["name"], *entry.get("aliases", [])]
        if any(normalize_company(n) == key for n in names):
            return entry
    return None


def company_names(name: str) -> list[str]:
    entry = registry_entry(name)
    names = [name] + ([entry["name"], *entry.get("aliases", [])] if entry else [])
    return list(dict.fromkeys(n for n in names if n))


def company_matches(job_company: str, names: list[str]) -> bool:
    """'DHL Supply Chain (UK) Limited' matches 'DHL'; 'Amazonia Foods' does not match 'Amazon'."""
    job_key = f" {normalize_company(job_company)} "
    for name in names:
        key = normalize_company(name)
        if key and f" {key} " in job_key:
            return True
    return False


def slug_candidates(name: str) -> list[str]:
    base = normalize_company(name)
    words = base.split()
    if not words:
        return []
    candidates = ["".join(words), "-".join(words), words[0]]
    raw = re.sub(r"[^a-z0-9]+", "", name.lower())
    candidates.append(raw)
    return [c for c in dict.fromkeys(candidates) if len(c) >= 2]


class SmartRecruitersSource(JobSourceClient):
    kind = "smartrecruiters"
    display_name = "SmartRecruiters"
    needs_identifier = True
    identifier_help = "Company identifier from jobs.smartrecruiters.com/<identifier>."
    MAX_DETAILS = 40

    def fetch(self, query: SearchQuery) -> list[NormalizedJob]:
        from backend.jobs.matcher import JobPreferences, quick_relevance

        base = f"https://api.smartrecruiters.com/v1/companies/{self.identifier}/postings"
        data = self.get_json(base, params={"limit": 100})
        postings = data.get("content", [])
        prefs = JobPreferences(target_roles=query.keywords)
        jobs: list[NormalizedJob] = []
        for p in postings:
            loc = p.get("location") or {}
            location = ", ".join(x for x in (loc.get("city"), loc.get("region"), loc.get("country", "").upper()) if x)
            stub = build_job(source=self.kind, source_job_id=p.get("id", ""), url="", title=p.get("name", ""),
                             company=(p.get("company") or {}).get("name", self.identifier), location=location)
            if query.keywords and quick_relevance(stub, prefs) < 0.34:
                continue
            if len(jobs) >= self.MAX_DETAILS:
                break
            try:
                detail = self.get_json(f"{base}/{p['id']}")
            except SourceError:
                continue
            sections = (detail.get("jobAd") or {}).get("sections") or {}
            text = "\n\n".join(f"{s.get('title', '')}\n{strip_html(s.get('text', ''))}"
                               for s in sections.values() if isinstance(s, dict) and s.get("text"))
            remote = "remote" if loc.get("remote") else ""
            jobs.append(build_job(
                source=self.kind, source_job_id=p["id"], url=detail.get("postingUrl") or "",
                apply_url=detail.get("applyUrl") or detail.get("postingUrl") or "", title=p.get("name", ""),
                company=(p.get("company") or {}).get("name", self.identifier), location=location,
                description_text=text, posted_at=p.get("releasedDate"),
                employment_hint=(p.get("typeOfEmployment") or {}).get("label", ""), remote_hint=remote,
                department=(p.get("department") or {}).get("label", ""), raw={"company_id": self.identifier},
            ))
        return jobs


class CompanySearchSource(JobSourceClient):
    """Finds one company's jobs in the chosen countries through official job-search APIs."""
    kind = "company_search"
    display_name = "Company search (Adzuna + Jooble)"
    needs_identifier = True
    identifier_help = "Company name, e.g. 'DHL Group'."
    terms_note = "Needs a free Adzuna key and/or a free Jooble key in .env. Descriptions from these APIs are short " \
                 "snippets; open the job to read the full description on the employer's site."

    def fetch(self, query: SearchQuery) -> list[NormalizedJob]:
        names = company_names(self.identifier)
        roles = query.keywords or (registry_entry(self.identifier) or {}).get("roles", [])[:3] or [""]
        countries = query.countries or (registry_entry(self.identifier) or {}).get("hubs", [])
        jobs: list[NormalizedJob] = []
        errors: list[str] = []
        used_any = False
        if self.credentials.get("adzuna_app_id") and self.credentials.get("adzuna_app_key"):
            used_any = True
            try:
                jobs += self._adzuna(names, roles, countries)
            except SourceError as exc:
                errors.append(str(exc))
        if self.credentials.get("jooble_key"):
            used_any = True
            try:
                jobs += self._jooble(names, roles, countries)
            except SourceError as exc:
                errors.append(str(exc))
        if not used_any:
            raise SourceError("Company search needs ADZUNA_APP_ID/ADZUNA_APP_KEY or JOOBLE_API_KEY in .env "
                              "(both are free). Until then, use the company's careers page link.")
        if errors and not jobs:
            raise SourceError("; ".join(errors))
        return [j for j in jobs if company_matches(j.company, names)]

    def _adzuna(self, names: list[str], roles: list[str], countries: list[str]) -> list[NormalizedJob]:
        codes = [(c, ADZUNA_COUNTRIES[c]) for c in countries if c in ADZUNA_COUNTRIES]
        out: list[NormalizedJob] = []
        short = normalize_company(names[0]).split()[0] if names else ""
        for country, code in codes[:6]:
            for role in roles[:4]:
                params = {"app_id": self.credentials["adzuna_app_id"], "app_key": self.credentials["adzuna_app_key"],
                          "results_per_page": 50, "content-type": "application/json", "max_days_old": 45,
                          "what": f"{short} {role}".strip()}
                data = self.get_json(f"https://api.adzuna.com/v1/api/jobs/{code}/search/1", params=params)
                for r in data.get("results", []):
                    job = self.safe_build(lambda x: build_job(
                        source="adzuna", source_job_id=x["id"], url=x.get("redirect_url", ""),
                        title=strip_html(x.get("title", "")), company=(x.get("company") or {}).get("display_name", ""),
                        location=(x.get("location") or {}).get("display_name", "") or country,
                        description_html=x.get("description") or "", posted_at=x.get("created"),
                        employment_hint=" ".join(filter(None, [x.get("contract_time"), x.get("contract_type")])),
                        salary_min=x.get("salary_min"), salary_max=x.get("salary_max"), salary_period="year",
                        raw={"country": code, "snippet_only": True},
                    ), r)
                    if job:
                        if not job.country:
                            job.country = country
                        out.append(job)
        return out

    def _jooble(self, names: list[str], roles: list[str], countries: list[str]) -> list[NormalizedJob]:
        import httpx

        out: list[NormalizedJob] = []
        short = names[0] if names else ""
        for country in (countries or [""])[:6]:
            for role in roles[:4]:
                try:
                    response = httpx.post(f"https://jooble.org/api/{self.credentials['jooble_key']}",
                                          json={"keywords": f"{role} {short}".strip(), "location": country, "page": 1},
                                          timeout=self.timeout, headers={"User-Agent": self.user_agent})
                except httpx.HTTPError as exc:
                    raise SourceError(f"Jooble: {exc}") from exc
                if response.status_code in (401, 403):
                    raise SourceError("Jooble: the API key was rejected.")
                if response.status_code >= 300:
                    raise SourceError(f"Jooble: HTTP {response.status_code}")
                for r in response.json().get("jobs", []):
                    job = self.safe_build(lambda x: build_job(
                        source="jooble", source_job_id=str(x.get("id") or sha256_text(x.get("link", ""))[:24]),
                        url=x.get("link", ""), title=strip_html(x.get("title", "")), company=x.get("company", ""),
                        location=x.get("location", "") or country, description_html=x.get("snippet", ""),
                        posted_at=x.get("updated"), employment_hint=x.get("type", ""),
                        raw={"salary_text": x.get("salary", ""), "via": x.get("source", ""), "snippet_only": True},
                    ), r)
                    if job:
                        if not job.country:
                            job.country = country
                        out.append(job)
        return out


def detect_company_boards(name: str, timeout: float = 8.0) -> list[dict]:
    """Probe public ATS APIs for boards belonging to this company. Read-only, a few requests."""
    import httpx

    names = company_names(name)
    found: list[dict] = []
    probes = {
        "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}",
        "lever": "https://api.lever.co/v0/postings/{slug}?mode=json&limit=1",
        "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
        "workable": "https://apply.workable.com/api/v1/widget/accounts/{slug}",
        "smartrecruiters": "https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=1",
    }
    slugs = list(dict.fromkeys(s for n in names[:3] for s in slug_candidates(n)))[:6]
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        for kind, template in probes.items():
            for slug in slugs:
                try:
                    r = client.get(template.format(slug=slug))
                except httpx.HTTPError:
                    continue
                if r.status_code != 200:
                    continue
                try:
                    data = r.json()
                except ValueError:
                    continue
                count = _count(kind, data)
                board_name = _board_name(kind, data)
                # SmartRecruiters answers 200 with zero postings for unknown ids; require real postings
                # and, where the API tells us, a company name that matches.
                if count == 0 or (board_name and not company_matches(board_name, names)):
                    continue
                found.append({"kind": kind, "identifier": slug, "count": count, "board_name": board_name or slug})
                break
    return found


def _count(kind: str, data) -> int:
    if kind == "lever":
        return len(data) if isinstance(data, list) else 0
    if kind == "smartrecruiters":
        return int(data.get("totalFound", 0))
    if kind == "greenhouse":
        return 1 if data.get("name") else 0
    return len(data.get("jobs", []))


def _board_name(kind: str, data) -> str:
    if kind == "greenhouse":
        return data.get("name", "")
    if kind == "workable":
        return data.get("name", "")
    if kind == "smartrecruiters":
        content = data.get("content") or []
        return ((content[0].get("company") or {}).get("name", "")) if content else ""
    return ""
