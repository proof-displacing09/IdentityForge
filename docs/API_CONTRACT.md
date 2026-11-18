# API Contract — IdentityForge (v3, Operation Trustline third release)

> Version: `v1` (paths under `/api/v1/`). All JSON unless stated otherwise.
> All endpoints bind to loopback only (`127.0.0.1:8000`). There is no
> wildcard CORS; the only allowed origin is the lab frontend
> (`http://127.0.0.1:5173`). Sensitive responses carry
> `Cache-Control: no-store` and standard security headers (see §8).
>
> Error shape (all endpoints): FastAPI's `{"detail": "<stable-code>"}`.
> The `detail` value is a stable machine-readable code
> (`csrf_denied`, `unauthenticated`, `policy_denied`, `rate_limited`,
> `unknown_scenario`, `invalid_json`, `run_not_found`,
> `live_login_not_found`, `scenario_not_found`); there is no
> `{"error": {"code": ...}}` envelope and never a stack trace, token,
> code, verifier, or internal detail in an error body.
>
> Ports are FIXED for this lab (P1-14): 8080/8000/5173 are part of the
> issuer/redirect identity. There is no supported port override.

## 1. Health and lab metadata

### `GET /api/v1/health`

- **Auth:** none (liveness only — reveals no lab data).
- **Response 200:** `{"status": "ok", "service": "identityforge-backend", "version": "1.7.1", "provider_mode": "keycloak-local", "keycloak": "see /api/v1/lab/status for measured IdP status", "synthetic_data_label": "SYNTHETIC LAB DATA — NOT REAL IDENTITY INFORMATION"}`.
  Health is liveness only: it does NOT claim Keycloak is up. Used by
  the Compose healthcheck and `scripts/doctor.sh` (which additionally
  verifies the service name — a bare 200 from another process is not
  enough; see P1-21).
  **Version (v6, IF-V5-05; v7.1 carries it at 1.7.1):** `version` is the version the RUNNING
  backend reports, and it must equal the release version (1.7.1) —
  enforced by `scripts/check-version-contract.py`, which compares the
  manifest, `backend/pyproject.toml`, `backend/src/identityforge/__init__.py`,
  the FastAPI version, this health version, and the frontend package
  files. The UI About card reads this value from this endpoint; the
  UI holds no competing hard-coded version string. Never quote a
  hard-coded version in a doc as proof of the deployed artifact —
  only this measured value (and the matching sources) proves it.

### `GET /api/v1/lab/status`

- **Auth:** none. The measured lab status.
- **Response 200:**
  ```json
  {
    "backend": "ok",
    "issuer": "http://127.0.0.1:8080/realms/identityforge-lab",
    "provider_mode": "keycloak-local",
    "idp": {"reachable": true, "issuer_matches": true, "discovery_url": "http://keycloak:8080/realms/identityforge-lab/.well-known/openid-configuration", "reason": "OK"},
    "evidence": {"events_saved": 536, "event_save_errors": 0, "evidence_available": true},
    "last_verified_login": {"at": "2026-11-11T...", "username": "student_01", "subject": "10000000-0000-4000-8000-000000000001", "issuer": "http://127.0.0.1:8080/realms/identityforge-lab"}
  }
  ```
- `idp.reachable` is a live discovery fetch (via the transport base)
  with the issuer validated; `last_verified_login` is set only when a
  real callback actually succeeded in this backend process, and is
  `null` otherwise. Neither is inferred from a running container.
  On a host run the transport base is `http://127.0.0.1:8080`; in
  Compose it is `http://keycloak:8080` (the Keycloak service DNS
  name on the private bridge network — v3, P0-04). The canonical
  issuer is `http://127.0.0.1:8080/realms/identityforge-lab` in both.
- **Evidence health (P1-11, v3):** `evidence` reports process-lifetime
  counters for live-login event saves: `events_saved` (events
  persisted), `event_save_errors` (failed saves, WARNING-logged with
  stage/outcome/reason only — no secret material), and
  `evidence_available` (False exactly when errors > 0 and saved == 0).
  When errors > 0, `partial_timeline_reason` explains that recorded
  timelines may be incomplete — the Atlas must not present a timeline
  as complete when no event was captured. Counters survive a lab
  reset by design (they describe this backend process, not the
  evidence store). A failed save never breaks a login; read
  endpoints (`/live-logins`) still fail closed (500) on a
  locked/corrupt store.

### `GET /api/v1/lab/config`

- **Auth:** none. Returns **safe public metadata only** — no secrets, no
  internal URLs beyond the loopback lab addresses.
- **Response 200:** `issuer`, `client_id`, `redirect_uri`,
  `frontend_url`, `provider_mode`, `fixture_revision`,
  `clock_skew_seconds`, `session_ttl_seconds`,
  `synthetic_data_label`.
- **P0-02:** this is a PURE READ. It does not set, rotate, or mint any
  cookie. A client that cached a CSRF token keeps using it after
  reading config (the Trustline v2 fix — config GET used to mint a
  fresh CSRF cookie on every call, invalidating the frontend's cache).

### `GET /api/v1/csrf-token`

- **Auth:** none. Returns `{"csrf_token": "<token>"}` and sets the
  `identityforge_csrf` cookie to the SAME value.
- **Deterministic lifecycle (P0-02):** idempotent per browser. If the
  browser already presents a well-formed CSRF cookie, the endpoint
  returns that token; it mints a new one only when the browser has
  none. The cookie value and the returned header value are always
  identical. See §6 for rotation and the client retry rule.

## 2. Scenarios and runs (research console)

### `GET /api/v1/scenarios`

- **Auth:** none (scenario definitions are public lab content).
- **Response 200:** `{"scenarios": [...], "count": 18}` — scenario
  definitions: `id`, `title`, `explanation`, `attack_surface`,
  `expected_secure_result`, `mode`, `preconditions`.

### `GET /api/v1/scenarios/{id}`

- **Auth:** none.
- **Response 200:** one scenario definition.
- **Response 404:** `{"detail": "scenario_not_found"}`.

### `POST /api/v1/runs`

- **Auth:** same-origin + CSRF token required (v2 P1-10 — scenario
  creation writes evidence, so it enforces the same contract as
  logout and reset). Missing/wrong token or hostile Origin →
  **403** `{"detail": "csrf_denied"}`. The CLI uses the engine
  directly and is unaffected.
- **Rate limit:** 30 runs/minute per client IP → **429**
  `{"detail": "rate_limited"}`. `GET /auth/login` is separately
  limited (v4, P1-11): 30 starts/minute per browser key, 120/minute
  globally → **429** `{"detail": "rate_limited", "reason":
  "LOGIN_RATE_LIMITED"}` (see §4).
- **Request size (v4, P1-04):** every request body is bounded by a
  genuinely streaming limit of **1,048,576 bytes, inclusive**
  (exactly at the bound is allowed; one byte over → **413**
  `{"detail": "request_too_large"}`). The bound is enforced on the
  actual streamed bytes, not only on `Content-Length`: chunked
  bodies with no `Content-Length` are counted as they stream.
  Missing `Content-Length` → the stream is counted; duplicate
  identical `Content-Length` values → used; duplicate conflicting,
  negative, or non-integer values → **400**
  `{"detail": "malformed_content_length"}`; declared over the bound
  → 413 without reading the body. An oversized request is rejected
  before JSON parsing, evidence writes, CSRF, or rate-limit
  consumption — a 413 never consumes rate budget and never requires
  CSRF; in-bound requests still go through CSRF normally.
- **Body:** JSON object `{"scenario_id": "I6"}` (case-insensitive;
  the id is upper-cased). Malformed JSON or a non-object body →
  **400** `invalid_json`; unknown id → **400** `unknown_scenario`.
- **Response 200:** a `ComparisonResult` (see §5). It never touches
  the real portal session store and never contacts Keycloak.
- **Guarantee:** a run created here can never mint a portal session
  and can never change the secure portal's configuration. It operates
  on synthetic transactions in an isolated harness.

### `GET /api/v1/runs/{id}`

- **Auth:** none (run records contain no secrets; see §5).
- **Response 200:** the stored run record. **404** `run_not_found`.

### `GET /api/v1/runs/{id}/events`

- **Auth:** none.
- **Response 200:** `{"run_id": ..., "events": [...]}` — the redacted
  transaction timeline: ordered steps with `step`, `state`,
  `validator`, `outcome`, `reason_code`, `timestamp`,
  `correlation_id`. No tokens, codes, verifiers, or cookies appear.
  **404** `run_not_found`.

### `GET /api/v1/runs/{id}/report`

- **Auth:** none.
- **Response 200:** the stored run report as JSON by default.
  `?format=md` returns a Markdown rendering (`text/markdown`) that
  prints the v2 session/provenance fields (see §5).
  `?format=csv` is NOT a server format — it returns the JSON report;
  CSV export is generated client-side by the frontend, which must
  neutralize formula injection there (see §5).
  **404** `run_not_found`.

### `GET /api/v1/lab/counts`

- **Auth:** none. Read-only counts of what a reset would clear, so
  Settings can show the affected evidence before the operator
  confirms. Counts are lab metadata, not secrets.
- **Response 200:** `{"runs": <int>, "sessions": <int>,
  "sessions_total_issued": <int>, "live_logins": <int>,
  "transactions": <int>, "events": <int>, "runs_limit": <int>,
  "events_limit": <int>, "live_logins_limit": <int>}` — stored runs,
  live sessions, live-login events, and live login transactions
  respectively. (v3, P0-01.)
- **Semantics (v5, IF-V4-03 / IF-V4-11):** `sessions` is ACTIVE
  sessions only — live, unexpired, unrevoked (expired/revoked
  records are pruned on access and never counted).
  `sessions_total_issued` is the separate process-lifetime total of
  sessions ever minted by this backend process; a lab reset clears
  stored sessions but does not rewind it. `events` is the stored
  scenario-timeline event count, and the `*_limit` fields expose the
  documented retention caps (latest 1000 runs, 20000 events, 1000
  live-login events) so the UI can show the storage budget; see
  `docs/EVIDENCE_RETENTION.md`.
- **Retention honesty (v6, IF-V5-08):** "Old evidence is automatically
  pruned at capacity; manual full reset requires an officer session +
  CSRF + two confirmations." The caps above are the pruning bound:
  when a store is at its cap, the next save evicts the oldest record
  at that cap — export anything still needed first (Findings &
  Evidence downloads, or `GET /api/v1/runs/{id}/report`), because a
  pruned run cannot be recovered. Pruning, manual reset, session
  revocation, and Keycloak realm/volume deletion are four different
  actions — see `docs/EVIDENCE_RETENTION.md` for the distinction.

### `POST /api/v1/lab/reset`

- **Purpose:** reset synthetic lab state — evidence store (runs AND
  live-login events), in-memory sessions, transactions, and
  `last_login` — to a clean state. Explicit local-operator action only.
- **Auth (v3, P0-01 — officer-only):** ALL three are required, in
  this check order: (a) a valid CSRF token → **403** `csrf_denied`
  otherwise; (b) a valid, unexpired, unrevoked live session →
  **401** `unauthenticated` otherwise; (c) the session's roles must
  include `officer` → **403** `policy_denied` for a student session;
  (d) a deliberate confirmation body `{"confirm": "RESET_LAB"}` →
  **422** `invalid_confirmation` otherwise (missing body, wrong
  value, or non-object body). No writes happen before authorization
  succeeds. **The v2 statement that reset is an unprivileged
  single-operator localhost action is FALSE in v3 and is withdrawn:**
  CSRF alone can no longer authorize a reset — a logged-in officer
  session is required, because `GET /api/v1/csrf-token` is
  intentionally public and a token alone must never authorize
  wiping another operator's evidence.
- **Response 200:** `{"status": "reset", "operator": "<username>", "cleared": {"runs": <int>, "sessions": <int>, "live_logins": <int>, "transactions": <int>}, "operator_session_revoked": true, "csrf_token": "<fresh token>"}` and a rotated CSRF cookie.
  The caller MUST adopt the returned `csrf_token` — the old token is
  dead after reset. **The operator's own session IS revoked by the
  reset** (`operator_session_revoked: true`): after a successful
  reset the officer must sign in again. The `cleared` counts are the
  pre-reset values from `GET /api/v1/lab/counts`.
- **Two-stage clear:** evidence is cleared first; if that fails the
  endpoint returns **500** `reset_failed` and sessions are left
  untouched — a half-cleared lab (evidence gone, sessions live) is
  worse than a failed reset.
- **Guarantee:** this endpoint resets *lab state only*. It cannot
  change the secure portal into an unsafe mode, cannot alter the
  Keycloak realm or its persistent volume, and cannot disable any
  validator. It does not reset Keycloak. The evidence-health
  counters in `GET /api/v1/lab/status` (`events_saved`,
  `event_save_errors`) are process-lifetime and intentionally
  survive a reset.
- **Retention wording (v6, IF-V5-08):** "Old evidence is automatically
  pruned at capacity; manual full reset requires an officer session +
  CSRF + two confirmations." This endpoint is the manual full reset
  in that sentence — the two confirmations are the two dialogs in
  Lab Settings (the API additionally requires the
  `{"confirm": "RESET_LAB"}` body). It is NOT automatic pruning
  (oldest-only, at capacity, on save), NOT session revocation
  (logout/expiry revokes sessions but deletes no evidence), and NOT
  Keycloak realm/volume deletion (`docker compose down -v` /
  `scripts/reset.ps1 -Confirm` delete the volumes on the host with
  no officer session or CSRF involved). See
  `docs/EVIDENCE_RETENTION.md` for the four-way distinction.

## 3. Real Keycloak login evidence (P0-05)

These endpoints expose ONLY what the backend actually observed
(BFF-observed redirect, callback, binding, token exchange, ID-token
validation, session creation, authorization decisions, logout).
Stages the BFF cannot observe (Keycloak's internal password
authentication) are recorded as NOT OBSERVED, never SUCCESS by
assumption. No raw token, code, state, PKCE verifier, client secret,
password, cookie, or authorization URL is stored or returned.
Subjects appear as a SHA-256 hash plus the synthetic username
(`student_01` / `officer_01`).

### `GET /api/v1/live-logins`

- **Auth:** none (records contain no secrets).
- **Response 200:** `{"mode": "LIVE_KEYCLOAK", "logins": [...]}` —
  up to 20 most recent real logins, each with `correlation_id`
  (the login transaction id), `mode: "LIVE_KEYCLOAK"`, and `events`
  (ordered `LiveLoginEvent`s: `stage`, `outcome` (`ok` /
  `rejected` / `error`), `reason_code`, `subject_hash`, `username`,
  `detail`, `at`). Stages: `AUTH_STARTED`, `CALLBACK_RECEIVED`,
  `BINDING_VERIFIED`, `TOKEN_ENDPOINT`, `ID_TOKEN_VALIDATED`,
  `SESSION_CREATED`, `AUTHORIZATION_DECISION`, `LOGOUT`.
- This namespace is NEVER mixed with `OFFLINE_FIXTURE` runs. An
  offline run id must never be presented as a real login.

### `GET /api/v1/live-logins/{correlation_id}`

- **Auth:** none.
- **Response 200:** one live login with its full event list.
  **404** `live_login_not_found`.

## 4. Authentication (portal)

### `GET /auth/login`

- **Auth:** none (it *starts* authentication).
- **Behaviour:** creates a server-side transaction (random `state`,
  `nonce`, PKCE verifier + S256 challenge), stores it, sets the
  HttpOnly per-transaction browser-binding cookie
  `identityforge_txn_<state>` (v3, P1-06 — one cookie per login
  transaction), and redirects
  (302) to the Keycloak authorization endpoint with the exact
  registered `redirect_uri`, `client_id=campus-club-portal`,
  `response_type=code`, `scope=openid`, `state`, `nonce`,
  `code_challenge`, and `code_challenge_method=S256`.
- **Transaction caps (v4, P1-10):** at most **4 live transactions
  per browser** and **20 live transactions globally**. A browser
  that starts a 5th transaction evicts only its OWN oldest
  transaction — never another browser's. When the global cap is
  reached, login returns **503** `{"detail":
  "provider_unavailable", "reason": "TRANSACTION_STORE_FULL"}`.
  The browser is correlated by an anonymous HttpOnly
  `identityforge_browser` cookie (random 128-bit value, `SameSite=Lax`,
  `path=/auth`, set on the login-start response when absent or
  invalid); the server stores only its SHA-256 hash — the raw value
  is never stored, logged, or included in evidence.
- **Rate limit (v4, P1-11):** 30 login starts/minute per browser key
  and 120/minute globally → **429** `{"detail": "rate_limited",
  "reason": "LOGIN_RATE_LIMITED"}`. The browser cookie is set on
  every login response (including 429/503) so the limit sticks;
  cookie-discarding clients are still bounded by the global bucket.
- **Response:** 302 to Keycloak. No token or verifier is exposed.

### `GET /auth/callback?code=...&state=...`

- **Auth:** none (it *completes* authentication).
- **Behaviour:** verifies the browser binding, then `state` once
  (then invalidates it), handles an IdP `error` parameter safely,
  exchanges the code + PKCE verifier server-to-server, validates
  the ID token (signature via JWKS, `iss`, `aud`, `azp`, `nonce`,
  `exp`, `iat`/`nbf`, `alg` allowlist RS256, known `kid`), rotates
  the session ID, creates a server-side session, sets the `HttpOnly`
  `SameSite=Lax` session cookie, and redirects to the portal.
  **JWKS (v3, P1-07 + fix):** real Keycloak publishes two RSA keys —
  an RS256 signing key (`use: sig`) and an RSA-OAEP encryption key
  (`use: enc`). The JWKS parser SKIPS non-signing keys (enc,
  non-RS256 `alg`, non-RSA `kty`) and returns only usable signing
  keys; a malformed *signing* key still fails the whole document
  (`JWKS_ERROR`, no session). The over-strict v3 rule that rejected
  the document for the enc key broke every real login and was fixed
  2026-11-11 (see `docs/VERIFICATION_LOG.md`, v3 section).
- **Failure response:** redirect to the frontend with a safe error
  and a stable reason code (`STATE_BINDING_MISMATCH`, `STATE_REUSED`,
  `PROVIDER_ERROR`, … — see `docs/AUTH_FLOW.md` §2); **no session is
  created**. The reason code is the stable, non-sensitive identifier,
  never a stack trace or token.
- **Replay:** a second callback with the same `code`/`state` is
  rejected with `STATE_REUSED`. A callback from a different browser
  than the one that started the login is rejected with
  `STATE_BINDING_MISMATCH` and does NOT consume the transaction —
  the legitimate browser can still complete it.
- **Keycloak behaviour (measured 2026-11-11):** a failed PKCE
  exchange at the real token endpoint returns 400 `invalid_grant`
  ("PKCE verification failed") AND burns the authorization code — a
  second exchange of the same code returns 400 `invalid_grant`
  ("Code not valid"). Test drivers must use a disposable transaction
  for wrong-verifier probes; see `scripts/live-gate.py`.

### `POST /auth/logout`

- **Auth:** CSRF token required (see §6) → **403** `csrf_denied`
  otherwise. A valid session is NOT required: logout revokes the
  session if one exists and always reports the local revocation.
  (Verified live 2026-11-11: valid CSRF + no session cookie → 200.)
- **Behaviour:** revokes the session server-side, clears the session
  cookie, records a `LOGOUT` live event, rotates the CSRF token and
  returns it in-band (`{"status": "logged_out", "csrf_token":
  "<fresh>"}`) so the caller's next mutation does not 403.
- **Response 200:** `{"status": "logged_out", "csrf_token": ...}`.
- **Semantics:** APP-LOCAL revocation ONLY. This does NOT end the
  IdP's SSO session at Keycloak. The UI must say so; it must never
  imply IdP logout happened.

## 5. Portal (protected resources)

All portal endpoints require a valid server-side session (opaque
cookie). They return **401** `{"detail": "unauthenticated"}` with no
session, and **403** `{"detail": "policy_denied"}` when the subject
lacks the required role. The body never reveals whether a resource
exists for another user. Allowed decisions are recorded as
`AUTHORIZATION_DECISION` live events (P0-05).

### `GET /api/v1/portal/me`

- **Auth:** session required.
- **Response 200:** synthetic profile of the signed-in subject:
  ```json
  {"sub": "<subject id>", "username": "student_01", "roles": ["member"], "issuer": "http://127.0.0.1:8080/realms/identityforge-lab", "expires_at": "<iso>", "synthetic_data_label": "SYNTHETIC LAB DATA — NOT REAL IDENTITY INFORMATION"}
  ```
  The identity is the validated `(iss, sub)` pair; `username` is a
  display label from the trusted token, never a lookup key for
  authorization. Roles come from the backend policy map, never from
  token role claims.

### `GET /api/v1/portal/member`

- **Auth:** session + role `member`.
- **Response 200:** the fictional member-only resource (club notices).
- **403** `policy_denied` without the `member` role.

### `GET /api/v1/portal/officer`

- **Auth:** session + role `officer`.
- **Response 200:** the fictional officer-only resource (club roster / budget).
- **403** `policy_denied` for `student_01` (member only).

## 6. Run / report record (shared shape) — v3 session semantics

```json
{
  "run_id": "<uuid>",
  "scenario_id": "I6",
  "title": "Wrong audience",
  "mode": "DETERMINISTIC OFFLINE FIXTURE",
  "status": "PASS",
  "expected_outcome": "reject",
  "secure_result": "reject",
  "flawed_result": "accept",
  "secure_reason": "WRONG_AUDIENCE",
  "flawed_reason": "OK",
  "secure_session_created": false,
  "flawed_session_created": false,
  "session_preexisted": false,
  "session_revoked": false,
  "flawed_model_status": "EXECUTED",
  "flawed_guard_omitted": "audience check",
  "flawed_observed_result": "accepted with mismatched audience",
  "protected_resource_disclosed": false,
  "resource_access": {},
  "timeline": [],
  "decisions": [],
  "elapsed_ms": 12,
  "evidence_saved": true,
  "evidence_error": "",
  "evidence_provenance": "OFFLINE_FIXTURE",
  "limitations": "Offline fixture; not a live Keycloak execution."
}
```

Session fields describe what ACTUALLY happened in the test (P0-06) —
never a convenient boolean:

| Field | Meaning |
|---|---|
| `secure_session_created` | `SessionStore.create/rotate` EXECUTED on the secure path of this run (I1 login, I11 rotation). False everywhere else. |
| `flawed_session_created` | The flawed path EXECUTED a session creation. False for I16/I17/I18 (no session exists in those tests) and for I14 (the flawed path also rejects). |
| `session_preexisted` | A legitimate session already existed before the tested action (I10 first redemption, I13 student login, I12 login before logout). A denied action leaves it valid — a rejection does NOT mean "no session existed". |
| `session_revoked` | A session was revoked by the tested action (I12 logout). |
| `flawed_model_status` | `EXECUTED` (the flawed comparator ran) or `NOT_MODELED` (no meaningful flawed session path exists; the flawed decision is still recorded in `flawed_result`). |
| `flawed_guard_omitted` | The single check the flawed fixture omitted (one per scenario). Empty when nothing meaningful was omitted. |
| `flawed_observed_result` | What the flawed path observably did (e.g. "accepted with mismatched audience", "also rejected: unparseable token"). |
| `protected_resource_disclosed` | True only when the flawed path discloses a protected resource to an actor who must not have it (I13 spoofed officer role). |
| `evidence_saved` | Defaults to **False**. Set to True only AFTER the SQLite transaction commits (P1-09). A run with no store is `evidence_provenance: EPHEMERAL` and `evidence_saved: false` — it must never be presented as persisted evidence. |
| `evidence_provenance` | `OFFLINE_FIXTURE` (saved offline run), `EPHEMERAL` (no store — CLI/offline unsaved run), or `LIVE_KEYCLOAK` (real-login timeline; only on `/live-logins`). |

`status` is one of `PASS | FAIL | ERROR | SKIPPED | INCONCLUSIVE`.
`evidence_hash` (in stored reports) proves the integrity of the
redacted record only — not the truth of the underlying claim.

## 7. CSRF and origin rules (P0-02 lifecycle)

- **Mutations** (`POST /api/v1/runs`, `POST /api/v1/lab/reset`,
  `POST /auth/logout`) require the `x-csrf-token` header whose value
  equals the `identityforge_csrf` cookie, **and** an `Origin`
  matching the lab frontend origin. Failure → **403**
  `{"detail": "csrf_denied"}`.
- **Lifecycle:** `GET /api/v1/csrf-token` is idempotent per browser
  (returns the existing token, mints only when absent).
  `GET /api/v1/lab/config` never touches the token. `POST
  /api/v1/lab/reset` and `POST /auth/logout` ROTATE the token and
  return the fresh value in-band as `csrf_token` in the JSON body
  (plus a rotated cookie) — the client MUST adopt it.
- **Client rule:** on a 403 `csrf_denied` from a mutation, the client
  may refresh the token once and retry the mutation at most once.
  A second 403 is a real failure and must be surfaced, not retried.
  A logout/reset must never be reported as successful unless the
  backend confirmed it.
- `GET /auth/login` is not CSRF-protected in the usual sense (it
  starts a login), but the transaction it creates is bound to the
  browser session via `state` + the binding cookie, which is the
  login-CSRF defence.
- No endpoint accepts a `state`, issuer URL, or redirect URI from the
  request body to override the pinned lab configuration.

## 8. Headers and caching

- Sensitive API responses and authenticated pages: `Cache-Control: no-store`,
  `Pragma: no-cache`.
- Security headers on all responses: `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`,
  `Content-Security-Policy` appropriate to the frontend (no inline tokens).
- `Strict-Transport-Security` is **not** sent over local HTTP (it would be
  meaningless); it is required if the lab is ever served over HTTPS.
- Cookies: `HttpOnly` (session + transaction binding cookies),
  `SameSite=Lax`, `Path=/`; `Secure` only under HTTPS (local HTTP
  exception, documented in `docs/VALIDATION_AND_LIMITATIONS.md`).
  The CSRF cookie is intentionally readable by the frontend script
  (double-submit pattern); it is not an authentication credential.

## 9. Versioning

- The contract version is `v1`. Breaking changes require a new version
  prefix (`/api/v2/`). Additive fields are allowed within `v1`.
- The backend must return `404` `NOT_FOUND` for unknown `/api/v1/` routes
  rather than an HTML error page.
