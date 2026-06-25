"""Persistence for the enterprise layer (hardened).

Backends behind one method surface:

- ``LocalStore``        — offline SQLite mirror. Emulates schema-per-tenant by
                          keeping ONE database file per tenant schema
                          (``enterprise_<schema>.db``); cross-tenant reads are
                          impossible because the data physically lives in
                          different files.
- ``PostgresStore``     — synchronous Supabase/PostgreSQL (psycopg). Sets
                          ``search_path`` to the tenant schema on every borrowed
                          connection.
- ``AsyncPostgresStore``— asyncio psycopg ``AsyncConnectionPool`` used by the
                          gateway middleware and the orphan-sweep cron.

A deterministic state machine (``conversation_state``) is enforced in the
application on every transition; the Postgres schema also guards it with a
trigger (see supabase/migrations/0004).
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
from pathlib import Path

from ..contracts import utcnow
from ..security import chain_hash

GENESIS = "0" * 64

# -- deterministic conversation state machine ---------------------------------

CONSENT_LOGGED = "consent_logged"
AUDIO_UPLOADED = "audio_uploaded"
TRANSCRIBING = "transcribing"
EXTRACTING = "extracting"
DISPATCHING = "dispatching"
PURGED = "purged"
ERROR_PURGED = "error_purged"

CONVERSATION_STATES = (
    CONSENT_LOGGED, AUDIO_UPLOADED, TRANSCRIBING, EXTRACTING, DISPATCHING,
    PURGED, ERROR_PURGED,
)
TERMINAL_STATES = frozenset({PURGED, ERROR_PURGED})

# happy-path ladder; error_purged is reachable from any non-terminal state.
ALLOWED_TRANSITIONS = {
    CONSENT_LOGGED: {AUDIO_UPLOADED, ERROR_PURGED},
    AUDIO_UPLOADED: {TRANSCRIBING, ERROR_PURGED},
    TRANSCRIBING: {EXTRACTING, ERROR_PURGED},
    EXTRACTING: {DISPATCHING, ERROR_PURGED},
    DISPATCHING: {PURGED, ERROR_PURGED},
    PURGED: set(),
    ERROR_PURGED: set(),
}


class IllegalTransition(Exception):
    """Raised when a conversation is moved between states illegally."""


def assert_transition(old: str, new: str) -> None:
    if old == new:
        return
    if new not in ALLOWED_TRANSITIONS.get(old, set()):
        raise IllegalTransition(f"illegal state transition {old} -> {new}")


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (text or "").strip().lower()).strip("_")
    return s[:48] or "default"


def schema_for_tenant(tenant_id: str) -> str:
    """Tenant -> PostgreSQL schema name, e.g. 'sleep_company' -> 'schema_sleep_company'."""
    return "schema_" + slugify(tenant_id)


# -- SQLite mirror schema (one file per tenant schema) ------------------------

_LOCAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS immutable_consent_logs (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL, agent_id TEXT NOT NULL, session_id TEXT NOT NULL,
  customer_phone_hash TEXT NOT NULL, language TEXT NOT NULL,
  purposes TEXT NOT NULL, device_fingerprint TEXT NOT NULL,
  consent_artifact TEXT NOT NULL, artifact_sha256 TEXT NOT NULL,
  prev_hash TEXT NOT NULL, entry_hash TEXT NOT NULL,
  captured_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS showroom_conversations (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL, agent_id TEXT NOT NULL, store_id TEXT NOT NULL,
  consent_log_id TEXT NOT NULL,
  s3_bucket TEXT NOT NULL, s3_key TEXT NOT NULL, audio_sha256 TEXT NOT NULL,
  duration_seconds REAL,
  state TEXT NOT NULL DEFAULT 'consent_logged', error_detail TEXT,
  transcript_codemix TEXT, transcript_english TEXT,
  detected_languages TEXT NOT NULL DEFAULT '[]', asr_path TEXT,
  extraction TEXT, extraction_confidence REAL,
  requires_human_verification INTEGER NOT NULL DEFAULT 0,
  verified_by TEXT, verified_at TEXT,
  erase_after TEXT NOT NULL, erased_at TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS routing_outbox (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
  channel TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 5,
  idempotency_key TEXT NOT NULL DEFAULT '',
  payload TEXT NOT NULL, response TEXT, detail TEXT,
  next_retry_at TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE (conversation_id, channel)
);
CREATE TABLE IF NOT EXISTS failed_routing_outbox (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL, conversation_id TEXT NOT NULL, channel TEXT NOT NULL,
  attempts INTEGER NOT NULL, idempotency_key TEXT NOT NULL DEFAULT '',
  payload TEXT NOT NULL, last_response TEXT, failure_reason TEXT NOT NULL,
  original_created_at TEXT, failed_at TEXT NOT NULL
);
"""

_JSON_FIELDS = {
    "purposes", "device_fingerprint", "consent_artifact",
    "detected_languages", "extraction", "payload", "response", "last_response",
}


def _dumps(value) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=False)


def _decode_row(row: dict) -> dict:
    out = dict(row)
    for key in _JSON_FIELDS:
        if key in out and isinstance(out[key], str):
            try:
                out[key] = json.loads(out[key])
            except (json.JSONDecodeError, TypeError):
                pass
    if "requires_human_verification" in out:
        out["requires_human_verification"] = bool(out["requires_human_verification"])
    return out


class LocalStore:
    """SQLite mirror with one database file per tenant schema (offline isolation)."""

    backend = "local"

    def __init__(self, root):
        self.root = Path(str(root))
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conns: dict[str, sqlite3.Connection] = {}
        # re-open any schema files created by previous runs
        for path in self.root.glob("enterprise_*.db"):
            self._open(path.stem[len("enterprise_"):])

    # -- schema/connection routing --------------------------------------------
    def _open(self, schema: str) -> sqlite3.Connection:
        conn = self._conns.get(schema)
        if conn is not None:
            return conn
        conn = sqlite3.connect(str(self.root / f"enterprise_{schema}.db"),
                               check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.executescript(_LOCAL_SCHEMA)
        conn.commit()
        self._conns[schema] = conn
        return conn

    def _conn_for_tenant(self, tenant_id: str) -> sqlite3.Connection:
        return self._open(schema_for_tenant(tenant_id))

    def _conns_for_scope(self, tenant_id: str | None) -> list[sqlite3.Connection]:
        if tenant_id is not None:
            return [self._conn_for_tenant(tenant_id)]
        return list(self._conns.values())

    def provision_tenant(self, tenant_id: str) -> str:
        with self._lock:
            self._conn_for_tenant(tenant_id)
        return schema_for_tenant(tenant_id)

    # -- consent ---------------------------------------------------------------
    def last_consent_entry_hash(self, tenant_id: str) -> str:
        with self._lock:
            row = self._conn_for_tenant(tenant_id).execute(
                "SELECT entry_hash FROM immutable_consent_logs WHERE tenant_id=?"
                " ORDER BY captured_at DESC, rowid DESC LIMIT 1",
                (tenant_id,),
            ).fetchone()
        return row["entry_hash"] if row else GENESIS

    def insert_consent_log(self, row: dict) -> str:
        data = dict(row)
        for key in ("purposes", "device_fingerprint", "consent_artifact"):
            data[key] = _dumps(data[key])
        with self._lock:
            self._conn_for_tenant(row["tenant_id"]).execute(
                "INSERT INTO immutable_consent_logs (id, tenant_id, agent_id,"
                " session_id, customer_phone_hash, language, purposes,"
                " device_fingerprint, consent_artifact, artifact_sha256,"
                " prev_hash, entry_hash, captured_at)"
                " VALUES (:id,:tenant_id,:agent_id,:session_id,:customer_phone_hash,"
                ":language,:purposes,:device_fingerprint,:consent_artifact,"
                ":artifact_sha256,:prev_hash,:entry_hash,:captured_at)",
                data,
            )
            self._conn_for_tenant(row["tenant_id"]).commit()
        return data["id"]

    def get_consent_log(self, tenant_id: str, consent_id: str) -> dict | None:
        with self._lock:
            row = self._conn_for_tenant(tenant_id).execute(
                "SELECT * FROM immutable_consent_logs WHERE tenant_id=? AND id=?",
                (tenant_id, consent_id),
            ).fetchone()
        return _decode_row(dict(row)) if row else None

    def verify_consent_chain(self, tenant_id: str) -> tuple[bool, str | None]:
        with self._lock:
            rows = self._conn_for_tenant(tenant_id).execute(
                "SELECT * FROM immutable_consent_logs WHERE tenant_id=?"
                " ORDER BY captured_at, rowid",
                (tenant_id,),
            ).fetchall()
        prev = GENESIS
        for row in rows:
            expected = chain_hash(prev, row["tenant_id"], row["session_id"],
                                  row["artifact_sha256"], row["captured_at"])
            if expected != row["entry_hash"]:
                return False, row["id"]
            prev = row["entry_hash"]
        return True, None

    # -- conversations ---------------------------------------------------------
    def insert_conversation(self, row: dict) -> str:
        data = dict(row)
        data["detected_languages"] = _dumps(data.get("detected_languages") or [])
        data.setdefault("state", CONSENT_LOGGED)
        data.setdefault("duration_seconds", None)
        data.setdefault("created_at", utcnow())
        data.setdefault("updated_at", utcnow())
        with self._lock:
            conn = self._conn_for_tenant(row["tenant_id"])
            conn.execute(
                "INSERT INTO showroom_conversations (id, tenant_id, agent_id,"
                " store_id, consent_log_id, s3_bucket, s3_key, audio_sha256,"
                " duration_seconds, state, detected_languages, erase_after,"
                " created_at, updated_at)"
                " VALUES (:id,:tenant_id,:agent_id,:store_id,:consent_log_id,"
                ":s3_bucket,:s3_key,:audio_sha256,:duration_seconds,:state,"
                ":detected_languages,:erase_after,:created_at,:updated_at)",
                data,
            )
            conn.commit()
        return data["id"]

    def _find_conv(self, conversation_id: str):
        for conn in self._conns.values():
            row = conn.execute(
                "SELECT * FROM showroom_conversations WHERE id=?",
                (conversation_id,)).fetchone()
            if row:
                return conn, row
        return None, None

    def get_conversation(self, conversation_id: str,
                         tenant_id: str | None = None) -> dict | None:
        with self._lock:
            for conn in self._conns_for_scope(tenant_id):
                sql = "SELECT * FROM showroom_conversations WHERE id=?"
                params = [conversation_id]
                if tenant_id is not None:
                    sql += " AND tenant_id=?"
                    params.append(tenant_id)
                row = conn.execute(sql, params).fetchone()
                if row:
                    return _decode_row(dict(row))
        return None

    def update_conversation(self, conversation_id: str, **fields) -> None:
        if not fields:
            return
        with self._lock:
            conn, row = self._find_conv(conversation_id)
            if conn is None:
                return
            data = dict(fields)
            if "state" in data:
                assert_transition(row["state"], data["state"])
            if "detected_languages" in data:
                data["detected_languages"] = _dumps(data["detected_languages"])
            if "extraction" in data and not isinstance(data["extraction"], str):
                data["extraction"] = _dumps(data["extraction"])
            if "requires_human_verification" in data:
                data["requires_human_verification"] = int(bool(data["requires_human_verification"]))
            data["updated_at"] = utcnow()
            sets = ", ".join(f"{k}=:{k}" for k in data)
            data["_id"] = conversation_id
            conn.execute(
                f"UPDATE showroom_conversations SET {sets} WHERE id=:_id", data)
            conn.commit()

    def set_state(self, conversation_id: str, new_state: str, **fields) -> None:
        self.update_conversation(conversation_id, state=new_state, **fields)

    def due_erasures(self, now_iso: str, limit: int = 100) -> list[dict]:
        out: list[dict] = []
        with self._lock:
            for conn in self._conns.values():
                rows = conn.execute(
                    "SELECT * FROM showroom_conversations"
                    " WHERE erased_at IS NULL AND erase_after <= ?"
                    " AND state NOT IN ('purged','error_purged')"
                    " ORDER BY erase_after LIMIT ?",
                    (now_iso, limit)).fetchall()
                out.extend(_decode_row(dict(r)) for r in rows)
        return out[:limit]

    def due_orphans(self, cutoff_iso: str, limit: int = 100) -> list[dict]:
        """Non-terminal conversations created before the cutoff (stranded)."""
        out: list[dict] = []
        with self._lock:
            for conn in self._conns.values():
                rows = conn.execute(
                    "SELECT * FROM showroom_conversations"
                    " WHERE state NOT IN ('purged','error_purged')"
                    " AND created_at < ? ORDER BY created_at LIMIT ?",
                    (cutoff_iso, limit)).fetchall()
                out.extend(_decode_row(dict(r)) for r in rows)
        return out[:limit]

    def mark_error_purged(self, conversation_id: str, detail: str = "") -> None:
        self.update_conversation(conversation_id, state=ERROR_PURGED,
                                 erased_at=utcnow(),
                                 error_detail=detail or "force-purged (orphan)")

    def pending_verifications(self, tenant_id: str, agent_id: str | None = None) -> list[dict]:
        sql = ("SELECT * FROM showroom_conversations WHERE tenant_id=?"
               " AND requires_human_verification=1 AND verified_at IS NULL")
        params = [tenant_id]
        if agent_id:
            sql += " AND agent_id=?"
            params.append(agent_id)
        with self._lock:
            rows = self._conn_for_tenant(tenant_id).execute(sql, params).fetchall()
        return [_decode_row(dict(r)) for r in rows]

    # -- routing ---------------------------------------------------------------
    def insert_routing(self, row: dict) -> str:
        data = dict(row)
        data["payload"] = _dumps(data.get("payload") or {})
        data.setdefault("status", "pending")
        data.setdefault("attempts", 0)
        data.setdefault("max_attempts", 5)
        data.setdefault("idempotency_key", "")
        data.setdefault("next_retry_at", utcnow())
        data.setdefault("created_at", utcnow())
        data.setdefault("updated_at", utcnow())
        data.setdefault("response", None)
        data.setdefault("detail", None)
        with self._lock:
            conn = self._conn_for_tenant(row["tenant_id"])
            conn.execute(
                "INSERT OR IGNORE INTO routing_outbox (id, tenant_id,"
                " conversation_id, channel, status, attempts, max_attempts,"
                " idempotency_key, payload, response, detail, next_retry_at,"
                " created_at, updated_at)"
                " VALUES (:id,:tenant_id,:conversation_id,:channel,:status,"
                ":attempts,:max_attempts,:idempotency_key,:payload,:response,"
                ":detail,:next_retry_at,:created_at,:updated_at)",
                data)
            conn.commit()
        return data["id"]

    def get_routing_for_conversation(self, conversation_id: str) -> list[dict]:
        with self._lock:
            for conn in self._conns.values():
                rows = conn.execute(
                    "SELECT * FROM routing_outbox WHERE conversation_id=? ORDER BY channel",
                    (conversation_id,)).fetchall()
                if rows:
                    return [_decode_row(dict(r)) for r in rows]
        return []

    def get_routing(self, conversation_id: str, channel: str) -> dict | None:
        with self._lock:
            for conn in self._conns.values():
                row = conn.execute(
                    "SELECT * FROM routing_outbox WHERE conversation_id=? AND channel=?",
                    (conversation_id, channel)).fetchone()
                if row:
                    return _decode_row(dict(row))
        return None

    def _find_routing(self, routing_id: str):
        for conn in self._conns.values():
            row = conn.execute("SELECT * FROM routing_outbox WHERE id=?",
                               (routing_id,)).fetchone()
            if row:
                return conn, row
        return None, None

    def update_routing(self, routing_id: str, **fields) -> None:
        if not fields:
            return
        with self._lock:
            conn, _ = self._find_routing(routing_id)
            if conn is None:
                return
            data = dict(fields)
            for key in ("payload", "response"):
                if key in data and not isinstance(data[key], (str, type(None))):
                    data[key] = _dumps(data[key])
            data["updated_at"] = utcnow()
            sets = ", ".join(f"{k}=:{k}" for k in data)
            data["_id"] = routing_id
            conn.execute(f"UPDATE routing_outbox SET {sets} WHERE id=:_id", data)
            conn.commit()

    def due_routing(self, now_iso: str, limit: int = 100) -> list[dict]:
        out: list[dict] = []
        with self._lock:
            for conn in self._conns.values():
                rows = conn.execute(
                    "SELECT * FROM routing_outbox"
                    " WHERE status IN ('pending','failed') AND next_retry_at <= ?"
                    " ORDER BY next_retry_at LIMIT ?",
                    (now_iso, limit)).fetchall()
                out.extend(_decode_row(dict(r)) for r in rows)
        return out[:limit]

    def move_to_dlq(self, row: dict, reason: str) -> str:
        """Move a poison-pill routing row into the dead-letter table."""
        import uuid
        with self._lock:
            conn, current = self._find_routing(row["id"])
            if conn is None:
                return ""
            dlq_id = uuid.uuid4().hex
            attempts = int(row.get("attempts", current["attempts"]))
            conn.execute(
                "INSERT INTO failed_routing_outbox (id, tenant_id, conversation_id,"
                " channel, attempts, idempotency_key, payload, last_response,"
                " failure_reason, original_created_at, failed_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (dlq_id, current["tenant_id"], current["conversation_id"],
                 current["channel"], attempts,
                 current["idempotency_key"], current["payload"],
                 current["response"], reason, current["created_at"], utcnow()))
            conn.execute("DELETE FROM routing_outbox WHERE id=?", (row["id"],))
            conn.commit()
        return dlq_id

    def get_dlq_for_conversation(self, conversation_id: str) -> list[dict]:
        with self._lock:
            for conn in self._conns.values():
                rows = conn.execute(
                    "SELECT * FROM failed_routing_outbox WHERE conversation_id=?",
                    (conversation_id,)).fetchall()
                if rows:
                    return [_decode_row(dict(r)) for r in rows]
        return []

    def close(self) -> None:
        with self._lock:
            for conn in self._conns.values():
                conn.close()
            self._conns.clear()


class PostgresStore:
    """Synchronous Supabase/PostgreSQL backend with per-tenant search_path."""

    backend = "postgres"

    def __init__(self, dsn: str):
        import psycopg  # noqa: F401
        from psycopg_pool import ConnectionPool

        self._pool = ConnectionPool(dsn, min_size=1, max_size=8, open=True)

    @staticmethod
    def _schema(tenant_id: str | None) -> str:
        return schema_for_tenant(tenant_id) if tenant_id else "public"

    def _conn(self, tenant_id: str | None):  # pragma: no cover - needs PG
        conn = self._pool.connection()
        return conn

    def _set_path(self, conn, tenant_id: str | None):  # pragma: no cover
        conn.execute(f'SET search_path TO "{self._schema(tenant_id)}", public')

    def provision_tenant(self, tenant_id: str) -> str:  # pragma: no cover
        schema = schema_for_tenant(tenant_id)
        with self._pool.connection() as conn:
            conn.execute("SELECT public.provision_tenant_schema(%s)", (schema,))
        return schema

    def _one(self, sql, params=(), tenant_id=None):  # pragma: no cover - needs PG
        from psycopg.rows import dict_row
        with self._pool.connection() as conn:
            self._set_path(conn, tenant_id)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
        return _decode_row(row) if row else None

    def _all(self, sql, params=(), tenant_id=None):  # pragma: no cover - needs PG
        from psycopg.rows import dict_row
        with self._pool.connection() as conn:
            self._set_path(conn, tenant_id)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        return [_decode_row(r) for r in rows]

    def _exec(self, sql, params=(), tenant_id=None):  # pragma: no cover - needs PG
        with self._pool.connection() as conn:
            self._set_path(conn, tenant_id)
            conn.execute(sql, params)

    # -- consent ---------------------------------------------------------------
    def last_consent_entry_hash(self, tenant_id):  # pragma: no cover
        row = self._one(
            "SELECT entry_hash FROM immutable_consent_logs WHERE tenant_id=%s"
            " ORDER BY captured_at DESC LIMIT 1", (tenant_id,), tenant_id)
        return row["entry_hash"] if row else GENESIS

    def insert_consent_log(self, row):  # pragma: no cover - needs PG
        from psycopg.types.json import Jsonb
        out = self._one(
            "INSERT INTO immutable_consent_logs (id, tenant_id, agent_id,"
            " session_id, customer_phone_hash, language, purposes,"
            " device_fingerprint, consent_artifact, artifact_sha256,"
            " prev_hash, entry_hash, captured_at)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (row["id"], row["tenant_id"], row["agent_id"], row["session_id"],
             row["customer_phone_hash"], row["language"], Jsonb(row["purposes"]),
             Jsonb(row["device_fingerprint"]), Jsonb(row["consent_artifact"]),
             row["artifact_sha256"], row["prev_hash"], row["entry_hash"],
             row["captured_at"]), row["tenant_id"])
        return out["id"] if out else row["id"]

    def get_consent_log(self, tenant_id, consent_id):  # pragma: no cover
        return self._one(
            "SELECT * FROM immutable_consent_logs WHERE tenant_id=%s AND id=%s",
            (tenant_id, consent_id), tenant_id)

    def verify_consent_chain(self, tenant_id):  # pragma: no cover
        rows = self._all(
            "SELECT * FROM immutable_consent_logs WHERE tenant_id=%s"
            " ORDER BY captured_at", (tenant_id,), tenant_id)
        prev = GENESIS
        for r in rows:
            expected = chain_hash(prev, r["tenant_id"], r["session_id"],
                                  r["artifact_sha256"], str(r["captured_at"]))
            if expected != r["entry_hash"]:
                return False, r["id"]
            prev = r["entry_hash"]
        return True, None

    # -- conversations ---------------------------------------------------------
    def insert_conversation(self, row):  # pragma: no cover - needs PG
        out = self._one(
            "INSERT INTO showroom_conversations (id, tenant_id, agent_id,"
            " store_id, consent_log_id, s3_bucket, s3_key, audio_sha256,"
            " duration_seconds, state, detected_languages, erase_after)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (row["id"], row["tenant_id"], row["agent_id"], row["store_id"],
             row["consent_log_id"], row["s3_bucket"], row["s3_key"],
             row["audio_sha256"], row.get("duration_seconds"),
             row.get("state", CONSENT_LOGGED), row.get("detected_languages") or [],
             row["erase_after"]), row["tenant_id"])
        return out["id"] if out else row["id"]

    def get_conversation(self, conversation_id, tenant_id=None):  # pragma: no cover
        return self._one(
            "SELECT * FROM showroom_conversations WHERE id=%s", (conversation_id,),
            tenant_id)

    def update_conversation(self, conversation_id, tenant_id=None, **fields):  # pragma: no cover
        from psycopg.types.json import Jsonb
        if "state" in fields:
            current = self.get_conversation(conversation_id, tenant_id)
            if current:
                assert_transition(current["state"], fields["state"])
        cols, vals = [], []
        for key, value in fields.items():
            if key == "extraction" and value is not None:
                value = Jsonb(value)
            cols.append(f"{key}=%s")
            vals.append(value)
        vals.append(conversation_id)
        self._exec(
            f"UPDATE showroom_conversations SET {', '.join(cols)} WHERE id=%s",
            tuple(vals), tenant_id)

    def set_state(self, conversation_id, new_state, tenant_id=None, **fields):  # pragma: no cover
        self.update_conversation(conversation_id, tenant_id=tenant_id,
                                 state=new_state, **fields)

    def due_erasures(self, now_iso, limit=100):  # pragma: no cover
        return self._all(
            "SELECT * FROM showroom_conversations WHERE erased_at IS NULL"
            " AND erase_after <= %s AND state NOT IN ('purged','error_purged')"
            " ORDER BY erase_after LIMIT %s", (now_iso, limit))

    def due_orphans(self, cutoff_iso, limit=100):  # pragma: no cover
        return self._all(
            "SELECT * FROM showroom_conversations"
            " WHERE state NOT IN ('purged','error_purged') AND created_at < %s"
            " ORDER BY created_at LIMIT %s", (cutoff_iso, limit))

    def mark_error_purged(self, conversation_id, detail="", tenant_id=None):  # pragma: no cover
        self.update_conversation(
            conversation_id, tenant_id=tenant_id, state=ERROR_PURGED,
            erased_at=utcnow(), error_detail=detail or "force-purged (orphan)")

    def pending_verifications(self, tenant_id, agent_id=None):  # pragma: no cover
        if agent_id:
            return self._all(
                "SELECT * FROM showroom_conversations WHERE tenant_id=%s"
                " AND agent_id=%s AND requires_human_verification=true"
                " AND verified_at IS NULL", (tenant_id, agent_id), tenant_id)
        return self._all(
            "SELECT * FROM showroom_conversations WHERE tenant_id=%s"
            " AND requires_human_verification=true AND verified_at IS NULL",
            (tenant_id,), tenant_id)

    # -- routing ---------------------------------------------------------------
    def insert_routing(self, row):  # pragma: no cover - needs PG
        from psycopg.types.json import Jsonb
        out = self._one(
            "INSERT INTO routing_outbox (id, tenant_id, conversation_id, channel,"
            " status, attempts, max_attempts, idempotency_key, payload, next_retry_at)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
            " ON CONFLICT (conversation_id, channel) DO NOTHING RETURNING id",
            (row["id"], row["tenant_id"], row["conversation_id"], row["channel"],
             row.get("status", "pending"), row.get("attempts", 0),
             row.get("max_attempts", 5), row.get("idempotency_key", ""),
             Jsonb(row.get("payload") or {}), row.get("next_retry_at", utcnow())),
            row["tenant_id"])
        return out["id"] if out else row["id"]

    def get_routing_for_conversation(self, conversation_id):  # pragma: no cover
        return self._all(
            "SELECT * FROM routing_outbox WHERE conversation_id=%s ORDER BY channel",
            (conversation_id,))

    def get_routing(self, conversation_id, channel):  # pragma: no cover
        return self._one(
            "SELECT * FROM routing_outbox WHERE conversation_id=%s AND channel=%s",
            (conversation_id, channel))

    def update_routing(self, routing_id, **fields):  # pragma: no cover
        from psycopg.types.json import Jsonb
        cols, vals = [], []
        for key, value in fields.items():
            if key in ("payload", "response") and value is not None:
                value = Jsonb(value)
            cols.append(f"{key}=%s")
            vals.append(value)
        vals.append(routing_id)
        self._exec(f"UPDATE routing_outbox SET {', '.join(cols)} WHERE id=%s",
                   tuple(vals))

    def due_routing(self, now_iso, limit=100):  # pragma: no cover
        return self._all(
            "SELECT * FROM routing_outbox WHERE status IN ('pending','failed')"
            " AND next_retry_at <= %s ORDER BY next_retry_at LIMIT %s",
            (now_iso, limit))

    def move_to_dlq(self, row, reason):  # pragma: no cover - needs PG
        from psycopg.types.json import Jsonb
        import uuid
        dlq_id = uuid.uuid4().hex
        with self._pool.connection() as conn:
            self._set_path(conn, row.get("tenant_id"))
            with conn.transaction():
                conn.execute(
                    "INSERT INTO failed_routing_outbox (id, tenant_id,"
                    " conversation_id, channel, attempts, idempotency_key,"
                    " payload, last_response, failure_reason, original_created_at)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (dlq_id, row["tenant_id"], row["conversation_id"],
                     row["channel"], row.get("attempts", 0),
                     row.get("idempotency_key", ""), Jsonb(row.get("payload") or {}),
                     Jsonb(row.get("response") or {}), reason, row.get("created_at")))
                conn.execute("DELETE FROM routing_outbox WHERE id=%s", (row["id"],))
        return dlq_id

    def close(self):  # pragma: no cover - needs PG
        self._pool.close()


class AsyncPostgresStore:  # pragma: no cover - requires live async PG
    """Asyncio psycopg pool for the gateway middleware + orphan-sweep cron.

    Every method borrows a connection and stamps ``search_path`` to the tenant
    schema for that operation, realizing the per-request schema routing from
    Task 1 against an async connection pool.
    """

    backend = "async-postgres"

    def __init__(self, dsn: str):
        from psycopg_pool import AsyncConnectionPool

        self._dsn = dsn
        self._pool = AsyncConnectionPool(dsn, min_size=1, max_size=8, open=False)
        self._opened = False

    async def open(self) -> None:
        if not self._opened:
            await self._pool.open()
            self._opened = True

    async def close(self) -> None:
        if self._opened:
            await self._pool.close()
            self._opened = False

    async def _set_schema(self, conn, schema: str | None):
        await conn.execute(f'SET search_path TO "{schema or "public"}", public')

    async def set_search_path(self, conn, tenant_id) -> str:
        """Public helper for the gateway middleware: bind a connection to the
        tenant schema for the lifetime of a request."""
        schema = schema_for_tenant(tenant_id) if tenant_id else "public"
        await self._set_schema(conn, schema)
        return schema

    async def provision_tenant(self, tenant_id):
        await self.open()
        schema = schema_for_tenant(tenant_id)
        async with self._pool.connection() as conn:
            await conn.execute("SELECT public.provision_tenant_schema(%s)", (schema,))
        return schema

    async def get_conversation(self, conversation_id, schema=None):
        from psycopg.rows import dict_row
        await self.open()
        async with self._pool.connection() as conn:
            await self._set_schema(conn, schema)
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM showroom_conversations WHERE id=%s",
                    (conversation_id,))
                row = await cur.fetchone()
        return _decode_row(row) if row else None

    async def due_orphans(self, cutoff_iso, schema=None, limit=100):
        from psycopg.rows import dict_row
        await self.open()
        async with self._pool.connection() as conn:
            await self._set_schema(conn, schema)
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM showroom_conversations"
                    " WHERE state NOT IN ('purged','error_purged')"
                    " AND created_at < %s ORDER BY created_at LIMIT %s",
                    (cutoff_iso, limit))
                rows = await cur.fetchall()
        return [_decode_row(r) for r in rows]

    async def mark_error_purged(self, conversation_id, schema=None, detail=""):
        await self.open()
        async with self._pool.connection() as conn:
            await self._set_schema(conn, schema)
            await conn.execute(
                "UPDATE showroom_conversations SET state='error_purged',"
                " erased_at=%s, error_detail=%s WHERE id=%s",
                (utcnow(), detail or "force-purged (orphan)", conversation_id))

    async def list_tenant_schemas(self):
        await self.open()
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "SELECT schema_name FROM information_schema.schemata"
                " WHERE schema_name LIKE 'schema\\_%%' ESCAPE '\\'")
            rows = await cur.fetchall()
        return [r[0] for r in rows]


def open_store(settings):
    """Synchronous store for the in-process pipeline (Postgres or SQLite mirror)."""
    if settings.has_supabase():
        try:
            return PostgresStore(settings.supabase_db_url)
        except Exception:
            pass
    return LocalStore(settings.local_path / "store")


def open_async_store(settings):
    """Async store for the gateway middleware + orphan sweep, or None offline."""
    if settings.has_supabase():
        try:
            return AsyncPostgresStore(settings.supabase_db_url)
        except Exception:
            return None
    return None
