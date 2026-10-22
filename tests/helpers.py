from backend.cv.profile import CandidateProfile
from backend.cv.structurer import structure_cv
from backend.cv.truthfulness import FactBase
from backend.jobs.matcher import JobPreferences
from backend.jobs.normalizer import build_job
from tests.conftest import SAMPLE_CV, SAMPLE_JOB


def sample_cv():
    return structure_cv(SAMPLE_CV)


def sample_profile():
    return CandidateProfile(full_name="Priya Sharma", work_authorized_countries=["India"],
                            needs_sponsorship_countries=["Germany"], notice_period="60 days",
                            salary_expectation="₹14 LPA")


def sample_facts(cv=None, profile=None):
    cv = cv or sample_cv()
    profile = profile or sample_profile()
    return FactBase(cv, profile.evidence_text(), profile.work_authorized_countries,
                    profile.needs_sponsorship_countries)


def sample_job(**overrides):
    fields = dict(source="greenhouse", source_job_id="1", url="https://boards.greenhouse.io/x/jobs/1",
                  title="Senior Mechanical Design Engineer", company="Example EV Inc",
                  location="Bengaluru, India", description_text=SAMPLE_JOB)
    fields.update(overrides)
    return build_job(**fields)


def sample_prefs(**overrides):
    fields = dict(target_roles=["Mechanical Design Engineer", "Design Engineer"], preferred_countries=["India"],
                  work_authorized_countries=["India"])
    fields.update(overrides)
    return JobPreferences(**fields)
