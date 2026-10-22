"""The Absolute Truthfulness Rule: generated content may never add facts."""
from backend.ai.generation import tailor_cv, write_cover_letter
from backend.ai.providers.base import AIConfig, LLMProvider
from backend.cv.schema import EducationItem, ExperienceItem
from backend.cv.truthfulness import check_cv, check_free_text, sanitize_cv
from backend.jobs.matcher import score_job
from tests.helpers import sample_cv, sample_facts, sample_job, sample_prefs, sample_profile


def codes(report):
    return {v.code for v in report.violations if v.severity == "error"}


def test_master_cv_passes_its_own_guard():
    cv = sample_cv()
    assert check_cv(cv, sample_facts(cv)).passed


def test_invented_employer_title_education_certification_are_blocked():
    cv = sample_cv()
    facts = sample_facts(cv)
    bad = cv.model_copy(deep=True)
    bad.experience.append(ExperienceItem(employer="Tesla", title="Lead Engineer", start="2018", end="2019"))
    bad.experience[0].title = "Principal Engineer"
    bad.education.append(EducationItem(institution="IIT Bombay", degree="M.Tech"))
    bad.certifications.append("PMP")
    found = codes(check_cv(bad, facts))
    assert {"INVENTED_EMPLOYER", "INVENTED_JOB_TITLE", "INVENTED_EDUCATION", "INVENTED_CERTIFICATION"} <= found


def test_unsupported_skill_and_misattributed_skill_are_blocked():
    cv = sample_cv()
    facts = sample_facts(cv)
    bad = cv.model_copy(deep=True)
    bad.skills.append("Kubernetes")
    # AutoCAD is real, but only at Mahindra; claiming it at Tata is misattribution.
    bad.experience[0].bullets[0] = "Designed brackets in AutoCAD for 4 passenger-vehicle programs."
    found = codes(check_cv(bad, facts))
    assert "UNSUPPORTED_SKILL" in found
    assert "MISATTRIBUTED_SKILL" in found


def test_invented_metric_and_changed_dates_are_blocked():
    cv = sample_cv()
    facts = sample_facts(cv)
    bad = cv.model_copy(deep=True)
    bad.experience[0].bullets[1] = "Ran static and fatigue FEA in ANSYS, reducing bracket mass by 35% while meeting load targets."
    bad.experience[1].start = "Jan 2017"
    found = codes(check_cv(bad, facts))
    assert {"INVENTED_METRIC", "CHANGED_DATES"} <= found


def test_inflated_experience_and_authorization_claims_are_blocked():
    facts = sample_facts()
    report = check_free_text("I bring 15 years of experience and US work authorization.", facts)
    assert {"INFLATED_EXPERIENCE", "UNSUPPORTED_AUTHORIZATION"} <= codes(report)
    assert check_free_text("I am authorized to work in India.", facts).passed


def test_rewording_with_same_facts_is_allowed():
    cv = sample_cv()
    facts = sample_facts(cv)
    ok = cv.model_copy(deep=True)
    ok.experience[0].bullets[1] = "Reduced bracket mass by 12% while meeting load targets, using static and fatigue FEA in ANSYS."
    ok.skills = list(reversed(ok.skills))
    assert check_cv(ok, facts).passed


def test_sanitize_removes_every_error():
    cv = sample_cv()
    facts = sample_facts(cv)
    bad = cv.model_copy(deep=True)
    bad.skills += ["Python", "Kubernetes"]
    bad.experience.append(ExperienceItem(employer="Tesla", title="Lead Engineer"))
    bad.experience[0].bullets.insert(0, "Built Python tools for 9 teams.")
    bad.summary = "Engineer with 12 years of experience and a PhD."
    bad.contact.location = "Berlin"
    fixed, original = sanitize_cv(bad, facts)
    assert not original.passed
    assert check_cv(fixed, facts).passed
    assert "Python" not in fixed.skills and len(fixed.experience) == len(cv.experience)
    assert fixed.contact.location == cv.contact.location


class LyingProvider(LLMProvider):
    """Simulates an LLM that ignores instructions and embellishes."""
    name = "lying"

    def complete(self, system, prompt, **kwargs):
        if "JSON" in prompt or kwargs.get("json_mode"):
            cv = sample_cv()
            cv.skills.append("Kubernetes")
            cv.certifications.append("PMP")
            cv.experience[0].bullets[0] = "Led a team of 25 engineers designing EV battery packs in Creo."
            cv.summary = "Senior engineer with 10 years of experience."
            return cv.model_dump_json()
        return "Dear Hiring Team,\nI have 10 years of Creo and CFD experience and I am a US citizen.\nSincerely,\nPriya"


def test_lying_model_output_never_reaches_the_user():
    cv = sample_cv()
    facts = sample_facts(cv)
    job = sample_job()
    match = score_job(job, cv, sample_prefs(), facts)
    provider = LyingProvider(AIConfig(provider="lying", model="x"))
    doc = tailor_cv(cv, job, match, facts, provider)
    assert check_cv(doc.content, facts).passed
    assert "Kubernetes" not in doc.content.skills and "PMP" not in doc.content.certifications
    assert all("25 engineers" not in b for e in doc.content.experience for b in e.bullets)
    assert doc.notes  # the user is told something was removed

    letter = write_cover_letter(cv, sample_profile(), job, match, facts, provider)
    assert letter.method == "deterministic"
    assert "citizen" not in letter.content
    assert letter.guard.passed
