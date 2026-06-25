-- VoClyp enterprise hardening — schema-per-tenant + deterministic state engine.
--
-- Tenant isolation is achieved with one PostgreSQL SCHEMA per enterprise client
-- (schema_sleep_company, schema_max_life, ...) instead of a shared public schema
-- with row-level security. The gateway sets `search_path` to the tenant schema
-- for the duration of each request, so the same un-qualified SQL transparently
-- hits the right tenant's tables.
--
-- This migration:
--   1. Defines the conversation_state ENUM and a transition-guard trigger fn.
--   2. Defines provision_tenant_schema(text) which creates a fresh schema with
--      immutable_consent_logs, showroom_conversations, routing_outbox, and the
--      failed_routing_outbox dead-letter table, plus indexes and triggers.
--   3. Provisions the two known tenants.

create extension if not exists "pgcrypto";

-- ---- shared types + functions (live in public, referenced by every schema) --

do $$
begin
  if not exists (select 1 from pg_type where typname = 'conversation_state') then
    create type public.conversation_state as enum (
      'consent_logged',   -- consent ledger written; row exists before S3 PUT
      'audio_uploaded',   -- raw audio persisted to S3 (Mumbai)
      'transcribing',     -- Sarvam ASR in flight
      'extracting',       -- Bedrock Claude extraction in flight
      'dispatching',      -- routing fan-out (Zoho/Twilio/push)
      'purged',           -- normal end-of-life: raw audio destroyed
      'error_purged'      -- forced cleanup of a stranded/stuck conversation
    );
  end if;
end
$$;

-- Append-only guard for the consent ledger (reused by every tenant schema).
create or replace function public.raise_immutable() returns trigger
language plpgsql as $$
begin
  raise exception 'consent log is append-only (% blocked)', tg_op;
end;
$$;

-- updated_at touch (reused by every tenant schema).
create or replace function public.touch_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- Deterministic state-machine guard. Illegal transitions are rejected at the
-- database boundary as a backstop to the application-level enforcement in
-- voclyp/enterprise/store.py.
create or replace function public.enforce_conversation_state() returns trigger
language plpgsql as $$
begin
  if new.state = old.state then
    return new;
  end if;
  -- purged is terminal; nothing may leave it.
  if old.state = 'purged' then
    raise exception 'illegal state transition % -> % (purged is terminal)', old.state, new.state;
  end if;
  -- error_purged is terminal.
  if old.state = 'error_purged' then
    raise exception 'illegal state transition % -> % (error_purged is terminal)', old.state, new.state;
  end if;
  -- error_purged is reachable from ANY non-terminal state (orphan sweep).
  if new.state = 'error_purged' then
    return new;
  end if;
  -- the happy-path ladder
  if (old.state, new.state) in (
      ('consent_logged','audio_uploaded'),
      ('audio_uploaded','transcribing'),
      ('transcribing','extracting'),
      ('extracting','dispatching'),
      ('dispatching','purged')) then
    return new;
  end if;
  raise exception 'illegal state transition % -> %', old.state, new.state;
end;
$$;

-- ---- per-tenant schema provisioning ----------------------------------------

create or replace function public.provision_tenant_schema(p_schema text)
returns void
language plpgsql as $$
begin
  execute format('create schema if not exists %I', p_schema);

  -- immutable, tamper-evident consent ledger
  execute format($f$
    create table if not exists %I.immutable_consent_logs (
      id                  uuid primary key default gen_random_uuid(),
      tenant_id           text not null,
      agent_id            text not null,
      session_id          text not null,
      customer_phone_hash text not null,
      language            text not null,
      purposes            jsonb not null,
      device_fingerprint  jsonb not null,
      consent_artifact    jsonb not null,
      artifact_sha256     text not null,
      prev_hash           text not null,
      entry_hash          text not null,
      captured_at         timestamptz not null default now()
    )$f$, p_schema);
  execute format('create unique index if not exists %I on %I.immutable_consent_logs (tenant_id, entry_hash)',
                 'uq_' || p_schema || '_consent_entry', p_schema);
  execute format('drop trigger if exists trg_consent_no_mutate on %I.immutable_consent_logs', p_schema);
  execute format($f$create trigger trg_consent_no_mutate
      before update or delete on %I.immutable_consent_logs
      for each row execute function public.raise_immutable()$f$, p_schema);
  execute format('revoke update, delete, truncate on %I.immutable_consent_logs from public', p_schema);

  -- conversation lifecycle, driven by the conversation_state ENUM
  execute format($f$
    create table if not exists %I.showroom_conversations (
      id                          uuid primary key default gen_random_uuid(),
      tenant_id                   text not null,
      agent_id                    text not null,
      store_id                    text not null,
      consent_log_id              uuid not null references %I.immutable_consent_logs(id),
      s3_bucket                   text not null,
      s3_key                      text not null,
      audio_sha256                text not null,
      duration_seconds            numeric,
      state                       public.conversation_state not null default 'consent_logged',
      error_detail                text,
      transcript_codemix          text,
      transcript_english          text,
      detected_languages          text[] not null default '{}',
      asr_path                    text,
      extraction                  jsonb,
      extraction_confidence       numeric,
      requires_human_verification boolean not null default false,
      verified_by                 text,
      verified_at                 timestamptz,
      erase_after                 timestamptz not null,
      erased_at                   timestamptz,
      created_at                  timestamptz not null default now(),
      updated_at                  timestamptz not null default now()
    )$f$, p_schema, p_schema);
  execute format('create index if not exists %I on %I.showroom_conversations (tenant_id, state)',
                 'idx_' || p_schema || '_conv_state', p_schema);
  -- orphan-sweep scan: non-terminal rows still holding S3 audio
  execute format($f$create index if not exists %I on %I.showroom_conversations (created_at)
      where state not in ('purged','error_purged')$f$,
                 'idx_' || p_schema || '_conv_orphan', p_schema);
  execute format('drop trigger if exists trg_conv_touch on %I.showroom_conversations', p_schema);
  execute format($f$create trigger trg_conv_touch
      before update on %I.showroom_conversations
      for each row execute function public.touch_updated_at()$f$, p_schema);
  execute format('drop trigger if exists trg_conv_state on %I.showroom_conversations', p_schema);
  execute format($f$create trigger trg_conv_state
      before update of state on %I.showroom_conversations
      for each row execute function public.enforce_conversation_state()$f$, p_schema);

  -- active routing outbox (at-least-once, idempotent, capped retries)
  execute format($f$
    create table if not exists %I.routing_outbox (
      id              uuid primary key default gen_random_uuid(),
      tenant_id       text not null,
      conversation_id uuid not null references %I.showroom_conversations(id),
      channel         text not null,
      status          text not null default 'pending',
      attempts        int not null default 0,
      max_attempts    int not null default 5,
      idempotency_key text not null,
      payload         jsonb not null,
      response        jsonb,
      detail          text,
      next_retry_at   timestamptz not null default now(),
      created_at      timestamptz not null default now(),
      updated_at      timestamptz not null default now(),
      unique (conversation_id, channel)
    )$f$, p_schema, p_schema);
  execute format($f$create index if not exists %I on %I.routing_outbox (next_retry_at)
      where status in ('pending','failed')$f$,
                 'idx_' || p_schema || '_routing_due', p_schema);
  execute format('drop trigger if exists trg_routing_touch on %I.routing_outbox', p_schema);
  execute format($f$create trigger trg_routing_touch
      before update on %I.routing_outbox
      for each row execute function public.touch_updated_at()$f$, p_schema);

  -- dead-letter queue: poison pills that exhausted their retries
  execute format($f$
    create table if not exists %I.failed_routing_outbox (
      id              uuid primary key default gen_random_uuid(),
      tenant_id       text not null,
      conversation_id uuid not null,
      channel         text not null,
      attempts        int not null,
      idempotency_key text not null,
      payload         jsonb not null,
      last_response   jsonb,
      failure_reason  text not null,
      original_created_at timestamptz,
      failed_at       timestamptz not null default now()
    )$f$, p_schema);
  execute format('create index if not exists %I on %I.failed_routing_outbox (tenant_id, failed_at)',
                 'idx_' || p_schema || '_dlq', p_schema);
end;
$$;

-- ---- provision the known tenants -------------------------------------------
select public.provision_tenant_schema('schema_sleep_company');
select public.provision_tenant_schema('schema_max_life');
