from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


def now() -> datetime:
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    mod_key: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    questions: Mapped[list["Question"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    quiz_sessions: Mapped[list["QuizSession"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class Question(Base):
    __tablename__ = "questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    author_token: Mapped[str] = mapped_column(String(64))
    author_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    session: Mapped[Session] = relationship(back_populates="questions")
    votes: Mapped[list["QuestionVote"]] = relationship(back_populates="question", cascade="all, delete-orphan")


class QuestionVote(Base):
    __tablename__ = "question_votes"
    __table_args__ = (UniqueConstraint("question_id", "voter_token", name="uq_qvote"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    voter_token: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    question: Mapped[Question] = relationship(back_populates="votes")


class Quiz(Base):
    __tablename__ = "quizzes"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(10), default="draft")  # "draft" | "ready"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    questions: Mapped[list["QuizQuestion"]] = relationship(
        back_populates="quiz",
        cascade="all, delete-orphan",
        order_by="QuizQuestion.order_index",
    )


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    qtype: Mapped[str] = mapped_column(String(10), default="single")  # "single" | "multi"
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    quiz: Mapped[Quiz] = relationship(back_populates="questions")
    options: Mapped[list["QuizOption"]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="QuizOption.order_index",
    )


class QuizOption(Base):
    __tablename__ = "quiz_options"
    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("quiz_questions.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    question: Mapped[QuizQuestion] = relationship(back_populates="options")


class QuizSession(Base):
    """Instance of a Quiz running inside a Session."""
    __tablename__ = "quiz_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|live|closed
    current_question_idx: Mapped[int] = mapped_column(Integer, default=0)
    reveal_results: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    session: Mapped[Session] = relationship(back_populates="quiz_sessions")
    quiz: Mapped[Quiz] = relationship()
    responses: Mapped[list["QuizResponse"]] = relationship(cascade="all, delete-orphan")


class QuizResponse(Base):
    __tablename__ = "quiz_responses"
    __table_args__ = (
        UniqueConstraint("quiz_session_id", "question_id", "option_id", "voter_token", name="uq_qresp"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_session_id: Mapped[int] = mapped_column(ForeignKey("quiz_sessions.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("quiz_questions.id", ondelete="CASCADE"))
    option_id: Mapped[int] = mapped_column(ForeignKey("quiz_options.id", ondelete="CASCADE"))
    voter_token: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
