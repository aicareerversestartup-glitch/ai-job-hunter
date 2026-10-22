"""Extract structured requirements from a job description."""
from __future__ import annotations

import re
from dataclasses import dataclass

from backend.cv.structurer import DEGREE_RE
from backend.jobs.skills_taxonomy import PREFERRED_CUES, REQUIRED_CUES, find_skills

YEARS_REQ_RE = re.compile(
    r"(\d{1,2})\s*(?:\+|plus)?\s*(?:-|–|to)?\s*(\d{1,2})?\s*\+?\s*(?:years?|yrs?)(?:\s+of)?(?:\s+\w+){0,4}\s+"
    r"(?:experience|exp\b)", re.IGNORECASE)
LANGUAGE_REQ_RE = re.compile(
    r"\b(?:fluent|fluency|proficien\w*|native|business[- ]level|working knowledge)\b[^.\n]{0,30}?\b"
    r"(english|german|french|spanish|dutch|italian|portuguese|japanese|mandarin|chinese|arabic|hindi|swedish|polish)\b"
    r"|\b(english|german|french|spanish|dutch|italian|portuguese|japanese|mandarin|chinese|arabic|hindi|swedish|polish)"
    r"\b[^.\n]{0,20}\b(?:fluency|fluent|required|proficiency|c1|c2|b2)\b",
    re.IGNORECASE)
AUTH_REQ_RE = re.compile(
    r"\b(?:must|should) (?:be|have)[^.\n]{0,40}?(?:authori[sz]ed|eligible|right) to work in (?:the )?([A-Z][\w .]+?)"
    r"(?:[.,;\n]| without| and)|\b(?:no|not able to|unable to|cannot|can't|do not) (?:offer |provide )?(?:visa )?sponsor",
    re.IGNORECASE)
CERT_RE = re.compile(r"\b(PMP|CSM|CFA|CPA|ACCA|CISSP|CEH|CCNA|CCNP|PE license|professional engineer|"
                     r"six sigma (?:green|black) belt|AWS Certified[\w ]*|Azure (?:Administrator|Developer)[\w ]*|"
                     r"OSHA[\w ]*|NEBOSH|ISTQB|PRINCE2|ITIL)\b", re.IGNORECASE)

PREFERRED_HEADINGS = re.compile(r"(nice[- ]to[- ]have|preferred|bonus|desirable|plus points|good to have)", re.IGNORECASE)
REQUIRED_HEADINGS = re.compile(r"(requirements|qualifications|must[- ]have|what you('ll)? (need|bring)|"
                               r"who you are|about you|what we('re)? looking for|skills required|eligibility)",
                               re.IGNORECASE)
OTHER_HEADINGS = re.compile(r"^(benefits|perks|what we offer|about us|about the company|our culture|"
                            r"responsibilities|what you('ll)? do|the role|equal opportunity)\b", re.IGNORECASE)

DEGREE_LEVEL = {"phd": 4, "doctorate": 4, "master": 3, "mba": 3, "mtech": 3, "me": 3, "msc": 3, "ma": 3, "mca": 3,
                "mcom": 3, "llm": 3, "bachelor": 2, "btech": 2, "be": 2, "bsc": 2, "ba": 2, "bba": 2, "bca": 2,
                "bcom": 2, "llb": 2, "mbbs": 2, "md": 3, "associate degree": 1, "diploma": 1, "high school": 0,
                "hsc": 0, "ssc": 0, "a level": 0, "a levels": 0}


def degree_level(text: str) -> int:
    key = re.sub(r"[^a-z ]", "", text.lower()).replace(" ", "")
    for name, level in sorted(DEGREE_LEVEL.items(), key=lambda kv: -len(kv[0])):
        if key.startswith(name.replace(" ", "")):
            return level
    return -1


@dataclass
class Requirement:
    kind: str  # skill | experience_years | degree | certification | language | authorization
    value: str
    importance: str  # required | preferred
    evidence: str  # the JD sentence it came from
    years: float | None = None
    level: int | None = None


STRONG_REQUIRED_CUES = ("required", "must", "mandatory", "essential", "minimum")


def _classify_line(line: str, section: str) -> str:
    lowered = line.lower()
    if any(cue in lowered for cue in PREFERRED_CUES):
        return "preferred"
    if section == "preferred":
        # Inside a "nice to have" block only an explicit "must"/"required" upgrades a line.
        return "required" if any(cue in lowered for cue in STRONG_REQUIRED_CUES) else "preferred"
    if any(cue in lowered for cue in REQUIRED_CUES):
        return "required"
    return section


def extract_requirements(description: str) -> list[Requirement]:
    reqs: list[Requirement] = []
    section = "required"  # unlabeled postings: treat mentioned skills as required
    in_other = False
    seen: set[tuple[str, str]] = set()

    def add(req: Requirement) -> None:
        key = (req.kind, req.value.lower())
        if key in seen:
            # Upgrade a preferred requirement if it is also stated as required elsewhere.
            if req.importance == "required":
                for existing in reqs:
                    if (existing.kind, existing.value.lower()) == key:
                        existing.importance = "required"
            return
        seen.add(key)
        reqs.append(req)

    for raw_line in re.split(r"\n|(?<=[.;])\s+(?=[A-Z])", description or ""):
        line = raw_line.strip(" -•*\t")
        if not line:
            continue
        if len(line) < 60 and PREFERRED_HEADINGS.search(line):
            section, in_other = "preferred", False
            continue
        if len(line) < 60 and REQUIRED_HEADINGS.search(line):
            section, in_other = "required", False
            continue
        if len(line) < 60 and OTHER_HEADINGS.search(line):
            in_other = True
            section = "required"
            continue
        importance = _classify_line(line, section)
        if in_other and importance == section:
            # Responsibilities still describe the stack; count those skills as preferred.
            importance = "preferred"
        for skill in find_skills(line):
            add(Requirement("skill", skill, importance, line))
        for m in YEARS_REQ_RE.finditer(line):
            years = float(m.group(1))
            if years <= 30:
                add(Requirement("experience_years", f"{m.group(1)}+ years", importance, line, years=years))
        for m in DEGREE_RE.finditer(line):
            lvl = degree_level(m.group(0))
            if lvl >= 1:
                add(Requirement("degree", m.group(0).strip(), importance, line, level=lvl))
        for m in CERT_RE.finditer(line):
            cert = m.group(0).strip()
            # A certification acronym that is also a known skill (e.g. PMP) is tracked once, as a certification.
            reqs[:] = [r for r in reqs if not (r.kind == "skill" and r.value.lower() == cert.lower())]
            seen.discard(("skill", cert.lower()))
            add(Requirement("certification", cert, importance, line))
        for m in LANGUAGE_REQ_RE.finditer(line):
            lang = (m.group(1) or m.group(2) or "").title()
            if lang:
                add(Requirement("language", lang, importance, line))
        for m in AUTH_REQ_RE.finditer(line):
            country = (m.group(1) or "").strip()
            add(Requirement("authorization", country or "no visa sponsorship", "required", line))
    # Years and degrees in a "preferred" block are softer; everything else stays as classified.
    return reqs
