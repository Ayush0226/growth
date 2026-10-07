# Growthboard backend

FastAPI foundation for the Instagram MVP. It includes:

- Supabase JWT authentication.
- One-workspace provisioning.
- Hashed, expiring, single-use Instagram OAuth state.
- Server-side code exchange and long-lived token exchange.
- Encrypted access-token storage.
- Granted-permission detection and connection status.
- Disconnect/revoke flow with cancellation of pending jobs.
- Workspace-scoped PostgreSQL schema and RLS migration.

## Local setup

1. Create a Supabase project and run `supabase/migrations/001_initial_schema.sql` in its SQL editor.
2. Copy `.env.example` to `.env` and set every secret. Generate `TOKEN_ENCRYPTION_KEY` with a password manager or `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
3. Create a virtual environment and run `pip install -e .[dev]`.
4. Run `uvicorn app.main:app --reload --no-access-log`.
5. Run tests with `pytest`.

Never commit `.env`, Meta secrets, service-role keys, access tokens, or production customer data. Confirm the active Meta Graph API version and Instagram Login endpoint behavior in Meta's current documentation before production deployment.

## Meta configuration

Set the OAuth callback to `/api/integrations/instagram/callback`. Production also needs separate deauthorization and data-deletion endpoints before App Review; the database includes deletion requests, but those public callback implementations are intentionally not represented as complete until Meta app credentials and signing behavior can be integration-tested.
