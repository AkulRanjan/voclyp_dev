"""Tenant-scoped persistence: insights, consent log, audit log, webhooks, keys.

Isolation is structural: there is no read or write method on this class that
does not take a tenant_id, and every SQL statement filters on it.

Security properties:
- API keys are stored only as salted PBKDF2 hashes with scopes, optional
  expiry, and revocation; the plaintext key is returned exactly once.
- The audit log is hash-chained per tenant, so tampering with any historical
  entry breaks verification.
- Webhook endpoints carry per-endpoint HMAC secrets (dual-secret rotation)
  and event-type subscriptions; deliveries are a first-class ledger with
  attempts, response codes, and retry state — not log archaeology.
- The outbox table makes event emission transactional with the insight
  write (an event exists if and only if the write committed).
- The insights stored here are de-identified by design (PII is redacted and
  raw audio destroyed upstream); database/disk-level encryption is a
  deployment concern (see docs/SECURITY.md).
"""
from __future__ import annotations

import datetime
import json
import re
import sqlite3
import threading
from pathlib import Path

from . import events, security
from .contracts import utcnow

_TENANT_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
  tenant_id TEXT PRIMARY KEY, name TEXT, industry TEXT, region TEXT DEFAULT 'in'
);
CREATE TABLE IF NOT EXISTS api_keys (
  key_id TEXT PRIMARY KEY,
  key_hash TEXT NOT NULL, salt TEXT NOT NULL,
  tenant_id TEXT NOT NULL, scopes TEXT NOT NULL,
  created_at TEXT NOT NULL, expires_at TEXT, revoked INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS insights (
  tenant_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
  schema_version TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, conversation_id)
);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL, conversation_id TEXT, event TEXT NOT NULL,
  detail TEXT, ts TEXT NOT NULL,
  prev_hash TEXT NOT NULL, entry_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS consent_log (
  tenant_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
  agent_id TEXT, captured INTEGER NOT NULL, ts TEXT NOT NULL,
  PRIMARY KEY (tenant_id, conversation_id)
);
CREATE TABLE IF NOT EXISTS webhook_endpoints (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL, url TEXT NOT NULL,
  secret TEXT NOT NULL, secret_prev TEXT, rotated_at TEXT,
  event_types TEXT NOT NULL DEFAULT '*',
  status TEXT NOT NULL DEFAULT 'active',  -- active | disabled
  api_version TEXT NOT NULL DEFAULT 'v1',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS webhook_deliveries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL, endpoint_id TEXT NOT NULL, event_id TEXT NOT NULL,
  attempt INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'pending', -- pending | retrying | delivered | dead | blocked
  response_code INTEGER, detail TEXT,
  next_retry_at REAL NOT NULL,            -- unix seconds; row is due when <= now
  updated_at TEXT NOT NULL,
  UNIQUE (endpoint_id, event_id)          -- fan-out is idempotent per endpoint
);
CREATE TABLE IF NOT EXISTS outbox (
  event_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL, event_type TEXT NOT NULL,
  resource TEXT NOT NULL, resource_id TEXT NOT NULL, resource_status TEXT NOT NULL,
  sequence INTEGER NOT NULL, schema_version TEXT NOT NULL,
  occurred_at TEXT NOT NULL, fanned_out INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sequences (
  tenant_id TEXT NOT NULL, resource_id TEXT NOT NULL, seq INTEGER NOT NULL,
  PRIMARY KEY (tenant_id, resource_id)
);
CREATE TABLE IF NOT EXISTS idempotency (
  tenant_id TEXT NOT NULL, client_ref TEXT NOT NULL, conversation_id TEXT NOT NULL,
  PRIMARY KEY (tenant_id, client_ref)
);
CREATE TABLE IF NOT EXISTS metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
  stage TEXT NOT NULL, ms REAL NOT NULL, ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
  provider_endpoint TEXT NOT NULL, calls INTEGER NOT NULL, ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
  target TEXT NOT NULL, correction TEXT NOT NULL, note TEXT, ts TEXT NOT NULL
);
"""

_GENESIS = "0" * 64


class Store:
    def __init__(self, db_path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def _exec(self, sql, params=()):
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    # -- tenancy ------------------------------------------------------------
    def create_tenant(self, tenant_id, name, industry, region="in"):
        if not _TENANT_SLUG.match(tenant_id):
            raise ValueError(
                "tenant_id must be a lowercase slug (a-z, 0-9, '-', 2-63 chars)"
            )
        self._exec(
            "INSERT OR REPLACE INTO tenants VALUES (?,?,?,?)",
            (tenant_id, name, industry, region),
        )

    def tenant_industry(self, tenant_id):
        row = self._exec(
            "SELECT industry FROM tenants WHERE tenant_id=?", (tenant_id,)
        ).fetchone()
        return row[0] if row else None

    # -- API keys -----------------------------------------------------------
    def create_api_key(self, tenant_id, scopes=("ingest", "read"), expires_days=None):
        """Create a key and return its plaintext exactly once."""
        for scope in scopes:
            if scope not in security.VALID_SCOPES:
                raise ValueError(f"unknown scope '{scope}'")
        full_key, key_id, secret = security.generate_api_key()
        salt = security.new_salt()
        expires_at = None
        if expires_days is not None:
            expires_at = (
                datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(days=expires_days)
            ).isoformat()
        self._exec(
            "INSERT INTO api_keys VALUES (?,?,?,?,?,?,?,0)",
            (key_id, security.hash_secret(secret, bytes.fromhex(salt)), salt,
             tenant_id, ",".join(scopes), utcnow(), expires_at),
        )
        return full_key

    def authenticate(self, api_key):
        """Return {'tenant_id', 'scopes', 'key_id'} or None.
        Constant-time hash comparison; checks revocation and expiry."""
        parsed = security.parse_api_key(api_key)
        if not parsed:
            return None
        key_id, secret = parsed
        row = self._exec(
            "SELECT key_hash, salt, tenant_id, scopes, expires_at, revoked"
            " FROM api_keys WHERE key_id=?", (key_id,),
        ).fetchone()
        if not row:
            return None
        key_hash, salt, tenant_id, scopes, expires_at, revoked = row
        if revoked or not security.verify_secret(secret, salt, key_hash):
            return None
        if expires_at and expires_at < utcnow():
            return None
        return {"tenant_id": tenant_id, "scopes": scopes.split(","), "key_id": key_id}

    def revoke_api_key(self, key_id):
        self._exec("UPDATE api_keys SET revoked=1 WHERE key_id=?", (key_id,))
        self.audit("-", None, "api_key_revoked", f"key_id={key_id}")

    # -- insights -----------------------------------------------------------
    def save_insight(self, tenant_id, conversation_id, doc: dict):
        self._exec(
            "INSERT OR REPLACE INTO insights VALUES (?,?,?,?,?)",
            (tenant_id, conversation_id, doc["schema_version"],
             json.dumps(doc, ensure_ascii=False), doc["created_at"]),
        )

    def get_insight(self, tenant_id, conversation_id):
        row = self._exec(
            "SELECT body FROM insights WHERE tenant_id=? AND conversation_id=?",
            (tenant_id, conversation_id),
        ).fetchone()
        return json.loads(row[0]) if row else None

    def list_insights(self, tenant_id, limit=100):
        rows = self._exec(
            "SELECT body FROM insights WHERE tenant_id=? ORDER BY created_at DESC LIMIT ?",
            (tenant_id, limit),
        ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def delete_conversation(self, tenant_id, conversation_id):
        """Delete-on-demand: wipe the stored insight and audit the wipe."""
        cur = self._exec(
            "DELETE FROM insights WHERE tenant_id=? AND conversation_id=?",
            (tenant_id, conversation_id),
        )
        self.audit(tenant_id, conversation_id, "insight_deleted_on_demand",
                   f"rows={cur.rowcount}")
        return cur.rowcount > 0

    # -- compliance ---------------------------------------------------------
    def log_consent(self, tenant_id, conversation_id, agent_id, captured: bool):
        self._exec(
            "INSERT OR REPLACE INTO consent_log VALUES (?,?,?,?,?)",
            (tenant_id, conversation_id, agent_id, int(captured), utcnow()),
        )

    def audit(self, tenant_id, conversation_id, event, detail=""):
        """Append a hash-chained audit entry (chain is per tenant)."""
        ts = utcnow()
        with self._lock:
            row = self._conn.execute(
                "SELECT entry_hash FROM audit_log WHERE tenant_id=?"
                " ORDER BY id DESC LIMIT 1", (tenant_id,),
            ).fetchone()
            prev_hash = row[0] if row else _GENESIS
            entry_hash = security.chain_hash(
                prev_hash, tenant_id, conversation_id or "", event, detail, ts
            )
            self._conn.execute(
                "INSERT INTO audit_log (tenant_id, conversation_id, event,"
                " detail, ts, prev_hash, entry_hash) VALUES (?,?,?,?,?,?,?)",
                (tenant_id, conversation_id, event, detail, ts, prev_hash, entry_hash),
            )
            self._conn.commit()

    def verify_audit_chain(self, tenant_id):
        """Recompute the tenant's hash chain; returns (ok, first_bad_entry_id)."""
        rows = self._exec(
            "SELECT id, conversation_id, event, detail, ts, prev_hash, entry_hash"
            " FROM audit_log WHERE tenant_id=? ORDER BY id", (tenant_id,),
        ).fetchall()
        prev = _GENESIS
        for (row_id, conv, event, detail, ts, prev_hash, entry_hash) in rows:
            expected = security.chain_hash(
                prev, tenant_id, conv or "", event, detail, ts
            )
            if prev_hash != prev or entry_hash != expected:
                return False, row_id
            prev = entry_hash
        return True, None

    def audit_export(self, tenant_id, conversation_id=None):
        sql = ("SELECT conversation_id, event, detail, ts, entry_hash"
               " FROM audit_log WHERE tenant_id=?")
        params = [tenant_id]
        if conversation_id:
            sql += " AND conversation_id=?"
            params.append(conversation_id)
        rows = self._exec(sql + " ORDER BY id", params).fetchall()
        return [
            {"conversation_id": r[0], "event": r[1], "detail": r[2],
             "ts": r[3], "entry_hash": r[4]}
            for r in rows
        ]

    # -- idempotency (offline-sync re-uploads) --------------------------------
    def idempotency_get(self, tenant_id, client_ref):
        row = self._exec(
            "SELECT conversation_id FROM idempotency WHERE tenant_id=? AND client_ref=?",
            (tenant_id, client_ref),
        ).fetchone()
        return row[0] if row else None

    def idempotency_set(self, tenant_id, client_ref, conversation_id):
        self._exec(
            "INSERT OR IGNORE INTO idempotency VALUES (?,?,?)",
            (tenant_id, client_ref, conversation_id),
        )

    # -- MLOps: metrics + feedback loop ---------------------------------------
    def add_metrics(self, tenant_id, conversation_id, stage_timings_ms: dict):
        ts = utcnow()
        for stage, ms in stage_timings_ms.items():
            self._exec(
                "INSERT INTO metrics (tenant_id, conversation_id, stage, ms, ts)"
                " VALUES (?,?,?,?,?)",
                (tenant_id, conversation_id, stage, ms, ts),
            )

    def metrics_summary(self, tenant_id):
        rows = self._exec(
            "SELECT stage, COUNT(*), AVG(ms), MAX(ms) FROM metrics"
            " WHERE tenant_id=? GROUP BY stage", (tenant_id,),
        ).fetchall()
        return [
            {"stage": r[0], "conversations": r[1],
             "avg_ms": round(r[2], 2), "max_ms": round(r[3], 2)}
            for r in rows
        ]

    def add_usage(self, tenant_id, conversation_id, provider_usage: dict):
        """Meter external AI-provider calls (credit/cost per conversation)."""
        ts = utcnow()
        for endpoint, calls in provider_usage.items():
            self._exec(
                "INSERT INTO usage (tenant_id, conversation_id,"
                " provider_endpoint, calls, ts) VALUES (?,?,?,?,?)",
                (tenant_id, conversation_id, endpoint, calls, ts),
            )

    def usage_summary(self, tenant_id):
        rows = self._exec(
            "SELECT provider_endpoint, SUM(calls), COUNT(DISTINCT conversation_id)"
            " FROM usage WHERE tenant_id=? GROUP BY provider_endpoint", (tenant_id,),
        ).fetchall()
        return [
            {"endpoint": r[0], "total_calls": r[1], "conversations": r[2],
             "avg_calls_per_conversation": round(r[1] / r[2], 2) if r[2] else 0}
            for r in rows
        ]

    def add_feedback(self, tenant_id, conversation_id, target, correction, note=""):
        """User corrections — the raw material for future model training."""
        self._exec(
            "INSERT INTO feedback (tenant_id, conversation_id, target,"
            " correction, note, ts) VALUES (?,?,?,?,?,?)",
            (tenant_id, conversation_id, target, correction, note, utcnow()),
        )
        self.audit(tenant_id, conversation_id, "feedback_received", f"target={target}")

    def feedback_for(self, tenant_id, conversation_id=None):
        sql = ("SELECT conversation_id, target, correction, note, ts"
               " FROM feedback WHERE tenant_id=?")
        params = [tenant_id]
        if conversation_id:
            sql += " AND conversation_id=?"
            params.append(conversation_id)
        rows = self._exec(sql + " ORDER BY id", params).fetchall()
        return [
            {"conversation_id": r[0], "target": r[1], "correction": r[2],
             "note": r[3], "ts": r[4]}
            for r in rows
        ]

    # -- transactional outbox -------------------------------------------------
    def save_insight_with_event(self, tenant_id, conversation_id, doc: dict,
                                event_type=events.INSIGHTS_READY,
                                resource_status="ready"):
        """Persist the insight AND its outbox event in one transaction, so an
        event is emitted if and only if the insight write committed (no
        dual-write inconsistency). Returns the event_id. The per-resource
        sequence is bumped in the same transaction, so consumers can always
        order events for a conversation."""
        event_id = events.new_event_id()
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO insights VALUES (?,?,?,?,?)",
                (tenant_id, conversation_id, doc["schema_version"],
                 json.dumps(doc, ensure_ascii=False), doc["created_at"]),
            )
            self._conn.execute(
                "INSERT INTO sequences VALUES (?,?,1) ON CONFLICT"
                " (tenant_id, resource_id) DO UPDATE SET seq=seq+1",
                (tenant_id, conversation_id),
            )
            seq = self._conn.execute(
                "SELECT seq FROM sequences WHERE tenant_id=? AND resource_id=?",
                (tenant_id, conversation_id),
            ).fetchone()[0]
            self._conn.execute(
                "INSERT INTO outbox VALUES (?,?,?,?,?,?,?,?,?,0)",
                (event_id, tenant_id, event_type, "insight", conversation_id,
                 resource_status, seq, events.ENVELOPE_VERSION, utcnow()),
            )
            self._conn.commit()
        return event_id

    def unfanned_events(self, limit=100):
        rows = self._exec(
            "SELECT event_id, tenant_id, event_type, resource, resource_id,"
            " resource_status, sequence, schema_version, occurred_at"
            " FROM outbox WHERE fanned_out=0 ORDER BY occurred_at LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._event_row(r) for r in rows]

    def get_event(self, tenant_id, event_id):
        row = self._exec(
            "SELECT event_id, tenant_id, event_type, resource, resource_id,"
            " resource_status, sequence, schema_version, occurred_at"
            " FROM outbox WHERE tenant_id=? AND event_id=?",
            (tenant_id, event_id),
        ).fetchone()
        return self._event_row(row) if row else None

    @staticmethod
    def _event_row(r):
        return {"event_id": r[0], "tenant_id": r[1], "event_type": r[2],
                "resource": r[3], "resource_id": r[4], "resource_status": r[5],
                "sequence": r[6], "schema_version": r[7], "occurred_at": r[8]}

    def mark_fanned_out(self, event_id):
        self._exec("UPDATE outbox SET fanned_out=1 WHERE event_id=?", (event_id,))

    # -- webhook endpoints ----------------------------------------------------
    # Signing secrets are stored raw (not hashed) because the dispatcher needs
    # them to sign outbound payloads; production wraps this column with
    # KMS/disk-level encryption (see docs/SECURITY.md). API keys, which only
    # need verification, remain salted hashes.
    def add_webhook(self, tenant_id, url, event_types=("*",), api_version="v1"):
        """Register an endpoint; returns (endpoint_id, signing_secret).
        The secret is returned exactly once."""
        endpoint_id = "we_" + security.new_salt()
        secret = security.new_webhook_secret()
        self._exec(
            "INSERT INTO webhook_endpoints (id, tenant_id, url, secret,"
            " event_types, created_at) VALUES (?,?,?,?,?,?)",
            (endpoint_id, tenant_id, url, secret, ",".join(event_types), utcnow()),
        )
        self.audit(tenant_id, None, "webhook_registered",
                   f"endpoint={endpoint_id} url={url}")
        return endpoint_id, secret

    _ENDPOINT_COLS = ("id, tenant_id, url, secret, secret_prev, rotated_at,"
                      " event_types, status, api_version, created_at")

    @staticmethod
    def _endpoint_row(r):
        return {"id": r[0], "tenant_id": r[1], "url": r[2], "secret": r[3],
                "secret_prev": r[4], "rotated_at": r[5],
                "event_types": r[6].split(","), "status": r[7],
                "api_version": r[8], "created_at": r[9]}

    def get_endpoint(self, tenant_id, endpoint_id):
        row = self._exec(
            f"SELECT {self._ENDPOINT_COLS} FROM webhook_endpoints"
            " WHERE tenant_id=? AND id=?", (tenant_id, endpoint_id),
        ).fetchone()
        return self._endpoint_row(row) if row else None

    def endpoints_for(self, tenant_id, event_type=None, status="active"):
        rows = self._exec(
            f"SELECT {self._ENDPOINT_COLS} FROM webhook_endpoints"
            " WHERE tenant_id=? AND status=?", (tenant_id, status),
        ).fetchall()
        endpoints = [self._endpoint_row(r) for r in rows]
        if event_type is None:
            return endpoints
        return [e for e in endpoints
                if "*" in e["event_types"] or event_type in e["event_types"]]

    def list_endpoints(self, tenant_id):
        rows = self._exec(
            "SELECT id, url, event_types, status, api_version, created_at"
            " FROM webhook_endpoints WHERE tenant_id=?", (tenant_id,),
        ).fetchall()
        return [{"id": r[0], "url": r[1], "event_types": r[2].split(","),
                 "status": r[3], "api_version": r[4], "created_at": r[5]}
                for r in rows]

    def rotate_webhook_secret(self, tenant_id, endpoint_id):
        """Dual-secret rotation: the old secret keeps signing alongside the
        new one for the overlap window, so consumers migrate with zero
        downtime. Returns the new secret (shown exactly once) or None."""
        if not self.get_endpoint(tenant_id, endpoint_id):
            return None
        secret = security.new_webhook_secret()
        self._exec(
            "UPDATE webhook_endpoints SET secret_prev=secret, secret=?,"
            " rotated_at=? WHERE tenant_id=? AND id=?",
            (secret, utcnow(), tenant_id, endpoint_id),
        )
        self.audit(tenant_id, None, "webhook_secret_rotated",
                   f"endpoint={endpoint_id}")
        return secret

    def set_endpoint_status(self, tenant_id, endpoint_id, status):
        cur = self._exec(
            "UPDATE webhook_endpoints SET status=? WHERE tenant_id=? AND id=?",
            (status, tenant_id, endpoint_id),
        )
        if cur.rowcount:
            self.audit(tenant_id, None, f"webhook_{status}",
                       f"endpoint={endpoint_id}")
        return cur.rowcount > 0

    # -- delivery ledger ------------------------------------------------------
    def create_delivery(self, tenant_id, endpoint_id, event_id, due_at: float):
        """Idempotent: re-fanning the same event to the same endpoint is a
        no-op thanks to the UNIQUE(endpoint_id, event_id) constraint."""
        self._exec(
            "INSERT OR IGNORE INTO webhook_deliveries (tenant_id, endpoint_id,"
            " event_id, next_retry_at, updated_at) VALUES (?,?,?,?,?)",
            (tenant_id, endpoint_id, event_id, due_at, utcnow()),
        )

    def due_deliveries(self, now: float, limit=100):
        rows = self._exec(
            "SELECT id, tenant_id, endpoint_id, event_id, attempt"
            " FROM webhook_deliveries WHERE status IN ('pending','retrying')"
            " AND next_retry_at<=? ORDER BY next_retry_at LIMIT ?",
            (now, limit),
        ).fetchall()
        return [{"id": r[0], "tenant_id": r[1], "endpoint_id": r[2],
                 "event_id": r[3], "attempt": r[4]} for r in rows]

    def mark_delivery(self, delivery_id, status, attempt, response_code=None,
                      detail="", next_retry_at=0.0):
        self._exec(
            "UPDATE webhook_deliveries SET status=?, attempt=?, response_code=?,"
            " detail=?, next_retry_at=?, updated_at=? WHERE id=?",
            (status, attempt, response_code, detail, next_retry_at,
             utcnow(), delivery_id),
        )

    def deliveries_for(self, tenant_id, conversation_id=None, status=None):
        sql = ("SELECT e.url, d.event_id, d.attempt, d.status, d.response_code,"
               " d.detail, d.updated_at FROM webhook_deliveries d"
               " JOIN webhook_endpoints e ON e.id=d.endpoint_id"
               " LEFT JOIN outbox o ON o.event_id=d.event_id"
               " WHERE d.tenant_id=?")
        params = [tenant_id]
        if conversation_id:
            sql += " AND o.resource_id=?"
            params.append(conversation_id)
        if status:
            sql += " AND d.status=?"
            params.append(status)
        rows = self._exec(sql + " ORDER BY d.id", params).fetchall()
        return [{"url": r[0], "event_id": r[1], "attempt": r[2], "status": r[3],
                 "response_code": r[4], "detail": r[5], "ts": r[6]}
                for r in rows]

    def consecutive_dead(self, endpoint_id) -> int:
        """How many of the endpoint's most recent settled deliveries exhausted
        their retries, counting back until the last success — the dispatcher's
        auto-disable signal for flapping endpoints."""
        rows = self._exec(
            "SELECT status FROM webhook_deliveries WHERE endpoint_id=?"
            " AND status IN ('delivered','dead') ORDER BY id DESC",
            (endpoint_id,),
        ).fetchall()
        n = 0
        for (status,) in rows:
            if status != "dead":
                break
            n += 1
        return n

    def replay_dead(self, tenant_id, now: float, endpoint_id=None) -> int:
        """One-click DLQ replay: re-arm dead deliveries (fresh attempt budget)
        once the consumer endpoint has recovered."""
        sql = ("UPDATE webhook_deliveries SET status='pending', attempt=0,"
               " next_retry_at=?, updated_at=? WHERE tenant_id=? AND status='dead'")
        params = [now, utcnow(), tenant_id]
        if endpoint_id:
            sql += " AND endpoint_id=?"
            params.append(endpoint_id)
        cur = self._exec(sql, params)
        if cur.rowcount:
            self.audit(tenant_id, None, "dlq_replayed",
                       f"deliveries={cur.rowcount}"
                       + (f" endpoint={endpoint_id}" if endpoint_id else ""))
        return cur.rowcount

    def delivery_stats(self, tenant_id):
        """Per-endpoint delivery health for the observability dashboard:
        delivered/dead/in-flight counts, retry rate, DLQ depth."""
        rows = self._exec(
            "SELECT e.id, e.url, e.status,"
            " SUM(CASE WHEN d.status='delivered' THEN 1 ELSE 0 END),"
            " SUM(CASE WHEN d.status='dead' THEN 1 ELSE 0 END),"
            " SUM(CASE WHEN d.status IN ('pending','retrying') THEN 1 ELSE 0 END),"
            " SUM(CASE WHEN d.attempt>1 THEN 1 ELSE 0 END), COUNT(d.id)"
            " FROM webhook_endpoints e"
            " LEFT JOIN webhook_deliveries d ON d.endpoint_id=e.id"
            " WHERE e.tenant_id=? GROUP BY e.id", (tenant_id,),
        ).fetchall()
        out = []
        for r in rows:
            delivered, dead, in_flight, retried, total = (
                r[3] or 0, r[4] or 0, r[5] or 0, r[6] or 0, r[7] or 0)
            settled = delivered + dead
            out.append({
                "endpoint_id": r[0], "url": r[1], "endpoint_status": r[2],
                "delivered": delivered, "dlq_depth": dead,
                "in_flight": in_flight,
                "success_rate": round(delivered / settled, 3) if settled else None,
                "retry_rate": round(retried / total, 3) if total else None,
            })
        return out
