import { useEffect, useId, useRef } from 'react'
import type { ReactNode } from 'react'

export default function Modal({ title, children, onClose, busy = false }: { title: string; children: ReactNode; onClose: () => void; busy?: boolean }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const id = useId()
  useEffect(() => {
    const element = dialog.current
    element?.showModal()
    return () => element?.close()
  }, [])
  return <dialog ref={dialog} className="app-dialog" aria-labelledby={id} onCancel={event => { event.preventDefault(); if (!busy) onClose() }}>
    <div className="dialog-header"><h2 id={id}>{title}</h2><button type="button" className="dialog-close" aria-label="Close dialog" disabled={busy} onClick={onClose}>×</button></div>
    {children}
  </dialog>
}
