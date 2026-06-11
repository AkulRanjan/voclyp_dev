"""Real ASR via Sarvam Saarika — built for Indian languages and the
code-mixed Hindi-English speech VoClyp's field agents actually encounter.

Enabled per the language policy (configs/languages.json): with one enabled
language the code is pinned (cheaper, more accurate); with several, Saarika
auto-detects (``language_code="unknown"``). Adding languages later changes
that config, not this stage.

Every API call is metered into ctx.provider_usage so credit burn is visible
per conversation. Ingestion's chunking keeps each request within the API's
clip-length limits.
"""
from __future__ import annotations

import re

from ..base import Stage
from ..registry import register
from ...config import load_settings
from ...contracts import ConversationContext, Utterance
from ...languages import load_languages, short
from ...providers.sarvam import SarvamClient
from ...security import AudioVault

_SENTENCE_SPLIT = re.compile(r"(?<=[।.!?])\s+")


class SarvamASR(Stage):
    name = "asr"

    def __init__(self, client: SarvamClient, vault: AudioVault = None,
                 languages: dict = None, model: str = "saarika:v2.5"):
        self.client = client
        self.vault = vault or AudioVault()
        self.languages = languages or load_languages()
        self.model = model
        self.version = f"sarvam-{model}"

    def run(self, ctx: ConversationContext) -> None:
        enabled = [lang["code"] for lang in self.languages["enabled"]]
        language_code = enabled[0] if len(enabled) == 1 else "unknown"

        for path in ctx.audio_paths:
            audio = self.vault.read(path)
            resp = self.client.speech_to_text(
                audio, model=self.model, language_code=language_code
            )
            ctx.provider_usage["sarvam:speech-to-text"] = (
                ctx.provider_usage.get("sarvam:speech-to-text", 0) + 1
            )
            detected = short(resp.get("language_code") or "")
            transcript = (resp.get("transcript") or "").strip()
            for sentence in _SENTENCE_SPLIT.split(transcript):
                sentence = sentence.strip()
                if sentence:
                    ctx.utterances.append(Utterance(
                        text=sentence,
                        languages=[detected] if detected else [],
                    ))


@register("asr", "sarvam")
def _create(options, services):
    settings = services.get("settings") or load_settings()
    return SarvamASR(
        SarvamClient(settings.sarvam_api_key),
        services.get("vault"),
        services.get("languages"),
        model=options.get("model", "saarika:v2.5"),
    )
