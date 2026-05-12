"""Admin auth: password hashing + signed session cookie.

Single-admin model for now (local self-host). Multi-user/multi-org is a
future expansion; keep this module the seam where that change lands.
"""
from __future__ import annotations

import os
import secrets as pysecrets
from typing import Annotated

import bcrypt
from fastapi import Cookie, Depends, HTTPException, Response
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .db import get_db
from . import models as m

COOKIE_NAME = "prashna_admin"
SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 days
# bcrypt silently truncates inputs beyond 72 bytes; reject longer to avoid
# users believing a long passphrase is fully protecting them.
MAX_PASSWORD_BYTES = 72

# Without PRASHNA_SECRET_KEY, sessions are valid only for the process lifetime.
# Set the env var in any real deployment so sessions survive restarts.
_secret = os.environ.get("PRASHNA_SECRET_KEY") or pysecrets.token_urlsafe(32)
_signer = TimestampSigner(_secret)


def hash_password(pw: str) -> str:
    pw_bytes = pw.encode("utf-8")
    if len(pw_bytes) > MAX_PASSWORD_BYTES:
        raise HTTPException(400, f"password must be at most {MAX_PASSWORD_BYTES} bytes")
    return bcrypt.hashpw(pw_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def issue_session(response: Response, user_id: int, session_version: int, *, secure: bool) -> None:
    # Cookie value is "user_id:session_version". The session_version comes
    # from the User row; bumping it on password change invalidates older
    # cookies even though they remain validly signed.
    token = _signer.sign(f"{user_id}:{session_version}").decode()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=secure,
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME)


def _parse_cookie(cookie: str | None) -> tuple[int, int] | None:
    """Return (user_id, session_version) from a signed cookie, or None."""
    if not cookie:
        return None
    try:
        raw = _signer.unsign(cookie, max_age=SESSION_MAX_AGE).decode()
    except (BadSignature, SignatureExpired):
        return None
    # Backwards-compat for older cookies (no session_version field).
    if ":" in raw:
        try:
            uid_str, ver_str = raw.split(":", 1)
            return int(uid_str), int(ver_str)
        except ValueError:
            return None
    try:
        return int(raw), 1
    except ValueError:
        return None


def current_admin(
    prashna_admin: Annotated[str | None, Cookie()] = None,
    db: DbSession = Depends(get_db),
) -> m.User:
    parsed = _parse_cookie(prashna_admin)
    if parsed is None:
        raise HTTPException(401, "Not authenticated")
    uid, ver = parsed
    u = db.get(m.User, uid)
    if u is None or u.session_version != ver:
        raise HTTPException(401, "Not authenticated")
    return u


def optional_admin(
    prashna_admin: Annotated[str | None, Cookie()] = None,
    db: DbSession = Depends(get_db),
) -> m.User | None:
    parsed = _parse_cookie(prashna_admin)
    if parsed is None:
        return None
    uid, ver = parsed
    u = db.get(m.User, uid)
    if u is None or u.session_version != ver:
        return None
    return u


def admin_exists(db: DbSession) -> bool:
    return db.scalar(select(m.User.id).limit(1)) is not None
