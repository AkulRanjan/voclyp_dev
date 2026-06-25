"""Enterprise ingestion — consent-first, then S3, then event.

DPDP ordering is non-negotiable and enforced here:

  1. Write the immutable consent record (aborts the whole request if it fails).
  2. Only then PUT the raw audio to S3 (tagged with the 2-hour erase deadline).
  3. Insert the conversation row referencing the consent log.
  4. Produce ``audio.raw.uploaded`` to kick off the async pipeline.

If consent recording fails for any reason, no audio ever leaves the device
boundary into cloud storage.
"""
from __future__ import annotations

import datetime
import uuid

from ..contracts import utcnow
from .consent.service import sha256_hex
from .events import topics
from .storage.s3 import audio_key


class EnterpriseIngestion:
    def __init__(self, settings, store, audio_store, bus, consent_service):
        self.settings = settings
        self.store = store
        self.audio_store = audio_store
        self.bus = bus
        self.consent = consent_service

    def ingest(self, *, tenant_id: str, agent_id: str, store_id: str,
               session_id: str, language: str, purposes: dict,
               device_fingerprint: dict, notice_text: str, audio: bytes,
               customer_phone: str = "", mock_transcript: str | None = None,
               extra_artifact: dict | None = None) -> dict:
        # 1. immutable consent BEFORE any audio reaches cloud storage
        consent = self.consent.record(
            tenant_id=tenant_id, agent_id=agent_id, session_id=session_id,
            language=language, purposes=purposes,
            device_fingerprint=device_fingerprint, notice_text=notice_text,
            customer_phone=customer_phone, extra_artifact=extra_artifact)

        conversation_id = uuid.uuid4().hex
        erase_after = (
            datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(seconds=self.settings.erase_after_seconds)
        ).isoformat()
        key = audio_key(tenant_id, conversation_id)

        # 2. create the conversation row in 'consent_logged' BEFORE the S3 PUT.
        #    If the upload then fails, the row is left non-terminal and the
        #    orphan sweep will force-purge it — no stranded S3 audio, no record
        #    gap.
        created_at = utcnow()
        self.store.insert_conversation({
            "id": conversation_id,
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "store_id": store_id,
            "consent_log_id": consent["consent_id"],
            "s3_bucket": self.audio_store.bucket,
            "s3_key": key,
            "audio_sha256": sha256_hex(audio),
            "state": "consent_logged",
            "detected_languages": [],
            "erase_after": erase_after,
            "created_at": created_at,
            "updated_at": created_at,
        })

        # 3. PUT ephemeral audio to S3 (Mumbai), tagged with the erase deadline,
        #    then advance the state machine to audio_uploaded.
        self.audio_store.put(
            key, audio, erase_after=erase_after,
            metadata={"tenant_id": tenant_id, "conversation_id": conversation_id})
        self.store.set_state(conversation_id, "audio_uploaded")

        # 4. fire the pipeline
        self.bus.produce(topics.AUDIO_RAW_UPLOADED, {
            "conversation_id": conversation_id,
            "tenant_id": tenant_id,
            "mock_transcript": mock_transcript,
        }, key=conversation_id)

        return {
            "conversation_id": conversation_id,
            "consent_id": consent["consent_id"],
            "consent_entry_hash": consent["entry_hash"],
            "state": "audio_uploaded",
            "erase_after": erase_after,
        }
