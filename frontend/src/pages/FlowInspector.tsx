import { Fragment, useEffect, useRef, useState } from 'react'
import { getLiveLogins, getRunEvents } from '../api'
import type { LiveLogin, RunEvent, RunResult } from '../types'
import { assessLiveLoginTimeline, isVerifiedLiveLogin } from '../lib/liveLogins'
import { ModeBadge, StatusBadge } from '../components/Badge'
import { EmptyState } from '../components/ui'

/** Identity Transaction Atlas: an event-driven flow diagram.
 *  Every node is grounded in a timeline step actually recorded for the
 *  selected run — a node with no recorded step is shown with the reason,
 *  never drawn as completed. A rejected node stops the flow: every
 *  later node is NOT REACHED. Clicking a node opens the inspector with
 *  what was checked, what was expected, the reason code, the recorded
 *  timestamp, the provenance namespace and a short explanation.
 *
 *  Stage states (v4 vocabulary):
 *  - VERIFIED — the recorded step succeeded.
 *  - DENIED — the recorded step was rejected (reason code shown).
 *  - ERROR — the recorded step errored (transport/provider failure).
 *  - NOT REACHED — the flow stopped at an earlier rejected stage.
 *  - FIXTURE-ONLY — the stage does not exist in fixture mode (the
 *    IdP step: fixtures mint their test token directly).
 *  - NOT OBSERVED — live mode: the BFF cannot observe this stage
 *    (password authentication inside Keycloak, or a resource that was
 *    never loaded during the login).
 *  - NOT RUN — no timeline step recorded and no earlier rejection.
 *
 *  Two namespaces, never mixed:
 *  - OFFLINE_FIXTURE: scenario runs from this browser (deterministic
 *    fixtures; the IdP node is FIXTURE-ONLY because fixtures mint
 *    their test token directly).
 *  - LIVE_KEYCLOAK: real Keycloak logins observed by the backend
 *    (GET /api/v1/live-logins). The IdP password step is NOT OBSERVED —
 *    the BFF cannot see inside Keycloak — and is shown as such, never
 *    assumed successful. */

type NodeStatus = 'VERIFIED' | 'DENIED' | 'ERROR' | 'NOT REACHED' | 'FIXTURE-ONLY' | 'NOT OBSERVED' | 'NOT RUN'

interface AtlasStage {
  id: string
  actor: 'BROWSER' | 'APP (BFF)' | 'KEYCLOAK' | 'SESSION POLICY'
  title: string
  steps: string[] // timeline step names that ground this node
  checked: string
  expected: string
  explanation: string
}

const STAGES: AtlasStage[] = [
  {
    id: 'start', actor: 'BROWSER', title: 'Sign-in started',
    steps: ['AUTHORIZATION_STARTED'],
    checked: 'A one-use transaction is created: random state, nonce and a PKCE S256 challenge.',
    expected: 'AUTHORIZATION_STARTED recorded with outcome ok.',
    explanation: 'The login begins in the browser. State, nonce and the PKCE challenge are generated server-side; the raw verifier never leaves the backend.',
  },
  {
    id: 'idp', actor: 'KEYCLOAK', title: 'Identity provider authenticates',
    steps: [],
    checked: 'The synthetic account signs in at the local Keycloak login page.',
    expected: 'An IdP authentication event for the selected run.',
    explanation: 'Offline fixture runs mint a test token directly, so no IdP event is recorded for them — this node is NOT RUN for fixtures, not failed. For live logins the BFF cannot observe the password step inside Keycloak, so it is NOT OBSERVED, never assumed successful.',
  },
  {
    id: 'callback', actor: 'BROWSER', title: 'Callback returned with code + state',
    steps: ['CALLBACK_RECEIVED'],
    checked: 'The callback carries exactly one code and one state; the state must match the transaction the browser started.',
    expected: 'CALLBACK_RECEIVED recorded with outcome ok; a wrong, reused or missing state is rejected (I2, I7).',
    explanation: 'State binds the reply to the request that started it. A state from another browser, or a replayed one, stops the flow here.',
  },
  {
    id: 'exchange', actor: 'APP (BFF)', title: 'Code exchanged at the token endpoint',
    steps: ['CODE_REDEEMED'],
    checked: 'The backend redeems the code with the matching PKCE verifier, at the validated token endpoint.',
    expected: 'CODE_REDEEMED recorded with outcome ok; a wrong verifier or reused code is rejected (I3, I10).',
    explanation: 'Only the backend holds the verifier, so an intercepted code alone cannot be redeemed.',
  },
  {
    id: 'verify', actor: 'APP (BFF)', title: 'ID token verified',
    steps: ['TOKEN_VERIFIED'],
    checked: 'Signature against the issuer JWKS (RS256 only), exact issuer, audience, nonce, expiry and required claims.',
    expected: 'TOKEN_VERIFIED recorded with outcome ok; any failed check rejects the token (I5, I6, I8, I9).',
    explanation: 'A valid signature alone is not enough — the token must also be for this client, from this issuer, for this login attempt, and still in date.',
  },
  {
    id: 'session', actor: 'SESSION POLICY', title: 'Session created & policy applied',
    steps: ['SESSION_CREATED', 'SESSION_REVOKED'],
    checked: 'The validated subject is mapped to roles by trusted server-side policy; an opaque session is created and rotated.',
    expected: 'SESSION_CREATED recorded with outcome ok; member allowed, officer only for officer_01 (I13).',
    explanation: 'Roles come from the server-side issuer+subject map, never from a browser-supplied claim. The session cookie is an opaque random lookup key.',
  },
  {
    id: 'resource', actor: 'SESSION POLICY', title: 'Resource accessed',
    steps: ['RESOURCE_ACCESSED'],
    checked: 'The session is presented to a protected resource; the server-side policy decides allow or deny on every request.',
    expected: 'RESOURCE_ACCESSED recorded with outcome ok, or a denial (POLICY_DENIED) for a role the subject lacks (I13).',
    explanation: 'Access is decided server-side from the validated session on each request, never from a claim the browser can edit. A denial here is the authorization test passing, not a failure.',
  },
]

/** Live login stages (BFF-observed) mapped onto the fixture step names
 *  the Atlas grounds its nodes in. AUTHORIZATION_DECISION is the
 *  resource-access decision the backend records when a signed-in
 *  browser loads a member/officer resource. */
const LIVE_STEP_MAP: Record<string, string> = {
  AUTH_STARTED: 'AUTHORIZATION_STARTED',
  CALLBACK_RECEIVED: 'CALLBACK_RECEIVED',
  TOKEN_ENDPOINT: 'CODE_REDEEMED',
  ID_TOKEN_VALIDATED: 'TOKEN_VERIFIED',
  SESSION_CREATED: 'SESSION_CREATED',
  AUTHORIZATION_DECISION: 'RESOURCE_ACCESSED',
}

function outcomeToStatus(outcome: string): NodeStatus {
  if (outcome === 'ok') return 'VERIFIED'
  if (outcome === 'rejected') return 'DENIED'
  if (outcome === 'error') return 'ERROR'
  return 'NOT RUN'
}

type Namespace = 'fixture' | 'live'

export function FlowInspector({ runs }: { runs: RunResult[] }) {
  const [namespace, setNamespace] = useState<Namespace>('fixture')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [events, setEvents] = useState<RunEvent[] | null>(null)
  const [eventsError, setEventsError] = useState<string | null>(null)
  const [openStage, setOpenStage] = useState<string | null>(null)
  const [liveLogins, setLiveLogins] = useState<LiveLogin[]>([])
  const [liveLoading, setLiveLoading] = useState(false)
  const [liveError, setLiveError] = useState<string | null>(null)
  const [liveSelected, setLiveSelected] = useState<string | null>(null)
  const atlasRef = useRef<HTMLDivElement>(null)

  const latest = runs[runs.length - 1]
  const selected = runs.find((r) => r.run_id === selectedId) ?? latest
  const selectedLive = liveLogins.find((l) => l.correlation_id === liveSelected) ?? liveLogins[0]

  useEffect(() => {
    if (namespace !== 'live') return
    let alive = true
    setLiveLoading(true); setLiveError(null)
    getLiveLogins()
      .then((ll) => { if (alive) setLiveLogins(ll) })
      .catch((e) => { if (alive) setLiveError(String(e)) })
      .finally(() => { if (alive) setLiveLoading(false) })
    return () => { alive = false }
  }, [namespace])

  useEffect(() => {
    if (namespace !== 'fixture' || !selected) { setEvents(null); return }
    let alive = true
    setEvents(null); setEventsError(null)
    getRunEvents(selected.run_id)
      .then((ev) => { if (alive) setEvents(ev) })
      .catch((e) => { if (alive) setEventsError(String(e)) })
    return () => { alive = false }
  }, [namespace, selected?.run_id]) // eslint-disable-line react-hooks/exhaustive-deps

  // Arrow-key traversal between Atlas nodes (they are also Tab-able).
  // Down/Right move forward along the flow, Up/Left move back — the
  // Atlas is vertical on narrow screens and horizontal on wide ones.
  function onAtlasKeyDown(e: React.KeyboardEvent) {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp' && e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
    const buttons = [...(atlasRef.current?.querySelectorAll<HTMLButtonElement>('.atlas-node') ?? [])]
    const i = buttons.indexOf(document.activeElement as HTMLButtonElement)
    if (i === -1) return
    e.preventDefault()
    const forward = e.key === 'ArrowDown' || e.key === 'ArrowRight'
    const next = forward ? Math.min(i + 1, buttons.length - 1) : Math.max(i - 1, 0)
    buttons[next].focus()
  }

  // ---- Build the step list for the active namespace ----
  let steps: { step: string; outcome: string; reason?: string; detail?: string; at?: string }[] = []
  let header: React.ReactNode = null
  let empty: React.ReactNode = null

  if (namespace === 'fixture') {
    if (!selected) {
      empty = (
        <EmptyState title="No run yet">Run any scenario (for example I1) in the Scenario Studio to populate this atlas.</EmptyState>
      )
    } else {
      steps = [
        ...(selected.timeline ?? []).map((t) => ({ step: t.step, outcome: t.outcome, reason: t.reason ?? t.reason_code, detail: t.detail, at: t.at })),
        ...(events ?? [])
          .filter((ev) => !(selected.timeline ?? []).some((t) => t.step === ev.step))
          .map((ev) => ({ step: ev.step, outcome: ev.outcome, reason: ev.reason_code ?? undefined, detail: ev.detail, at: ev.at })),
      ]
      // Resource stage (v4): fixtures record no RESOURCE timeline
      // step, but the run DOES record resource_access_outcome
      // ("member=allowed; officer=denied", "session_created" or
      // "no_session"). Map that recorded field — verbatim, as the
      // evidence — onto a RESOURCE_ACCESSED step so the Atlas can
      // show the final stage without inventing a timeline entry.
      const rao = selected.resource_access_outcome ?? ''
      if (rao.includes('allowed')) {
        steps.push({ step: 'RESOURCE_ACCESSED', outcome: 'ok', reason: undefined, detail: `Recorded on the run: ${rao}`, at: undefined })
      } else if (rao.includes('denied')) {
        steps.push({ step: 'RESOURCE_ACCESSED', outcome: 'rejected', reason: 'POLICY_DENIED', detail: `Recorded on the run: ${rao}`, at: undefined })
      }
      const isFixture = (selected.mode ?? '').includes('FIXTURE') || (selected.mode ?? '').includes('OFFLINE')
      const modeLabel = isFixture ? 'OFFLINE FIXTURE' : selected.mode.includes('KEYCLOAK') ? 'REAL KEYCLOAK' : selected.mode
      header = (
        <>
          <label htmlFor="atlas-run">Run</label>
          <select id="atlas-run" value={selected.run_id} onChange={(e) => setSelectedId(e.target.value)}>
            {[...runs].reverse().map((r) => (
              <option key={r.run_id} value={r.run_id}>{r.scenario_id} — {r.title} · {r.timestamp} · {r.run_id.slice(0, 12)}…</option>
            ))}
          </select>
          <p><StatusBadge status={selected.status} /> <ModeBadge mode={selected.mode} /> <span className="badge badge-mode">{modeLabel} TRACE</span></p>
          <p className="small muted">Run {selected.run_id} · {selected.timestamp} · {selected.elapsed_ms} ms · expected: {selected.expected_outcome}</p>
          {selected.evidence_saved === false && <div className="alert alert-warn" role="alert">Evidence for this run was NOT SAVED by the backend{selected.evidence_error ? `: ${selected.evidence_error}` : ''}. The timeline above is the in-memory result, not a persisted record.</div>}
          {eventsError && <p className="small muted">Server events unavailable ({eventsError}) — showing the timeline carried by the run itself.</p>}
        </>
      )
    }
  } else {
    if (liveLoading) {
      header = <p role="status">Waiting for the lab — loading live login evidence…</p>
    } else if (liveError) {
      empty = <div className="alert alert-error" role="alert">Could not load live logins: {liveError}. Live login evidence is NOT RUN until the backend responds.</div>
    } else if (liveLogins.length === 0) {
      empty = (
        <EmptyState title="No real logins observed yet">
          No LIVE_KEYCLOAK timelines have been recorded by this backend process. Sign in through the Campus Club Portal (real Keycloak), then return here.
        </EmptyState>
      )
    } else if (selectedLive) {
      steps = selectedLive.events.map((ev) => ({
        step: LIVE_STEP_MAP[ev.stage] ?? ev.stage,
        outcome: ev.outcome,
        reason: ev.reason_code,
        detail: ev.detail,
        at: ev.at,
      }))
      const assessment = assessLiveLoginTimeline(selectedLive)
      // IF-V6-02: SESSION CREATED is shown only when the timeline is
      // a complete verified login (backend assessment when present,
      // else the canonical mirror). A SESSION_CREATED ok event in an
      // incomplete timeline is NOT VERIFIED, never SESSION CREATED.
      const verifiedSession = isVerifiedLiveLogin(selectedLive)
      const observedSession = selectedLive.events.some((e) => e.stage === 'SESSION_CREATED' && e.outcome === 'ok')
      const user = selectedLive.events.find((e) => e.username)?.username ?? ''
      // IF-V5-02: exact units on the live tab — this tab shows ONE
      // transaction; the list holds at most the 20 most recent.
      const shownEvents = selectedLive.events.length
      header = (
        <>
          <label htmlFor="atlas-live">Real login</label>
          <select id="atlas-live" value={selectedLive.correlation_id} onChange={(e) => setLiveSelected(e.target.value)}>
            {liveLogins.map((l) => {
              const u = l.events.find((e) => e.username)?.username ?? 'unknown'
              const at = l.events[l.events.length - 1]?.at ?? ''
              return <option key={l.correlation_id} value={l.correlation_id}>{u} · {new Date(at).toLocaleString()} · {l.correlation_id.slice(0, 16)}…</option>
            })}
          </select>
          <p>
            <span className="badge badge-live">LIVE KEYCLOAK</span>{' '}
            <span className={`badge ${verifiedSession ? 'badge-pass' : observedSession ? 'badge-brass' : 'badge-fail'}`}>{verifiedSession ? 'SESSION CREATED' : observedSession ? 'SESSION NOT VERIFIED — INCOMPLETE TIMELINE' : 'NO SESSION'}</span>
          </p>
          <p className="small muted">
            1 transaction · {shownEvents} event(s) in this transaction · {liveLogins.length} of at most 20 recent transactions shown.
            Correlation <span className="code">{selectedLive.correlation_id}</span>
            {user && <> · synthetic user <span className="code">{user}</span></>} · subject shown only as a SHA-256 hash in the events.
            Stages the BFF cannot observe (password authentication inside Keycloak) are recorded as NOT OBSERVED, never assumed.
            A timeline can be incomplete by retention: older events are pruned at the 1000-event cap, so a missing stage is never rendered as VERIFIED.
            {!assessment.timeline_complete && (
              <> Timeline incomplete — missing: {assessment.missing_stages.length > 0 ? assessment.missing_stages.join(', ') : 'ends before a terminal stage'}. {assessment.retention_reason}</>
            )}
          </p>
        </>
      )
    }
  }

  const byStep = new Map(steps.map((s) => [s.step, s]))
  let stopped = false
  const nodes = STAGES.map((stage) => {
    const step = stage.steps.map((name) => byStep.get(name)).find(Boolean)
    let status: NodeStatus
    let reason = step?.reason
    let detail = step?.detail ?? ''
    let at = step?.at
    if (stage.id === 'idp') {
      if (namespace === 'live') {
        status = 'NOT OBSERVED'
        detail = 'The BFF cannot observe password authentication inside Keycloak — recorded as not observed, never assumed successful.'
      } else {
        status = 'FIXTURE-ONLY'
        detail = 'This stage does not exist for offline fixtures: the fixture mints its test token directly, so no IdP step is recorded.'
      }
    } else if (stopped) {
      status = 'NOT REACHED'
      reason = undefined
      detail = 'Not reached — the flow stopped at an earlier rejected stage.'
    } else if (!step) {
      if (namespace === 'live') {
        status = 'NOT OBSERVED'
        detail = stage.id === 'resource'
          ? 'No resource was loaded during this login, so no access decision was recorded.'
          : 'No event for this stage was recorded for this login.'
      } else if (stage.id === 'start' || stage.id === 'callback' || stage.id === 'exchange') {
        // Real fixture timelines (see the backend engine) contain
        // only the validator steps — a fixture never performs the
        // browser start, the callback or the code exchange, so those
        // stages do not exist in fixture mode at all.
        status = 'FIXTURE-ONLY'
        detail = 'Offline fixtures do not perform this stage — they mint a test token directly and run only the validator checks.'
      } else {
        status = 'NOT RUN'
        detail = stage.id === 'resource'
          ? 'No resource access was recorded for this run (no session was created, or no resource was attempted).'
          : 'No timeline step recorded for this stage in this run.'
      }
    } else {
      status = outcomeToStatus(step.outcome)
      if (status === 'DENIED' || status === 'ERROR') stopped = true
    }
    return { stage, status, reason, detail, at }
  })

  const open = nodes.find((n) => n.stage.id === openStage)

  return (
    <section aria-label="Flow Inspector">
      <p className="eyebrow">Research · Identity Transaction Atlas</p>
      <h1>Flow Inspector — Identity Transaction Atlas</h1>
      <p className="page-sub">Event-driven flow map for one run. Each node shows what actually happened for that run; rejected paths stop at the exact rejection stage. Fixture traces and real Keycloak traces are labelled separately — a fixture trace is not a live login.</p>

      <div className="filter-bar" aria-label="Atlas namespace">
        <button type="button" className="chip" aria-pressed={namespace === 'fixture'} onClick={() => setNamespace('fixture')}>Offline fixture runs</button>
        <button type="button" className="chip" aria-pressed={namespace === 'live'} onClick={() => setNamespace('live')}>Live Keycloak logins</button>
        <span className="provenance">{namespace === 'fixture' ? 'Namespace: OFFLINE_FIXTURE' : 'Namespace: LIVE_KEYCLOAK — redacted BFF-observed timelines'}</span>
      </div>

      {/* Atelier v7 (d): the seven node states, each with its badge,
          so a partial, denied or errored Atlas reads without
          guessing — and so a missing stage is never mistaken for a
          verified one. */}
      <ul className="atlas-legend" aria-label="Atlas stage states">
        <li><span className="badge badge-pass">VERIFIED</span> step recorded, outcome ok</li>
        <li><span className="badge badge-fail">DENIED</span> step recorded, rejected — flow stops here</li>
        <li><span className="badge badge-fail">ERROR</span> step recorded, errored — flow stops here</li>
        <li><span className="badge badge-notrun">NOT REACHED</span> flow stopped at an earlier stage</li>
        <li><span className="badge badge-fixture">FIXTURE-ONLY</span> stage does not exist in fixture mode</li>
        <li><span className="badge badge-brass">NOT OBSERVED</span> live mode: the BFF cannot see this stage</li>
        <li><span className="badge badge-notrun">NOT RUN</span> no step recorded, no earlier rejection</li>
      </ul>

      {empty}
      {header && <div className="card">{header}</div>}

      {!empty && steps.length > 0 && (
        <>
          <div className="atlas" role="list" aria-label="Identity transaction stages" ref={atlasRef} onKeyDown={onAtlasKeyDown}>
            {nodes.map(({ stage, status, reason, detail }, i) => (
              <div key={stage.id} role="listitem">
                <button
                  type="button"
                  className={`atlas-node${status === 'DENIED' || status === 'ERROR' ? ' stopped' : ''}${status === 'NOT RUN' || status === 'NOT OBSERVED' || status === 'NOT REACHED' || status === 'FIXTURE-ONLY' ? ' notrun' : ''}`}
                  aria-expanded={openStage === stage.id}
                  onClick={() => setOpenStage(openStage === stage.id ? null : stage.id)}
                >
                  <span className="atlas-actor">{stage.actor}</span>
                  <span>
                    <span className="atlas-title">{i + 1}. {stage.title}</span>
                    <p>{status === 'NOT RUN' || status === 'NOT OBSERVED' || status === 'NOT REACHED' || status === 'FIXTURE-ONLY' ? detail : `${stage.checked}`}{detail && (status === 'VERIFIED' || status === 'DENIED' || status === 'ERROR') ? <> — {detail}</> : null}{reason ? <><br /><span className="code">{reason.split('_').map((frag, i, arr) => (
                      <Fragment key={i}>{frag}{i < arr.length - 1 ? <>{'_' }<wbr /></> : null}</Fragment>
                    ))}</span></> : null}</p>
                  </span>
                  <span className={`badge ${status === 'VERIFIED' ? 'badge-pass' : status === 'DENIED' || status === 'ERROR' ? 'badge-fail' : status === 'NOT OBSERVED' ? 'badge-brass' : status === 'FIXTURE-ONLY' ? 'badge-fixture' : 'badge-notrun'}`}>{status}</span>
                </button>
                {i < nodes.length - 1 && <div className={`atlas-connector${status === 'DENIED' || status === 'ERROR' ? ' stopped' : ''}`} aria-hidden="true"><span aria-hidden="true">↓</span></div>}
              </div>
            ))}
          </div>

          {open && (
            <div className="card" role="region" aria-label={`Details for ${open.stage.title}`}>
              <h2>Inspector — {open.stage.title}</h2>
              <dl className="kv">
                <dt>Actor</dt><dd>{open.stage.actor}</dd>
                <dt>Status</dt><dd>{open.status}{open.reason ? <> · reason <span className="code">{open.reason}</span></> : ''}</dd>
                <dt>Recorded at</dt><dd>{open.at ? new Date(open.at).toLocaleString() : 'No timestamp recorded for this stage'}</dd>
                <dt>Provenance</dt><dd>{namespace === 'live' ? 'LIVE_KEYCLOAK — redacted BFF-observed timeline' : 'OFFLINE_FIXTURE — deterministic offline fixture run'}</dd>
                <dt>What was checked</dt><dd>{open.stage.checked}</dd>
                <dt>Expected</dt><dd>{open.stage.expected}</dd>
                <dt>Observed</dt><dd>{open.detail || 'Recorded in the run timeline.'}</dd>
                {/* Atelier v7 (d): a missing stage always names its
                    reason. Incomplete is never VERIFIED: in a live
                    timeline the stage may have been pruned at the
                    retention cap, or the flow may never have reached
                    it — either way the reason is written down here. */}
                {(open.status === 'NOT OBSERVED' || open.status === 'NOT REACHED' || open.status === 'NOT RUN' || open.status === 'FIXTURE-ONLY') && (
                  <>
                    <dt>Missing-stage reason</dt><dd>{open.detail}{namespace === 'live' ? ' A missing stage in a live timeline is never rendered as VERIFIED: it was pruned at the retention cap, never reached, or never observed by the BFF.' : ''}</dd>
                  </>
                )}
                {namespace === 'fixture' && selected?.flawed_guard_omitted && (
                  <>
                    <dt>Flawed fixture omitted check</dt><dd><span className="code">{selected.flawed_guard_omitted}</span> — the one check the offline flawed fixture did not run; every other check ran in both variants.</dd>
                  </>
                )}
              </dl>
              <p className="muted">{open.stage.explanation}</p>
              <p><button className="btn btn-ghost" onClick={() => setOpenStage(null)}>Close inspector</button></p>
            </div>
          )}

          <div className="card">
            <h2>Full timeline — text alternative to the diagram</h2>
            <ol className="timeline">{steps.map((s, i) => (
              <li key={i} className={/reject|fail|denied/i.test(s.outcome) ? 'rejected' : s.outcome === 'skipped' ? 'notrun' : ''}>
                <span className="step">{s.step}</span> — {s.outcome}{s.reason ? ` (${s.reason})` : ''}{s.detail ? ` — ${s.detail}` : ''}{s.at ? ` · ${new Date(s.at).toLocaleTimeString()}` : ''}
              </li>))}
            </ol>
          </div>
        </>
      )}
    </section>
  )
}
