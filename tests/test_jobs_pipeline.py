"""Parsing, normalization, dedupe, fraud screening, matching and requirement extraction."""
from datetime import datetime, timedelta, timezone

from backend.cv.parser import extract_text
from backend.cv.renderer import cv_to_docx, cv_to_markdown, cv_to_pdf
from backend.jobs.dedupe import dedupe
from backend.jobs.fraud import assess_job
from backend.jobs.matcher import score_job
from backend.jobs.normalizer import infer_country, infer_employment_type, infer_remote_type, infer_seniority
from backend.jobs.requirements import extract_requirements
from backend.jobs.skills_taxonomy import find_skills
from backend.utils.dates import total_experience_months
from tests.conftest import SAMPLE_CV
from tests.helpers import sample_cv, sample_facts, sample_job, sample_prefs


def test_structure_sample_cv():
    cv = sample_cv()
    assert cv.contact.email == "priya.sharma@example.com"
    assert [e.employer for e in cv.experience] == ["Tata AutoComp Systems", "Mahindra & Mahindra"]
    assert cv.experience[0].title == "Design Engineer" and cv.experience[0].end == "Present"
    assert len(cv.experience[0].bullets) == 4
    assert cv.education[0].degree == "B.Tech" and cv.education[0].institution == "College of Engineering Pune"
    assert "SolidWorks" in cv.skills and "Lean Six Sigma Green Belt" in cv.certifications


def test_docx_roundtrip_and_renderers():
    cv = sample_cv()
    data = cv_to_docx(cv)
    extracted = extract_text("cv.docx", data)
    assert "Tata AutoComp Systems" in extracted.text
    assert cv_to_pdf(cv).startswith(b"%PDF")
    assert "## Experience" in cv_to_markdown(cv)


def test_plain_text_extraction():
    assert "PRIYA SHARMA" in extract_text("cv.txt", SAMPLE_CV.encode()).text


def test_experience_months_merges_overlaps():
    months = total_experience_months([("Jan 2020", "Dec 2020"), ("Jun 2020", "Jun 2021")],
                                     today=datetime(2026, 1, 1).date())
    assert months == 18


def test_skill_extraction_handles_symbols_and_ambiguity():
    skills = find_skills("C++, C# and GD&T. You will excel at teamwork. Go to market. Advanced Excel.")
    assert {"C++", "C#", "GD&T", "Excel"} <= set(skills)
    assert "Go" not in skills


def test_inference_helpers():
    assert infer_country("Gurugram, Haryana") == "India"
    assert infer_remote_type("Hybrid - 3 days in office") == "hybrid"
    assert infer_employment_type("Summer Internship 2026") == "internship"
    assert infer_seniority("Sr. Software Engineer") == "senior"


def test_requirements_respect_nice_to_have_sections():
    reqs = {(r.kind, r.value): r.importance for r in extract_requirements(sample_job().description_text)}
    assert reqs[("skill", "GD&T")] == "required"
    assert reqs[("skill", "Python")] == "preferred"
    assert reqs[("certification", "PMP")] == "preferred"
    assert ("experience_years", "5+ years") in reqs


def test_match_reports_missing_requirements():
    cv = sample_cv()
    result = score_job(sample_job(), cv, sample_prefs(), sample_facts(cv))
    missing = {m["requirement"] for m in result.missing_requirements}
    assert {"Creo", "CFD", "Python", "PMP"} <= missing
    assert all(m["label"] == "MISSING REQUIREMENT" for m in result.missing_requirements)
    assert "SolidWorks" in result.matched_skills
    assert result.score >= 75 and not result.dealbreakers


def test_dealbreakers_cap_the_score():
    cv = sample_cv()
    job = sample_job(location="Berlin, Germany", source_job_id="2")
    result = score_job(job, cv, sample_prefs(), sample_facts(cv))
    assert result.dealbreakers and result.score <= 35


def test_missing_years_is_reported():
    cv = sample_cv()
    job = sample_job(description_text="Requirements\n- 12+ years of experience in mechanical design.\n- SolidWorks.")
    result = score_job(job, cv, sample_prefs(), sample_facts(cv))
    assert any(m["kind"] == "experience_years" for m in result.missing_requirements)


def test_dedupe_across_sources():
    a = sample_job()
    b = sample_job(source="adzuna", source_job_id="zz", url="https://adzuna.example/1", company="Example EV")
    c = sample_job(source_job_id="3", title="Quality Engineer")
    result = dedupe([b, a, c])
    assert len(result.unique) == 2
    assert result.unique[0].source == "greenhouse"  # direct employer source preferred


def test_fraud_rules():
    scam = sample_job(source="rss", source_job_id="s1", description_text=(
        "Work from home data entry! Earn $5000 per week, no interview needed. Pay a refundable deposit for your "
        "training kit and send your bank account details on WhatsApp to recruiter@gmail.com"))
    report = assess_job(scam)
    assert report.risk_level == "high"
    assert {"ASKS_FOR_PAYMENT", "OFF_PLATFORM_CONTACT", "FREE_EMAIL_CONTACT"} <= {f["code"] for f in report.flags}
    assert assess_job(sample_job()).risk_level == "low"


def test_stale_posting_lowers_quality_not_risk():
    old = sample_job(posted_at=(datetime.now(timezone.utc) - timedelta(days=90)).isoformat())
    report = assess_job(old)
    assert report.risk_level == "low" and report.quality_score < 100
