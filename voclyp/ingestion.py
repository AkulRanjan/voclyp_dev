"""Ingestion service: validate the upload, persist the audio, enqueue work.

Guardrails enforced here, before anything is stored:
- Consent is a hard precondition — no consent, no bytes written.
- Upload size and metadata field lengths are capped (defense against abuse
  and queue poisoning).
- Audio is written through the AudioVault (encrypted at rest when a master
  key is configured) and lives only until the pipeline destroys it.
- Re-uploads are idempotent: field devices syncing after connectivity gaps
  may retry, and the same ``client_ref`` never creates a duplicate job.
- Long audio is split into ordered chunks before queueing so the pipeline
  works in manageable units. Phase-0 stand-in audio is text, so chunks split
  on utterance (line) boundaries — the analog of silence-based splitting for
  real audio.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from .audio.prepare import looks_like_audio
from .config import Settings
from .queueing import JobQueue
from .security import AudioVault
from .store import Store


class ConsentRequired(Exception):
    pass


class ValidationError(Exception):
    pass


class IngestionService:
    def __init__(self, store: Store, queue: JobQueue, audio_dir,
                 vault: AudioVault = None, settings: Settings = None):
        self.store = store
        self.queue = queue
        self.audio_dir = Path(audio_dir)
        self.vault = vault or AudioVault()
        self.settings = settings or Settings()

    def _chunk(self, audio_bytes: bytes) -> list:
        """Split large uploads. Text stubs split on newlines; binary audio on byte boundaries."""
        limit = self.settings.chunk_bytes
        if len(audio_bytes) <= limit:
            return [audio_bytes]
        if looks_like_audio(audio_bytes):
            chunks = []
            while audio_bytes:
                chunks.append(audio_bytes[:limit])
                audio_bytes = audio_bytes[limit:]
            return chunks
        chunks = []
        while audio_bytes:
            if len(audio_bytes) <= limit:
                chunks.append(audio_bytes)
                break
            split_at = audio_bytes.rfind(b"\n", 0, limit) + 1 or limit
            chunks.append(audio_bytes[:split_at])
            audio_bytes = audio_bytes[split_at:]
        return chunks

    def _field(self, metadata: dict, *path) -> str:
        value = metadata
        for key in path:
            value = (value or {}).get(key, "")
        value = str(value or "")
        if len(value) > self.settings.max_metadata_field_len:
            raise ValidationError(f"metadata field '{'.'.join(path)}' too long")
        return value

    def submit(self, tenant_id: str, audio_bytes: bytes, metadata: dict) -> str:
        """Accept one field conversation; returns the conversation_id."""
        consent = metadata.get("consent") or {}
        if not consent.get("captured"):
            raise ConsentRequired("recording consent was not captured")
        if not audio_bytes:
            raise ValidationError("empty audio upload")
        if len(audio_bytes) > self.settings.max_upload_bytes:
            raise ValidationError(
                f"upload exceeds limit of {self.settings.max_upload_bytes} bytes"
            )
        industry = self.store.tenant_industry(tenant_id)
        if industry is None:
            raise ValidationError(f"unknown tenant '{tenant_id}'")

        agent_id = self._field(metadata, "agent_id")
        store_id = self._field(metadata, "store_id")
        customer_name = self._field(metadata, "consent", "customer_name")
        client_ref = self._field(metadata, "client_ref")

        if client_ref:
            existing = self.store.idempotency_get(tenant_id, client_ref)
            if existing:
                self.store.audit(tenant_id, existing, "duplicate_upload_ignored",
                                 f"client_ref={client_ref}")
                return existing

        conversation_id = uuid.uuid4().hex
        audio_paths = []
        for i, chunk in enumerate(self._chunk(audio_bytes)):
            path = self.audio_dir / tenant_id / f"{conversation_id}.part{i}.audio"
            self.vault.write(path, chunk)
            audio_paths.append(str(path))

        self.store.log_consent(tenant_id, conversation_id, agent_id, True)
        if client_ref:
            self.store.idempotency_set(tenant_id, client_ref, conversation_id)

        self.queue.enqueue(tenant_id, conversation_id, {
            "audio_paths": audio_paths,
            "industry": industry,
            "agent_id": agent_id,
            "store_id": store_id,
            "customer_name": customer_name,
        })
        self.store.audit(
            tenant_id, conversation_id, "ingested",
            f"agent={agent_id} store={store_id} bytes={len(audio_bytes)}"
            f" chunks={len(audio_paths)} encrypted_at_rest={self.vault.encrypted}",
        )
        return conversation_id
