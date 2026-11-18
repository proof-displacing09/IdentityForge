import { useMemo } from 'react'
import { getLabCounts, getLabStatus, getLiveLogins, listScenarios } from '../api'
import { announce, EmptyState, MetricTile, RequestStatePill, Skeleton, StatusPill } from '../components/ui'
import type { LabCounts, RunResult } from '../types'
import { ModeBadge, ProvenanceBadge, StatusBadge } from '../components/Badge'
import { useResource } from '../lib/useResource'
import { LIVE_LOGIN_SAMPLE_LIMIT, findVerifiedLogin, liveLoginSummaryNote, summarizeLiveLogins } from '../lib/liveLogins'

export function Overview({ runs, onNavigate }: { runs: RunResult[]; onNavigate: (path: string) => void }) {
  // IF-V5-06 (v6): each resource has its own explicit request state
  // (IDLE/LOADING/READY/STALE/ERROR/NOT RUN) with a timestamp. A later
  // success clears a stale error; stale saved evidence is never
  // presented as current live health. The hook aborts in-flight
  // requests on unmount and ignores superseded responses.
  const statusRes = useResource((signal) => getLabStatus(signal))
  const scenariosRes = useResource((signal) => listScenarios(signal))
  const liveRes = useResource((signal) => getLiveLogins(signal))
  const countsRes = useResource((signal) => getLabCounts(signal))

  const status = statusRes.data
  const scenarios = scenariosRes.data ?? []
  const liveLogins = liveRes.data ?? []
  const counts: LabCounts | null = countsRes.data
  const loading = statusRes.state === 'LOADING' || statusRes.state === 'IDLE'
  const error = statusRes.state === 'ERROR' ? statusRes.error : null

  // IF-V5-02 (v6): one summary, exact units, shared everywhere.
  // Transactions = distinct correlation_ids (retained total, from the
  // WS1 v6 counts fields when present, else computed from the sample).
  // The sample shows at most 20 recent transactions; the total is the
  // RETAINED total, never an all-time total.
  const summary = useMemo(
    () => summarizeLiveLogins(liveRes.data, counts),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [liveRes.data, countsRes.data],
  )

  const passCount = runs.filter((r) => r.status === 'PASS').length
  const failCount = runs.filter((r) => r.status === 'FAIL' || r.status === 'ERROR').length
  const evidenceMissing = runs.filter((r) => r.evidence_saved === false).length
  const lastLogin = status?.last_verified_login
  const recent = [...runs].reverse().slice(0, 5)
  // IF-V6-02: a verified sign-in needs the backend canonical
  // assessment (complete timeline ending SESSION_CREATED ok), never
  // the SESSION_CREATED event-exists shortcut.
  const verifiedLogin = (username: string) => findVerifiedLogin(liveLogins, username)
  const distinctScenarios = new Set(runs.map((r) => r.scenario_id)).size

  // IF-V6-03: READY is a NECESSARY condition for a CURRENT green
  // VERIFIED badge. STALE data is shown only as a past-tense
  // 'Previously verified — last verified at …' chip, never green.
  type StepState = 'done' | 'todo' | 'action' | 'mismatch' | 'error' | 'stale'
  function servicesStep(): { state: StepState; evidence?: string } {
    if (error) return { state: 'error', evidence: 'Status could not be loaded — see the error above. Nothing on this page is a measured result.' }
    if (!status) return { state: 'todo' }
    if (status.backend !== 'ok') return { state: 'todo', evidence: `Backend reports ${status.backend} — services are not ready.` }
    if (!status.idp.reachable) return { state: 'todo', evidence: undefined }
    if (status.idp.issuer_matches === false) return { state: 'mismatch', evidence: 'IdP reachable but discovery issuer does NOT match the configured issuer — real login is NOT RUN.' }
    if (status.idp.issuer_matches === true) {
      if (statusRes.state === 'READY') return { state: 'done', evidence: 'IdP discovery reachable — issuer matches' }
      return { state: 'stale', evidence: `Last verified at ${statusRes.updatedAt?.toLocaleString() ?? 'unknown time'} — a newer status request failed, so this is not current live health.` }
    }
    return { state: 'todo', evidence: 'IdP reachable — issuer match not yet determined.' }
  }
  const services = servicesStep()
  function loginStep(username: string, title: string, detail: string): { title: string; detail: string; path: string; linkLabel: string; state: StepState; evidence?: string } {
    const base = { title, detail, path: '/portal', linkLabel: 'Open Portal' }
    if (liveRes.state === 'ERROR') return { ...base, state: 'error', evidence: 'Live login evidence could not be loaded — count is Unknown.' }
    const verified = verifiedLogin(username)
    if (!verified) return { ...base, state: 'todo', evidence: undefined }
    if (liveRes.state === 'READY') return { ...base, state: 'done', evidence: `${username} completed a verified live login (complete timeline ending SESSION_CREATED ok)` }
    return { ...base, state: 'stale', evidence: `${username} was previously observed with a verified live login — last verified at ${liveRes.updatedAt?.toLocaleString() ?? 'unknown time'}. Not current live health.` }
  }
  const atlasState: StepState =
    liveRes.state === 'ERROR' ? 'error'
    : summary.transactions !== null && summary.transactions > 0
      ? liveRes.state === 'READY' ? 'done' : 'stale'
      : 'todo'
  const atlasEvidence: string | undefined =
    liveRes.state === 'ERROR'
      ? 'Live login evidence could not be loaded — count is Unknown.'
      : summary.transactions !== null && summary.transactions > 0
        ? liveRes.state === 'READY'
          ? `${summary.transactions} live login transaction(s) retained (${summary.events ?? 'Unknown'} event(s)); recent ${summary.displayedTransactions} shown`
          : `Previously observed: ${summary.transactions} live login transaction(s) retained — last verified at ${liveRes.updatedAt?.toLocaleString() ?? 'unknown time'}. Not current live health.`
        : undefined
  const reviewerSteps: { title: string; detail: string; path: string; linkLabel: string; state: StepState; evidence?: string }[] = [
    {
      title: 'Start services',
      // IF-V7-01: never claim a Docker Compose boot from a browser
      // status request, and never describe the probe as host-process
      // (the API provides no deployment-type fact). The detail is
      // state-aware: the measured claim appears only when the step
      // is currently Verified; otherwise the step says plainly that
      // readiness is not currently verified in this browser.
      detail:
        services.state === 'done'
          ? 'Backend responds; Keycloak discovery is reachable; issuer matches — measured by /api/v1/lab/status. Docker Compose cold-start is not measured in this view; see docs/REVIEWER_GUIDE.md §7.'
          : 'Backend and Keycloak readiness is measured by /api/v1/lab/status in this browser — not currently verified. Docker Compose cold-start is not measured in this view; see docs/REVIEWER_GUIDE.md §7.',
      path: '/settings',
      linkLabel: 'Open Lab Settings',
      ...services,
    },
    loginStep('student_01', 'Secure student sign-in', 'Sign in as student_01 in the Campus Club Portal — a real Keycloak login.'),
    { title: 'Deny officer as student', detail: 'As student_01, load the officer resource in the Portal — it must be denied (403).', path: '/portal', linkLabel: 'Open Portal', state: 'action' },
    loginStep('officer_01', 'Officer sign-in', 'Sign in as officer_01 — member and officer resources must both be allowed.'),
    { title: 'Run I1–I18 offline cases', detail: 'Run all eighteen scenarios in the Studio; each compares the secure validator against the one-check-omitted flawed model.', path: '/scenarios', linkLabel: 'Open Scenario Studio', state: distinctScenarios >= 18 ? 'done' : 'todo', evidence: distinctScenarios > 0 ? `${distinctScenarios} of 18 scenarios run in this browser` : undefined },
    {
      title: 'Inspect live Atlas events', detail: 'Open the Flow Inspector and switch to the Live Keycloak tab — redacted, real login timelines.', path: '/flow', linkLabel: 'Open Flow Inspector',
      state: atlasState,
      evidence: atlasEvidence,
    },
    { title: 'Compare one missing-check model', detail: 'In Secure vs Flawed, pick a scenario and read what the single omitted check actually changes.', path: '/compare', linkLabel: 'Open Secure vs Flawed', state: 'action' },
    { title: 'Export redacted evidence', detail: 'Download a JSON/CSV/Markdown report from Findings & Evidence — no tokens, codes or subjects inside.', path: '/findings', linkLabel: 'Open Findings & Evidence', state: 'action' },
  ]

  function retryAll() {
    statusRes.retry(); scenariosRes.retry(); liveRes.retry(); countsRes.retry()
  }

  return (
    <section aria-label="Overview">
      <div className="hero">
        <p className="eyebrow">Operation Trustline · Local laboratory</p>
        <h1>Overview</h1>
        <p className="page-sub">A local OAuth 2.0 / OpenID Connect login laboratory for the fictional Cedarbridge Campus Club. All data is synthetic — but the lab uses genuine Keycloak software, running locally, for real authentication: real authorization codes, real PKCE, real signed ID tokens. No claim below is made without a measurement behind it.</p>
        <p>
          <a className="btn btn-brass" href="/portal" onClick={(e) => { e.preventDefault(); onNavigate('/portal') }}>Open Campus Club Portal</a>{' '}
          <a className="btn btn-ghost" href="/scenarios" onClick={(e) => { e.preventDefault(); onNavigate('/scenarios') }}>Open Scenario Studio</a>{' '}
          <a className="btn btn-ghost" href="/flow" onClick={(e) => { e.preventDefault(); onNavigate('/flow') }}>Open Flow Inspector</a>
        </p>
      </div>

      {/* IF-V5-06: per-resource request states, each with a timestamp.
          A resource that failed shows ERROR + its error; a resource
          that recovered shows READY and the error is gone.
          Atelier v7: the region is aria-live so a state change is
          announced; on wide screens the four states sit two-across
          (see .resource-states in styles.css) — same four rows, no
          state hidden by the denser layout. */}
      <div className="card resource-states" aria-label="Data request states" aria-live="polite">
        <h2>Data requests</h2>
        <dl className="kv">
          <dt>Lab status</dt><dd><RequestStatePill state={statusRes.state} updatedAt={statusRes.updatedAt} errorAt={statusRes.errorAt} />{statusRes.error ? ` — ${statusRes.error}` : ''}</dd>
          <dt>Scenarios</dt><dd><RequestStatePill state={scenariosRes.state} updatedAt={scenariosRes.updatedAt} errorAt={scenariosRes.errorAt} />{scenariosRes.error ? ` — ${scenariosRes.error}` : ''}</dd>
          <dt>Live logins</dt><dd><RequestStatePill state={liveRes.state} updatedAt={liveRes.updatedAt} errorAt={liveRes.errorAt} />{liveRes.error ? ` — ${liveRes.error}` : ''}</dd>
          <dt>Lab counts</dt><dd><RequestStatePill state={countsRes.state} updatedAt={countsRes.updatedAt} errorAt={countsRes.errorAt} />{countsRes.error ? ` — ${countsRes.error}` : ''}</dd>
        </dl>
        {(statusRes.state === 'ERROR' || statusRes.state === 'STALE' || scenariosRes.state === 'ERROR' || scenariosRes.state === 'STALE' || liveRes.state === 'ERROR' || liveRes.state === 'STALE' || countsRes.state === 'ERROR' || countsRes.state === 'STALE') && (
          <p><button type="button" className="btn btn-ghost" onClick={retryAll}>Retry failed requests</button></p>
        )}
        {(statusRes.state === 'STALE' || liveRes.state === 'STALE' || countsRes.state === 'STALE') && (
          <p className="small muted" role="note">STALE means the numbers below are from an earlier successful load; a newer request failed. They are not current live health. Retry to refresh them.</p>
        )}
      </div>

      {error && <div className="alert alert-error" role="alert">Lab status failed: {error} — the backend may not be running on 127.0.0.1:8000. Scenario runs are <strong>NOT RUN</strong> until the backend responds.</div>}
      {error && <p><button type="button" className="btn btn-ghost" onClick={retryAll}>Retry loading lab status</button></p>}

      <h2 className="section-label">Measured readiness</h2>
      {loading ? (
        <div className="grid" role="status" aria-label="Loading lab health">
          <p className="muted">Measuring lab status…</p>
          <Skeleton height={120} label="Loading backend status" /><Skeleton height={120} label="Loading identity provider status" /><Skeleton height={120} label="Loading last verified login" /><Skeleton height={120} label="Loading live login counts" />
        </div>
      ) : status ? (
        <div className="grid" data-testid="overview-settled" aria-label="Measured readiness">
          <MetricTile label="Backend" value={status.backend === 'ok' ? 'OK' : status.backend} note={`Provider mode: ${status.provider_mode ?? 'unknown'}`} />
          <MetricTile
            label="Identity provider"
            value={status.idp.reachable ? (status.idp.issuer_matches === true ? 'Reachable' : status.idp.issuer_matches === false ? 'Issuer mismatch' : 'Reachable — issuer unknown') : 'Not reachable'}
            note={status.idp.reachable ? (status.idp.issuer_matches === true ? 'Discovery issuer matches the configured issuer.' : status.idp.issuer_matches === false ? 'Discovery issuer does NOT match the configured issuer — real login is NOT RUN.' : 'Discovery reachable; issuer match not determined — real login is NOT RUN.') : `Reason: ${status.idp.reason} — real Keycloak login is NOT RUN.`}
          />
          {/* Atelier v7 (b) / IF-V6-03: when the status fetch is STALE,
              the last verified login is historical, not current — an
              amber past-tense chip ("Last verified at …"), never
              current green. The login did happen; it is simply not a
              live measurement any more. */}
          <MetricTile
            label="Last verified login"
            value={lastLogin ? lastLogin.username : 'NOT RUN'}
            note={lastLogin ? (
              statusRes.state === 'STALE' ? (
                <><span className="stale-chip">Last verified at {new Date(lastLogin.at).toLocaleString()}</span>{' '}· subject {lastLogin.subject.slice(0, 12)}… — historical, not current live health. Retry the data requests above to re-verify.</>
              ) : (
                <>Verified {new Date(lastLogin.at).toLocaleString()} · subject {lastLogin.subject.slice(0, 12)}…</>
              )
            ) : 'No real browser login has completed in this backend process.'}
          />
          {/* Atelier v7 (e): the retained transaction total is the
              hero number; the event total is smaller beneath it.
              Retained totals, never all-time; the sample shown in
              the Flow Inspector holds at most the 20 most recent
              transactions. */}
          <MetricTile
            label="Real Keycloak logins observed"
            value={summary.transactions === null ? 'Unknown' : String(summary.transactions)}
            note={<>{liveLoginSummaryNote(summary)}{liveRes.state === 'STALE' ? <> <span className="stale-chip">Previously measured</span> — these counts are from an earlier successful load, not a current one.</> : null}</>}
          />
          <MetricTile
            label="Scenarios loaded"
            value={scenariosRes.state === 'ERROR' ? 'Unknown' : String(scenarios.length)}
            note={scenariosRes.state === 'ERROR' ? 'Scenario list unavailable — the backend did not return it.' : `${runs.length} runs in this browser · ${passCount} PASS · ${failCount} FAIL/ERROR`}
          />
          <MetricTile label="Docker / Playwright gates" value="Not measured" note="These gates run outside this browser — see Reports & Walkthrough. They are never implied by this page." />
        </div>
      ) : (
        <EmptyState title="Lab status unavailable">The backend did not respond. Start the stack and refresh — nothing below is a measured result.</EmptyState>
      )}

      {/* Atelier v7 (e): live counts, one strip — the retained
          transaction total large, the event total small beneath it.
          The wording keeps the three distinctions in one place:
          transactions vs events, retained vs all-time, and the
          last-20 sample vs the retained total. Unknown stays Unknown. */}
      <div className="card" aria-label="Live login counts">
        <h2>Live login counts</h2>
        {summary.transactions === null ? (
          <p role="status">Unknown — live login evidence could not be loaded. The count is not zero; it was not measured.</p>
        ) : (
          <>
            <p className="count-hero">
              <span className="count-total">{summary.transactions}</span>
              <span className="count-total-label">retained live login transaction{summary.transactions === 1 ? '' : 's'}</span>
              {liveRes.state === 'STALE' && <span className="stale-chip">Previously measured</span>}
            </p>
            <p className="count-sub">
              <strong>{summary.events ?? 'Unknown'} retained event{summary.events === 1 ? '' : 's'}</strong>
              {' '}· {summary.successfulTransactions ?? 'Unknown'} verified successful login{summary.successfulTransactions === 1 ? '' : 's'} (complete timeline ending SESSION_CREATED ok)
              {' '}· recent sample: {summary.displayedTransactions} of at most {LIVE_LOGIN_SAMPLE_LIMIT} transactions shown in the Flow Inspector.
            </p>
            <p className="stale-note">
              Retained totals, not all-time totals — older live-login evidence is pruned at the retention cap
              {summary.eventLimit !== null ? ` (latest ${summary.eventLimit} live-login events)` : ''}.
              {summary.atRetentionLimit ? ' The retained set is AT the cap: older transactions have been evicted.' : ''}
              {summary.source === 'computed' ? ' Totals computed from the fetched sample (this backend did not report retained totals).' : ''}
            </p>
          </>
        )}
      </div>

      <div className="grid2">
        <div className="card">
          <h2>What is genuinely verified</h2>
          <p><ModeBadge mode="DETERMINISTIC OFFLINE FIXTURE" /> Offline fixture scenarios run against the local validator with synthetic keys — no live Keycloak traffic.</p>
          <p><span className="badge badge-live">LIVE KEYCLOAK</span> Real Keycloak login is verified only when the Compose stack is up and a browser login completes. If Keycloak is down, that mode is <strong>NOT RUN</strong>, never faked.</p>
          <p className="small muted">One transaction is one login attempt (one correlation ID). One transaction can contain several recorded events, so the event count is always ≥ the transaction count. The sample shown in the Flow Inspector holds the {LIVE_LOGIN_SAMPLE_LIMIT} most recent transactions.</p>
          {evidenceMissing > 0 && <p><StatusPill tone="warn">{evidenceMissing} run(s) reported evidence NOT SAVED</StatusPill> — their decisions are shown, but the backend could not persist them. See Findings &amp; Evidence.</p>}
        </div>
        <div className="card">
          <h2>Lab status</h2>
          {status ? (
            <dl className="kv">
              <dt>Issuer</dt><dd><span className="code">{status.issuer}</span></dd>
              <dt>Discovery</dt><dd><span className="code">{status.idp.discovery_url}</span></dd>
              <dt>IdP probe</dt><dd>{status.idp.reason}</dd>
              <dt>Synthetic label</dt><dd>{status.synthetic_data_label ?? 'SYNTHETIC LAB DATA — NOT REAL IDENTITY INFORMATION'}</dd>
            </dl>
          ) : <p className="muted">No measured status yet.</p>}
        </div>
      </div>

      <div className="card">
        <h2>Investigation feed — latest runs in this browser</h2>
        {recent.length === 0 ? (
          <p className="muted" role="status">No runs yet. Run scenario I1 (normal login) in the Scenario Studio, then a negative case such as I6 (wrong audience).</p>
        ) : (
          <div className="table-wrap" tabIndex={0} role="region" aria-label="Latest runs table"><table>
            <thead><tr><th scope="col">Scenario</th><th scope="col">Decision</th><th scope="col">Secure</th><th scope="col">Flawed fixture</th><th scope="col">Provenance</th><th scope="col">When</th></tr></thead>
            <tbody>
              {recent.map((r) => (
                <tr key={r.run_id}>
                  <td><strong>{r.scenario_id}</strong> — {r.title}</td>
                  <td><StatusBadge status={r.status} /></td>
                  <td>{r.observed_secure}</td>
                  <td>{r.observed_flawed}</td>
                  <td><ProvenanceBadge provenance={r.evidence_provenance} /></td>
                  <td>{new Date(r.timestamp).toLocaleTimeString()}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
        <p>
          <a className="btn btn-ghost" href="/scenarios" onClick={(e) => { e.preventDefault(); onNavigate('/scenarios') }}>Open Scenario Studio</a>{' '}
          <a className="btn btn-ghost" href="/findings" onClick={(e) => { e.preventDefault(); onNavigate('/findings'); announce('Opened Findings and Evidence') }}>Open Findings &amp; Evidence</a>
        </p>
      </div>

      <div className="card">
        <h2>Guided reviewer path — about 5–10 minutes</h2>
        <p className="small muted">Cedarbridge Campus Club is the fictional portal; Trustline is the research workstation around it. Each step below does real work. A step is marked <strong>Verified</strong> only when this browser holds the evidence for it; otherwise it says <strong>Not run yet</strong> or names the action to take.</p>
        <ol className="reviewer-path">
          {reviewerSteps.map((s) => {
            // Atelier v7 (b) / IF-V6-03: a step whose evidence comes
            // from a fetched resource carries the WS2 'stale' state
            // while that fetch is STALE — it shows an amber
            // past-tense "Previously verified" pill plus its
            // "Last verified at …" evidence, and NO current-green
            // Verified pill. A later successful retry returns it to
            // Verified. Browser-local steps (scenario runs) are
            // unaffected by a stale fetch.
            return (
            <li key={s.title}>
              <strong>{s.title}</strong> — {s.detail}{' '}
              {s.state === 'done'
                  ? <><StatusPill tone="teal">Verified</StatusPill>{s.evidence ? ` ${s.evidence}` : ''}</>
                  : s.state === 'stale'
                    ? <><StatusPill tone="warn">Previously verified</StatusPill>{s.evidence ? ` ${s.evidence}` : ''}</>
                    : s.state === 'mismatch'
                    ? <><StatusPill tone="bad">Issuer mismatch</StatusPill>{s.evidence ? ` ${s.evidence}` : ''}</>
                    : s.state === 'error'
                      ? <><StatusPill tone="bad">Status error</StatusPill>{s.evidence ? ` ${s.evidence}` : ''}</>
                      : s.state === 'todo'
                        ? <><StatusPill tone="neutral">Not run yet</StatusPill>{s.evidence ? ` ${s.evidence}` : ''}</>
                        : <span className="muted">Do this now — no browser record exists for it.</span>}{' '}
              <a href={s.path} onClick={(e) => { e.preventDefault(); onNavigate(s.path) }}>{s.linkLabel}</a>
            </li>
            )
          })}
        </ol>
      </div>

      <div className="card">
        <h2>Start here</h2>
        <p>1. Try the real login in the Campus Club Portal. 2. Run scenario I1 (normal login) in the Scenario Studio, then a negative case such as I6 (wrong audience). 3. Compare secure vs flawed in the comparison view and download the report.</p>
      </div>
    </section>
  )
}
