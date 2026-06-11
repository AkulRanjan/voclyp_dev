"""Canonical event envelope (contracts/event-envelope/v1).

Every externally visible state change becomes one of these. The payload is
deliberately thin — a resource reference plus a fetch URL, never the insight
document itself — so PII stays out of intermediary pipes (Zapier, Make.com)
and the API response can evolve independently of the event envelope.

Consumers are documented to:
- deduplicate on ``event_id`` (delivery is at-least-once; duplicates happen),
- use ``sequence`` so a delayed older event never overwrites newer state,
- verify the HMAC signature and tenant_id before trusting anything.
"""
from __future__ import annotations

import secrets
import time
import uuid

ENVELOPE_VERSION = "1.0"

# Namespaced event types. Additive-only within a major version.
INSIGHTS_READY = "conversation.insights.ready"
CONVERSATION_DELETED = "conversation.deleted"
ENDPOINT_TEST = "endpoint.test.ping"


def new_event_id() -> str:
    """UUIDv7: time-ordered, so the id itself sorts by occurrence and works
    as both a globally unique id and the consumer's deduplication key."""
    ts_ms = int(time.time() * 1000)
    raw = bytearray(ts_ms.to_bytes(6, "big") + secrets.token_bytes(10))
    raw[6] = (raw[6] & 0x0F) | 0x70  # version 7
    raw[8] = (raw[8] & 0x3F) | 0x80  # RFC 4122 variant
    return str(uuid.UUID(bytes=bytes(raw)))


def fetch_url_for(resource: str, resource_id: str, base_url: str = "") -> str:
    path = {
        "insight": f"/v1/insights/{resource_id}",
        "conversation": f"/v1/insights/{resource_id}",
    }.get(resource, f"/v1/{resource}s/{resource_id}")
    return base_url.rstrip("/") + path if base_url else path


def build_envelope(event: dict, delivered_at: str, base_url: str = "") -> dict:
    """Assemble the wire payload from a stored outbox row. ``delivered_at``
    is stamped per attempt (retries carry a fresh timestamp); everything
    else is immutable from the moment the event was committed."""
    return {
        "event_id": event["event_id"],
        "event_type": event["event_type"],
        "schema_version": event["schema_version"],
        "occurred_at": event["occurred_at"],
        "delivered_at": delivered_at,
        "tenant_id": event["tenant_id"],
        "sequence": event["sequence"],
        "data": {
            "resource": event["resource"],
            "id": event["resource_id"],
            "status": event["resource_status"],
            "fetch_url": fetch_url_for(
                event["resource"], event["resource_id"], base_url
            ),
        },
    }
