import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Reports } from './Reports'
import type { LabStatus } from '../types'

vi.mock('../api', () => ({
  getLabStatus: vi.fn(),
  getLiveLogins: vi.fn(),
  getLabCounts: vi.fn(),
  downloadText: vi.fn(),
}))

import { getLabCounts, getLabStatus, getLiveLogins } from '../api'

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

function stub(status: LabStatus) {
  vi.mocked(getLabStatus).mockResolvedValue(status)
  vi.mocked(getLiveLogins).mockResolvedValue([])
  vi.mocked(getLabCounts).mockResolvedValue({ runs: 0, sessions: 0, live_logins: 0, transactions: 0 })
}

afterEach(() => { vi.restoreAllMocks() })

/** Walkthrough step 1: 'Start services'. */
function stepOne(): HTMLElement {
  const el = screen.getByText('Start services.').closest('li')
  if (!el) throw new Error('Step 1 not rendered')
  return el
}

describe('Reports walkthrough step 1 (IF-V4-05)', () => {
  it('reachable + issuer mismatch is NOT VERIFIED', async () => {
    stub(statusBody({ issuer_matches: false }))
    render(<Reports runs={[]} />)
    const step = stepOne()
    await within(step).findByText(/NOT VERIFIED — IdP reachable but discovery issuer does NOT match/)
    expect(within(step).queryByText(/Verified — Backend responds; Keycloak discovery is reachable; issuer matches\./)).not.toBeInTheDocument()
  })

  it('reachable + issuer match IS VERIFIED', async () => {
    stub(statusBody({ issuer_matches: true }))
    render(<Reports runs={[]} />)
    const step = stepOne()
    await within(step).findByText(/Verified — Backend responds; Keycloak discovery is reachable; issuer matches\./)
  })

  it('IdP unreachable is NOT RUN', async () => {
    stub(statusBody({ reachable: false, issuer_matches: null, reason: 'PROVIDER_DOWN' }))
    render(<Reports runs={[]} />)
    const step = stepOne()
    await within(step).findByText(/NOT RUN — IdP unreachable \(PROVIDER_DOWN\)\./)
    expect(within(step).queryByText(/Verified/)).not.toBeInTheDocument()
  })

  it('reachable with issuer match undetermined is NOT VERIFIED', async () => {
    stub(statusBody({ issuer_matches: null }))
    render(<Reports runs={[]} />)
    const step = stepOne()
    await within(step).findByText(/NOT VERIFIED — IdP reachable; issuer match not determined\./)
  })
})

describe('Reports reviewer attribution (IF-V6-04, failing-first)', () => {
  const FULL = ['AUTH_STARTED', 'CALLBACK_RECEIVED', 'BINDING_VERIFIED', 'TOKEN_ENDPOINT', 'ID_TOKEN_VALIDATED', 'SESSION_CREATED']
  function fullLogin(correlation_id: string, username: string): unknown {
    return {
      correlation_id, mode: 'LIVE_KEYCLOAK',
      timeline_complete: true, successful: true,
      events: FULL.map((stage, i) => ({
        correlation_id, stage, outcome: 'ok', reason_code: 'OK', subject_hash: 'h', username, detail: '', at: `2026-11-11T10:00:0${i}Z`,
      })),
    }
  }
  function tailLogin(correlation_id: string, username: string): unknown {
    return {
      correlation_id, mode: 'LIVE_KEYCLOAK',
      timeline_complete: false, successful: false,
      events: [{ correlation_id, stage: 'SESSION_CREATED', outcome: 'ok', reason_code: 'OK', subject_hash: 'h', username, detail: '', at: '2026-11-11T10:00:00Z' }],
    }
  }
  function stubLive(logins: unknown[] | Error) {
    vi.mocked(getLabStatus).mockResolvedValue(statusBody({ issuer_matches: true }))
    vi.mocked(getLabCounts).mockResolvedValue({ runs: 0, sessions: 0, live_logins: 0, transactions: 0 })
    if (logins instanceof Error) vi.mocked(getLiveLogins).mockRejectedValue(logins)
    else vi.mocked(getLiveLogins).mockResolvedValue(logins as never)
  }
  function step(text: string): HTMLElement {
    const el = screen.getByText(text).closest('li')
    if (!el) throw new Error(`${text} step not rendered`)
    return el
  }

  it('officer-only: officer step Verified, student step NOT RUN (no generic-count attribution)', async () => {
    stubLive([fullLogin('corr-o', 'officer_01')])
    render(<Reports runs={[]} />)
    // Wait for the live data to land (Atlas step shows the retained count) —
    // the initial empty render already says NOT RUN, which would be vacuous.
    await within(step('Inspect live Atlas events.')).findByText(/1 retained live login transaction/)
    const student = step('Secure student sign-in (Portal).')
    await within(student).findByText(/NOT RUN/)
    expect(within(student).queryByText(/Verified/)).not.toBeInTheDocument()
    const officer = step('Officer sign-in (Portal).')
    expect(within(officer).getByText(/Verified/)).toBeInTheDocument()
  })

  it('student-only: student step Verified, officer step NOT RUN', async () => {
    stubLive([fullLogin('corr-s', 'student_01')])
    render(<Reports runs={[]} />)
    const student = step('Secure student sign-in (Portal).')
    await within(student).findByText(/Verified/)
    const officer = step('Officer sign-in (Portal).')
    expect(within(officer).getByText(/NOT RUN/)).toBeInTheDocument()
    expect(within(officer).queryByText(/Verified/)).not.toBeInTheDocument()
  })

  it('both verified flows: both steps Verified', async () => {
    stubLive([fullLogin('corr-s', 'student_01'), fullLogin('corr-o', 'officer_01')])
    render(<Reports runs={[]} />)
    await within(step('Secure student sign-in (Portal).')).findByText(/Verified/)
    await within(step('Officer sign-in (Portal).')).findByText(/Verified/)
  })

  it('incomplete flow: a SESSION_CREATED tail is NOT a verified sign-in for either user', async () => {
    stubLive([tailLogin('corr-t', 'student_01')])
    render(<Reports runs={[]} />)
    await within(step('Inspect live Atlas events.')).findByText(/1 retained live login transaction/)
    const student = step('Secure student sign-in (Portal).')
    await within(student).findByText(/NOT RUN/)
    expect(within(student).queryByText(/Verified/)).not.toBeInTheDocument()
  })

  it('failed live-login fetch: both sign-in steps say Unknown, never a fake count', async () => {
    stubLive(new Error('backend down'))
    render(<Reports runs={[]} />)
    await within(step('Secure student sign-in (Portal).')).findByText(/Unknown/)
    await within(step('Officer sign-in (Portal).')).findByText(/Unknown/)
  })

  it('matching transaction outside the last-20 sample: "Not confirmed from loaded sample", not Verified and not global NOT RUN', async () => {
    const twenty = Array.from({ length: 20 }, (_, i) => fullLogin(`corr-${i}`, 'officer_01'))
    stubLive(twenty)
    render(<Reports runs={[]} />)
    const student = step('Secure student sign-in (Portal).')
    await within(student).findByText(/Not confirmed from loaded sample/)
    expect(within(student).queryByText(/Verified/)).not.toBeInTheDocument()
  })

  it('resource-authorization step separates login success from authorization proof (member 200 / officer 403 vs 200 / 200)', async () => {
    stubLive([fullLogin('corr-s', 'student_01')])
    render(<Reports runs={[]} />)
    const deny = step('Deny officer as student.')
    await within(deny).findByText(/Login success alone does not prove/)
    expect(within(deny).getByText(/member resource must allow \(200\)/)).toBeInTheDocument()
    expect(within(deny).getByText(/officer resource must deny \(403\)/)).toBeInTheDocument()
    expect(within(deny).getByText(/officer_01.*both must allow \(200 \/ 200\)|both must allow \(200 \/ 200\)/)).toBeInTheDocument()
    expect(within(deny).getByText(/No browser record exists/)).toBeInTheDocument()
  })

  it('start-services step never claims the old sandbox verdict (replaced by IF-V7-01)', async () => {
    stubLive([])
    render(<Reports runs={[]} />)
    const one = stepOne()
    await within(one).findByText(/Verified — Backend responds; Keycloak discovery is reachable; issuer matches\./)
    // The v7 text this replaced — kept here as a regression guard, not
    // as an expectation: none of it may come back.
    expect(within(one).queryByText(/no Docker binary\/socket in this sandbox/)).not.toBeInTheDocument()
    expect(within(one).queryByText(/host-process/)).not.toBeInTheDocument()
    expect(within(one).queryByText(/Docker Compose boot: NOT RUN/)).not.toBeInTheDocument()
    expect(within(one).queryByText(/Reviewer gate on Docker Desktop \(docs\/RELEASE_MANIFEST\.md\)/)).not.toBeInTheDocument()
  })
})

/** IF-V7-01 (failing-first): the release gate is two honest tiers.
 *  (1) A success-shaped /lab/status NEVER implies Compose proof.
 *  (2) The literal sandbox claim appears nowhere in the rendered UI.
 *  (3) No "host-process" deployment-type claim — the API gives no
 *      such fact.
 *  (4) Stale/failed status after earlier success shows no current
 *      green VERIFIED.
 *  (5) No hardcoded PASS/NOT RUN release-gate result in the UI; the
 *      gate tier is UNVERIFIED IN THIS BROWSER with an explicit
 *      reviewer-log reference. */
describe('Reports release-gate honesty (IF-V7-01)', () => {
  it('(1) success-shaped /lab/status NEVER implies Compose proof', async () => {
    stub(statusBody({ issuer_matches: true }))
    render(<Reports runs={[]} />)
    const one = stepOne()
    await within(one).findByText(/Verified — Backend responds; Keycloak discovery is reachable; issuer matches\./)
    expect(within(one).getByText(/a browser status request cannot establish a Docker Compose boot/i)).toBeInTheDocument()
    expect(within(one).getByText(/a responding web app is not Compose proof/i)).toBeInTheDocument()
    expect(within(one).queryByText(/Docker Compose boot: (PASS|NOT RUN)/)).not.toBeInTheDocument()
    expect(within(one).queryByText(/Docker Compose stack up/)).not.toBeInTheDocument()
  })

  it('(2) the sandbox claim appears nowhere in the rendered UI', async () => {
    stub(statusBody({ issuer_matches: true }))
    render(<Reports runs={[]} />)
    await screen.findByText(/Reports & Reviewer Walkthrough/)
    await within(stepOne()).findByText(/Verified — Backend responds/)
    expect(document.body.textContent).not.toMatch(/no Docker binary\/socket in this sandbox/)
    expect(document.body.textContent).not.toMatch(/no Docker binary/)
  })

  it('(3) no host-process deployment-type claim when the API gave no such fact', async () => {
    stub(statusBody({ issuer_matches: true }))
    render(<Reports runs={[]} />)
    const one = stepOne()
    await within(one).findByText(/Verified — Backend responds/)
    expect(within(one).queryByText(/host-process/i)).not.toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/host-process/i)
  })

  it('(4) stale status after earlier success shows no current green VERIFIED', async () => {
    // Status succeeds but live logins fail, so the Retry button is
    // rendered; retrying with status now failing must turn the tier
    // STALE — past-tense, amber, never current green.
    vi.mocked(getLabStatus).mockResolvedValue(statusBody({ issuer_matches: true }))
    vi.mocked(getLiveLogins).mockRejectedValue(new Error('backend down'))
    vi.mocked(getLabCounts).mockResolvedValue({ runs: 0, sessions: 0, live_logins: 0, transactions: 0 })
    render(<Reports runs={[]} />)
    const one = stepOne()
    await within(one).findByText(/Verified — Backend responds; Keycloak discovery is reachable; issuer matches\./)
    vi.mocked(getLabStatus).mockRejectedValue(new Error('backend down'))
    fireEvent.click(screen.getByRole('button', { name: /Retry failed requests/ }))
    await within(one).findByText(/Previously verified/)
    expect(within(one).queryByText(/Verified — Backend responds; Keycloak discovery is reachable; issuer matches\./)).not.toBeInTheDocument()
    expect(one.querySelector('.badge-live')).toBeNull()
    expect(one.querySelector('.stale-chip')).not.toBeNull()
  })

  it('(5) no hardcoded PASS/NOT RUN release-gate result; the gate tier is UNVERIFIED IN THIS BROWSER with a reviewer-log reference', async () => {
    stub(statusBody({ issuer_matches: true }))
    render(<Reports runs={[]} />)
    const one = stepOne()
    await within(one).findByText(/Verified — Backend responds/)
    expect(within(one).getByText(/UNVERIFIED IN THIS BROWSER/)).toBeInTheDocument()
    expect(within(one).getByText(/NOT MEASURED IN THIS VIEW/)).toBeInTheDocument()
    expect(within(one).getByText(/docs\/REVIEWER_GUIDE\.md §7/)).toBeInTheDocument()
    expect(within(one).getByText(/docs\/VERIFICATION_LOG\.md/)).toBeInTheDocument()
    expect(within(one).getByText(/\.\/scripts\/test-all\.sh --full/)).toBeInTheDocument()
    expect(within(one).queryByText(/Docker Compose boot: (PASS|NOT RUN)/)).not.toBeInTheDocument()
    expect(within(one).queryByText(/Docker Compose boot.*NOT RUN/)).not.toBeInTheDocument()
    expect(within(one).queryByText(/Docker Compose boot.*PASS/)).not.toBeInTheDocument()
  })

  it('reproducibility note says the release gate is not measured in this browser, never that it was never executed', async () => {
    stub(statusBody({ issuer_matches: true }))
    render(<Reports runs={[]} />)
    await within(stepOne()).findByText(/Verified — Backend responds/)
    expect(screen.getByText(/Docker Compose boot and Playwright browser E2E are not measured in this browser/)).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/Docker Compose boot and Playwright browser E2E are NOT RUN/)
  })
})
