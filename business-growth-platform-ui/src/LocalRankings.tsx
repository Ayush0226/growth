import { useEffect, useRef, useState } from 'react'
import { request } from './lib/api'
import './local-rankings.css'

type Business = {position:number;business_name:string;rating:number|null;reviews:number|null;address?:string;is_target:boolean}
export type RankReport = {id?:string;keyword:string;status?:string;actual_rank?:number|null;search_area?:string;target_business?:string;checked_at?:string;created_at?:string;results?:Business[];top_10_results?:Business[];latest_attempt_status?:string}
export type RankSetup = {keywords:string[];reports:RankReport[]}
type Props = {locationName:string;providerReady:boolean;loadRequest?:typeof request}
const clean = (words:string[]) => words.map(word=>word.trim().replace(/\s+/g,' ')).filter(Boolean)
const topTen = (report?:RankReport) => (report?.top_10_results || report?.results || []).filter(row=>row.position>=1&&row.position<=10).sort((a,b)=>a.position-b.position).slice(0,10)
function rankLabel(report?:RankReport) {
  if (!report?.results && !report?.top_10_results) return 'Not checked'
  if (report.actual_rank && report.actual_rank<=10) return `#${report.actual_rank}`
  const count=topTen(report).length
  return count===10 || (report.actual_rank||0)>10 ? 'Outside top 10' : `Not found in ${count} results`
}

export default function LocalRankings({locationName,providerReady,loadRequest=request}:Props){
  const [words,setWords]=useState<string[]>(['']);const [reports,setReports]=useState<Record<string,RankReport>>({})
  const [selected,setSelected]=useState('');const [loading,setLoading]=useState(true);const [saving,setSaving]=useState(false)
  const [checking,setChecking]=useState(false);const [message,setMessage]=useState('');const [progress,setProgress]=useState('')
  const [errors,setErrors]=useState<Record<string,string>>({});const [dirty,setDirty]=useState(false)
  const [loadFailed,setLoadFailed]=useState(false);const [loadVersion,setLoadVersion]=useState(0)
  const stopped=useRef(false);const mounted=useRef(true)
  useEffect(()=>{
    mounted.current=true;let active=true;setLoading(true);setLoadFailed(false)
    loadRequest<RankSetup>(`/api/gbp/rank-keywords?${new URLSearchParams({location_name:locationName})}`).then(data=>{
      if(!active)return
      setWords(data.keywords.length?data.keywords:['']);setSelected(data.keywords[0]||'')
      setReports(Object.fromEntries(data.reports.map(report=>[report.keyword,report])))
    }).catch(e=>{if(active){setMessage(e.message);setLoadFailed(true)}}).finally(()=>{if(active)setLoading(false)})
    return()=>{active=false;mounted.current=false;stopped.current=true}
  },[locationName,loadRequest,loadVersion])
  const keywords=clean(words);const busy=loading||saving||checking||loadFailed
  function edit(next:string[]){setWords(next);setDirty(true);setMessage('')}
  function move(index:number,offset:number){const next=[...words];[next[index],next[index+offset]]=[next[index+offset],next[index]];edit(next)}
  async function save(){
    const normalized=clean(words)
    if(new Set(normalized.map(word=>word.toLocaleLowerCase())).size!==normalized.length)throw new Error('Use a different phrase for each keyword.')
    const data=await loadRequest<RankSetup>('/api/gbp/rank-keywords',{method:'PUT',body:JSON.stringify({location_name:locationName,keywords:normalized})})
    if(mounted.current){setWords(data.keywords.length?data.keywords:['']);setDirty(false);setSelected(current=>data.keywords.includes(current)?current:data.keywords[0]||'')}
    return data.keywords
  }
  async function saveOnly(){setSaving(true);setMessage('');try{await save();setMessage('Keywords and priority saved for this location.')}catch(e){setMessage(e instanceof Error?e.message:'Could not save keywords.')}finally{if(mounted.current)setSaving(false)}}
  async function scan(only?:string){
    if(checking||!providerReady)return
    setChecking(true);setMessage('');setErrors({});stopped.current=false
    let completed=0;let failed=0
    try{
      const saved=await save();const queue=only?saved.filter(word=>word===only):saved
      for(let index=0;index<queue.length;index++){
        if(stopped.current)break
        const keyword=queue[index];setProgress(`Checking ${index+1} of ${queue.length} · ${keyword}`)
        try{
          const report=await loadRequest<RankReport>('/api/rank/generate-report',{method:'POST',body:JSON.stringify({location_name:locationName,keyword,request_id:crypto.randomUUID()})})
          completed++
          if(mounted.current){setReports(current=>({...current,[keyword]:report}));setSelected(current=>current||keyword)}
        }catch(e){failed++;if(mounted.current)setErrors(current=>({...current,[keyword]:e instanceof Error?e.message:'This check could not finish.'}))}
      }
      if(mounted.current)setMessage(`${completed} keyword${completed===1?'':'s'} checked${failed?`; ${failed} could not be checked`:''}.${stopped.current?' Remaining checks stopped.':''}`)
    }catch(e){if(mounted.current)setMessage(e instanceof Error?e.message:'Could not start the checks.')}
    finally{if(mounted.current){setChecking(false);setProgress('')}}
  }
  const selectedKeyword=keywords.includes(selected)?selected:keywords[0]||''
  const report=reports[selectedKeyword];const businesses=topTen(report)
  const measured=Boolean(report?.results||report?.top_10_results)
  const checkedAt=report?.checked_at||report?.created_at
  return <section className="local-rankings" aria-label="Local rankings">
    <div className="rank-heading"><div><p className="eyebrow">LOCAL RANKINGS</p><h2>See where you stand.</h2><p>Track up to 10 keywords and see the businesses appearing in local search for each one.</p></div><span className="rank-count">{keywords.length}<small>/ 10 keywords</small></span></div>
    {!providerReady&&<p className="notice" role="status">Live ranking checks are being set up. You can add keywords and save their priority now.</p>}
    {message&&<p className="notice" role="status">{message}</p>}
    {loadFailed&&<button type="button" className="button secondary" onClick={()=>setLoadVersion(value=>value+1)}>Retry loading saved keywords</button>}
    <div className="rank-layout"><article className="card rank-keywords"><div className="section-title"><div><h3>Your keywords</h3><p>Priority 1 is checked first.</p></div><span className="rank-tag">{dirty?'Unsaved changes':'Saved order'}</span></div>
      <ol className="rank-keyword-editor">{words.map((word,index)=><li key={index}><span className="keyword-priority" aria-label={`Priority ${index+1}`}>{index+1}</span><label><span className="visually-hidden">Keyword {index+1}</span><input value={word} disabled={busy} maxLength={120} placeholder={index===0?'e.g. preschool in Dombivli':'Add a search phrase'} onChange={e=>edit(words.map((value,i)=>i===index?e.target.value:value))}/></label><div className="keyword-controls"><button type="button" aria-label={`Move keyword ${index+1} up`} disabled={busy||index===0} onClick={()=>move(index,-1)}>↑</button><button type="button" aria-label={`Move keyword ${index+1} down`} disabled={busy||index===words.length-1} onClick={()=>move(index,1)}>↓</button><button type="button" aria-label={`Remove keyword ${index+1}`} disabled={busy} onClick={()=>edit(words.length===1?['']:words.filter((_,i)=>i!==index))}>×</button></div></li>)}</ol>
      <button type="button" className="rank-add" disabled={busy||words.length>=10} onClick={()=>edit([...words,''])}>＋ Add keyword <span>{words.length}/10</span></button>
      <div className="rank-actions"><button type="button" className="button secondary" disabled={busy} onClick={()=>void saveOnly()}>{saving?'Saving…':'Save keywords'}</button><button type="button" className="button primary" disabled={busy||!keywords.length||!providerReady} onClick={()=>void scan()}>{checking?'Checking…':'Check all keywords'}</button></div>
      <p className="rank-hint">Use ↑ and ↓ to set priority. This controls the check order, not your position on Google.</p>
      {checking&&<div className="rank-progress" role="status"><p>{progress}</p><button type="button" className="text-button" onClick={()=>{stopped.current=true;setProgress('Finishing the current check…')}}>Stop after this keyword</button></div>}
    </article><div className="rank-results-panel"><div className="rank-keyword-switcher" aria-label="Choose a keyword">{keywords.map((keyword,index)=><button type="button" key={keyword+index} aria-pressed={selectedKeyword===keyword} onClick={()=>setSelected(keyword)}><span>Priority {index+1}</span><b>{keyword}</b><small>{rankLabel(reports[keyword])}</small></button>)}</div>
      <article className="card rank-leaderboard"><div className="rank-results-header"><div><p className="eyebrow">{selectedKeyword||'YOUR LOCAL AREA'}</p><h3>Top 10 local businesses</h3></div>{selectedKeyword&&<button type="button" className="button secondary compact" disabled={busy||!providerReady} onClick={()=>void scan(selectedKeyword)}>Check keyword</button>}</div>
        {errors[selectedKeyword]&&<p className="notice" role="alert">{errors[selectedKeyword]}</p>}
        {report?.latest_attempt_status==='failed'&&<p className="notice">The latest check could not finish.{measured?' The last successful result is shown below.':' Try checking this keyword again.'}</p>}
        {measured?<><div className="rank-your-position"><div><span>Your position</span><strong>{rankLabel(report)}</strong><p>{report.target_business}</p></div><div><span>Search area</span><b>{report.search_area}</b>{checkedAt&&<small>Checked {new Date(checkedAt).toLocaleString()}</small>}</div></div>
          <div className="rank-table-scroll"><table className="rank-table"><caption>{businesses.length} measured local results for “{selectedKeyword}”</caption><thead><tr><th scope="col">Rank</th><th scope="col">Business</th><th scope="col">Rating</th><th scope="col">Reviews</th></tr></thead><tbody>{businesses.map((business,index)=><tr key={index} className={business.is_target?'is-yours':''}><td><span className={`rank-number ${business.position<=3?'rank-leading':''}`}>{business.position}</span></td><td><strong>{business.business_name}</strong>{business.is_target&&<span className="rank-you">Your business</span>}{business.address&&<small>{business.address}</small>}</td><td>{business.rating==null?'—':business.rating.toFixed(1)}{business.rating!=null&&<span aria-label="stars"> ★</span>}</td><td>{business.reviews?.toLocaleString()??'—'}</td></tr>)}</tbody></table></div><p className="rank-hint">A snapshot of Google local results for this keyword and area. Positions can vary by search location and time.</p></>:<div className="rank-empty"><span aria-hidden="true">↗</span><h4>{keywords.length?'Your next check starts here.':'Add your first keyword.'}</h4><p>{keywords.length?'Check a keyword to see the local top 10 and your position.':'Choose the searches that matter most to your business, then set their priority.'}</p></div>}
      </article></div></div>
    {loading&&<p role="status">Loading saved keywords…</p>}
  </section>
}
