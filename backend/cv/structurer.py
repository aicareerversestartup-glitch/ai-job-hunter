"""Turn raw CV text into ``CVData`` using deterministic heuristics.

The heuristic parser never adds information: every value it outputs is a substring of the
uploaded document. Parsing is imperfect for unusual layouts, so the UI shows the structured
result for the user to correct and confirm before it becomes the verified fact base.
An optional LLM pass (``backend.ai.extraction``) can improve the structure, and its output is
checked against the raw text by the same truthfulness guard.
"""
from __future__ import annotations

import re

from backend.cv.schema import ContactInfo, CVData, EducationItem, ExperienceItem, ProjectItem
from backend.utils.text import clean_whitespace

SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "summary": ("summary", "professional summary", "profile", "about me", "objective", "career objective",
                "career summary", "professional profile"),
    "experience": ("experience", "work experience", "professional experience", "employment",
                   "employment history", "work history", "career history", "internships", "internship"),
    "education": ("education", "academic background", "academics", "qualifications",
                  "educational qualifications", "academic qualifications"),
    "skills": ("skills", "technical skills", "core skills", "key skills", "core competencies",
               "competencies", "technologies", "tools", "tools & technologies", "skills & tools"),
    "certifications": ("certifications", "certificates", "licenses", "licences", "certifications & licenses",
                       "courses", "training"),
    "projects": ("projects", "academic projects", "personal projects", "key projects"),
    "languages": ("languages", "spoken languages"),
}
_HEADING_LOOKUP = {alias: key for key, aliases in SECTION_ALIASES.items() for alias in aliases}

MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
DATE = rf"(?:{MONTH}\s*,?\s*\d{{4}}|\d{{1,2}}[/.-]\d{{4}}|\d{{4}})"
DATE_RANGE_RE = re.compile(
    rf"(?P<start>{DATE})\s*(?:-|–|—|to|until)\s*(?P<end>{DATE}|present|current|now|ongoing|till date|date)",
    re.IGNORECASE,
)
SINGLE_DATE_RE = re.compile(DATE, re.IGNORECASE)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
URL_RE = re.compile(r"(?:https?://|www\.)\S+|(?:linkedin\.com|github\.com)/\S+", re.IGNORECASE)
BULLET_RE = re.compile(r"^\s*(?:[-•▪●◦*·‣–]|\d+[.)])\s+")

TITLE_WORDS = (
    "engineer", "developer", "manager", "analyst", "intern", "lead", "designer", "consultant", "specialist",
    "director", "officer", "associate", "executive", "technician", "scientist", "architect", "administrator",
    "coordinator", "head", "supervisor", "assistant", "trainee", "programmer", "researcher", "teacher",
    "lecturer", "accountant", "representative", "owner", "founder", "president", "vp", "partner", "advisor",
    "operator", "inspector", "planner", "buyer", "editor", "writer", "nurse", "therapist", "agent", "apprentice",
)
INSTITUTION_WORDS = ("university", "college", "institute", "school", "academy", "polytechnic", "iit", "nit",
                     "iiit", "iim", "universidad", "université", "hochschule")
DEGREE_RE = re.compile(
    r"\b(b\.?\s?tech|m\.?\s?tech|b\.?\s?e\b|m\.?\s?e\b|b\.?\s?sc|m\.?\s?sc|bsc|msc|b\.?\s?a\b|m\.?\s?a\b|mba|bba|bca|mca|"
    r"ph\.?\s?d|doctorate|bachelor[a-z']*|master[a-z']*|associate degree|diploma|high school|hsc|ssc|"
    r"a[- ]levels?|b\.?\s?com|m\.?\s?com|llb|llm|md\b|mbbs)",
    re.IGNORECASE,
)


def structure_cv(raw_text: str) -> CVData:
    text = clean_whitespace(raw_text)
    lines = [line for line in text.splitlines()]
    sections = _split_sections(lines)
    cv = CVData()
    cv.contact = _parse_contact(sections.get("_header", []), text)
    header_rest = [l for l in sections.get("_header", [])[1:] if not _is_contact_line(l)]
    if header_rest:
        cv.headline = header_rest[0] if len(header_rest[0]) <= 120 else ""
    cv.summary = " ".join(l.strip() for l in sections.get("summary", []) if l.strip())
    cv.experience = _parse_experience(sections.get("experience", []))
    cv.education = _parse_education(sections.get("education", []))
    cv.skills = _parse_list(sections.get("skills", []))
    cv.certifications = _parse_lines(sections.get("certifications", []))
    cv.projects = _parse_projects(sections.get("projects", []))
    cv.languages = _parse_list(sections.get("languages", []))
    for key, value in sections.items():
        if key.startswith("other:") and value:
            cv.other_sections[key.split(":", 1)[1]] = _parse_lines(value)
    return cv


def _heading_key(line: str) -> str | None:
    candidate = line.strip().strip(":").strip()
    if not candidate or len(candidate) > 45 or BULLET_RE.match(line):
        return None
    lowered = re.sub(r"[^a-z& ]", "", candidate.lower()).strip()
    if lowered in _HEADING_LOOKUP:
        return _HEADING_LOOKUP[lowered]
    # An ALL-CAPS short line is very likely a heading we don't know about.
    letters = [c for c in candidate if c.isalpha()]
    if letters and all(c.isupper() for c in letters) and 1 <= len(candidate.split()) <= 4 \
            and not EMAIL_RE.search(candidate) and not SINGLE_DATE_RE.search(candidate):
        return f"other:{candidate.title()}"
    return None


def _split_sections(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {"_header": []}
    current = "_header"
    for line in lines:
        key = _heading_key(line)
        if key and not (current == "_header" and not sections["_header"]):
            current = key
            sections.setdefault(current, [])
            continue
        if key and current == "_header" and not sections["_header"]:
            # The very first line is almost always the person's name, even in capitals.
            sections["_header"].append(line)
            continue
        sections.setdefault(current, []).append(line)
    return sections


def _is_contact_line(line: str) -> bool:
    return bool(EMAIL_RE.search(line) or URL_RE.search(line) or (PHONE_RE.search(line) and len(line) < 60))


def _parse_contact(header: list[str], full_text: str) -> ContactInfo:
    contact = ContactInfo()
    email = EMAIL_RE.search(full_text)
    contact.email = email.group(0) if email else ""
    head_text = "\n".join(header) or full_text[:600]
    phone = PHONE_RE.search(head_text)
    if phone and sum(c.isdigit() for c in phone.group(0)) >= 8:
        contact.phone = phone.group(0).strip()
    contact.links = list(dict.fromkeys(m.group(0).rstrip(".,;)") for m in URL_RE.finditer(head_text)))
    for line in header:
        stripped = line.strip()
        if stripped and not _is_contact_line(stripped) and len(stripped.split()) <= 5:
            contact.full_name = stripped
            break
    for line in header:
        for part in re.split(r"[|•·]", line):
            part = part.strip()
            if part and not _is_contact_line(part) and part != contact.full_name and "," in part \
                    and len(part) < 60 and not any(w in part.lower() for w in TITLE_WORDS):
                contact.location = part
                break
        if contact.location:
            break
    return contact


def _strip_bullet(line: str) -> str:
    return BULLET_RE.sub("", line).strip()


def _split_header_parts(text: str) -> list[str]:
    if "|" in text:
        # "Assistant Manager - Warehouse | Snowman Logistics": the pipe is the real separator.
        parts = re.split(r"\s*\|\s*|\s+@\s+", text)
        return [p.strip(" ,|-–—") for p in parts if p and p.strip(" ,|-–—")]
    parts = re.split(r"\s+(?:\||—|–|-|@|at)\s+|\s*\|\s*|,\s+(?=[A-Z])", text)
    return [p.strip(" ,|-–—") for p in parts if p and p.strip(" ,|-–—")]


def _looks_like_title(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(rf"\b{w}", lowered) for w in TITLE_WORDS)


def _parse_experience(lines: list[str]) -> list[ExperienceItem]:
    entries: list[ExperienceItem] = []
    header_block: list[str] = []
    bullets: list[str] = []

    def flush():
        if not header_block and not bullets:
            return
        entry = _build_experience(header_block, bullets)
        if entry:
            entries.append(entry)

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        is_bullet = bool(BULLET_RE.match(raw))
        if is_bullet:
            bullets.append(_strip_bullet(raw))
            continue
        # A non-bullet line after bullets starts a new entry when it looks like a header.
        if bullets and (DATE_RANGE_RE.search(line) or _looks_like_title(line) or len(line) < 70):
            flush()
            header_block, bullets = [], []
        if not bullets:
            header_block.append(line)
        else:
            bullets[-1] = f"{bullets[-1]} {line}"  # wrapped bullet continuation
    flush()
    return entries


def _build_experience(header: list[str], bullets: list[str]) -> ExperienceItem | None:
    joined = " | ".join(header)
    start = end = ""
    match = DATE_RANGE_RE.search(joined)
    if match:
        start, end = match.group("start").strip(), match.group("end").strip()
        joined = (joined[: match.start()] + joined[match.end():]).strip(" |,()")
    parts = [p for p in _split_header_parts(joined) if p]
    title = employer = location = ""
    for part in parts:
        if not title and _looks_like_title(part):
            title = part
        elif not employer:
            employer = part
        elif not location and ("," in part or len(part.split()) <= 3):
            location = part
    if not title and len(parts) >= 2:
        title = parts[1] if employer == parts[0] else parts[0]
    if not employer and not title:
        return None
    # Long header remainders that are really sentences belong to the bullets.
    return ExperienceItem(employer=employer or "(employer not detected)", title=title or "(title not detected)",
                          location=location, start=start, end=end, bullets=bullets)


def _parse_education(lines: list[str]) -> list[EducationItem]:
    items: list[EducationItem] = []
    current: EducationItem | None = None
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if BULLET_RE.match(raw) and current is not None:
            current.details.append(_strip_bullet(raw))
            continue
        lowered = line.lower()
        has_inst = any(re.search(rf"\b{w}\b", lowered) for w in INSTITUTION_WORDS)
        degree = DEGREE_RE.search(line)
        dates = DATE_RANGE_RE.search(line)
        single = SINGLE_DATE_RE.findall(line)
        if has_inst or degree:
            if current is None or (has_inst and current.institution) or (degree and current.degree):
                current = EducationItem(institution="")
                items.append(current)
            content = line
            if dates:
                current.start, current.end = dates.group("start"), dates.group("end")
                content = (line[: dates.start()] + line[dates.end():])
            elif single and not current.end:
                current.end = single[-1]
                content = line.replace(single[-1], "")
            content = re.sub(r"\(\s*[-–,]?\s*\)", "", content)
            for part in _split_header_parts(content):
                part_l = part.lower()
                if any(re.search(rf"\b{w}\b", part_l) for w in INSTITUTION_WORDS) and not current.institution:
                    current.institution = part
                elif DEGREE_RE.search(part) and not current.degree:
                    degree_text, _, field = part.partition(" in ")
                    current.degree = degree_text.strip()
                    current.field = field.strip()
                elif part and not current.field and current.degree and not DEGREE_RE.search(part):
                    current.field = part
        elif current is not None:
            current.details.append(line)
    for item in items:
        if not item.institution:
            item.institution = "(institution not detected)"
    return items


def _parse_list(lines: list[str]) -> list[str]:
    values: list[str] = []
    for raw in lines:
        line = _strip_bullet(raw)
        if not line:
            continue
        if ":" in line and len(line.split(":", 1)[0]) < 35:
            line = line.split(":", 1)[1]
        for item in re.split(r"[,;|•·]|\s{2,}|\s/\s", line):
            item = item.strip(" .")
            if item and len(item) <= 60:
                values.append(item)
    return list(dict.fromkeys(values))


def _parse_lines(lines: list[str]) -> list[str]:
    return [s for s in (_strip_bullet(l) for l in lines) if s]


def _parse_projects(lines: list[str]) -> list[ProjectItem]:
    projects: list[ProjectItem] = []
    current: ProjectItem | None = None
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if BULLET_RE.match(raw) and current is not None:
            current.bullets.append(_strip_bullet(raw))
            continue
        if current is None or len(line) < 90:
            pieces = re.split(r"\s[—–-]\s|:\s", line, maxsplit=1)
            name = pieces[0]
            rest = pieces[1] if len(pieces) > 1 else ""
            current = ProjectItem(name=name.strip(), description=rest.strip())
            tech = re.search(r"(?:tech(?:nologies)?|stack|tools)\s*:\s*(.+)$", line, re.IGNORECASE)
            if tech:
                current.technologies = [t.strip() for t in re.split(r"[,;/]", tech.group(1)) if t.strip()]
            projects.append(current)
        else:
            current.description = (current.description + " " + line).strip()
    return projects
