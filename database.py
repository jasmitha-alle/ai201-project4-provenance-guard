import sqlite3
import json
from datetime import datetime

DB_PATH = "provenance.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            content_id  TEXT NOT NULL,
            creator_id  TEXT NOT NULL,
            timestamp   TEXT NOT NULL,
            attribution TEXT NOT NULL,
            confidence  REAL NOT NULL,
            llm_score   REAL,
            status      TEXT NOT NULL DEFAULT 'classified',
            extra       TEXT
        )
    """)
    conn.commit()
    conn.close()


def write_entry(content_id, creator_id, attribution, confidence, llm_score, status="classified", extra=None):
    conn = get_db()
    conn.execute(
        """INSERT INTO log
           (content_id, creator_id, timestamp, attribution, confidence, llm_score, status, extra)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            content_id,
            creator_id,
            datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            attribution,
            confidence,
            llm_score,
            status,
            json.dumps(extra) if extra else None,
        ),
    )
    conn.commit()
    conn.close()


def update_status(content_id, status, extra=None):
    conn = get_db()
    conn.execute(
        "UPDATE log SET status = ? WHERE content_id = ?",
        (status, content_id),
    )
    if extra:
        conn.execute(
            "UPDATE log SET extra = ? WHERE content_id = ?",
            (json.dumps(extra), content_id),
        )
    conn.commit()
    conn.close()


def get_log(limit=50):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM log ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    entries = []
    for r in rows:
        e = dict(r)
        if e.get("extra"):
            e["extra"] = json.loads(e["extra"])
        entries.append(e)
    return entries


def get_entry(content_id):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM log WHERE content_id = ? ORDER BY id DESC LIMIT 1",
        (content_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None