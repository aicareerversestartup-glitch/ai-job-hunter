"""Structured CV representation.

The Master CV is parsed into ``CVData`` once and stored alongside the original file.
Every tailored CV is also a ``CVData`` instance, which lets the truthfulness guard compare
the two field-by-field instead of guessing from free text.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ContactInfo(BaseModel):
    full_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    links: list[str] = Field(default_factory=list)


class ExperienceItem(BaseModel):
    employer: str
    title: str
    location: str = ""
    start: str = ""  # free text as written in the CV, e.g. "Jan 2021"
    end: str = ""  # "Present" allowed
    employment_type: str = ""  # "" (permanent) | contract | consulting | freelance | internship
    bullets: list[str] = Field(default_factory=list)


class EducationItem(BaseModel):
    institution: str
    degree: str = ""
    field: str = ""
    start: str = ""
    end: str = ""
    details: list[str] = Field(default_factory=list)


class ProjectItem(BaseModel):
    name: str
    description: str = ""
    bullets: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    link: str = ""


class CVData(BaseModel):
    contact: ContactInfo = Field(default_factory=ContactInfo)
    headline: str = ""
    summary: str = ""
    experience: list[ExperienceItem] = Field(default_factory=list)
    education: list[EducationItem] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    other_sections: dict[str, list[str]] = Field(default_factory=dict)

    def all_text(self) -> str:
        """Every word the candidate has written, used as the evidence base for claims."""
        parts: list[str] = [self.headline, self.summary]
        for exp in self.experience:
            parts += [exp.employer, exp.title, exp.location, *exp.bullets]
        for edu in self.education:
            parts += [edu.institution, edu.degree, edu.field, *edu.details]
        for proj in self.projects:
            parts += [proj.name, proj.description, *proj.bullets, *proj.technologies]
        parts += self.skills + self.certifications + self.languages
        for lines in self.other_sections.values():
            parts += lines
        return "\n".join(p for p in parts if p)
