"""Suggest target roles from any CV: the titles you actually held plus closely related roles that
your skills support. Used alongside the roles you typed; yours always rank first."""
from __future__ import annotations

import re

from backend.cv.schema import CVData
from backend.jobs.normalizer import infer_seniority
from backend.jobs.skills_taxonomy import find_skills
from backend.utils.text import normalize_key

# Role family -> (skills that indicate it, role titles to search)
FAMILIES: list[tuple[str, set[str], list[str]]] = [
    ("operations", {"Warehouse Management", "Logistics Management", "Process Improvement", "KPI Management",
                    "People Management", "Lean Manufacturing", "P&L Management", "Distribution"},
     ["Operations Manager", "Site Operations Manager"]),
    ("warehouse", {"Warehouse Management", "WMS", "Inventory Management", "SAP EWM", "Manhattan WMS", "Distribution"},
     ["Warehouse Manager", "Distribution Centre Manager"]),
    ("logistics", {"Logistics Management", "Transportation Management", "TMS", "Freight Forwarding", "Last Mile Delivery",
                   "Customs & EXIM", "Incoterms", "Cold Chain"},
     ["Logistics Manager", "Transport Manager"]),
    ("supply_chain", {"Supply Chain", "Demand Planning", "S&OP", "Inventory Management", "SAP", "Oracle SCM",
                      "Blue Yonder", "Material Planning"},
     ["Supply Chain Manager", "Supply Chain Planner"]),
    ("procurement", {"Procurement", "Strategic Sourcing", "Vendor Management"},
     ["Procurement Manager", "Sourcing Manager"]),
    ("plant", {"Plant Operations", "Production Planning", "OEE", "GMP", "Food Safety", "Lean Manufacturing", "Six Sigma"},
     ["Plant Manager", "Production Manager"]),
    ("quality", {"Quality Control", "Quality Assurance", "ISO 9001", "IATF 16949", "Six Sigma", "Root Cause Analysis",
                 "Food Safety", "SPC", "PPAP", "APQP"},
     ["Quality Manager", "Quality Engineer"]),
    ("mechanical_design", {"SolidWorks", "CATIA", "Creo", "Siemens NX", "AutoCAD", "GD&T", "FEA", "ANSYS", "DFMEA",
                           "Machine Design", "Sheet Metal"},
     ["Mechanical Design Engineer", "Product Design Engineer"]),
    ("data", {"Python", "SQL", "Power BI", "Tableau", "Data Analysis", "Statistics", "Excel"},
     ["Data Analyst", "Business Analyst"]),
    ("software", {"Python", "Java", "JavaScript", "TypeScript", "React", "Node.js", "Docker", "AWS"},
     ["Software Engineer", "Backend Developer"]),
]
MIN_FAMILY_HITS = 2


GENERIC_TITLES = {"executive", "senior executive", "assistant manager", "deputy manager", "manager", "associate",
                  "officer", "senior officer", "team lead", "team leader", "supervisor", "trainee", "lead"}
LEVEL_ORDER = ["intern", "entry", "mid", "senior", "lead", "manager", "director", "executive"]


def _clean_title(title: str) -> str:
    """'Assistant Manager - Warehouse' -> 'Warehouse Assistant Manager'; drops bracketed notes."""
    title = re.sub(r"\(.*?\)", "", title)
    parts = [p.strip() for p in re.split(r"\s+[-–|/]\s+|,", title) if p.strip()]
    if not parts:
        return ""
    head = parts[0]
    if normalize_key(head) in GENERIC_TITLES and len(parts) > 1:
        head = f"{parts[1]} {head}"
    return re.sub(r"\s+", " ", head).strip()


def suggest_roles(cv: CVData, limit: int = 6) -> list[dict]:
    """[{"title", "reason"}], most recent title first, then skill-supported families."""
    out: list[dict] = []
    seen: set[str] = set()

    def add(title: str, reason: str) -> None:
        key = normalize_key(title)
        if key and key not in seen and len(out) < limit:
            seen.add(key)
            out.append({"title": title, "reason": reason})

    latest_level = LEVEL_ORDER.index(infer_seniority(cv.experience[0].title)) if cv.experience else 0
    latest_is_full = bool(cv.experience) and not re.search(r"assistant|deputy|asst|junior|jr", cv.experience[0].title, re.I)
    for exp in cv.experience[:3]:
        title = _clean_title(exp.title)
        level = LEVEL_ORDER.index(infer_seniority(exp.title))
        junior_variant = latest_is_full and re.search(r"assistant|deputy|asst|junior|jr", exp.title, re.I)
        if (not title or "not detected" in title or level < latest_level or junior_variant
                or normalize_key(title) in GENERIC_TITLES):
            continue  # only search at your current level or the same kind of role
        add(title, f"Your role at {exp.employer}")

    skills = set(find_skills(cv.all_text())) | set(cv.skills)
    ranked = []
    for family, signals, titles in FAMILIES:
        hits = sorted(signals & skills)
        if len(hits) >= MIN_FAMILY_HITS:
            ranked.append((len(hits), titles, hits))
    ranked.sort(key=lambda r: -r[0])
    senior = any(infer_seniority(e.title) in ("manager", "lead", "director", "senior") for e in cv.experience[:2])
    for _, titles, hits in ranked:
        for title in titles:
            if not senior and "Manager" in title:
                continue
            add(title, "Your skills: " + ", ".join(hits[:4]))
    return out
