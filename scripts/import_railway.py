"""Import a workspace exported from another deployment into this one.

Written for the Railway → Oracle move, but it works for any instance-to-
instance transfer: the media itself already lives in B2 and is shared between
deployments, so only the metadata rows need to travel.

Produce the export by reading the old deployment's own API — every column the
database holds is exposed there. Then pipe it in on the target host:

    cat backup.json | docker compose exec -T app python /app/scripts/import_railway.py

Rows are inserted with *new* ids and the references are remapped, so this is
safe against a database that already holds unrelated characters. It appends;
it never deletes.
"""

import json
import sqlite3
import sys

TARGET_WORKSPACE = "default"
DB_PATH = "/data/character_vault.db"


def _columns(db: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in db.execute(f"PRAGMA table_info({table})")]


def _insert(db: sqlite3.Connection, table: str, row: dict, extra: dict | None = None) -> int:
    """Insert `row` into `table`, keeping only keys that are real columns.

    The export carries computed fields no table has a place for (signed_url,
    nested assets), and `id` has to go so SQLite assigns a fresh one — the
    source ids collide with whatever is already here.
    """
    columns = _columns(db, table)
    values = {k: v for k, v in row.items() if k in columns and k != "id"}
    if extra:
        values.update({k: v for k, v in extra.items() if k in columns})
    # The API hands back JSON columns already decoded — a scene's character_ids
    # and a motion comic's script arrive as real lists. sqlite3 refuses to bind
    # those, so put them back the way the column stores them.
    values = {
        k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
        for k, v in values.items()
    }
    keys = list(values)
    placeholders = ",".join("?" * len(keys))
    cur = db.execute(
        f"INSERT INTO {table} ({','.join(keys)}) VALUES ({placeholders})",
        [values[k] for k in keys],
    )
    return cur.lastrowid


def main() -> None:
    data = json.load(sys.stdin)
    db = sqlite3.connect(DB_PATH)

    # Characters first — everything else points at them.
    id_map: dict[int, int] = {}
    for character in data.get("characters", []):
        id_map[character["id"]] = _insert(
            db, "characters", character, {"workspace_id": TARGET_WORKSPACE}
        )
    counts = {"characters": len(id_map)}

    # Assets hang off a character; skip any whose character didn't come along.
    counts["assets"] = 0
    for asset in data.get("assets", []):
        source = asset.get("character_id")
        if source in id_map:
            _insert(db, "assets", asset, {"character_id": id_map[source]})
            counts["assets"] += 1

    for key, table in (("scenes", "scenes"), ("scripts", "scripts"), ("dialogues", "dialogues")):
        counts[key] = 0
        for row in data.get(key, []):
            try:
                _insert(db, table, row, {"workspace_id": TARGET_WORKSPACE})
                counts[key] += 1
            except sqlite3.Error as exc:
                print(f"{table}: row skipped ({exc})", file=sys.stderr)

    # A video may reference a character, or none at all for text-to-video.
    counts["videos"] = 0
    for video in data.get("videos", []):
        _insert(db, "videos", video, {
            "workspace_id": TARGET_WORKSPACE,
            "character_id": id_map.get(video.get("character_id")),
        })
        counts["videos"] += 1

    db.commit()

    print("imported:", counts)
    print(f"\ncharacters now in '{TARGET_WORKSPACE}':")
    for row in db.execute(
        "SELECT id, name, description FROM characters WHERE workspace_id = ? ORDER BY id",
        (TARGET_WORKSPACE,),
    ):
        print(f"  {row[0]:>3}  {row[1]}  —  {(row[2] or '')[:60]}")


if __name__ == "__main__":
    main()
