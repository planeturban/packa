"""
Persistent slave identity.

If slave.id is not set in the config file, the ID is looked up in the slave DB.
If it has never been set there either, a UUID is generated and stored for future runs.
"""

import uuid

from sqlalchemy import text

from .database import engine

_CREATE = """
CREATE TABLE IF NOT EXISTS slave_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""
_SELECT = "SELECT value FROM slave_settings WHERE key = 'slave_id'"
_INSERT = "INSERT INTO slave_settings (key, value) VALUES ('slave_id', :v)"


def _ensure_table(conn) -> None:
    conn.execute(text(_CREATE))


def get_stored_slave_id() -> str | None:
    """Return the slave ID stored in the DB, or None if not set."""
    with engine.connect() as conn:
        _ensure_table(conn)
        row = conn.execute(text(_SELECT)).fetchone()
        return row[0] if row else None


def get_or_create_slave_id() -> str:
    """Return the stored slave ID, generating and persisting a new UUID if absent."""
    with engine.connect() as conn:
        _ensure_table(conn)
        row = conn.execute(text(_SELECT)).fetchone()
        if row:
            return row[0]
        new_id = str(uuid.uuid4())
        conn.execute(text(_INSERT), {"v": new_id})
        conn.commit()
        return new_id
