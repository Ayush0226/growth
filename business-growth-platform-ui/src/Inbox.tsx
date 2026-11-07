import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { api, getCached } from './lib/api'
import type { Conversation, DirectMessage, InstagramConnection, InstagramPage } from './lib/api'

function merged<T extends { id: string }>(older: T[], newer: T[]) {
  return [...new Map([...older, ...newer].map(item => [item.id, item])).values()]
}
const when = (value: string) => new Date(value).toLocaleString(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit' })
const link = (value?: string) => { try { const url = new URL(value || ''); return ['https:', 'http:'].includes(url.protocol) ? url.href : undefined } catch { return undefined } }
function MessageContent({ message }: { message: DirectMessage }) {
  const attachments = message.attachments?.data || []
  const shares = message.shares?.data || []
  return <>
    {message.message && <p>{message.message}</p>}
    {attachments.map((item, index) => {
      const url = link(item.image_data?.url || item.image_data?.preview_url || item.video_data?.url || item.file_url || item.payload?.url)
      if (!url) return <p className="attachment-note" key={item.id || index}>Attachment preview unavailable</p>
      return <div className="message-attachment" key={item.id || index}>
        {item.image_data || item.mime_type?.startsWith('image/') ? <a href={url} target="_blank" rel="noreferrer"><img src={url} alt={item.name || 'Image attachment'} loading="lazy" /></a>
          : item.video_data || item.mime_type?.startsWith('video/') ? <video src={url} controls preload="none" />
            : item.mime_type?.startsWith('audio/') ? <audio src={url} controls preload="none" />
              : <a href={url} target="_blank" rel="noreferrer">{item.name || 'Open attachment'} ↗</a>}
      </div>
    })}
    {shares.map((share, index) => link(share.link) ? <a className="shared-link" key={index} href={link(share.link)} target="_blank" rel="noreferrer">{share.name || 'Open shared post'} ↗</a> : <p key={index}>Shared post preview unavailable</p>)}
    {!message.message && !attachments.length && !shares.length && <p className="attachment-note">Instagram did not provide this message’s content. <a href="https://www.instagram.com/direct/inbox/" target="_blank" rel="noreferrer">View in Instagram ↗</a></p>}
  </>
}

export default function Inbox() {
  const initialThreads = getCached<InstagramPage<Conversation>>('/api/instagram/conversations')
  const [ownId, setOwnId] = useState(getCached<InstagramConnection>('/api/integrations/instagram')?.provider_account_id || '')
  const [threads, setThreads] = useState<Conversation[]>(initialThreads?.data || [])
  const [selected, setSelected] = useState<Conversation | null>(initialThreads?.data[0] || null)
  const [messages, setMessages] = useState<DirectMessage[]>([])
  const [text, setText] = useState('')
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(!initialThreads)
  const [loadingMessages, setLoadingMessages] = useState(false)
  const [loadingOlder, setLoadingOlder] = useState(false)
  const [threadCursor, setThreadCursor] = useState<string>()
  const [olderCursor, setOlderCursor] = useState<string>()
  const [loadingThreads, setLoadingThreads] = useState(false)
  const [notice, setNotice] = useState('')
  const stream = useRef<HTMLDivElement>(null)
  const stickToBottom = useRef(true)
  const olderAnchor = useRef<{ height: number; top: number } | null>(null)
  const selection = useRef<string | undefined>(selected?.id)
  selection.current = selected?.id
  useEffect(() => {
    let active = true
    const load = async (refresh = false) => {
      try {
        const result = await api.conversations(undefined, refresh)
        if (!active) return
        setThreads(current => {
          const next = merged(result.data, current).map(item => result.data.find(fresh => fresh.id === item.id) || item)
          return next.sort((a, b) => Date.parse(b.updated_time) - Date.parse(a.updated_time))
        })
        setSelected(current => result.data.find(item => item.id === current?.id) || current || result.data[0] || null)
        if (!refresh) setThreadCursor(result.paging?.has_more ? result.paging.cursors?.after : undefined)
      } catch (error) { if (active) setNotice(error instanceof Error ? error.message : 'Could not load conversations.') }
      finally { if (active) setLoading(false) }
    }
    void api.instagramStatus().then(result => { if (active) setOwnId(result.provider_account_id || '') }).catch(error => { if (active) setNotice(error.message) })
    void load()
    const timer = setInterval(() => { if (document.visibilityState === 'visible') void load(true) }, 15000)
    return () => { active = false; clearInterval(timer) }
  }, [])
  const selectedId = selected?.id
  useEffect(() => {
    let active = true
    setText(''); setOlderCursor(undefined); stickToBottom.current = true; olderAnchor.current = null
    const previous = selectedId ? getCached<InstagramPage<DirectMessage>>(`/api/instagram/conversations/${selectedId}/messages`) : undefined
    setMessages(previous ? [...previous.data].sort((a, b) => Date.parse(a.created_time) - Date.parse(b.created_time)) : [])
    if (!selectedId) return
    setLoadingMessages(!previous)
    const load = async (refresh = false) => {
      try {
        const result = await api.messages(selectedId, undefined, refresh)
        if (!active) return
        setMessages(current => merged(current, result.data).sort((a, b) => Date.parse(a.created_time) - Date.parse(b.created_time)))
        if (!refresh) setOlderCursor(result.paging?.has_more ? result.paging.cursors?.after : undefined)
      } catch (error) { if (active) setNotice(error instanceof Error ? error.message : 'Could not load messages.') }
      finally { if (active) setLoadingMessages(false) }
    }
    void load()
    const timer = setInterval(() => { if (document.visibilityState === 'visible') void load(true) }, 15000)
    return () => { active = false; clearInterval(timer) }
  }, [selectedId])
  useLayoutEffect(() => {
    const element = stream.current
    if (!element) return
    if (olderAnchor.current) {
      element.scrollTop = olderAnchor.current.top + element.scrollHeight - olderAnchor.current.height
      olderAnchor.current = null
    } else if (stickToBottom.current) element.scrollTop = element.scrollHeight
  }, [messages])
  async function older() {
    if (!selectedId || !olderCursor || loadingOlder) return
    const id = selectedId; setLoadingOlder(true)
    try {
      const result = await api.messages(id, olderCursor)
      if (selection.current !== id) return
      if (stream.current) olderAnchor.current = { height: stream.current.scrollHeight, top: stream.current.scrollTop }
      stickToBottom.current = false
      setMessages(current => merged(result.data, current).sort((a, b) => Date.parse(a.created_time) - Date.parse(b.created_time)))
      setOlderCursor(result.paging?.has_more ? result.paging.cursors?.after : undefined)
    } catch (error) { setNotice(error instanceof Error ? error.message : 'Could not load older messages.') }
    finally { setLoadingOlder(false) }
  }
  async function moreThreads() {
    if (!threadCursor || loadingThreads) return
    setLoadingThreads(true)
    try { const result = await api.conversations(threadCursor); setThreads(current => merged(current, result.data)); setThreadCursor(result.paging?.has_more ? result.paging.cursors?.after : undefined) }
    catch (error) { setNotice(error instanceof Error ? error.message : 'Could not load conversations.') }
    finally { setLoadingThreads(false) }
  }
  const other = selected?.participants?.data.find(person => person.id !== ownId)
  const visible = threads.filter(thread => !query || (thread.participants?.data || []).some(person => person.id !== ownId && (person.username || person.id).toLowerCase().includes(query.toLowerCase())))
  async function send(event: FormEvent) {
    event.preventDefault()
    if (!ownId || !other || !text.trim() || busy || !selectedId) return
    const outgoing = text.trim(); setBusy(true); setNotice('')
    try {
      const result = await api.sendMessage(other.id, outgoing)
      stickToBottom.current = true
      setMessages(current => merged(current, [{ id: result.message_id || result.id || crypto.randomUUID(), created_time: new Date().toISOString(), message: outgoing, from: { id: ownId, username: 'You' } }]))
      setText('')
    } catch (error) { setNotice(error instanceof Error ? error.message : 'Check Instagram before retrying this message.') }
    finally { setBusy(false) }
  }
  return <>
    <section className="page-heading compact-heading"><p className="eyebrow">Engagement</p><h1>Messages</h1><p>Your conversations, with available history and attachment previews.</p></section>
    {notice && <p className="notice wide" role="status">{notice}</p>}
    <div className="inbox-layout card"><section className="thread-list" aria-label="Conversations">
      <div className="inbox-search"><input aria-label="Search conversations" placeholder="Search conversations" value={query} onChange={event => setQuery(event.target.value)} /></div>
      {loading && <div className="panel-loading" role="status">Loading conversations…<div className="skeleton-row" /><div className="skeleton-row" /></div>}
      {!loading && !visible.length && <p className="empty">{query ? 'No matching conversations.' : 'No conversations available yet.'}</p>}
      {visible.map(thread => { const person = thread.participants?.data.find(item => item.id !== ownId); return <button disabled={busy} key={thread.id} className={selectedId === thread.id ? 'thread active' : 'thread'} onClick={() => setSelected(thread)}><span className="avatar">{person?.username?.[0]?.toUpperCase() || 'I'}</span><span><b>{person?.username ? `@${person.username}` : 'Instagram user'}</b><small>{thread.messages?.data[0]?.message || 'Open conversation'}</small></span></button> })}
      {threadCursor && <button className="button secondary history-button" disabled={loadingThreads} onClick={() => void moreThreads()}>{loadingThreads ? 'Loading…' : 'More conversations'}</button>}
    </section><section className="message-panel" aria-label="Conversation messages">
      {selected ? <><div className="message-head"><b>{other?.username ? `@${other.username}` : 'Instagram user'}</b><span>Instagram Direct · refreshes while this page is visible</span></div>
        <div className="message-stream" ref={stream} onScroll={() => { const element = stream.current; if (element) stickToBottom.current = element.scrollHeight - element.scrollTop - element.clientHeight < 80 }}>
          {loadingMessages ? <div className="panel-loading" role="status">Loading messages…<div className="skeleton-row" /></div> : <>
            {olderCursor ? <button className="button secondary history-button" disabled={loadingOlder} onClick={() => void older()}>{loadingOlder ? 'Loading older messages…' : 'Load older messages'}</button> : <p className="history-note">Beginning of the history Instagram makes available. Older or expired content may only appear in Instagram.</p>}
            {!messages.length && <p className="empty">No messages available in this conversation.</p>}
            {messages.map(message => <div className={message.from?.id === ownId ? 'bubble mine' : 'bubble'} key={message.id}><MessageContent message={message} /><small>{when(message.created_time)}</small></div>)}
          </>}
        </div><form className="message-compose" onSubmit={send}><input aria-label="Reply message" maxLength={1000} disabled={busy} value={text} onChange={event => setText(event.target.value)} placeholder="Write a reply…" /><button className="button primary" disabled={busy || !ownId || !other || !text.trim()}>{busy ? 'Sending…' : 'Send'}</button></form>
      </> : <div className="empty"><h3>Select a conversation</h3><p>Choose a customer to see their messages.</p></div>}
    </section></div>
  </>
}
