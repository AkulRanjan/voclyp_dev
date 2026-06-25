-- VoClyp enterprise — showroom conversation lifecycle.
--
-- One row per field/showroom conversation. Tracks the event-driven pipeline
-- state machine, both transcripts (codemix for display/WhatsApp, English for
-- Claude), the constrained-JSON extraction, the human-verification gate, and
-- the ephemeral-audio erasure deadline.

create table if not exists showroom_conversations (
  id                          uuid primary key default gen_random_uuid(),
  tenant_id                   text        not null,
  agent_id                    text        not null,
  store_id                    text        not null,
  consent_log_id              uuid        not null references immutable_consent_logs(id),

  -- ephemeral audio in S3 (Mumbai)
  s3_bucket                   text        not null,
  s3_key                      text        not null,
  audio_sha256                text        not null,
  duration_seconds            numeric,

  -- pipeline state machine
  status                      text        not null default 'uploaded',
  -- uploaded | transcribing | transcribed | extracting | extracted
  --          | routing | routed | erased | failed
  error_detail                text,

  -- dual transcripts (Self-Correction: preserve multilingual nuance)
  transcript_codemix          text,
  transcript_english          text,
  detected_languages          text[]      not null default '{}',
  asr_path                    text,       -- 'rest' | 'batch'

  -- constrained extraction (Bedrock Claude)
  extraction                  jsonb,
  extraction_confidence       numeric,
  requires_human_verification boolean     not null default false,
  verified_by                 text,
  verified_at                 timestamptz,

  -- DPDP ephemeral-audio erasure
  erase_after                 timestamptz not null,
  erased_at                   timestamptz,

  created_at                  timestamptz not null default now(),
  updated_at                  timestamptz not null default now(),

  constraint status_known check (status in (
    'uploaded','transcribing','transcribed','extracting','extracted',
    'routing','routed','erased','failed'))
);

create index if not exists idx_conv_tenant_status on showroom_conversations (tenant_id, status);
create index if not exists idx_conv_store         on showroom_conversations (tenant_id, store_id, created_at);
create index if not exists idx_conv_agent         on showroom_conversations (tenant_id, agent_id, created_at);
-- erasure worker scan: only rows that still have audio to destroy
create index if not exists idx_conv_erase_due     on showroom_conversations (erase_after)
  where erased_at is null;
-- verification queue for the agent app
create index if not exists idx_conv_needs_verify  on showroom_conversations (tenant_id, agent_id)
  where requires_human_verification = true and verified_at is null;

create or replace function touch_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_conv_touch on showroom_conversations;
create trigger trg_conv_touch
  before update on showroom_conversations
  for each row execute function touch_updated_at();

alter table showroom_conversations enable row level security;

drop policy if exists conv_tenant_read on showroom_conversations;
create policy conv_tenant_read on showroom_conversations
  for select using (tenant_id = current_setting('request.jwt.claims', true)::jsonb->>'tenant_id');
