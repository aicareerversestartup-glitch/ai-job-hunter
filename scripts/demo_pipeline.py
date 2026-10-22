"""Run the whole matching + tailoring pipeline offline on the sample CV and a sample job.

    python scripts/demo_pipeline.py

No server, database, network or AI key needed. Useful to see what the truthfulness guard does.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.ai.generation import DEFAULT_QUESTIONS, answer_questions, tailor_cv, write_cover_letter  # noqa: E402
from backend.cv.profile import CandidateProfile  # noqa: E402
from backend.cv.structurer import structure_cv  # noqa: E402
from backend.cv.truthfulness import FactBase  # noqa: E402
from backend.jobs.fraud import assess_job  # noqa: E402
from backend.jobs.matcher import JobPreferences, score_job  # noqa: E402
from backend.jobs.normalizer import build_job  # noqa: E402

cv = structure_cv((ROOT / "data/samples/sample_master_cv.txt").read_text(encoding="utf-8"))
profile = CandidateProfile(full_name="Priya Sharma", work_authorized_countries=["India"], notice_period="60 days")
facts = FactBase(cv, profile.evidence_text(), profile.work_authorized_countries)
job = build_job(source="manual", source_job_id="demo", url="https://example.com/job",
                title="Senior Mechanical Design Engineer", company="Example EV Ltd", location="Bengaluru, India",
                description_text=(ROOT / "data/samples/sample_job.txt").read_text(encoding="utf-8"))
prefs = JobPreferences(target_roles=["Mechanical Design Engineer"], preferred_countries=["India"],
                       work_authorized_countries=["India"])
match = score_job(job, cv, prefs, facts)
print(f"Match score: {match.score} ({match.recommendation})")
print("Components:", json.dumps(match.components))
print("Matched skills:", ", ".join(match.matched_skills))
for m in match.missing_requirements:
    print(f"  {m['label']}: {m['requirement']} [{m['importance']}] - {m['detail']}")
print("Fraud check:", assess_job(job).as_dict())
doc = tailor_cv(cv, job, match, facts, provider=None)
print("\nTailored CV guard:", doc.guard.as_dict())
print("\nCover letter:\n" + write_cover_letter(cv, profile, job, match, facts, None).content)
print("\nAnswers:")
for a in answer_questions(DEFAULT_QUESTIONS, cv, profile, job, facts, None):
    print(f"  {a['question']}\n    -> {a['answer'] or '[needs your input]'}")
