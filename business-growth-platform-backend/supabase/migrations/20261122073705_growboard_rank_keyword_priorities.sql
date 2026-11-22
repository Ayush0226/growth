begin;
create table public.gbp_rank_keyword_sets (
  location_name text primary key,
  workspace_id uuid not null,
  keywords jsonb not null default '[]'::jsonb,
  updated_at timestamptz not null default now(),
  foreign key(workspace_id,location_name) references public.gbp_locations(workspace_id,name),
  check(jsonb_typeof(keywords) = 'array' and jsonb_array_length(keywords) <= 10)
);
create index gbp_rank_keyword_sets_workspace on public.gbp_rank_keyword_sets(workspace_id);
alter table public.gbp_rank_keyword_sets enable row level security;
revoke all on public.gbp_rank_keyword_sets from public,anon,authenticated;
grant all on public.gbp_rank_keyword_sets to service_role;
commit;
