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
    password_hash: Mapped[str] = mapped_column(String(255))
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    questions: Mapped[list["Question"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    quiz_runs: Mapped[list["QuizRun"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    participants: Mapped[list["Participant"]] = relationship(back_populates="session", cascade="all, delete-orphan")


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


# ---------- Q&A ----------

class Question(Base):
    __tablename__ = "questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Soft-remove: a removed question is hidden from participants but kept for audit / preserve-session-data.
    removed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    session: Mapped[Session] = relationship(back_populates="questions")
    participant: Mapped[Participant] = relationship()
    votes: Mapped[list["QuestionVote"]] = relationship(back_populates="question", cascade="all, delete-orphan")


class QuestionVote(Base):
    __tablename__ = "question_votes"
    __table_args__ = (UniqueConstraint("question_id", "participant_id", name="uq_qvote"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    question: Mapped[Question] = relationship(back_populates="votes")


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

    items: Mapped[list["QuizItem"]] = relationship(
        back_populates="quiz",
        cascade="all, delete-orphan",
        order_by="QuizItem.order_index",
    )
    versions: Mapped[list["QuizVersion"]] = relationship(
        back_populates="quiz",
        cascade="all, delete-orphan",
        order_by="QuizVersion.version_no",
    )


class QuizItem(Base):
    __tablename__ = "quiz_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    qtype: Mapped[str] = mapped_column(String(10), default="single")  # "single" | "multi"
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    quiz: Mapped[Quiz] = relationship(back_populates="items")
    options: Mapped[list["QuizOption"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="QuizOption.order_index",
    )


class QuizOption(Base):
    __tablename__ = "quiz_options"
    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("quiz_items.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    item: Mapped[QuizItem] = relationship(back_populates="options")


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
    items: Mapped[list["QuizVersionItem"]] = relationship(
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="QuizVersionItem.order_index",
    )


class QuizVersionItem(Base):
    __tablename__ = "quiz_version_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("quiz_versions.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    qtype: Mapped[str] = mapped_column(String(10), default="single")
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    version: Mapped[QuizVersion] = relationship(back_populates="items")
    options: Mapped[list["QuizVersionOption"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="QuizVersionOption.order_index",
    )


class QuizVersionOption(Base):
    __tablename__ = "quiz_version_options"
    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("quiz_version_items.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    item: Mapped[QuizVersionItem] = relationship(back_populates="options")


# ---------- quiz runs (one playthrough of a frozen quiz inside a session) ----------

class QuizRun(Base):
    """One playthrough of a QuizVersion inside a Session."""
    __tablename__ = "quiz_runs"
    __table_args__ = (
        # Enforce "at most one live QuizRun per Session" at the storage layer.
        # Partial unique index — SQLite & Postgres both support this syntax.
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
    current_item_idx: Mapped[int] = mapped_column(Integer, default=0)
    reveal_current: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    session: Mapped[Session] = relationship(back_populates="quiz_runs")
    quiz_version: Mapped[QuizVersion] = relationship()
    responses: Mapped[list["QuizResponse"]] = relationship(cascade="all, delete-orphan")


class QuizResponse(Base):
    __tablename__ = "quiz_responses"
    __table_args__ = (
        UniqueConstraint("quiz_run_id", "item_id", "option_id", "participant_id", name="uq_qresp"),
        # Tally queries filter by (quiz_run_id, item_id); back this with an index.
        Index("ix_qresp_run_item", "quiz_run_id", "item_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_run_id: Mapped[int] = mapped_column(ForeignKey("quiz_runs.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("quiz_version_items.id", ondelete="CASCADE"))
    option_id: Mapped[int] = mapped_column(ForeignKey("quiz_version_options.id", ondelete="CASCADE"))
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
