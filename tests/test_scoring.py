"""Scoring: subtype bonuses (NPS/referral, buying commitment) + components."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voclyp.scoring import score_conversation  # noqa: E402


def sig(type_, subtype):
    return {"type": type_, "subtype": subtype, "speaker": "customer",
            "quote": "", "turn": 0, "confidence": 0.7}


class Scoring(unittest.TestCase):
    def test_referral_adds_advocacy_and_extra_points(self):
        base = score_conversation([sig("demand", "orthopaedic_need")])
        withref = score_conversation([
            sig("demand", "orthopaedic_need"),
            sig("intent", "referral_intent"),
        ])
        # referral is a positive intent (+12) plus the NPS bonus (+10).
        self.assertGreater(withref["score"], base["score"] + 12)
        self.assertEqual(withref["components"]["advocacy"], 1)

    def test_purchase_intent_bonus(self):
        generic = score_conversation([sig("intent", "consider_later")])
        buying = score_conversation([sig("intent", "purchase_intent")])
        self.assertGreater(buying["score"], generic["score"])

    def test_discovery_depth_counts_distinct_demands(self):
        out = score_conversation([
            sig("demand", "orthopaedic_need"),
            sig("demand", "cooling_need"),
            sig("demand", "cooling_need"),
            sig("demand", "firmness_preference"),
        ])
        self.assertEqual(out["components"]["discovery_depth"], 3)

    def test_backwards_compatible_shape(self):
        out = score_conversation([])
        for key in ("score", "rating", "outcome", "signal_counts", "components"):
            self.assertIn(key, out)
        self.assertEqual(out["score"], 50.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
