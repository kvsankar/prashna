"""Prashna — live Q&A + quiz tool for training sessions."""
from __future__ import annotations

import secrets
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    File,
    Form,
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
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession, selectinload
from starlette.middleware.base import BaseHTTPMiddleware

from .db import SessionLocal, get_db, init_db
from . import models as m
from . import auth
from .ws import hub

BASE = Path(__file__).resolve().parent.parent
STATIC = BASE / "static"
UPLOADS = BASE / "uploads"
UPLOADS.mkdir(exist_ok=True)
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

app = FastAPI(title="Prashna")


class UploadsSecurityHeaders(BaseHTTPMiddleware):
    """Defense-in-depth headers for user-uploaded files.

    Prevents content-type sniffing and disables script execution for any
    file served from /uploads/ — so a file that slips past extension
    checks cannot execute in the app's origin.
    """

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/uploads/"):
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
            response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        return response


app.add_middleware(UploadsSecurityHeaders)


@app.on_event("startup")
def _startup() -> None:
    init_db()


app.mount("/uploads", StaticFiles(directory=UPLOADS), name="uploads")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


# ---------- helpers ----------

def gen_code(n: int = 6) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(n))


def gen_token() -> str:
    return uuid.uuid4().hex


def ensure_voter_token(token: str | None, request: Request, response: Response) -> str:
    if token:
        return token
    token = gen_token()
    # Secure only when the request actually arrived over HTTPS, so local
    # `uvicorn --reload` over plain HTTP still works in dev.
    secure = request.url.scheme == "https"
    response.set_cookie(
        "voter_token",
        token,
        max_age=60 * 60 * 24 * 365,
        httponly=False,  # non-HttpOnly is intentional — see CLAUDE.md
        samesite="lax",
        secure=secure,
    )
    return token


def get_session_by_code(db: DbSession, code: str) -> m.Session:
    s = db.scalar(select(m.Session).where(m.Session.code == code.upper()))
    if not s:
        raise HTTPException(404, "Session not found")
    return s


def require_mod(session: m.Session, mod_key: str | None) -> None:
    if not mod_key or not secrets.compare_digest(mod_key, session.mod_key):
        raise HTTPException(403, "Moderator key required")


MIN_PASSWORD_LEN = 8
MAX_USERNAME_LEN = 80


def _validate_credentials(username: str, password: str) -> tuple[str, str]:
    u = (username or "").strip()
    if not u or len(u) > MAX_USERNAME_LEN:
        raise HTTPException(400, "username required")
    if not password or len(password) < MIN_PASSWORD_LEN:
        raise HTTPException(400, f"password must be at least {MIN_PASSWORD_LEN} characters")
    return u, password


# ---------- serialization ----------

def serialize_question(q: m.Question, voter_token: str, is_mod: bool) -> dict:
    return {
        "id": q.id,
        "text": q.text,
        "author_name": q.author_name,
        "answer_text": q.answer_text,
        "answered": q.answered_at is not None,
        "hidden": q.hidden,
        "vote_count": len(q.votes),
        "voted": any(v.voter_token == voter_token for v in q.votes),
        "mine": q.author_token == voter_token,
        "created_at": q.created_at.isoformat(),
        **({"author_token": q.author_token} if is_mod else {}),
    }


def serialize_quiz(quiz: m.Quiz, include_correct: bool = False) -> dict:
    return {
        "id": quiz.id,
        "title": quiz.title,
        "questions": [
            {
                "id": qq.id,
                "text": qq.text,
                "image_url": qq.image_url,
                "qtype": qq.qtype,
                "order_index": qq.order_index,
                "options": [
                    {
                        "id": op.id,
                        "text": op.text,
                        "image_url": op.image_url,
                        "order_index": op.order_index,
                        **({"is_correct": op.is_correct} if include_correct else {}),
                    }
                    for op in qq.options
                ],
            }
            for qq in quiz.questions
        ],
    }


def tally_question(db: DbSession, qs: m.QuizSession, qq: m.QuizQuestion) -> dict:
    rows = db.scalars(
        select(m.QuizResponse).where(
            m.QuizResponse.quiz_session_id == qs.id,
            m.QuizResponse.question_id == qq.id,
        )
    ).all()
    counts = Counter(r.option_id for r in rows)
    voters = {r.voter_token for r in rows}
    return {
        "question_id": qq.id,
        "respondents": len(voters),
        "totals": {op.id: counts.get(op.id, 0) for op in qq.options},
    }


def serialize_quiz_session(db: DbSession, qs: m.QuizSession, *, voter_token: str, is_mod: bool) -> dict:
    quiz = qs.quiz
    questions = quiz.questions
    current = questions[qs.current_question_idx] if 0 <= qs.current_question_idx < len(questions) else None
    show_correct = is_mod or (qs.status == "closed") or qs.reveal_results
    payload = {
        "id": qs.id,
        "session_id": qs.session_id,
        "quiz_id": quiz.id,
        "quiz_title": quiz.title,
        "status": qs.status,
        "current_question_idx": qs.current_question_idx,
        "question_count": len(questions),
        "reveal_results": qs.reveal_results,
        "current_question": None,
        "my_selections": [],
        "results": None,
    }
    if current is not None:
        payload["current_question"] = {
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
        mine = db.scalars(
            select(m.QuizResponse).where(
                m.QuizResponse.quiz_session_id == qs.id,
                m.QuizResponse.question_id == current.id,
                m.QuizResponse.voter_token == voter_token,
            )
        ).all()
        payload["my_selections"] = [r.option_id for r in mine]
        if is_mod or qs.reveal_results or qs.status == "closed":
            payload["results"] = tally_question(db, qs, current)
    return payload


# ---------- broadcast ----------

async def broadcast_session(db: DbSession, session: m.Session, kind: str = "update") -> None:
    await hub.broadcast(f"session:{session.code}", {"type": kind})


# ---------- routes: pages ----------

@app.get("/")
def root():
    return FileResponse(STATIC / "index.html")


def _session_exists(code: str, db: DbSession) -> bool:
    return bool(db.scalar(select(m.Session.id).where(m.Session.code == code.upper())))


def _bad_code_redirect(code: str) -> RedirectResponse:
    # Send the user back to the landing page with a hint. Status 303 so a
    # link that was hot-cached doesn't keep redirecting back to a stale state.
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
def list_sessions(db: DbSession = Depends(get_db), _admin: m.User = Depends(auth.current_admin)):
    rows = db.scalars(select(m.Session).order_by(m.Session.created_at.desc())).all()
    return [
        {
            "code": s.code,
            "title": s.title,
            "mod_key": s.mod_key,
            "created_at": s.created_at.isoformat(),
            "question_count": len(s.questions),
            "quiz_session_count": len(s.quiz_sessions),
        }
        for s in rows
    ]


@app.post("/api/sessions")
def create_session(payload: dict, db: DbSession = Depends(get_db), _admin: m.User = Depends(auth.current_admin)):
    title = (payload.get("title") or "").strip() or "Untitled session"
    code = gen_code()
    while db.scalar(select(m.Session).where(m.Session.code == code)):
        code = gen_code()
    s = m.Session(code=code, title=title, mod_key=gen_token()[:16])
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"code": s.code, "title": s.title, "mod_key": s.mod_key}


@app.get("/api/sessions/{code}")
def get_session(code: str, db: DbSession = Depends(get_db)):
    s = get_session_by_code(db, code)
    return {"code": s.code, "title": s.title, "created_at": s.created_at.isoformat()}


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
    token = ensure_voter_token(voter_token, request, response)
    qs = db.scalars(
        select(m.Question)
        .where(m.Question.session_id == s.id)
        .options(selectinload(m.Question.votes))
        .order_by(m.Question.created_at.desc())
    ).all()
    if not is_mod:
        qs = [q for q in qs if not q.hidden]
    return [serialize_question(q, token, is_mod) for q in qs]


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
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text required")
    if len(text) > 1000:
        raise HTTPException(400, "text too long")
    token = ensure_voter_token(voter_token, request, response)
    name = (payload.get("author_name") or "").strip()[:80] or None
    q = m.Question(session_id=s.id, text=text, author_token=token, author_name=name)
    db.add(q)
    db.commit()
    db.refresh(q)
    db.refresh(q, ["votes"])
    await broadcast_session(db, s, "question_new")
    return serialize_question(q, token, False)


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
    q = db.get(m.Question, qid)
    if not q or q.session_id != s.id:
        raise HTTPException(404)
    token = ensure_voter_token(voter_token, request, response)
    existing = db.scalar(
        select(m.QuestionVote).where(
            m.QuestionVote.question_id == qid,
            m.QuestionVote.voter_token == token,
        )
    )
    if existing:
        db.delete(existing)
        voted = False
    else:
        db.add(m.QuestionVote(question_id=qid, voter_token=token))
        voted = True
    db.commit()
    db.refresh(q, ["votes"])
    await broadcast_session(db, s, "question_vote")
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
    await broadcast_session(db, s, "question_answered")
    return {"ok": True}


@app.post("/api/sessions/{code}/questions/{qid}/hide")
async def hide_question(
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
    q.hidden = bool(payload.get("hidden", True))
    db.commit()
    await broadcast_session(db, s, "question_hidden")
    return {"ok": True}


@app.delete("/api/sessions/{code}/questions/{qid}")
async def delete_question(
    code: str,
    qid: int,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
):
    s = get_session_by_code(db, code)
    require_mod(s, x_mod_key)
    q = db.get(m.Question, qid)
    if not q or q.session_id != s.id:
        raise HTTPException(404)
    db.delete(q)
    db.commit()
    await broadcast_session(db, s, "question_deleted")
    return {"ok": True}


# ---------- helpers: quiz lifecycle ----------

def _validate_quiz_ready(quiz: m.Quiz) -> None:
    """Raise 400 if the quiz can't be published in its current shape."""
    if not quiz.questions:
        raise HTTPException(400, "Quiz needs at least one question")
    for idx, qq in enumerate(quiz.questions, start=1):
        if not qq.text.strip():
            raise HTTPException(400, f"Question {idx} is missing text")
        if len(qq.options) < 2:
            raise HTTPException(400, f"Question {idx} needs at least 2 options")
        correct = [op for op in qq.options if op.is_correct]
        if qq.qtype == "single" and len(correct) != 1:
            raise HTTPException(400, f"Question {idx} (single choice) needs exactly one correct option")
        if qq.qtype == "multi" and len(correct) < 1:
            raise HTTPException(400, f"Question {idx} (multiple choice) needs at least one correct option")
        for op_idx, op in enumerate(qq.options, start=1):
            if not op.text.strip() and not op.image_url:
                raise HTTPException(400, f"Question {idx}, option {op_idx} is empty")


def _revert_to_draft(quiz: m.Quiz) -> None:
    """Any structural edit on a Ready quiz drops it back to Draft.

    Forces the admin to re-validate and explicitly re-publish before the
    quiz can be attached to new sessions.
    """
    if quiz.status != "draft":
        quiz.status = "draft"


def _quiz_for_question(db: DbSession, qq: m.QuizQuestion) -> m.Quiz:
    return db.get(m.Quiz, qq.quiz_id)


# ---------- routes: quizzes (templates) ----------

@app.get("/api/quizzes")
def list_quizzes(
    ready_only: bool = False,
    db: DbSession = Depends(get_db),
):
    stmt = select(m.Quiz).options(
        selectinload(m.Quiz.questions).selectinload(m.QuizQuestion.options)
    ).order_by(m.Quiz.created_at.desc())
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
    _admin: m.User = Depends(auth.current_admin),
):
    title = (payload.get("title") or "").strip() or "Untitled quiz"
    quiz = m.Quiz(title=title)
    db.add(quiz)
    db.commit()
    db.refresh(quiz)
    return {"id": quiz.id, "title": quiz.title}


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
    show = include_correct and me is not None
    payload = serialize_quiz(quiz, include_correct=show)
    payload["status"] = quiz.status
    return payload


@app.post("/api/quizzes/{quiz_id}/publish")
def publish_quiz(
    quiz_id: int,
    db: DbSession = Depends(get_db),
    _admin: m.User = Depends(auth.current_admin),
):
    quiz = db.get(m.Quiz, quiz_id)
    if not quiz:
        raise HTTPException(404)
    _validate_quiz_ready(quiz)
    quiz.status = "ready"
    db.commit()
    return {"status": quiz.status}


@app.post("/api/quizzes/{quiz_id}/unpublish")
def unpublish_quiz(
    quiz_id: int,
    db: DbSession = Depends(get_db),
    _admin: m.User = Depends(auth.current_admin),
):
    quiz = db.get(m.Quiz, quiz_id)
    if not quiz:
        raise HTTPException(404)
    quiz.status = "draft"
    db.commit()
    return {"status": quiz.status}


@app.patch("/api/quizzes/{quiz_id}")
def update_quiz(
    quiz_id: int,
    payload: dict,
    db: DbSession = Depends(get_db),
    _admin: m.User = Depends(auth.current_admin),
):
    quiz = db.get(m.Quiz, quiz_id)
    if not quiz:
        raise HTTPException(404)
    if "title" in payload:
        new_title = (str(payload["title"] or "")).strip() or quiz.title
        if new_title != quiz.title:
            quiz.title = new_title
            _revert_to_draft(quiz)
    db.commit()
    return {"ok": True, "status": quiz.status}


@app.delete("/api/quizzes/{quiz_id}")
def delete_quiz(
    quiz_id: int,
    db: DbSession = Depends(get_db),
    _admin: m.User = Depends(auth.current_admin),
):
    quiz = db.get(m.Quiz, quiz_id)
    if not quiz:
        raise HTTPException(404)
    db.delete(quiz)
    db.commit()
    return {"ok": True}


@app.post("/api/quizzes/{quiz_id}/questions")
def add_quiz_question(
    quiz_id: int,
    payload: dict,
    db: DbSession = Depends(get_db),
    _admin: m.User = Depends(auth.current_admin),
):
    quiz = db.get(m.Quiz, quiz_id)
    if not quiz:
        raise HTTPException(404)
    qtype = payload.get("qtype", "single")
    if qtype not in ("single", "multi"):
        raise HTTPException(400, "qtype must be single or multi")
    max_order = db.scalar(
        select(m.QuizQuestion).where(m.QuizQuestion.quiz_id == quiz_id).order_by(m.QuizQuestion.order_index.desc())
    )
    next_order = (max_order.order_index + 1) if max_order else 0
    qq = m.QuizQuestion(
        quiz_id=quiz_id,
        text=(payload.get("text") or "").strip(),
        image_url=payload.get("image_url"),
        qtype=qtype,
        order_index=payload.get("order_index", next_order),
    )
    db.add(qq)
    _revert_to_draft(quiz)
    db.commit()
    db.refresh(qq)
    return {"id": qq.id}


@app.patch("/api/quiz_questions/{qq_id}")
def update_quiz_question(
    qq_id: int,
    payload: dict,
    db: DbSession = Depends(get_db),
    _admin: m.User = Depends(auth.current_admin),
):
    qq = db.get(m.QuizQuestion, qq_id)
    if not qq:
        raise HTTPException(404)
    if "text" in payload:
        qq.text = str(payload["text"] or "").strip()
    if "image_url" in payload:
        v = payload["image_url"]
        qq.image_url = str(v) if v else None
    if "qtype" in payload:
        if payload["qtype"] not in ("single", "multi"):
            raise HTTPException(400, "qtype must be single or multi")
        qq.qtype = payload["qtype"]
    if "order_index" in payload:
        try:
            qq.order_index = int(payload["order_index"])
        except (TypeError, ValueError):
            raise HTTPException(400, "order_index must be an integer")
    _revert_to_draft(_quiz_for_question(db, qq))
    db.commit()
    return {"ok": True}


@app.delete("/api/quiz_questions/{qq_id}")
def delete_quiz_question(
    qq_id: int,
    db: DbSession = Depends(get_db),
    _admin: m.User = Depends(auth.current_admin),
):
    qq = db.get(m.QuizQuestion, qq_id)
    if not qq:
        raise HTTPException(404)
    parent_quiz = _quiz_for_question(db, qq)
    db.delete(qq)
    _revert_to_draft(parent_quiz)
    db.commit()
    return {"ok": True}


@app.post("/api/quiz_questions/{qq_id}/options")
def add_quiz_option(
    qq_id: int,
    payload: dict,
    db: DbSession = Depends(get_db),
    _admin: m.User = Depends(auth.current_admin),
):
    qq = db.get(m.QuizQuestion, qq_id)
    if not qq:
        raise HTTPException(404)
    max_order = db.scalar(
        select(m.QuizOption).where(m.QuizOption.question_id == qq_id).order_by(m.QuizOption.order_index.desc())
    )
    next_order = (max_order.order_index + 1) if max_order else 0
    op = m.QuizOption(
        question_id=qq_id,
        text=(payload.get("text") or "").strip(),
        image_url=payload.get("image_url"),
        is_correct=bool(payload.get("is_correct", False)),
        order_index=payload.get("order_index", next_order),
    )
    db.add(op)
    _revert_to_draft(_quiz_for_question(db, qq))
    db.commit()
    db.refresh(op)
    return {"id": op.id}


@app.patch("/api/quiz_options/{op_id}")
def update_quiz_option(
    op_id: int,
    payload: dict,
    db: DbSession = Depends(get_db),
    _admin: m.User = Depends(auth.current_admin),
):
    op = db.get(m.QuizOption, op_id)
    if not op:
        raise HTTPException(404)
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
    qq = db.get(m.QuizQuestion, op.question_id)
    _revert_to_draft(_quiz_for_question(db, qq))
    db.commit()
    return {"ok": True}


@app.delete("/api/quiz_options/{op_id}")
def delete_quiz_option(
    op_id: int,
    db: DbSession = Depends(get_db),
    _admin: m.User = Depends(auth.current_admin),
):
    op = db.get(m.QuizOption, op_id)
    if not op:
        raise HTTPException(404)
    qq = db.get(m.QuizQuestion, op.question_id)
    parent_quiz = _quiz_for_question(db, qq)
    db.delete(op)
    _revert_to_draft(parent_quiz)
    db.commit()
    return {"ok": True}


# ---------- routes: uploads ----------

@app.post("/api/uploads")
async def upload_image(
    file: UploadFile = File(...),
    _admin: m.User = Depends(auth.current_admin),
):
    ext = Path(file.filename or "").suffix.lower()
    # SVG is intentionally excluded — it can carry inline <script> and would
    # execute in the app's origin when fetched directly via /uploads/.
    if ext not in ALLOWED_IMAGE_EXTS:
        raise HTTPException(400, "unsupported image type")
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "max 5MB")
    # Stream-read with a hard cap so a client lying about Content-Length
    # cannot exhaust memory.
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


# ---------- routes: quiz sessions (running quizzes) ----------

@app.get("/api/sessions/{code}/quiz_sessions")
def list_quiz_sessions(
    code: str,
    request: Request,
    response: Response,
    voter_token: Annotated[str | None, Cookie()] = None,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
):
    s = get_session_by_code(db, code)
    is_mod = bool(x_mod_key) and secrets.compare_digest(x_mod_key, s.mod_key)
    token = ensure_voter_token(voter_token, request, response)
    rows = db.scalars(
        select(m.QuizSession)
        .where(m.QuizSession.session_id == s.id)
        .order_by(m.QuizSession.created_at.desc())
    ).all()
    if not is_mod:
        rows = [r for r in rows if r.status in ("live", "closed")]
    return [serialize_quiz_session(db, r, voter_token=token, is_mod=is_mod) for r in rows]


@app.post("/api/sessions/{code}/quiz_sessions")
async def create_quiz_session(
    code: str,
    payload: dict,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
):
    s = get_session_by_code(db, code)
    require_mod(s, x_mod_key)
    quiz_id = payload.get("quiz_id")
    quiz = db.get(m.Quiz, quiz_id) if quiz_id else None
    if not quiz:
        raise HTTPException(404, "quiz not found")
    if quiz.status != "ready":
        raise HTTPException(400, "Quiz is still a draft — publish it first")
    qs = m.QuizSession(session_id=s.id, quiz_id=quiz.id, status="draft")
    db.add(qs)
    db.commit()
    db.refresh(qs)
    await broadcast_session(db, s, "quiz_session_new")
    return {"id": qs.id}


def _get_qs_mod(db: DbSession, code: str, qs_id: int, mod_key: str | None) -> tuple[m.Session, m.QuizSession]:
    s = get_session_by_code(db, code)
    require_mod(s, mod_key)
    qs = db.get(m.QuizSession, qs_id)
    if not qs or qs.session_id != s.id:
        raise HTTPException(404)
    return s, qs


@app.post("/api/sessions/{code}/quiz_sessions/{qs_id}/start")
async def start_quiz_session(
    code: str,
    qs_id: int,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
):
    s, qs = _get_qs_mod(db, code, qs_id, x_mod_key)
    qs.status = "live"
    qs.current_question_idx = 0
    qs.reveal_results = False
    qs.started_at = datetime.utcnow()
    db.commit()
    await broadcast_session(db, s, "quiz_session_update")
    return {"ok": True}


@app.post("/api/sessions/{code}/quiz_sessions/{qs_id}/advance")
async def advance_quiz_session(
    code: str,
    qs_id: int,
    payload: dict,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
):
    s, qs = _get_qs_mod(db, code, qs_id, x_mod_key)
    direction = payload.get("direction", "next")
    quiz = db.get(m.Quiz, qs.quiz_id)
    total = len(quiz.questions)
    if direction == "next":
        qs.current_question_idx = min(qs.current_question_idx + 1, max(total - 1, 0))
    elif direction == "prev":
        qs.current_question_idx = max(qs.current_question_idx - 1, 0)
    elif direction == "to" and "index" in payload:
        try:
            idx = int(payload["index"])
        except (TypeError, ValueError):
            raise HTTPException(400, "index must be an integer")
        qs.current_question_idx = max(0, min(idx, max(total - 1, 0)))
    qs.reveal_results = False
    db.commit()
    await broadcast_session(db, s, "quiz_session_update")
    return {"ok": True}


@app.post("/api/sessions/{code}/quiz_sessions/{qs_id}/reveal")
async def reveal_quiz_session(
    code: str,
    qs_id: int,
    payload: dict,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
):
    s, qs = _get_qs_mod(db, code, qs_id, x_mod_key)
    qs.reveal_results = bool(payload.get("reveal", True))
    db.commit()
    await broadcast_session(db, s, "quiz_session_update")
    return {"ok": True}


@app.post("/api/sessions/{code}/quiz_sessions/{qs_id}/close")
async def close_quiz_session(
    code: str,
    qs_id: int,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
):
    s, qs = _get_qs_mod(db, code, qs_id, x_mod_key)
    qs.status = "closed"
    qs.reveal_results = True
    qs.closed_at = datetime.utcnow()
    db.commit()
    await broadcast_session(db, s, "quiz_session_update")
    return {"ok": True}


@app.delete("/api/sessions/{code}/quiz_sessions/{qs_id}")
async def delete_quiz_session(
    code: str,
    qs_id: int,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
):
    s, qs = _get_qs_mod(db, code, qs_id, x_mod_key)
    db.delete(qs)
    db.commit()
    await broadcast_session(db, s, "quiz_session_deleted")
    return {"ok": True}


@app.get("/api/sessions/{code}/quiz_sessions/{qs_id}")
def get_quiz_session(
    code: str,
    qs_id: int,
    request: Request,
    response: Response,
    voter_token: Annotated[str | None, Cookie()] = None,
    x_mod_key: Annotated[str | None, Header()] = None,
    db: DbSession = Depends(get_db),
):
    s = get_session_by_code(db, code)
    is_mod = bool(x_mod_key) and secrets.compare_digest(x_mod_key, s.mod_key)
    token = ensure_voter_token(voter_token, request, response)
    qs = db.get(m.QuizSession, qs_id)
    if not qs or qs.session_id != s.id:
        raise HTTPException(404)
    if not is_mod and qs.status not in ("live", "closed"):
        raise HTTPException(404)
    return serialize_quiz_session(db, qs, voter_token=token, is_mod=is_mod)


@app.post("/api/sessions/{code}/quiz_sessions/{qs_id}/respond")
async def respond_quiz(
    code: str,
    qs_id: int,
    payload: dict,
    request: Request,
    response: Response,
    voter_token: Annotated[str | None, Cookie()] = None,
    db: DbSession = Depends(get_db),
):
    s = get_session_by_code(db, code)
    qs = db.get(m.QuizSession, qs_id)
    if not qs or qs.session_id != s.id or qs.status != "live":
        raise HTTPException(404, "Quiz not live")
    question_id = payload.get("question_id")
    option_ids = payload.get("option_ids") or []
    qq = db.get(m.QuizQuestion, question_id)
    if not qq or qq.quiz_id != qs.quiz_id:
        raise HTTPException(404, "Question not found")
    # Only allow responding to the current question
    quiz = db.get(m.Quiz, qs.quiz_id)
    if quiz.questions[qs.current_question_idx].id != qq.id:
        raise HTTPException(400, "Not the current question")
    if qq.qtype == "single" and len(option_ids) > 1:
        raise HTTPException(400, "Only one option allowed")
    valid_option_ids = {op.id for op in qq.options}
    bad = [oid for oid in option_ids if oid not in valid_option_ids]
    if bad:
        raise HTTPException(400, "Invalid option")
    token = ensure_voter_token(voter_token, request, response)
    # Clear existing responses by this voter for this question
    existing = db.scalars(
        select(m.QuizResponse).where(
            m.QuizResponse.quiz_session_id == qs.id,
            m.QuizResponse.question_id == qq.id,
            m.QuizResponse.voter_token == token,
        )
    ).all()
    for r in existing:
        db.delete(r)
    for oid in option_ids:
        db.add(m.QuizResponse(
            quiz_session_id=qs.id,
            question_id=qq.id,
            option_id=oid,
            voter_token=token,
        ))
    db.commit()
    await broadcast_session(db, s, "quiz_response")
    return {"ok": True}


# ---------- websocket ----------

@app.websocket("/ws/sessions/{code}")
async def ws_session(ws: WebSocket, code: str):
    # Reject cross-origin WebSocket handshakes — browsers do not enforce
    # same-origin for WS, so without this an attacker page could open a
    # socket on behalf of a logged-in user. Server-to-server clients
    # (no Origin header) are allowed.
    origin = ws.headers.get("origin")
    if origin:
        host = ws.headers.get("host", "")
        expected_http = f"http://{host}"
        expected_https = f"https://{host}"
        if origin != expected_http and origin != expected_https:
            await ws.close(code=4403)
            return
    # Just validate the session exists
    with SessionLocal() as db:
        s = db.scalar(select(m.Session).where(m.Session.code == code.upper()))
        if not s:
            await ws.close(code=4404)
            return
    room = f"session:{code.upper()}"
    await hub.join(room, ws)
    try:
        while True:
            # Client may send pings; we ignore content
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.leave(room, ws)
    except Exception:
        hub.leave(room, ws)
