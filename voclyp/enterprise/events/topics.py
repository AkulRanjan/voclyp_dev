"""Kafka topic names for the event-driven pipeline.

Flow:
  audio.raw.uploaded  -> Sarvam ASR worker
  transcript.ready    -> Bedrock extraction worker
  insight.extracted   -> routing dispatcher
  routing.requested   -> (internal) per-channel fan-out

Names are stable contracts; additive-only within a major version.
"""
from __future__ import annotations

AUDIO_RAW_UPLOADED = "audio.raw.uploaded"
TRANSCRIPT_READY = "transcript.ready"
INSIGHT_EXTRACTED = "insight.extracted"
ROUTING_REQUESTED = "routing.requested"

ALL = (AUDIO_RAW_UPLOADED, TRANSCRIPT_READY, INSIGHT_EXTRACTED, ROUTING_REQUESTED)
