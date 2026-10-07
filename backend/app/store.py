"""SQLite persistence: runs, their full event traces, and long-term recall.

Events are written as they are emitted, so the trace of a run survives a
restart and a finished run can be replayed event by event. Recall finds past
runs on similar questions; the coordinator sees them as long-term memory.
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from app.textutil import similarity

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id          TEXT PRIMARY KEY,
    query       TEXT NOT NULL,
    options     TEXT NOT NULL,
    status      TEXT NOT NULL,
    created_at  REAL NOT NULL,
    finished_at REAL,
    title       TEXT,
    result      TEXT
);
CREATE TABLE IF NOT EXISTS events (
    run_id  TEXT NOT NULL,
    seq     INTEGER NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);
"""


class RunStore:
    def __init__(self, path: Path | str) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            if path != ":memory:":
                self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(SCHEMA)

    def _execute(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    # ----------------------------------------------------------------- writes

    def create_run(self, run_id: str, query: str, options: dict[str, Any]) -> None:
        self._execute(
            "INSERT INTO runs (id, query, options, status, created_at) VALUES (?, ?, ?, 'running', ?)",
            (run_id, query, json.dumps(options), time.time()),
        )

    def append_event(self, run_id: str, event: dict[str, Any]) -> None:
        self._execute(
            "INSERT OR REPLACE INTO events (run_id, seq, payload) VALUES (?, ?, ?)",
            (run_id, event["seq"], json.dumps(event, default=str)),
        )

    def finish_run(self, run_id: str, status: str, result: dict[str, Any] | None) -> None:
        self._execute(
            "UPDATE runs SET status = ?, finished_at = ?, title = ?, result = ? WHERE id = ?",
            (status, time.time(), (result or {}).get("title"),
             json.dumps(result, default=str) if result else None, run_id),
        )

    def mark_interrupted(self) -> int:
        """Runs still 'running' at startup died with the previous process."""
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE runs SET status = 'failed', finished_at = ? WHERE status = 'running'",
                (time.time(),),
            )
            return cursor.rowcount

    # ------------------------------------------------------------------ reads

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        rows = self._execute("SELECT * FROM runs WHERE id = ?", (run_id,))
        if not rows:
            return None
        row = rows[0]
        return {
            "id": row["id"],
            "query": row["query"],
            "options": json.loads(row["options"]),
            "status": row["status"],
            "created_at": row["created_at"],
            "finished_at": row["finished_at"],
            "title": row["title"],
            "result": json.loads(row["result"]) if row["result"] else None,
        }

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._execute(
            "SELECT id, query, status, created_at, finished_at, title, "
            "json_extract(result, '$.final_score') AS score, "
            "json_extract(result, '$.review_status') AS review_status "
            "FROM runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in rows]

    def events(self, run_id: str, after: int = 0) -> list[dict[str, Any]]:
        rows = self._execute(
            "SELECT payload FROM events WHERE run_id = ? AND seq > ? ORDER BY seq", (run_id, after)
        )
        return [json.loads(row["payload"]) for row in rows]

    def recall(self, query: str, *, limit: int = 2, exclude: str | None = None) -> list[dict[str, Any]]:
        """Completed past runs on a similar question, best match first."""
        rows = self._execute(
            "SELECT id, query, title, created_at, result FROM runs "
            "WHERE status = 'completed' AND result IS NOT NULL ORDER BY created_at DESC LIMIT 200"
        )
        matches = []
        for row in rows:
            if row["id"] == exclude:
                continue
            score, shared = similarity(query, f"{row['query']} {row['title'] or ''}")
            if shared >= 2 and score >= 0.2:
                matches.append((score, row))
        matches.sort(key=lambda m: m[0], reverse=True)

        related = []
        for score, row in matches[:limit]:
            result = json.loads(row["result"])
            cited = set(result.get("cited_ids") or [])
            urls = [e["url"] for e in result.get("evidence", []) if e["id"] in cited][:5]
            related.append({
                "run_id": row["id"],
                "query": row["query"],
                "title": row["title"] or "",
                "date": time.strftime("%Y-%m-%d", time.localtime(row["created_at"])),
                "similarity": round(score, 2),
                "urls": urls,
            })
        return related
