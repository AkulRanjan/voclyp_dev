"""Real ASR via Sarvam batch jobs — saaras:v3 with native speaker diarization.

Unlike the synchronous Saarika stage (sarvam_asr.py), the batch API returns a
diarized transcript: who said what. Speaker ids are mapped positionally —
first voice heard = agent (agents open the visit; same assumption the stub
diarizer makes), second = customer — and the diarization stage downstream
only fills speakers still marked unknown, so these labels survive.

The SDK uploads files from disk, so each encrypted chunk is decrypted to a
private temp directory for the duration of the job and shredded in a
``finally`` — the only point in the platform where plaintext audio briefly
touches disk. Requires the optional ``sarvamai`` package and SARVAM_API_KEY;
every processed file is metered into ctx.provider_usage.
"""
from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path

from ..base import Stage
from ..registry import register
from ...config import load_settings
from ...contracts import ConversationContext, Utterance
from ...languages import load_languages, short
from ...providers.sarvam import SarvamError
from ...security import AudioVault

_SENTENCE_SPLIT = re.compile(r"(?<=[।.!?])\s+")
_SPEAKER_BY_ARRIVAL = ("agent", "customer")


class SarvamBatchASR(Stage):
    name = "asr"

    def __init__(self, job_factory, vault: AudioVault = None,
                 model: str = "saaras:v3", timeout_s: int = 600):
        self.job_factory = job_factory
        self.vault = vault or AudioVault()
        self.timeout_s = timeout_s
        self.version = f"sarvam-batch-{model}"

    def run(self, ctx: ConversationContext) -> None:
        workdir = Path(tempfile.mkdtemp(prefix="voclyp-stt-"))
        try:
            wav_paths = []
            for i, enc_path in enumerate(ctx.audio_paths):
                plain = workdir / f"part{i:04d}.wav"
                plain.write_bytes(self.vault.read(enc_path))
                wav_paths.append(str(plain))

            job = self.job_factory()
            job.upload_files(file_paths=wav_paths)
            job.start()
            job.wait_until_complete(timeout=self.timeout_s)

            results = job.get_file_results()
            failed = results.get("failed") or []
            if failed:
                first = failed[0]
                raise SarvamError(
                    f"sarvam batch job: {len(failed)} file(s) failed "
                    f"({first.get('file_name')}: {first.get('error_message')})"
                )

            outdir = workdir / "out"
            job.download_outputs(output_dir=str(outdir))
            ctx.provider_usage["sarvam:speech-to-text-job"] = (
                ctx.provider_usage.get("sarvam:speech-to-text-job", 0)
                + len(wav_paths)
            )
            # chunk order = conversation order; output files keep input names
            for path in sorted(outdir.rglob("*.json")):
                self._parse_output(
                    ctx, json.loads(path.read_text(encoding="utf-8")))
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    def _parse_output(self, ctx: ConversationContext, doc: dict) -> None:
        detected = short(doc.get("language_code") or "")
        langs = [detected] if detected else []

        entries = ((doc.get("diarized_transcript") or {}).get("entries")) or []
        if entries:
            speaker_map: dict = {}
            for entry in entries:
                sid = str(entry.get("speaker_id", ""))
                if sid not in speaker_map:
                    n = len(speaker_map)
                    speaker_map[sid] = (
                        _SPEAKER_BY_ARRIVAL[n]
                        if n < len(_SPEAKER_BY_ARRIVAL) else "unknown")
                text = (entry.get("transcript") or "").strip()
                if text:
                    ctx.utterances.append(Utterance(
                        text=text, speaker=speaker_map[sid], languages=langs))
            return

        # diarization unavailable for this file: sentence-split the flat
        # transcript and let the diarization stage assign speakers
        for sentence in _SENTENCE_SPLIT.split((doc.get("transcript") or "").strip()):
            sentence = sentence.strip()
            if sentence:
                ctx.utterances.append(Utterance(text=sentence, languages=langs))


@register("asr", "sarvam_batch")
def _create(options, services):
    settings = services.get("settings") or load_settings()
    if not settings.sarvam_api_key:
        raise SarvamError(
            "Sarvam API key not configured — set the SARVAM_API_KEY "
            "environment variable"
        )
    languages = services.get("languages") or load_languages()
    enabled = [lang["code"] for lang in languages["enabled"]]
    model = options.get("model", "saaras:v3")

    def job_factory():
        from sarvamai import SarvamAI  # optional extra, imported lazily

        client = SarvamAI(api_subscription_key=settings.sarvam_api_key)
        return client.speech_to_text_job.create_job(
            model=model,
            mode=options.get("mode", "transcribe"),
            language_code=enabled[0] if len(enabled) == 1 else "unknown",
            with_diarization=True,
            # None = auto-detect. Forcing a count makes the diarizer split a
            # single voice into that many "speakers"; only pin it when the
            # deployment truly knows (e.g. always exactly agent + customer).
            num_speakers=options.get("num_speakers"),
        )

    return SarvamBatchASR(
        job_factory, services.get("vault"), model=model,
        timeout_s=options.get("timeout_s", 600),
    )
