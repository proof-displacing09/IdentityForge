import { useEffect, useState } from 'react'
import { getMe, getMember, getOfficer } from '../api'
import type { PortalUser } from '../types'
import { announce } from '../components/ui'

/** Identity & Session Boundaries: authentication (who signed in) and
 *  authorization (what they may do) are separate server-side decisions.
 *  The matrix below states the EXPECTED decision for each actor; the
 *  live probe measures the ACTUAL decision with the current browser
 *  session — the two are never conflated. */

const MATRIX: { actor: string; member: string; officer: string; note: string }[] = [
  { actor: 'Anonymous visitor', member: '401 — no session', officer: '401 — no session', note: 'Nothing is disclosed without a session.' },
  { actor: 'student_01 (member)', member: '200 — allowed', officer: '403 — denied', note: 'The denial is the authorization test (I13).' },
  { actor: 'officer_01 (member + officer)', member: '200 — allowed', officer: '200 — allowed', note: 'Both roles come from server-side policy, never a browser claim.' },
]

export function IdentityBoundaries() {
  const [member, setMember] = useState<string | null>(null)
  const [officer, setOfficer] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [me, setMe] = useState<PortalUser | null>(null)
  const [meState, setMeState] = useState<'loading' | 'signed-in' | 'signed-out' | 'error'>('loading')

  useEffect(() => {
    getMe()
      .then((u) => { setMe(u); setMeState('signed-in') })
      .catch((e) => { setMeState(/401/.test(String(e)) ? 'signed-out' : 'error') })
  }, [])

  async function probe() {
    setBusy(true); setMember(null); setOfficer(null)
    try { await getMember(); setMember('Allowed — member resource returned (200).') } catch (e) { setMember(`Denied: ${String(e)}`) }
    try { await getOfficer(); setOfficer('Allowed — officer resource returned (200).') } catch (e) { setOfficer(`Denied: ${String(e)}`) }
    setBusy(false)
    announce('Authorization probe finished.')
  }

  return (
    <section aria-label="Identity and Session Boundaries">
      <p className="eyebrow">Research · Who you are vs what you may do</p>
      <h1>Identity &amp; Session Boundaries</h1>
      <p className="page-sub">Authentication (who signed in) and authorization (what they may do) are separate server-side decisions. A valid ID token proves identity; it never by itself grants officer access. Roles are resolved from trusted server-side policy, not from a claim the browser can edit.</p>

      <div className="card">
        <h2>Current session</h2>
        {meState === 'loading' && <p role="status">Checking your session…</p>}
        {meState === 'signed-out' && <p role="status">You are not signed in — the probe below will be denied for both resources (401).</p>}
        {meState === 'error' && <p role="alert">Could not check your session — the backend did not respond.</p>}
        {meState === 'signed-in' && me && (
          <dl className="kv">
            <dt>Signed in as</dt><dd>{me.username ?? me.name ?? 'unknown'}</dd>
            <dt>Subject</dt><dd><span className="code">{me.sub ?? 'unknown'}</span></dd>
            <dt>Roles</dt><dd>{(me.roles ?? []).join(', ') || 'member'}</dd>
          </dl>
        )}
      </div>

      <div className="card">
        <h2>Expected authorization matrix</h2>
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Authorization matrix"><table>
          <thead><tr><th scope="col">Actor</th><th scope="col">Member resource</th><th scope="col">Officer resource</th><th scope="col">Why</th></tr></thead>
          <tbody>
            {MATRIX.map((row) => (
              <tr key={row.actor}>
                <td><strong>{row.actor}</strong></td>
                <td>{row.member}</td>
                <td>{row.officer}</td>
                <td>{row.note}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
        <p className="small muted">401 means “no valid session” (authentication); 403 means “signed in, but not allowed” (authorization). The two are different decisions — a 403 for a student is the system working, not a failure.</p>
      </div>

      <div className="grid2">
        <div className="card"><h2>Member vs officer</h2><p><strong>student_01</strong> (member): member resource allowed, officer resource denied (I13). <strong>officer_01</strong>: both allowed. An unauthenticated visitor: both denied.</p></div>
        <div className="card"><h2>Session boundaries</h2><p>Sessions are opaque random IDs in HttpOnly cookies; rotation on login prevents fixation (I11); logout revokes the session server-side (I12); expiry is bounded.</p></div>
      </div>
      <div className="card">
        <h2>Live authorization probe</h2>
        <p className="small muted">Calls the real protected endpoints with your current browser session and reports the actual decision — no simulated outcome.</p>
        <button className="btn" onClick={() => void probe()} disabled={busy}>{busy ? 'Probing…' : 'Probe member and officer access'}</button>
        {member && <p role="status">Member: {member}</p>}
        {officer && <p role="status">Officer: {officer}</p>}
      </div>
    </section>
  )
}
