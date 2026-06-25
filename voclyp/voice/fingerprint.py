"""Lightweight, dependency-free voice fingerprinting.

A *voiceprint* is a small fixed-length feature vector summarizing a speaker's
acoustic envelope (energy contour + zero-crossing/pitch proxy over time, plus
global statistics). It is NOT raw audio and cannot be played back — the
enrollment clip is shredded the instant the vector is computed.

Why a hand-rolled fingerprint? It runs anywhere with zero extra packages, which
keeps the platform's "no heavy deps in core" promise. It is deliberately
pluggable: `VOCLYP_VOICEPRINT_BACKEND=aws` (or any future embedding service)
swaps this baseline for a learned speaker embedding without touching callers —
the contract is just `embed(audio_bytes) -> list[float]` and `similarity(a, b)`.

For real WAV/PCM audio this produces a genuine acoustic fingerprint usable for
agent/customer separation in diarization; for opaque/compressed blobs it falls
back to a stable byte-derived vector so the enrollment flow still completes.
"""
from __future__ import annotations

import array
import hashlib
import io
import math
import os
import wave

MODEL_ACOUSTIC = "voclyp-acoustic-v1"
MODEL_FALLBACK = "voclyp-bytes-v1"

_SEGMENTS = 16  # temporal resolution of the energy / pitch contour


def _read_wav_samples(audio: bytes):
    """Return (mono float samples in [-1,1], sample_rate) or None if not WAV."""
    try:
        with wave.open(io.BytesIO(audio), "rb") as wav:
            n_channels = wav.getnchannels()
            width = wav.getsampwidth()
            rate = wav.getframerate()
            frames = wav.readframes(wav.getnframes())
    except (wave.Error, EOFError, ValueError):
        return None
    if width != 2 or not frames:
        # only 16-bit PCM is handled by the baseline; anything else -> fallback
        return None
    samples = array.array("h")
    samples.frombytes(frames)
    if n_channels > 1:
        mono = [
            sum(samples[i:i + n_channels]) / n_channels
            for i in range(0, len(samples) - n_channels + 1, n_channels)
        ]
    else:
        mono = list(samples)
    if not mono:
        return None
    return [s / 32768.0 for s in mono], rate


def _l2_normalize(vec):
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec] if norm else vec


def _acoustic_vector(samples) -> list:
    n = len(samples)
    seg_len = max(1, n // _SEGMENTS)
    rms_contour, zcr_contour = [], []
    for s in range(_SEGMENTS):
        seg = samples[s * seg_len:(s + 1) * seg_len] or [0.0]
        rms = math.sqrt(sum(x * x for x in seg) / len(seg))
        crossings = sum(
            1 for i in range(1, len(seg))
            if (seg[i - 1] >= 0) != (seg[i] >= 0)
        )
        rms_contour.append(rms)
        zcr_contour.append(crossings / len(seg))
    # global statistics give the vector speaker-discriminative shape, not just
    # loudness: mean pitch proxy, its variance, and energy dynamics
    mean_zcr = sum(zcr_contour) / len(zcr_contour)
    zcr_var = sum((z - mean_zcr) ** 2 for z in zcr_contour) / len(zcr_contour)
    mean_rms = sum(rms_contour) / len(rms_contour)
    rms_var = sum((r - mean_rms) ** 2 for r in rms_contour) / len(rms_contour)
    vec = rms_contour + zcr_contour + [mean_zcr, zcr_var, mean_rms, rms_var]
    return _l2_normalize(vec)


def _fallback_vector(audio: bytes) -> list:
    """Deterministic vector from a content hash — keeps the flow working for
    compressed/opaque audio the baseline can't decode. Not acoustically
    meaningful; swap in a real embedding backend for production."""
    digest = hashlib.sha256(audio).digest()
    dims = _SEGMENTS * 2 + 4
    vals = [digest[i % len(digest)] / 255.0 for i in range(dims)]
    return _l2_normalize(vals)


def embed(audio: bytes) -> dict:
    """Compute a voiceprint. Returns {'vector', 'model', 'frames'}.

    Honors VOCLYP_VOICEPRINT_BACKEND: 'acoustic' (default, this module) or
    'aws' (delegates to voclyp.voice.aws_embed if configured)."""
    backend = os.environ.get("VOCLYP_VOICEPRINT_BACKEND", "acoustic").lower()
    if backend == "aws":
        try:
            from .aws import aws_embed  # optional, documented in DEPLOYMENT_AWS
            return aws_embed(audio)
        except Exception:
            pass  # fall through to the dependency-free baseline
    parsed = _read_wav_samples(audio)
    if parsed is not None:
        samples, _rate = parsed
        return {"vector": _acoustic_vector(samples),
                "model": MODEL_ACOUSTIC, "frames": len(samples)}
    return {"vector": _fallback_vector(audio),
            "model": MODEL_FALLBACK, "frames": 0}


def similarity(a, b) -> float:
    """Cosine similarity of two (already L2-normalized) voiceprints, in [0,1].
    Returns 0.0 for mismatched dimensions or empty vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    return max(0.0, min(1.0, (dot + 1.0) / 2.0))


def merge(existing, incoming, existing_count: int) -> list:
    """Running mean of voiceprints (re-enrollment improves the profile)."""
    if not existing or len(existing) != len(incoming):
        return incoming
    n = existing_count + 1
    merged = [(existing[i] * existing_count + incoming[i]) / n
              for i in range(len(incoming))]
    return _l2_normalize(merged)
