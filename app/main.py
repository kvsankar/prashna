"""Prashna — live Q&A + quiz tool for training sessions."""
from __future__ import annotations

import logging
import os
import secrets
import threading
import uuid
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

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
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload
from starlette.middleware.base import BaseHTTPMiddleware

from . import auth, oauth
from . import models as m
from .db import SessionLocal, get_db, init_db
from .diagnostics import log_diagnostic
from .ratelimit import TokenBucketLimiter, enabled_from_env
from .ws import hub

BASE = Path(__file__).resolve().parent.parent
# Vite build output (the TypeScript frontend). Produced by `npm run build`
# (and by the Docker build stage in prod). Pages 404 until it exists — in
# dev use the Vite dev server (`npm run dev`) which proxies the API here.
STATIC = BASE / "frontend" / "dist"
UPLOADS = Path(os.environ.get("PRASHNA_UPLOADS_DIR") or (BASE / "uploads"))
UPLOADS.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
PRESENCE_WINDOW = timedelta(seconds=30)
LAST_SEEN_THROTTLE = timedelta(seconds=5)

# ---------- rate limiting (UC-X-08) ----------
# Single-process in-memory limiter. Keyed by client IP. See app/ratelimit.py.
limiter = TokenBucketLimiter(enabled=enabled_from_env(os.environ.get("PRASHNA_RATELIMIT")))

# Number of trusted reverse-proxy hops in front of the app. 0 (default) =
# use the socket peer (correct for direct localhost; degrades to a global
# throttle behind a proxy). Set to 1 when fronted by ngrok or the bundled
# nginx (a single hop) so the limiter keys on the real client IP and not a
# spoofable X-Forwarded-For prefix.
TRUSTED_PROXY_HOPS = max(0, int(os.environ.get("PRASHNA_TRUSTED_PROXY_HOPS") or 0))

# (capacity = burst, refill = tokens/second). Generous for a human,
# hostile to a script. Tunable here; not per-deployment config by design.
RL_LOGIN = (8, 1 / 30)       # admin login attempts per IP
RL_NEW_PARTICIPANT = (15, 1 / 20)  # fresh Participant rows per IP
RL_ASK = (6, 1 / 10)         # query submissions per IP
RL_VOTE = (30, 2.0)          # query vote toggles per IP
RL_SUBMIT = (20, 0.5)        # quiz-answer submissions per IP
RL_FEEDBACK = (10, 0.5)      # session-feedback submissions per IP


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


logger = logging.getLogger("prashna")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    if auth.SECRET_KEY_IS_EPHEMERAL:
        logger.warning(
            "PRASHNA_SECRET_KEY is not set — admin sessions use an ephemeral "
            "signing key and will be invalidated on every restart. Set it to a "
            "long, stable random string for any real deployment (UC-X-07)."
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
        if request.url.path.startswith("/uploads/"):
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
            response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        else:
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("X-Frame-Options", "DENY")
            response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'")
            response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response


app.add_middleware(SecurityHeaders)

app.mount("/uploads", StaticFiles(directory=UPLOADS), name="uploads")
# Mounted only when a build exists, so importing the app (e.g. the API tests,
# which don't build the frontend) never fails on a missing dist dir.
if STATIC.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")


# ---------- helpers ----------

MIN_PASSWORD_LEN = 8
MAX_USERNAME_LEN = 80


def _validate_credentials(username: str, password: str) -> tuple[str, str]:
    u = (username or "").strip()
    if not u or len(u) > MAX_USERNAME_LEN:
        raise HTTPException(400, "username required")
    if not password or len(password) < MIN_PASSWORD_LEN:
        raise HTTPException(400, f"password must be at least {MIN_PASSWORD_LEN} characters")
    return u, password


def gen_code(n: int = 6) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(n))


def gen_token() -> str:
    return uuid.uuid4().hex


def _set_voter_cookie(request: Request, response: Response, token: str) -> None:
    """voter_token is non-HttpOnly on purpose — frontend reads it for 'mine' checks."""
    secure = request.url.scheme == "https"
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
        if not limiter.allow(f"newp:{_client_ip(request)}", *RL_NEW_PARTICIPANT):
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


def normalize_optional_text(value, max_len: int) -> str | None:
    text = (value or "").strip()
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


def participant_has_profile(p: m.Participant) -> bool:
    return (
        p.photo_url is not None
        or any(getattr(p, field) for field in PROFILE_FIELDS)
    )


def serialize_query(q: m.Query, viewer_participant_id: int | None, is_mod: bool) -> dict:
    return {
        "id": q.id,
        "text": q.text,
        "author_name": q.participant.name if q.participant else None,
        "response_text": q.response_text,
        "responded": q.responded_at is not None,
        "removed": q.removed_at is not None,
        "vote_count": len(q.votes),
        "voted": any(v.participant_id == viewer_participant_id for v in q.votes),
        "mine": q.participant_id == viewer_participant_id,
        "created_at": q.created_at.isoformat(),
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
    payload = {
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
            payload["results"] = tally_question(db, run, current)
    return payload


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


# ---------- quiz lifecycle helpers ----------

def _validate_quiz_publishable(quiz: m.Quiz) -> None:
    if not quiz.questions:
        raise HTTPException(400, "Quiz needs at least one question")
    for idx, qq in enumerate(quiz.questions, start=1):
        if not qq.text.strip():
            raise HTTPException(400, f"Question {idx} is missing text")
        if len(qq.answers) < 2:
            raise HTTPException(400, f"Question {idx} needs at least 2 answers")
        # Poll/survey questions (graded=False) intentionally have no correct
        # answer — skip the correctness requirement for them.
        if qq.graded:
            correct = [a for a in qq.answers if a.is_correct]
            if qq.qtype == "single" and len(correct) != 1:
                raise HTTPException(400, f"Question {idx} (single choice) needs exactly one correct answer")
            if qq.qtype == "multi" and len(correct) < 1:
                raise HTTPException(400, f"Question {idx} (multiple choice) needs at least one correct answer")
        for ai, a in enumerate(qq.answers, start=1):
            if not a.text.strip() and not a.image_url:
                raise HTTPException(400, f"Question {idx}, answer {ai} is empty")


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


# ---------- routes: admin auth ----------

@app.get("/api/admin/status")
def admin_status(db: DbSession = Depends(get_db), me: m.User | None = Depends(auth.optional_admin)):
    return {
        "initialized": auth.admin_exists(db),
        "authenticated": me is not None,
        "username": me.username if me else None,
        "github_enabled": oauth.enabled(),
    }


# ---------- routes: GitHub OAuth login (UC-A-26) ----------

def _auth_error_redirect(message: str) -> RedirectResponse:
    return RedirectResponse(f"/?auth_error={quote(message)}", status_code=303)


@app.get("/api/auth/github/login")
def github_login():
    if not oauth.enabled():
        raise HTTPException(404, "GitHub login is not configured")
    return RedirectResponse(oauth.authorize_url(oauth.sign_state()), status_code=302)


@app.get("/api/auth/github/callback")
def github_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    db: DbSession = Depends(get_db),
):
    if not oauth.enabled():
        raise HTTPException(404, "GitHub login is not configured")
    if not code or not oauth.check_state(state):
        return _auth_error_redirect("GitHub sign-in failed — please try again")
    token = oauth.exchange_code(code)
    if not token:
        return _auth_error_redirect("GitHub sign-in failed — please try again")
    ghuser = oauth.fetch_user(token) or {}
    gid, login = ghuser.get("id"), ghuser.get("login")
    if not gid or not oauth.is_allowed(login or ""):
        return _auth_error_redirect("That GitHub account is not authorized for this server")
    user = db.scalar(select(m.User).where(m.User.github_id == gid))
    if user is None:
        user = _create_github_admin(db, gid, login)
    redirect = RedirectResponse("/", status_code=303)
    auth.issue_session(redirect, user.id, user.session_version, secure=request.url.scheme == "https")
    return redirect


def _create_github_admin(db: DbSession, gid: int, login: str | None) -> m.User:
    """Find-or-create the admin User for a GitHub id. Handles the insert race
    (another concurrent callback won) and a username collision with an
    existing local admin (fall back to a github-suffixed username)."""
    username = login or f"github-{gid}"
    user = m.User(username=username, github_id=gid, password_hash="")
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        winner = db.scalar(select(m.User).where(m.User.github_id == gid))
        if winner is not None:
            return winner
        # Username collided with a local admin — retry with a unique name.
        user = m.User(username=f"{username}-gh{gid}", github_id=gid, password_hash="")
        db.add(user)
        db.commit()
    db.refresh(user)
    return user


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
        try:
            username, password = _validate_credentials(
                payload.get("username", ""),
                payload.get("password", ""),
            )
        except HTTPException:
            log_diagnostic("auth.setup", outcome="invalid")
            raise
        user = m.User(username=username, password_hash=auth.hash_password(password))
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
        auth.issue_session(response, user.id, user.session_version, secure=request.url.scheme == "https")
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
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    user = db.scalar(select(m.User).where(m.User.username == username)) if username else None
    if not user or not auth.verify_password(password, user.password_hash):
        log_diagnostic("auth.login", outcome="failure")
        raise HTTPException(401, "Invalid username or password")
    limiter.reset(ip_key)
    auth.issue_session(response, user.id, user.session_version, secure=request.url.scheme == "https")
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
    current = payload.get("current_password") or ""
    new = payload.get("new_password") or ""
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
        raise HTTPException(400, f"new password must be at least {MIN_PASSWORD_LEN} characters")
    me.password_hash = auth.hash_password(new)
    # Bumping session_version invalidates every cookie issued under the old
    # version — anywhere the old password may have been stored stops working.
    me.session_version = (me.session_version or 1) + 1
    db.commit()
    auth.issue_session(response, me.id, me.session_version, secure=request.url.scheme == "https")
    log_diagnostic("auth.password_change", outcome="success", actor_id=me.id)
    return {"ok": True}


# ---------- routes: sessions ----------

@app.get("/api/sessions")
def list_sessions(db: DbSession = Depends(get_db), me: m.User = Depends(auth.current_admin)):
    rows = db.scalars(
        select(m.Session).where(m.Session.owner_user_id == me.id)
        .order_by(m.Session.created_at.desc())
    ).all()
    return [
        {
            "code": s.code,
            "title": s.title,
            "status": s.status,
            "mod_key": s.mod_key,
            "participant_base_url": s.participant_base_url,
            "created_at": s.created_at.isoformat(),
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "ended_at": s.ended_at.isoformat() if s.ended_at else None,
            "query_count": len(s.queries),
            "quiz_run_count": len(s.quiz_runs),
        }
        for s in rows
    ]


@app.post("/api/sessions")
def create_session(payload: dict, db: DbSession = Depends(get_db), me: m.User = Depends(auth.current_admin)):
    title = (payload.get("title") or "").strip()
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
    return {"code": s.code, "title": s.title, "mod_key": s.mod_key, "status": s.status}


@app.get("/api/sessions/{code}")
def get_session(code: str, db: DbSession = Depends(get_db)):
    s = get_session_by_code(db, code)
    return {
        "code": s.code,
        "title": s.title,
        "status": s.status,
        "created_at": s.created_at.isoformat(),
        "participant_base_url": s.participant_base_url,
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
        new_title = (payload.get("title") or "").strip()
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
    return {"code": s.code, "title": s.title, "status": s.status}


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
    url = (payload.get("url") or "").strip()
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
        s.status = "ended"
        s.ended_at = datetime.utcnow()
        db.commit()
        await broadcast_session(s, "session_state")
        log_diagnostic(
            "session.lifecycle",
            action="end",
            outcome="success",
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
    has_data = bool(s.queries) or bool(s.quiz_runs)
    if has_data:
        confirm_title = (payload or {}).get("confirm_title", "")
        if confirm_title != s.title:
            raise HTTPException(400, "Type the session title exactly to confirm deletion")
    session_code = s.code
    session_id = s.id
    db.delete(s)
    db.commit()
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
def session_presence(
    code: str,
    request: Request,
    response: Response,
    voter_token: Annotated[str | None, Cookie()] = None,
    db: DbSession = Depends(get_db),
):
    s = get_session_by_code(db, code)
    current_participant(s, request, response, voter_token, db)
    return {"online": participant_count_online(db, s)}


# ---------- routes: participant self ----------

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
    p = current_participant(s, request, response, voter_token, db)
    for field, max_len in PROFILE_FIELDS.items():
        if field in payload:
            setattr(p, field, normalize_optional_text(payload.get(field), max_len))
    if "photo_url" in payload:
        if normalize_optional_text(payload.get("photo_url"), 500) is not None:
            raise HTTPException(400, "photo must be uploaded")
        p.photo_url = None
    db.commit()
    db.refresh(p)
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
    p = current_participant(s, request, response, voter_token, db)
    p.photo_url = await store_uploaded_image(file, actor="participant_profile")
    db.commit()
    db.refresh(p)
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

def serialize_feedback(f: m.SessionFeedback, *, include_author: bool = False) -> dict:
    d = {
        "rating": f.rating,
        "went_well": f.went_well,
        "to_improve": f.to_improve,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
    }
    if include_author:
        d["author_name"] = f.participant.name if f.participant else None
    return d


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
    """Upsert the caller's feedback (one row per participant). Allowed in
    any session status — the feedback card is always available."""
    s = get_session_by_code(db, code)
    if not limiter.allow(f"fb:{_client_ip(request)}", *RL_FEEDBACK):
        raise HTTPException(429, "You're submitting feedback too fast — wait a moment and try again")
    rating = payload.get("rating")
    if not isinstance(rating, int) or isinstance(rating, bool) or rating < 1 or rating > 5:
        raise HTTPException(400, "rating must be an integer from 1 to 5")
    went_well = (payload.get("went_well") or "").strip()[:2000] or None
    to_improve = (payload.get("to_improve") or "").strip()[:2000] or None
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
        "items": [serialize_feedback(r, include_author=True) for r in rows],
    }


# ---------- routes: queries (the Q&A board) ----------

@app.get("/api/sessions/{code}/queries")
def list_queries(
    code: str,
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
    qs = db.scalars(
        select(m.Query)
        .where(m.Query.session_id == s.id)
        .options(selectinload(m.Query.votes), selectinload(m.Query.participant))
        .order_by(m.Query.created_at.desc())
    ).all()
    if not is_mod:
        qs = [q for q in qs if q.removed_at is None]
    return [serialize_query(q, p.id, is_mod) for q in qs]


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
    if not limiter.allow(f"ask:{_client_ip(request)}", *RL_ASK):
        raise HTTPException(429, "You're asking too fast — wait a moment and try again")
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text required")
    if len(text) > 1000:
        raise HTTPException(400, "text too long")
    p = current_participant(s, request, response, voter_token, db)
    if "author_name" in payload:
        nm = (payload.get("author_name") or "").strip()[:80] or None
        p.name = nm
    q = m.Query(session_id=s.id, text=text, participant_id=p.id)
    db.add(q)
    db.commit()
    db.refresh(q)
    db.refresh(q, ["votes", "participant"])
    await broadcast_session(s, "query_new")
    return serialize_query(q, p.id, False)


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
    if not limiter.allow(f"vote:{_client_ip(request)}", *RL_VOTE):
        raise HTTPException(429, "Too many votes — slow down and try again")
    q = db.get(m.Query, qid)
    if not q or q.session_id != s.id:
        raise HTTPException(404)
    if q.removed_at is not None:
        raise HTTPException(404)
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
        raise HTTPException(404)
    q.response_text = (payload.get("response_text") or "").strip() or None
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
        raise HTTPException(404)
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
        raise HTTPException(404)
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
    stmt = (
        select(m.Quiz)
        .where(m.Quiz.owner_user_id == me.id)
        .options(selectinload(m.Quiz.questions).selectinload(m.Question.answers))
        .order_by(m.Quiz.created_at.desc())
    )
    if ready_only:
        stmt = stmt.where(m.Quiz.status == "ready")
    quizzes = db.scalars(stmt).all()
    return [
        {"id": q.id, "title": q.title, "status": q.status, "question_count": len(q.questions)}
        for q in quizzes
    ]


@app.post("/api/quizzes")
def create_quiz(
    payload: dict,
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    title = (payload.get("title") or "").strip() or "Untitled quiz"
    quiz = m.Quiz(title=title, owner_user_id=me.id)
    db.add(quiz)
    db.commit()
    db.refresh(quiz)
    return {"id": quiz.id, "title": quiz.title, "status": quiz.status}


def _owned_quiz_or_404(db: DbSession, quiz_id: int, user: m.User) -> m.Quiz:
    quiz = db.get(m.Quiz, quiz_id)
    if not quiz or quiz.owner_user_id != user.id:
        raise HTTPException(404)
    return quiz


@app.get("/api/quizzes/{quiz_id}")
def get_quiz(
    quiz_id: int,
    include_correct: bool = False,
    db: DbSession = Depends(get_db),
    me: m.User | None = Depends(auth.optional_admin),
):
    quiz = db.get(m.Quiz, quiz_id)
    if not quiz:
        raise HTTPException(404)
    if not me or quiz.owner_user_id != me.id:
        raise HTTPException(404)
    return serialize_quiz(quiz, include_correct=include_correct)


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
        new_title = (str(payload["title"] or "")).strip() or quiz.title
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
    next_order = (max((qq.order_index for qq in quiz.questions), default=-1)) + 1
    qq = m.Question(
        quiz_id=quiz_id,
        text=(payload.get("text") or "").strip(),
        image_url=payload.get("image_url"),
        qtype=qtype,
        graded=bool(payload.get("graded", True)),
        order_index=payload.get("order_index", next_order),
    )
    db.add(qq)
    _mark_quiz_edited(quiz)
    db.commit()
    db.refresh(qq)
    return {"id": qq.id}


def _owned_quiz_question_or_404(db: DbSession, question_id: int, user: m.User) -> m.Question:
    qq = db.get(m.Question, question_id)
    if not qq or qq.quiz.owner_user_id != user.id:
        raise HTTPException(404)
    return qq


@app.patch("/api/quiz_questions/{question_id}")
def update_quiz_question(
    question_id: int,
    payload: dict,
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    qq = _owned_quiz_question_or_404(db, question_id, me)
    if "text" in payload:
        qq.text = str(payload["text"] or "").strip()
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
        try:
            qq.order_index = int(payload["order_index"])
        except (TypeError, ValueError):
            raise HTTPException(400, "order_index must be an integer")
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
    next_order = (max((a.order_index for a in qq.answers), default=-1)) + 1
    a = m.Answer(
        question_id=question_id,
        text=(payload.get("text") or "").strip(),
        image_url=payload.get("image_url"),
        is_correct=bool(payload.get("is_correct", False)),
        order_index=payload.get("order_index", next_order),
    )
    db.add(a)
    _mark_quiz_edited(qq.quiz)
    db.commit()
    db.refresh(a)
    return {"id": a.id}


def _owned_quiz_answer_or_404(db: DbSession, answer_id: int, user: m.User) -> m.Answer:
    a = db.get(m.Answer, answer_id)
    if not a or a.question.quiz.owner_user_id != user.id:
        raise HTTPException(404)
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
        a.text = str(payload["text"] or "").strip()
    if "image_url" in payload:
        v = payload["image_url"]
        a.image_url = str(v) if v else None
    if "is_correct" in payload:
        a.is_correct = bool(payload["is_correct"])
    if "order_index" in payload:
        try:
            a.order_index = int(payload["order_index"])
        except (TypeError, ValueError):
            raise HTTPException(400, "order_index must be an integer")
    qq = db.get(m.Question, a.question_id)
    _mark_quiz_edited(qq.quiz)
    db.commit()
    return {"ok": True}


@app.delete("/api/quiz_answers/{answer_id}")
def delete_quiz_answer(
    answer_id: int,
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    a = _owned_quiz_answer_or_404(db, answer_id, me)
    qq = db.get(m.Question, a.question_id)
    quiz = qq.quiz
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
        raise HTTPException(400, "unsupported image type")
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        log_diagnostic(
            "upload.reject",
            actor=actor,
            reason="size",
            size=file.size,
        )
        raise HTTPException(400, "max 5MB")
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
            raise HTTPException(400, "max 5MB")
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
    rows = db.scalars(
        select(m.QuizRun)
        .join(m.Session, m.QuizRun.session_id == m.Session.id)
        .where(m.Session.owner_user_id == me.id)
        .options(
            selectinload(m.QuizRun.session),
            selectinload(m.QuizRun.quiz_version).selectinload(m.QuizVersion.questions),
            selectinload(m.QuizRun.submissions),
        )
        .order_by(m.QuizRun.created_at.desc())
    ).all()
    out = []
    for r in rows:
        question_count = len(r.quiz_version.questions)
        respondents = len({sub.participant_id for sub in r.submissions})
        out.append({
            "id": r.id,
            "status": r.status,
            "session_code": r.session.code,
            "session_title": r.session.title,
            "quiz_id": r.quiz_version.quiz_id,
            "quiz_title": r.quiz_version.quiz_title,
            "version_no": r.quiz_version.version_no,
            "current_question_idx": r.current_question_idx,
            "question_count": question_count,
            "respondent_count": respondents,
            "created_at": r.created_at.isoformat(),
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "closed_at": r.closed_at.isoformat() if r.closed_at else None,
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
        raise HTTPException(404)
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
    voter_token: Annotated[str | None, Cookie()] = None,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
    me: m.User | None = Depends(auth.optional_admin),
):
    s = get_session_by_code(db, code)
    is_mod = is_mod_authed(s, x_mod_key) or is_admin_owner(s, me)
    p = current_participant(s, request, response, voter_token, db)
    rows = db.scalars(
        select(m.QuizRun).where(m.QuizRun.session_id == s.id)
        .order_by(m.QuizRun.created_at.desc())
    ).all()
    # Non-mods see queued/live/closed (queued powers the projector "Next up"
    # lobby). The participant page itself ignores queued in its own render.
    return [serialize_quiz_run(db, r, viewer_participant_id=p.id, is_mod=is_mod) for r in rows]


@app.get("/api/sessions/{code}/available_quizzes")
def list_available_quizzes(
    code: str,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
    me: m.User | None = Depends(auth.optional_admin),
):
    """Ready quizzes the session-owner can launch in this session.

    Same shape as `/api/quizzes?ready_only=true`, but gated on mod-or-owner
    auth so a delegate (mod-key holder, no admin account) can populate the
    Launch dropdown. Filters by `owner_user_id = session.owner_user_id`.
    """
    s = get_session_by_code(db, code)
    require_mod_or_owner(s, x_mod_key, me)
    quizzes = db.scalars(
        select(m.Quiz)
        .where(m.Quiz.owner_user_id == s.owner_user_id, m.Quiz.status == "ready")
        .options(selectinload(m.Quiz.questions))
        .order_by(m.Quiz.created_at.desc())
    ).all()
    return [
        {"id": q.id, "title": q.title, "status": q.status, "question_count": len(q.questions)}
        for q in quizzes
    ]


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
        raise HTTPException(404, "quiz not found")
    if quiz.status != "ready":
        raise HTTPException(400, "Quiz is still a draft — publish it first")
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
        raise HTTPException(404)
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
    if s.status == "planning":
        s.status = "live"
        s.started_at = datetime.utcnow()
    run.status = "live"
    run.current_question_idx = 0
    run.reveal_current = False
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
    log_diagnostic(
        "quiz_run.lifecycle",
        action="start",
        outcome="success",
        session_id=s.id,
        session_code=s.code,
        run_id=run.id,
    )
    return {"ok": True}


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
    elif direction == "to" and "index" in payload:
        try:
            idx = int(payload["index"])
        except (TypeError, ValueError):
            raise HTTPException(400, "index must be an integer")
        run.current_question_idx = max(0, min(idx, max(total - 1, 0)))
    run.reveal_current = False
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
        raise HTTPException(404)
    if not is_mod and run.status not in ("live", "closed"):
        raise HTTPException(404)
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
    if not limiter.allow(f"submit:{_client_ip(request)}", *RL_SUBMIT):
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


# ---------- websocket ----------

@app.websocket("/ws/sessions/{code}")
async def ws_session(ws: WebSocket, code: str):
    origin = ws.headers.get("origin")
    if origin:
        host = ws.headers.get("host", "")
        if origin not in (f"http://{host}", f"https://{host}"):
            log_diagnostic("ws.reject", outcome="failure", reason="origin")
            await ws.close(code=4403)
            return
    with SessionLocal() as db:
        s = db.scalar(select(m.Session).where(m.Session.code == code.upper()))
        if not s:
            log_diagnostic("ws.reject", outcome="failure", reason="session")
            await ws.close(code=4404)
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
            await ws.receive_text()
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
