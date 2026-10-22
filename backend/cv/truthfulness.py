"""The Absolute Truthfulness Rule, enforced in code.

Every generated document (tailored CV, cover letter, application answer) is checked against a
``FactBase`` built only from the user's verified Master CV and the profile they entered. Anything
the guard cannot trace back to those sources is reported as a violation, and ``sanitize_cv``
removes or reverts it. The LLM is never trusted to police itself: this module is deterministic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.cv.schema import CVData, ExperienceItem
from backend.cv.structurer import DEGREE_RE
from backend.jobs.skills_taxonomy import canonical_skill, find_skills
from backend.utils.dates import total_experience_months
from backend.utils.text import contains_phrase, normalize_key, token_set

AUTHORIZATION_RE = re.compile(
    r"\b(authori[sz]ed to work|work authori[sz]ation|work permit|citizen(ship)?|permanent resident|green card|"
    r"visa|no sponsorship|without sponsorship|security clearance|right to work)\b",
    re.IGNORECASE,
)
SALARY_RE = re.compile(r"(?:[$€£₹]\s?\d[\d,.]*\s?(?:k|lpa|lakhs?|crore)?|\b\d[\d,.]*\s?(?:lpa|lakhs?|ctc|per annum)\b)",
                       re.IGNORECASE)
NUMBER_RE = re.compile(r"(?<![A-Za-z])\d+(?:[.,]\d+)?\s?%?")
YEARS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)", re.IGNORECASE)
BULLET_GROUNDING_MIN = 0.5  # share of a bullet's content words that must come from the source role


@dataclass
class Violation:
    code: str  # e.g. INVENTED_EMPLOYER, UNSUPPORTED_SKILL
    location: str  # where in the document, e.g. "experience[1].bullets[2]"
    message: str
    value: str = ""
    severity: str = "error"  # "error" blocks approval; "warning" needs the user's eyes

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class GuardReport:
    violations: list[Violation] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any(v.severity == "error" for v in self.violations)

    def add(self, *args, **kwargs) -> None:
        self.violations.append(Violation(*args, **kwargs))

    def as_dict(self) -> dict:
        return {"passed": self.passed, "violations": [v.as_dict() for v in self.violations]}


class FactBase:
    """Everything the user has verifiably stated. Built once per Master CV version."""

    def __init__(self, master: CVData, profile_text: str = "", authorized_countries: list[str] | None = None,
                 sponsorship_countries: list[str] | None = None):
        self.master = master
        self.authorized_countries = {normalize_key(c) for c in (authorized_countries or [])}
        self.sponsorship_countries = {normalize_key(c) for c in (sponsorship_countries or [])}
        self.profile_text = profile_text or ""
        self.evidence_text = master.all_text() + "\n" + self.profile_text
        self.evidence_lower = self.evidence_text.lower()
        self.roles = {self.role_key(e): e for e in master.experience}
        self.education = {(normalize_key(e.institution), normalize_key(e.degree)): e for e in master.education}
        self.certifications = {normalize_key(c) for c in master.certifications}
        self.projects = {normalize_key(p.name) for p in master.projects}
        self.languages = {normalize_key(l) for l in master.languages}
        self.skills = {normalize_key(canonical_skill(s)) for s in master.skills}
        self.skills |= {normalize_key(s) for s in master.skills}
        self.skills |= {normalize_key(s) for s in find_skills(self.evidence_text)}
        self.numbers = {_norm_number(n) for n in NUMBER_RE.findall(self.evidence_text)}
        months = total_experience_months([(e.start, e.end) for e in master.experience])
        self.total_years = months / 12
        for whole in range(0, int(self.total_years) + 1):
            self.numbers.add(str(whole))  # "N years of experience" is fine if N <= real total
        self.degrees = {normalize_key(m.group(0)) for m in DEGREE_RE.finditer(self.evidence_text)}

    @staticmethod
    def role_key(exp: ExperienceItem) -> tuple[str, str]:
        return normalize_key(exp.employer), normalize_key(exp.title)

    def has_skill(self, skill: str) -> bool:
        key = normalize_key(skill)
        if not key:
            return True
        if key in self.skills or normalize_key(canonical_skill(skill)) in self.skills:
            return True
        return contains_phrase(self.evidence_lower, skill.lower())

    def role_text(self, exp: ExperienceItem) -> str:
        source = self.roles.get(self.role_key(exp))
        if not source:
            return ""
        return "\n".join([source.title, source.employer, *source.bullets])


def _norm_number(value: str) -> str:
    return value.replace(",", "").replace(" ", "").rstrip("%").rstrip(".")


# --------------------------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------------------------

def check_cv(tailored: CVData, facts: FactBase) -> GuardReport:
    report = GuardReport()
    master = facts.master

    for attr in ("full_name", "email", "phone", "location"):
        if getattr(tailored.contact, attr) != getattr(master.contact, attr):
            report.add("CHANGED_CONTACT", f"contact.{attr}", "Contact details must match the Master CV.",
                       getattr(tailored.contact, attr))

    for i, exp in enumerate(tailored.experience):
        where = f"experience[{i}]"
        source = facts.roles.get(facts.role_key(exp))
        if source is None:
            known_employers = {normalize_key(e.employer) for e in master.experience}
            code = "INVENTED_JOB_TITLE" if normalize_key(exp.employer) in known_employers else "INVENTED_EMPLOYER"
            report.add(code, where, "This employer/title pair is not in the Master CV.", f"{exp.title} @ {exp.employer}")
            continue
        if (exp.employment_type or "") != (source.employment_type or ""):
            report.add("CHANGED_EMPLOYMENT_TYPE", where, "Contract/permanent status must match the Master CV.",
                       exp.employment_type or "permanent")
        if (exp.start, exp.end) != (source.start, source.end):
            report.add("CHANGED_DATES", where, "Employment dates must match the Master CV.", f"{exp.start} – {exp.end}")
        if exp.location and normalize_key(exp.location) != normalize_key(source.location):
            report.add("CHANGED_LOCATION", where, "Job location must match the Master CV.", exp.location)
        role_text = facts.role_text(exp)
        for j, bullet in enumerate(exp.bullets):
            _check_bullet(bullet, role_text, facts, report, f"{where}.bullets[{j}]")

    for i, edu in enumerate(tailored.education):
        if (normalize_key(edu.institution), normalize_key(edu.degree)) not in facts.education:
            report.add("INVENTED_EDUCATION", f"education[{i}]", "This education entry is not in the Master CV.",
                       f"{edu.degree} @ {edu.institution}")
    for i, cert in enumerate(tailored.certifications):
        if normalize_key(cert) not in facts.certifications:
            report.add("INVENTED_CERTIFICATION", f"certifications[{i}]", "Certification not in the Master CV.", cert)
    for i, skill in enumerate(tailored.skills):
        if not facts.has_skill(skill):
            report.add("UNSUPPORTED_SKILL", f"skills[{i}]", "Skill does not appear anywhere in the Master CV.", skill)
    for i, proj in enumerate(tailored.projects):
        if normalize_key(proj.name) not in facts.projects:
            report.add("INVENTED_PROJECT", f"projects[{i}]", "Project not in the Master CV.", proj.name)
        for tech in proj.technologies:
            if not facts.has_skill(tech):
                report.add("UNSUPPORTED_SKILL", f"projects[{i}].technologies", "Technology not in the Master CV.", tech)
    for i, lang in enumerate(tailored.languages):
        if normalize_key(lang) not in facts.languages:
            report.add("INVENTED_LANGUAGE", f"languages[{i}]", "Language not in the Master CV.", lang)

    for name, text in (("headline", tailored.headline), ("summary", tailored.summary)):
        report.violations += check_free_text(text, facts, location=name).violations
    return report


def _check_bullet(bullet: str, role_text: str, facts: FactBase, report: GuardReport, where: str) -> None:
    role_lower = role_text.lower()
    for skill in find_skills(bullet):
        if not any(contains_phrase(role_lower, alias) for alias in _aliases(skill)):
            report.add("MISATTRIBUTED_SKILL", where,
                       f"'{skill}' is not mentioned for this role in the Master CV.", skill)
    role_numbers = {_norm_number(n) for n in NUMBER_RE.findall(role_text)}
    for number in NUMBER_RE.findall(bullet):
        if _norm_number(number) not in role_numbers:
            report.add("INVENTED_METRIC", where, "This number does not appear in the source bullet points.", number)
    bullet_tokens = token_set(bullet)
    if bullet_tokens:
        overlap = len(bullet_tokens & token_set(role_text)) / len(bullet_tokens)
        if overlap < BULLET_GROUNDING_MIN:
            report.add("UNGROUNDED_BULLET", where,
                       "Bullet introduces content that is not in the Master CV for this role.", bullet,
                       severity="warning" if overlap >= BULLET_GROUNDING_MIN / 2 else "error")
    _check_sensitive_claims(bullet, facts, report, where)


def _aliases(skill: str) -> tuple[str, ...]:
    from backend.jobs.skills_taxonomy import skill_aliases

    return skill_aliases().get(skill, (skill.lower(),))


def _check_sensitive_claims(text: str, facts: FactBase, report: GuardReport, where: str) -> None:
    from backend.jobs.normalizer import infer_country

    for m in AUTHORIZATION_RE.finditer(text):
        window = text[max(0, m.start() - 60): m.end() + 60]
        country = normalize_key(infer_country(window))
        if country:
            sponsorship_claim = re.search(r"sponsor|visa", window, re.IGNORECASE)
            supported = country in facts.authorized_countries or (
                bool(sponsorship_claim) and country in facts.sponsorship_countries)
        else:
            supported = contains_phrase(facts.evidence_lower, m.group(0).lower())
        if not supported:
            report.add("UNSUPPORTED_AUTHORIZATION", where,
                       "Work authorization claims must come from your profile.", window.strip())
    for m in SALARY_RE.finditer(text):
        if m.group(0).strip() not in facts.evidence_text:
            report.add("UNSUPPORTED_SALARY", where, "Salary figures must come from your profile.", m.group(0))
    for m in DEGREE_RE.finditer(text):
        if normalize_key(m.group(0)) not in facts.degrees:
            report.add("INVENTED_DEGREE", where, "Degree not in the Master CV.", m.group(0))


def check_free_text(text: str, facts: FactBase, location: str = "text",
                    allowed_text: str = "") -> GuardReport:
    """Check prose (summary, cover letter, answers). ``allowed_text`` is quoted material such as
    the job title or company name, which may be mentioned without being a claim about the user."""
    report = GuardReport()
    if not text:
        return report
    allowed_lower = allowed_text.lower()
    for skill in find_skills(text):
        if facts.has_skill(skill):
            continue
        # Mentioning the employer's stack ("your team uses Kafka") is not a claim; describing
        # the user's own skill is. Without reliable parsing we flag it for review.
        mentioned_in_job = any(contains_phrase(allowed_lower, a) for a in _aliases(skill))
        report.add("UNSUPPORTED_SKILL", location,
                   f"'{skill}' is not in your Master CV. Make sure the text does not claim it.", skill,
                   severity="warning" if mentioned_in_job else "error")
    for m in YEARS_RE.finditer(text):
        claimed = float(m.group(1))
        if claimed > facts.total_years + 0.5 and m.group(0) not in facts.evidence_text:
            report.add("INFLATED_EXPERIENCE", location,
                       f"Claims {m.group(0)} but the Master CV shows about {facts.total_years:.1f} years.", m.group(0))
    for number in NUMBER_RE.findall(text):
        n = _norm_number(number)
        if n not in facts.numbers and n not in {_norm_number(x) for x in NUMBER_RE.findall(allowed_text)}:
            report.add("UNVERIFIED_NUMBER", location, "Number not found in your Master CV; check it.", number,
                       severity="warning")
    _check_sensitive_claims(text, facts, report, location)
    return report


# --------------------------------------------------------------------------------------------
# Repair
# --------------------------------------------------------------------------------------------

def sanitize_cv(tailored: CVData, facts: FactBase) -> tuple[CVData, GuardReport]:
    """Return a copy of ``tailored`` with every unverifiable element removed or reverted, plus the
    report of what was fixed. The result is guaranteed to pass ``check_cv`` errors-wise."""
    master = facts.master
    fixed = tailored.model_copy(deep=True)
    original_report = check_cv(tailored, facts)
    fixed.contact = master.contact.model_copy(deep=True)

    kept: list[ExperienceItem] = []
    for exp in fixed.experience:
        source = facts.roles.get(facts.role_key(exp))
        if source is None:
            continue
        exp.start, exp.end, exp.location = source.start, source.end, source.location
        exp.employment_type = source.employment_type
        exp.employer, exp.title = source.employer, source.title
        role_text = facts.role_text(exp)
        good: list[str] = []
        for bullet in exp.bullets:
            probe = GuardReport()
            _check_bullet(bullet, role_text, facts, probe, "probe")
            if probe.passed:
                good.append(bullet)
        exp.bullets = good or list(source.bullets)
        kept.append(exp)
    fixed.experience = kept or [e.model_copy(deep=True) for e in master.experience]

    fixed.education = [e for e in fixed.education
                       if (normalize_key(e.institution), normalize_key(e.degree)) in facts.education]
    fixed.certifications = [c for c in fixed.certifications if normalize_key(c) in facts.certifications]
    fixed.skills = [s for s in fixed.skills if facts.has_skill(s)]
    fixed.projects = [p for p in fixed.projects if normalize_key(p.name) in facts.projects]
    for proj in fixed.projects:
        proj.technologies = [t for t in proj.technologies if facts.has_skill(t)]
    fixed.languages = [l for l in fixed.languages if normalize_key(l) in facts.languages]
    if not check_free_text(fixed.summary, facts, "summary").passed:
        fixed.summary = master.summary
    if not check_free_text(fixed.headline, facts, "headline").passed:
        fixed.headline = master.headline
    return fixed, original_report
