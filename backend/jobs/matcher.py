"""Score a job against the user's verified CV and preferences, and list missing requirements.

The score is deterministic and explainable (each component is returned). An LLM can add a
narrative assessment on top (``backend.ai.services.explain_match``) but never changes the facts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from pydantic import BaseModel, Field

from backend.cv.schema import CVData
from backend.cv.truthfulness import FactBase
from backend.jobs.normalizer import NormalizedJob, normalize_title
from backend.jobs.requirements import Requirement, degree_level, extract_requirements
from backend.utils.text import contains_phrase, normalize_key, token_set

WEIGHTS = {"skills": 40, "role": 25, "experience": 15, "preferences": 10, "education": 5, "other": 5}
SENIORITY_ORDER = ["intern", "entry", "mid", "senior", "lead", "manager", "director", "executive"]


class JobPreferences(BaseModel):
    target_roles: list[str] = Field(default_factory=list)
    preferred_countries: list[str] = Field(default_factory=list)
    preferred_cities: list[str] = Field(default_factory=list)
    remote_preference: str = "any"  # any | remote_only | hybrid_ok | onsite_ok
    employment_types: list[str] = Field(default_factory=lambda: ["full_time"])
    min_salary: float | None = None
    salary_currency: str = ""
    seniority_levels: list[str] = Field(default_factory=list)  # empty = any
    work_authorized_countries: list[str] = Field(default_factory=list)
    needs_sponsorship_countries: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    exclude_companies: list[str] = Field(default_factory=list)
    willing_to_relocate: bool = False
    # Companies to search directly: [{"name": "DHL Group", "countries": ["Germany", "Netherlands"]}]
    target_companies: list[dict] = Field(default_factory=list)
    min_apply_score: int = 70  # below this, drafting warns that interview chances are low
    include_cv_roles: bool = True  # also search roles suggested from your CV
    excluded_cv_roles: list[str] = Field(default_factory=list)
    cv_roles: list[str] = Field(default_factory=list)  # filled at runtime from the active CV; not stored

    def all_roles(self) -> list[str]:
        return list(dict.fromkeys([*self.target_roles, *(self.cv_roles if self.include_cv_roles else [])]))


@dataclass
class MatchResult:
    score: int
    components: dict[str, float]
    matched_skills: list[str]
    missing_requirements: list[dict]
    dealbreakers: list[str]
    reasons: list[str]
    recommendation: str
    years_experience: float
    requirements: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _title_similarity(a: str, b: str) -> float:
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb:
        return 0.0
    seq = SequenceMatcher(None, na, nb).ratio()
    ta, tb = token_set(na), token_set(nb)
    overlap = len(ta & tb) / max(1, min(len(ta), len(tb))) if ta and tb else 0.0
    contained = 1.0 if na in nb or nb in na else 0.0
    return max(seq, 0.85 * overlap, 0.9 * contained)


def score_job(job: NormalizedJob, cv: CVData, prefs: JobPreferences, facts: FactBase | None = None) -> MatchResult:
    facts = facts or FactBase(cv)
    reqs = extract_requirements(job.description_text)
    components: dict[str, float] = {}
    reasons: list[str] = []
    dealbreakers: list[str] = []
    missing: list[dict] = []

    def miss(req: Requirement, detail: str) -> None:
        missing.append({"label": "MISSING REQUIREMENT", "kind": req.kind, "requirement": req.value,
                        "importance": req.importance, "detail": detail, "evidence": req.evidence[:300]})

    # --- Skills ---------------------------------------------------------------------------
    skill_reqs = [r for r in reqs if r.kind == "skill"]
    matched_skills = [r.value for r in skill_reqs if facts.has_skill(r.value)]
    for r in skill_reqs:
        if r.value not in matched_skills:
            miss(r, f"'{r.value}' does not appear in your Master CV.")
    req_sk = [r for r in skill_reqs if r.importance == "required"]
    pref_sk = [r for r in skill_reqs if r.importance == "preferred"]
    if skill_reqs:
        req_ratio = sum(r.value in matched_skills for r in req_sk) / len(req_sk) if req_sk else 1.0
        pref_ratio = sum(r.value in matched_skills for r in pref_sk) / len(pref_sk) if pref_sk else req_ratio
        skills_score = 0.8 * req_ratio + 0.2 * pref_ratio
    else:
        cv_tokens = token_set(" ".join(cv.skills))
        skills_score = min(1.0, len(cv_tokens & token_set(job.description_text)) / max(3, len(cv_tokens) * 0.3)) \
            if cv_tokens else 0.3
    components["skills"] = skills_score
    if matched_skills:
        reasons.append(f"Matches {len(matched_skills)} of {len(skill_reqs)} skills mentioned: "
                       + ", ".join(matched_skills[:8]))

    # --- Role / title ---------------------------------------------------------------------
    target_sim = max((_title_similarity(job.title, t) for t in prefs.all_roles()), default=0.0)
    history_sim = max((_title_similarity(job.title, e.title) for e in cv.experience), default=0.0)
    role_score = max(target_sim, 0.8 * history_sim)
    components["role"] = role_score
    if target_sim >= 0.6:
        reasons.append("Title matches one of your target roles.")
    elif history_sim >= 0.6:
        reasons.append("Title is close to a role you have held.")

    # --- Experience -----------------------------------------------------------------------
    have_years = facts.total_years
    years_reqs = [r for r in reqs if r.kind == "experience_years"]
    exp_score = 1.0
    if years_reqs:
        need = max(r.years or 0 for r in years_reqs if r.importance == "required") if any(
            r.importance == "required" for r in years_reqs) else max(r.years or 0 for r in years_reqs)
        if need > 0 and have_years + 0.25 < need:
            exp_score = max(0.0, have_years / need)
            worst = max(years_reqs, key=lambda r: r.years or 0)
            miss(worst, f"Asks for {need:g}+ years; your CV shows about {have_years:.1f} years.")
    if prefs.seniority_levels and job.seniority in SENIORITY_ORDER:
        wanted = [SENIORITY_ORDER.index(s) for s in prefs.seniority_levels if s in SENIORITY_ORDER]
        if wanted:
            gap = min(abs(SENIORITY_ORDER.index(job.seniority) - w) for w in wanted)
            exp_score *= max(0.4, 1 - 0.3 * gap)
    components["experience"] = exp_score

    # --- Preferences (location / remote / type / salary) ------------------------------------
    pref_score, pref_parts = 0.0, 0
    countries = {normalize_key(c) for c in prefs.preferred_countries}
    if countries or prefs.preferred_cities:
        pref_parts += 1
        loc_ok = (normalize_key(job.country) in countries) or any(
            contains_phrase(job.location.lower(), c.lower()) for c in prefs.preferred_cities)
        remote_ok = job.remote_type == "remote" and prefs.remote_preference in ("any", "remote_only", "hybrid_ok")
        if loc_ok or remote_ok:
            pref_score += 1
        elif job.country and not prefs.willing_to_relocate:
            dealbreakers.append(f"Location {job.location or job.country} is outside your preferred countries.")
    if prefs.remote_preference == "remote_only":
        pref_parts += 1
        if job.remote_type == "remote":
            pref_score += 1
        elif job.remote_type in ("onsite", "hybrid"):
            dealbreakers.append(f"Job is {job.remote_type}; you asked for remote only.")
        else:
            pref_score += 0.5
    if prefs.employment_types:
        pref_parts += 1
        if job.employment_type in prefs.employment_types or job.employment_type == "unknown":
            pref_score += 1
        else:
            dealbreakers.append(f"Employment type is {job.employment_type.replace('_', ' ')}.")
    if prefs.min_salary and job.salary_max:
        pref_parts += 1
        same_currency = not prefs.salary_currency or not job.salary_currency or \
            prefs.salary_currency.upper() == job.salary_currency.upper()
        if same_currency and job.salary_max < prefs.min_salary:
            dealbreakers.append(f"Advertised salary tops out at {job.salary_max:,.0f}, below your minimum.")
        else:
            pref_score += 1
    components["preferences"] = pref_score / pref_parts if pref_parts else 1.0

    # --- Education --------------------------------------------------------------------------
    have_levels = [degree_level(e.degree) for e in cv.education if e.degree]
    have_level = max(have_levels, default=-1)
    degree_reqs = [r for r in reqs if r.kind == "degree"]
    edu_score = 1.0
    if degree_reqs:
        need_level = min(r.level or 0 for r in degree_reqs)  # "Bachelor's or Master's" -> bachelor
        if have_level < need_level:
            edu_score = 0.3
            req = min(degree_reqs, key=lambda r: r.level or 0)
            miss(req, "Your Master CV does not list this level of degree.")
    components["education"] = edu_score

    # --- Other: certifications, languages, authorization -----------------------------------
    other_total, other_ok = 0, 0
    for r in reqs:
        if r.kind == "certification":
            other_total += 1
            if any(contains_phrase(c.lower(), r.value.lower()) or contains_phrase(r.value.lower(), c.lower())
                   for c in cv.certifications):
                other_ok += 1
            else:
                miss(r, "Certification not in your Master CV.")
        elif r.kind == "language":
            other_total += 1
            if any(contains_phrase(l.lower(), r.value.lower()) for l in cv.languages) or \
                    (r.value.lower() == "english" and not cv.languages):
                other_ok += 1
            else:
                miss(r, f"{r.value} is not listed in your languages.")
        elif r.kind == "authorization":
            other_total += 1
            auth = {normalize_key(c) for c in prefs.work_authorized_countries}
            needs = {normalize_key(c) for c in prefs.needs_sponsorship_countries}
            country = normalize_key(job.country or r.value)
            if r.value == "no visa sponsorship":
                if country and country in needs:
                    dealbreakers.append("Employer does not sponsor visas and you need sponsorship there.")
                    miss(r, "No visa sponsorship offered.")
                else:
                    other_ok += 1
            elif country in auth or any(a and a in normalize_key(r.value) for a in auth):
                other_ok += 1
            else:
                miss(r, "Your profile does not state work authorization for this country.")
    components["other"] = other_ok / other_total if other_total else 1.0

    # --- Exclusions -------------------------------------------------------------------------
    blob = f"{job.title} {job.company} {job.description_text}".lower()
    for kw in prefs.exclude_keywords:
        if kw.strip() and contains_phrase(blob, kw.strip().lower()):
            dealbreakers.append(f"Contains excluded keyword '{kw}'.")
    if any(normalize_key(c) == normalize_key(job.company) for c in prefs.exclude_companies):
        dealbreakers.append("Company is on your exclusion list.")

    raw = sum(WEIGHTS[k] * components[k] for k in WEIGHTS)
    score = int(round(raw))
    if dealbreakers:
        score = min(score, 35)
    required_missing = [m for m in missing if m["importance"] == "required"]
    if len(required_missing) >= 4:
        score = min(score, 55)
    recommendation = ("strong" if score >= 75 else "good" if score >= 60 else "stretch" if score >= 45 else "poor")
    return MatchResult(score=score, components={k: round(v, 3) for k, v in components.items()},
                       matched_skills=matched_skills, missing_requirements=missing, dealbreakers=dealbreakers,
                       reasons=reasons, recommendation=recommendation, years_experience=round(have_years, 1),
                       requirements=[r.__dict__ for r in reqs])


def quick_relevance(job: NormalizedJob, prefs: JobPreferences) -> float:
    """Cheap pre-filter used during discovery so we only fully score plausible jobs."""
    roles = prefs.all_roles()
    if not roles:
        return 1.0
    best = max(_title_similarity(job.title, t) for t in roles)
    target_tokens = set().union(*(token_set(t) for t in roles))
    title_tokens = token_set(job.title)
    token_hit = len(title_tokens & target_tokens) / max(1, len(title_tokens)) if title_tokens else 0
    return max(best, token_hit)


ROLE_MATCH = 0.6
GENERIC_ROLE_WORDS = {"manager", "senior", "junior", "lead", "head", "assistant", "deputy", "associate", "executive",
                      "specialist", "officer", "engineer", "director", "principal", "staff", "i", "ii", "iii", "of",
                      "and", "global", "regional", "site", "sr", "jr", "chief", "team"}


def role_similarity(job_title: str, role: str) -> float:
    """Like _title_similarity, but the function words of a title (operations, warehouse, supply chain…)
    must match; 'Warehouse Manager' is not the same role as 'Operations Manager'."""
    a = token_set(normalize_title(job_title)) - GENERIC_ROLE_WORDS
    b = token_set(normalize_title(role)) - GENERIC_ROLE_WORDS
    if not a or not b:
        return _title_similarity(job_title, role)
    core = len(a & b) / len(b)
    return core * max(0.6, _title_similarity(job_title, role))


def priority(job: NormalizedJob, score: int, prefs: JobPreferences) -> dict:
    """Ordering the user asked for: their country list first (in their order), within that their own
    roles first, then roles suggested from the CV, then by match score. Lower rank = shown first."""
    countries = [normalize_key(c) for c in prefs.preferred_countries]
    country = normalize_key(job.country)
    if country and country in countries:
        country_rank = countries.index(country)
    elif job.remote_type == "remote":
        country_rank = len(countries)
    else:
        country_rank = len(countries) + 1
    yours = max((role_similarity(job.title, t) for t in prefs.target_roles), default=0.0)
    from_cv = max((role_similarity(job.title, t) for t in prefs.cv_roles), default=0.0)
    if yours >= ROLE_MATCH and yours >= from_cv - 0.05:
        tier, role = 0, max(prefs.target_roles, key=lambda t: role_similarity(job.title, t))
    elif from_cv >= ROLE_MATCH and prefs.include_cv_roles:
        tier, role = 1, max(prefs.cv_roles, key=lambda t: role_similarity(job.title, t))
    else:
        tier, role = 2, ""
    return {"country_rank": country_rank, "in_country_list": country_rank < len(countries), "role_tier": tier,
            "matched_role": role, "rank": country_rank * 10000 + tier * 1000 + (100 - score)}
