"""Document generation: tailored CV, cover letter, application answers, and CV extraction.

Each function works without AI (deterministic fallback). When a provider is configured the model
drafts the content, and the truthfulness guard checks and repairs it before anything is returned.
"""
from __future__ import annotations

import logging
from typing import Any
import re
from dataclasses import dataclass, field

from backend.ai import prompts
from backend.ai.providers.base import LLMError, LLMProvider
from backend.cv.profile import CandidateProfile
from backend.cv.schema import CVData
from backend.cv.structurer import structure_cv
from backend.cv.truthfulness import FactBase, GuardReport, check_cv, check_free_text, sanitize_cv
from backend.jobs.matcher import MatchResult
from backend.jobs.normalizer import NormalizedJob
from backend.jobs.skills_taxonomy import canonical_skill, find_skills
from backend.utils.text import contains_phrase, normalize_key, token_set, truncate

log = logging.getLogger(__name__)
MAX_JD_CHARS = 9000


@dataclass
class GeneratedDocument:
    content: Any  # CVData for CVs, str for letters
    method: str  # "ai" | "deterministic" | "ai+repaired"
    guard: GuardReport
    notes: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------------------------
# Tailored CV
# --------------------------------------------------------------------------------------------

def _relevance(text: str, job_tokens: set[str], job_skills: set[str]) -> float:
    tokens = token_set(text)
    skill_hits = sum(1 for s in find_skills(text) if s in job_skills)
    return len(tokens & job_tokens) / (1 + len(tokens)) ** 0.5 + 1.5 * skill_hits


def deterministic_tailor(master: CVData, job: NormalizedJob, match: MatchResult | None) -> CVData:
    """Reorder (never invent): most relevant bullets, skills and projects first."""
    cv = master.model_copy(deep=True)
    job_tokens = token_set(job.title + " " + job.description_text)
    job_skills = set(find_skills(job.description_text))
    for exp in cv.experience:
        exp.bullets = sorted(exp.bullets, key=lambda b: -_relevance(b, job_tokens, job_skills))
    # ATS keywords: JD skills that your CV already shows in your experience but that are missing from
    # the Skills list are added there. Only evidenced skills qualify, so nothing new is claimed.
    evidence = master.all_text().lower()
    listed = {normalize_key(canonical_skill(s)) for s in cv.skills} | {normalize_key(s) for s in cv.skills}
    from backend.jobs.skills_taxonomy import skill_aliases
    for skill in find_skills(job.description_text):
        if normalize_key(skill) in listed:
            continue
        if any(contains_phrase(evidence, alias) for alias in skill_aliases().get(skill, (skill.lower(),))):
            cv.skills.append(skill)
            listed.add(normalize_key(skill))
    matched = {normalize_key(s) for s in (match.matched_skills if match else job_skills)}
    cv.skills = sorted(cv.skills, key=lambda s: (0 if normalize_key(canonical_skill(s)) in matched
                                                 or normalize_key(s) in matched else 1))
    cv.projects = sorted(cv.projects, key=lambda p: -_relevance(
        " ".join([p.name, p.description, *p.bullets, *p.technologies]), job_tokens, job_skills))
    return cv


def tailor_cv(master: CVData, job: NormalizedJob, match: MatchResult | None, facts: FactBase,
              provider: LLMProvider | None) -> GeneratedDocument:
    base = deterministic_tailor(master, job, match)
    if provider is None or not provider.available:
        return GeneratedDocument(base, "deterministic", check_cv(base, facts),
                                 ["No AI provider configured: content reordered for relevance, wording unchanged."])
    prompt = prompts.TAILOR_PROMPT.format(
        title=job.title, company=job.company, description=truncate(job.description_text, MAX_JD_CHARS),
        matched=", ".join(match.matched_skills) if match else "",
        missing=", ".join(m["requirement"] for m in (match.missing_requirements if match else [])) or "none",
        cv_json=base.model_dump_json(indent=1),
    )
    try:
        data = provider.complete_json(prompts.TAILOR_SYSTEM, prompt)
        draft = CVData.model_validate(data)
    except (LLMError, ValueError) as exc:
        log.warning("AI tailoring failed, using deterministic version: %s", exc)
        return GeneratedDocument(base, "deterministic", check_cv(base, facts), [f"AI tailoring failed: {exc}"])

    repaired, original_report = sanitize_cv(draft, facts)
    final_report = check_cv(repaired, facts)
    notes = []
    removed = [v for v in original_report.violations if v.severity == "error"]
    if removed:
        notes.append(f"The truthfulness guard removed or reverted {len(removed)} unverifiable item(s) "
                     "from the AI draft. See the guard report.")
    if not final_report.passed:  # should not happen, but never ship a failing CV
        return GeneratedDocument(base, "deterministic", check_cv(base, facts),
                                 notes + ["AI draft could not be repaired; using reordered Master CV."])
    final_report.violations = original_report.violations + [
        v for v in final_report.violations if v not in original_report.violations]
    return GeneratedDocument(repaired, "ai+repaired" if removed else "ai", final_report, notes)


# --------------------------------------------------------------------------------------------
# Cover letter
# --------------------------------------------------------------------------------------------

def deterministic_cover_letter(master: CVData, profile: CandidateProfile, job: NormalizedJob,
                               match: MatchResult | None) -> str:
    name = profile.full_name or master.contact.full_name or ""
    matched = (match.matched_skills if match else [])[:5]
    job_tokens = token_set(job.description_text)
    job_skills = set(find_skills(job.description_text))
    best_role = max(master.experience, key=lambda e: _relevance(" ".join(e.bullets), job_tokens, job_skills),
                    default=None)
    paragraphs = ["Dear Hiring Team,",
                  f"I am writing to apply for the {job.title} position at {job.company}."]
    if best_role:
        top = sorted(best_role.bullets, key=lambda b: -_relevance(b, job_tokens, job_skills))[:2]
        sentence = f"In my role as {best_role.title} at {best_role.employer}, my work has included the following:"
        paragraphs.append(sentence + "\n" + "\n".join(f"- {b.rstrip('.')}." for b in top))
    if matched:
        paragraphs.append("My background includes " + _join(matched) + ", which the role calls for.")
    paragraphs.append(f"I would welcome the opportunity to discuss how I can contribute to {job.company}. "
                      "Thank you for your time and consideration.")
    paragraphs.append(f"Sincerely,\n{name}".rstrip())
    return "\n\n".join(paragraphs)


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def write_cover_letter(master: CVData, profile: CandidateProfile, job: NormalizedJob, match: MatchResult | None,
                       facts: FactBase, provider: LLMProvider | None) -> GeneratedDocument:
    allowed = f"{job.title}\n{job.company}\n{job.location}\n{job.description_text}"
    fallback = deterministic_cover_letter(master, profile, job, match)
    if provider is None or not provider.available:
        return GeneratedDocument(fallback, "deterministic",
                                 check_free_text(fallback, facts, "cover_letter", allowed))
    prompt = prompts.COVER_PROMPT.format(
        title=job.title, company=job.company, location=job.location or job.remote_type,
        description=truncate(job.description_text, MAX_JD_CHARS), profile=profile.summary_for_prompt(),
        cv_json=master.model_dump_json(indent=1), matched=", ".join(match.matched_skills) if match else "",
        missing=", ".join(m["requirement"] for m in (match.missing_requirements if match else [])) or "none",
        name=profile.full_name or master.contact.full_name,
    )
    try:
        text = provider.complete(prompts.COVER_SYSTEM, prompt, temperature=0.4).strip()
    except LLMError as exc:
        return GeneratedDocument(fallback, "deterministic", check_free_text(fallback, facts, "cover_letter", allowed),
                                 [f"AI cover letter failed: {exc}"])
    report = check_free_text(text, facts, "cover_letter", allowed)
    if not report.passed:
        notes = ["The AI draft made claims not supported by your Master CV, so a fact-only letter was used. "
                 "Blocked claims: " + "; ".join(v.value for v in report.violations if v.severity == "error")]
        return GeneratedDocument(fallback, "deterministic", check_free_text(fallback, facts, "cover_letter", allowed),
                                 notes)
    return GeneratedDocument(text, "ai", report)


# --------------------------------------------------------------------------------------------
# Application answers
# --------------------------------------------------------------------------------------------

NEEDS_INPUT = "NEEDS_USER_INPUT"
DEFAULT_QUESTIONS = [
    "Are you legally authorized to work in this country?",
    "Will you now or in the future require visa sponsorship?",
    "What are your salary expectations?",
    "What is your notice period / earliest start date?",
    "Are you willing to relocate?",
    "How many years of relevant experience do you have?",
    "LinkedIn profile URL",
    "Why are you interested in this role?",
]


def _rule_answer(question: str, profile: CandidateProfile, facts: FactBase, job: NormalizedJob) -> str | None:
    q = question.lower()
    for saved_q, saved_a in profile.saved_answers.items():
        if normalize_key(saved_q) == normalize_key(question):
            return saved_a
    country = job.country
    if re.search(r"authori[sz]ed|eligible to work|right to work|work permit", q):
        if not country:
            return NEEDS_INPUT
        if any(normalize_key(c) == normalize_key(country) for c in profile.work_authorized_countries):
            return f"Yes, I am authorized to work in {country}."
        return NEEDS_INPUT  # unknown: the user must answer; we never assume
    if "sponsor" in q:
        if not country:
            return NEEDS_INPUT
        if any(normalize_key(c) == normalize_key(country) for c in profile.needs_sponsorship_countries):
            return f"Yes, I would require visa sponsorship to work in {country}."
        if any(normalize_key(c) == normalize_key(country) for c in profile.work_authorized_countries):
            return "No, I do not require sponsorship."
        return NEEDS_INPUT
    if re.search(r"salary|compensation|ctc|pay expectation", q):
        return profile.salary_expectation or NEEDS_INPUT
    if re.search(r"notice period|start date|when can you start|availability", q):
        parts = [p for p in (profile.notice_period and f"Notice period: {profile.notice_period}.",
                             profile.earliest_start_date and f"Earliest start date: {profile.earliest_start_date}.") if p]
        return " ".join(parts) or NEEDS_INPUT
    if "relocat" in q:
        return "Yes, I am willing to relocate." if profile.willing_to_relocate else NEEDS_INPUT
    if re.search(r"years of (relevant |professional |work )?experience|how many years", q):
        return f"{facts.total_years:.0f} years of professional experience, per my CV." if facts.total_years else NEEDS_INPUT
    if "linkedin" in q:
        return profile.linkedin_url or NEEDS_INPUT
    if "github" in q:
        return profile.github_url or NEEDS_INPUT
    if "portfolio" in q or "website" in q:
        return profile.portfolio_url or NEEDS_INPUT
    if re.search(r"gender|race|ethnicity|veteran|disability|sexual orientation|pronoun", q):
        return profile.pronouns if "pronoun" in q and profile.pronouns else profile.eeo_default
    if re.search(r"phone|mobile", q):
        return profile.phone or NEEDS_INPUT
    if "email" in q:
        return profile.email or NEEDS_INPUT
    return None


def answer_questions(questions: list[str], master: CVData, profile: CandidateProfile, job: NormalizedJob,
                     facts: FactBase, provider: LLMProvider | None) -> list[dict]:
    allowed = f"{job.title}\n{job.company}\n{job.description_text}"
    answers: list[dict] = []
    for question in questions:
        answer = _rule_answer(question, profile, facts, job)
        source = "profile"
        if answer is None:
            source = "ai"
            if provider is None or not provider.available:
                answer = _deterministic_motivation(question, master, job) or NEEDS_INPUT
                source = "deterministic" if answer != NEEDS_INPUT else "none"
            else:
                try:
                    answer = provider.complete(prompts.ANSWER_SYSTEM, prompts.ANSWER_PROMPT.format(
                        title=job.title, company=job.company, question=question,
                        profile=profile.summary_for_prompt(), cv_json=master.model_dump_json()),
                        temperature=0.3).strip()
                except LLMError:
                    answer = NEEDS_INPUT
        report = check_free_text(answer, facts, "answer", allowed) if answer != NEEDS_INPUT else GuardReport()
        if not report.passed:
            answer, source = NEEDS_INPUT, "blocked"
        answers.append({"question": question, "answer": "" if answer == NEEDS_INPUT else answer,
                        "needs_user_input": answer == NEEDS_INPUT, "source": source,
                        "guard": report.as_dict()})
    return answers


def _deterministic_motivation(question: str, master: CVData, job: NormalizedJob) -> str | None:
    if not re.search(r"why (are you|do you)|interest|motivat", question.lower()):
        return None
    cv_text = master.all_text().lower()
    skills = [s for s in find_skills(job.description_text) if contains_phrase(cv_text, s.lower())][:3]
    text = f"The {job.title} role at {job.company} lines up with my experience"
    if skills:
        text += " in " + _join(skills)
    return text + ", and I would like to apply that experience to your team."


# --------------------------------------------------------------------------------------------
# CV extraction
# --------------------------------------------------------------------------------------------

def extract_cv_structure(raw_text: str, provider: LLMProvider | None) -> tuple[CVData, list[str]]:
    """Heuristic parse, optionally improved by AI. AI output is accepted only for values that occur
    in the original text, so extraction can never introduce new facts."""
    heuristic = structure_cv(raw_text)
    if provider is None or not provider.available:
        return heuristic, ["Parsed with built-in rules. Please review every section."]
    try:
        data = provider.complete_json(prompts.EXTRACT_SYSTEM, prompts.EXTRACT_PROMPT.format(text=raw_text[:20000]),
                                      temperature=0)
        ai_cv = CVData.model_validate(data)
    except (LLMError, ValueError) as exc:
        return heuristic, [f"AI extraction failed ({exc}); parsed with built-in rules."]
    problems = check_cv_against_text(ai_cv, raw_text)
    if problems:
        return heuristic, ["AI extraction produced values not found in your file, so built-in parsing was used: "
                           + "; ".join(problems[:5])]
    return ai_cv, ["Parsed with AI. Every value was checked against your file. Please review."]


def check_cv_against_text(cv: CVData, raw_text: str) -> list[str]:
    """Return values in ``cv`` that do not appear in ``raw_text`` (whitespace/case-insensitive)."""
    hay = re.sub(r"\s+", " ", raw_text.lower())

    def present(value: str) -> bool:
        v = re.sub(r"\s+", " ", value.lower()).strip()
        if not v:
            return True
        if v in hay:
            return True
        words = [w for w in re.findall(r"[a-z0-9+#]+", v) if len(w) > 2]
        return bool(words) and sum(w in hay for w in words) / len(words) >= 0.85

    missing = []
    values = [cv.contact.full_name, cv.contact.email, cv.contact.phone]
    for e in cv.experience:
        values += [e.employer, e.title, e.start, e.end, *e.bullets]
    for ed in cv.education:
        values += [ed.institution, ed.degree]
    values += cv.skills + cv.certifications + [p.name for p in cv.projects] + cv.languages
    for value in values:
        if value and not present(value):
            missing.append(value)
    return missing

