"""FastAPI dependencies: database session and the authenticated user."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session

from backend.db import get_session
from backend.models import User
from backend.security.crypto import TokenError, decode_access_token

SESSION_COOKIE = "aijh_session"


def _token_from_request(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.cookies.get(SESSION_COOKIE)


def current_user(request: Request, session: Session = Depends(get_session)) -> User:
    token = _token_from_request(request)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in.")
    try:
        payload = decode_access_token(token)
    except TokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired. Please sign in again.")
    user = session.get(User, int(payload["sub"]))
    if user is None or not user.is_active or payload.get("ver") != user.token_version:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session is no longer valid.")
    return user


def get_owned(session: Session, model, object_id: int, user: User):
    """Fetch a row that belongs to the user, or 404 (never reveal other users' rows)."""
    obj = session.get(model, object_id)
    if obj is None or getattr(obj, "user_id", None) != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    return obj
