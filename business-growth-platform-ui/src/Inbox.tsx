import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api } from './lib/api'
import type { Conversation, DirectMessage } from './lib/api'

export default function Inbox() {
  const [ownId,setOwnId]=useState('')
  const [threads,setThreads]=useState<Conversation[]>([])
  const [selected,setSelected]=useState<Conversation|null>(null)
  const [messages,setMessages]=useState<DirectMessage[]>([])
  const [text,setText]=useState('')
  const [query,setQuery]=useState('')
  const [busy,setBusy]=useState(false)
  const [notice,setNotice]=useState('')
  useEffect(()=>{
    let active=true
    const load=()=>api.conversations().then(r=>{
      if(!active)return
      setThreads(r.data)
      setSelected(current=>r.data.find(t=>t.id===current?.id)||r.data[0]||null)
    }).catch(e=>{if(active)setNotice(e.message)})
    api.instagramStatus().then(r=>{if(active)setOwnId(r.provider_account_id||'')}).catch(e=>{if(active)setNotice(e.message)})
    void load()
    const timer=setInterval(()=>void load(),15000)
    return()=>{active=false;clearInterval(timer)}
  },[])
  const selectedId=selected?.id
  useEffect(()=>{
    let active=true
    setMessages([]);setText('')
    if(!selectedId)return
    const load=()=>api.messages(selectedId).then(r=>{if(active)setMessages([...r.data].reverse())}).catch(e=>{if(active)setNotice(e.message)})
    void load()
    const timer=setInterval(()=>void load(),15000)
    return()=>{active=false;clearInterval(timer)}
  },[selectedId])
  const other=selected?.participants?.data.find(p=>p.id!==ownId)
  const visible=threads.filter(t=>(t.participants?.data||[]).some(p=>p.id!==ownId&&(p.username||p.id).toLowerCase().includes(query.toLowerCase())))
  async function send(e:FormEvent){
    e.preventDefault()
    if(!ownId||!other||!text.trim()||busy||!selectedId)return
    setBusy(true);setNotice('')
    try{
      await api.sendMessage(other.id,text.trim())
      setMessages(current=>[...current,{id:crypto.randomUUID(),created_time:new Date().toISOString(),message:text.trim(),from:{id:ownId,username:'You'}}])
      setText('')
    }catch(e){setNotice(e instanceof Error?e.message:'Message could not be confirmed. Check Instagram before retrying.')}
    finally{setBusy(false)}
  }
  return <>
    <section className="page-heading"><p className="eyebrow">Engagement</p><h1>Inbox</h1><p>Read conversations and reply to customers. New activity refreshes every 15 seconds.</p></section>
    {notice&&<p className="notice wide" role="status">{notice}</p>}
    <div className="inbox-layout card"><section className="thread-list">
      <div className="inbox-search"><input aria-label="Search conversations" placeholder="Search conversations" value={query} onChange={e=>setQuery(e.target.value)}/></div>
      {!visible.length&&<p className="empty">{query?'No matching conversations.':'No conversations yet. Send a test DM from another account, then allow the inbox to refresh.'}</p>}
      {visible.map(t=>{const person=t.participants?.data.find(p=>p.id!==ownId);return <button disabled={busy} key={t.id} className={selectedId===t.id?'thread active':'thread'} onClick={()=>setSelected(t)}><span className="avatar">{person?.username?.[0]?.toUpperCase()||'I'}</span><span><b>@{person?.username||'Instagram user'}</b><small>{t.messages?.data[0]?.message||'Open conversation'}</small></span></button>})}
    </section><section className="message-panel">
      {selected?<><div className="message-head"><b>@{other?.username||'Instagram user'}</b><span>Instagram Direct</span></div><div className="message-stream">{messages.map(message=><div className={message.from?.id===ownId?'bubble mine':'bubble'} key={message.id}><p>{message.message||'Media or attachment'}</p><small>{new Date(message.created_time).toLocaleString()}</small></div>)}</div><form className="message-compose" onSubmit={send}><input aria-label="Reply message" maxLength={1000} disabled={busy} value={text} onChange={e=>setText(e.target.value)} placeholder="Write a reply…"/><button className="button primary" disabled={busy||!ownId||!other||!text.trim()}>{busy?'Sending…':'Send'}</button></form></>:<div className="empty"><h3>Select a conversation</h3><p>New incoming DMs will appear here when Instagram has granted messaging access.</p></div>}
    </section></div>
  </>
}
