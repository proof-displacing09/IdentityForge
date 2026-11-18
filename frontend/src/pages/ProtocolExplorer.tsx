import { useState } from 'react'
import type { RunResult } from '../types'
import { EmptyState } from '../components/ui'

/** Protocol Explorer: shows ONLY metadata that actually exists in the
 *  selected run. No placeholder token strings are presented as captured
 *  values — the one illustrative example is explicitly labelled SAMPLE
 *  and contains no real secret material. Copy buttons exist only for
 *  harmless identifiers (issuer, client id, run id, redirect URI) —
 *  never for tokens, codes, verifiers or nonces. */

function CopyButton({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false)
  async function copy() {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
    }
  }
  return (
    <button type="button" className="btn btn-ghost" onClick={() => void copy()} aria-label={`Copy ${label}`}>
      {copied ? 'Copied' : `Copy ${label}`}
    </button>
  )
}

export function ProtocolExplorer({ runs }: { runs: RunResult[] }) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const selected = runs.find((r) => r.run_id === selectedId) ?? runs[runs.length - 1]

  return (
    <section aria-label="Protocol Explorer">
      <p className="eyebrow">Research · Redacted protocol metadata</p>
      <h1>Protocol Explorer</h1>
      <p className="page-sub">Redacted redirect, code-exchange and token-validation steps for one run. Full tokens, authorization codes, PKCE verifiers, nonces and client secrets are <strong>never</strong> displayed — showing them would make the interface impressive and the lab unsafe.</p>
      {!selected ? (
        <EmptyState title="No run yet">Run a scenario first — this view only shows metadata from a run that actually happened.</EmptyState>
      ) : (
        <>
          <div className="card">
            <p><span className="badge badge-fixture">RUN DATA</span> <span className="small muted">Every value below comes from the selected run held in this browser — the run&apos;s own record, not a fresh server verification.</span></p>
            <label htmlFor="protocol-run">Run</label>
            <select id="protocol-run" value={selected.run_id} onChange={(e) => setSelectedId(e.target.value)}>
              {[...runs].reverse().map((r) => (
                <option key={r.run_id} value={r.run_id}>{r.scenario_id} — {r.title} · {r.timestamp}</option>
              ))}
            </select>
            <dl className="kv">
              <dt>Scenario</dt><dd>{selected.scenario_id} — {selected.title}</dd>
              <dt>Mode</dt><dd>{selected.mode}</dd>
              <dt>Run ID</dt><dd><span className="code">{selected.run_id}</span> <CopyButton label="run ID" value={selected.run_id} /></dd>
              <dt>Timestamp</dt><dd>{selected.timestamp} · {selected.elapsed_ms} ms</dd>
              <dt>Validation reason</dt><dd><span className="code">{selected.validation_reason}</span></dd>
              <dt>Secure decision</dt><dd>{selected.observed_secure}</dd>
              <dt>Flawed fixture decision</dt><dd>{selected.observed_flawed}</dd>
              <dt>Resource access</dt><dd>{selected.resource_access_outcome}</dd>
              <dt>Authorization code</dt><dd>Not recorded — single-use codes are never stored or shown.</dd>
              <dt>PKCE verifier</dt><dd>Not recorded — server-side only, never rendered.</dd>
              <dt>ID token</dt><dd>Not rendered — signature and claims are validated server-side; header and payload are not shown.</dd>
            </dl>
            <h3>Harmless identifiers — safe to copy</h3>
            <p>
              <CopyButton label="issuer" value="http://127.0.0.1:8080/realms/identityforge-lab" />{' '}
              <span className="code">http://127.0.0.1:8080/realms/identityforge-lab</span>
            </p>
            <p>
              <CopyButton label="client ID" value="campus-club-portal" />{' '}
              <span className="code">campus-club-portal</span>
            </p>
            <p>
              <CopyButton label="redirect URI" value="http://127.0.0.1:8000/auth/callback" />{' '}
              <span className="code">http://127.0.0.1:8000/auth/callback</span>
            </p>
          </div>
          <div className="card">
            <h2>Validation steps in this run</h2>
            {(selected.timeline ?? []).length ? (
              <div className="table-wrap" tabIndex={0} role="region" aria-label="Validation steps table"><table>
                <thead><tr><th scope="col">Step</th><th scope="col">Outcome</th><th scope="col">Reason</th><th scope="col">Detail</th></tr></thead>
                <tbody>
                  {(selected.timeline ?? []).map((s, i) => (
                    <tr key={i}><td><span className="code">{s.step}</span></td><td>{s.outcome}</td><td>{s.reason ?? s.reason_code ?? '—'}</td><td>{s.detail ?? '—'}</td></tr>
                  ))}
                </tbody>
              </table></div>
            ) : <p>No timeline steps were returned for this run.</p>}
            <p className="small muted">What the validator actually checked: issuer, audience, signature (allowed algorithms only, never alg=none), expiry, nonce/state/PKCE binding, and single-use code/state. See Validation Rules for the full list.</p>
          </div>
          <div className="card">
            <h2>Illustrative example — SAMPLE, not a captured value</h2>
            <p><span className="badge badge-notrun">SAMPLE</span> <span className="small muted">This authorization URL shape was not captured from any login; the values are placeholders.</span></p>
            <pre>{`GET /realms/identityforge-lab/protocol/openid-connect/auth
  ?response_type=code
  &client_id=campus-club-portal
  &redirect_uri=http://127.0.0.1:8000/auth/callback
  &scope=openid
  &state=&lt;random, single-use, browser-bound&gt;
  &nonce=&lt;random, single-use&gt;
  &code_challenge=&lt;SHA-256 of verifier, base64url&gt;
  &code_challenge_method=S256`}</pre>
          </div>
        </>
      )}
    </section>
  )
}
