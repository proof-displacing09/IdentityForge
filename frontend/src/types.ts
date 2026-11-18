export type RunMode = 'DETERMINISTIC OFFLINE FIXTURE' | 'LOCAL REAL KEYCLOAK INTEGRATION' | 'PREVIOUS SAVED EVIDENCE'
export type RunStatus = 'PASS' | 'FAIL' | 'ERROR' | 'SKIPPED' | 'RUNNING'

export interface TimelineStep {
  step: string
  outcome: string
  reason?: string
  reason_code?: string
  detail?: string
  at?: string
}

export interface RunEvent {
  step: string
  outcome: string
  reason_code?: string | null
  detail?: string
  at?: string
}

export interface RunResult {
  run_id: string
  scenario_id: string
  title: string
  mode: string
  status: RunStatus
  expected_outcome: string
  observed_secure: string
  observed_flawed: string
  validation_reason: string
  resource_access_outcome: string
  timeline: TimelineStep[]
  elapsed_ms: number
  timestamp: string
  /** False when the backend could not persist the evidence row (P1-14). */
  evidence_saved?: boolean
  evidence_error?: string
  reproducibility?: { fixture_revision?: string; provider?: string; [k: string]: unknown }
  // --- Session / flawed-comparator semantics (P0-06, backend truth) ---
  /** Secure path executed SessionStore.create/rotate in this run. */
  secure_session_created?: boolean
  /** Flawed path executed a session create in this run (often false:
   *  a denied action creates no session). */
  flawed_session_created?: boolean
  /** A legitimate session already existed before the tested action. */
  session_preexisted?: boolean
  /** The tested action revoked a session (I12 logout). */
  session_revoked?: boolean
  /** EXECUTED = the flawed path ran; NOT_MODELED = this scenario has
   *  no meaningful flawed session path (the flawed decision is still
   *  recorded in observed_flawed). */
  flawed_model_status?: 'EXECUTED' | 'NOT_MODELED'
  /** The single check the flawed fixture omits, e.g. 'state'. */
  flawed_guard_omitted?: string
  /** What the flawed fixture actually observed (may be 'accept'). */
  flawed_observed_result?: string
  /** True only when the flawed path discloses a protected resource to
   *  an actor who must not have it (I13 spoofed officer role). */
  protected_resource_disclosed?: boolean
  /** OFFLINE_FIXTURE | LIVE_KEYCLOAK | EPHEMERAL — where this run's
   *  evidence came from. EPHEMERAL = never persisted. */
  evidence_provenance?: 'OFFLINE_FIXTURE' | 'LIVE_KEYCLOAK' | 'EPHEMERAL'
  secure_result?: string
  flawed_result?: string
  secure_reason?: string
  flawed_reason?: string
  [k: string]: unknown
}

export interface Scenario {
  id: string
  title: string
  description?: string
  explanation?: string
  attack_surface?: string
  expected_secure_result?: string
  preconditions?: string[]
  /** Attacker-controlled input for this scenario (backend definition). */
  attacker_input?: string
  /** Expected secure decision, backend wording. */
  expected_secure?: string
  /** What the flawed fixture does differently. */
  flawed_description?: string
  /** The validation step where the decision is made. */
  decision_step?: string
  remediation?: string
  [k: string]: unknown
}

export interface Health {
  status: string
  service?: string
  version?: string
  provider_mode?: string
  [k: string]: unknown
}

/** Measured lab status from GET /api/v1/lab/status (P1-15). Nothing here
 *  is inferred: idp.reachable is a live discovery probe, and
 *  last_verified_login is set only by a real callback that succeeded. */
export interface LabStatus {
  backend: string
  issuer: string
  provider_mode?: string
  idp: {
    reachable: boolean
    issuer_matches: boolean | null
    discovery_url: string
    reason: string
  }
  /** P1-11 evidence health: the Atlas must not claim a complete
   *  timeline when event saves have failed. */
  evidence?: {
    events_saved: number
    event_save_errors: number
    evidence_available: boolean
    partial_timeline_reason?: string
  }
  last_verified_login: {
    at: string
    username: string
    subject: string
    issuer: string
  } | null
  synthetic_data_label?: string
  [k: string]: unknown
}

export interface LabConfig {
  backend_url?: string
  frontend_url?: string
  keycloak_url?: string
  issuer?: string
  provider_mode?: string
  fixture_revision?: string
  ports?: Record<string, number>
  [k: string]: unknown
}

export interface PortalUser {
  sub?: string
  username?: string
  name?: string
  email?: string
  roles?: string[]
  [k: string]: unknown
}

/** Counts of lab evidence a reset would clear (GET /api/v1/lab/counts,
 *  P0-01 v3). Lab metadata, not secrets — the endpoint needs no auth. */
export interface LabCounts {
  runs: number
  /** IF-V4-03 (v5): ACTIVE sessions only (live, unexpired, unrevoked). */
  sessions: number
  /** Process-lifetime sessions minted since backend start (IF-V4-03).
   *  Diagnostic only: not cleared by a lab reset. Optional so older
   *  mocks without it still type-check; the UI shows Unknown then. */
  sessions_total_issued?: number
  /** IF-V5-02 (v6): RETAINED live-login EVENT rows (v5 backend
   *  semantics: COUNT(*) over live_login_events). The field name is
   *  historical — this is NOT a transaction/login count and must
   *  never be rendered as "N logins". Prefer the v6 fields below
   *  when the backend reports them. */
  live_logins: number
  transactions: number
  /** IF-V5-02 (v6, WS1): retained live-login TRANSACTIONS =
   *  COUNT DISTINCT correlation_id. Authoritative when present. */
  live_login_transactions?: number
  /** IF-V5-02 (v6, WS1): retained live-login EVENT rows. */
  live_login_events?: number
  /** IF-V5-02 (v6, WS1): transactions in the retained set that
   *  reached SESSION_CREATED with outcome ok. */
  live_login_successful_transactions?: number
  /** IF-V5-02 (v6, WS1): retention cap for live-login events. */
  live_login_event_limit?: number
  events?: number
  runs_limit?: number
  events_limit?: number
  live_logins_limit?: number
}

/** Result of POST /api/v1/lab/reset (P0-01, v3). The officer's own
 *  session IS revoked by the reset (`operator_session_revoked`), and
 *  `csrf_token` is the rotated token the client must adopt. */
export interface ResetResult {
  status: string
  operator: string
  cleared: LabCounts
  operator_session_revoked: boolean
  csrf_token: string
}

/** One redacted, BFF-observed step of a REAL Keycloak login (P0-05).
 *  Stages the BFF cannot observe (IdP password authentication) are
 *  recorded as NOT OBSERVED by the backend, never SUCCESS by
 *  assumption. No tokens, codes, states or verifiers are ever here. */
export interface LiveLoginEvent {
  correlation_id: string
  stage: 'AUTH_STARTED' | 'CALLBACK_RECEIVED' | 'BINDING_VERIFIED' | 'TOKEN_ENDPOINT' | 'ID_TOKEN_VALIDATED' | 'SESSION_CREATED' | 'AUTHORIZATION_DECISION' | 'LOGOUT'
  outcome: 'ok' | 'rejected' | 'error'
  reason_code: string
  subject_hash: string
  username: string
  detail: string
  at: string
}

export interface LiveLogin {
  correlation_id: string
  mode: 'LIVE_KEYCLOAK'
  events: LiveLoginEvent[]
  /** IF-V5-04 (v6, WS1 backend): the backend's own completeness
   *  assessment of this transaction's recorded timeline. Present on
   *  the v6 /api/v1/live-logins payload; absent on older backends,
   *  in which case the frontend mirrors the same canonical predicate
   *  locally (see lib/liveLogins assessLiveLoginTimeline). */
  timeline_complete?: boolean
  /** True only when the timeline is complete AND ends in a
   *  SESSION_CREATED with outcome ok. Never true for a truncated
   *  tail that merely contains a SESSION_CREATED ok event. */
  successful?: boolean
  missing_stages?: string[]
  truncated_at?: string | null
  retention_reason?: string | null
}

export type ViewId =
  | 'overview' | 'portal' | 'scenarios' | 'flow' | 'protocol' | 'rules'
  | 'compare' | 'boundaries' | 'findings' | 'reports' | 'settings' | 'learn'
