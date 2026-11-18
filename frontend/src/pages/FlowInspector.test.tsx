import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { FlowInspector } from './FlowInspector'
import type { RunResult } from '../types'

vi.mock('../api', () => ({
  getLiveLogins: vi.fn(async () => []),
  getRunEvents: vi.fn(async () => []),
}))

function run(overrides: Partial<RunResult> = {}): RunResult {
  return {
    run_id: 'run-i1',
    scenario_id: 'I1',
    title: 'Normal login',
    mode: 'DETERMINISTIC OFFLINE FIXTURE',
    status: 'PASS',
    expected_outcome: 'accept',
    observed_secure: 'accept',
    observed_flawed: 'accept',
    validation_reason: 'OK',
    resource_access_outcome: 'member=allowed; officer=denied',
    timeline: [
      { step: 'AUTHORIZATION_STARTED', outcome: 'ok', reason: 'OK', at: '2026-11-11T07:00:00Z' },
      { step: 'CALLBACK_RECEIVED', outcome: 'ok', reason: 'OK', at: '2026-11-11T07:00:01Z' },
      { step: 'CODE_REDEEMED', outcome: 'ok', reason: 'OK', at: '2026-11-11T07:00:02Z' },
      { step: 'TOKEN_VERIFIED', outcome: 'ok', reason: 'OK', at: '2026-11-11T07:00:03Z' },
      { step: 'SESSION_CREATED', outcome: 'ok', reason: 'OK', at: '2026-11-11T07:00:04Z' },
    ],
    elapsed_ms: 12,
    timestamp: '2026-11-11T07:00:04Z',
    flawed_guard_omitted: 'audience',
    ...overrides,
  }
}

describe('Atlas stage states (P2-20, v4)', () => {
  it('I1 success: all recorded stages VERIFIED, IdP FIXTURE-ONLY, resource from the recorded outcome', () => {
    render(<FlowInspector runs={[run()]} />)
    const atlas = screen.getByRole('list', { name: 'Identity transaction stages' })
    const nodes = within(atlas).getAllByRole('button')
    expect(nodes).toHaveLength(7)
    expect(nodes[0]).toHaveTextContent('VERIFIED')
    expect(nodes[1]).toHaveTextContent('FIXTURE-ONLY')
    expect(nodes[2]).toHaveTextContent('VERIFIED')
    expect(nodes[3]).toHaveTextContent('VERIFIED')
    expect(nodes[4]).toHaveTextContent('VERIFIED')
    expect(nodes[5]).toHaveTextContent('VERIFIED')
    // Resource stage is grounded in the run's recorded
    // resource_access_outcome, shown verbatim as its evidence.
    expect(nodes[6]).toHaveTextContent('7. Resource accessed')
    expect(nodes[6]).toHaveTextContent('VERIFIED')
    expect(nodes[6]).toHaveTextContent('member=allowed; officer=denied')
  })

  it('real backend fixture shape (validator steps only): front stages are FIXTURE-ONLY', () => {
    // The backend engine records only TOKEN_VERIFIED / SESSION_CREATED
    // for a fixture run — the fixture never performs the browser start,
    // callback or code exchange. Those stages are FIXTURE-ONLY, not
    // "not run" as if the run had failed to reach them.
    const realShape = run({
      timeline: [
        { step: 'TOKEN_VERIFIED', outcome: 'ok', reason: 'OK' },
        { step: 'SESSION_CREATED', outcome: 'ok', reason: 'OK' },
      ],
    })
    render(<FlowInspector runs={[realShape]} />)
    const atlas = screen.getByRole('list', { name: 'Identity transaction stages' })
    const nodes = within(atlas).getAllByRole('button')
    expect(nodes[0]).toHaveTextContent('FIXTURE-ONLY')
    expect(nodes[1]).toHaveTextContent('FIXTURE-ONLY')
    expect(nodes[2]).toHaveTextContent('FIXTURE-ONLY')
    expect(nodes[3]).toHaveTextContent('FIXTURE-ONLY')
    expect(nodes[4]).toHaveTextContent('VERIFIED')
    expect(nodes[5]).toHaveTextContent('VERIFIED')
    expect(nodes[6]).toHaveTextContent('VERIFIED')
  })

  it('I6 wrong audience: verify DENIED, later stages NOT REACHED, resource never attempted', () => {
    const i6 = run({
      run_id: 'run-i6',
      scenario_id: 'I6',
      title: 'Wrong audience',
      status: 'FAIL',
      observed_secure: 'reject',
      validation_reason: 'WRONG_AUDIENCE',
      resource_access_outcome: 'no_session',
      timeline: [
        { step: 'AUTHORIZATION_STARTED', outcome: 'ok', reason: 'OK' },
        { step: 'CALLBACK_RECEIVED', outcome: 'ok', reason: 'OK' },
        { step: 'CODE_REDEEMED', outcome: 'ok', reason: 'OK' },
        { step: 'TOKEN_VERIFIED', outcome: 'rejected', reason: 'WRONG_AUDIENCE' },
      ],
    })
    render(<FlowInspector runs={[i6]} />)
    const atlas = screen.getByRole('list', { name: 'Identity transaction stages' })
    const nodes = within(atlas).getAllByRole('button')
    expect(nodes[4]).toHaveTextContent('DENIED')
    expect(nodes[4]).toHaveTextContent('WRONG_AUDIENCE')
    expect(nodes[5]).toHaveTextContent('NOT REACHED')
    expect(nodes[6]).toHaveTextContent('NOT REACHED')
  })

  it('inspector shows timestamp, provenance and the exact omitted check', async () => {
    const user = userEvent.setup()
    render(<FlowInspector runs={[run()]} />)
    const node = screen.getByRole('button', { name: /ID token verified/ })
    await user.click(node)
    const region = screen.getByRole('region', { name: /Details for ID token verified/ })
    expect(within(region).getByText('OFFLINE_FIXTURE — deterministic offline fixture run')).toBeInTheDocument()
    expect(within(region).getByText('audience')).toBeInTheDocument()
    expect(within(region).getByText(/2026/)).toBeInTheDocument()
  })

  it('resource denied only: the resource stage is DENIED with the recorded outcome', () => {
    const denied = run({
      resource_access_outcome: 'member=denied; officer=denied',
      timeline: [
        { step: 'AUTHORIZATION_STARTED', outcome: 'ok', reason: 'OK' },
        { step: 'CALLBACK_RECEIVED', outcome: 'ok', reason: 'OK' },
        { step: 'CODE_REDEEMED', outcome: 'ok', reason: 'OK' },
        { step: 'TOKEN_VERIFIED', outcome: 'ok', reason: 'OK' },
        { step: 'SESSION_CREATED', outcome: 'ok', reason: 'OK' },
      ],
    })
    render(<FlowInspector runs={[denied]} />)
    const atlas = screen.getByRole('list', { name: 'Identity transaction stages' })
    const nodes = within(atlas).getAllByRole('button')
    expect(nodes[6]).toHaveTextContent('DENIED')
    expect(nodes[6]).toHaveTextContent('member=denied; officer=denied')
  })
})

describe('IF-V6-02 live session badge (failing-first: a truncated tail is never SESSION CREATED)', () => {
  const FULL = ['AUTH_STARTED', 'CALLBACK_RECEIVED', 'BINDING_VERIFIED', 'TOKEN_ENDPOINT', 'ID_TOKEN_VALIDATED', 'SESSION_CREATED']
  function liveLogin(correlation_id: string, stages: string[], username = 'student_01') {
    return {
      correlation_id, mode: 'LIVE_KEYCLOAK',
      timeline_complete: stages.length === FULL.length, successful: stages.length === FULL.length,
      events: stages.map((stage, i) => ({
        correlation_id, stage, outcome: 'ok', reason_code: 'OK', subject_hash: 'h', username, detail: '', at: `2026-11-11T10:00:0${i}Z`,
      })),
    }
  }
  async function openLiveTab() {
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Live Keycloak logins' }))
  }

  it('a SESSION_CREATED-ok tail shows SESSION NOT VERIFIED — INCOMPLETE TIMELINE, never SESSION CREATED', async () => {
    const { getLiveLogins } = await import('../api')
    vi.mocked(getLiveLogins).mockResolvedValue([liveLogin('corr-tail', ['SESSION_CREATED'])] as never)
    render(<FlowInspector runs={[run()]} />)
    await openLiveTab()
    expect(await screen.findByText('SESSION NOT VERIFIED — INCOMPLETE TIMELINE')).toBeInTheDocument()
    expect(screen.queryByText('SESSION CREATED', { exact: true })).not.toBeInTheDocument()
    expect(screen.getByText(/Timeline incomplete — missing:/)).toBeInTheDocument()
  })

  it('a complete canonical login shows SESSION CREATED', async () => {
    const { getLiveLogins } = await import('../api')
    vi.mocked(getLiveLogins).mockResolvedValue([liveLogin('corr-full', FULL)] as never)
    render(<FlowInspector runs={[run()]} />)
    await openLiveTab()
    expect(await screen.findByText('SESSION CREATED', { exact: true })).toBeInTheDocument()
    expect(screen.queryByText(/SESSION NOT VERIFIED/)).not.toBeInTheDocument()
  })
})
