"""Tests for grounded mattress recommendations (catalog matcher + LLM grounding)."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voclyp.catalog import load_catalog, rank_products, emi_line  # noqa: E402
from voclyp.recommend import recommend_products  # noqa: E402

CATALOG = load_catalog("sleep_company")


def sig(type_, subtype, quote=""):
    return {"type": type_, "subtype": subtype, "quote": quote}


class Matcher(unittest.TestCase):
    def test_back_pain_picks_ortho(self):
        ranked = rank_products(CATALOG, [sig("demand", "orthopaedic_need", "mujhe back pain hai")])
        self.assertTrue(ranked[0]["series"] == "ortho",
                        f"expected an ortho top pick, got {ranked[0]['sku']}")

    def test_cooling_need_picks_snowtec(self):
        ranked = rank_products(CATALOG, [sig("demand", "cooling_need", "I am a hot sleeper, need cooling")])
        self.assertEqual(ranked[0]["sku"], "SMART-LUXE-SNOWTEC")
        self.assertTrue(ranked[0]["cooling"])

    def test_budget_boosts_affordable_tiers(self):
        budget = rank_products(CATALOG, [
            sig("objection", "budget_too_high", "budget is tight, too expensive"),
            sig("demand", "orthopaedic_need", "back pain"),
        ])
        # The entry-tier ortho should outrank the pricier ortho pro under budget pressure.
        order = [p["sku"] for p in budget]
        self.assertIn("SMART-ORTHO", order)
        self.assertLess(order.index("SMART-ORTHO"), order.index("SMART-ORTHO-PRO")
                        if "SMART-ORTHO-PRO" in order else len(order))

    def test_emi_line_surfaced_in_reasons(self):
        ranked = rank_products(CATALOG, [sig("intent", "emi_request", "koi emi option hai")])
        top = ranked[0]
        self.assertTrue(top["emi"].startswith("No-cost EMI"))
        self.assertTrue(any("EMI" in r for r in top["reasons"]))

    def test_every_product_has_emi_and_reasons(self):
        ranked = rank_products(CATALOG, [], limit=5)
        self.assertEqual(len(ranked), 5)
        for p in ranked:
            self.assertTrue(emi_line(p).startswith("No-cost EMI"))
            self.assertIsInstance(p["reasons"], list)

    def test_discussed_sku_leads_over_needs(self):
        # Needs point at ortho (back pain), but they kept discussing the Royale.
        ranked = rank_products(
            CATALOG,
            [sig("demand", "orthopaedic_need", "back pain hai")],
            limit=3,
            discussed_skus=["SMART-LUXE-ROYALE"],
        )
        self.assertEqual(ranked[0]["sku"], "SMART-LUXE-ROYALE")
        self.assertIn("You discussed this in-store", ranked[0]["reasons"])

    def test_no_discussed_keeps_needs_ranking(self):
        ranked = rank_products(
            CATALOG, [sig("demand", "orthopaedic_need", "back pain hai")], limit=3,
        )
        self.assertEqual(ranked[0]["series"], "ortho")

    def test_discussed_order_preserved(self):
        ranked = rank_products(
            CATALOG, [], limit=3,
            discussed_skus=["SMART-LUXE-SNOWTEC", "SMART-ORTHO"],
        )
        self.assertEqual([ranked[0]["sku"], ranked[1]["sku"]],
                         ["SMART-LUXE-SNOWTEC", "SMART-ORTHO"])


class _FakeLLMOk:
    def chat_completions(self, messages, model="sarvam-30b", max_tokens=900,
                         reasoning_effort=None):
        # Echo back a valid grounded recommendation for whatever SKUs are listed.
        user = messages[-1]["content"]
        sku = "SMART-ORTHO" if "SMART-ORTHO" in user else "SMART-LUXE-PRO"
        payload = {"recommendations": [
            {"sku": sku, "why": "Great for your back pain.",
             "whatsapp_blurb": "Smart Ortho — perfect back support, no-cost EMI."}
        ]}
        return {"choices": [{"message": {"content": json.dumps(payload)}}]}


class _FakeLLMBoom:
    def chat_completions(self, *a, **k):
        raise RuntimeError("sarvam down")


class Grounding(unittest.TestCase):
    def test_llm_failure_is_failsoft(self):
        signals = [sig("demand", "orthopaedic_need", "back pain")]
        out = recommend_products(CATALOG, signals, transcript="Customer: back pain",
                                 llm_client=_FakeLLMBoom())
        self.assertTrue(out)  # never raises, still returns shortlist
        for p in out:
            self.assertTrue(p["why"])             # deterministic fallback present
            self.assertTrue(p["whatsapp_blurb"])  # deterministic fallback present

    def test_llm_success_attaches_why(self):
        signals = [sig("demand", "orthopaedic_need", "back pain")]
        out = recommend_products(CATALOG, signals, transcript="Customer: back pain",
                                 llm_client=_FakeLLMOk())
        grounded = [p for p in out if p["why"] == "Great for your back pain."]
        self.assertTrue(grounded, "expected at least one LLM-grounded why")

    def test_no_client_uses_deterministic(self):
        out = recommend_products(CATALOG, [sig("demand", "cooling_need", "hot sleeper")],
                                 llm_client=None)
        self.assertEqual(out[0]["sku"], "SMART-LUXE-SNOWTEC")
        self.assertTrue(out[0]["why"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
