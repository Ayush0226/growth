import { FormEvent, useEffect, useState } from 'react'
import { Link, Navigate, Route, Routes, useNavigate, useSearchParams } from 'react-router-dom'
import type { Session } from '@supabase/supabase-js'
import { supabase } from './lib/supabase'
import Automations from './Automations'
import InboxPage from './Inbox'
import { api, type CalendarItem, type InstagramComment, type InstagramConnection, type InstagramMedia, type Insights } from './lib/api'

function Shell({ children }: { children: React.ReactNode }) {
  return <div className="app-shell"><aside><Link className="brand" to="/dashboard"><span className="brand-mark">G</span><span>Growthboard<small>Instagram OS</small></span></Link><nav><Link to="/dashboard">⌂ <span>Overview</span></Link><Link to="/composer">＋ <span>Create</span></Link><Link to="/calendar">□ <span>Calendar</span></Link><Link to="/engagement">♡ <span>Comments</span></Link><Link to="/inbox">✉ <span>Messages</span></Link><Link to="/automations">⚡ <span>Automations</span></Link><Link to="/insights">↗ <span>Insights</span></Link></nav><div className="side-bottom"><Link to="/settings/connections">⚙ <span>Settings</span></Link><Link to="/support">? <span>Support</span></Link><button className="text-button" onClick={()=>void supabase.auth.signOut()}>Sign out</button></div></aside><div className="workspace"><header><div><b>Workspace</b><span>Content & engagement control center</span></div><Link className="button primary compact" to="/composer">＋ New post</Link></header><main>{children}</main></div></div>
}

function Home() {
  return <Shell><section className="hero"><span className="eyebrow">Instagram publishing, kept simple</span><h1>Plan with confidence.<br/>Publish with approval.</h1><p>One calm workspace for creating, scheduling, and safely publishing content to your professional Instagram account.</p><div className="actions"><Link className="button primary" to="/login">Start private access</Link><Link className="button secondary" to="/privacy">How we handle data</Link></div><div className="proof"><span>One workspace</span><span>Approval required</span><span>Disconnect anytime</span></div></section></Shell>
}

function Login() {
  const [email, setEmail] = useState(''); const [password, setPassword] = useState(''); const [signup, setSignup] = useState(false); const [message, setMessage] = useState(''); const navigate = useNavigate()
  async function submit(e: FormEvent) { e.preventDefault(); setMessage(''); const result = signup ? await supabase.auth.signUp({ email, password }) : await supabase.auth.signInWithPassword({ email, password }); if (result.error) setMessage(result.error.message); else if (signup && !result.data.session) setMessage('Check your email to confirm your account.'); else navigate('/dashboard') }
  return <Shell><section className="auth-card"><p className="eyebrow">{signup ? 'Create your workspace' : 'Welcome back'}</p><h1>{signup ? 'Start publishing thoughtfully.' : 'Sign in to Growthboard.'}</h1><form onSubmit={submit}><label>Email<input type="email" value={email} onChange={e=>setEmail(e.target.value)} required /></label><label>Password<input type="password" minLength={8} value={password} onChange={e=>setPassword(e.target.value)} required /></label><button className="button primary" type="submit">{signup ? 'Create account' : 'Sign in'}</button></form>{message && <p className="notice">{message}</p>}<button className="text-button" onClick={()=>setSignup(!signup)}>{signup ? 'Already have an account? Sign in' : 'New here? Create an account'}</button></section></Shell>
}

function Protected({ session, children }: { session: Session | null, children: React.ReactNode }) { return session ? <>{children}</> : <Navigate to="/login" replace /> }

function Dashboard() {
  const [name, setName] = useState(''); const [message, setMessage] = useState(''); const [workspaceReady,setWorkspaceReady]=useState(false); useEffect(()=>{api.workspace().then(r=>setWorkspaceReady(Boolean(r.workspace))).catch(e=>setMessage(e.message))},[])
  async function create(e: FormEvent) { e.preventDefault(); try { await api.provisionWorkspace(name); setWorkspaceReady(true); setMessage('Workspace ready. You can now connect Instagram.'); } catch (err) { setMessage(err instanceof Error ? err.message : 'Could not create workspace') } }
  const [connection,setConnection]=useState<InstagramConnection|null>(null); const [calendar,setCalendar]=useState<CalendarItem[]>([]); useEffect(()=>{api.instagramStatus().then(setConnection).catch(()=>{});api.calendar().then(r=>setCalendar(r.items)).catch(()=>{})},[])
  if(connection?.connected) return <Shell><section className="page-heading"><p className="eyebrow">Command center</p><h1>Your workspace at a glance.</h1><p>Here is what is happening with @{connection.username}.</p></section><div className="metric-grid"><article><span>Scheduled</span><strong>{calendar.filter(x=>x.status==='scheduled').length}</strong><small>Upcoming posts</small></article><article><span>Published</span><strong>{calendar.filter(x=>x.status==='published').length}</strong><small>Successful posts</small></article><article><span>Needs attention</span><strong>{calendar.filter(x=>x.status==='failed').length}</strong><small>Failed actions</small></article><article><span>Connection</span><strong className="live-dot">Live</strong><small>@{connection.username}</small></article></div><div className="dashboard-grid"><article className="card"><div className="section-title"><div><p className="eyebrow">Publishing</p><h2>Upcoming content</h2></div><Link to="/calendar">View calendar →</Link></div>{calendar.filter(x=>x.status==='scheduled').slice(0,3).map(x=><div className="activity-row" key={x.id}><span className="date-tile">{new Date(x.scheduled_for).getDate()}<small>{new Date(x.scheduled_for).toLocaleString('en',{month:'short'})}</small></span><p>{x.content_targets.content_drafts.caption||'Untitled post'}<small>{new Date(x.scheduled_for).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}</small></p><span className="status-pill scheduled">Scheduled</span></div>)||null}{!calendar.some(x=>x.status==='scheduled')&&<Empty title="Nothing scheduled" action="Create a post" to="/composer"/>}</article><article className="card quick-panel"><p className="eyebrow">Quick actions</p><h2>Keep momentum</h2><Link to="/composer">Create a post <span>→</span></Link><Link to="/engagement">Review comments <span>→</span></Link><Link to="/inbox">Open inbox <span>→</span></Link><Link to="/insights">Check performance <span>→</span></Link></article></div></Shell>
  return <Shell><section className="page-heading"><p className="eyebrow">Setup</p><h1>Build your command center.</h1><p>Create a workspace, connect Instagram, then manage publishing and engagement in one place.</p></section><div className="grid"><article className="card"><span className="step">01</span><h2>Create workspace</h2>{workspaceReady?<p>Your workspace is ready. Connect Instagram to continue.</p>:<form onSubmit={create}><label>Business name<input value={name} onChange={e=>setName(e.target.value)} placeholder="Acme Studio" required /></label><button className="button primary">Create workspace</button></form>}{message&&<p className="notice">{message}</p>}</article><article className="card muted"><span className="step">02</span><h2>Connect Instagram</h2><Link className="button secondary" to="/settings/connections">Manage connection</Link></article></div></Shell>
}

function Empty({title,action,to}:{title:string,action:string,to:string}){return <div className="empty"><span>◇</span><h3>{title}</h3><Link to={to}>{action} →</Link></div>}

function Connections() {
  const [includeInsights, setIncludeInsights] = useState(false)
  const [status, setStatus] = useState<InstagramConnection | null>(null)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [params] = useSearchParams()
  const refresh = () => api.instagramStatus().then(setStatus).catch(e => setMessage(e.message))
  useEffect(() => {
    void refresh()
    const timer = setInterval(() => void refresh(), 15000)
    const outcome = params.get('instagram')
    if (outcome) {
      const messages: Record<string, string> = {
        connected: 'Instagram connected successfully.',
        limited: 'Connected with limited permissions. Reconnect to approve the features you need.',
        invalid_state: 'This connection link expired or was already used. Start Connect Instagram again.',
        cancelled: 'Connection was cancelled.',
        failed: 'Connection failed. Try connecting again. If this continues, contact support.',
      }
      setMessage(messages[outcome] || 'Check your Instagram connection.')
    }
    return () => clearInterval(timer)
  }, [params])
  async function connect() {
    setBusy(true)
    try {
      const { authorization_url } = await api.instagramConnectUrl(includeInsights)
      window.location.assign(authorization_url)
    } catch (e) { setMessage(e instanceof Error ? e.message : 'Could not connect'); setBusy(false) }
  }
  async function disconnect() {
    if (!confirm('Disconnect Instagram, pause automation rules, and cancel pending publications?')) return
    setBusy(true)
    try {
      await api.disconnectInstagram(); setStatus({ connected: false })
      setMessage('Instagram disconnected; rules paused and pending jobs cancelled.')
    } catch (e) { setMessage(e instanceof Error ? e.message : 'Could not disconnect') }
    finally { setBusy(false) }
  }
  async function subscribe() {
    setBusy(true)
    try {
      await api.subscribeInstagram()
      setMessage('Instagram accepted the connection request. Send a new DM from another account to confirm that messages are arriving.')
      await refresh()
    } catch { setMessage('Automatic replies could not be connected. Reconnect permissions or contact support.') }
    finally { setBusy(false) }
  }
  const capability = (label: string, on?: boolean) => <div><dt>{label}</dt><dd className={on ? 'enabled' : 'disabled'}>{on ? '● Granted' : '○ Not granted'}</dd></div>
  return <Shell>
    <section className="page-heading"><p className="eyebrow">Settings / Connections</p><h1>Connected accounts</h1><p>Connect a professional Instagram account and control its publishing and engagement permissions.</p><label className="check-row"><input type="checkbox" checked={includeInsights} onChange={e => setIncludeInsights(e.target.checked)} />Also request optional insights permission when connecting</label></section>
    {message && <p className="notice wide" role="status">{message}</p>}
    <article className="connection card"><div className="ig-mark">IG</div><div><h2>Instagram</h2>
      {status?.connected ? <>
        <p className="status good">Connected · @{status.username}</p>
        <dl>{capability('Publishing', status.publishing_enabled)}{capability('Comments', status.comments_enabled)}{capability('Messages', status.messages_enabled)}</dl>
        <h3>Automatic replies</h3>
        {status.last_event_received_at ? <p>Last incoming activity: {new Date(status.last_event_received_at).toLocaleString()}. <Link to="/automations">View reply activity →</Link></p>
          : <p className="notice">Waiting for the first incoming message or comment. Send a new DM from another account. If it does not appear in Automations, contact support to check your connection.</p>}
        {status.token_expires_at && <p>Connection renewal due: {new Date(status.token_expires_at).toLocaleDateString()}</p>}
        {status.webhook_error && <p className="notice">Automatic replies need attention. Reconnect permissions or contact support.</p>}
        <div className="actions"><button className="button primary" disabled={busy} onClick={connect}>Reconnect permissions</button>{!status.webhook_subscribed && <button className="button secondary" disabled={busy || !status.messages_enabled} onClick={subscribe}>Connect automatic replies</button>}<button className="button danger" disabled={busy} onClick={disconnect}>Disconnect</button></div>
      </> : <><p>Create a workspace first, then connect a Business or Creator account.</p><button className="button primary" disabled={busy} onClick={connect}>{busy ? 'Opening Instagram…' : 'Connect Instagram'}</button></>}
    </div></article>
  </Shell>
}

function Composer() {
  const [approved,setApproved]=useState(false); const [file,setFile]=useState<File|null>(null); const [preview,setPreview]=useState(''); const [caption,setCaption]=useState(''); const [scheduled,setScheduled]=useState(''); const [busy,setBusy]=useState(false); const [message,setMessage]=useState('')
  function choose(next: File|null) { setApproved(false); setFile(next); if(preview) URL.revokeObjectURL(preview); setPreview(next ? URL.createObjectURL(next) : '') }
  async function submit(publishNow:boolean) { if(!approved) return setMessage('Approve the image and caption before continuing.'); if(!publishNow&&(!scheduled||new Date(scheduled)<=new Date())) return setMessage('Choose a future schedule time.'); if(!file) return setMessage('Choose a JPEG image first.'); setBusy(true); setMessage('Uploading and validating image…'); try { const asset=await api.uploadMedia(file); setMessage(publishNow ? 'Publishing to Instagram…' : 'Creating scheduled post…'); const result=await api.createPost({caption,media_asset_id:asset.id,scheduled_for:scheduled ? new Date(scheduled).toISOString() : undefined,timezone:Intl.DateTimeFormat().resolvedOptions().timeZone,approved:true,publish_now:publishNow}); setMessage(result.job.status==='published' ? 'Published successfully.' : 'Post added to the calendar.'); } catch(e) { setMessage(e instanceof Error ? e.message : 'Post could not be created') } finally { setBusy(false) } }
  return <Shell><section className="page-heading"><p className="eyebrow">Content studio</p><h1>Create one clear post.</h1><p>JPEG photo publishing is enabled. Every post requires your approval.</p></section><div className="composer-grid"><article className="card"><label>JPEG image<input type="file" accept="image/jpeg" onChange={e=>choose(e.target.files?.[0]??null)}/></label><label>Caption<textarea value={caption} maxLength={2200} rows={8} onChange={e=>{setApproved(false);setCaption(e.target.value)}} placeholder="Write your caption…"/></label><label>Schedule (optional)<input type="datetime-local" value={scheduled} onChange={e=>setScheduled(e.target.value)}/></label><label className="check-row approval"><input type="checkbox" checked={approved} onChange={e=>setApproved(e.target.checked)}/>I approve this image and caption for publication.</label><div className="actions"><button disabled={busy||!approved} className="button primary" onClick={()=>submit(true)}>Publish now</button><button disabled={busy||!scheduled||!approved} className="button secondary" onClick={()=>submit(false)}>Schedule</button></div>{message&&<p className="notice">{message}</p>}</article><article className="phone-preview">{preview?<img src={preview} alt="Post preview"/>:<div className="empty-preview">Your post preview</div>}<p>{caption||'Your caption will appear here.'}</p></article></div></Shell>
}

function Calendar() {
  const [items,setItems]=useState<CalendarItem[]>([]); const [message,setMessage]=useState(''); const load=()=>api.calendar().then(r=>setItems(r.items)).catch(e=>setMessage(e.message)); useEffect(()=>{void load();const timer=setInterval(()=>void load(),15000);return()=>clearInterval(timer)},[])
  async function publish(id:string){setMessage('Publishing…');try{await api.publishJob(id);setMessage('Published successfully.');load()}catch(e){setMessage(e instanceof Error?e.message:'Publishing failed')}}
  const grouped=items.reduce<Record<string,CalendarItem[]>>((all,item)=>{const d=new Date(item.scheduled_for);const day=`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;(all[day]??=[]).push(item);return all},{})
  async function cancel(id:string){if(!confirm('Cancel this scheduled post?'))return;try{await api.cancelCalendarItem(id);setMessage('Post cancelled.');load()}catch(e){setMessage(e instanceof Error?e.message:'Could not cancel')}}
  async function edit(item:CalendarItem){const caption=prompt('Edit caption',item.content_targets.content_drafts.caption);if(caption===null)return;const when=prompt('Schedule in ISO format',item.scheduled_for);if(when===null)return;try{await api.updateCalendarItem(item.id,{caption,scheduled_for:new Date(when).toISOString()});setMessage('Post updated.');load()}catch(e){setMessage(e instanceof Error?e.message:'Could not update')}}
  return <Shell><section className="page-heading split"><div><p className="eyebrow">Content calendar</p><h1>Your publishing rhythm.</h1><p>Plan, reschedule, cancel, retry and review every post.</p></div><Link className="button primary" to="/composer">＋ Create post</Link></section><div className="filter-bar"><span>All content</span><span>{items.filter(x=>x.status==='scheduled').length} scheduled</span><span>{items.filter(x=>x.status==='published').length} published</span></div><div className="calendar-list">{Object.keys(grouped).length===0?<Empty title="No posts yet" action="Create your first post" to="/composer"/>:Object.entries(grouped).map(([day,posts])=><section key={day} className="calendar-day"><time>{new Date(`${day}T00:00:00`).toLocaleDateString(undefined,{weekday:'long',month:'short',day:'numeric'})}</time><div>{posts.map(item=><article className="calendar-item" key={item.id}><div><span className={`status-pill ${item.status}`}>{item.status}</span><p>{item.content_targets.content_drafts.caption||'Untitled post'}</p>{item.failure_message&&<p className="notice">{item.failure_message}</p>}<small>{new Date(item.scheduled_for).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}</small></div><div className="row-actions">{['scheduled','failed'].includes(item.status)&&<button onClick={()=>edit(item)}>Edit</button>}{item.status==='failed'&&<button onClick={()=>publish(item.id)}>Retry</button>}{item.status==='scheduled'&&new Date(item.scheduled_for)<=new Date()&&<button onClick={()=>publish(item.id)}>Publish now</button>}{['scheduled','failed'].includes(item.status)&&<button className="danger-link" onClick={()=>cancel(item.id)}>Cancel</button>}{item.provider_permalink&&<a href={item.provider_permalink} target="_blank">Open ↗</a>}</div></article>)}</div></section>)}</div>{message&&<p className="notice wide">{message}</p>}</Shell>
}

function Engagement(){
  const [media,setMedia]=useState<InstagramMedia[]>([]);const [selected,setSelected]=useState<InstagramMedia|null>(null);const [comments,setComments]=useState<InstagramComment[]>([]);const [message,setMessage]=useState('')
  useEffect(()=>{api.media().then(r=>{setMedia(r.data);if(r.data[0])setSelected(r.data[0])}).catch(e=>setMessage(e.message))},[])
  useEffect(()=>{if(selected)api.comments(selected.id).then(r=>setComments(r.data)).catch(e=>setMessage(e.message))},[selected])
  async function reply(c:InstagramComment){const text=prompt(`Reply to @${c.username}`);if(!text)return;try{await api.replyComment(c.id,text);setMessage('Reply posted.');if(selected)setComments((await api.comments(selected.id)).data)}catch(e){setMessage(e instanceof Error?e.message:'Reply failed')}}
  async function hide(c:InstagramComment){try{await api.hideComment(c.id,!c.hidden);setComments(comments.map(x=>x.id===c.id?{...x,hidden:!x.hidden}:x))}catch(e){setMessage(e instanceof Error?e.message:'Action failed')}}
  async function remove(c:InstagramComment){if(!confirm('Permanently delete this comment?'))return;try{await api.deleteComment(c.id);setComments(comments.filter(x=>x.id!==c.id))}catch(e){setMessage(e instanceof Error?e.message:'Delete failed')}}
  return <Shell><section className="page-heading split"><div><p className="eyebrow">Community</p><h1>Comments</h1><p>Respond thoughtfully and moderate conversations from one queue.</p></div><span className="status-pill published">Live data</span></section><div className="engagement-layout"><section className="media-rail card"><h3>Published posts</h3>{media.map(m=><button className={selected?.id===m.id?'media-row active':'media-row'} onClick={()=>setSelected(m)} key={m.id}><img src={m.thumbnail_url||m.media_url}/><span>{m.caption||'Untitled post'}<small>{m.comments_count||0} comments</small></span></button>)}</section><section className="comment-panel card"><div className="section-title"><h2>Conversation</h2><span>{comments.length} comments</span></div>{comments.length===0?<Empty title="No comments here" action="Open calendar" to="/calendar"/>:comments.map(c=><article className={c.hidden?'comment hidden':'comment'} key={c.id}><div className="avatar">{c.username?.[0]?.toUpperCase()}</div><div><b>@{c.username}</b><small>{new Date(c.timestamp).toLocaleString()}</small><p>{c.text}</p>{c.replies?.data?.map(r=><p className="reply" key={r.id}><b>@{r.username}</b> {r.text}</p>)}<div className="row-actions"><button onClick={()=>reply(c)}>Reply</button><button onClick={()=>hide(c)}>{c.hidden?'Unhide':'Hide'}</button><button className="danger-link" onClick={()=>remove(c)}>Delete</button></div></div></article>)}</section></div>{message&&<p className="notice wide">{message}</p>}</Shell>
}

function Inbox(){return <Shell><InboxPage/></Shell>}

function InsightsPage(){const [data,setData]=useState<Insights|null>(null);const [message,setMessage]=useState('');useEffect(()=>{api.insights().then(setData).catch(e=>setMessage(e.message))},[]);const metric=(name:string)=>data?.metrics.find(x=>x.name===name)?.total_value?.value??data?.metrics.find(x=>x.name===name)?.values?.at(-1)?.value??'—';return <Shell><section className="page-heading"><p className="eyebrow">Performance</p><h1>Insights</h1><p>A focused view of account growth and audience attention.</p></section><div className="metric-grid"><article><span>Followers</span><strong>{data?.profile.followers_count??'—'}</strong><small>Current audience</small></article><article><span>Reach</span><strong>{metric('reach')}</strong><small>Accounts reached</small></article><article><span>Views</span><strong>{metric('views')}</strong><small>Content views</small></article><article><span>Profile views</span><strong>{metric('profile_views')}</strong><small>Profile activity</small></article></div><article className="card insight-note"><p className="eyebrow">Reporting</p><h2>Performance, without the noise.</h2><p>Metrics shown here come directly from Instagram. Account-level reporting availability depends on the professional account type and the permission granted during connection.</p></article>{message&&<p className="notice wide">{message}</p>}</Shell>}

const legal: Record<string, {title:string, body:string[]}> = {
  privacy: { title:'Privacy policy', body:['Growthboard uses authorised professional account details, publishing content, comments and messages to provide the features you enable. Instagram messages and comment events can trigger the automation rules you explicitly enable.','We store encrypted Instagram access tokens, publishing assets and captions, incoming text events needed for automations, your rule settings, and delivery history. Publishing image links are temporary. Contact the pilot administrator about retention and deletion of stored workspace data.','Disconnect Instagram in Settings to remove the stored access token, pause rules and cancel pending publications. Request deletion of stored workspace data through the pilot administrator using your registered email. The service uses Meta, Supabase and Render to provide these features.'] },
  terms: { title:'Terms of service', body:['This private-testing service helps approved businesses prepare and publish Instagram content. You remain responsible for your content, permissions, and compliance with Instagram terms and applicable law.','The service is provided for evaluation during the private pilot and may change. Do not use it for unlawful, deceptive, unsolicited, or rights-infringing activity. Review the exact content before publishing and enable automation rules only for replies you authorise.'] },
  support: { title:'Support', body:['For pilot support, contact the address supplied with your invitation. Include your workspace name and error reference, but never send passwords, access tokens, or Meta app secrets.'] },
  'data-deletion': { title:'Data deletion', body:['Disconnect Instagram in Settings to revoke the stored token, pause automation rules and cancel pending work. For deletion of stored account data, contact the pilot administrator from your registered account email.','Until the self-service deletion screen is enabled, contact the pilot support address. We will verify account ownership before processing the request.'] },
}
function Legal({ kind }: {kind:string}) { const page=legal[kind]; return <Shell><article className="legal"><p className="eyebrow">Last updated November 3, 2026</p><h1>{page.title}</h1>{page.body.map((p,i)=><p key={i}>{p}</p>)}</article></Shell> }

export default function App() {
  const [session, setSession] = useState<Session | null>(null); const [ready, setReady] = useState(false)
  useEffect(()=>{ supabase.auth.getSession().then(({data})=>{setSession(data.session);setReady(true)}); const {data}=supabase.auth.onAuthStateChange((_e,s)=>setSession(s)); return()=>data.subscription.unsubscribe() },[])
  if(!ready) return <div className="loading">Growthboard</div>
  return <Routes><Route path="/" element={<Home/>}/><Route path="/login" element={<Login/>}/><Route path="/dashboard" element={<Protected session={session}><Dashboard/></Protected>}/><Route path="/composer" element={<Protected session={session}><Composer/></Protected>}/><Route path="/calendar" element={<Protected session={session}><Calendar/></Protected>}/><Route path="/engagement" element={<Protected session={session}><Engagement/></Protected>}/><Route path="/inbox" element={<Protected session={session}><Inbox/></Protected>}/><Route path="/automations" element={<Protected session={session}><Shell><Automations/></Shell></Protected>}/><Route path="/insights" element={<Protected session={session}><InsightsPage/></Protected>}/><Route path="/settings/connections" element={<Protected session={session}><Connections/></Protected>}/>{Object.keys(legal).map(k=><Route key={k} path={`/${k}`} element={<Legal kind={k}/>}/>)}<Route path="*" element={<Navigate to="/"/>}/></Routes>
}
