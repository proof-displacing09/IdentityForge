import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Settings } from './Settings'

const statusBody = {
  backend: 'ok', issuer: 'http://127.0.0.1:8080/realms/identityforge-lab',
  idp: { reachable: false, issuer_matches: null, discovery_url: 'x', reason: 'NOT RUN' },
  last_verified_login: null,
}
const configBody = { issuer: 'http://127.0.0.1:8080/realms/identityforge-lab', keycloak_url: 'http://127.0.0.1:8080' }
const countsBody = { runs: 5, sessions: 2, sessions_total_issued: 48, live_logins: 1, transactions: 3 }

function ok(body: unknown) {
  return { ok: true, status: 200, statusText: 'OK', json: async () => body, text: async () => '' } as Response
}
function fail(status: number, detail: string) {
  return { ok: false, status, statusText: 'Error', json: async () => ({ detail }), text: async () => JSON.stringify({ detail }) } as Response
}

/** Stub fetch per endpoint. `me` is the /portal/me outcome: an object
 *  (signed in), null (401 = not signed in), or 'error' (network).
 *  `meStatus` overrides the failure status (403 / 500); `meThrow`
 *  makes /portal/me reject like a network failure. */
function stubFetch(opts: {
  me?: Record<string, unknown> | null
  meStatus?: number
  meThrow?: boolean
  status?: Record<string, unknown>
  reset?: (attempt: number) => Response
  countsAfterReset?: Record<string, number>
} = {}) {
  const me = opts.me ?? null
  let resetAttempts = 0
  let countsCalls = 0
  let meCalls = 0
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url === '/api/v1/lab/config') return ok(configBody)
    if (url === '/api/v1/health') return ok({ status: 'ok', service: 'identityforge-backend', version: '1.8.5' })
    if (url === '/api/v1/lab/status') return ok(opts.status ?? statusBody)
    if (url === '/api/v1/portal/me') {
      meCalls += 1
      if (opts.meThrow) throw new TypeError('fetch failed')
      if (me === null) return fail(opts.meStatus ?? 401, opts.meStatus === 403 ? 'forbidden' : opts.meStatus === 500 ? 'server error' : 'unauthenticated')
      return ok(me)
    }
    if (url === '/api/v1/lab/counts') {
      countsCalls += 1
      return ok(countsCalls > 1 && opts.countsAfterReset ? opts.countsAfterReset : countsBody)
    }
    if (url === '/api/v1/csrf-token') return ok({ csrf_token: 'tok-1' })
    if (url === '/api/v1/lab/reset') {
      resetAttempts += 1
      if (opts.reset) return opts.reset(resetAttempts)
      return ok({ status: 'reset', operator: 'officer_01', cleared: countsBody, operator_session_revoked: true, csrf_token: 'tok-2' })
    }
    throw new Error(`unexpected ${url}`)
  }))
  return { get resetAttempts() { return resetAttempts }, get meCalls() { return meCalls } }
}

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('Settings reset card identity states (P0-01, v3)', () => {
  it('officer: button enabled, reset authorized, counts shown', async () => {
    stubFetch({ me: { username: 'officer_01', sub: 'iss|officer_01', roles: ['member', 'officer'] } })
    render(<Settings />)
    expect(await screen.findByText('Signed in as officer_01 — reset authorized')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Reset lab state/ })).toBeEnabled()
    expect(screen.getByText('Runs that would be cleared')).toBeInTheDocument()
    expect(screen.getByText('Active sessions that would be cleared')).toBeInTheDocument()
    expect(screen.getByText('Live login transactions that would be cleared')).toBeInTheDocument()
    expect(screen.getByText('Live login events that would be cleared')).toBeInTheDocument()
    expect(screen.getByText('Transactions that would be cleared')).toBeInTheDocument()
  })

  it('student: button disabled, only an officer can reset, counts shown', async () => {
    stubFetch({ me: { username: 'student_01', sub: 'iss|student_01', roles: ['member'] } })
    render(<Settings />)
    expect(await screen.findByText('Signed in as student_01 — only an officer can reset')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Reset lab state/ })).toBeDisabled()
    expect(screen.getByText('Runs that would be cleared')).toBeInTheDocument()
  })

  it('not signed in: button disabled, sign in as officer to enable, no error banner', async () => {
    stubFetch({ me: null })
    render(<Settings />)
    expect(await screen.findByText('Sign in as officer_01 to enable reset')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Reset lab state/ })).toBeDisabled()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByText('Runs that would be cleared')).toBeInTheDocument()
  })
})

describe('Settings identity truthfulness (P2-23, v4)', () => {
  it('403 identity check: refused, not "not signed in"; reset disabled; retry offered', async () => {
    stubFetch({ me: null, meStatus: 403 })
    render(<Settings />)
    expect(await screen.findByText(/refused the identity check \(403\)/)).toBeInTheDocument()
    expect(screen.queryByText('Sign in as officer_01 to enable reset')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Reset lab state/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: /Retry identity check/ })).toBeEnabled()
  })

  it('network failure: identity unknown, not "not signed in"; reset disabled; retry re-checks', async () => {
    const user = userEvent.setup()
    const stub = stubFetch({ me: null, meThrow: true })
    render(<Settings />)
    expect(await screen.findByText(/Could not reach the backend/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Reset lab state/ })).toBeDisabled()
    const retry = screen.getByRole('button', { name: /Retry identity check/ })
    await user.click(retry)
    expect(stub.meCalls).toBeGreaterThan(1)
  })

  it('500 identity check: server error named, reset disabled, retry offered', async () => {
    stubFetch({ me: null, meStatus: 500 })
    render(<Settings />)
    expect(await screen.findByText(/returned a server error/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Reset lab state/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: /Retry identity check/ })).toBeEnabled()
  })

  it('retry after a transient failure recovers the measured officer identity', async () => {
    const user = userEvent.setup()
    let calls = 0
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/v1/lab/config') return ok(configBody)
      if (url === '/api/v1/lab/status') return ok(statusBody)
      if (url === '/api/v1/lab/counts') return ok(countsBody)
      if (url === '/api/v1/portal/me') {
        calls += 1
        if (calls === 1) throw new TypeError('fetch failed')
        return ok({ username: 'officer_01', sub: 'iss|officer_01', roles: ['member', 'officer'] })
      }
      throw new Error(`unexpected ${url}`)
    }))
    render(<Settings />)
    expect(await screen.findByText(/Could not reach the backend/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Retry identity check/ }))
    expect(await screen.findByText('Signed in as officer_01 — reset authorized')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Reset lab state/ })).toBeEnabled()
  })
})

describe('Settings reset flow (P0-01, v3)', () => {
  it('officer double-confirm succeeds: shows cleared counts, session revoked, counts refresh to zeros, onReset called', async () => {
    const user = userEvent.setup()
    const onReset = vi.fn()
    const stub = stubFetch({
      me: { username: 'officer_01', sub: 'iss|officer_01', roles: ['member', 'officer'] },
      countsAfterReset: { runs: 0, sessions: 0, live_logins: 0, transactions: 0 },
    })
    render(<Settings onReset={onReset} />)
    await screen.findByText('Signed in as officer_01 — reset authorized')
    await user.click(screen.getByRole('button', { name: /Reset lab state/ }))
    await user.click(screen.getByRole('button', { name: 'Yes, reset — continue' }))
    await user.click(screen.getByRole('button', { name: 'Yes, reset now' }))
    expect(await screen.findByText(/Reset confirmed/)).toBeInTheDocument()
    expect(screen.getByText(/Cleared 5 runs, 2 sessions, 1 live login event\(s\) \(transaction count not reported by this backend\) and 3 transactions/)).toBeInTheDocument()
    expect(screen.getByText(/Your officer session was revoked by the reset — sign in again to continue/)).toBeInTheDocument()
    // Counts re-fetched after the reset: now zeros.
    expect(await screen.findByText('Sign in as officer_01 to enable reset')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Reset lab state/ })).toBeDisabled()
    expect(onReset).toHaveBeenCalledTimes(1)
    expect(stub.resetAttempts).toBe(1)
  })

  it('a 403 policy_denied mid-reset fails truthfully and nothing was cleared', async () => {
    const user = userEvent.setup()
    stubFetch({
      me: { username: 'officer_01', sub: 'iss|officer_01', roles: ['member', 'officer'] },
      reset: () => fail(403, 'policy_denied'),
    })
    render(<Settings />)
    await screen.findByText('Signed in as officer_01 — reset authorized')
    await user.click(screen.getByRole('button', { name: /Reset lab state/ }))
    await user.click(screen.getByRole('button', { name: 'Yes, reset — continue' }))
    await user.click(screen.getByRole('button', { name: 'Yes, reset now' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/only an officer can reset/)
    expect(alert).toHaveTextContent(/Nothing was cleared/)
    // The officer is still signed in after a failed reset.
    expect(screen.getByText('Signed in as officer_01 — reset authorized')).toBeInTheDocument()
  })
  it('About shows the backend version read from /api/v1/health, and the retention warning names FIFO eviction', async () => {
    stubFetch({ me: { username: 'officer_01', sub: 'iss|officer_01', roles: ['member', 'officer'] } })
    render(<Settings />)
    expect(await screen.findByText('About this build')).toBeInTheDocument()
    expect(screen.getByText('Backend version')).toBeInTheDocument()
    expect(screen.getByText(/1\.8\.5/)).toBeInTheDocument()
    expect(screen.getByText(/from \/api\/v1\/health/)).toBeInTheDocument()
    expect(screen.getByText('Evidence retention — what is kept, what is pruned')).toBeInTheDocument()
    expect(screen.getByText(/automatically pruned/)).toBeInTheDocument()
    expect(screen.getByText(/Export before eviction/)).toBeInTheDocument()
    expect(screen.getByText(/only manual destructive action/)).toBeInTheDocument()
    expect(screen.getByText(/never contain passwords, client secrets, authorization codes/)).toBeInTheDocument()
  })
})

describe('Settings measured status honesty (IF-V4-13)', () => {
  it('issuer mismatch is named as a mismatch, not hidden behind reachable', async () => {
    stubFetch({
      me: { username: 'officer_01', sub: 'iss|officer_01', roles: ['member', 'officer'] },
      status: { ...statusBody, idp: { reachable: true, issuer_matches: false, discovery_url: 'x', reason: 'ValueError' } },
    })
    render(<Settings />)
    expect(await screen.findByText(/No — MISMATCH/)).toBeInTheDocument()
    expect(screen.getByText(/real login is NOT RUN/)).toBeInTheDocument()
  })

  it('issuer match is stated as Yes when discovery matches', async () => {
    stubFetch({
      me: { username: 'officer_01', sub: 'iss|officer_01', roles: ['member', 'officer'] },
      status: { ...statusBody, idp: { reachable: true, issuer_matches: true, discovery_url: 'x', reason: 'OK' } },
    })
    render(<Settings />)
    expect(await screen.findByText(/Yes — discovery issuer matches/)).toBeInTheDocument()
  })

  it('session count is labelled as active sessions, with total issued shown separately', async () => {
    stubFetch({ me: { username: 'officer_01', sub: 'iss|officer_01', roles: ['member', 'officer'] } })
    render(<Settings />)
    expect(await screen.findByText('Active sessions that would be cleared')).toBeInTheDocument()
    expect(screen.getByText(/active sessions only/)).toBeInTheDocument()
    expect(screen.getByText('Sessions issued since backend start')).toBeInTheDocument()
    expect(screen.getByText('48')).toBeInTheDocument()
    expect(screen.queryByText(/stored records, not live sessions/)).not.toBeInTheDocument()
  })
})

describe('Settings reset during pending identity re-check (IF-V6-06 / P2-06, failing-first)', () => {
  function deferred<T>() {
    let resolve!: (v: T) => void
    let reject!: (e: unknown) => void
    const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
    return { promise, resolve, reject }
  }

  it('officer login → pending re-check → reset disabled until the officer identity is confirmed again', async () => {
    const user = userEvent.setup()
    const officer = { username: 'officer_01', sub: 'iss|officer_01', roles: ['member', 'officer'] }
    const recheck = deferred<Response>()
    let meCalls = 0
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/v1/lab/config') return ok(configBody)
      if (url === '/api/v1/health') return ok({ status: 'ok', service: 'identityforge-backend', version: '1.8.5' })
      if (url === '/api/v1/lab/status') return ok(statusBody)
      if (url === '/api/v1/lab/counts') return ok(countsBody)
      if (url === '/api/v1/portal/me') {
        meCalls += 1
        return meCalls === 1 ? ok(officer) : recheck.promise
      }
      if (url === '/api/v1/csrf-token') return ok({ csrf_token: 'tok-1' })
      throw new Error(`unexpected ${url}`)
    }))
    render(<Settings />)
    expect(await screen.findByText('Signed in as officer_01 — reset authorized')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Reset lab state/ })).toBeEnabled()
    await user.click(screen.getByRole('button', { name: /Re-check identity/ }))
    expect(screen.getByText('Checking who is signed in…')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Reset lab state/ })).toBeDisabled()
    recheck.resolve(ok(officer))
    expect(await screen.findByText('Signed in as officer_01 — reset authorized')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Reset lab state/ })).toBeEnabled()
  })

  it('re-check that fails 401 leaves reset disabled and says sign in as officer', async () => {
    const user = userEvent.setup()
    const officer = { username: 'officer_01', sub: 'iss|officer_01', roles: ['member', 'officer'] }
    const recheck = deferred<Response>()
    let meCalls = 0
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/v1/lab/config') return ok(configBody)
      if (url === '/api/v1/health') return ok({ status: 'ok', service: 'identityforge-backend', version: '1.8.5' })
      if (url === '/api/v1/lab/status') return ok(statusBody)
      if (url === '/api/v1/lab/counts') return ok(countsBody)
      if (url === '/api/v1/portal/me') {
        meCalls += 1
        return meCalls === 1 ? ok(officer) : recheck.promise
      }
      if (url === '/api/v1/csrf-token') return ok({ csrf_token: 'tok-1' })
      throw new Error(`unexpected ${url}`)
    }))
    render(<Settings />)
    expect(await screen.findByText('Signed in as officer_01 — reset authorized')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Re-check identity/ }))
    expect(screen.getByRole('button', { name: /Reset lab state/ })).toBeDisabled()
    recheck.resolve(fail(401, 'unauthenticated'))
    expect(await screen.findByText('Sign in as officer_01 to enable reset')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Reset lab state/ })).toBeDisabled()
  })
})
