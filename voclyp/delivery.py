"""Webhook dispatcher: fans outbox events out to consumer endpoints.

This is the only component that talks to consumer endpoints; business code
never sends webhooks directly — it commits an outbox event (see
Store.save_insight_with_event) and the dispatcher owns everything after:

- Thin payloads: the canonical envelope (events.build_envelope) carries a
  resource reference + fetch URL, never insight content. Consumers pull the
  document from the authenticated REST API.
- HMAC signing (``X-Voclyp-Signature: t=<ts>,v1=<hex>[,v1=<hex>]``) with the
  endpoint's secret; during a rotation overlap window the previous secret's
  signature rides along, so rotation never breaks a consumer.
- At-least-once delivery with exponential backoff + jitter
  (1m → 5m → 30m → 2h → 12h, max 5 attempts), then the dead-letter queue.
  Dead deliveries are replayable (Store.replay_dead); endpoints whose
  deliveries keep exhausting retries are auto-disabled with an audit event
  rather than left to absorb silent data loss.
- The SSRF guard re-runs at send time (registration-time checks are not
  enough — DNS can change). ``log://`` URLs record the delivery without a
  network call (tests, demos, and the Phase-3 connector seam).

Delivery failures never fail the pipeline; every attempt lands in the
webhook_deliveries ledger that powers the delivery-health dashboard.
"""
from __future__ import annotations

import datetime
import json
import random
import time
import urllib.request

from . import events
from .config import Settings, load_settings
from .contracts import utcnow
from .security import check_webhook_url, sign_webhook
from .store import Store

RETRY_SCHEDULE_S = (60, 300, 1800, 7200, 43200)  # 1m, 5m, 30m, 2h, 12h
MAX_ATTEMPTS = len(RETRY_SCHEDULE_S)
JITTER = 0.2                       # ± fraction applied to each backoff step
AUTO_DISABLE_AFTER = 3             # consecutive exhausted deliveries
ROTATION_OVERLAP_S = 48 * 3600     # how long the previous secret co-signs
HTTP_TIMEOUT_S = 5


def backoff_s(attempt: int) -> float:
    """Delay before the next try after `attempt` failures, with jitter so a
    recovering consumer is not hit by a synchronized retry stampede."""
    base = RETRY_SCHEDULE_S[min(attempt, MAX_ATTEMPTS) - 1]
    return base * random.uniform(1 - JITTER, 1 + JITTER)


class Dispatcher:
    def __init__(self, store: Store, settings: Settings = None, now=time.time):
        self.store = store
        self.settings = settings or load_settings()
        self.now = now

    # -- fan-out ---------------------------------------------------------------
    def fan_out(self) -> int:
        """Turn committed outbox events into delivery rows for every active
        endpoint subscribed to the event type. Idempotent: a crash between
        creating deliveries and marking the event leaves rows that the UNIQUE
        constraint deduplicates on the next pass."""
        created = 0
        for event in self.store.unfanned_events():
            for endpoint in self.store.endpoints_for(
                event["tenant_id"], event["event_type"]
            ):
                self.store.create_delivery(
                    event["tenant_id"], endpoint["id"], event["event_id"],
                    due_at=self.now(),
                )
                created += 1
            self.store.mark_fanned_out(event["event_id"])
        return created

    # -- delivery --------------------------------------------------------------
    def deliver_due(self, limit=100) -> int:
        """Attempt every delivery whose retry timer has elapsed."""
        attempted = 0
        for delivery in self.store.due_deliveries(self.now(), limit):
            self._attempt(delivery)
            attempted += 1
        return attempted

    def run_once(self) -> dict:
        return {"fanned_out": self.fan_out(), "attempted": self.deliver_due()}

    def _attempt(self, delivery: dict):
        endpoint = self.store.get_endpoint(
            delivery["tenant_id"], delivery["endpoint_id"]
        )
        event = self.store.get_event(delivery["tenant_id"], delivery["event_id"])
        attempt = delivery["attempt"] + 1
        if endpoint is None or event is None or endpoint["status"] != "active":
            self.store.mark_delivery(delivery["id"], "blocked", attempt,
                                     detail="endpoint missing or disabled")
            return

        envelope = events.build_envelope(
            event, delivered_at=utcnow(), base_url=self.settings.public_base_url
        )
        body = json.dumps(envelope).encode("utf-8")

        ok, reason = check_webhook_url(
            endpoint["url"], self.settings.allow_insecure_webhooks
        )
        if not ok:
            self.store.mark_delivery(delivery["id"], "blocked", attempt,
                                     detail=f"ssrf:{reason}")
            return

        try:
            code = self._post(endpoint, body, event)
            self.store.mark_delivery(delivery["id"], "delivered", attempt,
                                     response_code=code)
        except Exception as exc:  # consumer failure must not fail the pipeline
            detail = f"{type(exc).__name__}"
            if attempt >= MAX_ATTEMPTS:
                self.store.mark_delivery(delivery["id"], "dead", attempt,
                                         detail=detail)
                self.store.audit(delivery["tenant_id"], event["resource_id"],
                                 "delivery_dead_lettered",
                                 f"endpoint={endpoint['id']} event={event['event_id']}")
                self._maybe_disable(delivery["tenant_id"], endpoint)
            else:
                self.store.mark_delivery(
                    delivery["id"], "retrying", attempt, detail=detail,
                    next_retry_at=self.now() + backoff_s(attempt),
                )

    def _post(self, endpoint: dict, body: bytes, event: dict) -> int:
        """One HTTP attempt; raises on any failure. Non-2xx is a failure —
        only the consumer's acknowledgement counts as delivered."""
        if endpoint["url"].startswith("log://"):
            return 200
        req = urllib.request.Request(
            endpoint["url"], data=body, method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Voclyp-Signature": self._signature(endpoint, body),
                "X-Voclyp-Event-Id": event["event_id"],
                "X-Voclyp-Event-Type": event["event_type"],
                "X-Voclyp-Schema-Version": event["schema_version"],
            },
        )
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
            if not 200 <= resp.status < 300:
                raise RuntimeError(f"http {resp.status}")
            return resp.status

    def _signature(self, endpoint: dict, body: bytes) -> str:
        extra = ()
        if endpoint["secret_prev"] and endpoint["rotated_at"]:
            rotated = datetime.datetime.fromisoformat(endpoint["rotated_at"])
            age = (datetime.datetime.now(datetime.timezone.utc) - rotated)
            if age.total_seconds() < ROTATION_OVERLAP_S:
                extra = (endpoint["secret_prev"],)
        return sign_webhook(endpoint["secret"], int(self.now()), body, *extra)

    def _maybe_disable(self, tenant_id: str, endpoint: dict):
        if self.store.consecutive_dead(endpoint["id"]) >= AUTO_DISABLE_AFTER:
            self.store.set_endpoint_status(tenant_id, endpoint["id"], "disabled")

    # -- developer-portal test event --------------------------------------------
    def send_test_event(self, tenant_id: str, endpoint_id: str) -> dict:
        """Synchronous ping so an integrator can verify their receiver
        (signature check, dedup, parsing) before real traffic arrives."""
        endpoint = self.store.get_endpoint(tenant_id, endpoint_id)
        if endpoint is None:
            return {"sent": False, "detail": "unknown endpoint"}
        event = {
            "event_id": events.new_event_id(),
            "event_type": events.ENDPOINT_TEST,
            "schema_version": events.ENVELOPE_VERSION,
            "occurred_at": utcnow(), "tenant_id": tenant_id,
            "resource": "endpoint", "resource_id": endpoint_id,
            "resource_status": "test", "sequence": 0,
        }
        body = json.dumps(events.build_envelope(
            event, delivered_at=utcnow(), base_url=self.settings.public_base_url
        )).encode("utf-8")
        ok, reason = check_webhook_url(
            endpoint["url"], self.settings.allow_insecure_webhooks
        )
        if not ok:
            return {"sent": False, "detail": f"ssrf:{reason}"}
        try:
            code = self._post(endpoint, body, event)
            return {"sent": True, "response_code": code}
        except Exception as exc:
            return {"sent": False, "detail": type(exc).__name__}
