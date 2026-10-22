"""Request/response models for the HTTP API."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from backend.cv.profile import CandidateProfile
from backend.cv.schema import CVData
from backend.jobs.matcher import JobPreferences


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)
    full_name: str = Field(default="", max_length=200)
    ref: str = Field(default="", max_length=16)  # referral code


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=200)


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str


class ProfileIO(BaseModel):
    profile: CandidateProfile = Field(default_factory=CandidateProfile)
    preferences: JobPreferences = Field(default_factory=JobPreferences)
    auto_discovery: bool = True


class MasterCVOut(BaseModel):
    id: int
    version: int
    original_filename: str
    status: str
    is_active: bool
    parse_method: str
    parse_notes: list
    data: CVData
    parsed_data: CVData
    raw_text: str
    created_at: datetime
    verified_at: datetime | None


class MasterCVSummary(BaseModel):
    id: int
    version: int
    original_filename: str
    status: str
    is_active: bool
    created_at: datetime
    verified_at: datetime | None


class SourceIn(BaseModel):
    kind: str
    identifier: str = Field(default="", max_length=500)
    label: str = Field(default="", max_length=120)
    enabled: bool = True


class SourcePatch(BaseModel):
    identifier: str | None = None
    label: str | None = None
    enabled: bool | None = None


class ManualJobIn(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    company: str = Field(default="", max_length=200)
    location: str = Field(default="", max_length=200)
    url: str = Field(default="", max_length=2000)
    apply_url: str = Field(default="", max_length=2000)
    description: str = Field(min_length=50, max_length=60000)


class ImportUrlIn(BaseModel):
    url: str = Field(max_length=2000)


class JobPatch(BaseModel):
    status: str | None = None  # new | shortlisted | dismissed | closed
    override_risk: bool | None = None  # user confirms a flagged posting is genuine

    @field_validator("status")
    @classmethod
    def _status(cls, v):
        if v is not None and v not in {"new", "shortlisted", "dismissed", "closed", "applied"}:
            raise ValueError("Invalid status")
        return v


class CreateApplicationIn(BaseModel):
    job_id: int
    questions: list[str] | None = None


class ReviewUpdateIn(BaseModel):
    tailored_cv: CVData | None = None
    cover_letter: str | None = Field(default=None, max_length=20000)
    answers: list[dict] | None = None
    notes: str | None = Field(default=None, max_length=20000)


class ApproveIn(BaseModel):
    confirm_reviewed: bool = False
    auto_submit: bool = False


class ApplyIn(BaseModel):
    mode: str = "assist"  # manual | assist | submit


class SubmittedIn(BaseModel):
    method: str = "manual"
    submitted_at: datetime | None = None


class OutcomeIn(BaseModel):
    status: str | None = None  # in_review | interviewing | offer | accepted | rejected | withdrawn
    kind: str = "status_change"  # status_change | interview | note
    occurred_at: datetime | None = None
    title: str = Field(default="", max_length=300)  # e.g. "Technical interview"
    notes: str = Field(default="", max_length=5000)
    location: str = Field(default="", max_length=500)


class AISettingsIn(BaseModel):
    provider: str = "none"
    model: str = Field(default="", max_length=200)
    base_url: str = Field(default="", max_length=500)
    api_key: str | None = Field(default=None, max_length=500)  # None keeps the stored key
    temperature: float = Field(default=0.2, ge=0, le=1)


class AISettingsOut(BaseModel):
    provider: str
    model: str
    base_url: str
    api_key_masked: str
    temperature: float
    source: str  # "user" or "server-default"


class FormatIn(BaseModel):
    country_code: str = Field(max_length=4)
    style: str = Field(default="modern", max_length=20)
    custom_layout_id: str = Field(default="", max_length=40)
    date_precision: str = Field(default="month", max_length=10)  # month | year
    layout: str = Field(default="chronological", max_length=20)  # chronological | hybrid
