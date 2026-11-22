import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { supabase } from './lib/supabase'

const sections = [
  { id: 'channels', label: 'Channels', icon: '◉', links: [
    ['Google Business Profile', '/google'], ['Instagram', '/settings/connections'], ['WhatsApp', '/whatsapp'],
  ] },
  { id: 'content', label: 'Content', icon: '▧', links: [
    ['Create a post', '/composer'], ['Calendar', '/calendar'], ['Google posts', '/google?tab=posts'],
    ['Campaigns', '/google?tab=campaigns'], ['Media library', '/google?tab=media'],
  ] },
  { id: 'inbox', label: 'Inbox', icon: '✉', links: [
    ['Messages', '/inbox'], ['Comments', '/engagement'], ['Google reviews', '/google?tab=reviews'],
  ] },
  { id: 'automations', label: 'Automations', icon: 'ϟ', links: [
    ['Instagram rules', '/automations'], ['Google review replies', '/google?tab=automation'],
    ['Reply history', '/google?tab=history'], ['WhatsApp tools', '/whatsapp?view=automation'],
  ] },
  { id: 'reports', label: 'Reports', icon: '↗', links: [
    ['Instagram insights', '/insights'], ['Google performance', '/google?tab=performance'],
    ['Local rankings', '/google?tab=rank'],
  ] },
]
const storageKey = 'growboard.navigation.section'

export default function WorkspaceShell({ children }: { children: ReactNode }) {
  const location = useLocation()
  const current = location.pathname + location.search
  const activeSection = sections.find(section => section.links.some(([, to]) => to === current))?.id
    || (location.pathname === '/google' ? 'channels' : '')
  const [expanded, setExpanded] = useState<string>(() => {
    try { return activeSection || localStorage.getItem(storageKey) || '' } catch { return activeSection }
  })
  const drawer = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    if (activeSection) setExpanded(activeSection)
    drawer.current?.close()
  }, [current, activeSection])
  useEffect(() => { try { localStorage.setItem(storageKey, expanded) } catch { /* Storage is optional. */ } }, [expanded])
  const nav = (prefix: string) => <>
    <Link className="workspace-wordmark" to="/dashboard"><span className="brand-mark">G</span><span>Growboard<small>YOUR BUSINESS, CONNECTED</small></span></Link>
    <nav className="workspace-navigation" aria-label="Main navigation">
      <Link className={`nav-overview ${location.pathname === '/dashboard' ? 'is-active' : ''}`} aria-current={location.pathname === '/dashboard' ? 'page' : undefined} to="/dashboard"><span aria-hidden="true">⌂</span>Overview</Link>
      {sections.map(section => <div className={`nav-section ${activeSection === section.id ? 'is-active' : ''}`} key={section.id}>
        <button type="button" aria-expanded={expanded === section.id} aria-controls={`${prefix}-${section.id}`} onClick={() => setExpanded(expanded === section.id ? '' : section.id)}>
          <span aria-hidden="true">{section.icon}</span><span>{section.label}</span><span className="nav-chevron" aria-hidden="true">{expanded === section.id ? '−' : '+'}</span>
        </button>
        <div id={`${prefix}-${section.id}`} className="nav-submenu" hidden={expanded !== section.id}>
          {section.links.map(([label, to]) => <Link key={to} className={current === to ? 'is-active' : ''} aria-current={current === to ? 'page' : undefined} to={to}>{label}</Link>)}
        </div>
      </div>)}
    </nav>
    <div className="workspace-nav-bottom"><Link to="/settings/connections">⚙ <span>Settings</span></Link><Link to="/support">? <span>Help & support</span></Link><button onClick={() => void supabase.auth.signOut()}>↪ <span>Sign out</span></button></div>
  </>
  return <div className="app-shell grouped-shell">
    <aside className="workspace-sidebar">{nav('desktop')}</aside>
    <dialog ref={drawer} className="workspace-nav-drawer" aria-label="Navigation" onClick={e => { if (e.target === e.currentTarget) drawer.current?.close() }}>
      <button className="nav-drawer-close" aria-label="Close navigation" onClick={() => drawer.current?.close()}>×</button>{nav('mobile')}
    </dialog>
    <div className="workspace"><header className="workspace-header"><div className="workspace-header-title"><button type="button" className="nav-menu-button" aria-label="Open navigation" onClick={() => drawer.current?.showModal()}>☰</button><div><b>Workspace</b><span>Your business, in one place</span></div></div><div className="header-actions"><Link to="/assistant" className={`workspace-ai ${location.pathname === '/assistant' ? 'is-active' : ''}`}>✦ <span>Business AI</span></Link><Link className="button primary compact" to="/composer">＋ <span>New post</span></Link></div></header><main>{children}</main></div>
  </div>
}
