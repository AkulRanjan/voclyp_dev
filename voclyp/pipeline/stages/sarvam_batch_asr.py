"""Real ASR via Sarvam batch jobs — saaras:v3 with native speaker diarization."""
from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path

from ..base import Stage
from ..registry import register
from ...audio.prepare import merge_encrypted_chunks, normalize_for_sarvam, prepare_sarvam_file
from ...config import load_settings
from ...contracts import ConversationContext, Utterance
from ...languages import load_languages, short
from ...pipeline.speaker_cleanup import cleanup_conversation
from ...providers.sarvam import SarvamClient, SarvamError
from ...security import AudioVault

_SENTENCE_SPLIT = re.compile(r"(?<=[।.!?])\s+")


class SarvamBatchASR(Stage):
    name = "asr"

    def __init__(self, job_factory, vault: AudioVault = None,
                 model: str = "saaras:v3", timeout_s: int = 900,
                 num_speakers: int = 2, relabel_speakers: bool = True,
                 voiceprint_threshold: float = 0.65,
                 sync_client: SarvamClient | None = None,
                 language_code: str = "hi-IN",
                 sync_model: str = "saarika:v2.5"):
        self.job_factory = job_factory
        self.vault = vault or AudioVault()
        self.timeout_s = timeout_s
        self.num_speakers = num_speakers
        self.relabel_speakers = relabel_speakers
        self.voiceprint_threshold = voiceprint_threshold
        self.sync_client = sync_client
        self.language_code = language_code
        self.sync_model = sync_model
        self.version = f"sarvam-batch-{model}"

    def run(self, ctx: ConversationContext) -> None:
        workdir = Path(tempfile.mkdtemp(prefix="voclyp-stt-"))
        try:
            merged = merge_encrypted_chunks(self.vault, ctx.audio_paths)
            upload_path = prepare_sarvam_file(workdir, merged)

            try:
                self._run_batch(ctx, upload_path)
            except SarvamError as exc:
                if not self.sync_client:
                    raise
                self._run_sync_fallback(ctx, upload_path.read_bytes(), exc)

            if self.relabel_speakers and ctx.utterances:
                cleanup_conversation(
                    ctx, merged, ctx.agent_voiceprint or None,
                    threshold=self.voiceprint_threshold,
                )
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    def _run_batch(self, ctx: ConversationContext, upload_path: Path) -> None:
        job = self.job_factory()
        job.upload_files(file_paths=[str(upload_path)])
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

        outdir = upload_path.parent / "out"
        job.download_outputs(output_dir=str(outdir))
        ctx.provider_usage["sarvam:speech-to-text-job"] = (
            ctx.provider_usage.get("sarvam:speech-to-text-job", 0) + 1
        )
        for path in sorted(outdir.rglob("*.json")):
            self._parse_output(ctx, json.loads(path.read_text(encoding="utf-8")))

    def _run_sync_fallback(self, ctx: ConversationContext, audio: bytes,
                           batch_err: SarvamError) -> None:
        """Batch rejected the file (common with iPhone m4a) — use sync Saarika."""
        normalized, filename = normalize_for_sarvam(audio)
        resp = self.sync_client.speech_to_text(
            normalized,
            filename=filename,
            model=self.sync_model,
            language_code=self.language_code,
        )
        ctx.provider_usage["sarvam:speech-to-text"] = (
            ctx.provider_usage.get("sarvam:speech-to-text", 0) + 1
        )
        ctx.provider_usage["sarvam:batch-fallback"] = 1
        detected = short(resp.get("language_code") or "")
        if detected and detected not in ctx.detected_languages:
            ctx.detected_languages.append(detected)
        langs = [detected] if detected else []
        transcript = (resp.get("transcript") or "").strip()
        if not transcript:
            raise batch_err
        for sentence in _SENTENCE_SPLIT.split(transcript):
            sentence = sentence.strip()
            if sentence:
                ctx.utterances.append(Utterance(text=sentence, languages=langs))

    def _parse_output(self, ctx: ConversationContext, doc: dict) -> None:
        detected = short(doc.get("language_code") or "")
        if detected and detected not in ctx.detected_languages:
            ctx.detected_languages.append(detected)
        langs = [detected] if detected else []

        entries = ((doc.get("diarized_transcript") or {}).get("entries")) or []
        if entries:
            for entry in entries:
                text = (entry.get("transcript") or "").strip()
                if not text:
                    continue
                ctx.utterances.append(Utterance(
                    text=text,
                    speaker="unknown",
                    speaker_id=str(entry.get("speaker_id", "")),
                    start_time=float(entry.get("start_time_seconds") or 0),
                    end_time=float(entry.get("end_time_seconds") or 0),
                    languages=langs,
                ))
            return

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
    lang = options.get("language_code")
    if not lang:
        lang = next((c for c in enabled if c.startswith("hi")), enabled[0] if len(enabled) == 1 else "hi-IN")
    model = options.get("model", "saaras:v3")
    num_speakers = int(options.get("num_speakers", 2))

    def job_factory():
        from sarvamai import SarvamAI

        client = SarvamAI(api_subscription_key=settings.sarvam_api_key)
        return client.speech_to_text_job.create_job(
            model=model,
            mode=options.get("mode", "codemix"),
            language_code=lang,
            with_diarization=True,
            num_speakers=num_speakers,
        )

    return SarvamBatchASR(
        job_factory,
        services.get("vault"),
        model=model,
        timeout_s=int(options.get("timeout_s", 900)),
        num_speakers=num_speakers,
        relabel_speakers=options.get("relabel_speakers", True),
        voiceprint_threshold=float(options.get("voiceprint_threshold", 0.65)),
        sync_client=SarvamClient(settings.sarvam_api_key),
        language_code=lang,
        sync_model=options.get("sync_fallback_model", "saarika:v2.5"),
    )
