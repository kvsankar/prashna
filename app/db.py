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
