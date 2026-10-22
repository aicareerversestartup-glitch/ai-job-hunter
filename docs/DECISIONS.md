# Decisions and assumptions

The build prompt was cut off in section 5 (project structure, after `data/`). These are the defaults chosen to fill the gap; change any of them freely.

1. **Job sources**: official APIs and public ATS boards only (Greenhouse, Lever, Ashby, Workable, Remotive, Arbeitnow, Adzuna, RSS) plus manual paste and JSON-LD import from company career pages. No scraping of sites whose terms forbid it.
2. **Default apply mode is "assist"**: fill the form, upload approved files, then stop for you to press Submit. Auto-submit exists but is off by default.
3. **Single user per deployment** is the expected use (registration closes after the first account when `ALLOW_REGISTRATION=false`), but the data model is multi-user with strict ownership checks.
4. **Background jobs** use APScheduler and threads rather than Celery/Redis, to keep a personal deployment to one process (or one API + one worker container).
5. **AI is optional**, with deterministic fallbacks everywhere, so the core workflow never depends on a vendor.
6. **Scoring is deterministic** and explainable; AI never changes the score or the missing-requirements list.
7. **Experience years** are computed from the dates on your CV, with overlapping roles counted once.
8. **Skill vocabulary** (`backend/jobs/skills_taxonomy.py`) covers software, data, mechanical/manufacturing and business skills. Add your own in `data/skills_extra.txt` as `Canonical|alias|alias`.
9. **Initial migration** creates the schema from the models; generate later migrations with `alembic revision --autogenerate`.
10. **Default sources** (Remotive, Arbeitnow) skew towards remote and European roles. For India-based roles, add Adzuna (country India) and the career boards of target companies.
