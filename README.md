# VoClyp

Field conversations in, structured insight out. VoClyp is not a single AI model —
it is a pipeline of specialized, swappable stages wrapped in a platform, organized
around three stable contracts:

1. **The gateway** — the one secure way in (`voclyp/gateway/`).
2. **The versioned insight schema** — the one stable way out (`contracts/insight-schema/v1/`).
3. **The taxonomy config** — industry behavior as data, not code (`configs/taxonomy/`).

External consumers integrate through the **event rails** (SYS-ARCH-02 §3–4):
thin signed webhook events (`contracts/event-envelope/v1/`) for triggering,
the authenticated REST API for fetching — never insight content in the pipe.

Read **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for the system diagrams,
**[docs/BUILD-MAP.md](docs/BUILD-MAP.md)** for what is built, where, and in what
order, and **[docs/SECURITY.md](docs/SECURITY.md)** for the threat model and
cybersecurity guardrails (hashed scoped API keys, encrypted audio at rest,
signed webhooks with SSRF protection, tamper-evident audit chain, rate limits,
Aadhaar/PAN/phone/email redaction, delete-on-demand).

## Quick start (no dependencies — Python 3.10+ stdlib only)

```powershell
# full end-to-end demo: consent -> ingest -> queue -> pipeline ->
# audio destroyed -> taxonomy-driven signals -> versioned insight
python scripts/demo.py

# tests
python -m unittest discover tests -v

# MLOps eval harness (regression gate, also run in CI)
python -m voclyp.mlops.eval --industry fmcg

# run the worker as a service
python -m voclyp.worker --data-dir data
```

The HTTP gateway is optional and needs extras:

```powershell
pip install fastapi uvicorn python-multipart
uvicorn voclyp.gateway.app:app
```

Or run the whole platform (gateway + worker) as one artifact:

```powershell
$env:VOCLYP_MASTER_KEY = "<from your KMS>"
docker compose up
```

### Swapping in real models

Pipeline composition lives in `configs/pipeline.json`. To use real Whisper ASR
instead of the stub (`pip install faster-whisper`), change one line:

```json
{ "role": "asr", "impl": "whisper", "options": { "model_size": "tiny" } }
```

The config loader rejects any composition that violates the privacy invariant
(redact → destroy audio → only then analyze).

### Production: Sarvam AI (Indian languages)

The production pipeline uses Sarvam's Saarika ASR (built for Indian languages
and code-mixed Hindi-English) and Sarvam translate:

```powershell
$env:SARVAM_API_KEY = "<your key>"
$env:VOCLYP_PIPELINE_CONFIG = "configs/pipeline.sarvam.json"
python scripts/sarvam_check.py recording.wav   # live smoke test (uses a few credits)
```

Language policy is data (`configs/languages.json`): Hindi + English enabled
today; enabling Tamil/Telugu/Bengali/... later is a config edit, not code.
Credit discipline is built in: already-English utterances skip the translate
call, and every provider call is metered per conversation
(`GET /v1/metrics` → `provider_usage`).

## Layout

```
contracts/insight-schema/v1/   the output contract (JSON Schema)
contracts/event-envelope/v1/   the webhook event contract (thin payloads)
configs/taxonomy/              base + per-industry signal packs (fmcg, pharma)
voclyp/
  gateway/                     API gateway: auth, rate limit, tenant routing,
                               webhook endpoint management + DLQ replay
  ingestion.py                 consent check, validate, store audio, enqueue
  queueing.py                  durable job queue (retries, dead-letter)
  pipeline/                    Stage contract + runner
    stages/                    asr, diarization, translation, redaction,
                               audio_delete, signals, summarize
  worker.py                    leases jobs, runs the pipeline, stores + emits
  store.py                     tenant-scoped insights/audit/consent/webhooks,
                               transactional outbox, delivery ledger
  events.py                    canonical event envelope (UUIDv7, sequence)
  delivery.py                  dispatcher: fan-out, signing, retries, DLQ
scripts/demo.py                one conversation, end to end
tests/                         end-to-end tests
```

Phase 0 status: every AI stage is a deterministic stub behind its final
interface; the privacy and security machinery is real — consent gate, PII
redaction (incl. Aadhaar/PAN), audio encrypted at rest and destroyed with a
hash-chained audit trail, salted-hashed API keys with scopes/expiry/revocation,
HMAC-signed webhooks with SSRF guarding, per-key rate limits, idempotent
offline-sync uploads, delete-on-demand, and structural tenant isolation.

The integration rails are also real: transactional outbox (an event exists iff
the insight write committed), thin signed event envelopes with UUIDv7 ids and
per-resource sequence numbers, at-least-once delivery with exponential backoff
+ jitter (1m → 5m → 30m → 2h → 12h, max 5 attempts), dead-letter queue with
one-click replay, auto-disable of flapping endpoints, dual-secret rotation
with zero-downtime overlap, and per-endpoint delivery-health stats.
