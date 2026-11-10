# Growthboard WhatsApp activation: steps 1 to 7

Checked 10 November 2026. Source is saved in the original Instagram Automation folder. The WhatsApp product is built locally and its production database upgrade is complete; deployment and live Meta activation are pending.

## 1. Check the existing Meta app

The user identified the **Growthboard** Meta app as **1782960182852309**, using this WhatsApp setup page: https://developers.facebook.com/apps/1782960182852309/whatsapp-business/wa-tools/?business_id=726178539900233 . The earlier ID `1661705735602387` came from local backend configuration and must not be treated as the confirmed WhatsApp app.

The user chose to keep **Art Nest Digial Artwork and marketing** as the same business portfolio. The latest pasted screen shows WhatsApp **Quickstart**, **Test the API**, **Become a Tech Provider**, and an **Action Required** notice: **This feature is not available. Create a WhatsApp Business Account to get started.** No usable account is confirmed available to the affected feature; an account could still exist elsewhere in the portfolio. Open **Test the API** and follow its account-selection/creation and test-assets setup. Use the same portfolio and select the intended existing WABA if offered. The earlier setup screen offered a test number limited to five recipient numbers. Embedded Signup configuration remains pending.

Use this app's matching ID and secret in the dedicated `WHATSAPP_APP_ID` and `WHATSAPP_APP_SECRET` backend settings. Do not replace existing Instagram Meta settings or pair the new WhatsApp app ID with the older app's secret. No secret or runtime configuration was changed when recording this correction.

- If WhatsApp is already present, open its setup area.
- If the app offers WhatsApp as an additional use case/product, add it to this app.
- If WhatsApp is unavailable, first confirm the app's supported configuration. A separate Meta app may be necessary, while Growthboard continues to use the same website and backend.

Use Meta's provided test setup or an owned test number for the initial pilot. Test assets used for a basic API exercise and assets eligible for Embedded Signup may differ; successful onboarding must also be tested in step 5. Do not delete or migrate an active business number as part of this check.

**Finished when:** we know the WhatsApp app ID and the intended test account/number. Keep app secrets and access tokens out of chat and screenshots.

**Initial test completed:** the user confirmed receiving Meta's sample message from test sender `+1 (555) 170-4092`. The setup page identifies Phone Number ID `1420594534475715` and Messaging account ID `964345243077963`. No access token was copied here. This verifies Meta developer-test sending; Growthboard webhook integration, Embedded Signup, and real-number acceptance remain pending. Next inspect the app's WhatsApp Configuration page and prepare the backend deployment before attempting Growthboard callback verification.

## 2. Add the WhatsApp database tables

**Completed on 10 November 2026** in Supabase project **Insta ai**, reference `vcbpmtfarhhdjrnuwlts`, with migration `20261110094018_growthboard_whatsapp_activation`.

All nine WhatsApp tables have RLS enabled. Direct anonymous and signed-in browser access is denied; the backend role has the required access. Foreign keys and the immutable-number trigger were verified. The AI budget function uses caller permissions and is executable only by the backend role; its non-existent-connection check returned false. Local migration replay, workspace isolation, number locking, and atomic AI budget checks passed.

The upgrade combines migrations 007 and 008. The initial application schema was not rerun. Do not repeat this step during setup.

## 3. Publish the updated Growthboard source

The user confirmed **My Workspace**, Render connection **Primary**. Both existing services are connected to `https://github.com/Ayush0226/growth`, branch `main`, with automatic deployment on commit. Their current live release is `d0d1cb7be02a578d4963241382786754417fad64`, which predates the local WhatsApp product changes.

Review and publish the intended source changes to this repository, then monitor the automatic deployments of the existing services:

- Frontend: https://growthboard-web.onrender.com
- Backend: https://business-growth-platform-api.onrender.com

Keep `WHATSAPP_ENABLED=false` for this initial release. Preserve the existing encryption key and Instagram configuration. Check the frontend and backend readiness after deployment.

**Finished when:** both services run the updated release successfully. No additional application service is required by the current implementation.

## 4. Configure Meta signup and webhook delivery

In the selected Meta app, configure Facebook Login for Business / WhatsApp Embedded Signup for the Growthboard website. Obtain the signup configuration ID. The connection code requires `whatsapp_business_management` and `whatsapp_business_messaging`; check Meta's current setup for any additional permissions and access requirements applicable to this app.

When the app dashboard offers **Facebook Login for Business → Configurations**, open it and create a configuration for **WhatsApp Embedded Signup**. Follow Meta's current access/token options for that flow, select the required WhatsApp permissions, save, and copy its **Configuration ID**. If this area is missing, report the visible use-case/product options before creating another app or selecting a different login flow. Meta's detailed documentation currently requires login or returns a rate limit to our documentation fetch, so confirm the actual dashboard choices.

Add the following settings to the existing backend service's environment:

```text
WHATSAPP_ENABLED=false
WHATSAPP_APP_ID=1782960182852309
WHATSAPP_APP_SECRET=<that app's secret>
WHATSAPP_SIGNUP_CONFIG_ID=<the Embedded Signup configuration ID>
WHATSAPP_WEBHOOK_VERIFY_TOKEN=<a newly generated random verification value>
```

Configure the allowed website domain/origin for `https://growthboard-web.onrender.com` in the relevant Meta login settings. Follow the current dashboard's URL validation requirements. Store secrets in backend hosting settings.

Set the WhatsApp webhook callback to:

```text
https://business-growth-platform-api.onrender.com/api/whatsapp/webhook
```

Use the identical verification value in Meta and the backend. Verify the callback and subscribe to the WhatsApp `messages` field. The backend also subscribes the connected business account during connection.

**Current webhook-screen checkpoint:** Meta's pasted Production setup page explicitly says Development mode receives only dashboard test webhooks, and production data (including app admins/developers/testers) requires Live mode. Callback verification and dashboard test events are separate from production-message acceptance. Do not count a Development-mode dashboard test as a completed real-message test. Move to Live only when the applicable app requirements and pilot configuration are ready.

A random verification token has been prepared in the ignored private file `business-growth-platform-backend/.env.whatsapp-setup`. This is a self-chosen callback verification value, separate from the Meta API access token. It has not been installed on Render. The updated backend also remains unpublished, so the proposed callback must not be presented as verified yet. The client-certificate option is optional; the current implementation uses HTTPS and Meta's signed-event validation and has no client-certificate setup.

**Finished when:** Meta verifies the callback, the correct signup configuration is saved, and the production app reports that signup is configured.

## 5. Connect the pilot account and configure direct Meta billing

Enable WhatsApp for the pilot after steps 2–4 are ready. In Growthboard, sign in and open **WhatsApp → Connection & billing → Connect with Meta**. Complete Meta's business/account/number selection using assets permitted for this test. Complete number verification or registration only when requested for that onboarding route.

In the connected WhatsApp account's Meta billing settings, the account owner adds the payment method or available prepaid funding option needed for chargeable messaging. Payment goes directly to Meta. A temporary developer test token is not the production customer connection.

Use Growthboard's **Open Meta billing** link, select the connected **WhatsApp Business Account**, then its payment settings. Add the available payment method; use a prepaid top-up only if Meta offers it for that account. This is separate from an advertising account's balance. Complete OTP/financial authorization directly in Meta. Ordinary customers will repeat this connection and payment setup for their own accounts.

**Finished when:** Growthboard shows the intended number and an incoming message from an owned test recipient appears in its inbox. Growthboard's billing acknowledgement is not payment or balance verification.

## 6. Test the complete messaging flow

Use a reviewed message and an owned recipient for the first outbound test. Check a manual reply, keyword/welcome automation, STOP handling, staff takeover, and delivery receipts. Confirm duplicate events do not duplicate replies and reconnection behaves correctly.

A simple first walkthrough is:

1. From a second phone, send `hello` to the connected business number. Confirm it appears in **Inbox**.
2. In **Inbox**, select that conversation, enter a reviewed reply, and choose **Queue reply**. Check arrival on the second phone and delivery status in **Activity**.
3. In **Automations**, create a keyword rule: keyword `price`, reply `Thanks for asking. Our team will share pricing shortly.` Save it paused, review, and explicitly enable it. Resume automation for the test contact if the manual reply paused it. Send `price` from the second phone and confirm one reply.
4. Send `STOP` and confirm the contact is opted out and further automation is suppressed. Do not bypass an opt-out for subsequent campaign tests; use a separate consenting test contact or the supported re-consent process.
5. Use **Take over** on a suitable test conversation and confirm automation pauses.

Submit one text template for Meta approval. Once approved, record the recipient's consent and review a one-recipient campaign. Verify sending, scheduling, pausing, and receipts before expanding the audience. Confirm chargeable delivery in Meta's own billing records.

**Finished when:** these real-number checks pass and any issues they expose are fixed. Bulk campaigns use the same Growthboard campaign queue and approved templates, subject to Meta's applicable limits.

## 7. Prepare for other businesses to connect

Complete the business verification, Tech Provider/access verification, App Review/Advanced Access, and live-mode requirements applicable to this app. Prepare the reviewer login, signup demonstration, messaging demonstration, and public privacy/support information. Meta controls approval and timing.

Verify the onboarding route for an unrelated eligible business and confirm background processing remains reliable on the chosen hosting plan.

Before public launch, implement and test **WhatsApp username / Business Scoped User ID (BSUID)** compatibility. The current webhook parser reads `messages[].from` as a numeric phone identifier, and contacts and sends use phone-number IDs. It has no BSUID-only identity path. Meta's username rollout can replace the phone identifier for users who adopt usernames, so webhook parsing, contact identity storage, replies, receipts, consent/opt-out matching, and campaign eligibility need corresponding updates. This work has not been implemented. [Meta's explanation](https://developers.meta.com/resources/videos/whatsapp-usernames/).

The database security advisor also reported pre-existing warnings concerning older public functions and password protection. These are separate from the new WhatsApp tables and need review before public launch. See the database activation report saved in `output/whatsapp-2026-11-10/DATABASE_ACTIVATION.md`.

**Finished when:** Meta permits the intended public use and another eligible business can connect its own number and complete the tested flow.

## Separate pricing decision

The proposed 15–20% Growthboard software fee still needs a chosen percentage, calculation basis, and collection method. Customer payments to Meta do not automatically pay this fee to Growthboard. This fee collection is not implemented.
