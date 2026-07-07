import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from app.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    voice_provider TEXT,
    voice_id TEXT
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
    created_at TEXT NOT NULL,
    disclosure TEXT,
    original_url TEXT,
    quality TEXT,
    cost_usd REAL,
    model TEXT
);

CREATE TABLE IF NOT EXISTS scenes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt TEXT NOT NULL,
    url TEXT NOT NULL,
    original_url TEXT,
    sha256 TEXT,
    model TEXT,
    disclosure TEXT,
    cost_usd REAL,
    manifest_verified INTEGER NOT NULL DEFAULT 0,
    participant_ids TEXT NOT NULL,
    participant_names TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

MIGRATIONS = (
    "ALTER TABLE assets ADD COLUMN disclosure TEXT",
    "ALTER TABLE assets ADD COLUMN original_url TEXT",
    "ALTER TABLE assets ADD COLUMN quality TEXT",
    "ALTER TABLE assets ADD COLUMN cost_usd REAL",
    "ALTER TABLE assets ADD COLUMN model TEXT",
    "ALTER TABLE characters ADD COLUMN voice_provider TEXT",
    "ALTER TABLE characters ADD COLUMN voice_id TEXT",
)


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
        for migration in MIGRATIONS:
            try:
                conn.execute(migration)
            except sqlite3.OperationalError:
                pass  # column already exists


def create_character(name: str, description: str) -> dict:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO characters (name, description, created_at) VALUES (?, ?, ?)",
            (name, description, now()),
        )
        character_id = cur.lastrowid
    return get_character(character_id)


def set_character_voice(character_id: int, voice_provider: str, voice_id: str) -> dict | None:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE characters SET voice_provider = ?, voice_id = ? WHERE id = ?",
            (voice_provider, voice_id, character_id),
        )
        if cur.rowcount == 0:
            return None
    return get_character(character_id)


def list_characters() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT characters.*,
                      (SELECT url FROM assets
                       WHERE assets.character_id = characters.id AND assets.kind = 'image'
                       ORDER BY assets.id DESC LIMIT 1) AS thumbnail_source_url
               FROM characters ORDER BY characters.id"""
        ).fetchall()
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


def delete_character(character_id: int) -> bool:
    with get_conn() as conn:
        conn.execute("DELETE FROM assets WHERE character_id = ?", (character_id,))
        cur = conn.execute("DELETE FROM characters WHERE id = ?", (character_id,))
        return cur.rowcount > 0


def delete_asset(asset_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
        return cur.rowcount > 0


def list_assets(kind: str | None = None) -> list[dict]:
    with get_conn() as conn:
        if kind is None:
            rows = conn.execute(
                """SELECT assets.*, characters.name AS character_name
                   FROM assets JOIN characters ON characters.id = assets.character_id
                   ORDER BY assets.id"""
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT assets.*, characters.name AS character_name
                   FROM assets JOIN characters ON characters.id = assets.character_id
                   WHERE assets.kind = ?
                   ORDER BY assets.id""",
                (kind,),
            ).fetchall()
        return [dict(row) for row in rows]


def add_asset(
    character_id: int,
    kind: str,
    url: str,
    sha256: str | None,
    mime_type: str | None,
    prompt: str,
    manifest_verified: bool,
    disclosure: str | None = None,
    original_url: str | None = None,
    quality: str | None = None,
    cost_usd: float | None = None,
    model: str | None = None,
) -> dict:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO assets
               (character_id, kind, url, sha256, mime_type, prompt, manifest_verified,
                created_at, disclosure, original_url, quality, cost_usd, model)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                character_id,
                kind,
                url,
                sha256,
                mime_type,
                prompt,
                int(manifest_verified),
                now(),
                disclosure,
                original_url,
                quality,
                cost_usd,
                model,
            ),
        )
        row = conn.execute(
            "SELECT * FROM assets WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return dict(row)


def create_scene(
    prompt: str,
    url: str,
    original_url: str | None,
    sha256: str | None,
    model: str | None,
    disclosure: str | None,
    cost_usd: float | None,
    manifest_verified: bool,
    participant_ids: list[int],
    participant_names: list[str],
) -> dict:
    import json

    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO scenes
               (prompt, url, original_url, sha256, model, disclosure, cost_usd,
                manifest_verified, participant_ids, participant_names, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                prompt, url, original_url, sha256, model, disclosure, cost_usd,
                int(manifest_verified), json.dumps(participant_ids),
                json.dumps(participant_names), now(),
            ),
        )
        return _scene_row(conn, cur.lastrowid)


def _scene_row(conn, scene_id: int) -> dict:
    import json

    row = dict(conn.execute("SELECT * FROM scenes WHERE id = ?", (scene_id,)).fetchone())
    row["participant_ids"] = json.loads(row["participant_ids"])
    row["participant_names"] = json.loads(row["participant_names"])
    return row


def list_scenes() -> list[dict]:
    import json

    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM scenes ORDER BY id DESC").fetchall()
        out = []
        for row in rows:
            d = dict(row)
            d["participant_ids"] = json.loads(d["participant_ids"])
            d["participant_names"] = json.loads(d["participant_names"])
            out.append(d)
        return out


def delete_scene(scene_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM scenes WHERE id = ?", (scene_id,))
        return cur.rowcount > 0
