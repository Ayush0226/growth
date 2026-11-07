# Google sign-in and first-use access

The intended flow is Google/email sign-in → one-time administrator access code → business workspace → connect Instagram. Approval is saved per Supabase user. The shared code is not the user's Google password or personal account password.

## What the code implements

- Google sign-in through the Instagram project's Supabase Auth. The button checks whether Google is enabled before starting the redirect.
- First-use `/access` page after login, with a server-side access check on every protected API call.
- Code approval saved to a server-only table; the shared code is never included in website assets or saved in the approval row.
- Five redemption attempts per account per fifteen-minute window, counted atomically in the database.
- Existing workspace members receive approvals in the migration. Their existing Instagram rules and scheduled work continue.
- A revoked approval cannot be restored by re-entering the shared code.
- Database restrictions retain workspace isolation for direct Supabase reads.

## Required setup

### 1. Supabase database

Run `APPLY_ACCESS_UPGRADE.sql` in the current Instagram Supabase SQL editor. This is migration `006_pilot_access.sql`; it must be applied after the existing workspace schema.

### 2. Render backend

Open **business-growth-platform-api → Environment**. Add `PILOT_ACCESS_CODE` with the shared code specified by the owner, then choose **Save and deploy**. It is case-sensitive. Do not add this secret to the frontend environment or commit it to source control.

### 3. Google Cloud OAuth client

Use a Google OAuth **Web application** client. If reusing the existing GBP login client, add these URLs to it rather than replacing URLs GBP already uses:

- Authorized JavaScript origin: `https://growthboard-web.onrender.com`
- Authorized redirect URI: `https://vcbpmtfarhhdjrnuwlts.supabase.co/auth/v1/callback`

Google login only requests identity/profile/email for app login. Connecting an Instagram business remains a separate action in Growthboard. Google sign-in does not connect Google Business Profile or Instagram automatically.

### 4. Supabase Google provider

In the **Instagram Supabase project → Authentication → Sign In / Providers → Google**, supply the Web application's client ID and client secret, enable Google and save. Keep the client secret private.

In **Authentication → URL Configuration**:

- Site URL: `https://growthboard-web.onrender.com`
- Allowed redirect URL: `https://growthboard-web.onrender.com/access`

### 5. Verify

Use a new account: Google login should return to `/access`; an incorrect code should be rejected; the correct code should unlock workspace creation. Sign out and sign back into that same account: it should retain approval. A different new account should still need its own redemption.

An existing workspace account should remain usable after deployment. Verify a current rule and worker health without sending unsolicited messages.

## Shared GBP / Instagram / WhatsApp access

This change establishes the Instagram app's access flow. GBP currently uses a separate backend/auth setup; reusing the same Google account does not by itself create a shared session or transfer a paid entitlement. A truly shared product needs one identity/entitlement source and explicit account/workspace mapping across the modules.

Free hosting can serve the common login and dashboard. Render's 750 free instance-hours are shared across free web services in a workspace, so separate always-running servers consume that allowance together. Workload capacity must be measured; a shared login is not a guarantee of timely automation delivery on free compute.

Sources: [Supabase Google sign-in](https://supabase.com/docs/guides/auth/social-sign-in/auth-google), [Render Free](https://render.com/docs/free).
