begin;
alter table public.whatsapp_connections
  add column connection_mode text not null default 'existing_api' check(connection_mode in ('existing_api','new_number','coexistence')),
  add column contacts_sync_status text not null default 'not_started',
  add column history_sync_status text not null default 'not_started',
  add column history_sync_progress integer not null default 0 check(history_sync_progress between 0 and 100),
  add column contacts_sync_request_id text,
  add column history_sync_request_id text,
  add column sync_warning text not null default '';
alter table public.whatsapp_messages add column is_history boolean not null default false;
alter table public.whatsapp_contacts add column app_synced_at timestamptz;
-- Existing service-role-only grants and RLS remain unchanged.
notify pgrst, 'reload schema';
commit;
