import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useNavigationType } from 'react-router-dom'
import './route-fog.css'
export default function RouteFog() {
 const { pathname } = useLocation(), navigate = useNavigate(), navigationType = useNavigationType()
 const [phase,setPhase] = useState('')
 const running = useRef(false)
 const navigation = useRef(navigate)
 useEffect(() => { navigation.current = navigate },[navigate])
 useEffect(() => { if (navigationType !== 'POP') window.scrollTo(0,0) },[pathname,navigationType])
 useEffect(() => {
  let alive=true
  const timers = new Set<ReturnType<typeof setTimeout>>()
  const wait = (ms:number) => new Promise<void>(resolve => { const t=setTimeout(()=>{timers.delete(t);resolve()},ms);timers.add(t) })
  const click = async (event:MouseEvent) => {
   if(event.defaultPrevented || event.button!==0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
   try { if(matchMedia('(prefers-reduced-motion: reduce)').matches || localStorage.getItem('growboard.motion')==='off')return } catch { return }
   const link=(event.target as Element).closest<HTMLAnchorElement>('.gb-site a[href]')
   if(!link || link.target || link.hasAttribute('download'))return
   const url=new URL(link.href)
   if(url.origin!==location.origin || (url.pathname===location.pathname && url.search===location.search))return
   event.preventDefault();event.stopPropagation()
   if(running.current)return
   running.current=true;setPhase('active')
   await wait(30);if(!alive)return;setPhase('active cover')
   await wait(620);if(!alive)return;setPhase('active cover covered')
   await wait(180);if(!alive)return;navigation.current(url.pathname+url.search+url.hash)
   await wait(90);if(!alive)return;setPhase('active cover covered clearing')
   await wait(880);if(!alive)return;setPhase('');running.current=false
  }
  document.addEventListener('click',click,true)
  return () => { alive=false;timers.forEach(clearTimeout);running.current=false;document.removeEventListener('click',click,true) }
 },[])
 return <div className={`gb-cloud-transition ${phase}`} aria-hidden="true"><div className="fog-bank left">{Array.from({length:6},(_,i)=><i key={i}/>)}</div><div className="fog-bank right">{Array.from({length:6},(_,i)=><i key={i}/>)}</div><div className="fog-veil"/><span className="fog-mark">✳</span></div>
}
