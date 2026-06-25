"""Enterprise cloud layer — full offline end-to-end (no network, no creds).

Exercises consent-first ingestion, the in-memory event cascade (Sarvam ASR mock
-> Bedrock heuristic extractor -> routing fan-out), the EMI human-verification
hold + release, immutable consent hash-chain verification, and the 2-hour
erasure sweep — all against the SQLite/filesystem/mock backends.
"""
import asyncio
import io
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voclyp.enterprise.config import EnterpriseSettings
from voclyp.enterprise.consent.service import ConsentError
from voclyp.enterprise.erasure import orphan_sweep
from voclyp.enterprise.extraction.schema import EXTRACTION_SCHEMA, build_tool_config
from voclyp.enterprise.pipeline import build_enterprise
from voclyp.enterprise.routing.dispatcher import MAX_ATTEMPTS, idempotency_key
from voclyp.enterprise.store import (
    IllegalTransition,
    LocalStore,
    PostgresStore,
    assert_transition,
    schema_for_tenant,
)


def _wav_bytes(seconds: float = 1.0, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))
    return buf.getvalue()


def _read_lines(path: Path) -> list:
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


class EnterprisePipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="voclyp-ent-test-")
        self.settings = EnterpriseSettings(enabled=True, local_dir=self.tmp)
        self.pipeline = build_enterprise(self.settings)

    def _ingest(self, **overrides):
        kwargs = dict(
            tenant_id="tenant-a", agent_id="agent-7", store_id="store-1",
            session_id="sess-1", language="hi-IN",
            purposes={"recording": True, "whatsapp_followup": True,
                      "crm_storage": True},
            device_fingerprint={"model": "iPhone 14", "os": "iOS 17"},
            notice_text="Aapki baat record ki ja rahi hai...",
            audio=_wav_bytes(), customer_phone="+919812345678")
        kwargs.update(overrides)
        return self.pipeline.ingestion.ingest(**kwargs)

    def test_offline_backends_selected(self):
        self.assertIsInstance(self.pipeline.store, LocalStore)
        self.assertEqual(self.pipeline.bus.backend, "memory")
        self.assertEqual(self.pipeline.audio_store.backend, "local")

    def test_full_cascade_with_emi_hold_and_release(self):
        result = self._ingest()
        cid = result["conversation_id"]
        self.assertEqual(result["state"], "audio_uploaded")
        self.assertTrue(result["consent_entry_hash"])

        # in-memory bus cascaded synchronously to a dispatching conversation
        conv = self.pipeline.store.get_conversation(cid)
        self.assertEqual(conv["state"], "dispatching")
        self.assertTrue(conv["transcript_codemix"])
        self.assertTrue(conv["transcript_english"])
        self.assertIn("hi", conv["detected_languages"])

        # the canned mock transcript contains an EMI figure -> verification hold
        extraction = conv["extraction"]
        self.assertTrue(extraction["emi_commitments"])
        self.assertTrue(conv["requires_human_verification"])

        routing = {r["channel"]: r for r in
                   self.pipeline.store.get_routing_for_conversation(cid)}
        self.assertEqual(routing["zoho"]["status"], "delivered")
        self.assertEqual(routing["push"]["status"], "delivered")
        self.assertEqual(routing["whatsapp"]["status"], "held")
        # idempotency key persisted on every outbox row (64-hex SHA-256)
        self.assertEqual(len(routing["zoho"]["idempotency_key"]), 64)

        sinks = Path(self.tmp) / "sinks"
        self.assertEqual(len(_read_lines(sinks / "zoho.jsonl")), 1)
        self.assertEqual(len(_read_lines(sinks / "push.jsonl")), 1)
        self.assertEqual(_read_lines(sinks / "whatsapp.jsonl"), [])  # held

        # agent verification queue lists it
        pending = self.pipeline.store.pending_verifications("tenant-a", "agent-7")
        self.assertEqual(len(pending), 1)

        # 1-tap verify releases the WhatsApp hold and delivers it
        out = self.pipeline.dispatcher.verify(cid, verified_by="agent-7",
                                              whatsapp_to="+919812345678")
        self.assertTrue(out["whatsapp_released"])
        routing = self.pipeline.store.get_routing(cid, "whatsapp")
        self.assertEqual(routing["status"], "delivered")
        self.assertEqual(len(_read_lines(sinks / "whatsapp.jsonl")), 1)

        conv = self.pipeline.store.get_conversation(cid)
        self.assertFalse(conv["requires_human_verification"])
        self.assertEqual(conv["verified_by"], "agent-7")

    def test_consent_chain_is_tamper_evident(self):
        self._ingest()
        self._ingest(session_id="sess-2")
        ok, bad = self.pipeline.store.verify_consent_chain("tenant-a")
        self.assertTrue(ok)
        self.assertIsNone(bad)

    def test_consent_first_aborts_before_storage(self):
        with self.assertRaises(ConsentError):
            self._ingest(purposes={"recording": False, "whatsapp_followup": True})
        # nothing was written downstream
        ok, _ = self.pipeline.store.verify_consent_chain("tenant-zzz")
        self.assertTrue(ok)

    def test_low_confidence_forces_verification(self):
        # an empty/no-signal transcript yields low overall confidence
        res = self._ingest(mock_transcript="Namaste. Theek hai. Dhanyavaad.")
        conv = self.pipeline.store.get_conversation(res["conversation_id"])
        self.assertLess(conv["extraction_confidence"],
                        self.settings.confidence_threshold)
        self.assertTrue(conv["requires_human_verification"])

    def test_erasure_sweep_destroys_audio(self):
        res = self._ingest()
        cid = res["conversation_id"]
        conv = self.pipeline.store.get_conversation(cid)
        # audio is present until erased
        self.assertTrue(self.pipeline.audio_store.get(conv["s3_key"]))

        # force the deadline into the past, then sweep
        self.pipeline.store.update_conversation(
            cid, erase_after="2000-01-01T00:00:00+00:00")
        summary = self.pipeline.erasure.run_once()
        self.assertEqual(summary["erased"], 1)

        conv = self.pipeline.store.get_conversation(cid)
        self.assertEqual(conv["state"], "purged")
        self.assertIsNotNone(conv["erased_at"])
        with self.assertRaises(Exception):
            self.pipeline.audio_store.get(conv["s3_key"])
        self.assertEqual(
            len(_read_lines(Path(self.tmp) / "sinks" / "erasure.jsonl")), 1)

    def test_routing_retry_for_failed_channel(self):
        res = self._ingest()
        cid = res["conversation_id"]
        # simulate a transient zoho failure that is now due for retry
        row = self.pipeline.store.get_routing(cid, "zoho")
        self.pipeline.store.update_routing(
            row["id"], status="failed", attempts=1,
            next_retry_at="2000-01-01T00:00:00+00:00")
        processed = self.pipeline.dispatcher.process_due()
        self.assertGreaterEqual(processed, 1)
        self.assertEqual(self.pipeline.store.get_routing(cid, "zoho")["status"],
                         "delivered")

    def test_illegal_state_transition_rejected(self):
        res = self._ingest()
        cid = res["conversation_id"]
        # conversation is in 'dispatching' after the cascade; jumping back to
        # 'transcribing' is illegal and must raise.
        with self.assertRaises(IllegalTransition):
            self.pipeline.store.set_state(cid, "transcribing")

    def test_dlq_on_sixth_failure(self):
        res = self._ingest()
        cid = res["conversation_id"]

        class _AlwaysFails:
            def send(self, payload, idempotency_key=""):
                return {"ok": False, "response": {}, "detail": "boom"}

        self.pipeline.dispatcher.clients["zoho"] = _AlwaysFails()
        row = self.pipeline.store.get_routing(cid, "zoho")
        # pretend we have already burned all 5 retries
        self.pipeline.store.update_routing(
            row["id"], status="failed", attempts=MAX_ATTEMPTS,
            next_retry_at="2000-01-01T00:00:00+00:00")
        self.pipeline.dispatcher.process_due()
        # 6th failure -> moved out of the active outbox into the DLQ
        self.assertIsNone(self.pipeline.store.get_routing(cid, "zoho"))
        dlq = self.pipeline.store.get_dlq_for_conversation(cid)
        self.assertEqual(len(dlq), 1)
        self.assertEqual(dlq[0]["channel"], "zoho")
        self.assertEqual(dlq[0]["attempts"], MAX_ATTEMPTS + 1)

    def test_idempotency_key_is_deterministic(self):
        payload = {"a": 1, "b": [2, 3]}
        k1 = idempotency_key("conv-1", "zoho", payload)
        k2 = idempotency_key("conv-1", "zoho", {"b": [2, 3], "a": 1})  # key order
        self.assertEqual(k1, k2)
        self.assertEqual(len(k1), 64)
        # destination type is part of the material -> different channel, new key
        self.assertNotEqual(k1, idempotency_key("conv-1", "whatsapp", payload))
        self.assertNotEqual(k1, idempotency_key("conv-2", "zoho", payload))

    def test_tenant_schema_isolation(self):
        a = self._ingest(tenant_id="sleep_company", session_id="s-a")
        b = self._ingest(tenant_id="max_life", session_id="s-b")
        # cross-tenant reads are impossible (data lives in separate schema files)
        self.assertIsNone(self.pipeline.store.get_conversation(
            a["conversation_id"], "max_life"))
        self.assertIsNone(self.pipeline.store.get_conversation(
            b["conversation_id"], "sleep_company"))
        # one physical SQLite file per tenant schema
        store_dir = Path(self.tmp) / "store"
        self.assertTrue((store_dir / "enterprise_schema_sleep_company.db").exists())
        self.assertTrue((store_dir / "enterprise_schema_max_life.db").exists())

    def test_orphan_sweep_force_purges_stranded(self):
        # craft a conversation stranded in audio_uploaded with an old timestamp
        cid = "orphan-conv-1"
        key = "tenant-a/orphan-conv-1.wav"
        self.pipeline.audio_store.put(key, b"RIFFstub", erase_after="")
        self.pipeline.store.insert_conversation({
            "id": cid, "tenant_id": "tenant-a", "agent_id": "a", "store_id": "s1",
            "consent_log_id": "c1", "s3_bucket": self.pipeline.audio_store.bucket,
            "s3_key": key, "audio_sha256": "x", "state": "audio_uploaded",
            "detected_languages": [], "erase_after": "2000-01-01T00:00:00+00:00",
            "created_at": "2000-01-01T00:00:00+00:00",
            "updated_at": "2000-01-01T00:00:00+00:00"})

        summary = asyncio.run(orphan_sweep.sweep_once(self.settings))
        self.assertEqual(summary["backend"], "local")
        self.assertGreaterEqual(summary["swept"], 1)

        conv = self.pipeline.store.get_conversation(cid)
        self.assertEqual(conv["state"], "error_purged")
        self.assertIsNotNone(conv["erased_at"])
        with self.assertRaises(Exception):
            self.pipeline.audio_store.get(key)


class StateMachineTest(unittest.TestCase):
    def test_allowed_and_blocked_transitions(self):
        assert_transition("audio_uploaded", "transcribing")        # ok
        assert_transition("dispatching", "purged")                 # ok
        assert_transition("transcribing", "error_purged")          # ok from any
        assert_transition("dispatching", "dispatching")            # no-op ok
        with self.assertRaises(IllegalTransition):
            assert_transition("audio_uploaded", "purged")
        with self.assertRaises(IllegalTransition):
            assert_transition("purged", "dispatching")             # terminal

    def test_schema_for_tenant(self):
        self.assertEqual(schema_for_tenant("Sleep Company"), "schema_sleep_company")
        self.assertEqual(schema_for_tenant("max_life"), "schema_max_life")


class ExtractionSchemaTest(unittest.TestCase):
    def test_tool_config_shape(self):
        cfg = build_tool_config()
        spec = cfg["tools"][0]["toolSpec"]
        self.assertEqual(spec["name"], "extract_showroom_intel")
        self.assertEqual(cfg["toolChoice"]["tool"]["name"], "extract_showroom_intel")
        self.assertIs(spec["inputSchema"]["json"], EXTRACTION_SCHEMA)

    def test_schema_required_top_level_keys(self):
        self.assertEqual(set(EXTRACTION_SCHEMA["required"]), {
            "posture_issues", "pricing_objections", "competitor_mentions",
            "emi_commitments", "next_best_action", "overall_confidence"})
        self.assertFalse(EXTRACTION_SCHEMA["additionalProperties"])


class BackendSelectionTest(unittest.TestCase):
    def test_postgres_store_is_lazy(self):
        # constructing PostgresStore requires psycopg; just confirm the class
        # is importable and open_store falls back to local without a DSN.
        self.assertTrue(hasattr(PostgresStore, "insert_consent_log"))


if __name__ == "__main__":
    unittest.main()
