# Growthboard UI

React/TypeScript MVP frontend with Supabase email authentication, workspace onboarding, required public policy pages, and Instagram connection management.

## Local setup

1. Copy `.env.example` to `.env.local` and fill in the public Supabase URL and anon key plus the backend URL.
2. Run `npm install`.
3. Run `npm run dev`.

The browser must never receive `META_APP_SECRET`, a Supabase service-role key, or an Instagram access token.

