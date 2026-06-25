"""DPDP-grade consent capture."""
from __future__ import annotations

from .service import ConsentError, ConsentService, canonical_artifact, sha256_hex

__all__ = ["ConsentError", "ConsentService", "canonical_artifact", "sha256_hex"]
