import { useEffect, useState } from 'react'
import { request } from './lib/api'

type Location={name:string;title:string}
type Asset={id:string;width:number;height:number;bytes:number}
type Campaign={id:string;title:string;locations:{id:string;location_name:string;status:string;scheduled_for?:string}[]}
const send=<T,>(path:string,body:unknown)=>request<T>(path,{method:'POST',body:JSON.stringify(body)})
function eventParts(value:string){const [date,time]=value.split('T');const [year,month,day]=date.split('-').map(Number);const [hours,minutes]=time.split(':').map(Number);return {date:{year,month,day},time:{hours,minutes}}}

export default function GoogleCampaigns({locations}:{locations:Location[]}){
 const [campaigns,setCampaigns]=useState<Campaign[]>([]);const [assets,setAssets]=useState<Asset[]>([]);const [title,setTitle]=useState('');const [summary,setSummary]=useState('')
 const [targets,setTargets]=useState<string[]>([]);const [type,setType]=useState('STANDARD');const [start,setStart]=useState('');const [end,setEnd]=useState('');const [eventTitle,setEventTitle]=useState('');const [coupon,setCoupon]=useState('');const [image,setImage]=useState('')
 const [when,setWhen]=useState<Record<string,string>>({});const [busy,setBusy]=useState(false);const [message,setMessage]=useState('')
 async function load(){const [result,media]=await Promise.all([request<{campaigns:Campaign[]}>('/api/platform/campaigns'),request<{assets:Asset[]}>('/api/gbp/media')]);setCampaigns(result.campaigns);setAssets(media.assets)}
 async function run(action:()=>Promise<void>){setBusy(true);setMessage('');try{await action()}catch(e){setMessage(e instanceof Error?e.message:'Could not complete this action.')}finally{setBusy(false)}}
 useEffect(()=>{void run(load)},[])
 return <section>{message&&<p role="status" className="notice">{message}</p>}<form className="card" onSubmit={e=>{e.preventDefault();void run(async()=>{
  const event=type==='STANDARD'?undefined:{title:eventTitle,schedule:{startDate:eventParts(start).date,startTime:eventParts(start).time,endDate:eventParts(end).date,endTime:eventParts(end).time}}
  await send('/api/platform/campaigns',{title,summary,location_ids:targets,topic_type:type,event_details:event,offer_details:type==='OFFER'?{couponCode:coupon}:undefined,media_asset_id:image||null})
  setTitle('');setSummary('');await load();setMessage('Campaign draft saved. Review its targets, then choose a publication time.')
 })}}><h2>One campaign, multiple locations</h2><label>Campaign name<input required maxLength={160} value={title} onChange={e=>setTitle(e.target.value)}/></label><label>Post text<textarea required maxLength={1500} value={summary} onChange={e=>setSummary(e.target.value)}/></label><label>Post type<select value={type} onChange={e=>setType(e.target.value)}><option value="STANDARD">Business update</option><option value="EVENT">Event</option><option value="OFFER">Offer</option></select></label>
 {type!=='STANDARD'&&<div className="google-fields"><label>Event or offer title<input required value={eventTitle} maxLength={58} onChange={e=>setEventTitle(e.target.value)}/></label><label>Starts (business local time)<input type="datetime-local" required value={start} onChange={e=>setStart(e.target.value)}/></label><label>Ends (business local time)<input type="datetime-local" min={start} required value={end} onChange={e=>setEnd(e.target.value)}/></label></div>}
 {type==='OFFER'&&<label>Coupon code<input value={coupon} maxLength={100} onChange={e=>setCoupon(e.target.value)}/></label>}
 <label>Image<select value={image} onChange={e=>setImage(e.target.value)}><option value="">No image</option>{assets.map(asset=><option key={asset.id} value={asset.id}>{asset.width} × {asset.height} · {asset.id.slice(0,8)}</option>)}</select></label>
 <fieldset><legend>Target locations</legend>{locations.map(location=><label key={location.name} className="google-checkbox"><input type="checkbox" checked={targets.includes(location.name)} onChange={e=>setTargets(current=>e.target.checked?[...current,location.name]:current.filter(x=>x!==location.name))}/>{location.title}</label>)}</fieldset><button disabled={busy||!targets.length} className="button primary">Save campaign draft</button></form>
 {campaigns.map(campaign=><article className="card" key={campaign.id}><h3>{campaign.title}</h3><ul>{campaign.locations.map(item=><li key={item.id}>{locations.find(l=>l.name===item.location_name)?.title||item.location_name} · {item.status}{item.scheduled_for&&` · ${new Date(item.scheduled_for).toLocaleString()}`}</li>)}</ul>{campaign.locations.every(item=>item.status==='draft')&&<><label>Publication time (your local time)<input type="datetime-local" value={when[campaign.id]||''} onChange={e=>setWhen({...when,[campaign.id]:e.target.value})}/></label><button disabled={busy||!when[campaign.id]} className="button primary" onClick={()=>void run(async()=>{await send(`/api/platform/campaigns/${campaign.id}/schedule`,{publish_at:new Date(when[campaign.id]).toISOString()});await load();setMessage('Campaign scheduled.')})}>Schedule campaign</button></>}{campaign.locations.every(item=>['draft','scheduled','cancelled'].includes(item.status))&&<button disabled={busy} className="button secondary" onClick={()=>void run(async()=>{await send(`/api/platform/campaigns/${campaign.id}/cancel`,{});await load()})}>Cancel campaign</button>}</article>)}
 </section>
}

export function GoogleMedia(){
 const [assets,setAssets]=useState<Asset[]>([]);const [busy,setBusy]=useState(false);const [message,setMessage]=useState('');const [prompt,setPrompt]=useState('');const [provider,setProvider]=useState(false);const [key,setKey]=useState(()=>crypto.randomUUID())
 async function load(){const result=await request<{assets:Asset[]}>('/api/gbp/media');setAssets(result.assets)}
 async function run(action:()=>Promise<void>){setBusy(true);setMessage('');try{await action();await load()}catch(e){setMessage(e instanceof Error?e.message:'Could not complete this action.')}finally{setBusy(false)}}
 useEffect(()=>{void run(async()=>{const result=await request<{cloudflare_available:boolean}>('/api/images/providers');setProvider(result.cloudflare_available)})},[])
 return <section>{message&&<p className="notice" role="status">{message}</p>}<article className="card"><h2>Google media library</h2><p>Upload a JPEG, PNG or WebP image smaller than 8 MB, at least 250 pixels per side.</p><label>Upload photo<input type="file" accept="image/jpeg,image/png,image/webp" disabled={busy} onChange={e=>{const file=e.target.files?.[0];if(file){void run(async()=>{const body=new FormData();body.append('file',file);await request('/api/gbp/media/upload',{method:'POST',body});setMessage('Photo added to your library.')})}}}/></label></article>
 <form className="card" onSubmit={e=>{e.preventDefault();void run(async()=>{await send('/api/images/generate',{request_id:key,prompt});setMessage('Generated image added to your library.');setKey(crypto.randomUUID())})}}><h2>Image Studio</h2><label>Describe your image<textarea required minLength={5} maxLength={2000} value={prompt} onChange={e=>{setPrompt(e.target.value);setKey(crypto.randomUUID())}}/></label><button disabled={busy||!provider} className="button primary">Generate image</button>{!provider&&<p>The image provider still needs activation.</p>}</form>
 <div className="google-fields">{assets.map(asset=><article className="card" key={asset.id}><b>{asset.width} × {asset.height}</b><p>{Math.round(asset.bytes/1024)} KB · {asset.id.slice(0,8)}</p><small>Available in the campaign image selector.</small></article>)}</div></section>
}
