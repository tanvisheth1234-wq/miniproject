"""Per-node persistence: every message and event, queryable for the
section 16 metrics (delivery ratio, hop distribution, latency by
priority, recovery time -- all of them are just queries against this).

Spec: docs/project-plan.md section 11. WAL mode lets the future API
server (section 12) read live state while the engine keeps writing.
Plain ``sqlite3`` + raw SQL -- the schema is three tables, an ORM would
add indirection without benefit (section 13's explicit rationale).
"""

from __future__ import annotations

import sqlite3
import time
from typing import Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    msg_id      TEXT PRIMARY KEY,
    src         TEXT NOT NULL,
    dst         TEXT NOT NULL,
    priority    INTEGER NOT NULL,
    direction   TEXT NOT NULL,   -- sent | received | forwarded
    status      TEXT NOT NULL,   -- pending | delivered | failed | queued_sf
    body        TEXT,            -- plaintext only if we are src or dst
    created_ms  INTEGER NOT NULL,
    resolved_ms INTEGER,
    hop_count   INTEGER,
    path        TEXT             -- comma-separated node IDs
);

CREATE TABLE IF NOT EXISTS events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_ms   INTEGER NOT NULL,
    kind    TEXT NOT NULL,       -- sent | recv | forward | drop_ttl | drop_dup
                                  -- | ack | retry | sf_queue | sf_flush
                                  -- | peer_up | peer_down | route_change
    msg_id  TEXT,
    peer    TEXT,
    detail  TEXT
);

CREATE TABLE IF NOT EXISTS peers (
    node_id       TEXT PRIMARY KEY,
    role          TEXT NOT NULL,  -- NORMAL | GATEWAY | RESCUE
    last_seen_ms  INTEGER NOT NULL,
    link_quality  REAL,
    public_key    BLOB
);

CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts_ms);
CREATE INDEX IF NOT EXISTS idx_msg_status ON messages(status);
"""


def _now_ms() -> int:
    return int(time.time() * 1000)


class Store:
    """One node's SQLite-backed message/event/peer log. Use as a context
    manager, or call ``close()`` explicitly."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # -- messages ----------------------------------------------------------------

    def record_message(
        self,
        msg_id: str,
        src: str,
        dst: str,
        priority: int,
        direction: str,
        status: str,
        body: Optional[str] = None,
        created_ms: Optional[int] = None,
        resolved_ms: Optional[int] = None,
        hop_count: Optional[int] = None,
        path: Optional[list[str]] = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO messages
                (msg_id, src, dst, priority, direction, status, body,
                 created_ms, resolved_ms, hop_count, path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(msg_id) DO UPDATE SET
                direction=excluded.direction, status=excluded.status,
                body=excluded.body, resolved_ms=excluded.resolved_ms,
                hop_count=excluded.hop_count, path=excluded.path
            """,
            (
                msg_id, src, dst, priority, direction, status, body,
                created_ms if created_ms is not None else _now_ms(),
                resolved_ms, hop_count,
                ",".join(path) if path is not None else None,
            ),
        )
        self._conn.commit()

    def update_message_status(
        self, msg_id: str, status: str, resolved_ms: Optional[int] = None
    ) -> bool:
        """Returns False if ``msg_id`` isn't known -- callers should treat
        that as a bug (you can't resolve a message you never recorded)."""
        cur = self._conn.execute(
            "UPDATE messages SET status = ?, resolved_ms = COALESCE(?, resolved_ms) WHERE msg_id = ?",
            (status, resolved_ms, msg_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def get_message(self, msg_id: str) -> Optional[dict]:
        row = self._conn.execute("SELECT * FROM messages WHERE msg_id = ?", (msg_id,)).fetchone()
        return dict(row) if row is not None else None

    def messages_by_status(self, status: str) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM messages WHERE status = ?", (status,)).fetchall()
        return [dict(row) for row in rows]

    # -- events --------------------------------------------------------------------

    def record_event(
        self,
        kind: str,
        msg_id: Optional[str] = None,
        peer: Optional[str] = None,
        detail: Optional[str] = None,
        ts_ms: Optional[int] = None,
    ) -> int:
        """Returns the new event's row id."""
        cur = self._conn.execute(
            "INSERT INTO events (ts_ms, kind, msg_id, peer, detail) VALUES (?, ?, ?, ?, ?)",
            (ts_ms if ts_ms is not None else _now_ms(), kind, msg_id, peer, detail),
        )
        self._conn.commit()
        return cur.lastrowid

    def events_for_message(self, msg_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM events WHERE msg_id = ? ORDER BY ts_ms ASC", (msg_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def events_by_kind(self, kind: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM events WHERE kind = ? ORDER BY ts_ms ASC", (kind,)
        ).fetchall()
        return [dict(row) for row in rows]

    def count_events(self, kind: str) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS n FROM events WHERE kind = ?", (kind,)).fetchone()
        return row["n"]

    # -- peers -----------------------------------------------------------------------

    def upsert_peer(
        self,
        node_id: str,
        role: str,
        last_seen_ms: Optional[int] = None,
        link_quality: Optional[float] = None,
        public_key: Optional[bytes] = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO peers (node_id, role, last_seen_ms, link_quality, public_key)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(node_id) DO UPDATE SET
                role=excluded.role, last_seen_ms=excluded.last_seen_ms,
                link_quality=COALESCE(excluded.link_quality, peers.link_quality),
                public_key=COALESCE(excluded.public_key, peers.public_key)
            """,
            (node_id, role, last_seen_ms if last_seen_ms is not None else _now_ms(), link_quality, public_key),
        )
        self._conn.commit()

    def get_peer(self, node_id: str) -> Optional[dict]:
        row = self._conn.execute("SELECT * FROM peers WHERE node_id = ?", (node_id,)).fetchone()
        return dict(row) if row is not None else None

    def remove_peer(self, node_id: str) -> None:
        self._conn.execute("DELETE FROM peers WHERE node_id = ?", (node_id,))
        self._conn.commit()

    def all_peers(self) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM peers").fetchall()
        return [dict(row) for row in rows]
