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
