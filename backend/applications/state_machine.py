"""Application lifecycle: DRAFT → REVIEW → USER APPROVAL → APPLY → tracking.

Nothing can reach ``submitting``/``submitted`` without passing through ``approved``, and approval
is bound to a hash of exactly what the user saw. Any edit after approval drops the application
back to ``ready_for_review``.
"""
from __future__ import annotations

import json

from backend.utils.text import sha256_text

DRAFT = "draft"
READY = "ready_for_review"
APPROVED = "approved"
SUBMITTING = "submitting"
NEEDS_USER = "needs_user_action"  # paused: CAPTCHA, login, MFA, unsupported form…
SUBMITTED = "submitted"
IN_REVIEW = "in_review"
INTERVIEWING = "interviewing"
OFFER = "offer"
ACCEPTED = "accepted"
REJECTED = "rejected"
WITHDRAWN = "withdrawn"
DISCARDED = "discarded"

PIPELINE = [DRAFT, READY, APPROVED, SUBMITTING, NEEDS_USER, SUBMITTED, IN_REVIEW, INTERVIEWING, OFFER, ACCEPTED,
            REJECTED, WITHDRAWN, DISCARDED]

TRANSITIONS: dict[str, set[str]] = {
    DRAFT: {READY, DISCARDED},
    READY: {APPROVED, DRAFT, DISCARDED},
    APPROVED: {SUBMITTING, READY, SUBMITTED, DISCARDED},
    SUBMITTING: {SUBMITTED, NEEDS_USER, APPROVED},
    NEEDS_USER: {SUBMITTED, APPROVED, READY, DISCARDED},
    SUBMITTED: {IN_REVIEW, INTERVIEWING, OFFER, REJECTED, WITHDRAWN},
    IN_REVIEW: {INTERVIEWING, OFFER, REJECTED, WITHDRAWN},
    INTERVIEWING: {INTERVIEWING, OFFER, REJECTED, WITHDRAWN},
    OFFER: {ACCEPTED, REJECTED, WITHDRAWN},
    ACCEPTED: set(),
    REJECTED: set(),
    WITHDRAWN: set(),
    DISCARDED: {DRAFT},
}
EDITABLE = {DRAFT, READY, APPROVED, NEEDS_USER}
TRACKING_STATES = {SUBMITTED, IN_REVIEW, INTERVIEWING, OFFER, ACCEPTED, REJECTED, WITHDRAWN}


class TransitionError(ValueError):
    pass


def check_transition(current: str, target: str) -> None:
    if target not in TRANSITIONS.get(current, set()):
        raise TransitionError(f"Cannot move an application from '{current}' to '{target}'.")


def snapshot_hash(*, tailored_cv: dict, cover_letter: str, answers: list, apply_url: str,
                  cv_format: dict | None = None) -> str:
    payload = json.dumps({"cv": tailored_cv, "letter": cover_letter, "answers": answers, "url": apply_url,
                          "format": cv_format or {}},
                         sort_keys=True, ensure_ascii=False)
    return sha256_text(payload)


def approval_blockers(*, cv_guard: dict, cover_guard: dict, answers: list, confirmed: bool) -> list[str]:
    """Reasons the user cannot approve yet. Empty list means approval is allowed."""
    problems: list[str] = []
    if not confirmed:
        problems.append("Confirm that you reviewed the company, job, CV, cover letter and answers.")
    if cv_guard and not cv_guard.get("passed", False):
        problems.append("The tailored CV has unverified claims. Fix them or regenerate.")
    if cover_guard and not cover_guard.get("passed", False):
        problems.append("The cover letter has unverified claims. Edit it before approving.")
    unanswered = [a["question"] for a in answers if a.get("needs_user_input") and not a.get("answer")
                  and not a.get("skip")]
    if unanswered:
        problems.append(f"{len(unanswered)} application question(s) need your answer or must be marked as skip.")
    return problems
