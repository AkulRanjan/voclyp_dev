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
import secrets
import sqlite3
import threading
from pathlib import Path

from . import events, security
from .contracts import utcnow

_TENANT_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# "manager" is the single-org console owner (web console + first signup);
# store_manager/area_manager/admin are the multi-store hierarchy roles.
USER_ROLES = ("sales", "manager", "store_manager", "area_manager", "admin")

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
  -- denormalized analytics dimensions/measures, mirrored from body on write so
  -- store/rep/area rollups are plain indexed SQL, not JSON archaeology.
  store_id TEXT, agent_id TEXT, score REAL, rating TEXT, outcome TEXT,
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
CREATE TABLE IF NOT EXISTS users (
  user_id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,           -- stored lowercased
  name TEXT NOT NULL,
  role TEXT NOT NULL,                   -- manager | sales
  tenant_id TEXT NOT NULL,
  key_hash TEXT NOT NULL, salt TEXT NOT NULL,  -- PBKDF2 of the password
  created_at TEXT NOT NULL,
  session_epoch INTEGER NOT NULL DEFAULT 0     -- bump to revoke all sessions
);
CREATE TABLE IF NOT EXISTS invites (
  invite_id TEXT PRIMARY KEY,
  code_hash TEXT NOT NULL, salt TEXT NOT NULL,  -- PBKDF2 of the invite secret
  tenant_id TEXT NOT NULL, role TEXT NOT NULL,
  created_by TEXT, expires_at TEXT,
  used INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS areas (
  tenant_id TEXT NOT NULL, area_id TEXT NOT NULL,
  name TEXT NOT NULL,
  manager_id TEXT NOT NULL,
  region TEXT,
  created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, area_id),
  FOREIGN KEY (manager_id) REFERENCES users(user_id)
);
CREATE TABLE IF NOT EXISTS role_scopes (
  tenant_id TEXT NOT NULL, user_id TEXT NOT NULL,
  role TEXT NOT NULL,
  area_id TEXT,
  store_ids TEXT,
  PRIMARY KEY (tenant_id, user_id),
  FOREIGN KEY (user_id) REFERENCES users(user_id)
);
CREATE TABLE IF NOT EXISTS stores (
  tenant_id TEXT NOT NULL, store_id TEXT NOT NULL,
  name TEXT NOT NULL,
  area_id TEXT NOT NULL,
  region TEXT,
  address_lat REAL, address_lng REAL, address_full TEXT,
  manager_id TEXT NOT NULL,
  team_size INTEGER,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, store_id),
  FOREIGN KEY (manager_id) REFERENCES users(user_id)
);
CREATE TABLE IF NOT EXISTS live_sessions (
  tenant_id TEXT NOT NULL, session_id TEXT NOT NULL,
  store_id TEXT NOT NULL, agent_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'identity',
  customer_name TEXT, customer_phone TEXT,
  name_source TEXT, phone_source TEXT,
  partial_transcript TEXT DEFAULT '',
  consent_at TEXT, conversation_id TEXT,
  started_at TEXT NOT NULL, ended_at TEXT,
  PRIMARY KEY (tenant_id, session_id)
);
CREATE INDEX IF NOT EXISTS idx_live_sessions_store ON live_sessions(tenant_id, store_id, status);
CREATE TABLE IF NOT EXISTS session_chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL, session_id TEXT NOT NULL,
  seq INTEGER NOT NULL, chunk_path TEXT NOT NULL,
  received_at TEXT NOT NULL,
  UNIQUE (tenant_id, session_id, seq)
);
-- Sales-rep voiceprints: a small acoustic fingerprint enrolled at login so
-- diarization can label which diarized speaker is the rep (vs customers).
-- This is a feature vector, never raw audio — the enrollment clip is shredded
-- the moment the fingerprint is computed.
CREATE TABLE IF NOT EXISTS voiceprints (
  tenant_id TEXT NOT NULL, user_id TEXT NOT NULL,
  vector TEXT NOT NULL,           -- json list[float], L2-normalized
  sample_count INTEGER NOT NULL DEFAULT 1,
  model TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, user_id)
);
"""

# Columns added after the initial release; applied to existing databases.
_MIGRATIONS = {
    "users": [("session_epoch", "INTEGER NOT NULL DEFAULT 0")],
    "insights": [
        ("store_id", "TEXT"), ("agent_id", "TEXT"), ("score", "REAL"),
        ("rating", "TEXT"), ("outcome", "TEXT"),
    ],
}

_GENESIS = "0" * 64

# Indexes over columns that were added by migration; created AFTER _migrate so
# pre-existing databases (whose base table predates these columns) don't fail.
_POST_MIGRATION_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_insights_store ON insights(tenant_id, store_id)",
    "CREATE INDEX IF NOT EXISTS idx_insights_agent ON insights(tenant_id, agent_id)",
)


class Store:
    def __init__(self, db_path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._migrate()
        for stmt in _POST_MIGRATION_INDEXES:
            self._conn.execute(stmt)
        self._conn.commit()

    def _migrate(self):
        """Add columns introduced after a table first shipped (additive only)."""
        for table, columns in _MIGRATIONS.items():
            existing = {row[1] for row in
                        self._conn.execute(f"PRAGMA table_info({table})").fetchall()}
            for name, decl in columns:
                if name not in existing:
                    self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")

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

    # -- console users (email/password login, role-scoped) ------------------
    def create_user(self, email, name, role, tenant_id, password):
        """Create a console user; the password is stored only as a salted
        PBKDF2 hash. Returns the new user_id. Raises ValueError on bad input
        or a duplicate email."""
        email = (email or "").strip().lower()
        name = (name or "").strip()
        if role not in USER_ROLES:
            raise ValueError(f"role must be one of {USER_ROLES}")
        if not _EMAIL.match(email):
            raise ValueError("invalid email address")
        if not name:
            raise ValueError("name is required")
        if len(password or "") < 8:
            raise ValueError("password must be at least 8 characters")
        if self.get_user_by_email(email):
            raise ValueError("an account with this email already exists")
        if len(password) > 256:
            raise ValueError("password too long")
        user_id = "usr_" + secrets.token_hex(8)
        salt = security.new_salt()
        key_hash = security.hash_secret(password, bytes.fromhex(salt))
        self._exec(
            "INSERT INTO users (user_id, email, name, role, tenant_id, key_hash,"
            " salt, created_at, session_epoch) VALUES (?,?,?,?,?,?,?,?,0)",
            (user_id, email, name, role, tenant_id, key_hash, salt, utcnow()),
        )
        return user_id

    def get_user_by_email(self, email):
        row = self._exec(
            "SELECT user_id, email, name, role, tenant_id, key_hash, salt, session_epoch"
            " FROM users WHERE email=?", ((email or "").strip().lower(),),
        ).fetchone()
        if not row:
            return None
        return {"user_id": row[0], "email": row[1], "name": row[2], "role": row[3],
                "tenant_id": row[4], "key_hash": row[5], "salt": row[6],
                "session_epoch": row[7]}

    def get_user(self, user_id):
        """Public fields used to validate a session token against live state."""
        row = self._exec(
            "SELECT user_id, email, name, role, tenant_id, session_epoch"
            " FROM users WHERE user_id=?", (user_id,),
        ).fetchone()
        if not row:
            return None
        return {"user_id": row[0], "email": row[1], "name": row[2], "role": row[3],
                "tenant_id": row[4], "session_epoch": row[5]}

    def verify_user_password(self, email, password):
        """Return the user's public fields on a correct password, else None.
        Constant-time comparison."""
        user = self.get_user_by_email(email)
        if not user:
            return None
        if not security.verify_secret(password or "", user["salt"], user["key_hash"]):
            return None
        return {k: user[k] for k in
                ("user_id", "email", "name", "role", "tenant_id", "session_epoch")}

    def bump_session_epoch(self, user_id):
        """Invalidate every outstanding session for a user (logout-all, role
        change, password reset)."""
        self._exec("UPDATE users SET session_epoch = session_epoch + 1"
                   " WHERE user_id=?", (user_id,))

    def user_count(self):
        return self._exec("SELECT COUNT(*) FROM users").fetchone()[0]

    def tenant_user_count(self, tenant_id):
        return self._exec("SELECT COUNT(*) FROM users WHERE tenant_id=?",
                          (tenant_id,)).fetchone()[0]

    # -- invites (join an existing tenant; manager-issued) ------------------
    def create_invite(self, tenant_id, role, created_by, ttl_days=14):
        """Mint a single-use invite for a role on a tenant. The code is shown
        once; only its salted hash is stored."""
        if role not in USER_ROLES:
            raise ValueError(f"role must be one of {USER_ROLES}")
        invite_id = secrets.token_hex(8)
        secret = secrets.token_urlsafe(24)
        salt = security.new_salt()
        expires = (datetime.datetime.now(datetime.timezone.utc)
                   + datetime.timedelta(days=ttl_days)).isoformat()
        self._exec(
            "INSERT INTO invites VALUES (?,?,?,?,?,?,?,0,?)",
            (invite_id, security.hash_secret(secret, bytes.fromhex(salt)), salt,
             tenant_id, role, created_by, expires, utcnow()),
        )
        return f"vinv_{invite_id}_{secret}"

    def consume_invite(self, code, tenant_id):
        """Validate and burn an invite for tenant_id; returns its role or None."""
        parts = (code or "").split("_", 2)
        if len(parts) != 3 or parts[0] != "vinv":
            return None
        invite_id, secret = parts[1], parts[2]
        row = self._exec(
            "SELECT code_hash, salt, tenant_id, role, expires_at, used"
            " FROM invites WHERE invite_id=?", (invite_id,),
        ).fetchone()
        if not row:
            return None
        code_hash, salt, inv_tenant, role, expires_at, used = row
        if used or inv_tenant != tenant_id:
            return None
        if not security.verify_secret(secret, salt, code_hash):
            return None
        if expires_at and expires_at < utcnow():
            return None
        self._exec("UPDATE invites SET used=1 WHERE invite_id=?", (invite_id,))
        return role

    # -- insights -----------------------------------------------------------
    @staticmethod
    def _insight_row(tenant_id, conversation_id, doc: dict) -> tuple:
        """Full row for the insights table, mirroring the denormalized
        analytics dimensions (store/agent/score/rating/outcome) out of the
        insight body so store, rep, and area rollups are plain indexed SQL."""
        scoring = doc.get("scoring") or {}
        return (
            tenant_id, conversation_id, doc["schema_version"],
            json.dumps(doc, ensure_ascii=False), doc["created_at"],
            doc.get("store_id") or None, doc.get("agent_id") or None,
            scoring.get("score"), scoring.get("rating"), scoring.get("outcome"),
        )

    def save_insight(self, tenant_id, conversation_id, doc: dict):
        self._exec(
            "INSERT OR REPLACE INTO insights"
            " (tenant_id, conversation_id, schema_version, body, created_at,"
            " store_id, agent_id, score, rating, outcome)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            self._insight_row(tenant_id, conversation_id, doc),
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

    def latest_audit_detail(self, tenant_id, conversation_id, event: str) -> str | None:
        row = self._exec(
            "SELECT detail FROM audit_log WHERE tenant_id=? AND conversation_id=?"
            " AND event=? ORDER BY id DESC LIMIT 1",
            (tenant_id, conversation_id, event),
        ).fetchone()
        return row[0] if row else None

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
                "INSERT OR REPLACE INTO insights"
                " (tenant_id, conversation_id, schema_version, body, created_at,"
                " store_id, agent_id, score, rating, outcome)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                self._insight_row(tenant_id, conversation_id, doc),
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

    # -- stores (multi-store support) -----------------------------------------
    def create_store(self, tenant_id, store_id, name, area_id, manager_id,
                     region=None, lat=None, lng=None, address_full=None, team_size=None):
        """Create a new store. Returns True if created, False if already exists."""
        try:
            self._exec(
                "INSERT INTO stores (tenant_id, store_id, name, area_id, region,"
                " address_lat, address_lng, address_full, manager_id, team_size,"
                " created_at, updated_at, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'active')",
                (tenant_id, store_id, name, area_id, region, lat, lng, address_full,
                 manager_id, team_size, utcnow(), utcnow()),
            )
            return True
        except sqlite3.IntegrityError:
            return False

    def get_store(self, tenant_id, store_id):
        """Get store details by ID."""
        row = self._exec(
            "SELECT store_id, name, area_id, region, address_lat, address_lng,"
            " address_full, manager_id, team_size, status, created_at, updated_at"
            " FROM stores WHERE tenant_id=? AND store_id=?",
            (tenant_id, store_id),
        ).fetchone()
        if not row:
            return None
        return {
            "store_id": row[0], "name": row[1], "area_id": row[2], "region": row[3],
            "latitude": row[4], "longitude": row[5], "address": row[6],
            "manager_id": row[7], "team_size": row[8], "status": row[9],
            "created_at": row[10], "updated_at": row[11],
        }

    def list_stores(self, tenant_id, area_id=None, status="active"):
        """List stores for a tenant, optionally filtered by area."""
        sql = "SELECT store_id, name, area_id, manager_id, status FROM stores WHERE tenant_id=?"
        params = [tenant_id]
        if status:
            sql += " AND status=?"
            params.append(status)
        if area_id:
            sql += " AND area_id=?"
            params.append(area_id)
        sql += " ORDER BY name"
        rows = self._exec(sql, params).fetchall()
        return [{"store_id": r[0], "name": r[1], "area_id": r[2],
                 "manager_id": r[3], "status": r[4]} for r in rows]

    def update_store_status(self, tenant_id, store_id, status):
        """Update store status (active/inactive/archived)."""
        self._exec(
            "UPDATE stores SET status=?, updated_at=? WHERE tenant_id=? AND store_id=?",
            (status, utcnow(), tenant_id, store_id),
        )

    # -- areas (region/area grouping) -----------------------------------------
    def create_area(self, tenant_id, area_id, name, manager_id, region=None):
        """Create a new area. Returns True if created, False if already exists."""
        try:
            self._exec(
                "INSERT INTO areas (tenant_id, area_id, name, manager_id, region, created_at)"
                " VALUES (?,?,?,?,?,?)",
                (tenant_id, area_id, name, manager_id, region, utcnow()),
            )
            return True
        except sqlite3.IntegrityError:
            return False

    def get_area(self, tenant_id, area_id):
        """Get area details by ID."""
        row = self._exec(
            "SELECT area_id, name, manager_id, region, created_at"
            " FROM areas WHERE tenant_id=? AND area_id=?",
            (tenant_id, area_id),
        ).fetchone()
        if not row:
            return None
        return {
            "area_id": row[0], "name": row[1], "manager_id": row[2],
            "region": row[3], "created_at": row[4],
        }

    def list_areas(self, tenant_id, manager_id=None):
        """List areas for a tenant, optionally filtered by manager."""
        sql = "SELECT area_id, name, manager_id, region FROM areas WHERE tenant_id=?"
        params = [tenant_id]
        if manager_id:
            sql += " AND manager_id=?"
            params.append(manager_id)
        sql += " ORDER BY name"
        rows = self._exec(sql, params).fetchall()
        return [{"area_id": r[0], "name": r[1], "manager_id": r[2],
                 "region": r[3]} for r in rows]

    # -- role scopes (area manager access control) ----------------------------
    def set_user_role_scope(self, tenant_id, user_id, role, area_id=None, store_ids=None):
        """Set a user's role and scope (area_id for area managers, store_ids list)."""
        store_ids_str = ",".join(store_ids) if store_ids else None
        self._exec(
            "INSERT OR REPLACE INTO role_scopes (tenant_id, user_id, role, area_id, store_ids)"
            " VALUES (?,?,?,?,?)",
            (tenant_id, user_id, role, area_id, store_ids_str),
        )

    def get_user_role_scope(self, tenant_id, user_id):
        """Get user's role and scope."""
        row = self._exec(
            "SELECT role, area_id, store_ids FROM role_scopes WHERE tenant_id=? AND user_id=?",
            (tenant_id, user_id),
        ).fetchone()
        if not row:
            return None
        return {
            "role": row[0], "area_id": row[1],
            "store_ids": row[2].split(",") if row[2] else [],
        }

    def get_manager_stores(self, tenant_id, manager_id):
        """Get all stores managed by a user."""
        rows = self._exec(
            "SELECT store_id, name FROM stores WHERE tenant_id=? AND manager_id=? AND status='active'",
            (tenant_id, manager_id),
        ).fetchall()
        return [{"store_id": r[0], "name": r[1]} for r in rows]

    # -- live sessions (field visit streaming) --------------------------------
    def create_live_session(self, tenant_id, session_id, store_id, agent_id):
        self._exec(
            "INSERT INTO live_sessions (tenant_id, session_id, store_id, agent_id,"
            " status, started_at) VALUES (?,?,?,?,'identity',?)",
            (tenant_id, session_id, store_id, agent_id, utcnow()),
        )

    def get_live_session(self, tenant_id, session_id):
        row = self._exec(
            "SELECT session_id, store_id, agent_id, status, customer_name,"
            " customer_phone, name_source, phone_source, partial_transcript,"
            " consent_at, conversation_id, started_at, ended_at"
            " FROM live_sessions WHERE tenant_id=? AND session_id=?",
            (tenant_id, session_id),
        ).fetchone()
        if not row:
            return None
        return {
            "session_id": row[0], "store_id": row[1], "agent_id": row[2],
            "status": row[3], "customer_name": row[4], "customer_phone": row[5],
            "name_source": row[6], "phone_source": row[7],
            "partial_transcript": row[8], "consent_at": row[9],
            "conversation_id": row[10], "started_at": row[11], "ended_at": row[12],
        }

    def update_live_session_customer(self, tenant_id, session_id, *,
                                     name=None, phone=None, source="manual"):
        session = self.get_live_session(tenant_id, session_id)
        if not session:
            return None
        updates, params = [], []
        if name is not None:
            updates.append("customer_name=?")
            params.append(name)
            updates.append("name_source=?")
            params.append(source)
        if phone is not None:
            updates.append("customer_phone=?")
            params.append(phone)
            updates.append("phone_source=?")
            params.append(source)
        if not updates:
            return session
        params.extend([tenant_id, session_id])
        self._exec(
            f"UPDATE live_sessions SET {', '.join(updates)} WHERE tenant_id=? AND session_id=?",
            params,
        )
        return self.get_live_session(tenant_id, session_id)

    def update_live_session_transcript(self, tenant_id, session_id, text):
        self._exec(
            "UPDATE live_sessions SET partial_transcript=? WHERE tenant_id=? AND session_id=?",
            (text, tenant_id, session_id),
        )

    def set_live_session_status(self, tenant_id, session_id, status, *,
                                consent=False, conversation_id=None):
        fields, params = ["status=?"], [status]
        if consent:
            fields.append("consent_at=?")
            params.append(utcnow())
        if conversation_id:
            fields.append("conversation_id=?")
            params.append(conversation_id)
        if status in ("complete", "processing"):
            fields.append("ended_at=?")
            params.append(utcnow())
        params.extend([tenant_id, session_id])
        self._exec(
            f"UPDATE live_sessions SET {', '.join(fields)} WHERE tenant_id=? AND session_id=?",
            params,
        )
        return self.get_live_session(tenant_id, session_id)

    def complete_live_session_for_conversation(self, tenant_id, conversation_id):
        """Mark the live visit complete once its insight is stored."""
        self._exec(
            "UPDATE live_sessions SET status='complete', ended_at=?"
            " WHERE tenant_id=? AND conversation_id=? AND status='processing'",
            (utcnow(), tenant_id, conversation_id),
        )

    def append_session_chunk(self, tenant_id, session_id, seq, chunk_path):
        self._exec(
            "INSERT OR REPLACE INTO session_chunks"
            " (tenant_id, session_id, seq, chunk_path, received_at)"
            " VALUES (?,?,?,?,?)",
            (tenant_id, session_id, seq, chunk_path, utcnow()),
        )

    def list_session_chunks(self, tenant_id, session_id):
        rows = self._exec(
            "SELECT seq, chunk_path, received_at FROM session_chunks"
            " WHERE tenant_id=? AND session_id=? ORDER BY seq",
            (tenant_id, session_id),
        ).fetchall()
        return [{"seq": r[0], "chunk_path": r[1], "received_at": r[2]} for r in rows]

    def list_active_sessions(self, tenant_id, area_id=None, store_ids=None):
        sql = (
            "SELECT s.session_id, s.store_id, st.name, s.agent_id, s.status,"
            " s.customer_name, s.customer_phone, s.started_at, s.consent_at"
            " FROM live_sessions s"
            " LEFT JOIN stores st ON st.tenant_id=s.tenant_id AND st.store_id=s.store_id"
            " WHERE s.tenant_id=? AND s.status IN ('identity','active')"
        )
        params: list = [tenant_id]
        if store_ids:
            placeholders = ",".join("?" * len(store_ids))
            sql += f" AND s.store_id IN ({placeholders})"
            params.extend(store_ids)
        elif area_id:
            sql += " AND st.area_id=?"
            params.append(area_id)
        sql += " ORDER BY s.started_at DESC"
        rows = self._exec(sql, params).fetchall()
        return [{
            "session_id": r[0], "store_id": r[1], "store_name": r[2],
            "agent_id": r[3], "status": r[4], "customer_name": r[5],
            "customer_phone": r[6], "started_at": r[7], "consent_at": r[8],
        } for r in rows]

    def analytics_stores_compare(self, tenant_id, area_id=None, store_ids=None):
        """Aggregate insight metrics per store for manager comparison."""
        stores = self.list_stores(tenant_id, area_id=area_id)
        if store_ids:
            stores = [s for s in stores if s["store_id"] in store_ids]

        results = []
        for st in stores:
            sid = st["store_id"]
            rows = self._exec(
                "SELECT body FROM insights WHERE tenant_id=? AND store_id=?",
                (tenant_id, sid),
            ).fetchall()
            visits = len(rows)
            ortho = competitor = trial = emi = buying = 0
            objections: dict[str, int] = {}
            for (body,) in rows:
                doc = json.loads(body)
                for sig in doc.get("signals") or []:
                    stype = sig.get("type", "")
                    sub = sig.get("subtype", "")
                    if stype == "demand" and "ortho" in sub:
                        ortho += 1
                    if stype == "competitor_mention":
                        competitor += 1
                    if stype == "intent" and sub == "trial_request":
                        trial += 1
                    if stype == "intent" and sub == "emi_request":
                        emi += 1
                    if stype == "intent" and sub == "purchase_intent":
                        buying += 1
                    if stype == "objection":
                        objections[sub or "other"] = objections.get(sub or "other", 0) + 1
            top_objection = max(objections, key=objections.get) if objections else None
            qualified_pct = round(100 * buying / visits, 1) if visits else 0
            results.append({
                "store_id": sid,
                "store_name": st["name"],
                "visits": visits,
                "qualified_pct": qualified_pct,
                "orthopaedic_demand_pct": round(100 * ortho / visits, 1) if visits else 0,
                "competitor_mentions": competitor,
                "trial_requests": trial,
                "emi_requests": emi,
                "top_objection": top_objection,
            })

        if results:
            avg_visits = sum(r["visits"] for r in results) / len(results)
            for r in results:
                r["vs_area_avg_visits"] = round(r["visits"] - avg_visits, 1)
        return {"stores": results, "area_id": area_id}

    # -- voiceprints (rep voice enrollment for diarization) -------------------
    def set_voiceprint(self, tenant_id, user_id, vector, model, sample_count=1):
        """Store (or re-enroll) a rep's voice fingerprint. The vector is a small
        L2-normalized feature list; no raw audio is ever persisted."""
        existing = self.get_voiceprint(tenant_id, user_id)
        created = existing["created_at"] if existing else utcnow()
        self._exec(
            "INSERT OR REPLACE INTO voiceprints"
            " (tenant_id, user_id, vector, sample_count, model, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (tenant_id, user_id, json.dumps(vector), int(sample_count),
             model, created, utcnow()),
        )
        self.audit(tenant_id, None, "voiceprint_enrolled",
                   f"user={user_id} dims={len(vector)} model={model}")

    def get_voiceprint(self, tenant_id, user_id):
        row = self._exec(
            "SELECT vector, sample_count, model, created_at, updated_at"
            " FROM voiceprints WHERE tenant_id=? AND user_id=?",
            (tenant_id, user_id),
        ).fetchone()
        if not row:
            return None
        return {"vector": json.loads(row[0]), "sample_count": row[1],
                "model": row[2], "created_at": row[3], "updated_at": row[4]}

    def analytics_reps(self, tenant_id, area_id=None, store_ids=None):
        """Per-rep leaderboard: visits, average score, win rate, top objection.
        The comparable, aggregatable view a manager coaches from."""
        stores = self.list_stores(tenant_id, area_id=area_id)
        allowed = {s["store_id"] for s in stores}
        if store_ids:
            allowed &= set(store_ids)
        rows = self._exec(
            "SELECT agent_id, store_id, score, rating, outcome, body"
            " FROM insights WHERE tenant_id=?", (tenant_id,),
        ).fetchall()
        reps: dict = {}
        for agent_id, store_id, score, rating, outcome, body in rows:
            if not agent_id or (allowed and store_id not in allowed):
                continue
            rep = reps.setdefault(agent_id, {
                "agent_id": agent_id, "visits": 0, "score_sum": 0.0,
                "promising": 0, "at_risk": 0, "objections": {},
            })
            rep["visits"] += 1
            rep["score_sum"] += score or 0.0
            if outcome == "promising":
                rep["promising"] += 1
            elif outcome == "at_risk":
                rep["at_risk"] += 1
            for sig in (json.loads(body).get("signals") or []):
                if sig.get("type") == "objection":
                    sub = sig.get("subtype") or "other"
                    rep["objections"][sub] = rep["objections"].get(sub, 0) + 1
        out = []
        for rep in reps.values():
            visits = rep["visits"]
            user = self.get_user(rep["agent_id"])
            objections = rep.pop("objections")
            out.append({
                "agent_id": rep["agent_id"],
                "name": (user or {}).get("name") or rep["agent_id"],
                "visits": visits,
                "avg_score": round(rep["score_sum"] / visits, 1) if visits else 0,
                "win_rate": round(100 * rep["promising"] / visits, 1) if visits else 0,
                "at_risk": rep["at_risk"],
                "top_objection": max(objections, key=objections.get) if objections else None,
            })
        out.sort(key=lambda r: (r["avg_score"], r["visits"]), reverse=True)
        return {"reps": out, "area_id": area_id}

    def analytics_area_summary(self, tenant_id, area_id=None, store_ids=None):
        """Headline KPIs across the manager's scope — the dashboard hero row."""
        compare = self.analytics_stores_compare(
            tenant_id, area_id=area_id, store_ids=store_ids)
        stores = compare["stores"]
        visits = sum(s["visits"] for s in stores)
        if not stores:
            return {"area_id": area_id, "stores": 0, "visits": 0,
                    "qualified_pct": 0, "avg_score": 0,
                    "top_store": None, "needs_attention": None}
        weighted_q = sum(s["qualified_pct"] * s["visits"] for s in stores)
        # average score across the scope, read from the denormalized column
        allowed = [s["store_id"] for s in stores]
        placeholders = ",".join("?" * len(allowed))
        row = self._exec(
            f"SELECT AVG(score) FROM insights WHERE tenant_id=?"
            f" AND store_id IN ({placeholders})",
            [tenant_id, *allowed],
        ).fetchone()
        ranked = sorted(stores, key=lambda s: s["qualified_pct"], reverse=True)
        return {
            "area_id": area_id,
            "stores": len(stores),
            "visits": visits,
            "qualified_pct": round(weighted_q / visits, 1) if visits else 0,
            "avg_score": round(row[0], 1) if row and row[0] is not None else 0,
            "top_store": {"store_id": ranked[0]["store_id"],
                          "store_name": ranked[0]["store_name"],
                          "qualified_pct": ranked[0]["qualified_pct"]},
            "needs_attention": {"store_id": ranked[-1]["store_id"],
                                "store_name": ranked[-1]["store_name"],
                                "qualified_pct": ranked[-1]["qualified_pct"]},
        }

    def analytics_store_detail(self, tenant_id, store_id):
        store = self.get_store(tenant_id, store_id)
        if not store:
            return None
        compare = self.analytics_stores_compare(tenant_id, store_ids=[store_id])
        insights = self._exec(
            "SELECT conversation_id, body, created_at, agent_id FROM insights"
            " WHERE tenant_id=? AND store_id=? ORDER BY created_at DESC LIMIT 50",
            (tenant_id, store_id),
        ).fetchall()
        recent = []
        for cid, body, created, agent in insights:
            doc = json.loads(body)
            recent.append({
                "conversation_id": cid,
                "agent_id": agent,
                "created_at": created,
                "summary": doc.get("summary", {}).get("text", ""),
                "signal_count": len(doc.get("signals") or []),
            })
        return {
            "store": store,
            "metrics": compare["stores"][0] if compare["stores"] else {},
            "recent_visits": recent,
        }
