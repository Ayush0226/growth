import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from './lib/api'
import type { CalendarItem } from './lib/api'
import { preparePhoto, type ImageFit } from './lib/images'

type Mode = 'photo' | 'carousel' | 'batch'
type Photo = { id: string; requestId: string; original: File; file: File; url: string; width: number; height: number; caption: string; job?: CalendarItem }

export default function ComposerPage() {
  const [params] = useSearchParams()
  const [mode, setMode] = useState<Mode>('photo')
  const [photos, setPhotos] = useState<Photo[]>([])
  const [caption, setCaption] = useState('')
  const [scheduled, setScheduled] = useState(() => /^\d{4}-\d{2}-\d{2}$/.test(params.get('date') || '') ? `${params.get('date')}T09:00` : '')
  const [fit, setFit] = useState<ImageFit>('original')
  const [spacing, setSpacing] = useState(0)
  const [approved, setApproved] = useState(false)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [action, setAction] = useState<boolean>()
  const [groupJob, setGroupJob] = useState<CalendarItem>()
  const requestId = useRef(crypto.randomUUID())
  const uploads = useRef(new Map<string, string>())
  const urls = useRef(new Set<string>())
  const locked = busy || submitted
  const done = mode === 'batch' ? photos.length > 0 && photos.every(photo => photo.job) : Boolean(groupJob)
  const total = mode === 'batch' ? photos.length : 1
  const queued = mode === 'batch' ? photos.filter(photo => photo.job).length : groupJob ? 1 : 0
  useEffect(() => {
    const current = urls.current
    return () => current.forEach(url => URL.revokeObjectURL(url))
  }, [])

  function changed() { setApproved(false); requestId.current = crypto.randomUUID(); setNotice('') }
  async function choose(files: FileList | null) {
    if (!files?.length || locked) return
    const available = (mode === 'photo' ? 1 : 10) - (mode === 'photo' ? 0 : photos.length)
    if (files.length > available) { setNotice(`Choose up to ${mode === 'photo' ? 1 : 10} images in this selection.`); return }
    const added: Photo[] = []
    const chosenUrls: string[] = []
    setBusy(true)
    try {
      for (const file of Array.from(files)) {
        const prepared = await preparePhoto(file, fit)
        const url = URL.createObjectURL(prepared.file)
        chosenUrls.push(url)
        urls.current.add(url)
        added.push({ id: crypto.randomUUID(), requestId: crypto.randomUUID(), original: file, ...prepared, url, caption })
      }
      if (mode === 'photo') {
        photos.forEach(photo => { URL.revokeObjectURL(photo.url); urls.current.delete(photo.url) })
        setPhotos(added)
      } else setPhotos(current => [...current, ...added])
      changed()
    } catch (error) {
      chosenUrls.forEach(url => { URL.revokeObjectURL(url); urls.current.delete(url) })
      setNotice(error instanceof Error ? error.message : 'Could not load these images.')
    } finally { setBusy(false) }
  }
  async function changeFit(next: ImageFit) {
    if (locked) return
    if (!photos.length) { setFit(next); changed(); return }
    setBusy(true)
    const replacements: Photo[] = []
    try {
      for (const photo of photos) {
        const prepared = await preparePhoto(photo.original, next)
        const url = URL.createObjectURL(prepared.file)
        replacements.push({ ...photo, ...prepared, url })
      }
      photos.forEach(photo => { URL.revokeObjectURL(photo.url); urls.current.delete(photo.url) })
      replacements.forEach(photo => urls.current.add(photo.url))
      uploads.current.clear(); setPhotos(replacements); setFit(next); changed()
    } catch (error) {
      replacements.forEach(photo => URL.revokeObjectURL(photo.url))
      setNotice(error instanceof Error ? error.message : 'Could not change image fit.')
    } finally { setBusy(false) }
  }
  function remove(id: string) {
    const photo = photos.find(item => item.id === id)
    if (photo) { URL.revokeObjectURL(photo.url); urls.current.delete(photo.url) }
    uploads.current.delete(id); setPhotos(current => current.filter(item => item.id !== id)); changed()
  }
  function move(index: number, by: number) {
    const next = [...photos]; [next[index], next[index + by]] = [next[index + by], next[index]]
    setPhotos(next); changed()
  }
  function startAgain() {
    if (submitted && !done && !window.confirm('Some posts may already be queued. Check Calendar before starting another batch. Start a new batch?')) return
    urls.current.forEach(url => URL.revokeObjectURL(url)); urls.current.clear(); uploads.current.clear()
    setPhotos([]); setCaption(''); setScheduled(''); setSpacing(0); setApproved(false); setSubmitted(false); setAction(undefined); setGroupJob(undefined); setNotice(''); requestId.current = crypto.randomUUID()
  }
  async function submit(publishNow: boolean) {
    if (busy || done || !approved) return
    if (!photos.length || (mode === 'photo' && photos.length !== 1) || (mode === 'carousel' && photos.length < 2)) { setNotice(mode === 'carousel' ? 'Choose 2–10 images for a carousel.' : 'Choose the images to publish.'); return }
    if (mode === 'batch' && (!Number.isInteger(spacing) || spacing < 0 || spacing > 10080)) { setNotice('Choose a whole number from 0 to 10080 minutes between scheduled posts.'); return }
    if (mode === 'carousel') {
      const ratios = photos.map(photo => photo.width / photo.height)
      if (Math.max(...ratios) - Math.min(...ratios) > 0.01) { setNotice('Use the same image proportions for every carousel slide so the full images appear together.'); return }
    }
    if (!submitted && !publishNow && (!scheduled || new Date(scheduled) <= new Date())) { setNotice('Choose a future schedule time.'); return }
    setBusy(true); setNotice('Uploading your images…')
    try {
      const assetIds: string[] = []
      for (let index = 0; index < photos.length; index++) {
        const photo = photos[index]
        if (!uploads.current.has(photo.id)) {
          setNotice(`Uploading image ${index + 1} of ${photos.length}…`)
          const asset = await api.uploadMedia(photo.file)
          uploads.current.set(photo.id, asset.id)
        }
        assetIds.push(uploads.current.get(photo.id)!)
      }
      const options = { approved: true, publish_now: publishNow, enqueue_only: true, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone }
      setSubmitted(true); setAction(publishNow)
      if (mode === 'batch') {
        let accepted = queued
        for (let index = 0; index < photos.length; index++) {
          const photo = photos[index]
          if (photo.job) continue
          setNotice(`Saving post ${index + 1} of ${photos.length}…`)
          const scheduledFor = !publishNow && scheduled ? new Date(new Date(scheduled).getTime() + index * spacing * 60_000).toISOString() : undefined
          const result = await api.createPost({ ...options, request_id: photo.requestId, caption: photo.caption, media_asset_id: assetIds[index], scheduled_for: scheduledFor })
          setPhotos(current => current.map(item => item.id === photo.id ? { ...item, job: result.job } : item))
          accepted++
          setNotice(`${accepted} of ${photos.length} posts saved.`)
        }
      } else {
        const result = await api.createPost({ ...options, request_id: requestId.current, caption, media_asset_ids: assetIds, scheduled_for: !publishNow && scheduled ? new Date(scheduled).toISOString() : undefined })
        setGroupJob(result.job)
      }
      setNotice(publishNow ? `${total === 1 ? 'Your post is' : `Your ${total} separate posts are`} queued for publishing. Follow each result in Calendar.` : `${total === 1 ? 'Your post is' : `Your ${total} separate posts are`} scheduled. View Calendar for the individual times.`)
    } catch (error) {
      setNotice(`${error instanceof Error ? error.message : 'The posts could not be saved.'} Completed posts stay in Calendar. Retry unchanged to continue without creating duplicates.`)
    } finally { setBusy(false) }
  }

  return <>
    <section className="page-heading"><p className="eyebrow">Content studio</p><h1>Create your next posts.</h1><p>Publish one photo, make a swipeable carousel, or prepare several separate posts together.</p></section>
    <section className="card composer-options">
      <label>What are you creating?<select value={mode} disabled={locked} onChange={event => { setMode(event.target.value as Mode); changed() }}><option value="photo">One photo post</option><option value="carousel">One carousel · 2–10 images</option><option value="batch">Several separate posts · up to 10</option></select></label>
      <p>{mode === 'carousel' ? 'One caption for the full carousel. Use matching image proportions and arrange the slides below.' : mode === 'batch' ? 'Each image becomes its own post with its own caption. Instagram processes posts individually; they will not appear at precisely the same instant.' : 'One image and one caption.'}</p>
      <label>Image fit<select value={fit} disabled={locked} onChange={event => void changeFit(event.target.value as ImageFit)}><option value="original">Keep original proportions</option><option value="portrait">Portrait · 4:5</option><option value="square">Square · 1:1</option><option value="landscape">Landscape · 1.91:1</option></select><small>Fitted images add white borders where needed. Nothing is cropped. Choose one fit for matching carousel slides.</small></label>
      <label>Choose images<input key={mode + String(submitted)} type="file" accept="image/jpeg,image/png,image/webp" multiple={mode !== 'photo'} disabled={locked} onChange={event => { void choose(event.target.files); event.target.value = '' }} /><small>JPEG, PNG or WebP · up to 20 MB and 25 megapixels per original. Images are resized and prepared as JPEGs below Instagram’s 8 MB limit. Transparency becomes white. Review the prepared previews before approving.</small></label>
    </section>
    {photos.length > 0 && <div className="post-image-grid">{photos.map((photo, index) => <article className="card post-image-card" key={photo.id}>
      <div className="post-image-heading"><h3>{mode === 'carousel' ? 'Slide' : 'Post'} {index + 1}</h3>{photo.job && <span className="status-pill scheduled">Saved to Calendar</span>}</div>
      <img src={photo.url} alt={`${mode === 'carousel' ? 'Slide' : 'Post'} ${index + 1} preview`} />
      <small>{photo.original.name} · {photo.width} × {photo.height} · {(photo.file.size / 1024 / 1024).toFixed(2)} MB prepared</small>
      {mode === 'batch' && <label>Caption<textarea value={photo.caption} maxLength={2200} rows={5} disabled={locked} onChange={event => { setPhotos(current => current.map(item => item.id === photo.id ? { ...item, caption: event.target.value, requestId: crypto.randomUUID() } : item)); changed() }} /><small>{photo.caption.length}/2200 characters</small></label>}
      {!submitted && <div className="actions"><button className="button secondary compact" disabled={busy || index === 0} onClick={() => move(index, -1)}>Move earlier</button><button className="button secondary compact" disabled={busy || index === photos.length - 1} onClick={() => move(index, 1)}>Move later</button><button className="button danger compact" disabled={busy} onClick={() => remove(photo.id)}>Remove</button></div>}
    </article>)}</div>}
    <section className="card composer-details">
      {mode !== 'batch' && <label>Caption<textarea value={caption} maxLength={2200} rows={6} disabled={locked} onChange={event => { setCaption(event.target.value); changed() }} placeholder="Write your caption…" /><small>{caption.length}/2200 characters</small></label>}
      <div className="grid"><label>{mode === 'batch' ? 'First post schedule (optional)' : 'Schedule (optional)'}<input type="datetime-local" disabled={locked} value={scheduled} onChange={event => { setScheduled(event.target.value); changed() }} /></label>{mode === 'batch' && <label>Minutes between scheduled posts<input type="number" min={0} max={10080} value={spacing} disabled={locked} onChange={event => { setSpacing(Number(event.target.value)); changed() }} /><small>Use 0 to schedule them for the same time.</small></label>}</div>
      {mode === 'batch' && scheduled && <ol>{photos.map((photo, index) => <li key={photo.id}>Post {index + 1}: {new Date(new Date(scheduled).getTime() + index * spacing * 60_000).toLocaleString()}</li>)}</ol>}
      <label className="check-row approval"><input type="checkbox" checked={approved} disabled={locked} onChange={event => setApproved(event.target.checked)} />I approve {mode === 'batch' ? `all ${photos.length} images and their individual captions` : mode === 'carousel' ? 'these images, their order, and the carousel caption' : 'this image and caption'} for publication.</label>
      <div className="actions"><button className="button primary" disabled={busy || !approved || !photos.length || done || (submitted && action === false)} onClick={() => void submit(true)}>{busy ? 'Saving…' : submitted && !done && action ? 'Retry remaining posts' : mode === 'batch' ? 'Publish these posts' : 'Publish now'}</button><button className="button secondary" disabled={busy || !approved || !photos.length || !scheduled || done || (submitted && action === true)} onClick={() => void submit(false)}>{submitted && !done && action === false ? 'Retry schedule' : 'Schedule'}</button><Link className="button secondary" to="/calendar">View Calendar</Link>{submitted && <button className="button secondary" disabled={busy} onClick={startAgain}>Start new posts</button>}</div>
      {notice && <p className="notice" role="status">{notice}</p>}
      {submitted && !done && <p>Your selections are locked while the result is being confirmed. Retry with the same selections to avoid duplicates.</p>}
    </section>
  </>
}
