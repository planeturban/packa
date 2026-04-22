"""Persistent key-value store for web state (web.db)."""
from sqlalchemy import create_engine, text

_engine = create_engine("sqlite:///web.db", connect_args={"check_same_thread": False})

_CREATE = """
CREATE TABLE IF NOT EXISTS web_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""


def _conn():
    return _engine.begin()


def get_setting(key: str) -> str | None:
    with _conn() as conn:
        conn.execute(text(_CREATE))
        row = conn.execute(text("SELECT value FROM web_settings WHERE key = :k"), {"k": key}).fetchone()
        return row[0] if row else None


def set_setting(key: str, value: str) -> None:
    with _conn() as conn:
        conn.execute(text(_CREATE))
        conn.execute(
            text("INSERT INTO web_settings (key, value) VALUES (:k, :v) ON CONFLICT(key) DO UPDATE SET value = excluded.value"),
            {"k": key, "v": value},
        )
