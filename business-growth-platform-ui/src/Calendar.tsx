import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, type CalendarDay, type CalendarKind, type CalendarRecord, type CalendarSummary, type Insights } from './lib/api'
import Modal from './Modal'

type Tab = 'posts' | 'automation' | 'ai' | 'insights'
function dayKey(date: Date) { return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}` }
function parseDay(value: string) { const date = new Date(`${value}T12:00:00`); return Number.isNaN(date.getTime()) || dayKey(date) !== value ? new Date() : date }
function localTime(value: string) { const d = new Date(value); return `${dayKey(d)}T${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}` }
const labels: Record<CalendarKind, string> = { posts: 'Planned posts', published: 'Published posts', automation: 'Incoming events', deliveries: 'Reply deliveries', ai: 'AI runs' }

export default function CalendarPage() {
  const [params, setParams] = useSearchParams()
  const initial = parseDay(params.get('date') || dayKey(new Date()))
  const [month, setMonth] = useState(() => new Date(initial.getFullYear(), initial.getMonth(), 1))
  const [selected, setSelected] = useState(() => dayKey(initial))
  const [tab, setTab] = useState<Tab>('posts')
  const [kind, setKind] = useState<CalendarKind>('posts')
  const [summary, setSummary] = useState<CalendarSummary>()
  const [summaryError, setSummaryError] = useState('')
  const [detail, setDetail] = useState<CalendarDay>()
  const [metrics, setMetrics] = useState<Insights>()
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [revision, setRevision] = useState(0)
  const [loading, setLoading] = useState(false)
  const [more, setMore] = useState(false)
  const [editing, setEditing] = useState<CalendarRecord>()
  const [cancelling, setCancelling] = useState<CalendarRecord>()
  const [retrying, setRetrying] = useState<CalendarRecord>()
  const [caption, setCaption] = useState('')
  const [when, setWhen] = useState('')
  const [busy, setBusy] = useState(false)
  const requestVersion = useRef(0)
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  const today = dayKey(new Date())
  const first = new Date(month.getFullYear(), month.getMonth(), 1)
  const start = new Date(first); start.setDate(1 - ((first.getDay() + 6) % 7))
  const end = new Date(start); end.setDate(start.getDate() + 42)
  const startKey = dayKey(start); const endKey = dayKey(end)
  const title = month.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
  const selectedTitle = parseDay(selected).toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
  const counts = summary?.days[selected]

  useEffect(() => {
    let active = true
    setSummary(undefined); setSummaryError('')
    api.calendarSummary(startKey, endKey, timezone, revision > 0).then(result => { if (active) setSummary(result) }).catch(e => { if (active) setSummaryError(e.message) })
    return () => { active = false }
  }, [startKey, endKey, timezone, revision])
  useEffect(() => {
    const version = ++requestVersion.current
    setLoading(true); setDetail(undefined); setMetrics(undefined); setError(''); setMore(false)
    const task = tab === 'insights' ? api.dailyInsights(selected, timezone, revision > 0) : api.calendarDay(selected, kind, timezone)
    task.then(result => {
      if (version !== requestVersion.current) return
      if ('items' in result) setDetail(result); else setMetrics(result)
    }).catch(e => { if (version === requestVersion.current) setError(e.message) }).finally(() => { if (version === requestVersion.current) setLoading(false) })
    return () => { requestVersion.current = version + 1 }
  }, [selected, kind, tab, timezone, revision])

  function select(date: Date) { const key = dayKey(date); setSelected(key); setMonth(new Date(date.getFullYear(), date.getMonth(), 1)); setParams({ date: key }, { replace: true }) }
  function switchTab(next: Tab) { setTab(next); setKind(next === 'posts' ? 'posts' : next === 'automation' ? 'automation' : 'ai') }
  async function loadMore() {
    if (!detail || more) return
    const version = requestVersion.current
    setMore(true)
    try {
      const next = await api.calendarDay(selected, kind, timezone, detail.next_offset)
      if (version === requestVersion.current) setDetail(current => current ? { ...next, items: [...current.items, ...next.items.filter(x => !current.items.some(y => y.id === x.id))] } : next)
    } catch (e) { if (version === requestVersion.current) setError(e instanceof Error ? e.message : 'Could not load more activity.') }
    finally { if (version === requestVersion.current) setMore(false) }
  }
  function refresh() { setRevision(value => value + 1) }
  async function saveEdit(event: React.FormEvent) {
    event.preventDefault(); if (!editing || busy) return
    setBusy(true); setNotice('')
    try {
      if (!when || new Date(when) <= new Date()) throw new Error('Choose a future date and time.')
      await api.updateCalendarItem(editing.id, { caption, scheduled_for: new Date(when).toISOString() })
      setEditing(undefined); setNotice('Post updated.'); refresh()
    } catch (e) { setNotice(e instanceof Error ? e.message : 'Could not update post.') }
    finally { setBusy(false) }
  }
  async function runAction(action: 'cancel' | 'retry') {
    const post = action === 'cancel' ? cancelling : retrying
    if (!post || busy) return
    setBusy(true); setNotice('')
    try {
      if (action === 'cancel') await api.cancelCalendarItem(post.id); else await api.publishJob(post.id)
      setCancelling(undefined); setRetrying(undefined)
      setNotice(action === 'cancel' ? 'Post cancelled.' : 'Publishing request completed. Review the updated result.'); refresh()
    } catch (e) { setNotice(e instanceof Error ? e.message : 'Action failed. Check activity before trying again.') }
    finally { setBusy(false) }
  }
  const metricValue = (name: string) => { const metric = metrics?.metrics.find(x => x.name === name); return metric?.total_value?.value ?? metric?.values?.at(-1)?.value ?? '—' }

  return <>
    <section className="page-heading split"><div><p className="eyebrow">Your business calendar</p><h1>Every day, in one place.</h1><p>Choose a date to review posts, automated replies, business AI and Instagram performance.</p></div><Link className="button primary" to={`/composer?date=${selected}`}>＋ Plan a post</Link></section>
    <section className="card activity-calendar" aria-label="Business calendar">
      <div className="calendar-toolbar"><div className="calendar-month-controls"><button className="button secondary compact" aria-label="Previous month" onClick={() => select(new Date(month.getFullYear(), month.getMonth() - 1, 1))}>←</button><h2 aria-live="polite">{title}</h2><button className="button secondary compact" aria-label="Next month" onClick={() => select(new Date(month.getFullYear(), month.getMonth() + 1, 1))}>→</button></div><div className="calendar-tools"><button className="button secondary compact" onClick={() => select(new Date())}>Today</button><label className="calendar-date-jump">Go to date<input type="date" value={selected} onChange={event => { if (event.target.value) select(parseDay(event.target.value)) }} /></label><button className="button secondary compact" disabled={loading} onClick={refresh}>Refresh</button></div></div>
      <p className="calendar-timezone">Dates and activity use {timezone}. Performance is supplied by Instagram and may arrive later.</p>
      {summaryError && <p className="notice" role="alert">Calendar counts could not load: {summaryError}</p>}
      {summary && summary.truncated_categories.length > 0 && <p className="notice">This is a busy month. Overview counts for {summary.truncated_categories.map(x => labels[x]).join(', ')} are partial. Open a date and use Load more for its full recorded activity.</p>}
      <table className="month-grid"><caption className="sr-only">{title}; choose a date for business activity</caption><thead><tr>{['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map(label => <th key={label} scope="col">{label}</th>)}</tr></thead><tbody>{Array.from({ length: 6 }, (_, week) => <tr key={week}>{Array.from({ length: 7 }, (_, weekday) => {
        const date = new Date(start); date.setDate(start.getDate() + week * 7 + weekday)
        const key = dayKey(date); const day = summary?.days[key]
        return <td key={key}><button className={`calendar-date ${date.getMonth() !== month.getMonth() ? 'outside-month' : ''} ${key === selected ? 'selected' : ''} ${key === today ? 'today' : ''}`} aria-pressed={key === selected} aria-current={key === today ? 'date' : undefined} aria-label={`${date.toLocaleDateString(undefined, { dateStyle: 'full' })}${day ? `, ${day.posts} planned posts, ${day.published} published, ${day.automation} incoming events, ${day.deliveries} replies, ${day.ai} AI runs` : ', counts loading'}`} onClick={() => select(date)}><span className="calendar-day-number">{date.getDate()}</span><span className="calendar-date-counts">{day && <>{(day.posts > 0 || day.published > 0) && <span className="day-marker posting"><i />{day.posts} planned · {day.published} published</span>}{day.automation > 0 && <span className="day-marker automation"><i />{day.automation} events</span>}{day.deliveries > 0 && <span className="day-marker replies"><i />{day.deliveries} replies</span>}{day.ai > 0 && <span className="day-marker ai"><i />{day.ai} AI</span>}</>}</span></button></td>
      })}</tr>)}</tbody></table>
      <div className="calendar-legend"><span><i className="posting" />Posting</span><span><i className="automation" />Automations</span><span><i className="ai" />Business AI</span><span>{summary ? 'Recorded workspace activity' : 'Loading day counts…'}</span></div>
    </section>
    <section className="card calendar-details" aria-labelledby="day-details-title" aria-busy={loading}>
      <div className="section-title"><div><p className="eyebrow">Selected day</p><h2 id="day-details-title">{selectedTitle}</h2></div><span>{selected > today ? 'Upcoming' : selected === today ? 'Today' : 'Past activity'}</span></div>
      <div className="calendar-tabs" aria-label="Day activity categories">{(['posts', 'automation', 'ai', 'insights'] as Tab[]).map(value => <button key={value} aria-pressed={tab === value} onClick={() => switchTab(value)}>{value === 'posts' ? 'Posting' : value === 'automation' ? 'Automations' : value === 'ai' ? 'Business AI' : 'Insights'}{counts && value !== 'insights' && <small>{value === 'posts' ? counts.posts : value === 'automation' ? counts.automation : counts.ai}</small>}</button>)}</div>
      {tab === 'posts' && <div className="segmented"><button aria-pressed={kind === 'posts'} onClick={() => setKind('posts')}>Planned for this date</button><button aria-pressed={kind === 'published'} onClick={() => setKind('published')}>Published on this date</button></div>}
      {tab === 'automation' && <div className="segmented"><button aria-pressed={kind === 'automation'} onClick={() => setKind('automation')}>Incoming messages / comments</button><button aria-pressed={kind === 'deliveries'} onClick={() => setKind('deliveries')}>Reply deliveries</button></div>}
      {tab === 'ai' && <p className="muted-text">Recorded generations include practice previews and live attempts. A generated answer does not by itself confirm a sent message; check Reply deliveries for the delivery result.</p>}
      {tab === 'posts' && <p className="muted-text">Planned dates and actual publication dates can differ. Statuses show the latest recorded result.</p>}
      {error && <p className="notice" role="alert">{error}</p>}
      {loading ? <p className="panel-loading" role="status">Loading this day’s activity…</p> : tab === 'insights' ? <>
        {metrics?.metrics_status === 'future' ? <div className="calendar-empty"><h3>Insights will appear after this day.</h3><p>Future performance cannot be reported yet.</p></div> : metrics?.metrics_status !== 'available' ? <div className="calendar-empty"><h3>No Instagram metrics available for this date.</h3><p>Instagram may not provide older or very recent data. Check the insights permission in Connections. Missing data is not shown as zero.</p><Link to="/settings/connections">Check connection →</Link></div> : <><div className="calendar-insights">{[['reach', 'Reach'], ['views', 'Views'], ['profile_views', 'Profile views']].map(([name, label]) => <article key={name}><span>{label}</span><strong>{metricValue(name)}</strong></article>)}</div><p className="muted-text">Requested date: {selected}. Instagram’s reporting periods and availability determine these totals.{metrics.provisional && ' Today’s figures are incomplete and can change.'}</p></>}
      </> : detail && !detail.items.length ? <div className="calendar-empty"><h3>{tab === 'posts' ? 'No posts for this date.' : tab === 'ai' ? 'No AI runs recorded on this date.' : 'No automation activity recorded on this date.'}</h3><p>{selected > today ? 'Automatic replies and AI run when customer activity arrives; they are not scheduled by choosing a date.' : 'Only activity recorded by this workspace is shown.'}</p><Link to={tab === 'posts' ? `/composer?date=${selected}` : tab === 'ai' ? '/assistant' : '/automations'}>{tab === 'posts' ? 'Plan a post' : tab === 'ai' ? 'Open Business AI' : 'Manage automations'} →</Link></div> : <div className="calendar-activity-list">{detail?.items.map(item => <article className="calendar-activity-card" key={item.id}><div><span className={`status-pill ${item.status}`}>{item.status}</span><small>{new Date((kind === 'published' ? item.published_at : item.scheduled_for || item.received_at || item.created_at) || '').toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</small></div>{tab === 'posts' ? <><h3>{item.content_targets?.content_drafts.post_type === 'carousel' ? 'Carousel' : 'Photo post'}</h3><p>{item.content_targets?.content_drafts.caption || 'No caption'}</p>{item.failure_message && <p className="notice">{item.failure_message}</p>}<div className="actions">{['scheduled', 'failed'].includes(item.status) && <><button className="button secondary compact" onClick={() => { setEditing(item); setCaption(item.content_targets?.content_drafts.caption || ''); setWhen(localTime(item.scheduled_for!)); setNotice('') }}>Edit</button><button className="button danger compact" onClick={() => { setCancelling(item); setNotice('') }}>Cancel post</button></>}{item.status === 'failed' && <button className="button secondary compact" onClick={() => { setRetrying(item); setNotice('') }}>Review retry</button>}{item.provider_permalink && <a className="button secondary compact" target="_blank" rel="noreferrer" href={item.provider_permalink}>Open on Instagram ↗</a>}</div></> : tab === 'ai' ? <><h3>{item.purpose === 'preview' ? 'Practice preview' : 'Live AI attempt'}</h3><p>{item.status === 'generated' ? 'An answer was generated.' : item.status === 'failed' ? 'Generation did not complete.' : 'Generation was reserved.'}</p></> : <><h3>{kind === 'deliveries' ? 'Automatic reply' : item.kind === 'dm' ? 'Incoming DM' : 'Comment'}</h3>{item.reply_text && <p className="calendar-reply">{item.reply_text}</p>}{item.detail && <p>{item.detail}</p>}</>}</article>)}</div>}
      {detail?.has_more && <button className="button secondary" disabled={more || loading} onClick={() => void loadMore()}>{more ? 'Loading…' : 'Load more activity'}</button>}
      {notice && !editing && !cancelling && !retrying && <p className="notice" role="status">{notice}</p>}
    </section>
    {editing && <Modal title="Edit scheduled post" onClose={() => setEditing(undefined)} busy={busy}><form onSubmit={saveEdit}><label>Caption<textarea rows={5} maxLength={2200} value={caption} onChange={event => setCaption(event.target.value)} /></label><label>Schedule ({timezone})<input type="datetime-local" value={when} required onChange={event => setWhen(event.target.value)} /></label>{notice && <p className="notice" role="alert">{notice}</p>}<div className="dialog-actions"><button type="button" className="button secondary" disabled={busy} onClick={() => setEditing(undefined)}>Keep current post</button><button className="button primary" disabled={busy}>{busy ? 'Saving…' : 'Save changes'}</button></div></form></Modal>}
    {cancelling && <Modal title="Cancel this post?" busy={busy} onClose={() => setCancelling(undefined)}><p>This cancels the scheduled publication. A post already being sent may need its delivery checked.</p>{notice && <p className="notice" role="alert">{notice}</p>}<div className="dialog-actions"><button className="button secondary" disabled={busy} onClick={() => setCancelling(undefined)}>Keep post</button><button className="button danger" disabled={busy} onClick={() => void runAction('cancel')}>{busy ? 'Cancelling…' : 'Cancel post'}</button></div></Modal>}
    {retrying && <Modal title="Retry this publication?" busy={busy} onClose={() => setRetrying(undefined)}><p>Check your Instagram account first. If this post already appeared, do not retry it.</p><blockquote className="dialog-quote">{retrying.content_targets?.content_drafts.caption || 'No caption'}</blockquote>{notice && <p className="notice" role="alert">{notice}</p>}<div className="dialog-actions"><button className="button secondary" disabled={busy} onClick={() => setRetrying(undefined)}>Go back</button><button className="button primary" disabled={busy} onClick={() => void runAction('retry')}>{busy ? 'Requesting…' : 'Retry publication'}</button></div></Modal>}
  </>
}
