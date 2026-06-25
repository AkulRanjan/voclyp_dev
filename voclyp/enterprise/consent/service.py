"""DPDP Act 2026 consent service.

Asking "Can I record?" is not enough under the DPDP Act. Consent must be:

- granular   — a per-purpose toggle map (recording, whatsapp_followup, crm_storage,
               marketing), with recording mandatory before any audio is accepted;
- multilingual — the notice language (one of the 22 + English) is recorded;
- verifiable — the exact notice/toggle state is canonicalized and hashed
               (SHA-256), then linked into a per-tenant hash chain so the
               ledger is tamper-evident and replayable;
- pre-capture — the immutable record is committed BEFORE any audio is allowed
                to reach S3 (enforced by the ingestion service).

The raw customer phone is never written to the consent ledger — only a SHA-256
of its E.164 form, so the immutable log itself carries no contact PII.
"""
from __future__ import annotations

import hashlib
import json
import uuid

from ...contracts import utcnow
from ...security import chain_hash

# Purposes a caller may toggle. ``recording`` is mandatory.
KNOWN_PURPOSES = ("recording", "whatsapp_followup", "crm_storage", "marketing")


class ConsentError(Exception):
    """Raised when consent is missing, malformed, or recording is not granted."""


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def canonical_artifact(artifact: dict) -> str:
    """Deterministic JSON (sorted keys, no whitespace) so the SHA-256 is stable
    regardless of key ordering on the wire."""
    return json.dumps(artifact, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def hash_phone(phone: str) -> str:
    """SHA-256 of a normalized E.164-ish phone (digits and leading +)."""
    cleaned = "".join(ch for ch in (phone or "") if ch.isdigit() or ch == "+")
    return sha256_hex(cleaned) if cleaned else ""


def normalize_purposes(purposes: dict | None) -> dict:
    purposes = purposes or {}
    out = {key: bool(purposes.get(key, False)) for key in KNOWN_PURPOSES}
    # carry through any extra custom purpose toggles too
    for key, value in purposes.items():
        if key not in out:
            out[key] = bool(value)
    return out


class ConsentService:
    def __init__(self, store):
        self.store = store

    def record(self, *, tenant_id: str, agent_id: str, session_id: str,
               language: str, purposes: dict, device_fingerprint: dict,
               notice_text: str, customer_phone: str = "",
               extra_artifact: dict | None = None) -> dict:
        """Validate + persist an immutable consent record. Returns the stored
        identifiers; raises ConsentError if recording consent is absent."""
        purposes = normalize_purposes(purposes)
        if not purposes.get("recording"):
            raise ConsentError("recording consent was not granted")
        if not language:
            raise ConsentError("consent notice language is required")

        artifact = {
            "notice_text": notice_text,
            "language": language,
            "purposes": purposes,
            "device_fingerprint": device_fingerprint or {},
            "captured_at": utcnow(),
        }
        if extra_artifact:
            artifact["extra"] = extra_artifact

        canonical = canonical_artifact(artifact)
        artifact_sha256 = sha256_hex(canonical)

        prev_hash = self.store.last_consent_entry_hash(tenant_id)
        captured_at = artifact["captured_at"]
        entry_hash = chain_hash(
            prev_hash, tenant_id, session_id, artifact_sha256, captured_at,
        )

        consent_id = uuid.uuid4().hex
        self.store.insert_consent_log({
            "id": consent_id,
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "session_id": session_id,
            "customer_phone_hash": hash_phone(customer_phone),
            "language": language,
            "purposes": purposes,
            "device_fingerprint": device_fingerprint or {},
            "consent_artifact": artifact,
            "artifact_sha256": artifact_sha256,
            "prev_hash": prev_hash,
            "entry_hash": entry_hash,
            "captured_at": captured_at,
        })
        return {
            "consent_id": consent_id,
            "artifact_sha256": artifact_sha256,
            "entry_hash": entry_hash,
            "purposes": purposes,
            "captured_at": captured_at,
        }
