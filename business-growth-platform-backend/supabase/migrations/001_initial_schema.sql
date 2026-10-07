begin;

create extension if not exists pgcrypto;

create table public.workspaces (
  id uuid primary key default gen_random_uuid(),
  name text not null check (char_length(name) between 2 and 100),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.workspace_members (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null default 'owner' check (role in ('owner', 'member')),
  created_at timestamptz not null default now(),
  unique (workspace_id, user_id),
  unique (user_id)
);

create table public.social_connections (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  provider text not null check (provider in ('instagram')),
  status text not null default 'active' check (status in ('active', 'expired', 'revoked', 'error')),
  access_token_encrypted text,
  token_expires_at timestamptz,
  granted_scopes text[] not null default '{}',
  connected_by uuid references auth.users(id) on delete set null,
  connected_at timestamptz not null default now(),
  disconnected_at timestamptz,
  updated_at timestamptz not null default now(),
  unique (workspace_id, provider),
  check ((status = 'active' and access_token_encrypted is not null) or status <> 'active')
);

create table public.social_accounts (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  connection_id uuid not null references public.social_connections(id) on delete cascade,
  provider_account_id text not null,
  username text,
  account_type text,
  profile_picture_url text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (connection_id, provider_account_id)
);

create table public.social_permissions (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  connection_id uuid not null references public.social_connections(id) on delete cascade,
  permission text not null,
  status text not null check (status in ('granted', 'declined', 'expired', 'revoked')),
  checked_at timestamptz not null default now(),
  unique (connection_id, permission)
);

create table public.media_assets (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  created_by uuid references auth.users(id) on delete set null,
  original_storage_path text not null,
  prepared_storage_path text,
  media_type text not null check (media_type in ('image', 'video')),
  mime_type text not null,
  bytes bigint not null check (bytes > 0),
  width integer check (width > 0),
  height integer check (height > 0),
  duration_seconds numeric check (duration_seconds >= 0),
  validation_status text not null default 'pending' check (validation_status in ('pending', 'valid', 'invalid')),
  validation_errors jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  expires_at timestamptz
);

create table public.content_drafts (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  created_by uuid references auth.users(id) on delete set null,
  post_type text not null check (post_type in ('photo', 'carousel', 'reel')),
  caption text not null default '' check (char_length(caption) <= 2200),
  status text not null default 'draft' check (status in ('draft', 'approved', 'archived')),
  approved_by uuid references auth.users(id) on delete set null,
  approved_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check ((status <> 'approved') or (approved_by is not null and approved_at is not null))
);

create table public.content_draft_media (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  draft_id uuid not null references public.content_drafts(id) on delete cascade,
  media_asset_id uuid not null references public.media_assets(id) on delete cascade,
  position smallint not null check (position between 0 and 9),
  unique (draft_id, position),
  unique (draft_id, media_asset_id)
);

create table public.content_targets (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  draft_id uuid not null references public.content_drafts(id) on delete cascade,
  social_account_id uuid not null references public.social_accounts(id) on delete cascade,
  scheduled_for timestamptz,
  timezone text not null default 'UTC',
  created_at timestamptz not null default now(),
  unique (draft_id, social_account_id)
);

create table public.publishing_jobs (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  content_target_id uuid not null references public.content_targets(id) on delete cascade,
  status text not null default 'scheduled' check (status in ('draft', 'scheduled', 'processing', 'published', 'failed', 'cancelled')),
  idempotency_key uuid not null default gen_random_uuid() unique,
  attempt_count integer not null default 0 check (attempt_count >= 0),
  scheduled_for timestamptz not null,
  locked_at timestamptz,
  locked_by text,
  provider_container_id text,
  provider_media_id text,
  provider_permalink text,
  failure_code text,
  failure_message text,
  retryable boolean not null default false,
  next_attempt_at timestamptz,
  published_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.usage_counters (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  period_start date not null,
  posts_count integer not null default 0 check (posts_count between 0 and 10),
  ai_requests_count integer not null default 0 check (ai_requests_count >= 0),
  storage_bytes bigint not null default 0 check (storage_bytes >= 0),
  unique (workspace_id, period_start)
);

create table public.deletion_requests (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid references public.workspaces(id) on delete set null,
  requested_by uuid references auth.users(id) on delete set null,
  request_type text not null check (request_type in ('instagram_data', 'account', 'meta_callback')),
  confirmation_code text not null unique,
  status text not null default 'pending' check (status in ('pending', 'processing', 'completed', 'failed')),
  requested_at timestamptz not null default now(),
  completed_at timestamptz,
  detail jsonb not null default '{}'::jsonb
);

create table public.audit_events (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  actor_user_id uuid references auth.users(id) on delete set null,
  event_type text not null,
  subject_type text,
  subject_id text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table public.oauth_states (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  provider text not null check (provider = 'instagram'),
  state_hash text not null unique check (char_length(state_hash) = 64),
  expires_at timestamptz not null,
  consumed_at timestamptz,
  created_at timestamptz not null default now()
);

create index publishing_jobs_due_idx on public.publishing_jobs (scheduled_for)
  where status = 'scheduled';
create index audit_events_workspace_created_idx on public.audit_events (workspace_id, created_at desc);
create index oauth_states_expiry_idx on public.oauth_states (expires_at) where consumed_at is null;
create index media_assets_workspace_idx on public.media_assets (workspace_id);
create index content_drafts_workspace_idx on public.content_drafts (workspace_id);

create or replace function public.is_workspace_member(candidate_workspace_id uuid)
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.workspace_members
    where workspace_id = candidate_workspace_id and user_id = auth.uid()
  );
$$;

create or replace function public.create_workspace_for_user(workspace_name text, owner_id uuid)
returns uuid language plpgsql security definer set search_path = '' as $$
declare new_workspace_id uuid;
begin
  if owner_id is distinct from auth.uid() and auth.role() <> 'service_role' then
    raise exception 'Cannot create a workspace for another user';
  end if;
  if exists (select 1 from public.workspace_members where user_id = owner_id) then
    raise exception 'User already belongs to a workspace';
  end if;
  insert into public.workspaces(name) values (workspace_name) returning id into new_workspace_id;
  insert into public.workspace_members(workspace_id, user_id, role) values (new_workspace_id, owner_id, 'owner');
  return new_workspace_id;
end;
$$;

revoke all on function public.create_workspace_for_user(text, uuid) from public;
grant execute on function public.create_workspace_for_user(text, uuid) to service_role;

alter table public.workspaces enable row level security;
alter table public.workspace_members enable row level security;
alter table public.social_connections enable row level security;
alter table public.social_accounts enable row level security;
alter table public.social_permissions enable row level security;
alter table public.media_assets enable row level security;
alter table public.content_drafts enable row level security;
alter table public.content_draft_media enable row level security;
alter table public.content_targets enable row level security;
alter table public.publishing_jobs enable row level security;
alter table public.usage_counters enable row level security;
alter table public.deletion_requests enable row level security;
alter table public.audit_events enable row level security;
alter table public.oauth_states enable row level security;

create policy "members read their workspace" on public.workspaces for select to authenticated
  using (public.is_workspace_member(id));
create policy "members read their membership" on public.workspace_members for select to authenticated
  using (user_id = auth.uid());

-- Sensitive integration rows are backend-only. Product-owned content can be read by workspace members.
create policy "members read social accounts" on public.social_accounts for select to authenticated
  using (public.is_workspace_member(workspace_id));
create policy "members read media" on public.media_assets for select to authenticated
  using (public.is_workspace_member(workspace_id));
create policy "members read drafts" on public.content_drafts for select to authenticated
  using (public.is_workspace_member(workspace_id));
create policy "members read draft media" on public.content_draft_media for select to authenticated
  using (public.is_workspace_member(workspace_id));
create policy "members read targets" on public.content_targets for select to authenticated
  using (public.is_workspace_member(workspace_id));
create policy "members read jobs" on public.publishing_jobs for select to authenticated
  using (public.is_workspace_member(workspace_id));
create policy "members read usage" on public.usage_counters for select to authenticated
  using (public.is_workspace_member(workspace_id));
create policy "members read deletion requests" on public.deletion_requests for select to authenticated
  using (requested_by = auth.uid());
create policy "members read audits" on public.audit_events for select to authenticated
  using (public.is_workspace_member(workspace_id));

-- Private media bucket. Signed URLs must be minted by the backend only.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('instagram-media', 'instagram-media', false, 104857600, array['image/jpeg', 'video/mp4'])
on conflict (id) do nothing;

commit;
