"""Real ASR implementation backed by faster-whisper.

This is the first real model swapped in behind the Stage interface — enabling
it is a config change (``{"role": "asr", "impl": "whisper"}``), nothing else
in the pipeline moves. Whisper handles real audio (wav/mp3/m4a chunks) with
automatic language detection; Hindi and code-switched speech work, though a
dedicated Indic ASR is the Phase-2 target for the long tail of dialects.

The import is lazy so the platform never requires the model libraries unless
this implementation is actually configured.
"""
from __future__ import annotations

import os
import tempfile

from ..base import Stage
from ..registry import register
from ...contracts import ConversationContext, Utterance
from ...security import AudioVault


class WhisperASR(Stage):
    name = "asr"

    def __init__(self, vault: AudioVault = None, model_size: str = "tiny",
                 device: str = "cpu", compute_type: str = "int8"):
        try:
            import faster_whisper
        except ImportError as exc:
            raise RuntimeError(
                "asr impl 'whisper' requires the 'faster-whisper' package "
                "(pip install faster-whisper)"
            ) from exc
        self.vault = vault or AudioVault()
        self.model_size = model_size
        self.version = f"faster-whisper-{faster_whisper.__version__}/{model_size}"
        self._model = None
        self._device, self._compute_type = device, compute_type

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                self.model_size, device=self._device, compute_type=self._compute_type
            )
        return self._model

    def run(self, ctx: ConversationContext) -> None:
        model = self._load()
        for path in ctx.audio_paths:
            data = self.vault.read(path)
            # The model wants a file path; decrypted bytes live in a temp file
            # only for the duration of transcription.
            fd, tmp = tempfile.mkstemp(suffix=".audio")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(data)
                segments, info = model.transcribe(tmp, vad_filter=True)
                for seg in segments:
                    text = seg.text.strip()
                    if text:
                        ctx.utterances.append(
                            Utterance(text=text, languages=[info.language])
                        )
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)


@register("asr", "whisper")
def _create(options, services):
    return WhisperASR(
        services.get("vault"),
        model_size=options.get("model_size", "tiny"),
        device=options.get("device", "cpu"),
        compute_type=options.get("compute_type", "int8"),
    )
