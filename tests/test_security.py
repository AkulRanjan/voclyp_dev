"""Security guardrail tests: keys, encryption, SSRF, signing, audit chain, PII."""
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voclyp import security
from voclyp.config import Settings
from voclyp.contracts import ConversationContext, Utterance
from voclyp.ingestion import IngestionService, ValidationError
from voclyp.pipeline.stages.redaction import RegexRedaction
from voclyp.queueing import JobQueue
from voclyp.security import AudioVault
from voclyp.store import Store


class ApiKeyTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="voclyp-sec-"))
        self.store = Store(self.dir / "voclyp.db")
        self.store.create_tenant("acme-fmcg", "Acme", "fmcg")

    def test_plaintext_never_stored(self):
        key = self.store.create_api_key("acme-fmcg")
        secret = key.split("_", 2)[2]
        self.assertNotIn(secret.encode(), (self.dir / "voclyp.db").read_bytes())

    def test_authenticate_and_scopes(self):
        key = self.store.create_api_key("acme-fmcg", scopes=("read",))
        auth = self.store.authenticate(key)
        self.assertEqual(auth["tenant_id"], "acme-fmcg")
        self.assertEqual(auth["scopes"], ["read"])

    def test_wrong_secret_rejected(self):
        key = self.store.create_api_key("acme-fmcg")
        key_id = key.split("_")[1]
        self.assertIsNone(self.store.authenticate(f"vclp_{key_id}_wrongsecret"))
        self.assertIsNone(self.store.authenticate("garbage"))
        self.assertIsNone(self.store.authenticate(""))

    def test_revocation(self):
        key = self.store.create_api_key("acme-fmcg")
        self.store.revoke_api_key(key.split("_")[1])
        self.assertIsNone(self.store.authenticate(key))

    def test_expiry(self):
        key = self.store.create_api_key("acme-fmcg", expires_days=-1)
        self.assertIsNone(self.store.authenticate(key))

    def test_unknown_scope_rejected(self):
        with self.assertRaises(ValueError):
            self.store.create_api_key("acme-fmcg", scopes=("superuser",))


class AuditChainTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="voclyp-sec-"))
        self.store = Store(self.dir / "voclyp.db")

    def test_chain_verifies_and_detects_tamper(self):
        for i in range(5):
            self.store.audit("t1", f"c{i}", "event", f"detail-{i}")
        self.assertEqual(self.store.verify_audit_chain("t1"), (True, None))

        conn = sqlite3.connect(self.dir / "voclyp.db")
        conn.execute("UPDATE audit_log SET detail='forged' WHERE detail='detail-2'")
        conn.commit(); conn.close()
        ok, bad_id = self.store.verify_audit_chain("t1")
        self.assertFalse(ok)
        self.assertIsNotNone(bad_id)


class VaultTest(unittest.TestCase):
    def test_encrypts_at_rest_and_round_trips(self):
        path = Path(tempfile.mkdtemp(prefix="voclyp-sec-")) / "a.audio"
        vault = AudioVault(b"test-master-key")
        self.assertTrue(vault.encrypted)
        vault.write(path, b"sensitive conversation audio")
        self.assertNotIn(b"sensitive", path.read_bytes())
        self.assertEqual(vault.read(path), b"sensitive conversation audio")
        vault.delete(path)
        self.assertFalse(path.exists())

    def test_plaintext_mode_is_explicit(self):
        self.assertFalse(AudioVault().encrypted)


class SsrfGuardTest(unittest.TestCase):
    def test_blocks_internal_targets(self):
        for url in (
            "https://127.0.0.1/hook",
            "https://169.254.169.254/latest/meta-data",  # cloud metadata
            "https://10.0.0.5/hook",
            "https://192.168.1.1/hook",
            "http://8.8.8.8/hook",                        # not https
            "ftp://8.8.8.8/hook",
            "https://user:pass@8.8.8.8/hook",             # credentials
        ):
            ok, reason = security.check_webhook_url(url)
            self.assertFalse(ok, f"{url} should be blocked ({reason})")

    def test_allows_public_https_and_log_sink(self):
        self.assertTrue(security.check_webhook_url("https://8.8.8.8/hook")[0])
        self.assertTrue(security.check_webhook_url("log://connector")[0])


class WebhookSigningTest(unittest.TestCase):
    def test_sign_verify_roundtrip_and_tamper(self):
        secret = security.new_webhook_secret()
        body = b'{"schema_version": "1.0"}'
        header = security.sign_webhook(secret, int(time.time()), body)
        self.assertTrue(security.verify_webhook_signature(secret, header, body))
        self.assertFalse(security.verify_webhook_signature(secret, header, b"{}"))
        self.assertFalse(security.verify_webhook_signature("whsec_other", header, body))

    def test_replay_rejected(self):
        secret = security.new_webhook_secret()
        body = b"{}"
        old = security.sign_webhook(secret, int(time.time()) - 3600, body)
        self.assertFalse(security.verify_webhook_signature(secret, old, body))


class RedactionTest(unittest.TestCase):
    def _redact(self, text):
        ctx = ConversationContext("t", "c", "fmcg", "x")
        ctx.utterances = [Utterance(text=text, normalized_text=text)]
        RegexRedaction().run(ctx)
        return ctx.utterances[0].text, ctx.pii_redactions

    def test_aadhaar_redacted_whole(self):
        text, counts = self._redact("Aadhaar 1234 5678 9012 likha hai")
        self.assertIn("[REDACTED:AADHAAR]", text)
        self.assertNotIn("5678", text)
        self.assertEqual(counts.get("aadhaar"), 1)

    def test_pan_redacted(self):
        text, counts = self._redact("PAN ABCDE1234F diya")
        self.assertIn("[REDACTED:PAN]", text)
        self.assertEqual(counts.get("pan"), 1)

    def test_phone_and_email(self):
        text, counts = self._redact("call 98765 43210 or mail x@y.com")
        self.assertIn("[REDACTED:PHONE]", text)
        self.assertIn("[REDACTED:EMAIL]", text)


class IngestionGuardrailTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="voclyp-sec-"))
        self.store = Store(self.dir / "voclyp.db")
        self.queue = JobQueue(self.dir / "queue.db")
        self.store.create_tenant("acme-fmcg", "Acme", "fmcg")
        self.ingestion = IngestionService(
            self.store, self.queue, self.dir / "audio",
            settings=Settings(max_upload_bytes=64, max_metadata_field_len=16),
        )
        self.meta = {"agent_id": "a1", "consent": {"captured": True}}

    def test_oversize_upload_rejected(self):
        with self.assertRaises(ValidationError):
            self.ingestion.submit("acme-fmcg", b"x" * 65, self.meta)

    def test_oversize_metadata_rejected(self):
        with self.assertRaises(ValidationError):
            self.ingestion.submit(
                "acme-fmcg", b"ok",
                {"agent_id": "a" * 17, "consent": {"captured": True}},
            )

    def test_idempotent_resubmission(self):
        meta = dict(self.meta, client_ref="ref-1")
        first = self.ingestion.submit("acme-fmcg", b"audio", meta)
        second = self.ingestion.submit("acme-fmcg", b"audio", meta)
        self.assertEqual(first, second)
        self.assertEqual(self.queue.counts().get("pending"), 1)

    def test_bad_tenant_slug_rejected(self):
        with self.assertRaises(ValueError):
            self.store.create_tenant("../escape", "Evil", "fmcg")
        with self.assertRaises(ValueError):
            self.store.create_tenant("UPPER", "Evil", "fmcg")


if __name__ == "__main__":
    unittest.main()
