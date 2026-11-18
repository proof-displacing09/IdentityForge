import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Portal } from './Portal'

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('Portal unauthenticated state', () => {
  it('shows the unauthenticated view and a real sign-in link when /me returns 401', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false, status: 401, statusText: 'Unauthorized', json: async () => ({}), text: async () => 'unauthorized',
    } as Response)))
    render(<Portal />)
    expect(await screen.findByText('You are not signed in')).toBeInTheDocument()
    const link = screen.getByRole('link', { name: /Sign in with local identity provider/ })
    expect(link).toHaveAttribute('href', '/auth/login')
    // No member content is shown while signed out.
    expect(screen.queryByRole('button', { name: /Load member resource/ })).not.toBeInTheDocument()
  })

  it('shows a signed-in dashboard when /me succeeds', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true, status: 200, statusText: 'OK',
      json: async () => ({ username: 'student_01', sub: 'iss|student_01', roles: ['member'] }),
      text: async () => '',
    } as Response)))
    render(<Portal />)
    expect(await screen.findByText('Signed-in dashboard')).toBeInTheDocument()
    expect(screen.getByText('student_01')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Load officer resource/ })).toBeInTheDocument()
  })

  it('logout succeeds only on backend 200 and then shows the signed-out view', async () => {
    const user = (await import('@testing-library/user-event')).default.setup()
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/v1/csrf-token') return { ok: true, status: 200, statusText: 'OK', json: async () => ({ csrf_token: 'tok' }), text: async () => '' } as Response
      if (url === '/auth/logout') return { ok: true, status: 200, statusText: 'OK', json: async () => ({ status: 'logged_out' }), text: async () => '' } as Response
      return { ok: true, status: 200, statusText: 'OK', json: async () => ({ username: 'student_01', sub: 'iss|student_01', roles: ['member'] }), text: async () => '' } as Response
    }))
    render(<Portal />)
    await screen.findByText('Signed-in dashboard')
    await user.click(screen.getByRole('button', { name: /Log out/ }))
    expect(await screen.findByText('You are not signed in')).toBeInTheDocument()
  })

  it('logout failure keeps the session UI and shows the error (no false logout)', async () => {
    const user = (await import('@testing-library/user-event')).default.setup()
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/v1/csrf-token') return { ok: true, status: 200, statusText: 'OK', json: async () => ({ csrf_token: 'tok' }), text: async () => '' } as Response
      if (url === '/auth/logout') return { ok: false, status: 403, statusText: 'Forbidden', json: async () => ({}), text: async () => 'csrf_denied' } as Response
      return { ok: true, status: 200, statusText: 'OK', json: async () => ({ username: 'student_01', sub: 'iss|student_01', roles: ['member'] }), text: async () => '' } as Response
    }))
    render(<Portal />)
    await screen.findByText('Signed-in dashboard')
    await user.click(screen.getByRole('button', { name: /Log out/ }))
    expect(await screen.findByText(/Logout failed/)).toBeInTheDocument()
    // Session UI is still there: the user is still signed in.
    expect(screen.getByText('Signed-in dashboard')).toBeInTheDocument()
    expect(screen.queryByText('You are not signed in')).not.toBeInTheDocument()
  })
})
