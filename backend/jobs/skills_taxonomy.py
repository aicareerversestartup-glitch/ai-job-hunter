"""A compact skill vocabulary used to extract requirements from job descriptions.

Each canonical skill maps to the aliases that count as the same thing. The list spans software,
data, engineering (incl. mechanical/manufacturing), and business skills; extend it freely in
``data/skills_extra.txt`` (one line per skill: ``canonical|alias1|alias2``).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from backend.utils.text import contains_phrase, normalize_key

_BASE: dict[str, tuple[str, ...]] = {
    # Programming languages
    "Python": ("python",), "Java": ("java",), "JavaScript": ("javascript", "js", "ecmascript"),
    "TypeScript": ("typescript",), "C": (), "C++": ("c++", "cpp"), "C#": ("c#", "csharp"),
    "Go": ("golang",), "Rust": ("rust",), "Kotlin": ("kotlin",), "Swift": ("swift",), "Ruby": ("ruby",),
    "PHP": ("php",), "Scala": ("scala",), "R": (), "MATLAB": ("matlab",), "SQL": ("sql",),
    "Bash": ("bash", "shell scripting"), "VBA": ("vba",), "Dart": ("dart",),
    # Web / backend
    "React": ("react", "react.js", "reactjs"), "Angular": ("angular",), "Vue": ("vue", "vue.js"),
    "Next.js": ("next.js", "nextjs"), "Node.js": ("node.js", "nodejs"), "Django": ("django",),
    "Flask": ("flask",), "FastAPI": ("fastapi",), "Spring Boot": ("spring boot", "spring framework"), ".NET": (".net", "dotnet"),
    "GraphQL": ("graphql",), "REST APIs": ("rest api", "restful", "rest apis"), "HTML": ("html", "html5"),
    "CSS": ("css", "css3", "tailwind"), "Microservices": ("microservices", "microservice"),
    # Data / ML
    "Machine Learning": ("machine learning", "ml"), "Deep Learning": ("deep learning",),
    "NLP": ("nlp", "natural language processing"), "Computer Vision": ("computer vision",),
    "LLMs": ("llm", "llms", "large language models", "generative ai", "genai"),
    "PyTorch": ("pytorch",), "TensorFlow": ("tensorflow",), "scikit-learn": ("scikit-learn", "sklearn"),
    "Pandas": ("pandas",), "NumPy": ("numpy",), "Spark": ("spark", "pyspark", "apache spark"),
    "Airflow": ("airflow",), "dbt": ("dbt",), "Tableau": ("tableau",), "Power BI": ("power bi", "powerbi"),
    "Excel": ("excel", "ms excel", "microsoft excel", "advanced excel", "vlookup", "pivot tables", "pivot table"), "Statistics": ("statistics", "statistical"),
    "Data Analysis": ("data analysis", "data analytics"), "ETL": ("etl", "elt"),
    # Databases
    "PostgreSQL": ("postgresql", "postgres"), "MySQL": ("mysql",), "MongoDB": ("mongodb", "mongo"),
    "Redis": ("redis",), "Elasticsearch": ("elasticsearch",), "Snowflake": ("snowflake",),
    "BigQuery": ("bigquery",), "Oracle": ("oracle",),
    # Cloud / DevOps
    "AWS": ("aws", "amazon web services"), "Azure": ("azure",), "GCP": ("gcp", "google cloud"),
    "Docker": ("docker",), "Kubernetes": ("kubernetes", "k8s"), "Terraform": ("terraform",),
    "CI/CD": ("ci/cd", "continuous integration", "github actions", "jenkins", "gitlab ci"),
    "Linux": ("linux", "unix"), "Git": ("git",), "Ansible": ("ansible",),
    # Security / QA
    "Cybersecurity": ("cybersecurity", "information security", "infosec"), "Selenium": ("selenium",),
    "Playwright": ("playwright",), "Test Automation": ("test automation", "automated testing"),
    # Mechanical / manufacturing / engineering
    "AutoCAD": ("autocad",), "SolidWorks": ("solidworks", "solid works"), "CATIA": ("catia",),
    "Creo": ("creo", "pro/e", "pro engineer", "pro/engineer"), "Siemens NX": ("siemens nx", "unigraphics", "nx cad"),
    "Inventor": ("autodesk inventor",), "Fusion 360": ("fusion 360",), "ANSYS": ("ansys",),
    "Abaqus": ("abaqus",), "HyperMesh": ("hypermesh",), "COMSOL": ("comsol",),
    "FEA": ("fea", "finite element analysis", "finite element"), "CFD": ("cfd", "computational fluid dynamics"),
    "GD&T": ("gd&t", "geometric dimensioning and tolerancing"), "CAD": ("cad", "3d modeling", "3d modelling"),
    "CAM": ("cnc programming", "computer-aided manufacturing"), "CNC": ("cnc",), "PLC": ("plc", "plc programming"),
    "SCADA": ("scada",), "HVAC": ("hvac",), "Thermodynamics": ("thermodynamics",),
    "Heat Transfer": ("heat transfer",), "Fluid Mechanics": ("fluid mechanics",),
    "Machine Design": ("machine design", "mechanical design"), "Product Design": ("product design",),
    "DFM": ("dfm", "design for manufacturing", "design for manufacturability"), "DFMEA": ("dfmea", "fmea", "pfmea"),
    "Root Cause Analysis": ("root cause analysis", "rca", "8d", "5 why"), "Six Sigma": ("six sigma", "lean six sigma"),
    "Lean Manufacturing": ("lean manufacturing", "kaizen", "5s", "lean techniques", "lean layout"), "Quality Control": ("quality control", "qc"),
    "Quality Assurance": ("quality assurance",), "ISO 9001": ("iso 9001", "iso9001"), "IATF 16949": ("iatf 16949",),
    "APQP": ("apqp",), "PPAP": ("ppap",), "SPC": ("spc", "statistical process control"),
    "Project Management": ("project management",), "PMP": ("pmp",), "Agile": ("agile", "scrum", "kanban"),
    "SAP": ("sap", "sap erp", "sap mm", "sap pp", "sap scm"), "Microsoft Dynamics": ("microsoft dynamics", "dynamics 365", "navision"), "ERP": ("erp",), "Supply Chain": ("supply chain",),
    "Procurement": ("procurement", "sourcing"), "Maintenance": ("preventive maintenance", "predictive maintenance", "tpm"),
    "Welding": ("welding",), "Sheet Metal": ("sheet metal",), "Injection Molding": ("injection molding", "injection moulding"),
    "Piping": ("piping",), "Revit": ("revit",), "BIM": ("bim",), "Robotics": ("robotics",),
    "Embedded Systems": ("embedded systems", "embedded c", "firmware"), "Arduino": ("arduino",),
    # Logistics, supply chain, warehouse, food operations
    "Warehouse Management": ("warehouse management", "warehouse operations", "warehousing"),
    "WMS": ("wms", "warehouse management system"), "TMS": ("tms", "transport management system"),
    "SAP EWM": ("sap ewm", "extended warehouse management"), "SAP SD": ("sap sd",),
    "Oracle SCM": ("oracle scm", "oracle supply chain"), "Blue Yonder": ("blue yonder", "jda"),
    "Manhattan WMS": ("manhattan associates", "manhattan wms"),
    "Inventory Management": ("inventory management", "inventory control", "stock control"),
    "Demand Planning": ("demand planning", "demand forecasting", "forecasting"), "S&OP": ("s&op", "sales and operations planning"),
    "Production Planning": ("production planning", "mrp", "material requirements planning"),
    "Material Planning": ("material planning", "materials planning"),
    "Logistics Management": ("logistics management", "logistics operations"),
    "Transportation Management": ("transportation management", "transport management", "fleet management"),
    "Last Mile Delivery": ("last mile", "last-mile"), "Cold Chain": ("cold chain", "cold-chain", "temperature-controlled"),
    "Freight Forwarding": ("freight forwarding", "freight forwarder", "sea freight", "air freight", "ocean freight"),
    "Customs & EXIM": ("customs clearance", "exim", "import export", "export documentation", "customs compliance"),
    "Incoterms": ("incoterms",), "Distribution": ("distribution centre", "distribution center", "distribution management"),
    "Vendor Management": ("vendor management", "supplier management", "supplier relationship"),
    "Strategic Sourcing": ("strategic sourcing", "category management"),
    "KPI Management": ("kpi", "kpis", "otif", "on-time in-full", "service level", "sla", "slas"),
    "Capacity Planning": ("capacity planning", "resource planning"), "Cross-functional Leadership": ("cross-functional", "cross functional"),
    "Stakeholder Management": ("stakeholder management", "stakeholder engagement"),
    "Cost Reduction": ("cost reduction", "cost savings", "cost optimisation", "cost optimization"),
    "Process Improvement": ("process improvement", "continuous improvement", "operational excellence"),
    "OEE": ("oee", "overall equipment effectiveness"), "Plant Operations": ("plant operations", "plant management", "factory management"),
    "Food Safety": ("food safety", "haccp", "fssc 22000", "iso 22000", "brcgs", "brc", "fssai"), "GMP": ("gmp", "good manufacturing practice"),
    "Health & Safety": ("health and safety", "ehs", "hse", "osha"),
    "People Management": ("people management", "team management", "workforce management", "shift management"),
    "P&L Management": ("p&l", "profit and loss", "budget management", "budgeting"),
    # Business / soft
    "Communication": ("communication skills",),
    "Leadership": ("team leadership", "people management"), "Sales": ("sales",), "Marketing": ("marketing",),
    "SEO": ("seo",), "Customer Service": ("customer service", "customer support"), "Accounting": ("accounting",),
    "Financial Modeling": ("financial modeling", "financial modelling"), "Figma": ("figma",),
    "Jira": ("jira",), "Salesforce": ("salesforce",),
}

# Words that indicate the surrounding sentence states a requirement versus a nice-to-have.
REQUIRED_CUES = ("required", "must have", "must-have", "requirements", "you have", "you will need",
                 "minimum", "qualifications", "essential", "mandatory", "need to have", "proficiency in",
                 "experience with", "experience in", "strong knowledge", "expertise in")
PREFERRED_CUES = ("nice to have", "nice-to-have", "preferred", "bonus", "a plus", "plus if", "desirable",
                  "advantageous", "good to have", "ideally")

# Short/ambiguous aliases that only count when written in a matching case or context.
_CASE_SENSITIVE = {"C": r"(?<![A-Za-z0-9+#])C(?![A-Za-z0-9+#])", "R": r"(?<![A-Za-z0-9])R(?![A-Za-z0-9&])",
                   "Go": r"(?<![A-Za-z0-9])Go(?:lang)?(?![A-Za-z0-9])",
                   "Excel": r"(?i)(?<![a-z])excel(?![a-z])(?!\s+(?:at|in|as|with|when|under)\b)"}


@lru_cache(maxsize=1)
def skill_aliases() -> dict[str, tuple[str, ...]]:
    merged = {k: (v if v else (k.lower(),)) for k, v in _BASE.items()}
    extra = Path(__file__).resolve().parents[2] / "data" / "skills_extra.txt"
    if extra.exists():
        for line in extra.read_text(encoding="utf-8").splitlines():
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if parts and not line.startswith("#"):
                merged[parts[0]] = tuple(dict.fromkeys([parts[0].lower(), *[p.lower() for p in parts[1:]]]))
    return merged


def find_skills(text: str) -> list[str]:
    """Return canonical skills mentioned in ``text`` (order of first appearance)."""
    import re

    if not text:
        return []
    found: list[tuple[int, str]] = []
    lowered = text.lower()
    for canonical, aliases in skill_aliases().items():
        if canonical in _CASE_SENSITIVE:
            m = re.search(_CASE_SENSITIVE[canonical], text)
            if m and canonical in ("C", "R", "Go"):
                # Single letters need a programming context to count.
                window = text[max(0, m.start() - 40): m.end() + 40].lower()
                if not any(w in window for w in ("language", "programming", "python", "java", ",", "/")):
                    m = None
            if m:
                found.append((m.start(), canonical))
            continue
        positions = [max(lowered.find(alias), 0) for alias in aliases if contains_phrase(lowered, alias)]
        if positions:
            found.append((min(positions), canonical))
    found.sort()
    return list(dict.fromkeys(name for _, name in found))


def canonical_skill(value: str) -> str:
    """Map a free-text skill from a CV (e.g. 'ReactJS') onto the canonical name if known."""
    key = normalize_key(value)
    for canonical, aliases in skill_aliases().items():
        if key == normalize_key(canonical) or key in {normalize_key(a) for a in aliases}:
            return canonical
    return value.strip()
