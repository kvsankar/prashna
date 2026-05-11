"""Prashna — live Q&A + quiz tool for training sessions."""
from __future__ import annotations

import os
import secrets
import uuid
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated

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
from contextlib import asynccontextmanager
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession, selectinload
from starlette.middleware.base import BaseHTTPMiddleware

from .db import SessionLocal, get_db, init_db
from . import models as m
from . import auth
from .ws import hub

BASE = Path(__file__).resolve().parent.parent
STATIC = BASE / "static"
UPLOADS = Path(os.environ.get("PRASHNA_UPLOADS_DIR") or (BASE / "uploads"))
UPLOADS.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
PRESENCE_WINDOW = timedelta(seconds=30)
# Throttle last_seen_at writes — SQLite is single-writer; updating per request
# bottlenecks under load. Idle polls touch the row at most once per this window.
LAST_SEEN_THROTTLE = timedelta(seconds=5)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Prashna", lifespan=lifespan)


class UploadsSecurityHeaders(BaseHTTPMiddleware):
    """Defense-in-depth headers for user-uploaded files."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/uploads/"):
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
            response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        return response


app.add_middleware(UploadsSecurityHeaders)


app.mount("/uploads", StaticFiles(directory=UPLOADS), name="uploads")
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


def require_mod(session: m.Session, mod_key: str | None) -> None:
    if not mod_key or not secrets.compare_digest(mod_key, session.mod_key):
        raise HTTPException(403, "Moderator key required")


def require_session_owner(session: m.Session, user: m.User) -> None:
    if session.owner_user_id != user.id:
        raise HTTPException(403, "Not your session")


def require_quiz_owner(quiz: m.Quiz, user: m.User) -> None:
    if quiz.owner_user_id != user.id:
        raise HTTPException(403, "Not your quiz")


def current_participant(
    session: m.Session,
    request: Request,
    response: Response,
    voter_token: str | None,
    db: DbSession,
) -> m.Participant:
    """Resolve the participant for this (session, voter_token) tuple. Create if missing.

    Updates last_seen_at as a side effect — this drives the live presence count.
    Issues the voter_token cookie when a fresh token is minted.
    """
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
        p = m.Participant(session_id=session.id, voter_token=token)
        db.add(p)
        db.commit()
        db.refresh(p)
    else:
        # Throttle: skip the write if last_seen_at is fresh enough already.
        now = datetime.utcnow()
        if now - p.last_seen_at >= LAST_SEEN_THROTTLE:
            p.last_seen_at = now
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

def serialize_question(q: m.Question, viewer_participant_id: int | None, is_mod: bool) -> dict:
    return {
        "id": q.id,
        "text": q.text,
        "author_name": q.participant.name if q.participant else None,
        "answer_text": q.answer_text,
        "answered": q.answered_at is not None,
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
        "items": [
            {
                "id": it.id,
                "text": it.text,
                "image_url": it.image_url,
                "qtype": it.qtype,
                "order_index": it.order_index,
                "options": [
                    {
                        "id": op.id,
                        "text": op.text,
                        "image_url": op.image_url,
                        "order_index": op.order_index,
                        **({"is_correct": op.is_correct} if include_correct else {}),
                    }
                    for op in it.options
                ],
            }
            for it in quiz.items
        ],
    }


def tally_item(db: DbSession, run: m.QuizRun, vitem: m.QuizVersionItem) -> dict:
    rows = db.scalars(
        select(m.QuizResponse).where(
            m.QuizResponse.quiz_run_id == run.id,
            m.QuizResponse.item_id == vitem.id,
        )
    ).all()
    counts = Counter(r.option_id for r in rows)
    voters = {r.participant_id for r in rows}
    return {
        "item_id": vitem.id,
        "respondents": len(voters),
        "totals": {op.id: counts.get(op.id, 0) for op in vitem.options},
    }


def serialize_quiz_run(
    db: DbSession,
    run: m.QuizRun,
    *,
    viewer_participant_id: int | None,
    is_mod: bool,
) -> dict:
    version = run.quiz_version
    items = version.items
    current = items[run.current_item_idx] if 0 <= run.current_item_idx < len(items) else None
    show_correct = is_mod or (run.status == "closed") or run.reveal_current
    payload = {
        "id": run.id,
        "session_id": run.session_id,
        "quiz_version_id": version.id,
        "quiz_id": version.quiz_id,
        "quiz_title": version.quiz_title,
        "version_no": version.version_no,
        "status": run.status,
        "current_item_idx": run.current_item_idx,
        "item_count": len(items),
        "reveal_current": run.reveal_current,
        "current_item": None,
        "my_selections": [],
        "results": None,
    }
    if current is not None:
        payload["current_item"] = {
            "id": current.id,
            "text": current.text,
            "image_url": current.image_url,
            "qtype": current.qtype,
            "options": [
                {
                    "id": op.id,
                    "text": op.text,
                    "image_url": op.image_url,
                    **({"is_correct": op.is_correct} if show_correct else {}),
                }
                for op in current.options
            ],
        }
        if viewer_participant_id is not None:
            mine = db.scalars(
                select(m.QuizResponse).where(
                    m.QuizResponse.quiz_run_id == run.id,
                    m.QuizResponse.item_id == current.id,
                    m.QuizResponse.participant_id == viewer_participant_id,
                )
            ).all()
            payload["my_selections"] = [r.option_id for r in mine]
        if is_mod or run.reveal_current or run.status == "closed":
            payload["results"] = tally_item(db, run, current)
    return payload


# ---------- quiz lifecycle helpers ----------

def _validate_quiz_publishable(quiz: m.Quiz) -> None:
    if not quiz.items:
        raise HTTPException(400, "Quiz needs at least one item")
    for idx, it in enumerate(quiz.items, start=1):
        if not it.text.strip():
            raise HTTPException(400, f"Item {idx} is missing text")
        if len(it.options) < 2:
            raise HTTPException(400, f"Item {idx} needs at least 2 options")
        correct = [op for op in it.options if op.is_correct]
        if it.qtype == "single" and len(correct) != 1:
            raise HTTPException(400, f"Item {idx} (single choice) needs exactly one correct option")
        if it.qtype == "multi" and len(correct) < 1:
            raise HTTPException(400, f"Item {idx} (multiple choice) needs at least one correct option")
        for opi, op in enumerate(it.options, start=1):
            if not op.text.strip() and not op.image_url:
                raise HTTPException(400, f"Item {idx}, option {opi} is empty")


def _mark_quiz_edited(quiz: m.Quiz) -> None:
    quiz.last_edited_at = datetime.utcnow()


def _latest_version(db: DbSession, quiz: m.Quiz) -> m.QuizVersion | None:
    return db.scalar(
        select(m.QuizVersion).where(m.QuizVersion.quiz_id == quiz.id)
        .order_by(m.QuizVersion.version_no.desc())
    )


def _ensure_current_version(db: DbSession, quiz: m.Quiz) -> m.QuizVersion:
    """Return the version that captures the quiz's current editable tree.

    Creates a new version only if the editable tree has been touched since the
    latest version was captured. Race-safe: if two requests both try to create
    version N+1, the UNIQUE(quiz_id, version_no) constraint causes one to
    fail; we catch and return the winner's version.
    """
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
    for it in quiz.items:
        vit = m.QuizVersionItem(
            version_id=version.id,
            text=it.text,
            image_url=it.image_url,
            qtype=it.qtype,
            order_index=it.order_index,
        )
        db.add(vit)
        db.flush()
        for op in it.options:
            db.add(m.QuizVersionOption(
                item_id=vit.id,
                text=op.text,
                image_url=op.image_url,
                is_correct=op.is_correct,
                order_index=op.order_index,
            ))
    db.commit()
    db.refresh(version)
    return version


# ---------- broadcast ----------

async def broadcast_session(session: m.Session, kind: str = "update") -> None:
    await hub.broadcast(f"session:{session.code}", {"type": kind})


# ---------- routes: pages ----------

@app.get("/")
def root():
    return FileResponse(STATIC / "index.html")


def _session_exists(code: str, db: DbSession) -> bool:
    return bool(db.scalar(select(m.Session.id).where(m.Session.code == code.upper())))


def _bad_code_redirect(code: str) -> RedirectResponse:
    return RedirectResponse(url=f"/?bad_code={code}", status_code=303)


@app.get("/s/{code}")
def participant_page(code: str, db: DbSession = Depends(get_db)):
    if not _session_exists(code, db):
        return _bad_code_redirect(code)
    return FileResponse(STATIC / "participant.html")


@app.get("/m/{code}")
def moderator_page(code: str, db: DbSession = Depends(get_db)):
    if not _session_exists(code, db):
        return _bad_code_redirect(code)
    return FileResponse(STATIC / "moderator.html")


@app.get("/p/{code}")
def projector_page(code: str, db: DbSession = Depends(get_db)):
    if not _session_exists(code, db):
        return _bad_code_redirect(code)
    return FileResponse(STATIC / "projector.html")


@app.get("/quizzes")
def quizzes_page():
    return FileResponse(STATIC / "quizzes.html")


# ---------- routes: admin auth ----------

@app.get("/api/admin/status")
def admin_status(db: DbSession = Depends(get_db), me: m.User | None = Depends(auth.optional_admin)):
    return {
        "initialized": auth.admin_exists(db),
        "authenticated": me is not None,
        "username": me.username if me else None,
    }


@app.post("/api/admin/setup")
def admin_setup(payload: dict, request: Request, response: Response, db: DbSession = Depends(get_db)):
    if auth.admin_exists(db):
        raise HTTPException(409, "Admin already initialized")
    username, password = _validate_credentials(payload.get("username", ""), payload.get("password", ""))
    user = m.User(username=username, password_hash=auth.hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    auth.issue_session(response, user.id, secure=request.url.scheme == "https")
    return {"username": user.username}


@app.post("/api/admin/login")
def admin_login(payload: dict, request: Request, response: Response, db: DbSession = Depends(get_db)):
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    user = db.scalar(select(m.User).where(m.User.username == username)) if username else None
    if not user or not auth.verify_password(password, user.password_hash):
        raise HTTPException(401, "Invalid username or password")
    auth.issue_session(response, user.id, secure=request.url.scheme == "https")
    return {"username": user.username}


@app.post("/api/admin/logout")
def admin_logout(response: Response):
    auth.clear_session(response)
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
            "created_at": s.created_at.isoformat(),
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "ended_at": s.ended_at.isoformat() if s.ended_at else None,
            "question_count": len(s.questions),
            "quiz_run_count": len(s.quiz_runs),
        }
        for s in rows
    ]


@app.post("/api/sessions")
def create_session(payload: dict, db: DbSession = Depends(get_db), me: m.User = Depends(auth.current_admin)):
    title = (payload.get("title") or "").strip() or "Untitled session"
    code = gen_code()
    while db.scalar(select(m.Session).where(m.Session.code == code)):
        code = gen_code()
    s = m.Session(code=code, title=title, mod_key=gen_token()[:16], owner_user_id=me.id)
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"code": s.code, "title": s.title, "mod_key": s.mod_key, "status": s.status}


@app.get("/api/sessions/{code}")
def get_session(code: str, db: DbSession = Depends(get_db)):
    s = get_session_by_code(db, code)
    return {
        "code": s.code,
        "title": s.title,
        "status": s.status,
        "created_at": s.created_at.isoformat(),
    }


@app.post("/api/sessions/{code}/start")
async def start_session(
    code: str,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
):
    s = get_session_by_code(db, code)
    require_mod(s, x_mod_key)
    if s.status == "ended":
        raise HTTPException(400, "Session has ended")
    if s.status == "planning":
        s.status = "live"
        s.started_at = datetime.utcnow()
        db.commit()
        await broadcast_session(s, "session_state")
    return {"status": s.status}


@app.post("/api/sessions/{code}/end")
async def end_session(
    code: str,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
):
    s = get_session_by_code(db, code)
    require_mod(s, x_mod_key)
    if s.status != "ended":
        s.status = "ended"
        s.ended_at = datetime.utcnow()
        db.commit()
        await broadcast_session(s, "session_state")
    return {"status": s.status}


@app.get("/api/sessions/{code}/presence")
def session_presence(
    code: str,
    request: Request,
    response: Response,
    voter_token: Annotated[str | None, Cookie()] = None,
    db: DbSession = Depends(get_db),
):
    s = get_session_by_code(db, code)
    # Touch the participant row so the counter reflects this caller too.
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
    return {"id": p.id, "name": p.name}


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
    if "name" in payload:
        new_name = (payload.get("name") or "").strip()[:80] or None
        p.name = new_name
    db.commit()
    db.refresh(p)
    await broadcast_session(s, "participant")
    return {"id": p.id, "name": p.name}


# ---------- routes: questions (Q&A) ----------

@app.get("/api/sessions/{code}/questions")
def list_questions(
    code: str,
    request: Request,
    response: Response,
    voter_token: Annotated[str | None, Cookie()] = None,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
):
    s = get_session_by_code(db, code)
    is_mod = bool(x_mod_key) and secrets.compare_digest(x_mod_key, s.mod_key)
    p = current_participant(s, request, response, voter_token, db)
    qs = db.scalars(
        select(m.Question)
        .where(m.Question.session_id == s.id)
        .options(selectinload(m.Question.votes), selectinload(m.Question.participant))
        .order_by(m.Question.created_at.desc())
    ).all()
    if not is_mod:
        qs = [q for q in qs if q.removed_at is None]
    return [serialize_question(q, p.id, is_mod) for q in qs]


@app.post("/api/sessions/{code}/questions")
async def create_question(
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
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text required")
    if len(text) > 1000:
        raise HTTPException(400, "text too long")
    p = current_participant(s, request, response, voter_token, db)
    # Allow the participant to set their name in the same call.
    if "author_name" in payload:
        nm = (payload.get("author_name") or "").strip()[:80] or None
        p.name = nm
    q = m.Question(session_id=s.id, text=text, participant_id=p.id)
    db.add(q)
    db.commit()
    db.refresh(q)
    db.refresh(q, ["votes", "participant"])
    await broadcast_session(s, "question_new")
    return serialize_question(q, p.id, False)


@app.post("/api/sessions/{code}/questions/{qid}/vote")
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
    q = db.get(m.Question, qid)
    if not q or q.session_id != s.id:
        raise HTTPException(404)
    if q.removed_at is not None:
        raise HTTPException(404)  # invisible to participants
    p = current_participant(s, request, response, voter_token, db)
    existing = db.scalar(
        select(m.QuestionVote).where(
            m.QuestionVote.question_id == qid,
            m.QuestionVote.participant_id == p.id,
        )
    )
    if existing:
        db.delete(existing)
        voted = False
    else:
        db.add(m.QuestionVote(question_id=qid, participant_id=p.id))
        voted = True
    db.commit()
    db.refresh(q, ["votes"])
    await broadcast_session(s, "question_vote")
    return {"voted": voted, "vote_count": len(q.votes)}


@app.post("/api/sessions/{code}/questions/{qid}/answer")
async def answer_question(
    code: str,
    qid: int,
    payload: dict,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
):
    s = get_session_by_code(db, code)
    require_mod(s, x_mod_key)
    q = db.get(m.Question, qid)
    if not q or q.session_id != s.id:
        raise HTTPException(404)
    q.answer_text = (payload.get("answer_text") or "").strip() or None
    q.answered_at = datetime.utcnow() if payload.get("answered", True) else None
    db.commit()
    await broadcast_session(s, "question_answered")
    return {"ok": True}


@app.post("/api/sessions/{code}/questions/{qid}/remove")
async def remove_question(
    code: str,
    qid: int,
    payload: dict,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
):
    """Soft-remove: hides from participants but keeps the row for audit."""
    s = get_session_by_code(db, code)
    require_mod(s, x_mod_key)
    q = db.get(m.Question, qid)
    if not q or q.session_id != s.id:
        raise HTTPException(404)
    if payload.get("removed", True):
        q.removed_at = datetime.utcnow()
    else:
        q.removed_at = None
    db.commit()
    await broadcast_session(s, "question_removed")
    return {"ok": True}


@app.delete("/api/sessions/{code}/questions/{qid}")
async def delete_question(
    code: str,
    qid: int,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
):
    """Hard delete: admin escape hatch. Not on the standard moderator UI."""
    s = get_session_by_code(db, code)
    require_mod(s, x_mod_key)
    q = db.get(m.Question, qid)
    if not q or q.session_id != s.id:
        raise HTTPException(404)
    db.delete(q)
    db.commit()
    await broadcast_session(s, "question_deleted")
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
        .options(selectinload(m.Quiz.items).selectinload(m.QuizItem.options))
        .order_by(m.Quiz.created_at.desc())
    )
    if ready_only:
        stmt = stmt.where(m.Quiz.status == "ready")
    quizzes = db.scalars(stmt).all()
    return [
        {"id": q.id, "title": q.title, "status": q.status, "item_count": len(q.items)}
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
    # Only the owner can read the template at all.
    if not me or quiz.owner_user_id != me.id:
        raise HTTPException(404)
    payload = serialize_quiz(quiz, include_correct=include_correct)
    return payload


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
    # Preserve session data: refuse to delete if any version has been used in a run.
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


@app.post("/api/quizzes/{quiz_id}/items")
def add_quiz_item(
    quiz_id: int,
    payload: dict,
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    quiz = _owned_quiz_or_404(db, quiz_id, me)
    qtype = payload.get("qtype", "single")
    if qtype not in ("single", "multi"):
        raise HTTPException(400, "qtype must be single or multi")
    next_order = (max((it.order_index for it in quiz.items), default=-1)) + 1
    it = m.QuizItem(
        quiz_id=quiz_id,
        text=(payload.get("text") or "").strip(),
        image_url=payload.get("image_url"),
        qtype=qtype,
        order_index=payload.get("order_index", next_order),
    )
    db.add(it)
    _mark_quiz_edited(quiz)
    db.commit()
    db.refresh(it)
    return {"id": it.id}


def _owned_quiz_item_or_404(db: DbSession, item_id: int, user: m.User) -> m.QuizItem:
    it = db.get(m.QuizItem, item_id)
    if not it or it.quiz.owner_user_id != user.id:
        raise HTTPException(404)
    return it


@app.patch("/api/quiz_items/{item_id}")
def update_quiz_item(
    item_id: int,
    payload: dict,
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    it = _owned_quiz_item_or_404(db, item_id, me)
    if "text" in payload:
        it.text = str(payload["text"] or "").strip()
    if "image_url" in payload:
        v = payload["image_url"]
        it.image_url = str(v) if v else None
    if "qtype" in payload:
        if payload["qtype"] not in ("single", "multi"):
            raise HTTPException(400, "qtype must be single or multi")
        it.qtype = payload["qtype"]
    if "order_index" in payload:
        try:
            it.order_index = int(payload["order_index"])
        except (TypeError, ValueError):
            raise HTTPException(400, "order_index must be an integer")
    _mark_quiz_edited(it.quiz)
    db.commit()
    return {"ok": True}


@app.delete("/api/quiz_items/{item_id}")
def delete_quiz_item(
    item_id: int,
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    it = _owned_quiz_item_or_404(db, item_id, me)
    quiz = it.quiz
    db.delete(it)
    _mark_quiz_edited(quiz)
    db.commit()
    return {"ok": True}


@app.post("/api/quiz_items/{item_id}/options")
def add_quiz_option(
    item_id: int,
    payload: dict,
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    it = _owned_quiz_item_or_404(db, item_id, me)
    next_order = (max((op.order_index for op in it.options), default=-1)) + 1
    op = m.QuizOption(
        item_id=item_id,
        text=(payload.get("text") or "").strip(),
        image_url=payload.get("image_url"),
        is_correct=bool(payload.get("is_correct", False)),
        order_index=payload.get("order_index", next_order),
    )
    db.add(op)
    _mark_quiz_edited(it.quiz)
    db.commit()
    db.refresh(op)
    return {"id": op.id}


def _owned_quiz_option_or_404(db: DbSession, op_id: int, user: m.User) -> m.QuizOption:
    op = db.get(m.QuizOption, op_id)
    if not op or op.item.quiz.owner_user_id != user.id:
        raise HTTPException(404)
    return op


@app.patch("/api/quiz_options/{op_id}")
def update_quiz_option(
    op_id: int,
    payload: dict,
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    op = _owned_quiz_option_or_404(db, op_id, me)
    if "text" in payload:
        op.text = str(payload["text"] or "").strip()
    if "image_url" in payload:
        v = payload["image_url"]
        op.image_url = str(v) if v else None
    if "is_correct" in payload:
        op.is_correct = bool(payload["is_correct"])
    if "order_index" in payload:
        try:
            op.order_index = int(payload["order_index"])
        except (TypeError, ValueError):
            raise HTTPException(400, "order_index must be an integer")
    _mark_quiz_edited(op.item.quiz)
    db.commit()
    return {"ok": True}


@app.delete("/api/quiz_options/{op_id}")
def delete_quiz_option(
    op_id: int,
    db: DbSession = Depends(get_db),
    me: m.User = Depends(auth.current_admin),
):
    op = _owned_quiz_option_or_404(db, op_id, me)
    quiz = op.item.quiz
    db.delete(op)
    _mark_quiz_edited(quiz)
    db.commit()
    return {"ok": True}


# ---------- routes: uploads ----------

@app.post("/api/uploads")
async def upload_image(
    file: UploadFile = File(...),
    _admin: m.User = Depends(auth.current_admin),
):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTS:
        raise HTTPException(400, "unsupported image type")
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "max 5MB")
    buf = bytearray()
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > MAX_UPLOAD_BYTES:
            raise HTTPException(400, "max 5MB")
    name = f"{uuid.uuid4().hex}{ext}"
    (UPLOADS / name).write_bytes(bytes(buf))
    return {"url": f"/uploads/{name}"}


# ---------- routes: quiz runs (was quiz_sessions) ----------

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
            selectinload(m.QuizRun.quiz_version).selectinload(m.QuizVersion.items),
            selectinload(m.QuizRun.responses),
        )
        .order_by(m.QuizRun.created_at.desc())
    ).all()
    out = []
    for r in rows:
        item_count = len(r.quiz_version.items)
        respondents = len({rsp.participant_id for rsp in r.responses})
        out.append({
            "id": r.id,
            "status": r.status,
            "session_code": r.session.code,
            "session_title": r.session.title,
            "quiz_id": r.quiz_version.quiz_id,
            "quiz_title": r.quiz_version.quiz_title,
            "version_no": r.quiz_version.version_no,
            "current_item_idx": r.current_item_idx,
            "item_count": item_count,
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
    items = []
    for vit in version.items:
        tally = tally_item(db, run, vit)
        items.append({
            "id": vit.id,
            "text": vit.text,
            "image_url": vit.image_url,
            "qtype": vit.qtype,
            "options": [
                {
                    "id": op.id,
                    "text": op.text,
                    "image_url": op.image_url,
                    "is_correct": op.is_correct,
                    "count": tally["totals"].get(op.id, 0),
                }
                for op in vit.options
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
        "current_item_idx": run.current_item_idx,
        "items": items,
    }


@app.get("/api/sessions/{code}/quiz_runs")
def list_quiz_runs(
    code: str,
    request: Request,
    response: Response,
    voter_token: Annotated[str | None, Cookie()] = None,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
):
    s = get_session_by_code(db, code)
    is_mod = bool(x_mod_key) and secrets.compare_digest(x_mod_key, s.mod_key)
    p = current_participant(s, request, response, voter_token, db)
    rows = db.scalars(
        select(m.QuizRun).where(m.QuizRun.session_id == s.id)
        .order_by(m.QuizRun.created_at.desc())
    ).all()
    if not is_mod:
        rows = [r for r in rows if r.status in ("live", "closed")]
    return [serialize_quiz_run(db, r, viewer_participant_id=p.id, is_mod=is_mod) for r in rows]


@app.post("/api/sessions/{code}/quiz_runs")
async def create_quiz_run(
    code: str,
    payload: dict,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
):
    """Queue a quiz onto a session.

    Creates a QuizVersion lazily if the Quiz has been edited since the latest version,
    then creates a QuizRun (status=queued) pointing at that version.
    """
    s = get_session_by_code(db, code)
    require_mod(s, x_mod_key)
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
    return {"id": run.id, "version_no": version.version_no, "status": run.status}


def _get_run_mod(db: DbSession, code: str, run_id: int, mod_key: str | None) -> tuple[m.Session, m.QuizRun]:
    s = get_session_by_code(db, code)
    require_mod(s, mod_key)
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
):
    s, run = _get_run_mod(db, code, run_id, x_mod_key)
    if run.status != "queued":
        raise HTTPException(400, f"Cannot start from status: {run.status}")
    # Auto-advance Session: planning → live the first time a quiz starts.
    if s.status == "planning":
        s.status = "live"
        s.started_at = datetime.utcnow()
    run.status = "live"
    run.current_item_idx = 0
    run.reveal_current = False
    run.started_at = datetime.utcnow()
    # "At most one live run per session" is enforced by a partial unique index
    # (uq_session_live_run). If a concurrent Start already won, the commit
    # below raises IntegrityError; we surface 409.
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Another quiz is already live — close it first.")
    await broadcast_session(s, "quiz_run_update")
    return {"ok": True}


@app.post("/api/sessions/{code}/quiz_runs/{run_id}/advance")
async def advance_quiz_run(
    code: str,
    run_id: int,
    payload: dict,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
):
    s, run = _get_run_mod(db, code, run_id, x_mod_key)
    direction = payload.get("direction", "next")
    total = len(run.quiz_version.items)
    if direction == "next":
        run.current_item_idx = min(run.current_item_idx + 1, max(total - 1, 0))
    elif direction == "prev":
        run.current_item_idx = max(run.current_item_idx - 1, 0)
    elif direction == "to" and "index" in payload:
        try:
            idx = int(payload["index"])
        except (TypeError, ValueError):
            raise HTTPException(400, "index must be an integer")
        run.current_item_idx = max(0, min(idx, max(total - 1, 0)))
    run.reveal_current = False
    db.commit()
    await broadcast_session(s, "quiz_run_update")
    return {"ok": True}


@app.post("/api/sessions/{code}/quiz_runs/{run_id}/reveal")
async def reveal_quiz_run(
    code: str,
    run_id: int,
    payload: dict,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
):
    s, run = _get_run_mod(db, code, run_id, x_mod_key)
    run.reveal_current = bool(payload.get("reveal", True))
    db.commit()
    await broadcast_session(s, "quiz_run_update")
    return {"ok": True}


@app.post("/api/sessions/{code}/quiz_runs/{run_id}/close")
async def close_quiz_run(
    code: str,
    run_id: int,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
):
    s, run = _get_run_mod(db, code, run_id, x_mod_key)
    run.status = "closed"
    run.reveal_current = True
    run.closed_at = datetime.utcnow()
    db.commit()
    await broadcast_session(s, "quiz_run_update")
    return {"ok": True}


@app.delete("/api/sessions/{code}/quiz_runs/{run_id}")
async def delete_quiz_run(
    code: str,
    run_id: int,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
):
    s, run = _get_run_mod(db, code, run_id, x_mod_key)
    if run.status == "closed":
        raise HTTPException(400, "Closed quiz runs are historical and cannot be deleted")
    db.delete(run)
    db.commit()
    await broadcast_session(s, "quiz_run_deleted")
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
):
    s = get_session_by_code(db, code)
    is_mod = bool(x_mod_key) and secrets.compare_digest(x_mod_key, s.mod_key)
    p = current_participant(s, request, response, voter_token, db)
    run = db.get(m.QuizRun, run_id)
    if not run or run.session_id != s.id:
        raise HTTPException(404)
    if not is_mod and run.status not in ("live", "closed"):
        raise HTTPException(404)
    return serialize_quiz_run(db, run, viewer_participant_id=p.id, is_mod=is_mod)


@app.post("/api/sessions/{code}/quiz_runs/{run_id}/respond")
async def respond_quiz_run(
    code: str,
    run_id: int,
    payload: dict,
    request: Request,
    response: Response,
    voter_token: Annotated[str | None, Cookie()] = None,
    db: DbSession = Depends(get_db),
):
    s = get_session_by_code(db, code)
    if s.status == "ended":
        raise HTTPException(400, "Session has ended")
    run = db.get(m.QuizRun, run_id)
    if not run or run.session_id != s.id or run.status != "live":
        raise HTTPException(404, "Quiz not live")
    item_id = payload.get("item_id")
    option_ids_raw = payload.get("option_ids") or []
    if not isinstance(option_ids_raw, list):
        raise HTTPException(400, "option_ids must be a list")
    try:
        option_ids = [int(o) for o in option_ids_raw]
    except (TypeError, ValueError):
        raise HTTPException(400, "option_ids must be integers")
    vit = db.get(m.QuizVersionItem, item_id)
    if not vit or vit.version_id != run.quiz_version_id:
        raise HTTPException(404, "Item not in this quiz run")
    items = run.quiz_version.items
    if items[run.current_item_idx].id != vit.id:
        raise HTTPException(400, "Not the current item")
    if vit.qtype == "single" and len(option_ids) > 1:
        raise HTTPException(400, "Only one option allowed")
    valid_option_ids = {op.id for op in vit.options}
    if any(oid not in valid_option_ids for oid in option_ids):
        raise HTTPException(400, "Invalid option")
    p = current_participant(s, request, response, voter_token, db)
    # Clear existing responses by this participant for this item.
    existing = db.scalars(
        select(m.QuizResponse).where(
            m.QuizResponse.quiz_run_id == run.id,
            m.QuizResponse.item_id == vit.id,
            m.QuizResponse.participant_id == p.id,
        )
    ).all()
    for r in existing:
        db.delete(r)
    for oid in option_ids:
        db.add(m.QuizResponse(
            quiz_run_id=run.id,
            item_id=vit.id,
            option_id=oid,
            participant_id=p.id,
        ))
    db.commit()
    await broadcast_session(s, "quiz_response")
    return {"ok": True}


# ---------- websocket ----------

@app.websocket("/ws/sessions/{code}")
async def ws_session(ws: WebSocket, code: str):
    origin = ws.headers.get("origin")
    if origin:
        host = ws.headers.get("host", "")
        if origin not in (f"http://{host}", f"https://{host}"):
            await ws.close(code=4403)
            return
    with SessionLocal() as db:
        s = db.scalar(select(m.Session).where(m.Session.code == code.upper()))
        if not s:
            await ws.close(code=4404)
            return
    room = f"session:{code.upper()}"
    await hub.join(room, ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.leave(room, ws)
    except Exception:
        hub.leave(room, ws)
