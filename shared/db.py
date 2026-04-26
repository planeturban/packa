"""
Shared database helpers — used by master and worker to create their engines,
session factories, and FastAPI dependency callables.
"""

from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

# Columns added after the initial schema — applied via ALTER TABLE on startup.
_MIGRATE_COLS = [
    ("file_size", "INTEGER"),
    ("cancel_reason", "VARCHAR(32)"),
    ("cancel_detail", "VARCHAR(128)"),
    ("discard_reason", "VARCHAR(32)"),
    ("encoder", "VARCHAR(64)"),
    ("avg_fps", "FLOAT"),
    ("avg_speed", "FLOAT"),
    ("duplicate_of_id", "INTEGER"),
    ("width", "INTEGER"),
    ("height", "INTEGER"),
    ("bitrate", "INTEGER"),
    ("duration", "REAL"),
    ("force_encode", "INTEGER NOT NULL DEFAULT 0"),
    ("ffmpeg_cmd", "VARCHAR(2048)"),
    ("ffmpeg_stderr", "VARCHAR(4096)"),
    ("master_synced", "INTEGER NOT NULL DEFAULT 1"),
]


def make_engine(url: str):
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": 15},
        poolclass=NullPool,
    )

    @event.listens_for(engine, "connect")
    def _set_wal(conn, _):
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")

    return engine


def make_session_factory(engine) -> sessionmaker:
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def migrate(engine) -> None:
    """Add columns introduced after initial schema creation (idempotent)."""
    with engine.connect() as conn:
        for col, typedef in _MIGRATE_COLS:
            try:
                conn.execute(text(f"ALTER TABLE file_records ADD COLUMN {col} {typedef}"))
                conn.commit()
            except Exception:
                pass  # column already exists

        # Rename slave_id → worker_id (SQLite 3.25+)
        try:
            conn.execute(text("ALTER TABLE file_records RENAME COLUMN slave_id TO worker_id"))
            conn.commit()
        except Exception:
            pass  # already renamed or column doesn't exist


def make_get_db(session_factory: sessionmaker):
    """Return a FastAPI dependency callable for the given session factory."""
    def get_db() -> Generator[Session, None, None]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()
    return get_db
