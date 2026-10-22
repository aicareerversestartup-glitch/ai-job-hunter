"""Keyword-search sources: public job APIs and RSS/Atom feeds."""
from __future__ import annotations

import xml.etree.ElementTree as ET

from backend.integrations.base import JobSourceClient, SearchQuery, SourceError
from backend.jobs.normalizer import NormalizedJob, build_job
from backend.utils.text import sha256_text, strip_html


class RemotiveSource(JobSourceClient):
    kind = "remotive"
    display_name = "Remotive (remote jobs)"
    terms_note = "Remotive asks API users to link back to the posting and to limit polling (a few times a day)."

    def fetch(self, query: SearchQuery) -> list[NormalizedJob]:
        jobs: list[NormalizedJob] = []
        seen: set[str] = set()
        for keyword in (query.keywords or [""])[:5]:
            data = self.get_json("https://remotive.com/api/remote-jobs", params={"search": keyword, "limit": 100})
            for r in data.get("jobs", []):
                if str(r.get("id")) in seen:
                    continue
                seen.add(str(r.get("id")))
                job = self.safe_build(lambda x: build_job(
                    source=self.kind, source_job_id=x["id"], url=x.get("url", ""), title=x.get("title", ""),
                    company=x.get("company_name", ""), location=x.get("candidate_required_location", "") or "Remote",
                    description_html=x.get("description") or "", posted_at=x.get("publication_date"),
                    employment_hint=x.get("job_type", ""), remote_hint="remote", department=x.get("category", ""),
                    raw={"salary_text": x.get("salary", ""), "tags": x.get("tags", [])},
                ), r)
                if job:
                    jobs.append(job)
        return jobs[: query.max_results]


class ArbeitnowSource(JobSourceClient):
    kind = "arbeitnow"
    display_name = "Arbeitnow (Europe)"

    def fetch(self, query: SearchQuery) -> list[NormalizedJob]:
        jobs: list[NormalizedJob] = []
        for page in range(1, 4):
            data = self.get_json("https://www.arbeitnow.com/api/job-board-api", params={"page": page})
            records = data.get("data", [])
            if not records:
                break
            for r in records:
                job = self.safe_build(lambda x: build_job(
                    source=self.kind, source_job_id=x["slug"], url=x.get("url", ""), title=x.get("title", ""),
                    company=x.get("company_name", ""), location=x.get("location", ""),
                    description_html=x.get("description") or "", posted_at=x.get("created_at"),
                    employment_hint=" ".join(x.get("job_types") or []),
                    remote_hint="remote" if x.get("remote") else "", raw={"tags": x.get("tags", [])},
                ), r)
                if job:
                    jobs.append(job)
            if not (data.get("links") or {}).get("next"):
                break
        return jobs[: query.max_results * 3]


ADZUNA_COUNTRIES = {"United Kingdom": "gb", "United States": "us", "India": "in", "Germany": "de", "Canada": "ca",
                    "Australia": "au", "Netherlands": "nl", "France": "fr", "Singapore": "sg", "New Zealand": "nz",
                    "South Africa": "za", "Austria": "at", "Brazil": "br", "Switzerland": "ch", "Spain": "es",
                    "Italy": "it", "Mexico": "mx", "Poland": "pl", "Belgium": "be"}


class AdzunaSource(JobSourceClient):
    kind = "adzuna"
    display_name = "Adzuna"
    terms_note = "Requires a free Adzuna developer key (ADZUNA_APP_ID / ADZUNA_APP_KEY). Descriptions are snippets."

    def fetch(self, query: SearchQuery) -> list[NormalizedJob]:
        app_id = self.credentials.get("app_id")
        app_key = self.credentials.get("app_key")
        if not app_id or not app_key:
            raise SourceError("Adzuna needs ADZUNA_APP_ID and ADZUNA_APP_KEY in the environment.")
        countries = [ADZUNA_COUNTRIES[c] for c in query.countries if c in ADZUNA_COUNTRIES] or ["in"]
        jobs: list[NormalizedJob] = []
        for code in countries[:4]:
            for keyword in (query.keywords or [""])[:5]:
                data = self.get_json(f"https://api.adzuna.com/v1/api/jobs/{code}/search/1", params={
                    "app_id": app_id, "app_key": app_key, "what": keyword, "results_per_page": 50,
                    "content-type": "application/json", "max_days_old": 30})
                for r in data.get("results", []):
                    job = self.safe_build(lambda x: build_job(
                        source=self.kind, source_job_id=x["id"], url=x.get("redirect_url", ""),
                        title=strip_html(x.get("title", "")), company=(x.get("company") or {}).get("display_name", ""),
                        location=(x.get("location") or {}).get("display_name", ""),
                        description_html=x.get("description") or "", posted_at=x.get("created"),
                        employment_hint=" ".join(filter(None, [x.get("contract_time"), x.get("contract_type")])),
                        salary_min=x.get("salary_min"), salary_max=x.get("salary_max"), salary_period="year",
                        raw={"category": (x.get("category") or {}).get("label", ""), "country": code},
                    ), r)
                    if job:
                        jobs.append(job)
        return jobs


class RSSSource(JobSourceClient):
    kind = "rss"
    display_name = "RSS / Atom feed"
    needs_identifier = True
    identifier_help = "Full URL of a job feed (many company career pages and job sites publish one)."

    def fetch(self, query: SearchQuery) -> list[NormalizedJob]:
        from backend.security.guards import validate_public_url

        url = validate_public_url(self.identifier)
        try:
            root = ET.fromstring(self.get_text(url).encode("utf-8"))
        except ET.ParseError as exc:
            raise SourceError(f"Feed is not valid XML: {exc}") from exc
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item") or root.findall(".//atom:entry", ns)
        jobs: list[NormalizedJob] = []
        for item in items:
            def text(tag: str) -> str:
                el = item.find(tag) if not tag.startswith("atom:") else item.find(tag, ns)
                return (el.text or "").strip() if el is not None and el.text else ""

            link = text("link")
            if not link:
                link_el = item.find("atom:link", ns)
                link = link_el.get("href", "") if link_el is not None else ""
            title = text("title") or text("atom:title")
            if not link or not title:
                continue
            company, _, role = title.partition(":") if ":" in title else ("", "", title)
            job = self.safe_build(lambda _: build_job(
                source=self.kind, source_job_id=text("guid") or text("atom:id") or sha256_text(link)[:24], url=link,
                title=(role or title).strip(), company=(company or self._feed_title(root)).strip(),
                location=text("location") or text("region"),
                description_html=text("description") or text("atom:summary") or text("atom:content"),
                posted_at=text("pubDate") or text("atom:updated"), raw={"feed": url},
            ), item)
            if job:
                jobs.append(job)
        return jobs

    @staticmethod
    def _feed_title(root) -> str:
        el = root.find("./channel/title")
        return (el.text or "").strip() if el is not None and el.text else ""
