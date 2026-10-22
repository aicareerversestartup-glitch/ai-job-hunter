"""Country CV conventions, researched from public sample CVs and official guidance (sources listed
per country). A format only changes layout and which of YOUR stated personal details appear; it
never adds facts. Personal details (date of birth, nationality, visa status, photo, referees) are
taken from your profile and only shown when you filled them in and the country expects them."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from backend.utils.text import normalize_key

SECTION_KEYS = ("summary", "skills", "experience", "projects", "education", "certifications", "languages",
                "other", "referees")


@dataclass(frozen=True)
class CountryFormat:
    code: str
    country: str
    document_title: str  # heading word used in that market
    max_pages: int
    photo: str  # expected | common | optional | no
    personal_details: tuple[str, ...]  # which profile fields to show: dob, nationality, visa_status, driving_licence
    section_order: tuple[str, ...]
    summary_heading: str
    date_style: str  # "Mon YYYY" | "MM/YYYY"
    signature_line: bool = False
    referees: str = "omit"  # omit | on_request | list
    tips: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return asdict(self)


FORMATS: dict[str, CountryFormat] = {f.code: f for f in [
    CountryFormat(
        "IN", "India", "Curriculum Vitae", 2, "optional", ("dob", "nationality"),
        ("summary", "skills", "experience", "projects", "education", "certifications", "languages", "other"),
        "Professional Summary", "Mon YYYY",
        tips=("Two pages for experienced candidates.", "A short skills block near the top helps recruiters and ATS.",
              "Date of birth and nationality are common but optional."),
    ),
    CountryFormat(
        "US", "United States", "Resume", 2, "no", (),
        ("summary", "skills", "experience", "education", "certifications", "projects", "languages"),
        "Summary", "Mon YYYY",
        tips=("One page under ~10 years of experience, two pages above.", "No photo, date of birth, marital status or "
              "nationality (US anti-discrimination norms).", "Lead with quantified results."),
    ),
    CountryFormat(
        "GB", "United Kingdom", "Curriculum Vitae", 2, "no", (),
        ("summary", "experience", "skills", "education", "certifications", "languages"),
        "Personal Profile", "Mon YYYY", referees="on_request",
        tips=("Two pages is the norm.", "No photo or date of birth.", "A short personal profile opens the CV.",
              "State visa or right-to-work status in the application form, not as a guess on the CV."),
        sources=("https://www.remitly.com/blog/en-gb/jobs/cv-format-guide/",
                 "https://www.dundee.ac.uk/guides/cv-writing-guidance-international-students"),
    ),
    CountryFormat(
        "DE", "Germany", "Lebenslauf / Curriculum Vitae", 2, "expected", ("dob", "nationality", "visa_status"),
        ("experience", "education", "skills", "certifications", "languages", "other"),
        "Profil", "MM/YYYY", signature_line=True,
        tips=("Maximum two pages, tabular layout, most recent first.", "Professional photo top right is common.",
              "Date of birth as DD.MM.YYYY; leave out marital status.", "Dates as MM/YYYY.",
              "State German level using CEFR (e.g. B1).", "Ends with place, date and signature."),
        sources=("https://expatrio.com/about-germany/german-cv-guide",
                 "https://www.visualcv.com/international/germany-cv/"),
    ),
    CountryFormat(
        "EU", "Europe (Europass)", "Curriculum Vitae (Europass)", 2, "no", ("nationality",),
        ("summary", "experience", "education", "languages", "skills", "certifications", "other"),
        "About Me", "MM/YYYY",
        tips=("Europass structure: work experience, education and training, language skills (use CEFR levels such "
              "as C1), digital skills, then other information.", "Photo switched off here; Europass makes it optional.",
              "Write achievements with numbers from your real results (team size, cost, %, volume).",
              "For Germany, many recruiters still prefer the German format with a photo; compare both."),
        sources=("https://europass.europa.eu/en/create-europass-cv",),
    ),
    CountryFormat(
        "NL", "Netherlands", "Curriculum Vitae", 2, "no", (),
        ("summary", "experience", "skills", "education", "languages", "certifications"),
        "Profile", "Mon YYYY",
        tips=("One to two pages, direct and concise.", "No photo, date of birth or marital status.",
              "Explain unfamiliar international job titles and company scope briefly.", "Show results with numbers."),
        sources=("https://www.leideninternationalcentre.nl/get-advice/blogs/how-to-update-your-cv-for-the-dutch-job-"
                 "market-without-overcomplicating-it",),
    ),
    CountryFormat(
        "AE", "United Arab Emirates", "Curriculum Vitae", 2, "expected", ("nationality", "visa_status", "dob",
                                                                           "driving_licence"),
        ("summary", "experience", "skills", "languages", "certifications", "education"),
        "Professional Summary", "Mon YYYY",
        tips=("Up to two pages.", "Passport-style photo is commonly expected in the private sector.",
              "Nationality and visa status (e.g. 'Employment Visa – Transferable') appear under contact details.",
              "Marital status usually omitted."),
        sources=("https://www.visualcv.com/international/uae-resume/",),
    ),
    CountryFormat(
        "SA", "Saudi Arabia", "Curriculum Vitae", 2, "expected", ("nationality", "visa_status", "dob"),
        ("summary", "experience", "skills", "languages", "certifications", "education"),
        "Professional Summary", "Mon YYYY",
        tips=("Gulf conventions: photo, nationality and visa/iqama status are commonly included.",),
    ),
    CountryFormat(
        "QA", "Qatar", "Curriculum Vitae", 2, "expected", ("nationality", "visa_status", "dob"),
        ("summary", "experience", "skills", "languages", "certifications", "education"),
        "Professional Summary", "Mon YYYY",
        tips=("Gulf conventions: photo, nationality and visa status are commonly included.",),
    ),
    CountryFormat(
        "SG", "Singapore", "Resume", 3, "optional", ("visa_status",),
        ("summary", "experience", "education", "skills", "certifications", "languages"),
        "Summary", "Mon YYYY",
        tips=("One to two pages early career, two to three for mid-level and managers.",
              "Photo is common but optional.", "Mention work-pass status when relevant.",
              "Leave out age, religion, marital status, full home address and NRIC."),
        sources=("https://sg.jobstreet.com/career-advice/article/resume-format",),
    ),
    CountryFormat(
        "CA", "Canada", "Resume", 2, "no", (),
        ("summary", "skills", "experience", "education", "certifications", "languages"),
        "Professional Summary", "Mon YYYY",
        tips=("No more than two pages.", "No photo, age, marital status or SIN.",
              "References on a separate sheet, only when asked.", "Avoid 'I', 'my' and 'me'."),
        sources=("https://www.jobbank.gc.ca/findajob/resources/write-good-resume",),
    ),
    CountryFormat(
        "AU", "Australia", "Resume", 3, "no", ("visa_status",),
        ("summary", "skills", "experience", "education", "certifications", "languages", "referees"),
        "Career Profile", "Mon YYYY", referees="list",
        tips=("Two to three pages for mid-career.", "No photo, date of birth, marital status.",
              "State work rights plainly, e.g. 'Permanent resident, unrestricted work rights'.",
              "List two to three referees (with their permission)."),
        sources=("https://resumegeni.com/blog/how-to-write-resume-australia",),
    ),
    CountryFormat(
        "NZ", "New Zealand", "CV", 3, "no", ("visa_status",),
        ("summary", "skills", "experience", "education", "certifications", "referees"),
        "Profile", "Mon YYYY", referees="list",
        tips=("Similar to Australia: no photo, state work rights, list referees.",),
    ),
    CountryFormat(
        "IE", "Ireland", "Curriculum Vitae", 2, "no", (),
        ("summary", "experience", "skills", "education", "certifications", "languages"),
        "Profile", "Mon YYYY", referees="on_request",
        tips=("Two pages, no photo, no date of birth.",),
    ),
    CountryFormat(
        "CH", "Switzerland", "Curriculum Vitae", 2, "expected", ("dob", "nationality", "visa_status"),
        ("summary", "experience", "education", "skills", "languages", "certifications"),
        "Profile", "MM/YYYY",
        tips=("Photo common.", "Nationality and permit type (e.g. B/C permit) are usually stated.",
              "Language levels matter (German/French/Italian)."),
    ),
    CountryFormat(
        "FR", "France", "CV", 2, "common", (),
        ("summary", "experience", "education", "skills", "languages", "certifications"),
        "Profil", "MM/YYYY",
        tips=("One page early career, two for experienced.", "A photo is common but optional.",
              "List French level clearly."),
    ),
    CountryFormat(
        "DK", "Denmark", "CV", 2, "common", (),
        ("summary", "experience", "education", "skills", "languages", "certifications"),
        "Profile", "Mon YYYY",
        tips=("Two pages, concise.", "A photo is common in Danish CVs."),
    ),
    CountryFormat(
        "CN", "China", "Resume", 2, "expected", ("dob", "nationality"),
        ("summary", "experience", "education", "skills", "languages", "certifications"),
        "Summary", "MM/YYYY",
        tips=("Photo and date of birth are commonly included.", "For international employers an English CV is fine; "
              "state Mandarin level."),
    ),
]}

COUNTRY_TO_CODE = {normalize_key(f.country): code for code, f in FORMATS.items()}
COUNTRY_TO_CODE.update({"uae": "AE", "uk": "GB", "usa": "US", "united states of america": "US", "taiwan": "CN"})
COUNTRY_TO_CODE.update({c: "EU" for c in ("poland", "spain", "belgium", "austria", "sweden", "italy", "portugal",
                                          "finland", "norway", "czech republic", "czechia", "luxembourg", "greece")})
DEFAULT_CODE = "IN"

STYLES = {
    "classic": {"label": "Classic", "font": "Georgia", "pdf_font": "Times-Roman", "pdf_bold": "Times-Bold",
                "size": 10.5, "accent": "#1f2d3d", "align_name": "center", "spacing": 1.0},
    "modern": {"label": "Modern", "font": "Calibri", "pdf_font": "Helvetica", "pdf_bold": "Helvetica-Bold",
               "size": 10.5, "accent": "#1f4e79", "align_name": "left", "spacing": 1.0},
    "compact": {"label": "Compact", "font": "Arial", "pdf_font": "Helvetica", "pdf_bold": "Helvetica-Bold",
                "size": 9.5, "accent": "#333333", "align_name": "left", "spacing": 0.85},
}


@dataclass
class CustomLayout:
    """A layout learned from a sample CV the user liked (structure only, never its text)."""
    id: str
    name: str
    section_order: list[str]
    max_pages: int
    photo: bool
    personal_details: list[str] = field(default_factory=list)
    headings: dict[str, str] = field(default_factory=dict)  # our key -> heading text used by the sample


def code_for_country(country: str) -> str:
    return COUNTRY_TO_CODE.get(normalize_key(country), DEFAULT_CODE)


def get_format(code: str) -> CountryFormat:
    return FORMATS.get((code or DEFAULT_CODE).upper(), FORMATS[DEFAULT_CODE])


def list_formats() -> list[dict]:
    return [f.as_dict() for f in FORMATS.values()]


def resolve_layout(cv_format: dict, custom_layouts: list[dict]) -> tuple[CountryFormat, dict]:
    """Return the country format (possibly overridden by a custom sample layout) and style dict."""
    fmt = get_format(cv_format.get("country_code", DEFAULT_CODE))
    style = {**STYLES.get(cv_format.get("style", "modern"), STYLES["modern"]),
             "date_precision": cv_format.get("date_precision", "month"),
             "layout": cv_format.get("layout", "chronological")}
    custom_id = cv_format.get("custom_layout_id")
    if custom_id:
        custom = next((c for c in custom_layouts if c.get("id") == custom_id), None)
        if custom:
            from dataclasses import replace

            fmt = replace(fmt, section_order=tuple(s for s in custom["section_order"] if s in SECTION_KEYS) or
                          fmt.section_order, max_pages=custom.get("max_pages") or fmt.max_pages,
                          photo="expected" if custom.get("photo") else "no",
                          personal_details=tuple(custom.get("personal_details") or ()))
            style = {**style, "headings": custom.get("headings", {})}
    return fmt, style
