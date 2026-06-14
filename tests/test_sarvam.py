"""Sarvam integration tests — fake client, no network, no credits burned.

The live path is exercised by scripts/sarvam_check.py with a real key.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voclyp.contracts import ConversationContext, Utterance
from voclyp.languages import load_languages, short
from voclyp.pipeline.registry import validate_pipeline_config
from voclyp.pipeline.stages.sarvam_asr import SarvamASR
from voclyp.pipeline.stages.sarvam_batch_asr import SarvamBatchASR
from voclyp.pipeline.stages.sarvam_translate import SarvamTranslate
from voclyp.providers.sarvam import SarvamClient, SarvamError
from voclyp.security import AudioVault


class FakeSarvam:
    """Stands in for SarvamClient; records every call."""

    def __init__(self):
        self.stt_calls = []
        self.translate_calls = []

    def speech_to_text(self, audio, model="saarika:v2.5", language_code="unknown"):
        self.stt_calls.append({"bytes": len(audio), "language_code": language_code})
        return {
            "transcript": "यह बहुत महंगा है। The margin is also low.",
            "language_code": "hi-IN",
        }

    def translate(self, text, source="auto", target="en-IN"):
        self.translate_calls.append({"text": text, "target": target})
        return {
            "translated_text": "This is very costly.",
            "source_language_code": "hi-IN",
        }


def _ctx(paths=()):
    return ConversationContext(
        tenant_id="t", conversation_id="c", industry="fmcg",
        audio_paths=list(paths), consent_captured=True,
    )


class LanguagePolicyTest(unittest.TestCase):
    def test_default_policy_is_hindi_english(self):
        config = load_languages()
        codes = [lang["code"] for lang in config["enabled"]]
        self.assertEqual(codes, ["hi-IN", "en-IN"])
        self.assertEqual(config["normalize_to"], "en-IN")
        self.assertIn("ta-IN", config["planned"])  # multilingual later

    def test_short_codes(self):
        self.assertEqual(short("hi-IN"), "hi")
        self.assertEqual(short(""), "")


class SarvamAsrStageTest(unittest.TestCase):
    def test_transcribes_chunks_and_meters_usage(self):
        import tempfile
        vault = AudioVault()
        work = Path(tempfile.mkdtemp(prefix="voclyp-sarvam-"))
        for i in range(2):
            vault.write(work / f"c.part{i}.audio", b"fake-wav-bytes")
        fake = FakeSarvam()
        stage = SarvamASR(fake, vault)
        ctx = _ctx([str(work / "c.part0.audio"), str(work / "c.part1.audio")])
        stage.run(ctx)

        self.assertEqual(len(fake.stt_calls), 2)
        # two enabled languages -> auto-detect mode
        self.assertEqual(fake.stt_calls[0]["language_code"], "unknown")
        self.assertEqual(ctx.provider_usage["sarvam:speech-to-text"], 2)
        # sentence splitting handles the Hindi danda (।)
        self.assertEqual(len(ctx.utterances), 4)
        self.assertEqual(ctx.utterances[0].languages, ["hi"])
        self.assertTrue(stage.version.startswith("sarvam-saarika"))


class FakeBatchJob:
    """Stands in for the sarvamai SpeechToTextJob; writes a canned diarized
    output for every uploaded file."""

    def __init__(self):
        self.uploaded = []
        self.started = False

    def upload_files(self, file_paths, timeout=60.0):
        self.uploaded = list(file_paths)
        return True

    def start(self):
        self.started = True

    def wait_until_complete(self, poll_interval=5, timeout=600):
        return {"job_state": "Completed"}

    def get_file_results(self):
        return {"successful": [{"file_name": Path(p).name} for p in self.uploaded],
                "failed": []}

    def download_outputs(self, output_dir):
        import json
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        for p in self.uploaded:
            (out / (Path(p).stem + ".json")).write_text(json.dumps({
                "language_code": "hi-IN",
                "transcript": "नमस्ते जी। Order book kar dijiye.",
                "diarized_transcript": {"entries": [
                    {"speaker_id": "SPEAKER_0", "transcript": "नमस्ते जी, नया स्टॉक आया है।"},
                    {"speaker_id": "SPEAKER_1", "transcript": "Ye pack bahut costly hai."},
                    {"speaker_id": "SPEAKER_0", "transcript": "Scheme bhi hai is mahine."},
                ]},
            }, ensure_ascii=False), encoding="utf-8")
        return True


class SarvamBatchAsrStageTest(unittest.TestCase):
    def test_diarized_output_maps_speakers_and_meters(self):
        import tempfile
        vault = AudioVault()
        work = Path(tempfile.mkdtemp(prefix="voclyp-batch-"))
        vault.write(work / "c.part0.audio", b"fake-wav-bytes")
        fake = FakeBatchJob()
        stage = SarvamBatchASR(lambda: fake, vault)
        ctx = _ctx([str(work / "c.part0.audio")])
        stage.run(ctx)

        self.assertTrue(fake.started)
        self.assertEqual(len(fake.uploaded), 1)
        # plaintext temp copies are shredded after the job
        self.assertFalse(Path(fake.uploaded[0]).exists())
        self.assertEqual(ctx.provider_usage["sarvam:speech-to-text-job"], 1)
        # first voice = agent, second = customer; labels survive for diarization
        self.assertEqual([u.speaker for u in ctx.utterances],
                         ["agent", "customer", "agent"])
        self.assertEqual(ctx.utterances[0].languages, ["hi"])
        self.assertTrue(stage.version.startswith("sarvam-batch-saaras"))

        # the insight document carries the diarized, redacted transcript
        from voclyp.contracts import build_insight
        doc = build_insight(ctx)
        self.assertEqual(doc["speakers"], {"count": 2, "turns": 3})
        self.assertEqual(len(doc["transcript"]), 3)
        self.assertEqual(doc["transcript"][1]["speaker"], "customer")
        self.assertIn("costly", doc["transcript"][1]["text"])

    def test_failed_file_raises_with_detail(self):
        import tempfile
        vault = AudioVault()
        work = Path(tempfile.mkdtemp(prefix="voclyp-batch-"))
        vault.write(work / "c.part0.audio", b"fake-wav-bytes")

        class FailingJob(FakeBatchJob):
            def get_file_results(self):
                return {"successful": [], "failed": [
                    {"file_name": "part0000.wav", "error_message": "bad audio"}]}

        stage = SarvamBatchASR(lambda: FailingJob(), vault)
        with self.assertRaises(SarvamError) as caught:
            stage.run(_ctx([str(work / "c.part0.audio")]))
        self.assertIn("bad audio", str(caught.exception))

    def test_flat_transcript_fallback_leaves_speakers_unknown(self):
        import tempfile
        vault = AudioVault()
        work = Path(tempfile.mkdtemp(prefix="voclyp-batch-"))
        vault.write(work / "c.part0.audio", b"fake-wav-bytes")

        class FlatJob(FakeBatchJob):
            def download_outputs(self, output_dir):
                import json
                out = Path(output_dir)
                out.mkdir(parents=True, exist_ok=True)
                (out / "part0000.json").write_text(json.dumps({
                    "language_code": "en-IN",
                    "transcript": "Namaste ji. Book my order please.",
                }), encoding="utf-8")
                return True

        ctx = _ctx([str(work / "c.part0.audio")])
        SarvamBatchASR(lambda: FlatJob(), vault).run(ctx)
        self.assertEqual(len(ctx.utterances), 2)
        self.assertTrue(all(u.speaker == "unknown" for u in ctx.utterances))


class SarvamTranslateStageTest(unittest.TestCase):
    def test_translates_hindi_and_skips_english(self):
        fake = FakeSarvam()
        stage = SarvamTranslate(fake)
        ctx = _ctx()
        ctx.utterances = [
            Utterance(text="यह बहुत महंगा है।", languages=["hi"]),
            Utterance(text="I will deliver by tomorrow.", languages=["en"]),
        ]
        stage.run(ctx)

        # only the Hindi utterance cost a credit
        self.assertEqual(len(fake.translate_calls), 1)
        self.assertEqual(ctx.provider_usage["sarvam:translate"], 1)
        self.assertEqual(ctx.utterances[0].normalized_text, "This is very costly.")
        self.assertEqual(ctx.utterances[1].normalized_text,
                         "I will deliver by tomorrow.")
        self.assertEqual(ctx.detected_languages, ["hi", "en"])
        self.assertTrue(ctx.code_switching)
        self.assertEqual(ctx.normalized_to, "en")

    def test_code_mixed_single_utterance_flagged(self):
        fake = FakeSarvam()
        stage = SarvamTranslate(fake)
        ctx = _ctx()
        ctx.utterances = [Utterance(text="यह pack बहुत costly है।")]
        stage.run(ctx)
        self.assertEqual(ctx.utterances[0].languages, ["hi", "en"])
        self.assertTrue(ctx.code_switching)


class SarvamWiringTest(unittest.TestCase):
    def test_sarvam_pipeline_config_is_valid(self):
        import json
        config = json.loads(
            (Path(__file__).resolve().parents[1] / "configs"
             / "pipeline.sarvam.json").read_text(encoding="utf-8")
        )
        validate_pipeline_config(config)  # registered + privacy order intact

    def test_missing_api_key_fails_closed_with_clear_error(self):
        with self.assertRaises(SarvamError) as caught:
            SarvamClient("")
        self.assertIn("SARVAM_API_KEY", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
