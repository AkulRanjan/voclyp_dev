"""Orphan sweep — force-cleanup of stranded conversations (DPDP safety net).

A conversation should march consent_logged -> audio_uploaded -> transcribing ->
extracting -> dispatching -> purged. If anything stalls (worker crash, Sarvam /
Bedrock outage, failed S3 PUT), the row is left non-terminal while its raw audio
may still sit in S3 past the 2-hour promise. This cron scans for any
conversation stuck in a non-purged state older than the erase window, force-
deletes the S3 object, and flags the record ``error_purged`` with a
high-priority alert.

Run as a cron / k8s CronJob:

    python -m voclyp.enterprise.erasure.orphan_sweep            # one shot
    python -m voclyp.enterprise.erasure.orphan_sweep --loop 300 # every 5 min

Uses the async psycopg pool when SUPABASE_DB_URL is set (iterating every tenant
schema), otherwise the synchronous SQLite mirror.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime

from ...env import load_dotenv
from ..config import load_enterprise_settings
from ..obs import alert, get_logger
from ..storage.s3 import open_audio_store
from ..store import open_async_store, open_store

_log = get_logger("orphan_sweep")


def _cutoff_iso(seconds: int) -> str:
    return (datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(seconds=seconds)).isoformat()


async def sweep_once(settings=None) -> dict:
    settings = settings or load_enterprise_settings()
    audio_store = open_audio_store(settings)
    cutoff = _cutoff_iso(settings.erase_after_seconds)
    async_store = open_async_store(settings)

    if async_store is not None:
        return await _sweep_postgres(async_store, audio_store, cutoff)
    return _sweep_local(open_store(settings), audio_store, cutoff)


async def _sweep_postgres(store, audio_store, cutoff) -> dict:  # pragma: no cover - needs PG
    swept = 0
    schemas = await store.list_tenant_schemas()
    for schema in schemas:
        orphans = await store.due_orphans(cutoff, schema=schema)
        for conv in orphans:
            await _purge_one_async(store, audio_store, schema, conv)
            swept += 1
    await store.close()
    result = {"backend": "postgres", "schemas": len(schemas), "swept": swept}
    _log.info("orphan sweep complete", extra={"fields": result})
    return result


async def _purge_one_async(store, audio_store, schema, conv):  # pragma: no cover - needs PG
    loop = asyncio.get_running_loop()
    try:
        # S3 delete is blocking (boto3); keep the event loop responsive
        await loop.run_in_executor(None, audio_store.delete, conv["s3_key"])
    except Exception as exc:
        _log.error("orphan S3 delete failed", extra={"fields": {
            "conversation_id": conv["id"], "schema": schema, "error": str(exc)}})
    await store.mark_error_purged(
        conv["id"], schema=schema,
        detail=f"orphan force-purged from state={conv.get('state')}")
    alert(_log, "stranded conversation force-purged",
          conversation_id=conv["id"], schema=schema, prior_state=conv.get("state"),
          s3_key=conv["s3_key"])


def _sweep_local(store, audio_store, cutoff) -> dict:
    orphans = store.due_orphans(cutoff)
    swept = 0
    for conv in orphans:
        try:
            audio_store.delete(conv["s3_key"])
        except Exception as exc:
            _log.error("orphan S3 delete failed", extra={"fields": {
                "conversation_id": conv["id"], "error": str(exc)}})
        store.mark_error_purged(
            conv["id"], detail=f"orphan force-purged from state={conv.get('state')}")
        alert(_log, "stranded conversation force-purged",
              conversation_id=conv["id"], prior_state=conv.get("state"),
              s3_key=conv["s3_key"])
        swept += 1
    result = {"backend": "local", "swept": swept}
    _log.info("orphan sweep complete", extra={"fields": result})
    return result


async def _run(loop_seconds: int | None) -> None:
    load_dotenv()
    settings = load_enterprise_settings()
    if loop_seconds:
        while True:
            await sweep_once(settings)
            await asyncio.sleep(loop_seconds)
    else:
        await sweep_once(settings)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="VoClyp orphan conversation sweep")
    parser.add_argument("--loop", type=int, default=0,
                        help="run forever, sleeping N seconds between sweeps")
    args = parser.parse_args(argv)
    asyncio.run(_run(args.loop or None))


if __name__ == "__main__":
    main()
