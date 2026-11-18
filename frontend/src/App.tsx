import { Suspense, lazy, useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import type { LabStatus, RunResult, ViewId } from './types'
import { getLabStatus } from './api'
import { clearRuns, loadRuns, saveRuns } from './lib/history'
import { ROUTES, parseRoute } from './router'
import { StatusPill } from './components/ui'
// P2-24: route-level code splitting — each view is its own chunk, so
// the first load on an 8 GB laptop is the shell plus the one view
// actually open, not all twelve. Suspense shows a real loading state.
const Overview = lazy(() => import('./pages/Overview').then((m) => ({ default: m.Overview })))
const Portal = lazy(() => import('./pages/Portal').then((m) => ({ default: m.Portal })))
const ScenarioStudio = lazy(() => import('./pages/ScenarioStudio').then((m) => ({ default: m.ScenarioStudio })))
const FlowInspector = lazy(() => import('./pages/FlowInspector').then((m) => ({ default: m.FlowInspector })))
const ProtocolExplorer = lazy(() => import('./pages/ProtocolExplorer').then((m) => ({ default: m.ProtocolExplorer })))
const ValidationRules = lazy(() => import('./pages/ValidationRules').then((m) => ({ default: m.ValidationRules })))
const SecureVsFlawed = lazy(() => import('./pages/SecureVsFlawed').then((m) => ({ default: m.SecureVsFlawed })))
const IdentityBoundaries = lazy(() => import('./pages/IdentityBoundaries').then((m) => ({ default: m.IdentityBoundaries })))
const Findings = lazy(() => import('./pages/Findings').then((m) => ({ default: m.Findings })))
const Reports = lazy(() => import('./pages/Reports').then((m) => ({ default: m.Reports })))
const Settings = lazy(() => import('./pages/Settings').then((m) => ({ default: m.Settings })))
const Learning = lazy(() => import('./pages/Learning').then((m) => ({ default: m.Learning })))

/** Custom Atelier glyphs (P2-20): one geometric mark per section,
 *  drawn as inline SVG — no emoji, no stock icon font. */
const NAV_ICONS: Record<ViewId, ReactNode> = {
  overview: <><rect x="1.5" y="1.5" width="5" height="5" rx="1" /><rect x="9.5" y="1.5" width="5" height="5" rx="1" /><rect x="1.5" y="9.5" width="5" height="5" rx="1" /><rect x="9.5" y="9.5" width="5" height="5" rx="1" /></>,
  portal: <><path d="M3 14V3.5A1.5 1.5 0 0 1 4.5 2h7A1.5 1.5 0 0 1 13 3.5V14" /><path d="M6 14V8h4v6" /><circle cx="10.6" cy="11" r="0.4" fill="currentColor" stroke="none" /></>,
  scenarios: <><path d="M6.5 2h3M7.5 2v4.2L4 12a1.5 1.5 0 0 0 1.3 2.2h5.4A1.5 1.5 0 0 0 12 12L8.5 6.2V2" /><path d="M5.8 10h4.4" /></>,
  flow: <><circle cx="3.2" cy="3.2" r="1.7" /><circle cx="12.8" cy="8" r="1.7" /><circle cx="3.2" cy="12.8" r="1.7" /><path d="M4.6 4.2 11.4 7M11.4 9 4.6 11.8" /></>,
  protocol: <><circle cx="5.5" cy="5.5" r="2.8" /><path d="M7.5 7.5 13 13M10.8 10.8l1.8-1.8M12.4 12.4l1.6-1.6" /></>,
  rules: <><path d="M1.5 4l1 1 2-2.5M1.5 8.5l1 1 2-2.5M1.5 13l1 1 2-2.5" /><path d="M6 4h8.5M6 8.5h8.5M6 13h8.5" /></>,
  compare: <><rect x="2" y="6" width="4" height="8" rx="1" /><rect x="10" y="2" width="4" height="12" rx="1" /></>,
  boundaries: <><path d="M8 1.5 13.5 3.5v4c0 3.2-2.4 5.4-5.5 7-3.1-1.6-5.5-3.8-5.5-7v-4Z" /><path d="m5.5 8 1.8 1.8L10.8 6" /></>,
  findings: <><circle cx="7" cy="7" r="4.5" /><path d="m10.5 10.5 3.5 3.5" /></>,
  reports: <><path d="M4 1.5h5.5L13 5v9.5a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-12a1 1 0 0 1 1-1Z" /><path d="M9.5 1.5V5H13M5.5 8h5M5.5 11h5" /></>,
  settings: <><circle cx="8" cy="8" r="2.2" /><path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M12.6 3.4l-1.4 1.4M4.8 11.2 3.4 12.6" /></>,
  learn: <><path d="M8 4.5C6.5 3 4.5 2.5 2 2.5v10c2.5 0 4.5.5 6 2 1.5-1.5 3.5-2 6-2v-10c-2.5 0-4.5.5-6 2Z" /><path d="M8 4.5v10" /></>,
}

function NavIcon({ view }: { view: ViewId }) {
  return (
    <svg className="nav-icon" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {NAV_ICONS[view]}
    </svg>
  )
}

function currentRoute() {
  return parseRoute(window.location.pathname)
}

/** Real history routing (P0-09): nav links are <a href> so deep links,
 *  refresh, back/forward and the /portal?login=success callback all land
 *  on the right view. Unknown paths render the 404 view. */
export function navigate(path: string): void {
  if (window.location.pathname + window.location.search !== path) {
    window.history.pushState(null, '', path)
  }
  window.dispatchEvent(new PopStateEvent('popstate'))
}

function NotFound() {
  return (
    <section aria-label="Page not found">
      <h1>Page not found</h1>
      <p className="page-sub">That route does not exist in the research console. Nothing was changed — pick a section below.</p>
      <p><a className="btn" href="/overview" onClick={(e) => { e.preventDefault(); navigate('/overview') }}>Go to Overview</a></p>
    </section>
  )
}

export default function App() {
  const [route, setRoute] = useState(() => currentRoute())
  const [runs, setRuns] = useState<RunResult[]>(() => loadRuns())
  const [selectedScenario, setSelectedScenario] = useState<string | null>(null)
  const [collapsed, setCollapsed] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [labStatus, setLabStatus] = useState<LabStatus | null>(null)
  const [statusError, setStatusError] = useState<string | null>(null)
  const [diagOpen, setDiagOpen] = useState(false)
  const [authError, setAuthError] = useState<string | null>(null)
  const [announcement, setAnnouncement] = useState('')
  const navRef = useRef<HTMLElement>(null)
  const menuBtnRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    const onPop = () => { setRoute(currentRoute()); setDrawerOpen(false) }
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  // Callback error path: /?error=REASON carries only a safe reason code.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const err = params.get('error')
    if (err) setAuthError(err)
  }, [])

  // Screen-reader announcements from pages (runs, login, logout, errors).
  useEffect(() => {
    const onAnnounce = (e: Event) => setAnnouncement((e as CustomEvent<string>).detail ?? '')
    window.addEventListener('if-announce', onAnnounce)
    return () => window.removeEventListener('if-announce', onAnnounce)
  }, [])

  // Mobile drawer: ESC closes, Tab is trapped inside while open, focus
  // returns to the menu button on close.
  useEffect(() => {
    if (!drawerOpen) return
    const firstLink = navRef.current?.querySelector<HTMLElement>('a, button')
    firstLink?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); setDrawerOpen(false); menuBtnRef.current?.focus(); return }
      if (e.key !== 'Tab' || !navRef.current) return
      const focusables = [...navRef.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled])',
      )]
      if (focusables.length === 0) return
      const first = focusables[0]
      const last = focusables[focusables.length - 1]
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [drawerOpen])

  const refreshStatus = useCallback(() => {
    getLabStatus()
      .then((s) => { setLabStatus(s); setStatusError(null) })
      .catch((e) => { setLabStatus(null); setStatusError(String(e)) })
  }, [])
  useEffect(() => { refreshStatus() }, [refreshStatus])

  useEffect(() => { saveRuns(runs) }, [runs])

  function addRun(r: RunResult) {
    setRuns((prev) => [...prev, r].slice(-100))
  }
  function handleClear() { setRuns([]); clearRuns() }

  const view: ViewId = route?.view ?? 'overview'
  const groups: ('Lab' | 'Research' | 'Evidence')[] = ['Lab', 'Research', 'Evidence']
  const idp = labStatus?.idp
  const lastLogin = labStatus?.last_verified_login
  // P2-22 / IF-V4-05: ONE priority readiness state. Teal = verified
  // identity (backend ok, IdP reachable, discovery issuer matches).
  // Anything else is a named not-ready state, never a silent green.
  const readiness: { tone: 'teal' | 'warn' | 'bad' | 'neutral'; label: string } = !labStatus
    ? { tone: statusError ? 'warn' : 'neutral', label: statusError ? 'Lab status unavailable' : 'Checking lab status…' }
    : labStatus.backend === 'ok' && idp?.reachable && idp.issuer_matches
      ? { tone: 'teal', label: 'Ready — IdP verified' }
      : idp?.reachable && idp.issuer_matches === false
        ? { tone: 'bad', label: 'Not ready — issuer mismatch' }
        : idp?.reachable
          ? { tone: 'warn', label: `Not ready — backend ${labStatus.backend}` }
          : { tone: 'warn', label: `Not ready — IdP unreachable (${idp?.reason ?? 'NOT RUN'})` }

  return (
    <div className="app">
      <a className="skip-link" href="#main">Skip to main content</a>
      <div aria-live="polite" role="status" className="sr-only">{announcement}</div>
      {drawerOpen && <div className="drawer-backdrop" role="presentation" onClick={() => setDrawerOpen(false)} />}
      <nav
        ref={navRef}
        id="sidebar-nav"
        className={`sidebar${collapsed ? ' collapsed' : ''}${drawerOpen ? ' open' : ''}`}
        aria-label="IdentityForge sections"
      >
        <div className="brand"><span className="brand-mark" aria-hidden="true">IF</span><span className="brand-text">Identity<span>Forge</span></span></div>
        <p className="brand-sub">Operation Trustline<br />OAuth / OIDC Attack Laboratory<br />SYNTHETIC LAB DATA — NOT REAL IDENTITY INFORMATION</p>
        {groups.map((g) => (
          <div key={g}>
            <p className="nav-label">{g}</p>
            {ROUTES.filter((r) => r.group === g).map((n) => (
              <a
                key={n.path}
                className="nav-btn"
                href={n.path}
                aria-current={view === n.view ? 'page' : undefined}
                title={n.label}
                onClick={(e) => { e.preventDefault(); setDrawerOpen(false); navigate(n.path) }}
              >
                <NavIcon view={n.view} />
                <span className="nav-btn-label">{n.label}</span>
              </a>
            ))}
          </div>
        ))}
        <button className="sidebar-toggle" onClick={() => setCollapsed((c) => !c)} aria-expanded={!collapsed}>
          {collapsed ? 'Expand navigation' : 'Collapse navigation'}
        </button>
      </nav>
      <main className="main" id="main" tabIndex={-1}>
        <div className="topbar">
          <button
            type="button"
            className="menu-btn"
            ref={menuBtnRef}
            aria-expanded={drawerOpen}
            aria-controls="sidebar-nav"
            onClick={() => setDrawerOpen((o) => !o)}
          >
            {drawerOpen ? 'Close menu' : 'Open menu'}
          </button>
          <span className="env"><strong>Environment:</strong> local · loopback 127.0.0.1 · no real accounts</span>
          <span className="status-summary">
            <StatusPill tone={readiness.tone}>{readiness.label}</StatusPill>
            <button
              type="button"
              className="btn btn-ghost status-details-btn"
              aria-expanded={diagOpen}
              aria-controls="status-diagnostics"
              onClick={() => setDiagOpen((o) => !o)}
            >
              {diagOpen ? 'Hide details' : 'Details'}
            </button>
          </span>
          <span className="spacer" />
          <button className="btn btn-ghost" onClick={refreshStatus}>Refresh status</button>
          {diagOpen && (
            <div className="status-diagnostics" id="status-diagnostics" role="region" aria-label="Lab status diagnostics">
              {labStatus ? (
                <dl className="kv">
                  <dt>Backend</dt><dd>{labStatus.backend}</dd>
                  <dt>Issuer</dt><dd><span className="code">{labStatus.issuer}</span></dd>
                  <dt>Provider mode</dt><dd>{labStatus.provider_mode ?? 'unknown'}</dd>
                  <dt>Identity provider</dt><dd>{idp?.reachable ? (idp.issuer_matches ? 'Reachable — discovery issuer matches' : 'Reachable — issuer MISMATCH') : `Not reachable — ${idp?.reason ?? 'NOT RUN'}`}</dd>
                  <dt>Discovery</dt><dd><span className="code">{idp?.discovery_url}</span></dd>
                  <dt>Evidence saved</dt><dd>{labStatus.evidence ? `${labStatus.evidence.events_saved} event(s) saved · ${labStatus.evidence.event_save_errors} save error(s)${labStatus.evidence.partial_timeline_reason ? ` — ${labStatus.evidence.partial_timeline_reason}` : ''}` : 'unknown'}</dd>
                  <dt>Last verified login</dt><dd>{lastLogin ? `${lastLogin.username} · ${new Date(lastLogin.at).toLocaleString()}` : 'NOT RUN — no real browser login has completed in this backend process'}</dd>
                </dl>
              ) : (
                <p role="alert">Lab status unavailable{statusError ? `: ${statusError}` : ''}.</p>
              )}
              <p className="small muted">Live gates (Docker / Playwright): not measured in this browser — see Reports &amp; Walkthrough. They are never implied by this page.</p>
              {(!labStatus || !idp?.reachable) && (
                <p className="alert alert-warn" role="note">The lab is not ready for real sign-in. Run <span className="code">./scripts/doctor.sh</span> (or <span className="code">.\scripts\doctor.ps1</span> on Windows) to diagnose the backend and identity provider.</p>
              )}
            </div>
          )}
        </div>
        <div className="banner" role="note">Local lab only · loopback 127.0.0.1 · synthetic data only</div>
        {route && (
          <nav className="breadcrumbs" aria-label="Breadcrumb">
            <a href="/overview" onClick={(e) => { e.preventDefault(); navigate('/overview') }}>IdentityForge</a>
            {' / '}{route.group}{' / '}
            <span aria-current="page">{route.label}</span>
          </nav>
        )}
        {authError && (
          <div className="alert alert-error" role="alert">
            Sign-in failed: <span className="code">{authError}</span>. No session was created. Try signing in again, or run a scenario to see what that reason code means.
            {' '}<button className="btn btn-ghost" onClick={() => setAuthError(null)}>Dismiss</button>
          </div>
        )}
        {!route ? <NotFound /> : (
          <Suspense fallback={<p role="status">Loading view…</p>}>
            {view === 'overview' && <Overview runs={runs} onNavigate={(p: string) => navigate(p)} />}
            {view === 'portal' && <Portal />}
            {view === 'scenarios' && <ScenarioStudio runs={runs} onRun={addRun} selectedId={selectedScenario} onSelect={setSelectedScenario} />}
            {view === 'flow' && <FlowInspector runs={runs} />}
            {view === 'protocol' && <ProtocolExplorer runs={runs} />}
            {view === 'rules' && <ValidationRules />}
            {view === 'compare' && <SecureVsFlawed runs={runs} />}
            {view === 'boundaries' && <IdentityBoundaries />}
            {view === 'findings' && <Findings runs={runs} onClear={handleClear} />}
            {view === 'reports' && <Reports runs={runs} />}
            {view === 'settings' && <Settings onReset={() => { handleClear() }} />}
            {view === 'learn' && <Learning onOpenScenario={(id: string) => { setSelectedScenario(id); navigate('/scenarios') }} />}
          </Suspense>
        )}
      </main>
    </div>
  )
}
