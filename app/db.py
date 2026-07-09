import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from app.config import DB_PATH

# Existing (pre-multitenancy) rows are backfilled to this workspace so nothing
# is orphaned. A user can reach that legacy data by entering "default" as their
# workspace token.
DEFAULT_WORKSPACE = "default"

SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL DEFAULT 'default',
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    voice_provider TEXT,
    voice_id TEXT,
    personality TEXT,
    purpose TEXT,
    seed INTEGER
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
    workspace_id TEXT NOT NULL DEFAULT 'default',
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

CREATE TABLE IF NOT EXISTS studio_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL DEFAULT 'default',
    kind TEXT NOT NULL,
    prompt TEXT NOT NULL,
    url TEXT NOT NULL,
    original_url TEXT,
    sha256 TEXT,
    model TEXT,
    quality TEXT,
    disclosure TEXT,
    cost_usd REAL,
    manifest_verified INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL DEFAULT 'default',
    character_id INTEGER,
    character_name TEXT,
    kind TEXT NOT NULL,
    prompt TEXT NOT NULL,
    model TEXT,
    duration INTEGER,
    aspect_ratio TEXT,
    url TEXT,
    original_url TEXT,
    sha256 TEXT,
    mime_type TEXT,
    cost_usd REAL,
    manifest_verified INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running',
    error TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audio_clips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL DEFAULT 'default',
    text TEXT NOT NULL,
    voice TEXT,
    url TEXT NOT NULL,
    sha256 TEXT,
    mime_type TEXT,
    model TEXT,
    cost_usd REAL,
    manifest_verified INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dialogues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL DEFAULT 'default',
    script TEXT NOT NULL,
    url TEXT NOT NULL,
    sha256 TEXT,
    mime_type TEXT,
    cost_usd REAL,
    manifest_verified INTEGER NOT NULL DEFAULT 0,
    participant_ids TEXT NOT NULL,
    participant_names TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL DEFAULT 'default',
    idea TEXT NOT NULL,
    format TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS batch_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL DEFAULT 'default',
    character_id INTEGER NOT NULL REFERENCES characters(id),
    mode TEXT NOT NULL,
    prompt TEXT NOT NULL,
    requested INTEGER NOT NULL,
    completed INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running',
    quality TEXT,
    model TEXT,
    disclosure TEXT,
    cost_estimate REAL,
    error TEXT,
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
    "ALTER TABLE characters ADD COLUMN personality TEXT",
    "ALTER TABLE characters ADD COLUMN purpose TEXT",
    "ALTER TABLE characters ADD COLUMN seed INTEGER",
    "ALTER TABLE assets ADD COLUMN batch_id INTEGER",
    # Multitenancy: scope every top-level table to a workspace.
    "ALTER TABLE characters ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'default'",
    "ALTER TABLE scenes ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'default'",
    "ALTER TABLE studio_images ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'default'",
    "ALTER TABLE videos ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'default'",
    "ALTER TABLE audio_clips ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'default'",
    "ALTER TABLE batch_jobs ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'default'",
    # Motion comics (panels + dialogue, no video model) reuse the videos
    # table via kind="motion_comic" — this carries their per-panel transcript.
    "ALTER TABLE videos ADD COLUMN script TEXT",
    # The seed actually used per image, for the transparency detail card —
    # separate from characters.seed, which can change later and would
    # otherwise misrepresent what an older image was really generated with.
    "ALTER TABLE assets ADD COLUMN seed INTEGER",
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
        # Ensure the legacy workspace exists so backfilled rows resolve.
        conn.execute(
            "INSERT OR IGNORE INTO workspaces (id, name, created_at) VALUES (?, ?, ?)",
            (DEFAULT_WORKSPACE, "Default", now()),
        )


# ── Workspaces (tenants) ─────────────────────────────────────────────────

def create_workspace(name: str) -> dict:
    workspace_id = uuid.uuid4().hex
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO workspaces (id, name, created_at) VALUES (?, ?, ?)",
            (workspace_id, name, now()),
        )
        return dict(conn.execute(
            "SELECT * FROM workspaces WHERE id = ?", (workspace_id,)
        ).fetchone())


def get_workspace(workspace_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM workspaces WHERE id = ?", (workspace_id,)
        ).fetchone()
        return dict(row) if row else None


# ── Characters ───────────────────────────────────────────────────────────

def create_character(
    workspace_id: str,
    name: str,
    description: str,
    personality: str | None = None,
    purpose: str | None = None,
    seed: int | None = None,
) -> dict:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO characters
               (workspace_id, name, description, created_at, personality, purpose, seed)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (workspace_id, name, description, now(), personality, purpose, seed),
        )
        character_id = cur.lastrowid
    return get_character(workspace_id, character_id)


def update_character(workspace_id: str, character_id: int, fields: dict) -> dict | None:
    allowed = {"name", "description", "personality", "purpose", "seed"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return get_character(workspace_id, character_id)
    with get_conn() as conn:
        assignments = ", ".join(f"{k} = ?" for k in updates)
        cur = conn.execute(
            f"UPDATE characters SET {assignments} WHERE id = ? AND workspace_id = ?",
            (*updates.values(), character_id, workspace_id),
        )
        if cur.rowcount == 0:
            return None
    return get_character(workspace_id, character_id)


def set_character_voice(workspace_id: str, character_id: int, voice_provider: str, voice_id: str) -> dict | None:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE characters SET voice_provider = ?, voice_id = ? WHERE id = ? AND workspace_id = ?",
            (voice_provider, voice_id, character_id, workspace_id),
        )
        if cur.rowcount == 0:
            return None
    return get_character(workspace_id, character_id)


def list_characters(workspace_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT characters.*,
                      (SELECT url FROM assets
                       WHERE assets.character_id = characters.id AND assets.kind = 'image'
                       ORDER BY assets.id DESC LIMIT 1) AS thumbnail_source_url
               FROM characters WHERE workspace_id = ? ORDER BY characters.id""",
            (workspace_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_character(workspace_id: str, character_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM characters WHERE id = ? AND workspace_id = ?",
            (character_id, workspace_id),
        ).fetchone()
        if row is None:
            return None
        character = dict(row)
        asset_rows = conn.execute(
            "SELECT * FROM assets WHERE character_id = ? ORDER BY id", (character_id,)
        ).fetchall()
        character["assets"] = [dict(a) for a in asset_rows]
        return character


def delete_character(workspace_id: str, character_id: int) -> bool:
    with get_conn() as conn:
        owned = conn.execute(
            "SELECT 1 FROM characters WHERE id = ? AND workspace_id = ?",
            (character_id, workspace_id),
        ).fetchone()
        if owned is None:
            return False
        conn.execute("DELETE FROM assets WHERE character_id = ?", (character_id,))
        cur = conn.execute("DELETE FROM characters WHERE id = ?", (character_id,))
        return cur.rowcount > 0


# ── Assets (inherit workspace via their character) ───────────────────────

def delete_asset(workspace_id: str, asset_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            """DELETE FROM assets WHERE id = ? AND character_id IN
               (SELECT id FROM characters WHERE workspace_id = ?)""",
            (asset_id, workspace_id),
        )
        return cur.rowcount > 0


def list_assets(workspace_id: str, kind: str | None = None) -> list[dict]:
    with get_conn() as conn:
        base = """SELECT assets.*, characters.name AS character_name
                  FROM assets JOIN characters ON characters.id = assets.character_id
                  WHERE characters.workspace_id = ?"""
        if kind is None:
            rows = conn.execute(base + " ORDER BY assets.id", (workspace_id,)).fetchall()
        else:
            rows = conn.execute(
                base + " AND assets.kind = ? ORDER BY assets.id", (workspace_id, kind)
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
    batch_id: int | None = None,
    seed: int | None = None,
) -> dict:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO assets
               (character_id, kind, url, sha256, mime_type, prompt, manifest_verified,
                created_at, disclosure, original_url, quality, cost_usd, model, batch_id, seed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                character_id, kind, url, sha256, mime_type, prompt,
                int(manifest_verified), now(), disclosure, original_url,
                quality, cost_usd, model, batch_id, seed,
            ),
        )
        row = conn.execute(
            "SELECT * FROM assets WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return dict(row)


# ── Scenes ───────────────────────────────────────────────────────────────

def create_scene(
    workspace_id: str,
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
               (workspace_id, prompt, url, original_url, sha256, model, disclosure, cost_usd,
                manifest_verified, participant_ids, participant_names, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                workspace_id, prompt, url, original_url, sha256, model, disclosure, cost_usd,
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


def list_scenes(workspace_id: str) -> list[dict]:
    import json

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM scenes WHERE workspace_id = ? ORDER BY id DESC", (workspace_id,)
        ).fetchall()
        out = []
        for row in rows:
            d = dict(row)
            d["participant_ids"] = json.loads(d["participant_ids"])
            d["participant_names"] = json.loads(d["participant_names"])
            out.append(d)
        return out


def get_scene(workspace_id: str, scene_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM scenes WHERE id = ? AND workspace_id = ?", (scene_id, workspace_id)
        ).fetchone()
        return _scene_row(conn, row["id"]) if row else None


def delete_scene(workspace_id: str, scene_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM scenes WHERE id = ? AND workspace_id = ?", (scene_id, workspace_id)
        )
        return cur.rowcount > 0


def create_dialogue(
    workspace_id: str,
    script: list[dict],
    url: str,
    sha256: str | None,
    mime_type: str | None,
    cost_usd: float | None,
    manifest_verified: bool,
    participant_ids: list[int],
    participant_names: list[str],
) -> dict:
    import json

    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO dialogues
               (workspace_id, script, url, sha256, mime_type, cost_usd,
                manifest_verified, participant_ids, participant_names, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                workspace_id, json.dumps(script), url, sha256, mime_type, cost_usd,
                int(manifest_verified), json.dumps(participant_ids),
                json.dumps(participant_names), now(),
            ),
        )
        return _dialogue_row(conn, cur.lastrowid)


def _dialogue_row(conn, dialogue_id: int) -> dict:
    import json

    row = dict(conn.execute("SELECT * FROM dialogues WHERE id = ?", (dialogue_id,)).fetchone())
    row["script"] = json.loads(row["script"])
    row["participant_ids"] = json.loads(row["participant_ids"])
    row["participant_names"] = json.loads(row["participant_names"])
    return row


def list_dialogues(workspace_id: str) -> list[dict]:
    import json

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM dialogues WHERE workspace_id = ? ORDER BY id DESC", (workspace_id,)
        ).fetchall()
        out = []
        for row in rows:
            d = dict(row)
            d["script"] = json.loads(d["script"])
            d["participant_ids"] = json.loads(d["participant_ids"])
            d["participant_names"] = json.loads(d["participant_names"])
            out.append(d)
        return out


def delete_dialogue(workspace_id: str, dialogue_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM dialogues WHERE id = ? AND workspace_id = ?", (dialogue_id, workspace_id)
        )
        return cur.rowcount > 0


# ── Studio images ────────────────────────────────────────────────────────

def create_studio_image(
    workspace_id: str,
    kind: str,
    prompt: str,
    url: str,
    original_url: str | None,
    sha256: str | None,
    model: str | None,
    quality: str | None,
    disclosure: str | None,
    cost_usd: float | None,
    manifest_verified: bool,
) -> dict:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO studio_images
               (workspace_id, kind, prompt, url, original_url, sha256, model, quality, disclosure,
                cost_usd, manifest_verified, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (workspace_id, kind, prompt, url, original_url, sha256, model, quality, disclosure,
             cost_usd, int(manifest_verified), now()),
        )
        return dict(conn.execute(
            "SELECT * FROM studio_images WHERE id = ?", (cur.lastrowid,)
        ).fetchone())


def list_studio_images(workspace_id: str, kind: str | None = None) -> list[dict]:
    with get_conn() as conn:
        if kind:
            rows = conn.execute(
                "SELECT * FROM studio_images WHERE workspace_id = ? AND kind = ? ORDER BY id DESC",
                (workspace_id, kind),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM studio_images WHERE workspace_id = ? ORDER BY id DESC",
                (workspace_id,),
            ).fetchall()
        return [dict(row) for row in rows]


def delete_studio_image(workspace_id: str, image_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM studio_images WHERE id = ? AND workspace_id = ?",
            (image_id, workspace_id),
        )
        return cur.rowcount > 0


# ── Videos ───────────────────────────────────────────────────────────────

def create_video(
    workspace_id: str,
    character_id: int | None,
    character_name: str | None,
    kind: str,
    prompt: str,
    model: str | None,
    duration: int | None,
    aspect_ratio: str | None,
) -> dict:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO videos
               (workspace_id, character_id, character_name, kind, prompt, model, duration,
                aspect_ratio, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (workspace_id, character_id, character_name, kind, prompt, model, duration,
             aspect_ratio, now()),
        )
        return dict(conn.execute(
            "SELECT * FROM videos WHERE id = ?", (cur.lastrowid,)
        ).fetchone())


def _video_row(row) -> dict:
    import json

    d = dict(row)
    d["script"] = json.loads(d["script"]) if d.get("script") else None
    return d


def get_video(workspace_id: str, video_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM videos WHERE id = ? AND workspace_id = ?", (video_id, workspace_id)
        ).fetchone()
        return _video_row(row) if row else None


def finish_video(video_id: int, *, status: str, url: str | None = None,
                 original_url: str | None = None, sha256: str | None = None,
                 mime_type: str | None = None, cost_usd: float | None = None,
                 manifest_verified: bool = False, error: str | None = None,
                 duration: float | None = None, script: list[dict] | None = None) -> None:
    import json

    with get_conn() as conn:
        if duration is not None or script is not None:
            conn.execute(
                """UPDATE videos SET status = ?, url = ?, original_url = ?, sha256 = ?,
                   mime_type = ?, cost_usd = ?, manifest_verified = ?, error = ?,
                   duration = COALESCE(?, duration), script = COALESCE(?, script)
                   WHERE id = ?""",
                (status, url, original_url, sha256, mime_type, cost_usd,
                 int(manifest_verified), error, duration,
                 json.dumps(script) if script is not None else None, video_id),
            )
        else:
            conn.execute(
                """UPDATE videos SET status = ?, url = ?, original_url = ?, sha256 = ?,
                   mime_type = ?, cost_usd = ?, manifest_verified = ?, error = ?
                   WHERE id = ?""",
                (status, url, original_url, sha256, mime_type, cost_usd,
                 int(manifest_verified), error, video_id),
            )


def list_videos(workspace_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM videos WHERE workspace_id = ? ORDER BY id DESC", (workspace_id,)
        ).fetchall()
        return [_video_row(row) for row in rows]


def delete_video(workspace_id: str, video_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM videos WHERE id = ? AND workspace_id = ?", (video_id, workspace_id)
        )
        return cur.rowcount > 0


# ── Audio clips ──────────────────────────────────────────────────────────

def create_audio_clip(
    workspace_id: str,
    text: str,
    voice: str | None,
    url: str,
    sha256: str | None,
    mime_type: str | None,
    model: str | None,
    cost_usd: float | None,
    manifest_verified: bool,
) -> dict:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO audio_clips
               (workspace_id, text, voice, url, sha256, mime_type, model, cost_usd,
                manifest_verified, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (workspace_id, text, voice, url, sha256, mime_type, model, cost_usd,
             int(manifest_verified), now()),
        )
        return dict(conn.execute(
            "SELECT * FROM audio_clips WHERE id = ?", (cur.lastrowid,)
        ).fetchone())


def list_audio_clips(workspace_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM audio_clips WHERE workspace_id = ? ORDER BY id DESC", (workspace_id,)
        ).fetchall()
        return [dict(row) for row in rows]


def delete_audio_clip(workspace_id: str, clip_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM audio_clips WHERE id = ? AND workspace_id = ?", (clip_id, workspace_id)
        )
        return cur.rowcount > 0


# ── Batch jobs ───────────────────────────────────────────────────────────

def create_script(workspace_id: str, idea: str, fmt: str, content: str) -> dict:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO scripts (workspace_id, idea, format, content, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (workspace_id, idea, fmt, content, now()),
        )
        return dict(conn.execute(
            "SELECT * FROM scripts WHERE id = ?", (cur.lastrowid,)
        ).fetchone())


def list_scripts(workspace_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM scripts WHERE workspace_id = ? ORDER BY id DESC", (workspace_id,)
        ).fetchall()
        return [dict(row) for row in rows]


def delete_script(workspace_id: str, script_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM scripts WHERE id = ? AND workspace_id = ?", (script_id, workspace_id)
        )
        return cur.rowcount > 0


def create_batch(
    workspace_id: str,
    character_id: int,
    mode: str,
    prompt: str,
    requested: int,
    quality: str | None,
    model: str | None,
    disclosure: str | None,
    cost_estimate: float | None,
) -> dict:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO batch_jobs
               (workspace_id, character_id, mode, prompt, requested, quality, model, disclosure,
                cost_estimate, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (workspace_id, character_id, mode, prompt, requested, quality, model, disclosure,
             cost_estimate, now()),
        )
        return dict(conn.execute(
            "SELECT * FROM batch_jobs WHERE id = ?", (cur.lastrowid,)
        ).fetchone())


def get_batch(batch_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM batch_jobs WHERE id = ?", (batch_id,)
        ).fetchone()
        return dict(row) if row else None


def bump_batch(batch_id: int, *, completed: int = 0, failed: int = 0) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE batch_jobs SET completed = completed + ?, failed = failed + ? WHERE id = ?",
            (completed, failed, batch_id),
        )


def finish_batch(batch_id: int, status: str, error: str | None = None) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE batch_jobs SET status = ?, error = ? WHERE id = ?",
            (status, error, batch_id),
        )
