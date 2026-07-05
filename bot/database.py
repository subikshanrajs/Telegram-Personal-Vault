import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import DB_PATH, OWNER_ID

# --- Series/episode auto-grouping ------------------------------------------------
# Heuristic: strip common episode/quality markers from a filename to derive a
# shared "collection" key so e.g. "Show.S01E01.mkv" and "Show.S01E02.mkv" group
# together. Imperfect by nature — override any file's grouping with /collection.

_EPISODE_PATTERNS = [
    r"\bS\d{1,2}E\d{1,3}\b",
    r"\bSeason\s*\d{1,3}\b",
    r"\bEp(?:isode)?\.?\s*\d{1,4}\b",
    r"\bE\d{1,4}\b",
    r"\bPart\s*\d{1,3}\b",
    r"\b\d{1,3}\s*of\s*\d{1,3}\b",
    r"\(\d{4}\)",
    r"\[\d{4}\]",
    r"\b\d{3,4}p\b",
    r"\b(x264|x265|HEVC|WEBRip|WEB-DL|BluRay|HDRip|HDTV)\b",
]


def derive_collection(file_name: str):
    base = os.path.splitext(file_name)[0]
    cleaned = base
    matched = False
    for pat in _EPISODE_PATTERNS:
        cleaned, n = re.subn(pat, " ", cleaned, flags=re.IGNORECASE)
        if n:
            matched = True
    cleaned = re.sub(r"[._]+", " ", cleaned)
    cleaned = re.sub(r"[\-\s]{2,}", " ", cleaned)
    # strip a lone trailing number left over from naive "Name 1", "Name 2" naming
    cleaned, n2 = re.subn(r"\s+\d{1,3}\s*$", "", cleaned)
    if n2:
        matched = True
    cleaned = cleaned.strip(" -_.")
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    # Only call it a collection if we actually found episode/sequence evidence —
    # otherwise every one-off file would form a "collection of one".
    if not matched or len(cleaned) < 3:
        return None
    return cleaned


def _ensure_column(conn, table, column, coldef):
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coldef}")


def _get_or_create_collection(conn, name):
    if not name:
        return None
    row = conn.execute(
        "SELECT id FROM collections WHERE name = ? COLLATE NOCASE", (name,)
    ).fetchone()
    if row:
        return row[0]
    cur = conn.execute("INSERT INTO collections (name) VALUES (?)", (name,))
    return cur.lastrowid


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")

    files_table_existed = (
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='files'"
        ).fetchone()
        is not None
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS collections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL,
            file_type TEXT NOT NULL,
            file_size INTEGER,
            telegram_file_id TEXT,
            telegram_unique_id TEXT,
            channel_message_id INTEGER NOT NULL,
            caption TEXT,
            tags TEXT,
            uploaded_by INTEGER,
            upload_date TEXT NOT NULL,
            collection_id INTEGER REFERENCES collections(id)
        )
        """
    )
    _ensure_column(conn, "files", "collection_id", "INTEGER REFERENCES collections(id)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS allowed_users (
            user_id INTEGER PRIMARY KEY,
            is_owner INTEGER NOT NULL DEFAULT 0,
            added_by INTEGER,
            added_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT OR IGNORE INTO allowed_users (user_id, is_owner, added_by, added_at) "
        "VALUES (?, 1, ?, ?)",
        (OWNER_ID, OWNER_ID, datetime.now(timezone.utc).isoformat()),
    )
    conn.execute("UPDATE allowed_users SET is_owner = 1 WHERE user_id = ?", (OWNER_ID,))

    version_row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    version = int(version_row[0]) if version_row else (1 if files_table_existed else 2)

    if version < 2:
        conn.execute("DROP TRIGGER IF EXISTS files_ai")
        conn.execute("DROP TRIGGER IF EXISTS files_ad")
        conn.execute("DROP TRIGGER IF EXISTS files_au")
        conn.execute("DROP TABLE IF EXISTS files_fts")
        conn.execute(
            """
            CREATE VIRTUAL TABLE files_fts USING fts5(
                file_name, tags, caption, collection_name, content='files', content_rowid='id'
            )
            """
        )
        # Backfill collections for rows that predate this feature
        for rid, fname in conn.execute(
            "SELECT id, file_name FROM files WHERE collection_id IS NULL"
        ).fetchall():
            name = derive_collection(fname)
            cid = _get_or_create_collection(conn, name) if name else None
            conn.execute("UPDATE files SET collection_id = ? WHERE id = ?", (cid, rid))
        conn.execute(
            """
            INSERT INTO files_fts(rowid, file_name, tags, caption, collection_name)
            SELECT f.id, f.file_name, f.tags, f.caption, COALESCE(c.name, '')
            FROM files f LEFT JOIN collections c ON c.id = f.collection_id
            """
        )
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('schema_version', '2') "
            "ON CONFLICT(key) DO UPDATE SET value = '2'"
        )
    else:
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
                file_name, tags, caption, collection_name, content='files', content_rowid='id'
            )
            """
        )

    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS files_ai AFTER INSERT ON files BEGIN
            INSERT INTO files_fts(rowid, file_name, tags, caption, collection_name)
            VALUES (new.id, new.file_name, new.tags, new.caption,
                COALESCE((SELECT name FROM collections WHERE id = new.collection_id), ''));
        END
        """
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS files_ad AFTER DELETE ON files BEGIN
            INSERT INTO files_fts(files_fts, rowid, file_name, tags, caption, collection_name)
            VALUES ('delete', old.id, old.file_name, old.tags, old.caption,
                COALESCE((SELECT name FROM collections WHERE id = old.collection_id), ''));
        END
        """
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS files_au AFTER UPDATE ON files BEGIN
            INSERT INTO files_fts(files_fts, rowid, file_name, tags, caption, collection_name)
            VALUES ('delete', old.id, old.file_name, old.tags, old.caption,
                COALESCE((SELECT name FROM collections WHERE id = old.collection_id), ''));
            INSERT INTO files_fts(rowid, file_name, tags, caption, collection_name)
            VALUES (new.id, new.file_name, new.tags, new.caption,
                COALESCE((SELECT name FROM collections WHERE id = new.collection_id), ''));
        END
        """
    )

    conn.commit()
    conn.close()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# --- Files -------------------------------------------------------------------


def add_file(file_name, file_type, file_size, telegram_file_id, telegram_unique_id,
             channel_message_id, caption, uploaded_by, tags="", collection_name=None):
    if collection_name is None:
        collection_name = derive_collection(file_name)
    with get_conn() as conn:
        collection_id = _get_or_create_collection(conn, collection_name)
        cur = conn.execute(
            """
            INSERT INTO files (file_name, file_type, file_size, telegram_file_id,
                telegram_unique_id, channel_message_id, caption, tags, uploaded_by,
                upload_date, collection_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (file_name, file_type, file_size, telegram_file_id, telegram_unique_id,
             channel_message_id, caption, tags, uploaded_by,
             datetime.now(timezone.utc).isoformat(), collection_id),
        )
        return cur.lastrowid, collection_name


def get_file(file_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        return dict(row) if row else None


def delete_file(file_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM files WHERE id = ?", (file_id,))


def rename_file(file_id, new_name):
    with get_conn() as conn:
        conn.execute("UPDATE files SET file_name = ? WHERE id = ?", (new_name, file_id))


def set_file_collection(file_id, name):
    with get_conn() as conn:
        cid = _get_or_create_collection(conn, name) if name else None
        conn.execute("UPDATE files SET collection_id = ? WHERE id = ?", (cid, file_id))


def list_files(page=0, page_size=10):
    offset = page * page_size
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM files ORDER BY id DESC LIMIT ? OFFSET ?", (page_size, offset)
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        return [dict(r) for r in rows], total


def search_grouped(query, page=0, page_size=10):
    """Search by filename or collection name; episodes sharing a collection are
    folded into a single group entry instead of N separate results."""
    fts_query = " ".join(f"{tok}*" for tok in query.split() if tok)
    with get_conn() as conn:
        try:
            rows = conn.execute(
                """
                SELECT f.*, c.name AS collection_name FROM files f
                JOIN files_fts ON files_fts.rowid = f.id
                LEFT JOIN collections c ON c.id = f.collection_id
                WHERE files_fts MATCH ?
                ORDER BY f.id DESC
                """,
                (fts_query,),
            ).fetchall()
        except sqlite3.OperationalError:
            like = f"%{query}%"
            rows = conn.execute(
                """
                SELECT f.*, c.name AS collection_name FROM files f
                LEFT JOIN collections c ON c.id = f.collection_id
                WHERE f.file_name LIKE ? OR c.name LIKE ?
                ORDER BY f.id DESC
                """,
                (like, like),
            ).fetchall()
        rows = [dict(r) for r in rows]

    groups = {}
    order = []
    items = []
    for r in rows:
        cid = r["collection_id"]
        if cid:
            if cid not in groups:
                groups[cid] = {"name": r["collection_name"], "members": []}
                order.append(cid)
            groups[cid]["members"].append(r)
        else:
            items.append(("file", r))

    for cid in order:
        g = groups[cid]
        if len(g["members"]) > 1:
            items.append(("collection", cid, g["name"], g["members"]))
        else:
            items.append(("file", g["members"][0]))

    items.sort(
        key=lambda it: it[1]["id"] if it[0] == "file" else max(m["id"] for m in it[3]),
        reverse=True,
    )
    total = len(items)
    start = page * page_size
    return items[start:start + page_size], total


def collection_files(collection_id):
    with get_conn() as conn:
        name_row = conn.execute(
            "SELECT name FROM collections WHERE id = ?", (collection_id,)
        ).fetchone()
        rows = conn.execute(
            "SELECT * FROM files WHERE collection_id = ? ORDER BY file_name COLLATE NOCASE",
            (collection_id,),
        ).fetchall()
        return (name_row[0] if name_row else None), [dict(r) for r in rows]


def list_collections(page=0, page_size=10):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.name, COUNT(f.id) AS cnt, COALESCE(SUM(f.file_size), 0) AS total_size
            FROM collections c JOIN files f ON f.collection_id = c.id
            GROUP BY c.id HAVING cnt > 1
            ORDER BY cnt DESC
            LIMIT ? OFFSET ?
            """,
            (page_size, page * page_size),
        ).fetchall()
        total = conn.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT c.id FROM collections c JOIN files f ON f.collection_id = c.id
                GROUP BY c.id HAVING COUNT(f.id) > 1
            )
            """
        ).fetchone()[0]
        return [dict(r) for r in rows], total


def all_files():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM files ORDER BY id ASC").fetchall()
        return [dict(r) for r in rows]


def total_file_count():
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]


def stats():
    with get_conn() as conn:
        count, total_size = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(file_size), 0) FROM files"
        ).fetchone()
        by_type = conn.execute(
            "SELECT file_type, COUNT(*) FROM files GROUP BY file_type ORDER BY 2 DESC"
        ).fetchall()
        return count, total_size, [(r[0], r[1]) for r in by_type]


# --- Multi-user access ---------------------------------------------------------


def is_allowed(user_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM allowed_users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row is not None


def is_owner(user_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM allowed_users WHERE user_id = ? AND is_owner = 1", (user_id,)
        ).fetchone()
        return row is not None


def add_allowed_user(user_id, added_by):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO allowed_users (user_id, is_owner, added_by, added_at) "
            "VALUES (?, 0, ?, ?)",
            (user_id, added_by, datetime.now(timezone.utc).isoformat()),
        )


def remove_allowed_user(user_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM allowed_users WHERE user_id = ? AND is_owner = 0", (user_id,))


def list_allowed_users():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT user_id, is_owner, added_at FROM allowed_users "
            "ORDER BY is_owner DESC, added_at ASC"
        ).fetchall()
        return [dict(r) for r in rows]
