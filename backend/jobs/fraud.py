"""Job quality and fraud screening. Rules-based and explainable: every point of risk has a reason."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse

from backend.jobs.normalizer import NormalizedJob

DIRECT_ATS_SOURCES = {"greenhouse", "lever", "ashby", "workable", "smartrecruiters"}
FREE_EMAIL_DOMAINS = ("gmail.com", "yahoo.", "hotmail.", "outlook.com", "rediffmail.com", "proton.me", "aol.com")

RULES: list[tuple[str, int, str, str]] = [
    # (code, risk points, regex, explanation)
    ("ASKS_FOR_PAYMENT", 45,
     r"\b(registration|application|processing|training|joining|security|onboarding|kit|visa)\s+(fee|fees|charge|deposit)"
     r"|\bpay (a|the)?\s*(small )?(fee|deposit)|\brefundable deposit",
     "Asks candidates to pay money. Legitimate employers never charge applicants."),
    ("SENSITIVE_DATA_REQUEST", 35,
     r"\b(bank account|account number|ssn|social security|aadhaa?r|pan card|passport (copy|number)|credit card|otp)\b",
     "Requests sensitive personal or financial details up front."),
    ("OFF_PLATFORM_CONTACT", 25, r"\b(whats\s?app|telegram|signal app|wechat)\b|\btext (us|me) (at|on)\b",
     "Asks you to move the conversation to a messaging app."),
    ("MONEY_MULE_PATTERN", 50,
     r"\b(reshipp?ing|package forwarding|parcel forwarding|money transfer agent|payment processing agent|"
     r"cash(ing)? (a )?checks?|receive funds|crypto(currency)? (wallet|investment))\b",
     "Matches money-mule or reshipping scam patterns."),
    ("TOO_GOOD_TO_BE_TRUE", 25,
     r"\b(earn|make)\s+(up to\s+)?[$€£₹]?\s?\d[\d,]*\s*(k\s*)?(per|a|/)\s*(day|week)\b"
     r"|\bno (experience|interview) (needed|required)\b.*\b(high|huge|unlimited) (pay|income|earnings)"
     r"|\bunlimited (earning|income)\b|\bget rich\b",
     "Unrealistic pay claims."),
    ("MLM_PATTERN", 30, r"\b(be your own boss|recruit (others|friends)|network marketing|downline|multi-level)\b",
     "Looks like multi-level marketing rather than employment."),
    ("PRESSURE_TACTICS", 10, r"\b(limited seats|hurry|apply immediately|offer valid today|only today|act now)\b",
     "Uses pressure tactics."),
    ("NO_INTERVIEW", 20, r"\b(no interview|without (an )?interview|instant (hiring|selection|offer))\b",
     "Promises hiring without an interview."),
]


@dataclass
class QualityReport:
    risk_score: int = 0  # 0..100, higher is riskier
    quality_score: int = 100  # 0..100, higher is better
    flags: list[dict] = field(default_factory=list)

    @property
    def risk_level(self) -> str:
        return "high" if self.risk_score >= 50 else "medium" if self.risk_score >= 20 else "low"

    def flag(self, code: str, points: int, message: str, *, quality_only: bool = False) -> None:
        self.flags.append({"code": code, "points": points, "message": message,
                           "kind": "quality" if quality_only else "fraud"})
        if quality_only:
            self.quality_score = max(0, self.quality_score - points)
        else:
            self.risk_score = min(100, self.risk_score + points)
            self.quality_score = max(0, self.quality_score - points // 2)

    def as_dict(self) -> dict:
        return {"risk_score": self.risk_score, "risk_level": self.risk_level,
                "quality_score": self.quality_score, "flags": self.flags}


def assess_job(job: NormalizedJob, now: datetime | None = None) -> QualityReport:
    now = now or datetime.now(timezone.utc)
    report = QualityReport()
    text = f"{job.title}\n{job.description_text}"
    lowered = text.lower()

    for code, points, pattern, message in RULES:
        if re.search(pattern, lowered, re.IGNORECASE | re.DOTALL):
            report.flag(code, points, message)

    emails = re.findall(r"[\w.+-]+@([\w-]+\.[\w.-]+)", lowered)
    if any(any(free in domain for free in FREE_EMAIL_DOMAINS) for domain in emails):
        report.flag("FREE_EMAIL_CONTACT", 20, "Recruiter uses a free email address instead of a company domain.")

    if not job.company.strip() or job.company.lower() in {"confidential", "company", "n/a", "hiring company"}:
        report.flag("NO_COMPANY", 15, "Employer is not named.")

    if job.source not in DIRECT_ATS_SOURCES and job.company_domain and job.apply_url:
        host = urlparse(job.apply_url).hostname or ""
        if host and job.company_domain not in host and not _known_ats_host(host):
            report.flag("APPLY_DOMAIN_MISMATCH", 15, f"Apply link goes to {host}, not the company's site.")

    # Quality-only signals: they lower the ranking but are not evidence of fraud.
    if len(job.description_text) < 300:
        report.flag("THIN_DESCRIPTION", 25, "Description is very short; requirements may be unclear.", quality_only=True)
    if job.posted_at and (now - job.posted_at).days > 60:
        report.flag("STALE", 20, f"Posted {(now - job.posted_at).days} days ago; it may be filled.", quality_only=True)
    letters = [c for c in job.title if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.8 and len(letters) > 8:
        report.flag("SHOUTY_TITLE", 10, "Title is written in capitals.", quality_only=True)
    if text.count("!") >= 5:
        report.flag("EXCESSIVE_EXCLAMATION", 10, "Unusually many exclamation marks.", quality_only=True)

    if job.source in DIRECT_ATS_SOURCES:
        # Posted on the employer's own applicant tracking system: much lower prior risk.
        report.risk_score = max(0, report.risk_score - 10)
    return report


def _known_ats_host(host: str) -> bool:
    return any(h in host for h in ("greenhouse.io", "lever.co", "ashbyhq.com", "workable.com", "myworkdayjobs.com",
                                   "smartrecruiters.com", "icims.com", "taleo.net", "successfactors", "bamboohr.com",
                                   "recruitee.com", "personio", "jobvite.com", "breezy.hr"))
