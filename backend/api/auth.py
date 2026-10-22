from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field
from sqlmodel import Session, select

from backend.api.deps import SESSION_COOKIE, current_user
from backend.config import get_settings
from backend.db import get_session
from backend.models import User
from backend.schemas.api import LoginIn, RegisterIn, UserOut
from backend.security.crypto import (TokenError, create_access_token, create_reset_token, decode_reset_token,
                                     hash_password, verify_password)
from backend.security.guards import RateLimiter, login_limiter
from backend.services.account_service import delete_account, export_user_data
from backend.services.common import audit
from backend.utils.mailer import email_configured, send_email

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_session(response: Response, user: User) -> dict:
    settings = get_settings()
    token = create_access_token(user.id, user.token_version)
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", secure=settings.is_production,
                        max_age=settings.access_token_minutes * 60, path="/")
    return {"user": UserOut(id=user.id, email=user.email, full_name=user.full_name).model_dump(),
            "access_token": token, "token_type": "bearer"}


@router.post("/register")
def register(body: RegisterIn, response: Response, session: Session = Depends(get_session)):
    settings = get_settings()
    has_users = session.exec(select(User)).first() is not None
    if has_users and not settings.allow_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Registration is disabled on this server.")
    email = body.email.lower()
    if session.exec(select(User).where(User.email == email)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    try:
        password_hash = hash_password(body.password)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    user = User(email=email, password_hash=password_hash, full_name=body.full_name.strip())
    session.add(user)
    session.flush()
    if body.ref:
        from backend.services.billing import apply_referral

        apply_referral(session, user, body.ref)
    audit(session, user.id, "auth.registered")
    session.commit()
    session.refresh(user)
    return _set_session(response, user)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, session: Session = Depends(get_session)):
    key = f"{request.client.host if request.client else 'unknown'}:{body.email.lower()}"
    if not login_limiter.hit(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Try again in a few minutes.")
    user = session.exec(select(User).where(User.email == body.email.lower())).first()
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        audit(session, user.id if user else None, "auth.login_failed", email=body.email.lower())
        session.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
    login_limiter.reset(key)
    audit(session, user.id, "auth.login")
    session.commit()
    return _set_session(response, user)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.post("/logout-everywhere")
def logout_everywhere(response: Response, user: User = Depends(current_user), session: Session = Depends(get_session)):
    user = session.get(User, user.id)
    user.token_version += 1
    session.add(user)
    audit(session, user.id, "auth.revoked_all_sessions")
    session.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return UserOut(id=user.id, email=user.email, full_name=user.full_name)


@router.get("/status")
def auth_status(session: Session = Depends(get_session)):
    """Lets the UI show 'create the first account' vs 'sign in'."""
    has_users = session.exec(select(User)).first() is not None
    return {"has_users": has_users, "registration_open": (not has_users) or get_settings().allow_registration}


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str = Field(max_length=2000)
    password: str = Field(min_length=10, max_length=200)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(min_length=10, max_length=200)


class DeleteAccountIn(BaseModel):
    password: str = Field(max_length=200)
    confirm: str = Field(max_length=20)  # must be "DELETE"


reset_limiter = RateLimiter(max_events=5, window_seconds=3600)


@router.post("/forgot-password")
def forgot_password(body: ForgotIn, request: Request, session: Session = Depends(get_session)):
    """Always answers the same way, so it can't be used to find out who has an account."""
    key = f"{request.client.host if request.client else 'unknown'}:{body.email.lower()}"
    if reset_limiter.hit(key):
        user = session.exec(select(User).where(User.email == body.email.lower())).first()
        if user and user.is_active:
            token = create_reset_token(user.id, user.password_hash)
            link = f"{get_settings().public_url}/reset-password?token={token}"
            send_email(user.email, "Reset your AI Job Hunter password",
                       f"Hello,\n\nUse this link within 30 minutes to choose a new password:\n{link}\n\n"
                       "If you didn't ask for this, ignore this email; your password stays the same.")
            audit(session, user.id, "auth.reset_requested")
            session.commit()
    return {"ok": True, "message": "If that email has an account, a reset link is on its way.",
            "email_enabled": email_configured()}


@router.post("/reset-password")
def reset_password(body: ResetIn, response: Response, session: Session = Depends(get_session)):
    def lookup(user_id: int) -> str:
        u = session.get(User, user_id)
        return u.password_hash if u else ""

    try:
        user_id = decode_reset_token(body.token, lookup)
    except TokenError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    user = session.get(User, user_id)
    user.password_hash = hash_password(body.password)
    user.token_version += 1  # signs out every device
    session.add(user)
    audit(session, user.id, "auth.password_reset")
    session.commit()
    return _set_session(response, user)


@router.post("/change-password")
def change_password(body: ChangePasswordIn, response: Response, user: User = Depends(current_user),
                    session: Session = Depends(get_session)):
    user = session.get(User, user.id)
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your current password is not correct.")
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1
    session.add(user)
    audit(session, user.id, "auth.password_changed")
    session.commit()
    return _set_session(response, user)


@router.get("/export")
def export_data(user: User = Depends(current_user), session: Session = Depends(get_session)):
    data = export_user_data(session, session.get(User, user.id))
    return JSONResponse(data, headers={"Content-Disposition": 'attachment; filename="ai-job-hunter-export.json"'})


@router.post("/delete-account")
def delete_account_route(body: DeleteAccountIn, response: Response, user: User = Depends(current_user),
                         session: Session = Depends(get_session)):
    user = session.get(User, user.id)
    if body.confirm != "DELETE":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Type DELETE to confirm.")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your password is not correct.")
    delete_account(session, user)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/config")
def public_config():
    """Non-secret settings the app needs before sign-in."""
    s = get_settings()
    return {"operator_name": s.operator_name, "support_email": s.support_email, "public_url": s.public_url,
            "email_enabled": email_configured(), "apply_assist_enabled": s.apply_assist_enabled,
            "ads": {"enabled": s.ads_enabled, "test_mode": s.ads_test_mode, "adsense_client": s.adsense_client,
                    "adsense_slot_waiting": s.adsense_slot_waiting, "adsense_slot_feed": s.adsense_slot_feed,
                    "admob_banner_android": s.admob_banner_android, "admob_banner_ios": s.admob_banner_ios,
                    "admob_rewarded_android": s.admob_rewarded_android, "admob_rewarded_ios": s.admob_rewarded_ios}}
