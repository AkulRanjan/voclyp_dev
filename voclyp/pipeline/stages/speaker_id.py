"""Speaker identification: verify the agent voice against the rep's voiceprint.

Runs after ASR/diarization (which separate the speakers) and BEFORE audio
deletion (it is the last stage that needs the waveform). It compares the
conversation audio to the sales rep's enrolled voiceprint so the diarized
"agent" turns can be confidently attributed to a named rep — the same identity
the manager dashboards and the rep's own post-visit insight are keyed on.

The enrolled vector arrives on the context (the worker loads it for the
conversation's agent_id); when no rep is enrolled the stage is a no-op, so the
pipeline degrades gracefully to positional diarization.
"""
from __future__ import annotations

from ..base import Stage
from ..registry import register
from ...security import AudioVault
from ...voice import embed, similarity


class VoiceprintSpeakerID(Stage):
    name = "speaker_id"
    version = "voiceprint-v1"

    def __init__(self, vault: AudioVault, threshold: float = 0.7):
        self.vault = vault
        self.threshold = threshold

    def run(self, ctx) -> None:
        if not ctx.agent_voiceprint or not ctx.audio_paths:
            return
        # Verification is done in sarvam_batch + cleanup_conversation when
        # diarized timestamps exist; keep a full-clip check as fallback.
        if ctx.agent_voice_verified:
            return
        try:
            audio = b"".join(self.vault.read(p) for p in ctx.audio_paths)
        except Exception:
            return
        if not audio:
            return
        result = embed(audio)
        sim = similarity(result["vector"], ctx.agent_voiceprint)
        ctx.agent_voice_similarity = round(sim, 3)
        ctx.agent_voice_verified = sim >= self.threshold


@register("speaker_id", "voiceprint")
def _create(options, services):
    return VoiceprintSpeakerID(
        services.get("vault") or AudioVault(),
        threshold=options.get("threshold", 0.7),
    )
