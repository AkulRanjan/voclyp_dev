"""Language ID + translation stage.

Normalizes every utterance into one common working language (English) so the
analysis stages never need to understand each language natively. The original
text is kept alongside the normalized version.

Phase-0 stub: aggregates the per-utterance language sniff from ASR and applies
a tiny romanized-Hindi word dictionary. Phase 2 swaps in real LID + MT.
"""
from __future__ import annotations

import re

from ..base import Stage
from ..registry import register
from ...contracts import ConversationContext

_HI_EN = {
    "mehenga": "expensive", "chahiye": "need", "nahi": "no", "nahin": "no",
    "bahut": "very", "accha": "good", "kal": "tomorrow", "zyada": "more",
    "thoda": "little", "paisa": "money", "dukaan": "shop", "purana": "old",
    "theek": "okay", "abhi": "now", "kya": "what", "hai": "is",
    "mera": "my", "mahine": "month",
}


class StubTranslation(Stage):
    name = "lang_id_translation"
    version = "stub-0.1"

    def run(self, ctx: ConversationContext) -> None:
        detected = []
        for utt in ctx.utterances:
            for lang in utt.languages:
                if lang not in detected:
                    detected.append(lang)
            utt.normalized_text = re.sub(
                r"[a-zA-Z]+",
                lambda m: _HI_EN.get(m.group(0).lower(), m.group(0)),
                utt.text,
            )
        ctx.detected_languages = detected
        ctx.code_switching = any(len(u.languages) > 1 for u in ctx.utterances)
        ctx.normalized_to = "en"


@register("lang_id_translation", "stub")
def _create(options, services):
    return StubTranslation()
