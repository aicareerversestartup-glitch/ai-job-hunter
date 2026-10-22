"""CV strength check for experienced (7+ years) operations / supply-chain managers.

It only READS the verified Master CV and reports which kinds of evidence recruiters look for are
present, with the lines that show them. Missing items become questions for the user; the app never
fills in numbers or claims itself.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.cv.schema import CVData
from backend.utils.dates import total_experience_months

CHECKS: list[tuple[str, str, str, str]] = [
    ("team_size", "Team size you led",
     r"\b(led|lead|leading|managed|managing|supervised|headed|oversaw)\b[^.]{0,60}?\b\d{1,4}\+?\s*(-|to)?\s*\d{0,4}\s*"
     r"(people|staff|employees|associates|members|supervisors|engineers|operators|workers|fte|direct reports|reports|"
     r"drivers|pickers|team)|\bteam of\s*\d{1,4}\+?",
     "How many people did you lead (supervisors, staff, labour)? e.g. 'Led a team of 35 across 3 shifts.'"),
    ("pnl", "Budget, P&L or OPEX ownership",
     r"\b(p&l|profit and loss|budget|opex|capex|operating expenditure|cost cent(er|re))\b",
     "Did you own a budget, P&L or OPEX? Give the size if you can, e.g. 'Managed ₹8 Cr annual OPEX budget.'"),
    ("cost", "Cost reduction or savings with a number",
     r"\b(reduc\w*|cut|sav\w*|lower\w*|optimi[sz]\w*)\b[^.]{0,60}?(\d+(\.\d+)?\s?%|[$€£₹]\s?\d|\d+\s?(lakh|lakhs|cr|crore|k|m|million))",
     "Any measurable savings? e.g. 'Reduced freight cost 12% by consolidating carriers.'"),
    ("vendors", "Vendor / supplier / 3PL management",
     r"\b(vendor|vendors|supplier|suppliers|3pl|carrier|carriers|transporter|transporters|contractor)s?\b",
     "Which vendors, suppliers, carriers or 3PLs did you manage, and how many?"),
    ("clients", "Client or stakeholder handling",
     r"\b(client|clients|customer|customers|key account|stakeholder|stakeholders)\b",
     "Which clients or internal stakeholders did you work with (e.g. key accounts, regional heads)?"),
    ("international", "International exposure",
     r"\b(international|global|cross[- ]border|export|import|overseas|multi[- ]country|region(al)?|apac|emea|gcc)\b",
     "Any work with other countries: exports, global clients, overseas suppliers, regional roles?"),
    ("scale", "Scale of operations",
     r"\b\d[\d,.]*\s?(sq\.?\s?ft|sqft|square feet|pallets|skus|orders|shipments|tonnes|tons|teu|trucks|vehicles|"
     r"sites|warehouses|dcs|plants|stores|units)\b",
     "Size of what you ran: warehouse sq ft, SKUs, daily orders, shipments, sites, fleet size."),
    ("tools", "Systems and tools (ERP / WMS / reporting)",
     r"\b(sap|oracle|dynamics|navision|wms|tms|blue yonder|manhattan|excel|power bi|tableau|erp)\b",
     "Which systems do you use daily? ERP (SAP, Oracle, Dynamics), WMS/TMS, Excel, Power BI, Tableau."),
    ("kpis", "KPIs improved",
     r"\b(otif|on[- ]time|fill rate|accuracy|productivity|throughput|turnaround|tat|lead time|inventory turns|"
     r"oee|downtime|damage|shrinkage)\b",
     "Which KPIs did you improve, from what to what? e.g. 'Raised OTIF from 88% to 96%.'"),
]
NUMBER_RE = re.compile(r"\d")


@dataclass
class StrengthReport:
    years: float
    senior: bool
    items: list[dict] = field(default_factory=list)
    quantified_bullets: int = 0
    total_bullets: int = 0
    score: int = 0
    tenure: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def assess(cv: CVData) -> StrengthReport:
    years = total_experience_months([(e.start, e.end) for e in cv.experience]) / 12
    lines = [cv.summary] + [b for e in cv.experience for b in e.bullets] + [p.description for p in cv.projects]
    lines += [", ".join(cv.skills)] if cv.skills else []
    lines = [l for l in lines if l]
    bullets = [b for e in cv.experience for b in e.bullets]
    report = StrengthReport(years=round(years, 1), senior=years >= 7, total_bullets=len(bullets),
                            quantified_bullets=sum(1 for b in bullets if NUMBER_RE.search(b)))
    found_count = 0
    for key, label, pattern, question in CHECKS:
        evidence = [l for l in lines if re.search(pattern, l, re.IGNORECASE)][:3]
        found_count += bool(evidence)
        report.items.append({"key": key, "label": label, "found": bool(evidence), "evidence": evidence,
                             "question": question})
    report.tenure = tenure_summary(cv)
    report.tenure["progression_line"] = progression_line(cv, years)
    share = report.quantified_bullets / report.total_bullets if report.total_bullets else 0
    report.score = round(70 * found_count / len(CHECKS) + 30 * min(1.0, share / 0.6))
    return report


def tenure_summary(cv: CVData) -> dict:
    """Employers, average and longest tenure, and short stints, so the user can pick a layout."""
    from backend.jobs.normalizer import normalize_company

    by_employer: dict[str, list[tuple[str, str]]] = {}
    names: dict[str, str] = {}
    for e in cv.experience:
        key = normalize_company(e.employer)
        by_employer.setdefault(key, []).append((e.start, e.end))
        names.setdefault(key, e.employer)
    months = {k: total_experience_months(v) for k, v in by_employer.items()}
    months = {k: m for k, m in months.items() if m}
    if not months:
        return {"employers": len(by_employer), "average_months": 0, "longest_months": 0, "longest_employer": "",
                "short_stints": 0, "promotions": 0, "suggest_hybrid": False}
    longest = max(months, key=lambda k: months[k])
    short = sum(1 for m in months.values() if m < 18)
    promotions = sum(len(v) - 1 for v in by_employer.values() if len(v) > 1)
    average = round(sum(months.values()) / len(months))
    return {"employers": len(by_employer), "average_months": average, "longest_months": months[longest],
            "longest_employer": names[longest], "short_stints": short, "promotions": promotions,
            "suggest_hybrid": short >= 2 or average < 24}


def progression_line(cv: CVData, years: float) -> str:
    """Suggest a summary opening built only from your own titles and dates, when titles show growth."""
    from backend.jobs.normalizer import infer_seniority
    from backend.utils.dates import parse_cv_date

    order = ["intern", "entry", "mid", "senior", "lead", "manager", "director", "executive"]
    dated = []
    for e in cv.experience:
        start = parse_cv_date(e.start)
        if start is not None:
            dated.append((start, e))
    if len(dated) < 2 or years < 3:
        return ""
    dated.sort(key=lambda x: x[0])
    first, last = dated[0][1], dated[-1][1]
    if order.index(infer_seniority(last.title)) <= order.index(infer_seniority(first.title)) or first.title == last.title:
        return ""
    return (f"{last.title} with {int(years)}+ years of career progression from {first.title} to {last.title}, "
            f"across {len({e.employer for _, e in dated})} organisations.")
