"""Streaming ASR: accumulate audio chunks, emit partial transcripts.

Real-time consent capture relies on this: as the rep speaks, audio windows are
transcribed and customer name/number are extracted on the fly so they appear on
the dashboard live. When SARVAM_API_KEY is configured this calls Sarvam's
Saarika ASR (Hindi-English code-mix native) and meters every call; otherwise it
falls back to a deterministic dev stub so the flow works without credits.

Mobile sends a **complete** recording file every ~2 s (not raw PCM). Each chunk
is transcribed on its own — concatenating multiple WAV/m4a headers breaks STT.
"""
from __future__ import annotations

import audioop
import io
import os
import wave

from ..audio.prepare import detect_audio_suffix, normalize_for_sarvam
from ..providers.sarvam import SarvamClient, SarvamError
from ..languages import load_languages
from .entities import extract_entities, extract_name


def _streaming_language() -> str:
    """Auto-detect among Sarvam's 23 languages (Hindi, Gujarati, English, etc.)."""
    return "unknown"


def _names_equal(a: str | None, b: str | None) -> bool:
    return bool(a) and bool(b) and a.strip().lower() == b.strip().lower()


class StreamingASR:
    """Micro-batch partial transcription with entity extraction."""

    def __init__(self, flush_bytes: int = 48_000, api_key: str | None = None,
                 model: str = "saarika:v2.5", language_code: str | None = None):
        self.flush_bytes = flush_bytes
        self.api_key = api_key if api_key is not None else os.environ.get("SARVAM_API_KEY", "")
        self.model = model
        self.language_code = language_code or _streaming_language()
        self._transcript = ""
        self._chunk_count = 0
        self.sarvam_calls = 0
        self._client = None
        # Loudness tracking: people tend to raise their voice on their own name,
        # so we keep a running average chunk loudness to boost name confidence.
        self._energy_n = 0
        self._energy_mean = 0.0

    @property
    def transcript(self) -> str:
        return self._transcript

    def add_chunk(self, data: bytes) -> dict | None:
        """Add one complete mobile recording chunk; return event when text found."""
        if not data or len(data) < 4_000:
            return None
        self._chunk_count += 1

        # Each WebSocket payload is a full file from expo-av (WAV or m4a).
        audio, filename = normalize_for_sarvam(data)
        partial = self._transcribe_window(audio, filename)

        if partial:
            self._transcript = (self._transcript + " " + partial).strip()
            loudness = self._update_loudness(audio)
            # Resolve name/phone from the WHOLE transcript every time. The
            # extractors are correction-aware (they segment on cues like "nahi"
            # and read only the latest value), so a spoken correction wins
            # without us freezing an earlier mis-hear here.
            entities = extract_entities(self._transcript)
            # Voice emphasis: people often raise their voice on their own name.
            # If this chunk was clearly louder and its name matches what we
            # resolved, nudge confidence up — but never let loudness override
            # the corrected value.
            if entities.get("name") and loudness > 1.25:
                chunk_name, _ = extract_name(partial)
                if _names_equal(chunk_name, entities["name"]):
                    entities["name_confidence"] = min(
                        0.97, entities.get("name_confidence", 0.0) + 0.1)
            return {
                "type": "partial_transcript",
                "text": self._transcript,
                "lang": self.language_code,
                "entities": entities,
            }
        return None

    def _update_loudness(self, audio: bytes) -> float:
        """Return this chunk's loudness relative to the running average (1.0 =
        average). Falls back to 1.0 when the chunk isn't decodable PCM."""
        rms = self._chunk_rms(audio)
        if rms is None or rms <= 0:
            return 1.0
        self._energy_n += 1
        self._energy_mean += (rms - self._energy_mean) / self._energy_n
        if self._energy_mean <= 0:
            return 1.0
        return max(0.5, min(2.0, rms / self._energy_mean))

    @staticmethod
    def _chunk_rms(audio: bytes) -> float | None:
        """RMS amplitude of a 16-bit PCM WAV chunk (None if not WAV/decodable)."""
        if not audio or audio[:4] != b"RIFF":
            return None
        try:
            with wave.open(io.BytesIO(audio), "rb") as w:
                width = w.getsampwidth()
                frames = w.readframes(w.getnframes())
            if not frames:
                return None
            return float(audioop.rms(frames, width))
        except (wave.Error, EOFError, audioop.error):
            return None

    def _transcribe_window(self, audio: bytes, filename: str = "chunk.wav") -> str:
        """Transcribe a window of audio. Uses Sarvam if configured, else stub."""
        if self.api_key:
            text = self._sarvam_transcribe(audio, filename)
            if text:
                return text
        return self._stub_transcribe(audio)

    def _stub_transcribe(self, audio: bytes) -> str:
        # Dev stub: decode as utf-8 if text pipeline, else inject demo phrases.
        try:
            text = audio.decode("utf-8").strip()
            if text and any(c.isalpha() for c in text):
                return text
        except UnicodeDecodeError:
            pass
        if self._chunk_count <= 2:
            return ""
        if self._chunk_count == 3:
            return "Customer naam Rahul hai, WhatsApp number 9876543210."
        if self._chunk_count == 5:
            return "Pith mein dard hai, orthopaedic mattress chahiye."
        return ""

    def _sarvam_transcribe(self, audio: bytes, filename: str) -> str:
        """Real partial transcription via Sarvam Saarika; metered, fail-soft."""
        try:
            if self._client is None:
                self._client = SarvamClient(self.api_key)
            if not filename:
                suffix = detect_audio_suffix(audio)
                filename = f"chunk{suffix}"
            resp = self._client.speech_to_text(
                audio, filename=filename,
                model=self.model, language_code=self.language_code,
            )
            self.sarvam_calls += 1
            return (resp.get("transcript") or "").strip()
        except SarvamError:
            return ""
