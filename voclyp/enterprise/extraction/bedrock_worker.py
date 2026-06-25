"""AWS Bedrock Claude 3.5 Sonnet extraction worker.

Consumes ``transcript.ready``, runs the English transcript through Claude via
the Bedrock Converse API with a forced tool call (constrained decoding into
extraction/schema.py), then applies confidence/EMI gating (Self-Correction 2):

- If any ``emi_commitments`` are present, the conversation is flagged
  ``requires_human_verification`` — financing figures must never be auto-sent.
- If ``overall_confidence`` is below the configured threshold, it is likewise
  flagged for a quick human check.

Emits ``insight.extracted``. With no AWS Bedrock credentials it falls back to a
deterministic keyword-based extractor so the pipeline still produces a
schema-shaped result offline.
"""
from __future__ import annotations

import re

from ..events import topics
from .schema import SYSTEM_PROMPT, TOOL_NAME, build_tool_config


class BedrockExtractor:
    topic = topics.TRANSCRIPT_READY

    def __init__(self, settings, store, bus, client=None):
        self.settings = settings
        self.store = store
        self.bus = bus
        self.client = client  # boto3 bedrock-runtime | None (None => mock)

    def handle(self, event: dict) -> None:
        value = event.get("value", event)
        conversation_id = value["conversation_id"]
        conv = self.store.get_conversation(conversation_id)
        if not conv:
            return
        self.store.set_state(conversation_id, "extracting")
        try:
            transcript = conv.get("transcript_english") or conv.get("transcript_codemix") or ""
            extraction = self.extract(transcript)
            confidence = float(extraction.get("overall_confidence") or 0.0)
            requires_verification = (
                bool(extraction.get("emi_commitments"))
                or confidence < self.settings.confidence_threshold
            )
            # data update only; the state advances to 'dispatching' in routing
            self.store.update_conversation(
                conversation_id,
                extraction=extraction,
                extraction_confidence=confidence,
                requires_human_verification=requires_verification,
            )
            self.bus.produce(topics.INSIGHT_EXTRACTED, {
                "conversation_id": conversation_id,
                "tenant_id": conv["tenant_id"],
                "requires_human_verification": requires_verification,
            }, key=conversation_id)
        except Exception as exc:
            self.store.update_conversation(
                conversation_id,
                error_detail=f"extract: {type(exc).__name__}: {exc}"[:480])

    # -- extraction ------------------------------------------------------------
    def extract(self, transcript: str) -> dict:
        if self.client is None:
            return _heuristic_extraction(transcript)
        return self._extract_bedrock(transcript)

    def _extract_bedrock(self, transcript: str) -> dict:  # pragma: no cover - AWS
        resp = self.client.converse(
            modelId=self.settings.bedrock_model_id,
            system=[{"text": SYSTEM_PROMPT}],
            messages=[{"role": "user", "content": [{"text":
                "Transcript:\n\n" + transcript}]}],
            toolConfig=build_tool_config(),
            inferenceConfig={"maxTokens": 2000, "temperature": 0.0},
        )
        for block in resp["output"]["message"]["content"]:
            tool_use = block.get("toolUse")
            if tool_use and tool_use.get("name") == TOOL_NAME:
                return _normalize(tool_use["input"])
        raise RuntimeError("Bedrock returned no toolUse block")


# -- offline deterministic extractor -------------------------------------------

_POSTURE = [
    (re.compile(r"lower back|kamar|back hurt|back pain", re.I), "lower_back_pain", "lower back"),
    (re.compile(r"neck|gardan", re.I), "neck_pain", "neck"),
    (re.compile(r"shoulder|kandha", re.I), "shoulder_pain", "shoulder"),
    (re.compile(r"spine|spinal|alignment", re.I), "spinal_alignment", "spine"),
    (re.compile(r"stiff|akdan", re.I), "stiffness", ""),
    (re.compile(r"hip", re.I), "hip_pressure", "hip"),
]
_COMPETITORS = ["Kurlon", "Sleepwell", "Wakefit", "Duroflex", "SleepyCat",
                "Peps", "Springwel", "Nilkamal", "Centuary"]
_EMI = re.compile(
    r"([0-9][0-9,]{2,})\s*(?:rs\.?|rupees?|rupaye|rupay|₹|inr)?\s*"
    r"(?:per month|/month|monthly|per maheena|per mahina|mahine|a month|every month)",
    re.I)
_TENURE = re.compile(r"([0-9]{1,2})\s*(?:months?|month|mahine|maheena)", re.I)


def _sentence_around(text: str, match: re.Match, width: int = 160) -> str:
    start = max(0, match.start() - width // 2)
    end = min(len(text), match.end() + width // 2)
    return text[start:end].strip()[:500]


def _heuristic_extraction(transcript: str) -> dict:
    text = transcript or ""
    posture, seen = [], set()
    for pattern, issue, region in _POSTURE:
        m = pattern.search(text)
        if m and issue not in seen:
            seen.add(issue)
            posture.append({
                "issue": issue, "body_region": region,
                "evidence_quote": _sentence_around(text, m),
                "confidence": 0.82,
            })

    pricing = []
    m = re.search(r"expensive|mehenga|costly|too much|zyada", text, re.I)
    if m:
        pricing.append({
            "objection_type": "too_expensive", "amount_inr": None,
            "evidence_quote": _sentence_around(text, m), "confidence": 0.78})
    m = re.search(r"emi|installment|kisht", text, re.I)
    if m:
        pricing.append({
            "objection_type": "emi_concern", "amount_inr": None,
            "evidence_quote": _sentence_around(text, m), "confidence": 0.7})
    m = re.search(r"discount|chhoot|kam kar", text, re.I)
    if m:
        pricing.append({
            "objection_type": "needs_discount", "amount_inr": None,
            "evidence_quote": _sentence_around(text, m), "confidence": 0.66})

    competitors = []
    for brand in _COMPETITORS:
        m = re.search(re.escape(brand), text, re.I)
        if m:
            competitors.append({
                "brand": brand, "context": _sentence_around(text, m),
                "sentiment": "neutral", "confidence": 0.75})

    emi = []
    m = _EMI.search(text)
    if m:
        amount = float(m.group(1).replace(",", ""))
        tenure_m = _TENURE.search(text)
        tenure = int(tenure_m.group(1)) if tenure_m else 0
        interest = 0.0 if re.search(r"zero interest|no interest|0%|bina byaj", text, re.I) else None
        emi.append({
            "product": "", "monthly_amount_inr": amount, "tenure_months": tenure,
            "interest_rate_pct": interest, "evidence_quote": _sentence_around(text, m),
            "confidence": 0.6})

    if pricing or emi:
        channel, action = "whatsapp", "Share EMI/pricing options and a tailored quote"
    elif posture:
        channel, action = "whatsapp", "Send orthopedic product recommendation with benefits"
    else:
        channel, action = "call", "Follow up to understand customer needs"
    next_best = {
        "action": action, "channel": channel,
        "recommended_product": "Orthopedic Memory Foam Mattress" if posture else "",
        "talking_point": "Address comfort/posture and clarify value for the price",
        "priority": "high" if (posture and pricing) else "medium",
        "confidence": 0.72,
    }

    signal_count = len(posture) + len(pricing) + len(competitors) + len(emi)
    overall = 0.45 if signal_count == 0 else min(0.9, 0.55 + 0.07 * signal_count)
    return _normalize({
        "posture_issues": posture,
        "pricing_objections": pricing,
        "competitor_mentions": competitors,
        "emi_commitments": emi,
        "next_best_action": next_best,
        "overall_confidence": round(overall, 2),
    })


def _normalize(extraction: dict) -> dict:
    """Guarantee all required top-level keys exist and arrays are lists."""
    out = dict(extraction or {})
    for key in ("posture_issues", "pricing_objections", "competitor_mentions",
                "emi_commitments"):
        if not isinstance(out.get(key), list):
            out[key] = []
    if not isinstance(out.get("next_best_action"), dict):
        out["next_best_action"] = {
            "action": "Follow up with the customer", "channel": "call",
            "talking_point": "Reconnect and clarify needs", "confidence": 0.4}
    try:
        out["overall_confidence"] = float(out.get("overall_confidence") or 0.0)
    except (TypeError, ValueError):
        out["overall_confidence"] = 0.0
    return out
