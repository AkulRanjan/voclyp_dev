"""Routing dispatcher — concurrent multi-channel fan-out with a verification hold.

On ``insight.extracted`` the dispatcher writes one ``routing_outbox`` row per
channel (Zoho CRM, Twilio WhatsApp, agent push) and fans them out
concurrently. At-least-once delivery with retry/backoff mirrors
voclyp/delivery.py.

Self-Correction 2 (hallucinated financials): when the conversation requires
human verification (EMI figures present, or low overall confidence), the
WhatsApp row is created in status ``held`` and is NOT sent. A push goes to the
agent asking for a 1-tap confirmation; ``verify()`` flips the held row to
``pending`` and delivers it.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import uuid
from concurrent.futures import ThreadPoolExecutor

from ...contracts import utcnow
from ..events import topics
from ..obs import alert, get_logger

_log = get_logger("routing")

# Hard retry ceiling: 5 retries, so the 6th delivery failure is a poison pill.
MAX_ATTEMPTS = 5


def _future_iso(seconds: float) -> str:
    return (datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(seconds=seconds)).isoformat()


def idempotency_key(conversation_id: str, destination_type: str, payload: dict) -> str:
    """SHA-256 of (conversation_id + destination_type + payload_hash).

    Stable across retries so third-party systems (Zoho, Twilio) safely drop
    duplicated requests caused by partial network failures.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False)
    payload_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    material = f"{conversation_id}\x1f{destination_type}\x1f{payload_hash}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class RoutingDispatcher:
    topic = topics.INSIGHT_EXTRACTED

    def __init__(self, settings, store, clients: dict, bus=None, max_workers: int = 3):
        self.settings = settings
        self.store = store
        self.clients = clients  # {"zoho":..., "whatsapp":..., "push":...}
        self.bus = bus
        self.max_workers = max_workers

    # -- event entrypoint ------------------------------------------------------
    def handle(self, event: dict) -> None:
        value = event.get("value", event)
        conversation_id = value["conversation_id"]
        conv = self.store.get_conversation(conversation_id)
        if not conv:
            return
        self.store.set_state(conversation_id, "dispatching")
        requires_verification = bool(conv.get("requires_human_verification"))
        payloads = self._build_payloads(conv, requires_verification)

        for channel, payload in payloads.items():
            held = channel == "whatsapp" and requires_verification
            self.store.insert_routing({
                "id": uuid.uuid4().hex,
                "tenant_id": conv["tenant_id"],
                "conversation_id": conversation_id,
                "channel": channel,
                "status": "held" if held else "pending",
                "max_attempts": MAX_ATTEMPTS,
                "idempotency_key": idempotency_key(conversation_id, channel, payload),
                "payload": payload,
            })

        # deliver everything that is ready right now (held WhatsApp waits).
        # The conversation stays in 'dispatching' until the erasure worker
        # purges it; routing delivery status lives on the outbox rows.
        self._deliver_ready(conversation_id)

    # -- payload construction --------------------------------------------------
    def _build_payloads(self, conv: dict, requires_verification: bool) -> dict:
        extraction = conv.get("extraction") or {}
        nba = extraction.get("next_best_action") or {}
        summary = self._summarize(extraction)
        codemix = conv.get("transcript_codemix") or ""

        zoho_payload = {
            "lead": {
                "Last_Name": f"Showroom Visit {conv['id'][:8]}",
                "Lead_Source": "VoClyp Showroom",
                "Description": summary,
            },
            "conversation_id": conv["id"],
            "extraction": extraction,
        }
        whatsapp_payload = {
            "conversation_id": conv["id"],
            "to": "",  # resolved by the agent app; raw phone is never persisted
            "body": self._whatsapp_body(nba, codemix),
            "content_variables": None,
            "held_for_verification": requires_verification,
        }
        push_payload = {
            "conversation_id": conv["id"],
            "agent_id": conv["agent_id"],
            "type": "verify_emi" if requires_verification else "insight_ready",
            "title": ("Verify EMI before WhatsApp" if requires_verification
                      else "New showroom insight ready"),
            "body": summary[:240],
            "requires_action": requires_verification,
        }
        return {"zoho": zoho_payload, "whatsapp": whatsapp_payload, "push": push_payload}

    @staticmethod
    def _summarize(extraction: dict) -> str:
        bits = []
        if extraction.get("posture_issues"):
            issues = ", ".join(p.get("issue", "") for p in extraction["posture_issues"])
            bits.append(f"Posture: {issues}")
        if extraction.get("pricing_objections"):
            objs = ", ".join(o.get("objection_type", "") for o in extraction["pricing_objections"])
            bits.append(f"Objections: {objs}")
        if extraction.get("competitor_mentions"):
            comps = ", ".join(c.get("brand", "") for c in extraction["competitor_mentions"])
            bits.append(f"Competitors: {comps}")
        if extraction.get("emi_commitments"):
            bits.append(f"EMI mentioned ({len(extraction['emi_commitments'])}) — verify")
        nba = extraction.get("next_best_action") or {}
        if nba.get("action"):
            bits.append(f"Next: {nba['action']}")
        return " | ".join(bits) or "Showroom conversation processed."

    @staticmethod
    def _whatsapp_body(nba: dict, codemix: str) -> str:
        action = nba.get("talking_point") or nba.get("action") or "Thank you for visiting!"
        return action[:300]

    # -- delivery --------------------------------------------------------------
    def _deliver_ready(self, conversation_id: str) -> None:
        rows = [r for r in self.store.get_routing_for_conversation(conversation_id)
                if r["status"] == "pending"]
        self._deliver_rows(rows)

    def _deliver_rows(self, rows: list[dict]) -> None:
        if not rows:
            return
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            list(pool.map(self._deliver_one, rows))

    def _deliver_one(self, row: dict) -> None:
        client = self.clients.get(row["channel"])
        if client is None:
            self.store.update_routing(row["id"], status="skipped",
                                      detail="no client for channel")
            return
        self.store.update_routing(row["id"], status="delivering")
        attempts = int(row.get("attempts", 0)) + 1
        # idempotency key is stable across retries; backfill legacy rows.
        key = row.get("idempotency_key") or idempotency_key(
            row["conversation_id"], row["channel"], row.get("payload") or {})
        try:
            result = client.send(row["payload"], idempotency_key=key)
        except Exception as exc:
            result = {"ok": False, "response": {}, "detail": f"{type(exc).__name__}: {exc}"}

        if result.get("ok"):
            self.store.update_routing(
                row["id"], status="delivered", attempts=attempts,
                response=result.get("response") or {}, detail=result.get("detail"))
            return

        max_attempts = int(row.get("max_attempts", MAX_ATTEMPTS))
        if attempts > max_attempts:
            # 6th failure (after 5 retries) — poison pill -> dead-letter queue.
            reason = (result.get("detail") or "max retries exceeded")[:480]
            row_for_dlq = dict(row, attempts=attempts)
            self.store.move_to_dlq(row_for_dlq, reason)
            alert(_log, "routing poison pill moved to DLQ",
                  conversation_id=row["conversation_id"], channel=row["channel"],
                  tenant_id=row.get("tenant_id"), attempts=attempts,
                  idempotency_key=key, reason=reason)
        else:
            backoff = min(3600, 2 ** attempts * 30)
            self.store.update_routing(
                row["id"], status="failed", attempts=attempts,
                next_retry_at=_future_iso(backoff), detail=result.get("detail"))

    # -- retry worker ----------------------------------------------------------
    def process_due(self, limit: int = 100) -> int:
        rows = self.store.due_routing(utcnow(), limit=limit)
        self._deliver_rows(rows)
        return len(rows)

    # -- verification release --------------------------------------------------
    def verify(self, conversation_id: str, verified_by: str,
               whatsapp_to: str = "") -> dict:
        conv = self.store.get_conversation(conversation_id)
        if not conv:
            raise KeyError("conversation not found")
        self.store.update_conversation(
            conversation_id, requires_human_verification=False,
            verified_by=verified_by, verified_at=utcnow())
        row = self.store.get_routing(conversation_id, "whatsapp")
        released = False
        if row and row["status"] == "held":
            updates = {"status": "pending", "next_retry_at": utcnow()}
            if whatsapp_to:
                payload = dict(row.get("payload") or {})
                payload["to"] = whatsapp_to
                updates["payload"] = payload
            self.store.update_routing(row["id"], **updates)
            self._deliver_ready(conversation_id)
            released = True
        return {"conversation_id": conversation_id, "verified_by": verified_by,
                "whatsapp_released": released}
