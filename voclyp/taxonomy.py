"""Taxonomy config loading.

Industry behavior lives in configs/taxonomy/*.json as data, not code.
An industry pack extends the universal base: its patterns are appended to the
base patterns per signal type, and its summary fields are added to the base's.
Onboarding a new industry means adding one JSON file here.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_CONFIG_DIR = Path(
    os.environ.get("VOCLYP_TAXONOMY_DIR")
    or Path(__file__).resolve().parents[1] / "configs" / "taxonomy"
)

UNIVERSAL_SIGNAL_TYPES = (
    "objection", "intent", "demand", "competitor_mention", "price_reaction", "promise",
)


class TaxonomyError(Exception):
    pass


def _load_pack(industry: str, config_dir: Path) -> dict:
    path = config_dir / f"{industry}.json"
    if not path.exists():
        raise TaxonomyError(f"no taxonomy pack for industry '{industry}' at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_taxonomy(industry: str, config_dir=None) -> dict:
    """Return the merged (base + industry) taxonomy for an industry."""
    config_dir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
    pack = _load_pack(industry, config_dir)

    if pack.get("extends"):
        base = _load_pack(pack["extends"], config_dir)
    elif industry != "base":
        base = _load_pack("base", config_dir)
    else:
        base = {"signals": {}, "summary_fields": [], "version": pack.get("version", "1.0")}

    signals = {t: {"patterns": []} for t in UNIVERSAL_SIGNAL_TYPES}
    for source in (base, pack):
        for sig_type, spec in source.get("signals", {}).items():
            if sig_type not in signals:
                raise TaxonomyError(
                    f"'{sig_type}' is not a universal signal type {UNIVERSAL_SIGNAL_TYPES}"
                )
            signals[sig_type]["patterns"].extend(spec.get("patterns", []))

    summary_fields = list(base.get("summary_fields", [])) + list(pack.get("summary_fields", []))
    version = f"base-{base.get('version', '?')}+{industry}-{pack.get('version', '?')}"

    return {
        "industry": industry,
        "version": version,
        "signals": signals,
        "summary_fields": summary_fields,
    }
