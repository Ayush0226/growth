# Instagram: calendar, image preparation and public onboarding

## Implemented in this release

- A real six-week month calendar, previous/next month, Today and date jump.
- Select a date to review planned posts, actual publications, incoming automation events, reply delivery records and business AI generation records.
- Separate date-specific Instagram insights request. Future dates and unavailable metrics are explicit empty states; missing data is not converted to zero. Current-day metrics are provisional. Current follower counts are not presented as historical daily counts.
- Dates are grouped in the browser's IANA timezone with UTC query boundaries, including daylight-saving changes.
- Day histories are paginated in pages of50. Overview counts have a5000records/category cap and clearly report partial counts for busy periods.
- Post editing uses caption and date/time fields; cancellation and retry use in-app review dialogs.
- “Plan a post” preselects the calendar date in Create.
- Mobile navigation retains Settings, Support and Sign out through an Account menu; icon navigation has accessible names.
- Upload JPEG, PNG and WebP originals up to20MiB/25megapixels. Prepare JPEGs below8MiB with bounded dimensions, EXIF orientation and white behind transparency. Metadata is stripped on the server.
- Original, portrait, square and landscape fit options. Fitting adds borders without cropping and is shown in the preview before publication approval.
- Server independently validates/normalizes images, limits decode concurrency and bounds multipart intake. Still images only; HEIC/GIF/animated files and Reels/video are not added by this release.
- Existing2–10image carousel and separate-post batch behavior is retained. This release does not claim that the current app supports Instagram's native maximum for every API version.

No database migration or new secret is required for these features. The calendar reads existing workspace-owned jobs/events/deliveries/AI tables; Instagram must grant the optional insights permission for live performance reporting. It cannot recover activity never stored by Growthboard or metrics Meta does not expose.

## Public onboarding is not approved yet

The owner supplied Meta's Permissions and Features page on8November2026. Instagram business permissions show **Standard Access** and **No App Review requested**. The copied Development/Live toggle text does not independently establish its selected state. Existing owner/tester operation is not evidence that arbitrary outside businesses can connect.

The intended customer flow is:

1. Google/email app login.
2. Redeem the owner's pilot admission code once.
3. Create the customer's own workspace.
4. Connect that customer's Business/Creator Instagram account through Meta consent.
5. Grant the permissions needed for the chosen features and enable replies/AI deliberately.

Customers should not join the operator's workspace to manage their own businesses. App login and Instagram provider consent are separate.

### Google setup

See [Google access setup](GOOGLE_ACCESS_SETUP.md). The last verified Instagram Supabase provider flag was Google disabled. Add the Instagram Supabase callback to the existing Google OAuth client without removing the GBP callback, configure the matching ID/secret in Instagram Supabase, and allow the production `/access` return URL. Sharing the OAuth client does not merge the existing GBP and Instagram Supabase users/sessions.

### Meta setup and review package

Use the Instagram Login permission family already requested by this app:

- `instagram_business_basic`: connected profile/media.
- `instagram_business_content_publish`: photo/carousel publishing and scheduling.
- `instagram_business_manage_comments`: comments, approved replies/moderation, keyword private replies.
- `instagram_business_manage_messages`: inbox/manual replies and explicitly enabled DM/AI rules.
- `instagram_business_manage_insights`: optional metrics; review/availability should match the configured feature.

Request the applicable Advanced Access for serving outside businesses; complete Meta's stated business/Tech Provider verification requirements. Do not request all permissions on the general dashboard list. The existing app uses Instagram Login; unrelated Facebook Login/Page permission families should not be added just because they appear nearby.

Prepare accurate review demonstrations on an authorized test account:

1. Reviewer can sign in, redeem pilot access and create a separate workspace using the review instructions supplied privately to Meta.
2. Connect professional Instagram, show granted capabilities and disconnect controls.
3. Approve and publish a photo/carousel, then show the actual Instagram result and calendar status.
4. Display a comment and reply/moderate; show a selected-post keyword private-reply rule with owner-approved text.
5. Open an incoming DM, use manual reply, demonstrate an enabled keyword rule and optional business AI handoff.
6. Request supported insights and show actual results or clearly labeled unavailable data.
7. Provide working public privacy/terms/support/deletion information and the exact callback URLs below. Replace invitation-only support with a verified business contact before public launch.

The operator must supply genuine business details and record real feature demonstrations. No review application, approval, screencast or business verification is fabricated by this release. Meta approval timing cannot be guaranteed for today.

## Exact production URLs

- Website: https://growthboard-web.onrender.com
- Google callback: https://vcbpmtfarhhdjrnuwlts.supabase.co/auth/v1/callback
- Instagram OAuth callback: https://business-growth-platform-api.onrender.com/api/integrations/instagram/callback
- Instagram webhook: https://business-growth-platform-api.onrender.com/api/instagram/webhook
- Privacy: https://growthboard-web.onrender.com/privacy
- Terms: https://growthboard-web.onrender.com/terms
- Deletion information: https://growthboard-web.onrender.com/data-deletion
- API readiness: https://business-growth-platform-api.onrender.com/health/ready

## Verification boundaries

Automated checks use isolated fixtures; read-only live database queries validate calendar joins/date filtering without creating posts/messages. Hosted version, frontend assets and route availability are checked after Git push. These do not replace a fresh customer Google-login flow, Meta external-account approval or an owner-approved real publication. Existing queue recovery/token renewal/retention items in the architecture audit remain separate launch work.
