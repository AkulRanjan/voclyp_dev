"""Gateway boundary tests: auth, scopes, rate limits, SSRF, headers.

Skipped automatically when the optional gateway extras (fastapi/httpx) are
not installed; the core platform tests do not depend on them.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from fastapi.testclient import TestClient
    HAVE_FASTAPI = True
except ImportError:
    HAVE_FASTAPI = False

from voclyp.config import Settings
from voclyp.worker import Worker

CONVERSATION = b"""\
AGENT: Namaste ji!
CUSTOMER: Ye pack bahut costly hai. Chota pack chahiye, sachet wala.
AGENT: I will deliver by tomorrow.
"""


@unittest.skipUnless(HAVE_FASTAPI, "fastapi not installed")
class GatewayTest(unittest.TestCase):
    def setUp(self):
        from voclyp.gateway.app import create_app

        self.data_dir = Path(tempfile.mkdtemp(prefix="voclyp-gw-"))
        self.settings = Settings(
            master_key=b"test-master-key",
            rate_limit_requests=30,
            rate_limit_window_s=60.0,
        )
        self.app = create_app(self.data_dir, self.settings)
        self.client = TestClient(self.app, raise_server_exceptions=False)
        self.store = self.app.state.store
        self.store.create_tenant("acme-fmcg", "Acme", "fmcg")
        self.full_key = self.store.create_api_key(
            "acme-fmcg", scopes=("ingest", "read", "admin")
        )
        self.read_key = self.store.create_api_key("acme-fmcg", scopes=("read",))

    def _submit(self, key=None):
        return self.client.post(
            "/v1/conversations",
            headers={"X-API-Key": key or self.full_key},
            files={"audio": ("rec.audio", CONVERSATION)},
            data={"consent_captured": "true", "agent_id": "a1",
                  "customer_name": "Ramesh Kumar"},
        )

    def test_no_key_rejected(self):
        # No credential at all -> 401 (auth required); a malformed key -> 401.
        self.assertEqual(self.client.get("/v1/insights").status_code, 401)
        self.assertEqual(
            self.client.get("/v1/insights", headers={"X-API-Key": "vclp_x_y"}).status_code,
            401,
        )

    def test_scope_enforced(self):
        resp = self._submit(key=self.read_key)
        self.assertEqual(resp.status_code, 403)
        resp = self.client.delete(
            "/v1/conversations/abc", headers={"X-API-Key": self.read_key}
        )
        self.assertEqual(resp.status_code, 403)

    def test_consent_required(self):
        resp = self.client.post(
            "/v1/conversations",
            headers={"X-API-Key": self.full_key},
            files={"audio": ("rec.audio", CONVERSATION)},
            data={"consent_captured": "false"},
        )
        self.assertEqual(resp.status_code, 422)

    def test_full_flow_through_gateway(self):
        resp = self._submit()
        self.assertEqual(resp.status_code, 202)
        conv_id = resp.json()["conversation_id"]

        # not ready yet
        resp = self.client.get(f"/v1/insights/{conv_id}",
                               headers={"X-API-Key": self.full_key})
        self.assertEqual(resp.status_code, 404)

        Worker(self.store, self.app.state.queue, vault=self.app.state.vault).drain()

        resp = self.client.get(f"/v1/insights/{conv_id}",
                               headers={"X-API-Key": self.full_key})
        self.assertEqual(resp.status_code, 200)
        doc = resp.json()
        self.assertEqual(doc["schema_version"], "1.0")
        self.assertTrue(any(s["type"] == "objection" for s in doc["signals"]))

        # audit endpoint reports an intact chain
        resp = self.client.get("/v1/audit", headers={"X-API-Key": self.full_key})
        self.assertTrue(resp.json()["chain_intact"])

        # admin scope can delete-on-demand
        resp = self.client.delete(f"/v1/conversations/{conv_id}",
                                  headers={"X-API-Key": self.full_key})
        self.assertTrue(resp.json()["deleted"])

    def test_webhook_ssrf_blocked(self):
        for url in ("https://127.0.0.1/h", "http://example.com/h",
                    "https://169.254.169.254/h"):
            resp = self.client.post("/v1/webhooks", json={"url": url},
                                    headers={"X-API-Key": self.full_key})
            self.assertEqual(resp.status_code, 400, url)

    def test_webhook_registration_returns_secret_once(self):
        resp = self.client.post("/v1/webhooks", json={"url": "log://crm"},
                                headers={"X-API-Key": self.full_key})
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.json()["signing_secret"].startswith("whsec_"))

    def test_security_headers_present(self):
        resp = self.client.get("/v1/insights", headers={"X-API-Key": self.full_key})
        self.assertEqual(resp.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(resp.headers["Cache-Control"], "no-store")
        self.assertEqual(resp.headers["X-Frame-Options"], "DENY")

    def test_rate_limit(self):
        for _ in range(self.settings.rate_limit_requests - 1):
            self.client.get("/v1/insights", headers={"X-API-Key": self.read_key})
        resp = self.client.get("/v1/insights", headers={"X-API-Key": self.read_key})
        last = self.client.get("/v1/insights", headers={"X-API-Key": self.read_key})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(last.status_code, 429)
        self.assertIn("Retry-After", last.headers)

    def test_feedback_endpoint(self):
        conv_id = self._submit().json()["conversation_id"]
        Worker(self.store, self.app.state.queue, vault=self.app.state.vault).drain()

        resp = self.client.post(
            f"/v1/insights/{conv_id}/feedback",
            json={"target": "signals[0].subtype", "correction": "margin_too_low"},
            headers={"X-API-Key": self.full_key},
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(
            self.store.feedback_for("acme-fmcg", conv_id)[0]["correction"],
            "margin_too_low",
        )
        resp = self.client.post(
            "/v1/insights/nonexistent/feedback",
            json={"target": "x", "correction": "y"},
            headers={"X-API-Key": self.full_key},
        )
        self.assertEqual(resp.status_code, 404)

    def test_metrics_endpoint_admin_only(self):
        resp = self.client.get("/v1/metrics", headers={"X-API-Key": self.read_key})
        self.assertEqual(resp.status_code, 403)

        self._submit()
        Worker(self.store, self.app.state.queue, vault=self.app.state.vault).drain()
        resp = self.client.get("/v1/metrics", headers={"X-API-Key": self.full_key})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("asr", {row["stage"] for row in body["stages"]})
        self.assertEqual(body["queue"].get("done"), 1)

    def test_errors_do_not_leak_internals(self):
        resp = self.client.post("/v1/webhooks", content=b"not-json",
                                headers={"X-API-Key": self.full_key,
                                         "Content-Type": "application/json"})
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.json(), {"detail": "internal error"})


if __name__ == "__main__":
    unittest.main()
