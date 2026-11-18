import { render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Overview } from './Overview'
import type { LabStatus } from '../types'

vi.mock('../api', () => ({
  getLabStatus: vi.fn(),
  listScenarios: vi.fn(),
  getLiveLogins: vi.fn(),
  getLabCounts: vi.fn(),
}))

import { getLabCounts, getLabStatus, getLiveLogins, listScenarios } from '../api'

function statusBody(overrides: Partial<LabStatus['idp']> & { backend?: string } = {}): LabStatus {
  const { backend = 'ok', ...idp } = overrides
  return {
    backend,
    issuer: 'http://127.0.0.1:8080/realms/identityforge-lab',
    provider_mode: 'keycloak-local',
    idp: {
      reachable: true, issuer_matches: true,
      discovery_url: 'http://127.0.0.1:8080/realms/identityforge-lab/.well-known/openid-configuration',
      reason: 'OK', ...idp,
    },
    last_verified_login: null,
  }
}

function stub(opts: { status?: LabStatus | Error; scenarios?: unknown[]; scenariosError?: Error; liveLogins?: unknown[]; counts?: unknown } = {}) {
  if (opts.status instanceof Error) vi.mocked(getLabStatus).mockRejectedValue(opts.status)
  else vi.mocked(getLabStatus).mockResolvedValue(opts.status ?? statusBody())
  if (opts.scenariosError) vi.mocked(listScenarios).mockRejectedValue(opts.scenariosError)
  else vi.mocked(listScenarios).mockResolvedValue((opts.scenarios ?? []) as never)
  vi.mocked(getLiveLogins).mockResolvedValue((opts.liveLogins ?? []) as never)
  vi.mocked(getLabCounts).mockResolvedValue((opts.counts ?? { runs: 0, sessions: 0, live_logins: 0, transactions: 0 }) as never)
}

afterEach(() => { vi.restoreAllMocks() })

/** The 'Start services' reviewer step row. */
function servicesStep(): HTMLElement {
  const el = screen.getByText('Start services').closest('li')
  if (!el) throw new Error('Start services step not rendered')
  return el
}

describe('Overview reviewer step 1 (IF-V4-05)', () => {
  it('reachable + issuer mismatch is NOT VERIFIED — named mismatch, never a success shortcut', async () => {
    stub({ status: statusBody({ issuer_matches: false }) })
    render(<Overview runs={[]} onNavigate={() => undefined} />)
    await screen.findByTestId('overview-settled')
    const step = servicesStep()
    expect(within(step).getByText('Issuer mismatch')).toBeInTheDocument()
    expect(within(step).queryByText('Verified', { exact: true })).not.toBeInTheDocument()
    expect(within(step).getByText(/does NOT match the configured issuer/)).toBeInTheDocument()
    // The metric tile agrees: no 'Reachable' success value either.
    const tile = screen.getByText('Identity provider').closest('.metric')!
    expect(tile).toHaveTextContent('Issuer mismatch')
  })

  it('reachable + issuer match + backend ok IS VERIFIED', async () => {
    stub({ status: statusBody({ issuer_matches: true }) })
    render(<Overview runs={[]} onNavigate={() => undefined} />)
    const step = servicesStep()
    await within(step).findByText('Verified')
    expect(within(step).getByText(/IdP discovery reachable — issuer matches/)).toBeInTheDocument()
  })

  it('IdP unreachable is NOT RUN, not verified', async () => {
    stub({ status: statusBody({ reachable: false, issuer_matches: null, reason: 'PROVIDER_DOWN' }) })
    render(<Overview runs={[]} onNavigate={() => undefined} />)
    const step = servicesStep()
    await within(step).findByText('Not run yet')
    expect(within(step).queryByText('Verified', { exact: true })).not.toBeInTheDocument()
  })

  it('reachable with issuer match undetermined is NOT VERIFIED', async () => {
    stub({ status: statusBody({ issuer_matches: null }) })
    render(<Overview runs={[]} onNavigate={() => undefined} />)
    const step = servicesStep()
    await within(step).findByText('Not run yet')
    expect(within(step).queryByText('Verified', { exact: true })).not.toBeInTheDocument()
    const tile = screen.getByText('Identity provider').closest('.metric')!
    expect(tile).toHaveTextContent('Reachable — issuer unknown')
  })

  it('failed status load is an error state, not success', async () => {
    stub({ status: new Error('fetch failed') })
    render(<Overview runs={[]} onNavigate={() => undefined} />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/Lab status failed/)
    const step = servicesStep()
    expect(within(step).getByText('Status error')).toBeInTheDocument()
    expect(within(step).queryByText('Verified', { exact: true })).not.toBeInTheDocument()
  })

  it('backend not ok is NOT VERIFIED even when the IdP answers', async () => {
    stub({ status: statusBody({ backend: 'error', issuer_matches: true }) })
    render(<Overview runs={[]} onNavigate={() => undefined} />)
    const step = servicesStep()
    await within(step).findByText('Not run yet')
    expect(within(step).queryByText('Verified', { exact: true })).not.toBeInTheDocument()
  })

  it('step 1 never claims Docker Compose proof (IF-V7-01)', async () => {
    stub({ status: statusBody({ issuer_matches: true }) })
    render(<Overview runs={[]} onNavigate={() => undefined} />)
    const step = servicesStep()
    await within(step).findByText('Verified')
    expect(step).toHaveTextContent(/Docker Compose cold-start is not measured in this view/)
    expect(step).not.toHaveTextContent(/Docker Compose stack up/)
    expect(step).not.toHaveTextContent(/host-process/)
    expect(step).not.toHaveTextContent(/no Docker binary\/socket in this sandbox/)
  })

  it('step 1 in a non-verified state says readiness is not currently verified (IF-V7-01)', async () => {
    stub({ status: statusBody({ issuer_matches: false }) })
    render(<Overview runs={[]} onNavigate={() => undefined} />)
    const step = servicesStep()
    await within(step).findByText('Issuer mismatch')
    expect(step).toHaveTextContent(/not currently verified/)
    expect(step).toHaveTextContent(/Docker Compose cold-start is not measured in this view/)
    expect(step).not.toHaveTextContent(/Docker Compose stack up/)
    expect(step).not.toHaveTextContent(/host-process/)
  })
})

describe('Overview metric honesty (IF-V4-13)', () => {
  it('a failed scenario list shows Unknown, not a false 0', async () => {
    stub({ scenariosError: new Error('backend down') })
    render(<Overview runs={[]} onNavigate={() => undefined} />)
    await screen.findByTestId('overview-settled')
    const tile = screen.getByText('Scenarios loaded').closest('.metric')!
    expect(tile).toHaveTextContent('Unknown')
    expect(tile).toHaveTextContent(/Scenario list unavailable/)
  })

  it('a loaded scenario list shows its measured count', async () => {
    stub({ scenarios: Array.from({ length: 18 }, (_, i) => ({ id: `I${i + 1}` })) })
    render(<Overview runs={[]} onNavigate={() => undefined} />)
    await screen.findByTestId('overview-settled')
    const tile = screen.getByText('Scenarios loaded').closest('.metric')!
    expect(tile).toHaveTextContent('18')
  })
})

describe('Overview live-login units (IF-V5-02)', () => {
  function liveLogin(correlation_id: string, withSession: boolean) {
    const events: unknown[] = [
      { correlation_id, stage: 'AUTH_STARTED', outcome: 'ok', reason_code: 'OK', subject_hash: 'h', username: 'student_01', detail: '', at: '2026-11-11T10:00:00Z' },
    ]
    if (withSession) events.push({ correlation_id, stage: 'SESSION_CREATED', outcome: 'ok', reason_code: 'OK', subject_hash: 'h', username: 'student_01', detail: '', at: '2026-11-11T10:00:01Z' })
    return { correlation_id, mode: 'LIVE_KEYCLOAK', events }
  }

  it('25 correlations → sample 20 recent, total counter 25; label names the 20-row sample', async () => {
    const sample = Array.from({ length: 20 }, (_, i) => liveLogin(`corr-${i}`, true))
    stub({
      liveLogins: sample,
      counts: { runs: 0, sessions: 0, live_logins: 63, transactions: 0, live_login_transactions: 25, live_login_events: 63, live_login_event_limit: 1000 },
    })
    render(<Overview runs={[]} onNavigate={() => undefined} />)
    await screen.findByTestId('overview-settled')
    const tile = screen.getByText('Real Keycloak logins observed').closest('.metric')!
    expect(tile).toHaveTextContent('25')
    expect(tile).toHaveTextContent('Recent transactions displayed (max 20): 20')
    expect(tile).toHaveTextContent('Retained total, not an all-time total')
  })

  it('more events for an existing login do not inflate the transaction count', async () => {
    const a = liveLogin('corr-a', true)
    a.events.push({ correlation_id: 'corr-a', stage: 'AUTHORIZATION_DECISION', outcome: 'ok', reason_code: 'OK', subject_hash: 'h', username: 'student_01', detail: '', at: '2026-11-11T10:00:02Z' })
    stub({ liveLogins: [a, liveLogin('corr-b', true)] })
    render(<Overview runs={[]} onNavigate={() => undefined} />)
    await screen.findByTestId('overview-settled')
    const tile = screen.getByText('Real Keycloak logins observed').closest('.metric')!
    // 2 transactions, 5 events — the tile value is transactions.
    expect(tile).toHaveTextContent('2')
    expect(tile).toHaveTextContent('5 retained event(s)')
  })

  it('a failed live-login fetch shows Unknown, never a fake zero', async () => {
    stub({ liveLogins: [] })
    vi.mocked(getLiveLogins).mockRejectedValue(new Error('backend down'))
    render(<Overview runs={[]} onNavigate={() => undefined} />)
    await screen.findByTestId('overview-settled')
    const tile = screen.getByText('Real Keycloak logins observed').closest('.metric')!
    expect(tile).toHaveTextContent('Unknown')
    // The per-resource state names the failure and offers a retry.
    expect(screen.getByText('Live logins')).toBeInTheDocument()
    expect(screen.getByText('Retry failed requests')).toBeInTheDocument()
  })
})

describe('Overview request states (IF-V5-06)', () => {
  it('every resource shows an explicit state; a success clears a stale error', async () => {
    stub({})
    render(<Overview runs={[]} onNavigate={() => undefined} />)
    await screen.findByTestId('overview-settled')
    const states = screen.getByLabelText('Data request states')
    expect(within(states).getByText('Lab status')).toBeInTheDocument()
    expect(within(states).getByText('Live logins')).toBeInTheDocument()
    // All four resources READY after a successful load.
    expect(within(states).getAllByText('READY')).toHaveLength(4)
  })
})

describe('Overview stale green VERIFIED (IF-V6-03, failing-first)', () => {
  function deferred<T>() {
    let resolve!: (v: T) => void
    let reject!: (e: unknown) => void
    const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
    return { promise, resolve, reject }
  }
  function reviewerStep(title: string): HTMLElement {
    const el = screen.getByText(title).closest('li')
    if (!el) throw new Error(`${title} step not rendered`)
    return el
  }

  it('READY → retry rejects → STALE: zero current VERIFIED labels, past-tense Last verified chip', async () => {
    const user = (await import('@testing-library/user-event')).default.setup()
    const statusDeferred = deferred<LabStatus>()
    let statusCalls = 0
    vi.mocked(getLabStatus).mockImplementation(() => { statusCalls += 1; return statusCalls === 1 ? statusDeferred.promise : Promise.reject(new Error('backend down')) })
    vi.mocked(listScenarios).mockResolvedValue([])
    vi.mocked(getLiveLogins).mockResolvedValue([])
    vi.mocked(getLabCounts).mockResolvedValue({ runs: 0, sessions: 0, live_logins: 0, transactions: 0 })
    // A different resource in ERROR exposes the retry button that retries ALL resources.
    vi.mocked(listScenarios).mockRejectedValue(new Error('scenarios down'))
    render(<Overview runs={[]} onNavigate={() => undefined} />)
    statusDeferred.resolve(statusBody({ issuer_matches: true }))
    const step = servicesStep()
    await within(step).findByText('Verified')
    await user.click(screen.getByRole('button', { name: /Retry failed requests/ }))
    // After the failed retry the services step must not show a current green Verified.
    await screen.findByText(/Last verified at/)
    expect(within(servicesStep()).queryByText('Verified', { exact: true })).not.toBeInTheDocument()
    // No current-Verified pill anywhere in the reviewer path (the page
    // intro paragraph mentions 'Verified' in prose — that is not a badge).
    const path = document.querySelector('.reviewer-path') as HTMLElement
    expect(within(path).queryByText('Verified', { exact: true })).not.toBeInTheDocument()
    expect(within(servicesStep()).getByText(/Last verified at/)).toBeInTheDocument()
  })

  it('STALE → retry succeeds → READY: Verified returns and the error is cleared', async () => {
    const user = (await import('@testing-library/user-event')).default.setup()
    let statusCalls = 0
    vi.mocked(getLabStatus).mockImplementation(() => {
      statusCalls += 1
      if (statusCalls === 1) return Promise.resolve(statusBody({ issuer_matches: true }))
      if (statusCalls === 2) return Promise.reject(new Error('backend down'))
      return Promise.resolve(statusBody({ issuer_matches: true }))
    })
    vi.mocked(listScenarios).mockRejectedValue(new Error('scenarios down'))
    vi.mocked(getLiveLogins).mockResolvedValue([])
    vi.mocked(getLabCounts).mockResolvedValue({ runs: 0, sessions: 0, live_logins: 0, transactions: 0 })
    render(<Overview runs={[]} onNavigate={() => undefined} />)
    await within(servicesStep()).findByText('Verified')
    await user.click(screen.getByRole('button', { name: /Retry failed requests/ }))
    await screen.findByText(/Last verified at/)
    await user.click(screen.getByRole('button', { name: /Retry failed requests/ }))
    await within(servicesStep()).findByText('Verified')
    expect(screen.queryByText(/Last verified at/)).not.toBeInTheDocument()
  })

  it('READY → retry returns issuer mismatch → WRONG ISSUER, never green', async () => {
    const user = (await import('@testing-library/user-event')).default.setup()
    let statusCalls = 0
    vi.mocked(getLabStatus).mockImplementation(() => {
      statusCalls += 1
      return statusCalls === 1
        ? Promise.resolve(statusBody({ issuer_matches: true }))
        : Promise.resolve(statusBody({ issuer_matches: false }))
    })
    vi.mocked(listScenarios).mockRejectedValue(new Error('scenarios down'))
    vi.mocked(getLiveLogins).mockResolvedValue([])
    vi.mocked(getLabCounts).mockResolvedValue({ runs: 0, sessions: 0, live_logins: 0, transactions: 0 })
    render(<Overview runs={[]} onNavigate={() => undefined} />)
    await within(servicesStep()).findByText('Verified')
    await user.click(screen.getByRole('button', { name: /Retry failed requests/ }))
    const step = servicesStep()
    await within(step).findByText('Issuer mismatch')
    expect(within(step).queryByText('Verified', { exact: true })).not.toBeInTheDocument()
  })

  it('slow status request shows no current Verified until it resolves', async () => {
    const d = deferred<LabStatus>()
    vi.mocked(getLabStatus).mockImplementation(() => d.promise)
    vi.mocked(listScenarios).mockResolvedValue([])
    vi.mocked(getLiveLogins).mockResolvedValue([])
    vi.mocked(getLabCounts).mockResolvedValue({ runs: 0, sessions: 0, live_logins: 0, transactions: 0 })
    render(<Overview runs={[]} onNavigate={() => undefined} />)
    expect(within(servicesStep()).queryByText('Verified', { exact: true })).not.toBeInTheDocument()
    d.resolve(statusBody({ issuer_matches: true }))
    await within(servicesStep()).findByText('Verified')
  })

  it('a truncated SESSION_CREATED tail is NOT a verified student sign-in', async () => {
    const tail = {
      correlation_id: 'corr-tail', mode: 'LIVE_KEYCLOAK',
      events: [{ correlation_id: 'corr-tail', stage: 'SESSION_CREATED', outcome: 'ok', reason_code: 'OK', subject_hash: 'h', username: 'student_01', detail: '', at: '2026-11-11T10:00:00Z' }],
    }
    stub({ liveLogins: [tail] })
    render(<Overview runs={[]} onNavigate={() => undefined} />)
    await screen.findByTestId('overview-settled')
    const step = reviewerStep('Secure student sign-in')
    expect(within(step).queryByText('Verified', { exact: true })).not.toBeInTheDocument()
    expect(within(step).getByText('Not run yet')).toBeInTheDocument()
  })
})
