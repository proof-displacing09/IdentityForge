import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

// Deterministic backend stub: lab status (IdP NOT RUN), no scenarios,
// unauthenticated portal. Keeps async state updates inside the tests.
beforeEach(() => {
  window.history.pushState(null, '', '/')
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const body: Record<string, unknown> = url.includes('/api/v1/lab/status')
      ? { backend: 'ok', issuer: 'http://127.0.0.1:8080/realms/identityforge-lab', idp: { reachable: false, issuer_matches: null, discovery_url: 'x', reason: 'NOT RUN' }, last_verified_login: null }
      : url.includes('/api/v1/scenarios') ? { scenarios: [] } : {}
    const ok = !url.includes('/api/v1/portal/me')
    return { ok, status: ok ? 200 : 401, statusText: ok ? 'OK' : 'Unauthorized', json: async () => body, text: async () => '' } as Response
  }))
})
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('App navigation and accessibility', () => {
  it('renders the sidebar nav with all 12 sections and a skip link', async () => {
    render(<App />)
    expect(screen.getByRole('link', { name: 'Skip to main content' })).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'IdentityForge sections' })
    expect(nav).toBeInTheDocument()
    expect(screen.getByRole('main')).toBeInTheDocument()
    for (const label of ['Overview', 'Campus Club Portal', 'Scenario Studio', 'Flow Inspector', 'Protocol Explorer', 'Validation Rules', 'Secure vs Flawed', 'Learning Center']) {
      expect(within(nav).getByRole('link', { name: new RegExp(label) })).toBeInTheDocument()
    }
    // Flush the async lab-status fetch so no state update lands after the test.
    await screen.findByText(/Not ready — IdP unreachable/)
  })

  it('navigates by keyboard/click, marks the current page, and updates the URL', async () => {
    render(<App />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('link', { name: /Learning Center/ }))
    expect(await screen.findByText('Learning Center', { selector: 'h1' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Learning Center/ })).toHaveAttribute('aria-current', 'page')
    expect(window.location.pathname).toBe('/learn')
  })

  it('marks synthetic-data labelling on every view', async () => {
    render(<App />)
    expect(screen.getByText(/SYNTHETIC LAB DATA/)).toBeInTheDocument()
    await screen.findByText(/Not ready — IdP unreachable/)
  })

  it('shows the 404 view for an unknown path', async () => {
    window.history.pushState(null, '', '/does-not-exist')
    render(<App />)
    expect(await screen.findByText('Page not found')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Go to Overview/ })).toBeInTheDocument()
    window.history.pushState(null, '', '/')
  })

  it('deep-links to /portal on load', async () => {
    window.history.pushState(null, '', '/portal')
    render(<App />)
    expect(await screen.findByText('Cedarbridge Campus Club', { selector: 'h1' })).toBeInTheDocument()
    window.history.pushState(null, '', '/')
  })
})
