"""Stage implementations. Importing this package registers every
implementation with the pipeline registry; pipeline composition itself is
configuration (configs/pipeline.json), not imports."""
from .asr import StubASR
from .diarization import StubDiarization
from .translation import StubTranslation
from .redaction import RegexRedaction
from .audio_delete import AudioDeletion
from .signals import TaxonomySignalExtraction
from .summarize import TaxonomySummarization
from . import whisper_asr  # registers asr:whisper (lazy heavy imports)
from . import sarvam_asr  # registers asr:sarvam
from . import sarvam_translate  # registers lang_id_translation:sarvam

__all__ = [
    "StubASR", "StubDiarization", "StubTranslation", "RegexRedaction",
    "AudioDeletion", "TaxonomySignalExtraction", "TaxonomySummarization",
]
