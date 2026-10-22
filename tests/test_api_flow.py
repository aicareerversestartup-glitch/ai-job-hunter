"""End-to-end API flow: account → profile → Master CV → job → draft → review → approve → apply → track."""
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlmodel")

from fastapi.testclient import TestClient  # noqa: E402

from tests.conftest import SAMPLE_CV, SAMPLE_JOB  # noqa: E402


@pytest.fixture(scope="module")
def client():
    from backend.db import init_db
    from backend.main import app

    init_db()
    with TestClient(app) as c:
        yield c


def test_full_flow(client):
    r = client.post("/api/auth/register", json={"email": "priya@example.com", "password": "a-long-password",
                                                "full_name": "Priya Sharma"})
    assert r.status_code == 200, r.text
    assert client.get("/api/auth/me").json()["email"] == "priya@example.com"

    profile = client.get("/api/profile").json()
    profile["profile"]["work_authorized_countries"] = ["India"]
    profile["preferences"]["target_roles"] = ["Mechanical Design Engineer"]
    profile["preferences"]["preferred_countries"] = ["India"]
    assert client.put("/api/profile", json=profile).status_code == 200

    # Matching requires a verified CV.
    r = client.post("/api/cv/upload", files={"file": ("cv.txt", SAMPLE_CV.encode(), "text/plain")})
    assert r.status_code == 200, r.text
    cv = r.json()
    assert cv["status"] == "needs_review"
    r = client.post("/api/jobs/manual", json={"title": "Senior Mechanical Design Engineer", "company": "Example EV",
                                              "location": "Bengaluru, India", "url": "https://example.com/j/1",
                                              "description": SAMPLE_JOB})
    job_id = r.json()["id"]
    assert client.post("/api/applications", json={"job_id": job_id}).status_code == 422  # CV not verified yet

    assert client.post(f"/api/cv/{cv['id']}/verify").json()["status"] == "verified"
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["match"]["score"] >= 60
    assert any(m["requirement"] == "Creo" for m in job["match"]["result"]["missing_requirements"])

    app = client.post("/api/applications", json={"job_id": job_id}).json()
    assert app["status"] == "ready_for_review"
    assert app["cv_guard"]["passed"]

    # Cannot apply before approval.
    assert client.post(f"/api/applications/{app['id']}/apply", json={"mode": "manual"}).status_code == 409
    # Cannot approve without confirming review / answering questions.
    assert client.post(f"/api/applications/{app['id']}/approve", json={"confirm_reviewed": False}).status_code == 422

    answers = [{**a, "answer": a["answer"] or "Yes", "skip": False} for a in app["answers"]]
    app = client.put(f"/api/applications/{app['id']}/review", json={"answers": answers}).json()
    # An edit that invents a skill is caught on save and blocks approval.
    bad_cv = app["tailored_cv"]
    bad_cv["skills"].append("Kubernetes")
    app = client.put(f"/api/applications/{app['id']}/review", json={"tailored_cv": bad_cv}).json()
    assert not app["cv_guard"]["passed"]
    assert client.post(f"/api/applications/{app['id']}/approve", json={"confirm_reviewed": True}).status_code == 422
    bad_cv["skills"].remove("Kubernetes")
    app = client.put(f"/api/applications/{app['id']}/review", json={"tailored_cv": bad_cv}).json()

    app = client.post(f"/api/applications/{app['id']}/approve", json={"confirm_reviewed": True}).json()
    assert app["status"] == "approved" and app["approval_valid"]

    # Changing the CV format after approval also revokes approval.
    app = client.put(f"/api/applications/{app['id']}/format", json={"country_code": "DE", "style": "classic"}).json()
    assert app["status"] == "ready_for_review" and app["cv_format"]["country_code"] == "DE"
    app = client.post(f"/api/applications/{app['id']}/approve", json={"confirm_reviewed": True}).json()

    # Editing after approval revokes it.
    app = client.put(f"/api/applications/{app['id']}/review", json={"cover_letter": app["cover_letter"] + "\n"}).json()
    assert app["status"] == "ready_for_review"
    app = client.post(f"/api/applications/{app['id']}/approve", json={"confirm_reviewed": True}).json()

    app = client.post(f"/api/applications/{app['id']}/apply", json={"mode": "manual"}).json()
    assert app["status"] == "needs_user_action"
    app = client.post(f"/api/applications/{app['id']}/submitted", json={"method": "manual"}).json()
    assert app["status"] == "submitted"
    app = client.post(f"/api/applications/{app['id']}/events",
                      json={"status": "interviewing", "kind": "interview", "title": "Technical round"}).json()
    assert app["status"] == "interviewing"
    assert client.get(f"/api/applications/{app['id']}/documents/cv_pdf").content.startswith(b"%PDF")
    dash = client.get("/api/dashboard").json()
    assert dash["interviews"] == 1 and dash["interview_rate"] == 100
    r = client.post("/api/companies", json={"name": "DHL", "countries": ["Germany"]})
    assert r.json()["name"] == "DHL Group"
    assert client.get("/api/companies").json()[0]["careers_url"].startswith("https://")
    assert client.get(f"/api/cv/{cv['id']}/strength").json()["items"]


def test_other_users_cannot_see_data(client):
    client.post("/api/auth/logout")
    r = client.post("/api/auth/register", json={"email": "other@example.com", "password": "another-long-password"})
    if r.status_code == 403:  # registration closed by env
        pytest.skip("registration disabled")
    assert client.get("/api/applications/1").status_code == 404
    assert client.get("/api/jobs/1").status_code == 404


def test_account_export_report_and_delete(client):
    client.post("/api/auth/logout")
    r = client.post("/api/auth/register", json={"email": "leaver@example.com", "password": "leaver-password-1"})
    if r.status_code == 403:
        pytest.skip("registration disabled")
    client.post("/api/cv/upload", files={"file": ("cv.txt", SAMPLE_CV.encode(), "text/plain")})
    export = client.get("/api/auth/export").json()
    assert export["account"]["email"] == "leaver@example.com" and export["master_cvs"]
    assert client.post("/api/auth/delete-account", json={"password": "wrong", "confirm": "DELETE"}).status_code == 400
    assert client.post("/api/auth/delete-account",
                       json={"password": "leaver-password-1", "confirm": "DELETE"}).json()["ok"]
    assert client.post("/api/auth/login", json={"email": "leaver@example.com",
                                                 "password": "leaver-password-1"}).status_code == 401
    assert client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"}).json()["ok"]


def test_plans_rewards_and_referrals(client):
    client.post("/api/auth/logout")
    r = client.post("/api/auth/register", json={"email": "inviter@example.com", "password": "inviter-password-1"})
    if r.status_code == 403:
        pytest.skip("registration disabled")
    st = client.get("/api/billing/status").json()
    assert st["plan"] == "free" and st["show_ads"] and st["referral_code"]
    before = st["drafts_per_day"]
    st2 = client.post("/api/billing/reward-ad").json()
    assert st2["drafts_per_day"] == before + st2["reward_ad_bonus"]
    client.post("/api/billing/reward-ad")
    assert client.post("/api/billing/reward-ad").status_code == 429  # daily cap
    code = st["referral_code"]
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": "invitee@example.com", "password": "invitee-password-1", "ref": code})
    assert client.get("/api/billing/status").json()["plan"] == "pro"
    assert client.post("/api/billing/revenuecat", json={"event": {}}).status_code == 401
