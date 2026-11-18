import type { LabCounts, LiveLogin } from '../types'

/** IF-V5-02 (v6): exact transaction/event units for real Keycloak logins.
 *
 * Units, fixed once here so every view agrees:
 * - A TRANSACTION is one login attempt = one distinct correlation_id.
 * - An EVENT is one recorded BFF-observed step inside a transaction.
 * - `live_logins` in the v5 /api/v1/lab/counts payload is a RETAINED
 *   EVENT count (COUNT(*) over live_login_events), NOT a transaction
 *   count — the field name is historical and must never be rendered
 *   as "N logins".
 * - WS1's v6 counts fields, when present, are authoritative:
 *   live_login_transactions (COUNT DISTINCT correlation_id, retained),
 *   live_login_events (retained event rows),
 *   live_login_event_limit (retention cap, 1000 in v5).
 *   When they are absent (older backend), the same numbers are
 *   computed from the /api/v1/live-logins sample (max 20 most recent
 *   transactions) — and the summary says so.
 * - The sample is at most 20 transactions; the retained TOTAL can be
 *   larger. Both are shown, never conflated: "Recent transactions
 *   displayed (max 20)" for the sample, "Retained total" for the
 *   count. Retention pruning means the retained total is NOT an
 *   all-time total.
 * - A failed/partial fetch yields nulls (UNKNOWN), never a fake 0. */

export const LIVE_LOGIN_SAMPLE_LIMIT = 20

/** IF-V5-04 (v6) canonical login flow, mirrored from the backend's
 *  assess_live_login_timeline (backend/src/identityforge/evidence/
 *  store.py LOGIN_STAGES). Post-login stages (AUTHORIZATION_DECISION,
 *  LOGOUT) may follow a successful SESSION_CREATED but are not part
 *  of the login flow and never affect completeness. */
export const LOGIN_STAGES = [
  'AUTH_STARTED',
  'CALLBACK_RECEIVED',
  'BINDING_VERIFIED',
  'TOKEN_ENDPOINT',
  'ID_TOKEN_VALIDATED',
  'SESSION_CREATED',
] as const

export interface LiveLoginAssessment {
  timeline_complete: boolean
  successful: boolean
  missing_stages: string[]
  truncated_at: string | null
  retention_reason: string | null
}

/** Mirror of the backend canonical predicate: complete means the
 *  login-phase stages start at AUTH_STARTED, proceed in canonical
 *  order with no gaps, and reach a terminal stage (SESSION_CREATED
 *  ok, or any stage rejected/error — a fully recorded failure).
 *  `successful` requires completeness AND a SESSION_CREATED ok: a
 *  truncated tail that merely contains such an event proves nothing. */
export function assessLiveLoginTimeline(login: LiveLogin): LiveLoginAssessment {
  const events = (login.events ?? []).filter((e) => (LOGIN_STAGES as readonly string[]).includes(e.stage))
  const missing: string[] = []
  let gap = false
  let terminal = false
  let expectedIdx = 0
  let lastStage: string | null = null
  for (const event of events) {
    const stage = event.stage
    const idx = LOGIN_STAGES.indexOf(stage as (typeof LOGIN_STAGES)[number])
    lastStage = stage
    if (idx < expectedIdx) { gap = true; continue }
    if (idx > expectedIdx) {
      missing.push(...LOGIN_STAGES.slice(expectedIdx, idx))
      gap = true
    }
    expectedIdx = Math.max(expectedIdx, idx + 1)
    if (event.outcome === 'rejected' || event.outcome === 'error') { terminal = true; break }
    if (stage === 'SESSION_CREATED' && event.outcome === 'ok') { terminal = true; break }
  }
  if (!terminal) missing.push(...LOGIN_STAGES.slice(expectedIdx))
  const complete = !gap && terminal
  const successful = complete && events.some((e) => e.stage === 'SESSION_CREATED' && e.outcome === 'ok')
  return {
    timeline_complete: complete,
    successful,
    missing_stages: missing,
    truncated_at: complete ? null : lastStage,
    retention_reason: complete
      ? null
      : gap
        ? 'a login stage was skipped in the recorded sequence: leading events were not recorded (pre-v6 per-row retention, an evidence save failure, or an interrupted login); the recorded outcome must not be read as a successful login'
        : 'timeline ends before a terminal stage: trailing events were not recorded (interrupted login, evidence save failure, or pre-v6 per-row retention); the recorded outcome must not be read as a successful login',
  }
}

/** IF-V6-02: a transaction counts as a VERIFIED successful login
 *  only when the backend assessment says so (successful===true AND
 *  timeline_complete===true) — or, when the backend did not report
 *  an assessment, when the local mirror of the canonical predicate
 *  says so. Never the SESSION_CREATED event-exists shortcut. */
export function isVerifiedLiveLogin(login: LiveLogin): boolean {
  if (typeof login.successful === 'boolean' || typeof login.timeline_complete === 'boolean') {
    return login.successful === true && login.timeline_complete === true
  }
  return assessLiveLoginTimeline(login).successful
}

/** The one verified login for a username in a sample, or undefined.
 *  Assessed per transaction (see isVerifiedLiveLogin), never by a
 *  generic count. */
export function findVerifiedLogin(logins: LiveLogin[], username: string): LiveLogin | undefined {
  return logins.find(
    (l) => isVerifiedLiveLogin(l) && l.events.some((e) => e.username === username),
  )
}

export interface LiveLoginSummary {
  /** Distinct retained transactions (COUNT DISTINCT correlation_id),
   *  or null when no source could measure it. */
  transactions: number | null
  /** Retained event rows, or null when unmeasured. */
  events: number | null
  /** Transactions in the retained set that reached SESSION_CREATED
   *  with outcome ok — null when the sample cannot measure it. */
  successfulTransactions: number | null
  /** Transactions actually present in the fetched sample (<= 20). */
  displayedTransactions: number
  /** Events actually present in the fetched sample. */
  displayedEvents: number
  /** Retention cap for live-login events, when the backend reports it. */
  eventLimit: number | null
  /** Where the totals came from. 'server' = WS1 v6 counts fields;
   *  'computed' = derived from the fetched sample (older backend);
   *  'unknown' = nothing could be measured. */
  source: 'server' | 'computed' | 'unknown'
  /** True when the retained total is at the retention cap, i.e. older
   *  evidence has almost certainly been pruned. */
  atRetentionLimit: boolean
}

/** Distinct transactions in a fetched sample. Extra events for an
 *  existing correlation_id never inflate this number. */
export function countTransactions(logins: LiveLogin[]): number {
  return new Set(logins.map((l) => l.correlation_id)).size
}

export function countEvents(logins: LiveLogin[]): number {
  return logins.reduce((n, l) => n + (l.events?.length ?? 0), 0)
}

/** IF-V6-02: canonical verified-success count. A transaction counts
 *  only when its timeline is complete and ends in SESSION_CREATED ok
 *  (backend assessment when present, else the local canonical mirror).
 *  A truncated tail with a SESSION_CREATED ok event counts 0. */
export function countSuccessfulTransactions(logins: LiveLogin[]): number {
  return logins.filter((l) => isVerifiedLiveLogin(l)).length
}

/** Explicitly-named observed-event counter: transactions that contain
 *  a SESSION_CREATED event with outcome ok, regardless of whether the
 *  rest of the timeline was recorded. This is an OBSERVED-EVENT count
 *  only — it must be labelled exactly that in UI copy, never as a
 *  verified successful login. */
export function countObservedSessionCreatedTransactions(logins: LiveLogin[]): number {
  return logins.filter((l) =>
    l.events?.some((e) => e.stage === 'SESSION_CREATED' && e.outcome === 'ok'),
  ).length
}

/** Build the one summary every view renders. `counts` is the optional
 *  /api/v1/lab/counts payload; `logins` is the optional fetched
 *  /api/v1/live-logins sample. Either may be absent; a summary with
 *  nulls is UNKNOWN, never zero. */
export function summarizeLiveLogins(
  logins: LiveLogin[] | null,
  counts?: LabCounts | null,
): LiveLoginSummary {
  const displayedTransactions = logins ? countTransactions(logins) : 0
  const displayedEvents = logins ? countEvents(logins) : 0
  const serverTx = counts?.live_login_transactions
  const serverEv = counts?.live_login_events
  const eventLimit = counts?.live_login_event_limit ?? counts?.live_logins_limit ?? null
  if (typeof serverTx === 'number' && typeof serverEv === 'number') {
    return {
      transactions: serverTx,
      events: serverEv,
      // IF-V6-02: the server successful count is the backend canonical
      // count (WS1 v7: assess_live_login_timeline — complete timeline
      // ending SESSION_CREATED ok). It is used ONLY when the backend
      // reports it; otherwise the canonical count is computed from the
      // sample with the same predicate. Never the event-exists shortcut.
      successfulTransactions:
        typeof counts?.live_login_successful_transactions === 'number'
          ? counts.live_login_successful_transactions
          : logins
            ? countSuccessfulTransactions(logins)
            : null,
      displayedTransactions,
      displayedEvents,
      eventLimit,
      source: 'server',
      atRetentionLimit: eventLimit !== null && serverEv >= eventLimit,
    }
  }
  if (logins) {
    return {
      transactions: displayedTransactions,
      events: displayedEvents,
      successfulTransactions: countSuccessfulTransactions(logins),
      displayedTransactions,
      displayedEvents,
      eventLimit,
      source: 'computed',
      atRetentionLimit: eventLimit !== null && displayedEvents >= eventLimit,
    }
  }
  return {
    transactions: null,
    events: null,
    successfulTransactions: null,
    displayedTransactions: 0,
    displayedEvents: 0,
    eventLimit,
    source: 'unknown',
    atRetentionLimit: false,
  }
}

/** Human wording for a summary, shared by Overview / Settings /
 *  Reports / Atlas so the units can never drift apart. */
export function liveLoginSummaryNote(s: LiveLoginSummary): string {
  if (s.transactions === null) return 'Live login evidence unavailable — count is Unknown, not zero.'
  const parts = [
    `${s.transactions} retained transaction(s)`,
    `${s.events ?? 'Unknown'} retained event(s)`,
  ]
  if (s.successfulTransactions !== null) parts.push(`${s.successfulTransactions} verified successful login(s) (complete timeline ending SESSION_CREATED ok)`)
  let note = parts.join(' · ')
  note += `. Recent transactions displayed (max ${LIVE_LOGIN_SAMPLE_LIMIT}): ${s.displayedTransactions}.`
  note += ' Retained total, not an all-time total — older evidence is pruned at the retention cap'
  note += s.eventLimit !== null ? ` (latest ${s.eventLimit} live-login events).` : '.'
  if (s.atRetentionLimit) note += ' The retained set is AT the cap: older transactions have been evicted.'
  return note
}
