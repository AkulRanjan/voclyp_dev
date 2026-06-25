"""Tests for product-mention + anaphora resolution over a visit transcript."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voclyp.catalog import load_catalog  # noqa: E402
from voclyp.product_mentions import resolve_product_mentions  # noqa: E402

CATALOG = load_catalog("sleep_company")


def turns(*lines):
    """Build transcript turns from (speaker, text) tuples or plain strings."""
    out = []
    for ln in lines:
        if isinstance(ln, tuple):
            out.append({"speaker": ln[0], "text": ln[1]})
        else:
            out.append({"speaker": "customer", "text": ln})
    return out


class Resolution(unittest.TestCase):
    def test_mention_once_then_pronoun_binds(self):
        # "yeh ortho wala dekho" names ORTHO, then "ye" / "isme" refer back.
        res = resolve_product_mentions(CATALOG, turns(
            ("agent", "yeh ortho wala dekho sir"),
            ("customer", "ye kaisa hai? isme kya warranty milti hai"),
            ("customer", "iska price kya hai"),
        ))
        self.assertEqual(res["dominant_sku"], "SMART-ORTHO")
        m = res["mentions"]["SMART-ORTHO"]
        self.assertEqual(m["named"], 1)
        self.assertGreaterEqual(m["anaphora"], 2)

    def test_focus_switches_to_new_product(self):
        res = resolve_product_mentions(CATALOG, turns(
            ("agent", "yeh ortho wala dekhiye"),
            ("customer", " isme thoda hard lagta hai"),
            ("agent", "to ye snowtec wala try karo, cooling ke saath"),
            ("customer", " haan ye accha hai, isme kya emi hai"),
        ))
        # Both named once; SnowTec picks up the later anaphora and should lead.
        self.assertEqual(res["dominant_sku"], "SMART-LUXE-SNOWTEC")
        self.assertIn("SMART-ORTHO", res["mentions"])

    def test_pronoun_before_any_product_ignored(self):
        res = resolve_product_mentions(CATALOG, turns(
            ("customer", "ye kaisa hai, isme kya hai"),
            ("agent", "back pain ke liye kuch dikhao"),
        ))
        self.assertIsNone(res["dominant_sku"])
        self.assertEqual(res["mentions"], {})

    def test_multiple_in_one_line_last_is_focus(self):
        res = resolve_product_mentions(CATALOG, turns(
            ("agent", "ortho pro ya luxe pro dono dekho"),
            ("customer", "ye le lunga"),
        ))
        # Both named; the last-positioned (luxe pro) becomes current, so the
        # trailing "ye" attaches to it -> luxe pro leads.
        self.assertEqual(res["dominant_sku"], "SMART-LUXE-PRO")
        self.assertIn("SMART-ORTHO-PRO", res["mentions"])

    def test_royale_not_miscounted_as_luxe_pro(self):
        res = resolve_product_mentions(CATALOG, turns(
            ("agent", "ye luxe royale wala sabse premium hai"),
        ))
        self.assertEqual(res["dominant_sku"], "SMART-LUXE-ROYALE")
        self.assertNotIn("SMART-LUXE-PRO", res["mentions"])

    def test_ortho_alias_not_fired_by_orthopaedic_need(self):
        # "orthopaedic" is a NEED word, not naming the product -> no mention.
        res = resolve_product_mentions(CATALOG, turns(
            ("customer", "mujhe orthopaedic support chahiye back pain hai"),
        ))
        self.assertEqual(res["mentions"], {})

    def test_english_hindi_mix(self):
        res = resolve_product_mentions(CATALOG, turns(
            ("agent", "show the snowtec, it has cooling"),
            ("customer", "this one is good, what about iska emi"),
        ))
        self.assertEqual(res["dominant_sku"], "SMART-LUXE-SNOWTEC")

    def test_real_asr_spellings_resolve_all_three(self):
        # Real ASR spellings from the demo: "Ortho Pro", "Lux Pro", "Lux Pro Snowtech".
        res = resolve_product_mentions(CATALOG, turns(
            ("agent", "So there are three mattresses, the Ortho Pro and Lux Pro and the Lux Pro Snowtech."),
        ))
        skus = set(res["mentions"].keys())
        self.assertIn("SMART-ORTHO-PRO", skus)
        self.assertIn("SMART-LUXE-PRO", skus)
        self.assertIn("SMART-LUXE-SNOWTEC", skus)

    def test_customer_picks_lux_pro(self):
        res = resolve_product_mentions(CATALOG, turns(
            ("agent", "the Ortho Pro and Lux Pro and the Lux Pro Snowtech"),
            ("customer", "I will go for the previous one"),
            ("agent", "Okay, the 17k one, the Lux Pro mattress, yeah"),
            ("customer", "Lux Pro mattress like will it be custom made?"),
        ))
        self.assertEqual(res["dominant_sku"], "SMART-LUXE-PRO")


if __name__ == "__main__":
    unittest.main(verbosity=2)
