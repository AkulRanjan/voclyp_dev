"""Prepare field recordings for Sarvam batch STT (correct format + single file).

Mobile uploads are often m4a/aac; the batch stage used to write them as ``.wav``,
which made Sarvam reject the file. We detect the real container, merge ordered
parts into one clip, and optionally transcode to 16 kHz mono WAV when ffmpeg is
available.
"""
from __future__ import annotations

import io
import shutil
import subprocess
import wave
import audioop
from pathlib import Path

from ..security import AudioVault


def detect_audio_suffix(audio: bytes) -> str:
    if len(audio) >= 4 and audio[:4] == b"RIFF":
        return ".wav"
    if len(audio) >= 12 and audio[4:8] == b"ftyp":
        return ".m4a"
    if audio[:3] == b"ID3" or (len(audio) >= 2 and audio[0] == 0xFF and audio[1] & 0xE0 == 0xE0):
        return ".mp3"
    if audio[:5] == b"#!AMR":
        return ".amr"
    if audio[:4] == b"fLaC":
        return ".flac"
    if audio[:4] == b"OggS":
        return ".ogg"
    return ".wav"


def looks_like_audio(audio: bytes) -> bool:
    if not audio or len(audio) < 4:
        return False
    if audio[:4] == b"RIFF":
        return True
    if len(audio) >= 12 and audio[4:8] == b"ftyp":
        return True
    if audio[:5] == b"#!AMR":
        return True
    if audio[:4] == b"fLaC" or audio[:4] == b"OggS":
        return True
    # UTF-8 text stub used in tests
    try:
        sample = audio[:512].decode("utf-8")
        return not any(c.isalpha() for c in sample)
    except UnicodeDecodeError:
        return True


def merge_files_to_bytes(paths: list[str]) -> bytes:
    """Merge multiple on-disk audio files into one blob for ASR."""
    parts = [Path(p).read_bytes() for p in paths if Path(p).is_file()]
    if not parts:
        return b""
    if len(parts) == 1:
        return parts[0]
    suffixes = {detect_audio_suffix(p) for p in parts}
    if suffixes == {".wav"}:
        return _merge_wav_pcm(parts)
    if _ffmpeg_available():
        merged = _ffmpeg_concat(parts)
        if merged:
            return merged
    return max(parts, key=len)


def _ffmpeg_concat(parts: list[bytes]) -> bytes | None:
    import tempfile
    work = Path(tempfile.mkdtemp(prefix="voclyp-concat-"))
    try:
        list_file = work / "list.txt"
        paths = []
        for i, blob in enumerate(parts):
            ext = detect_audio_suffix(blob)
            p = work / f"part{i}{ext}"
            p.write_bytes(blob)
            paths.append(p)
        list_file.write_text(
            "\n".join(f"file '{p.as_posix()}'" for p in paths),
            encoding="utf-8",
        )
        out = work / "merged.wav"
        proc = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-f", "concat", "-safe", "0", "-i", str(list_file),
                "-ar", "16000", "-ac", "1", "-f", "wav", str(out),
            ],
            capture_output=True,
            timeout=180,
        )
        if proc.returncode == 0 and out.is_file():
            return out.read_bytes()
    except (subprocess.SubprocessError, OSError):
        pass
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return None


def merge_encrypted_chunks(vault: AudioVault, paths: list[str]) -> bytes:
    """Concatenate ordered encrypted chunks into one byte blob."""
    parts = [vault.read(p) for p in paths]
    if len(parts) == 1:
        return parts[0]
    suffixes = {detect_audio_suffix(p) for p in parts}
    if len(suffixes) == 1 and ".wav" in suffixes:
        return _merge_wav_pcm(parts)
    if _ffmpeg_available():
        merged = _ffmpeg_concat(parts)
        if merged:
            return merged
    return max(parts, key=len)


def _merge_wav_pcm(chunks: list[bytes]) -> bytes:
    """Append mono/stereo 16-bit WAV chunks into one WAV."""
    all_samples: list[bytes] = []
    rate = 16000
    width = 2
    channels = 1
    for chunk in chunks:
        try:
            with wave.open(io.BytesIO(chunk), "rb") as w:
                rate = w.getframerate()
                width = w.getsampwidth()
                channels = w.getnchannels()
                all_samples.append(w.readframes(w.getnframes()))
        except (wave.Error, EOFError):
            continue
    if not all_samples:
        return chunks[-1] if chunks else b""
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        for frames in all_samples:
            w.writeframes(frames)
    return out.getvalue()


def normalize_wav_16k_mono(audio: bytes) -> bytes | None:
    """Resample WAV to 16 kHz mono using stdlib (works without ffmpeg)."""
    try:
        with wave.open(io.BytesIO(audio), "rb") as w:
            channels = w.getnchannels()
            width = w.getsampwidth()
            rate = w.getframerate()
            frames = w.readframes(w.getnframes())
    except (wave.Error, EOFError):
        return None
    if not frames:
        return None
    if channels == 2:
        frames = audioop.tomono(frames, width, 0.5, 0.5)
        channels = 1
    if rate != 16000:
        frames, _ = audioop.ratecv(frames, width, channels, rate, 16000, None)
        rate = 16000
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(frames)
    return out.getvalue()


def normalize_for_sarvam(audio: bytes) -> tuple[bytes, str]:
    """Return (bytes, filename) in the best format Sarvam batch/sync accepts."""
    suffix = detect_audio_suffix(audio)
    if suffix == ".wav":
        normalized = _transcode_wav_16k_mono(audio, suffix) or normalize_wav_16k_mono(audio)
        if normalized:
            return normalized, "visit.wav"
    if suffix == ".m4a" and _ffmpeg_available():
        transcoded = _transcode_wav_16k_mono(audio, suffix)
        if transcoded:
            return transcoded, "visit.wav"
    return audio, f"visit{suffix}"


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _transcode_wav_16k_mono(audio: bytes, src_suffix: str) -> bytes | None:
    if not _ffmpeg_available():
        return None
    try:
        proc = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-i", f"pipe:0",
                "-ar", "16000", "-ac", "1", "-f", "wav", "pipe:1",
            ],
            input=audio,
            capture_output=True,
            timeout=120,
            check=True,
        )
        return proc.stdout
    except (subprocess.SubprocessError, FileNotFoundError):
        return None


def prepare_sarvam_file(workdir: Path, audio: bytes) -> Path:
    """Write one upload file for Sarvam batch with the correct format."""
    workdir.mkdir(parents=True, exist_ok=True)
    normalized, name = normalize_for_sarvam(audio)
    path = workdir / name
    path.write_bytes(normalized)
    return path
