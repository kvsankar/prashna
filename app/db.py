import os
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Allow the DB location to be overridden via env (Docker volume in prod).
DB_PATH = Path(os.environ.get("PRASHNA_DB_PATH") or
               Path(__file__).resolve().parent.parent / "prashna.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    future=True,
)


# SQLite ignores ON DELETE CASCADE / FK constraints unless this PRAGMA is set
# per connection. Without it, partial DB-level integrity is lost and orphaned
# rows are possible on direct/bulk operations.
@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_conn, _conn_record):
    try:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
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


def _apply_additive_migrations():
    """Bridge gap between `create_all()` and additive column changes.

    Prashna intentionally has no Alembic. `create_all` only creates
    missing tables, not missing columns. For each additive column we
    introduce post-launch, add an `ALTER TABLE … ADD COLUMN` here so
    operators don't have to delete `prashna.db` on every model change.
    """
    additive = [
        # (table, column, ddl-snippet)
        ("users", "session_version", "INTEGER NOT NULL DEFAULT 1"),
        ("users", "github_id", "INTEGER"),
    ]
    # Unique indexes to (re)create on existing DBs — `ALTER TABLE ADD COLUMN`
    # can't carry a UNIQUE constraint, so back it with an index. SQLite treats
    # NULLs as distinct, so existing password-only admins (github_id NULL) are
    # unaffected. Matches the name `create_all` uses for the mapped column.
    indexes = [
        ("ix_users_github_id", "users", "github_id", True),
    ]
    with engine.begin() as conn:
        for table, column, ddl in additive:
            cols = {row[1] for row in conn.exec_driver_sql(
                f"PRAGMA table_info({table})").fetchall()}
            if column not in cols:
                conn.exec_driver_sql(
                    f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        for name, table, column, unique in indexes:
            uniq = "UNIQUE " if unique else ""
            conn.exec_driver_sql(
                f"CREATE {uniq}INDEX IF NOT EXISTS {name} ON {table} ({column})")
