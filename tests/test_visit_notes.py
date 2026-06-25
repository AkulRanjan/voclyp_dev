"""Tests for the product-grounded visit-notes summarizer.

Covers: deterministic fallback is never blank (coaching >= 2, product-grounded),
products_discussed stays strictly within the catalog, and the LLM success path
parses crisp fields. Uses fakes so it runs offline with no Sarvam credits.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voclyp.catalog import load_catalog  # noqa: E402
from voclyp.contracts import ConversationContext, Signal, Utterance  # noqa: E402
from voclyp.pipeline.stages.sarvam_visit_notes import SarvamVisitNotes  # noqa: E402

CATALOG = load_catalog("sleep_company")
TAXONOMY = {"summary_fields": []}  # the summarizer only needs the key to exist


def ctx_with(utterances, signals=None):
    ctx = ConversationContext(
        tenant_id="t", conversation_id="c", industry="sleep_company", audio_paths=[],
    )
    ctx.utterances = utterances
    ctx.signals = signals or []
    return ctx


class _FakeLLMOk:
    def chat_completions(self, messages, model="sarvam-30b", max_tokens=900,
                         temperature=0.0, reasoning_effort=None):
        payload = {
            "visit_notes": "Customer came in for back pain; rep pitched the Smart Ortho.",
            "customer_wants": ["Back support", "EMI option"],
            "objections": ["Budget / price concern"],
            "rep_did_well": ["Explained SmartGRID clearly"],
            "coaching": ["Offer a trial", "Lead with no-cost EMI"],
            "products_discussed": [
                {"sku": "SMART-ORTHO", "name": "Whatever", "why": "fits back pain"},
                {"sku": "NOT-A-REAL-SKU", "name": "Fake", "why": "should be dropped"},
            ],
            "outcome": "promising",
        }
        return {"choices": [{"message": {"content": json.dumps(payload)}}]}


class _FakeLLMBoom:
    def chat_completions(self, *a, **k):
        raise RuntimeError("sarvam down")


def _signal(type_, subtype, quote=""):
    return Signal(type=type_, subtype=subtype, speaker="customer",
                  quote=quote, turn=0, confidence=0.7)


class Fallback(unittest.TestCase):
    def test_fallback_never_blank(self):
        stage = SarvamVisitNotes(_FakeLLMBoom(), TAXONOMY, catalog=CATALOG)
        ctx = ctx_with(
            [
                Utterance(text="mujhe back pain hai, ortho chahiye", speaker="customer"),
                Utterance(text="hamare paas Smart Ortho hai", speaker="agent"),
            ],
            [_signal("demand", "orthopaedic_need", "mujhe back pain hai")],
        )
        stage.run(ctx)
        f = ctx.summary_fields
        self.assertTrue(ctx.summary_text)
        self.assertGreaterEqual(len(f["coaching"]), 2)  # coaching never blank
        self.assertTrue(f["customer_wants"])
        self.assertTrue(f["products_discussed"])
        self.assertIn("llm_error", f)

    def test_fallback_products_within_catalog(self):
        stage = SarvamVisitNotes(_FakeLLMBoom(), TAXONOMY, catalog=CATALOG)
        ctx = ctx_with(
            [Utterance(text="garmi lagti hai, cooling chahiye", speaker="customer")],
            [_signal("demand", "cooling_need", "garmi lagti hai")],
        )
        stage.run(ctx)
        skus = {p["sku"] for p in ctx.summary_fields["products_discussed"]}
        valid = {p["sku"] for p in CATALOG["products"]}
        self.assertTrue(skus.issubset(valid))
        self.assertIn("SMART-LUXE-SNOWTEC", skus)  # cooling need -> SnowTec

    def test_wants_are_short_labels_not_quotes(self):
        stage = SarvamVisitNotes(_FakeLLMBoom(), TAXONOMY, catalog=CATALOG)
        ctx = ctx_with(
            [Utterance(text="koi emi plan", speaker="customer")],
            [_signal("intent", "emi_request", "koi emi plan hai kya bhaiya")],
        )
        stage.run(ctx)
        wants = ctx.summary_fields["customer_wants"]
        self.assertIn("EMI / monthly payment option", wants)
        # crisp label, not the raw utterance
        self.assertNotIn("koi emi plan hai kya bhaiya", wants)

    def test_too_short_recording(self):
        stage = SarvamVisitNotes(_FakeLLMBoom(), TAXONOMY, catalog=CATALOG)
        ctx = ctx_with([Utterance(text="hi", speaker="agent")])
        stage.run(ctx)
        self.assertGreaterEqual(len(ctx.summary_fields["coaching"]), 1)

    def test_no_substance_stays_honest_on_fallback(self):
        # Real speech, but no needs/products discussed → no invented insights.
        stage = SarvamVisitNotes(_FakeLLMBoom(), TAXONOMY, catalog=CATALOG)
        ctx = ctx_with([
            Utterance(text="namaste sir, kaise hain aap aaj", speaker="agent"),
            Utterance(text="bas aise hi dekhne aaya tha, kaam tha thoda", speaker="customer"),
        ])
        stage.run(ctx)
        f = ctx.summary_fields
        self.assertEqual(f["customer_wants"], [])
        self.assertEqual(f["objections"], [])
        self.assertEqual(f["products_discussed"], [])
        self.assertEqual(f["llm_outcome"], "neutral")
        self.assertNotIn("pitched", f["visit_notes"].lower())


class NoHallucination(unittest.TestCase):
    def test_llm_invented_wants_are_dropped_when_nothing_discussed(self):
        class _Hallucinator:
            def chat_completions(self, *a, **k):
                payload = {
                    "visit_notes": "Rep pitched the Smart Ortho for back pain.",
                    "customer_wants": ["Back & spine support", "Cooling"],
                    "objections": ["Price too high"],
                    "rep_did_well": ["Built rapport"],
                    "coaching": ["Follow up tomorrow"],
                    "products_discussed": [],
                    "outcome": "promising",
                }
                return {"choices": [{"message": {"content": json.dumps(payload)}}]}

        stage = SarvamVisitNotes(_Hallucinator(), TAXONOMY, catalog=CATALOG)
        ctx = ctx_with([
            Utterance(text="namaste, baith jaiye aaram se", speaker="agent"),
            Utterance(text="haan bas thoda time tha to aa gaya", speaker="customer"),
        ])
        stage.run(ctx)
        f = ctx.summary_fields
        self.assertEqual(f["customer_wants"], [])      # invented wants dropped
        self.assertEqual(f["objections"], [])          # invented objection dropped
        self.assertEqual(f["products_discussed"], [])  # no real product → none
        self.assertEqual(f["llm_outcome"], "neutral")  # not "promising"

    def test_llm_real_product_is_kept_as_substance(self):
        class _RealProduct:
            def chat_completions(self, *a, **k):
                payload = {
                    "visit_notes": "Customer asked about the Smart Ortho.",
                    "customer_wants": ["Back support"],
                    "objections": [],
                    "rep_did_well": [],
                    "coaching": ["Offer a trial"],
                    "products_discussed": [
                        {"sku": "SMART-ORTHO", "name": "x", "why": "back support"}],
                    "outcome": "promising",
                }
                return {"choices": [{"message": {"content": json.dumps(payload)}}]}

        stage = SarvamVisitNotes(_RealProduct(), TAXONOMY, catalog=CATALOG)
        ctx = ctx_with([
            Utterance(text="Smart Ortho ke baare mein bataiye", speaker="customer"),
        ])
        stage.run(ctx)
        skus = {p["sku"] for p in ctx.summary_fields["products_discussed"]}
        self.assertIn("SMART-ORTHO", skus)
        self.assertEqual(ctx.summary_fields["llm_outcome"], "promising")


class LLMSuccess(unittest.TestCase):
    def test_parses_and_filters(self):
        stage = SarvamVisitNotes(_FakeLLMOk(), TAXONOMY, catalog=CATALOG)
        ctx = ctx_with(
            [
                Utterance(text="back pain hai", speaker="customer"),
                Utterance(text="Smart Ortho dikhata hu", speaker="agent"),
            ],
            [_signal("demand", "orthopaedic_need", "back pain hai")],
        )
        stage.run(ctx)
        f = ctx.summary_fields
        self.assertEqual(f["llm_outcome"], "promising")
        self.assertTrue(f["visit_notes"])
        skus = {p["sku"] for p in f["products_discussed"]}
        self.assertIn("SMART-ORTHO", skus)
        self.assertNotIn("NOT-A-REAL-SKU", skus)  # invalid SKU dropped
        # catalog name overrides the model's bogus name
        ortho = next(p for p in f["products_discussed"] if p["sku"] == "SMART-ORTHO")
        self.assertNotEqual(ortho["name"], "Whatever")

    def test_thin_llm_backfilled(self):
        class _Thin:
            def chat_completions(self, *a, **k):
                payload = {"visit_notes": "", "coaching": [], "customer_wants": [],
                           "objections": [], "products_discussed": [], "outcome": "neutral"}
                return {"choices": [{"message": {"content": json.dumps(payload)}}]}

        stage = SarvamVisitNotes(_Thin(), TAXONOMY, catalog=CATALOG)
        ctx = ctx_with(
            [Utterance(text="back pain hai mujhe", speaker="customer")],
            [_signal("demand", "orthopaedic_need", "back pain hai mujhe")],
        )
        stage.run(ctx)
        f = ctx.summary_fields
        self.assertTrue(ctx.summary_text)              # backfilled visit_notes
        self.assertGreaterEqual(len(f["coaching"]), 2)  # backfilled coaching
        self.assertTrue(f["products_discussed"])        # backfilled product


if __name__ == "__main__":
    unittest.main(verbosity=2)
