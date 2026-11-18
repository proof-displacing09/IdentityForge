import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { csvCell, downloadRunReport, getConfig, getCsrfToken, getLabCounts, getLabStatus, getLiveLogins, logout, resetCsrfCache, resetLab, runToCsv, runToMarkdown } from './api'
import type { ResetResult, RunResult } from './types'

/** Full POST /api/v1/lab/reset success body (P0-01, v3). */
const resetSuccess: ResetResult = {
  status: 'reset', operator: 'officer_01',
  cleared: { runs: 3, sessions: 2, live_logins: 1, transactions: 4 },
  operator_session_revoked: true, csrf_token: 'tok-rotated',
}

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300, status, statusText: status === 200 ? 'OK' : 'Forbidden',
    json: async () => body, text: async () => JSON.stringify(body),
  } as Response
}

let calls: { url: string; init?: RequestInit }[]

beforeEach(() => {
  calls = []
  resetCsrfCache()
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    if (url === '/api/v1/csrf-token') return jsonResponse({ csrf_token: 'csrf-abc-123' })
    if (url === '/auth/logout') return jsonResponse({ status: 'logged_out' })
    if (url === '/api/v1/lab/reset') return jsonResponse(resetSuccess)
    if (url === '/api/v1/lab/counts') return jsonResponse({ runs: 3, sessions: 2, live_logins: 1, transactions: 4 })
    if (url === '/api/v1/lab/status') return jsonResponse({ backend: 'ok', issuer: 'http://127.0.0.1:8080/realms/identityforge-lab', idp: { reachable: false, issuer_matches: null, discovery_url: 'x', reason: 'NOT RUN' }, last_verified_login: null })
    throw new Error(`unexpected ${url}`)
  }))
})
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); resetCsrfCache() })

describe('CSRF client (P0-08)', () => {
  it('fetches the token once per page load and caches it', async () => {
    await expect(getCsrfToken()).resolves.toBe('csrf-abc-123')
    await expect(getCsrfToken()).resolves.toBe('csrf-abc-123')
    expect(calls.filter((c) => c.url === '/api/v1/csrf-token')).toHaveLength(1)
  })

  it('logout sends the x-csrf-token header with credentials included', async () => {
    await logout()
    const call = calls.find((c) => c.url === '/auth/logout')
    expect(call).toBeDefined()
    expect(call!.init?.method).toBe('POST')
    expect(call!.init?.credentials).toBe('include')
    const headers = call!.init?.headers as Record<string, string>
    expect(headers['x-csrf-token']).toBe('csrf-abc-123')
  })

  it('reset sends the token and resolves only on backend success', async () => {
    await expect(resetLab()).resolves.toEqual(resetSuccess)
    const call = calls.find((c) => c.url === '/api/v1/lab/reset')
    expect((call!.init?.headers as Record<string, string>)['x-csrf-token']).toBe('csrf-abc-123')
  })

  it('logout rejects on 403 so the UI must keep the session', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/v1/csrf-token') return jsonResponse({ csrf_token: 'csrf-abc-123' })
      return jsonResponse({ detail: 'csrf_denied' }, 403)
    }))
    await expect(logout()).rejects.toThrow('403')
  })

  it('a failed token fetch fails the mutation instead of sending it token-less', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('Network error') }))
    await expect(logout()).rejects.toThrow('Network error')
  })

  it('lab status returns the measured IdP state (never hardcoded)', async () => {
    const s = await getLabStatus()
    expect(s.backend).toBe('ok')
    expect(s.idp.reachable).toBe(false)
    expect(s.idp.reason).toBe('NOT RUN')
    expect(s.last_verified_login).toBeNull()
  })
})

describe('CSRF lifecycle (P0-02)', () => {
  it('directive repro: token → reset 200 → config GET → reset with the same token still 200', async () => {
    // The config GET must not invalidate the cached token (the old
    // backend minted a fresh cookie on every config GET, which broke
    // the next mutation). Reset rotates the token in-band; the client
    // adopts it, so the second reset sends the ROTATED token.
    const tokenHeaders: string[] = []
    let tokenFetches = 0
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/v1/csrf-token') { tokenFetches += 1; return jsonResponse({ csrf_token: 'tok-1' }) }
      if (url === '/api/v1/lab/config') return jsonResponse({ issuer: 'http://127.0.0.1:8080/realms/identityforge-lab' })
      if (url === '/api/v1/lab/reset') {
        tokenHeaders.push((init?.headers as Record<string, string>)['x-csrf-token'])
        return jsonResponse({ status: 'reset', csrf_token: 'tok-2' })
      }
      throw new Error(`unexpected ${url}`)
    }))
    await expect(getCsrfToken()).resolves.toBe('tok-1')
    await expect(resetLab()).resolves.toEqual({ status: 'reset', csrf_token: 'tok-2' })
    // Config GET: pure read, no token side effect.
    await expect(getConfig()).resolves.toEqual({ issuer: 'http://127.0.0.1:8080/realms/identityforge-lab' })
    // Second reset sends the adopted rotated token, not the stale one,
    // and needs no token refetch (the rotation was adopted in-band).
    await expect(resetLab()).resolves.toEqual({ status: 'reset', csrf_token: 'tok-2' })
    expect(tokenHeaders).toEqual(['tok-1', 'tok-2'])
    expect(tokenFetches).toBe(1)
  })

  it('retries once on a 403 csrf_denied, then succeeds with the refreshed token', async () => {
    let logoutAttempts = 0
    let tokenFetches = 0
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/v1/csrf-token') { tokenFetches += 1; return jsonResponse({ csrf_token: `tok-${tokenFetches}` }) }
      if (url === '/auth/logout') {
        logoutAttempts += 1
        if (logoutAttempts === 1) return jsonResponse({ detail: 'csrf_denied' }, 403)
        return jsonResponse({ status: 'logged_out', csrf_token: 'tok-3' })
      }
      throw new Error(`unexpected ${url}`)
    }))
    await expect(logout()).resolves.toBeUndefined()
    expect(logoutAttempts).toBe(2)
    expect(tokenFetches).toBe(2)
    // The rotated token from the successful logout is adopted.
    await expect(getCsrfToken()).resolves.toBe('tok-3')
  })

  it('a second 403 is NOT retried (retry-once, then fail loudly)', async () => {
    let logoutAttempts = 0
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/v1/csrf-token') return jsonResponse({ csrf_token: 'tok-1' })
      if (url === '/auth/logout') { logoutAttempts += 1; return jsonResponse({ detail: 'csrf_denied' }, 403) }
      throw new Error(`unexpected ${url}`)
    }))
    await expect(logout()).rejects.toThrow('403')
    expect(logoutAttempts).toBe(2)
  })

  it('a non-CSRF 403 is not retried', async () => {
    let logoutAttempts = 0
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/v1/csrf-token') return jsonResponse({ csrf_token: 'tok-1' })
      if (url === '/auth/logout') { logoutAttempts += 1; return jsonResponse({ detail: 'forbidden' }, 403) }
      throw new Error(`unexpected ${url}`)
    }))
    await expect(logout()).rejects.toThrow('403')
    expect(logoutAttempts).toBe(1)
  })
})

describe('CSRF retry safeguards (P1-12)', () => {
  it('reset retries once on a 403 csrf_denied, then succeeds (no double execution)', async () => {
    // The retry is safe only because the backend rejects a CSRF
    // failure BEFORE any write (see backend
    // test_trustline_v3_csrf_retry.py): the first attempt cleared
    // nothing, so the retried request is the only execution.
    let resetAttempts = 0
    let tokenFetches = 0
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/v1/csrf-token') { tokenFetches += 1; return jsonResponse({ csrf_token: `tok-${tokenFetches}` }) }
      if (url === '/api/v1/lab/reset') {
        resetAttempts += 1
        if (resetAttempts === 1) return jsonResponse({ detail: 'csrf_denied' }, 403)
        return jsonResponse({ status: 'reset', csrf_token: 'tok-3' })
      }
      throw new Error(`unexpected ${url}`)
    }))
    await expect(resetLab()).resolves.toEqual({ status: 'reset', csrf_token: 'tok-3' })
    expect(resetAttempts).toBe(2)
    expect(tokenFetches).toBe(2)
  })

  it('a 403 policy_denied is NOT retried', async () => {
    // A student asking for an officer resource gets policy_denied;
    // retrying with a fresh token cannot change the authorization
    // outcome, so the client must not retry it.
    let logoutAttempts = 0
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/v1/csrf-token') return jsonResponse({ csrf_token: 'tok-1' })
      if (url === '/auth/logout') { logoutAttempts += 1; return jsonResponse({ detail: 'policy_denied' }, 403) }
      throw new Error(`unexpected ${url}`)
    }))
    await expect(logout()).rejects.toThrow('403')
    expect(logoutAttempts).toBe(1)
  })

  it('a 401 unauthenticated is NOT retried', async () => {
    let logoutAttempts = 0
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/v1/csrf-token') return jsonResponse({ csrf_token: 'tok-1' })
      if (url === '/auth/logout') { logoutAttempts += 1; return jsonResponse({ detail: 'unauthenticated' }, 401) }
      throw new Error(`unexpected ${url}`)
    }))
    await expect(logout()).rejects.toThrow('401')
    expect(logoutAttempts).toBe(1)
  })

  it('a network failure on logout is NOT retried (no double revocation)', async () => {
    // The first attempt may have completed server-side while the
    // response was dropped; retrying could revoke an already-revoked
    // session or, for reset, wipe evidence twice. The client surfaces
    // the failure instead of guessing.
    let logoutAttempts = 0
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/v1/csrf-token') return jsonResponse({ csrf_token: 'tok-1' })
      if (url === '/auth/logout') { logoutAttempts += 1; throw new Error('Network error') }
      throw new Error(`unexpected ${url}`)
    }))
    await expect(logout()).rejects.toThrow('Network error')
    expect(logoutAttempts).toBe(1)
  })

  it('a network failure on reset is NOT retried (no double destructive action)', async () => {
    let resetAttempts = 0
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/v1/csrf-token') return jsonResponse({ csrf_token: 'tok-1' })
      if (url === '/api/v1/lab/reset') { resetAttempts += 1; throw new Error('Network error') }
      throw new Error(`unexpected ${url}`)
    }))
    await expect(resetLab()).rejects.toThrow('Network error')
    expect(resetAttempts).toBe(1)
  })
})

describe('Lab reset client (P0-01, v3)', () => {
  it('resetLab sends {"confirm": "RESET_LAB"} in the body', async () => {
    await resetLab()
    const call = calls.find((c) => c.url === '/api/v1/lab/reset')
    expect(call).toBeDefined()
    expect(call!.init?.method).toBe('POST')
    expect(JSON.parse(String(call!.init?.body))).toEqual({ confirm: 'RESET_LAB' })
  })

  it('returns the new shape and adopts the rotated csrf_token', async () => {
    const result = await resetLab()
    expect(result.status).toBe('reset')
    expect(result.operator).toBe('officer_01')
    expect(result.cleared).toEqual({ runs: 3, sessions: 2, live_logins: 1, transactions: 4 })
    expect(result.operator_session_revoked).toBe(true)
    expect(result.csrf_token).toBe('tok-rotated')
    // The rotated token is adopted in-band: the next mutation needs no refetch.
    await expect(getCsrfToken()).resolves.toBe('tok-rotated')
    expect(calls.filter((c) => c.url === '/api/v1/csrf-token')).toHaveLength(1)
  })

  it('a 401 unauthenticated is NOT retried', async () => {
    let resetAttempts = 0
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/v1/csrf-token') return jsonResponse({ csrf_token: 'tok-1' })
      if (url === '/api/v1/lab/reset') { resetAttempts += 1; return jsonResponse({ detail: 'unauthenticated' }, 401) }
      throw new Error(`unexpected ${url}`)
    }))
    await expect(resetLab()).rejects.toThrow('401')
    expect(resetAttempts).toBe(1)
  })

  it('a 403 policy_denied is NOT retried', async () => {
    let resetAttempts = 0
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/v1/csrf-token') return jsonResponse({ csrf_token: 'tok-1' })
      if (url === '/api/v1/lab/reset') { resetAttempts += 1; return jsonResponse({ detail: 'policy_denied' }, 403) }
      throw new Error(`unexpected ${url}`)
    }))
    await expect(resetLab()).rejects.toThrow('403')
    expect(resetAttempts).toBe(1)
  })

  it('a 422 invalid_confirmation is NOT retried', async () => {
    let resetAttempts = 0
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/v1/csrf-token') return jsonResponse({ csrf_token: 'tok-1' })
      if (url === '/api/v1/lab/reset') { resetAttempts += 1; return jsonResponse({ detail: 'invalid_confirmation' }, 422) }
      throw new Error(`unexpected ${url}`)
    }))
    await expect(resetLab()).rejects.toThrow('422')
    expect(resetAttempts).toBe(1)
  })

  it('getLabCounts returns the counts a reset would clear', async () => {
    await expect(getLabCounts()).resolves.toEqual({ runs: 3, sessions: 2, live_logins: 1, transactions: 4 })
  })
})

describe('Live logins client (P0-05)', () => {
  it('returns the redacted LIVE_KEYCLOAK timelines', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/v1/live-logins') {
        return jsonResponse({ mode: 'LIVE_KEYCLOAK', logins: [{ correlation_id: 'abc', mode: 'LIVE_KEYCLOAK', events: [{ correlation_id: 'abc', stage: 'SESSION_CREATED', outcome: 'ok', reason_code: 'OK', subject_hash: 'deadbeef', username: 'student_01', detail: '', at: '2026-11-11T00:00:00Z' }] }] })
      }
      throw new Error(`unexpected ${url}`)
    }))
    const logins = await getLiveLogins()
    expect(logins).toHaveLength(1)
    expect(logins[0].mode).toBe('LIVE_KEYCLOAK')
    expect(logins[0].events[0].stage).toBe('SESSION_CREATED')
  })
})

function sampleRun(): RunResult {
  return {
    run_id: 'run-1', scenario_id: 'I6', title: 'Wrong audience', mode: 'DETERMINISTIC OFFLINE FIXTURE',
    status: 'PASS', expected_outcome: 'reject', observed_secure: 'reject', observed_flawed: 'accept',
    validation_reason: 'WRONG_AUDIENCE', resource_access_outcome: 'denied',
    timeline: [], elapsed_ms: 12, timestamp: '2026-11-11T00:00:00Z',
    evidence_saved: false, evidence_provenance: 'OFFLINE_FIXTURE',
    flawed_model_status: 'EXECUTED', flawed_guard_omitted: 'audience',
    flawed_observed_result: 'accept', protected_resource_disclosed: false,
    secure_session_created: false, flawed_session_created: false,
    session_preexisted: false, session_revoked: false,
  }
}

describe('CSV formula-injection neutralization', () => {
  it('prefixes formula-trigger cells with a single quote', () => {
    expect(csvCell('=2+2')).toBe('"\'=2+2"')
    expect(csvCell('+cmd')).toBe("\"'+cmd\"")
    expect(csvCell('-2+3')).toBe('"\'-2+3"')
    expect(csvCell('@SUM(A1:A2)')).toBe('"\'@SUM(A1:A2)"')
    expect(csvCell('\t=evil')).toBe('"\'\t=evil"')
    expect(csvCell('  =evil')).toBe('"\'  =evil"')
  })
  it('leaves ordinary cells unchanged and escapes quotes', () => {
    expect(csvCell('reject')).toBe('"reject"')
    expect(csvCell('say "hi"')).toBe('"say ""hi"""')
    expect(csvCell(12)).toBe('"12"')
    expect(csvCell(null)).toBe('""')
  })
  it('runToCsv neutralizes a hostile validation_reason', () => {
    const run = sampleRun()
    run.validation_reason = '=HYPERLINK("http://evil")'
    const csv = runToCsv(run)
    expect(csv).toContain('"\'=HYPERLINK(""http://evil"")"')
    expect(csv).not.toContain('\n"=HYPERLINK')
  })
})

describe('Findings downloads (LOCAL_UNSAVED_COPY fallback)', () => {
  // jsdom's Blob has no .text(); read via FileReader instead.
  function blobText(b: Blob): Promise<string> {
    return new Promise((resolve, reject) => {
      const r = new FileReader()
      r.onload = () => resolve(String(r.result))
      r.onerror = () => reject(r.error)
      r.readAsText(b)
    })
  }

  it('server report success downloads the server file (origin=server)', async () => {
    const blobs: Blob[] = []
    const downloads: string[] = []
    vi.stubGlobal('URL', { createObjectURL: vi.fn((b: Blob) => { blobs.push(b); return 'blob:x' }), revokeObjectURL: vi.fn() })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) { downloads.push(this.download) })
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/v1/runs/run-1/report') return jsonResponse(sampleRun())
      throw new Error(`unexpected ${url}`)
    }))
    const outcome = await downloadRunReport(sampleRun(), 'json')
    expect(outcome.origin).toBe('server')
    expect(outcome.localCopy).toBe(false)
    expect(outcome.filename).toBe('I6-run-1.json')
    expect(downloads).toContain('I6-run-1.json')
    expect(JSON.parse(await blobText(blobs[0]))).toEqual(sampleRun())
  })

  it('server report failure downloads a labelled LOCAL UNSAVED COPY (origin=browser_cache)', async () => {
    const blobs: Blob[] = []
    const downloads: string[] = []
    vi.stubGlobal('URL', { createObjectURL: vi.fn((b: Blob) => { blobs.push(b); return 'blob:x' }), revokeObjectURL: vi.fn() })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) { downloads.push(this.download) })
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('backend down') }))
    const outcome = await downloadRunReport(sampleRun(), 'json')
    expect(outcome.origin).toBe('browser_cache')
    expect(outcome.localCopy).toBe(true)
    expect(outcome.provenance).toBe('LOCAL_UNSAVED_FALLBACK')
    expect(outcome.serverFetchFailed).toBe(true)
    expect(outcome.fetchError).toContain('backend down')
    expect(outcome.filename).toContain('LOCAL-UNSAVED-COPY')
    expect(downloads[0]).toContain('LOCAL-UNSAVED-COPY')
    const payload = JSON.parse(await blobText(blobs[0]))
    expect(payload.fallback_label).toBe('LOCAL_UNSAVED_COPY')
    expect(payload.provenance).toBe('LOCAL_UNSAVED_FALLBACK')
    expect(payload.origin).toBe('browser_cache')
    expect(payload.server_fetch_error).toContain('backend down')
    expect(payload.run.run_id).toBe('run-1')
  })
})

describe('Report provenance (IF-V4-12)', () => {
  function blobText(b: Blob): Promise<string> {
    return new Promise((resolve, reject) => {
      const r = new FileReader()
      r.onload = () => resolve(String(r.result))
      r.onerror = () => reject(r.error)
      r.readAsText(b)
    })
  }

  function captureDownloads() {
    const blobs: Blob[] = []
    const downloads: string[] = []
    vi.stubGlobal('URL', { createObjectURL: vi.fn((b: Blob) => { blobs.push(b); return 'blob:x' }), revokeObjectURL: vi.fn() })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) { downloads.push(this.download) })
    return { blobs, downloads }
  }

  it('json success is a SERVER_VERIFIED_ARTIFACT, not a local copy', async () => {
    captureDownloads()
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/v1/runs/run-1/report') return jsonResponse(sampleRun())
      throw new Error(`unexpected ${url}`)
    }))
    const outcome = await downloadRunReport(sampleRun(), 'json')
    expect(outcome.provenance).toBe('SERVER_VERIFIED_ARTIFACT')
    expect(outcome.localCopy).toBe(false)
    expect(outcome.serverFetchFailed).toBeUndefined()
  })

  it('csv re-fetches the server report and is labelled CLIENT_DERIVED_FROM_SERVER_RUN', async () => {
    const { blobs, downloads } = captureDownloads()
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/v1/runs/run-1/report') return jsonResponse(sampleRun())
      throw new Error(`unexpected ${url}`)
    }))
    const outcome = await downloadRunReport(sampleRun(), 'csv')
    expect(outcome.provenance).toBe('CLIENT_DERIVED_FROM_SERVER_RUN')
    expect(outcome.localCopy).toBe(false)
    expect(outcome.filename).toContain('CLIENT-DERIVED')
    expect(outcome.filename).toContain('I6-run-1.csv')
    expect(downloads[0]).toContain('CLIENT-DERIVED')
    const csv = await blobText(blobs[0])
    expect(csv.startsWith('run_id,scenario_id,')).toBe(true)
    expect(csv).toContain('run-1')
  })

  it('csv labels a LOCAL UNSAVED COPY when the server report cannot be fetched', async () => {
    captureDownloads()
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('backend down') }))
    const outcome = await downloadRunReport(sampleRun(), 'csv')
    expect(outcome.provenance).toBe('LOCAL_UNSAVED_FALLBACK')
    expect(outcome.localCopy).toBe(true)
    expect(outcome.serverFetchFailed).toBe(true)
    expect(outcome.fetchError).toContain('backend down')
    expect(outcome.filename).toContain('LOCAL-UNSAVED-COPY')
    expect(outcome.filename).toContain('I6-run-1.csv')
  })

  it('md carries a provenance footer stating its derivation (server confirmed)', async () => {
    const { blobs } = captureDownloads()
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/v1/runs/run-1/report') return jsonResponse(sampleRun())
      throw new Error(`unexpected ${url}`)
    }))
    const outcome = await downloadRunReport(sampleRun(), 'md')
    expect(outcome.provenance).toBe('CLIENT_DERIVED_FROM_SERVER_RUN')
    expect(outcome.filename).toContain('CLIENT-DERIVED')
    const md = await blobText(blobs[0])
    expect(md).toContain('## Provenance')
    expect(md).toContain('derivation: CLIENT_DERIVED_FROM_SERVER_RUN')
    expect(md).toContain('assembled in this browser, not served by the backend')
    expect(md).not.toContain('LOCAL_UNSAVED_FALLBACK')
  })

  it('md fallback footer names the fetch failure and denies server verification', async () => {
    const { blobs } = captureDownloads()
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('backend down') }))
    const outcome = await downloadRunReport(sampleRun(), 'md')
    expect(outcome.provenance).toBe('LOCAL_UNSAVED_FALLBACK')
    expect(outcome.filename).toContain('LOCAL-UNSAVED-COPY')
    const md = await blobText(blobs[0])
    expect(md).toContain('## Provenance')
    expect(md).toContain('derivation: LOCAL_UNSAVED_FALLBACK')
    expect(md).toContain('could not be re-fetched')
    expect(md).toContain('NOT a server-verified report')
  })

  it('runToMarkdown without provenance keeps the old body (no footer)', () => {
    const md = runToMarkdown(sampleRun())
    expect(md).toContain('# IdentityForge run report — I6 Wrong audience')
    expect(md).not.toContain('## Provenance')
  })
})

describe('IF-V6-01 export provenance: validated server report (failing-first)', () => {
  function blobText(b: Blob): Promise<string> {
    return new Promise((resolve, reject) => {
      const r = new FileReader()
      r.onload = () => resolve(String(r.result))
      r.onerror = () => reject(r.error)
      r.readAsText(b)
    })
  }
  function captureDownloads() {
    const blobs: Blob[] = []
    const downloads: string[] = []
    vi.stubGlobal('URL', { createObjectURL: vi.fn((b: Blob) => { blobs.push(b); return 'blob:x' }), revokeObjectURL: vi.fn() })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) { downloads.push(this.download) })
    return { blobs, downloads }
  }
  /** Browser-held run: OLD LOCAL TITLE / PASS. Server report: NEW SERVER TITLE / FAIL. */
  function localRun(): RunResult { return { ...sampleRun(), title: 'OLD LOCAL TITLE', status: 'PASS' } }
  function serverReport(): RunResult { return { ...sampleRun(), title: 'NEW SERVER TITLE', status: 'FAIL' } }
  function stubReport(body: unknown, status = 200) {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/v1/runs/run-1/report') return jsonResponse(body, status)
      throw new Error(`unexpected ${url}`)
    }))
  }

  it('csv divergent server/local: exported bytes show the SERVER title and status, never the local ones', async () => {
    const { blobs } = captureDownloads()
    stubReport(serverReport())
    const outcome = await downloadRunReport(localRun(), 'csv')
    expect(outcome.provenance).toBe('CLIENT_DERIVED_FROM_SERVER_RUN')
    const csv = await blobText(blobs[0])
    expect(csv).toContain('NEW SERVER TITLE')
    expect(csv).toContain('FAIL')
    expect(csv).not.toContain('OLD LOCAL TITLE')
  })

  it('md divergent server/local: exported bytes show the SERVER title and status, never the local ones', async () => {
    const { blobs } = captureDownloads()
    stubReport(serverReport())
    const outcome = await downloadRunReport(localRun(), 'md')
    expect(outcome.provenance).toBe('CLIENT_DERIVED_FROM_SERVER_RUN')
    const md = await blobText(blobs[0])
    expect(md).toContain('NEW SERVER TITLE')
    expect(md).toContain('status: FAIL')
    expect(md).not.toContain('OLD LOCAL TITLE')
  })

  it('json divergent server/local: the file is the server report verbatim', async () => {
    const { blobs } = captureDownloads()
    stubReport(serverReport())
    const outcome = await downloadRunReport(localRun(), 'json')
    expect(outcome.provenance).toBe('SERVER_VERIFIED_ARTIFACT')
    const payload = JSON.parse(await blobText(blobs[0]))
    expect(payload.title).toBe('NEW SERVER TITLE')
    expect(payload.status).toBe('FAIL')
  })

  it('csv identical server/local keeps CLIENT_DERIVED_FROM_SERVER_RUN with the shared values', async () => {
    const { blobs } = captureDownloads()
    stubReport(sampleRun())
    const outcome = await downloadRunReport(sampleRun(), 'csv')
    expect(outcome.provenance).toBe('CLIENT_DERIVED_FROM_SERVER_RUN')
    expect(outcome.localCopy).toBe(false)
    expect(await blobText(blobs[0])).toContain('Wrong audience')
  })

  it('wrong run_id in the server report fails closed to LOCAL UNSAVED COPY, never SERVER_VERIFIED', async () => {
    const { blobs, downloads } = captureDownloads()
    stubReport({ ...serverReport(), run_id: 'run-OTHER' })
    const outcome = await downloadRunReport(localRun(), 'csv')
    expect(outcome.provenance).toBe('LOCAL_UNSAVED_FALLBACK')
    expect(outcome.localCopy).toBe(true)
    expect(outcome.serverReportInvalid).toBe(true)
    expect(outcome.fetchError).toMatch(/run_id/)
    expect(downloads[0]).toContain('LOCAL-UNSAVED-COPY')
    const csv = await blobText(blobs[0])
    expect(csv).toContain('OLD LOCAL TITLE')
    expect(csv).not.toContain('NEW SERVER TITLE')
  })

  it('wrong scenario_id in the server report fails closed to LOCAL UNSAVED COPY', async () => {
    captureDownloads()
    stubReport({ ...serverReport(), scenario_id: 'I1' })
    const outcome = await downloadRunReport(localRun(), 'md')
    expect(outcome.provenance).toBe('LOCAL_UNSAVED_FALLBACK')
    expect(outcome.serverReportInvalid).toBe(true)
    expect(outcome.fetchError).toMatch(/scenario_id/)
  })

  it('malformed server report (string / null / array / empty object / missing title) fails closed', async () => {
    for (const bad of ['not an object', null, [], {}, { ...serverReport(), title: undefined }]) {
      captureDownloads()
      stubReport(bad)
      const outcome = await downloadRunReport(localRun(), 'json')
      expect(outcome.provenance).toBe('LOCAL_UNSAVED_FALLBACK')
      expect(outcome.localCopy).toBe(true)
      expect(outcome.serverReportInvalid).toBe(true)
    }
  })

  it('server 404 after retention eviction: csv is a clearly labelled LOCAL UNSAVED COPY, never green/server artifact', async () => {
    const { blobs, downloads } = captureDownloads()
    stubReport({ detail: 'run_not_found' }, 404)
    const outcome = await downloadRunReport(localRun(), 'csv')
    expect(outcome.provenance).toBe('LOCAL_UNSAVED_FALLBACK')
    expect(outcome.localCopy).toBe(true)
    expect(outcome.serverFetchFailed).toBe(true)
    expect(downloads[0]).toContain('LOCAL-UNSAVED-COPY')
    expect(downloads[0]).not.toContain('CLIENT-DERIVED')
    const csv = await blobText(blobs[0])
    expect(csv).toContain('OLD LOCAL TITLE')
  })

  it('server 404 after retention eviction: md is a clearly labelled LOCAL UNSAVED COPY with a notice naming the 404', async () => {
    const { blobs } = captureDownloads()
    stubReport({ detail: 'run_not_found' }, 404)
    const outcome = await downloadRunReport(localRun(), 'md')
    expect(outcome.provenance).toBe('LOCAL_UNSAVED_FALLBACK')
    const md = await blobText(blobs[0])
    expect(md).toContain('LOCAL_UNSAVED_FALLBACK')
    expect(md).toContain('404')
    expect(md).toContain('OLD LOCAL TITLE')
  })

  it('unreachable backend: json falls back to a LOCAL UNSAVED COPY whose payload names the failure', async () => {
    const { blobs } = captureDownloads()
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('backend down') }))
    const outcome = await downloadRunReport(localRun(), 'json')
    expect(outcome.provenance).toBe('LOCAL_UNSAVED_FALLBACK')
    const payload = JSON.parse(await blobText(blobs[0]))
    expect(payload.fallback_label).toBe('LOCAL_UNSAVED_COPY')
    expect(payload.run.title).toBe('OLD LOCAL TITLE')
  })

  it('csv keeps formula-injection defenses when built from the server report', async () => {
    const { blobs } = captureDownloads()
    stubReport({ ...serverReport(), validation_reason: '=HYPERLINK("http://evil")' })
    await downloadRunReport(localRun(), 'csv')
    const csv = await blobText(blobs[0])
    expect(csv).toContain('"\'=HYPERLINK(""http://evil"")"')
    expect(csv).not.toContain('\n"=HYPERLINK')
  })
})
