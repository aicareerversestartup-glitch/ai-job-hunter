"""Database tables (SQLModel / SQLAlchemy). Works on SQLite (dev) and PostgreSQL (prod)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Column, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def JSONField(default_factory=dict, **kwargs):  # noqa: N802 - reads like a type
    return Field(default_factory=default_factory, sa_column=Column(JSON, nullable=False), **kwargs)


def TextField(default: str = ""):  # noqa: N802
    return Field(default=default, sa_column=Column(Text, nullable=False, default=default))


class User(SQLModel, table=True):
    __tablename__ = "users"
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True, max_length=320)
    password_hash: str
    full_name: str = ""
    is_active: bool = True
    token_version: int = 0  # bump to revoke every outstanding token
    created_at: datetime = Field(default_factory=utcnow)
    # Monetization
    plan: str = "free"  # free | pro
    plan_expires_at: Optional[datetime] = None  # None with plan=pro means lifetime
    plan_source: str = ""  # store | referral | admin
    referral_code: Optional[str] = Field(default=None, index=True, unique=True, max_length=16)
    referred_by: Optional[int] = Field(default=None, foreign_key="users.id")


class Profile(SQLModel, table=True):
    __tablename__ = "profiles"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", unique=True, index=True)
    data: dict = JSONField()  # backend.cv.profile.CandidateProfile
    preferences: dict = JSONField()  # backend.jobs.matcher.JobPreferences
    updated_at: datetime = Field(default_factory=utcnow)


class MasterCV(SQLModel, table=True):
    """The original upload is stored once and never modified. Structured data is versioned:
    once a version is verified it is frozen, and corrections create a new version."""
    __tablename__ = "master_cvs"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    version: int = 1
    parent_id: Optional[int] = Field(default=None, foreign_key="master_cvs.id")
    original_filename: str
    stored_path: str  # read-only copy of the uploaded file
    sha256: str = Field(index=True)
    raw_text: str = TextField()
    parsed_data: dict = JSONField()  # automatic parse, never edited
    data: dict = JSONField()  # user-reviewed CVData: the verified fact base once status == verified
    parse_method: str = ""
    parse_notes: list = JSONField(default_factory=list)
    status: str = "needs_review"  # needs_review | verified | superseded
    is_active: bool = True
    created_at: datetime = Field(default_factory=utcnow)
    verified_at: Optional[datetime] = None


class JobSource(SQLModel, table=True):
    __tablename__ = "job_sources"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    kind: str  # greenhouse | lever | ashby | workable | remotive | arbeitnow | adzuna | rss
    identifier: str = ""  # board token, company slug, feed URL, or "" for keyword-search sources
    label: str = ""
    enabled: bool = True
    last_run_at: Optional[datetime] = None
    last_status: str = ""
    last_error: str = ""
    last_count: int = 0
    options: dict = JSONField()  # e.g. {"countries": ["Germany"], "company": "DHL Group"}


class Job(SQLModel, table=True):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("user_id", "source", "source_job_id", name="uq_job_source"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    source: str = Field(index=True)
    source_job_id: str
    fingerprint: str = Field(index=True)
    url: str
    apply_url: str = ""
    title: str
    company: str = Field(index=True)
    location: str = ""
    country: str = ""
    remote_type: str = "unknown"
    employment_type: str = "unknown"
    seniority: str = "unknown"
    department: str = ""
    description_text: str = TextField()
    posted_at: Optional[datetime] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: str = ""
    salary_period: str = ""
    company_domain: str = ""
    discovered_at: datetime = Field(default_factory=utcnow, index=True)
    last_seen_at: datetime = Field(default_factory=utcnow)
    quality: dict = JSONField()
    risk_level: str = Field(default="low", index=True)
    status: str = Field(default="new", index=True)  # new | shortlisted | dismissed | applied | closed
    also_seen_on: list = JSONField(default_factory=list)  # duplicate postings merged into this one
    raw: dict = JSONField()


class JobMatch(SQLModel, table=True):
    __tablename__ = "job_matches"
    __table_args__ = (UniqueConstraint("job_id", "master_cv_id", name="uq_match"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    job_id: int = Field(foreign_key="jobs.id", index=True)
    master_cv_id: int = Field(foreign_key="master_cvs.id")
    score: int = Field(index=True)
    priority: int = Field(default=99999, index=True)  # lower = shown first (country list, your roles, CV roles)
    recommendation: str = ""
    result: dict = JSONField()
    ai_assessment: str = TextField()
    created_at: datetime = Field(default_factory=utcnow)


class Application(SQLModel, table=True):
    __tablename__ = "applications"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    job_id: int = Field(foreign_key="jobs.id", index=True)
    master_cv_id: int = Field(foreign_key="master_cvs.id")
    status: str = Field(default="draft", index=True)
    match_score: int = 0
    tailored_cv: dict = JSONField()
    cv_guard: dict = JSONField()
    cover_letter: str = TextField()
    cover_guard: dict = JSONField()
    cv_format: dict = JSONField()  # {"country_code": "DE", "style": "modern", "custom_layout_id": ""}
    format_notes: list = JSONField(default_factory=list)  # e.g. bullets left out to fit the page limit
    answers: list = JSONField(default_factory=list)
    generation_notes: list = JSONField(default_factory=list)
    generation_method: dict = JSONField()
    approved_at: Optional[datetime] = None
    approved_snapshot: str = ""  # hash of exactly what the user approved
    submitted_at: Optional[datetime] = None
    submission_method: str = ""  # manual | assisted | automated
    apply_url: str = ""
    blocker: dict = JSONField()
    notes: str = TextField()
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ApplicationEvent(SQLModel, table=True):
    __tablename__ = "application_events"
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="applications.id", index=True)
    kind: str  # status_change | interview | note | blocker | document
    from_status: str = ""
    to_status: str = ""
    details: dict = JSONField()
    occurred_at: datetime = Field(default_factory=utcnow)
    created_at: datetime = Field(default_factory=utcnow)


class AISettings(SQLModel, table=True):
    __tablename__ = "ai_settings"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", unique=True, index=True)
    provider: str = "none"
    model: str = ""
    base_url: str = ""
    api_key_encrypted: str = ""
    temperature: float = 0.2
    updated_at: datetime = Field(default_factory=utcnow)


class DiscoveryRun(SQLModel, table=True):
    __tablename__ = "discovery_runs"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    trigger: str = "manual"  # manual | schedule
    status: str = "running"  # running | completed | failed
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: Optional[datetime] = None
    stats: dict = JSONField()
    errors: list = JSONField(default_factory=list)


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    action: str = Field(index=True)
    entity: str = ""
    entity_id: Optional[int] = None
    details: dict = JSONField()
    created_at: datetime = Field(default_factory=utcnow, index=True)


class InboxSettings(SQLModel, table=True):
    """Read-only IMAP access used to spot interview / rejection / offer emails."""
    __tablename__ = "inbox_settings"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", unique=True, index=True)
    provider: str = "gmail"
    host: str = ""
    port: int = 993
    username: str = ""
    password_encrypted: str = ""
    enabled: bool = True
    last_checked_at: Optional[datetime] = None
    last_status: str = ""
    last_error: str = ""
    seen_message_ids: list = JSONField(default_factory=list)


class BonusCredit(SQLModel, table=True):
    """Extra applications for one day, e.g. earned by watching a rewarded ad."""
    __tablename__ = "bonus_credits"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    kind: str  # rewarded_ad
    amount: int
    valid_on: str = Field(index=True)  # YYYY-MM-DD (UTC)
    created_at: datetime = Field(default_factory=utcnow)
