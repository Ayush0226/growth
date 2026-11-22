import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import GrowboardLogo from './GrowboardLogo'
import './growboard-cinema.css'
import PrototypeStories from './PrototypeStories'

const clamp = (n: number) => Math.min(1, Math.max(0, n))
// Supply an original same-origin film or HTTPS CDN URL when ready.
const heroFilm = import.meta.env.VITE_GROWBOARD_HERO_VIDEO as string | undefined
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
        {heroFilm && !filmFailed ? <video ref={video} className="gb-hero-film" src={heroFilm} muted playsInline preload="metadata" onError={() => setFilmFailed(true)} aria-label="Growboard opening film, controlled by scrolling"/> : <div className="gb-sculpture" aria-hidden="true"><div className="gb-aura"/><div className="gb-orbital orbit-back"/><div className="gb-monolith"><GrowboardLogo wordmark={false}/></div><div className="gb-orbital orbit-front"/><span className="gb-star star-a">✳</span><span className="gb-star star-b">✦</span><span className="gb-satellite satellite-a"><img src="/brand/instagram.svg" alt="Instagram"/></span><span className="gb-satellite satellite-b"><img src="/brand/google.svg" alt="Google"/></span><span className="gb-satellite satellite-c"><img src="/brand/whatsapp.svg" alt="WhatsApp"/></span></div>}
        <div className="gb-hero-copy"><p className="gb-kicker">A LITTLE LESS BUSYWORK. A LOT MORE YOU.</p><h1 id="gb-headline">GOOD BUSINESS.<br/><span>BIG ENERGY.</span></h1><div className="gb-hero-bottom"><p>Your local presence. Your next post. Your next hello.<br/>Bring it all together. Make it unmistakably yours.</p><Link className="gb-pill gb-pill-white" to="/access">Find your momentum <span aria-hidden="true">✳</span></Link></div></div>
        <div className="gb-hero-foot"><span>GOOGLE · INSTAGRAM · WHATSAPP</span><a href="#platform">SCROLL TO FIND YOUR FLOW <span aria-hidden="true">↓</span></a><span>BY AS TECHZONE</span></div>
      </div></section>
      <PrototypeStories still={still}/>
      <section id="your-rhythm" className="gb-rhythm"><div className="gb-rhythm-head"><p className="gb-kicker">A WORKSPACE. YOUR WAY.</p><h2>YOU CALL<br/>THE <span>SHOTS.</span></h2><p>Set the tone. Choose the rules. Keep the human touch.<br/>Good automation starts with your intent.</p></div><div className="gb-rhythm-grid"><article className="gb-rhythm-connect"><div className="gb-connect-art" aria-hidden="true"><span>G</span><span>◎</span><span>◉</span><GrowboardLogo wordmark={false}/></div><h3>Your world.<br/>Brought together.</h3><p>Connect the accounts you manage to your own workspace.</p></article><article className="gb-rhythm-tone"><span className="gb-tone-quote" aria-hidden="true">“</span><div><p className="gb-kicker">SOUNDS LIKE YOU.</p><h3>Warm?<br/><i>Witty?</i><br/>All business?</h3><p>Your business facts and voice give every rule its direction.</p></div></article><article className="gb-rhythm-control"><div className="gb-rule-art"><span>YOUR RULES</span><b>Helpful by design.</b><div><span>Choose what runs</span><i>✓</i></div><div><span>Review the activity</span><i>✓</i></div><div><span>Pause when you need</span><i>✓</i></div></div><h3>More control.<br/>Less on your plate.</h3><p>Enable the flows you’re ready for. Keep an eye on their activity.</p></article></div></section>
      <section className="gb-statement"><span>BUILT FOR THE</span><h2>SMALL TEAMS.<br/><i>BIG DREAMS.</i></h2><p>The neighbourhood favourite. The next independent brand.<br/>The business only you could build.</p><span className="gb-statement-flower" aria-hidden="true">✳</span></section>
      <section className="gb-faq" id="questions"><div><p className="gb-kicker">NO MYSTERY. JUST MOMENTUM.</p><h2>A few<br/><i>good answers.</i></h2></div><div>
        <details><summary>What can I use today?</summary><p>Connected pilot accounts can use Instagram publishing and conversation tools, plus Google connections, reviews and business tools. Local ranking checks require provider setup. WhatsApp needs provider activation before messages can run. The previews above use fictional content.</p></details>
        <details><summary>Can I still use GBP AutoMaster?</summary><p>Yes. GBP AutoMaster continues to run separately. Growboard has its own workspace and infrastructure; connecting to Growboard does not move your old history or settings automatically.</p></details>
        <details><summary>How do automatic replies work?</summary><p>You choose the rules and tone. Eligible conversations can follow enabled rules. Google automatic delivery is currently paused while live testing is completed; connecting Google alone does not start sending replies.</p></details>
        <details><summary>How do I get access?</summary><p>Create an account, then use your administrator’s invitation code to activate your workspace. Availability depends on the channels and permissions connected to your account.</p></details>
        <details><summary>What about WhatsApp charges?</summary><p>Meta messaging charges are paid directly by the connected business. Software pricing is separate and will be confirmed before paid onboarding.</p></details>
      </div></section>
      <PrototypeStories still={still} closing/>

    </main>
    <footer className="gb-footer"><Link to="/" aria-label="Growboard home"><GrowboardLogo/></Link><p>Independent spirit.<br/>Connected thinking.</p><nav aria-label="Legal links"><Link to="/privacy">Privacy</Link><Link to="/terms">Terms</Link><Link to="/support">Support</Link><Link to="/data-deletion">Data deletion</Link></nav><small>© {new Date().getFullYear()} AS Techzone</small></footer>
  </div>
}
