-- First-use access approvals. The shared code is configured only in the backend environment.
begin;
create table if not exists public.pilot_access_grants (
  user_id uuid primary key references auth.users(id) on delete cascade,
  granted_at timestamptz not null default now(),
  source text not null default 'access_code' check (source in ('access_code','existing_workspace')),
  revoked_at timestamptz
);
create table if not exists public.pilot_access_attempts (
  user_id uuid primary key references auth.users(id) on delete cascade,
  window_started_at timestamptz not null default now(),
  attempts integer not null default 0
);
alter table public.pilot_access_grants enable row level security;
alter table public.pilot_access_attempts enable row level security;
revoke all on public.pilot_access_grants,public.pilot_access_attempts from anon,authenticated;
grant all on public.pilot_access_grants,public.pilot_access_attempts to service_role;

-- Preserve access for accounts already using the app. Never overwrite a revocation.
insert into public.pilot_access_grants(user_id,source)
select distinct user_id,'existing_workspace' from public.workspace_members
on conflict(user_id) do nothing;

create or replace function public.has_growthboard_access()
returns boolean language sql stable security definer set search_path = '' as $$
  select exists(select 1 from public.pilot_access_grants
    where user_id=auth.uid() and revoked_at is null);
$$;
revoke all on function public.has_growthboard_access() from public,anon;
grant execute on function public.has_growthboard_access() to authenticated,service_role;

-- Additional restrictions preserve the existing workspace isolation policies.
do $$
declare table_name text;
begin
  foreach table_name in array array['workspaces','workspace_members','social_accounts','media_assets',
    'content_drafts','content_draft_media','content_targets','publishing_jobs','usage_counters',
    'deletion_requests','audit_events'] loop
    if not exists(select 1 from pg_policies where schemaname='public' and tablename=table_name and policyname='pilot access required') then
      execute format('create policy "pilot access required" on public.%I as restrictive for all to authenticated using (public.has_growthboard_access()) with check (public.has_growthboard_access())',table_name);
    end if;
  end loop;
end $$;

create or replace function public.reserve_pilot_access_attempt(p_user uuid)
returns boolean language plpgsql security definer set search_path = public as $$
declare record_value pilot_access_attempts%rowtype;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_user::text || ':pilot-access',0));
  insert into pilot_access_attempts(user_id) values(p_user) on conflict do nothing;
  select * into record_value from pilot_access_attempts where user_id=p_user for update;
  if record_value.window_started_at <= now()-interval '15 minutes' then
    update pilot_access_attempts set attempts=1,window_started_at=now() where user_id=p_user;
    return true;
  end if;
  if record_value.attempts>=5 then return false; end if;
  update pilot_access_attempts set attempts=attempts+1 where user_id=p_user;
  return true;
end $$;
revoke all on function public.reserve_pilot_access_attempt(uuid) from public,anon,authenticated;
grant execute on function public.reserve_pilot_access_attempt(uuid) to service_role;
notify pgrst,'reload schema';
commit;
