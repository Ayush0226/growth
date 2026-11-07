import { useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate } from 'react-router-dom'
import type { Session } from '@supabase/supabase-js'
import { api } from './lib/api'
import { supabase } from './lib/supabase'

export type AccessState={approved:boolean;setup_ready:boolean;revoked:boolean}
export default function AccessPage({session,state,error,onRefresh}:{session:Session|null;state?:AccessState;error:string;onRefresh:()=>Promise<void>}){
  const [code,setCode]=useState('')
  const [notice,setNotice]=useState('')
  const [busy,setBusy]=useState(false)
  if(!session)return <Navigate to="/login" replace/>
  if(state?.approved)return <Navigate to="/dashboard" replace/>
  async function submit(event:FormEvent){event.preventDefault();if(busy)return;setBusy(true);setNotice('');try{await api.redeemAccess(code);setCode('');await onRefresh()}catch(e){setNotice(e instanceof Error?e.message:'Could not confirm access.')}finally{setBusy(false)}}
  return <section className="auth-card access-card"><p className="eyebrow">Growthboard private access</p><h1>Welcome. You’re almost in.</h1><p className="muted-text">Signed in as <b>{session.user.email||'your account'}</b>. Enter the access code provided by your administrator once to unlock your workspace.</p>
    {!state&&!error&&<p role="status">Checking your access…</p>}
    {error&&<><p className="notice" role="alert">{error}</p><button className="button secondary" disabled={busy} onClick={()=>void onRefresh()}>Try again</button></>}
    {state?.revoked?<p className="notice">Access has been withdrawn for this account. Contact your administrator.</p>:state&&!state.setup_ready?<p className="notice">Access setup is being completed. Please contact your administrator.</p>:state&&<form onSubmit={submit}><label>Access code<input type="password" autoComplete="off" spellCheck={false} maxLength={128} value={code} onChange={event=>setCode(event.target.value)} disabled={busy} required/></label><button className="button primary" disabled={busy||!code}>{busy?'Checking…':'Unlock my workspace'}</button></form>}
    {notice&&<p className="notice" role="alert">{notice}</p>}<p className="muted-text">Your approval is saved to your account for future sign-ins.</p><button className="text-button" disabled={busy} onClick={()=>void supabase.auth.signOut()}>Use a different account</button>
  </section>
}
