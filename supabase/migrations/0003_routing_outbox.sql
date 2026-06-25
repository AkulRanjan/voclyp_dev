-- VoClyp enterprise — multi-channel routing outbox.
--
-- One row per (conversation, channel). The routing dispatcher fans an
-- extracted insight out to Zoho CRM, Twilio WhatsApp, and the agent push
-- channel concurrently, with at-least-once delivery and retry/backoff (same
-- discipline as voclyp/delivery.py). The WhatsApp row is created in status
-- 'held' whenever human verification is required (Self-Correction 2) and only
-- becomes 'pending' after a 1-tap agent confirmation.

create table if not exists routing_outbox (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     text        not null,
  conversation_id uuid      not null references showroom_conversations(id),
  channel       text        not null,   -- 'zoho' | 'whatsapp' | 'push'
  status        text        not null default 'pending',
  -- pending | held | delivering | delivered | failed | dead | skipped
  attempts      int         not null default 0,
  max_attempts  int         not null default 5,
  payload       jsonb       not null,
  response      jsonb,
  detail        text,
  next_retry_at timestamptz not null default now(),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),

  constraint channel_known check (channel in ('zoho','whatsapp','push')),
  constraint routing_status_known check (status in (
    'pending','held','delivering','delivered','failed','dead','skipped')),
  unique (conversation_id, channel)
);

create index if not exists idx_routing_due on routing_outbox (next_retry_at)
  where status in ('pending','failed');
create index if not exists idx_routing_held on routing_outbox (tenant_id)
  where status = 'held';

drop trigger if exists trg_routing_touch on routing_outbox;
create trigger trg_routing_touch
  before update on routing_outbox
  for each row execute function touch_updated_at();

alter table routing_outbox enable row level security;

drop policy if exists routing_tenant_read on routing_outbox;
create policy routing_tenant_read on routing_outbox
  for select using (tenant_id = current_setting('request.jwt.claims', true)::jsonb->>'tenant_id');
