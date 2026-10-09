"""GitHub OAuth admin login (UC-A-26).

Optional sign-in path for hosted deploys, allowlisted to specific GitHub
accounts. Runs alongside username/password login; password stays a
fallback. Enabled only when client id + secret + a non-empty allowlist
are all configured via env.

No new runtime dependency: the two GitHub calls use stdlib `urllib`.
The HTTP functions (`exchange_code`, `fetch_user`) are module-level so
tests can monkeypatch them without touching the network.
"""
from __future__ import annotations

import json
import os
import secrets
import urllib.parse
import urllib.request

from itsdangerous import BadSignature, SignatureExpired

from . import auth

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"
USER_URL = "https://api.github.com/user"
STATE_MAX_AGE = 600  # 10 minutes to complete the round-trip
_HTTP_TIMEOUT = 10


# ---------- configuration (read dynamically so tests can toggle env) ----------

def _client_id() -> str:
    return os.environ.get("PRASHNA_GITHUB_CLIENT_ID", "").strip()


def _client_secret() -> str:
    return os.environ.get("PRASHNA_GITHUB_CLIENT_SECRET", "").strip()


def admins() -> set[str]:
    raw = os.environ.get("PRASHNA_GITHUB_ADMINS", "")
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


def enabled() -> bool:
    return bool(_client_id() and _client_secret() and admins())


def is_allowed(login: str) -> bool:
    return bool(login) and login.lower() in admins()


# ---------- CSRF state ----------

def sign_state() -> str:
    return auth.new_signer().sign(secrets.token_urlsafe(16)).decode()


def check_state(state: str | None) -> bool:
    if not state:
        return False
    try:
        auth.new_signer().unsign(state, max_age=STATE_MAX_AGE)
        return True
    except (BadSignature, SignatureExpired):
        return False


# ---------- GitHub round-trip ----------

def authorize_url(state: str) -> str:
    q = urllib.parse.urlencode({
        "client_id": _client_id(),
        "state": state,
        "scope": "read:user",
        "allow_signup": "false",
    })
    return f"{AUTHORIZE_URL}?{q}"


def exchange_code(code: str) -> str | None:
    """Exchange an authorization code for an access token (or None)."""
    data = urllib.parse.urlencode({
        "client_id": _client_id(),
        "client_secret": _client_secret(),
        "code": code,
    }).encode()
    req = urllib.request.Request(
        TOKEN_URL, data=data,
        headers={"Accept": "application/json", "User-Agent": "prashna"},
    )
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as r:
            body = json.loads(r.read().decode())
    except Exception:
        return None
    return body.get("access_token")


def fetch_user(token: str) -> dict | None:
    """Fetch the authenticated GitHub user's public profile (or None)."""
    req = urllib.request.Request(
        USER_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "prashna",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None
