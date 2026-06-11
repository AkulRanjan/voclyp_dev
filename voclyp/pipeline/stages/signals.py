"""Signal extraction — the brain of the pipeline.

Reads the cleaned, diarized, normalized conversation and pulls out structured
signals. It contains no industry logic of its own: every pattern it matches
comes from the merged taxonomy config it was constructed with. Phase 2 swaps
the matching engine for an LLM, still driven by the same taxonomy packs.
"""
from __future__ import annotations

from ..base import Stage
from ..registry import register
from ...contracts import ConversationContext, Signal


class TaxonomySignalExtraction(Stage):
    name = "signal_extraction"
    version = "taxonomy-match-0.1"

    def __init__(self, taxonomy: dict):
        self.taxonomy = taxonomy

    def run(self, ctx: ConversationContext) -> None:
        ctx.taxonomy_version = self.taxonomy["version"]
        seen = set()
        for turn, utt in enumerate(ctx.utterances):
            haystack = utt.normalized_text.lower()
            for sig_type, spec in self.taxonomy["signals"].items():
                for pattern in spec["patterns"]:
                    if not any(phrase.lower() in haystack for phrase in pattern.get("any", [])):
                        continue
                    key = (sig_type, pattern["subtype"], turn)
                    if key in seen:
                        continue
                    seen.add(key)
                    ctx.signals.append(Signal(
                        type=sig_type,
                        subtype=pattern["subtype"],
                        speaker=utt.speaker,
                        quote=utt.normalized_text,
                        turn=turn,
                        confidence=0.7,
                    ))


@register("signal_extraction", "taxonomy")
def _create(options, services):
    return TaxonomySignalExtraction(services["taxonomy"])
