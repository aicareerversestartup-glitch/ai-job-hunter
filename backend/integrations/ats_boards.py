"""Company job boards hosted on public applicant-tracking-system APIs.

These are the best sources: the posting comes straight from the employer and the apply link is
the employer's own form. Add the companies you care about by their board identifier.
"""
from __future__ import annotations

import html

from backend.integrations.base import JobSourceClient, SearchQuery, SourceError
from backend.jobs.normalizer import NormalizedJob, build_job


class GreenhouseSource(JobSourceClient):
    kind = "greenhouse"
    display_name = "Greenhouse"
    needs_identifier = True
    identifier_help = "Board token from boards.greenhouse.io/<token> (e.g. 'airbnb')."

    def fetch(self, query: SearchQuery) -> list[NormalizedJob]:
        base = f"https://boards-api.greenhouse.io/v1/boards/{self.identifier}"
        try:
            company = self.get_json(base).get("name") or self.identifier
        except SourceError:
            company = self.identifier
        data = self.get_json(f"{base}/jobs", params={"content": "true"})

        def build(r: dict) -> NormalizedJob:
            offices = ", ".join(o.get("name", "") for o in r.get("offices") or [] if o.get("name"))
            return build_job(
                source=self.kind, source_job_id=r["id"], url=r.get("absolute_url", ""), title=r.get("title", ""),
                company=company, location=(r.get("location") or {}).get("name", "") or offices,
                description_html=html.unescape(r.get("content") or ""), posted_at=r.get("updated_at"),
                department=", ".join(d.get("name", "") for d in r.get("departments") or []),
                raw={"id": r.get("id"), "internal_job_id": r.get("internal_job_id"), "board": self.identifier},
            )
        return [j for j in (self.safe_build(build, r) for r in data.get("jobs", [])) if j]


class LeverSource(JobSourceClient):
    kind = "lever"
    display_name = "Lever"
    needs_identifier = True
    identifier_help = "Company slug from jobs.lever.co/<slug>. Prefix with 'eu:' for EU-hosted boards."

    def fetch(self, query: SearchQuery) -> list[NormalizedJob]:
        slug, host = self.identifier, "https://api.lever.co"
        if slug.startswith("eu:"):
            slug, host = slug[3:], "https://api.eu.lever.co"
        data = self.get_json(f"{host}/v0/postings/{slug}", params={"mode": "json"})

        def build(r: dict) -> NormalizedJob:
            cats = r.get("categories") or {}
            sections = [r.get("descriptionPlain") or ""]
            for block in r.get("lists") or []:
                sections.append(f"{block.get('text', '')}\n{block.get('content', '')}")
            sections.append(r.get("additionalPlain") or "")
            from backend.utils.text import strip_html
            text = "\n\n".join(strip_html(s) if "<" in s else s for s in sections if s)
            salary = r.get("salaryRange") or {}
            return build_job(
                source=self.kind, source_job_id=r["id"], url=r.get("hostedUrl", ""), apply_url=r.get("applyUrl", ""),
                title=r.get("text", ""), company=slug.replace("-", " ").title(), location=cats.get("location", ""),
                description_text=text, posted_at=r.get("createdAt"), employment_hint=cats.get("commitment", ""),
                remote_hint=r.get("workplaceType", ""), department=cats.get("team", ""),
                salary_min=salary.get("min"), salary_max=salary.get("max"), salary_currency=salary.get("currency", ""),
                salary_period=(salary.get("interval") or "").replace("per-", ""),
                raw={"id": r.get("id"), "slug": slug},
            )
        records = data if isinstance(data, list) else []
        return [j for j in (self.safe_build(build, r) for r in records) if j]


class AshbySource(JobSourceClient):
    kind = "ashby"
    display_name = "Ashby"
    needs_identifier = True
    identifier_help = "Job board name from jobs.ashbyhq.com/<name>."

    def fetch(self, query: SearchQuery) -> list[NormalizedJob]:
        data = self.get_json(f"https://api.ashbyhq.com/posting-api/job-board/{self.identifier}",
                             params={"includeCompensation": "true"})

        def build(r: dict) -> NormalizedJob:
            comp = (r.get("compensation") or {}).get("summaryComponents") or []
            salary = next((c for c in comp if c.get("compensationType") == "Salary"), {})
            remote = "remote" if r.get("isRemote") else (r.get("workplaceType") or "")
            return build_job(
                source=self.kind, source_job_id=r["id"], url=r.get("jobUrl", ""), apply_url=r.get("applyUrl", ""),
                title=r.get("title", ""), company=self.identifier.replace("-", " ").title(),
                location=r.get("location", ""), description_html=r.get("descriptionHtml") or "",
                description_text=r.get("descriptionPlain") or "", posted_at=r.get("publishedAt"),
                employment_hint=r.get("employmentType", ""), remote_hint=remote,
                department=r.get("department", "") or r.get("team", ""),
                salary_min=salary.get("minValue"), salary_max=salary.get("maxValue"),
                salary_currency=salary.get("currencyCode", ""), salary_period=(salary.get("interval") or "").lower(),
                raw={"id": r.get("id"), "board": self.identifier},
            )
        return [j for j in (self.safe_build(build, r) for r in data.get("jobs", [])) if j]


class WorkableSource(JobSourceClient):
    kind = "workable"
    display_name = "Workable"
    needs_identifier = True
    identifier_help = "Account subdomain from apply.workable.com/<subdomain>."

    def fetch(self, query: SearchQuery) -> list[NormalizedJob]:
        data = self.get_json(f"https://apply.workable.com/api/v1/widget/accounts/{self.identifier}",
                             params={"details": "true"})
        company = data.get("name") or self.identifier

        def build(r: dict) -> NormalizedJob:
            location = ", ".join(p for p in (r.get("city"), r.get("state"), r.get("country")) if p)
            return build_job(
                source=self.kind, source_job_id=r.get("shortcode") or r.get("id"), url=r.get("url", ""),
                apply_url=r.get("application_url", ""), title=r.get("title", ""), company=company,
                location=location, description_html=r.get("description") or "", posted_at=r.get("published_on"),
                employment_hint=r.get("employment_type", ""), remote_hint="remote" if r.get("telecommuting") else "",
                department=r.get("department", ""), raw={"shortcode": r.get("shortcode"), "account": self.identifier},
            )
        return [j for j in (self.safe_build(build, r) for r in data.get("jobs", [])) if j]
