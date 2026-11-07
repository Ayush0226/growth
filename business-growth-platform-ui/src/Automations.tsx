import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api } from './lib/api'
import type { AutomationActivity, AutomationInput, AutomationRule, InstagramMedia } from './lib/api'
import Modal from './Modal'

const blank: AutomationInput = {name:'',trigger:'welcome',keywords:[],media_ids:[],reply_text:'',enabled:false,daily_limit:20,cooldown_minutes:60}
const labels = {welcome:'Welcome after the first incoming DM',dm_keyword:'Reply to a DM keyword',comment_keyword:'Comment keyword to private DM'}

export default function Automations() {
  const [rules,setRules]=useState<AutomationRule[]>([])
  const [draft,setDraft]=useState<AutomationInput>({...blank})
  const [editing,setEditing]=useState<string>()
  const [words,setWords]=useState('')
  const [media,setMedia]=useState<InstagramMedia[]>([])
  const [activity,setActivity]=useState<AutomationActivity>({events:[],deliveries:[]})
  const [notice,setNotice]=useState('')
  const [busy,setBusy]=useState(false)
  const [example,setExample]=useState('')
  const [preview,setPreview]=useState('')
  const [mediaError,setMediaError]=useState('')
  const [review,setReview]=useState<AutomationRule>()
  const [activityTab,setActivityTab]=useState<'events'|'deliveries'>('events')
  const [activityPage,setActivityPage]=useState(0)
  const load = async () => {
    try { const [r,a] = await Promise.all([api.automationRules(),api.automationActivity()]);setRules(r.items);setActivity(a) }
    catch(e){setNotice(e instanceof Error?e.message:'Could not load automations')}
  }
  useEffect(()=>{void load();api.media().then(r=>setMedia(r.data)).catch(e=>setMediaError(e.message));const timer=setInterval(()=>{if(document.visibilityState==='visible')void load()},15000);return()=>clearInterval(timer)},[])
  function edit(rule:AutomationRule){setEditing(rule.id);setDraft({...rule,enabled:false});setWords(rule.keywords.join(', '));setNotice('Saving changes pauses this rule. Review the updated text before enabling it again.');setPreview('')}
  function reset(){setDraft({...blank});setWords('');setEditing(undefined);setPreview('')}
  async function save(e:FormEvent){e.preventDefault();setBusy(true);try{await api.saveAutomationRule({...draft,keywords:words.split(',').map(x=>x.trim()).filter(Boolean),enabled:false},editing);reset();setNotice('Rule saved and paused. Enable it when you are ready.');await load()}catch(e){setNotice(e instanceof Error?e.message:'Could not save rule')}finally{setBusy(false)}}
  async function toggle(rule:AutomationRule){
    setBusy(true);try{await api.saveAutomationRule({...rule,enabled:!rule.enabled},rule.id);setReview(undefined);setNotice(rule.enabled?'Rule paused.':'Rule enabled.');await load()}catch(e){setNotice(e instanceof Error?e.message:'Could not update rule')}finally{setBusy(false)}
  }
  async function test(){try{const r=await api.previewAutomation(example,words.split(',').map(x=>x.trim()));setPreview(r.matched?'Keyword matched. No message was sent.':'No keyword matched. No message was sent.')}catch(e){setPreview(e instanceof Error?e.message:'Preview unavailable')}}
  const activityCount=activity[activityTab].length
  const page=Math.min(activityPage,Math.max(0,Math.ceil(activityCount/8)-1))
  return <>
    <section className="page-heading"><p className="eyebrow">Engagement / Automations</p><h1>Helpful replies, under your control.</h1><p>Welcome customers after their first DM, answer keywords, or send a private reply to a comment on a selected post.</p><Link to="/settings/connections">Check your Instagram connection →</Link></section>
    {notice&&<p className="notice wide" role="status">{notice}</p>}
    <div className="automation-layout">
      <article className="card"><h2>{editing?'Edit rule':'Create a rule'}</h2><form onSubmit={save} className="automation-form">
        <label>Rule name<input value={draft.name} maxLength={80} required onChange={e=>setDraft({...draft,name:e.target.value})}/></label>
        <label>When to reply<select value={draft.trigger} onChange={e=>setDraft({...draft,trigger:e.target.value as AutomationInput['trigger']})}>{Object.entries(labels).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
        {draft.trigger!=='welcome'&&<label>Keywords, separated by commas<input value={words} onChange={e=>setWords(e.target.value)} placeholder="price, menu, details" required/><small>Matches complete words or phrases, regardless of case.</small></label>}
        {draft.trigger==='comment_keyword'&&<fieldset><legend>Only these Instagram posts or Reels</legend>{mediaError&&<p className="notice">{mediaError}</p>}{!media.length&&<p>No posts loaded. Connect Instagram and refresh this page.</p>}{media.map(item=><label className="check-row" key={item.id}><input type="checkbox" checked={draft.media_ids.includes(item.id)} onChange={e=>setDraft({...draft,media_ids:e.target.checked?[...draft.media_ids,item.id]:draft.media_ids.filter(id=>id!==item.id)})}/><span>{item.caption?.slice(0,90)||item.id}</span></label>)}</fieldset>}
        <label>Exact reply to send<textarea value={draft.reply_text} onChange={e=>setDraft({...draft,reply_text:e.target.value})} maxLength={1000} rows={5} required/><small>{draft.reply_text.length}/1000 characters. Plain text and links are supported.</small></label>
        <div className="grid"><label>Daily reply limit<input type="number" min={1} max={100} required value={draft.daily_limit} onChange={e=>setDraft({...draft,daily_limit:Number(e.target.value)})}/></label><label>Recipient cooldown (minutes)<input type="number" min={1} max={1440} required value={draft.cooldown_minutes} onChange={e=>setDraft({...draft,cooldown_minutes:Number(e.target.value)})}/></label></div>
        <p className="muted-text">Rules start paused. A welcome is sent only after the first incoming text DM observed by Growthboard. DM replies use the standard 24-hour window; comment private replies are limited to the supported comment window. Only the first matching keyword rule replies.</p>
        <div className="actions"><button className="button primary" disabled={busy}>Save paused rule</button>{editing&&<button className="button secondary" type="button" onClick={reset}>Cancel edit</button>}</div>
      </form>
      {draft.trigger!=='welcome'&&<div className="rule-preview"><h3>Try a keyword</h3><input value={example} onChange={e=>setExample(e.target.value)} placeholder="Example customer message"/><button className="button secondary" type="button" onClick={test}>Check match</button>{preview&&<p role="status">{preview}</p>}</div>}
      </article>
      <section><article className="card"><h2>Your rules</h2>{rules.length===0&&<p>Create your first rule. Nothing will send until you enable it.</p>}{rules.map(rule=><div className="automation-rule" key={rule.id}><span className={`status-pill ${rule.enabled?'published':'cancelled'}`}>{rule.enabled?'Enabled':'Paused'}</span><h3>{rule.name}</h3><p>{labels[rule.trigger]}</p><blockquote>{rule.reply_text}</blockquote><small>{rule.keywords.join(', ')} · {rule.daily_limit}/day · {rule.cooldown_minutes} min cooldown</small><div className="actions"><button className="button secondary" disabled={busy} onClick={()=>edit(rule)}>Edit</button><button className={`button ${rule.enabled?'danger':'primary'}`} disabled={busy} onClick={()=>{setNotice('');if(rule.enabled)void toggle(rule);else setReview(rule)}}>{rule.enabled?'Pause':'Enable rule'}</button></div></div>)}</article>
      </section>
    </div>
    <article className="card automation-activity">
      <div className="section-title"><div><p className="eyebrow">Delivery log</p><h2>Recent activity</h2></div><button className="button secondary compact" onClick={()=>void load()}>Refresh</button></div>
      <div className="segmented" aria-label="Activity type">{(['events','deliveries'] as const).map(tab=><button key={tab} aria-pressed={activityTab===tab} onClick={()=>{setActivityTab(tab);setActivityPage(0)}}>{tab==='events'?'Incoming events':'Reply deliveries'} <small>{activity[tab].length}</small></button>)}</div>
      {!activityCount&&<p className="empty">{activityTab==='events'?'New messages and comments will appear here.':'Your sent replies will appear here.'}</p>}
      <div className="activity-entries">{activityTab==='events'?activity.events.slice(page*8,page*8+8).map(event=><div className="automation-event" key={event.id}><span className={`status-pill ${event.status}`}>{event.status==='pending'?'Queued':event.status}</span><div><b>{event.kind==='dm'?'Incoming DM':'Comment'}</b><p>{event.detail||(event.status==='pending'?'Waiting for the reply worker.':'Checking delivery…')}</p><small>{new Date(event.received_at).toLocaleString()}</small></div></div>):activity.deliveries.slice(page*8,page*8+8).map(item=><div className="automation-event" key={item.id}><span className={`status-pill ${item.status}`}>{item.status}</span><div><b>{item.rule_id?'Automation reply':'AI reply'}</b><p>{item.reply_text}</p>{item.detail&&<p>{item.detail}</p>}<small>{new Date(item.created_at).toLocaleString()}</small></div></div>)}</div>
      {activityCount>8&&<div className="pagination"><button className="button secondary compact" disabled={page===0} onClick={()=>setActivityPage(page-1)}>Previous</button><span>{page*8+1}–{Math.min(page*8+8,activityCount)} of {activityCount} recent entries</span><button className="button secondary compact" disabled={(page+1)*8>=activityCount} onClick={()=>setActivityPage(page+1)}>Next</button></div>}
    </article>
    {review&&<Modal title={`Enable ${review.name}?`} busy={busy} onClose={()=>setReview(undefined)}><p>{labels[review.trigger]}</p><dl className="review-details"><div><dt>Keywords</dt><dd>{review.keywords.join(', ')||'First incoming DM'}</dd></div><div><dt>Applies to</dt><dd>{review.media_ids.length?review.media_ids.map(id=>media.find(item=>item.id===id)?.caption?.slice(0,70)||'Selected Instagram post').join('; '):'Incoming DMs'}</dd></div><div><dt>Daily limit</dt><dd>{review.daily_limit} replies · resets at midnight UTC</dd></div><div><dt>Cooldown</dt><dd>{review.cooldown_minutes} minutes per recipient</dd></div></dl><h3>Reply customers will receive</h3><blockquote className="dialog-quote">{review.reply_text}</blockquote><p className="muted-text">Enabling this rule authorizes future automatic replies when this trigger matches.</p>{notice&&<p className="notice" role="status">{notice}</p>}<div className="dialog-actions"><button className="button secondary" disabled={busy} onClick={()=>setReview(undefined)}>Keep paused</button><button className="button primary" disabled={busy} onClick={()=>void toggle(review)}>{busy?'Enabling…':'Enable automatic replies'}</button></div></Modal>}

  </>
}
