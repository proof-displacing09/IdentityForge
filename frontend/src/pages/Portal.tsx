import { useCallback, useEffect, useState } from 'react'
import { ApiError, getMe, getMember, getOfficer, logout } from '../api'
import type { PortalUser } from '../types'
import { announce, StatusPill } from '../components/ui'

type LoadState = 'loading' | 'signed-in' | 'signed-out' | 'error' | 'expired'

export function Portal() {
  const [state, setState] = useState<LoadState>('loading')
  const [user, setUser] = useState<PortalUser | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [member, setMember] = useState<unknown>(null)
  const [memberError, setMemberError] = useState<string | null>(null)
  const [officer, setOfficer] = useState<unknown>(null)
  const [officerError, setOfficerError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [logoutError, setLogoutError] = useState<string | null>(null)
  const [loginSuccess, setLoginSuccess] = useState(false)

  const loadMe = useCallback(async () => {
    setState('loading'); setError(null)
    try {
      const me = await getMe()
      setUser(me); setState('signed-in')
    } catch (e) {
      const msg = String(e)
      if (/401/.test(msg)) { setState('signed-out'); setUser(null) }
      else if (/expired/i.test(msg)) setState('expired')
      else {
        // IF-V4-13: a network failure (backend down) and a backend
        // server error are different states with different fixes.
        setState('error')
        setError(e instanceof ApiError && e.status >= 500
          ? `Backend returned ${e.status} — the portal could not confirm your session.`
          : /fetch failed|failed to fetch|network/i.test(msg)
            ? 'Could not reach the backend on 127.0.0.1:8000 — is the stack running?'
            : msg)
      }
    }
  }, [])

  useEffect(() => { void loadMe() }, [loadMe])

  // Callback landing: /portal?login=success is set by the backend only
  // after a validated ID token created a session. It is a hint, not
  // proof — /me above is what actually confirms the session.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (params.get('login') === 'success') setLoginSuccess(true)
  }, [])

  useEffect(() => {
    if (state === 'signed-in' && user) announce(`Signed in as ${user.username ?? user.name ?? 'unknown'}`)
  }, [state, user])

  async function fetchMember() {
    setMember(null); setMemberError(null)
    try { setMember(await getMember()); announce('Member resource allowed') } catch (e) { setMemberError(String(e)); announce('Member resource denied') }
  }
  async function fetchOfficer() {
    setOfficer(null); setOfficerError(null)
    try { setOfficer(await getOfficer()); announce('Officer resource allowed') } catch (e) { setOfficerError(String(e)); announce('Officer resource denied') }
  }

  /** Logout (P0-08): success is shown ONLY when the backend returns
   *  200. On failure the session UI stays exactly as it was — the
   *  server session may still be active, and claiming otherwise would
   *  be a false logout. This is APP-LOCAL revocation: it ends this
   *  portal's session, not the identity provider's SSO session. */
  async function doLogout() {
    setBusy(true); setLogoutError(null)
    try {
      await logout()
      setUser(null); setMember(null); setOfficer(null); setState('signed-out')
      announce('Logged out. Portal session revoked.')
    } catch (e) {
      setLogoutError(`Logout failed: ${String(e)}. You are still signed in — the server session was NOT revoked. Try again.`)
      announce('Logout failed. You are still signed in.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section aria-label="Campus Club Portal">
      <div className="portal-hero">
        <span className="crest" aria-hidden="true">
          <svg viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
            <path d="M16 3 27 7v8c0 6.4-4.8 10.8-11 14C9.8 25.8 5 21.4 5 15V7Z" />
            <path d="M11 12.5c1.6-1 3.4-1.5 5-1.5s3.4.5 5 1.5v6c-1.6-1-3.4-1.5-5-1.5s-3.4.5-5 1.5Z" />
            <path d="M16 11v6" />
          </svg>
        </span>
        <div>
          <p className="eyebrow">Cedarbridge Campus Club · Fictional portal</p>
          <h1>Cedarbridge Campus Club</h1>
          <p className="page-sub">Synthetic members only. Sign in uses the local identity provider (Keycloak on 127.0.0.1:8080) via the backend; no tokens are stored in the browser.</p>
        </div>
      </div>

      <div className="alert alert-info" role="note">
        <strong>About sign-in and sign-out.</strong> Signing in happens at the local identity provider and creates a session in <em>this portal</em>.
        Logging out below revokes this portal&apos;s session only — it is <strong>app-local revocation, not IdP SSO logout</strong>: the identity
        provider&apos;s own session is untouched, so returning to the portal may sign you straight back in without a password prompt. That is
        expected behaviour for this lab, not a bug.
      </div>

      {loginSuccess && state === 'signed-in' && (
        <div className="alert alert-teal" role="status">Signed in via the local identity provider — session confirmed by the backend.</div>
      )}
      {logoutError && <div className="alert alert-error" role="alert">{logoutError}</div>}

      {state === 'loading' && <p role="status">Checking your session…</p>}
      {state === 'error' && <div className="alert alert-error" role="alert">Provider unavailable or backend error: {error} — this is an honest error state, not a signed-in session. <button className="btn btn-ghost" onClick={() => void loadMe()}>Retry</button></div>}
      {state === 'expired' && <div className="alert alert-warn" role="alert">Your session has expired. Please sign in again.</div>}

      {state === 'signed-out' && (
        <div className="card card-selected">
          <h2>You are not signed in</h2>
          <p>This is the unauthenticated view: no member content is shown, and member/officer resources are not fetched.</p>
          <p><a className="btn btn-teal" href="/auth/login">Sign in with local identity provider</a></p>
          <p className="small muted">Test identities are provisioned by the Keycloak realm import (for example <span className="code">student_01</span> and <span className="code">officer_01</span>). Passwords are synthetic lab credentials defined in the realm import — see the project README, never share them outside the lab.</p>
        </div>
      )}

      {state === 'signed-in' && user && (
        <>
          <div className="card">
            <h2>Signed-in dashboard</h2>
            <dl className="kv">
              <dt>Username</dt><dd>{user.username ?? user.name ?? 'unknown'}</dd>
              <dt>Subject (iss + sub)</dt><dd><span className="code">{user.sub ?? 'unknown'}</span></dd>
              <dt>Email</dt><dd>{user.email ?? '—'}</dd>
              <dt>Roles</dt><dd>{(user.roles ?? []).join(', ') || 'member'}</dd>
            </dl>
            <p><StatusPill tone="ok">Session verified by /api/v1/portal/me</StatusPill></p>
            <p><button className="btn btn-danger" onClick={() => void doLogout()} disabled={busy}>{busy ? 'Signing out…' : 'Log out'}</button></p>
            <p className="small muted">Logout revokes the server-side portal session; reusing the old cookie afterwards must not resurrect it (scenario I12). It does not end the identity provider&apos;s SSO session.</p>
          </div>
          <div className="grid2">
            <div className="card">
              <h2>Member-only resource</h2>
              <p className="small muted">Any authenticated member may read this.</p>
              <button className="btn" onClick={() => void fetchMember()}>Load member resource</button>
              {member !== null && <pre aria-label="Member resource">{JSON.stringify(member, null, 2)}</pre>}
              {memberError && <div className="alert alert-error" role="alert">Member resource denied: {memberError}</div>}
            </div>
            <div className="card">
              <h2>Officer-only resource</h2>
              <p className="small muted">Only the officer role may read this. A normal student must see a denial — that denial is the authorization test (I13).</p>
              <button className="btn" onClick={() => void fetchOfficer()}>Load officer resource</button>
              {officer !== null && <pre aria-label="Officer resource">{JSON.stringify(officer, null, 2)}</pre>}
              {officerError && <div className="alert alert-error" role="alert">Officer resource denied: {officerError}</div>}
            </div>
          </div>
        </>
      )}
    </section>
  )
}
