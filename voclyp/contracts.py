"""Internal data model and the v1 insight document builder.

The JSON produced by ``build_insight`` is the system's only output contract;
its shape is pinned by contracts/insight-schema/v1/insight.schema.json.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Optional

from .scoring import score_conversation

SCHEMA_VERSION = "1.0"


def utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


@dataclass
class Utterance:
    text: str                      # original-language text (redacted in place)
    speaker: str = "unknown"       # agent | customer | unknown
    normalized_text: str = ""      # common working language (redacted in place)
    languages: list = field(default_factory=list)
    speaker_id: str = ""           # raw diarization id from ASR (e.g. "0", "1")
    start_time: float = 0.0
    end_time: float = 0.0


@dataclass
class Signal:
    type: str
    subtype: str
    speaker: str
    quote: str
    turn: int
    confidence: float


@dataclass
class ConversationContext:
    """Mutable state that flows through the pipeline stages."""

    tenant_id: str
    conversation_id: str
    industry: str
    audio_paths: list                  # one or more chunks, in order
    agent_id: str = ""
    store_id: str = ""             # which store this conversation belongs to
    consent_captured: bool = False
    customer_name: str = ""        # from consent form; consumed by redaction, then cleared

    # Speaker identity (set by the speaker_id stage from the rep's enrolled
    # voiceprint). rep_name labels the agent turns; the verification fields
    # record whether the agent voice matched the enrolled profile.
    rep_name: str = ""
    agent_voiceprint: list = field(default_factory=list)
    agent_voice_similarity: Optional[float] = None
    agent_voice_verified: bool = False

    utterances: list = field(default_factory=list)
    detected_languages: list = field(default_factory=list)
    code_switching: bool = False
    normalized_to: str = "en"
    pii_redactions: dict = field(default_factory=dict)
    signals: list = field(default_factory=list)
    summary_text: str = ""
    summary_fields: dict = field(default_factory=dict)

    audio_deleted_at: Optional[str] = None
    stage_versions: dict = field(default_factory=dict)
    stage_timings_ms: dict = field(default_factory=dict)  # MLOps metrics, not part of the insight doc
    provider_usage: dict = field(default_factory=dict)    # external API calls (credit metering)
    taxonomy_version: str = ""


def build_insight(ctx: ConversationContext) -> dict:
    """Assemble the schema-v1 insight document from a finished context."""
    return {
        "schema_version": SCHEMA_VERSION,
        "tenant_id": ctx.tenant_id,
        "conversation_id": ctx.conversation_id,
        "industry": ctx.industry,
        "agent_id": ctx.agent_id,
        "store_id": ctx.store_id,
        "languages": {
            "detected": ctx.detected_languages,
            "normalized_to": ctx.normalized_to,
            "code_switching": ctx.code_switching,
        },
        "speakers": {
            "count": len({u.speaker for u in ctx.utterances
                          if u.speaker != "unknown"}),
            "turns": len(ctx.utterances),
            # display labels for the diarized speaker tokens: the rep is named
            # from the enrolled voiceprint; customers stay de-identified.
            "names": {"agent": ctx.rep_name or "Sales rep", "customer": "Customer"},
            "agent_voice_verified": ctx.agent_voice_verified,
            "agent_voice_similarity": ctx.agent_voice_similarity,
        },
        # Redacted by the PII stage before the audio was destroyed; this is
        # the only surviving record of what was said.
        "transcript": [
            {
                "turn": i,
                "speaker": u.speaker,
                "text": u.text,
                "normalized_text": u.normalized_text or u.text,
                "languages": u.languages,
                **({"start_time": u.start_time, "end_time": u.end_time}
                   if u.end_time > u.start_time else {}),
            }
            for i, u in enumerate(ctx.utterances)
        ],
        "signals": [
            {
                "type": s.type,
                "subtype": s.subtype,
                "speaker": s.speaker,
                "quote": s.quote,
                "turn": s.turn,
                "confidence": s.confidence,
            }
            for s in ctx.signals
        ],
        # Deterministic, explainable score over the extracted signals; the
        # comparable measure every dashboard and ranking aggregates on.
        "scoring": score_conversation(ctx.signals),
        "summary": {"text": ctx.summary_text, "fields": ctx.summary_fields},
        "privacy": {
            "consent_captured": ctx.consent_captured,
            "pii_redactions": ctx.pii_redactions,
        },
        "audit": {
            "audio_deleted_at": ctx.audio_deleted_at,
            "stage_versions": ctx.stage_versions,
            "taxonomy_version": ctx.taxonomy_version,
        },
        "created_at": utcnow(),
    }
