# VoClyp — Build Map

This is the map of what is being built, in what order, and where each piece of the
described architecture lands in this repository.

## Guiding rule

Everything is organized around the **three fixed contracts**. They are built first,
as data and interfaces, and everything else is allowed to change behind them:

| Contract | What it is | Where it lives |
|---|---|---|
| 1. The gateway | One secure way in: auth, rate limits, tenant routing | `voclyp/gateway/` |
| 2. The insight schema | One stable, versioned way out | `contracts/insight-schema/v1/` + `voclyp/contracts.py` |
| 3. The taxonomy config | One way to change industry behavior without code | `configs/taxonomy/*.json` + `voclyp/taxonomy.py` |

## Component → repository map

| Architecture component | Repo location | Phase-0 implementation |
|---|---|---|
| Field app / SDK | *(external — talks only to the gateway)* | simulated by `scripts/demo.py` |
| Consent capture | `voclyp/ingestion.py` (required on submit) | enforced + logged |
| API gateway (auth, rate limit, tenant routing) | `voclyp/gateway/app.py` | FastAPI app, API-key → tenant, token-bucket rate limit |
| Ingestion service (validate, chunk, enqueue) | `voclyp/ingestion.py` | validate + enqueue (chunking stubbed) |
| Processing queue | `voclyp/queueing.py` | SQLite-backed durable job queue with retries |
| ASR (120+ langs, code-switching) | `voclyp/pipeline/stages/asr.py` | stub: reads stand-in transcript, flags code-switching |
| Diarization (agent vs customer) | `voclyp/pipeline/stages/diarization.py` | stub: speaker labeling |
| Language ID + translation | `voclyp/pipeline/stages/translation.py` | stub: tiny Hindi→English normalizer, keeps original |
| PII redaction | `voclyp/pipeline/stages/redaction.py` | regex redaction (phones, emails, consented name) |
| **Audio auto-delete + audit** | `voclyp/pipeline/stages/audio_delete.py` | real: deletes file, writes audit log entry |
| Signal extraction (the brain) | `voclyp/pipeline/stages/signals.py` | taxonomy-driven pattern matching — fully config-driven |
| Summarization (industry fields) | `voclyp/pipeline/stages/summarize.py` | taxonomy-driven field filling |
| Insight store (per-tenant, versioned) | `voclyp/store.py` | SQLite, tenant_id required on every query |
| Webhooks / events | `voclyp/delivery.py` | dispatcher with delivery log |
| Insights API (REST) | `voclyp/gateway/app.py` | pull endpoints |
| Connectors (CRM / BI) | *(Phase 3)* | — |
| Dashboards | *(Phase 3)* | — |
| Auth + multi-tenancy | `voclyp/store.py` (api_keys) + gateway | API keys, isolation enforced in store layer |
| Compliance (consent log, delete-on-demand, audit export) | `voclyp/store.py` + gateway DELETE endpoint | implemented |
| MLOps (eval harness, monitoring) | *(Phase 2)* | stage versions recorded per insight now |

## Phases

### Phase 0 — Contracts + walking skeleton  ← *being built now*
A complete, runnable, end-to-end system in which every AI stage is a deterministic
stub behind the real interface it will eventually have. The point is that the
**shape** of the system is final even though every model inside it is fake.

Deliverables:
- The three contracts (insight schema v1, taxonomy config format + FMCG/pharma packs, gateway API).
- Pipeline runner with six swappable stages + audio-deletion stage.
- Durable queue, per-tenant SQLite insight store, audit/consent logs.
- Webhook delivery, delete-on-demand.
- `scripts/demo.py`: a full conversation flows in one end and versioned insight JSON comes out the other, with the "audio" provably deleted.
- End-to-end test.

### Phase 1 — Real ingestion path  ← *done*
- ✅ Pipeline composition is config (`configs/pipeline.json` + stage registry,
  `voclyp/pipeline/registry.py`); the loader rejects any order violating the
  privacy invariant.
- ✅ Long audio chunked at ingestion (utterance-boundary splits), processed in
  order, all chunks destroyed.
- ✅ Idempotent offline-sync uploads (`client_ref`).
- ✅ Worker is a runnable service (`python -m voclyp.worker`); gateway + worker
  ship as one Docker image (`Dockerfile`, `docker-compose.yml`); CI in
  `.github/workflows/ci.yml`.
- Remaining: real object storage for chunks; real broker behind `queueing.py`.

### Phase 2 — Real models, one stage at a time  ← *started*
- ✅ First real model swapped in: `asr: whisper` (faster-whisper) — verified on
  real spoken audio; enabling it is a one-line pipeline-config change.
- ✅ MLOps: eval harness with labeled sets per industry
  (`python -m voclyp.mlops.eval`, regression-gated in CI), per-stage latency
  metrics (`GET /v1/metrics`), feedback loop
  (`POST /v1/insights/{id}/feedback`).
- ✅ Production Indic stack: Sarvam AI (`asr: sarvam` = Saarika, built for
  code-mixed Hindi-English; `lang_id_translation: sarvam`) selected via
  `configs/pipeline.sarvam.json` + `SARVAM_API_KEY`. Language policy is data
  (`configs/languages.json`: hi-IN + en-IN enabled, 9 more planned).
- ✅ Cost-per-conversation monitoring: every provider call metered
  (`usage` table, `provider_usage` in `/v1/metrics`); pure-English utterances
  skip the translate call to conserve credits.
- Remaining: real diarization, ML-based PII redaction, LLM-backed signal
  extraction + summarization (still taxonomy-driven).

### Phase 3 — Delivery surface
- CRM connectors (Salesforce, Zoho), BI connectors (Power BI, Tableau).
- Voice-of-customer dashboards reading the same store.
- Deployment artifacts: single containerized bundle for cloud / private cloud / on-prem; data-residency configuration.

## Invariants that must never break

1. Nothing outside the gateway touches internal services.
2. No consumer ever binds to anything but the versioned insight schema.
3. Industry behavior changes only via taxonomy config files.
4. Raw audio never survives past redaction; deletion is audited.
5. Every store read/write is tenant-scoped — there is no query path without a `tenant_id`.
