"""Internal data model and the v1 insight document builder.

The JSON produced by ``build_insight`` is the system's only output contract;
its shape is pinned by contracts/insight-schema/v1/insight.schema.json.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Optional

SCHEMA_VERSION = "1.0"


def utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


@dataclass
class Utterance:
    text: str                      # original-language text (redacted in place)
    speaker: str = "unknown"       # agent | customer | unknown
    normalized_text: str = ""      # common working language (redacted in place)
    languages: list = field(default_factory=list)


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
    consent_captured: bool = False
    customer_name: str = ""        # from consent form; consumed by redaction, then cleared

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
        "languages": {
            "detected": ctx.detected_languages,
            "normalized_to": ctx.normalized_to,
            "code_switching": ctx.code_switching,
        },
        "speakers": {
            "count": len({u.speaker for u in ctx.utterances
                          if u.speaker != "unknown"}),
            "turns": len(ctx.utterances),
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
