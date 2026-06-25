"""Offline no-network sink shared by the mock channel clients.

Every mock ``send`` appends one JSON line to data/enterprise/sinks/<channel>.jsonl
so tests and local runs can assert exactly what *would* have been delivered.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from ...contracts import utcnow

_LOCK = threading.Lock()


def record(local_dir, channel: str, entry: dict) -> dict:
    out = dict(entry)
    out["recorded_at"] = utcnow()
    path = Path(local_dir) / "sinks" / f"{channel}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(out, ensure_ascii=False) + "\n")
    return out
