import { useMemo, useState } from 'react'
import { downloadText, getLabCounts, getLabStatus, getLiveLogins } from '../api'
import type { LabCounts, LabStatus, LiveLogin, RunResult } from '../types'
import { announce } from '../components/ui'
import { useResource } from '../lib/useResource'
import { LIVE_LOGIN_SAMPLE_LIMIT, countTransactions, findVerifiedLogin, summarizeLiveLogins } from '../lib/liveLogins'

/** IF-V6-04 / IF-V6-03: the reviewer walkthrough, with attribution
 *  that cannot drift from the evidence.
 *
 *  - A sign-in step is Verified only for a COMPLETE verified flow
 *    for THAT user (backend canonical assessment: complete timeline
 *    ending SESSION_CREATED ok), never for a generic count of
 *    SESSION_CREATED events, and never for another user's login.
 *  - When the loaded sample (at most 20 recent transactions) holds
 *    no matching verified flow, the step says 'Not confirmed from
 *    loaded sample' — not a global NOT RUN, and not falsely VERIFIED.
 *  - Login success is NOT resource-authorization proof: the deny step
 *    names the member-200 / officer-403 (student) and 200 / 200
 *    (officer) expectations separately, and states that no browser
 *    record exists for them.
 *  - 'Start services' never implies Docker proof from a status
 *    request: the status probe measures only the CURRENT RUNTIME
 *    (backend responds, discovery reachable, issuer matches) when
 *    its resource state is READY, and says so in the past tense
 *    when STALE. The Docker Compose cold-start gate is a SEPARATE
 *    tier that this browser cannot measure: it is labelled
 *    UNVERIFIED IN THIS BROWSER / NOT MEASURED IN THIS VIEW, with
 *    a pointer to the separately executed gate and log
 *    (docs/REVIEWER_GUIDE.md §7, docs/VERIFICATION_LOG.md) — never
 *    a categorical PASS or NOT RUN, and never a claim about how
 *    the stack was deployed, which the API does not report.
 *  - READY is a NECESSARY condition for a CURRENT Verified label:
 *    STALE data is past-tense 'Previously observed — last verified
 *    at …', never current green. */
export function Reports({ runs }: { runs: RunResult[] }) {
  const i1 = runs.find((r) => r.scenario_id === 'I1')
  const i6 = runs.find((r) => r.scenario_id === 'I6')
  const i3 = runs.find((r) => r.scenario_id === 'I3')
  const [packMsg, setPackMsg] = useState<string | null>(null)
  const [summaryMsg, setSummaryMsg] = useState<string | null>(null)
  const statusRes = useResource((signal) => getLabStatus(signal))
  const liveRes = useResource((signal) => getLiveLogins(signal))
  const countsRes = useResource((signal) => getLabCounts(signal))

  const status: LabStatus | null = statusRes.data
  const liveLogins: LiveLogin[] = liveRes.data ?? []
  const counts: LabCounts | null = countsRes.data
  const liveError = liveRes.state === 'ERROR' ? liveRes.error : null

  const distinctScenarios = new Set(runs.map((r) => r.scenario_id)).size
  // IF-V6-02: one canonical summary — successful transactions are
  // complete timelines ending SESSION_CREATED ok, never the
  // SESSION_CREATED event-exists shortcut.
  const liveSummary = useMemo(
    () => summarizeLiveLogins(liveRes.data, counts),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [liveRes.data, countsRes.data],
  )

  function retryAll() {
    statusRes.retry(); liveRes.retry(); countsRes.retry()
  }

  /** Step 1, tier 1 (IF-V7-01): CURRENT RUNTIME only. The status
   *  request measures that the backend responds, Keycloak discovery
   *  is reachable and the issuer matches — nothing about how the
   *  stack was deployed, and nothing about a Docker Compose boot.
   *  READY is necessary for a current Verified; STALE is past
   *  tense, never current green. */
  function startServicesText(): string {
    if (statusRes.state === 'ERROR') return 'Lab status could not be loaded — backend/IdP readiness is Unknown, not verified.'
    if (!status) return 'Lab status not loaded yet.'
    if (status.backend === 'ok' && status.idp.reachable && status.idp.issuer_matches === true) {
      return statusRes.state === 'READY'
        ? 'Verified — Backend responds; Keycloak discovery is reachable; issuer matches.'
        : `Previously observed — Backend responded; Keycloak discovery was reachable; issuer matched; last verified at ${statusRes.updatedAt?.toLocaleString() ?? 'unknown time'}. A newer status request failed, so this is not current live health.`
    }
    if (status.idp.reachable && status.idp.issuer_matches === false) return 'NOT VERIFIED — IdP reachable but discovery issuer does NOT match the configured issuer.'
    if (status.idp.reachable) return 'NOT VERIFIED — IdP reachable; issuer match not determined.'
    return `NOT RUN — IdP unreachable (${status.idp.reason}).`
  }

  /** Step 1, tier 1 badge (IF-V7-01): a short label for the measured
   *  runtime state. Teal only for a current READY verification;
   *  amber stale-chip for past-tense data; neutral for unknown or
   *  unmeasured. The release gate never gets a coloured badge here
   *  — it is not measured in this view at all. */
  function runtimeBadge(): { className: string; label: string } {
    const runtimeOk = status !== null && status.backend === 'ok' && status.idp.reachable && status.idp.issuer_matches === true
    if (statusRes.state === 'READY' && runtimeOk) return { className: 'badge badge-live', label: 'Verified' }
    if (statusRes.state === 'STALE' && runtimeOk) return { className: 'stale-chip', label: 'Previously verified' }
    if (status !== null && status.idp.reachable && status.idp.issuer_matches !== true) return { className: 'badge badge-error', label: 'NOT VERIFIED' }
    if (statusRes.state === 'ERROR' || !status) return { className: 'badge badge-notrun', label: 'Unknown' }
    return { className: 'badge badge-notrun', label: 'NOT RUN' }
  }

  /** Steps 2/4: Verified only for a complete verified flow for THAT
   *  user in the loaded sample; otherwise NOT RUN, or — when the
   *  sample is full (20) — 'Not confirmed from loaded sample'. */
  function loginStepText(username: string): string {
    if (liveRes.state === 'ERROR') return 'Live login evidence unavailable — count is Unknown.'
    const verified = findVerifiedLogin(liveLogins, username)
    if (verified) {
      return liveRes.state === 'READY'
        ? `Verified — ${username} completed a verified live login (complete timeline ending SESSION_CREATED ok).`
        : `Previously observed — ${username} completed a verified live login; last verified at ${liveRes.updatedAt?.toLocaleString() ?? 'unknown time'}. Not current live health.`
    }
    const displayed = countTransactions(liveLogins)
    if (displayed >= LIVE_LOGIN_SAMPLE_LIMIT) {
      return `Not confirmed from loaded sample — no verified ${username} login in the ${displayed} most recent transactions loaded; the matching transaction may be older than the sample. This is not a global NOT RUN, and it is not verified.`
    }
    return `NOT RUN yet — no verified ${username} login in the loaded sample.`
  }

  function downloadPack() {
    const pack = {
      origin: 'browser_cache',
      note: 'Evidence pack assembled in this browser from runs held in localStorage. Each run carries its own provenance; runs with evidence_saved=false were not persisted by the backend.',
      exported_at: new Date().toISOString(),
      run_count: runs.length,
      runs,
    }
    downloadText(`identityforge-evidence-pack-${new Date().toISOString().slice(0, 10)}.json`, JSON.stringify(pack, null, 2), 'application/json')
    setPackMsg(`Evidence pack downloaded (${runs.length} runs, origin=browser_cache).`)
    announce('Evidence pack downloaded.')
  }

  /** Portfolio evidence summary (P2-23): privacy-safe, exportable,
   *  and honest about provenance. No tokens, codes, verifiers or raw
   *  subjects — live logins appear only as counts and synthetic
   *  usernames. Authorship is stated plainly: this lab was built with
   *  AI-assisted development, so no claim of sole manual authorship
   *  is made; every claim here is backed by the run evidence it
   *  contains. */
  function downloadSummary() {
    const byScenario = new Map<string, RunResult>()
    for (const r of runs) byScenario.set(r.scenario_id, r)
    const summary = {
      origin: 'browser_cache',
      exported_at: new Date().toISOString(),
      project: 'IdentityForge — Operation Trustline (OAuth/OIDC attack laboratory, synthetic local lab)',
      authorship_note: 'Built with AI-assisted development (Muse, Meta\'s personal AI agent). Code authorship is not claimed as solely manual. Every claim in this summary is backed by the run evidence it contains — verify it against the runs, do not take it on trust.',
      privacy_note: 'Contains no tokens, authorization codes, PKCE verifiers, nonces, passwords or raw subject identifiers. Live logins are reported as counts and synthetic usernames only.',
      lab: {
        issuer: status?.issuer ?? 'unknown',
        provider_mode: status?.provider_mode ?? 'unknown',
        idp_reachable: status?.idp.reachable ?? null,
        idp_reason: status?.idp.reason ?? 'NOT RUN',
        last_verified_login: status?.last_verified_login ? { username: status.last_verified_login.username, at: status.last_verified_login.at } : null,
      },
      runs: {
        total: runs.length,
        distinct_scenarios: distinctScenarios,
        pass: runs.filter((r) => r.status === 'PASS').length,
        fail_or_error: runs.filter((r) => r.status === 'FAIL' || r.status === 'ERROR').length,
        evidence_not_saved: runs.filter((r) => r.evidence_saved === false).length,
      },
      live_keycloak: {
        // IF-V6-02: transactions and events are separate units; the
        // sample holds at most the 20 most recent transactions.
        // Successful = complete timeline ending SESSION_CREATED ok.
        transactions_retained: liveSummary.transactions,
        events_retained: liveSummary.events,
        transactions_verified_successful: liveSummary.successfulTransactions,
        transactions_verified_successful_source: liveSummary.source === 'server' ? 'server counts (backend canonical assessment)' : liveSummary.source === 'computed' ? 'computed from the fetched sample with the canonical assessment' : 'unknown — live login evidence could not be loaded',
        recent_transactions_displayed_max: 20,
        recent_transactions_displayed: countTransactions(liveLogins),
        totals_source: liveSummary.source === 'server' ? 'server counts (retained totals)' : liveSummary.source === 'computed' ? 'computed from the fetched sample of at most 20 recent transactions' : 'unknown — live login evidence could not be loaded',
        retention_note: 'Retained totals, not all-time totals: older live-login evidence is pruned at the retention cap (latest 1000 live-login events).',
        usernames: [...new Set(liveLogins.flatMap((l) => l.events.map((e) => e.username)))],
      },
      gates_not_measured_in_browser: 'Docker Compose boot and Playwright browser E2E are not measured in this browser; they are recorded in docs/VERIFICATION_LOG.md and run via ./scripts/test-all.sh --full — see docs/REVIEWER_GUIDE.md §7 for the reviewer gate.',
      latest_per_scenario: [...byScenario.values()].map((r) => ({
        scenario_id: r.scenario_id, title: r.title, status: r.status,
        observed_secure: r.observed_secure, validation_reason: r.validation_reason,
        evidence_provenance: r.evidence_provenance ?? 'unknown',
        evidence_saved: r.evidence_saved ?? 'unknown', timestamp: r.timestamp,
      })),
    }
    downloadText(`identityforge-portfolio-summary-${new Date().toISOString().slice(0, 10)}.json`, JSON.stringify(summary, null, 2), 'application/json')
    setSummaryMsg(`Portfolio summary downloaded (${runs.length} runs, ${liveSummary.transactions === null ? 'Unknown' : liveSummary.transactions} retained live login transaction(s), ${liveSummary.events === null ? 'Unknown' : liveSummary.events} retained event(s)).`)
    announce('Portfolio evidence summary downloaded.')
  }

  return (
    <section aria-label="Reports and Reviewer Walkthrough">
      <p className="eyebrow">Evidence · For a reviewer</p>
      <h1>Reports &amp; Reviewer Walkthrough</h1>
      <p className="page-sub">A 5–10 minute guided path for a reviewer. Each step below is checked against runs actually performed in this browser; steps without a run are marked NOT RUN, not passed. Each step also names who performs it and where it runs — a step is person- and environment-specific, not generic.</p>
      {(statusRes.state === 'ERROR' || statusRes.state === 'STALE' || liveRes.state === 'ERROR' || liveRes.state === 'STALE' || countsRes.state === 'ERROR' || countsRes.state === 'STALE') && (
        <p><button type="button" className="btn btn-ghost" onClick={retryAll}>Retry failed requests</button>{liveError ? ` — live login evidence: ${liveError}` : ''}</p>
      )}
      <ol>
        <li><strong>Start services.</strong><span className="step-context"><span className="chip chip-persona">reviewer</span><span className="chip chip-env-live">live stack</span></span> Backend and Keycloak readiness, measured by <code>/api/v1/lab/status</code>.
          <div className="evidence-tiers">
            <p className="evidence-tier"><span className="evidence-tier-label">Current runtime — measured in this browser</span> <span className={runtimeBadge().className} role="status">{runtimeBadge().label}</span> <span>{startServicesText()}</span>{statusRes.state === 'READY' && statusRes.updatedAt && <span className="provenance">Measured by <code>/api/v1/lab/status</code> at {statusRes.updatedAt.toLocaleString()}.</span>}</p>
            <p className="evidence-tier"><span className="evidence-tier-label">Release gate — Docker Compose cold-start</span> <span className="badge badge-notrun" role="status">UNVERIFIED IN THIS BROWSER</span> <span>Docker Compose cold-start and in-image readiness: NOT MEASURED IN THIS VIEW. A browser status request cannot establish a Docker Compose boot, and a responding web app is not Compose proof. See the separately executed test gate and log: <code>docs/REVIEWER_GUIDE.md §7</code> and <code>docs/VERIFICATION_LOG.md</code> — run <code>./scripts/test-all.sh --full</code>.</span></p>
          </div>
        </li>
        <li><strong>Secure student sign-in (Portal).</strong><span className="step-context"><span className="chip chip-persona">student_01</span><span className="chip chip-env-live">live Keycloak</span></span> Sign in as student_01 via the real local Keycloak. {loginStepText('student_01')}</li>
        <li><strong>Deny officer as student.</strong><span className="step-context"><span className="chip chip-persona">student_01</span><span className="chip chip-env-live">live Keycloak</span></span> Login success alone does not prove resource authorization — a login only proves a session was created; the authorization decision is made separately on every resource request. No browser record exists for this step. Check in the Portal: as student_01, the member resource must allow (200) and the officer resource must deny (403); as officer_01, both must allow (200 / 200). Do it and watch the denial.</li>
        <li><strong>Officer sign-in (Portal).</strong><span className="step-context"><span className="chip chip-persona">officer_01</span><span className="chip chip-env-live">live Keycloak</span></span> Sign in as officer_01; both resources must be allowed. {loginStepText('officer_01')}</li>
        <li><strong>Run I1–I18 offline cases.</strong><span className="step-context"><span className="chip chip-persona">reviewer</span><span className="chip chip-env-fixture">offline fixture</span></span> {distinctScenarios > 0 ? `${distinctScenarios} of 18 scenarios run in this browser.` : 'NOT RUN yet.'} Normal login (I1): {i1 ? `${i1.status} — ${i1.observed_secure}` : 'NOT RUN yet.'} Wrong audience (I6): {i6 ? `${i6.status} — ${i6.observed_secure}` : 'NOT RUN yet.'} Wrong PKCE verifier (I3): {i3 ? `${i3.status} — ${i3.observed_secure}` : 'NOT RUN yet.'}</li>
        <li><strong>Inspect live Atlas events.</strong><span className="step-context"><span className="chip chip-persona">reviewer</span><span className="chip chip-env-live">live Keycloak</span></span> Open the Flow Inspector and switch to the Live Keycloak tab. {liveError ? 'Live login evidence unavailable — count is Unknown.' : liveSummary.transactions !== null && liveSummary.transactions > 0 ? `${liveSummary.transactions} retained live login transaction(s) (${liveSummary.events ?? 'Unknown'} event(s)); the sample shows the 20 most recent transactions.${liveRes.state === 'STALE' ? ` Previously observed — last verified at ${liveRes.updatedAt?.toLocaleString() ?? 'unknown time'}; not current live health.` : ''}` : 'NOT RUN yet — no live login timelines.'}</li>
        <li><strong>Compare one missing-check model.</strong><span className="step-context"><span className="chip chip-persona">reviewer</span><span className="chip chip-env-fixture">offline fixture</span></span> In Secure vs Flawed, pick a scenario and read what the single omitted check actually changes. {runs.length > 0 ? 'A run exists to compare.' : 'Run a scenario first.'}</li>
        <li><strong>Export redacted evidence.</strong><span className="step-context"><span className="chip chip-persona">reviewer</span><span className="chip chip-env-fixture">exports</span></span> Download a JSON/CSV/Markdown report from Findings &amp; Evidence and check the run_id, timestamps, expected vs observed fields, and reason codes match what you saw.</li>
      </ol>
      <div className="card">
        <h2>Reviewer tour</h2>
        <p>1. <strong>Overview</strong> — check the measured lab status (backend, IdP discovery, last verified login) before trusting anything below it.</p>
        <p>2. <strong>Portal</strong> — sign in as student_01, confirm member 200 / officer 403, log out, confirm the stale session is denied (401).</p>
        <p>3. <strong>Scenario Studio</strong> — run I1, I6 and I3; read each run&apos;s session &amp; model state, not just PASS/FAIL.</p>
        <p>4. <strong>Flow Inspector</strong> — open the I6 run, watch the Atlas stop at the ID-token verification node with reason WRONG_AUDIENCE; switch to the Live Keycloak tab after a real login.</p>
        <p>5. <strong>Findings &amp; Evidence</strong> — download one JSON report and confirm its run_id and reason code match the run you saw.</p>
      </div>
      <div className="card">
        <h2>Portfolio evidence summary</h2>
        <p className="small muted">One privacy-safe JSON file for a portfolio reviewer: run counts and latest outcomes per scenario, live-login counts (synthetic usernames only), lab status, and the gates that were <strong>not</strong> measured in this browser. No tokens, codes, verifiers or raw subjects. The file states plainly that this lab was built with AI-assisted development — authorship is not claimed as solely manual.</p>
        <button className="btn" onClick={downloadSummary} disabled={runs.length === 0 && liveLogins.length === 0}>Download portfolio summary</button>
        {summaryMsg && <p role="status">{summaryMsg}</p>}
        {runs.length === 0 && liveLogins.length === 0 && <p className="small muted">No runs or live logins yet — nothing to summarise.</p>}
      </div>
      <div className="card">
        <h2>Evidence pack</h2>
        <p className="small muted">Downloads every run held in this browser as one JSON file (origin=browser_cache). Per-run server reports are available in Findings &amp; Evidence.</p>
        <button className="btn" onClick={downloadPack} disabled={runs.length === 0}>Download evidence pack ({runs.length} runs)</button>
        {packMsg && <p role="status">{packMsg}</p>}
        {runs.length === 0 && <p className="small muted">No runs yet — nothing to pack.</p>}
      </div>
      <div className="card">
        <h2>Reproducibility</h2>
        <p>Every report carries run_id, scenario_id, mode, fixture revision, provider, timestamp and elapsed time. Re-running the same scenario should produce the same decision (PASS/FAIL) even though run IDs and timestamps differ. Concurrent/replay scenarios (I7, I10) are repeated by the backend test suite; the UI runs each scenario once per click.</p>
        <p className="small muted">Historical evidence: runs saved in this browser are labelled PREVIOUS SAVED EVIDENCE in the Findings view; they are not live provider traffic. Docker Compose boot and Playwright browser E2E are not measured in this browser — they are recorded in docs/VERIFICATION_LOG.md and run via ./scripts/test-all.sh --full; see docs/REVIEWER_GUIDE.md §7 for the reviewer gate.</p>
      </div>
    </section>
  )
}
