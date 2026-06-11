"""Language ID + translation via Sarvam's translate API.

Normalizes every utterance into the working language declared by the language
policy (en-IN today) while keeping the original text alongside — the analysis
stages never need to understand each language natively.

Credit discipline: utterances that are already in the target language (no
Indic script present) are copied through without an API call. In code-mixed
Hindi-English field conversations this skips a large share of calls. Each
real call is metered into ctx.provider_usage.
"""
from __future__ import annotations

import re

from ..base import Stage
from ..registry import register
from ...config import load_settings
from ...contracts import ConversationContext
from ...languages import load_languages, short
from ...providers.sarvam import SarvamClient

_INDIC = re.compile(r"[ऀ-෿]")   # Devanagari through Sinhala block
_LATIN = re.compile(r"[A-Za-z]")


class SarvamTranslate(Stage):
    name = "lang_id_translation"
    version = "sarvam-translate-v1"

    def __init__(self, client: SarvamClient, languages: dict = None):
        self.client = client
        self.languages = languages or load_languages()

    def run(self, ctx: ConversationContext) -> None:
        target = self.languages["normalize_to"]
        detected: list = []

        def note(lang: str):
            if lang and lang not in detected:
                detected.append(lang)

        for utt in ctx.utterances:
            has_indic = bool(_INDIC.search(utt.text))
            has_latin = bool(_LATIN.search(utt.text))

            if not has_indic:
                # already in the target language: no API call, no credits
                utt.normalized_text = utt.text
                if short(target) not in utt.languages:
                    utt.languages = utt.languages or [short(target)]
                note(short(target))
                continue

            resp = self.client.translate(utt.text, source="auto", target=target)
            ctx.provider_usage["sarvam:translate"] = (
                ctx.provider_usage.get("sarvam:translate", 0) + 1
            )
            utt.normalized_text = (resp.get("translated_text") or utt.text).strip()
            source = short(resp.get("source_language_code") or "")
            langs = [lang for lang in (source,) if lang]
            if has_latin:  # code-mixed inside a single utterance
                langs.append(short(target))
            utt.languages = langs or utt.languages
            for lang in langs:
                note(lang)

        ctx.detected_languages = detected
        ctx.code_switching = (
            len(detected) > 1
            or any(len(u.languages) > 1 for u in ctx.utterances)
        )
        ctx.normalized_to = short(target)


@register("lang_id_translation", "sarvam")
def _create(options, services):
    settings = services.get("settings") or load_settings()
    return SarvamTranslate(
        SarvamClient(settings.sarvam_api_key),
        services.get("languages"),
    )
