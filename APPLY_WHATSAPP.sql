-- Growthboard WhatsApp upgrade for the existing workspace database.

-- Prepared foundation; apply when WhatsApp connection setup starts.
begin;
create table if not exists public.whatsapp_connections (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null unique references public.workspaces(id) on delete cascade,
  connected_by uuid references auth.users(id) on delete set null,
  waba_id text not null,
  phone_number_id text not null unique,
  display_phone_number text,
  verified_name text,
  access_token_encrypted text not null,
  status text not null default 'paused' check(status in ('active','paused','revoked','error')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(id,workspace_id)
);
create table if not exists public.whatsapp_messages (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  connection_id uuid not null,
  contact_wa_id text not null,
  direction text not null check(direction in ('inbound','outbound')),
  provider_message_id text,
  request_id uuid,
  message_type text not null default 'text',
  text text not null default '',
  status text not null check(status in ('received','queued','sending','sent','delivered','read','failed','uncertain','unsupported')),
  occurred_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  foreign key(connection_id,workspace_id) references public.whatsapp_connections(id,workspace_id) on delete cascade,
  unique(connection_id,provider_message_id),
  unique(workspace_id,request_id)
);
create index if not exists whatsapp_contact_messages_idx on public.whatsapp_messages(connection_id,contact_wa_id,occurred_at desc);
create table if not exists public.whatsapp_events (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  connection_id uuid not null,
  event_key text not null,
  event jsonb not null,
  status text not null default 'pending' check(status in ('pending','processing','processed','ignored','failed')),
  received_at timestamptz not null default now(),
  processed_at timestamptz,
  foreign key(connection_id,workspace_id) references public.whatsapp_connections(id,workspace_id) on delete cascade,
  unique(connection_id,event_key)
);
alter table public.whatsapp_connections enable row level security;
alter table public.whatsapp_messages enable row level security;
alter table public.whatsapp_events enable row level security;
revoke all on public.whatsapp_connections,public.whatsapp_messages,public.whatsapp_events from anon,authenticated;
grant all on public.whatsapp_connections,public.whatsapp_messages,public.whatsapp_events to service_role;
notify pgrst,'reload schema';
commit;


-- Apply after 007. All WhatsApp data is accessed through authenticated backend routes.
begin;
alter table public.whatsapp_connections add column if not exists connected_at timestamptz not null default now();
alter table public.whatsapp_connections add column if not exists billing_acknowledged boolean not null default false;
alter table public.whatsapp_connections add column if not exists ai_enabled boolean not null default false;
alter table public.whatsapp_connections add column if not exists business_name text not null default '';
alter table public.whatsapp_connections add column if not exists knowledge text not null default '';
alter table public.whatsapp_connections add column if not exists instructions text not null default '';
alter table public.whatsapp_connections add column if not exists handoff_message text not null default 'Our team will help you here. Please leave your question.';
alter table public.whatsapp_connections add column if not exists ai_daily_limit integer not null default 50 check(ai_daily_limit between 1 and 200);
alter table public.whatsapp_connections add column if not exists ai_enabled_at timestamptz;

create or replace function public.wa_keep_number() returns trigger language plpgsql set search_path=public as $$
begin
  if old.phone_number_id <> new.phone_number_id or old.waba_id <> new.waba_id then
    raise exception 'This workspace already belongs to another WhatsApp number';
  end if;
  return new;
end $$;
drop trigger if exists wa_keep_number on public.whatsapp_connections;
create trigger wa_keep_number before update on public.whatsapp_connections for each row execute function public.wa_keep_number();

create table if not exists public.whatsapp_contacts (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  connection_id uuid not null,
  wa_id text not null check(wa_id ~ '^[0-9]{7,15}$'),
  name text not null default '',
  opted_in boolean not null default false,
  consent_source text not null default '',
  opted_in_at timestamptz,
  opted_out boolean not null default false,
  automation_paused boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(connection_id,wa_id),
  foreign key(connection_id,workspace_id) references public.whatsapp_connections(id,workspace_id) on delete cascade
);
create table if not exists public.whatsapp_rules (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  connection_id uuid not null,
  name text not null,
  trigger text not null check(trigger in ('welcome','keyword')),
  keywords jsonb not null default '[]',
  reply_text text not null,
  enabled boolean not null default false,
  daily_limit integer not null default 50 check(daily_limit between 1 and 200),
  cooldown_minutes integer not null default 60 check(cooldown_minutes between 1 and 1440),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key(connection_id,workspace_id) references public.whatsapp_connections(id,workspace_id) on delete cascade
);
create unique index if not exists wa_one_welcome on public.whatsapp_rules(connection_id) where trigger='welcome';
create table if not exists public.whatsapp_templates (
  id text not null,
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  connection_id uuid not null,
  name text not null,
  language text not null,
  status text not null,
  category text not null,
  components jsonb not null default '[]',
  sendable boolean not null default false,
  parameter_count integer not null default 0,
  synced_at timestamptz not null default now(),
  primary key(connection_id,id),
  foreign key(connection_id,workspace_id) references public.whatsapp_connections(id,workspace_id) on delete cascade
);
create table if not exists public.whatsapp_campaigns (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  connection_id uuid not null,
  request_id uuid not null,
  request_hash text not null,
  name text not null,
  template jsonb not null,
  recipients jsonb not null,
  status text not null default 'draft' check(status in ('draft','scheduled','running','paused','completed','cancelled')),
  scheduled_for timestamptz not null default now(),
  approved_at timestamptz,
  detail text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(workspace_id,request_id),
  unique(id,connection_id),
  foreign key(connection_id,workspace_id) references public.whatsapp_connections(id,workspace_id) on delete cascade
);
create index if not exists wa_campaign_due on public.whatsapp_campaigns(status,scheduled_for);
alter table public.whatsapp_messages add column if not exists purpose text not null default 'manual';
alter table public.whatsapp_messages add column if not exists category text not null default 'service';
alter table public.whatsapp_messages add column if not exists pricing_billable boolean;
alter table public.whatsapp_messages add column if not exists pricing_type text;
alter table public.whatsapp_messages add column if not exists delivered_at timestamptz;
alter table public.whatsapp_messages add column if not exists request_hash text;
alter table public.whatsapp_messages add column if not exists template jsonb;
alter table public.whatsapp_messages add column if not exists parameters jsonb not null default '[]';
alter table public.whatsapp_messages add column if not exists event_id uuid references public.whatsapp_events(id) on delete set null;
alter table public.whatsapp_messages add column if not exists rule_id uuid references public.whatsapp_rules(id) on delete set null;
alter table public.whatsapp_messages add column if not exists campaign_id uuid;
alter table public.whatsapp_messages add column if not exists detail text not null default '';
alter table public.whatsapp_messages add column if not exists updated_at timestamptz not null default now();
do $$ begin
  if not exists(select 1 from pg_constraint where conname='wa_campaign_message_fk') then
    alter table public.whatsapp_messages add constraint wa_campaign_message_fk foreign key(campaign_id,connection_id) references public.whatsapp_campaigns(id,connection_id);
  end if;
end $$;
create index if not exists wa_pending_messages on public.whatsapp_messages(status,created_at);
alter table public.whatsapp_events add column if not exists detail text not null default '';
alter table public.whatsapp_events add column if not exists claimed_at timestamptz;
alter table public.whatsapp_events add column if not exists next_attempt_at timestamptz not null default now();
create index if not exists wa_due_events on public.whatsapp_events(status,next_attempt_at);

create table if not exists public.whatsapp_signup_sessions (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  state_hash text not null unique,
  expires_at timestamptz not null,
  consumed boolean not null default false
);
create table if not exists public.whatsapp_ai_runs (
  id uuid primary key default gen_random_uuid(),
  connection_id uuid not null references public.whatsapp_connections(id) on delete cascade,
  event_id uuid not null unique references public.whatsapp_events(id) on delete cascade,
  created_at timestamptz not null default now()
);
create or replace function public.wa_reserve_ai(p_connection uuid,p_event uuid,p_limit integer)
returns boolean language plpgsql security invoker set search_path=public as $$
begin
  perform pg_advisory_xact_lock(hashtextextended(p_connection::text,0));
  if not exists(select 1 from whatsapp_connections c join whatsapp_events e on e.connection_id=c.id where c.id=p_connection and e.id=p_event and c.ai_enabled and c.status='active') then return false; end if;
  if exists(select 1 from whatsapp_ai_runs where event_id=p_event) then return false; end if;
  if (select count(*) from whatsapp_ai_runs where connection_id=p_connection and created_at >= date_trunc('day',now() at time zone 'UTC') at time zone 'UTC') >= p_limit then return false; end if;
  insert into whatsapp_ai_runs(connection_id,event_id) values(p_connection,p_event);
  return true;
end $$;
revoke all on function public.wa_reserve_ai(uuid,uuid,integer) from public,anon,authenticated;
grant execute on function public.wa_reserve_ai(uuid,uuid,integer) to service_role;

do $$ declare t text; begin
  foreach t in array array['whatsapp_contacts','whatsapp_rules','whatsapp_templates','whatsapp_campaigns','whatsapp_signup_sessions','whatsapp_ai_runs'] loop
    execute format('alter table public.%I enable row level security',t);
    execute format('revoke all on public.%I from anon,authenticated',t);
    execute format('grant all on public.%I to service_role',t);
  end loop;
end $$;
notify pgrst,'reload schema';
commit;
