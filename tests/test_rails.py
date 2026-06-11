"""Integration-rail tests: canonical envelope, transactional outbox, thin
payloads, retry/backoff/DLQ/replay, auto-disable, dual-secret rotation, and
the gateway's webhook-management surface."""
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voclyp import events, security
from voclyp.config import Settings
from voclyp.contracts import utcnow
from voclyp.delivery import (AUTO_DISABLE_AFTER, JITTER, MAX_ATTEMPTS,
                             RETRY_SCHEDULE_S, Dispatcher, backoff_s)
from voclyp.store import Store

INSIGHT = {
    "schema_version": "1.0", "tenant_id": "acme-fmcg",
    "conversation_id": "c1", "industry": "fmcg",
    "signals": [{"type": "objection", "quote": "bahut costly hai"}],
    "summary": {"text": "price objection", "fields": {}},
    "created_at": utcnow(),
}


class CapturingDispatcher(Dispatcher):
    """Records every send instead of doing network I/O; optionally fails."""

    def __init__(self, *args, fail=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fail = fail
        self.sent = []

    def _post(self, endpoint, body, event):
        if self.fail:
            raise ConnectionError("consumer down")
        self.sent.append((endpoint, body, event))
        return 200


class RailsTestCase(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="voclyp-rails-"))
        self.store = Store(self.dir / "voclyp.db")
        self.store.create_tenant("acme-fmcg", "Acme", "fmcg")
        self.clock = [1_000_000.0]
        self.settings = Settings()

    def dispatcher(self, fail=False):
        return CapturingDispatcher(self.store, settings=self.settings,
                                   now=lambda: self.clock[0], fail=fail)


class EnvelopeTest(RailsTestCase):
    def test_uuid7_is_time_ordered(self):
        ids = []
        for _ in range(5):  # ordering is to millisecond precision
            ids.append(events.new_event_id())
            time.sleep(0.002)
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(ids[0][14], "7")  # version nibble

    def test_envelope_is_thin(self):
        """The wire payload references the insight; it never contains it."""
        event_id = self.store.save_insight_with_event("acme-fmcg", "c1", INSIGHT)
        event = self.store.get_event("acme-fmcg", event_id)
        envelope = events.build_envelope(event, delivered_at=utcnow(),
                                         base_url="https://api.voclyp.io")
        self.assertEqual(envelope["event_type"], "conversation.insights.ready")
        self.assertEqual(envelope["schema_version"], events.ENVELOPE_VERSION)
        self.assertEqual(envelope["data"]["fetch_url"],
                         "https://api.voclyp.io/v1/insights/c1")
        wire = json.dumps(envelope)
        self.assertNotIn("costly", wire)        # no transcript content
        self.assertNotIn("price objection", wire)  # no summary content

    def test_sequence_is_monotonic_per_resource(self):
        for expected in (1, 2, 3):
            eid = self.store.save_insight_with_event("acme-fmcg", "c1", INSIGHT)
            self.assertEqual(
                self.store.get_event("acme-fmcg", eid)["sequence"], expected)
        eid = self.store.save_insight_with_event("acme-fmcg", "c2", INSIGHT)
        self.assertEqual(self.store.get_event("acme-fmcg", eid)["sequence"], 1)


class OutboxTest(RailsTestCase):
    def test_insight_and_event_commit_together(self):
        event_id = self.store.save_insight_with_event("acme-fmcg", "c1", INSIGHT)
        self.assertIsNotNone(self.store.get_insight("acme-fmcg", "c1"))
        self.assertIsNotNone(self.store.get_event("acme-fmcg", event_id))
        self.assertEqual(len(self.store.unfanned_events()), 1)

    def test_fan_out_filters_event_types_and_is_idempotent(self):
        self.store.add_webhook("acme-fmcg", "log://crm",
                               event_types=("conversation.insights.ready",))
        self.store.add_webhook("acme-fmcg", "log://deletes-only",
                               event_types=("conversation.deleted",))
        self.store.save_insight_with_event("acme-fmcg", "c1", INSIGHT)

        d = self.dispatcher()
        self.assertEqual(d.fan_out(), 1)  # only the subscribed endpoint
        self.assertEqual(d.fan_out(), 0)  # outbox row already fanned out
        self.assertEqual(len(self.store.deliveries_for("acme-fmcg")), 1)

    def test_tenant_isolation(self):
        self.store.create_tenant("zen-pharma", "Zen", "pharma")
        self.store.add_webhook("zen-pharma", "log://zen-crm")
        self.store.save_insight_with_event("acme-fmcg", "c1", INSIGHT)
        self.dispatcher().run_once()
        self.assertEqual(self.store.deliveries_for("zen-pharma"), [])


class DeliveryTest(RailsTestCase):
    def setUp(self):
        super().setUp()
        self.endpoint_id, self.secret = self.store.add_webhook(
            "acme-fmcg", "log://crm")
        self.store.save_insight_with_event("acme-fmcg", "c1", INSIGHT)

    def test_successful_delivery(self):
        d = self.dispatcher()
        d.run_once()
        (ledger,) = self.store.deliveries_for("acme-fmcg", "c1")
        self.assertEqual(ledger["status"], "delivered")
        self.assertEqual(ledger["attempt"], 1)
        self.assertEqual(ledger["response_code"], 200)
        envelope = json.loads(d.sent[0][1])
        self.assertEqual(envelope["data"]["id"], "c1")
        self.assertEqual(envelope["sequence"], 1)

    def test_redelivered_event_id_is_stable(self):
        """Retries re-send the same event_id, so consumer-side dedup works."""
        d = self.dispatcher(fail=True)
        d.run_once()
        (ledger,) = self.store.deliveries_for("acme-fmcg", "c1")
        self.clock[0] += RETRY_SCHEDULE_S[0] * 2
        ok = self.dispatcher()
        ok.deliver_due()
        envelope = json.loads(ok.sent[0][1])
        self.assertEqual(envelope["event_id"], ledger["event_id"])

    def test_backoff_schedule_with_jitter(self):
        for attempt in range(1, MAX_ATTEMPTS + 1):
            base = RETRY_SCHEDULE_S[attempt - 1]
            for _ in range(20):
                delay = backoff_s(attempt)
                self.assertGreaterEqual(delay, base * (1 - JITTER))
                self.assertLessEqual(delay, base * (1 + JITTER))

    def test_retries_then_dead_letter(self):
        d = self.dispatcher(fail=True)
        d.fan_out()
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self.assertEqual(d.deliver_due(), 1)
            (ledger,) = self.store.deliveries_for("acme-fmcg", "c1")
            self.assertEqual(ledger["attempt"], attempt)
            expected = "dead" if attempt == MAX_ATTEMPTS else "retrying"
            self.assertEqual(ledger["status"], expected)
            self.clock[0] += RETRY_SCHEDULE_S[min(attempt, MAX_ATTEMPTS) - 1] * 2
        self.assertEqual(d.deliver_due(), 0)  # dead rows are not retried
        self.assertTrue(any(e["event"] == "delivery_dead_lettered"
                            for e in self.store.audit_export("acme-fmcg")))

    def test_retry_not_due_early(self):
        d = self.dispatcher(fail=True)
        d.run_once()
        self.clock[0] += 1  # well inside the first backoff window
        self.assertEqual(d.deliver_due(), 0)

    def test_dlq_replay_recovers(self):
        d = self.dispatcher(fail=True)
        self.exhaust(d)
        self.assertEqual(self.store.replay_dead("acme-fmcg", self.clock[0]), 1)
        ok = self.dispatcher()
        self.assertEqual(ok.deliver_due(), 1)
        (ledger,) = self.store.deliveries_for("acme-fmcg", "c1")
        self.assertEqual(ledger["status"], "delivered")

    def test_flapping_endpoint_auto_disabled(self):
        d = self.dispatcher(fail=True)
        self.exhaust(d)  # dead delivery #1 (from setUp's event)
        for i in range(2, AUTO_DISABLE_AFTER + 1):
            self.store.save_insight_with_event("acme-fmcg", f"c{i}", INSIGHT)
            self.exhaust(d)
        endpoint = self.store.get_endpoint("acme-fmcg", self.endpoint_id)
        self.assertEqual(endpoint["status"], "disabled")
        # disabled endpoints receive no further fan-out
        self.store.save_insight_with_event("acme-fmcg", "c-after", INSIGHT)
        self.assertEqual(self.dispatcher().fan_out(), 0)

    def exhaust(self, dispatcher):
        dispatcher.fan_out()
        for attempt in range(MAX_ATTEMPTS):
            dispatcher.deliver_due()
            self.clock[0] += RETRY_SCHEDULE_S[min(attempt + 1, MAX_ATTEMPTS) - 1] * 2


class RotationTest(RailsTestCase):
    def test_dual_secret_overlap(self):
        endpoint_id, old_secret = self.store.add_webhook("acme-fmcg", "log://crm")
        new_secret = self.store.rotate_webhook_secret("acme-fmcg", endpoint_id)
        self.assertNotEqual(old_secret, new_secret)

        endpoint = self.store.get_endpoint("acme-fmcg", endpoint_id)
        d = Dispatcher(self.store, settings=self.settings)
        body = b'{"hello": "world"}'
        header = d._signature(endpoint, body)
        # consumers verifying against either secret accept the delivery
        self.assertTrue(security.verify_webhook_signature(new_secret, header, body))
        self.assertTrue(security.verify_webhook_signature(old_secret, header, body))
        self.assertFalse(security.verify_webhook_signature(
            security.new_webhook_secret(), header, body))

    def test_multi_signature_header_parses(self):
        secret = security.new_webhook_secret()
        body = b"{}"
        header = security.sign_webhook(secret, int(time.time()), body, "whsec_other")
        self.assertEqual(header.count("v1="), 2)
        self.assertTrue(security.verify_webhook_signature(secret, header, body))


try:
    from fastapi.testclient import TestClient
    HAVE_FASTAPI = True
except ImportError:
    HAVE_FASTAPI = False


@unittest.skipUnless(HAVE_FASTAPI, "fastapi not installed")
class GatewayRailsTest(unittest.TestCase):
    def setUp(self):
        from voclyp.gateway.app import create_app

        self.data_dir = Path(tempfile.mkdtemp(prefix="voclyp-rails-gw-"))
        self.app = create_app(self.data_dir, Settings())
        self.client = TestClient(self.app, raise_server_exceptions=False)
        self.store = self.app.state.store
        self.store.create_tenant("acme-fmcg", "Acme", "fmcg")
        self.key = self.store.create_api_key(
            "acme-fmcg", scopes=("ingest", "read", "admin"))
        self.headers = {"X-API-Key": self.key}

    def register(self, url="log://crm", **extra):
        return self.client.post("/v1/webhooks", json={"url": url, **extra},
                                headers=self.headers)

    def test_lifecycle(self):
        resp = self.register(event_types=["conversation.insights.ready"])
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        endpoint_id = body["endpoint_id"]
        self.assertTrue(body["signing_secret"].startswith("whsec_"))

        listed = self.client.get("/v1/webhooks", headers=self.headers).json()
        self.assertEqual(listed["endpoints"][0]["id"], endpoint_id)
        self.assertNotIn("secret", listed["endpoints"][0])

        rotated = self.client.post(f"/v1/webhooks/{endpoint_id}/rotate",
                                   headers=self.headers)
        self.assertNotEqual(rotated.json()["signing_secret"],
                            body["signing_secret"])

        ping = self.client.post(f"/v1/webhooks/{endpoint_id}/test",
                                headers=self.headers)
        self.assertTrue(ping.json()["sent"])

        disabled = self.client.delete(f"/v1/webhooks/{endpoint_id}",
                                      headers=self.headers)
        self.assertEqual(disabled.json()["status"], "disabled")

    def test_invalid_event_types_rejected(self):
        resp = self.register(event_types="not-a-list")
        self.assertEqual(resp.status_code, 400)

    def test_deliveries_and_replay_endpoints(self):
        self.register()
        self.store.save_insight_with_event("acme-fmcg", "c1", INSIGHT)
        Dispatcher(self.store, Settings()).run_once()

        resp = self.client.get("/v1/deliveries", headers=self.headers)
        (ledger,) = resp.json()["deliveries"]
        self.assertEqual(ledger["status"], "delivered")

        resp = self.client.post("/v1/deliveries/replay", json={},
                                headers=self.headers)
        self.assertEqual(resp.json()["replayed"], 0)  # nothing dead

    def test_admin_scope_required(self):
        read_key = self.store.create_api_key("acme-fmcg", scopes=("read",))
        for method, path in (("get", "/v1/webhooks"), ("get", "/v1/deliveries")):
            resp = getattr(self.client, method)(path,
                                                headers={"X-API-Key": read_key})
            self.assertEqual(resp.status_code, 403, path)


if __name__ == "__main__":
    unittest.main()
