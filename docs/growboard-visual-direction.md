# Growboard — Big Energy

Implemented 22 November 2026. Original marketing design informed by the pacing of the user's Lilpost video reference. No reference video, third-party artwork or copied layout is shipped.

## Experience

- Ink, lime, lilac, cobalt and coral. Oversized Manrope typography with editorial serif accents.
- Original SVG rising-G mark, sculptural opening artwork, alternating Google/Instagram/WhatsApp scenes, asymmetric workflow cards, editorial statement, FAQs and closing invitation.
- Desktop channel cards enter from alternating sides as the user scrolls. Copy appears near the settled position; cards retreat and copy fades on exit. Scrolling backwards reverses the same sequence. No scroll hijacking.
- Mobile uses a shorter document flow with restrained lateral card entrances and readable text. No long pinned channel sections.
- The motion switch persists locally. System reduced-motion settings disable scene movement and fog. All controls remain keyboard-accessible; focusing a scene reveals its content.
- Route fog is a visual-only cloud reveal, keyed by pathname. It never blocks clicks or delays navigation/auth. Query-only workspace tab changes do not replay it.

## Original opening film

The owner's final film is not supplied yet. The current opening is original CSS/SVG artwork, not a video placeholder or borrowed footage.

1. Export an original landscape H.264 MP4, ideally 8–15 seconds, no required audio. Use frequent keyframes (around 0.25–0.5 seconds) and fast-start metadata for responsive seeking. Keep essential subjects near the centre for mobile cropping; leave room for the heading.
2. Save it under `business-growth-platform-ui/public/media/growboard-intro.mp4`, or host on an HTTPS CDN that supports range requests.
3. Set the frontend build variable `VITE_GROWBOARD_HERO_VIDEO=/media/growboard-intro.mp4` (or the full CDN URL) and rebuild.
4. Scroll progress controls the film's current time; scrolling backwards rewinds it. If loading fails, the sculpture returns. Reduced-motion mode keeps the film still.
5. Validate the real film on desktop and mobile devices before calling the film integration complete. No real final film was available for this release.

## Brand files

Editable vector mark, ink/lime/white variants, favicon, wordmark and visual board are in `business-growth-platform-ui/public/brand/`. The React mark uses the same path. The exported wordmark retains editable text with an Arial fallback; the website wordmark uses Manrope. This is a first design concept for user review.

## Product claims

All example conversations and reviews are explicitly marked fictional. Pilot access, WhatsApp activation and paused Google automatic delivery remain described accurately. This change does not enable sending, change APIs, modify customer records or migrate GBP history.

## Verification

Production build passed. Browser checks covered desktop scenes, mobile width/navigation/FAQs, motion switch and login navigation with non-blocking route fog. Actual film seeking awaits the owner's final video.
