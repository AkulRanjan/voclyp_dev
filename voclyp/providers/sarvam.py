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

    def speech_to_text(self, audio: bytes, filename: str = "audio.wav",
                       model: str = "saarika:v2.5",
                       language_code: str = "unknown") -> dict:
        """Returns {"transcript": ..., "language_code": "hi-IN", ...}."""
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
            f"Content-Type: audio/wav\r\n\r\n".encode("utf-8")
        )
        body = b"".join(parts) + audio + f"\r\n--{boundary}--\r\n".encode("utf-8")
        return self._request(
            "/speech-to-text", body, f"multipart/form-data; boundary={boundary}"
        )

    def translate(self, text: str, source: str = "auto",
                  target: str = "en-IN") -> dict:
        """Returns {"translated_text": ..., "source_language_code": ...}."""
        payload = json.dumps({
            "input": text,
            "source_language_code": source,
            "target_language_code": target,
        }).encode("utf-8")
        return self._request("/translate", payload, "application/json")
