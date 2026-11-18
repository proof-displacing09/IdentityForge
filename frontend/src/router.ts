import type { ViewId } from './types'

/** Real history routing (P0-09). One canonical path per view; the router
 *  is a pure function over the pathname so it is unit-testable without a
 *  browser. Unknown paths resolve to null and render the 404 view. */

export interface RouteDef {
  path: string
  view: ViewId
  num: string
  label: string
  group: 'Lab' | 'Research' | 'Evidence'
}

export const ROUTES: RouteDef[] = [
  { path: '/overview', view: 'overview', num: '01', label: 'Overview', group: 'Lab' },
  { path: '/portal', view: 'portal', num: '02', label: 'Campus Club Portal', group: 'Lab' },
  { path: '/scenarios', view: 'scenarios', num: '03', label: 'Scenario Studio', group: 'Research' },
  { path: '/flow', view: 'flow', num: '04', label: 'Flow Inspector', group: 'Research' },
  { path: '/protocol', view: 'protocol', num: '05', label: 'Protocol Explorer', group: 'Research' },
  { path: '/rules', view: 'rules', num: '06', label: 'Validation Rules', group: 'Research' },
  { path: '/compare', view: 'compare', num: '07', label: 'Secure vs Flawed', group: 'Research' },
  { path: '/boundaries', view: 'boundaries', num: '08', label: 'Identity & Session Boundaries', group: 'Research' },
  { path: '/findings', view: 'findings', num: '09', label: 'Findings & Evidence', group: 'Evidence' },
  { path: '/reports', view: 'reports', num: '10', label: 'Reports & Walkthrough', group: 'Evidence' },
  { path: '/settings', view: 'settings', num: '11', label: 'Lab Settings', group: 'Lab' },
  { path: '/learn', view: 'learn', num: '12', label: 'Learning Center', group: 'Evidence' },
]

const BY_PATH = new Map(ROUTES.map((r) => [r.path, r]))
const BY_VIEW = new Map(ROUTES.map((r) => [r.view, r]))

function normalise(pathname: string): string {
  // Collapse a trailing slash (except the root) and drop a hash fragment.
  let p = pathname.split('#')[0]
  if (p.length > 1 && p.endsWith('/')) p = p.slice(0, -1)
  return p
}

/** Parse a pathname into a route, or null for unknown paths (404). */
export function parseRoute(pathname: string): RouteDef | null {
  const p = normalise(pathname)
  if (p === '' || p === '/') return BY_PATH.get('/overview') ?? null
  return BY_PATH.get(p) ?? null
}

export function pathForView(view: ViewId): string {
  return BY_VIEW.get(view)?.path ?? '/overview'
}

export function routeForView(view: ViewId): RouteDef | undefined {
  return BY_VIEW.get(view)
}
