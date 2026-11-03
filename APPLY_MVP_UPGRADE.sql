-- Growthboard MVP upgrade. Apply to the EXISTING Supabase project; do not rerun migration 001.
-- Adds automation storage and a once-per-minute authenticated hosted worker wake-up.

begin;

create table if not exists public.automation_rules (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 80),
  trigger text not null check (trigger in ('welcome', 'dm_keyword', 'comment_keyword')),
  keywords text[] not null default '{}',
  media_ids text[] not null default '{}',
  reply_text text not null check (char_length(reply_text) between 1 and 1000),
  enabled boolean not null default false,
  daily_limit integer not null default 20 check (daily_limit between 1 and 100),
  cooldown_minutes integer not null default 60 check (cooldown_minutes between 1 and 1440),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index if not exists automation_one_welcome_idx on public.automation_rules(workspace_id) where trigger = 'welcome';

create table if not exists public.automation_events (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  connection_id uuid not null references public.social_connections(id) on delete cascade,
  account_id text not null,
  event_key text not null,
  kind text not null check (kind in ('dm', 'comment')),
  sender_id text not null,
  comment_id text,
  media_id text,
  text text not null default '',
  occurred_at timestamptz not null,
  status text not null default 'pending' check (status in ('pending', 'processing', 'processed', 'ignored', 'failed')),
  detail text,
  received_at timestamptz not null default now(),
  processed_at timestamptz,
  unique (connection_id, event_key)
);
create index if not exists automation_events_due_idx on public.automation_events(received_at) where status = 'pending';

create table if not exists public.automation_contacts (
  connection_id uuid not null references public.social_connections(id) on delete cascade,
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  sender_id text not null,
  first_event_id uuid not null references public.automation_events(id) on delete cascade,
  last_inbound_at timestamptz not null,
  primary key(connection_id, sender_id)
);

create table if not exists public.automation_deliveries (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  connection_id uuid not null references public.social_connections(id) on delete cascade,
  rule_id uuid references public.automation_rules(id) on delete set null,
  event_id uuid not null references public.automation_events(id) on delete cascade,
  recipient_id text not null,
  dedupe_key text not null,
  reply_text text not null,
  status text not null default 'sending' check (status in ('sending', 'sent', 'failed', 'uncertain')),
  provider_message_id text,
  detail text,
  created_at timestamptz not null default now(),
  unique (connection_id, dedupe_key)
);
create index if not exists automation_deliveries_rule_idx on public.automation_deliveries(rule_id, created_at desc);

create table if not exists public.scheduler_leases (
  name text primary key,
  holder uuid not null,
  expires_at timestamptz not null
);
create or replace function public.acquire_growthboard_lease(lease_holder uuid)
returns boolean language plpgsql security definer set search_path = public as $$
declare changed integer;
begin
  insert into scheduler_leases(name, holder, expires_at)
  values ('mvp', lease_holder, now() + interval '20 minutes')
  on conflict (name) do update set holder = excluded.holder, expires_at = excluded.expires_at
  where scheduler_leases.expires_at < now();
  get diagnostics changed = row_count;
  return changed = 1;
end;
$$;
revoke all on function public.acquire_growthboard_lease(uuid) from public, anon, authenticated;
grant execute on function public.acquire_growthboard_lease(uuid) to service_role;

alter table public.social_connections add column if not exists webhook_subscribed boolean not null default false;
alter table public.social_connections add column if not exists webhook_error text;
alter table public.social_connections add column if not exists active_account_id text;

alter table public.automation_rules enable row level security;
alter table public.automation_events enable row level security;
alter table public.automation_contacts enable row level security;
alter table public.automation_deliveries enable row level security;
alter table public.scheduler_leases enable row level security;
revoke all on public.automation_rules, public.automation_events, public.automation_contacts,
  public.automation_deliveries, public.scheduler_leases from anon, authenticated;
grant all on public.automation_rules, public.automation_events, public.automation_contacts,
  public.automation_deliveries, public.scheduler_leases to service_role;

commit;


-- Supabase SQL Editor only: wake Render every minute, even if the browser/laptop is closed.
begin;
create extension if not exists pg_cron;
create schema if not exists extensions;
create extension if not exists pg_net with schema extensions;
create table if not exists public.scheduler_configuration (
  name text primary key,
  secret text not null,
  last_finished_at timestamptz,
  last_result jsonb
);
alter table public.scheduler_configuration enable row level security;
revoke all on public.scheduler_configuration from anon, authenticated;
grant all on public.scheduler_configuration to service_role;
insert into public.scheduler_configuration(name, secret)
values ('mvp', gen_random_uuid()::text || gen_random_uuid()::text)
on conflict(name) do nothing;

select cron.schedule('growthboard-mvp-worker', '* * * * *', $job$
  select net.http_post(
    url := 'https://business-growth-platform-api.onrender.com/api/internal/publishing/run',
    headers := jsonb_build_object('Content-Type', 'application/json', 'X-Cron-Secret',
      (select secret from public.scheduler_configuration where name = 'mvp')),
    body := '{}'::jsonb,
    timeout_milliseconds := 120000
  );
$job$);
commit;
