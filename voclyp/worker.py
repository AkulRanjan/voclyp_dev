"""Pipeline worker: leases jobs from the queue and runs the core pipeline.

The pipeline's composition comes from configs/pipeline.json via the stage
registry — swapping a stub for a real model is a config change. The loader
enforces the privacy invariant (redact, destroy audio, only then analyze), so
a misordered pipeline cannot be constructed.

Runnable as a service:  python -m voclyp.worker --data-dir data
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from .config import Settings, load_settings
from .contracts import ConversationContext, build_insight
from .delivery import Dispatcher
from .languages import load_languages
from .pipeline import PipelineRunner
from .pipeline.registry import build_pipeline, load_pipeline_config
from .queueing import JobQueue
from .security import AudioVault
from .store import Store
from .taxonomy import load_taxonomy


class Worker:
    def __init__(self, store: Store, queue: JobQueue, taxonomy_dir=None,
                 vault: AudioVault = None, pipeline_config: dict = None,
                 settings: Settings = None):
        self.store = store
        self.queue = queue
        self.taxonomy_dir = taxonomy_dir
        self.vault = vault or AudioVault()
        self.pipeline_config = pipeline_config or load_pipeline_config()
        self.settings = settings or load_settings()
        # Phase 0 co-locates the dispatcher with the worker; it is its own
        # service once a real broker arrives (the seam is the outbox table).
        self.dispatcher = Dispatcher(store, settings=self.settings)
        self._pipelines: dict = {}

    def _pipeline_for(self, industry: str) -> PipelineRunner:
        if industry not in self._pipelines:
            services = {
                "vault": self.vault,
                "taxonomy": load_taxonomy(industry, self.taxonomy_dir),
                "settings": self.settings,
                "languages": load_languages(),
            }
            self._pipelines[industry] = build_pipeline(self.pipeline_config, services)
        return self._pipelines[industry]

    def process_one(self):
        """Process a single queued conversation; returns the insight or None."""
        job = self.queue.dequeue()
        if job is None:
            return None
        tenant_id, conversation_id = job["tenant_id"], job["conversation_id"]
        payload = job["payload"]
        try:
            ctx = ConversationContext(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                industry=payload["industry"],
                audio_paths=list(payload["audio_paths"]),
                agent_id=payload.get("agent_id", ""),
                consent_captured=True,  # enforced at ingestion
                customer_name=payload.get("customer_name", ""),
            )
            self._pipeline_for(ctx.industry).run(ctx)

            doc = build_insight(ctx)
            # transactional outbox: insight + event commit together, then the
            # dispatcher (not this worker) owns signing, retries, and the DLQ
            self.store.save_insight_with_event(tenant_id, conversation_id, doc)
            self.store.add_metrics(tenant_id, conversation_id, ctx.stage_timings_ms)
            self.store.add_usage(tenant_id, conversation_id, ctx.provider_usage)
            self.store.audit(tenant_id, conversation_id, "audio_deleted",
                             ctx.audio_deleted_at or "")
            self.store.audit(tenant_id, conversation_id, "insight_stored",
                             f"signals={len(ctx.signals)}")
            self.dispatcher.run_once()
            self.queue.complete(job["id"])
            return doc
        except Exception as exc:
            status = self.queue.fail(job["id"], job["attempts"])
            self.store.audit(tenant_id, conversation_id, "processing_failed",
                             f"{type(exc).__name__}: {exc} -> {status}")
            if status == "dead":
                raise
            return None

    def drain(self) -> int:
        """Process until the queue is empty; returns how many succeeded."""
        n = 0
        while True:
            doc = self.process_one()
            if doc is None and not self.queue.counts().get("pending"):
                return n
            if doc is not None:
                n += 1

    def run_forever(self, poll_interval: float = 2.0):
        print(f"voclyp worker started (pipeline {self.pipeline_config['version']}, "
              f"encrypted_at_rest={self.vault.encrypted})")
        while True:
            try:
                doc = self.process_one()
            except Exception as exc:
                # dead-lettered job: logged + audited, keep serving the queue
                print(f"job dead-lettered: {type(exc).__name__}: {exc}")
                doc = None
            if doc is None and not self.queue.counts().get("pending"):
                self.dispatcher.run_once()  # due webhook retries fire while idle
                time.sleep(poll_interval)


def main(argv=None):
    parser = argparse.ArgumentParser(description="VoClyp pipeline worker")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--once", action="store_true",
                        help="drain the queue and exit")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    args = parser.parse_args(argv)

    settings = load_settings()
    data_dir = Path(args.data_dir or settings.data_dir)
    worker = Worker(
        Store(data_dir / "voclyp.db"),
        JobQueue(data_dir / "queue.db"),
        vault=AudioVault(settings.master_key),
    )
    if args.once:
        print(f"processed {worker.drain()} job(s)")
    else:
        try:
            worker.run_forever(args.poll_interval)
        except KeyboardInterrupt:
            print("worker stopped")


if __name__ == "__main__":
    main()
