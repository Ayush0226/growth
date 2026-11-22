import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import GrowboardLogo from './GrowboardLogo'
import './growboard-cinema.css'

const clamp = (n: number) => Math.min(1, Math.max(0, n))
// Supply an original same-origin film or HTTPS CDN URL when ready.
const heroFilm = import.meta.env.VITE_GROWBOARD_HERO_VIDEO as string | undefined
const stories = [
  { id: 'google', name: 'Google Business Profile', short: 'Be the local favourite.', title: ['BIG ON', 'YOUR BLOCK.'], copy: 'Turn a search nearby into a reason to choose you. Give your reviews, business updates and local visibility a place to come together.', tags: ['Reviews & replies', 'Business updates', 'Local rankings'], to: '/google', action: 'Explore Google tools', status: 'Connected Google tools · live ranking checks require setup' },
  { id: 'instagram', name: 'Instagram', short: 'Make attention mean something.', title: ['STOP THE', 'SCROLL.'], copy: 'Make the post. Plan the moment. Keep the conversation going. Bring your content, comments and DMs into the same creative rhythm.', tags: ['Content calendar', 'Comment-to-DM', 'Business AI'], to: '/settings/connections', action: 'Explore Instagram', status: 'Available for connected pilot accounts' },
  { id: 'whatsapp', name: 'WhatsApp', short: 'A little closer to your customers.', title: ['LESS WAIT.', 'MORE HELLO.'], copy: 'Be there when the conversation starts. Organise questions, prepare useful replies and bring a real person in when it matters.', tags: ['Shared inbox', 'Reply rules', 'Human handover'], to: '/whatsapp', action: 'Explore WhatsApp', status: 'Provider activation required before messaging' },
]

function ChannelCard({ channel }: { channel: string }) {
  if (channel === 'google') return <div className="gb-product-card gb-google-card"><div className="gb-demo-bar"><span className="gb-channel-symbol">G</span><b>Your neighbourhood, connected.</b><span>DEMO</span></div><div className="gb-map"><div className="gb-map-road road-a"/><div className="gb-map-road road-b"/><div className="gb-map-road road-c"/><span className="gb-map-block block-a"/><span className="gb-map-block block-b"/><span className="gb-map-pin"><GrowboardLogo wordmark={false}/></span><span className="gb-map-place">YOUR BUSINESS</span></div><div className="gb-review"><span className="gb-stars">★★★★★</span><h3>“My new favourite spot.”</h3><p>A great experience deserves a thoughtful reply.</p><div className="gb-reply-demo"><GrowboardLogo wordmark={false}/><p>Thanks for making us part of your day.<br/>We’d love to see you again.</p></div></div><div className="gb-card-foot">Reviews. Replies. Real connections.<span>✦</span></div></div>
  if (channel === 'instagram') return <div className="gb-product-card gb-instagram-card"><div className="gb-demo-bar"><span className="gb-channel-symbol">◎</span><b>A post with somewhere to go.</b><span>DEMO</span></div><div className="gb-poster"><span>THE EVERYDAY STUDIO</span><strong>MAKE<br/>A LITTLE<br/><i>NOISE.</i></strong><div className="gb-poster-orb"/><span className="gb-poster-stamp">MADE TO<br/>STAND OUT</span></div><div className="gb-dm-comment"><span className="gb-person">S</span><p><b>Someone new</b><br/>GUIDE! I’d love to know more.</p><span>♡</span></div><div className="gb-dm-response"><span>COMMENT → CONVERSATION</span><p>Here’s the guide you asked for.<br/>Let’s make something happen.</p></div></div>
  return <div className="gb-product-card gb-whatsapp-card"><div className="gb-demo-bar"><span className="gb-channel-symbol">◉</span><b>A warmer welcome.</b><span>DEMO</span></div><div className="gb-chat-title"><span className="gb-person">Y</span><div><b>Your business</b><small>A conversation, with care.</small></div><span>•••</span></div><div className="gb-chat"><span className="gb-chat-day">A LITTLE HELLO</span><p className="gb-bubble incoming">Hey! Can you help me find<br/>the right one?<small>10:24</small></p><p className="gb-bubble outgoing">Of course. Tell us what you<br/>have in mind — we’re all ears.<small>10:24 · ✓✓</small></p><div className="gb-handover"><span>✳</span><p>People first.<br/><b>Bring your team in anytime.</b></p></div></div><div className="gb-chat-input">Make every hello count.<span>♡</span></div></div>
}

export default function GrowboardHome() {
  const root = useRef<HTMLDivElement>(null)
  const video = useRef<HTMLVideoElement>(null)
  const [menu, setMenu] = useState(false)
  const [filmFailed, setFilmFailed] = useState(false)
  const [still, setStill] = useState(() => {
    try { return localStorage.getItem('growboard.motion') === 'off' || window.matchMedia('(prefers-reduced-motion: reduce)').matches } catch { return true }
  })
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const change = () => { if (media.matches) setStill(true) }
    media.addEventListener('change', change)
    return () => media.removeEventListener('change', change)
  }, [])
  useEffect(() => {
    const escape = (e: KeyboardEvent) => { if (e.key === 'Escape') setMenu(false) }
    window.addEventListener('keydown', escape)
    return () => window.removeEventListener('keydown', escape)
  }, [])
  useEffect(() => {
    const el = root.current
    if (!el) return
    const scenes = Array.from(el.querySelectorAll<HTMLElement>('.gb-scene'))
    const hero = el.querySelector<HTMLElement>('.gb-cinema')!
    let frame = 0
    const draw = () => {
      frame = 0
      const mobile = window.innerWidth <= 800
      const height = window.innerHeight
      const bounds = hero.getBoundingClientRect()
      const progress = clamp(-bounds.top / Math.max(1, bounds.height - height))
      hero.style.setProperty('--film-progress', String(still ? 0 : progress))
      const film = video.current
      if (film && !still && Number.isFinite(film.duration) && !film.seeking) {
        const target = progress * Math.max(0, film.duration - .08)
        if (Math.abs(film.currentTime - target) > .06) film.currentTime = target
      }
      for (const scene of scenes) {
        const rect = scene.getBoundingClientRect()
        const p = (height - rect.top) / (rect.height + height)
        const enter = clamp((p - .13) / .20)
        const leave = clamp((p - .68) / .22)
        const presence = still ? 1 : mobile ? clamp((height - rect.top - 120) / (height * .6)) : enter * (1 - leave)
        scene.style.setProperty('--presence', String(presence))
        scene.style.setProperty('--travel', String(1 - presence))
        scene.style.setProperty('--copy-visible', String(still || mobile || (enter > .94 && leave < .12) ? 1 : 0))
      }
    }
    const schedule = () => { if (!frame) frame = requestAnimationFrame(draw) }
    draw()
    window.addEventListener('scroll', schedule, { passive: true })
    window.addEventListener('resize', schedule)
    const film = video.current
    film?.addEventListener('loadedmetadata', schedule)
    film?.addEventListener('seeked', schedule)
    return () => { cancelAnimationFrame(frame); window.removeEventListener('scroll', schedule); window.removeEventListener('resize', schedule); film?.removeEventListener('loadedmetadata', schedule); film?.removeEventListener('seeked', schedule) }
  }, [still, filmFailed])
  function toggleMotion() {
    const next = !still
    setStill(next)
    try { localStorage.setItem('growboard.motion', next ? 'off' : 'on') } catch { /* Optional preference. */ }
    window.dispatchEvent(new Event('growboard-motion-change'))
  }
  return <div ref={root} className={`gb-site ${still ? 'gb-still' : ''}`}>
    <a className="gb-skip" href="#gb-main">Skip to content</a>
    <header className="gb-nav"><Link to="/" aria-label="Growboard home"><GrowboardLogo/></Link><button className="gb-menu" onClick={() => setMenu(!menu)} aria-expanded={menu} aria-controls="gb-nav-links">{menu ? 'Close' : 'Menu'}</button><nav id="gb-nav-links" className={menu ? 'is-open' : ''} aria-label="Website navigation"><a href="#platform" onClick={() => setMenu(false)}>The platform</a><a href="#your-rhythm" onClick={() => setMenu(false)}>Your rhythm</a><a href="#questions" onClick={() => setMenu(false)}>Good to know</a><Link to="/login">Log in</Link><Link to="/access" className="gb-pill gb-pill-lime">Let’s grow</Link></nav></header>
    <main id="gb-main">
      <section className="gb-cinema" aria-labelledby="gb-headline"><div className="gb-cinema-sticky">
        <div className="gb-hero-meta"><span>THE BUSINESS YOU IMAGINE. CLOSER.</span><button className="gb-motion" onClick={toggleMotion} aria-pressed={!still}>Motion {still ? 'off' : 'on'} <span aria-hidden="true">{still ? '○' : '◉'}</span></button></div>
        {heroFilm && !filmFailed ? <video ref={video} className="gb-hero-film" src={heroFilm} muted playsInline preload="metadata" onError={() => setFilmFailed(true)} aria-label="Growboard opening film, controlled by scrolling"/> : <div className="gb-sculpture" aria-hidden="true"><div className="gb-aura"/><div className="gb-orbital orbit-back"/><div className="gb-monolith"><GrowboardLogo wordmark={false}/></div><div className="gb-orbital orbit-front"/><span className="gb-star star-a">✳</span><span className="gb-star star-b">✦</span><span className="gb-satellite satellite-a">◎</span><span className="gb-satellite satellite-b">G</span><span className="gb-satellite satellite-c">◉</span></div>}
        <div className="gb-hero-copy"><p className="gb-kicker">A LITTLE LESS BUSYWORK. A LOT MORE YOU.</p><h1 id="gb-headline">GOOD BUSINESS.<br/><span>BIG ENERGY.</span></h1><div className="gb-hero-bottom"><p>Your local presence. Your next post. Your next hello.<br/>Bring it all together. Make it unmistakably yours.</p><Link className="gb-pill gb-pill-white" to="/access">Find your momentum <span aria-hidden="true">✳</span></Link></div></div>
        <div className="gb-hero-foot"><span>GOOGLE · INSTAGRAM · WHATSAPP</span><a href="#platform">SCROLL TO FIND YOUR FLOW <span aria-hidden="true">↓</span></a><span>BY AS TECHZONE</span></div>
      </div></section>
      <section className="gb-manifesto" id="platform"><p className="gb-kicker">YOU DIDN’T START A BUSINESS TO JUGGLE TABS.</p><h2>More creating.<br/>More connecting.<br/><span>More <i>you.</i></span></h2><div className="gb-manifesto-bottom"><span className="gb-asterisk" aria-hidden="true">✳</span><p>One place for the things that move your business forward.<br/>Three channels. A whole new rhythm.</p><span className="gb-outline-label">MEET YOUR NEXT CHAPTER</span></div></section>
      <div className="gb-stories">{stories.map((story, i) => <section className={`gb-scene gb-scene-${story.id} ${i % 2 ? 'gb-reverse' : ''}`} key={story.id} aria-labelledby={`title-${story.id}`}><div className="gb-scene-sticky"><div className="gb-scene-label"><span>{story.name}</span><span>{story.short}</span></div><div className="gb-scene-grid"><div className="gb-scene-visual"><ChannelCard channel={story.id}/><span className="gb-demo-note">Illustrative preview · fictional content</span></div><div className="gb-scene-copy"><p className="gb-kicker">{story.short}</p><h2 id={`title-${story.id}`}>{story.title[0]}<br/><em>{story.title[1]}</em></h2><p>{story.copy}</p><div className="gb-tags">{story.tags.map(tag => <span key={tag}>{tag}</span>)}</div><Link className="gb-pill" to={story.to}>{story.action}</Link><small>{story.status}</small></div></div></div></section>)}</div>
      <section id="your-rhythm" className="gb-rhythm"><div className="gb-rhythm-head"><p className="gb-kicker">A WORKSPACE. YOUR WAY.</p><h2>YOU CALL<br/>THE <span>SHOTS.</span></h2><p>Set the tone. Choose the rules. Keep the human touch.<br/>Good automation starts with your intent.</p></div><div className="gb-rhythm-grid"><article className="gb-rhythm-connect"><div className="gb-connect-art" aria-hidden="true"><span>G</span><span>◎</span><span>◉</span><GrowboardLogo wordmark={false}/></div><h3>Your world.<br/>Brought together.</h3><p>Connect the accounts you manage to your own workspace.</p></article><article className="gb-rhythm-tone"><span className="gb-tone-quote" aria-hidden="true">“</span><div><p className="gb-kicker">SOUNDS LIKE YOU.</p><h3>Warm?<br/><i>Witty?</i><br/>All business?</h3><p>Your business facts and voice give every rule its direction.</p></div></article><article className="gb-rhythm-control"><div className="gb-rule-art"><span>YOUR RULES</span><b>Helpful by design.</b><div><span>Choose what runs</span><i>✓</i></div><div><span>Review the activity</span><i>✓</i></div><div><span>Pause when you need</span><i>✓</i></div></div><h3>More control.<br/>Less on your plate.</h3><p>Enable the flows you’re ready for. Keep an eye on their activity.</p></article></div></section>
      <section className="gb-statement"><span>BUILT FOR THE</span><h2>SMALL TEAMS.<br/><i>BIG DREAMS.</i></h2><p>The neighbourhood favourite. The next independent brand.<br/>The business only you could build.</p><span className="gb-statement-flower" aria-hidden="true">✳</span></section>
      <section className="gb-faq" id="questions"><div><p className="gb-kicker">NO MYSTERY. JUST MOMENTUM.</p><h2>A few<br/><i>good answers.</i></h2></div><div>
        <details><summary>What can I use today?</summary><p>Connected pilot accounts can use Instagram publishing and conversation tools, plus Google connections, reviews and business tools. Local ranking checks require provider setup. WhatsApp needs provider activation before messages can run. The previews above use fictional content.</p></details>
        <details><summary>Can I still use GBP AutoMaster?</summary><p>Yes. GBP AutoMaster continues to run separately. Growboard has its own workspace and infrastructure; connecting to Growboard does not move your old history or settings automatically.</p></details>
        <details><summary>How do automatic replies work?</summary><p>You choose the rules and tone. Eligible conversations can follow enabled rules. Google automatic delivery is currently paused while live testing is completed; connecting Google alone does not start sending replies.</p></details>
        <details><summary>How do I get access?</summary><p>Create an account, then use your administrator’s invitation code to activate your workspace. Availability depends on the channels and permissions connected to your account.</p></details>
        <details><summary>What about WhatsApp charges?</summary><p>Meta messaging charges are paid directly by the connected business. Software pricing is separate and will be confirmed before paid onboarding.</p></details>
      </div></section>
      <section className="gb-finale"><p className="gb-kicker">MAKE YOUR NEXT MOVE A GOOD ONE.</p><h2>LET’S<br/><span>GROW</span><span className="gb-finale-spark" aria-hidden="true">✳</span><br/>SOMETHING.</h2><div><p>Your business has a story.<br/>Give it room to get bigger.</p><Link className="gb-pill gb-pill-lime" to="/access">Open your workspace</Link><small>Pilot access by invitation.</small></div></section>
    </main>
    <footer className="gb-footer"><Link to="/" aria-label="Growboard home"><GrowboardLogo/></Link><p>Independent spirit.<br/>Connected thinking.</p><nav aria-label="Legal links"><Link to="/privacy">Privacy</Link><Link to="/terms">Terms</Link><Link to="/support">Support</Link><Link to="/data-deletion">Data deletion</Link></nav><small>© {new Date().getFullYear()} AS Techzone</small></footer>
  </div>
}
