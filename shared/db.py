"""
Shared database helpers — used by master and slave to create their engines,
session factories, and FastAPI dependency callables.
"""

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# Columns added after the initial schema — applied via ALTER TABLE on startup.
_MIGRATE_COLS = [
    ("file_size", "INTEGER"),
    ("cancel_reason", "VARCHAR(32)"),
    ("encoder", "VARCHAR(64)"),
    ("avg_fps", "FLOAT"),
    ("avg_speed", "FLOAT"),
    ("duplicate_of_id", "INTEGER"),
]


def make_engine(url: str):
    return create_engine(url, connect_args={"check_same_thread": False})


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


def make_get_db(session_factory: sessionmaker):
    """Return a FastAPI dependency callable for the given session factory."""
    def get_db() -> Generator[Session, None, None]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()
    return get_db
