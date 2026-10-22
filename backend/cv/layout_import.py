"""Learn a layout from a sample CV the user liked (from the internet or anywhere else).

Only STRUCTURE is kept: which sections appear and in what order, the heading words used, page
count, whether there is a photo, and which personal-detail fields appear. The sample's text is
discarded immediately and never reaches the user's CV.
"""
from __future__ import annotations

import io
import re
import uuid
from pathlib import Path

from backend.cv.parser import CVParseError, extract_text
from backend.cv.structurer import SECTION_ALIASES

KEY_MAP = {"summary": "summary", "experience": "experience", "education": "education", "skills": "skills",
           "certifications": "certifications", "projects": "projects", "languages": "languages"}
EXTRA_HEADINGS = {"references": "referees", "referees": "referees", "interests": "other", "hobbies": "other",
                  "achievements": "other", "awards": "other", "volunteering": "other", "publications": "other"}
PERSONAL_PATTERNS = {"dob": r"date of birth|d\.o\.b|geburtsdatum|born", "nationality": r"nationality|staatsangeh",
                     "visa_status": r"visa|work permit|residency|right to work|iqama",
                     "driving_licence": r"driving licen[cs]e|f[üu]hrerschein"}


def learn_layout(filename: str, data: bytes, name: str = "") -> dict:
    extracted = extract_text(filename, data)
    text = extracted.text
    if len(text) < 80:
        raise CVParseError("Could not read this sample. Use a text-based PDF or a DOCX.")
    order: list[str] = []
    headings: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip().strip(":").strip()
        if not line or len(line) > 45:
            continue
        key = re.sub(r"[^a-z& ]", "", line.lower()).strip()
        section = None
        for canonical, aliases in SECTION_ALIASES.items():
            if key in aliases:
                section = KEY_MAP.get(canonical)
        section = section or EXTRA_HEADINGS.get(key)
        if section and section not in order:
            order.append(section)
            headings[section] = line.title() if line.isupper() else line
    if len(order) < 3:
        raise CVParseError("Couldn't recognise enough section headings in this sample to copy its layout.")
    head = text[:800].lower()
    personal = [k for k, pattern in PERSONAL_PATTERNS.items() if re.search(pattern, head)]
    return {
        "id": uuid.uuid4().hex[:12],
        "name": name or f"From {Path(filename).stem}"[:60],
        "section_order": order,
        "headings": headings,
        "max_pages": max(1, min(extracted.pages, 4)),
        "photo": _has_photo(filename, data),
        "personal_details": personal,
    }


def _has_photo(filename: str, data: bytes) -> bool:
    ext = Path(filename).suffix.lower()
    try:
        if ext == ".pdf":
            from pypdf import PdfReader

            first = PdfReader(io.BytesIO(data)).pages[0]
            return len(list(first.images)) > 0
        if ext == ".docx":
            import docx

            return len(docx.Document(io.BytesIO(data)).inline_shapes) > 0
    except Exception:
        return False
    return False
