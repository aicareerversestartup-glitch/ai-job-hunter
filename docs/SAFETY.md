# Truthfulness and application safety

## The fact base

Your verified Master CV plus your profile form the only evidence. The uploaded file is stored once, content-addressed and read-only. Its automatic parse is kept unchanged. Your corrections are stored as the verified data; once verified, a version is frozen and further edits create a new version. Values you add that aren't in the original file are flagged so adding them is a conscious choice.

## What the guard checks (`backend/cv/truthfulness.py`)

For a tailored CV, every item is compared with the Master CV:

| Check | Blocks |
|---|---|
| Employer + title pair must exist | invented employers, changed job titles |
| Dates and location of each role must match | changed dates/locations |
| Education (institution + degree) must exist | invented degrees |
| Certifications, projects, languages must exist | invented credentials |
| Skills must appear somewhere in the Master CV | invented skills / languages / tools |
| Skills named in a bullet must appear in **that role** | moving experience between jobs |
| Numbers in a bullet must appear in that role's source text | invented metrics |
| Bullet wording must be grounded in the role's source text | invented responsibilities/achievements |
| Contact details must match | changed location etc. |
| "N years" claims ≤ experience computed from your dates | inflated experience |
| Work authorization / visa claims must match your profile, per country | false authorization |
| Salary figures must come from your profile | invented salary |

Cover letters and answers get the prose checks (skills, years, degrees, authorization, salary, unverified numbers). Mentions of the employer's own stack taken from the job description are flagged for review rather than blocked.

AI output is never trusted: `sanitize_cv` removes or reverts every failing item, the result is re-checked, and if it still fails the reordered Master CV is used. A failing AI cover letter is replaced with a fact-only letter. Answers the app can't support with your data are left blank and marked **Needs your answer** — for example, work authorization for a country your profile doesn't mention.

Requirements you don't meet are listed as **MISSING REQUIREMENT** on the job and the review screen and are never added to documents.

## Application safety

- States: `draft → ready_for_review → approved → submitting → submitted` (plus `needs_user_action`). Skipping approval is impossible in the state machine.
- Approval requires: an explicit "I reviewed…" confirmation, zero blocking guard violations, every question answered or marked as not asked.
- Approval stores a SHA-256 of the exact CV, letter, answers and apply URL. Any edit drops the application back to review; apply/submit endpoints re-verify the hash.
- High fraud-risk postings can't be drafted until you confirm the employer is genuine.
- The apply assistant **never** solves or bypasses CAPTCHAs, bot checks, sign-ins or MFA. Hard stops (bot wall, sign-in, verification code, "no automation" notices) halt before any field is filled. A CAPTCHA guarding the submit button means it may fill fields, but only you can submit. Sensitive fields (ID numbers, bank details, passwords, date of birth) are always left for you.
- Fully automatic submission needs three switches: server `ALLOW_AUTO_SUBMIT=true`, your tick on that application at approval, and a supported ATS page with no blockers. It's off by default.
- Every significant action is written to `audit_log`.

## Job sources and terms of service

Only official APIs, public employer ATS boards and RSS feeds are queried. LinkedIn, Indeed, Glassdoor, Naukri and similar sites prohibit automated access and auto-apply in their terms, so they aren't scraped and their pages aren't fetched by URL import; paste those jobs instead. Remotive asks API users to link back and poll sparingly; the default 12-hour schedule respects that.

## Security

scrypt password hashing; signed, revocable session tokens in httpOnly SameSite=Strict cookies; login rate limiting; per-user row ownership checks on every route; Fernet encryption of stored API keys; SSRF protection on user-supplied URLs (RSS feeds, job links); upload size limits and safe filenames; security headers; API docs disabled in production; containers run as a non-root user.


## Formats and CV presentation options

- Country formats change layout and which **profile** details print. Fitting to a page limit only removes the least relevant bullets of older roles (listed for you on the review screen).
- Sample-CV layouts keep structure only; the sample's text is discarded after analysis.
- ATS keyword additions to the Skills list are limited to skills already written in your experience.
- "(Contract)" / "(Consulting Assignment)" labels come only from the role type you set in the Master CV, and the guard blocks any change.
- Year-only dates are an option; application forms and background checks still need exact months, which must be answered truthfully.
- Bullet-coach templates contain blanks; a Master CV with unfilled blanks cannot be verified.

## Inbox tracking

IMAP, read-only (`BODY.PEEK`, mailbox opened read-only). The app password is stored encrypted. Emails are matched to applications by company name/domain in the sender or subject; job-board notification senders are ignored. Status changes from emails are suggestions you confirm.
