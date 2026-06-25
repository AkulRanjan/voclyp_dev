"""Sarvam dual-transcript ASR worker.

Consumes ``audio.raw.uploaded``, fetches the WAV from S3, and produces TWO
transcripts:

- ``transcript_codemix``  — native-script code-mixed text (Saarika /
  ``mode=codemix``). This is what the dashboard shows and what goes into the
  WhatsApp follow-up, preserving the customer's own Hindi/Gujarati/English mix.
- ``transcript_english``  — English (Saaras ``speech-to-text-translate`` /
  ``mode=translate``). This is the clean input fed to Claude for extraction.

Quota safety (Self-Correction 3): Sarvam REST tops out at 30s, so anything
longer is routed to the Batch API; if Batch is unavailable the audio is split
into <=30s WAV chunks and transcribed via REST, then stitched back together.

With no SARVAM_API_KEY the worker runs a deterministic offline mock so the full
event pipeline still flows end-to-end.
"""
from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
import uuid
import wave

from ...contracts import utcnow
from ...languages import short
from ..events import topics


def wav_duration_seconds(audio: bytes) -> float:
    try:
        with wave.open(io.BytesIO(audio), "rb") as w:
            rate = w.getframerate() or 16000
            return w.getnframes() / float(rate)
    except Exception:
        return 0.0


def split_wav_chunks(audio: bytes, chunk_seconds: float = 25.0) -> list[bytes]:
    """Split a PCM WAV into <=chunk_seconds pieces (each a valid WAV)."""
    try:
        with wave.open(io.BytesIO(audio), "rb") as w:
            params = w.getparams()
            rate = w.getframerate() or 16000
            frames_per_chunk = max(1, int(rate * chunk_seconds))
            chunks: list[bytes] = []
            while True:
                frames = w.readframes(frames_per_chunk)
                if not frames:
                    break
                buf = io.BytesIO()
                with wave.open(buf, "wb") as out:
                    out.setnchannels(params.nchannels)
                    out.setsampwidth(params.sampwidth)
                    out.setframerate(rate)
                    out.writeframes(frames)
                chunks.append(buf.getvalue())
            return chunks or [audio]
    except Exception:
        return [audio]


class SarvamAsrWorker:
    topic = topics.AUDIO_RAW_UPLOADED

    def __init__(self, settings, store, bus, audio_store, client=None,
                 batch_factory=None):
        self.settings = settings
        self.store = store
        self.bus = bus
        self.audio_store = audio_store
        self.client = client                # SarvamClient | None (None => mock)
        self.batch_factory = batch_factory   # callable(mode) -> sarvamai job

    # -- event entrypoint ------------------------------------------------------
    def handle(self, event: dict) -> None:
        value = event.get("value", event)
        conversation_id = value["conversation_id"]
        conv = self.store.get_conversation(conversation_id)
        if not conv:
            return
        self.store.set_state(conversation_id, "transcribing")
        try:
            audio = self.audio_store.get(conv["s3_key"])
            result = self.transcribe(audio, hint=value.get("mock_transcript"))
            # data update only; the state stays 'transcribing' until extraction
            self.store.update_conversation(
                conversation_id,
                transcript_codemix=result["codemix"],
                transcript_english=result["english"],
                detected_languages=result["languages"],
                duration_seconds=result["duration_seconds"],
                asr_path=result["path"],
            )
            self.bus.produce(topics.TRANSCRIPT_READY, {
                "conversation_id": conversation_id,
                "tenant_id": conv["tenant_id"],
            }, key=conversation_id)
        except Exception as exc:  # keep the pipeline alive; surface the reason
            # leave the state for the orphan sweep; just record why it stalled
            self.store.update_conversation(
                conversation_id,
                error_detail=f"asr: {type(exc).__name__}: {exc}"[:480])

    # -- transcription ---------------------------------------------------------
    def transcribe(self, audio: bytes, hint: str | None = None) -> dict:
        from ...audio.prepare import normalize_for_sarvam

        normalized, filename = normalize_for_sarvam(audio)
        duration = wav_duration_seconds(normalized) or wav_duration_seconds(audio)

        if self.client is None:
            return self._mock(normalized, duration, hint)

        if duration > self.settings.sarvam_rest_limit_s:
            try:
                return self._transcribe_batch(normalized, duration)
            except Exception:
                return self._transcribe_chunked(normalized, duration)
        return self._transcribe_rest(normalized, filename, duration, path="rest")

    def _transcribe_rest(self, audio: bytes, filename: str, duration: float,
                         path: str) -> dict:
        codemix_resp = self.client.speech_to_text(
            audio, filename=filename, model="saarika:v2.5", language_code="unknown")
        codemix = (codemix_resp.get("transcript") or "").strip()
        languages = []
        detected = short(codemix_resp.get("language_code") or "")
        if detected:
            languages.append(detected)

        english = self._english_transcript(audio, filename, codemix)
        return {
            "codemix": codemix,
            "english": english,
            "languages": languages,
            "duration_seconds": duration,
            "path": path,
        }

    def _english_transcript(self, audio: bytes, filename: str, codemix: str) -> str:
        """Saaras speech-to-text-translate; fall back to translating the codemix."""
        try:
            resp = self._stt_translate(audio, filename)
            english = (resp.get("transcript") or "").strip()
            if english:
                return english
        except Exception:
            pass
        if codemix:
            try:
                resp = self.client.translate(codemix, source="auto", target="en-IN")
                return (resp.get("translated_text") or codemix).strip()
            except Exception:
                return codemix
        return ""

    def _stt_translate(self, audio: bytes, filename: str) -> dict:
        """POST /speech-to-text-translate (Saaras) using the client's transport.

        Kept here (not in the shared SarvamClient) so the core pipeline stays
        untouched. Mirrors the client's multipart format and auth header.
        """
        fname, mime = self.client._audio_file_meta(audio, filename)
        boundary = uuid.uuid4().hex
        parts = [
            (f"--{boundary}\r\nContent-Disposition: form-data; "
             f'name="model"\r\n\r\nsaaras:v2.5\r\n').encode("utf-8"),
            (f"--{boundary}\r\nContent-Disposition: form-data; "
             f'name="file"; filename="{fname}"\r\n'
             f"Content-Type: {mime}\r\n\r\n").encode("utf-8"),
        ]
        body = b"".join(parts) + audio + f"\r\n--{boundary}--\r\n".encode("utf-8")
        req = urllib.request.Request(
            self.client.base_url + "/speech-to-text-translate", data=body,
            method="POST",
            headers={
                "api-subscription-key": self.client.api_key,
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            })
        with urllib.request.urlopen(req, timeout=self.client.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _transcribe_chunked(self, audio: bytes, duration: float) -> dict:
        codemix_parts, english_parts, languages = [], [], []
        for chunk in split_wav_chunks(audio):
            part = self._transcribe_rest(chunk, "chunk.wav", 0.0, path="rest")
            if part["codemix"]:
                codemix_parts.append(part["codemix"])
            if part["english"]:
                english_parts.append(part["english"])
            for lang in part["languages"]:
                if lang not in languages:
                    languages.append(lang)
        return {
            "codemix": " ".join(codemix_parts).strip(),
            "english": " ".join(english_parts).strip(),
            "languages": languages,
            "duration_seconds": duration,
            "path": "rest-chunked",
        }

    def _transcribe_batch(self, audio: bytes, duration: float) -> dict:
        if not self.batch_factory:
            raise RuntimeError("batch ASR not configured")
        import shutil
        import tempfile
        from pathlib import Path

        workdir = Path(tempfile.mkdtemp(prefix="voclyp-ent-stt-"))
        try:
            src = workdir / "audio.wav"
            src.write_bytes(audio)
            codemix = self._run_batch_mode(workdir, src, "codemix")
            english = self._run_batch_mode(workdir, src, "translate")
            return {
                "codemix": codemix["text"],
                "english": english["text"] or codemix["text"],
                "languages": codemix["languages"],
                "duration_seconds": duration,
                "path": "batch",
            }
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    def _run_batch_mode(self, workdir, src, mode: str) -> dict:  # pragma: no cover
        from pathlib import Path

        job = self.batch_factory(mode)
        job.upload_files(file_paths=[str(src)])
        job.start()
        job.wait_until_complete(timeout=900)
        outdir = Path(workdir) / f"out-{mode}"
        job.download_outputs(output_dir=str(outdir))
        texts, languages = [], []
        for path in sorted(Path(outdir).rglob("*.json")):
            doc = json.loads(path.read_text(encoding="utf-8"))
            detected = short(doc.get("language_code") or "")
            if detected and detected not in languages:
                languages.append(detected)
            entries = ((doc.get("diarized_transcript") or {}).get("entries")) or []
            if entries:
                texts.extend((e.get("transcript") or "").strip() for e in entries)
            elif doc.get("transcript"):
                texts.append(doc["transcript"].strip())
        return {"text": " ".join(t for t in texts if t).strip(), "languages": languages}

    # -- offline mock ----------------------------------------------------------
    def _mock(self, audio: bytes, duration: float, hint: str | None) -> dict:
        """Deterministic transcript so the pipeline runs with no Sarvam key."""
        if hint:
            codemix = hint
            english = hint
        else:
            codemix = (
                "Customer: Mera lower back bahut pain karta hai subah uthte time. "
                "Main ek achha mattress dhund raha hoon. "
                "Sales: Sir hamara orthopedic memory foam model perfect rahega. "
                "Customer: Lekin Kurlon se compare kiya toh thoda expensive lag raha hai, "
                "EMI option hai kya? "
                "Sales: Haan sir, 5000 rupaye per month, 12 months ke liye, zero interest. "
                "Customer: Theek hai, ghar pe wife se baat karke confirm karta hoon."
            )
            english = (
                "Customer: My lower back hurts a lot when I get up in the morning. "
                "I'm looking for a good mattress. "
                "Sales: Sir, our orthopedic memory foam model will be perfect. "
                "Customer: But compared to Kurlon it feels a bit expensive, is there an EMI option? "
                "Sales: Yes sir, 5000 rupees per month for 12 months at zero interest. "
                "Customer: Okay, I'll confirm after talking to my wife at home."
            )
        return {
            "codemix": codemix,
            "english": english,
            "languages": ["hi", "en"],
            "duration_seconds": duration or 42.0,
            "path": "mock",
        }
