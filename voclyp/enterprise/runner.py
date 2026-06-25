"""Standalone worker entrypoints.

In production each worker runs as its own process consuming from Kafka:

    python -m voclyp.enterprise.runner asr
    python -m voclyp.enterprise.runner extractor
    python -m voclyp.enterprise.runner routing
    python -m voclyp.enterprise.runner erasure   # periodic sweep

With the in-memory bus (no Kafka configured) ``asr``/``extractor``/``routing``
have nothing to consume — the cascade runs in-process via the gateway — so
those become no-ops, while ``erasure`` still runs its periodic sweep.
"""
from __future__ import annotations

import sys
import time

from ..env import load_dotenv
from .events import topics
from .events.bus import KafkaBus
from .pipeline import build_enterprise

_CONSUMERS = {
    "asr": (lambda p: p.asr.handle, [topics.AUDIO_RAW_UPLOADED]),
    "extractor": (lambda p: p.extractor.handle, [topics.TRANSCRIPT_READY]),
    "routing": (lambda p: p.dispatcher.handle, [topics.INSIGHT_EXTRACTED]),
}


def run_worker(name: str, poll_seconds: float = 15.0) -> None:
    load_dotenv()
    pipeline = build_enterprise(dispatch=False)

    if name == "erasure":
        while True:
            result = pipeline.erasure.run_once()
            print(f"[erasure] {result}", flush=True)
            pipeline.dispatcher.process_due()
            time.sleep(poll_seconds)

    if name not in _CONSUMERS:
        raise SystemExit(f"unknown worker '{name}'; "
                         f"choose from {list(_CONSUMERS) + ['erasure']}")

    handler_factory, sub_topics = _CONSUMERS[name]
    handler = handler_factory(pipeline)

    if isinstance(pipeline.bus, KafkaBus):  # pragma: no cover - needs broker
        print(f"[{name}] consuming {sub_topics} from Kafka", flush=True)
        pipeline.bus.consume(sub_topics, handler, group_id=f"voclyp-{name}")
    else:
        print(f"[{name}] in-memory bus configured — cascade runs in-process; "
              f"nothing to consume. Idle.", flush=True)


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        raise SystemExit("usage: python -m voclyp.enterprise.runner "
                         "<asr|extractor|routing|erasure>")
    run_worker(argv[0])


if __name__ == "__main__":
    main()
