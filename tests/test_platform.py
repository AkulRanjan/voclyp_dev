"""Phase-1 platform tests: pipeline config, chunking, eval harness,
feedback loop, and metrics."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voclyp.config import Settings
from voclyp.ingestion import IngestionService
from voclyp.mlops.eval import run_eval
from voclyp.pipeline.registry import (
    PipelineConfigError, build_pipeline, load_pipeline_config,
    validate_pipeline_config,
)
from voclyp.queueing import JobQueue
from voclyp.security import AudioVault
from voclyp.store import Store
from voclyp.taxonomy import load_taxonomy
from voclyp.worker import Worker


def _config(roles_impls):
    return {"version": "test", "stages": [
        {"role": r, "impl": i} for r, i in roles_impls
    ]}

_GOOD = [
    ("asr", "stub"), ("diarization", "stub"), ("lang_id_translation", "stub"),
    ("pii_redaction", "regex"), ("audio_deletion", "vault"),
    ("signal_extraction", "taxonomy"), ("summarization", "taxonomy"),
]


class PipelineConfigTest(unittest.TestCase):
    def test_default_config_valid(self):
        config = load_pipeline_config()
        self.assertEqual(len(config["stages"]), 7)

    def test_valid_config_builds(self):
        services = {"vault": AudioVault(), "taxonomy": load_taxonomy("fmcg")}
        runner = build_pipeline(_config(_GOOD), services)
        self.assertEqual(len(runner.stages), 7)

    def test_privacy_invariant_enforced(self):
        # audio deletion after analysis: forbidden
        bad = [x for x in _GOOD if x[0] != "audio_deletion"]
        bad.append(("audio_deletion", "vault"))
        with self.assertRaises(PipelineConfigError):
            validate_pipeline_config(_config(bad))
        # redaction after deletion: forbidden
        swapped = list(_GOOD)
        i, j = swapped.index(("pii_redaction", "regex")), swapped.index(("audio_deletion", "vault"))
        swapped[i], swapped[j] = swapped[j], swapped[i]
        with self.assertRaises(PipelineConfigError):
            validate_pipeline_config(_config(swapped))

    def test_missing_required_role_rejected(self):
        with self.assertRaises(PipelineConfigError):
            validate_pipeline_config(
                _config([x for x in _GOOD if x[0] != "audio_deletion"])
            )

    def test_unknown_impl_rejected(self):
        bad = [("asr", "imaginary")] + _GOOD[1:]
        with self.assertRaises(PipelineConfigError):
            validate_pipeline_config(_config(bad))

    def test_whisper_impl_registered_and_buildable(self):
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            self.skipTest("faster-whisper not installed")
        config = _config([("asr", "whisper")] + _GOOD[1:])
        services = {"vault": AudioVault(), "taxonomy": load_taxonomy("fmcg")}
        runner = build_pipeline(config, services)  # lazy: no model download
        self.assertTrue(runner.stages[0].version.startswith("faster-whisper-"))


class ChunkingTest(unittest.TestCase):
    def test_long_audio_chunked_processed_and_destroyed(self):
        data_dir = Path(tempfile.mkdtemp(prefix="voclyp-chunk-"))
        store = Store(data_dir / "voclyp.db")
        queue = JobQueue(data_dir / "queue.db")
        store.create_tenant("acme-fmcg", "Acme", "fmcg")
        ingestion = IngestionService(
            store, queue, data_dir / "audio",
            settings=Settings(chunk_bytes=64),
        )
        transcript = (
            "CUSTOMER: Purana stock pada hai, not selling.\n"
            "CUSTOMER: Chota pack chahiye, sachet wala.\n"
            "AGENT: I will deliver by tomorrow.\n"
        ).encode("utf-8")
        conv_id = ingestion.submit(
            "acme-fmcg", transcript, {"consent": {"captured": True}}
        )

        parts = sorted((data_dir / "audio" / "acme-fmcg").glob(f"{conv_id}.part*.audio"))
        self.assertGreaterEqual(len(parts), 2)
        # newline-boundary splitting: no utterance cut in half
        for part in parts:
            self.assertTrue(part.read_bytes().endswith(b"\n"))

        Worker(store, queue).drain()
        doc = store.get_insight("acme-fmcg", conv_id)
        types = {(s["type"], s["subtype"]) for s in doc["signals"]}
        # signals span all chunks -> the conversation was reassembled in order
        self.assertIn(("objection", "stock_unsold"), types)
        self.assertIn(("demand", "sku_request"), types)
        self.assertIn(("promise", "delivery_promise"), types)
        self.assertFalse(any(p.exists() for p in parts))


class EvalHarnessTest(unittest.TestCase):
    def test_fmcg_eval_perfect_on_labeled_set(self):
        report = run_eval("fmcg")
        self.assertEqual(report["overall"]["f1"], 1.0)
        self.assertIn("asr", report["stage_versions"])

    def test_pharma_eval(self):
        report = run_eval("pharma")
        self.assertGreaterEqual(report["overall"]["f1"], 0.8)


class FeedbackAndMetricsTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="voclyp-mlops-"))
        self.store = Store(self.dir / "voclyp.db")
        self.queue = JobQueue(self.dir / "queue.db")
        self.store.create_tenant("acme-fmcg", "Acme", "fmcg")
        self.ingestion = IngestionService(self.store, self.queue, self.dir / "audio")

    def test_feedback_roundtrip_and_audited(self):
        self.store.add_feedback("acme-fmcg", "conv1", "signals[0].subtype",
                                "margin_too_low", "was tagged price_too_high")
        rows = self.store.feedback_for("acme-fmcg", "conv1")
        self.assertEqual(rows[0]["correction"], "margin_too_low")
        events = [e["event"] for e in self.store.audit_export("acme-fmcg", "conv1")]
        self.assertIn("feedback_received", events)
        self.assertEqual(self.store.feedback_for("other-tenant"), [])

    def test_stage_metrics_recorded(self):
        self.ingestion.submit(
            "acme-fmcg", b"CUSTOMER: Ye bahut costly hai.\n",
            {"consent": {"captured": True}},
        )
        Worker(self.store, self.queue).drain()
        summary = self.store.metrics_summary("acme-fmcg")
        stages = {row["stage"] for row in summary}
        self.assertIn("asr", stages)
        self.assertIn("signal_extraction", stages)
        self.assertTrue(all(row["avg_ms"] >= 0 for row in summary))


if __name__ == "__main__":
    unittest.main()
