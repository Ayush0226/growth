# GBP integration status

The Google module release is 39c5897, live on Growboard's Render frontend and backend. Connection setup is enabled; automatic delivery and MCP are disabled. The migration is not complete: real Google consent, end-to-end checks, remaining compatibility adapters and selected historical data import are outstanding.

## Implemented and deployed

- Captured 69 legacy HTTP endpoint contracts, 32 request models and source hashes in legacy-contract.json. This inventory is not a claim that all 69 paths are compatible.
- Dedicated workspace-scoped Google module; existing Meta routes remain in place.
- Backend OAuth with PKCE, hashed one-use state, owner revalidation, encrypted refresh grants and connection revision checks. Google authorization is separate from Supabase app login.
- Paginated accounts/locations, authoritative ownership sync and canonical-location uniqueness.
- Paginated review reads, manual replies/revisions/deletion, AI drafts, automatic/draft/approval rules and review job history.
- Durable authenticated notification ingestion, polling fallback, independent worker loop, atomic send claims/quotas, uncertain-write holds, reply reconciliation and pause/disconnect.
- Standard posts, events/offers, drafts/scheduling/cancellation and multi-location campaigns with database-atomic target validation and lifecycle locks.
- Independent private media library and Cloudflare Image Studio with bounded image decoding and duplicate-generation protection.
- Google performance/keywords, measured local rank reports and authenticated PDF download; rank and text-generation algorithms ported from verified GBP source.
- Twenty MCP tool adapters use the same workspace-checked handlers; OAuth browser sessions are rejected, pilot access is rechecked, and MCP remains disabled until linking is verified.
- Google workspace UI, campaigns/media screens, draft/approval controls and OAuth consent screen.

## External setup and release gates

1. Isolated dependency installation completed. Latest backend, SQL and frontend checks passed; retain these checks for subsequent edits.
2. Review per-endpoint compatibility gaps against legacy-contract.json. User/admin/billing/onboarding settings, exact legacy calendar formats, account-default rules, batch workflows, Pollinations linking and MCP output schemas still require explicit parity decisions/adapters; these must not be presented as fully migrated. Retired credits and payments must remain retired.
3. Applied additive migration 20261121192057_growboard_google_workspace to Growboard project vcbpmtfarhhdjrnuwlts. All 12 new tables have RLS enabled and no anon/authenticated read grants. Existing GBP project jphuhxzhnqmhgnneaqmo stays untouched.
4. Created separate Growboard Web OAuth client in approved Google Cloud project steady-ether-500708-n8 (Google Busniess), after explicit user confirmation. Callback: https://business-growth-platform-api.onrender.com/api/integrations/google/callback. Existing Review AI web App client/callback unchanged. No refresh tokens transferred. Audience is External / In production; branding verified; business.manage is registered as non-sensitive.
5. Added GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI and GOOGLE_FRONTEND_URL=https://growboard.in to the Growboard backend using merge-only Render updates. Deployed first with all Google flags off, verified API health/readiness/CORS and authentication, then requested GOOGLE_ENABLED=true. GOOGLE_WORKER_ENABLED=false and GOOGLE_MCP_ENABLED=false. Existing TOKEN_ENCRYPTION_KEY preserved. Credential copy encrypted with Windows DPAPI outside the repository; temporary plaintext removed.
6. Connect a real workspace, sync one location, verify review reads, then one designated manual reply/post. No customer review or post has been sent in this task.
7. Inspect the existing account-level notification topic before adding a subscriber. Do not overwrite GBP notification settings. Configure OIDC audience/service-account checks before accepting events.
8. Confirm one active automatic reply product for the test location; enable/test automatic delivery and pause/restart/duplicate/uncertain cases before expanding.
9. Configure Supabase URL allowlist and OAuth Server/consent/client settings before enabling MCP. Provider consent remains a user action.
10. Map old GBP user IDs to Growboard user/workspace IDs from verified identities before importing selected history/settings. Import with jobs paused; never replay old queues. No live data or token import has occurred.

## Snapshot

Encrypted Windows-DPAPI snapshot saved under output/gbp-migration; 34 public tables, 138 rows and 3 Auth admin records. Encryption round-trip checked. This logical snapshot excludes storage file contents and is not a physical point-in-time database backup or tested full restoration. The snapshot is tied to this Windows account. It must never be committed.

## Access blocker

Google Cloud project is identified and accessible. User requested help signing into Growboard and Supabase. Verified the owner's existing Growboard email account and prepared its login form; no password was read, entered or changed. Supabase Auth dashboard setup still needs sign-in. A real Google workspace connection/consent remains a user action; automated delivery remains paused. No existing Google client, customer grant, IAM role or GBP notification topic was changed.

## Latest verification checkpoint

- Full backend suite in the isolated project environment: 165 passed. Includes pinned MCP 2 factory/schema/annotation tests, rejection of browser tokens, blank reply rejection and paused-scheduler guards. Added tzdata for portable IANA timezone support on Windows.
- Frontend build including Google workspace, campaigns/media and OAuth consent: passed.
- SQL sandbox test: ownership, one-use state, quotas, duplicate claims, pause/disconnect, atomic campaign target validation, campaign cancellation and backend-only grants passed.
- MCP 2 uses snake_case model fields; tool metadata and its contract tests were corrected and verified in the isolated environment. The system MCP remains compatible with the existing openai-agents installation.
- New schema and credentials are prepared in production. Integration source 39c5897 is live on both Render services. API reports version 0.8.0; health/readiness and Growboard CORS return 200; unauthenticated Google and Instagram routes return 401. Google connection enablement update accepted; worker and MCP flags remain OFF. No review reply, business post, account grant or history/token import has occurred.
