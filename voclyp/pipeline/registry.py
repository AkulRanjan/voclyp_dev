"""Stage registry and pipeline configuration.

Pipeline composition is data, not code: configs/pipeline.json lists the stages
by (role, impl), and implementations register themselves here. Swapping the
stub ASR for a real model is a one-line config change.

The loader refuses any composition that violates the privacy invariant:
redaction must precede audio deletion, and audio deletion must precede
analysis — a misconfigured pipeline cannot be built, let alone run.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .base import PipelineRunner

_REGISTRY: dict = {}

REQUIRED_ROLES = (
    "asr", "pii_redaction", "audio_deletion", "signal_extraction", "summarization",
)
# Roles that, when present, must appear in this relative order.
_PRIVACY_ORDER = [
    "asr", "pii_redaction", "audio_deletion", "signal_extraction", "summarization",
]

DEFAULT_PIPELINE_CONFIG = (
    Path(__file__).resolve().parents[2] / "configs" / "pipeline.json"
)


class PipelineConfigError(Exception):
    pass


def register(role: str, impl: str):
    """Decorator: register a factory ``(options, services) -> Stage``."""
    def decorator(factory):
        _REGISTRY[(role, impl)] = factory
        return factory
    return decorator


def _ensure_implementations_loaded():
    from . import stages  # noqa: F401  (import side effect: registration)


def available() -> list:
    _ensure_implementations_loaded()
    return sorted(_REGISTRY)


def load_pipeline_config(path=None) -> dict:
    path = Path(
        path or os.environ.get("VOCLYP_PIPELINE_CONFIG") or DEFAULT_PIPELINE_CONFIG
    )
    config = json.loads(path.read_text(encoding="utf-8"))
    validate_pipeline_config(config)
    return config


def validate_pipeline_config(config: dict) -> None:
    _ensure_implementations_loaded()
    specs = config.get("stages") or []
    roles = [spec.get("role") for spec in specs]

    for spec in specs:
        key = (spec.get("role"), spec.get("impl"))
        if key not in _REGISTRY:
            raise PipelineConfigError(
                f"unknown stage {key}; available: {sorted(_REGISTRY)}"
            )
    if len(set(roles)) != len(roles):
        raise PipelineConfigError("duplicate stage roles in pipeline config")
    for role in REQUIRED_ROLES:
        if role not in roles:
            raise PipelineConfigError(f"pipeline config is missing required role '{role}'")

    positions = [roles.index(r) for r in _PRIVACY_ORDER if r in roles]
    if positions != sorted(positions):
        raise PipelineConfigError(
            "pipeline order violates the privacy invariant: expected "
            + " -> ".join(_PRIVACY_ORDER)
        )


def build_pipeline(config: dict, services: dict) -> PipelineRunner:
    """services: shared dependencies stages may need (vault, taxonomy)."""
    validate_pipeline_config(config)
    stages = [
        _REGISTRY[(spec["role"], spec["impl"])](spec.get("options", {}), services)
        for spec in config["stages"]
    ]
    return PipelineRunner(stages)
