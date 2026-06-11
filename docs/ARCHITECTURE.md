# VoClyp — Architecture (as implemented)

VoClyp is not a single AI model: it is a pipeline of specialized, swappable stages
wrapped in a platform. Partners integrate once against three stable contracts —
the gateway (the only way in), the versioned insight schema (the only way out),
and the taxonomy config (the only way to change industry behavior). Everything
between those contracts can be rebuilt freely.

## 1. Target system

```mermaid
flowchart TB
  subgraph FIELD["Field layer (agent device)"]
    A1["Field app / SDK<br/>one-tap record"]
    A2["Consent capture<br/>name + permission"]
    A3["Offline buffer<br/>sync when online"]
    A1 --> A3
    A2 --> A3
  end

  subgraph EDGE["Ingestion edge"]
    B1["API Gateway<br/>auth, rate limit, tenant routing"]
    B2["Ingestion service<br/>validate, chunk, enqueue"]
    Q[["Processing queue<br/>durable, retryable"]]
    B1 --> B2 --> Q
  end

  A3 -->|upload audio + metadata| B1

  subgraph CORE["Core pipeline (the model)"]
    C1["ASR<br/>120+ Indian langs, code-switch"]
    C2["Diarization<br/>agent vs customer"]
    C3["Language ID + translation<br/>normalize, keep original"]
    C4["PII redaction"]
    DEL["Audio auto-delete<br/>+ audit log entry"]
    C5["Signal extraction (the brain)<br/>objections, demand, competitor,<br/>price, intent, promises"]
    C6["Summarization<br/>industry-shaped fields"]
    Q --> C1 --> C2 --> C3 --> C4 --> DEL --> C5 --> C6
  end

  TAX["Taxonomy config packs<br/>base + per-industry (data, not code)"] -. drives .-> C5
  TAX -. drives .-> C6

  subgraph DATA["Insight store + delivery"]
    D1[("Insights DB<br/>versioned JSON, per tenant")]
    D2["Webhooks (push)"]
    D3["Insights API (pull)"]
    D4["Connectors: CRM / BI"]
    D5["Dashboards"]
    C6 --> D1
    D1 --> D2
    D1 --> D3
    D1 --> D4
    D1 --> D5
  end

  D2 --> EXT["Partner systems"]
  D3 --> EXT
  D4 --> EXT

  subgraph X["Cross-cutting"]
    X1["Auth + multi-tenancy"]
    X2["Data residency"]
    X3["MLOps: eval, versioning,<br/>monitoring, feedback"]
    X4["Compliance: consent log,<br/>delete-on-demand, audit export"]
  end
```

Note one deliberate deviation from the original sketch: audio deletion sits
**inside** the pipeline, between redaction and signal extraction, as an explicit
stage. Analysis can never depend on raw audio because by the time analysis runs,
the audio no longer exists.

## 2. What is going to happen — Phase-0 implementation

Every box above exists in this repo today as a real module behind its real
interface; the AI stages are deterministic stubs that will be swapped for models
one at a time without changing anything around them.

```mermaid
flowchart LR
  subgraph repo["This repository"]
    GW["voclyp/gateway/app.py<br/>FastAPI: API-key auth,<br/>rate limit, tenant routing"]
    ING["voclyp/ingestion.py<br/>consent check, validate, enqueue"]
    QU[("voclyp/queueing.py<br/>SQLite job queue, retries")]
    WK["voclyp/worker.py<br/>pipeline runner"]
    ST[("voclyp/store.py<br/>insights + audit + consent,<br/>tenant-scoped SQLite")]
    DL["voclyp/delivery.py<br/>webhook dispatch"]
    PIPE["voclyp/pipeline/stages/*<br/>asr → diarize → translate →<br/>redact → delete-audio →<br/>signals → summarize"]
    TAXF["configs/taxonomy/*.json"]
    SCH["contracts/insight-schema/v1"]
  end
  GW --> ING --> QU --> WK --> PIPE --> ST --> DL
  TAXF -. drives .-> PIPE
  ST -. shape fixed by .-> SCH
```

### Sequence of one conversation

```mermaid
sequenceDiagram
  participant App as Field app (simulated)
  participant GW as Gateway
  participant Q as Queue
  participant W as Worker (pipeline)
  participant S as Insight store
  participant P as Partner

  App->>GW: POST /v1/conversations (audio + metadata + consent)
  GW->>GW: API key → tenant, rate limit
  GW->>Q: validated job enqueued
  GW-->>App: 202 conversation_id
  Q->>W: job leased
  W->>W: ASR → diarize → translate → redact
  W->>W: DELETE raw audio + audit entry
  W->>W: extract signals + summarize (taxonomy-driven)
  W->>S: insight JSON (schema v1, tenant-scoped)
  S->>P: webhook push
  P->>GW: GET /v1/insights/{id} (pull, same schema)
```

## 3. The three contracts

**Gateway API** — `POST /v1/conversations` (consent required), `GET /v1/insights`,
`GET /v1/insights/{conversation_id}`, `DELETE /v1/conversations/{id}`
(delete-on-demand), `POST /v1/webhooks`. Auth: `X-API-Key` mapped to a tenant;
every downstream operation carries that tenant id.

**Insight schema v1** — `contracts/insight-schema/v1/insight.schema.json`.
Versioned envelope: languages detected, redaction counts, extracted signals
(type, subtype, speaker, quote, turn, confidence), summary text + industry
fields, and an audit block proving audio deletion and recording stage versions.

**Taxonomy config** — `configs/taxonomy/base.json` defines the universal signal
types (objection, intent, demand, competitor_mention, price_reaction, promise).
Each industry pack (`fmcg.json`, `pharma.json`) maps its vocabulary onto those
types and declares its summary fields. Onboarding an industry = adding one file.

## 4. Tenancy, privacy, compliance

- `voclyp/store.py` exposes no query without a `tenant_id` parameter — isolation
  is structural, not conventional.
- Consent is required at submit time and logged; missing consent is a 4xx, not a warning.
- Audio deletion is a pipeline stage with an audit record; `DELETE /v1/conversations/{id}`
  wipes the stored insight on demand and audits that too.
- Every insight records the version of each stage that produced it (MLOps versioning seed).
