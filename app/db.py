import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .diagnostics import log_diagnostic as _log_diagnostic

# Allow the DB location to be overridden via env (Docker volume in prod).
DB_PATH = Path(os.environ.get("PRASHNA_DB_PATH") or
               Path(__file__).resolve().parent.parent / "prashna.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    future=True,
)

# Per-connection SQLite pragmas:
# - foreign_keys=ON: SQLite ignores ON DELETE CASCADE / FK constraints unless
#   set per connection; without it orphaned rows are possible.
# - journal_mode=WAL: readers don't block the single writer (and vice versa),
#   which matters under a live quiz where many participants submit at once.
# - busy_timeout=5000: a writer waits up to 5s for the lock instead of
#   erroring immediately with "database is locked".
# - synchronous=NORMAL: safe with WAL, much less fsync stalling under load.
@event.listens_for(Engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _conn_record):
    try:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()
    except Exception:
        # Other dialects (Postgres etc.) don't need this; ignore quietly.
        pass


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from . import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _apply_additive_migrations()


def _apply_additive_migrations(*, bind: Engine | None = None):
    """Bridge gap between `create_all()` and additive column changes.

    Prashna intentionally has no Alembic. `create_all` only creates
    missing tables, not missing columns or indexes on existing tables. For
    each supported additive change we introduce post-launch, add it here so
    operators don't have to delete `prashna.db` on every model addition.
    """
    target = bind or engine
    additive = [
        # (table, column, ddl-snippet)
        ("users", "session_version", "INTEGER NOT NULL DEFAULT 1"),
        ("users", "github_id", "INTEGER"),
        ("sessions", "participant_base_url", "VARCHAR(500)"),
        ("participants", "email", "VARCHAR(254)"),
        ("participants", "contact_number", "VARCHAR(40)"),
        ("participants", "organization", "VARCHAR(120)"),
        ("participants", "role", "VARCHAR(120)"),
        ("participants", "linkedin_url", "VARCHAR(500)"),
        ("participants", "photo_url", "VARCHAR(500)"),
        ("participants", "current_work", "TEXT"),
        ("participants", "learning_goal", "TEXT"),
        ("quiz_questions", "graded", "BOOLEAN NOT NULL DEFAULT 1"),
        ("quiz_version_questions", "graded", "BOOLEAN NOT NULL DEFAULT 1"),
        ("quiz_runs", "show_live_counts", "BOOLEAN NOT NULL DEFAULT 0"),
    ]
    # Indexes to (re)create on existing DBs. `ALTER TABLE ADD COLUMN` can't
    # carry UNIQUE/partial-index constraints; create those separately.
    indexes = [
        ("ix_users_github_id", "users", ["github_id"], True, None),
        (
            "uq_session_live_run",
            "quiz_runs",
            ["session_id"],
            True,
            "status = 'live'",
        ),
        ("ix_qsub_run_question", "quiz_submissions", ["quiz_run_id", "question_id"], False, None),
    ]
    with target.begin() as conn:
        tables = {
            row[0]
            for row in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for table, column, ddl in additive:
            if table not in tables:
                continue
            cols = {row[1] for row in conn.exec_driver_sql(
                f"PRAGMA table_info({table})").fetchall()}
            if column not in cols:
                conn.exec_driver_sql(
                    f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
                _log_diagnostic(
                    "db.migration",
                    action="add_column",
                    outcome="success",
                    table=table,
                    column=column,
                )
        for name, table, columns, unique, where in indexes:
            if table not in tables:
                continue
            existing_cols = {
                row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")
            }
            if not set(columns).issubset(existing_cols):
                continue
            uniq = "UNIQUE " if unique else ""
            where_sql = f" WHERE {where}" if where else ""
            conn.exec_driver_sql(
                f"CREATE {uniq}INDEX IF NOT EXISTS {name} ON {table} ({', '.join(columns)}){where_sql}")
            _log_diagnostic(
                "db.migration",
                action="create_index",
                outcome="success",
                table=table,
                index=name,
            )
