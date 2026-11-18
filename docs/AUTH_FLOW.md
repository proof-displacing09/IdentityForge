# Authentication Flow — IdentityForge

> Plain-language summary: signing in is a relay race. The browser carries a
> message (an authorization code) from Keycloak to the backend, and the
> backend — not the browser — checks that the message is genuine before
> creating a session. Every handoff is tied to the one before it with a
> random secret, so a message from a different race cannot be substituted.

## 1. The real login (happy path, scenario I1)

```
Browser                Backend BFF (127.0.0.1:8000)        Keycloak (127.0.0.1:8080)
  |                              |                                   |
  |  GET /auth/login             |                                   |
  |----------------------------->|  1. Create transaction:           |
  |                              |     random state, nonce,            |
  |                              |     PKCE verifier + S256 challenge  |
  |                              |     (stored server-side, short-lived)
  |                              |                                   |
  |  302 -> Keycloak             |  2. Redirect to authorization     |
  |  /authorize?client_id=       |     endpoint with exact registered  |
  |  campus-club-portal          |     redirect_uri, state, nonce,     |
  |  &code_challenge=...         |     code_challenge                  |
  |------------------------------|---------------------------------->|
  |                              |                                   |
  |  (user signs in as a         |                                   |
  |   synthetic user in          |                                   |
  |   Keycloak)                  |                                   |
  |                              |                                   |
  |  302 -> /auth/callback       |  3. Keycloak redirects back with  |
  |  ?code=...&state=...         |     a one-time authorization code   |
  |----------------------------->|                                   |
  |                              |  4. Verify state (once, then       |
  |                              |     invalidate), check for IdP error |
  |                              |  5. Exchange code + PKCE verifier |
  |                              |     for tokens (server-to-server)   |
  |                              |---------------------------------->|
  |                              |  6. ID token returned             |
  |                              |<----------------------------------|
  |                              |  7. Validate ID token: signature  |
  |                              |     (JWKS), iss, aud, exp, nonce, |
  |                              |     alg allowlist                  |
  |                              |  8. Rotate session ID, create      |
  |                              |     server-side session, set        |
  |                              |     HttpOnly SameSite=Lax cookie    |
  |  302 -> / (signed in)        |                                   |
  |<-----------------------------|                                   |
```

Key properties:

- **Tokens never touch the browser.** The code exchange and token
  validation happen server-to-server. The browser only ever sees the
  authorization code (in the redirect URL) and the opaque session cookie.
- **No token in storage.** No ID/access/refresh token is written to
  `localStorage` or `sessionStorage`.
- **One transaction, one use.** `state`, `nonce`, the PKCE verifier, and the
  authorization code are each consumed once and then invalidated. Replaying
  the callback URL fails (scenarios I7/I10).

## 2. Transaction state machine

The backend records one redacted event per transition (no codes, verifiers,
tokens, or cookies are stored — see §5).

```
CREATED -> AUTHORIZATION_STARTED -> CALLBACK_RECEIVED -> CODE_REDEEMED
        -> TOKEN_VERIFIED -> SESSION_CREATED
```

Any failure moves the transaction to a rejected state tagged with a stable
reason code, for example:

> Reason codes below are the exact `FailureReason` values in
> `backend/src/identityforge/models.py` — the human description sits
> beside the code, never in place of it.
> `scripts/validate-docs-contract.py` fails CI if a doc names any
> other code. (v5, IF-V4-06: earlier versions of this table used
> invented codes that are not `FailureReason` values; the enum is
> the only authority, and the v5 findings table in
> `docs/REMEDIATION_FINDINGS.md` records what the old codes were.)

| Reason code | Meaning | Scenario |
|---|---|---|
| `STATE_MISMATCH` | Callback `state` does not match the stored transaction (or is missing/stale) | I2 |
| `PKCE_MISMATCH` | Token endpoint rejected the verifier (or the fixture verifier differs) | I3 |
| `REDIRECT_URI_MISMATCH` | Redirect URI is not the exact registered one | I4 |
| `WRONG_ISSUER` | Token `iss` is not the pinned lab issuer | I5 |
| `WRONG_AUDIENCE` | Token `aud` is not `campus-club-portal` | I6 |
| `EXPIRED` | Token `exp` is in the past (beyond bounded skew) | I7 |
| `CODE_REUSED` | Authorization code already redeemed (second redemption of the same code) | I10 |
| `STATE_REUSED` | Callback / `state` already consumed (replayed callback) | I2, I10 |
| `NONCE_MISMATCH` | Token `nonce` does not match the transaction nonce | I8 |
| `BAD_SIGNATURE` | Signature does not verify against the issuer JWKS | I9 |
| `ALG_NOT_ALLOWED` | `alg` is not in the allowlist (`alg=none`, confusion, unknown) | I9 |
| `MALFORMED_TOKEN` | Token absent or not a well-formed JWT | I14 |
| `CSRF_DENIED` | State-changing request failed origin/CSRF validation | I16 |
| `INPUT_TOO_LONG` / `MALFORMED_INPUT` | Input exceeded bounds or failed schema validation | I17 |
| `UNTRUSTED_ISSUER_URL` | A supplied issuer URL is not the pinned lab issuer (metadata / private-IP URLs are rejected as `SSRF_BLOCKED` instead; either way there is no outbound fetch) | I18 |

I7 also contains a replay subtest (a previously consumed code/state,
run separately from the expiry subtest — see
`docs/SCENARIO_METHOD.md` §4); its reason is `CODE_REUSED` or
`STATE_REUSED` as above, not a single "replayed" code.

**I3 — fixture reason vs Keycloak's real error (do not conflate
them).** The offline fixture's reason for a wrong PKCE verifier is
`PKCE_MISMATCH`: the lab's deterministic model of the denial. Against
the real Keycloak token endpoint the same wrong verifier is denied by
Keycloak itself with the OAuth error `invalid_grant` ("PKCE
verification failed") — a different string from a different layer,
and the failed exchange burns the code (see `docs/TEST_MATRIX.md`
K2). When you read a report, `PKCE_MISMATCH` means "the lab fixture
modelled this denial"; `invalid_grant` means "Keycloak itself refused
the exchange".

A rejected transaction **never** creates a session and **never** grants
resource access. Every negative test asserts both the reason code *and*
the absence of a session/resource access.

## 3. Sessions

- **Format:** opaque random session ID in an `HttpOnly`, `SameSite=Lax`
  cookie. `Secure` is set only under HTTPS; on local HTTP the lab documents
  this as a development exception (see `docs/VALIDATION_AND_LIMITATIONS.md`).
- **Storage:** server-side (SQLite/in-memory store in the backend). The
  cookie is only a lookup key; it carries no identity claims.
- **Rotation:** a fresh session ID is issued on login (prevents session
  fixation, scenario I11). The pre-login session ID is invalidated.
- **Expiry:** sessions are bounded in lifetime and expire server-side.
- **Logout:** `POST /auth/logout` revokes the session server-side and
  clears the cookie. Replaying the old cookie afterwards is rejected
  (scenario I12).

## 4. Authorization (separate from authentication)

Authentication answers *"who signed in?"* (validated issuer + subject).
Authorization answers *"may this subject do this?"* and is checked
independently on every protected resource, server-side:

- `GET /api/v1/portal/member` — any authenticated subject with role `member`.
- `GET /api/v1/portal/officer` — only a subject with role `officer`.
  `student_01` (member only) is denied here even though their login is valid
  (scenarios I1, I13). Roles come from the backend policy map keyed by
  `(issuer, sub)` — never from token role claims. A token whose `sub`
  is not one of the two pinned UUIDs is rejected at callback with
  `UNKNOWN_SUBJECT` and gets no roles (v3 P1-10).

## 5. What is logged (and what is never logged)

Logged (redacted): run/transaction IDs, timestamps, validator name, outcome,
reason code, correlation ID, step transitions.

**Never logged, stored, or shown:** full tokens, authorization codes, PKCE
verifiers, nonces, client secrets, session cookies, or passwords. Evidence
stores a hash of the redacted record, not the secret material. If you see a
full token in a screenshot, log, or report, treat it as a defect and report
it (see `SECURITY.md`).

## 6. The issuer hostname trap (read this before debugging)

The browser and the backend must agree on the issuer string
`http://127.0.0.1:8080/realms/identityforge-lab`. The canonical issuer
and the network route are separate (Operation Trustline ADR,
`docs/KEYCLOAK_INTEGRATION.md`):

- **Canonical issuer** (browser-visible, in tokens and discovery):
  `http://127.0.0.1:8080/realms/identityforge-lab`. Keycloak is started
  with the hostname-v2 settings `KC_HOSTNAME=http://127.0.0.1:8080` and
  `KC_HOSTNAME_ADMIN=http://127.0.0.1:8080` (full URLs, including
  scheme and port). The old `--hostname-url` / `--hostname-admin-url`
  flags were removed in Keycloak 26.x and must not be used; the v1
  `KC_HOSTNAME_PORT` option is also rejected/deprecated — an earlier
  Trustline fix that used bare hosts (`KC_HOSTNAME=127.0.0.1`,
  `KC_HOSTNAME_PORT=8080`) failed the live boot and is recorded as
  history in `docs/REMEDIATION_FINDINGS.md`, not as current guidance.
- **Backend transport route** (Compose only):
  `http://keycloak:8080` (v3 P0-04 — the Keycloak service DNS name on
  the private bridge network; `extra_hosts` removed, all
  `container_name:` lines removed). The backend fetches discovery,
  token and JWKS over this route, but discovery's `issuer` must equal
  the canonical issuer exactly, and the endpoints must be the pinned
  realm paths under it. The backend rewrites only the host:port of
  those endpoints to the transport host, and only to an allowlisted
  transport host. The internal Docker name is NEVER substituted for
  the issuer identity: `keycloak` is allowlisted only as a transport
  host and is rejected by issuer/discovery validation. **Provenance
  fetch (v4, P0-01):** the bare `fetch_jwks` / `validate_jwks_url`
  still reject `keycloak:8080` (`SSRF_BLOCKED`) — the v3 code called
  `fetch_jwks` on the rewritten URL, so the Docker backend failed
  every login at JWKS retrieval. All backchannel fetches now go
  through provenance-carrying functions (`fetch_jwks_via_transport`,
  `post_token_via_transport`, `fetch_discovery_via_transport` in
  `protocol/jwks.py`): the canonical URL is validated BEFORE the
  rewrite, the transport base is validated as the configured
  `idp_transport_base`, and the rewritten URL is re-validated
  narrowly before any network call.

Never "fix" a mismatch by disabling issuer validation — that is
exactly scenario I5, and the lab's tests will fail if you do.

## 6b. Browser-bound login transactions (P0-07)

`state` alone is not bound to the browser that started the login: the
old code looked up a global state value, so any browser presenting a
known state could complete the login. Now `/auth/login` also sets an
`HttpOnly`, `SameSite=Lax`, short-lived cookie
`identityforge_txn_<state>` containing a random binding token (only its
SHA-256 is stored server-side, next to the transaction) — one cookie
per login transaction (v3 P1-06; v4 P1-10 — at most 4 live
transactions per browser, 20 globally; a browser evicts only its own
oldest; the global cap returns 503 `TRANSACTION_STORE_FULL`). The
browser is correlated by an anonymous HttpOnly `identityforge_browser`
cookie (random 128-bit value; only its SHA-256 hash is stored), and
login starts are rate-limited to 30/minute per browser key and
120/minute globally (429 `LOGIN_RATE_LIMITED`). `/auth/callback` requires the cookie named
for the presented `state` to match the transaction before consuming
it; a wrong or missing binding cookie returns
`STATE_BINDING_MISMATCH` and does NOT consume the transaction, so the
legitimate browser can still complete the login while another browser
cannot steal it. A mismatch does not consume the transaction, and a
successful login deletes only that transaction's cookie — so two
tabs can log in independently, in either order, and the live gate's
parallel flow proves it (see `docs/KEYCLOAK_INTEGRATION.md`).

## 6c. Subject-to-policy mapping (P0-06)

Real Keycloak `sub` values are stable UUIDs, not usernames. The realm
import pins deterministic subject IDs (`student_01` →
`10000000-0000-4000-8000-000000000001`, `officer_01` →
`10000000-0000-4000-8000-000000000002`), and the backend policy map is
keyed by `(issuer, sub)`. The display username comes from that pinned
mapping, never from a raw `sub` or an untrusted token claim. An
unknown subject is rejected at callback with `UNKNOWN_SUBJECT` and
gets no roles. Token role claims are never trusted (scenario I13).

## 7. Logout and error behaviour

- Logout (POST /auth/logout, CSRF-protected) revokes the session
  server-side and deletes the cookie; the UI reports success ONLY
  when the backend confirms revocation. A failed revocation is shown
  as an error and the session UI is kept, never cleared visually.
- Any callback error from Keycloak (`error=access_denied`, etc.) is shown as
  a generic, safe error page with a reason code, never a stack trace.
- Expired sessions redirect to sign-in with a "session expired" state; the
  old cookie is not resurrected.
