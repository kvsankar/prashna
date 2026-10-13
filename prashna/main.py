"""Prashna — live Q&A + quiz tool for training sessions."""
from __future__ import annotations

import json
import logging
import math
import os
import re
import secrets
import threading
import time
import uuid
from collections import Counter
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware

from . import auth
from . import export as data_export
from . import models as m
from .db import SessionLocal, default_data_dir, get_db, init_db
from .diagnostics import log_diagnostic
from .ratelimit import DEFAULT_LIMITS, TokenBucketLimiter, enabled_from_env, validated_limits
from .ws import hub

# Vite build output (the TypeScript frontend). Produced by `npm run build`
# (and by the Docker build stage in prod). Pages 404 until it exists — in
# dev use the Vite dev server (`npm run dev`) which proxies the API here.
# The Vite build lives inside the package (vite.config.ts outDir), so a
# source checkout, the Docker image, and the installed wheel all serve it.
STATIC = Path(__file__).resolve().parent / "static"
UPLOADS = Path(os.environ.get("PRASHNA_UPLOADS_DIR") or (default_data_dir() / "uploads"))
UPLOADS.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
PRESENCE_WINDOW = timedelta(seconds=30)
LAST_SEEN_THROTTLE = timedelta(seconds=5)

# ---------- rate limiting (UC-X-08) ----------
# Single-process in-memory limiter. See prashna/ratelimit.py.
limiter = TokenBucketLimiter(enabled=enabled_from_env(os.environ.get("PRASHNA_RATELIMIT")))

# Number of trusted reverse-proxy hops in front of the app. 0 (default) =
# use the socket peer (correct for direct localhost; degrades to a global
# throttle behind a proxy). Set to 1 when fronted by ngrok or the bundled
# nginx (a single hop) so the limiter keys on the real client IP and not a
# spoofable X-Forwarded-For prefix.
TRUSTED_PROXY_HOPS = max(0, int(os.environ.get("PRASHNA_TRUSTED_PROXY_HOPS") or 0))

# Fixed per-address buckets: (capacity = burst, refill = tokens/second).
RL_LOGIN = (8, 1 / 30)       # admin login attempts per IP
RL_PERFORMANCE = (10, 0.2)   # non-blocking usable-UI samples per IP

# The adjustable limits (UC-A-31): the defaults until load_limits() reads
# the admin's saved values at start; PUT /api/admin/limits updates them in
# place, so a change applies to the next request.
limits: dict[str, int] = dict(DEFAULT_LIMITS)


def load_limits(db: DbSession) -> None:
    row = db.get(m.Setting, "limits")
    saved = json.loads(row.value) if row else {}
    try:
        limits.update(validated_limits(DEFAULT_LIMITS, {k: v for k, v in saved.items() if k in DEFAULT_LIMITS}))
    except ValueError:
        logger.warning("Saved limits are invalid; using the defaults (UC-A-31).")
        limits.update(DEFAULT_LIMITS)


def allow_person(action: str, request: Request, voter_token: str | None) -> bool:
    """One person's bucket, then the address ceiling: "network_size" people's
    allowance, so a room behind one address never shares a budget (UC-X-08)."""
    burst = limits[f"{action}_burst"]
    rate = limits[f"{action}_per_minute"] / 60
    people = limits["network_size"]
    ip = _client_ip(request)
    return (limiter.allow(f"{action}:person:{voter_token or ip}", burst, rate)
            and limiter.allow(f"{action}:address:{ip}", burst * people, rate * people))

PAGE_BROWSER_CACHE = "public, max-age=0, must-revalidate"
PAGE_CDN_CACHE = "public, s-maxage=300, stale-while-revalidate=60"
PERFORMANCE_ROLES = {"landing", "participant", "moderator", "projector", "quizzes"}


def _client_ip(request: Request) -> str:
    """Best-effort client IP for rate-limit keying.

    With `TRUSTED_PROXY_HOPS = N > 0`, the client is the X-Forwarded-For
    entry the outermost trusted proxy recorded (the N-th from the right) —
    spoof-resistant, since a client-supplied prefix sits to its left. With
    N = 0 we use the socket peer.
    """
    if TRUSTED_PROXY_HOPS > 0:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            parts = [p.strip() for p in xff.split(",") if p.strip()]
            if parts:
                return parts[-min(TRUSTED_PROXY_HOPS, len(parts))]
    return request.client.host if request.client else "unknown"


def _is_https(request: Request) -> bool:
    """Whether the visitor used HTTPS, for the cookies' Secure flag. Behind
    a declared trusted proxy (hops > 0) the proxy's X-Forwarded-Proto
    counts too, whatever address the proxy connects from (UC-X-08)."""
    if request.url.scheme == "https":
        return True
    if TRUSTED_PROXY_HOPS > 0:
        proto = request.headers.get("x-forwarded-proto", "")
        return proto.split(",")[-1].strip().lower() == "https"
    return False


logger = logging.getLogger("prashna")


def _diagnostic_path(path: str) -> str:
    parts = [part for part in path.split("/") if part]
    if len(parts) >= 3 and parts[0] == "api" and parts[1] == "sessions":
        parts[2] = ":code"
    elif len(parts) >= 2 and parts[0] in {"s", "m", "p"}:
        parts[1] = ":code"
    return "/" + "/".join(parts)


# The `prashna` command prints the setup link itself (as a full URL), so it
# turns this off to keep the link from appearing twice.
ANNOUNCE_SETUP_LINK: bool = True
# The public address of the tunnel `prashna --tunnel` started, if any. Pages
# use it for participant links and QR codes when a session has no base URL
# of its own (UC-A-06, UC-X-15).
PUBLIC_URL: str | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    if auth.SECRET_KEY_IS_EPHEMERAL:
        logger.warning(
            "PRASHNA_SECRET_KEY is not set and %s can't be written — admin "
            "sessions use an ephemeral signing key and end on every restart. "
            "Make the data folder writable or set PRASHNA_SECRET_KEY (UC-X-07).",
            auth.SECRET_KEY_FILE,
        )
    with SessionLocal() as db:
        load_limits(db)
        token = auth.setup_token(db)
    if token and ANNOUNCE_SETUP_LINK:
        # The only place the first-admin link appears (UC-A-01).
        logger.warning(
            "No admin yet. Create one by opening this one-time link on this "
            "server's address: /#setup=%s", token,
        )
    yield


app = FastAPI(title="Prashna", lifespan=lifespan)


class SecurityHeaders(BaseHTTPMiddleware):
    """HTTP security headers (UC-X-03).

    Two tiers: a strict isolation set for user-uploaded files under
    `/uploads/`, and a clickjacking/sniffing baseline for every other
    response (pages + API). The baseline deliberately omits a `script-src`
    CSP — the no-build pages rely on inline module scripts — and uses
    `frame-ancestors 'none'`, the high-value directive that doesn't break
    them.
    """

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/uploads/"):
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
            response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        else:
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("X-Frame-Options", "DENY")
            response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'")
            response.headers.setdefault("Referrer-Policy", "no-referrer")
        page_shell = (
            path in {"/", "/quizzes"}
            or path.startswith(("/s/", "/m/", "/p/"))
        )
        if path.startswith("/static/assets/"):
            # Vite fingerprints these filenames, so they are safe to retain
            # across visits without a revalidation round trip.
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif page_shell and response.status_code == 200:
            # Page files contain no user/session state. Browsers revalidate so
            # a deploy cannot strand an old HTML shell, while a CDN may retain
            # the shell briefly and absorb the geographic origin round trip.
            response.headers["Cache-Control"] = PAGE_BROWSER_CACHE
            response.headers["CDN-Cache-Control"] = PAGE_CDN_CACHE
        elif page_shell:
            # In particular, never let the CDN retain a bad-code redirect.
            response.headers["Cache-Control"] = "no-store"
            if "CDN-Cache-Control" in response.headers:
                del response.headers["CDN-Cache-Control"]
        elif path.startswith("/static/"):
            response.headers.setdefault("Cache-Control", "no-cache")
        elif path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


class RequestTiming:
    """Emit safe duration diagnostics for mutating and slow HTTP requests."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status_code = 500

        async def send_with_status(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                app_ms = (time.perf_counter() - started) * 1000
                headers = list(message.get("headers", []))
                headers.append((b"server-timing", f"app;dur={app_ms:.2f}".encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            method = scope["method"].upper()
            if method not in {"GET", "HEAD", "OPTIONS"} or duration_ms >= 1000:
                log_diagnostic(
                    "http.request",
                    outcome="success" if status_code < 500 else "failure",
                    method=method,
                    path=_diagnostic_path(scope["path"]),
                    status_code=status_code,
                    duration_ms=duration_ms,
                )


app.add_middleware(RequestTiming)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(SecurityHeaders)

app.mount("/uploads", StaticFiles(directory=UPLOADS), name="uploads")
# Mounted only when a build exists, so importing the app (e.g. the API tests,
# which don't build the frontend) never fails on a missing dist dir.
if STATIC.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")


# ---------- helpers ----------

MIN_PASSWORD_LEN = 8
MAX_USERNAME_LEN = 80


def _text(payload: dict, field: str) -> str:
    """A JSON text field: "" when absent or null, `400 "<field> must be
    text"` for any other JSON type, so a wrong type never reaches `.strip()`
    or the database (UC-X-05)."""
    value = payload.get(field)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise HTTPException(400, f"{field} must be text")
    return value


def _order_index(value: Any) -> int:
    """An `order_index` from JSON, as an integer or `400` (UC-A-14..18)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        raise HTTPException(400, "order_index must be an integer")


def _hash_password(password: str) -> str:
    """auth.hash_password, with its length error as a 400 (UC-A-25)."""
    try:
        return auth.hash_password(password)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


def _validate_credentials(username: str, password: str) -> tuple[str, str]:
    u = username.strip()
    if not u or len(u) > MAX_USERNAME_LEN:
        raise HTTPException(400, "Username is required")
    if not password or len(password) < MIN_PASSWORD_LEN:
        raise HTTPException(400, f"Password must be at least {MIN_PASSWORD_LEN} characters")
    return u, password


def gen_code(n: int = 6) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(n))


def gen_token() -> str:
    return uuid.uuid4().hex


def _set_voter_cookie(request: Request, response: Response, token: str) -> None:
    """voter_token is non-HttpOnly on purpose — frontend reads it for 'mine' checks."""
    secure = _is_https(request)
    response.set_cookie(
        "voter_token",
        token,
        max_age=60 * 60 * 24 * 365,
        httponly=False,
        samesite="lax",
        secure=secure,
    )


def get_session_by_code(db: DbSession, code: str) -> m.Session:
    s = db.scalar(select(m.Session).where(m.Session.code == code.upper()))
    if not s:
        raise HTTPException(404, "Session not found")
    return s


def is_admin_owner(session: m.Session, user: m.User | None) -> bool:
    return user is not None and session.owner_user_id == user.id


def is_mod_authed(session: m.Session, mod_key: str | None) -> bool:
    return bool(mod_key) and secrets.compare_digest(mod_key, session.mod_key)


def require_mod_or_owner(
    session: m.Session,
    mod_key: str | None,
    user: m.User | None,
) -> None:
    """Authorize a session-moderation action.

    Admin owners reach moderator routes via their admin cookie without
    needing the mod_key URL fragment. The mod_key path remains so the
    owner can share moderation with a delegate (TA, co-host) who does
    not have an admin account.
    """
    if is_admin_owner(session, user) or is_mod_authed(session, mod_key):
        return
    raise HTTPException(403, "Not authorized — moderator key or admin login required")


def require_session_owner(session: m.Session, user: m.User) -> None:
    if session.owner_user_id != user.id:
        raise HTTPException(403, "Not your session")


def current_participant(
    session: m.Session,
    request: Request,
    response: Response,
    voter_token: str | None,
    db: DbSession,
) -> m.Participant:
    token = voter_token
    fresh = False
    if not token:
        token = gen_token()
        fresh = True
    p = db.scalar(select(m.Participant).where(
        m.Participant.session_id == session.id,
        m.Participant.voter_token == token,
    ))
    if not p:
        # Bound fresh-row creation per IP: a flooder rotating voter_token
        # cookies could otherwise mint unbounded Participants and inflate
        # presence counts (UC-X-08 / S4).
        if not limiter.allow(f"newp:{_client_ip(request)}", limits["network_size"],
                             limits["join_per_minute"] / 60):
            raise HTTPException(429, "Too many new participants from your network — slow down")
        p = m.Participant(session_id=session.id, voter_token=token)
        db.add(p)
        try:
            db.commit()
            db.refresh(p)
        except IntegrityError:
            # A concurrent request (e.g. the projector firing /queries and
            # /quiz_runs in parallel) inserted the same (session, voter_token)
            # first. Re-resolve to the winner's row instead of 500-ing.
            db.rollback()
            p = db.scalar(select(m.Participant).where(
                m.Participant.session_id == session.id,
                m.Participant.voter_token == token,
            ))
            if p is None:
                raise
    else:
        nowt = datetime.utcnow()
        if nowt - p.last_seen_at >= LAST_SEEN_THROTTLE:
            p.last_seen_at = nowt
            db.commit()
    if fresh:
        _set_voter_cookie(request, response, token)
    return p


def participant_count_online(db: DbSession, session: m.Session) -> int:
    cutoff = datetime.utcnow() - PRESENCE_WINDOW
    return db.scalar(
        select(func.count(m.Participant.id))
        .where(m.Participant.session_id == session.id, m.Participant.last_seen_at >= cutoff)
    ) or 0


# ---------- serialization ----------

PROFILE_FIELDS = {
    "name": 80,
    "email": 254,
    "contact_number": 40,
    "organization": 120,
    "role": 120,
    "linkedin_url": 500,
    "current_work": 500,
    "learning_goal": 500,
}


# Every API timestamp is UTC with `Z`, the same form as the exports.
iso = data_export.iso


def serialize_session(s: m.Session, *, include_mod_key: bool = False) -> dict:
    body = {
        "code": s.code,
        "title": s.title,
        "status": s.status,
        "participant_base_url": s.participant_base_url,
        "default_base_url": PUBLIC_URL,
        "feedback_enabled": bool(s.feedback_enabled),
        "created_at": iso(s.created_at),
        "started_at": iso(s.started_at),
        "ended_at": iso(s.ended_at),
    }
    if include_mod_key:
        body["mod_key"] = s.mod_key
    return body


def normalize_optional_text(payload: dict, field: str, max_len: int) -> str | None:
    text = _text(payload, field).strip()
    return text[:max_len] or None


def serialize_participant_profile(p: m.Participant) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "email": p.email,
        "contact_number": p.contact_number,
        "organization": p.organization,
        "role": p.role,
        "linkedin_url": p.linkedin_url,
        "photo_url": p.photo_url,
        "current_work": p.current_work,
        "learning_goal": p.learning_goal,
    }


def serialize_feedback(f: m.SessionFeedback) -> dict:
    """Feedback is anonymous: no name or participant id (Anonymity)."""
    return {
        "rating": f.rating,
        "went_well": f.went_well,
        "to_improve": f.to_improve,
        "updated_at": iso(f.updated_at),
    }


def participant_has_profile(p: m.Participant) -> bool:
    return (
        p.photo_url is not None
        or any(getattr(p, field) for field in PROFILE_FIELDS)
    )


def serialize_query(q: m.Query, viewer_participant_id: int | None) -> dict:
    return {
        "id": q.id,
        "text": q.text,
        "author_name": q.author_name,
        "response_text": q.response_text,
        "responded": q.responded_at is not None,
        "removed": q.removed_at is not None,
        "vote_count": len(q.votes),
        "voted": any(v.participant_id == viewer_participant_id for v in q.votes),
        "mine": q.participant_id == viewer_participant_id,
        "created_at": iso(q.created_at),
    }


def serialize_quiz(quiz: m.Quiz, include_correct: bool = False) -> dict:
    return {
        "id": quiz.id,
        "title": quiz.title,
        "status": quiz.status,
        "questions": [
            {
                "id": qq.id,
                "text": qq.text,
                "image_url": qq.image_url,
                "qtype": qq.qtype,
                "graded": qq.graded,
                "order_index": qq.order_index,
                "answers": [
                    {
                        "id": a.id,
                        "text": a.text,
                        "image_url": a.image_url,
                        "order_index": a.order_index,
                        **({"is_correct": a.is_correct} if include_correct else {}),
                    }
                    for a in qq.answers
                ],
            }
            for qq in quiz.questions
        ],
    }


def tally_question(db: DbSession, run: m.QuizRun, vq: m.QuizVersionQuestion) -> dict:
    rows = db.scalars(
        select(m.QuizSubmission).where(
            m.QuizSubmission.quiz_run_id == run.id,
            m.QuizSubmission.question_id == vq.id,
        )
    ).all()
    counts = Counter(r.answer_id for r in rows)
    voters = {r.participant_id for r in rows}
    return {
        "question_id": vq.id,
        "respondents": len(voters),
        "totals": {a.id: counts.get(a.id, 0) for a in vq.answers},
    }


def serialize_quiz_run(
    db: DbSession,
    run: m.QuizRun,
    *,
    viewer_participant_id: int | None,
    is_mod: bool,
) -> dict:
    version = run.quiz_version
    questions = version.questions
    current = questions[run.current_question_idx] if 0 <= run.current_question_idx < len(questions) else None
    show_correct = is_mod or (run.status == "closed") or run.reveal_current
    show_results = show_correct or run.show_live_counts
    payload: dict[str, Any] = {
        "id": run.id,
        "session_id": run.session_id,
        "quiz_version_id": version.id,
        "quiz_id": version.quiz_id,
        "quiz_title": version.quiz_title,
        "version_no": version.version_no,
        "status": run.status,
        "current_question_idx": run.current_question_idx,
        "question_count": len(questions),
        "reveal_current": run.reveal_current,
        "show_live_counts": run.show_live_counts,
        "current_question": None,
        "my_selections": [],
        "results": None,
    }
    # Non-mods don't see question/answer details for a queued run — they
    # only need lobby-safe metadata (title, version, status) to render the
    # "Next up" projector card. Exposing the first question before Start
    # would let a participant peek at upcoming items via the API.
    expose_question = current is not None and (is_mod or run.status in ("live", "closed"))
    if expose_question:
        # A poll question (not graded) never reveals correctness — there's no
        # right answer; the reveal just shows the distribution.
        reveal_correct = show_correct and current.graded
        payload["current_question"] = {
            "id": current.id,
            "text": current.text,
            "image_url": current.image_url,
            "qtype": current.qtype,
            "graded": current.graded,
            "answers": [
                {
                    "id": a.id,
                    "text": a.text,
                    "image_url": a.image_url,
                    **({"is_correct": a.is_correct} if reveal_correct else {}),
                }
                for a in current.answers
            ],
        }
        if viewer_participant_id is not None:
            mine = db.scalars(
                select(m.QuizSubmission).where(
                    m.QuizSubmission.quiz_run_id == run.id,
                    m.QuizSubmission.question_id == current.id,
                    m.QuizSubmission.participant_id == viewer_participant_id,
                )
            ).all()
            payload["my_selections"] = [r.answer_id for r in mine]
        if show_results:
            results = tally_question(db, run, current)
            if current.graded and not (run.reveal_current or run.status == "closed"):
                # Before reveal, a graded question's live counts must not name
                # the leading answer, or the room follows it (UC-P-12, UC-D-08).
                # The projector draws these unlabelled counts; only moderators
                # get the counts by answer.
                results["masked_counts"] = sorted(results["totals"].values(), reverse=True)
                if not is_mod:
                    results["totals"] = None
            payload["results"] = results
    return payload


def serialize_session_queries(
    db: DbSession,
    session: m.Session,
    *,
    viewer_participant_id: int | None,
    is_mod: bool,
) -> list[dict]:
    rows = db.scalars(
        select(m.Query)
        .where(m.Query.session_id == session.id)
        .options(selectinload(m.Query.votes), selectinload(m.Query.participant))
        .order_by(m.Query.created_at.desc())
    ).all()
    if not is_mod:
        rows = [row for row in rows if row.removed_at is None]
    return [
        serialize_query(row, viewer_participant_id)
        for row in rows
    ]


def serialize_session_quiz_runs(
    db: DbSession,
    session: m.Session,
    *,
    viewer_participant_id: int | None,
    is_mod: bool,
) -> list[dict]:
    rows = db.scalars(
        select(m.QuizRun)
        .where(m.QuizRun.session_id == session.id)
        .order_by(m.QuizRun.created_at.desc())
    ).all()
    return [
        serialize_quiz_run(
            db,
            row,
            viewer_participant_id=viewer_participant_id,
            is_mod=is_mod,
        )
        for row in rows
    ]


RUN_STATUS_RANK = {"live": 0, "queued": 1, "closed": 2}


def quiz_session_usage(
    db: DbSession, owner_user_id: int, session_id: int | None = None
) -> dict[int, dict[str, dict]]:
    """quiz_id -> session code -> where that quiz's runs are.

    The one source for "is this quiz already in that session" (UC-A-10
    `sessions`, UC-M-03 `in_session`). Each entry carries the most relevant
    run state there (live over queued over closed) and the run count.
    """
    stmt = (
        select(m.QuizVersion.quiz_id, m.Session.code, m.Session.title, m.Session.status, m.QuizRun.status)
        .join(m.QuizVersion, m.QuizRun.quiz_version_id == m.QuizVersion.id)
        .join(m.Session, m.QuizRun.session_id == m.Session.id)
        .join(m.Quiz, m.QuizVersion.quiz_id == m.Quiz.id)
        .where(m.Quiz.owner_user_id == owner_user_id)
        .order_by(m.QuizRun.id)
    )
    if session_id is not None:
        stmt = stmt.where(m.QuizRun.session_id == session_id)
    usage: dict[int, dict[str, dict]] = {}
    for quiz_id, code, title, session_status, run_status in db.execute(stmt):
        entry = usage.setdefault(quiz_id, {}).setdefault(code, {
            "code": code, "title": title, "session_status": session_status,
            "run_status": run_status, "run_count": 0,
        })
        entry["run_count"] += 1
        if RUN_STATUS_RANK.get(run_status, 9) < RUN_STATUS_RANK.get(entry["run_status"], 9):
            entry["run_status"] = run_status
    return usage


def available_quiz_summaries(
    db: DbSession, session: m.Session, include_drafts: bool = False
) -> list[dict]:
    """Quizzes that can be queued in this session. Drafts are included only
    for the admin owner, who can publish them on add (UC-M-03)."""
    statuses = ("ready", "draft") if include_drafts else ("ready",)
    question_count = (
        select(func.count(m.Question.id))
        .where(m.Question.quiz_id == m.Quiz.id)
        .correlate(m.Quiz)
        .scalar_subquery()
    )
    quizzes = db.execute(
        select(m.Quiz, question_count.label("question_count"))
        .where(
            m.Quiz.owner_user_id == session.owner_user_id,
            m.Quiz.status.in_(statuses),
        )
        .options(selectinload(m.Quiz.questions).selectinload(m.Question.answers))
        .order_by(m.Quiz.created_at.desc())
    ).all()
    usage = quiz_session_usage(db, session.owner_user_id, session_id=session.id)

    def in_session(quiz_id: int) -> dict | None:
        here = usage.get(quiz_id, {}).get(session.code)
        return {"run_status": here["run_status"], "run_count": here["run_count"]} if here else None

    return [
        {
            "id": quiz.id,
            "title": quiz.title,
            "status": quiz.status,
            "question_count": count,
            "in_session": in_session(quiz.id),
            "problem": quiz_problem(quiz),
        }
        for quiz, count in quizzes
    ]


def _no_live_quiz_run(db: DbSession, session: m.Session) -> None:
    """Raise 400 if any QuizRun in this Session is currently `live`."""
    live = db.scalar(
        select(m.QuizRun.id).where(
            m.QuizRun.session_id == session.id,
            m.QuizRun.status == "live",
        )
    )
    if live:
        raise HTTPException(
            400,
            "A quiz run is currently live — close it before ending the session",
        )


def _no_queued_quiz_run(db: DbSession, session: m.Session) -> None:
    """Raise 400 if this Session still has an unstarted QuizRun."""
    queued = db.scalar(
        select(m.QuizRun.id).where(
            m.QuizRun.session_id == session.id,
            m.QuizRun.status == "queued",
        )
    )
    if queued:
        raise HTTPException(
            400,
            "Remove queued quizzes before ending the session",
        )


# ---------- quiz lifecycle helpers ----------

@dataclass(frozen=True)
class PublishProblem:
    """One failing publish rule (UC-A-21).

    `message` is the short instruction shown at its place in the editor;
    `numbered` names the question and answer by position, for the API's
    400 detail and the lists' `problem` (UC-A-10).
    """

    question_id: int | None
    answer_id: int | None
    field: str  # questions | text | answers | correct | answer
    message: str
    numbered: str

    def as_json(self) -> dict:
        return {
            "question_id": self.question_id,
            "answer_id": self.answer_id,
            "field": self.field,
            "message": self.message,
        }


def _publish_problems(quiz: m.Quiz) -> list[PublishProblem]:
    """Every publish rule the quiz breaks, in quiz order (UC-A-21)."""
    if not quiz.questions:
        return [PublishProblem(None, None, "questions", "Add at least one question",
                               "Quiz needs at least one question")]
    problems: list[PublishProblem] = []
    for idx, qq in enumerate(quiz.questions, start=1):
        rules: list[tuple[str, str, str, int | None]] = []
        if not qq.text.strip():
            rules.append(("text", "Add the question text", f"Question {idx} is missing text", None))
        if len(qq.answers) < 2:
            rules.append(("answers", "Add at least 2 answers", f"Question {idx} needs at least 2 answers", None))
        # Poll/survey questions (graded=False) intentionally have no correct
        # answer — skip the correctness requirement for them.
        if qq.graded:
            correct = [a for a in qq.answers if a.is_correct]
            if qq.qtype == "single" and len(correct) != 1:
                rules.append(("correct", "Mark exactly one correct answer",
                              f"Question {idx} (single choice) needs exactly one correct answer", None))
            if qq.qtype == "multi" and len(correct) < 1:
                rules.append(("correct", "Mark at least one correct answer",
                              f"Question {idx} (multiple choice) needs at least one correct answer", None))
        for ai, a in enumerate(qq.answers, start=1):
            if not a.text.strip() and not a.image_url:
                rules.append(("answer", "Add answer text or an image", f"Question {idx}, answer {ai} is empty", a.id))
        problems.extend(PublishProblem(qq.id, answer_id, field, message, numbered)
                        for field, message, numbered, answer_id in rules)
    return problems


def _validate_quiz_publishable(quiz: m.Quiz) -> None:
    """Raise 400 naming the first failing publish rule (UC-A-21)."""
    problems = _publish_problems(quiz)
    if problems:
        raise HTTPException(400, problems[0].numbered)


def quiz_problem(quiz: m.Quiz) -> str | None:
    """Why a Ready quiz can't be added to a session, or None (UC-A-10).

    Editing a Ready quiz keeps it Ready even when the edit breaks a publish
    rule; the lists report the first failing rule instead, so the library
    and the session picker can say so before an add fails. Drafts report
    None: Publish already checks them.
    """
    if quiz.status != "ready":
        return None
    problems = _publish_problems(quiz)
    return problems[0].numbered if problems else None


def _mark_quiz_edited(quiz: m.Quiz) -> None:
    quiz.last_edited_at = datetime.utcnow()


def _latest_version(db: DbSession, quiz: m.Quiz) -> m.QuizVersion | None:
    return db.scalar(
        select(m.QuizVersion).where(m.QuizVersion.quiz_id == quiz.id)
        .order_by(m.QuizVersion.version_no.desc())
    )


def _ensure_current_version(db: DbSession, quiz: m.Quiz) -> m.QuizVersion:
    """Return the version that captures the quiz's current editable tree."""
    latest = _latest_version(db, quiz)
    if latest and latest.created_at >= quiz.last_edited_at:
        return latest
    _validate_quiz_publishable(quiz)
    next_no = (latest.version_no + 1) if latest else 1
    version = m.QuizVersion(quiz_id=quiz.id, version_no=next_no, quiz_title=quiz.title)
    db.add(version)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        winner = _latest_version(db, quiz)
        if winner is None:
            raise
        return winner
    for qq in quiz.questions:
        vq = m.QuizVersionQuestion(
            version_id=version.id,
            text=qq.text,
            image_url=qq.image_url,
            qtype=qq.qtype,
            graded=qq.graded,
            order_index=qq.order_index,
        )
        db.add(vq)
        db.flush()
        for a in qq.answers:
            db.add(m.QuizVersionAnswer(
                question_id=vq.id,
                text=a.text,
                image_url=a.image_url,
                # A poll question has no correct answer; freeze it clean even if
                # a stale is_correct lingers on the editable template.
                is_correct=a.is_correct if qq.graded else False,
                order_index=a.order_index,
            ))
    db.commit()
    db.refresh(version)
    return version


# ---------- broadcast ----------

async def broadcast_session(session: m.Session, kind: str = "update") -> None:
    await hub.broadcast(f"session:{session.code}", {"type": kind})


# ---------- routes: pages ----------

def _page(name: str) -> FileResponse:
    """Serve a page from the Vite build output."""
    return FileResponse(STATIC / f"{name}.html")


@app.get("/")
def root():
    return _page("index")


def _session_exists(code: str, db: DbSession) -> bool:
    return bool(db.scalar(select(m.Session.id).where(m.Session.code == code.upper())))


def _bad_code_redirect(code: str) -> RedirectResponse:
    return RedirectResponse(url=f"/?bad_code={code}", status_code=303)


@app.get("/s/{code}")
def participant_page(code: str, db: DbSession = Depends(get_db)):
    if not _session_exists(code, db):
        return _bad_code_redirect(code)
    return _page("participant")


@app.get("/m/{code}")
def moderator_page(code: str, db: DbSession = Depends(get_db)):
    if not _session_exists(code, db):
        return _bad_code_redirect(code)
    return _page("moderator")


@app.get("/p/{code}")
def projector_page(code: str, db: DbSession = Depends(get_db)):
    if not _session_exists(code, db):
        return _bad_code_redirect(code)
    return _page("projector")


@app.get("/quizzes")
def quizzes_page():
    return _page("quizzes")


# One-command installers (UC-X-15). The published copies are on GitHub Pages;
# every Prashna server also serves them, so a self-hosted server can offer them.
INSTALLERS = Path(__file__).resolve().parent / "installers"


@app.get("/install.sh", include_in_schema=False)
def install_sh():
    return FileResponse(INSTALLERS / "install.sh", media_type="text/plain; charset=utf-8",
                        headers={"Cache-Control": "no-cache"})


@app.get("/install.ps1", include_in_schema=False)
def install_ps1():
    return FileResponse(INSTALLERS / "install.ps1", media_type="text/plain; charset=utf-8",
                        headers={"Cache-Control": "no-cache"})


# ---------- routes: admin auth ----------

@app.get("/api/admin/status")
def admin_status(db: DbSession = Depends(get_db), me: m.User | None = Depends(auth.optional_admin)):
    return {
        "initialized": auth.admin_exists(db),
        "authenticated": me is not None,
        "username": me.username if me else None,
    }


def _bounded_performance_metric(
    payload: dict,
    name: str,
    *,
    maximum: float = 120_000,
) -> float | None:
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0 or numeric > maximum:
        return None
    return round(numeric, 2)


@app.post("/api/diagnostics/performance", status_code=204)
def performance_beacon(payload: dict, request: Request):
    """Retain a bounded, identifier-free usable-UI timing sample."""
    if not limiter.allow(f"perf:{_client_ip(request)}", *RL_PERFORMANCE):
        return Response(status_code=204)
    role = payload.get("role")
    usable_ms = _bounded_performance_metric(payload, "usable_ms")
    if role not in PERFORMANCE_ROLES or usable_ms is None:
        return Response(status_code=204)

    protocol = payload.get("protocol")
    if protocol not in {"h2", "h3", "http/1.1", "unknown"}:
        protocol = "unknown"
    navigation_type = payload.get("navigation_type")
    if navigation_type not in {"navigate", "reload", "back_forward", "prerender"}:
        navigation_type = "navigate"

    cf_colo = None
    cf_ray = request.headers.get("cf-ray", "")
    if "-" in cf_ray:
        candidate = cf_ray.rsplit("-", 1)[-1].upper()
        if 3 <= len(candidate) <= 8 and candidate.isalnum():
            cf_colo = candidate

    log_diagnostic(
        "performance.usable",
        role=role,
        usable_ms=usable_ms,
        dcl_ms=_bounded_performance_metric(payload, "dcl_ms"),
        fcp_ms=_bounded_performance_metric(payload, "fcp_ms"),
        app_server_ms=_bounded_performance_metric(
            payload,
            "app_server_ms",
            maximum=10_000,
        ),
        protocol=protocol,
        navigation_type=navigation_type,
        cf_colo=cf_colo,
    )
    return Response(status_code=204)


# Serializes first-run admin_setup against itself. Prashna runs as a
# single FastAPI process (see CLAUDE.md), so a process-wide lock is a
# real bootstrap invariant — not advisory. Closes the
# different-username concurrent-setup race that two DB statements
# alone cannot.
_setup_lock = threading.Lock()


@app.post("/api/admin/setup")
def admin_setup(payload: dict, request: Request, response: Response, db: DbSession = Depends(get_db)):
    with _setup_lock:
        if auth.admin_exists(db):
            log_diagnostic("auth.setup", outcome="already_initialized")
            raise HTTPException(409, "Admin already initialized")
        # Only someone who can read the server log (or the operator's env)
        # holds the token, so a public install can't be claimed (UC-A-01).
        if not auth.setup_token_matches(db, payload.get("setup_token")):
            log_diagnostic("auth.setup", outcome="bad_token")
            raise HTTPException(403, "Open the one-time setup link from the server log to create the first admin")
        try:
            username, password = _validate_credentials(
                _text(payload, "username"),
                _text(payload, "password"),
            )
        except HTTPException:
            log_diagnostic("auth.setup", outcome="invalid")
            raise
        user = m.User(username=username, password_hash=_hash_password(password))
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            # Defensive: a username UNIQUE collision against some
            # other admin row we didn't expect. Surface as 409.
            db.rollback()
            log_diagnostic("auth.setup", outcome="conflict")
            raise HTTPException(409, "Admin already initialized")
        db.refresh(user)
        auth.retire_setup_token()
        auth.issue_session(response, user.id, user.session_version, secure=_is_https(request))
        log_diagnostic("auth.setup", outcome="success", actor_id=user.id)
        return {"username": user.username}


@app.post("/api/admin/login")
def admin_login(payload: dict, request: Request, response: Response, db: DbSession = Depends(get_db)):
    # Throttle BEFORE verify_password: bcrypt is deliberately expensive, so a
    # login flood is itself a CPU DoS. A successful login clears the bucket so
    # a fumbling-then-correct admin is never locked out (UC-X-08).
    ip_key = f"login:{_client_ip(request)}"
    if not limiter.allow(ip_key, *RL_LOGIN):
        log_diagnostic("auth.login", outcome="rate_limited")
        raise HTTPException(429, "Too many login attempts — wait a moment and try again")
    username = _text(payload, "username").strip()
    password = _text(payload, "password")
    user = db.scalar(select(m.User).where(m.User.username == username)) if username else None
    if not user or not auth.verify_password(password, user.password_hash):
        log_diagnostic("auth.login", outcome="failure")
        raise HTTPException(401, "Invalid username or password")
    limiter.reset(ip_key)
    auth.issue_session(response, user.id, user.session_version, secure=_is_https(request))
    log_diagnostic("auth.login", outcome="success", actor_id=user.id)
    return {"username": user.username}


@app.post("/api/admin/logout")
def admin_logout(response: Response):
    auth.clear_session(response)
    log_diagnostic("auth.logout", outcome="success")
    return {"ok": True}


@app.post("/api/admin/change_password")
def admin_change_password(
    payload: dict,
    request: Request,
    response: Response,
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    current = _text(payload, "current_password")
    new = _text(payload, "new_password")
    if not auth.verify_password(current, me.password_hash):
        log_diagnostic(
            "auth.password_change",
            outcome="wrong_current",
            actor_id=me.id,
        )
        raise HTTPException(401, "Current password is incorrect")
    if len(new) < MIN_PASSWORD_LEN:
        log_diagnostic(
            "auth.password_change",
            outcome="invalid_new",
            actor_id=me.id,
        )
        raise HTTPException(400, f"New password must be at least {MIN_PASSWORD_LEN} characters")
    me.password_hash = _hash_password(new)
    # Bumping session_version invalidates every cookie issued under the old
    # version — anywhere the old password may have been stored stops working.
    me.session_version = (me.session_version or 1) + 1
    db.commit()
    auth.issue_session(response, me.id, me.session_version, secure=_is_https(request))
    log_diagnostic("auth.password_change", outcome="success", actor_id=me.id)
    return {"ok": True}


# ---------- routes: adjustable limits (UC-A-31) ----------

@app.get("/api/admin/limits")
def get_limits(_me: m.User = Depends(auth.current_admin)):
    return {"values": dict(limits), "defaults": dict(DEFAULT_LIMITS)}


@app.put("/api/admin/limits")
def put_limits(payload: dict, db: DbSession = Depends(get_db), me: m.User = Depends(auth.current_admin)):
    try:
        new = validated_limits(limits, payload)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    row = db.get(m.Setting, "limits")
    if row:
        row.value = json.dumps(new, sort_keys=True)
    else:
        db.add(m.Setting(key="limits", value=json.dumps(new, sort_keys=True)))
    db.commit()
    limits.update(new)
    # Fresh buckets, so the next request from everyone uses the new values.
    limiter.clear()
    log_diagnostic("limits.update", outcome="success", actor_id=me.id, changed=sorted(payload))
    return {"values": dict(limits), "defaults": dict(DEFAULT_LIMITS)}


# ---------- routes: sessions ----------

@app.get("/api/sessions")
def list_sessions(db: DbSession = Depends(get_db), me: m.User = Depends(auth.current_admin)):
    query_count = (
        select(func.count(m.Query.id))
        .where(m.Query.session_id == m.Session.id)
        .correlate(m.Session)
        .scalar_subquery()
    )
    quiz_run_count = (
        select(func.count(m.QuizRun.id))
        .where(m.QuizRun.session_id == m.Session.id)
        .correlate(m.Session)
        .scalar_subquery()
    )
    feedback_count = (
        select(func.count(m.SessionFeedback.id))
        .where(m.SessionFeedback.session_id == m.Session.id)
        .correlate(m.Session)
        .scalar_subquery()
    )
    # Participants with any profile field or a photograph (UC-A-04); the
    # same rule as participant_has_profile.
    profile_count = (
        select(func.count(m.Participant.id))
        .where(
            m.Participant.session_id == m.Session.id,
            or_(
                m.Participant.photo_url.is_not(None),
                *(func.coalesce(getattr(m.Participant, field), "") != "" for field in PROFILE_FIELDS),
            ),
        )
        .correlate(m.Session)
        .scalar_subquery()
    )
    rows = db.execute(
        select(
            m.Session,
            query_count.label("query_count"),
            quiz_run_count.label("quiz_run_count"),
            feedback_count.label("feedback_count"),
            profile_count.label("profile_count"),
        )
        .where(m.Session.owner_user_id == me.id)
        .order_by(m.Session.created_at.desc())
    ).all()
    return [
        {
            **serialize_session(s, include_mod_key=True),
            "query_count": query_total,
            "quiz_run_count": run_total,
            "feedback_count": feedback_total,
            "profile_count": profile_total,
        }
        for s, query_total, run_total, feedback_total, profile_total in rows
    ]


@app.post("/api/sessions")
def create_session(payload: dict, db: DbSession = Depends(get_db), me: m.User = Depends(auth.current_admin)):
    title = _text(payload, "title").strip()
    if not title:
        raise HTTPException(400, "Session title is required")
    if len(title) > 200:
        raise HTTPException(400, "Session title is too long (max 200 chars)")
    code = gen_code()
    while db.scalar(select(m.Session).where(m.Session.code == code)):
        code = gen_code()
    s = m.Session(code=code, title=title, mod_key=gen_token()[:16], owner_user_id=me.id)
    db.add(s)
    db.commit()
    db.refresh(s)
    log_diagnostic(
        "session.lifecycle",
        action="create",
        outcome="success",
        actor_id=me.id,
        session_id=s.id,
        session_code=s.code,
    )
    return serialize_session(s, include_mod_key=True)


@app.get("/api/sessions/{code}")
def get_session(code: str, db: DbSession = Depends(get_db)):
    s = get_session_by_code(db, code)
    return serialize_session(s)


@app.get("/api/sessions/{code}/participant-bootstrap")
def participant_bootstrap(
    code: str,
    request: Request,
    response: Response,
    voter_token: Annotated[str | None, Cookie()] = None,
    db: DbSession = Depends(get_db),
    admin: m.User | None = Depends(auth.optional_admin),
):
    """Return one cookie-consistent participant startup snapshot."""
    session = get_session_by_code(db, code)
    participant = current_participant(
        session,
        request,
        response,
        voter_token,
        db,
    )
    feedback = db.scalar(
        select(m.SessionFeedback).where(
            m.SessionFeedback.session_id == session.id,
            m.SessionFeedback.participant_id == participant.id,
        )
    )
    return {
        "session": serialize_session(session),
        "me": serialize_participant_profile(participant),
        "queries": serialize_session_queries(
            db,
            session,
            viewer_participant_id=participant.id,
            is_mod=False,
        ),
        "quiz_runs": serialize_session_quiz_runs(
            db,
            session,
            viewer_participant_id=participant.id,
            is_mod=False,
        ),
        "feedback": serialize_feedback(feedback) if feedback else None,
        # Lets the page link the session's other views for its owner.
        "viewer_is_owner": bool(admin and admin.id == session.owner_user_id),
    }


@app.get("/api/sessions/{code}/moderator-bootstrap")
def moderator_bootstrap(
    code: str,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
    me: m.User | None = Depends(auth.optional_admin),
):
    """Return the moderator's operational first paint in one request."""
    session = get_session_by_code(db, code)
    require_mod_or_owner(session, x_mod_key, me)
    return {
        "session": serialize_session(session),
        "available_quizzes": available_quiz_summaries(
            db, session, include_drafts=is_admin_owner(session, me)
        ),
        "is_owner": is_admin_owner(session, me),
    }


@app.get("/api/sessions/{code}/display-bootstrap")
def display_bootstrap(code: str, db: DbSession = Depends(get_db)):
    """Return public display state without creating participant identity."""
    session = get_session_by_code(db, code)
    return {
        "session": serialize_session(session),
        "queries": serialize_session_queries(
            db,
            session,
            viewer_participant_id=None,
            is_mod=False,
        ),
        "quiz_runs": serialize_session_quiz_runs(
            db,
            session,
            viewer_participant_id=None,
            is_mod=False,
        ),
    }


@app.patch("/api/sessions/{code}")
async def update_session(
    code: str,
    payload: dict,
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    s = get_session_by_code(db, code)
    # Session metadata (title, etc.) is owner-only — delegated moderators
    # shouldn't be able to rename someone else's session.
    require_session_owner(s, me)
    if "title" in payload:
        new_title = _text(payload, "title").strip()
        if not new_title:
            raise HTTPException(400, "Session title is required")
        if len(new_title) > 200:
            raise HTTPException(400, "Session title is too long (max 200 chars)")
        s.title = new_title
    db.commit()
    await broadcast_session(s, "session_state")
    log_diagnostic(
        "session.lifecycle",
        action="update",
        outcome="success",
        actor_id=me.id,
        session_id=s.id,
        session_code=s.code,
    )
    return serialize_session(s)


@app.post("/api/sessions/{code}/participant_base_url")
async def set_participant_base_url(
    code: str,
    payload: dict,
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    s = get_session_by_code(db, code)
    # Owner-only: base URL determines the QR shown to attendees; delegating
    # moderators shouldn't be able to redirect the audience elsewhere.
    require_session_owner(s, me)
    url = _text(payload, "url").strip()
    if url:
        if not (url.startswith("http://") or url.startswith("https://")):
            raise HTTPException(400, "URL must start with http:// or https://")
        if len(url) > 500:
            raise HTTPException(400, "URL is too long")
        url = url.rstrip("/")
        s.participant_base_url = url
    else:
        s.participant_base_url = None
    db.commit()
    await broadcast_session(s, "session_state")
    log_diagnostic(
        "session.lifecycle",
        action="participant_base_url",
        outcome="success",
        actor_id=me.id,
        session_id=s.id,
        session_code=s.code,
    )
    return {"participant_base_url": s.participant_base_url}


@app.post("/api/sessions/{code}/feedback_enabled")
async def set_feedback_enabled(
    code: str,
    payload: dict,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
    me: m.User | None = Depends(auth.optional_admin),
):
    s = get_session_by_code(db, code)
    require_mod_or_owner(s, x_mod_key, me)
    s.feedback_enabled = bool(payload.get("enabled", True))
    db.commit()
    await broadcast_session(s, "feedback_state")
    log_diagnostic(
        "session.lifecycle",
        action="feedback_enabled",
        outcome="success",
        actor_id=me.id if me else None,
        session_id=s.id,
        session_code=s.code,
        enabled=s.feedback_enabled,
    )
    return {"feedback_enabled": bool(s.feedback_enabled)}


@app.post("/api/sessions/{code}/start")
async def start_session(
    code: str,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
    me: m.User | None = Depends(auth.optional_admin),
):
    s = get_session_by_code(db, code)
    require_mod_or_owner(s, x_mod_key, me)
    if s.status == "ended":
        log_diagnostic(
            "session.lifecycle",
            action="start",
            outcome="ended",
            session_id=s.id,
            session_code=s.code,
        )
        raise HTTPException(400, "Session has ended")
    if s.status == "planning":
        s.status = "live"
        s.started_at = datetime.utcnow()
        db.commit()
        await broadcast_session(s, "session_state")
        log_diagnostic(
            "session.lifecycle",
            action="start",
            outcome="success",
            actor_id=me.id if me else None,
            session_id=s.id,
            session_code=s.code,
        )
    return {"status": s.status}


@app.post("/api/sessions/{code}/end")
async def end_session(
    code: str,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
    me: m.User | None = Depends(auth.optional_admin),
):
    s = get_session_by_code(db, code)
    require_mod_or_owner(s, x_mod_key, me)
    if s.status != "ended":
        _no_live_quiz_run(db, s)
        _no_queued_quiz_run(db, s)
        s.status = "ended"
        s.ended_at = datetime.utcnow()
        db.commit()
        await broadcast_session(s, "session_state")
        log_diagnostic(
            "session.lifecycle",
            action="end",
            outcome="success",
            actor_id=me.id if me else None,
            session_id=s.id,
            session_code=s.code,
        )
    return {"status": s.status}


@app.delete("/api/sessions/{code}")
async def delete_session(
    code: str,
    payload: dict | None = None,
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    s = get_session_by_code(db, code)
    require_session_owner(s, me)
    if s.status == "live":
        raise HTTPException(400, "End the session before deleting it")
    # Feedback and attendee profiles are data too (UC-A-07); a participant
    # who only opened the page is not.
    has_data = (
        bool(s.queries) or bool(s.quiz_runs) or bool(s.feedback)
        or any(participant_has_profile(p) for p in s.participants)
    )
    if has_data:
        confirm_title = (payload or {}).get("confirm_title", "")
        if confirm_title != s.title:
            raise HTTPException(400, "Type the session title exactly to confirm deletion")
    session_code = s.code
    session_id = s.id
    photos = [p.photo_url for p in s.participants if p.photo_url]
    db.delete(s)
    db.commit()
    for photo in photos:
        delete_uploaded_file(photo)
    await hub.broadcast(f"session:{session_code}", {"type": "session_deleted"})
    log_diagnostic(
        "session.lifecycle",
        action="delete",
        outcome="success",
        actor_id=me.id,
        session_id=session_id,
        session_code=session_code,
    )
    return {"ok": True}


@app.get("/api/sessions/{code}/presence")
def session_presence(code: str, db: DbSession = Depends(get_db)):
    # Read-only: the moderator page polls this, and a moderator tab must
    # not become a Participant (UC-M-10).
    s = get_session_by_code(db, code)
    return {"online": participant_count_online(db, s)}


# ---------- routes: participant self ----------

PROFILE_TOO_FAST = "You're saving your profile too fast — wait a moment and try again"

@app.get("/api/sessions/{code}/me")
def my_participant(
    code: str,
    request: Request,
    response: Response,
    voter_token: Annotated[str | None, Cookie()] = None,
    db: DbSession = Depends(get_db),
):
    s = get_session_by_code(db, code)
    p = current_participant(s, request, response, voter_token, db)
    return serialize_participant_profile(p)


@app.patch("/api/sessions/{code}/me")
async def update_my_participant(
    code: str,
    payload: dict,
    request: Request,
    response: Response,
    voter_token: Annotated[str | None, Cookie()] = None,
    db: DbSession = Depends(get_db),
):
    s = get_session_by_code(db, code)
    if not allow_person("profile", request, voter_token):
        raise HTTPException(429, PROFILE_TOO_FAST)
    linkedin = normalize_optional_text(payload, "linkedin_url", PROFILE_FIELDS["linkedin_url"])
    if linkedin and not linkedin.lower().startswith(("http://", "https://")):
        raise HTTPException(400, "LinkedIn profile must start with http:// or https://")
    if "photo_url" in payload and normalize_optional_text(payload, "photo_url", 500) is not None:
        raise HTTPException(400, "photo must be uploaded")
    p = current_participant(s, request, response, voter_token, db)
    for field, max_len in PROFILE_FIELDS.items():
        if field in payload:
            setattr(p, field, normalize_optional_text(payload, field, max_len))
    old_photo = p.photo_url
    if "photo_url" in payload:
        p.photo_url = None
    db.commit()
    db.refresh(p)
    if p.photo_url != old_photo:
        delete_uploaded_file(old_photo)
    await broadcast_session(s, "participant")
    return serialize_participant_profile(p)


@app.post("/api/sessions/{code}/me/photo")
async def upload_my_participant_photo(
    code: str,
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    voter_token: Annotated[str | None, Cookie()] = None,
    db: DbSession = Depends(get_db),
):
    s = get_session_by_code(db, code)
    if not allow_person("profile", request, voter_token):
        raise HTTPException(429, PROFILE_TOO_FAST)
    p = current_participant(s, request, response, voter_token, db)
    old_photo = p.photo_url
    p.photo_url = await store_uploaded_image(file, actor="participant_profile")
    db.commit()
    db.refresh(p)
    delete_uploaded_file(old_photo)
    await broadcast_session(s, "participant")
    return serialize_participant_profile(p)


@app.get("/api/sessions/{code}/participants")
def list_participant_profiles(
    code: str,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
    me: m.User | None = Depends(auth.optional_admin),
):
    s = get_session_by_code(db, code)
    require_mod_or_owner(s, x_mod_key, me)
    rows = db.scalars(
        select(m.Participant)
        .where(m.Participant.session_id == s.id)
        .order_by(m.Participant.last_seen_at.desc())
    ).all()
    items = [serialize_participant_profile(p) for p in rows if participant_has_profile(p)]
    return {"count": len(items), "items": items}


# ---------- routes: session feedback (participant rating + comments) ----------


@app.get("/api/sessions/{code}/feedback/mine")
def my_feedback(
    code: str,
    request: Request,
    response: Response,
    voter_token: Annotated[str | None, Cookie()] = None,
    db: DbSession = Depends(get_db),
):
    """The caller's own feedback for this session, or null if none yet."""
    s = get_session_by_code(db, code)
    p = current_participant(s, request, response, voter_token, db)
    f = db.scalar(select(m.SessionFeedback).where(
        m.SessionFeedback.session_id == s.id,
        m.SessionFeedback.participant_id == p.id,
    ))
    return serialize_feedback(f) if f else None


@app.post("/api/sessions/{code}/feedback")
async def submit_feedback(
    code: str,
    payload: dict,
    request: Request,
    response: Response,
    voter_token: Annotated[str | None, Cookie()] = None,
    db: DbSession = Depends(get_db),
):
    """Upsert the caller's feedback when the moderator has enabled it."""
    s = get_session_by_code(db, code)
    if not s.feedback_enabled:
        raise HTTPException(403, "Feedback is closed for this session")
    if not allow_person("feedback", request, voter_token):
        raise HTTPException(429, "You're submitting feedback too fast — wait a moment and try again")
    rating = payload.get("rating")
    if not isinstance(rating, int) or isinstance(rating, bool) or rating < 1 or rating > 5:
        raise HTTPException(400, "rating must be an integer from 1 to 5")
    went_well = _text(payload, "went_well").strip()[:2000] or None
    to_improve = _text(payload, "to_improve").strip()[:2000] or None
    p = current_participant(s, request, response, voter_token, db)
    # Record an immutable version for every submission (participants may
    # resubmit any number of times; the backend keeps the full trail).
    db.add(m.SessionFeedbackVersion(session_id=s.id, participant_id=p.id, rating=rating,
                                    went_well=went_well, to_improve=to_improve))
    db.commit()
    # Mirror the latest into the "current" row used by mine/summary.
    f = db.scalar(select(m.SessionFeedback).where(
        m.SessionFeedback.session_id == s.id,
        m.SessionFeedback.participant_id == p.id,
    ))
    if f is None:
        f = m.SessionFeedback(session_id=s.id, participant_id=p.id, rating=rating,
                              went_well=went_well, to_improve=to_improve)
        db.add(f)
        try:
            db.commit()
        except IntegrityError:
            # Concurrent insert won under UNIQUE(session, participant) —
            # re-resolve and update that row instead of 500-ing.
            db.rollback()
            f = db.scalar(select(m.SessionFeedback).where(
                m.SessionFeedback.session_id == s.id,
                m.SessionFeedback.participant_id == p.id,
            ))
            if f is None:
                raise
            f.rating, f.went_well, f.to_improve = rating, went_well, to_improve
            db.commit()
    else:
        f.rating, f.went_well, f.to_improve = rating, went_well, to_improve
        db.commit()
    db.refresh(f)
    await broadcast_session(s, "feedback")
    return serialize_feedback(f)


@app.delete("/api/sessions/{code}/feedback")
async def delete_my_feedback(
    code: str,
    request: Request,
    response: Response,
    voter_token: Annotated[str | None, Cookie()] = None,
    db: DbSession = Depends(get_db),
):
    """Retract the caller's current feedback (the 'undo' on the participant
    page). Version history in SessionFeedbackVersion is left intact."""
    s = get_session_by_code(db, code)
    if not s.feedback_enabled:
        raise HTTPException(403, "Feedback is closed for this session")
    p = current_participant(s, request, response, voter_token, db)
    f = db.scalar(select(m.SessionFeedback).where(
        m.SessionFeedback.session_id == s.id,
        m.SessionFeedback.participant_id == p.id,
    ))
    if f:
        db.delete(f)
        db.commit()
        await broadcast_session(s, "feedback")
    return {"ok": True}


@app.get("/api/sessions/{code}/feedback/summary")
def feedback_summary(
    code: str,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
    me: m.User | None = Depends(auth.optional_admin),
):
    """Aggregate feedback for the host (mod-key or admin owner): count,
    average, star distribution, and the individual responses."""
    s = get_session_by_code(db, code)
    require_mod_or_owner(s, x_mod_key, me)
    rows = db.scalars(
        select(m.SessionFeedback)
        .where(m.SessionFeedback.session_id == s.id)
        .options(selectinload(m.SessionFeedback.participant))
        .order_by(m.SessionFeedback.updated_at.desc())
    ).all()
    log_diagnostic(
        "feedback.summary",
        outcome="success",
        session_id=s.id,
        session_code=s.code,
        count=len(rows),
    )
    count = len(rows)
    average = round(sum(r.rating for r in rows) / count, 2) if count else None
    distribution = {i: 0 for i in range(1, 6)}
    for r in rows:
        distribution[r.rating] += 1
    return {
        "count": count,
        "average": average,
        "distribution": distribution,
        "items": [serialize_feedback(r) for r in rows],
    }


# ---------- routes: queries (the Q&A board) ----------

@app.get("/api/sessions/{code}/queries")
def list_queries(
    code: str,
    request: Request,
    response: Response,
    display: bool = False,
    voter_token: Annotated[str | None, Cookie()] = None,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
    me: m.User | None = Depends(auth.optional_admin),
):
    s = get_session_by_code(db, code)
    is_mod = is_mod_authed(s, x_mod_key) or is_admin_owner(s, me)
    p = None if display else current_participant(s, request, response, voter_token, db)
    return serialize_session_queries(
        db,
        s,
        viewer_participant_id=p.id if p else None,
        is_mod=is_mod,
    )


@app.post("/api/sessions/{code}/queries")
async def create_query(
    code: str,
    payload: dict,
    request: Request,
    response: Response,
    voter_token: Annotated[str | None, Cookie()] = None,
    db: DbSession = Depends(get_db),
):
    s = get_session_by_code(db, code)
    if s.status == "ended":
        raise HTTPException(400, "Session has ended")
    if not allow_person("ask", request, voter_token):
        raise HTTPException(429, "You're asking too fast — wait a moment and try again")
    text = _text(payload, "text").strip()
    if not text:
        raise HTTPException(400, "text required")
    if len(text) > 1000:
        raise HTTPException(400, "text too long")
    p = current_participant(s, request, response, voter_token, db)
    # A name only when the asker chose to show one for this question; the
    # profile is neither read nor changed (Anonymity, UC-P-04).
    author_name = _text(payload, "author_name").strip()[:80] or None
    q = m.Query(session_id=s.id, text=text, participant_id=p.id, author_name=author_name)
    db.add(q)
    db.commit()
    db.refresh(q)
    db.refresh(q, ["votes", "participant"])
    await broadcast_session(s, "query_new")
    return serialize_query(q, p.id)


@app.post("/api/sessions/{code}/queries/{qid}/vote")
async def toggle_vote(
    code: str,
    qid: int,
    request: Request,
    response: Response,
    voter_token: Annotated[str | None, Cookie()] = None,
    db: DbSession = Depends(get_db),
):
    s = get_session_by_code(db, code)
    if s.status == "ended":
        raise HTTPException(400, "Session has ended")
    if not allow_person("vote", request, voter_token):
        raise HTTPException(429, "Too many votes — slow down and try again")
    q = db.get(m.Query, qid)
    if not q or q.session_id != s.id:
        raise HTTPException(404, "Question not found")
    if q.removed_at is not None:
        raise HTTPException(404, "Question not found")
    p = current_participant(s, request, response, voter_token, db)
    existing = db.scalar(
        select(m.QueryVote).where(
            m.QueryVote.query_id == qid,
            m.QueryVote.participant_id == p.id,
        )
    )
    if existing:
        db.delete(existing)
        voted = False
        try:
            db.commit()
        except IntegrityError:
            db.rollback()  # Concurrent delete won — treat as idempotent.
    else:
        db.add(m.QueryVote(query_id=qid, participant_id=p.id))
        voted = True
        try:
            db.commit()
        except IntegrityError:
            # Concurrent insert won under UNIQUE(query_id, participant_id) —
            # the participant did vote, just not via this call. Idempotent.
            db.rollback()
    db.refresh(q, ["votes"])
    await broadcast_session(s, "query_vote")
    return {"voted": voted, "vote_count": len(q.votes)}


@app.post("/api/sessions/{code}/queries/{qid}/respond")
async def respond_to_query(
    code: str,
    qid: int,
    payload: dict,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
    me: m.User | None = Depends(auth.optional_admin),
):
    s = get_session_by_code(db, code)
    require_mod_or_owner(s, x_mod_key, me)
    q = db.get(m.Query, qid)
    if not q or q.session_id != s.id:
        raise HTTPException(404, "Question not found")
    q.response_text = _text(payload, "response_text").strip() or None
    q.responded_at = datetime.utcnow() if payload.get("responded", True) else None
    db.commit()
    await broadcast_session(s, "query_responded")
    log_diagnostic(
        "query.moderation",
        action="respond",
        outcome="success",
        session_id=s.id,
        session_code=s.code,
        query_id=q.id,
    )
    return {"ok": True}


@app.post("/api/sessions/{code}/queries/{qid}/remove")
async def remove_query(
    code: str,
    qid: int,
    payload: dict,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
    me: m.User | None = Depends(auth.optional_admin),
):
    """Soft-remove: hides from participants but keeps the row for audit."""
    s = get_session_by_code(db, code)
    require_mod_or_owner(s, x_mod_key, me)
    q = db.get(m.Query, qid)
    if not q or q.session_id != s.id:
        raise HTTPException(404, "Question not found")
    if payload.get("removed", True):
        q.removed_at = datetime.utcnow()
    else:
        q.removed_at = None
    db.commit()
    await broadcast_session(s, "query_removed")
    log_diagnostic(
        "query.moderation",
        action="remove",
        outcome="success",
        session_id=s.id,
        session_code=s.code,
        query_id=q.id,
    )
    return {"ok": True}


@app.delete("/api/sessions/{code}/queries/{qid}")
async def delete_query(
    code: str,
    qid: int,
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    """Hard delete: admin-owner escape hatch. Not on the standard moderator
    UI. Owner-only because deletion destroys the audit trail that
    soft-remove preserves."""
    s = get_session_by_code(db, code)
    require_session_owner(s, me)
    q = db.get(m.Query, qid)
    if not q or q.session_id != s.id:
        raise HTTPException(404, "Question not found")
    query_id = q.id
    db.delete(q)
    db.commit()
    await broadcast_session(s, "query_deleted")
    log_diagnostic(
        "query.moderation",
        action="delete",
        outcome="success",
        session_id=s.id,
        session_code=s.code,
        query_id=query_id,
    )
    return {"ok": True}


# ---------- routes: quizzes (templates) ----------

@app.get("/api/quizzes")
def list_quizzes(
    ready_only: bool = False,
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    question_count = (
        select(func.count(m.Question.id))
        .where(m.Question.quiz_id == m.Quiz.id)
        .correlate(m.Quiz)
        .scalar_subquery()
    )
    stmt = (
        select(m.Quiz, question_count.label("question_count"))
        .where(m.Quiz.owner_user_id == me.id)
        .options(selectinload(m.Quiz.questions).selectinload(m.Question.answers))
        .order_by(m.Quiz.created_at.desc())
    )
    if ready_only:
        stmt = stmt.where(m.Quiz.status == "ready")
    quizzes = db.execute(stmt).all()
    usage = quiz_session_usage(db, me.id)
    return [
        {
            "id": q.id, "title": q.title, "status": q.status, "question_count": count,
            "sessions": list(usage.get(q.id, {}).values()),
            "problem": quiz_problem(q),
        }
        for q, count in quizzes
    ]


@app.post("/api/quizzes")
def create_quiz(
    payload: dict,
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    title = _text(payload, "title").strip() or "Untitled quiz"
    quiz = m.Quiz(title=title, owner_user_id=me.id)
    db.add(quiz)
    db.commit()
    db.refresh(quiz)
    return {"id": quiz.id, "title": quiz.title, "status": quiz.status}


def _owned_quiz_or_404(db: DbSession, quiz_id: int, user: m.User) -> m.Quiz:
    quiz = db.get(m.Quiz, quiz_id)
    if not quiz or quiz.owner_user_id != user.id:
        raise HTTPException(404, "Quiz not found")
    return quiz


@app.get("/api/quizzes/{quiz_id}")
def get_quiz(
    quiz_id: int,
    include_correct: bool = False,
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    quiz = _owned_quiz_or_404(db, quiz_id, me)
    # Every failing publish rule, so the editor can mark them all (UC-A-21).
    return {
        **serialize_quiz(quiz, include_correct=include_correct),
        "problems": [p.as_json() for p in _publish_problems(quiz)],
    }


@app.post("/api/quizzes/{quiz_id}/publish")
def publish_quiz(
    quiz_id: int,
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    quiz = _owned_quiz_or_404(db, quiz_id, me)
    _validate_quiz_publishable(quiz)
    quiz.status = "ready"
    db.commit()
    return {"status": quiz.status}


@app.post("/api/quizzes/{quiz_id}/unpublish")
def unpublish_quiz(
    quiz_id: int,
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    quiz = _owned_quiz_or_404(db, quiz_id, me)
    quiz.status = "draft"
    db.commit()
    return {"status": quiz.status}


@app.patch("/api/quizzes/{quiz_id}")
def update_quiz(
    quiz_id: int,
    payload: dict,
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    quiz = _owned_quiz_or_404(db, quiz_id, me)
    if "title" in payload:
        new_title = _text(payload, "title").strip()
        if not new_title:
            raise HTTPException(400, "Quiz title is required")
        if new_title != quiz.title:
            quiz.title = new_title
            _mark_quiz_edited(quiz)
    db.commit()
    return {"ok": True, "status": quiz.status}


@app.delete("/api/quizzes/{quiz_id}")
def delete_quiz(
    quiz_id: int,
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    quiz = _owned_quiz_or_404(db, quiz_id, me)
    used = db.scalar(
        select(m.QuizRun.id)
        .join(m.QuizVersion, m.QuizRun.quiz_version_id == m.QuizVersion.id)
        .where(m.QuizVersion.quiz_id == quiz_id)
        .limit(1)
    )
    if used:
        raise HTTPException(400, "Quiz has been used in a session run and cannot be deleted")
    db.delete(quiz)
    db.commit()
    return {"ok": True}


COPY_SUFFIX = " (copy)"
QUIZ_TITLE_MAX = 200  # matches Quiz.title column length


@app.post("/api/quizzes/{quiz_id}/duplicate")
def duplicate_quiz(
    quiz_id: int,
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    """Copy the editable tree into a new draft quiz. Versions and runs stay
    with the source; image files are shared by URL (uploads are never
    deleted, so sharing is safe)."""
    src = _owned_quiz_or_404(db, quiz_id, me)
    title = src.title[: QUIZ_TITLE_MAX - len(COPY_SUFFIX)] + COPY_SUFFIX
    copy = m.Quiz(
        title=title,
        owner_user_id=me.id,
        questions=[
            m.Question(
                text=qq.text,
                image_url=qq.image_url,
                qtype=qq.qtype,
                graded=qq.graded,
                order_index=qq.order_index,
                answers=[
                    m.Answer(
                        text=a.text,
                        image_url=a.image_url,
                        is_correct=a.is_correct,
                        order_index=a.order_index,
                    )
                    for a in qq.answers
                ],
            )
            for qq in src.questions
        ],
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return {"id": copy.id, "title": copy.title, "status": copy.status}


@app.post("/api/quizzes/{quiz_id}/questions")
def add_quiz_question(
    quiz_id: int,
    payload: dict,
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    quiz = _owned_quiz_or_404(db, quiz_id, me)
    qtype = payload.get("qtype", "single")
    if qtype not in ("single", "multi"):
        raise HTTPException(400, "qtype must be single or multi")
    existing = list(quiz.questions)
    position = payload.get("position")
    if position is None:
        raw_order = payload.get("order_index")
        order_index = (
            max((qq.order_index for qq in existing), default=-1) + 1
            if raw_order is None else _order_index(raw_order)
        )
    else:
        # Insert at a 0-based index (UC-A-14): later questions shift down and
        # every question is renumbered 0..n in this same transaction.
        if not isinstance(position, int) or isinstance(position, bool):
            raise HTTPException(400, "position must be an integer")
        if not 0 <= position <= len(existing):
            raise HTTPException(400, "position out of range")
        for idx, other in enumerate(existing):
            other.order_index = idx if idx < position else idx + 1
        order_index = position
    qq = m.Question(
        quiz_id=quiz_id,
        text=_text(payload, "text").strip(),
        image_url=payload.get("image_url"),
        qtype=qtype,
        graded=bool(payload.get("graded", True)),
        order_index=order_index,
    )
    db.add(qq)
    _mark_quiz_edited(quiz)
    db.commit()
    db.refresh(qq)
    return {"id": qq.id}


def _owned_quiz_question_or_404(db: DbSession, question_id: int, user: m.User) -> m.Question:
    qq = db.get(m.Question, question_id)
    if not qq or qq.quiz.owner_user_id != user.id:
        raise HTTPException(404, "Question not found")
    return qq


def _apply_order(items: list, ids: object, message: str) -> None:
    """Renumber `items` 0..n-1 in the order given by `ids`, which must list
    every item's id exactly once; otherwise 400 and nothing changes."""
    by_id = {item.id: item for item in items}
    if (
        not isinstance(ids, list)
        or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids)
        or len(ids) != len(by_id)
        or set(ids) != set(by_id)
    ):
        raise HTTPException(400, message)
    for position, item_id in enumerate(ids):
        by_id[item_id].order_index = position


@app.put("/api/quizzes/{quiz_id}/question_order")
def reorder_quiz_questions(
    quiz_id: int,
    payload: dict,
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    quiz = _owned_quiz_or_404(db, quiz_id, me)
    _apply_order(
        quiz.questions,
        payload.get("question_ids"),
        "question_ids must list every question in this quiz exactly once",
    )
    _mark_quiz_edited(quiz)
    db.commit()
    return {"ok": True}


@app.put("/api/quiz_questions/{question_id}/answer_order")
def reorder_quiz_answers(
    question_id: int,
    payload: dict,
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    qq = _owned_quiz_question_or_404(db, question_id, me)
    _apply_order(
        qq.answers,
        payload.get("answer_ids"),
        "answer_ids must list every answer of this question exactly once",
    )
    _mark_quiz_edited(qq.quiz)
    db.commit()
    return {"ok": True}


@app.patch("/api/quiz_questions/{question_id}")
def update_quiz_question(
    question_id: int,
    payload: dict,
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    qq = _owned_quiz_question_or_404(db, question_id, me)
    if "text" in payload:
        qq.text = _text(payload, "text").strip()
    if "image_url" in payload:
        v = payload["image_url"]
        qq.image_url = str(v) if v else None
    if "qtype" in payload:
        if payload["qtype"] not in ("single", "multi"):
            raise HTTPException(400, "qtype must be single or multi")
        qq.qtype = payload["qtype"]
    if "graded" in payload:
        qq.graded = bool(payload["graded"])
    if "order_index" in payload:
        qq.order_index = _order_index(payload["order_index"])
    _mark_quiz_edited(qq.quiz)
    db.commit()
    return {"ok": True}


@app.delete("/api/quiz_questions/{question_id}")
def delete_quiz_question(
    question_id: int,
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    qq = _owned_quiz_question_or_404(db, question_id, me)
    quiz = qq.quiz
    db.delete(qq)
    _mark_quiz_edited(quiz)
    db.commit()
    return {"ok": True}


@app.post("/api/quiz_questions/{question_id}/answers")
def add_quiz_answer(
    question_id: int,
    payload: dict,
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    qq = _owned_quiz_question_or_404(db, question_id, me)
    raw_order = payload.get("order_index")
    order_index = (
        max((a.order_index for a in qq.answers), default=-1) + 1
        if raw_order is None else _order_index(raw_order)
    )
    a = m.Answer(
        question_id=question_id,
        text=_text(payload, "text").strip(),
        image_url=payload.get("image_url"),
        is_correct=bool(payload.get("is_correct", False)),
        order_index=order_index,
    )
    db.add(a)
    _mark_quiz_edited(qq.quiz)
    db.commit()
    db.refresh(a)
    return {"id": a.id}


def _owned_quiz_answer_or_404(db: DbSession, answer_id: int, user: m.User) -> m.Answer:
    a = db.get(m.Answer, answer_id)
    if not a or a.question.quiz.owner_user_id != user.id:
        raise HTTPException(404, "Answer not found")
    return a


@app.patch("/api/quiz_answers/{answer_id}")
def update_quiz_answer(
    answer_id: int,
    payload: dict,
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    a = _owned_quiz_answer_or_404(db, answer_id, me)
    if "text" in payload:
        a.text = _text(payload, "text").strip()
    if "image_url" in payload:
        v = payload["image_url"]
        a.image_url = str(v) if v else None
    if "is_correct" in payload:
        a.is_correct = bool(payload["is_correct"])
    if "order_index" in payload:
        a.order_index = _order_index(payload["order_index"])
    _mark_quiz_edited(a.question.quiz)
    db.commit()
    return {"ok": True}


@app.delete("/api/quiz_answers/{answer_id}")
def delete_quiz_answer(
    answer_id: int,
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    a = _owned_quiz_answer_or_404(db, answer_id, me)
    quiz = a.question.quiz
    db.delete(a)
    _mark_quiz_edited(quiz)
    db.commit()
    return {"ok": True}


# ---------- routes: uploads ----------

async def store_uploaded_image(file: UploadFile, *, actor: str) -> str:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTS:
        log_diagnostic(
            "upload.reject",
            actor=actor,
            reason="extension",
            extension=ext,
        )
        raise HTTPException(400, "Images must be PNG, JPEG, GIF or WebP")
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        log_diagnostic(
            "upload.reject",
            actor=actor,
            reason="size",
            size=file.size,
        )
        raise HTTPException(400, "Images must be 5 MB or smaller")
    buf = bytearray()
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > MAX_UPLOAD_BYTES:
            log_diagnostic(
                "upload.reject",
                actor=actor,
                reason="size",
                size=len(buf),
            )
            raise HTTPException(400, "Images must be 5 MB or smaller")
    name = f"{uuid.uuid4().hex}{ext}"
    (UPLOADS / name).write_bytes(bytes(buf))
    log_diagnostic(
        "upload.accept",
        actor=actor,
        outcome="success",
        extension=ext,
        size=len(buf),
    )
    return f"/uploads/{name}"


def delete_uploaded_file(url: str | None) -> None:
    """Delete a file store_uploaded_image saved, given its /uploads/ URL;
    anything else is left alone."""
    name = (url or "").removeprefix("/uploads/")
    if url and url.startswith("/uploads/") and re.fullmatch(r"[0-9a-f]{32}\.[a-z]+", name):
        (UPLOADS / name).unlink(missing_ok=True)


@app.post("/api/uploads")
async def upload_image(
    file: UploadFile = File(...),
    _admin: m.User = Depends(auth.current_admin),
):
    return {"url": await store_uploaded_image(file, actor="admin_quiz")}


# ---------- routes: quiz runs ----------

@app.get("/api/quiz_runs")
def list_all_quiz_runs(
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    """Admin-wide view of every quiz run for sessions this admin owns."""
    question_count = (
        select(func.count(m.QuizVersionQuestion.id))
        .where(m.QuizVersionQuestion.version_id == m.QuizRun.quiz_version_id)
        .correlate(m.QuizRun)
        .scalar_subquery()
    )
    respondent_count = (
        select(func.count(func.distinct(m.QuizSubmission.participant_id)))
        .where(m.QuizSubmission.quiz_run_id == m.QuizRun.id)
        .correlate(m.QuizRun)
        .scalar_subquery()
    )
    rows = db.execute(
        select(
            m.QuizRun,
            m.Session,
            m.QuizVersion,
            question_count.label("question_count"),
            respondent_count.label("respondent_count"),
        )
        .join(m.Session, m.QuizRun.session_id == m.Session.id)
        .join(m.QuizVersion, m.QuizRun.quiz_version_id == m.QuizVersion.id)
        .where(m.Session.owner_user_id == me.id)
        .order_by(m.QuizRun.created_at.desc())
    ).all()
    out = []
    for r, session, version, questions, respondents in rows:
        out.append({
            "id": r.id,
            "status": r.status,
            "session_code": session.code,
            "session_title": session.title,
            "quiz_id": version.quiz_id,
            "quiz_title": version.quiz_title,
            "version_no": version.version_no,
            "current_question_idx": r.current_question_idx,
            "question_count": questions,
            "respondent_count": respondents,
            "created_at": iso(r.created_at),
            "started_at": iso(r.started_at),
            "closed_at": iso(r.closed_at),
        })
    return out


@app.get("/api/quiz_runs/{run_id}/results")
def quiz_run_results(
    run_id: int,
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    run = db.get(m.QuizRun, run_id)
    if not run or run.session.owner_user_id != me.id:
        raise HTTPException(404, "Quiz run not found")
    version = run.quiz_version
    questions = []
    for vq in version.questions:
        tally = tally_question(db, run, vq)
        questions.append({
            "id": vq.id,
            "text": vq.text,
            "image_url": vq.image_url,
            "qtype": vq.qtype,
            "graded": vq.graded,
            "answers": [
                {
                    "id": a.id,
                    "text": a.text,
                    "image_url": a.image_url,
                    "is_correct": vq.graded and a.is_correct,
                    "count": tally["totals"].get(a.id, 0),
                }
                for a in vq.answers
            ],
            "respondents": tally["respondents"],
        })
    return {
        "id": run.id,
        "status": run.status,
        "session_code": run.session.code,
        "session_title": run.session.title,
        "quiz_title": version.quiz_title,
        "version_no": version.version_no,
        "current_question_idx": run.current_question_idx,
        "questions": questions,
    }


@app.get("/api/sessions/{code}/quiz_runs")
def list_quiz_runs(
    code: str,
    request: Request,
    response: Response,
    display: bool = False,
    voter_token: Annotated[str | None, Cookie()] = None,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
    me: m.User | None = Depends(auth.optional_admin),
):
    s = get_session_by_code(db, code)
    is_mod = is_mod_authed(s, x_mod_key) or is_admin_owner(s, me)
    p = None if display else current_participant(s, request, response, voter_token, db)
    # Non-mods see queued/live/closed (queued powers the projector "Next up"
    # lobby). The participant page itself ignores queued in its own render.
    return serialize_session_quiz_runs(
        db,
        s,
        viewer_participant_id=p.id if p else None,
        is_mod=is_mod,
    )


@app.get("/api/sessions/{code}/available_quizzes")
def list_available_quizzes(
    code: str,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
    me: m.User | None = Depends(auth.optional_admin),
):
    """Quizzes the session-owner can launch in this session.

    Same shape as `/api/quizzes`, but gated on mod-or-owner auth so a
    delegate (mod-key holder, no admin account) can populate the Add quiz
    picker. Filters by `owner_user_id = session.owner_user_id`. Delegates
    get Ready quizzes only; the admin owner also gets drafts (UC-M-03).
    """
    s = get_session_by_code(db, code)
    require_mod_or_owner(s, x_mod_key, me)
    return available_quiz_summaries(db, s, include_drafts=is_admin_owner(s, me))


@app.post("/api/sessions/{code}/quiz_runs")
async def create_quiz_run(
    code: str,
    payload: dict,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
    me: m.User | None = Depends(auth.optional_admin),
):
    s = get_session_by_code(db, code)
    require_mod_or_owner(s, x_mod_key, me)
    if s.status == "ended":
        raise HTTPException(400, "Session has ended")
    quiz_id = payload.get("quiz_id")
    quiz = db.get(m.Quiz, quiz_id) if quiz_id else None
    if not quiz or quiz.owner_user_id != s.owner_user_id:
        raise HTTPException(404, "Quiz not found")
    if quiz.status != "ready":
        if not payload.get("publish"):
            raise HTTPException(400, "Quiz is still a draft — publish it first")
        # Publishing is an authoring action: only the admin owner, never a
        # delegate holding just the mod_key.
        if not is_admin_owner(s, me):
            raise HTTPException(403, "Only the admin can publish a draft quiz")
        _validate_quiz_publishable(quiz)
        quiz.status = "ready"
    version = _ensure_current_version(db, quiz)
    run = m.QuizRun(session_id=s.id, quiz_version_id=version.id, status="queued")
    db.add(run)
    db.commit()
    db.refresh(run)
    await broadcast_session(s, "quiz_run_new")
    log_diagnostic(
        "quiz_run.lifecycle",
        action="create",
        outcome="success",
        session_id=s.id,
        session_code=s.code,
        run_id=run.id,
    )
    return {"id": run.id, "version_no": version.version_no, "status": run.status}


def _get_run_mod(
    db: DbSession,
    code: str,
    run_id: int,
    mod_key: str | None,
    user: m.User | None,
) -> tuple[m.Session, m.QuizRun]:
    s = get_session_by_code(db, code)
    require_mod_or_owner(s, mod_key, user)
    run = db.get(m.QuizRun, run_id)
    if not run or run.session_id != s.id:
        raise HTTPException(404, "Quiz run not found")
    return s, run


@app.post("/api/sessions/{code}/quiz_runs/{run_id}/start")
async def start_quiz_run(
    code: str,
    run_id: int,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
    me: m.User | None = Depends(auth.optional_admin),
):
    s, run = _get_run_mod(db, code, run_id, x_mod_key, me)
    if run.status != "queued":
        raise HTTPException(400, f"Cannot start from status: {run.status}")
    if s.status == "ended":
        raise HTTPException(400, "Session has ended")
    session_started = s.status == "planning"
    if session_started:
        s.status = "live"
        s.started_at = datetime.utcnow()
    run.status = "live"
    run.current_question_idx = 0
    run.reveal_current = False
    run.revealed_idxs = ""
    run.started_at = datetime.utcnow()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        log_diagnostic(
            "quiz_run.lifecycle",
            action="start",
            outcome="conflict",
            session_id=s.id,
            session_code=s.code,
            run_id=run.id,
        )
        raise HTTPException(409, "Another quiz is already live — close it first.")
    await broadcast_session(s, "quiz_run_update")
    if session_started:
        # The session went live with this run (UC-M-04): every page shows it.
        await broadcast_session(s, "session_state")
        log_diagnostic(
            "session.lifecycle",
            action="start",
            outcome="success",
            actor_id=me.id if me else None,
            session_id=s.id,
            session_code=s.code,
        )
    log_diagnostic(
        "quiz_run.lifecycle",
        action="start",
        outcome="success",
        session_id=s.id,
        session_code=s.code,
        run_id=run.id,
    )
    return {"ok": True}


def _revealed(run: m.QuizRun) -> set[int]:
    return {int(i) for i in (run.revealed_idxs or "").split(",") if i}


@app.post("/api/sessions/{code}/quiz_runs/{run_id}/advance")
async def advance_quiz_run(
    code: str,
    run_id: int,
    payload: dict,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
    me: m.User | None = Depends(auth.optional_admin),
):
    s, run = _get_run_mod(db, code, run_id, x_mod_key, me)
    if run.status != "live":
        raise HTTPException(400, f"Cannot advance from status: {run.status}")
    direction = payload.get("direction", "next")
    total = len(run.quiz_version.questions)
    if direction == "next":
        run.current_question_idx = min(run.current_question_idx + 1, max(total - 1, 0))
    elif direction == "prev":
        run.current_question_idx = max(run.current_question_idx - 1, 0)
    elif direction == "to":
        if "index" not in payload:
            raise HTTPException(400, "index is required")
        try:
            idx = int(payload["index"])
        except (TypeError, ValueError):
            raise HTTPException(400, "index must be an integer")
        run.current_question_idx = max(0, min(idx, max(total - 1, 0)))
    else:
        raise HTTPException(400, "direction must be next, prev or to")
    # A question revealed earlier stays revealed, so its voting stays closed
    # (UC-M-05).
    run.reveal_current = run.current_question_idx in _revealed(run)
    db.commit()
    await broadcast_session(s, "quiz_run_update")
    log_diagnostic(
        "quiz_run.lifecycle",
        action="advance",
        outcome="success",
        session_id=s.id,
        session_code=s.code,
        run_id=run.id,
    )
    return {"ok": True}


@app.post("/api/sessions/{code}/quiz_runs/{run_id}/live_counts")
async def set_live_counts(
    code: str,
    run_id: int,
    payload: dict,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
    me: m.User | None = Depends(auth.optional_admin),
):
    """Toggle whether the answering phase exposes running answer counts.

    Allowed while queued (mod configures ahead of Start) or live. Blocked
    on closed — those runs are historical.
    """
    s, run = _get_run_mod(db, code, run_id, x_mod_key, me)
    if run.status == "closed":
        raise HTTPException(400, "Cannot toggle live counts on a closed run")
    run.show_live_counts = bool(payload.get("show", True))
    db.commit()
    await broadcast_session(s, "quiz_run_update")
    log_diagnostic(
        "quiz_run.lifecycle",
        action="live_counts",
        outcome="success",
        session_id=s.id,
        session_code=s.code,
        run_id=run.id,
    )
    return {"show_live_counts": run.show_live_counts}


@app.post("/api/sessions/{code}/quiz_runs/{run_id}/reveal")
async def reveal_quiz_run(
    code: str,
    run_id: int,
    payload: dict,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
    me: m.User | None = Depends(auth.optional_admin),
):
    s, run = _get_run_mod(db, code, run_id, x_mod_key, me)
    if run.status != "live":
        raise HTTPException(400, f"Cannot reveal from status: {run.status}")
    run.reveal_current = bool(payload.get("reveal", True))
    revealed = _revealed(run)
    if run.reveal_current:
        revealed.add(run.current_question_idx)
    else:
        revealed.discard(run.current_question_idx)
    run.revealed_idxs = ",".join(str(i) for i in sorted(revealed))
    db.commit()
    await broadcast_session(s, "quiz_run_update")
    log_diagnostic(
        "quiz_run.lifecycle",
        action="reveal",
        outcome="success",
        session_id=s.id,
        session_code=s.code,
        run_id=run.id,
    )
    return {"ok": True}


@app.post("/api/sessions/{code}/quiz_runs/{run_id}/close")
async def close_quiz_run(
    code: str,
    run_id: int,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
    me: m.User | None = Depends(auth.optional_admin),
):
    s, run = _get_run_mod(db, code, run_id, x_mod_key, me)
    if run.status != "live":
        raise HTTPException(400, f"Cannot close from status: {run.status}")
    run.status = "closed"
    run.reveal_current = True
    run.closed_at = datetime.utcnow()
    db.commit()
    await broadcast_session(s, "quiz_run_update")
    log_diagnostic(
        "quiz_run.lifecycle",
        action="close",
        outcome="success",
        session_id=s.id,
        session_code=s.code,
        run_id=run.id,
    )
    return {"ok": True}


@app.delete("/api/sessions/{code}/quiz_runs/{run_id}")
async def delete_quiz_run(
    code: str,
    run_id: int,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
    me: m.User | None = Depends(auth.optional_admin),
):
    s, run = _get_run_mod(db, code, run_id, x_mod_key, me)
    if run.status == "closed":
        raise HTTPException(400, "Closed quiz runs are historical and cannot be deleted")
    deleted_run_id = run.id
    db.delete(run)
    db.commit()
    await broadcast_session(s, "quiz_run_deleted")
    log_diagnostic(
        "quiz_run.lifecycle",
        action="delete",
        outcome="success",
        session_id=s.id,
        session_code=s.code,
        run_id=deleted_run_id,
    )
    return {"ok": True}


@app.get("/api/sessions/{code}/quiz_runs/{run_id}")
def get_quiz_run(
    code: str,
    run_id: int,
    request: Request,
    response: Response,
    voter_token: Annotated[str | None, Cookie()] = None,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
    me: m.User | None = Depends(auth.optional_admin),
):
    s = get_session_by_code(db, code)
    is_mod = is_mod_authed(s, x_mod_key) or is_admin_owner(s, me)
    p = current_participant(s, request, response, voter_token, db)
    run = db.get(m.QuizRun, run_id)
    if not run or run.session_id != s.id:
        raise HTTPException(404, "Quiz run not found")
    if not is_mod and run.status not in ("live", "closed"):
        raise HTTPException(404, "Quiz run not found")
    return serialize_quiz_run(db, run, viewer_participant_id=p.id, is_mod=is_mod)


@app.post("/api/sessions/{code}/quiz_runs/{run_id}/submit")
async def submit_quiz_run(
    code: str,
    run_id: int,
    payload: dict,
    request: Request,
    response: Response,
    voter_token: Annotated[str | None, Cookie()] = None,
    db: DbSession = Depends(get_db),
):
    """Participant submits their selected answer(s) for the current question."""
    s = get_session_by_code(db, code)
    if s.status == "ended":
        raise HTTPException(400, "Session has ended")
    if not allow_person("submit", request, voter_token):
        raise HTTPException(429, "Too many submissions — slow down and try again")
    run = db.get(m.QuizRun, run_id)
    if not run or run.session_id != s.id or run.status != "live":
        raise HTTPException(404, "Quiz not live")
    # Voting closes when the moderator reveals results — last-write-wins
    # otherwise lets participants change their answer after seeing the
    # correctness markers and skew the final tally.
    if run.reveal_current:
        raise HTTPException(400, "Voting closed — results have been revealed")
    question_id = payload.get("question_id")
    answer_ids_raw = payload.get("answer_ids") or []
    if not isinstance(answer_ids_raw, list):
        raise HTTPException(400, "answer_ids must be a list")
    try:
        answer_ids = [int(a) for a in answer_ids_raw]
    except (TypeError, ValueError):
        raise HTTPException(400, "answer_ids must be integers")
    # Dedupe so duplicate ids in the payload don't collide with the
    # UNIQUE(quiz_run_id, question_id, answer_id, participant_id) constraint.
    answer_ids = list(dict.fromkeys(answer_ids))
    vq = db.get(m.QuizVersionQuestion, question_id)
    if not vq or vq.version_id != run.quiz_version_id:
        raise HTTPException(404, "Question not in this quiz run")
    questions = run.quiz_version.questions
    if questions[run.current_question_idx].id != vq.id:
        raise HTTPException(400, "Not the current question")
    if vq.qtype == "single" and len(answer_ids) > 1:
        raise HTTPException(400, "Only one answer allowed")
    valid_answer_ids = {a.id for a in vq.answers}
    if any(aid not in valid_answer_ids for aid in answer_ids):
        raise HTTPException(400, "Invalid answer")
    p = current_participant(s, request, response, voter_token, db)
    existing = {
        r.answer_id: r for r in db.scalars(
            select(m.QuizSubmission).where(
                m.QuizSubmission.quiz_run_id == run.id,
                m.QuizSubmission.question_id == vq.id,
                m.QuizSubmission.participant_id == p.id,
            )
        ).all()
    }
    new_ids = set(answer_ids)
    # Diff rather than delete-all-then-reinsert: re-submitting the identical
    # selection is then a no-op. (Delete-all-then-insert would 500 — the unit
    # of work flushes the new INSERT before the old DELETE, colliding on
    # UNIQUE(run, question, answer, participant).)
    for aid, row in existing.items():
        if aid not in new_ids:
            db.delete(row)
    for aid in answer_ids:
        if aid not in existing:
            db.add(m.QuizSubmission(
                quiz_run_id=run.id,
                question_id=vq.id,
                answer_id=aid,
                participant_id=p.id,
            ))
    db.commit()
    await broadcast_session(s, "quiz_submission")
    return {"ok": True}


# ---------- routes: data export (UC-A-30) ----------
# Owner-only: exports include participants' contact details, so the mod_key
# delegation path never reaches them.


def _export_format(value: str) -> str:
    if value not in data_export.FORMATS:
        raise HTTPException(400, data_export.FORMAT_ERROR)
    return value


def _export_response(result: data_export.Export, scope: str) -> Response:
    log_diagnostic("export.download", outcome="success", scope=scope,
                   format=result.filename.rsplit(".", 1)[-1], size_bytes=len(result.content))
    return Response(
        content=result.content,
        media_type=result.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{result.filename}"',
            "Cache-Control": "no-store",
        },
    )


@app.get("/api/export/all")
def export_all_data(
    format: str = "json",
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    fmt = _export_format(format)
    return _export_response(data_export.export_all(db, me, fmt), "all")


@app.get("/api/sessions/{code}/export")
def export_session(
    code: str,
    format: str = "json",
    part: str = "all",
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    s = get_session_by_code(db, code)
    require_session_owner(s, me)
    fmt = _export_format(format)
    if part not in data_export.PARTS:
        raise HTTPException(400, data_export.PART_ERROR)
    return _export_response(data_export.export_session(db, s, fmt, part), f"session:{part}")


@app.get("/api/quiz_runs/{run_id}/export")
def export_quiz_run(
    run_id: int,
    format: str = "json",
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    run = db.get(m.QuizRun, run_id)
    if not run or run.session.owner_user_id != me.id:
        raise HTTPException(404, "Quiz run not found")
    fmt = _export_format(format)
    return _export_response(data_export.export_quiz_run(db, run, fmt), "quiz_run")


@app.get("/api/quizzes/{quiz_id}/export")
def export_quiz(
    quiz_id: int,
    format: str = "json",
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    quiz = _owned_quiz_or_404(db, quiz_id, me)
    fmt = _export_format(format)
    return _export_response(data_export.export_quiz(db, quiz, fmt), "quiz")


# ---------- websocket ----------

async def _ws_reject(ws: WebSocket, code: int) -> None:
    """Close with an application code the browser can read (UC-X-02).

    A refused handshake reaches a page only as close code 1006, so the page
    cannot tell "stop" from "retry". Accepting first carries the code; the
    socket joins no room and is sent nothing.
    """
    await ws.accept()
    await ws.close(code=code)


@app.websocket("/ws/sessions/{code}")
async def ws_session(ws: WebSocket, code: str):
    origin = ws.headers.get("origin")
    if origin:
        host = ws.headers.get("host", "")
        if origin not in (f"http://{host}", f"https://{host}"):
            log_diagnostic("ws.reject", outcome="failure", reason="origin")
            await _ws_reject(ws, 4403)
            return
    with SessionLocal() as db:
        s = db.scalar(select(m.Session).where(m.Session.code == code.upper()))
        if not s:
            log_diagnostic("ws.reject", outcome="failure", reason="session")
            await _ws_reject(ws, 4404)
            return
    room = f"session:{code.upper()}"
    await hub.join(room, ws)
    log_diagnostic(
        "ws.join",
        outcome="success",
        session_id=s.id,
        session_code=s.code,
    )
    try:
        while True:
            # Pages send "ping" every 25 s and reconnect if nothing comes back
            # (UC-X-01); every other client frame is ignored.
            if await ws.receive_text() == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        hub.leave(room, ws)
        log_diagnostic(
            "ws.disconnect",
            outcome="success",
            session_id=s.id,
            session_code=s.code,
        )
    except Exception:
        hub.leave(room, ws)
        log_diagnostic(
            "ws.error",
            outcome="failure",
            session_id=s.id,
            session_code=s.code,
        )
