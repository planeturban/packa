from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from shared.base import Base

DATABASE_URL = "sqlite:///./master.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _migrate() -> None:
    """Add columns introduced after initial schema creation."""
    with engine.connect() as conn:
        for col, typedef in [("file_size", "INTEGER"), ("cancel_reason", "VARCHAR(32)")]:
            try:
                conn.execute(text(f"ALTER TABLE file_records ADD COLUMN {col} {typedef}"))
                conn.commit()
            except Exception:
                pass  # column already exists


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
