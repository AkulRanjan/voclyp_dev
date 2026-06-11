"""Language policy loading.

Which languages the platform accepts and what it normalizes to lives in
configs/languages.json — data, not code, exactly like the taxonomy. Today
that's Hindi + English; adding Tamil later is a config edit plus eval
coverage, no redeploy of stage code.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

DEFAULT_LANGUAGES_CONFIG = (
    Path(__file__).resolve().parents[1] / "configs" / "languages.json"
)
_CODE = re.compile(r"^[a-z]{2}-[A-Z]{2}$")


class LanguageConfigError(Exception):
    pass


def load_languages(path=None) -> dict:
    path = Path(
        path or os.environ.get("VOCLYP_LANGUAGES_CONFIG") or DEFAULT_LANGUAGES_CONFIG
    )
    config = json.loads(path.read_text(encoding="utf-8"))
    enabled = config.get("enabled") or []
    if not enabled:
        raise LanguageConfigError("languages config has no enabled languages")
    for lang in enabled:
        if not _CODE.match(lang.get("code", "")):
            raise LanguageConfigError(f"bad language code: {lang!r}")
    if not _CODE.match(config.get("normalize_to", "")):
        raise LanguageConfigError("languages config needs a 'normalize_to' code")
    return config


def short(code: str) -> str:
    """'hi-IN' -> 'hi' (the form used in the insight document)."""
    return (code or "").split("-")[0].lower()
