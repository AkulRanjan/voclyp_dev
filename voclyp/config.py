"""Central, environment-driven configuration.

Secrets never live in code or config files — they arrive via environment
variables (in production: injected from a secrets manager / KMS). Everything
here has a safe default and can be tightened per deployment.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    data_dir: str = "data"
    # ingestion guardrails
    max_upload_bytes: int = 100 * 1024 * 1024
    max_metadata_field_len: int = 256
    # long audio is split into chunks of roughly this size before queueing
    chunk_bytes: int = 10 * 1024 * 1024
    # gateway rate limiting (per API key)
    rate_limit_requests: int = 60
    rate_limit_window_s: float = 60.0
    # VOCLYP_MASTER_KEY enables audio encryption at rest (empty = disabled,
    # and the audit log will say so). Production: a 32+ byte random value
    # sourced from a KMS, never a human-chosen passphrase.
    master_key: bytes = b""
    # webhooks must be https and resolve to public addresses unless this is
    # explicitly relaxed for local development.
    allow_insecure_webhooks: bool = False
    # public origin of the REST API, prepended to fetch_url in event payloads
    # (empty = relative paths, fine for tests and single-host deployments).
    public_base_url: str = ""
    # Sarvam AI subscription key (SARVAM_API_KEY) — required only when the
    # pipeline config selects sarvam implementations.
    sarvam_api_key: str = ""


def load_settings() -> Settings:
    env = os.environ
    return Settings(
        data_dir=env.get("VOCLYP_DATA_DIR", "data"),
        max_upload_bytes=int(env.get("VOCLYP_MAX_UPLOAD_BYTES", 100 * 1024 * 1024)),
        max_metadata_field_len=int(env.get("VOCLYP_MAX_METADATA_FIELD_LEN", 256)),
        chunk_bytes=int(env.get("VOCLYP_CHUNK_BYTES", 10 * 1024 * 1024)),
        rate_limit_requests=int(env.get("VOCLYP_RATE_LIMIT", 60)),
        rate_limit_window_s=float(env.get("VOCLYP_RATE_WINDOW_S", 60)),
        master_key=env.get("VOCLYP_MASTER_KEY", "").encode("utf-8"),
        allow_insecure_webhooks=env.get("VOCLYP_ALLOW_INSECURE_WEBHOOKS") == "1",
        public_base_url=env.get("VOCLYP_PUBLIC_BASE_URL", ""),
        sarvam_api_key=env.get("SARVAM_API_KEY", ""),
    )
