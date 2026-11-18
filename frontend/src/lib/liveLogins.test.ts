import { describe, expect, it } from 'vitest'
import type { LabCounts, LiveLogin } from '../types'
import {
  assessLiveLoginTimeline,
  countEvents,
  countObservedSessionCreatedTransactions,
  countSuccessfulTransactions,
  countTransactions,
  findVerifiedLogin,
  isVerifiedLiveLogin,
  liveLoginSummaryNote,
  summarizeLiveLogins,
} from './liveLogins'

function login(correlation_id: string, stages: string[]): LiveLogin {
  return {
    correlation_id,
    mode: 'LIVE_KEYCLOAK',
    events: stages.map((stage, i) => ({
      correlation_id,
      stage: stage as never,
      outcome: 'ok',
      reason_code: 'OK',
      subject_hash: 'hash',
      username: 'student_01',
      detail: '',
      at: `2026-11-11T10:00:0${i}Z`,
    })),
  }
}

function counts(overrides: Partial<LabCounts> = {}): LabCounts {
  return { runs: 0, sessions: 0, live_logins: 25, transactions: 0, ...overrides }
}

describe('IF-V5-02 exact transaction/event units', () => {
  it('25 correlations → sample of 20 recent, total counter 25 (server fields authoritative)', () => {
    const sample = Array.from({ length: 20 }, (_, i) => login(`corr-${i}`, ['AUTH_STARTED', 'SESSION_CREATED']))
    const s = summarizeLiveLogins(sample, counts({ live_login_transactions: 25, live_login_events: 63, live_login_event_limit: 1000 }))
    expect(s.transactions).toBe(25)
    expect(s.events).toBe(63)
    expect(s.displayedTransactions).toBe(20)
    expect(s.source).toBe('server')
    expect(liveLoginSummaryNote(s)).toContain('Recent transactions displayed (max 20): 20')
    expect(liveLoginSummaryNote(s)).toContain('Retained total, not an all-time total')
  })

  it('more events for an existing login must not inflate the transaction count', () => {
    // IF-V6-02: both logins use the full canonical stage sequence, so
    // both are verified successful; the third entry is a post-login
    // AUTHORIZATION_DECISION for corr-a (ignored by the assessment).
    const FULL = ['AUTH_STARTED', 'CALLBACK_RECEIVED', 'BINDING_VERIFIED', 'TOKEN_ENDPOINT', 'ID_TOKEN_VALIDATED', 'SESSION_CREATED']
    const sample = [
      login('corr-a', FULL),
      login('corr-b', FULL),
      login('corr-a', ['AUTHORIZATION_DECISION']),
    ]
    // Note: two entries share corr-a; the sample groups by correlation_id.
    expect(countTransactions(sample)).toBe(2)
    expect(countEvents(sample)).toBe(13)
    const s = summarizeLiveLogins(sample)
    expect(s.transactions).toBe(2)
    expect(s.events).toBe(13)
    expect(s.successfulTransactions).toBe(2)
    expect(s.source).toBe('computed')
  })

  it('the v5 live_logins field is an EVENT count and is never rendered as transactions', () => {
    // 25 events across 7 transactions, older backend without v6 fields.
    const sample = Array.from({ length: 7 }, (_, i) =>
      login(`corr-${i}`, ['AUTH_STARTED', 'CALLBACK_RECEIVED', 'SESSION_CREATED']),
    )
    const s = summarizeLiveLogins(sample, counts({ live_logins: 25 }))
    expect(s.transactions).toBe(7)
    expect(s.events).toBe(21) // events measured from the sample, not from live_logins
    expect(s.transactions).not.toBe(25)
  })

  it('a failed fetch is UNKNOWN, never a fake zero', () => {
    const s = summarizeLiveLogins(null, null)
    expect(s.transactions).toBeNull()
    expect(s.events).toBeNull()
    expect(s.source).toBe('unknown')
    expect(liveLoginSummaryNote(s)).toContain('Unknown, not zero')
  })

  it('at the retention cap the summary says older transactions were evicted', () => {
    const sample = [login('corr-a', ['AUTH_STARTED', 'SESSION_CREATED'])]
    const s = summarizeLiveLogins(sample, counts({ live_login_transactions: 40, live_login_events: 1000, live_login_event_limit: 1000 }))
    expect(s.atRetentionLimit).toBe(true)
    expect(liveLoginSummaryNote(s)).toContain('AT the cap')
  })

  it('successful-transaction count counts only complete canonical flows ending SESSION_CREATED ok', () => {
    // IF-V6-02: a bare SESSION_CREATED ok tail is NOT successful — the
    // full canonical prefix is required.
    const FULL = ['AUTH_STARTED', 'CALLBACK_RECEIVED', 'BINDING_VERIFIED', 'TOKEN_ENDPOINT', 'ID_TOKEN_VALIDATED', 'SESSION_CREATED']
    const ok = login('corr-ok', FULL)
    const tail = login('corr-tail', ['SESSION_CREATED'])
    const denied = login('corr-no', ['AUTH_STARTED'])
    denied.events[0].outcome = 'rejected'
    expect(countSuccessfulTransactions([ok, tail, denied])).toBe(1)
    expect(countSuccessfulTransactions([tail])).toBe(0)
  })
})

describe('IF-V6-02 canonical live-login assessment (failing-first)', () => {
  const FULL = ['AUTH_STARTED', 'CALLBACK_RECEIVED', 'BINDING_VERIFIED', 'TOKEN_ENDPOINT', 'ID_TOKEN_VALIDATED', 'SESSION_CREATED']
  function fullLogin(correlation_id: string, username = 'student_01'): LiveLogin {
    return login(correlation_id, FULL).events.map((e) => ({ ...e, username })) && {
      correlation_id,
      mode: 'LIVE_KEYCLOAK' as const,
      events: FULL.map((stage, i) => ({
        correlation_id,
        stage: stage as never,
        outcome: 'ok' as const,
        reason_code: 'OK',
        subject_hash: 'hash',
        username,
        detail: '',
        at: `2026-11-11T10:00:0${i}Z`,
      })),
    }
  }

  it('a complete canonical flow counts as verified successful', () => {
    const l = fullLogin('corr-full')
    expect(isVerifiedLiveLogin(l)).toBe(true)
    expect(countSuccessfulTransactions([l])).toBe(1)
  })

  it('a SESSION_CREATED-ok tail with no observed prefix is NOT a verified login (truncated tail)', () => {
    const tail = login('corr-tail', ['SESSION_CREATED'])
    expect(isVerifiedLiveLogin(tail)).toBe(false)
    expect(countSuccessfulTransactions([tail])).toBe(0)
  })

  it('a flow missing BINDING_VERIFIED is NOT a verified login even though SESSION_CREATED is ok', () => {
    const gapped = login('corr-gap', ['AUTH_STARTED', 'CALLBACK_RECEIVED', 'TOKEN_ENDPOINT', 'ID_TOKEN_VALIDATED', 'SESSION_CREATED'])
    expect(isVerifiedLiveLogin(gapped)).toBe(false)
    expect(countSuccessfulTransactions([gapped])).toBe(0)
  })

  it('a flow that ends before SESSION_CREATED is NOT successful', () => {
    const early = login('corr-early', ['AUTH_STARTED', 'CALLBACK_RECEIVED', 'BINDING_VERIFIED'])
    expect(isVerifiedLiveLogin(early)).toBe(false)
    expect(countSuccessfulTransactions([early])).toBe(0)
  })

  it('the backend assessment fields win when present: successful=false with a SESSION_CREATED-ok tail is NOT verified', () => {
    const tail = login('corr-tail', ['SESSION_CREATED']) as LiveLogin & { timeline_complete?: boolean; successful?: boolean }
    tail.timeline_complete = false
    tail.successful = false
    expect(isVerifiedLiveLogin(tail)).toBe(false)
  })

  it('the backend assessment fields win when present: successful=true + timeline_complete=true is verified', () => {
    const l = fullLogin('corr-full') as LiveLogin & { timeline_complete?: boolean; successful?: boolean }
    l.timeline_complete = true
    l.successful = true
    expect(isVerifiedLiveLogin(l)).toBe(true)
  })

  it('assessLiveLoginTimeline names the missing stages of a truncated tail', () => {
    const a = assessLiveLoginTimeline(login('corr-tail', ['SESSION_CREATED']))
    expect(a.timeline_complete).toBe(false)
    expect(a.successful).toBe(false)
    expect(a.missing_stages).toEqual(['AUTH_STARTED', 'CALLBACK_RECEIVED', 'BINDING_VERIFIED', 'TOKEN_ENDPOINT', 'ID_TOKEN_VALIDATED'])
    expect(a.truncated_at).toBe('SESSION_CREATED')
    expect(a.retention_reason).toMatch(/must not be read as a successful login/)
  })

  it('the event-exists count is exposed ONLY under its explicit observed-event name, never as verified success', () => {
    const tail = login('corr-tail', ['SESSION_CREATED'])
    expect(countObservedSessionCreatedTransactions([tail])).toBe(1)
    expect(countSuccessfulTransactions([tail])).toBe(0)
  })

  it('findVerifiedLogin finds only the canonical student_01 flow, not a truncated tail for the same user', () => {
    const tail = login('corr-tail', ['SESSION_CREATED'])
    const full = fullLogin('corr-full', 'student_01')
    expect(findVerifiedLogin([tail], 'student_01')).toBeUndefined()
    expect(findVerifiedLogin([tail, full], 'student_01')?.correlation_id).toBe('corr-full')
  })

  it('summarizeLiveLogins counts successful transactions canonically from the sample when no server count exists', () => {
    const s = summarizeLiveLogins([fullLogin('corr-full'), login('corr-tail', ['SESSION_CREATED'])])
    expect(s.successfulTransactions).toBe(1)
  })
})
