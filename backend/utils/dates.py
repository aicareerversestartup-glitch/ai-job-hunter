"""Parse the loose date strings found in CVs and compute experience durations."""
from __future__ import annotations

import re
from datetime import date

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
PRESENT_WORDS = {"present", "current", "now", "ongoing", "till date", "date", "today"}


def parse_cv_date(value: str | None, *, end: bool = False, today: date | None = None) -> date | None:
    """Return a date for strings like 'Jan 2021', '01/2021', '2021' or 'Present'."""
    if not value:
        return None
    today = today or date.today()
    text = value.strip().lower().rstrip(".")
    if text in PRESENT_WORDS:
        return today
    m = re.match(r"([a-z]{3})[a-z]*\.?\s*,?\s*(\d{4})$", text)
    if m and m.group(1) in _MONTHS:
        return date(int(m.group(2)), _MONTHS[m.group(1)], 1)
    m = re.match(r"(\d{1,2})[/.-](\d{4})$", text)
    if m and 1 <= int(m.group(1)) <= 12:
        return date(int(m.group(2)), int(m.group(1)), 1)
    m = re.match(r"(\d{4})$", text)
    if m:
        return date(int(m.group(1)), 12 if end else 1, 1)
    return None


def months_between(start: date, end: date) -> int:
    return max(0, (end.year - start.year) * 12 + (end.month - start.month) + 1)


def total_experience_months(ranges: list[tuple[str, str]], today: date | None = None) -> int:
    """Total months covered by the given (start, end) ranges, counting overlaps once."""
    intervals: list[tuple[date, date]] = []
    for start_s, end_s in ranges:
        start = parse_cv_date(start_s, today=today)
        end = parse_cv_date(end_s, end=True, today=today) if end_s else None
        if start and end and end >= start:
            intervals.append((start, end))
    if not intervals:
        return 0
    intervals.sort()
    merged = [intervals[0]]
    for start, end in intervals[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return sum(months_between(s, e) for s, e in merged)
