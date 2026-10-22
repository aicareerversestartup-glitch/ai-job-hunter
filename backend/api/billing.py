"""Plans and payments, rewarded ads, referrals, partner links."""
from __future__ import annotations

import hmac
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from backend.api.deps import current_user
from backend.config import ROOT_DIR, get_settings
from backend.db import get_session
from backend.models import User
from backend.services import billing
from backend.services.common import audit

router = APIRouter(prefix="/api", tags=["billing"])
PARTNERS_FILE = ROOT_DIR / "data" / "partners.json"


@router.get("/billing/status")
def billing_status(user: User = Depends(current_user), session: Session = Depends(get_session)):
    user = session.get(User, user.id)
    billing.ensure_referral_code(session, user)
    return billing.status(session, user)


@router.post("/billing/sync")
def billing_sync(user: User = Depends(current_user), session: Session = Depends(get_session)):
    """Called by the app right after a purchase or 'Restore purchases'."""
    user = session.get(User, user.id)
    billing.sync_revenuecat(session, user)
    return billing.status(session, user)


@router.post("/billing/reward-ad")
def reward_ad(user: User = Depends(current_user), session: Session = Depends(get_session)):
    user = session.get(User, user.id)
    try:
        result = billing.grant_reward(session, user)
    except billing.LimitReached as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc))
    audit(session, user.id, "billing.reward_ad")
    session.commit()
    return result


@router.post("/billing/revenuecat")
async def revenuecat_webhook(request: Request, session: Session = Depends(get_session)):
    """RevenueCat webhook. Verified with the Authorization header you configure in RevenueCat; the plan is
    then read back from RevenueCat's API instead of trusting the payload."""
    expected = get_settings().revenuecat_webhook_auth
    got = request.headers.get("Authorization", "")
    if not expected or not hmac.compare_digest(got, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad webhook authorization.")
    try:
        event = (await request.json()).get("event") or {}
    except json.JSONDecodeError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid JSON.")
    ids = {str(event.get("app_user_id") or ""), str(event.get("original_app_user_id") or ""),
           *[str(a) for a in event.get("aliases") or []]}
    for candidate in ids:
        if candidate.isdigit():
            user = session.get(User, int(candidate))
            if user:
                billing.sync_revenuecat(session, user)
                audit(session, user.id, "billing.webhook", type=event.get("type", ""))
                session.commit()
                break
    return {"ok": True}


# ------------------------------------------------------------------------------------- partners
def _partners() -> list[dict]:
    if not Path(PARTNERS_FILE).exists():
        return []
    data = json.loads(Path(PARTNERS_FILE).read_text(encoding="utf-8"))
    return [p for p in data.get("partners", []) if p.get("enabled", True) and p.get("url")]


@router.get("/partners")
def partners(user: User = Depends(current_user)):
    return [{k: p.get(k, "") for k in ("id", "name", "category", "description", "countries", "disclosure")}
            for p in _partners()]


@router.get("/partners/{partner_id}/go")
def partner_go(partner_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)):
    partner = next((p for p in _partners() if p.get("id") == partner_id), None)
    if partner is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    audit(session, user.id, "partner.click", partner=partner_id)  # click counts only; nothing personal is shared
    session.commit()
    return {"url": partner["url"]}


@router.get("/r/{code}", include_in_schema=False)
def referral_link(code: str):
    return RedirectResponse(f"/signup?ref={code.upper()[:16]}")
