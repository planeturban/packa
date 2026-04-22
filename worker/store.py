"""
Persistent key-value store for worker state.

Backed by the `worker_settings` table (raw SQL, no ORM).
Provides general get/set and worker-ID management.
"""

from sqlalchemy import text

from .database import engine

_CREATE = """
CREATE TABLE IF NOT EXISTS worker_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""


def _ensure_table(conn) -> None:
    conn.execute(text(_CREATE))


def get_setting(key: str) -> str | None:
    with engine.begin() as conn:
        _ensure_table(conn)
        row = conn.execute(
            text("SELECT value FROM worker_settings WHERE key = :k"), {"k": key}
        ).fetchone()
        return row[0] if row else None


def set_setting(key: str, value: str) -> None:
    with engine.begin() as conn:
        _ensure_table(conn)
        conn.execute(
            text("""
                INSERT INTO worker_settings (key, value) VALUES (:k, :v)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """),
            {"k": key, "v": value},
        )


def get_stored_worker_id() -> str | None:
    """Return the worker ID stored in the DB, or None if not set."""
    return get_setting("worker_id")


def get_settings_with_prefix(prefix: str) -> dict[str, str]:
    """Return all key/value pairs whose key starts with prefix."""
    with engine.begin() as conn:
        _ensure_table(conn)
        rows = conn.execute(
            text("SELECT key, value FROM worker_settings WHERE key LIKE :p"),
            {"p": f"{prefix}%"},
        ).fetchall()
    return {row[0]: row[1] for row in rows}


def delete_setting(key: str) -> bool:
    """Delete a key; return True if it existed."""
    with engine.begin() as conn:
        _ensure_table(conn)
        result = conn.execute(
            text("DELETE FROM worker_settings WHERE key = :k"), {"k": key}
        )
        return result.rowcount > 0
