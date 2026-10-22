"""Normalize raw postings from any source into one ``NormalizedJob`` shape."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from backend.utils.text import clean_whitespace, normalize_key, sha256_text, strip_html

REMOTE_TYPES = ("remote", "hybrid", "onsite", "unknown")
EMPLOYMENT_TYPES = ("full_time", "part_time", "contract", "internship", "temporary", "unknown")
SENIORITY_LEVELS = ("intern", "entry", "mid", "senior", "lead", "manager", "director", "executive", "unknown")

COUNTRY_ALIASES: dict[str, tuple[str, ...]] = {
    "India": ("india", "bengaluru", "bangalore", "mumbai", "delhi", "new delhi", "gurgaon", "gurugram", "noida",
              "pune", "hyderabad", "chennai", "kolkata", "ahmedabad", "lucknow", "jaipur", "kochi", "indore",
              "chandigarh", "coimbatore", "vadodara", "nagpur", "varanasi", "kanpur", "prayagraj"),
    "United States": ("united states", "usa", "u.s.", "us", "new york", "san francisco", "seattle", "austin",
                      "boston", "chicago", "los angeles", "denver", "atlanta"),
    "United Kingdom": ("united kingdom", "uk", "england", "scotland", "london", "manchester", "edinburgh", "bristol"),
    "Germany": ("germany", "deutschland", "berlin", "munich", "münchen", "hamburg", "frankfurt", "stuttgart", "cologne"),
    "Canada": ("canada", "toronto", "vancouver", "montreal", "ottawa", "calgary"),
    "Australia": ("australia", "sydney", "melbourne", "brisbane", "perth"),
    "United Arab Emirates": ("united arab emirates", "uae", "dubai", "abu dhabi"),
    "Singapore": ("singapore",), "Netherlands": ("netherlands", "amsterdam", "rotterdam", "eindhoven"),
    "Ireland": ("ireland", "dublin"), "France": ("france", "paris", "lyon"),
    "Japan": ("japan", "tokyo", "osaka"), "Saudi Arabia": ("saudi arabia", "riyadh", "jeddah"),
    "Qatar": ("qatar", "doha"), "Sweden": ("sweden", "stockholm"), "Poland": ("poland", "warsaw", "krakow"),
    "Spain": ("spain", "madrid", "barcelona"), "Switzerland": ("switzerland", "zurich", "geneva"),
    "New Zealand": ("new zealand", "auckland", "wellington"),
}


class NormalizedJob(BaseModel):
    source: str
    source_job_id: str
    url: str
    apply_url: str = ""
    title: str
    company: str
    location: str = ""
    country: str = ""
    remote_type: str = "unknown"
    employment_type: str = "unknown"
    seniority: str = "unknown"
    department: str = ""
    description_text: str = ""
    posted_at: datetime | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str = ""
    salary_period: str = ""  # year | month | hour
    company_domain: str = ""
    raw: dict = Field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        """Same company + same normalized title + same location ⇒ same job across sources."""
        return sha256_text("|".join([normalize_company(self.company), normalize_title(self.title),
                                     normalize_key(self.location)]))[:32]


def normalize_company(name: str) -> str:
    key = normalize_key(name)
    key = re.sub(r"\b(inc|incorporated|llc|ltd|limited|pvt|private|plc|gmbh|corp|corporation|co|company|"
                 r"technologies|technology|solutions|group|holdings|ag|sa|bv)\b", " ", key)
    return re.sub(r"\s+", " ", key).strip()


def normalize_title(title: str) -> str:
    key = normalize_key(title)
    key = re.sub(r"\b(sr)\b", "senior", key)
    key = re.sub(r"\b(jr)\b", "junior", key)
    key = re.sub(r"\b(engg|eng)\b", "engineer", key)
    key = re.sub(r"\b(i{1,3}|iv|[1-4])\b$", "", key)  # level suffixes
    key = re.sub(r"\(.*?\)", "", key)
    return re.sub(r"\s+", " ", key).strip()


def infer_remote_type(*texts: str) -> str:
    blob = " ".join(t for t in texts if t).lower()
    if re.search(r"\bhybrid\b", blob):
        return "hybrid"
    if re.search(r"\b(fully remote|100% remote|remote[- ]first|work from home|wfh|remote)\b", blob):
        if re.search(r"\b(not remote|no remote|on-?site only)\b", blob):
            return "onsite"
        return "remote"
    if re.search(r"\b(on-?site|in-?office|office-based)\b", blob):
        return "onsite"
    return "unknown"


def infer_employment_type(*texts: str) -> str:
    blob = " ".join(t for t in texts if t).lower()
    checks = (("internship", r"\b(intern|internship|trainee program)\b"),
              ("contract", r"\b(contract|contractor|freelance|fixed[- ]term|c2h)\b"),
              ("part_time", r"\b(part[-_ ]time)\b"), ("temporary", r"\b(temporary|seasonal)\b"),
              ("full_time", r"\b(full[-_ ]time|permanent|fte)\b"))
    for label, pattern in checks:
        if re.search(pattern, blob):
            return label
    return "unknown"


def infer_seniority(title: str) -> str:
    t = normalize_key(title)
    rules = (("intern", r"\b(intern|internship|apprentice|trainee)\b"),
             ("executive", r"\b(chief|cto|ceo|cfo|coo|vp|vice president|president)\b"),
             ("director", r"\b(director|head of)\b"), ("manager", r"\b(manager|mgr)\b"),
             ("lead", r"\b(lead|principal|staff|architect)\b"), ("senior", r"\b(senior|sr)\b"),
             ("entry", r"\b(junior|jr|entry|graduate|fresher|associate|i)\b"))
    for label, pattern in rules:
        if re.search(pattern, t):
            return label
    return "mid"


def infer_country(location: str) -> str:
    key = f" {normalize_key(location)} "
    if not key.strip():
        return ""
    for country, aliases in COUNTRY_ALIASES.items():
        for alias in aliases:
            if f" {normalize_key(alias)} " in key:
                return country
    return ""


def parse_datetime(value) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip().replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            parsed = datetime.fromisoformat(text) if fmt is None else datetime.strptime(text, fmt)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def build_job(*, source: str, source_job_id: str, url: str, title: str, company: str, location: str = "",
              description_html: str = "", description_text: str = "", apply_url: str = "",
              posted_at=None, employment_hint: str = "", remote_hint: str = "", department: str = "",
              salary_min: float | None = None, salary_max: float | None = None, salary_currency: str = "",
              salary_period: str = "", company_domain: str = "", raw: dict | None = None) -> NormalizedJob:
    """The single constructor every integration uses, so inference rules apply consistently."""
    text = clean_whitespace(description_text) if description_text else strip_html(description_html)
    title = clean_whitespace(title)
    location = clean_whitespace(location)
    return NormalizedJob(
        source=source, source_job_id=str(source_job_id), url=url, apply_url=apply_url or url,
        title=title, company=clean_whitespace(company), location=location,
        country=infer_country(location),
        remote_type=infer_remote_type(remote_hint, location, title, text[:1500]),
        employment_type=infer_employment_type(employment_hint, title, text[:3000]),
        seniority=infer_seniority(title), department=department, description_text=text,
        posted_at=parse_datetime(posted_at), salary_min=salary_min, salary_max=salary_max,
        salary_currency=salary_currency, salary_period=salary_period, company_domain=company_domain,
        raw=raw or {},
    )
