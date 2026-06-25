"""Regenerate the latest sleep-company insight(s) from the stored transcript.

Re-runs signal extraction + the grounded visit-notes summarizer over transcripts
already saved in the DB and writes the refreshed insight back, so the app shows
the corrected output after a pipeline change (no re-recording needed).

    py scripts/reprocess_insights.py        # newest insight only
    py scripts/reprocess_insights.py 5      # the 5 newest insights
"""
import io
import json
import os
import sqlite3
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for line in open(".env", encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

from voclyp.catalog import load_catalog
from voclyp.config import load_settings
from voclyp.contracts import ConversationContext, Utterance, score_conversation
from voclyp.pipeline.stages.signals import TaxonomySignalExtraction
from voclyp.pipeline.stages.sarvam_visit_notes import SarvamVisitNotes
from voclyp.providers.sarvam import SarvamClient
from voclyp.store import Store
from voclyp.taxonomy import load_taxonomy

DB = "data/sleep-company/voclyp.db"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 1

con = sqlite3.connect(DB)
ids = [r[0] for r in con.execute(
    "SELECT conversation_id FROM insights ORDER BY created_at DESC LIMIT ?", (N,)
).fetchall()]
con.close()

store = Store(DB)
tax = load_taxonomy("sleep_company")
cat = load_catalog("sleep_company")
settings = load_settings()

for cid in ids:
    con = sqlite3.connect(DB)
    body = con.execute(
        "SELECT body FROM insights WHERE conversation_id=?", (cid,)
    ).fetchone()[0]
    con.close()
    doc = json.loads(body)
    tenant = doc["tenant_id"]

    ctx = ConversationContext(tenant_id=tenant, conversation_id=cid,
                              industry=doc.get("industry", "sleep_company"),
                              audio_paths=[])
    ctx.utterances = [
        Utterance(text=t.get("text") or "",
                  normalized_text=t.get("normalized_text") or "",
                  speaker=t.get("speaker") or "unknown")
        for t in (doc.get("transcript") or [])
    ]
    TaxonomySignalExtraction(tax).run(ctx)
    SarvamVisitNotes(SarvamClient(settings.sarvam_api_key), tax, catalog=cat).run(ctx)

    doc["signals"] = [
        {"type": s.type, "subtype": s.subtype, "speaker": s.speaker,
         "quote": s.quote, "turn": s.turn, "confidence": s.confidence}
        for s in ctx.signals
    ]
    doc["scoring"] = score_conversation(ctx.signals)
    doc["summary"] = {"text": ctx.summary_text, "fields": ctx.summary_fields}

    store.save_insight(tenant, cid, doc)
    print(f"[OK] {cid}: wants={ctx.summary_fields.get('customer_wants')} "
          f"objections={ctx.summary_fields.get('objections')} "
          f"llm_error={ctx.summary_fields.get('llm_error')}")
print("done")
