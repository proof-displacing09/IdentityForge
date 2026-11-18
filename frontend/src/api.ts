import type { Health, LabConfig, LabCounts, LabStatus, LiveLogin, PortalUser, ResetResult, RunEvent, RunResult, Scenario } from './types'

/** API client — CSRF lifecycle (P0-02, deterministic).
 *
 *  - GET /api/v1/csrf-token returns the token and sets the
 *    identityforge_csrf cookie. It is idempotent per browser: the backend
 *    returns the browser's existing well-formed token and mints only when
 *    there is none. The token is fetched once per page load and cached.
 *  - GET /api/v1/lab/config is a PURE READ: it never mints or sets a
 *    CSRF cookie, so visiting Settings cannot invalidate the token the
 *    frontend cached. (The directive repro — token, reset, config GET,
 *    reset with the same token — must stay 200 throughout.)
 *  - POST /api/v1/lab/reset and POST /auth/logout ROTATE the token and
 *    return the fresh value in-band as `csrf_token` in the JSON body
 *    (and as the cookie). The client adopts that value immediately so
 *    the next mutation does not 403 on a stale cache.
 *  - On a mutation that is rejected 403 with a CSRF reason, the client
 *    refreshes the token once and retries at most once, then surfaces
 *    the failure. A second 403 is never retried.
 *  - POST /api/v1/runs enforces CSRF (it writes evidence); every
 *    mutation goes through postWithCsrf.
 *  All requests send credentials so HttpOnly session cookies travel. */

export class ApiError extends Error {
  status: number
  detail: string
  constructor(status: number, statusText: string, detail: string) {
    super(`${status} ${statusText}${detail ? `: ${detail.slice(0, 300)}` : ''}`)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { credentials: 'include', headers: { 'Content-Type': 'application/json' }, ...init })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new ApiError(res.status, res.statusText, text)
  }
  return res.json() as Promise<T>
}

let csrfToken: string | null = null
let csrfPromise: Promise<string> | null = null

/** Fetch (once per page load) and cache the CSRF token. Exported for
 *  tests; callers normally use postWithCsrf. */
export function getCsrfToken(): Promise<string> {
  if (csrfToken) return Promise.resolve(csrfToken)
  if (!csrfPromise) {
    csrfPromise = req<{ csrf_token: string }>('/api/v1/csrf-token').then((d) => {
      if (!d.csrf_token) throw new Error('CSRF token endpoint returned no token')
      csrfToken = d.csrf_token
      return csrfToken
    }).catch((e) => {
      csrfPromise = null
      throw e
    })
  }
  return csrfPromise
}

/** Adopt a fresh token handed back in-band (reset/logout responses
 *  carry `csrf_token`). The next mutation uses it without a refetch. */
export function adoptCsrfToken(token: string): void {
  if (typeof token === 'string' && token.length > 0) {
    csrfToken = token
    csrfPromise = null
  }
}

/** Test hook: drop the cached token so the next mutation re-fetches it. */
export function resetCsrfCache(): void {
  csrfToken = null
  csrfPromise = null
}

function isCsrfDenial(e: unknown): boolean {
  return e instanceof ApiError && e.status === 403 && /csrf/i.test(e.detail ?? '')
}

function adoptTokenFromBody(body: unknown): void {
  if (body && typeof body === 'object' && 'csrf_token' in body) {
    const t = (body as { csrf_token?: unknown }).csrf_token
    if (typeof t === 'string') adoptCsrfToken(t)
  }
}

async function postWithCsrf<T>(path: string, body: unknown = {}): Promise<T> {
  const attempt = async (token: string): Promise<T> => {
    const result = await req<T>(path, {
      method: 'POST',
      body: JSON.stringify(body),
      headers: { 'Content-Type': 'application/json', 'x-csrf-token': token },
    })
    adoptTokenFromBody(result)
    return result
  }
  try {
    return await attempt(await getCsrfToken())
  } catch (e) {
    if (!isCsrfDenial(e)) throw e
    // Stale cached token (e.g. rotated by a reset/logout in another tab):
    // refresh once from /api/v1/csrf-token — which returns the cookie's
    // current value — and retry exactly once.
    resetCsrfCache()
    return attempt(await getCsrfToken())
  }
}

/** IF-V5-06 (v6): getters accept an optional AbortSignal so the
 *  useResource hook can abort in-flight requests on unmount / retry.
 *  The signal is passed straight through to fetch via req(). */
export function getHealth(signal?: AbortSignal): Promise<Health> { return req<Health>('/api/v1/health', { signal }) }
export function getLabStatus(signal?: AbortSignal): Promise<LabStatus> { return req<LabStatus>('/api/v1/lab/status', { signal }) }
export function getConfig(): Promise<LabConfig> { return req<LabConfig>('/api/v1/lab/config') }
export async function listScenarios(signal?: AbortSignal): Promise<Scenario[]> {
  const data = await req<unknown>('/api/v1/scenarios', { signal })
  if (Array.isArray(data)) return data as Scenario[]
  const obj = data as { scenarios?: Scenario[] }
  return obj.scenarios ?? []
}
export function getScenario(id: string): Promise<Scenario> { return req<Scenario>(`/api/v1/scenarios/${encodeURIComponent(id)}`) }
export function getMe(): Promise<PortalUser> { return req<PortalUser>('/api/v1/portal/me') }
export function getMember(): Promise<unknown> { return req<unknown>('/api/v1/portal/member') }
export function getOfficer(): Promise<unknown> { return req<unknown>('/api/v1/portal/officer') }

export async function createRun(scenarioId: string): Promise<RunResult> {
  const created = await postWithCsrf<RunResult>('/api/v1/runs', { scenario_id: scenarioId })
  // If the backend returns a pending run, poll until it settles (max ~30s).
  if (created.status === 'RUNNING' && created.run_id) {
    for (let i = 0; i < 30; i++) {
      await new Promise((r) => setTimeout(r, 1000))
      const polled = await req<RunResult>(`/api/v1/runs/${encodeURIComponent(created.run_id)}`)
      if (polled.status !== 'RUNNING') return polled
    }
    return created
  }
  return created
}
export function getRun(id: string): Promise<RunResult> { return req<RunResult>(`/api/v1/runs/${encodeURIComponent(id)}`) }
export async function getRunEvents(id: string): Promise<RunEvent[]> {
  const data = await req<{ events?: RunEvent[] }>(`/api/v1/runs/${encodeURIComponent(id)}/events`)
  return data.events ?? []
}
export function getReport(id: string): Promise<unknown> { return req<unknown>(`/api/v1/runs/${encodeURIComponent(id)}/report`) }
export async function getReportMarkdown(id: string): Promise<string> {
  const res = await fetch(`/api/v1/runs/${encodeURIComponent(id)}/report?format=md`, { credentials: 'include' })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.text()
}

/** Real Keycloak login evidence (P0-05, namespace LIVE_KEYCLOAK).
 *  Redacted BFF-observed timelines — never mixed with OFFLINE_FIXTURE
 *  runs. No tokens, codes, states or verifiers are ever returned. */
export async function getLiveLogins(signal?: AbortSignal): Promise<LiveLogin[]> {
  const data = await req<{ mode?: string; logins?: LiveLogin[] }>('/api/v1/live-logins', { signal })
  return data.logins ?? []
}
export function getLiveLogin(correlationId: string): Promise<LiveLogin> {
  return req<LiveLogin>(`/api/v1/live-logins/${encodeURIComponent(correlationId)}`)
}

/** Counts of what a reset would clear (GET /api/v1/lab/counts, P0-01
 *  v3). No auth: counts are lab metadata, not secrets. */
export function getLabCounts(signal?: AbortSignal): Promise<LabCounts> { return req<LabCounts>('/api/v1/lab/counts', { signal }) }

/** Lab reset (P0-01, v3): officer-only, double-confirmed by the UI.
 *  The backend checks, in order: CSRF (403 csrf_denied), session
 *  (401 unauthenticated), OFFICER role (403 policy_denied), then the
 *  confirmation body {"confirm": "RESET_LAB"} (422
 *  invalid_confirmation) — no writes happen before authorization
 *  succeeds, so a 401/403/422 here means nothing was cleared. On
 *  success the response carries the cleared counts, the rotated
 *  `csrf_token` (adopted above), and `operator_session_revoked: true`
 *  — the officer's own session is revoked by the reset. */
export function resetLab(): Promise<ResetResult> {
  return postWithCsrf<ResetResult>('/api/v1/lab/reset', { confirm: 'RESET_LAB' })
}
/** Logout (app-local revocation only — it does NOT end the IdP SSO
 *  session): resolves only on HTTP 200 from the backend, i.e. only
 *  after the server-side session was actually revoked. Callers must
 *  NOT clear the signed-in UI when this rejects. */
export async function logout(): Promise<void> {
  await postWithCsrf<unknown>('/auth/logout', {})
}

export function downloadText(filename: string, text: string, mime = 'text/plain'): void {
  const blob = new Blob([text], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

export type ReportProvenance =
  | 'SERVER_VERIFIED_ARTIFACT'
  | 'CLIENT_DERIVED_FROM_SERVER_RUN'
  | 'LOCAL_UNSAVED_FALLBACK'

export interface DownloadOutcome {
  /** 'server' = the artifact came from the backend report endpoint;
   *  'browser_cache' = the server fetch failed and the file was built
   *  from the run object held in this browser only. */
  origin: 'server' | 'browser_cache'
  filename: string
  /** True when the file is a LOCAL UNSAVED COPY (not server-verified). */
  localCopy: boolean
  /** Exact derivation of the downloaded bytes (IF-V4-12). Never a
   *  blanket 'verified': only SERVER_VERIFIED_ARTIFACT means the
   *  backend served the file. */
  provenance: ReportProvenance
  /** True when the server report fetch was attempted and failed. */
  serverFetchFailed?: boolean
  /** The fetch failure, when one happened (for the UI notice). */
  fetchError?: string
  /** True when the server answered but the report failed validation
   *  (IF-V6-01: wrong run_id/scenario_id, malformed, missing fields).
   *  Such a report is never used as the source of exported bytes. */
  serverReportInvalid?: boolean
}

/** IF-V6-01: strict validator for the server report shape. The
 *  run_id must equal the requested ID, the scenario_id must agree
 *  with the run the UI asked about, and every critical identity field
 *  (title, status, mode, expected/observed outcomes, validation
 *  reason, resource-access outcome, timeline, elapsed time,
 *  timestamp) must be present and well-typed. Anything else fails
 *  closed: the caller falls back to a labelled LOCAL UNSAVED COPY
 *  built from the browser-held run, never to SERVER_VERIFIED. */
const REPORT_STATUSES = ['PASS', 'FAIL', 'ERROR', 'SKIPPED', 'RUNNING']

export function validateServerReport(
  report: unknown,
  expected: { run_id: string; scenario_id: string },
): { ok: true; report: RunResult } | { ok: false; reason: string } {
  if (!report || typeof report !== 'object' || Array.isArray(report)) {
    return { ok: false, reason: 'server report is not an object (malformed, empty or non-object response)' }
  }
  const r = report as Record<string, unknown>
  if (typeof r.run_id !== 'string' || r.run_id.length === 0) {
    return { ok: false, reason: 'server report is missing required field run_id' }
  }
  if (r.run_id !== expected.run_id) {
    return { ok: false, reason: `server report run_id ${r.run_id} does not match the requested run_id ${expected.run_id}` }
  }
  if (typeof r.scenario_id !== 'string' || r.scenario_id.length === 0) {
    return { ok: false, reason: 'server report is missing required field scenario_id' }
  }
  if (r.scenario_id !== expected.scenario_id) {
    return { ok: false, reason: `server report scenario_id ${r.scenario_id} does not match the expected scenario_id ${expected.scenario_id}` }
  }
  const requiredStrings = ['title', 'mode', 'expected_outcome', 'observed_secure', 'observed_flawed', 'validation_reason', 'resource_access_outcome', 'timestamp']
  for (const field of requiredStrings) {
    if (typeof r[field] !== 'string' || (r[field] as string).length === 0) {
      return { ok: false, reason: `server report is missing required field ${field}` }
    }
  }
  if (typeof r.status !== 'string' || !REPORT_STATUSES.includes(r.status)) {
    return { ok: false, reason: `server report has an unknown status ${String(r.status)}` }
  }
  if (!Array.isArray(r.timeline)) {
    return { ok: false, reason: 'server report is missing required field timeline' }
  }
  if (typeof r.elapsed_ms !== 'number') {
    return { ok: false, reason: 'server report is missing required field elapsed_ms' }
  }
  return { ok: true, report: report as RunResult }
}

/** Build the labelled LOCAL UNSAVED COPY fallback for one format.
 *  `invalid` distinguishes a report that failed validation from a
 *  fetch that failed: both are local copies, but the notice names
 *  the exact reason so a reviewer can tell them apart. */
function downloadLocalFallback(
  run: RunResult,
  kind: 'json' | 'csv' | 'md',
  reason: string,
  invalid: boolean,
): DownloadOutcome {
  const filename = `identityforge-report-LOCAL-UNSAVED-COPY-${run.scenario_id}-${run.run_id}.${kind}`
  const notice = invalid
    ? `Server report failed validation at download time (${reason}). This file was built from the run object held in this browser only and is NOT a server-verified report.`
    : `The server report could not be re-fetched at download time (${reason}). This file was built from the run object held in this browser only and is NOT a server-verified report.`
  if (kind === 'json') {
    const payload = {
      fallback_label: 'LOCAL_UNSAVED_COPY',
      provenance: 'LOCAL_UNSAVED_FALLBACK',
      origin: 'browser_cache',
      note: 'Server report unavailable; this file was built from the run object held in this browser only. It is NOT a server-verified report.',
      server_fetch_error: reason,
      run,
    }
    downloadText(filename, JSON.stringify(payload, null, 2), 'application/json')
  } else if (kind === 'csv') {
    downloadText(filename, runToCsv(run), 'text/csv')
  } else {
    downloadText(filename, runToMarkdown(run, { label: 'LOCAL_UNSAVED_FALLBACK', note: notice }), 'text/markdown')
  }
  return { origin: 'browser_cache', filename, localCopy: true, provenance: 'LOCAL_UNSAVED_FALLBACK', serverFetchFailed: true, fetchError: reason, serverReportInvalid: invalid }
}

/** Download a run report. JSON is the server report when the backend
 *  answers AND the report validates (IF-V6-01); CSV/Markdown are
 *  assembled in this browser from the VALIDATED server report when
 *  it validates, and labelled CLIENT_DERIVED_FROM_SERVER_RUN. A
 *  report that fails validation (wrong run_id/scenario_id, malformed,
 *  missing fields) is never used as the source of exported bytes:
 *  the download falls back to a transparently labelled LOCAL
 *  UNSAVED COPY built from the browser-held run. The caller must
 *  show the outcome (see DownloadOutcome) — a fallback is never a
 *  silent substitute. */
export async function downloadRunReport(run: RunResult, kind: 'json' | 'csv' | 'md'): Promise<DownloadOutcome> {
  if (kind === 'json') {
    try {
      const raw = await getReport(run.run_id)
      const validated = validateServerReport(raw, run)
      if (!validated.ok) return downloadLocalFallback(run, 'json', `Server report failed validation: ${validated.reason}`, true)
      const filename = `${run.scenario_id}-${run.run_id}.json`
      downloadText(filename, JSON.stringify(raw, null, 2), 'application/json')
      return { origin: 'server', filename, localCopy: false, provenance: 'SERVER_VERIFIED_ARTIFACT' }
    } catch (e) {
      return downloadLocalFallback(run, 'json', String(e), false)
    }
  }
  // CSV/Markdown: always client-side derivations, but the SOURCE is
  // the validated server report when it validates — never the
  // browser-held run while labelled CLIENT_DERIVED_FROM_SERVER_RUN.
  let serverRun: RunResult | null = null
  let serverFetchFailed = false
  let fetchError: string | undefined
  let serverReportInvalid = false
  try {
    const raw = await getReport(run.run_id)
    const validated = validateServerReport(raw, run)
    if (!validated.ok) {
      serverFetchFailed = true
      serverReportInvalid = true
      fetchError = `Server report failed validation: ${validated.reason}`
    } else {
      serverRun = validated.report
    }
  } catch (e) {
    serverFetchFailed = true
    fetchError = String(e)
  }
  const source = serverRun ?? run
  const provenance: ReportProvenance = serverRun ? 'CLIENT_DERIVED_FROM_SERVER_RUN' : 'LOCAL_UNSAVED_FALLBACK'
  const tag = serverRun ? 'CLIENT-DERIVED' : 'LOCAL-UNSAVED-COPY'
  if (kind === 'csv') {
    const filename = `identityforge-report-${tag}-${run.scenario_id}-${run.run_id}.csv`
    downloadText(filename, runToCsv(source), 'text/csv')
    return { origin: 'browser_cache', filename, localCopy: !serverRun, provenance, serverFetchFailed, fetchError, serverReportInvalid }
  }
  const filename = `identityforge-report-${tag}-${run.scenario_id}-${run.run_id}.md`
  const note = serverRun
    ? 'The server report was re-fetched and validated successfully at download time, so the run itself is server-confirmed — but this file was assembled in this browser, not served by the backend.'
    : serverReportInvalid
      ? `The server report failed validation at download time (${fetchError}). This file was built from the run object held in this browser only and is NOT a server-verified report.`
      : `The server report could not be re-fetched at download time (${fetchError}). This file was built from the run object held in this browser only and is NOT a server-verified report.`
  downloadText(filename, runToMarkdown(source, { label: provenance, note }), 'text/markdown')
  return { origin: 'browser_cache', filename, localCopy: !serverRun, provenance, serverFetchFailed, fetchError, serverReportInvalid }
}

/** CSV formula-injection neutralization: a cell whose first non-space
 *  character is =, +, -, @ (or a tab/CR, which spreadsheets also treat
 *  as a formula trigger) is prefixed with a single quote so a
 *  spreadsheet opens it as text, never as a formula. */
export function csvCell(v: unknown): string {
  const s = String(v ?? '')
  const first = s.trimStart().charAt(0)
  const trigger = first === '=' || first === '+' || first === '-' || first === '@' || first === '\t' || first === '\r'
  const safe = trigger ? `'${s}` : s
  return `"${safe.replace(/"/g, '""')}"`
}

/** Markdown report. `provenance` (IF-V4-12) appends a footer stating
 *  exactly what the file proves: a client-derived file is never
 *  labelled as a server artifact, and a fallback names the fetch
 *  failure that forced it. */
export function runToMarkdown(r: RunResult, provenance?: { label: string; note?: string }): string {
  const lines = [
    `# IdentityForge run report — ${r.scenario_id} ${r.title}`,
    '',
    `SYNTHETIC LAB DATA — NOT REAL IDENTITY INFORMATION. Mode: ${r.mode}`,
    '',
    `- run_id: ${r.run_id}`,
    `- status: ${r.status}`,
    `- expected_outcome: ${r.expected_outcome}`,
    `- observed_secure: ${r.observed_secure}`,
    `- observed_flawed: ${r.observed_flawed}`,
    `- validation_reason: ${r.validation_reason}`,
    `- resource_access_outcome: ${r.resource_access_outcome}`,
    `- secure_session_created: ${r.secure_session_created ?? 'unknown'}`,
    `- flawed_session_created: ${r.flawed_session_created ?? 'unknown'}`,
    `- session_preexisted: ${r.session_preexisted ?? 'unknown'}`,
    `- session_revoked: ${r.session_revoked ?? 'unknown'}`,
    `- flawed_model_status: ${r.flawed_model_status ?? 'unknown'}`,
    `- flawed_guard_omitted: ${r.flawed_guard_omitted ?? ''}`,
    `- flawed_observed_result: ${r.flawed_observed_result ?? ''}`,
    `- protected_resource_disclosed: ${r.protected_resource_disclosed ?? 'unknown'}`,
    `- evidence_provenance: ${r.evidence_provenance ?? 'unknown'}`,
    `- elapsed_ms: ${r.elapsed_ms}`,
    `- timestamp: ${r.timestamp}`,
    `- evidence_saved: ${r.evidence_saved ?? 'unknown'}`,
    `- fixture_revision: ${r.reproducibility?.fixture_revision ?? 'unknown'}`,
    `- provider: ${r.reproducibility?.provider ?? 'offline-fixture'}`,
    '',
    '## Timeline',
    ...(r.timeline ?? []).map((s) => `- ${s.step}: ${s.outcome}${s.reason ? ` (${s.reason})` : ''}`),
  ]
  if (provenance) {
    lines.push('', '## Provenance', '', `- derivation: ${provenance.label}`)
    if (provenance.note) lines.push(`- note: ${provenance.note}`)
    lines.push('- What this file proves: the run record above as held in this browser. It does not prove a live Keycloak session and, unless labelled SERVER_VERIFIED_ARTIFACT, it was not served by the backend.')
  }
  return lines.join('\n')
}

export function runToCsv(r: RunResult): string {
  const header = 'run_id,scenario_id,title,mode,status,expected_outcome,observed_secure,observed_flawed,validation_reason,resource_access_outcome,secure_session_created,flawed_session_created,session_preexisted,session_revoked,flawed_model_status,flawed_guard_omitted,flawed_observed_result,protected_resource_disclosed,evidence_provenance,elapsed_ms,timestamp,evidence_saved'
  const row = [r.run_id, r.scenario_id, r.title, r.mode, r.status, r.expected_outcome, r.observed_secure, r.observed_flawed, r.validation_reason, r.resource_access_outcome, r.secure_session_created ?? '', r.flawed_session_created ?? '', r.session_preexisted ?? '', r.session_revoked ?? '', r.flawed_model_status ?? '', r.flawed_guard_omitted ?? '', r.flawed_observed_result ?? '', r.protected_resource_disclosed ?? '', r.evidence_provenance ?? '', r.elapsed_ms, r.timestamp, r.evidence_saved ?? ''].map(csvCell).join(',')
  return `${header}\n${row}\n`
}
