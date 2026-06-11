"""ASR stage.

Phase-0 stub: the "audio" file is a UTF-8 text stand-in where each line is one
utterance, optionally prefixed ``AGENT:`` or ``CUSTOMER:`` (a hint the real
system would not have — diarization owns final speaker labels). It also does a
toy per-utterance language sniff using a small romanized-Hindi wordlist so the
code-switching path is exercised end to end.

Phase 2 replaces this class with a real Indic ASR behind the same Stage
interface; nothing else in the pipeline changes.
"""
from __future__ import annotations

import re

from ..base import Stage
from ..registry import register
from ...contracts import ConversationContext, Utterance
from ...security import AudioVault

_HINDI_WORDS = {
    "hai", "nahi", "nahin", "bahut", "kya", "mehenga", "chahiye", "abhi",
    "kal", "dukaan", "paisa", "zyada", "thoda", "accha", "theek", "wala",
    "purana", "mera", "mahine", "namaste", "ji", "tak", "pada",
}
_SPEAKER_PREFIX = re.compile(r"^(AGENT|CUSTOMER)\s*:\s*", re.IGNORECASE)


class StubASR(Stage):
    name = "asr"
    version = "stub-0.1"

    def __init__(self, vault: AudioVault = None):
        # Audio is encrypted at rest when a master key is configured; only
        # this stage ever decrypts it, in memory, moments before deletion.
        self.vault = vault or AudioVault()

    def run(self, ctx: ConversationContext) -> None:
        # Chunks are split on utterance boundaries by ingestion; concatenating
        # them in order reconstructs the full conversation.
        raw = b"".join(self.vault.read(p) for p in ctx.audio_paths).decode("utf-8")
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            speaker = "unknown"
            m = _SPEAKER_PREFIX.match(line)
            if m:
                speaker = m.group(1).lower()
                line = line[m.end():]

            words = re.findall(r"[a-zA-Z]+", line.lower())
            has_hi = any(w in _HINDI_WORDS for w in words)
            has_en = any(w not in _HINDI_WORDS for w in words)
            langs = [l for l, present in (("hi", has_hi), ("en", has_en)) if present]

            ctx.utterances.append(Utterance(text=line, speaker=speaker, languages=langs))


@register("asr", "stub")
def _create(options, services):
    return StubASR(services.get("vault"))
