import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api, getCached } from './lib/api'
import type { InstagramComment, InstagramMedia, InstagramPage } from './lib/api'
import Modal from './Modal'

const author = (comment: InstagramComment) => comment.username || comment.from?.username
const label = (comment: InstagramComment) => author(comment) ? `@${author(comment)}` : 'Instagram user'
const date = (value: string) => new Date(value).toLocaleString(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit' })
function merge<T extends { id: string }>(first: T[], second: T[]) { return [...new Map([...first, ...second].map(item => [item.id, item])).values()] }
export default function Comments() {
  const initial = getCached<InstagramPage<InstagramMedia>>('/api/instagram/media')
  const [media, setMedia] = useState<InstagramMedia[]>(initial?.data || [])
  const [selected, setSelected] = useState<InstagramMedia | null>(initial?.data[0] || null)
  const [comments, setComments] = useState<InstagramComment[]>([])
  const [message, setMessage] = useState('')
  const [loadingMedia, setLoadingMedia] = useState(!initial)
  const [loadingComments, setLoadingComments] = useState(false)
  const [cursor, setCursor] = useState<string>()
  const [mediaCursor, setMediaCursor] = useState<string>()
  const [moreBusy, setMoreBusy] = useState(false)
  const [action, setAction] = useState<{ kind: 'reply' | 'delete'; comment: InstagramComment }>()
  const [replyText, setReplyText] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let active = true
    api.media().then(result => { if (active) { setMedia(result.data); setSelected(current => current || result.data[0] || null); setMediaCursor(result.paging?.has_more ? result.paging.cursors?.after : undefined) } }).catch(error => { if (active) setMessage(error.message) }).finally(() => { if (active) setLoadingMedia(false) })
    return () => { active = false }
  }, [])
  const selectedId = selected?.id
  useEffect(() => {
    let active = true
    const previous = selectedId ? getCached<InstagramPage<InstagramComment>>(`/api/instagram/media/${selectedId}/comments`) : undefined
    setComments(previous?.data || []); setCursor(undefined)
    if (!selectedId) return
    setLoadingComments(!previous)
    const load = async (refresh = false) => {
      try {
        const result = await api.comments(selectedId, undefined, refresh)
        if (active) { setComments(current => refresh ? merge(result.data, current).map(item => result.data.find(fresh => fresh.id === item.id) || item) : result.data); if (!refresh) setCursor(result.paging?.has_more ? result.paging.cursors?.after : undefined) }
      } catch (error) { if (active) setMessage(error instanceof Error ? error.message : 'Could not load comments.') }
      finally { if (active) setLoadingComments(false) }
    }
    void load()
    const timer = setInterval(() => { if (document.visibilityState === 'visible') void load(true) }, 15000)
    return () => { active = false; clearInterval(timer) }
  }, [selectedId])
  async function refresh() {
    if (!selectedId || busy) return
    setLoadingComments(true)
    try { const result = await api.comments(selectedId, undefined, true); setComments(result.data); setCursor(result.paging?.has_more ? result.paging.cursors?.after : undefined) }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Could not refresh comments.') }
    finally { setLoadingComments(false) }
  }
  async function morePosts() {
    if (!mediaCursor || moreBusy) return
    setMoreBusy(true)
    try { const result = await api.media(mediaCursor); setMedia(current => merge(current, result.data)); setMediaCursor(result.paging?.has_more ? result.paging.cursors?.after : undefined) }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Could not load posts.') }
    finally { setMoreBusy(false) }
  }
  async function moreComments() {
    if (!selectedId || !cursor || moreBusy) return
    setMoreBusy(true)
    try { const result = await api.comments(selectedId, cursor); setComments(current => merge(current, result.data)); setCursor(result.paging?.has_more ? result.paging.cursors?.after : undefined) }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Could not load more comments.') }
    finally { setMoreBusy(false) }
  }
  async function hide(comment: InstagramComment) {
    setBusy(true)
    try { await api.hideComment(comment.id, !comment.hidden); setComments(current => current.map(item => item.id === comment.id ? { ...item, hidden: !item.hidden } : item)); setMessage(comment.hidden ? 'Comment is visible again.' : 'Comment hidden.') }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Could not update the comment.') }
    finally { setBusy(false) }
  }
  async function confirmAction(event?: FormEvent) {
    event?.preventDefault()
    if (!action || busy || (action.kind === 'reply' && !replyText.trim())) return
    setBusy(true)
    try {
      if (action.kind === 'reply') { await api.replyComment(action.comment.id, replyText.trim()); setAction(undefined); setReplyText(''); setMessage('Your reply was posted.'); if (selectedId) { try { setComments((await api.comments(selectedId, undefined, true)).data) } catch { setMessage('Your reply was posted. Refresh the comments to see it.') } } }
      else { await api.deleteComment(action.comment.id); setComments(current => current.filter(item => item.id !== action.comment.id)); setMessage('Comment deleted.') }
      setAction(undefined); setReplyText('')
    } catch (error) { setMessage(error instanceof Error ? error.message : 'This action could not be confirmed.') }
    finally { setBusy(false) }
  }
  return <>
    <section className="page-heading compact-heading"><p className="eyebrow">Community</p><h1>Comments</h1><p>Choose a post, read the conversation and reply in one place.</p></section>
    {message && <p className="notice wide" role="status">{message}</p>}
    <div className="engagement-layout">
      <section className="media-rail card"><div className="section-title"><h2>Published posts</h2><span>{media.length}</span></div>
        {loadingMedia && <div className="panel-loading" role="status">Loading posts…<div className="skeleton-row" /></div>}
        {!loadingMedia && !media.length && <p className="empty">Your published posts will appear here.</p>}
        <div className="media-list">{media.map(item => <button className={selectedId === item.id ? 'media-row active' : 'media-row'} onClick={() => setSelected(item)} disabled={busy} key={item.id}>{item.thumbnail_url || item.media_url ? <img src={item.thumbnail_url || item.media_url} alt="" loading="lazy" /> : <span className="media-placeholder">IG</span>}<span><b>{item.caption || 'Untitled post'}</b><small>{item.comments_count || 0} comments</small></span></button>)}</div>
        {mediaCursor && <button className="button secondary history-button" disabled={moreBusy} onClick={() => void morePosts()}>{moreBusy ? 'Loading…' : 'More posts'}</button>}
      </section>
      <section className="comment-panel card"><div className="section-title"><div><h2>Conversation</h2><small>{selected ? `${comments.length} comments loaded` : 'Choose a post'}</small></div><button className="button secondary compact" disabled={!selected || busy || loadingComments} onClick={() => void refresh()}>Refresh</button></div>
        <div className="comment-stream">{loadingComments && !comments.length ? <div className="panel-loading" role="status">Loading comments…<div className="skeleton-row" /><div className="skeleton-row" /></div> : !comments.length ? <div className="empty"><h3>No comments here yet</h3><p>Choose another post or refresh after a new comment.</p></div> : comments.map(comment => <article className={comment.hidden ? 'comment hidden' : 'comment'} key={comment.id}><div className="avatar">{author(comment)?.[0]?.toUpperCase() || 'I'}</div><div className="comment-content"><b>{label(comment)}</b><small>{date(comment.timestamp)}{comment.hidden ? ' · Hidden' : ''}</small><p>{comment.text}</p>{comment.replies?.data?.map(reply => <div className="reply" key={reply.id}><b>{label(reply)}</b><p>{reply.text}</p></div>)}<div className="row-actions"><button disabled={busy} onClick={() => { setAction({ kind: 'reply', comment }); setReplyText('') }}>Reply</button><button disabled={busy} onClick={() => void hide(comment)}>{comment.hidden ? 'Unhide' : 'Hide'}</button><button disabled={busy} className="danger-link" onClick={() => setAction({ kind: 'delete', comment })}>Delete</button></div></div></article>)}</div>
        {cursor && <button className="button secondary history-button" disabled={moreBusy} onClick={() => void moreComments()}>{moreBusy ? 'Loading…' : 'Load more comments'}</button>}
      </section>
    </div>
    {action && <Modal title={action.kind === 'reply' ? `Reply to ${label(action.comment)}` : 'Delete comment?'} busy={busy} onClose={() => setAction(undefined)}><blockquote className="dialog-quote">{action.comment.text}</blockquote>{action.kind === 'reply' ? <form onSubmit={confirmAction}><label>Your public reply<textarea autoFocus value={replyText} rows={5} maxLength={1000} onChange={event => setReplyText(event.target.value)} disabled={busy} required /></label><p className="muted-text">This reply will appear publicly below the comment.</p><div className="dialog-actions"><button type="button" className="button secondary" disabled={busy} onClick={() => setAction(undefined)}>Cancel</button><button className="button primary" disabled={busy || !replyText.trim()}>{busy ? 'Posting…' : 'Post reply'}</button></div></form> : <><p>This permanently removes the selected comment from Instagram.</p><div className="dialog-actions"><button className="button secondary" disabled={busy} onClick={() => setAction(undefined)}>Keep comment</button><button className="button danger" disabled={busy} onClick={() => void confirmAction()}>{busy ? 'Deleting…' : 'Delete comment'}</button></div></>}{message && <p role="status" className="notice">{message}</p>}</Modal>}
  </>
}
