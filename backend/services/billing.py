"""Plans, limits, rewarded-ad credits, referrals and RevenueCat subscription sync.

Free: ads, FREE_DRAFTS_PER_DAY applications/day (+ rewarded-ad bonus), FREE_SEARCHES_PER_DAY searches.
Pro:  no ads, MAX_DRAFTS_PER_DAY applications/day, PRO_SEARCHES_PER_DAY searches, server AI rewriting.

Store rules: in the iOS/Android apps Pro is sold only through Apple/Google in-app purchase (via
RevenueCat). The server never trusts the client about purchases; it asks RevenueCat.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlmodel import Session, select

from backend.config import get_settings
from backend.models import Application, BonusCredit, DiscoveryRun, User

log = logging.getLogger(__name__)
REFERRAL_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
MAX_REFERRAL_REWARDS = 20


class LimitReached(ValueError):
    def __init__(self, message: str, kind: str):
        super().__init__(message)
        self.kind = kind


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def today() -> str:
    return _now().strftime("%Y-%m-%d")


def is_pro(user: User) -> bool:
    if user.plan != "pro":
        return False
    expires = _aware(user.plan_expires_at)
    return expires is None or expires > _now()


def _start_of_day() -> datetime:
    n = _now()
    return n.replace(hour=0, minute=0, second=0, microsecond=0)


def status(session: Session, user: User) -> dict:
    s = get_settings()
    pro = is_pro(user)
    day_start = _start_of_day()
    drafts_used = session.exec(select(func.count()).select_from(Application).where(
        Application.user_id == user.id, Application.created_at >= day_start)).one()
    searches_used = session.exec(select(func.count()).select_from(DiscoveryRun).where(
        DiscoveryRun.user_id == user.id, DiscoveryRun.trigger == "manual", DiscoveryRun.started_at >= day_start)).one()
    bonus_rows = session.exec(select(BonusCredit).where(BonusCredit.user_id == user.id,
                                                        BonusCredit.valid_on == today())).all()
    bonus = sum(b.amount for b in bonus_rows)
    rewards_used = sum(1 for b in bonus_rows if b.kind == "rewarded_ad")
    drafts_limit = s.max_drafts_per_day if pro else s.free_drafts_per_day + bonus
    return {
        "plan": "pro" if pro else "free",
        "plan_expires_at": _aware(user.plan_expires_at).isoformat() if pro and user.plan_expires_at else None,
        "plan_source": user.plan_source if pro else "",
        "show_ads": not pro,
        "drafts_per_day": drafts_limit, "drafts_used_today": drafts_used,
        "searches_per_day": s.pro_searches_per_day if pro else s.free_searches_per_day,
        "searches_used_today": searches_used,
        "bonus_today": bonus,
        "limits": {"free_drafts": s.free_drafts_per_day, "pro_drafts": s.max_drafts_per_day,
                   "free_searches": s.free_searches_per_day, "pro_searches": s.pro_searches_per_day},
        "reward_ads_left": 0 if pro else max(0, s.reward_ads_per_day - rewards_used),
        "reward_ad_bonus": s.reward_ad_bonus,
        "server_ai": pro or s.server_ai_for_free_users,
        "referral_code": user.referral_code,
        "referral_pro_days": s.referral_pro_days,
        "purchases": {"ios": s.revenuecat_public_ios, "android": s.revenuecat_public_android,
                      "web": s.revenuecat_public_web, "entitlement": s.pro_entitlement},
    }


def check_draft_allowed(session: Session, user_id: int) -> None:
    user = session.get(User, user_id)
    st = status(session, user)
    if st["drafts_used_today"] >= st["drafts_per_day"]:
        if st["plan"] == "pro":
            raise LimitReached("You've reached today's application limit. It resets at midnight UTC.", "drafts")
        raise LimitReached(f"You've used today's {st['drafts_per_day']} free applications. Watch a short ad for "
                           f"{st['reward_ad_bonus']} more, or go Pro for up to {get_settings().max_drafts_per_day} a day.",
                           "drafts")


def check_search_allowed(session: Session, user: User) -> None:
    st = status(session, user)
    if st["searches_used_today"] >= st["searches_per_day"]:
        raise LimitReached("You've reached today's search limit. New jobs are still found automatically; "
                           + ("" if st["plan"] == "pro" else "Pro includes more searches a day."), "searches")


def grant_reward(session: Session, user: User) -> dict:
    """Called after the app's rewarded ad reports a completed view. Capped per day.
    For stronger protection enable AdMob server-side verification (see docs/MONETIZATION.md)."""
    st = status(session, user)
    if st["plan"] == "pro":
        raise LimitReached("Pro already has the higher limit.", "reward")
    if st["reward_ads_left"] <= 0:
        raise LimitReached("You've used today's ad bonuses. More tomorrow.", "reward")
    s = get_settings()
    session.add(BonusCredit(user_id=user.id, kind="rewarded_ad", amount=s.reward_ad_bonus, valid_on=today()))
    session.commit()
    return status(session, user)


# ------------------------------------------------------------------------------------- referrals
def ensure_referral_code(session: Session, user: User) -> str:
    if user.referral_code:
        return user.referral_code
    for _ in range(10):
        code = "".join(secrets.choice(REFERRAL_ALPHABET) for _ in range(8))
        if not session.exec(select(User).where(User.referral_code == code)).first():
            user.referral_code = code
            session.add(user)
            session.commit()
            return code
    raise RuntimeError("Could not create a referral code")


def extend_pro(user: User, days: int, source: str) -> None:
    if user.plan == "pro" and user.plan_expires_at is None:
        return  # lifetime / store-managed without expiry
    base = _aware(user.plan_expires_at) if is_pro(user) else _now()
    user.plan = "pro"
    user.plan_expires_at = (base or _now()) + timedelta(days=days)
    if not user.plan_source or user.plan_source == "referral":
        user.plan_source = source


def apply_referral(session: Session, new_user: User, code: str) -> bool:
    code = (code or "").strip().upper()
    if not code:
        return False
    referrer = session.exec(select(User).where(User.referral_code == code)).first()
    if referrer is None or referrer.id == new_user.id:
        return False
    days = get_settings().referral_pro_days
    new_user.referred_by = referrer.id
    extend_pro(new_user, days, "referral")
    rewarded = session.exec(select(func.count()).select_from(User).where(User.referred_by == referrer.id)).one()
    if rewarded <= MAX_REFERRAL_REWARDS:
        extend_pro(referrer, days, "referral")
    session.add(new_user)
    session.add(referrer)
    return True


# ------------------------------------------------------------------------------------- RevenueCat
def sync_revenuecat(session: Session, user: User) -> bool:
    """Ask RevenueCat for the user's real entitlements and update the plan. Returns True if Pro."""
    import httpx

    s = get_settings()
    if not s.revenuecat_secret_key:
        return is_pro(user)
    try:
        r = httpx.get(f"https://api.revenuecat.com/v1/subscribers/{user.id}",
                      headers={"Authorization": f"Bearer {s.revenuecat_secret_key}"}, timeout=15)
        r.raise_for_status()
        ent = ((r.json().get("subscriber") or {}).get("entitlements") or {}).get(s.pro_entitlement)
    except Exception as exc:  # network or API problem: keep the current plan
        log.warning("RevenueCat sync failed for user %s: %s", user.id, exc)
        return is_pro(user)
    store_active = False
    expires = None
    if ent:
        raw = ent.get("expires_date")
        expires = datetime.fromisoformat(raw.replace("Z", "+00:00")) if raw else None
        store_active = expires is None or expires > _now()
    if store_active:
        user.plan, user.plan_expires_at, user.plan_source = "pro", expires, "store"
    elif user.plan_source == "store":
        user.plan, user.plan_expires_at, user.plan_source = "free", None, ""
    session.add(user)
    session.commit()
    return is_pro(user)
