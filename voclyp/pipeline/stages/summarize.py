"""Summarization stage — structured fields + transcript-grounded summary."""
from __future__ import annotations

from ..base import Stage
from ..registry import register
from ...contracts import ConversationContext


class TaxonomySummarization(Stage):
    name = "summarization"
    version = "taxonomy-transcript-1.0"

    def __init__(self, taxonomy: dict):
        self.taxonomy = taxonomy

    def _matching(self, ctx, spec):
        return [
            s for s in ctx.signals
            if s.type == spec["signal"]
            and ("subtype" not in spec or s.subtype == spec["subtype"])
        ]

    def _transcript_summary(self, ctx: ConversationContext) -> str:
        if not ctx.utterances:
            return "No speech was detected in this recording."

        customer_lines = [
            (u.normalized_text or u.text or "").strip()
            for u in ctx.utterances
            if u.speaker == "customer" and (u.normalized_text or u.text or "").strip()
        ]
        agent_lines = [
            (u.normalized_text or u.text or "").strip()
            for u in ctx.utterances
            if u.speaker == "agent" and (u.normalized_text or u.text or "").strip()
        ]

        parts = [
            f"Visit transcript: {len(ctx.utterances)} turns"
            f" ({len(agent_lines)} from sales rep, {len(customer_lines)} from customer).",
        ]

        if customer_lines:
            wants = " ".join(customer_lines[:4])
            if len(wants) > 320:
                wants = wants[:317] + "…"
            parts.append(f"Customer said: {wants}")

        demands = [s.quote for s in ctx.signals if s.type == "demand"]
        if demands:
            parts.append("Needs identified: " + "; ".join(demands[:3]))

        objections = [s.quote for s in ctx.signals if s.type in ("objection", "price_reaction")]
        if objections:
            parts.append("Concerns: " + "; ".join(objections[:2]))

        if ctx.signals:
            by_type: dict = {}
            for s in ctx.signals:
                by_type.setdefault(s.type, set()).add(s.subtype)
            sig_part = ", ".join(
                f"{len([x for x in ctx.signals if x.type == t])} {t.replace('_', ' ')}"
                for t in sorted(by_type)
            )
            parts.append(f"Signals: {sig_part}.")
        elif not customer_lines:
            parts.append("No clear product signals — the conversation may have been too short or noisy.")

        langs = "/".join(ctx.detected_languages) or "hi"
        parts.append(f"Language: {langs}.")
        return " ".join(parts)

    def run(self, ctx: ConversationContext) -> None:
        fields: dict = {}
        for spec in self.taxonomy["summary_fields"]:
            matches = self._matching(ctx, spec)
            if spec["from"] == "signal_count":
                fields[spec["name"]] = len(matches)
            elif spec["from"] == "signal_present":
                fields[spec["name"]] = bool(matches)
            elif spec["from"] == "signal_quotes":
                fields[spec["name"]] = [s.quote for s in matches]
        ctx.summary_fields = fields
        ctx.summary_text = self._transcript_summary(ctx)


@register("summarization", "taxonomy")
def _create(options, services):
    return TaxonomySummarization(services["taxonomy"])
