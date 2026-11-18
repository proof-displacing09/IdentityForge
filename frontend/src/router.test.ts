import { describe, expect, it } from 'vitest'
import { ROUTES, parseRoute, pathForView } from './router'

describe('parseRoute', () => {
  it('resolves all 12 canonical routes', () => {
    expect(ROUTES).toHaveLength(12)
    for (const r of ROUTES) {
      expect(parseRoute(r.path)?.view).toBe(r.view)
    }
  })
  it('maps / and the empty path to overview', () => {
    expect(parseRoute('/')?.view).toBe('overview')
    expect(parseRoute('')?.view).toBe('overview')
  })
  it('tolerates a trailing slash', () => {
    expect(parseRoute('/portal/')?.view).toBe('portal')
    expect(parseRoute('/scenarios/')?.view).toBe('scenarios')
  })
  it('returns null for unknown paths (404 view)', () => {
    expect(parseRoute('/nope')).toBeNull()
    expect(parseRoute('/portal/extra')).toBeNull()
    expect(parseRoute('/overviewx')).toBeNull()
  })
  it('round-trips view -> path -> view', () => {
    for (const r of ROUTES) {
      expect(parseRoute(pathForView(r.view))?.view).toBe(r.view)
    }
  })
  it('keeps /portal?login=success on the portal route', () => {
    // Query strings are not part of the pathname; the router must not
    // be confused by the callback landing URL.
    expect(parseRoute('/portal')?.view).toBe('portal')
  })
})
