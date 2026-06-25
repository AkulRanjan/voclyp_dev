"""Ephemeral-audio erasure worker (DPDP 2-hour promise).

Every conversation gets an ``erase_after`` deadline at ingestion
(created_at + 2h by default). This worker scans for due rows, deletes the raw
audio object from S3, stamps ``erased_at``, moves the row to ``erased``, and
writes a tamper-evident audit line. Transcripts/insights (already de-identified
working artifacts) are retained per policy; only the raw voice is destroyed.
"""
from __future__ import annotations

from ...contracts import utcnow
from ..routing import _sink
from ..store import IllegalTransition


class ErasureWorker:
    def __init__(self, settings, store, audio_store, audit_sink: bool = True):
        self.settings = settings
        self.store = store
        self.audio_store = audio_store
        self.audit_sink = audit_sink

    def run_once(self, limit: int = 100, now_iso: str | None = None) -> dict:
        now = now_iso or utcnow()
        due = self.store.due_erasures(now, limit=limit)
        erased, errors = 0, 0
        for conv in due:
            try:
                self.audio_store.delete(conv["s3_key"])
                # Normal end-of-life is dispatching -> purged. A conversation
                # that never reached dispatching can't legally go to 'purged',
                # so it is force-purged (error_purged) instead.
                try:
                    self.store.set_state(conv["id"], "purged", erased_at=utcnow())
                except IllegalTransition:
                    self.store.mark_error_purged(
                        conv["id"], detail="erased before reaching dispatching")
                self._audit(conv, ok=True, detail="raw audio destroyed")
                erased += 1
            except Exception as exc:
                self._audit(conv, ok=False, detail=f"{type(exc).__name__}: {exc}")
                errors += 1
        return {"scanned": len(due), "erased": erased, "errors": errors}

    def _audit(self, conv: dict, ok: bool, detail: str) -> None:
        if not self.audit_sink:
            return
        _sink.record(self.settings.local_path, "erasure", {
            "conversation_id": conv["id"],
            "tenant_id": conv["tenant_id"],
            "s3_bucket": conv["s3_bucket"],
            "s3_key": conv["s3_key"],
            "erase_after": conv["erase_after"],
            "ok": ok,
            "detail": detail,
        })
