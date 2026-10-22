"""Split a job description into the parts a candidate reads: about, responsibilities,
requirements, nice-to-have, benefits. Heuristic and display-only (matching uses requirements.py)."""
from __future__ import annotations

import re

SECTION_PATTERNS: list[tuple[str, str]] = [
    ("nice_to_have", r"nice[- ]to[- ]have|preferred|bonus|desirable|good to have|plus points|advantageous"),
    ("requirements", r"requirements|qualifications|must[- ]have|what you('ll)? (need|bring)|who you are|about you|"
                     r"what we('re)? looking for|skills (and|&) experience|your profile|eligibility|essential"),
    ("responsibilities", r"responsibilities|what you('ll)? do|your role|the role|key duties|duties|day[- ]to[- ]day|"
                         r"your tasks|accountabilities|key result areas|job purpose|in this role"),
    ("benefits", r"benefits|perks|what we offer|why join|we offer|compensation|rewards"),
    ("about", r"about (us|the company|the team|[A-Z][\w&]+)|who we are|company overview|our story"),
]
LABELS = {"about": "About the company", "responsibilities": "What you'll do", "requirements": "What they require",
          "nice_to_have": "Nice to have", "benefits": "What they offer", "other": "Other details"}


def _heading(line: str) -> str | None:
    text = line.strip().strip(":").strip()
    if not text or len(text) > 70 or text.endswith("."):
        return None
    for key, pattern in SECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return key
    return None


def split_jd(description: str) -> list[dict]:
    sections: dict[str, list[str]] = {}
    order: list[str] = []
    current = "other"
    for raw in (description or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        key = _heading(line)
        if key:
            current = key
            continue
        bullet = re.sub(r"^[-•*·▪●–]\s*", "", line)
        if current not in sections:
            sections[current] = []
            order.append(current)
        sections[current].append(bullet)
    return [{"key": k, "label": LABELS[k], "lines": sections[k]} for k in order]
