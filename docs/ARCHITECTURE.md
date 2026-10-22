# Architecture

## Workflow and where it lives

| Step | Code |
|---|---|
| Master profile | `cv/profile.py`, `api/profile.py` |
| Master CV (immutable original, versioned structured data) | `services/cv_service.py`, `cv/parser.py`, `cv/structurer.py` |
| Target roles and preferences | `jobs/matcher.py: JobPreferences` |
| Source discovery and collection | `integrations/*`, `services/discovery.py` |
| Normalization | `jobs/normalizer.py: build_job` (every source goes through it) |
| Duplicate detection | `jobs/dedupe.py` (source id, fingerprint, fuzzy title + description) |
| Quality / fraud check | `jobs/fraud.py` (explainable rules; high risk hidden by default) |
| Matching and score | `jobs/requirements.py`, `jobs/matcher.py` |
| Job-specific CV, cover letter, answers | `ai/generation.py` |
| Truthfulness enforcement | `cv/truthfulness.py` |
| Review, approval | `applications/state_machine.py`, `services/application_service.py` |
| Application assistance / submission | `automation/apply_assistant.py`, `automation/blockers.py` |
| Tracking (interview / rejection / offer) | `ApplicationEvent` table, `api/applications.py` |

## Runtime

- **API**: FastAPI (`backend/main.py`). Session is an httpOnly, SameSite=Strict cookie holding a signed JWT; Bearer tokens are also accepted for scripts. Token version on the user row revokes all sessions.
- **Database**: SQLModel/SQLAlchemy. `DATABASE_URL` empty means SQLite in `data/`. Production uses PostgreSQL via Docker Compose. Alembic migrations in `migrations/`.
- **Background work**: APScheduler runs discovery every `DISCOVERY_INTERVAL_HOURS`, in the API process by default or in the `worker` container. On-demand discovery and apply sessions run in background threads, so a single API worker process is expected (personal deployment).
- **AI**: `ai/providers` defines `LLMProvider`; implementations for OpenAI, Anthropic, Gemini, Ollama and any OpenAI-compatible endpoint. Per-user settings with encrypted keys; server default from env. Every AI function has a deterministic fallback, so the app is fully usable without AI.
- **Documents**: PDF via pypdf (OCR fallback via Tesseract + pypdfium2), DOCX via python-docx; output CVs/letters rendered to ATS-friendly single-column DOCX and PDF (reportlab).
- **Browser automation**: Playwright Chromium with a persistent profile in `data/browser-profile`, so sites you sign in to yourself stay signed in. Visible window by default.

## Data model

`users`, `profiles`, `master_cvs` (original file path + sha256, raw text, automatic parse, user-verified data, version chain), `job_sources`, `jobs` (normalized posting + quality report + duplicates merged into `also_seen_on`), `job_matches` (per job × CV version), `applications` (tailored CV, guard reports, letter, answers, approval snapshot hash, apply outcome), `application_events` (timeline), `ai_settings`, `discovery_runs`, `audit_log`.

## Scoring

Weighted, explainable components: skills 40 (required 80% / preferred 20%), role fit 25, experience 15, your preferences 10, education 5, other (certifications, languages, authorization) 5. Dealbreakers (location outside your countries, wrong employment type, salary below minimum, excluded keywords/companies, no sponsorship when you need it) cap the score at 35. Four or more missing required items cap it at 55.
