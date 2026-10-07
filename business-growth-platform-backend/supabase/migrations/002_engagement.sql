begin;

create table if not exists public.instagram_webhook_events (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid references public.workspaces(id) on delete cascade,
  payload jsonb not null,
  processed_at timestamptz,
  received_at timestamptz not null default now()
);

create table if not exists public.workspace_controls (
  workspace_id uuid primary key references public.workspaces(id) on delete cascade,
  publishing_enabled boolean not null default true,
  comments_enabled boolean not null default true,
  messages_enabled boolean not null default true,
  insights_enabled boolean not null default true,
  require_reply_approval boolean not null default true,
  updated_at timestamptz not null default now()
);

create index if not exists instagram_webhook_events_received_idx
  on public.instagram_webhook_events (received_at desc);

alter table public.instagram_webhook_events enable row level security;
alter table public.workspace_controls enable row level security;

drop policy if exists "members read workspace controls" on public.workspace_controls;
create policy "members read workspace controls" on public.workspace_controls for select to authenticated
  using (public.is_workspace_member(workspace_id));

commit;
