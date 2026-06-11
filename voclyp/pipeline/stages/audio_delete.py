"""Audio deletion stage — real, not a stub.

The privacy promise is enforced inside the pipeline itself: once transcription
and redaction are done, the raw audio is destroyed before analysis ever runs.
The deletion timestamp lands in the insight document's audit block, and the
worker writes the matching audit-log entry so the deletion can be proven.
"""
from __future__ import annotations

from ..base import Stage
from ..registry import register
from ...contracts import ConversationContext, utcnow
from ...security import AudioVault


class AudioDeletion(Stage):
    name = "audio_deletion"
    version = "1.1"

    def __init__(self, vault: AudioVault = None):
        self.vault = vault or AudioVault()

    def run(self, ctx: ConversationContext) -> None:
        # Vault deletion overwrites with random bytes before unlinking.
        for path in ctx.audio_paths:
            self.vault.delete(path)
        ctx.audio_deleted_at = utcnow()


@register("audio_deletion", "vault")
def _create(options, services):
    return AudioDeletion(services.get("vault"))
