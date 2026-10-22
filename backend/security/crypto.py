"""Password hashing, access tokens and encryption of stored secrets (e.g. users' AI API keys)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt  # PyJWT

from backend.config import get_settings

_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 64}
TOKEN_ALGORITHM = "HS256"


class TokenError(ValueError):
    pass


def hash_password(password: str) -> str:
    if len(password) < 10:
        raise ValueError("Password must be at least 10 characters.")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, **_SCRYPT)
    return "scrypt${}${}".format(base64.b64encode(salt).decode(), base64.b64encode(digest).decode())


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_b64, digest_b64 = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    digest = hashlib.scrypt(password.encode("utf-8"), salt=base64.b64decode(salt_b64), **_SCRYPT)
    return hmac.compare_digest(digest, base64.b64decode(digest_b64))


def create_access_token(user_id: int, token_version: int = 0, minutes: int | None = None) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "ver": token_version, "iat": now,
               "exp": now + timedelta(minutes=minutes or settings.access_token_minutes), "typ": "access"}
    return jwt.encode(payload, settings.secret_key, algorithm=TOKEN_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[TOKEN_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    if payload.get("typ") != "access":
        raise TokenError("Wrong token type")
    return payload


def _fernet():
    from cryptography.fernet import Fernet

    settings = get_settings()
    material = settings.encryption_key or settings.secret_key
    key = base64.urlsafe_b64encode(hashlib.sha256(("aijh-secrets:" + material).encode()).digest())
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii") if value else ""


def decrypt_secret(token: str) -> str:
    if not token:
        return ""
    from cryptography.fernet import InvalidToken

    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        return ""


def mask_secret(value: str) -> str:
    return "" if not value else ("•" * 8 + value[-4:] if len(value) > 8 else "•" * len(value))


def _password_fingerprint(password_hash: str) -> str:
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]


def create_reset_token(user_id: int, password_hash: str, minutes: int = 30) -> str:
    """Single-use: the token embeds a fingerprint of the current password hash, so it stops
    working as soon as the password changes."""
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "typ": "reset", "pwfp": _password_fingerprint(password_hash), "iat": now,
               "exp": now + timedelta(minutes=minutes)}
    return jwt.encode(payload, get_settings().secret_key, algorithm=TOKEN_ALGORITHM)


def decode_reset_token(token: str, password_hash_lookup) -> int:
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[TOKEN_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise TokenError("This reset link is invalid or has expired.") from exc
    if payload.get("typ") != "reset":
        raise TokenError("Wrong token type")
    user_id = int(payload["sub"])
    current = password_hash_lookup(user_id)
    if not current or payload.get("pwfp") != _password_fingerprint(current):
        raise TokenError("This reset link was already used.")
    return user_id
