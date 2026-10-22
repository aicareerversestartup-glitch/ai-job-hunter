"""X-Y-Z bullet coach: "Accomplished [X] as measured by [Y] by doing [Z]".

For bullets without any number it proposes a template with blanks ([__]) for the user to fill
with real figures. It never fills the blanks; a Master CV with unfilled blanks cannot be verified.
"""
from __future__ import annotations

import re

PLACEHOLDER = "[__]"
PLACEHOLDER_RE = re.compile(r"\[\s*_+\s*\]")
NUMBER_RE = re.compile(r"\d")

TEMPLATES: list[tuple[str, str]] = [
    (r"\b(implement|launch|set ?up|setting up|commission|roll ?out|go-live|migrat|open(ed|ing) (a |the )?new)",
     "Delivered {rest} within [__] months, on [__]% of budget, achieving [result]"),
    (r"\b(team|staff|people|supervis|associates|workforce|shift)", "Led a team of [__] {rest}, achieving [__]% on [KPI]"),
    (r"\b(cost|budget|opex|spend|expense|saving)", "{verb_rest}, reducing costs by [__]% ([__] per year) within [__] months"),
    (r"\b(vendor|supplier|carrier|3pl|transporter|negotiat)", "{verb_rest} across [__] vendors, saving [__] through [how]"),
    (r"\b(inventory|stock|warehouse|sku)", "{verb_rest} for [__] SKUs / [__] sq ft, improving inventory accuracy to [__]%"),
    (r"\b(deliver|dispatch|order|shipment|fulfil|fulfill|otif|on-time)", "{verb_rest}, raising OTIF from [__]% to [__]% across [__] orders per day"),
    (r"\b(process|lean|kaizen|six sigma|5s|improv|streamlin)", "{verb_rest}, cutting turnaround time by [__]% using [method]"),
]
DEFAULT = "{verb_rest}, improving [metric] by [__]% within [__] months"


def needs_numbers(bullet: str) -> bool:
    return not NUMBER_RE.search(bullet)


FILLER_RE = re.compile(r"^(responsible for|in charge of|handled|handling|managing|managed|worked on|involved in)\s+",
                       re.IGNORECASE)
VAGUE_TAIL_RE = re.compile(r"\s*(,|and)\s*(reducing|reduce|cutting|lowering|improving|improve)\s+(the\s+)?"
                           r"(costs?|efficiency|performance)$", re.IGNORECASE)


def suggest(bullet: str) -> str | None:
    text = bullet.strip().rstrip(".")
    if not text or not needs_numbers(text):
        return None
    core = text
    stripped = False
    while FILLER_RE.match(core):
        core = FILLER_RE.sub("", core, count=1)
        stripped = True
    core = VAGUE_TAIL_RE.sub("", core)
    lowered = text.lower()
    verb_rest = f"Managed {core[0].lower() + core[1:]}" if stripped else core
    for pattern, template in TEMPLATES:
        if re.search(pattern, lowered):
            rest = re.sub(r"^(led|managed|leading|managing|supervised)\s+(a\s+)?(team\s+(of\s+)?)?", "", core,
                          flags=re.IGNORECASE)
            return template.format(rest=rest, verb_rest=verb_rest) + "."
    return DEFAULT.format(verb_rest=verb_rest) + "."


def has_placeholders(text: str) -> bool:
    return bool(PLACEHOLDER_RE.search(text) or re.search(r"\[(KPI|how|method|metric|result|project)\]", text))
