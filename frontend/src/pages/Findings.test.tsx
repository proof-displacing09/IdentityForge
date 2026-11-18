import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Findings } from './Findings'
import type { RunResult } from '../types'

const run: RunResult = {
  run_id: 'run-1', scenario_id: 'I6', title: 'Wrong audience', mode: 'DETERMINISTIC OFFLINE FIXTURE',
  status: 'PASS', expected_outcome: 'reject', observed_secure: 'reject', observed_flawed: 'accept',
  validation_reason: 'WRONG_AUDIENCE', resource_access_outcome: 'denied',
  timeline: [], elapsed_ms: 12, timestamp: '2026-11-11T00:00:00Z',
  evidence_saved: true, evidence_provenance: 'OFFLINE_FIXTURE',
}

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300, status, statusText: status === 200 ? 'OK' : 'Error',
    json: async () => body, text: async () => JSON.stringify(body),
  } as Response
}

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

function row(): HTMLElement {
  const el = screen.getByText('I6').closest('tr')
  if (!el) throw new Error('Run row not rendered')
  return el
}

describe('Findings download provenance notices (IF-V4-12)', () => {
  it('CSV download shows the client-derived notice when the server report re-fetch succeeds', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:x'), revokeObjectURL: vi.fn() })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/v1/runs/run-1/report') return jsonResponse(run)
      throw new Error(`unexpected ${url}`)
    }))
    render(<Findings runs={[run]} onClear={() => undefined} />)
    await user.click(within(row()).getByRole('button', { name: 'CSV' }))
    expect(await within(row()).findByText(/Client-derived report/)).toBeInTheDocument()
    expect(within(row()).getByText(/CLIENT-DERIVED/)).toBeInTheDocument()
    expect(within(row()).queryByText(/LOCAL UNSAVED COPY/)).not.toBeInTheDocument()
  })

  it('CSV download shows the LOCAL UNSAVED COPY warning when the server report cannot be fetched', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:x'), revokeObjectURL: vi.fn() })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('backend down') }))
    render(<Findings runs={[run]} onClear={() => undefined} />)
    await user.click(within(row()).getByRole('button', { name: 'CSV' }))
    const notice = await within(row()).findByRole('alert')
    expect(notice).toHaveTextContent(/LOCAL UNSAVED COPY/)
    expect(notice).toHaveTextContent(/LOCAL-UNSAVED-COPY/)
    expect(notice).toHaveTextContent(/not a server-verified report/)
  })

  it('JSON download shows the server-verified note when the backend serves the report', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:x'), revokeObjectURL: vi.fn() })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/v1/runs/run-1/report') return jsonResponse(run)
      throw new Error(`unexpected ${url}`)
    }))
    render(<Findings runs={[run]} onClear={() => undefined} />)
    await user.click(within(row()).getByRole('button', { name: 'JSON' }))
    expect(await within(row()).findByText(/Server-verified artifact/)).toBeInTheDocument()
    expect(within(row()).queryByRole('alert')).not.toBeInTheDocument()
  })

  it('MD download shows the fallback warning when the server report cannot be fetched', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:x'), revokeObjectURL: vi.fn() })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('backend down') }))
    render(<Findings runs={[run]} onClear={() => undefined} />)
    await user.click(within(row()).getByRole('button', { name: 'MD' }))
    const notice = await within(row()).findByRole('alert')
    expect(notice).toHaveTextContent(/LOCAL UNSAVED COPY/)
  })
})
