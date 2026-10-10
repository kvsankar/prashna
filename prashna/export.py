"""Data export as one JSON document or one Excel workbook (UC-A-30).

Builders turn ORM rows into plain nested dicts (the JSON document). The
Excel writer flattens those dicts into one sheet per table, so both
formats always carry the same data. Nothing here reads voter tokens,
password hashes, or moderator keys, so no export can contain them.
"""
from __future__ import annotations

import io
import json
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import metadata
from typing import Any

import xlsxwriter
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload

from . import models as m

FORMATS = ("json", "xlsx")
PARTS = ("all", "profiles", "feedback", "qna", "quiz_runs")
FORMAT_ERROR = "format must be json or xlsx"
PART_ERROR = "part must be one of " + ", ".join(PARTS)
CONTENT_TYPES = {
    "json": "application/json",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
PERSONAL_DATA_NOTE = (
    "This file contains participants' personal data (names and any contact "
    "details they gave). Keep it private and delete it when no longer needed."
)
STATUS_LABELS = {
    "planning": "Not started", "live": "Live", "ended": "Ended",
    "queued": "Queued", "closed": "Closed",
    "open": "Open", "responded": "Responded", "removed": "Removed",
    "draft": "Draft", "ready": "Ready",
}
QTYPE_LABELS = {"single": "Single choice", "multi": "Multiple choice"}
# What each session part contains (JSON keys under `session`).
PART_KEYS = {
    "all": ("participants", "questions", "quiz_runs", "feedback"),
    "profiles": ("participants",),
    "feedback": ("feedback",),
    "qna": ("questions",),
    "quiz_runs": ("quiz_runs",),
}
PART_SCOPE = {"all": "session", "profiles": "profiles", "feedback": "feedback",
              "qna": "qna", "quiz_runs": "quiz-runs"}


def prashna_version() -> str:
    try:
        return metadata.version("prashna")
    except metadata.PackageNotFoundError:  # pragma: no cover - source checkout without install
        return "0+unknown"


def iso(dt: datetime | None) -> str | None:
    """Stored timestamps are naive UTC; export them as ISO 8601 with `Z`."""
    if dt is None:
        return None
    return dt.replace(microsecond=0).isoformat() + "Z"


def _profile_present(p: m.Participant) -> bool:
    fields = ("name", "email", "contact_number", "organization", "role",
              "linkedin_url", "photo_url", "current_work", "learning_goal")
    return any(getattr(p, f) for f in fields)


# ---------- builders: ORM rows -> nested dicts ----------

def _participant(p: m.Participant) -> dict:
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
        "first_seen_at": iso(p.first_seen_at),
        "last_seen_at": iso(p.last_seen_at),
    }


def _query(q: m.Query) -> dict:
    if q.removed_at is not None:
        status = "removed"
    elif q.responded_at is not None:
        status = "responded"
    else:
        status = "open"
    return {
        "id": q.id,
        "participant_id": q.participant_id,
        "author_name": q.participant.name if q.participant else None,
        "text": q.text,
        "vote_count": len(q.votes),
        "status": status,
        "responded": q.responded_at is not None,
        "response_text": q.response_text,
        "responded_at": iso(q.responded_at),
        "removed": q.removed_at is not None,
        "removed_at": iso(q.removed_at),
        "created_at": iso(q.created_at),
    }


def _feedback(f: m.SessionFeedback) -> dict:
    return {
        "participant_id": f.participant_id,
        "author_name": f.participant.name if f.participant else None,
        "rating": f.rating,
        "went_well": f.went_well,
        "to_improve": f.to_improve,
        "created_at": iso(f.created_at),
        "updated_at": iso(f.updated_at),
    }


def build_quiz_run(db: DbSession, run: m.QuizRun) -> dict:
    """One run: its frozen version, per-question results, and each
    participant's answers (one response per participant and question)."""
    version = run.quiz_version
    subs = db.scalars(
        select(m.QuizSubmission).where(m.QuizSubmission.quiz_run_id == run.id)
    ).all()
    names = dict(db.execute(
        select(m.Participant.id, m.Participant.name)
        .where(m.Participant.id.in_({s.participant_id for s in subs}))
    ).tuples().all()) if subs else {}
    picks: dict[tuple[int, int], list[m.QuizSubmission]] = defaultdict(list)
    for s in subs:
        picks[(s.question_id, s.participant_id)].append(s)
    questions, responses = [], []
    for number, vq in enumerate(version.questions, start=1):
        answers = {a.id: a for a in vq.answers}
        counts: dict[int, int] = defaultdict(int)
        respondents = set()
        for (qid, pid), rows in picks.items():
            if qid != vq.id:
                continue
            respondents.add(pid)
            for r in rows:
                counts[r.answer_id] += 1
        questions.append({
            "number": number,
            "text": vq.text,
            "image_url": vq.image_url,
            "qtype": vq.qtype,
            "graded": vq.graded,
            "respondents": len(respondents),
            "answers": [
                {
                    "number": i,
                    "text": a.text,
                    "image_url": a.image_url,
                    "is_correct": a.is_correct if vq.graded else None,
                    "count": counts.get(a.id, 0),
                }
                for i, a in enumerate(vq.answers, start=1)
            ],
        })
        correct_ids = {a.id for a in vq.answers if a.is_correct}
        for pid in sorted(respondents):
            rows = sorted(picks[(vq.id, pid)], key=lambda r: answers[r.answer_id].order_index)
            chosen = {r.answer_id for r in rows}
            responses.append({
                "participant_id": pid,
                "participant_name": names.get(pid),
                "question_number": number,
                "answers": [answers[r.answer_id].text for r in rows],
                "correct": (chosen == correct_ids) if vq.graded else None,
                "answered_at": iso(max(r.created_at for r in rows)),
            })
    return {
        "id": run.id,
        "session_code": run.session.code,
        "session_title": run.session.title,
        "quiz_id": version.quiz_id,
        "quiz_title": version.quiz_title,
        "version_no": version.version_no,
        "status": run.status,
        "created_at": iso(run.created_at),
        "started_at": iso(run.started_at),
        "closed_at": iso(run.closed_at),
        "question_count": len(questions),
        "respondent_count": len({s.participant_id for s in subs}),
        "questions": questions,
        "responses": responses,
    }


def build_session(db: DbSession, s: m.Session, part: str = "all") -> dict:
    """One session's details plus the lists its part includes."""
    keys = PART_KEYS[part]
    feedback_rows = sorted(s.feedback, key=lambda f: f.created_at)
    ratings = [f.rating for f in feedback_rows]
    body: dict[str, Any] = {
        "code": s.code,
        "title": s.title,
        "status": s.status,
        "created_at": iso(s.created_at),
        "started_at": iso(s.started_at),
        "ended_at": iso(s.ended_at),
        "feedback_enabled": bool(s.feedback_enabled),
        "participant_base_url": s.participant_base_url,
        "participant_count": len(s.participants),
        "question_count": len(s.queries),
        "quiz_run_count": len(s.quiz_runs),
        "feedback_count": len(ratings),
        "average_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
    }
    if "participants" in keys:
        people = sorted(s.participants, key=lambda p: p.id)
        if part == "profiles":
            people = [p for p in people if _profile_present(p)]
        body["participants"] = [_participant(p) for p in people]
    if "questions" in keys:
        queries = db.scalars(
            select(m.Query).where(m.Query.session_id == s.id)
            .options(selectinload(m.Query.votes), selectinload(m.Query.participant))
            .order_by(m.Query.created_at, m.Query.id)
        ).all()
        body["questions"] = [_query(q) for q in queries]
    if "quiz_runs" in keys:
        runs = sorted(s.quiz_runs, key=lambda r: (r.created_at, r.id))
        body["quiz_runs"] = [build_quiz_run(db, r) for r in runs]
    if "feedback" in keys:
        body["feedback"] = [_feedback(f) for f in feedback_rows]
    return body


def build_quiz(quiz: m.Quiz, run_counts: dict[int, int]) -> dict:
    return {
        "id": quiz.id,
        "title": quiz.title,
        "status": quiz.status,
        "created_at": iso(quiz.created_at),
        "last_edited_at": iso(quiz.last_edited_at),
        "questions": [
            {
                "number": n,
                "text": q.text,
                "image_url": q.image_url,
                "qtype": q.qtype,
                "graded": q.graded,
                "answers": [
                    {"number": i, "text": a.text, "image_url": a.image_url, "is_correct": a.is_correct}
                    for i, a in enumerate(q.answers, start=1)
                ],
            }
            for n, q in enumerate(quiz.questions, start=1)
        ],
        "versions": [
            {
                "version_no": v.version_no,
                "quiz_title": v.quiz_title,
                "created_at": iso(v.created_at),
                "question_count": len(v.questions),
                "run_count": run_counts.get(v.id, 0),
            }
            for v in quiz.versions
        ],
    }


def meta(scope: str, *, personal: bool, **identifiers: Any) -> dict:
    return {
        "scope": scope,
        **identifiers,
        "exported_at": iso(datetime.now(timezone.utc).replace(tzinfo=None)),
        "prashna_version": prashna_version(),
        "contains_personal_data": personal,
    }


# ---------- tables: nested dicts -> sheets ----------

Column = tuple[str, Callable[[dict], Any]]


@dataclass
class Sheet:
    name: str
    columns: list[Column]
    rows: list[dict] = field(default_factory=list)


def _yes_no(value: bool | None) -> str | None:
    return None if value is None else ("Yes" if value else "No")


def _label(value: str | None) -> str | None:
    return None if value is None else STATUS_LABELS.get(value, value)


def _key(name: str) -> Callable[[dict], Any]:
    return lambda row: row.get(name)


SESSION_COLUMNS: list[Column] = [
    ("Session code", _key("code")),
    ("Title", _key("title")),
    ("Status", lambda r: _label(r["status"])),
    ("Created at", _key("created_at")),
    ("Started at", _key("started_at")),
    ("Ended at", _key("ended_at")),
    ("Rating open", lambda r: _yes_no(r["feedback_enabled"])),
    ("Participant base URL", _key("participant_base_url")),
    ("Participants", _key("participant_count")),
    ("Questions", _key("question_count")),
    ("Quiz runs", _key("quiz_run_count")),
    ("Feedback responses", _key("feedback_count")),
    ("Average rating", _key("average_rating")),
]
PARTICIPANT_COLUMNS: list[Column] = [
    ("Participant ID", _key("id")),
    ("Name", _key("name")),
    ("Email", _key("email")),
    ("Contact number", _key("contact_number")),
    ("Organization", _key("organization")),
    ("Role", _key("role")),
    ("LinkedIn", _key("linkedin_url")),
    ("Photo", _key("photo_url")),
    ("Current work", _key("current_work")),
    ("Learning goal", _key("learning_goal")),
    ("First seen", _key("first_seen_at")),
    ("Last seen", _key("last_seen_at")),
]
QUESTION_COLUMNS: list[Column] = [
    ("Question ID", _key("id")),
    ("Asked at", _key("created_at")),
    ("Participant ID", _key("participant_id")),
    ("Asked by", _key("author_name")),
    ("Question", _key("text")),
    ("Votes", _key("vote_count")),
    ("Status", lambda r: _label(r["status"])),
    ("Responded", lambda r: _yes_no(r["responded"])),
    ("Response", _key("response_text")),
    ("Responded at", _key("responded_at")),
    ("Removed at", _key("removed_at")),
]
RUN_COLUMNS: list[Column] = [
    ("Run ID", _key("id")),
    ("Quiz", _key("quiz_title")),
    ("Version", _key("version_no")),
    ("Status", lambda r: _label(r["status"])),
    ("Questions", _key("question_count")),
    ("Respondents", _key("respondent_count")),
    ("Created at", _key("created_at")),
    ("Started at", _key("started_at")),
    ("Closed at", _key("closed_at")),
]
ANSWER_COLUMNS: list[Column] = [
    ("Run ID", _key("run_id")),
    ("Quiz", _key("quiz_title")),
    ("Question no.", _key("question_number")),
    ("Question", _key("question_text")),
    ("Participant ID", _key("participant_id")),
    ("Participant name", _key("participant_name")),
    ("Chosen answers", lambda r: "; ".join(r["answers"])),
    ("Correct", lambda r: _yes_no(r["correct"])),
    ("Answered at", _key("answered_at")),
]
FEEDBACK_COLUMNS: list[Column] = [
    ("Participant ID", _key("participant_id")),
    ("Name", _key("author_name")),
    ("Rating", _key("rating")),
    ("Went well", _key("went_well")),
    ("Could be better", _key("to_improve")),
    ("Submitted at", _key("created_at")),
    ("Updated at", _key("updated_at")),
]
RUN_INFO_COLUMNS: list[Column] = [
    ("Run ID", _key("id")),
    ("Session code", _key("session_code")),
    ("Session title", _key("session_title")),
    *RUN_COLUMNS[1:],
]
RESULT_COLUMNS: list[Column] = [
    ("Question no.", _key("question_number")),
    ("Question", _key("question_text")),
    ("Type", lambda r: QTYPE_LABELS.get(r["qtype"], r["qtype"])),
    ("Graded", lambda r: _yes_no(r["graded"])),
    ("Respondents", _key("respondents")),
    ("Answer no.", _key("number")),
    ("Answer", _key("text")),
    ("Correct", lambda r: _yes_no(r["is_correct"])),
    ("Count", _key("count")),
    ("Question image", _key("question_image_url")),
    ("Answer image", _key("image_url")),
]
QUIZ_COLUMNS: list[Column] = [
    ("Quiz ID", _key("id")),
    ("Title", _key("title")),
    ("Status", lambda r: _label(r["status"])),
    ("Questions", lambda r: len(r["questions"])),
    ("Created at", _key("created_at")),
    ("Last edited at", _key("last_edited_at")),
]
TEMPLATE_QUESTION_COLUMNS: list[Column] = [
    ("Question no.", _key("number")),
    ("Question", _key("text")),
    ("Type", lambda r: QTYPE_LABELS.get(r["qtype"], r["qtype"])),
    ("Graded", lambda r: _yes_no(r["graded"])),
    ("Answers", lambda r: len(r["answers"])),
    ("Image", _key("image_url")),
]
TEMPLATE_ANSWER_COLUMNS: list[Column] = [
    ("Question no.", _key("question_number")),
    ("Answer no.", _key("number")),
    ("Answer", _key("text")),
    ("Correct", lambda r: _yes_no(r["is_correct"])),
    ("Image", _key("image_url")),
]
VERSION_COLUMNS: list[Column] = [
    ("Version", _key("version_no")),
    ("Title", _key("quiz_title")),
    ("Created at", _key("created_at")),
    ("Questions", _key("question_count")),
    ("Runs", _key("run_count")),
]


def _answer_rows(runs: Iterable[dict]) -> list[dict]:
    rows = []
    for run in runs:
        texts = {q["number"]: q["text"] for q in run["questions"]}
        for resp in run["responses"]:
            rows.append({**resp, "run_id": run["id"], "quiz_title": run["quiz_title"],
                         "question_text": texts.get(resp["question_number"])})
    return rows


def _result_rows(run: dict) -> list[dict]:
    return [
        {**a, "question_number": q["number"], "question_text": q["text"], "qtype": q["qtype"],
         "graded": q["graded"], "respondents": q["respondents"], "question_image_url": q["image_url"]}
        for q in run["questions"] for a in q["answers"]
    ]


def session_sheets(sessions: list[dict], *, many: bool) -> list[Sheet]:
    """The session tables. With `many`, each table starts with Session code."""
    def coded(columns: list[Column]) -> list[Column]:
        return [("Session code", _key("session_code")), *columns] if many else columns

    def rows_of(key: str, expand: Callable[[dict], list[dict]] | None = None) -> list[dict]:
        out = []
        for s in sessions:
            items = expand(s) if expand else s.get(key, [])
            out.extend({**item, "session_code": s["code"]} for item in items)
        return out

    present = set().union(*(s.keys() for s in sessions)) if sessions else set(PART_KEYS["all"])
    sheets = [Sheet("Sessions" if many else "Session", SESSION_COLUMNS, list(sessions))]
    if "participants" in present:
        sheets.append(Sheet("Participants", coded(PARTICIPANT_COLUMNS), rows_of("participants")))
    if "questions" in present:
        sheets.append(Sheet("Questions", coded(QUESTION_COLUMNS), rows_of("questions")))
    if "quiz_runs" in present:
        sheets.append(Sheet("Quiz runs", coded(RUN_COLUMNS), rows_of("quiz_runs")))
        sheets.append(Sheet("Quiz answers", coded(ANSWER_COLUMNS),
                            rows_of("", lambda s: _answer_rows(s.get("quiz_runs", [])))))
    if "feedback" in present:
        sheets.append(Sheet("Feedback", coded(FEEDBACK_COLUMNS), rows_of("feedback")))
    return sheets


def quiz_run_sheets(run: dict) -> list[Sheet]:
    return [
        Sheet("Quiz run", RUN_INFO_COLUMNS, [run]),
        Sheet("Results", RESULT_COLUMNS, _result_rows(run)),
        Sheet("Quiz answers", ANSWER_COLUMNS, _answer_rows([run])),
    ]


def quiz_sheets(quiz: dict) -> list[Sheet]:
    return [
        Sheet("Quiz", QUIZ_COLUMNS, [quiz]),
        Sheet("Questions", TEMPLATE_QUESTION_COLUMNS, quiz["questions"]),
        Sheet("Answers", TEMPLATE_ANSWER_COLUMNS,
              [{**a, "question_number": q["number"]} for q in quiz["questions"] for a in q["answers"]]),
        Sheet("Versions", VERSION_COLUMNS, quiz["versions"]),
    ]


# ---------- writers ----------

def to_json(document: dict) -> bytes:
    return json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")


def to_xlsx(about: list[tuple[str, Any]], sheets: list[Sheet]) -> bytes:
    """One workbook: an About sheet, then one sheet per table."""
    buf = io.BytesIO()
    # Never turn participant text into formulas, links, or numbers.
    wb = xlsxwriter.Workbook(buf, {
        "in_memory": True,
        "strings_to_formulas": False,
        "strings_to_urls": False,
        "strings_to_numbers": False,
    })
    bold = wb.add_format({"bold": True})
    wrap = wb.add_format({"text_wrap": True, "valign": "top"})

    ws = wb.add_worksheet("About")
    ws.write_row(0, 0, ["Field", "Value"], bold)
    for i, (label, value) in enumerate(about, start=1):
        ws.write(i, 0, label, bold)
        ws.write(i, 1, value)
    ws.set_column(0, 0, 22)
    ws.set_column(1, 1, 90, wrap)

    for sheet in sheets:
        ws = wb.add_worksheet(sheet.name)
        headers = [h for h, _ in sheet.columns]
        ws.write_row(0, 0, headers, bold)
        ws.freeze_panes(1, 0)
        widths = [len(h) for h in headers]
        for r, row in enumerate(sheet.rows, start=1):
            for c, (_, get) in enumerate(sheet.columns):
                value = get(row)
                if value is None:
                    continue
                ws.write(r, c, value)
                widths[c] = max(widths[c], min(len(str(value)), 60))
        for c, w in enumerate(widths):
            ws.set_column(c, c, w + 2)
    wb.close()
    return buf.getvalue()


def about_rows(export: dict, description: str, identifiers: list[tuple[str, Any]],
               sheets: list[Sheet]) -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = [("Export", description), *identifiers,
                                   ("Exported at (UTC)", export["exported_at"]),
                                   ("Prashna version", export["prashna_version"]),
                                   ("Sheets", ", ".join(s.name for s in sheets))]
    if export["contains_personal_data"]:
        rows.append(("Personal data", PERSONAL_DATA_NOTE))
    return rows


def filename(scope: str, identifier: str | int | None, ext: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    parts = ["prashna", scope] + ([str(identifier)] if identifier is not None else []) + [stamp]
    return "-".join(parts) + "." + ext


@dataclass
class Export:
    """A finished export, ready to send as a download."""
    content: bytes
    content_type: str
    filename: str


def render(fmt: str, document: dict, description: str, identifiers: list[tuple[str, Any]],
           sheets: list[Sheet], scope: str, identifier: str | int | None) -> Export:
    if fmt == "json":
        content = to_json(document)
    else:
        content = to_xlsx(about_rows(document["export"], description, identifiers, sheets), sheets)
    return Export(content, CONTENT_TYPES[fmt], filename(scope, identifier, fmt))


# ---------- scopes ----------

PART_DESCRIPTIONS = {
    "all": "One session",
    "profiles": "One session's attendee profiles",
    "feedback": "One session's feedback",
    "qna": "One session's Q&A",
    "quiz_runs": "One session's quiz runs",
}


def export_sessions(db: DbSession, owner: m.User, fmt: str) -> Export:
    rows = db.scalars(
        select(m.Session).where(m.Session.owner_user_id == owner.id)
        .order_by(m.Session.created_at.desc(), m.Session.id.desc())
    ).all()
    sessions = [build_session(db, s) for s in rows]
    document = {"export": meta("sessions", personal=True, session_count=len(sessions)),
                "sessions": sessions}
    sheets = session_sheets(sessions, many=True)
    return render(fmt, document, "All sessions", [("Sessions", len(sessions))],
                  sheets, "all-sessions", None)


def export_session(db: DbSession, s: m.Session, fmt: str, part: str) -> Export:
    session = build_session(db, s, part)
    document = {"export": meta("session", personal=True, part=part, session_code=s.code),
                "session": session}
    sheets = session_sheets([session], many=False)
    identifiers = [("Session code", s.code), ("Session title", s.title)]
    return render(fmt, document, PART_DESCRIPTIONS[part], identifiers, sheets, PART_SCOPE[part], s.code)


def export_quiz_run(db: DbSession, run: m.QuizRun, fmt: str) -> Export:
    body = build_quiz_run(db, run)
    document = {"export": meta("quiz_run", personal=True, quiz_run_id=run.id), "quiz_run": body}
    identifiers = [("Quiz run ID", run.id), ("Quiz", body["quiz_title"]),
                   ("Version", body["version_no"]), ("Session code", body["session_code"])]
    return render(fmt, document, "One quiz run", identifiers, quiz_run_sheets(body), "quiz-run", run.id)


def export_quiz(db: DbSession, quiz: m.Quiz, fmt: str) -> Export:
    version_ids = [v.id for v in quiz.versions]
    run_counts: dict[int, int] = defaultdict(int)
    if version_ids:
        for vid in db.scalars(select(m.QuizRun.quiz_version_id).where(m.QuizRun.quiz_version_id.in_(version_ids))):
            run_counts[vid] += 1
    body = build_quiz(quiz, run_counts)
    document = {"export": meta("quiz", personal=False, quiz_id=quiz.id), "quiz": body}
    identifiers = [("Quiz ID", quiz.id), ("Quiz", quiz.title)]
    return render(fmt, document, "One quiz", identifiers, quiz_sheets(body), "quiz", quiz.id)
