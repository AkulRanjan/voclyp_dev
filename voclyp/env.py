"""Tiny .env loader (stdlib only) — no python-dotenv dependency.

Secrets still belong in a secrets manager in production; this just makes local
development ergonomic: drop SARVAM_API_KEY / AWS creds in a .env at the repo
root and every entrypoint (gateway, worker, run scripts) picks them up.

Existing environment variables always win, so a real injected secret is never
shadowed by a stray .env line.
"""
from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: str | Path | None = None) -> dict:
    """Load KEY=VALUE lines from a .env file into os.environ (without
    overriding values already set). Returns the keys it applied."""
    if path is None:
        # repo root is two levels up from this file (voclyp/env.py)
        path = Path(__file__).resolve().parents[1] / ".env"
    path = Path(path)
    applied: dict = {}
    if not path.is_file():
        return applied
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            applied[key] = value
    return applied
