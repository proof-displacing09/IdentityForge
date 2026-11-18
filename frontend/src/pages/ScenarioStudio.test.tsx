import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ScenarioStudio } from './ScenarioStudio'

const scenarios = [
  { id: 'I1', title: 'Normal login', description: 'Happy path.' },
  { id: 'I6', title: 'Wrong audience', description: 'Token for another client.' },
]

function jsonResponse(body: unknown) {
  return { ok: true, status: 200, statusText: 'OK', json: async () => body, text: async () => '' } as Response
}

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('ScenarioStudio', () => {
  it('renders the scenario list from the API', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/v1/csrf-token') return jsonResponse({ csrf_token: 'test-csrf' })
      if (url.includes('/api/v1/scenarios')) return jsonResponse({ scenarios })
      throw new Error(`unexpected ${url}`)
    }))
    render(<ScenarioStudio runs={[]} onRun={() => undefined} selectedId={null} onSelect={() => undefined} />)
    expect(await screen.findByRole('option', { name: /Normal login/ })).toBeInTheDocument()
    expect(await screen.findByRole('option', { name: /Wrong audience/ })).toBeInTheDocument()
    expect(screen.getByRole('listbox', { name: 'Scenarios' })).toBeInTheDocument()
  })

  it('disables the Run button while a run is in progress', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/v1/csrf-token') return jsonResponse({ csrf_token: 'test-csrf' })
      if (url.includes('/api/v1/runs')) return new Promise<Response>(() => undefined) // never resolves
      if (url.includes('/api/v1/scenarios')) return jsonResponse({ scenarios })
      throw new Error(`unexpected ${url}`)
    }))
    render(<ScenarioStudio runs={[]} onRun={() => undefined} selectedId="I1" onSelect={() => undefined} />)
    const runButton = await screen.findByRole('button', { name: /Run I1/ })
    await userEvent.click(runButton)
    expect(await screen.findByRole('button', { name: /Running/ })).toBeDisabled()
  })

  it('shows an honest error state when the API is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('Network error') }))
    render(<ScenarioStudio runs={[]} onRun={() => undefined} selectedId={null} onSelect={() => undefined} />)
    expect(await screen.findByText(/NOT RUN/)).toBeInTheDocument()
  })

  it('sorts by scenario number numerically (I2 before I10), not lexicographically', async () => {
    const outOfOrder = [
      { id: 'I10', title: 'Replay', description: '' },
      { id: 'I2', title: 'Wrong state', description: '' },
      { id: 'I1', title: 'Normal login', description: '' },
    ]
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.includes('/api/v1/scenarios')) return jsonResponse({ scenarios: outOfOrder })
      throw new Error(`unexpected ${url}`)
    }))
    render(<ScenarioStudio runs={[]} onRun={() => undefined} selectedId={null} onSelect={() => undefined} />)
    await screen.findByRole('option', { name: /Normal login/ })
    const options = within(screen.getByRole('listbox', { name: 'Scenarios' })).getAllByRole('option').map((o) => o.textContent ?? '')
    expect(options[0]).toContain('I1')
    expect(options[1]).toContain('I2')
    expect(options[2]).toContain('I10')
  })

  it('sorts by title A–Z when chosen', async () => {
    const user = userEvent.setup()
    const unordered = [
      { id: 'I6', title: 'Wrong audience', description: '' },
      { id: 'I1', title: 'Normal login', description: '' },
      { id: 'I3', title: 'Bad PKCE', description: '' },
    ]
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.includes('/api/v1/scenarios')) return jsonResponse({ scenarios: unordered })
      throw new Error(`unexpected ${url}`)
    }))
    render(<ScenarioStudio runs={[]} onRun={() => undefined} selectedId={null} onSelect={() => undefined} />)
    await screen.findByRole('option', { name: /Normal login/ })
    await user.selectOptions(screen.getByLabelText('Sort scenarios'), 'title')
    const options = within(screen.getByRole('listbox', { name: 'Scenarios' })).getAllByRole('option').map((o) => o.textContent ?? '')
    expect(options[0]).toContain('I3')
    expect(options[1]).toContain('I1')
    expect(options[2]).toContain('I6')
  })

  it('shows the secure outcome next to the test status, not just PASS', async () => {
    const runs = [{
      run_id: 'r1', scenario_id: 'I6', title: 'Wrong audience', mode: 'DETERMINISTIC OFFLINE FIXTURE',
      status: 'PASS', expected_outcome: 'reject', observed_secure: 'reject', observed_flawed: 'accept',
      validation_reason: 'WRONG_AUDIENCE', resource_access_outcome: 'denied',
      timeline: [], elapsed_ms: 5, timestamp: '2026-11-11T00:00:00Z',
    }]
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.includes('/api/v1/scenarios')) return jsonResponse({ scenarios })
      throw new Error(`unexpected ${url}`)
    }))
    render(<ScenarioStudio runs={runs as never} onRun={() => undefined} selectedId={null} onSelect={() => undefined} />)
    const option = await screen.findByRole('option', { name: /Wrong audience/ })
    // PASS is the test result; the secure outcome (a denial) is shown
    // alongside it, so PASS is never read as "access granted".
    expect(option).toHaveTextContent(/PASS/)
    expect(option).toHaveTextContent(/secure: reject/)
    expect(option).toHaveAccessibleName(/I6 — Wrong audience · PASS · secure: reject/)
  })
})
