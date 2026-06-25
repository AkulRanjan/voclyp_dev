"""Voice enrollment + speaker fingerprinting for diarization."""
from .fingerprint import (
    MODEL_ACOUSTIC,
    MODEL_FALLBACK,
    embed,
    merge,
    similarity,
)

__all__ = ["embed", "similarity", "merge", "MODEL_ACOUSTIC", "MODEL_FALLBACK"]
