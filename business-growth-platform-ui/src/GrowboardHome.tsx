import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import FogTransition from './FogTransition'
import './growboard.css'
import './growboard-neon.css'

const channels = [
  { name: 'Google', tag: 'Make every review a conversation.', headline: 'Get seen.\nStay brilliant.', description: 'Bring your local presence into focus. Reviews, thoughtful replies and regular business updates, connected to the rest of your business.', symbol: 'G', status: 'Google integration in preparation', item: 'A little recognition goes a long way.', label: 'Review reply preview', reply: 'Thank you for sharing your experience. We’re glad you enjoyed your visit and look forward to welcoming you again.', color: 'blue' },
  { name: 'Instagram', tag: 'Turn attention into a conversation.', headline: 'Stand out.\nSpark more.', description: 'Plan your next post, keep your inbox moving and turn the right comment into a helpful private conversation.', symbol: '◎', status: 'Available in the connected pilot', item: 'Your next conversation starts here.', label: 'Comment-to-DM preview', reply: 'Thanks for your interest! Here’s the guide you asked for. Reply here if you have a question.', color: 'violet' },
  { name: 'WhatsApp', tag: 'Keep the conversation going.', headline: 'Less waiting.\nMore wow.', description: 'A familiar place for customer questions, useful follow-ups and a real person whenever the conversation needs one.', symbol: '◉', status: 'Built · live activation pending', item: 'A warm welcome. Without the wait.', label: 'Customer reply preview', reply: 'Hello! Thanks for reaching out. Tell us what you’re looking for and we’ll help you find the right option.', color: 'green' },
]

export default function GrowboardHome() {
  const [selected, setSelected] = useState(0)
  const [sequence, setSequence] = useState(0)
  const [menu, setMenu] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const channel = channels[selected]
  useEffect(() => () => clearTimeout(timer.current), [])
  useEffect(() => {
    function escape(event: KeyboardEvent) { if (event.key === 'Escape') setMenu(false) }
    window.addEventListener('keydown', escape)
    return () => window.removeEventListener('keydown', escape)
  }, [])
  function switchChannel(index: number) {
    clearTimeout(timer.current)
    setSequence(value => value + 1)
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) setSelected(index)
    else timer.current = setTimeout(() => setSelected(index), 430)
  }
  return <div className={`grow-site grow-${channel.color}`}>
    <a className="grow-skip" href="#grow-main">Skip to content</a>
    <nav className="grow-nav" aria-label="Main navigation">
      <Link to="/" className="grow-wordmark"><span className="grow-mark" aria-hidden="true">g</span>growboard<span className="grow-wordmark-dot">.</span></Link>
      <button className="grow-menu-button" aria-expanded={menu} aria-controls="grow-menu" onClick={() => setMenu(!menu)}>{menu ? 'Close' : 'Menu'}</button>
      <div id="grow-menu" className={`grow-nav-links ${menu ? 'is-open' : ''}`}>
        <a href="#platform" onClick={() => setMenu(false)}>The platform</a><a href="#how-it-works" onClick={() => setMenu(false)}>How it works</a><a href="#questions" onClick={() => setMenu(false)}>Good to know</a>
        <Link to="/login" className="grow-login">Log in</Link><Link to="/access" className="grow-nav-cta">Open workspace</Link>
      </div>
    </nav>
    <main id="grow-main">
      <section className="grow-hero" aria-labelledby="grow-headline">
        <div className="grow-sky" aria-hidden="true"><div className="grow-orbit orbit-one"/><div className="grow-orbit orbit-two"/><div className="grow-cloud cloud-one"/><div className="grow-cloud cloud-two"/></div>
        <FogTransition sequence={sequence}/>
        <div className="grow-hero-top"><span>YOUR NEXT BIG MOVE</span><span>BY AS TECHZONE</span></div>
        <div className="grow-hero-grid">
          <div className="grow-hero-copy">
            <p className="grow-eyebrow">{channel.tag}</p>
            <h1 id="grow-headline">{channel.headline.split('\n').map((line, i) => <span key={i}>{line}</span>)}</h1>
            <p className="grow-intro">{channel.description}</p>
            <div className="grow-actions"><Link className="grow-button grow-button-dark" to="/access">Start your next chapter</Link><a className="grow-text-link" href="#platform">Explore the platform</a></div>
            <p className="grow-pilot">A growing workspace for independent businesses.</p>
          </div>
          <div className="grow-preview" aria-label={`${channel.name} illustrative preview`}>
            <div className="grow-floating-label"><span className="grow-spark">✦</span> Big energy. Less busywork.</div>
            <div className="grow-preview-card">
              <div className="grow-preview-header"><span className="grow-channel-icon">{channel.symbol}</span><div><b>{channel.name}</b><span>{channel.label}</span></div><span className="grow-demo-label">DEMO</span></div>
              <div className="grow-preview-content"><span className="grow-stars" aria-label="Illustrative five-star review">{selected === 0 ? '★★★★★' : '✦'}</span><h2>{channel.item}</h2><p>{selected === 0 ? '“Such a lovely experience. Friendly people and thoughtful service.”' : selected === 1 ? '“GUIDE — I’d love to know more.”' : '“Hi! Can you help me choose?”'}</p></div>
              <div className="grow-reply"><div><span className="grow-avatar">g</span><b>{selected === 0 ? 'Your business' : 'Your assistant'}</b></div><p>{channel.reply}</p><small>Illustrative content · no message is sent</small></div>
              <div className="grow-preview-footer"><span>{channel.status}</span><span aria-hidden="true">✧</span></div>
            </div>
            <div className="grow-floating-note"><span aria-hidden="true">☁</span><div>Less busywork.<br/><b>More your business.</b></div></div>
          </div>
        </div>
        <div className="grow-hero-bottom"><span>ONE VISION. THREE CONNECTIONS.</span><div className="grow-channel-tabs" role="group" aria-label="Explore a channel">{channels.map((item, i) => <button key={item.name} aria-pressed={selected === i} onClick={() => switchChannel(i)}><span aria-hidden="true">{item.symbol}</span>{item.name}</button>)}</div><button className="grow-fog-replay" onClick={() => setSequence(value => value + 1)}>Replay the fog</button></div>
      </section>
      <section id="platform" className="grow-platform">
        <div className="grow-section-heading"><p className="grow-eyebrow">MAKE SPACE FOR WHAT MATTERS</p><h2>Three channels.<br/><em>One bold vision.</em></h2><p>Your presence, your content and your conversations belong together. We’re bringing them into one considered workspace.</p></div>
        <div className="grow-features">
          <article><span className="grow-feature-icon">G</span><p className="grow-feature-state">JOINING GROWBOARD</p><h3>A stronger local presence.</h3><p>Bring GBP Master’s reviews, reply automation, multi-location publishing and rank reports into your new workspace.</p><a href="https://gbpautomaster.in" target="_blank" rel="noreferrer">Use the existing GBP platform</a></article>
          <article><span className="grow-feature-icon">◎</span><p className="grow-feature-state">CONNECTED PILOT</p><h3>Content with a conversation.</h3><p>Prepare photos and carousels, plan your calendar, manage comments and respond with keyword or business AI rules.</p><Link to="/composer">Open Instagram tools</Link></article>
          <article><span className="grow-feature-icon">◉</span><p className="grow-feature-state">ACTIVATION IN PROGRESS</p><h3>A more helpful hello.</h3><p>An inbox, contacts, approved templates and customer support flows. Human takeover stays close at hand.</p><Link to="/whatsapp">Open WhatsApp setup</Link></article>
        </div>
      </section>
      <section id="how-it-works" className="grow-flow"><div><p className="grow-eyebrow">AUTOMATION, WITH YOUR INTENT</p><h2>You set the tone.<br/>Let the work flow.</h2><p>Choose your channels, define what a helpful response looks like and decide which tasks can run automatically.</p><Link to="/assistant" className="grow-button grow-button-light">Explore Business AI</Link></div><ol><li><span>Connect your business</span><p>Sign in to your own workspace and authorize the channels you manage.</p></li><li><span>Make it sound like you</span><p>Add business facts, set your tone and review your automation rules.</p></li><li><span>Let the right tasks run</span><p>Enable a rule once. Eligible conversations follow that rule, with activity history and a pause control.</p></li></ol></section>
      <section className="grow-calendar-story"><div className="grow-calendar-visual" aria-label="Illustrative shared calendar concept"><div><b>A little perspective.</b><span>CALENDAR CONCEPT</span></div><div className="grow-calendar-grid">{Array.from({length:14},(_,i)=><div key={i}><span>{i+1}</span>{i===2&&<b className="cal-blue">Google update</b>}{i===5&&<b className="cal-purple">Instagram post</b>}{i===9&&<b className="cal-green">WhatsApp follow-up</b>}</div>)}</div><small>Shared cross-channel scheduling is planned. Existing channel tools remain available.</small></div><div><p className="grow-eyebrow">THE BIGGER PICTURE</p><h2>A clearer view<br/>of your day.</h2><p>Our direction is a shared calendar for content, conversations and activity across your business. A place to see what happened and decide what happens next.</p><Link to="/calendar" className="grow-text-link">Explore the current calendar</Link></div></section>
      <section id="questions" className="grow-faq"><div><p className="grow-eyebrow">GOOD TO KNOW</p><h2>A few clear answers.</h2></div><div>
        <details><summary>Can I keep using GBP AutoMaster?</summary><p>Yes. GBP AutoMaster remains a separate operational product. Growboard’s Google module is being prepared on Growboard’s own infrastructure.</p></details>
        <details><summary>Will every review need my approval?</summary><p>The planned Google auto-reply mode lets you enable a rule once and publish eligible replies automatically. You choose the rating range, tone and limits, and can pause the rule. It will only become available after the integration and live tests are complete.</p></details>
        <details><summary>Is everything shown already available?</summary><p>Instagram tools are available for the connected pilot. WhatsApp is built but still needs activation and provider approval. Google integration and the shared calendar are in preparation. The previews on this page use fictional content.</p></details>
        <details><summary>Are Meta messaging charges included?</summary><p>WhatsApp messaging charges are paid directly to Meta by the connected business. Growboard’s software pricing is separate and will be confirmed before paid onboarding.</p></details>
      </div></section>
      <section className="grow-final"><p className="grow-eyebrow">YOUR NEXT CHAPTER</p><h2>Your business.<br/><em>Turned all the way up.</em></h2><Link className="grow-button grow-button-dark" to="/access">Open your workspace</Link><p>Pilot access requires an invitation code.</p></section>
    </main>
    <footer className="grow-footer"><Link to="/" className="grow-wordmark">growboard.</Link><span>Made for the business you’re building.<br/>A product by AS Techzone.</span><div><Link to="/privacy">Privacy</Link><Link to="/terms">Terms</Link><Link to="/support">Support</Link><Link to="/data-deletion">Data deletion</Link></div><small>© {new Date().getFullYear()} AS Techzone</small></footer>
  </div>
}
