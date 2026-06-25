"""Bedrock Claude 3.5 Sonnet extraction schema (JSON Schema Draft 2020-12).

This is the exact ``toolConfig.tools[].toolSpec.inputSchema.json`` passed to the
Bedrock Converse API. Forcing ``toolChoice`` to this single tool makes Claude
emit constrained JSON (no prose, no markdown fences) that already conforms to
the schema, so the worker can trust the shape and focus on confidence gating.
"""
from __future__ import annotations

TOOL_NAME = "extract_showroom_intel"

EXTRACTION_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ShowroomConversationExtraction",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "posture_issues", "pricing_objections", "competitor_mentions",
        "emi_commitments", "next_best_action", "overall_confidence",
    ],
    "properties": {
        "posture_issues": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["issue", "evidence_quote", "confidence"],
                "properties": {
                    "issue": {"type": "string", "enum": [
                        "lower_back_pain", "neck_pain", "shoulder_pain",
                        "spinal_alignment", "stiffness", "hip_pressure",
                        "general_discomfort", "sleep_posture", "other"]},
                    "body_region": {"type": "string"},
                    "evidence_quote": {"type": "string", "maxLength": 500},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
        "pricing_objections": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["objection_type", "evidence_quote", "confidence"],
                "properties": {
                    "objection_type": {"type": "string", "enum": [
                        "too_expensive", "budget_constraint", "needs_discount",
                        "comparing_prices", "emi_concern", "value_doubt",
                        "spouse_approval", "other"]},
                    "amount_inr": {"type": ["number", "null"], "minimum": 0},
                    "evidence_quote": {"type": "string", "maxLength": 500},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
        "competitor_mentions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["brand", "sentiment", "confidence"],
                "properties": {
                    "brand": {"type": "string"},
                    "context": {"type": "string", "maxLength": 500},
                    "sentiment": {"type": "string",
                                  "enum": ["positive", "neutral", "negative"]},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
        "emi_commitments": {
            "type": "array",
            "description": ("Any stated financing figure; presence forces human "
                            "verification before WhatsApp."),
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["monthly_amount_inr", "tenure_months", "confidence"],
                "properties": {
                    "product": {"type": "string"},
                    "monthly_amount_inr": {"type": "number", "minimum": 0},
                    "tenure_months": {"type": "integer", "minimum": 0},
                    "interest_rate_pct": {"type": ["number", "null"], "minimum": 0},
                    "evidence_quote": {"type": "string", "maxLength": 500},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
        "next_best_action": {
            "type": "object",
            "additionalProperties": False,
            "required": ["action", "channel", "talking_point", "confidence"],
            "properties": {
                "action": {"type": "string", "maxLength": 280},
                "channel": {"type": "string",
                            "enum": ["call", "whatsapp", "in_person", "email"]},
                "recommended_product": {"type": "string"},
                "talking_point": {"type": "string", "maxLength": 280},
                "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
        },
        "overall_confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}


def build_tool_config() -> dict:
    """The Converse ``toolConfig`` that forces constrained decoding into the
    extraction schema."""
    return {
        "tools": [{
            "toolSpec": {
                "name": TOOL_NAME,
                "description": (
                    "Extract structured sales intelligence from a furniture/"
                    "mattress showroom conversation transcript. Only use direct "
                    "evidence from the transcript; never invent figures."),
                "inputSchema": {"json": EXTRACTION_SCHEMA},
            },
        }],
        "toolChoice": {"tool": {"name": TOOL_NAME}},
    }


SYSTEM_PROMPT = (
    "You are a sales-intelligence analyst for an Indian furniture and mattress "
    "retailer. Read the English transcript of a showroom conversation and call "
    "the extract_showroom_intel tool. Rules: (1) Quote only words actually said. "
    "(2) Never fabricate EMI/financing numbers — if a figure is uncertain, lower "
    "its confidence. (3) Set overall_confidence to reflect transcript clarity. "
    "(4) Return empty arrays when nothing applies."
)
