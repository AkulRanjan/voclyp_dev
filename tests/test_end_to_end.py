"""End-to-end tests for the Phase-0 walking skeleton.

Run from the repo root:  python -m unittest discover tests -v
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voclyp.ingestion import ConsentRequired, IngestionService
from voclyp.queueing import JobQueue
from voclyp.store import Store
from voclyp.worker import Worker

CONVERSATION = """\
AGENT: Ramesh Kumar ji, namaste!
CUSTOMER: Purana stock abhi tak pada hai, not selling at all.
CUSTOMER: Ye pack bahut costly hai. Chota pack chahiye, sachet wala.
AGENT: I will deliver by tomorrow.
CUSTOMER: Theek hai, book my order. Mera number 98765 43210 hai.
"""


class EndToEndTest(unittest.TestCase):
    def setUp(self):
        self.data_dir = Path(tempfile.mkdtemp(prefix="voclyp-test-"))
        self.store = Store(self.data_dir / "voclyp.db")
        self.queue = JobQueue(self.data_dir / "queue.db")
        self.ingestion = IngestionService(self.store, self.queue, self.data_dir / "audio")
        self.worker = Worker(self.store, self.queue)
        self.store.create_tenant("acme-fmcg", "Acme", "fmcg")

    def _submit(self):
        return self.ingestion.submit(
            "acme-fmcg",
            CONVERSATION.encode("utf-8"),
            {"agent_id": "a1",
             "consent": {"captured": True, "customer_name": "Ramesh Kumar"}},
        )

    def test_full_flow(self):
        conv_id = self._submit()
        audio = self.data_dir / "audio" / "acme-fmcg" / f"{conv_id}.part0.audio"
        self.assertTrue(audio.exists())

        self.assertEqual(self.worker.drain(), 1)
        doc = self.store.get_insight("acme-fmcg", conv_id)

        # schema envelope
        self.assertEqual(doc["schema_version"], "1.0")
        self.assertEqual(doc["industry"], "fmcg")
        self.assertTrue(doc["languages"]["code_switching"])
        self.assertIn("hi", doc["languages"]["detected"])

        # taxonomy-driven signals: FMCG pack found the stock and SKU signals
        types = {(s["type"], s["subtype"]) for s in doc["signals"]}
        self.assertIn(("objection", "stock_unsold"), types)
        self.assertIn(("demand", "sku_request"), types)
        self.assertIn(("promise", "delivery_promise"), types)
        self.assertIn(("intent", "purchase_intent"), types)

        # diarization: the promise came from the agent
        promise = next(s for s in doc["signals"] if s["type"] == "promise")
        self.assertEqual(promise["speaker"], "agent")

        # industry summary fields exist because the config declared them
        self.assertIn("restock_needed", doc["summary"]["fields"])
        self.assertTrue(doc["summary"]["fields"]["purchase_intent"])

        # privacy: PII redacted, audio destroyed and audited
        self.assertGreaterEqual(doc["privacy"]["pii_redactions"].get("phone", 0), 1)
        self.assertGreaterEqual(doc["privacy"]["pii_redactions"].get("name", 0), 1)
        self.assertFalse(audio.exists())
        self.assertIsNotNone(doc["audit"]["audio_deleted_at"])
        events = [e["event"] for e in self.store.audit_export("acme-fmcg", conv_id)]
        self.assertIn("audio_deleted", events)
        for s in doc["signals"]:  # no raw PII in any quote
            self.assertNotIn("98765", s["quote"])
            self.assertNotIn("Ramesh", s["quote"])

    def test_consent_is_mandatory(self):
        with self.assertRaises(ConsentRequired):
            self.ingestion.submit("acme-fmcg", b"x", {"consent": {"captured": False}})

    def test_tenant_isolation(self):
        conv_id = self._submit()
        self.worker.drain()
        self.store.create_tenant("zen-pharma", "Zen", "pharma")
        self.assertIsNone(self.store.get_insight("zen-pharma", conv_id))
        self.assertEqual(self.store.list_insights("zen-pharma"), [])

    def test_delete_on_demand(self):
        conv_id = self._submit()
        self.worker.drain()
        self.assertTrue(self.store.delete_conversation("acme-fmcg", conv_id))
        self.assertIsNone(self.store.get_insight("acme-fmcg", conv_id))
        events = [e["event"] for e in self.store.audit_export("acme-fmcg", conv_id)]
        self.assertIn("insight_deleted_on_demand", events)

    def test_failed_job_is_retried_then_dead(self):
        conv_id = self._submit()
        # sabotage: remove the audio so ASR fails every attempt
        (self.data_dir / "audio" / "acme-fmcg" / f"{conv_id}.part0.audio").unlink()
        with self.assertRaises(FileNotFoundError):
            while True:
                self.worker.process_one()
        self.assertEqual(self.queue.counts().get("dead"), 1)


if __name__ == "__main__":
    unittest.main()
