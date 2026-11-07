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
