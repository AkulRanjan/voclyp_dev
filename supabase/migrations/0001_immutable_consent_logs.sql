-- VoClyp enterprise — DPDP-grade consent ledger.
--
-- Append-only and tamper-evident. A row is written BEFORE any audio is allowed
-- to reach S3 (see voclyp/enterprise/ingestion.py). Immutability is enforced
-- two ways: privileges are revoked for UPDATE/DELETE, and a trigger raises on
-- any attempt, so even a privileged path cannot silently rewrite history. Each
-- row carries a SHA-256 of the canonical consent artifact plus a per-tenant
-- hash chain (prev_hash -> entry_hash) so the whole log can be replayed and
-- verified end to end.

create extension if not exists "pgcrypto";

create table if not exists immutable_consent_logs (
  id                  uuid primary key default gen_random_uuid(),
  tenant_id           text        not null,
  agent_id            text        not null,
  session_id          text        not null,
  -- DPDP: store a hash of the customer's phone, never the raw identifier here.
  customer_phone_hash text        not null,
  -- multilingual consent: BCP-47 code of the language the notice was shown in.
  language            text        not null,
  -- granular, per-purpose toggles, e.g.
  -- {"recording": true, "whatsapp_followup": true, "crm_storage": true, "marketing": false}
  purposes            jsonb       not null,
  -- device fingerprint captured at consent time (model, os, app_version, ip_hash...)
  device_fingerprint  jsonb       not null,
  -- the exact notice text + toggle state shown to the customer
  consent_artifact    jsonb       not null,
  -- SHA-256 of the canonical (sorted-key) consent_artifact
  artifact_sha256     text        not null,
  -- per-tenant hash chain making the ledger tamper-evident
  prev_hash           text        not null,
  entry_hash          text        not null,
  captured_at         timestamptz not null default now(),

  constraint purposes_is_object  check (jsonb_typeof(purposes) = 'object'),
  constraint recording_consented check ((purposes->>'recording')::boolean is true)
);

create index if not exists idx_consent_tenant       on immutable_consent_logs (tenant_id, captured_at);
create index if not exists idx_consent_session      on immutable_consent_logs (tenant_id, session_id);
create unique index if not exists uq_consent_entry  on immutable_consent_logs (tenant_id, entry_hash);

-- ---- immutability enforcement ---------------------------------------------
create or replace function raise_immutable() returns trigger
language plpgsql as $$
begin
  raise exception 'immutable_consent_logs is append-only (% blocked)', tg_op;
end;
$$;

drop trigger if exists trg_consent_no_mutate on immutable_consent_logs;
create trigger trg_consent_no_mutate
  before update or delete on immutable_consent_logs
  for each row execute function raise_immutable();

revoke update, delete, truncate on immutable_consent_logs from public;

-- ---- row level security ----------------------------------------------------
alter table immutable_consent_logs enable row level security;

drop policy if exists consent_tenant_read on immutable_consent_logs;
create policy consent_tenant_read on immutable_consent_logs
  for select using (tenant_id = current_setting('request.jwt.claims', true)::jsonb->>'tenant_id');

drop policy if exists consent_service_insert on immutable_consent_logs;
create policy consent_service_insert on immutable_consent_logs
  for insert with check (true);
