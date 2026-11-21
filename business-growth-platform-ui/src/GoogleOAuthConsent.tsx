import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { supabase } from './lib/supabase'

type Details={client:{name:string};user:{email:string};scope:string}
export default function GoogleOAuthConsent(){
 const [details,setDetails]=useState<Details>();const [signed,setSigned]=useState<boolean>();const [error,setError]=useState('');const [busy,setBusy]=useState(false);const [email,setEmail]=useState('');const [password,setPassword]=useState('')
 const id=new URLSearchParams(window.location.search).get('authorization_id')
 async function load(){
  if(!id){setError('This connection request has no authorization ID. Start again from your AI application.');return}
  const {data,error:userError}=await supabase.auth.getUser()
  if(userError||!data.user){setSigned(false);return}setSigned(true)
  const response=await supabase.auth.oauth.getAuthorizationDetails(id)
  if(response.error||!response.data){setError(response.error?.message||'Connection request expired.');return}
  if('redirect_url' in response.data){window.location.assign(response.data.redirect_url);return}
  setDetails(response.data as Details)
 }
 useEffect(()=>{void load().catch(()=>setError('Could not inspect this connection request.'))},[])
 async function decide(approve:boolean){if(!id)return;setBusy(true);setError('');try{
  const result=approve?await supabase.auth.oauth.approveAuthorization(id,{skipBrowserRedirect:true}):await supabase.auth.oauth.denyAuthorization(id,{skipBrowserRedirect:true})
  if(result.error||!result.data?.redirect_url)throw new Error(result.error?.message||'Could not complete this connection.')
  window.location.assign(result.data.redirect_url)
 }catch(e){setError(e instanceof Error?e.message:'Connection failed.');setBusy(false)}}
 return <main style={{maxWidth:650,margin:'60px auto',padding:24}}><Link to="/">Growboard</Link><article className="card"><h1>Connect your AI application</h1>{error&&<p className="notice" role="alert">{error}</p>}{signed===false?<form onSubmit={e=>{e.preventDefault();setBusy(true);void supabase.auth.signInWithPassword({email,password}).then(async result=>{setPassword('');if(result.error)throw result.error;await load()}).catch(e=>setError(e.message)).finally(()=>setBusy(false))}}><p>Sign in with your Growboard account to review this connection.</p><label>Email<input type="email" autoComplete="username" required value={email} onChange={e=>setEmail(e.target.value)}/></label><label>Password<input type="password" autoComplete="current-password" required value={password} onChange={e=>setPassword(e.target.value)}/></label><button disabled={busy} className="button primary">Sign in</button></form>:details?<><h2>Allow {details.client.name} to connect?</h2><p>Signed in as {details.user.email}. This application can access the Google Business Profile tools available to your Growboard workspace.</p><ul><li>Read connected locations, reviews and delivery history.</li><li>Draft and publish review replies and configure future reply automation.</li><li>Create, schedule and cancel business posts and campaigns.</li></ul><p>Requested account scopes: {details.scope}</p><p>Approve only an application you trust to act on your business. Google refresh tokens remain on the backend.</p><button disabled={busy} className="button secondary" onClick={()=>void decide(false)}>Deny</button><button disabled={busy} className="button primary" onClick={()=>void decide(true)}>Allow connection</button></>:!error&&<p>Checking your connection request…</p>}</article></main>
}
