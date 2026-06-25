"""Diarization stage: who spoke each turn, agent or customer.

This is what later lets the system attribute promises and objections to a
speaker. Phase-0 stub keeps speaker hints provided by the stand-in transcript
and alternates agent/customer for unlabeled turns (agents open the visit).
"""
from __future__ import annotations

from ..base import Stage
from ..registry import register
from ...contracts import ConversationContext


class StubDiarization(Stage):
    name = "diarization"
    version = "stub-0.1"

    def run(self, ctx: ConversationContext) -> None:
        # Sarvam batch already diarized — only alternate unlabeled turns.
        if any(u.speaker_id for u in ctx.utterances):
            for utt in ctx.utterances:
                if utt.speaker == "unknown" and not utt.speaker_id:
                    utt.speaker = "agent"
            return
        previous = "customer"
        for utt in ctx.utterances:
            if utt.speaker == "unknown":
                utt.speaker = "agent" if previous == "customer" else "customer"
            previous = utt.speaker


class PassthroughDiarization(Stage):
    """No-op when ASR + speaker cleanup already assigned speakers."""
    name = "diarization"
    version = "passthrough-1.0"

    def run(self, ctx: ConversationContext) -> None:
        for utt in ctx.utterances:
            if utt.speaker == "unknown":
                utt.speaker = "customer"


@register("diarization", "stub")
def _create_stub(options, services):
    return StubDiarization()


@register("diarization", "passthrough")
def _create_passthrough(options, services):
    return PassthroughDiarization()
