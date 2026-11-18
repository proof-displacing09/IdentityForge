import type { RunStatus } from '../types'

const LABELS: Record<RunStatus, string> = {
  PASS: 'PASS', FAIL: 'FAIL', ERROR: 'ERROR', SKIPPED: 'SKIPPED / NOT RUN', RUNNING: 'RUNNING',
}
const CLASSES: Record<RunStatus, string> = {
  PASS: 'badge-pass', FAIL: 'badge-fail', ERROR: 'badge-error', SKIPPED: 'badge-skipped', RUNNING: 'badge-running',
}

export function StatusBadge({ status }: { status: RunStatus }) {
  return <span className={`badge ${CLASSES[status]}`} role="status">{LABELS[status]}</span>
}

export function ModeBadge({ mode }: { mode: string }) {
  const isReal = mode.includes('KEYCLOAK')
  const isFixture = mode.includes('OFFLINE') || mode.includes('FIXTURE')
  // P2-19 (v4): teal is reserved for VERIFIED identity — a real
  // Keycloak login. Offline fixtures are protocol data, shown in
  // azure. The v3 mapping had this backwards (fixture teal, real
  // azure); the classes are corrected here, not just the labels.
  const cls = isReal ? 'badge-live' : isFixture ? 'badge-fixture' : 'badge-notrun'
  const label = isReal ? 'LOCAL REAL KEYCLOAK INTEGRATION'
    : isFixture ? 'DETERMINISTIC OFFLINE FIXTURE'
    : mode === 'NOT RUN' ? 'NOT RUN' : mode
  return <span className={`badge ${cls}`}>{label}</span>
}

export function NotRunBadge() {
  return <span className="badge badge-notrun">NOT RUN</span>
}

/** Where a run's evidence came from — never implied, always stated. */
export function ProvenanceBadge({ provenance }: { provenance?: string }) {
  if (provenance === 'LIVE_KEYCLOAK') return <span className="badge badge-live">LIVE KEYCLOAK</span>
  if (provenance === 'EPHEMERAL') return <span className="badge badge-notmodeled">EPHEMERAL — NOT SAVED</span>
  if (provenance === 'OFFLINE_FIXTURE') return <span className="badge badge-fixture">OFFLINE FIXTURE</span>
  return <span className="badge badge-notrun">PROVENANCE UNKNOWN</span>
}

/** Whether the flawed fixture actually executed a session path. */
export function ModelBadge({ status }: { status?: string }) {
  if (status === 'NOT_MODELED') return <span className="badge badge-notmodeled">FLAWED PATH: NOT MODELED</span>
  if (status === 'EXECUTED') return <span className="badge badge-mode">FLAWED PATH: EXECUTED</span>
  return null
}
