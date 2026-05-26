"""SQLite long-term memory store with optional embedding vectors."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_lock = threading.Lock()
_BASE = Path(__file__).resolve().parent.parent
DB_PATH = _BASE / "data" / "memory.db"

VALID_TYPES = frozenset({
    "conversation", "task", "person", "preference", "file", "event", "note",
})


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _lock:
        conn = _connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    embedding BLOB,
                    timestamp TEXT NOT NULL,
                    tags TEXT DEFAULT '[]',
                    client_id TEXT DEFAULT '',
                    meta TEXT DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type);
                CREATE INDEX IF NOT EXISTS idx_memories_client ON memories(client_id);
                CREATE INDEX IF NOT EXISTS idx_memories_ts ON memories(timestamp);

                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    content TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    client_id TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS tool_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool TEXT NOT NULL,
                    args TEXT NOT NULL,
                    result TEXT DEFAULT '',
                    ok INTEGER DEFAULT 1,
                    client_id TEXT DEFAULT '',
                    timestamp TEXT NOT NULL
                );
                """
            )
            conn.commit()
        finally:
            conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def insert_memory(
    *,
    mem_type: str,
    content: str,
    embedding: bytes | None = None,
    tags: list[str] | None = None,
    client_id: str = "",
    meta: dict | None = None,
) -> int:
    init_db()
    if mem_type not in VALID_TYPES:
        mem_type = "note"
    with _lock:
        conn = _connect()
        try:
            cur = conn.execute(
                """
                INSERT INTO memories (type, content, embedding, timestamp, tags, client_id, meta)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mem_type,
                    content.strip()[:4000],
                    embedding,
                    _now(),
                    json.dumps(tags or []),
                    client_id or "",
                    json.dumps(meta or {}),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()


def list_memories(
    *,
    client_id: str = "",
    mem_type: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    init_db()
    q = "SELECT id, type, content, timestamp, tags, client_id, meta FROM memories WHERE 1=1"
    params: list[Any] = []
    if client_id:
        q += " AND (client_id = ? OR client_id = '')"
        params.append(client_id)
    if mem_type:
        q += " AND type = ?"
        params.append(mem_type)
    q += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(q, params).fetchall()
            return [_row_to_dict(r) for r in rows]
        finally:
            conn.close()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "type": row["type"],
        "content": row["content"],
        "timestamp": row["timestamp"],
        "tags": json.loads(row["tags"] or "[]"),
        "client_id": row["client_id"],
        "meta": json.loads(row["meta"] or "{}"),
    }


def fetch_embeddings(limit: int = 500, client_id: str = "") -> list[tuple[int, str, bytes | None]]:
    init_db()
    q = "SELECT id, content, embedding FROM memories WHERE embedding IS NOT NULL"
    params: list[Any] = []
    if client_id:
        q += " AND (client_id = ? OR client_id = '')"
        params.append(client_id)
    q += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    with _lock:
        conn = _connect()
        try:
            return [(r[0], r[1], r[2]) for r in conn.execute(q, params).fetchall()]
        finally:
            conn.close()


def log_tool_execution(
    tool: str,
    args: dict,
    result: str,
    *,
    ok: bool = True,
    client_id: str = "",
) -> None:
    init_db()
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO tool_logs (tool, args, result, ok, client_id, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    tool,
                    json.dumps(args)[:2000],
                    (result or "")[:2000],
                    1 if ok else 0,
                    client_id or "",
                    _now(),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def upsert_task(title: str, content: str = "", *, client_id: str = "", status: str = "pending") -> int:
    init_db()
    now = _now()
    with _lock:
        conn = _connect()
        try:
            cur = conn.execute(
                """
                INSERT INTO tasks (title, status, content, created_at, updated_at, client_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (title[:200], status, content[:2000], now, now, client_id or ""),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()


def list_active_tasks(client_id: str = "", limit: int = 10) -> list[dict[str, Any]]:
    init_db()
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                """
                SELECT id, title, status, content, updated_at
                FROM tasks
                WHERE status IN ('pending', 'in_progress')
                  AND (client_id = ? OR client_id = '' OR ? = '')
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (client_id, client_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
