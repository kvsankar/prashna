from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


def now() -> datetime:
    return datetime.utcnow()


# ---------- users ----------

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    # Empty for GitHub-OAuth admins (UC-A-26) — they authenticate via GitHub,
    # not a password, so password login simply never verifies for them.
    password_hash: Mapped[str] = mapped_column(String(255))
    # Set for admins who signed in via GitHub OAuth; maps the immutable
    # GitHub numeric id to this User row. NULL for password-only admins.
    github_id: Mapped[int | None] = mapped_column(Integer, index=True, unique=True, nullable=True)
    # Bumped on every password change; included in the signed session cookie
    # so previously-issued cookies become invalid after a password change.
    session_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


# ---------- sessions (the live event) ----------

class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    mod_key: Mapped[str] = mapped_column(String(32))
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # Lifecycle: planning -> live -> ended.
    status: Mapped[str] = mapped_column(String(10), default="planning")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Optional override used when generating the participant URL + QR.
    # If unset, frontends fall back to location.origin.
    participant_base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    queries: Mapped[list["Query"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    quiz_runs: Mapped[list["QuizRun"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    participants: Mapped[list["Participant"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    feedback: Mapped[list["SessionFeedback"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    feedback_versions: Mapped[list["SessionFeedbackVersion"]] = relationship(back_populates="session", cascade="all, delete-orphan")


# ---------- participants (audience members, scoped per session) ----------

class Participant(Base):
    __tablename__ = "participants"
    __table_args__ = (UniqueConstraint("session_id", "voter_token", name="uq_session_voter"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    voter_token: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    session: Mapped[Session] = relationship(back_populates="participants")


# ---------- Q&A: queries (participant-asked) + their upvotes ----------

class Query(Base):
    """A participant-asked Q&A entry. Moderator can mark it responded
    (with optional response text), remove it (soft), or hard-delete."""
    __tablename__ = "queries"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Soft-remove: a removed query is hidden from participants but kept for audit / preserve-session-data.
    removed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    session: Mapped[Session] = relationship(back_populates="queries")
    participant: Mapped[Participant] = relationship()
    votes: Mapped[list["QueryVote"]] = relationship(back_populates="query", cascade="all, delete-orphan")


class SessionFeedback(Base):
    """A participant's rating + free-text feedback for a session. One row
    per (session, participant), upserted on resubmit. rating is 1..5."""
    __tablename__ = "session_feedback"
    __table_args__ = (UniqueConstraint("session_id", "participant_id", name="uq_session_feedback"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"), index=True)
    rating: Mapped[int] = mapped_column(Integer)
    went_well: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_improve: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    session: Mapped[Session] = relationship(back_populates="feedback")
    participant: Mapped[Participant] = relationship()


class SessionFeedbackVersion(Base):
    """Append-only history of every feedback submission. The latest version
    per participant is mirrored into SessionFeedback (the 'current' view);
    this table retains all prior submissions so participants can resubmit
    freely and the backend keeps the full trail."""
    __tablename__ = "session_feedback_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"), index=True)
    rating: Mapped[int] = mapped_column(Integer)
    went_well: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_improve: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    session: Mapped[Session] = relationship(back_populates="feedback_versions")
    participant: Mapped[Participant] = relationship()


class QueryVote(Base):
    __tablename__ = "query_votes"
    __table_args__ = (UniqueConstraint("query_id", "participant_id", name="uq_qvote"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    query_id: Mapped[int] = mapped_column(ForeignKey("queries.id", ondelete="CASCADE"), index=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    query: Mapped[Query] = relationship(back_populates="votes")


# ---------- quizzes (templates, mutable) ----------

class Quiz(Base):
    __tablename__ = "quizzes"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(10), default="draft")  # "draft" | "ready"
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # Used to detect "has the editable tree changed since the latest version?"
    last_edited_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    questions: Mapped[list["Question"]] = relationship(
        back_populates="quiz",
        cascade="all, delete-orphan",
        order_by="Question.order_index",
    )
    versions: Mapped[list["QuizVersion"]] = relationship(
        back_populates="quiz",
        cascade="all, delete-orphan",
        order_by="QuizVersion.version_no",
    )


class Question(Base):
    """One question in a Quiz template."""
    __tablename__ = "quiz_questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    qtype: Mapped[str] = mapped_column(String(10), default="single")  # "single" | "multi"
    # False = poll/survey question: has options but no correct answer (e.g.
    # collecting age/experience range). Publish skips the correct-answer
    # requirement and reveal shows the distribution without correctness.
    graded: Mapped[bool] = mapped_column(Boolean, default=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    quiz: Mapped[Quiz] = relationship(back_populates="questions")
    answers: Mapped[list["Answer"]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="Answer.order_index",
    )


class Answer(Base):
    """One answer choice for a Question in a Quiz template."""
    __tablename__ = "quiz_answers"
    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("quiz_questions.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    question: Mapped[Question] = relationship(back_populates="answers")


# ---------- quiz versions (immutable snapshots, created lazily on launch) ----------

class QuizVersion(Base):
    __tablename__ = "quiz_versions"
    __table_args__ = (UniqueConstraint("quiz_id", "version_no", name="uq_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    quiz_title: Mapped[str] = mapped_column(String(200))  # denormalized so renames don't reach history
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    quiz: Mapped[Quiz] = relationship(back_populates="versions")
    questions: Mapped[list["QuizVersionQuestion"]] = relationship(
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="QuizVersionQuestion.order_index",
    )


class QuizVersionQuestion(Base):
    __tablename__ = "quiz_version_questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("quiz_versions.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    qtype: Mapped[str] = mapped_column(String(10), default="single")
    # Frozen copy of Question.graded (poll vs scored). See Question.graded.
    graded: Mapped[bool] = mapped_column(Boolean, default=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    version: Mapped[QuizVersion] = relationship(back_populates="questions")
    answers: Mapped[list["QuizVersionAnswer"]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="QuizVersionAnswer.order_index",
    )


class QuizVersionAnswer(Base):
    __tablename__ = "quiz_version_answers"
    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("quiz_version_questions.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    question: Mapped[QuizVersionQuestion] = relationship(back_populates="answers")


# ---------- quiz runs (one playthrough of a frozen quiz inside a session) ----------

class QuizRun(Base):
    """One playthrough of a QuizVersion inside a Session."""
    __tablename__ = "quiz_runs"
    __table_args__ = (
        # Enforce "at most one live QuizRun per Session" at the storage layer.
        Index(
            "uq_session_live_run",
            "session_id",
            unique=True,
            sqlite_where=text("status = 'live'"),
            postgresql_where=text("status = 'live'"),
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    quiz_version_id: Mapped[int] = mapped_column(ForeignKey("quiz_versions.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(10), default="queued")  # "queued" | "live" | "closed"
    current_question_idx: Mapped[int] = mapped_column(Integer, default=0)
    reveal_current: Mapped[bool] = mapped_column(Boolean, default=False)
    # When true, the projector and participant pages show running answer counts
    # during the answering phase (before reveal). Correctness is still hidden
    # until reveal_current is true (or the run is closed).
    show_live_counts: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    session: Mapped[Session] = relationship(back_populates="quiz_runs")
    quiz_version: Mapped[QuizVersion] = relationship()
    submissions: Mapped[list["QuizSubmission"]] = relationship(cascade="all, delete-orphan")


class QuizSubmission(Base):
    """A participant's selected Answer for a Question during a QuizRun.

    One row per (run, question, answer, participant). Multi-choice picks
    create multiple rows; single-choice picks create one. Re-submitting a
    quiz answer deletes the participant's prior rows for the same
    (run, question) and inserts new ones — last-write-wins.
    """
    __tablename__ = "quiz_submissions"
    __table_args__ = (
        UniqueConstraint("quiz_run_id", "question_id", "answer_id", "participant_id", name="uq_qsubmission"),
        # Tally queries filter by (quiz_run_id, question_id); back this with an index.
        Index("ix_qsub_run_question", "quiz_run_id", "question_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_run_id: Mapped[int] = mapped_column(ForeignKey("quiz_runs.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("quiz_version_questions.id", ondelete="CASCADE"))
    answer_id: Mapped[int] = mapped_column(ForeignKey("quiz_version_answers.id", ondelete="CASCADE"))
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
