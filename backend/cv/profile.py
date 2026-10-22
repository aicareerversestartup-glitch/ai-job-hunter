"""The personal/professional profile the user enters. Together with the Master CV this is the only
source of truth for generated documents and application answers."""
from __future__ import annotations

from pydantic import BaseModel, Field


class CandidateProfile(BaseModel):
    full_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin_url: str = ""
    github_url: str = ""
    portfolio_url: str = ""
    headline: str = ""
    notice_period: str = ""  # e.g. "30 days", "Immediate"
    earliest_start_date: str = ""
    salary_expectation: str = ""  # free text, e.g. "₹12 LPA" or "$95,000"
    current_salary: str = ""  # optional; only used if the user fills it
    work_authorized_countries: list[str] = Field(default_factory=list)
    needs_sponsorship_countries: list[str] = Field(default_factory=list)
    willing_to_relocate: bool = False
    willing_to_travel: str = ""
    pronouns: str = ""
    # Personal details some countries expect on a CV (shown only where the country format uses them).
    date_of_birth: str = ""  # free text as you want it printed, e.g. 14.03.1995
    nationality: str = ""
    visa_status: str = ""  # e.g. "Employment Visa – Transferable", "EU Blue Card eligible"
    driving_licence: str = ""
    photo_path: str = ""  # set by the photo upload endpoint
    include_photo: bool = True  # use the photo where the country format expects one
    referees: list[dict] = Field(default_factory=list)  # {name, title, company, email, phone, relationship}
    custom_layouts: list[dict] = Field(default_factory=list)  # learned from sample CVs (structure only)
    # Shown under the contact details only for jobs in countries where you aren't authorized to work.
    relocation_statement: str = ""  # e.g. "Open to international relocation with visa sponsorship."
    passport_status: str = ""  # e.g. "Valid Indian Passport"
    # Answers the user has written once and wants reused verbatim (question -> answer).
    saved_answers: dict[str, str] = Field(default_factory=dict)
    # Voluntary self-identification questions default to declining.
    eeo_default: str = "I prefer not to say"

    def evidence_text(self) -> str:
        """Profile statements phrased so the truthfulness guard can match claims against them."""
        lines = [self.full_name, self.location, self.headline]
        for country in self.work_authorized_countries:
            lines.append(f"Authorized to work in {country}. Work authorization: {country}. Right to work in {country}.")
        for country in self.needs_sponsorship_countries:
            lines.append(f"Requires visa sponsorship in {country}.")
        if self.salary_expectation:
            lines.append(f"Salary expectation: {self.salary_expectation}")
        if self.current_salary:
            lines.append(f"Current salary: {self.current_salary}")
        if self.nationality:
            lines.append(f"Nationality: {self.nationality}")
        if self.visa_status:
            lines.append(f"Visa status: {self.visa_status}")
        if self.relocation_statement:
            lines.append(self.relocation_statement)
        if self.notice_period:
            lines.append(f"Notice period: {self.notice_period}")
        lines += [f"{q}\n{a}" for q, a in self.saved_answers.items()]
        return "\n".join(l for l in lines if l)

    def summary_for_prompt(self) -> str:
        data = self.model_dump(exclude={"saved_answers", "current_salary", "photo_path", "custom_layouts", "referees"})
        return "\n".join(f"{k}: {v}" for k, v in data.items() if v not in ("", [], None, False))
