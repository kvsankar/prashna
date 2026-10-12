"""Admin auth: password hashing + signed session cookie.

Single-admin model for now (local self-host). Multi-user/multi-org is a
future expansion; keep this module the seam where that change lands.
"""
from __future__ import annotations

import logging
import os
import secrets as pysecrets
from pathlib import Path
from typing import Annotated

import bcrypt
from fastapi import Cookie, Depends, HTTPException, Response
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import models as m
from .db import DB_PATH, get_db

COOKIE_NAME = "prashna_admin"
SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 days
# bcrypt silently truncates inputs beyond 72 bytes; reject longer to avoid
# users believing a long passphrase is fully protecting them.
MAX_PASSWORD_BYTES = 72

# Operator-free state lives beside the database, so a backup of the data
# folder carries it: the signing key (UC-X-07) and, until an admin exists,
# the one-time setup token (UC-A-01).
DATA_DIR = DB_PATH.parent
SECRET_KEY_FILE = DATA_DIR / "secret-key"
SETUP_TOKEN_FILE = DATA_DIR / "setup-token"
# Generated values carry a fixed prefix so a scanner (scripts/check_pii.py)
# recognises a leaked key or token in any file, whatever it is called.
SECRET_KEY_PREFIX = "prashna_sk_"  # pragma: allowlist secret
SETUP_TOKEN_PREFIX = "prashna_st_"

logger = logging.getLogger("prashna")


# A stored key or token shorter than this is corrupt, for example an empty
# file left by a crash or a full disk, and is replaced (UC-X-07).
MIN_STORED_SECRET_CHARS = 32


def _write_private(path: Path, value: str, *, replace: bool) -> None:
    """Write `path`, readable only by this user, whole: into a temporary file
    first, then moved into place, so a crash never leaves it half-written.
    Without `replace`, raise FileExistsError if `path` already exists."""
    tmp = path.with_name(f".{path.name}.{pysecrets.token_hex(8)}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(value + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        if replace:
            os.replace(tmp, path)
            return
        try:
            os.link(tmp, path)  # atomic create-if-absent
        except FileExistsError:
            raise
        except OSError:  # a filesystem without hard links
            os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _read_or_create(path: Path, make) -> str:
    try:
        stored: str | None = path.read_text().strip()
    except FileNotFoundError:
        stored = None
    if stored is not None and len(stored) >= MIN_STORED_SECRET_CHARS:
        return stored
    value = make()
    if stored is None:
        try:
            _write_private(path, value, replace=False)
            return value
        except FileExistsError:  # another start won the race; use its value
            stored = path.read_text().strip()
            if len(stored) >= MIN_STORED_SECRET_CHARS:
                return stored
    logger.warning("%s was empty or too short; replaced it with a new value (UC-X-07).", path)
    _write_private(path, value, replace=True)
    return value


def _resolve_secret(env_value: str | None, key_file: Path) -> tuple[str, bool]:
    """Return (signing_key, is_ephemeral) (UC-X-07).

    PRASHNA_SECRET_KEY wins. Otherwise the key is read from, or created in,
    `key_file`, so sessions survive restarts with no operator step. Only if
    that file can't be used do we fall back to a process-lifetime key
    (ephemeral), which startup warns about.
    """
    if env_value:
        return env_value, False
    try:
        return _read_or_create(key_file, lambda: SECRET_KEY_PREFIX + pysecrets.token_urlsafe(48)), False
    except OSError:
        return SECRET_KEY_PREFIX + pysecrets.token_urlsafe(32), True


_secret, SECRET_KEY_IS_EPHEMERAL = _resolve_secret(os.environ.get("PRASHNA_SECRET_KEY"), SECRET_KEY_FILE)
if not _secret:  # never sign with an empty key (UC-X-07)
    raise RuntimeError("The admin signing key is empty.")
_signer = TimestampSigner(_secret)


def hash_password(pw: str) -> str:
    """bcrypt-hash *pw*. Raises ValueError past 72 bytes; the routes turn it
    into a 400 and the command line into a plain message (UC-A-25, UC-X-15)."""
    pw_bytes = pw.encode("utf-8")
    if len(pw_bytes) > MAX_PASSWORD_BYTES:
        raise ValueError(f"password must be at most {MAX_PASSWORD_BYTES} bytes")
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


# ---------- one-time first-admin setup token (UC-A-01) ----------

def setup_token(db: DbSession) -> str | None:
    """The token that authorizes creating the first admin, or None once an
    admin exists. PRASHNA_SETUP_TOKEN wins; otherwise a random token is kept
    in SETUP_TOKEN_FILE and reused across restarts until setup completes."""
    if admin_exists(db):
        retire_setup_token()
        return None
    env_token = os.environ.get("PRASHNA_SETUP_TOKEN", "").strip()
    if env_token:
        return env_token
    return _read_or_create(SETUP_TOKEN_FILE, lambda: SETUP_TOKEN_PREFIX + pysecrets.token_urlsafe(24))


def setup_token_matches(db: DbSession, supplied: object) -> bool:
    expected = setup_token(db)
    return bool(expected) and isinstance(supplied, str) and pysecrets.compare_digest(supplied, expected)


def retire_setup_token() -> None:
    try:
        SETUP_TOKEN_FILE.unlink()
    except FileNotFoundError:
        pass
