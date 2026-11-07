import { FormEvent, createContext, useContext, useEffect, useState } from 'react'
import { Link, NavLink, Navigate, Route, Routes, useNavigate, useSearchParams } from 'react-router-dom'
import type { Session } from '@supabase/supabase-js'
import { supabase, googleSignInEnabled } from './lib/supabase'
import AccessPage from './AccessPage'
import type { AccessState } from './AccessPage'
import BusinessChatbot from './BusinessChatbot'
import Automations from './Automations'
import InboxPage from './Inbox'
import ComposerPage from './Composer'
import CommentsPage from './Comments'
import { api, setApiUser, getCached, type CalendarItem, type InstagramConnection, type Insights } from './lib/api'

function Shell({ children }: { children: React.ReactNode }) {
  return <div className="app-shell"><aside><Link className="brand" to="/dashboard"><span className="brand-mark">G</span><span>Growthboard<small>Instagram OS</small></span></Link><nav><NavLink to="/dashboard">⌂ <span>Overview</span></NavLink><NavLink to="/composer">＋ <span>Create</span></NavLink><NavLink to="/calendar">□ <span>Calendar</span></NavLink><NavLink to="/engagement">♡ <span>Comments</span></NavLink><NavLink to="/inbox">✉ <span>Messages</span></NavLink><NavLink to="/automations">⚡ <span>Automations</span></NavLink><NavLink to="/insights">↗ <span>Insights</span></NavLink><NavLink to="/assistant" title="Business AI">✦ <span>Business AI</span></NavLink></nav><div className="side-bottom"><Link to="/settings/connections">⚙ <span>Settings</span></Link><Link to="/support">? <span>Support</span></Link><button className="text-button" onClick={()=>void supabase.auth.signOut()}>Sign out</button></div></aside><div className="workspace"><header><div><b>Workspace</b><span>Content & engagement control center</span></div><Link className="button primary compact" to="/composer">＋ New post</Link></header><main>{children}</main></div></div>
}

function Home() {
  return <Shell><section className="hero"><span className="eyebrow">Instagram publishing, kept simple</span><h1>Plan with confidence.<br/>Publish with approval.</h1><p>One calm workspace for creating, scheduling, and safely publishing content to your professional Instagram account.</p><div className="actions"><Link className="button primary" to="/login">Start private access</Link><Link className="button secondary" to="/privacy">How we handle data</Link></div><div className="proof"><span>One workspace</span><span>Approval required</span><span>Disconnect anytime</span></div></section></Shell>
}

const AppAccess = createContext<{state?:AccessState;error:string;refresh:()=>Promise<void>}>({error:'',refresh:async()=>{}})
function Login() {
  const [email,setEmail]=useState('');const [password,setPassword]=useState('');const [signup,setSignup]=useState(false);const [message,setMessage]=useState('');const [busy,setBusy]=useState(false);const [google,setGoogle]=useState<boolean>();const navigate=useNavigate()
  useEffect(()=>{let active=true;googleSignInEnabled().then(value=>{if(active)setGoogle(value)}).catch(()=>{if(active)setGoogle(false)});return()=>{active=false}},[])
  async function submit(event:FormEvent){event.preventDefault();setBusy(true);setMessage('');try{const result=signup?await supabase.auth.signUp({email,password}):await supabase.auth.signInWithPassword({email,password});if(result.error)setMessage(result.error.message);else if(signup&&!result.data.session)setMessage('Check your email to confirm your account, then sign in.');else navigate('/access')}catch{setMessage('Could not sign in. Please try again.')}finally{setBusy(false)}}
  async function signInGoogle(){setBusy(true);setMessage('');try{const result=await supabase.auth.signInWithOAuth({provider:'google',options:{redirectTo:`${window.location.origin}/access`}});if(result.error){setMessage(result.error.message);setBusy(false)}}catch{setMessage('Google sign-in could not start. Please try again.');setBusy(false)}}
  return <Shell><section className="auth-card"><p className="eyebrow">{signup?'Create your account':'Welcome back'}</p><h1>{signup?'Join Growthboard.':'Sign in to Growthboard.'}</h1><button className="button google-signin" disabled={busy||!google} onClick={()=>void signInGoogle()}><span aria-hidden="true">G</span>Continue with Google</button>{google===false&&<small className="muted-text">Google sign-in is being configured. Email sign-in is available below.</small>}<div className="auth-divider"><span>or use email</span></div><form onSubmit={submit}><label>Email<input type="email" autoComplete="email" value={email} disabled={busy} onChange={event=>setEmail(event.target.value)} required/></label><label>Password<input type="password" autoComplete={signup?'new-password':'current-password'} minLength={8} value={password} disabled={busy} onChange={event=>setPassword(event.target.value)} required/></label><button className="button primary" disabled={busy}>{busy?'Please wait…':signup?'Create account':'Sign in'}</button></form>{message&&<p className="notice" role="status">{message}</p>}<button className="text-button" disabled={busy} onClick={()=>{setSignup(!signup);setMessage('')}}>{signup?'Already have an account? Sign in':'New here? Create an account'}</button><p className="muted-text">New accounts need your administrator’s access code after signing in.</p></section></Shell>
}
function Protected({session,children}:{session:Session|null;children:React.ReactNode}){
  const access=useContext(AppAccess)
  if(!session)return <Navigate to="/login" replace/>
  if(!access.state||!access.state.approved)return <Navigate to="/access" replace/>
  return <>{children}</>
}
function Access({session}:{session:Session|null}){const access=useContext(AppAccess);return <Shell><AccessPage session={session} state={access.state} error={access.error} onRefresh={access.refresh}/></Shell>}

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

function Composer() { return <Shell><ComposerPage /></Shell> }

function Calendar() {
  const [items,setItems]=useState<CalendarItem[]>([]); const [message,setMessage]=useState(''); const load=()=>api.calendar().then(r=>setItems(r.items)).catch(e=>setMessage(e.message)); useEffect(()=>{void load();const timer=setInterval(()=>void load(),15000);return()=>clearInterval(timer)},[])
  async function publish(id:string){setMessage('Publishing…');try{await api.publishJob(id);setMessage('Published successfully.');load()}catch(e){setMessage(e instanceof Error?e.message:'Publishing failed')}}
  const grouped=items.reduce<Record<string,CalendarItem[]>>((all,item)=>{const d=new Date(item.scheduled_for);const day=`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;(all[day]??=[]).push(item);return all},{})
  async function cancel(id:string){if(!confirm('Cancel this scheduled post?'))return;try{await api.cancelCalendarItem(id);setMessage('Post cancelled.');load()}catch(e){setMessage(e instanceof Error?e.message:'Could not cancel')}}
  async function edit(item:CalendarItem){const caption=prompt('Edit caption',item.content_targets.content_drafts.caption);if(caption===null)return;const when=prompt('Schedule in ISO format',item.scheduled_for);if(when===null)return;try{await api.updateCalendarItem(item.id,{caption,scheduled_for:new Date(when).toISOString()});setMessage('Post updated.');load()}catch(e){setMessage(e instanceof Error?e.message:'Could not update')}}
  return <Shell><section className="page-heading split"><div><p className="eyebrow">Content calendar</p><h1>Your publishing rhythm.</h1><p>Plan, reschedule, cancel, retry and review every post.</p></div><Link className="button primary" to="/composer">＋ Create post</Link></section><div className="filter-bar"><span>All content</span><span>{items.filter(x=>x.status==='scheduled').length} scheduled</span><span>{items.filter(x=>x.status==='published').length} published</span></div><div className="calendar-list">{Object.keys(grouped).length===0?<Empty title="No posts yet" action="Create your first post" to="/composer"/>:Object.entries(grouped).map(([day,posts])=><section key={day} className="calendar-day"><time>{new Date(`${day}T00:00:00`).toLocaleDateString(undefined,{weekday:'long',month:'short',day:'numeric'})}</time><div>{posts.map(item=><article className="calendar-item" key={item.id}><div><span className={`status-pill ${item.status}`}>{item.status}</span> <small>{item.content_targets.content_drafts.post_type==='carousel'?'Carousel':'Photo post'}</small><p>{item.content_targets.content_drafts.caption||'Untitled post'}</p>{item.failure_message&&<p className="notice">{item.failure_message}</p>}<small>{new Date(item.scheduled_for).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}</small></div><div className="row-actions">{['scheduled','failed'].includes(item.status)&&<button onClick={()=>edit(item)}>Edit</button>}{item.status==='failed'&&<button onClick={()=>publish(item.id)}>Retry</button>}{item.status==='scheduled'&&new Date(item.scheduled_for)<=new Date()&&<button onClick={()=>publish(item.id)}>Publish now</button>}{['scheduled','failed'].includes(item.status)&&<button className="danger-link" onClick={()=>cancel(item.id)}>Cancel</button>}{item.provider_permalink&&<a href={item.provider_permalink} target="_blank">Open ↗</a>}</div></article>)}</div></section>)}</div>{message&&<p className="notice wide">{message}</p>}</Shell>
}

function Engagement(){return <Shell><CommentsPage/></Shell>}

function Inbox(){return <Shell><InboxPage/></Shell>}

function InsightsPage(){const [data,setData]=useState<Insights|null>(getCached<Insights>('/api/instagram/insights')||null);const [message,setMessage]=useState('');useEffect(()=>{api.insights().then(setData).catch(e=>setMessage(e.message))},[]);const metric=(name:string)=>data?.metrics.find(x=>x.name===name)?.total_value?.value??data?.metrics.find(x=>x.name===name)?.values?.at(-1)?.value??'—';return <Shell><section className="page-heading"><p className="eyebrow">Performance</p><h1>Insights</h1><p>A focused view of account growth and audience attention.</p></section><div className="section-title insight-toolbar"><span>{data?'Recently loaded Instagram metrics':'Loading Instagram metrics…'}</span><button className="button secondary compact" onClick={()=>{setMessage('Refreshing…');api.insights(true).then(result=>{setData(result);setMessage('Metrics refreshed.')}).catch(error=>setMessage(error.message))}}>Refresh metrics</button></div><div className={`metric-grid ${!data?'is-loading':''}`}><article><span>Followers</span><strong>{data?.profile.followers_count??'—'}</strong><small>Current audience</small></article><article><span>Reach</span><strong>{metric('reach')}</strong><small>Accounts reached</small></article><article><span>Views</span><strong>{metric('views')}</strong><small>Content views</small></article><article><span>Profile views</span><strong>{metric('profile_views')}</strong><small>Profile activity</small></article></div><article className="card insight-note"><p className="eyebrow">Reporting</p><h2>Performance, without the noise.</h2><p>Metrics shown here come directly from Instagram. Account-level reporting availability depends on the professional account type and the permission granted during connection.</p></article>{message&&<p className="notice wide">{message}</p>}</Shell>}

const legal: Record<string, {title:string, body:string[]}> = {
  privacy: { title:'Privacy policy', body:['Growthboard uses authorised professional account details, publishing content, comments and messages to provide the features you enable. Instagram messages and comment events can trigger the automation rules you explicitly enable.','We store encrypted Instagram access tokens, publishing assets and captions, incoming text events needed for automations, your rule settings, and delivery history. Publishing image links are temporary. Contact the pilot administrator about retention and deletion of stored workspace data.','Disconnect Instagram in Settings to remove the stored access token, pause rules and cancel pending publications. Request deletion of stored workspace data through the pilot administrator using your registered email. The service uses Meta, Supabase and Render to provide these features. If you enable the business AI assistant, your business information and customer messages with recent conversation context are sent to Groq to generate replies. Preview questions are also sent to Groq when you request a preview. AI is optional and starts paused.'] },
  terms: { title:'Terms of service', body:['This private-testing service helps approved businesses prepare and publish Instagram content. You remain responsible for your content, permissions, and compliance with Instagram terms and applicable law.','The service is provided for evaluation during the private pilot and may change. Do not use it for unlawful, deceptive, unsolicited, or rights-infringing activity. Review the exact content before publishing and enable automation rules only for replies you authorise.'] },
  support: { title:'Support', body:['For pilot support, contact the address supplied with your invitation. Include your workspace name and error reference, but never send passwords, access tokens, or Meta app secrets.'] },
  'data-deletion': { title:'Data deletion', body:['Disconnect Instagram in Settings to revoke the stored token, pause automation rules and cancel pending work. For deletion of stored account data, contact the pilot administrator from your registered account email.','Until the self-service deletion screen is enabled, contact the pilot support address. We will verify account ownership before processing the request.'] },
}
function Legal({ kind }: {kind:string}) { const page=legal[kind]; return <Shell><article className="legal"><p className="eyebrow">Last updated November 7, 2026</p><h1>{page.title}</h1>{page.body.map((p,i)=><p key={i}>{p}</p>)}</article></Shell> }

export default function App() {
  const [session, setSession] = useState<Session | null>(null); const [ready, setReady] = useState(false)
  const [access,setAccess]=useState<{user:string;state?:AccessState;error:string}>({user:'',error:''})
  const userId=session?.user.id
  async function refreshAccess(){if(!userId)return;try{const state=await api.accessStatus();setAccess({user:userId,state,error:''})}catch(error){setAccess({user:userId,error:error instanceof Error?error.message:'Could not check access.'})}}
  useEffect(()=>{let active=true;if(userId){api.accessStatus().then(state=>{if(active)setAccess({user:userId,state,error:''})}).catch(error=>{if(active)setAccess({user:userId,error:error.message})})}return()=>{active=false}},[userId])
  useEffect(()=>{ supabase.auth.getSession().then(({data})=>{setApiUser(data.session?.user.id || '');setSession(data.session);setReady(true)}); const {data}=supabase.auth.onAuthStateChange((_e,s)=>{setApiUser(s?.user.id || '');setSession(s)}); return()=>data.subscription.unsubscribe() },[])
  if(!ready) return <div className="loading">Growthboard</div>
  return <AppAccess.Provider value={{state:access.user===userId?access.state:undefined,error:access.user===userId?access.error:'',refresh:refreshAccess}}><Routes key={session?.user.id||'public'}><Route path="/" element={<Home/>}/><Route path="/login" element={<Login/>}/><Route path="/access" element={<Access session={session}/>}/><Route path="/dashboard" element={<Protected session={session}><Dashboard/></Protected>}/><Route path="/composer" element={<Protected session={session}><Composer/></Protected>}/><Route path="/calendar" element={<Protected session={session}><Calendar/></Protected>}/><Route path="/engagement" element={<Protected session={session}><Engagement/></Protected>}/><Route path="/inbox" element={<Protected session={session}><Inbox/></Protected>}/><Route path="/automations" element={<Protected session={session}><Shell><Automations/></Shell></Protected>}/><Route path="/assistant" element={<Protected session={session}><Shell><BusinessChatbot/></Shell></Protected>}/><Route path="/insights" element={<Protected session={session}><InsightsPage/></Protected>}/><Route path="/settings/connections" element={<Protected session={session}><Connections/></Protected>}/>{Object.keys(legal).map(k=><Route key={k} path={`/${k}`} element={<Legal kind={k}/>}/>)}<Route path="*" element={<Navigate to="/"/>}/></Routes></AppAccess.Provider>
}
