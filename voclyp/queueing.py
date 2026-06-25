"""Durable processing queue.

Field uploads arrive in bursts (many agents syncing at once); the queue absorbs
the spike so the pipeline works steadily, and a failed job can be retried
without losing the conversation. SQLite-backed in Phase 0; Phase 1 swaps the
backend for a real broker behind this same interface.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from .contracts import utcnow

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
  payload TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',  -- pending | leased | done | dead
  attempts INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
"""


class JobQueue:
    def __init__(self, db_path, max_attempts=3):
        self.max_attempts = max_attempts
        Path(str(db_path)).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def enqueue(self, tenant_id, conversation_id, payload: dict) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO jobs (tenant_id, conversation_id, payload,"
                " created_at, updated_at) VALUES (?,?,?,?,?)",
                (tenant_id, conversation_id, json.dumps(payload), utcnow(), utcnow()),
            )
            self._conn.commit()
            return cur.lastrowid

    def dequeue(self):
        """Lease the oldest pending job, or return None."""
        with self._lock:
            row = self._conn.execute(
                "SELECT id, tenant_id, conversation_id, payload, attempts"
                " FROM jobs WHERE status='pending' ORDER BY id LIMIT 1"
            ).fetchone()
            if not row:
                return None
            self._conn.execute(
                "UPDATE jobs SET status='leased', attempts=attempts+1, updated_at=?"
                " WHERE id=?",
                (utcnow(), row[0]),
            )
            self._conn.commit()
        return {
            "id": row[0], "tenant_id": row[1], "conversation_id": row[2],
            "payload": json.loads(row[3]), "attempts": row[4] + 1,
        }

    def complete(self, job_id):
        self._set_status(job_id, "done")

    def fail(self, job_id, attempts):
        """Return the job to the queue, or park it as dead after max attempts."""
        status = "pending" if attempts < self.max_attempts else "dead"
        self._set_status(job_id, status)
        return status

    def _set_status(self, job_id, status):
        with self._lock:
            self._conn.execute(
                "UPDATE jobs SET status=?, updated_at=? WHERE id=?",
                (status, utcnow(), job_id),
            )
            self._conn.commit()

    def counts(self):
        with self._lock:
            rows = self._conn.execute(
                "SELECT status, COUNT(*) FROM jobs GROUP BY status"
            ).fetchall()
        return dict(rows)

    def lookup(self, tenant_id: str, conversation_id: str) -> dict | None:
        """Latest queue row for a conversation, if any."""
        with self._lock:
            row = self._conn.execute(
                "SELECT status, attempts FROM jobs"
                " WHERE tenant_id=? AND conversation_id=?"
                " ORDER BY id DESC LIMIT 1",
                (tenant_id, conversation_id),
            ).fetchone()
        if not row:
            return None
        return {"status": row[0], "attempts": row[1]}

    def requeue_dead(self, conversation_id: str) -> bool:
        """Reset the latest dead job for a conversation back to pending."""
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM jobs WHERE conversation_id=? AND status='dead'"
                " ORDER BY id DESC LIMIT 1",
                (conversation_id,),
            ).fetchone()
            if not row:
                return False
            self._conn.execute(
                "UPDATE jobs SET status='pending', attempts=0, updated_at=? WHERE id=?",
                (utcnow(), row[0]),
            )
            self._conn.commit()
        return True
