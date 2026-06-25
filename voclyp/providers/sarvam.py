"""Thin Sarvam AI client (stdlib only, no SDK dependency).

Sarvam endpoints used:
- POST /speech-to-text   (Saarika): ASR for Indian languages, handles
  code-mixed Hindi-English natively; ``language_code="unknown"`` auto-detects.
- POST /translate        (Mayura): text translation between Indian languages
  and English, ``source_language_code="auto"`` detects the source.

The API key arrives via SARVAM_API_KEY (in production: a secrets manager),
is sent only in the ``api-subscription-key`` header, and is never logged.
Every call is metered by the calling stage so credit burn is visible per
conversation in /v1/metrics.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid


class SarvamError(Exception):
    pass


class SarvamClient:
    def __init__(self, api_key: str, base_url: str = "https://api.sarvam.ai",
                 timeout: float = 60.0):
        if not api_key:
            raise SarvamError(
                "Sarvam API key not configured — set the SARVAM_API_KEY "
                "environment variable"
            )
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, path: str, body: bytes, content_type: str) -> dict:
        req = urllib.request.Request(
            self.base_url + path, data=body, method="POST",
            headers={
                "api-subscription-key": self.api_key,
                "Content-Type": content_type,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise SarvamError(f"sarvam {path} -> HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise SarvamError(f"sarvam {path} unreachable: {exc.reason}") from exc

    def speech_to_text(self, audio: bytes, filename: str | None = None,
                       model: str = "saarika:v2.5",
                       language_code: str = "unknown") -> dict:
        """Returns {"transcript": ..., "language_code": "hi-IN", ...}."""
        filename, mime = self._audio_file_meta(audio, filename)
        boundary = uuid.uuid4().hex
        parts = []
        for name, value in (("model", model), ("language_code", language_code)):
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; "
                f'name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8")
            )
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; "
            f'name="file"; filename="{filename}"\r\n'
            f"Content-Type: {mime}\r\n\r\n".encode("utf-8")
        )
        body = b"".join(parts) + audio + f"\r\n--{boundary}--\r\n".encode("utf-8")
        return self._request(
            "/speech-to-text", body, f"multipart/form-data; boundary={boundary}"
        )

    @staticmethod
    def _audio_file_meta(audio: bytes, filename: str | None = None) -> tuple[str, str]:
        """Pick filename + MIME so Sarvam receives the real container format."""
        if filename:
            lower = filename.lower()
            if lower.endswith(".m4a") or lower.endswith(".mp4"):
                return filename, "audio/mp4"
            if lower.endswith(".aac"):
                return filename, "audio/aac"
            if lower.endswith(".amr"):
                return filename, "audio/amr"
            if lower.endswith(".mp3"):
                return filename, "audio/mpeg"
            if lower.endswith(".wav"):
                return filename, "audio/wav"
        if len(audio) >= 12 and audio[4:8] == b"ftyp":
            return "audio.m4a", "audio/mp4"
        if audio[:4] == b"RIFF":
            return "audio.wav", "audio/wav"
        if audio[:5] == b"#!AMR":
            return "audio.amr", "audio/amr"
        return "audio.wav", "audio/wav"

    def translate(self, text: str, source: str = "auto",
                  target: str = "en-IN") -> dict:
        """Returns {"translated_text": ..., "source_language_code": ...}."""
        payload = json.dumps({
            "input": text,
            "source_language_code": source,
            "target_language_code": target,
        }).encode("utf-8")
        return self._request("/translate", payload, "application/json")

    def chat_completions(self, messages: list, model: str = "sarvam-30b",
                         max_tokens: int = 1200, temperature: float = 0.3,
                         reasoning_effort: str | None = "off") -> dict:
        """OpenAI-compatible chat completions (visit notes, coaching).

        Sarvam-30b/105b are hybrid *reasoning* models with thinking ON by
        default. On long transcripts the model loops in its hidden
        ``reasoning_content`` and burns the whole ``max_tokens`` budget before
        ever writing the visible ``content`` (``finish_reason="length"`` with an
        empty answer). For structured JSON extraction we don't want reasoning at
        all, so we DISABLE it by sending ``reasoning_effort: null`` — this makes
        the model return the JSON directly and fast.

        ``reasoning_effort`` values:
          * ``"off"`` (default) — send JSON ``null`` -> reasoning disabled.
          * ``"low"`` / ``"medium"`` / ``"high"`` — keep reasoning at that level.
          * ``None`` — omit the field (uses the API default, reasoning ON).
        """
        body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if reasoning_effort == "off":
            body["reasoning_effort"] = None  # explicit JSON null disables thinking
        elif reasoning_effort is not None:
            body["reasoning_effort"] = reasoning_effort
        return self._request(
            "/v1/chat/completions", json.dumps(body).encode("utf-8"),
            "application/json",
        )

    @staticmethod
    def message_text(resp: dict) -> str:
        """Extract the assistant's answer text from a chat response.

        Returns ``content`` only — never ``reasoning_content``, which holds the
        model's hidden thinking and is not the answer.
        """
        msg = ((resp.get("choices") or [{}])[0] or {}).get("message", {}) or {}
        return (msg.get("content") or "").strip()
