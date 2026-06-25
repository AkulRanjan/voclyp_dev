"""Filter diarized utterances and label agent vs customer using voiceprint."""
from __future__ import annotations

import io
import wave
from collections import defaultdict

from ..contracts import ConversationContext, Utterance
from ..voice import embed, similarity

_MIN_CHARS = 2
_MIN_DURATION_S = 0.2
_MIN_TALK_SHARE = 0.04  # drop speaker clusters below 4% of talk time


def _utterance_duration(u: Utterance) -> float:
    if u.end_time > u.start_time:
        return u.end_time - u.start_time
    return max(len(u.text.split()), 1) * 0.4


def _is_noise(u: Utterance) -> bool:
    text = (u.text or "").strip()
    if len(text) < _MIN_CHARS and len(text.split()) < 2:
        return True
    if u.end_time > u.start_time and (u.end_time - u.start_time) < _MIN_DURATION_S:
        return len(text) < 8
    return False


def _pcm_from_wav(audio: bytes, start_s: float, end_s: float) -> bytes | None:
    try:
        with wave.open(io.BytesIO(audio), "rb") as w:
            rate = w.getframerate()
            width = w.getsampwidth()
            channels = w.getnchannels()
            start = max(0, int(start_s * rate))
            end = min(w.getnframes(), int(end_s * rate))
            if end <= start:
                return None
            w.setpos(start)
            frames = w.readframes(end - start)
    except (wave.Error, EOFError, ValueError):
        return None
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(frames)
    return out.getvalue()


def _speaker_clip(audio: bytes, utterances: list[Utterance], speaker_id: str) -> bytes:
    """Build a WAV clip from all segments of one diarized speaker."""
    if not audio:
        return b""
    chunks: list[bytes] = []
    for u in utterances:
        if u.speaker_id != speaker_id or u.end_time <= u.start_time:
            continue
        clip = _pcm_from_wav(audio, u.start_time, u.end_time)
        if clip:
            chunks.append(clip)
    if not chunks:
        return audio[: min(len(audio), 200_000)]
    if len(chunks) == 1:
        return chunks[0]
    # merge wav clips
    try:
        all_frames = []
        params = None
        for c in chunks:
            with wave.open(io.BytesIO(c), "rb") as w:
                if params is None:
                    params = (w.getnchannels(), w.getsampwidth(), w.getframerate())
                all_frames.append(w.readframes(w.getnframes()))
        if not params:
            return chunks[0]
        out = io.BytesIO()
        with wave.open(out, "wb") as w:
            w.setnchannels(params[0])
            w.setsampwidth(params[1])
            w.setframerate(params[2])
            for fr in all_frames:
                w.writeframes(fr)
        return out.getvalue()
    except (wave.Error, EOFError):
        return chunks[0]


def cleanup_conversation(ctx: ConversationContext, audio: bytes,
                         voiceprint: list | None, threshold: float = 0.65) -> None:
    """Drop background/noise segments; map diarized ids to agent/customer."""
    utts = [u for u in ctx.utterances if not _is_noise(u)]
    if not utts:
        ctx.utterances = []
        return

    by_sid: dict[str, list[Utterance]] = defaultdict(list)
    for u in utts:
        sid = u.speaker_id or u.speaker or "0"
        by_sid[sid].append(u)

    durations = {sid: sum(_utterance_duration(u) for u in group) for sid, group in by_sid.items()}
    total = sum(durations.values()) or 1.0

    # Drop minor speakers (background / third person).
    keep_sids = [
        sid for sid, dur in durations.items()
        if dur / total >= _MIN_TALK_SHARE or len(by_sid) <= 2
    ]
    if len(keep_sids) > 2:
        keep_sids = sorted(durations, key=durations.get, reverse=True)[:2]
    utts = [u for u in utts if (u.speaker_id or u.speaker) in keep_sids]

    if not utts:
        ctx.utterances = []
        return

    # Recompute on filtered set
    by_sid = defaultdict(list)
    for u in utts:
        by_sid[u.speaker_id or u.speaker].append(u)

    agent_sid = None
    customer_sid = None

    if voiceprint and audio:
        scores = {}
        for sid in by_sid:
            clip = _speaker_clip(audio, utts, sid)
            if clip:
                scores[sid] = similarity(embed(clip)["vector"], voiceprint)
        if scores:
            agent_sid = max(scores, key=scores.get)
            ctx.agent_voice_similarity = round(scores[agent_sid], 3)
            ctx.agent_voice_verified = scores[agent_sid] >= threshold
            others = [s for s in by_sid if s != agent_sid]
            customer_sid = others[0] if others else None

    if agent_sid is None:
        # First speaker in time order = agent (opens the visit).
        ordered = sorted(
            by_sid.keys(),
            key=lambda sid: min((u.start_time for u in by_sid[sid]), default=0.0),
        )
        agent_sid = ordered[0]
        customer_sid = ordered[1] if len(ordered) > 1 else None

    for u in utts:
        sid = u.speaker_id or u.speaker
        if sid == agent_sid:
            u.speaker = "agent"
        elif customer_sid and sid == customer_sid:
            u.speaker = "customer"
        elif sid != agent_sid:
            u.speaker = "customer"
        else:
            u.speaker = "unknown"

    ctx.utterances = utts
