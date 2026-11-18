import { useMemo, useState } from 'react'
import { downloadRunReport, type DownloadOutcome } from '../api'
import type { RunResult } from '../types'
import { ProvenanceBadge, StatusBadge } from '../components/Badge'
import { announce } from '../components/ui'

type SortKey = 'timestamp' | 'scenario' | 'status'

export function Findings({ runs, onClear }: { runs: RunResult[]; onClear: () => void }) {
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [provFilter, setProvFilter] = useState('all')
  const [sortKey, setSortKey] = useState<SortKey>('timestamp')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [notices, setNotices] = useState<Record<string, DownloadOutcome>>({})

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    const list = runs.filter((r) => {
      if (q && !`${r.scenario_id} ${r.title} ${r.validation_reason}`.toLowerCase().includes(q)) return false
      if (statusFilter !== 'all' && r.status !== statusFilter) return false
      if (provFilter !== 'all' && (r.evidence_provenance ?? 'unknown') !== provFilter) return false
      return true
    })
    const dir = sortDir === 'asc' ? 1 : -1
    return [...list].sort((a, b) => {
      if (sortKey === 'scenario') return dir * a.scenario_id.localeCompare(b.scenario_id)
      if (sortKey === 'status') return dir * a.status.localeCompare(b.status)
      return dir * (new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
    })
  }, [runs, query, statusFilter, provFilter, sortKey, sortDir])

  async function download(run: RunResult, kind: 'json' | 'csv' | 'md') {
    const outcome = await downloadRunReport(run, kind)
    setNotices((prev) => ({ ...prev, [`${run.run_id}:${kind}`]: outcome }))
    if (outcome.localCopy) {
      announce(`Server report unavailable. Downloaded a LOCAL UNSAVED COPY for ${run.scenario_id}.`)
    }
  }

  /** Exact provenance wording for a download (IF-V4-12): what the
   *  file proves, in the UI next to the button that produced it —
   *  for every format, not just JSON. Tone follows the derivation:
   *  a fallback is a warning, a client-derived file is information,
   *  a server artifact is a plain note — never a warning for a
   *  verified file. */
  function provenanceNotice(o: DownloadOutcome): React.ReactNode {
    if (o.provenance === 'SERVER_VERIFIED_ARTIFACT') {
      return (
        <p className="small muted" role="status">
          Server-verified artifact — downloaded from the backend report endpoint (file <span className="code">{o.filename}</span>).
        </p>
      )
    }
    if (o.provenance === 'CLIENT_DERIVED_FROM_SERVER_RUN') {
      return (
        <div className="alert alert-info" role="status">
          Client-derived report — assembled in this browser from the run; the server report was re-fetched successfully at download time, so the run is server-confirmed, but this file itself was assembled locally (file <span className="code">{o.filename}</span>).
        </div>
      )
    }
    return (
      <div className="alert alert-warn export-degraded" role="alert">
        Server report unavailable{o.fetchError ? ` (${o.fetchError})` : ''} — this download is a <strong>LOCAL UNSAVED COPY</strong> from this browser&apos;s cache (file <span className="code">{o.filename}</span>). It is not a server-verified report.
      </div>
    )
  }

  const counts = { PASS: 0, FAIL: 0, ERROR: 0, SKIPPED: 0, RUNNING: 0 }
  runs.forEach((r) => { counts[r.status] = (counts[r.status] ?? 0) + 1 })

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortKey(key); setSortDir(key === 'timestamp' ? 'desc' : 'asc') }
  }

  return (
    <section aria-label="Findings and Evidence">
      <p className="eyebrow">Evidence · Runs in this browser</p>
      <h1>Findings &amp; Evidence</h1>
      <p className="page-sub">Run history is stored only in this browser (localStorage). Reports contain synthetic usernames and redacted claims only — no tokens, codes, passwords or cookies.</p>
      {/* Atelier v7 (c): provenance legend. Every download is one of
          three kinds, and the kind is visible before any download
          happens — a degraded export (LOCAL UNSAVED COPY) looks
          intentionally different (dashed amber) so it can never be
          mistaken for a server-verified artifact. */}
      <div className="card">
        <h2>What a download proves — provenance legend</h2>
        <ul className="provenance-legend">
          <li><strong>Server-verified artifact</strong> — downloaded from the backend report endpoint; the file is the stored server report, hash-checked against the stored report. Plain note next to the download.</li>
          <li><strong>Client-derived from server</strong> — assembled in this browser from the run; the server report was re-fetched successfully at download time, so the run is server-confirmed, but this file itself was assembled locally. Blue info notice next to the download.</li>
          <li><strong>LOCAL UNSAVED COPY</strong> — the server report could not be reached, so the file was assembled from this browser&apos;s cache only. Dashed amber warning next to the download; it is not a server-verified report.</li>
        </ul>
      </div>
      <div className="card">
        <h2>Export before eviction — retention</h2>
        <p className="small">
          The backend keeps only the latest <strong>1000 scenario runs</strong>, <strong>20000 run events</strong> and{' '}
          <strong>1000 live-login events</strong>. When a new record is saved past a cap, the oldest records are
          pruned automatically (FIFO) — a manual lab reset is the only manual destructive action, and it clears
          everything at once. Export any run you need to keep <em>before</em> running many more scenarios: once
          pruned, older evidence cannot be recovered from this lab. Exports contain redacted evidence only — never
          passwords, client secrets, authorization codes, ID tokens or session cookies — and no exported file is
          signed, so a download proves only what it contains (see the provenance label on each download).
        </p>
      </div>
      {runs.length === 0 ? (
        <div className="card"><p role="status">No runs yet — empty state. Nothing has been measured, so there is nothing to download.</p></div>
      ) : (
        <>
          <div className="card"><p>
            <StatusBadge status="PASS" /> {counts.PASS} · <StatusBadge status="FAIL" /> {counts.FAIL} · <StatusBadge status="ERROR" /> {counts.ERROR} · <StatusBadge status="SKIPPED" /> {counts.SKIPPED} — {runs.length} runs total.
            {' '}<button className="btn btn-ghost" onClick={() => { onClear(); announce('Local run history cleared.') }}>Clear local history</button>
          </p></div>

          <div className="filter-bar" role="search">
            <label htmlFor="findings-search" className="sr-only">Search findings</label>
            <input id="findings-search" type="search" placeholder="Search scenario, title, reason…" value={query} onChange={(e) => setQuery(e.target.value)} />
            <label htmlFor="findings-status" className="sr-only">Filter by status</label>
            <select id="findings-status" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="all">All statuses</option>
              <option value="PASS">PASS</option>
              <option value="FAIL">FAIL</option>
              <option value="ERROR">ERROR</option>
              <option value="SKIPPED">SKIPPED</option>
            </select>
            <label htmlFor="findings-prov" className="sr-only">Filter by provenance</label>
            <select id="findings-prov" value={provFilter} onChange={(e) => setProvFilter(e.target.value)}>
              <option value="all">All provenances</option>
              <option value="OFFLINE_FIXTURE">OFFLINE_FIXTURE</option>
              <option value="LIVE_KEYCLOAK">LIVE_KEYCLOAK</option>
              <option value="EPHEMERAL">EPHEMERAL</option>
            </select>
            <span className="provenance" role="status">{filtered.length} of {runs.length} runs</span>
          </div>

          {filtered.length === 0 ? (
            <p className="muted" role="status">No runs match those filters.</p>
          ) : (
            <div className="table-wrap" tabIndex={0} role="region" aria-label="Run history table"><table>
              <thead><tr>
                <th scope="col"><button type="button" className="btn btn-ghost" onClick={() => toggleSort('scenario')} aria-label={`Scenario${sortKey === 'scenario' ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''} — sort by scenario`}>Scenario {sortKey === 'scenario' ? (sortDir === 'asc' ? '↑' : '↓') : ''}</button></th>
                <th scope="col"><button type="button" className="btn btn-ghost" onClick={() => toggleSort('status')} aria-label={`Decision${sortKey === 'status' ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''} — sort by decision`}>Decision {sortKey === 'status' ? (sortDir === 'asc' ? '↑' : '↓') : ''}</button></th>
                <th scope="col">Secure</th>
                <th scope="col">Flawed fixture</th>
                <th scope="col">Reason</th>
                <th scope="col">Provenance</th>
                <th scope="col">Evidence</th>
                <th scope="col"><button type="button" className="btn btn-ghost" onClick={() => toggleSort('timestamp')} aria-label={`When${sortKey === 'timestamp' ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''} — sort by time`}>When {sortKey === 'timestamp' ? (sortDir === 'asc' ? '↑' : '↓') : ''}</button></th>
                <th scope="col">Downloads</th>
              </tr></thead>
              <tbody>
                {filtered.map((r) => {
                  const notice = (kind: 'json' | 'csv' | 'md') => notices[`${r.run_id}:${kind}`]
                  const anyNotice = notice('json') ?? notice('csv') ?? notice('md')
                  return (
                    <tr key={r.run_id}>
                      <td><strong>{r.scenario_id}</strong><br /><span className="small muted">{r.title}</span></td>
                      <td><StatusBadge status={r.status} /></td>
                      <td>{r.observed_secure}</td>
                      <td>{r.observed_flawed}</td>
                      <td><span className="code">{r.validation_reason}</span></td>
                      <td><ProvenanceBadge provenance={r.evidence_provenance} /></td>
                      <td>
                        {r.evidence_saved === true ? 'Saved' : r.evidence_saved === false ? <span className="badge badge-fail">NOT SAVED</span> : 'Unknown'}
                        {r.evidence_error ? <><br /><span className="small muted">{r.evidence_error}</span></> : null}
                      </td>
                      <td>{new Date(r.timestamp).toLocaleString()}</td>
                      <td>
                        <button className="btn btn-ghost" onClick={() => void download(r, 'json')}>JSON</button>{' '}
                        <button className="btn btn-ghost" onClick={() => void download(r, 'csv')}>CSV</button>{' '}
                        <button className="btn btn-ghost" onClick={() => void download(r, 'md')}>MD</button>
                        {anyNotice && provenanceNotice(anyNotice)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table></div>
          )}
          <p className="small muted">
            CSV exports neutralize spreadsheet formula injection (cells starting with =, +, -, @ are prefixed with a single quote).
            JSON reports come from the backend when it responds; when it does not, the fallback is a labelled LOCAL UNSAVED COPY — never a silent substitute.
            CSV and Markdown are always assembled in this browser: the server report is re-fetched first, so the download is labelled
            CLIENT-DERIVED when the run is server-confirmed, or LOCAL UNSAVED COPY when the server could not be reached. The notice
            next to each download states exactly which one it is.
          </p>
        </>
      )}
    </section>
  )
}
