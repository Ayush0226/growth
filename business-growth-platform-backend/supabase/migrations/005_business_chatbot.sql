-- Business-specific Instagram assistant. Existing keyword rules are unchanged.
begin;
create table if not exists public.business_chatbots (
  workspace_id uuid primary key references public.workspaces(id) on delete cascade,
  business_name text not null default '',
  role text not null default 'support' check (role in ('support','sales','feedback')),
  knowledge text not null default '',
  instructions text not null default '',
  handoff_message text not null default 'Thanks! A team member will help you here shortly.',
  daily_limit integer not null default 20 check (daily_limit between 1 and 100),
  enabled boolean not null default false,
  updated_at timestamptz not null default now()
);
create table if not exists public.chatbot_contacts (
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  connection_id uuid not null references public.social_connections(id) on delete cascade,
  sender_id text not null,
  paused boolean not null default true,
  reason text,
  updated_at timestamptz not null default now(),
  primary key(connection_id,sender_id)
);
create table if not exists public.chatbot_runs (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  event_id uuid unique references public.automation_events(id) on delete set null,
  purpose text not null check (purpose in ('preview','live')),
  status text not null default 'reserved' check (status in ('reserved','generated','failed')),
  created_at timestamptz not null default now()
);
create index if not exists chatbot_runs_workspace_day on public.chatbot_runs(workspace_id,purpose,created_at);
alter table public.business_chatbots enable row level security;
alter table public.chatbot_contacts enable row level security;
alter table public.chatbot_runs enable row level security;
-- Only the trusted backend may read business knowledge or reserve AI usage.
revoke all on public.business_chatbots, public.chatbot_contacts, public.chatbot_runs from anon, authenticated;
grant all on public.business_chatbots, public.chatbot_contacts, public.chatbot_runs to service_role;

create or replace function public.reserve_chatbot_run(p_workspace uuid,p_purpose text,p_event uuid default null)
returns uuid language plpgsql security definer set search_path = public as $$
declare v_limit integer; v_id uuid;
begin
  if p_purpose not in ('preview','live') then raise exception 'Invalid purpose'; end if;
  perform pg_advisory_xact_lock(hashtextextended(p_workspace::text || ':chatbot',0));
  if p_event is not null and exists(select 1 from chatbot_runs where event_id=p_event) then return null; end if;
  if p_purpose='preview' then v_limit:=20;
  else
    select daily_limit into v_limit from business_chatbots where workspace_id=p_workspace and enabled;
    if v_limit is null then return null; end if;
  end if;
  if (select count(*) from chatbot_runs where workspace_id=p_workspace and purpose=p_purpose
      and created_at >= date_trunc('day',now() at time zone 'UTC') at time zone 'UTC') >= v_limit then return null; end if;
  insert into chatbot_runs(workspace_id,event_id,purpose) values(p_workspace,p_event,p_purpose) returning id into v_id;
  return v_id;
end; $$;
revoke all on function public.reserve_chatbot_run(uuid,text,uuid) from public,anon,authenticated;
grant execute on function public.reserve_chatbot_run(uuid,text,uuid) to service_role;
notify pgrst,'reload schema';
commit;
