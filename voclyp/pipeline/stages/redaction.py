"""PII redaction stage.

Runs before any analysis, deliberately: sensitive identifiers are stripped
early so signal extraction and summarization never see them, and the raw audio
can be destroyed right after this stage. Redacts both the original and the
normalized text in place and counts redactions by type.
"""
from __future__ import annotations

import re

from ..base import Stage
from ..registry import register
from ...contracts import ConversationContext

# Order matters: longer identifiers first so e.g. a 12-digit Aadhaar is
# redacted whole rather than partially matched as a 10-digit phone number.
_PATTERNS = {
    "aadhaar": re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"),
    "pan": re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
    "phone": re.compile(r"(?:\+91[\s-]?)?\d{5}[\s-]?\d{5}\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"),
}


class RegexRedaction(Stage):
    name = "pii_redaction"
    version = "regex-0.1"

    def run(self, ctx: ConversationContext) -> None:
        counts: dict = {}
        name_re = None
        if ctx.customer_name:
            name_re = re.compile(re.escape(ctx.customer_name), re.IGNORECASE)

        for utt in ctx.utterances:
            for attr in ("text", "normalized_text"):
                value = getattr(utt, attr)
                for pii_type, pattern in _PATTERNS.items():
                    value, n = pattern.subn(f"[REDACTED:{pii_type.upper()}]", value)
                    if attr == "text" and n:  # count once, not per variant
                        counts[pii_type] = counts.get(pii_type, 0) + n
                if name_re:
                    value, n = name_re.subn("[REDACTED:NAME]", value)
                    if attr == "text" and n:
                        counts["name"] = counts.get("name", 0) + n
                setattr(utt, attr, value)

        ctx.pii_redactions = counts
        ctx.customer_name = ""  # consumed; the name does not travel further


@register("pii_redaction", "regex")
def _create(options, services):
    return RegexRedaction()
