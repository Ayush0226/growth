# Growthboard - Instagram MVP

React/TypeScript frontend, FastAPI backend, and Supabase database for one professional Instagram account per workspace.

## MVP scope

- Supabase email sign-in, persistent sessions and workspace onboarding.
- Instagram Login with publishing, comments and messaging permissions; insights are optional.
- Explicitly approved single-JPEG and 2–10-image carousel publishing and scheduling, with slide ordering, calendar editing, cancellation and retry.
- Batch preparation of up to 10 separate photo posts, with individual captions and optional schedule spacing. Stable request IDs make unchanged save retries return the original jobs.
- Manual comment management and an inbox that resolves the connected account dynamically.
- Opt-in welcome-after-first-DM, DM keyword, and selected-post comment-to-private-DM rules.
- Signed webhook validation, durable event deduplication, per-rule daily limits and recipient cooldowns.
- Activity history; uncertain sends are recorded and never retried automatically.
- A distributed worker lease and a Supabase Cron wake-up, so scheduling does not rely on an open laptop.

New automation rules are paused. Enabling a rule in the app explicitly authorises future replies using its displayed text, targets and limits. A welcome reacts to an incoming text message; it is not a new-follower broadcast. Automated DM replies use the standard 24-hour window. Comment private replies use the supported seven-day window. Replies only target the connected business's incoming events.

## Current deployment

- Frontend: https://growthboard-web.onrender.com
- API: https://business-growth-platform-api.onrender.com
- Readiness: https://business-growth-platform-api.onrender.com/health/ready
- API docs: https://business-growth-platform-api.onrender.com/docs

Backend Render root: `business-growth-platform-backend`; build `pip install -e .`; start `uvicorn app.main:app --host 0.0.0.0 --port $PORT --no-access-log`.
Frontend Static Site root: `business-growth-platform-ui`; build `npm ci && npm run build`; publish `dist`; rewrite `/*` to `/index.html`.
Production frontend must set `VITE_API_URL` to the hosted API plus its public Supabase URL/key. Backend secrets belong only in Render.

## Database upgrade and scheduling

For the existing project, run `APPLY_MVP_UPGRADE.sql` in the Supabase SQL Editor. It combines additive migrations 003 and 004. Do not rerun migration 001 against existing tables.

Migration 003 adds automation storage and a service-role-only worker lease. Migration 004 installs `pg_cron`/`pg_net`, generates a scheduler credential privately in the database, and registers `growthboard-mvp-worker` every minute. No credential is embedded in the SQL file. Confirm the correct API URL in migration 004 if deploying elsewhere.

The backend also processes due work every 30 seconds while running. Worker leases expire within two minutes and renew every 20 seconds while active; database requests have bounded timeouts. The hosted trigger wakes an idle Render service. Both paths use the same database lease. Cold starts, outages, quotas and provider limits can delay delivery; scheduled content more than 24 hours overdue is flagged for manual review rather than posted unexpectedly. Inspect the readiness endpoint for the latest worker completion. Supabase Cron's HTTP request result and the application completion heartbeat are distinct signals.

## Meta setup

1. In Instagram API with Instagram Login, register exactly:
   `https://business-growth-platform-api.onrender.com/api/integrations/instagram/callback`
2. Configure Instagram webhooks at:
   `https://business-growth-platform-api.onrender.com/api/instagram/webhook`
3. Use `INSTAGRAM_WEBHOOK_VERIFY_TOKEN` from the backend environment for GET verification. Event signatures are checked with `META_WEBHOOK_APP_SECRET` when configured, otherwise `META_APP_SECRET`. Use the Meta application secret for webhook signatures; a separately issued Instagram Login secret may differ.
4. Subscribe the Meta app to `messages` and `comments`. In development mode, use an approved Instagram tester and a professional account.
5. Reconnect in Growthboard and grant comments/messaging. Then click **Connect automatic replies** in Connections if shown to subscribe that Instagram account to the app.
6. Create a paused rule, review its exact text and target posts, and enable it when ready.

Requested scopes are not assumed granted. The token response's grants are stored; when Meta does not report them, the UI can show limited access rather than claiming all permissions. Production use by unrelated businesses depends on the appropriate Meta access/review status.

## Verification

Backend: `python -m pip install -e ".[dev]"`, then `python -m pytest -q` and `python -m ruff check app tests`.
Frontend: `npm ci`, `npm run build`, `npm run lint`.
Unit tests use isolated fake storage and HTTP transports; they do not publish to Instagram or mutate the production database. SQL upgrade checks were also exercised locally with PGlite, including repeated application, exclusive leases and browser-role isolation. Real Supabase extensions and external delivery require deployment verification.

## Live acceptance steps

- Sign in and verify that the existing workspace is recognised.
- Reconnect Instagram; check actual publishing, comment and message permissions and event subscription.
- Upload an owned JPEG (8 MB maximum), approve it, and publish or schedule it deliberately.
- Confirm calendar status and the resulting Instagram permalink. Do not retry a `processing`/uncertain result before inspecting Instagram.
- From a separate test account, send a DM, verify inbox retrieval, and deliberately send one manual reply.
- Enable a reviewed welcome or keyword rule; send a matching test DM and inspect delivery activity. Re-delivering the same event must not send twice.
- Enable a selected-post comment rule and test a keyword comment on that selected post. Other posts must not trigger it.
- Pause a rule or disconnect; verify subsequent events do not trigger new replies.

## Publishing formats

In **Create**, choose one photo, one carousel, or several separate posts. Carousels support 2–10 JPEG images with matching proportions, one caption and ordered slides. Batch mode creates up to 10 independent photo posts, each with its own caption. Scheduling can use the same time or a chosen number of minutes between posts. Each result appears separately in Calendar.

The composer uploads all selected images before creating jobs and requires approval of the displayed images, order and captions. **Publish now** queues approved jobs for the hosted worker. Independent posts are not an atomic Instagram transaction: partial success remains visible in Calendar. An unchanged retry uses stable request IDs, so it continues or returns an existing job instead of creating another post. Review uncertain results in Calendar before starting new posts. JPEGs are limited to 8 MB each; no video upload or direct PDF message attachment is included.

No schema upgrade is required for this change: the original content tables already support ordered carousel images. Live carousel acceptance still requires an explicitly approved post on the connected Instagram account.

## Boundaries

WhatsApp is implemented behind its setup flag; see [WhatsApp setup](WHATSAPP_MVP_PLAN.md) and apply `APPLY_WHATSAPP.sql` before enabling it. The inbox, text rules, optional business AI, contact consent, templates, campaigns and direct Meta billing share this application. Live account acceptance and Meta approvals remain required.

Branching chatbot flows, AI media generation, Reels/Stories/video-carousel publishing, billing and multi-account agency workflows are outside this MVP. Insights require their own optional permission. This is a private pilot until Meta configuration, legal/contact details and real-account acceptance checks are complete.

References: [Meta's official Instagram collection](https://www.postman.com/meta/instagram/folder/1z5vxzu/instagram-api-with-instagram-login) and [Supabase scheduled HTTP calls](https://supabase.com/docs/guides/database/extensions/pg_net).

