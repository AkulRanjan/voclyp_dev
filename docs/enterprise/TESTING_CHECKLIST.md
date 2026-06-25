# VoClyp Enterprise — Live Endpoint Testing Checklist

Everything below is **optional for offline development** — with no credentials
the layer runs entirely on in-process mocks. Provide a group of variables to
flip the corresponding component from mock to live. All variables are read in
`voclyp/enterprise/config.py`.

## 0. Master flag

| Env var | Required | Notes |
| --- | --- | --- |
| `VOCLYP_ENTERPRISE_ENABLED` | yes (to mount routes) | `true` to expose `/v1/enterprise/*`. |
| `VOCLYP_ENTERPRISE_DIR` | no | Local store/sink dir. Default `data/enterprise`. |
| `VOCLYP_CONFIDENCE_THRESHOLD` | no | EMI/low-confidence verification gate. Default `0.55`. |
| `VOCLYP_SARVAM_REST_LIMIT_S` | no | Batch-vs-REST cutoff. Default `30`. |
| `VOCLYP_ERASE_AFTER_SECONDS` | no | DPDP erase window. Default `7200` (2h). |

## 1. AWS — S3 (Mumbai) + Bedrock Claude

| Env var | Required | Notes |
| --- | --- | --- |
| `AWS_REGION` | yes | `ap-south-1`. |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | yes* | *Or use an instance/role credential chain. Explicit keys force live Bedrock. |
| `AWS_SESSION_TOKEN` | if temporary creds | STS sessions. |
| `VOCLYP_S3_BUCKET` | yes (S3) | Presence switches S3 from mock → live. |
| `VOCLYP_BEDROCK_MODEL_ID` | no | Default `anthropic.claude-3-5-sonnet-20240620-v1:0`. |

**IAM policy (least privilege):**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Sid": "BedrockInvoke", "Effect": "Allow",
      "Action": ["bedrock:InvokeModel"],
      "Resource": "arn:aws:bedrock:ap-south-1::foundation-model/anthropic.claude-3-5-sonnet-*" },
    { "Sid": "EphemeralAudioRW", "Effect": "Allow",
      "Action": ["s3:PutObject","s3:GetObject","s3:DeleteObject","s3:PutObjectTagging"],
      "Resource": "arn:aws:s3:::YOUR_BUCKET/*" },
    { "Sid": "BucketLifecycle", "Effect": "Allow",
      "Action": ["s3:PutLifecycleConfiguration","s3:GetBucketLocation"],
      "Resource": "arn:aws:s3:::YOUR_BUCKET" }
  ]
}
```

- Enable Bedrock **model access** for Claude 3.5 Sonnet in `ap-south-1` (or use a cross-region inference profile if Sonnet isn't available there).
- S3 bucket: Block Public Access ON, default SSE-KMS, versioning OFF (ephemeral). The erasure worker is the precise enforcer; the 1-day lifecycle rule (`ensure_lifecycle()`) is a backstop.

## 2. Supabase / PostgreSQL

| Env var | Required | Notes |
| --- | --- | --- |
| `SUPABASE_DB_URL` | yes | psycopg DSN, e.g. `postgresql://...@db.<project>.supabase.co:5432/postgres`. Presence switches store → Postgres. |
| `SUPABASE_URL` | no | `https://<project>.supabase.co`. |
| `SUPABASE_SERVICE_KEY` | no | Service-role key (server-side only — never ship to the app). |

Apply migrations: `supabase db push` or `psql "$SUPABASE_DB_URL" -f supabase/migrations/0001_immutable_consent_logs.sql` (then `0002`, `0003`).

## 3. Sarvam AI (ASR)

| Env var | Required | Notes |
| --- | --- | --- |
| `SARVAM_API_KEY` | yes | Same key as the core pipeline. Presence switches ASR → live (REST + Batch). Needs `sarvamai` for the Batch API. |

## 4. Kafka (AWS MSK / Confluent / local redpanda)

| Env var | Required | Notes |
| --- | --- | --- |
| `KAFKA_BOOTSTRAP_SERVERS` | yes | Presence switches bus → Kafka. |
| `KAFKA_SECURITY_PROTOCOL` | no | Default `SASL_SSL`. |
| `KAFKA_SASL_MECHANISM` | no | Default `PLAIN` (use `AWS_MSK_IAM` for MSK IAM). |
| `KAFKA_SASL_USERNAME` / `KAFKA_SASL_PASSWORD` | if SASL | |
| `KAFKA_GROUP_ID` | no | Default `voclyp-enterprise`. |

Topics to create: `audio.raw.uploaded`, `transcript.ready`, `insight.extracted`, `routing.requested`.
Run workers: `python -m voclyp.enterprise.runner {asr|extractor|routing|erasure}`.

## 5. Twilio WhatsApp

| Env var | Required | Notes |
| --- | --- | --- |
| `TWILIO_ACCOUNT_SID` | yes | |
| `TWILIO_AUTH_TOKEN` | yes | Presence (all three) switches WhatsApp → live. |
| `TWILIO_WHATSAPP_FROM` | yes | e.g. `whatsapp:+1415XXXXXXX`. |
| `TWILIO_TEMPLATE_SID` | no | Approved content template (`HX...`) for templated sends. |

## 6. Zoho CRM

| Env var | Required | Notes |
| --- | --- | --- |
| `ZOHO_CLIENT_ID` / `ZOHO_CLIENT_SECRET` | yes | Self-client or server app. |
| `ZOHO_REFRESH_TOKEN` | yes | Presence (id + refresh) switches Zoho → live. Scope: `ZohoCRM.modules.leads.ALL`. |
| `ZOHO_API_DOMAIN` | no | Default `https://www.zohoapis.in`. |
| `ZOHO_ACCOUNTS_DOMAIN` | no | Default `https://accounts.zoho.in`. |

## 7. Redis + push

| Env var | Required | Notes |
| --- | --- | --- |
| `REDIS_URL` | no | Cache/rate-limit (reserved). |
| `VOCLYP_PUSH_WEBHOOK` | no | If set, agent push POSTs here (FCM/APNs proxy); else recorded to offline sink. |

## Smoke test (live)

1. `export VOCLYP_ENTERPRISE_ENABLED=true` + the credential groups you want live.
2. Apply Supabase migrations.
3. Start the gateway: `uvicorn voclyp.gateway.app:app`.
4. Ingest (consent must include recording):

```bash
curl -X POST http://localhost:8000/v1/enterprise/conversations \
  -H "X-API-Key: $VOCLYP_API_KEY" \
  -F "consent_recording=true" -F "consent_whatsapp=true" -F "consent_crm=true" \
  -F "language=hi-IN" -F "store_id=store-1" -F "agent_id=agent-7" \
  -F "session_id=sess-123" -F "notice_text=Recording consent notice..." \
  -F "audio=@sample.wav"
```

5. Poll `GET /v1/enterprise/conversations/{id}` until `status=routed`.
6. If `requires_human_verification=true`, release WhatsApp:

```bash
curl -X POST http://localhost:8000/v1/enterprise/conversations/{id}/verify \
  -H "X-API-Key: $VOCLYP_API_KEY" -H "Content-Type: application/json" \
  -d '{"whatsapp_to":"+9198XXXXXXXX"}'
```

7. Confirm raw audio is gone after the window: `POST /v1/enterprise/maintenance/erasure` (admin) → object deleted, `status=erased`.

## Offline verification (no creds)

```bash
python -m pytest tests/test_enterprise_pipeline.py -q
```
