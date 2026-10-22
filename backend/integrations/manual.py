"""Add a job manually: from pasted text, or from a single public job-page URL the user supplies.

For a URL we read schema.org ``JobPosting`` JSON-LD, which most career sites publish for search
engines. Sites whose terms prohibit automated access are not fetched; the user pastes the text.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from backend.jobs.normalizer import NormalizedJob, build_job
from backend.utils.text import sha256_text, strip_html

NO_FETCH_DOMAINS = ("linkedin.com", "indeed.", "glassdoor.", "naukri.com", "monster.", "ziprecruiter.com",
                    "foundit.in", "shine.com", "timesjobs.com")


class ManualImportError(ValueError):
    pass


def fetch_allowed(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return not any(d in host for d in NO_FETCH_DOMAINS)


def job_from_text(*, title: str, company: str, description: str, url: str = "", location: str = "",
                  apply_url: str = "") -> NormalizedJob:
    if not title.strip() or not description.strip():
        raise ManualImportError("Title and description are required.")
    return build_job(source="manual", source_job_id=sha256_text(f"{company}|{title}|{url or description[:200]}")[:24],
                     url=url, apply_url=apply_url or url, title=title, company=company, location=location,
                     description_text=description)


def job_from_html(page_html: str, url: str) -> NormalizedJob:
    for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page_html, re.S | re.I):
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        for item in _walk(data):
            if isinstance(item, dict) and _is_type(item, "JobPosting"):
                return _from_jobposting(item, url)
    title = re.search(r"<title[^>]*>(.*?)</title>", page_html, re.S | re.I)
    body = re.search(r"<body[^>]*>(.*)</body>", page_html, re.S | re.I)
    text = strip_html(re.sub(r"<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ",
                             body.group(1) if body else page_html, flags=re.S | re.I))
    if not title or len(text) < 200:
        raise ManualImportError("Could not find a job description on that page. Paste the text instead.")
    return job_from_text(title=strip_html(title.group(1)), company=urlparse(url).hostname or "",
                         description=text[:20000], url=url)


def _walk(node):
    if isinstance(node, list):
        for n in node:
            yield from _walk(n)
    elif isinstance(node, dict):
        yield node
        if "@graph" in node:
            yield from _walk(node["@graph"])


def _is_type(item: dict, name: str) -> bool:
    t = item.get("@type")
    return t == name or (isinstance(t, list) and name in t)


def _from_jobposting(item: dict, url: str) -> NormalizedJob:
    org = item.get("hiringOrganization") or {}
    company = org.get("name", "") if isinstance(org, dict) else str(org)
    locations = item.get("jobLocation") or []
    if isinstance(locations, dict):
        locations = [locations]
    loc_parts = []
    for loc in locations:
        addr = (loc or {}).get("address") or {}
        if isinstance(addr, dict):
            loc_parts.append(", ".join(p for p in (addr.get("addressLocality"), addr.get("addressRegion"),
                                                   _country(addr.get("addressCountry"))) if p))
    salary = item.get("baseSalary") or {}
    value = salary.get("value") if isinstance(salary, dict) else {}
    value = value if isinstance(value, dict) else {}
    remote = "remote" if str(item.get("jobLocationType", "")).upper() == "TELECOMMUTE" else ""
    domain = urlparse(org.get("sameAs", "") if isinstance(org, dict) else "").hostname or ""
    return build_job(
        source="manual", source_job_id=str(item.get("identifier", {}).get("value") if isinstance(
            item.get("identifier"), dict) else sha256_text(url)[:24]),
        url=url, apply_url=item.get("url") or url, title=item.get("title", ""), company=company,
        location="; ".join(p for p in loc_parts if p), description_html=item.get("description", ""),
        posted_at=item.get("datePosted"), employment_hint=str(item.get("employmentType", "")), remote_hint=remote,
        salary_min=value.get("minValue"), salary_max=value.get("maxValue"),
        salary_currency=salary.get("currency", "") if isinstance(salary, dict) else "",
        salary_period=str(value.get("unitText", "")).lower(), company_domain=domain.replace("www.", ""),
        raw={"jsonld": True},
    )


def _country(value) -> str:
    if isinstance(value, dict):
        return value.get("name", "")
    return value or ""
