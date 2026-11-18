import { useEffect, useMemo, useState } from 'react'
import { createRun, listScenarios } from '../api'
import type { RunResult, Scenario } from '../types'
import { RunResultCard } from '../components/RunResultCard'
import { announce } from '../components/ui'

interface Props {
  runs: RunResult[]
  onRun: (r: RunResult) => void
  selectedId: string | null
  onSelect: (id: string) => void
}

type StatusFilter = 'all' | 'not-run' | 'PASS' | 'FAIL' | 'ERROR'

export function ScenarioStudio({ runs, onRun, selectedId, onSelect }: Props) {
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [sortKey, setSortKey] = useState<'id' | 'title' | 'status'>('id')

  function loadScenarios() {
    setLoading(true); setError(null)
    let alive = true
    listScenarios().then((s) => { if (alive) { setScenarios(s); setLoading(false) } })
      .catch((e) => { if (alive) { setError(String(e)); setLoading(false) } })
    return () => { alive = false }
  }

  useEffect(() => loadScenarios(), [])

  const runByScenario = useMemo(() => {
    const map = new Map<string, RunResult>()
    for (const r of runs) map.set(r.scenario_id, r)
    return map
  }, [runs])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    const list = scenarios.filter((s) => {
      const hay = `${s.id} ${s.title} ${s.explanation ?? ''} ${s.attack_surface ?? ''}`.toLowerCase()
      if (q && !hay.includes(q)) return false
      if (statusFilter === 'all') return true
      const latest = runByScenario.get(s.id)
      if (statusFilter === 'not-run') return !latest
      return latest?.status === statusFilter
    })
    // Sort is a real control, not decoration: numeric scenario order
    // (I2 before I10), title A–Z, or run status with not-run first.
    const statusRank = (s: Scenario): number => {
      const latest = runByScenario.get(s.id)
      if (!latest) return 0
      return latest.status === 'PASS' ? 1 : latest.status === 'FAIL' ? 2 : 3
    }
    const num = (id: string): number => Number.parseInt(id.replace(/\D/g, ''), 10) || 0
    return [...list].sort((a, b) => {
      if (sortKey === 'title') return a.title.localeCompare(b.title)
      if (sortKey === 'status') return statusRank(a) - statusRank(b) || num(a.id) - num(b.id)
      return num(a.id) - num(b.id)
    })
  }, [scenarios, query, statusFilter, sortKey, runByScenario])

  const selected = scenarios.find((s) => s.id === selectedId) ?? scenarios[0]
  const latestRun = selected ? runByScenario.get(selected.id) : undefined

  async function runSelected() {
    if (!selected || running) return
    setRunning(true); setRunError(null)
    try {
      const result = await createRun(selected.id)
      onRun(result)
      announce(`Scenario ${selected.id} finished: ${result.status}. Secure: ${result.observed_secure}.`)
    } catch (e) {
      setRunError(`Run failed to execute: ${String(e)} — recorded as ERROR, not PASS.`)
      announce(`Scenario ${selected.id} failed to execute.`)
    } finally { setRunning(false) }
  }

  if (loading) return <section aria-label="Scenario Studio"><h1>Scenario Studio</h1><p role="status">Loading scenarios…</p></section>
  if (error) return <section aria-label="Scenario Studio"><h1>Scenario Studio</h1><div className="alert alert-error" role="alert">Could not load scenarios: {error}. Scenarios are <strong>NOT RUN</strong> until the backend responds.</div><p><button type="button" className="btn btn-ghost" onClick={() => void loadScenarios()}>Retry loading scenarios</button></p></section>
  if (scenarios.length === 0) return <section aria-label="Scenario Studio"><h1>Scenario Studio</h1><p role="status">No scenarios returned by the API — empty state.</p></section>

  return (
    <section aria-label="Scenario Studio">
      <p className="eyebrow">Research · 18 scenarios</p>
      <h1>Scenario Studio</h1>
      <p className="page-sub">One scenario at a time. Each run calls the backend offline-fixture runner; results are measured, never hardcoded. Flawed variants run only inside that isolated harness — they cannot mint a portal session.</p>
      <div className="filter-bar" role="search">
        <label htmlFor="scenario-search" className="sr-only">Search scenarios</label>
        <input
          id="scenario-search"
          type="search"
          placeholder="Search by id, title, attack surface… (e.g. I6, audience)"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <label htmlFor="scenario-status" className="sr-only">Filter by run status</label>
        <select id="scenario-status" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}>
          <option value="all">All statuses</option>
          <option value="not-run">Not run yet</option>
          <option value="PASS">PASS</option>
          <option value="FAIL">FAIL</option>
          <option value="ERROR">ERROR</option>
        </select>
        <label htmlFor="scenario-sort" className="sr-only">Sort scenarios</label>
        <select id="scenario-sort" value={sortKey} onChange={(e) => setSortKey(e.target.value as 'id' | 'title' | 'status')}>
          <option value="id">Sort: scenario number</option>
          <option value="title">Sort: title A–Z</option>
          <option value="status">Sort: run status (not run first)</option>
        </select>
        <span className="provenance" role="status">{filtered.length} of {scenarios.length} scenarios</span>
      </div>
      <div className="grid2">
        <div>
          <h2>Scenarios ({filtered.length})</h2>
          {filtered.length === 0 ? (
            <p className="muted" role="status">No scenarios match that search. Clear the search to see all {scenarios.length}.</p>
          ) : (
            <div role="listbox" aria-label="Scenarios">
              {filtered.map((s) => {
                const latest = runByScenario.get(s.id)
                return (
                  <div key={s.id} style={{ marginBottom: '.4rem' }}>
                    <button
                      className="scenario-btn"
                      role="option"
                      aria-selected={selected?.id === s.id}
                      onClick={() => onSelect(s.id)}
                    >
                      <strong>{s.id}</strong> — {s.title}
                      {latest && <span className="muted"> · {latest.status} · secure: {latest.observed_secure}</span>}
                      {!latest && <span className="faint"> · not run</span>}
                    </button>
                  </div>
                )
              })}
            </div>
          )}
        </div>
        <div>
          {selected && (
            <article className="card" aria-label={`Scenario ${selected.id}`}>
              <h2>{selected.id} — {selected.title}</h2>
              <p>{selected.explanation ?? selected.description ?? 'No description supplied by the API.'}</p>
              <dl className="kv">
                {selected.attack_surface && <><dt>Attack surface</dt><dd>{selected.attack_surface}</dd></>}
                {selected.attacker_input && <><dt>Attacker input</dt><dd>{selected.attacker_input}</dd></>}
                {(selected.expected_secure ?? selected.expected_secure_result) && <><dt>Expected secure result</dt><dd>{selected.expected_secure ?? selected.expected_secure_result}</dd></>}
                {selected.flawed_description && <><dt>Flawed fixture</dt><dd>{selected.flawed_description}</dd></>}
                {selected.decision_step && <><dt>Decision step</dt><dd><span className="code">{selected.decision_step}</span></dd></>}
                {selected.remediation && <><dt>Remediation</dt><dd>{selected.remediation}</dd></>}
              </dl>
              {selected.preconditions && selected.preconditions.length > 0 && (
                <><h3>Preconditions</h3><ul>{selected.preconditions.map((p, i) => <li key={i}>{p}</li>)}</ul></>
              )}
              <button className="btn btn-teal" onClick={() => void runSelected()} disabled={running} aria-busy={running}>
                {running ? 'Running…' : `Run ${selected.id}`}
              </button>
              {runError && <div className="alert alert-error" role="alert">{runError}</div>}
              {latestRun?.evidence_saved === false && <div className="alert alert-warn" role="alert">This run&apos;s evidence was NOT SAVED by the backend{latestRun.evidence_error ? `: ${latestRun.evidence_error}` : ''} — the decision above is shown, but it is not a persisted record.</div>}
              <p className="small muted">The Run button is disabled while a run is in progress.</p>
            </article>
          )}
          {latestRun && <RunResultCard run={latestRun} />}
        </div>
      </div>
    </section>
  )
}
