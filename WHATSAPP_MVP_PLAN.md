# WhatsApp in Growthboard

Implemented locally on 10 November 2026. WhatsApp shares the existing FastAPI backend, Supabase workspace and React app. It has not been activated or acceptance-tested against a live Meta customer account. The production database upgrade is complete. Public-launch work also includes adding and testing username/BSUID identity support; the current messaging flow assumes contact phone numbers.

## Customer experience

1. Sign in, create a workspace and open **WhatsApp** in the sidebar.
2. In **Connection & billing**, use Meta Embedded Signup to authorize the business account and eligible number. The backend verifies the issuing app, permissions and number membership before storing encrypted authorization.
3. Configure payment directly in Meta. Growthboard links to Meta Billing & payments; select the connected WhatsApp Business Account. Prepaid/UPI/card options depend on the account. Growthboard's acknowledgement is not payment verification.
4. Enable reviewed welcome/keyword replies or optional business AI. Incoming messages and manual replies appear in Inbox. Manual replies take over the conversation; staff can explicitly resume automation.
5. Record contact consent individually or through a pasted import. Create/sync Meta templates, prepare a campaign, review recipient previews, and approve delivery or scheduling.

## Free service replies and billing

- The UI says **up to 1,000 eligible service replies per business number each month at no Meta messaging charge**, using Meta's standard allowance checked on 10 November 2026. Recheck this policy during maintenance.
- Meta applies the allowance across the business number. Connecting to Growthboard does not reset or reserve it.
- Templates, bulk marketing and authentication messages do not use this allowance. No ₹1,000 cash grant or Growthboard messaging wallet is included.
- The counter shows captured outbound service deliveries in the current UTC month. It is not an authoritative remaining allowance or Meta balance. Other integrations and differences in billing periods can affect Meta's totals.
- Messages are paid directly to Meta. No Razorpay messaging top-up, payment split or automatic platform commission is implemented. A software subscription/percentage fee requires a separate pricing decision and billing implementation.
- Campaign approval links to Meta's rates and authorizes applicable charges; no campaign cost is fabricated.

## Administrator setup

The production database upgrade was completed on 10 November 2026 in Supabase project **Insta ai** (`vcbpmtfarhhdjrnuwlts`) as migration `20261110094018_growthboard_whatsapp_activation`. All nine WhatsApp tables, backend permissions, browser-role isolation, foreign keys, and the number-lock trigger were verified. The AI reservation function uses `SECURITY INVOKER` and backend-only execution. **APPLY_WHATSAPP.sql** combines migrations 007 and 008; do not reapply the original workspace schema. Both migrations remain replayable. See `output/whatsapp-2026-11-10/DATABASE_ACTIVATION.md` for the production checks and pre-existing database advisories.

Configure these server-side variables on the existing backend:

```text
WHATSAPP_ENABLED=true
WHATSAPP_APP_ID=<WhatsApp-capable Meta app ID>
WHATSAPP_APP_SECRET=<that app's secret>
WHATSAPP_SIGNUP_CONFIG_ID=<WhatsApp Embedded Signup configuration ID>
WHATSAPP_WEBHOOK_VERIFY_TOKEN=<random verification secret>
```

App ID/secret fall back to the existing Meta credentials when omitted. Use dedicated values if WhatsApp uses a different app from Instagram. Never replace the existing token encryption key or place secrets/tokens in frontend settings.

Keep `WHATSAPP_ENABLED=false` until migrations and Meta setup are complete. The UI displays setup status until then. Configure Meta's allowed domains, HTTPS login settings, current Embedded Signup configuration and required WhatsApp permissions/Advanced Access. Complete applicable business verification, Tech Provider onboarding and App Review before unrelated businesses connect. Development/test access is not public customer approval.

Configure the selected Meta app's `messages` webhook:

```text
https://business-growth-platform-api.onrender.com/api/whatsapp/webhook
```

Use the verification token above. POST bodies are signature-checked with the selected WhatsApp app secret and bounded to 1 MiB. The authorized WABA is subscribed during connection.

For **new Cloud API numbers only**, users may explicitly choose registration and enter a six-digit two-step verification PIN. The PIN is used for registration and is not stored. Existing Business app numbers must follow supported Meta coexistence/migration. No account is automatically deregistered. Registration, display-name status, billing and actual delivery require live verification.

For local test-number setup, authenticated `POST /api/whatsapp/test-connection` accepts WABA ID, phone-number ID and token, still verifying app ownership and number membership. This endpoint is disabled in production. Customers connect through Embedded Signup rather than token entry.

Existing `GROQ_API_KEY` / `GROQ_MODEL` settings power optional AI. Without them, fixed replies and campaigns remain available, and AI cannot be enabled.

## Delivery behavior

- Signed incoming events are durable and deduplicated by connection/event key.
- The existing distributed worker lease processes Instagram and WhatsApp work. No third backend is required. Hosted wake-ups must operate reliably; free-hosting cold starts can delay replies/campaigns.
- Free-form replies require the current 24-hour incoming-message window, checked when queued and just before sending. Messages predating a renewed connection cannot trigger new sends.
- Rules start paused; saving edits pauses them. Keyword rules precede welcome replies, then AI. Daily limits, recipient cooldowns and atomic AI generation budgets bound usage.
- STOP/unsubscribe suppress messaging. Human requests pause automation. Campaign consent is rechecked immediately before dispatch.
- Campaigns are immutable drafts with template snapshots. Approval authorizes their recipients and text. The worker rechecks approval/content and sends bounded batches. Pause preserves remaining recipients; cancellation stops pending work. In-flight sends can finish.
- Stable request IDs make unchanged message/campaign retries idempotent. Timeouts, interrupted sends, 5xx failures and unreadable successful send results are uncertain and never replayed automatically. Uncertain campaign sends pause the campaign. Resume continues remaining recipients, without retrying uncertain ones.
- Receipts distinguish accepted, delivered, read and failed. Late receipts cannot downgrade delivered/read messages. Receipts preceding the send response are deferred without blocking new incoming messages.
- Disconnect removes saved authorization and stops pending work. It does not close the Meta account, delete funds or remove Meta-side permissions; customers can also manage app permissions in Meta.

## Product limits

- One immutable business number per workspace. Number changes require deliberate support/data migration.
- Text replies and text templates with up to 10 positional body values. Media-header, named-variable, authentication-creation and complex template formats are not supported by the initial sender. Incoming attachments appear as unsupported placeholders; no media fetching.
- Pasted contact imports and campaign recipient/value lists, up to 1,000 per request. Contact/message pagination and recent campaign activity are included; CSV export and a full reporting suite are not.
- Captured history only; no personal WhatsApp history import or exact synchronized Meta wallet balance.
- AI cannot confirm bookings, take payment or inspect live stock. Owners need a real staff escalation path.
- Source implementation does not establish that Meta approvals or production account setup have completed.

## Verification and live acceptance

Local checks cover existing backend behavior plus WhatsApp request idempotency, connection isolation, consent revocation, opt-out, reply windows, templates, campaigns, interrupted sends and billing boundaries. An isolated PGlite database checks migration replay, workspace foreign keys, immutable numbers, AI reservations and browser-role restrictions. Frontend checks include TypeScript, lint and a production build. Browser checks use local sample data and never authenticate a live Meta account.

Before public use:

1. Apply the upgrade and configure the Meta test app/account.
2. Authorize the test number and verify workspace isolation.
3. Send a real inbound test message; deliberately queue a reviewed manual reply and verify delivery.
4. Enable one reviewed rule, then test duplicate webhooks, STOP and staff takeover.
5. Submit/sync a template and confirm actual Meta approval.
6. Record consent for one owned test recipient; review and approve a one-person campaign. Confirm direct Meta billing.
7. Verify scheduling, pause, disconnect and worker recovery on hosting.
8. Finish public customer onboarding approvals before broad rollout.

References: [Meta pricing/billing FAQ](https://whatsappbusiness.com/resources/faq/), [Meta Cloud API collection](https://www.postman.com/meta/whatsapp-business-platform/collection/wlk6lh4/whatsapp-cloud-api), [Embedded Signup](https://www.postman.com/meta/whatsapp-business-platform/collection/du6gzjv/embedded-signup), [WhatsApp messaging policy](https://whatsappbusiness.com/policy/).
