# WhatsApp: current state and exact next steps

Updated 10 November 2026. The authoritative project is this original folder:

`C:\Users\Ayush\OneDrive\Documents\ChatGPT\Instagram Automation`

## Already built locally

- Meta account connection, encrypted authorization and number/workspace checks.
- Direct Meta billing guidance; no Growthboard messaging wallet.
- Inbox, manual replies, contacts and consent imports.
- Welcome/keyword automation, business AI and human takeover.
- Text-template submission/sync, campaign review, scheduling and delivery activity.
- Clear qualification of the current 1,000 eligible service-reply allowance. No ₹1,000 cash signup grant or guaranteed remaining balance is promised.
- Automated tests, migration checks, frontend build and sample-data desktop/mobile walkthrough.

This implementation has not been deployed/activated for live WhatsApp customers. The production WhatsApp database upgrade was applied and verified on 10 November 2026; real-number acceptance remains pending.

## Remaining, in order

1. **Initial Meta test complete.** Growthboard app `1782960182852309` uses the existing `Art Nest Digial Artwork and marketing` portfolio. Meta provided test sender `+1 (555) 170-4092`, Phone Number ID `1420594534475715`, and Messaging account ID `964345243077963`. The user confirmed receipt of the sample test message. This confirms Meta developer-test sending; Growthboard webhook delivery, customer Embedded Signup, and production-number acceptance are still pending. No token was copied into the project or chat. The older `1661705735602387` came from local backend configuration. Use dedicated WhatsApp ID/secret settings for the confirmed app and preserve existing Instagram credentials. Do not deregister/migrate an existing number without reviewing that process.
2. **Production database complete.** Migration `20261110094018_growthboard_whatsapp_activation` was applied to the existing `Insta ai` project. All nine WhatsApp tables have RLS enabled, no direct browser-role access, and the required backend access. The upgrade combines migrations 007/008. Do not reapply the initial workspace schema.
3. **Deploy the updated source.** The user confirmed Render `My Workspace` on connection `Primary`. Both existing services automatically deploy from `Ayush0226/growth`, branch `main`. Review and publish the updated source, initially keeping WhatsApp disabled. Current live release: `d0d1cb7`. No third backend service is required by the current code.
4. **Configure Meta onboarding and event delivery.** Set up the WhatsApp product/use case, Facebook Login for Business/Embedded Signup configuration, allowed website domains and the required permissions. Set the backend variables listed below. Configure the webhook URL and subscribe the app to message events. Keep app secrets server-side.
5. **Enable a controlled pilot and configure direct Meta billing.** Enable WhatsApp only after setup is ready. Connect the test account/number and verify actual incoming messages. Set up the correct WhatsApp account's payment method in Meta for chargeable messages; prepaid UPI availability depends on the account. The Growthboard acknowledgement does not verify a payment or balance
6. **Complete real-number acceptance.** Deliberately send one reviewed manual reply. Test a keyword/welcome rule, duplicate-event handling, STOP, staff takeover and reconnection/disconnection. Confirm receipts. Get one real template approved, record consent for an owned recipient and approve a one-person campaign. Verify scheduling/pause and direct Meta charges. Fix anything exposed by these live tests.
7. **Finish product compatibility and public-customer approval.** Add and test Meta username/BSUID support before public launch: the current parser, contact records, and sending flow use phone-number identifiers and do not implement this new identity path. Complete the applicable Meta business verification, Tech Provider onboarding, App Review/Advanced Access and live-mode requirements before unrelated businesses connect. Confirm the actual signup path, eligible existing-number/coexistence behavior, privacy/support details and background-worker reliability. Review the pre-existing database advisories recorded in `output/whatsapp-2026-11-10/DATABASE_ACTIVATION.md`.
8. **Finalize Growthboard's own fee.** Decide 15% or 20%, its calculation basis and whether there is a minimum monthly fee. Implement separate invoicing/payment collection for this software fee. A customer's Meta top-up does not automatically pay Growthboard commission. This fee collection is not implemented yet; messaging money can continue to go straight to Meta.

Backend configuration:

```text
WHATSAPP_ENABLED=false  # change only when setup is ready for the pilot
WHATSAPP_APP_ID=...
WHATSAPP_APP_SECRET=...
WHATSAPP_SIGNUP_CONFIG_ID=...
WHATSAPP_WEBHOOK_VERIFY_TOKEN=...
```

App ID/secret can fall back to existing Meta credentials if the same app is suitable. Preserve the existing token encryption key. Optional AI uses the existing Groq settings.

Webhook: `https://business-growth-platform-api.onrender.com/api/whatsapp/webhook`

## Where the work is saved

- Application source: `business-growth-platform-backend/app` and `business-growth-platform-ui/src`.
- SQL upgrade: `APPLY_WHATSAPP.sql`; individual migrations are in the backend's `supabase/migrations` folder.
- Product/setup details and current limits: `WHATSAPP_MVP_PLAN.md`.
- Portable local preview and check scripts: `tools/whatsapp-qa`.
- Screenshots, check results, source ZIP and hash manifest: `output/whatsapp-2026-11-10`.

The scripts now resolve project files relative to this folder. The temporary D-drive working directory is not needed to continue work. A secondary copy can remain there for recovery. Private `.env` files stay in their original application folders and are deliberately excluded from the source ZIP.
