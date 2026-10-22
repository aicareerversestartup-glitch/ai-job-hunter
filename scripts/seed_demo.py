"""Create a ready-to-use demo account for App Store / Play Store reviewers.

    python scripts/seed_demo.py --email reviewer@yourdomain.com --password "a-long-password"

The account gets the sample CV (verified), a profile, a few sample jobs (added as manual jobs, so
no network is needed) and one drafted application, so reviewers can see every screen working.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SAMPLE_JOBS = [
    {"title": "Operations Manager", "company": "Example Logistics GmbH", "location": "Hamburg, Germany",
     "description": (ROOT / "data/samples/sample_job.txt").read_text(encoding="utf-8").replace(
         "Senior Mechanical Design Engineer", "Operations Manager")},
    {"title": "Warehouse Manager", "company": "Example Fulfilment B.V.", "location": "Rotterdam, Netherlands",
     "description": "About the role\nRun a 100,000 sq ft fulfilment centre.\nRequirements\n- 5+ years of experience "
                    "in warehouse operations.\n- WMS, Excel and Power BI.\n- Lean, Kaizen and 5S.\n- Team leadership "
                    "of 40+ associates.\nNice to have\n- SAP EWM.\nThis is a full-time, on-site role."},
    {"title": "Supply Chain Manager", "company": "Example Foods Ltd", "location": "Toronto, Canada",
     "description": "Responsibilities\n- Own S&OP and demand planning.\n- Manage 3PL and carrier partners.\n"
                    "Requirements\n- 7+ years of supply chain experience.\n- SAP, Excel, inventory management.\n"
                    "- Cold chain and HACCP knowledge.\nWe offer\n- Relocation support."},
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

    from sqlmodel import select

    from backend.db import init_db, session_scope
    from backend.integrations.manual import job_from_text
    from backend.models import Profile, User
    from backend.security.crypto import hash_password
    from backend.services import application_service, cv_service
    from backend.services.common import apply_cv_roles, build_facts, get_active_cv, get_profile
    from backend.services.discovery import store_job

    init_db()
    with session_scope() as s:
        if s.exec(select(User).where(User.email == args.email.lower())).first():
            print("That account already exists.")
            return
        user = User(email=args.email.lower(), password_hash=hash_password(args.password), full_name="App Reviewer")
        s.add(user)
        s.flush()
        s.add(Profile(user_id=user.id, data={
            "full_name": "Rahul Verma", "email": args.email.lower(), "location": "Gurugram, India",
            "work_authorized_countries": ["India"], "needs_sponsorship_countries": ["Germany", "Netherlands", "Canada"],
            "notice_period": "60 days", "relocation_statement": "Open to international relocation with visa sponsorship.",
            "passport_status": "Valid Indian Passport"},
            preferences={"preferred_countries": ["Germany", "Netherlands", "Canada"],
                         "target_roles": ["Operations Manager"], "min_apply_score": 50}))
        s.commit()
        user_id = user.id
    with session_scope() as s:
        data = (ROOT / "data/samples/sample_operations_cv.txt").read_bytes()
        record = cv_service.upload_master_cv(s, user_id, "Rahul_Verma_CV.txt", data)
        cv_service.verify_master_cv(s, user_id, record)
    with session_scope() as s:
        profile, prefs = get_profile(s, user_id)
        active = get_active_cv(s, user_id)
        cv, facts = build_facts(active, profile)
        apply_cv_roles(prefs, cv)
        jobs = [store_job(s, user_id, job_from_text(title=j["title"], company=j["company"], location=j["location"],
                                                     description=j["description"],
                                                     url="https://example.com/jobs/" + str(i)),
                          active, cv, facts, prefs) for i, j in enumerate(SAMPLE_JOBS)]
        s.commit()
        application_service.create_draft(s, user_id, jobs[0])
    print(f"Demo account ready: {args.email}")


if __name__ == "__main__":
    main()
