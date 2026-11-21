-- Additive Google module. No existing Meta tables, users, grants or jobs are changed.
begin;
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('gbp-media','gbp-media',false,8388608,array['image/jpeg']) on conflict(id) do nothing;

create table public.gbp_connections (
  workspace_id uuid primary key references public.workspaces(id) on delete cascade,
  connected_by uuid not null references auth.users(id),
  google_subject text not null,
  email text,
  refresh_token_cipher text,
  scopes text[] not null default '{}',
  status text not null default 'active' check(status in ('active','needs_reauth','disconnected')),
  revision uuid not null default gen_random_uuid(),
  connected_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create table public.gbp_oauth_states (
  state_hash text primary key,
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  user_id uuid not null references auth.users(id),
  verifier_cipher text not null,
  expires_at timestamptz not null default now()+interval '10 minutes',
  created_at timestamptz not null default now()
);
create table public.gbp_locations (
  name text primary key check(name ~ '^accounts/[A-Za-z0-9_-]+/locations/[A-Za-z0-9_-]+$'),
  workspace_id uuid not null references public.gbp_connections(workspace_id) on delete cascade,
  title text not null,
  account_name text not null,
  account_display_name text,
  metadata jsonb not null default '{}',
  active boolean not null default true,
  synced_at timestamptz not null default now(),
  unique(workspace_id,name)
);
create index gbp_locations_workspace on public.gbp_locations(workspace_id,active);
create unique index gbp_location_canonical_owner on public.gbp_locations((split_part(name,'/',4)));
create table public.gbp_review_rules (
  location_name text primary key,
  workspace_id uuid not null,
  enabled boolean not null default false,
  enabled_at timestamptz,
  enabled_by uuid references auth.users(id),
  delivery_owned boolean not null default false,
  mode text not null default 'draft' check(mode in ('draft','approval','auto_publish')),
  rating_min integer not null default 4 check(rating_min between 1 and 5),
  rating_max integer not null default 5 check(rating_max between 1 and 5 and rating_max>=rating_min),
  delay_minutes integer not null default 0 check(delay_minutes between 0 and 10080),
  daily_limit integer not null default 20 check(daily_limit between 1 and 1000),
  tone text not null default 'friendly',
  language text not null default 'English',
  custom_instructions text not null default '',
  blocked_terms text[] not null default '{}',
  business_context text not null default '',
  updated_at timestamptz not null default now(),
  foreign key(workspace_id,location_name) references public.gbp_locations(workspace_id,name),
  check(not enabled or (enabled_at is not null and enabled_by is not null and delivery_owned))
);
create index gbp_rules_workspace on public.gbp_review_rules(workspace_id,enabled);
create table public.gbp_review_jobs (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  location_name text not null,
  review_name text not null unique,
  review_data jsonb not null,
  reply_text text,
  status text not null default 'pending' check(status in
    ('pending','generating','draft','approval','ready','publishing','sent','skipped','failed','uncertain','cancelled')),
  not_before timestamptz not null default now(),
  lease_owner uuid,
  lease_until timestamptz,
  reserved_on date,
  manual boolean not null default false,
  error_code text,
  provider_result jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key(workspace_id,location_name) references public.gbp_locations(workspace_id,name)
);
create index gbp_review_jobs_due on public.gbp_review_jobs(status,not_before)
  where status in ('pending','ready','generating','publishing');
create index gbp_review_jobs_history on public.gbp_review_jobs(workspace_id,created_at desc);
create index gbp_review_jobs_quota on public.gbp_review_jobs(location_name,reserved_on)
  where reserved_on is not null;
create table public.gbp_events (
  event_id text primary key,
  payload jsonb not null,
  status text not null default 'pending' check(status in ('pending','processed','failed')),
  attempts integer not null default 0,
  received_at timestamptz not null default now()
);
create index gbp_events_pending on public.gbp_events(received_at) where status='pending';
create table public.gbp_posts (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  location_name text not null,
  request_key uuid not null,
  payload jsonb not null,
  scheduled_for timestamptz,
  status text not null default 'draft' check(status in
    ('draft','scheduled','publishing','published','failed','uncertain','cancelled')),
  lease_until timestamptz,
  provider_result jsonb,
  error_code text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(workspace_id,request_key,location_name),
  foreign key(workspace_id,location_name) references public.gbp_locations(workspace_id,name)
);
create index gbp_posts_due on public.gbp_posts(status,scheduled_for) where status='scheduled';
create index gbp_posts_history on public.gbp_posts(workspace_id,created_at desc);
create table public.gbp_campaigns (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id),
  title text not null,
  timezone text not null default 'Asia/Kolkata',
  created_at timestamptz not null default now()
);
create index gbp_campaign_workspace on public.gbp_campaigns(workspace_id,created_at desc);
alter table public.gbp_posts add column campaign_id uuid references public.gbp_campaigns(id);
create index gbp_posts_campaign on public.gbp_posts(campaign_id);
create table public.gbp_audit (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id),
  user_id uuid references auth.users(id),
  action text not null,
  resource text,
  created_at timestamptz not null default now()
);
create index gbp_audit_workspace on public.gbp_audit(workspace_id,created_at desc);
create table public.gbp_rank_reports (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  location_name text not null,
  request_key uuid not null,
  keyword text not null,
  report jsonb,
  status text not null default 'processing' check(status in ('processing','completed','failed')),
  created_at timestamptz not null default now(),
  unique(workspace_id,request_key),
  foreign key(workspace_id,location_name) references public.gbp_locations(workspace_id,name)
);
create index gbp_rank_workspace on public.gbp_rank_reports(workspace_id,created_at desc);
create table public.gbp_media_assets (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id),
  created_by uuid not null references auth.users(id),
  storage_path text not null,
  mime_type text not null default 'image/jpeg',
  bytes integer not null,
  width integer not null,
  height integer not null,
  created_at timestamptz not null default now()
);
create index gbp_media_workspace on public.gbp_media_assets(workspace_id,created_at desc);
create table public.gbp_operations (
  operation_key text primary key,
  workspace_id uuid not null references public.workspaces(id),
  status text not null default 'publishing' check(status in ('publishing','completed','failed','uncertain')),
  result jsonb,
  created_at timestamptz not null default now()
);

-- Credentials, state and queues are backend-only. No broad authenticated grants.
do $$ declare t text; begin
  foreach t in array array['gbp_connections','gbp_oauth_states','gbp_locations','gbp_review_rules',
    'gbp_review_jobs','gbp_events','gbp_posts','gbp_campaigns','gbp_audit','gbp_rank_reports','gbp_media_assets','gbp_operations'] loop
    execute format('alter table public.%I enable row level security',t);
    execute format('revoke all on public.%I from public,anon,authenticated',t);
    execute format('grant all on public.%I to service_role',t);
  end loop;
end $$;

create function public.gbp_consume_oauth_state(p_hash text)
returns setof public.gbp_oauth_states language sql security invoker set search_path=public as $$
  delete from gbp_oauth_states where state_hash=p_hash and expires_at>now() returning *;
$$;

create function public.gbp_register_location(p_name text,p_workspace uuid,p_title text,p_account text,p_display text,p_metadata jsonb)
returns boolean language plpgsql security invoker set search_path=public as $$
begin
  insert into gbp_locations(name,workspace_id,title,account_name,account_display_name,metadata)
    values(p_name,p_workspace,p_title,p_account,p_display,p_metadata)
  on conflict(name) do update set title=p_title,account_name=p_account,account_display_name=p_display,
    metadata=p_metadata,active=true,synced_at=now() where gbp_locations.workspace_id=p_workspace;
  return found;
end $$;

-- Only the original authenticated workspace member can complete an OAuth grant.
create function public.gbp_save_connection(p_workspace uuid,p_user uuid,p_subject text,
  p_email text,p_cipher text,p_scopes text[]) returns void
language plpgsql security invoker set search_path=public as $$
begin
  perform 1 from workspace_members where workspace_id=p_workspace and user_id=p_user and role='owner' for update;
  if not found then raise exception 'Workspace owner required'; end if;
  -- Reconnection pauses automation and rotates revision to invalidate in-flight work.
  insert into gbp_connections(workspace_id,connected_by,google_subject,email,refresh_token_cipher,scopes)
    values(p_workspace,p_user,p_subject,p_email,p_cipher,p_scopes)
  on conflict(workspace_id) do update set connected_by=p_user,google_subject=p_subject,
    email=p_email,refresh_token_cipher=p_cipher,scopes=p_scopes,status='active',revision=gen_random_uuid(),updated_at=now();
  update gbp_review_rules set enabled=false,updated_at=now() where workspace_id=p_workspace;
  update gbp_locations set active=false where workspace_id=p_workspace;
  update gbp_review_jobs set status='cancelled',updated_at=now()
    where workspace_id=p_workspace and status in ('pending','generating','ready','draft','approval');
  update gbp_posts set status='cancelled',updated_at=now()
    where workspace_id=p_workspace and status='scheduled';
end $$;

create function public.gbp_disconnect(p_workspace uuid) returns void
language plpgsql security invoker set search_path=public as $$
begin
  update gbp_connections set status='disconnected',refresh_token_cipher=null,revision=gen_random_uuid(),updated_at=now()
    where workspace_id=p_workspace;
  update gbp_review_rules set enabled=false,updated_at=now() where workspace_id=p_workspace;
  update gbp_review_jobs set status='cancelled',updated_at=now()
    where workspace_id=p_workspace and status in ('pending','generating','ready','draft','approval');
  update gbp_posts set status='cancelled',updated_at=now() where workspace_id=p_workspace and status='scheduled';
  delete from gbp_oauth_states where workspace_id=p_workspace;
end $$;

create function public.gbp_claim_reply(p_job uuid,p_holder uuid) returns boolean
language plpgsql security invoker set search_path=public as $$
declare j gbp_review_jobs; r gbp_review_rules; c gbp_connections; used integer;
begin
  -- One location rule serializes quota reservations across competing jobs.
  select * into j from gbp_review_jobs where id=p_job;
  if not found then return false; end if;
  select * into c from gbp_connections where workspace_id=j.workspace_id for update;
  if c.status is distinct from 'active' then return false; end if;
  select * into r from gbp_review_rules where location_name=j.location_name for update;
  if not j.manual and (not found or not r.enabled or not r.delivery_owned) then return false; end if;
  select * into j from gbp_review_jobs where id=p_job for update;
  if j.status<>'ready' or j.not_before>now() then return false; end if;
  if not j.manual then
    select count(*) into used from gbp_review_jobs
      where location_name=j.location_name and reserved_on=(now() at time zone 'UTC')::date;
    if used>=r.daily_limit then return false; end if;
  end if;
  update gbp_review_jobs set status='publishing',lease_owner=p_holder,
    lease_until=now()+interval '5 minutes',reserved_on=(now() at time zone 'UTC')::date,updated_at=now()
    where id=p_job;
  return true;
end $$;

create function public.gbp_claim_post(p_post uuid) returns boolean
language plpgsql security invoker set search_path=public as $$
declare j gbp_posts;
begin
  select * into j from gbp_posts where id=p_post;
  if not found then return false; end if;
  if j.campaign_id is not null then
    perform 1 from gbp_campaigns where id=j.campaign_id for update;
  end if;
  perform 1 from gbp_connections where workspace_id=j.workspace_id and status='active' for update;
  if not found then return false; end if;
  update gbp_posts set status='publishing',lease_until=now()+interval '5 minutes',updated_at=now()
    where id=p_post and status='scheduled' and scheduled_for<=now();
  return found;
end $$;

create function public.gbp_create_campaign(p_workspace uuid,p_id uuid,p_title text,p_timezone text,p_locations text[],p_payload jsonb)
returns uuid language plpgsql security invoker set search_path=public as $$
declare loc text;
begin
  if cardinality(p_locations) not between 1 and 100 then raise exception 'Invalid target count'; end if;
  insert into gbp_campaigns(id,workspace_id,title,timezone) values(p_id,p_workspace,p_title,p_timezone);
  foreach loc in array p_locations loop
    perform 1 from gbp_locations where name=loc and workspace_id=p_workspace and active;
    if not found then raise exception 'Location does not belong to workspace'; end if;
    insert into gbp_posts(workspace_id,location_name,request_key,payload,campaign_id)
      values(p_workspace,loc,p_id,p_payload,p_id);
  end loop;
  return p_id;
end $$;

create function public.gbp_control_campaign(p_workspace uuid,p_id uuid,p_action text,p_when timestamptz)
returns boolean language plpgsql security invoker set search_path=public as $$
begin
  perform 1 from gbp_campaigns where id=p_id and workspace_id=p_workspace for update;
  if not found then return false; end if;
  -- Lock every child before changing any. A claimed child makes cancellation unsafe.
  perform 1 from gbp_posts where campaign_id=p_id order by id for update;
  if p_action='schedule' then
    if p_when is null or p_when<=now() or exists(select 1 from gbp_posts where campaign_id=p_id and status<>'draft') then return false; end if;
    update gbp_posts set status='scheduled',scheduled_for=p_when where campaign_id=p_id;
  elsif p_action='cancel' then
    if exists(select 1 from gbp_posts where campaign_id=p_id and status not in ('draft','scheduled','cancelled')) then return false; end if;
    update gbp_posts set status='cancelled' where campaign_id=p_id;
  else raise exception 'Invalid campaign action'; end if;
  return true;
end $$;

revoke all on function public.gbp_consume_oauth_state(text) from public,anon,authenticated;
revoke all on function public.gbp_register_location(text,uuid,text,text,text,jsonb) from public,anon,authenticated;
revoke all on function public.gbp_save_connection(uuid,uuid,text,text,text,text[]) from public,anon,authenticated;
revoke all on function public.gbp_disconnect(uuid) from public,anon,authenticated;
revoke all on function public.gbp_claim_reply(uuid,uuid) from public,anon,authenticated;
revoke all on function public.gbp_claim_post(uuid) from public,anon,authenticated;
grant execute on function public.gbp_consume_oauth_state(text) to service_role;
grant execute on function public.gbp_register_location(text,uuid,text,text,text,jsonb) to service_role;
grant execute on function public.gbp_save_connection(uuid,uuid,text,text,text,text[]) to service_role;
grant execute on function public.gbp_disconnect(uuid) to service_role;
grant execute on function public.gbp_claim_reply(uuid,uuid) to service_role;
grant execute on function public.gbp_claim_post(uuid) to service_role;
revoke all on function public.gbp_create_campaign(uuid,uuid,text,text,text[],jsonb) from public,anon,authenticated;
revoke all on function public.gbp_control_campaign(uuid,uuid,text,timestamptz) from public,anon,authenticated;
grant execute on function public.gbp_create_campaign(uuid,uuid,text,text,text[],jsonb) to service_role;
grant execute on function public.gbp_control_campaign(uuid,uuid,text,timestamptz) to service_role;
commit;
