"""Live visit session orchestration."""
from __future__ import annotations

import uuid
from pathlib import Path

from ..contracts import utcnow
from ..ingestion import IngestionService
from ..store import Store
from .streaming_asr import StreamingASR


class LiveSessionManager:
    def __init__(self, store: Store, ingestion: IngestionService, sessions_dir: Path):
        self.store = store
        self.ingestion = ingestion
        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._asr: dict[str, StreamingASR] = {}

    def start(self, tenant_id: str, store_id: str, agent_id: str) -> dict:
        session_id = f"sess-{uuid.uuid4().hex[:12]}"
        self.store.create_live_session(tenant_id, session_id, store_id, agent_id)
        self._asr[session_id] = StreamingASR()
        (self.sessions_dir / session_id).mkdir(parents=True, exist_ok=True)
        return {"session_id": session_id, "status": "identity"}

    def get(self, tenant_id: str, session_id: str) -> dict | None:
        return self.store.get_live_session(tenant_id, session_id)

    def reset_asr(self, tenant_id: str, session_id: str) -> None:
        """Wipe the streaming transcript/entity buffer for a session.

        Called when the rep restarts voice assist (a fresh WebSocket connect),
        so a new listen starts from a clean slate instead of appending to — and
        being polluted by — whatever was mis-heard before.
        """
        self._asr[session_id] = StreamingASR()
        self.store.update_live_session_transcript(tenant_id, session_id, "")

    def patch_customer(self, tenant_id: str, session_id: str, *,
                       name: str | None = None, phone: str | None = None,
                       source: str = "manual") -> dict | None:
        return self.store.update_live_session_customer(
            tenant_id, session_id, name=name, phone=phone, source=source,
        )

    def consent(self, tenant_id: str, session_id: str) -> dict | None:
        return self.store.set_live_session_status(tenant_id, session_id, "active", consent=True)

    def process_chunk(self, tenant_id: str, session_id: str, seq: int, data: bytes) -> list[dict]:
        events: list[dict] = []
        chunk_path = self.sessions_dir / session_id / f"{seq:06d}.bin"
        chunk_path.write_bytes(data)
        self.store.append_session_chunk(tenant_id, session_id, seq, str(chunk_path))

        asr = self._asr.setdefault(session_id, StreamingASR())
        partial = asr.add_chunk(data)
        if partial:
            self.store.update_live_session_transcript(tenant_id, session_id, partial["text"])
            events.append({"type": "partial_transcript", "text": partial["text"], "lang": partial["lang"]})
            ents = partial.get("entities") or {}
            if ents.get("name"):
                session = self.store.get_live_session(tenant_id, session_id) or {}
                if session.get("name_source") != "manual":
                    self.store.update_live_session_customer(
                        tenant_id, session_id, name=ents["name"], source="asr",
                    )
                    events.append({
                        "type": "entity", "field": "name",
                        "value": ents["name"], "confidence": ents.get("name_confidence", 0.8),
                    })
            if ents.get("phone"):
                session = self.store.get_live_session(tenant_id, session_id) or {}
                if session.get("phone_source") != "manual":
                    self.store.update_live_session_customer(
                        tenant_id, session_id, phone=ents["phone"], source="asr",
                    )
                    events.append({
                        "type": "entity", "field": "phone",
                        "value": ents["phone"], "confidence": ents.get("phone_confidence", 0.8),
                    })
        return events

    def complete(self, tenant_id: str, session_id: str,
                 final_audio: bytes | None = None) -> dict:
        session = self.store.get_live_session(tenant_id, session_id)
        if not session:
            raise ValueError("session not found")
        if session["status"] not in ("identity", "active"):
            raise ValueError(f"session not completable from status {session['status']}")

        chunks = self.store.list_session_chunks(tenant_id, session_id)
        chunk_files = [
            Path(c["chunk_path"]) for c in chunks
            if Path(c["chunk_path"]).exists()
        ]
        # Prefer the client's full visit clip. Never submit stub text for live visits.
        audio = final_audio
        if not audio and chunk_files:
            from ..audio.prepare import merge_files_to_bytes
            audio = merge_files_to_bytes([str(p) for p in chunk_files])

        if not audio or len(audio) < 8_000:
            raise ValueError(
                "recording too short — capture the full visit before ending"
            )

        metadata = {
            "agent_id": session["agent_id"],
            "store_id": session["store_id"],
            "client_ref": f"live-{session_id}",
            "customer_phone": session.get("customer_phone") or "",
            "consent": {
                "captured": bool(session.get("consent_at")),
                "customer_name": session.get("customer_name") or "",
            },
        }
        conversation_id = self.ingestion.submit(tenant_id, audio, metadata)
        self.store.set_live_session_status(
            tenant_id, session_id, "processing", conversation_id=conversation_id,
        )
        # Meter live-capture Sarvam calls against the conversation (credit
        # visibility in /v1/metrics, same as the batch pipeline).
        asr = self._asr.pop(session_id, None)
        if asr and getattr(asr, "sarvam_calls", 0):
            self.store.add_usage(
                tenant_id, conversation_id,
                {"sarvam:speech-to-text-streaming": asr.sarvam_calls},
            )
        return {"session_id": session_id, "conversation_id": conversation_id, "status": "processing"}

    def mark_complete(self, tenant_id: str, session_id: str) -> None:
        self.store.set_live_session_status(tenant_id, session_id, "complete")
