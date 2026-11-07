# WhatsApp module: foundation started

The first WhatsApp source module has been added alongside the existing Instagram backend. It is not yet exposed as a live customer feature. Instagram remains the live product while the access/Google provider settings are completed.

## Foundation implemented

- A WhatsApp Cloud API client for phone metadata and text replies, using bearer headers and redacted failures.
- Signed webhook validation and a one-megabyte intake limit.
- Normalization of incoming text, button/list replies and sent/delivered/read/failed receipts.
- Stable event keys for duplicate-webhook handling.
- Explicit uncertain-send errors with no automatic retry.
- A prepared, server-only database migration for isolated workspace connections, messages and durable events. Cross-workspace connection/message mismatches are rejected by database foreign keys.

No WhatsApp customer messages have been sent, no Meta account connected, and no new Render server created. The source foundation is not a completed WhatsApp inbox or automation product.

## Next implementation

1. Finish the current Google sign-in and access-code settings.
2. Connect a Meta test business/phone number first, verify ownership and store its token encrypted.
3. Wire the signed webhook route to durable events and add the worker processing/delivery state transitions.
4. Add the WhatsApp inbox, contacts, manual replies and supported history captured by our webhooks. Do not promise import of personal WhatsApp chat history.
5. Add keyword/welcome replies, opt-out handling, business-specific Groq answers and team handoff.
6. Add approved templates and explicit opt-in tracking for eligible business-initiated messaging. Free-form replies and templates have different eligibility and pricing.
7. Add customer onboarding/Embedded Signup and verify required Meta approvals before outside businesses connect.

## Meta setup required for the first real test

- Meta business portfolio and WhatsApp Business Account.
- A Meta test number or an eligible business phone number and its phone-number ID.
- A token with the required WhatsApp messaging/management permissions.
- The Meta app secret for signed webhooks and a chosen webhook verification token.

Use the Meta test number initially. Do not migrate or deregister an existing business/personal number without reviewing the intended setup and confirming the change.

## Hosting and shared access

The plan is to share the current website, Supabase user/workspace and backend service. This avoids requiring a third always-running free backend just for WhatsApp. It does not automatically merge the existing GBP service's identity, database or credits; those still need a deliberate integration.

External API/AI calls, media volume, queue latency and platform quotas still determine capacity. WhatsApp message charges are separate from Render hosting. The first phase is a small test-number pilot, followed by measured rollout.

References: [Meta's official WhatsApp Cloud API collection](https://www.postman.com/meta/whatsapp-business-platform/collection/wlk6lh4/whatsapp-cloud-api), [Meta Embedded Signup](https://www.postman.com/meta/whatsapp-business-platform/collection/du6gzjv/embedded-signup), [WhatsApp pricing](https://business.whatsapp.com/products/platform-pricing).
