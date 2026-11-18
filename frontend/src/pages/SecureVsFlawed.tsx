import { useState } from 'react'
import type { RunResult } from '../types'
import { ModelBadge, ProvenanceBadge, StatusBadge } from '../components/Badge'
import { EmptyState, StatusPill } from '../components/ui'

/** Secure vs Flawed: an aligned comparison from ONE real run — same
 *  scenario, same synthetic input, secure decision vs the
 *  single-check-missing flawed fixture. Provenance is shown with every
 *  row. A flawed fixture "accepting" proves the removed check was
 *  load-bearing for that input; it is not an exploit and not a live
 *  login. The state-transition table shows what ACTUALLY happened on
 *  each path (P0-06) — including NOT_MODELED where the flawed path has
 *  no meaningful session model. */

function yesNo(v: boolean | undefined): string {
  return v === true ? 'Yes' : v === false ? 'No' : 'Unknown'
}

export function SecureVsFlawed({ runs }: { runs: RunResult[] }) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const selected = runs.find((r) => r.run_id === selectedId) ?? runs[runs.length - 1]

  return (
    <section aria-label="Secure versus Flawed">
      <p className="eyebrow">Research · Same input, two validators</p>
      <h1>Secure vs Flawed</h1>
      <p className="page-sub">The same attack input, run through two validators: the secure one with every check, and an isolated offline fixture with exactly one check removed.</p>
      <div className="alert alert-info" role="note">
        The flawed variant is a discrete, isolated offline fixture: a validator function with one check deliberately removed, run only inside the test harness. It is <strong>not</strong> a mode of the portal, not a toggle, and not an HTTP endpoint. It can never mint a real session.
      </div>
      {!selected ? (
        <EmptyState title="No runs yet">Run a scenario (for example I2, I3 or I6) in the Scenario Studio to see its secure/flawed comparison.</EmptyState>
      ) : (
        <>
          <div className="card">
            <label htmlFor="compare-run">Run</label>
            <select id="compare-run" value={selected.run_id} onChange={(e) => setSelectedId(e.target.value)}>
              {[...runs].reverse().map((r) => (
                <option key={r.run_id} value={r.run_id}>{r.scenario_id} — {r.title} · {r.timestamp}</option>
              ))}
            </select>
            <p><StatusBadge status={selected.status} /> <ProvenanceBadge provenance={selected.evidence_provenance} /> <ModelBadge status={selected.flawed_model_status} /></p>
            <p className="small muted">Test status {selected.status} means the secure validator behaved as expected for this scenario — for negative scenarios that expected behaviour is a denial. Test status and secure outcome are shown separately: a PASS here never means access was granted.</p>
            <dl className="kv">
              <dt>Provenance</dt><dd>Run <span className="code">{selected.run_id}</span> · {selected.timestamp} · {selected.elapsed_ms} ms</dd>
              <dt>Mode</dt><dd>{selected.mode}</dd>
              <dt>Validation reason</dt><dd><span className="code">{selected.validation_reason}</span></dd>
              <dt>Evidence saved</dt><dd>{selected.evidence_saved === false ? 'NOT SAVED — see Findings' : selected.evidence_saved === true ? 'Yes' : 'Unknown (run predates evidence reporting)'}</dd>
              <dt>Guard omitted (flawed)</dt><dd>{selected.flawed_guard_omitted ? <span className="code">{selected.flawed_guard_omitted}</span> : '—'}</dd>
              <dt>Flawed observed result</dt><dd>{selected.flawed_observed_result || '—'}</dd>
            </dl>
          </div>

          <div className="compare-grid">
            <article className="card" aria-label="Secure variant">
              <h2>Secure variant — all checks on</h2>
              <p><StatusPill tone={selected.observed_secure.includes('reject') || selected.observed_secure.includes('denied') ? 'ok' : 'info'}>{selected.observed_secure}</StatusPill></p>
              <p>Expected outcome: {selected.expected_outcome}</p>
              <p>Resource access: {selected.resource_access_outcome}</p>
              <p className="small muted">This is the validator the real portal uses. A rejection here means no session was created and no protected resource was disclosed.</p>
            </article>
            <article className="card" aria-label="Flawed fixture variant">
              <h2>Flawed fixture — one check removed</h2>
              <p><StatusPill tone="warn">{selected.observed_flawed}</StatusPill></p>
              <p>Same input, same scenario — only the check under test is missing.</p>
              {selected.flawed_model_status === 'NOT_MODELED' && (
                <p className="small muted"><span className="badge badge-notmodeled">NOT MODELED</span> This scenario has no meaningful flawed session path; the flawed decision above is still recorded, but no session was created by the fixture.</p>
              )}
              <p className="small muted">The fixture accepts the input because the one guard that would have caught it is absent. That shows why the guard matters; it does not demonstrate an account takeover, and the fixture cannot reach the portal.</p>
            </article>
          </div>

          <div className="card">
            <h2>State transitions — what actually happened on each path</h2>
            <div className="table-wrap" tabIndex={0} role="region" aria-label="State transitions table"><table>
              <thead><tr><th scope="col">State</th><th scope="col">Secure path</th><th scope="col">Flawed fixture path</th></tr></thead>
              <tbody>
                <tr><td>Session created</td><td className="session-state">{yesNo(selected.secure_session_created)}</td><td className="session-state">{selected.flawed_model_status === 'NOT_MODELED' ? 'Not modeled' : yesNo(selected.flawed_session_created)}</td></tr>
                <tr><td>Session preexisted</td><td className="session-state" colSpan={2}>{yesNo(selected.session_preexisted)} <span className="muted">(shared pre-state for both paths)</span></td></tr>
                <tr><td>Session revoked</td><td className="session-state" colSpan={2}>{yesNo(selected.session_revoked)} <span className="muted">(shared pre-state for both paths)</span></td></tr>
                <tr>
                  <td>Protected resource disclosed</td>
                  <td>No — the secure path disclosed nothing</td>
                  <td>
                    {selected.protected_resource_disclosed === true
                      ? <span className="badge badge-fail">YES — disclosed to an actor who must not have it</span>
                      : selected.protected_resource_disclosed === false ? 'No' : 'Unknown'}
                  </td>
                </tr>
                <tr><td>Decision</td><td>{selected.observed_secure}</td><td>{selected.observed_flawed}</td></tr>
              </tbody>
            </table></div>
          </div>

          <div className="card">
            <h2>Why the results differ</h2>
            <p>The secure validator rejected with reason <span className="code">{selected.validation_reason}</span>; the flawed fixture did not run that check, so it reached <span className="code">{selected.observed_flawed}</span>. The difference is exactly one omitted check — every other check still ran in both variants.</p>
          </div>

          <h2>All runs</h2>
          <div className="table-wrap" tabIndex={0} role="region" aria-label="All runs table">
            <table>
              <thead><tr><th scope="col">Scenario</th><th scope="col">Status</th><th scope="col">Secure variant</th><th scope="col">Flawed fixture</th><th scope="col">Resource access</th><th scope="col">Provenance</th></tr></thead>
              <tbody>
                {[...runs].reverse().map((r) => (
                  <tr key={r.run_id} onClick={() => setSelectedId(r.run_id)} style={{ cursor: 'pointer' }}>
                    <td><strong>{r.scenario_id}</strong><br />{r.title}</td>
                    <td><StatusBadge status={r.status} /></td>
                    <td>{r.observed_secure}</td>
                    <td>{r.observed_flawed}</td>
                    <td>{r.resource_access_outcome}</td>
                    <td><ProvenanceBadge provenance={r.evidence_provenance} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="small muted">Select a row to inspect that run&apos;s comparison above.</p>
        </>
      )}
      <p className="small muted">Read the comparison honestly: a flawed fixture &ldquo;accepting&rdquo; an input proves the removed check was load-bearing for that input — it is not a real-world exploit, and it does not prove an account takeover.</p>
    </section>
  )
}
