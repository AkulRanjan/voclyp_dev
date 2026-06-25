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
from ...providers.sarvam import SarvamClient, SarvamError

_INDIC = re.compile(
    r"[\u0900-\u097F"   # Devanagari (Hindi, Marathi, …)
    r"\u0A80-\u0AFF"     # Gujarati
    r"\u0980-\u09FF"     # Bengali
    r"\u0B80-\u0BFF"     # Tamil
    r"\u0C00-\u0C7F"     # Telugu
    r"\u0C80-\u0CFF"     # Kannada
    r"\u0D00-\u0D7F"     # Malayalam
    r"\u0A00-\u0A7F"     # Gurmukhi (Punjabi)
    r"]"
)
_LATIN = re.compile(r"[A-Za-z]")

# Map the first Indic script we see to an explicit Sarvam source language code,
# so we never depend on auto-detection (which 422s on short/ambiguous text).
_SCRIPT_TO_LANG = [
    (re.compile(r"[\u0A80-\u0AFF]"), "gu-IN"),  # Gujarati
    (re.compile(r"[\u0980-\u09FF]"), "bn-IN"),  # Bengali
    (re.compile(r"[\u0B80-\u0BFF]"), "ta-IN"),  # Tamil
    (re.compile(r"[\u0C00-\u0C7F]"), "te-IN"),  # Telugu
    (re.compile(r"[\u0C80-\u0CFF]"), "kn-IN"),  # Kannada
    (re.compile(r"[\u0D00-\u0D7F]"), "ml-IN"),  # Malayalam
    (re.compile(r"[\u0A00-\u0A7F]"), "pa-IN"),  # Gurmukhi (Punjabi)
    (re.compile(r"[\u0900-\u097F]"), "hi-IN"),  # Devanagari (Hindi default)
]


def _guess_source_language(text: str) -> str:
    for pattern, code in _SCRIPT_TO_LANG:
        if pattern.search(text):
            return code
    return "hi-IN"


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
            text = utt.text or ""
            has_indic = bool(_INDIC.search(text))
            has_latin = bool(_LATIN.search(text))

            if not has_indic:
                # already in the target language: no API call, no credits
                utt.normalized_text = text
                if short(target) not in utt.languages:
                    utt.languages = utt.languages or [short(target)]
                note(short(target))
                continue

            translated, source = self._translate_resilient(ctx, text)
            # Translation is normalization, not a hard requirement: on failure we
            # keep the original text so a flaky translate call never sinks the
            # whole analysis (the signal/summary stages still run).
            utt.normalized_text = (translated or text or "").strip()
            langs = [lang for lang in (short(source),) if lang]
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

    def _translate_resilient(self, ctx: ConversationContext, text: str) -> tuple[str, str]:
        """Translate one utterance; never raise. Returns (text, source_lang).

        Uses an explicit source language guessed from the script first (Sarvam
        422s on `auto` when text is short/ambiguous), falls back to auto-detect,
        and finally degrades to the original text so the pipeline keeps running.
        """
        target = self.languages["normalize_to"]
        guessed = _guess_source_language(text)
        for source in (guessed, "auto"):
            try:
                resp = self.client.translate(text, source=source, target=target)
            except SarvamError:
                continue
            ctx.provider_usage["sarvam:translate"] = (
                ctx.provider_usage.get("sarvam:translate", 0) + 1
            )
            translated = (resp.get("translated_text") or "").strip()
            detected_src = resp.get("source_language_code") or (
                guessed if source != "auto" else ""
            )
            return translated or text, detected_src
        # Both attempts failed — keep the original text, attribute to the guess.
        ctx.provider_usage["sarvam:translate-skipped"] = (
            ctx.provider_usage.get("sarvam:translate-skipped", 0) + 1
        )
        return text, guessed


@register("lang_id_translation", "sarvam")
def _create(options, services):
    settings = services.get("settings") or load_settings()
    return SarvamTranslate(
        SarvamClient(settings.sarvam_api_key),
        services.get("languages"),
    )
