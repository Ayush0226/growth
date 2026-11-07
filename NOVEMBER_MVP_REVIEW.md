# Growthboard: Instagram, business AI and shared platform review

7 November 2026. This is an implementation and planning review, not a throughput benchmark.

## This release

| Screenshot / request | Change |
| --- | --- |
| Comments show `@undefined` | Request the available author fields, use the username when supplied, and show “Instagram user” when Meta omits it. Public replies use an in-app dialog with the original comment. |
| Composer controls / spacing | Consistent select, upload, caption and schedule controls; compact two-column upload area on desktop and stacked layout on mobile. Existing image/carousel/batch approval remains. |
| Long automation activity column | Incoming events and reply deliveries have separate tabs, eight entries per page, and a bounded scrolling area beneath the rules. |
| Inbox history / attachment placeholders | Cursor pagination for older messages and additional conversations, preserved scroll position when loading history, bounded message stream, visible reply composer, and image/video/audio/shared-link previews where Meta returns usable content. |
| Large browser confirmation | In-app rule review showing trigger, selected posts, reply, daily limit and cooldown. |
| Repeated 1–2 second loading | User-specific browser read cache, simultaneous-request deduplication, short account-specific backend read cache, pooled Meta read connections, parallel insights requests and visible loading states. Polling stops while a page is hidden. Vendor bundles are separated for browser caching. |

Fresh requests still involve authentication, Supabase and Meta. A first load may still take 1–2 seconds; no measured speedup is claimed. Free hosting cold starts can be much longer. Messages unavailable through Meta cannot be reconstructed from Instagram’s app-only history. Attachment previews can be unavailable or expire.

Browser verification was interrupted because the Chrome connection became unavailable and the in-app preview could not open. The release must therefore be visually checked in the user’s browser. Backend tests and production build checks are recorded in the chat. No real customer messages were sent for verification.

## Groq business assistant

The new **Business AI** screen is `/assistant`. It supports business facts, a support/sales/feedback role, response instructions, a handoff message, daily limits, a preview and an explicit enable review.

- The Groq key is server-side (`GROQ_API_KEY`); `GROQ_MODEL` defaults to `openai/gpt-oss-20b` hosted by Groq. It does not call OpenAI’s API. The model is configurable because provider availability changes.
- Saving business information pauses AI. The owner separately enables customer replies after reviewing the saved information.
- Existing keyword/welcome rules run first. AI handles unmatched new text DMs within Instagram’s reply window. It does not answer public comments, replay an old backlog, or generate a DM merely because somebody followed an account.
- A database reservation limits live generation attempts to the configured 1–100/day per workspace and previews to 20/day. Failed attempts count. These are product limits, not server capacity measurements.
- Recent context from the same customer/connection is included. Business facts and customer text/context are sent to Groq when the feature is used. Privacy text and enable review disclose this.
- Requests for a person, missing information, or staff actions can hand the conversation to the team. Manual replies pause AI for that customer. The team can resume AI from the Business AI screen. Keyword rules are separate and still retain their own settings.
- Generated replies cannot make bookings, charge payments, change stock, or submit reviews. Those would need separately authorized business integrations.
- Delivery has a deduplication key. An uncertain network send is recorded for inspection and is not blindly resent.
- AI remains unavailable until the database upgrade and provider key are configured. Existing rules work without the AI tables.

### Finish setup

1. In the existing Supabase project SQL editor, run `APPLY_AI_CHATBOT.sql` (same content as backend migration `005_business_chatbot.sql`). This adds three server-only tables and a restricted quota reservation function. It does not recreate the workspace tables or enable a bot.
2. On the **business-growth-platform-api** Render service, add `GROQ_API_KEY` using the intended Groq account, then save/redeploy. Do not put the key in the frontend or chat. `GROQ_MODEL` is optional; the default is above.
3. Open Business AI, enter one business’s actual services, prices, hours, policies and contact details, and save.
4. Preview ordinary, unknown, multilingual and handoff questions. Enable only after reviewing the answers. Then send a fresh DM from a second account to verify real delivery.

Groq documentation: [available models](https://console.groq.com/docs/models), [text generation](https://console.groq.com/docs/text-chat), [model retirements](https://console.groq.com/docs/deprecations).

## Screenshot 6: comment → button → guide

The screenshot appears to show a two-stage flow:

1. A comment matches a post’s trigger and keyword.
2. The business sends one opening private reply with a “Send me the access” quick reply or action button.
3. The customer taps it. The action or text reply reaches the webhook and opens the eligible messaging conversation.
4. A saved flow sends the guide message with a “Click me” website button.

The initial private reply alone does not open the normal 24-hour messaging window. A reply/action button interaction does; merely clicking a website link does not. The screenshot does not establish which vendor was used or whether a follow check was required. A follow condition is a separate feature.

Growthboard currently has the initial plain-text comment-to-DM and DM keyword stages. To reproduce this interface we still need button/quick-reply templates, postback handling, flow state, the follow-up message/link editor, and deduplication for button events. We should also provide a preview and delivery history for each stage. This release does not add that flow builder.

Source: [Manychat’s own comment trigger documentation](https://help.manychat.com/en/articles/17741897-instagram-post-and-reel-comments-trigger).

## Reel publishing

Reel publishing is possible through Meta’s publishing API. The normal sequence is video upload to storage → create a Reel container → wait for Meta processing → publish → save the result. Captions, scheduling and supported cover/feed options can sit in the existing publishing queue.

Growthboard’s current composer supports JPEG photo posts, 2–10-image carousels and batches of separate photo posts. It does not yet upload/publish videos or Reels. Video support needs direct storage uploads, video validation, a video preview, processing progress, scheduling and failure handling. We should avoid transcoding large videos or buffering them in the 512 MB web server. A hosted video must remain fetchable until Meta finishes ingesting it. An API publisher does not automatically provide Instagram’s music library or editing tools.

Source: [Meta’s official Instagram API collection](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api).

## One website: GBP Master + Instagram + WhatsApp

Yes, the three products can share one customer-facing website with one account, business workspace, subscription and navigation. They still need their own platform connections and permissions.

Suggested structure:

- Shared workspace: business profile, team roles, billing/credits, AI business facts, audit history and customer permissions.
- GBP module: locations, reviews, replies, campaigns and local-rank reports.
- Instagram module: publishing/calendar, comments, inbox, keyword flows and business AI.
- WhatsApp module: Cloud API connection, inbox, approved templates, consent tracking, sales/support flows and business AI.
- A durable job queue: short webhook intake, tenant-specific quotas, deduplication, processing leases and observable delivery results.
- Media in object storage; Cloudflare can serve/cache public static assets. Private inbox/account responses must remain isolated and uncached by shared CDNs.

The local GBP backend was found and already uses Groq, its own Supabase setup and its own job tables. Its dependency versions and authentication assumptions differ from this Instagram app. The local Wallys folder did not contain a WhatsApp implementation to inspect. Therefore, a shared header alone would not complete integration: account/workspace mapping, access checks, migration, credits and queues require deliberate work, and the WhatsApp source or a new Cloud API implementation is still needed.

## Exact published free-tier limits

| Resource | Published allowance / behavior | Consequence |
| --- | --- | --- |
| Render Free web service | 0.1 CPU and 512 MB RAM per instance | Keep the backend small; outsource AI inference and large media processing. |
| Render Free service hours | 750 hours per workspace per calendar month, shared across free web services | One continuously running service uses 720 hours in 30 days or 744 in 31. Three always-on backends would use 2,160 hours in 30 days. |
| Render idle behavior | Sleeps after 15 minutes without inbound traffic; wake-up takes about a minute | A customer arriving after sleep can encounter delayed webhooks/replies. External cron requests do not create additional free hours or an uptime guarantee. |
| Render Free worker/cron plans | Dedicated background-worker and cron compute are not free plans | Existing in-process processing and external/Supabase cron need careful coordination; a paid worker is a later reliability option. |
| Supabase Free | 500 MB database, 1 GB file storage, 5 GB egress plus 5 GB cached egress, 50,000 monthly active users; project pause after a week of inactivity | Auth user count is not the limiting factor for a small pilot. Event history, uploads, egress and operational reliability matter. |

Sources: [Render compute](https://render.com/docs/compute-plans), [Render Free](https://render.com/docs/free), [Supabase Free](https://supabase.com/pricing).

### Can it handle 10 businesses?

**Ten low-volume pilot businesses are a plausible target with one small combined backend, external AI, storage uploads, queues and conservative limits. This has not been benchmarked and is not a guaranteed maximum.** Ten accounts sitting idle are very different from ten busy accounts receiving a viral campaign at the same time. The three current apps cannot simply be placed together on 512 MB without measuring their combined memory use.

For illustration, ten businesses receiving 100 incoming messages each per day produce 1,000 incoming messages/day or roughly 30,000/month. That is a workload example, not an assertion that this deployment supports it. Each message can create multiple database rows and external calls. The current default AI cap would handle at most 20 AI attempts per business/day unless changed; other messages may be answered by rules or the team.

The Instagram worker currently processes up to ten events per batch, alongside a small publishing batch. Generation/API duration and queue contention determine actual throughput. If inference averaged three seconds, ten AI requests would alone occupy roughly thirty seconds, before database and delivery time; that is arithmetic, not a measured service rate.

To state an actual capacity, measure the combined backend’s idle/peak memory, CPU, concurrent dashboards, webhook acknowledgement time, oldest queued item, reply latency, provider throttling and database/storage growth under a representative burst. Upgrade when queues or customer-facing latency exceed the product target, rather than after an invented number of registered users.

For a light pilot, keep a single backend service, avoid CPU-heavy video work, retain events deliberately, cap AI usage and monitor queue age. For paying customers who need timely replies, plan paid always-on compute and backups. Cloudflare cannot prevent Render-origin sleeps by caching private API responses.

WhatsApp and AI also have costs and rules separate from hosting. [WhatsApp pricing](https://business.whatsapp.com/products/platform-pricing) varies by message category/market; business-specific customer support should be designed within the [current WhatsApp Business terms](https://www.whatsapp.com/legal/business-solution-terms). Hosting being free does not mean messages or AI inference are unlimited/free.

## Remaining work

1. Apply the AI migration, configure Groq and verify live replies with a fresh second-account DM after enabling a reviewed business configuration.
2. Visually inspect the new screens in a working browser connection; verify actual attachment availability and older-history cursors for this account.
3. Build the button-based comment-to-guide flow and optional follow-check behavior if chosen.
4. Add Reel/video publishing if chosen.
5. Design and implement shared identity/workspaces/billing, port GBP deliberately and locate/build the WhatsApp module.
6. Benchmark the combined workload before promising capacity; add production monitoring, retention and backup arrangements before a paid rollout.
