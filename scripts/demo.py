"""End-to-end demo: one field conversation flows through the whole platform.

Simulates the field app (consent + upload), then runs the worker so the
conversation is transcribed, diarized, normalized, redacted, the audio
destroyed, and signals extracted via the FMCG taxonomy pack — and prints the
resulting schema-v1 insight, the audit trail, and the security guarantees
(hashed API keys, encrypted audio at rest, signed webhooks, tamper-evident
audit chain, tenant isolation, delete-on-demand).

Run from the repo root:  python scripts/demo.py
"""
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voclyp.ingestion import IngestionService
from voclyp.queueing import JobQueue
from voclyp.security import AudioVault
from voclyp.store import Store
from voclyp.worker import Worker

# A code-switched (Hindi/English) FMCG field visit. In Phase 0 the "audio" is a
# text stand-in; the pipeline shape is identical when real audio + ASR arrive.
CONVERSATION = """\
AGENT: Ramesh Kumar ji, namaste! New stock dikhane aaya hoon.
CUSTOMER: Aao. Purana stock abhi tak pada hai, not selling at all.
AGENT: Is mahine scheme hai, one free piece per dozen.
CUSTOMER: Other company is giving better margin, their scheme is bigger.
CUSTOMER: Ye naya pack bahut costly hai. Chota pack chahiye, sachet wala.
AGENT: Sachet next week aa raha hai. I will deliver by tomorrow ka order aaj le leta hoon.
CUSTOMER: Theek hai, book my order for 2 boxes. Mera number 98765 43210 hai.
AGENT: Done ji. I will call before delivery.
"""


def main():
    data_dir = Path(tempfile.mkdtemp(prefix="voclyp-demo-"))
    store = Store(data_dir / "voclyp.db")
    queue = JobQueue(data_dir / "queue.db")
    vault = AudioVault(b"demo-master-key-use-a-kms-in-prod")
    ingestion = IngestionService(store, queue, data_dir / "audio", vault)
    worker = Worker(store, queue, vault=vault)

    # -- platform setup: two tenants, isolated -------------------------------
    store.create_tenant("acme-fmcg", "Acme Consumer Goods", "fmcg")
    api_key = store.create_api_key("acme-fmcg", scopes=("ingest", "read"))
    endpoint_id, webhook_secret = store.add_webhook(
        "acme-fmcg", "log://acme-crm-connector",
        event_types=("conversation.insights.ready",),
    )
    store.create_tenant("zen-pharma", "Zen Pharma", "pharma")

    print("=== SECURITY SETUP ===")
    print(f"API key issued once: {api_key[:18]}... (scopes: ingest, read)")
    db_bytes = (data_dir / "voclyp.db").read_bytes()
    print(f"plaintext key in database: {api_key.split('_')[2].encode() in db_bytes}")
    print(f"auth check: {store.authenticate(api_key)}")
    print(f"webhook signing secret issued once: {webhook_secret[:14]}...")
    print(f"audio encrypted at rest: {vault.encrypted}")

    # -- field layer: consent captured, one-tap record, sync ----------------
    conv_id = ingestion.submit(
        tenant_id="acme-fmcg",
        audio_bytes=CONVERSATION.encode("utf-8"),
        metadata={
            "agent_id": "agent-042",
            "client_ref": "device7-rec-001",  # offline-sync idempotency
            "consent": {"captured": True, "customer_name": "Ramesh Kumar"},
        },
    )
    audio_file = data_dir / "audio" / "acme-fmcg" / f"{conv_id}.part0.audio"
    on_disk = audio_file.read_bytes()
    print(f"\nsubmitted conversation {conv_id}")
    print(f"audio on disk before processing: {audio_file.exists()}"
          f" (ciphertext, plaintext readable: {b'Ramesh' in on_disk})")

    # duplicate sync from the field device is absorbed, not reprocessed
    dup = ingestion.submit(
        "acme-fmcg", CONVERSATION.encode("utf-8"),
        {"agent_id": "agent-042", "client_ref": "device7-rec-001",
         "consent": {"captured": True, "customer_name": "Ramesh Kumar"}},
    )
    print(f"re-upload with same client_ref returned same id: {dup == conv_id}")

    # -- core pipeline -------------------------------------------------------
    processed = worker.drain()
    print(f"worker processed {processed} job(s)\n")

    doc = store.get_insight("acme-fmcg", conv_id)
    print("=== INSIGHT DOCUMENT (schema v1) ===")
    print(json.dumps(doc, indent=2, ensure_ascii=False))

    print("\n=== PRIVACY + AUDIT PROOF ===")
    print(f"audio still on disk: {audio_file.exists()}")
    for ev in store.audit_export("acme-fmcg", conv_id):
        print(f"  [{ev['ts']}] {ev['event']}: {ev['detail']}")
    ok, bad = store.verify_audit_chain("acme-fmcg")
    print(f"audit hash chain intact: {ok}")
    print(f"webhook deliveries: {store.deliveries_for('acme-fmcg', conv_id)}")
    print(f"delivery health: {store.delivery_stats('acme-fmcg')}")

    print("\n=== MLOPS: STAGE LATENCY (ms) ===")
    for row in store.metrics_summary("acme-fmcg"):
        print(f"  {row['stage']:<22} avg={row['avg_ms']:>7.2f}  max={row['max_ms']:>7.2f}")

    print("\n=== TENANT ISOLATION ===")
    print(f"zen-pharma sees acme's insight: {store.get_insight('zen-pharma', conv_id)}")

    print("\n=== DELETE-ON-DEMAND ===")
    print(f"deleted: {store.delete_conversation('acme-fmcg', conv_id)}")
    print(f"insight after delete: {store.get_insight('acme-fmcg', conv_id)}")

    print("\n=== TAMPER DETECTION ===")
    conn = sqlite3.connect(data_dir / "voclyp.db")
    conn.execute("UPDATE audit_log SET detail='nothing happened' WHERE event='audio_deleted'")
    conn.commit(); conn.close()
    ok, bad = store.verify_audit_chain("acme-fmcg")
    print(f"after editing an audit row directly in the DB -> chain intact: {ok}"
          f" (first bad entry id: {bad})")

    shutil.rmtree(data_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
