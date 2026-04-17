"""
Key-value settings stored in the slave_settings table.

Reuses the same table created by identity.py.
"""

from sqlalchemy import text

from .database import engine

_CREATE = """
CREATE TABLE IF NOT EXISTS slave_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""


def get_setting(key: str) -> str | None:
    with engine.connect() as conn:
        conn.execute(text(_CREATE))
        row = conn.execute(
            text("SELECT value FROM slave_settings WHERE key = :k"), {"k": key}
        ).fetchone()
        return row[0] if row else None


def set_setting(key: str, value: str) -> None:
    with engine.connect() as conn:
        conn.execute(text(_CREATE))
        conn.execute(
            text("""
                INSERT INTO slave_settings (key, value) VALUES (:k, :v)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """),
            {"k": key, "v": value},
        )
        conn.commit()
