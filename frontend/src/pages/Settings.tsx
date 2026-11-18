import { useEffect, useState } from 'react'
import { ApiError, getConfig, getHealth, getLabCounts, getLabStatus, getMe, resetLab } from '../api'
import type { Health, LabConfig, LabCounts, LabStatus, PortalUser } from '../types'
import { announce, ConfirmDialog, StatusPill } from '../components/ui'

/** Truthful reason for a failed reset, from the backend's real
 *  outcome. Every branch means nothing was cleared. */
function resetFailureReason(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 401) return 'you are not signed in (401 unauthenticated)'
    if (e.status === 403 && /policy_denied/i.test(e.detail)) return 'only an officer can reset the lab — a student cannot reset (403 policy_denied)'
    if (e.status === 403) return 'the request was rejected as a CSRF failure (403 csrf_denied)'
    if (e.status === 422) return 'the reset confirmation was missing or invalid (422 invalid_confirmation)'
    return `${e.status} ${e.detail || e.message}`
  }
  return String(e)
}

export function Settings({ onReset }: { onReset?: () => void }) {
  const [config, setConfig] = useState<LabConfig | null>(null)
  const [status, setStatus] = useState<LabStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  /** Operator identity, measured honestly (P2-23, v4). `undefined` =
   *  not yet checked; `null` = measured 401 (not signed in). A 403, a
   *  network failure or a 500 are NOT "not signed in" — they are
   *  distinct unknown-identity states, and the reset stays disabled
   *  in every one of them. */
  const [me, setMe] = useState<PortalUser | null | undefined>(undefined)
  const [meState, setMeState] = useState<'checking' | 'signed-in' | 'signed-out' | 'forbidden' | 'unreachable' | 'server-error'>('checking')
  const [meError, setMeError] = useState<string | null>(null)
  const [counts, setCounts] = useState<LabCounts | null>(null)
  /** IF-V5-05 (v6): the version shown here comes ONLY from the
   *  /api/v1/health payload. No version string is hard-coded in the
   *  UI; if the fetch fails the version is Unknown, never guessed. */
  const [health, setHealth] = useState<Health | null>(null)
  const [healthError, setHealthError] = useState<string | null>(null)
  const [confirm, setConfirm] = useState(false)
  const [confirmAgain, setConfirmAgain] = useState(false)
  const [resetMsg, setResetMsg] = useState<string | null>(null)
  const [resetFailed, setResetFailed] = useState(false)
  const [busy, setBusy] = useState(false)

  const isOfficer = me?.roles?.includes('officer') ?? false

  /** (Re-)check who is signed in. The reset control is enabled only
   *  when this returns a measured officer identity — never while the
   *  identity is unknown for any reason. */
  async function checkIdentity(): Promise<void> {
    setMeState('checking'); setMeError(null)
    try {
      const who = await getMe()
      setMe(who); setMeState('signed-in')
    } catch (e) {
      setMe(null)
      if (e instanceof ApiError && e.status === 401) setMeState('signed-out')
      else if (e instanceof ApiError && e.status === 403) { setMeState('forbidden'); setMeError('403') }
      else if (e instanceof ApiError && e.status >= 500) { setMeState('server-error'); setMeError(`${e.status} ${e.detail || e.message}`) }
      else { setMeState('unreachable'); setMeError(String(e)) }
    }
  }

  useEffect(() => {
    Promise.allSettled([getConfig(), getLabStatus(), getLabCounts(), getHealth()]).then(([c, s, n, h]) => {
      if (c.status === 'fulfilled') setConfig(c.value)
      if (s.status === 'fulfilled') setStatus(s.value)
      if (n.status === 'fulfilled') setCounts(n.value)
      if (h.status === 'fulfilled') setHealth(h.value)
      else setHealthError(String(h.reason))
      if (c.status === 'rejected' && s.status === 'rejected') setError(String(c.reason))
      setLoading(false)
    })
    void checkIdentity()
  }, [])

  /** Atelier v7 (f): while a reset confirm dialog is open, the page
   *  behind it does not scroll. Focus trap, Escape and return-focus
   *  already live in ConfirmDialog (components/ui.tsx, v6) and are
   *  verified, not re-implemented here. */
  useEffect(() => {
    if (!confirm && !confirmAgain) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = prev }
  }, [confirm, confirmAgain])

  /** Reset: double confirmation (two separate dialogs), then the
   *  message reflects the backend's real outcome. A 401/403/422 means
   *  nothing was cleared. On success the response carries the cleared
   *  counts, and the officer's own session IS revoked by the reset —
   *  the identity state is cleared and the counts are re-fetched
   *  (they should now be zeros). The backend rotates the CSRF token
   *  on reset and returns it in-band; the API client adopts it, so
   *  the next mutation does not 403. */
  async function doReset() {
    setBusy(true); setResetMsg(null); setResetFailed(false)
    try {
      const result = await resetLab()
      const c = result.cleared
      // IF-V5-02: exact units. The v6 backend reports retained
      // transactions AND retained events separately; an older backend
      // reports only the retained event count (live_logins), which
      // must be labelled as events, never as logins/transactions.
      const tx = c.live_login_transactions
      const ev = c.live_login_events ?? c.live_logins
      const livePart = typeof tx === 'number'
        ? `${tx} live login transaction(s) (${ev} live login event(s))`
        : `${ev} live login event(s) (transaction count not reported by this backend)`
      setResetMsg(`Lab state reset by ${result.operator}. Cleared ${c.runs} runs, ${c.sessions} sessions, ${livePart} and ${c.transactions} transactions. Your officer session was revoked by the reset — sign in again to continue.`)
      announce('Lab state reset.')
      // The reset revoked the officer's own session.
      setMe(null); setMeState('signed-out')
      const fresh = await getLabCounts().catch(() => null)
      if (fresh) setCounts(fresh)
      onReset?.()
    } catch (e) {
      setResetFailed(true)
      setResetMsg(`Reset failed: ${resetFailureReason(e)}. Nothing was cleared — the backend rejected the request.`)
      announce('Lab reset failed. Nothing was cleared.')
    } finally { setBusy(false); setConfirm(false); setConfirmAgain(false) }
  }

  /** Plain-language operator identity, one line per measured state.
   *  Only 'signed-in' names a user; every other state says exactly
   *  what was measured and that reset stays disabled. */
  const identityCopy =
    meState === 'checking'
      ? 'Checking who is signed in…'
      : meState === 'signed-out'
        ? 'Sign in as officer_01 to enable reset'
        : meState === 'signed-in' && me
          ? isOfficer
            ? `Signed in as ${me.username ?? me.sub ?? 'officer'} — reset authorized`
            : `Signed in as ${me.username ?? me.sub ?? 'student'} — only an officer can reset`
          : meState === 'forbidden'
            ? 'The backend refused the identity check (403) — it would not confirm who is signed in, so reset stays disabled'
            : meState === 'unreachable'
              ? 'Could not reach the backend — who is signed in is unknown, so reset stays disabled'
              : 'The backend returned a server error — who is signed in is unknown, so reset stays disabled'
  const identityUnknown = meState === 'forbidden' || meState === 'unreachable' || meState === 'server-error'

  return (
    <section aria-label="Lab Settings">
      <p className="eyebrow">Lab · Truthful runtime configuration</p>
      <h1>Lab Settings</h1>
      <p className="page-sub">Real configuration only. There are deliberately <strong>no unsafe toggles</strong> here — no &ldquo;disable issuer check&rdquo;, no &ldquo;skip PKCE&rdquo;, no &ldquo;insecure mode&rdquo;. The flawed variants live only in the offline test harness and cannot be switched on from this UI.</p>
      {loading && <p role="status">Loading configuration…</p>}
      {error && <div className="alert alert-error" role="alert">Could not load lab config: {error}</div>}
      {status && (
        <div className="card"><h2>Measured lab status</h2>
          <dl className="kv">
            <dt>Backend</dt><dd>{status.backend}</dd>
            <dt>Issuer</dt><dd><span className="code">{status.issuer}</span></dd>
            <dt>Provider mode</dt><dd>{status.provider_mode ?? 'unknown'}</dd>
            <dt>IdP reachable</dt><dd>{status.idp.reachable ? 'Yes' : 'No'} — {status.idp.reason}</dd>
            <dt>Issuer matches</dt><dd>{status.idp.issuer_matches === true ? 'Yes — discovery issuer matches the configured issuer' : status.idp.issuer_matches === false ? 'No — MISMATCH: discovery issuer differs from the configured issuer; real login is NOT RUN' : 'Unknown — issuer match not determined'}</dd>
            <dt>Discovery</dt><dd><span className="code">{status.idp.discovery_url}</span></dd>
            <dt>Last verified login</dt><dd>{status.last_verified_login ? `${status.last_verified_login.username} · ${status.last_verified_login.at}` : 'NOT RUN'}</dd>
          </dl>
        </div>
      )}
      {config && (
        <div className="card"><h2>Configuration</h2><dl className="kv">
          <dt>Backend</dt><dd>http://127.0.0.1:8000</dd>
          <dt>Frontend</dt><dd>http://127.0.0.1:5173</dd>
          <dt>Keycloak</dt><dd>{config.keycloak_url ?? 'http://127.0.0.1:8080'}</dd>
          <dt>Issuer</dt><dd><span className="code">{config.issuer ?? 'http://127.0.0.1:8080/realms/identityforge-lab'}</span></dd>
          <dt>Fixture revision</dt><dd>{config.fixture_revision ?? 'unknown'}</dd>
          <dt>Secrets</dt><dd>Masked — no passwords, client secrets or tokens are ever shown in this UI. The Keycloak admin password and synthetic user passwords are documented in the project README only.</dd>
        </dl></div>
      )}
      <div className="card">
        <h2>Reset synthetic lab state</h2>
        <p className="small muted">Clears disposable fixture/session evidence on the backend (localhost operator action). It does not touch real accounts — there are none — and it cannot make the portal insecure. Reset asks twice: it cannot be undone.</p>
        {/* Atelier v7 (f): the measured identity state is a pill as
            well as words — teal only for a measured officer, amber
            while the identity is unknown for any reason, red only
            when the backend refused the check (403). The reset button
            below is described by this line, so a screen reader hears
            exactly why it is enabled or disabled. */}
        <p role="status" id="identity-state" className="identity-state">
          <StatusPill tone={meState === 'signed-in' && isOfficer ? 'teal' : meState === 'forbidden' ? 'bad' : meState === 'unreachable' || meState === 'server-error' ? 'warn' : 'neutral'}>
            {meState === 'checking' ? 'Checking identity…' : meState === 'signed-in' ? (isOfficer ? 'Officer — reset authorized' : 'Signed in — student') : meState === 'signed-out' ? 'Not signed in' : meState === 'forbidden' ? 'Identity refused (403)' : 'Identity unknown'}
          </StatusPill>
          <span>{identityCopy}</span>
        </p>
        {identityUnknown && (
          <p>
            <button type="button" className="btn btn-ghost" onClick={() => void checkIdentity()}>Retry identity check</button>
            {meError && <span className="small muted"> Last check: {meError}</span>}
          </p>
        )}
        {counts && (
          <>
            <dl className="kv">
              <dt>Runs that would be cleared</dt><dd>{counts.runs}{counts.runs_limit ? ` of ${counts.runs_limit} retained` : ''}</dd>
              <dt>Active sessions that would be cleared</dt><dd>{counts.sessions}</dd>
              <dt>Sessions issued since backend start</dt><dd>{counts.sessions_total_issued ?? 'Unknown'}</dd>
              {/* IF-V5-02: transactions and events are different units.
                  live_logins (v5 backend) is a retained EVENT count. */}
              <dt>Live login transactions that would be cleared</dt><dd>{counts.live_login_transactions ?? 'Unknown — this backend reports only the retained event count below'}</dd>
              <dt>Live login events that would be cleared</dt><dd>{counts.live_login_events ?? counts.live_logins}{counts.live_login_event_limit ?? counts.live_logins_limit ? ` of ${counts.live_login_event_limit ?? counts.live_logins_limit} retained` : ''}</dd>
              <dt>Transactions that would be cleared</dt><dd>{counts.transactions}</dd>
            </dl>
            <p className="small muted">
              Session count is active sessions only (IF-V4-03): live, unexpired and unrevoked sessions. Expired and revoked
              records are pruned and never counted. &ldquo;Sessions issued since backend start&rdquo; is a separate
              process-lifetime diagnostic — a lab reset clears the active sessions but does not rewind that total.
              One live login transaction is one login attempt (one correlation ID); one transaction can contain several
              recorded events, so the event count is always ≥ the transaction count.
            </p>
          </>
        )}
        {meState === 'signed-in' && (
          <p>
            <button type="button" className="btn btn-ghost" onClick={() => void checkIdentity()}>Re-check identity</button>
            <span className="small muted"> Re-checks /api/v1/portal/me. The reset button stays disabled while the re-check is pending, until the officer identity is confirmed again.</span>
          </p>
        )}
        <button className="btn btn-danger" disabled={!isOfficer || meState !== 'signed-in' || busy} aria-describedby="identity-state" onClick={() => setConfirm(true)}>Reset lab state…</button>
        {resetMsg && (
          resetFailed
            ? <div className="alert alert-error" role="alert">{resetMsg}</div>
            : <p role="status"><StatusPill tone="ok">Reset confirmed</StatusPill> {resetMsg}</p>
        )}
      </div>
      <div className="card">
        <h2>Evidence retention — what is kept, what is pruned</h2>
        <p>
          <StatusPill tone="warn">Automatic pruning at capacity</StatusPill>
        </p>
        <p>
          Old evidence is <strong>automatically pruned</strong> when the store reaches its capacity — oldest first
          (FIFO), at save time. The caps are the latest <strong>{counts?.runs_limit ?? 1000} scenario runs</strong>, the
          latest <strong>{counts?.events_limit ?? 20000} run events</strong> and the latest{' '}
          <strong>{counts?.live_login_event_limit ?? counts?.live_logins_limit ?? 1000} live-login events</strong>.
          When a new run or login event is saved past a cap, the oldest records at that cap are removed to make room.
          A manual lab reset is the <strong>only manual destructive action</strong> — it clears everything at once and
          cannot be undone; pruning, by contrast, removes only the oldest records, one save at a time.
        </p>
        <p>
          <strong>Export before eviction.</strong> If evidence matters for a report or a review, export it from
          Findings &amp; Evidence (JSON / CSV / Markdown) <em>before</em> running many more scenarios or logins —
          once pruned, the older runs and login timelines cannot be recovered from this lab. Exported files contain
          only redacted evidence: run decisions, timelines and reason codes. They never contain passwords, client
          secrets, authorization codes, ID tokens or session cookies, and no exported file is signed or tamper-proof —
          a downloaded file proves only what it contains, not that it came from this backend (see the provenance
          label on each download).
        </p>
        <p className="small muted">
          Current retained counts: {counts ? `${counts.runs} runs · ${counts.events ?? 'Unknown'} run events · ${counts.live_login_events ?? counts.live_logins} live-login events` : 'Unknown — the backend did not return counts.'}
          {counts && (counts.runs_limit && counts.runs >= counts.runs_limit ? ' The run store is AT its cap: the next saved run will evict the oldest run.' : '')}
          {counts && ((counts.live_login_event_limit ?? counts.live_logins_limit) && (counts.live_login_events ?? counts.live_logins) >= (counts.live_login_event_limit ?? counts.live_logins_limit ?? 1000) ? ' The live-login event store is AT its cap: the next saved login event will evict the oldest event.' : '')}
        </p>
      </div>
      <div className="card">
        <h2>About this build</h2>
        <dl className="kv">
          {/* IF-V5-05: version read from /api/v1/health at load time.
              The UI holds no competing hard-coded version string. */}
          <dt>Backend version</dt><dd>{health?.version ?? 'Unknown'} {healthError ? `— could not be read from /api/v1/health (${healthError})` : '— from /api/v1/health'}</dd>
          <dt>Service</dt><dd>{health?.service ?? 'Unknown'}</dd>
          <dt>Provider mode</dt><dd>{health?.provider_mode ?? status?.provider_mode ?? 'Unknown'}</dd>
          <dt>Lab</dt><dd>IdentityForge — OAuth / OIDC Authentication Attack Laboratory (Operation Trustline). Synthetic data only; loopback only.</dd>
        </dl>
      </div>
      <div className="card">
        <h2>Running the lab</h2>
        <p className="small muted">
          Docker: <span className="code">docker compose up --build -d</span> (see <span className="code">docs/WINDOWS_SETUP.md</span> for Docker Desktop on Windows; Docker Desktop&apos;s WSL2 backend does not require reinstalling a Linux distribution).
          Host-run checks: <span className="code">./scripts/test-all.sh --full --strict</span> and <span className="code">python3 scripts/live-gate.py all</span>.
          Verification evidence: <span className="code">docs/VERIFICATION_LOG.md</span>.
        </p>
      </div>
      {confirm && (
        <ConfirmDialog title="Reset lab state?" confirmLabel="Yes, reset — continue" busy={busy} onConfirm={() => { setConfirm(false); setConfirmAgain(true) }} onCancel={() => setConfirm(false)}>
          <p>This clears synthetic lab evidence and sessions on the backend. This cannot be undone.</p>
        </ConfirmDialog>
      )}
      {confirmAgain && (
        <ConfirmDialog title="Are you sure? This cannot be undone." confirmLabel="Yes, reset now" busy={busy} onConfirm={() => void doReset()} onCancel={() => setConfirmAgain(false)}>
          <p>Second confirmation: all recorded runs, sessions and transactions on the backend will be cleared. Your browser&apos;s local run history is cleared separately from Findings &amp; Evidence.</p>
        </ConfirmDialog>
      )}
    </section>
  )
}
