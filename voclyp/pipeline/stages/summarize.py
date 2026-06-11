"""Summarization stage.

Produces a per-conversation summary plus structured fields whose names and
filling rules are declared by the taxonomy config — the industry shapes the
output without this code knowing anything about the industry.

Field rules: ``signal_count`` (how many), ``signal_present`` (boolean),
``signal_quotes`` (the matched quotes), each optionally narrowed by subtype.
"""
from __future__ import annotations

from ..base import Stage
from ..registry import register
from ...contracts import ConversationContext


class TaxonomySummarization(Stage):
    name = "summarization"
    version = "taxonomy-fields-0.1"

    def __init__(self, taxonomy: dict):
        self.taxonomy = taxonomy

    def _matching(self, ctx, spec):
        return [
            s for s in ctx.signals
            if s.type == spec["signal"]
            and ("subtype" not in spec or s.subtype == spec["subtype"])
        ]

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

        by_type: dict = {}
        for s in ctx.signals:
            by_type.setdefault(s.type, []).append(s)
        parts = [
            f"{len(sigs)} {t.replace('_', ' ')}(s): "
            + "; ".join(sorted({s.subtype for s in sigs}))
            for t, sigs in sorted(by_type.items())
        ]
        ctx.summary_text = (
            f"{ctx.industry.upper()} field visit, {len(ctx.utterances)} turns, "
            f"languages {'/'.join(ctx.detected_languages) or 'unknown'}"
            f"{' (code-switching)' if ctx.code_switching else ''}. "
            + (" | ".join(parts) if parts else "No notable signals detected.")
        )


@register("summarization", "taxonomy")
def _create(options, services):
    return TaxonomySummarization(services["taxonomy"])
