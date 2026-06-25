"""Signal extraction — the brain of the pipeline.

Reads the cleaned, diarized, normalized conversation and pulls out structured
signals. It contains no industry logic of its own: every pattern it matches
comes from the merged taxonomy config it was constructed with.

Crucially, a keyword alone is not a signal. Real conversations are full of
questions and denials: the rep ASKS "aapko back pain hai?" and the customer
says "No"; the customer says "Non EMI" (declining EMI); the rep describes a
"warranty" as a benefit. Matching bare keywords turns all of these into false
customer needs/objections. So each match is gated by:

  * speaker  — a customer *need/intent/objection* must come from the customer;
               a *promise* from the rep. (Configurable per type; default below.)
  * negation — a keyword negated nearby ("no", "nahi", "non", "without", …) is
               not a signal.
  * question — a *demand* phrased as a question is the rep probing, not a need.
"""
from __future__ import annotations

import re

from ..base import Stage
from ..registry import register
from ...contracts import ConversationContext, Signal

# Which speaker a signal type legitimately comes from. Needs, intent and
# concerns are customer-side; promises are made by the rep. Anything not listed
# (or set to "any") is accepted from either speaker.
_DEFAULT_SPEAKER = {
    "demand": "customer",
    "intent": "customer",
    "objection": "customer",
    "price_reaction": "customer",
    "promise": "agent",
    "competitor_mention": "any",
}

# Negation only flips meaning for *wants/interest*: "no back pain" / "Non EMI" /
# "soft nahi chahiye" means the customer does NOT want it. For *objections* a
# negator usually reinforces the concern ("stock not selling", "doesn't last"),
# so we never suppress those.
_NEGATION_TYPES = {"demand", "intent", "price_reaction"}

# Negation cues (English + Hindi/Hinglish). Matched as whole words near the
# keyword. "non" catches "Non EMI"; "nahi/nahin" catch trailing Hindi negation.
_NEGATORS = {
    "no", "not", "never", "without", "non", "none", "cant", "cannot",
    "dont", "doesnt", "didnt", "wont", "nope",
    "nahi", "nahin", "nai", "mat", "bina", "nako",
}
_WORD = re.compile(r"[a-z']+")


def _strip_apostrophes(token: str) -> str:
    # "don't" -> "dont", "doesn't" -> "doesnt" so the negator set matches.
    return token.replace("'", "")


def _is_negated(haystack: str, phrase: str) -> bool:
    """True if a negator sits just before or shortly after the matched phrase.

    The window is asymmetric: English negates before the noun ("no back pain",
    "non EMI"), Hindi negates after the clause ("soft mattress nahi chahiye"),
    so we look a little before and a bit further after.
    """
    idx = haystack.find(phrase)
    if idx == -1:
        return False
    start = max(0, idx - 28)
    end = idx + len(phrase) + 36
    window = haystack[start:end]
    tokens = {_strip_apostrophes(t) for t in _WORD.findall(window)}
    return bool(tokens & _NEGATORS)


def _is_question(text: str) -> bool:
    if "?" in text:
        return True
    # Common interrogative openers (rep probing for needs).
    return bool(re.match(
        r"\s*(do|does|did|are|is|kya|kaisa|kitna|kaun|what|how|which)\b",
        text, re.IGNORECASE,
    ))


class TaxonomySignalExtraction(Stage):
    name = "signal_extraction"
    version = "taxonomy-match-0.2-speaker-negation"

    def __init__(self, taxonomy: dict):
        self.taxonomy = taxonomy

    def _expected_speaker(self, sig_type: str, spec: dict) -> str:
        # Taxonomy may override per type; otherwise use the universal default.
        return (spec.get("speaker") or _DEFAULT_SPEAKER.get(sig_type, "any")).lower()

    def run(self, ctx: ConversationContext) -> None:
        ctx.taxonomy_version = self.taxonomy["version"]
        seen = set()
        for turn, utt in enumerate(ctx.utterances):
            raw = (utt.normalized_text or utt.text or "")
            haystack = raw.lower()
            speaker = utt.speaker or "unknown"
            is_question = _is_question(raw)

            for sig_type, spec in self.taxonomy["signals"].items():
                expected = self._expected_speaker(sig_type, spec)
                # Speaker gate: a customer need can't come from the rep's mouth,
                # and a rep promise can't come from the customer.
                if expected != "any" and speaker != expected:
                    continue
                # A need phrased as a question is probing, not a stated need.
                if is_question and sig_type in ("demand", "intent"):
                    continue
                # A bare 1-2 word line ("Natural Cooling", "Boy", "Hmm") is an
                # echo/acknowledgement, not a stated need — don't treat it as a
                # demand/intent.
                if sig_type in ("demand", "intent") and len(_WORD.findall(haystack)) < 3:
                    continue

                for pattern in spec["patterns"]:
                    phrases = [p.lower() for p in pattern.get("any", [])]
                    matched = next((p for p in phrases if p in haystack), None)
                    if matched is None:
                        continue
                    # Negation gate (wants/interest only): "no back pain",
                    # "Non EMI", "soft nahi chahiye".
                    if sig_type in _NEGATION_TYPES and _is_negated(haystack, matched):
                        continue
                    key = (sig_type, pattern["subtype"], turn)
                    if key in seen:
                        continue
                    seen.add(key)
                    ctx.signals.append(Signal(
                        type=sig_type,
                        subtype=pattern["subtype"],
                        speaker=speaker,
                        quote=utt.normalized_text or utt.text or "",
                        turn=turn,
                        confidence=0.7,
                    ))


@register("signal_extraction", "taxonomy")
def _create(options, services):
    return TaxonomySignalExtraction(services["taxonomy"])
