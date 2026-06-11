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
        previous = "customer"  # so the first unknown turn becomes "agent"
        for utt in ctx.utterances:
            if utt.speaker == "unknown":
                utt.speaker = "agent" if previous == "customer" else "customer"
            previous = utt.speaker


@register("diarization", "stub")
def _create(options, services):
    return StubDiarization()
