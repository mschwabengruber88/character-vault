import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from app.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL REFERENCES characters(id),
    kind TEXT NOT NULL CHECK (kind IN ('image', 'voice')),
    url TEXT NOT NULL,
    sha256 TEXT,
    mime_type TEXT,
    prompt TEXT NOT NULL,
    manifest_verified INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def create_character(name: str, description: str) -> dict:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO characters (name, description, created_at) VALUES (?, ?, ?)",
            (name, description, now()),
        )
        character_id = cur.lastrowid
    return get_character(character_id)


def list_characters() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM characters ORDER BY id").fetchall()
        return [dict(row) for row in rows]


def get_character(character_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM characters WHERE id = ?", (character_id,)
        ).fetchone()
        if row is None:
            return None
        character = dict(row)
        asset_rows = conn.execute(
            "SELECT * FROM assets WHERE character_id = ? ORDER BY id", (character_id,)
        ).fetchall()
        character["assets"] = [dict(a) for a in asset_rows]
        return character


def add_asset(
    character_id: int,
    kind: str,
    url: str,
    sha256: str | None,
    mime_type: str | None,
    prompt: str,
    manifest_verified: bool,
) -> dict:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO assets
               (character_id, kind, url, sha256, mime_type, prompt, manifest_verified, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                character_id,
                kind,
                url,
                sha256,
                mime_type,
                prompt,
                int(manifest_verified),
                now(),
            ),
        )
        row = conn.execute(
            "SELECT * FROM assets WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return dict(row)
