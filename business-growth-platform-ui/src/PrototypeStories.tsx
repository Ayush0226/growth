import { useEffect, useRef } from 'react'
import './prototype-stories.css'
const clamp = (n: number) => Math.max(0, Math.min(1, n))
const storyHTML = `<section class="manifesto" id="platform"><p class="eyebrow">YOU BRING THE AMBITION.</p><h2>We make room<br/>for the <i>good stuff.</i></h2><div><span class="spark" aria-hidden="true">✳</span><p>Less jumping between tools.<br/>More being the business people remember.</p><span class="tiny">THREE CHANNELS.<br/>ONE BIGGER PICTURE.</span></div></section>
<section class="story google" aria-labelledby="google-title"><div class="story-stage"><div class="scene-top"><span>GET DISCOVERED / GOOGLE BUSINESS PROFILE</span><span>Around the corner. Top of mind.</span></div><div class="scene-grid"><div class="product-wrap"><article class="product google-product"><div class="product-top"><b class="google-g">G</b><span>Your neighbourhood, connected.</span><small>DEMO</small></div><div class="map"><div class="road r1"></div><div class="road r2"></div><div class="road r3"></div><span class="block b1"></span><span class="block b2"></span><span class="block b3"></span><div class="pin">✳</div><b>YOUR BUSINESS</b><span class="map-label">GOOD THINGS HAPPEN HERE.</span></div><div class="review"><span class="stars">★★★★★</span><h3>“Found my new favourite.”</h3><p>A happy customer. A conversation worth keeping.</p><div class="reply"><span>✳</span><p>Thanks for stopping by.<br/>We’d love to see you again.</p></div></div><div class="product-foot">A thoughtful reply, a warmer connection.<span>✳</span></div></article><small class="demo-note">Illustrative product story · fictional review and reply</small></div><div class="story-copy"><p class="eyebrow">MAKE YOUR NEIGHBOURHOOD NOTICE.</p><h2 id="google-title">BIG ON<br/><em>YOUR BLOCK.</em></h2><p>Give your reviews, business updates and local visibility a place to come together.</p><div class="tags"><span>Reviews & replies</span><span>Local rankings</span></div><a class="text-button" href="/google">See the bigger picture <span aria-hidden="true">✳</span></a></div></div><div class="scene-bottom"><span>GOOGLE BUSINESS PROFILE</span><div class="progress"><i></i></div><span>FOUND. REMEMBERED. CHOSEN.</span></div></div></section>
<section class="story instagram reverse" aria-labelledby="instagram-title"><div class="story-stage"><div class="scene-top"><span>START SOMETHING / INSTAGRAM</span><span>Attention is just the beginning.</span></div><div class="scene-grid"><div class="product-wrap"><article class="product instagram-product"><div class="product-top"><b>◎</b><span>The everyday studio</span><small>DEMO</small></div><div class="poster"><small>SMALL BUSINESS. BIG PERSONALITY.</small><strong>MAKE<br/>A LITTLE<br/><i>NOISE.</i></strong><span class="poster-orb"></span><span class="poster-stamp">MADE TO<br/>STAND OUT</span></div><div class="comment"><span class="avatar">S</span><p><b>Someone new</b><br/>GUIDE! I’d love to know more.</p><span>♡</span></div><div class="dm"><small>FROM COMMENT TO CONVERSATION</small><p>Here’s the guide you asked for.<br/>Let’s make something happen.</p></div></article><small class="demo-note">Illustrative product story · fictional post and conversation</small></div><div class="story-copy"><p class="eyebrow">MAKE ATTENTION MEAN SOMETHING.</p><h2 id="instagram-title">STOP THE<br/><em>SCROLL.</em></h2><p>Make the post. Plan the moment. Give every new conversation somewhere to go.</p><div class="tags"><span>Content planning</span><span>Comment-to-DM</span></div><a class="text-button" href="/settings/connections">Find your creative rhythm <span aria-hidden="true">✳</span></a></div></div><div class="scene-bottom"><span>INSTAGRAM</span><div class="progress"><i></i></div><span>A LITTLE LOUDER. A LOT MORE YOU.</span></div></div></section>
<section class="story whatsapp" aria-labelledby="whatsapp-title"><div class="story-stage"><div class="scene-top"><span>KEEP IT PERSONAL / WHATSAPP</span><span>Good business starts with a hello.</span></div><div class="scene-grid"><div class="product-wrap"><article class="product whatsapp-product"><div class="product-top"><b>◉</b><span>A warmer welcome.</span><small>DEMO</small></div><div class="chat-head"><span class="avatar">Y</span><p><b>Your business</b><br/><small>People first. Always.</small></p><span>•••</span></div><div class="chat"><small class="chat-date">A LITTLE HELLO</small><p class="bubble incoming">Hey! Can you help me find<br/>the right one?<small>10:24</small></p><p class="bubble outgoing">Of course. Tell us what<br/>you have in mind.<small>10:24 · ✓✓</small></p><div class="handover"><span>✳</span><p>A human touch.<br/><b>Your team, when it matters.</b></p></div></div><div class="chat-input">Make every hello count.<span>♡</span></div></article><small class="demo-note">Illustrative product story · fictional messages</small></div><div class="story-copy"><p class="eyebrow">A LITTLE CLOSER TO YOUR CUSTOMERS.</p><h2 id="whatsapp-title">LESS WAIT.<br/><em>MORE HELLO.</em></h2><p>Keep questions organised, conversations moving and your people in the loop.</p><div class="tags"><span>Shared inbox</span><span>Human handover</span></div><a class="text-button" href="/whatsapp">Keep the conversation going <span aria-hidden="true">✳</span></a></div></div><div class="scene-bottom"><span>WHATSAPP</span><div class="progress"><i></i></div><span>REAL CONNECTIONS. EVERY DAY.</span></div></div></section>
`
const closingHTML = `<section class="closing"><p class="eyebrow">YOUR NEXT CHAPTER DOESN’T NEED MORE TABS.</p><h2>It needs a little<br/><i>more space.</i></h2><a class="pill dark" href="/access">See what’s on the other side <span>✳</span></a><span class="closing-orbit" aria-hidden="true">✳</span></section>
`
export default function PrototypeStories({ still, closing = false }: { still: boolean; closing?: boolean }) {
 const root = useRef<HTMLDivElement>(null)
 useEffect(() => {
  let frame = 0
  const draw = () => {
   frame = 0
   const el = root.current
   if (!el) return
   const vh = innerHeight
   const end = el.querySelector<HTMLElement>('.closing')
   if (end) { const r = end.getBoundingClientRect(); end.style.setProperty('--closing-progress', String(still ? 0 : clamp((vh-r.top)/(vh+r.height*.35)))) }
   el.querySelectorAll<HTMLElement>('.story').forEach((scene, i) => {
    const r = scene.getBoundingClientRect()
    const enter = clamp((vh-r.top)/(vh*.95))
    const p = clamp(-r.top/Math.max(1,r.height-vh))
    const exit = clamp((p-.77)/.23)
    const visible = enter*(1-exit), direction = i%2 ? 1 : -1
    const text = clamp((enter-.85)/.15)*(1-clamp((p-.8)/.17))
    scene.style.setProperty('--p',String(p))
    scene.style.setProperty('--card-x',`${(1-visible)*direction*240}px`)
    scene.style.setProperty('--card-r',`${(1-visible)*direction*12}deg`)
    scene.style.setProperty('--card-opacity',String(clamp(visible*1.5)))
    scene.style.setProperty('--text-opacity',String(text))
    scene.style.setProperty('--text-y',`${(1-text)*28}px`)
    const arrival = clamp((vh-r.top)/(vh*.7))
    scene.style.setProperty('--mobile-x',`${still ? 0 : (1-arrival)*direction*55}px`)
    scene.style.setProperty('--mobile-r',`${still ? 0 : (1-arrival)*direction*3}deg`)
   })
  }
  const schedule = () => { if (!frame) frame = requestAnimationFrame(draw) }
  draw(); addEventListener('scroll',schedule,{passive:true}); addEventListener('resize',schedule)
  return () => { cancelAnimationFrame(frame); removeEventListener('scroll',schedule); removeEventListener('resize',schedule) }
 },[still])
 return <div ref={root} className={`gb-prototype ${still ? 'still' : ''}`} dangerouslySetInnerHTML={{__html:closing ? closingHTML : storyHTML}} />
}
