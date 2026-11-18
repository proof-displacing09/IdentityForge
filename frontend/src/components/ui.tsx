import { useEffect, useRef, type ReactNode } from 'react'
import type { RunStatus } from '../types'
import { stateTone, type RequestState } from '../lib/useResource'
import { ModeBadge, StatusBadge } from './Badge'

/** Shared design primitives (P2-22). Every one has a real loading /
 *  empty / error state; none is a decorative dead control. */

export function StatusPill({ tone, children }: { tone: 'ok' | 'warn' | 'bad' | 'info' | 'neutral' | 'teal'; children: ReactNode }) {
  const cls = tone === 'ok' ? 'pill-ok' : tone === 'warn' ? 'pill-warn' : tone === 'bad' ? 'pill-bad' : tone === 'info' ? 'pill-info' : tone === 'teal' ? 'pill-teal' : ''
  return <span className={`pill ${cls}`}><span className="dot" aria-hidden="true" />{children}</span>
}

export function MetricTile({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return (
    <div className="metric">
      <div className="metric-value">{value}</div>
      <div className="metric-label">{label}</div>
      {note && <div className="metric-note">{note}</div>}
    </div>
  )
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty" role="status">
      <p><strong>{title}</strong></p>
      {children}
    </div>
  )
}

export function Skeleton({ height = 18, width = '100%', label }: { height?: number; width?: string | number; label?: string }) {
  return (
    <div role="status" aria-label={label ?? 'Loading content'}>
      <div className="skeleton" style={{ height, width }} aria-hidden="true" />
      <span className="sr-only">{label ?? 'Loading content'}</span>
    </div>
  )
}

/** IF-V5-06 (v6): one labelled pill per resource request state, with
 *  a timestamp when the state was last measured. */
export function RequestStatePill({ state, updatedAt, errorAt }: { state: RequestState; updatedAt?: Date | null; errorAt?: Date | null }) {
  const at = state === 'READY' || state === 'STALE' ? updatedAt : state === 'ERROR' ? errorAt : null
  return (
    <span className="request-state">
      <StatusPill tone={stateTone(state)}>{state}</StatusPill>
      {at && <span className="small muted"> · {at.toLocaleTimeString()}</span>}
    </span>
  )
}

export function RunStatusRow({ status, mode }: { status: RunStatus; mode: string }) {
  return <p><StatusBadge status={status} /> <ModeBadge mode={mode} /></p>
}

/** Accessible confirm dialog: focus moves in, Tab is trapped inside,
 *  ESC / Cancel returns focus to the element that opened it. */
export function ConfirmDialog({ title, children, confirmLabel, busy, onConfirm, onCancel }: {
  title: string
  children: ReactNode
  confirmLabel: string
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  const cancelRef = useRef<HTMLButtonElement>(null)
  const dialogRef = useRef<HTMLDivElement>(null)
  const returnFocusRef = useRef<Element | null>(null)
  useEffect(() => {
    returnFocusRef.current = document.activeElement
    cancelRef.current?.focus()
    return () => {
      const el = returnFocusRef.current
      if (el && el instanceof HTMLElement) el.focus()
    }
  }, [])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); onCancel(); return }
      if (e.key !== 'Tab' || !dialogRef.current) return
      const focusables = [...dialogRef.current.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      )].filter((el) => !el.hasAttribute('disabled'))
      if (focusables.length === 0) return
      const first = focusables[0]
      const last = focusables[focusables.length - 1]
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onCancel])
  return (
    <div className="modal-backdrop" role="presentation">
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="confirm-title" ref={dialogRef}>
        <h2 id="confirm-title">{title}</h2>
        {children}
        <p>
          <button className="btn btn-danger" onClick={onConfirm} disabled={busy}>{busy ? 'Working…' : confirmLabel}</button>{' '}
          <button className="btn btn-ghost" ref={cancelRef} onClick={onCancel}>Cancel</button>
        </p>
      </div>
    </div>
  )
}

/** Announce a status change to screen readers. Pages call announce()
 *  after runs, logins, logouts and errors; App renders the live region. */
export function announce(message: string): void {
  window.dispatchEvent(new CustomEvent('if-announce', { detail: message }))
}

export function Toast({ message, tone, onClose }: { message: string; tone?: 'error' | 'info'; onClose: () => void }) {
  return (
    <div className={`toast${tone === 'error' ? ' toast-error' : ''}`} role={tone === 'error' ? 'alert' : 'status'}>
      {message}{' '}
      <button className="btn btn-ghost" onClick={onClose} aria-label="Dismiss notification">Dismiss</button>
    </div>
  )
}
