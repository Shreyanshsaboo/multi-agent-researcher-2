"""SQLite persistence: runs, conversations, their full event traces, and recall.

Events are written as they are emitted, so the trace of a run survives a
restart and a finished run can be replayed event by event. Runs that follow up
on each other share a thread id; a thread is one conversation. Recall finds
past runs on similar questions; the coordinator sees them as long-term memory.
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
    result      TEXT,
    thread_id   TEXT
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
            self._migrate()

    def _migrate(self) -> None:
        """Bring databases created before conversations existed up to date."""
        columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(runs)")}
        if "thread_id" not in columns:
            self._conn.execute("ALTER TABLE runs ADD COLUMN thread_id TEXT")
            self._conn.execute("UPDATE runs SET thread_id = id WHERE thread_id IS NULL")
        self._conn.execute("CREATE INDEX IF NOT EXISTS runs_by_thread ON runs (thread_id, created_at)")

    def _execute(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    # ----------------------------------------------------------------- writes

    def create_run(self, run_id: str, query: str, options: dict[str, Any],
                   thread_id: str | None = None) -> None:
        self._execute(
            "INSERT INTO runs (id, query, options, status, created_at, thread_id) "
            "VALUES (?, ?, ?, 'running', ?, ?)",
            (run_id, query, json.dumps(options), time.time(), thread_id or run_id),
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
        return self._run_dict(rows[0])

    @staticmethod
    def _run_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "thread_id": row["thread_id"],
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

    def list_threads(self, limit: int = 30) -> list[dict[str, Any]]:
        """Conversations, most recently active first, titled by their first question."""
        rows = self._execute(
            "SELECT thread_id, COUNT(*) AS turns, MIN(created_at) AS created_at, "
            "MAX(created_at) AS updated_at, "
            "(SELECT query FROM runs f WHERE f.thread_id = r.thread_id "
            " ORDER BY created_at LIMIT 1) AS title, "
            "(SELECT status FROM runs l WHERE l.thread_id = r.thread_id "
            " ORDER BY created_at DESC LIMIT 1) AS status "
            "FROM runs r GROUP BY thread_id ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in rows]

    def runs_since(self, since: float) -> int:
        return self._execute("SELECT COUNT(*) FROM runs WHERE created_at > ?", (since,))[0][0]

    def thread_runs(self, thread_id: str) -> list[dict[str, Any]]:
        rows = self._execute("SELECT * FROM runs WHERE thread_id = ? ORDER BY created_at", (thread_id,))
        return [self._run_dict(row) for row in rows]

    def events(self, run_id: str, after: int = 0) -> list[dict[str, Any]]:
        rows = self._execute(
            "SELECT payload FROM events WHERE run_id = ? AND seq > ? ORDER BY seq", (run_id, after)
        )
        return [json.loads(row["payload"]) for row in rows]

    def recall(self, query: str, *, limit: int = 2, exclude: str | None = None,
               exclude_thread: str | None = None) -> list[dict[str, Any]]:
        """Completed past runs on a similar question from other conversations, best first."""
        rows = self._execute(
            "SELECT id, query, title, created_at, result, thread_id FROM runs "
            "WHERE status = 'completed' AND result IS NOT NULL ORDER BY created_at DESC LIMIT 200"
        )
        matches = []
        for row in rows:
            if row["id"] == exclude or (exclude_thread and row["thread_id"] == exclude_thread):
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
