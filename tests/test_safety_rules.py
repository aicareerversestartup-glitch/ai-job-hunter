"""Application safety: approval gating, blocker detection, answers, security helpers, integrations."""
import pytest

from backend.ai.generation import DEFAULT_QUESTIONS, answer_questions
from backend.applications import state_machine as sm
from backend.automation.blockers import detect_ats, detect_blocker
from backend.integrations.manual import fetch_allowed, job_from_html
from backend.security.crypto import (create_access_token, decode_access_token, decrypt_secret, encrypt_secret,
                                     hash_password, verify_password)
from backend.security.guards import UnsafeURLError, validate_public_url
from tests.helpers import sample_cv, sample_facts, sample_job, sample_profile


def test_cannot_skip_approval():
    with pytest.raises(sm.TransitionError):
        sm.check_transition(sm.READY, sm.SUBMITTING)
    with pytest.raises(sm.TransitionError):
        sm.check_transition(sm.DRAFT, sm.SUBMITTED)
    sm.check_transition(sm.APPROVED, sm.SUBMITTING)


def test_snapshot_changes_when_content_changes():
    base = dict(tailored_cv={"a": 1}, cover_letter="x", answers=[], apply_url="u")
    assert sm.snapshot_hash(**base) != sm.snapshot_hash(**{**base, "cover_letter": "y"})


def test_approval_blockers():
    problems = sm.approval_blockers(cv_guard={"passed": False}, cover_guard={"passed": True},
                                    answers=[{"question": "q", "answer": "", "needs_user_input": True}], confirmed=False)
    assert len(problems) == 3
    assert sm.approval_blockers(cv_guard={"passed": True}, cover_guard={"passed": True},
                                answers=[{"question": "q", "answer": "", "needs_user_input": True, "skip": True}],
                                confirmed=True) == []


@pytest.mark.parametrize("html,kind", [
    ('<div class="g-recaptcha" data-sitekey="x"></div>', "captcha"),
    ("<title>Just a moment...</title>checking your browser", "bot_protection"),
    ('<form><input type="password" name="pw"></form>', "login"),
    ("Enter the code we sent to your phone", "mfa"),
])
def test_blockers_detected(html, kind):
    blocker = detect_blocker(html, "https://jobs.example.com/apply")
    assert blocker is not None and blocker.kind == kind


def test_plain_form_is_not_blocked():
    assert detect_blocker('<form><input name="first_name"><input type="file"></form>', "https://x.com/apply") is None


def test_ats_detection():
    assert detect_ats("https://boards.greenhouse.io/acme/jobs/1") == "greenhouse"
    assert detect_ats("https://jobs.lever.co/acme/abc") == "lever"


def test_answers_never_guess_authorization():
    cv = sample_cv()
    profile = sample_profile()
    facts = sample_facts(cv, profile)
    india = answer_questions(DEFAULT_QUESTIONS, cv, profile, sample_job(), facts, None)
    by_q = {a["question"]: a for a in india}
    assert by_q["Are you legally authorized to work in this country?"]["answer"].startswith("Yes")
    us_job = sample_job(location="Austin, TX, United States", source_job_id="9")
    us = {a["question"]: a for a in answer_questions(DEFAULT_QUESTIONS, cv, profile, us_job, facts, None)}
    assert us["Are you legally authorized to work in this country?"]["needs_user_input"]
    germany = sample_job(location="Munich, Germany", source_job_id="10")
    de = {a["question"]: a for a in answer_questions(DEFAULT_QUESTIONS, cv, profile, germany, facts, None)}
    assert de["Will you now or in the future require visa sponsorship?"]["answer"].startswith("Yes")


def test_password_hashing_and_tokens():
    stored = hash_password("correct horse battery")
    assert verify_password("correct horse battery", stored)
    assert not verify_password("wrong password!!", stored)
    with pytest.raises(ValueError):
        hash_password("short")
    payload = decode_access_token(create_access_token(7, token_version=2))
    assert payload["sub"] == "7" and payload["ver"] == 2


def test_secret_encryption_roundtrip():
    token = encrypt_secret("sk-test-123")
    assert token and "sk-test" not in token
    assert decrypt_secret(token) == "sk-test-123"


def test_ssrf_guard():
    for url in ("http://127.0.0.1/admin", "http://localhost:8000", "file:///etc/passwd", "http://169.254.169.254/",
                "http://10.0.0.5/feed"):
        with pytest.raises(UnsafeURLError):
            validate_public_url(url, resolve=False)
    assert validate_public_url("https://8.8.8.8/feed", resolve=False)


def test_restricted_sites_are_not_fetched():
    assert not fetch_allowed("https://www.linkedin.com/jobs/view/123")
    assert fetch_allowed("https://careers.example.com/jobs/123")


def test_jsonld_job_import():
    html = """<html><head><script type="application/ld+json">{"@context":"https://schema.org","@type":"JobPosting",
    "title":"Design Engineer","description":"<p>Design parts in SolidWorks. 3+ years of experience.</p>",
    "hiringOrganization":{"@type":"Organization","name":"Acme Motors"},"datePosted":"2026-10-01",
    "employmentType":"FULL_TIME","jobLocation":{"@type":"Place","address":{"addressLocality":"Pune","addressCountry":"IN"}}}
    </script></head><body></body></html>"""
    job = job_from_html(html, "https://careers.acme.example/jobs/1")
    assert job.title == "Design Engineer" and job.company == "Acme Motors"
    assert job.employment_type == "full_time" and "SolidWorks" in job.description_text
    assert job.country == "India"
