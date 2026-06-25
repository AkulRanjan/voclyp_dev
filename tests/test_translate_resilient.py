"""The translate stage must never sink the pipeline when Sarvam errors."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voclyp.contracts import ConversationContext, Utterance  # noqa: E402
from voclyp.pipeline.stages.sarvam_translate import SarvamTranslate  # noqa: E402
from voclyp.providers.sarvam import SarvamError  # noqa: E402

LANGS = {"normalize_to": "en-IN", "enabled": [{"code": "hi-IN"}]}


class AlwaysFailClient:
    def translate(self, text, source="auto", target="en-IN"):
        raise SarvamError("sarvam /translate -> HTTP 422: cannot detect language")


class ExplicitOnlyClient:
    """Fails on auto-detect but succeeds with an explicit source language."""
    def translate(self, text, source="auto", target="en-IN"):
        if source == "auto":
            raise SarvamError("HTTP 422: cannot detect language")
        return {"translated_text": "[translated] " + text, "source_language_code": source}


def _ctx():
    c = ConversationContext(
        tenant_id="t", conversation_id="c", industry="sleep_company",
        audio_paths=[], agent_id="a", store_id="s", consent_captured=True,
    )
    c.utterances = [Utterance(text="मुझे पीठ में दर्द है", speaker="customer")]
    return c


class TranslateResilience(unittest.TestCase):
    def test_failure_keeps_original_text_and_does_not_raise(self):
        ctx = _ctx()
        SarvamTranslate(AlwaysFailClient(), LANGS).run(ctx)  # must not raise
        self.assertEqual(ctx.utterances[0].normalized_text, "मुझे पीठ में दर्द है")
        self.assertEqual(ctx.provider_usage.get("sarvam:translate-skipped"), 1)

    def test_explicit_source_used_when_auto_detect_fails(self):
        ctx = _ctx()
        SarvamTranslate(ExplicitOnlyClient(), LANGS).run(ctx)
        self.assertTrue(ctx.utterances[0].normalized_text.startswith("[translated]"))
        self.assertEqual(ctx.provider_usage.get("sarvam:translate"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
