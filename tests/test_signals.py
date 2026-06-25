"""Signal extraction must respect speaker, negation, and questions.

These cases are taken straight from a real demo where the keyword-only matcher
produced false "customer wants" (back pain, cooling, EMI) and a false warranty
objection. The rep ASKED about back pain; the customer said no; she chose
"Non EMI"; warranty was a rep benefit.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voclyp.contracts import ConversationContext, Utterance  # noqa: E402
from voclyp.pipeline.stages.signals import TaxonomySignalExtraction  # noqa: E402
from voclyp.taxonomy import load_taxonomy  # noqa: E402

TAX = load_taxonomy("sleep_company")


def run(utterances):
    ctx = ConversationContext(tenant_id="t", conversation_id="c",
                              industry="sleep_company", audio_paths=[])
    ctx.utterances = [
        Utterance(text=t, normalized_text=t, speaker=sp) for sp, t in utterances
    ]
    TaxonomySignalExtraction(TAX).run(ctx)
    return ctx.signals


def types(signals):
    return {(s.type, s.subtype) for s in signals}


class SpeakerNegationQuestion(unittest.TestCase):
    def test_rep_question_is_not_a_demand(self):
        sigs = run([("agent", "Okay. So first of all, do you have any back pain or any such illness?"),
                    ("customer", "No")])
        self.assertNotIn(("demand", "orthopaedic_need"), types(sigs))
        self.assertNotIn(("demand", "product_request"), types(sigs))

    def test_rep_describing_product_is_not_customer_need(self):
        sigs = run([("agent", "Ek toh woh orthopedic specially designed for people with back pain, spine pain.")])
        self.assertNotIn(("demand", "orthopaedic_need"), types(sigs))

    def test_rep_cooling_benefit_is_not_customer_need(self):
        sigs = run([("agent", "So it gives you natural cooling and asa garmi mein bhi it is proven to be cool.")])
        self.assertNotIn(("demand", "cooling_need"), types(sigs))

    def test_non_emi_is_not_emi_interest(self):
        sigs = run([("customer", "Non EMI. Okay. And")])
        self.assertNotIn(("intent", "emi_request"), types(sigs))
        self.assertNotIn(("price_reaction", "emi_interest"), types(sigs))

    def test_rep_warranty_benefit_is_not_objection(self):
        sigs = run([("agent", "Snowtech provides more warranty, 12 months of more warranty plus cooling.")])
        self.assertNotIn(("objection", "warranty_concern"), types(sigs))

    def test_negated_soft_is_suppressed(self):
        sigs = run([("customer", "Basically mere ko zyada soft mattress nahi chahiye")])
        self.assertNotIn(("demand", "firmness_preference"), types(sigs))

    def test_positive_customer_need_still_fires(self):
        # Control: an affirmative customer need must still be extracted.
        sigs = run([("customer", "mujhe back pain hai, orthopaedic mattress chahiye")])
        self.assertIn(("demand", "orthopaedic_need"), types(sigs))

    def test_customer_emi_interest_still_fires(self):
        sigs = run([("customer", "EMI option chahiye mujhe, monthly installment")])
        self.assertIn(("intent", "emi_request"), types(sigs))


if __name__ == "__main__":
    unittest.main(verbosity=2)
