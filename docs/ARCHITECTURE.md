# Architecture — IdentityForge (v3, Operation Trustline third release)

Environment where this release was built and verified: Linux sandbox,
Python 3.12.3, Node 24.22.1 / npm 10.9.4, ~7.7 GB RAM. **Docker /
Docker Compose: NOT INSTALLED** in this sandbox (`docker: command not
found`, no socket). The live Keycloak gate ran the identical software
as host processes (Keycloak 26.8.2 tarball, venv backend, Vite
preview). The shipped `docker compose up` path is NOT RUN here and is
a reviewer gate on Docker Desktop.

## Stack (pinned, verified 2026-11-11)

- **Backend:** Python 3.12, FastAPI 0.162.4, Pydantic 2.10.4,
  PyJWT[crypto] 2.15.0, cryptography 50.0.2, httpx 0.28.1, uvicorn
  0.34.0, pytest 9.0.3, ruff 0.9.2. Authlib was REMOVED in Trustline
  (17 advisories, zero imports); token validation uses PyJWT + JWKS.
- **Frontend:** React + TypeScript 5.9.3, Vite 7.3.8, Vitest 5.1.0,
  Playwright 1.65.0. Served in Compose as a production build via
  `vite preview` (no Vite dev server for end users since v2).
- **IdP:** Keycloak 26.8.2 (`quay.io/keycloak/keycloak:26.8.2`,
  released 2026-11-05), realm `identityforge-lab`, client
  `campus-club-portal`, synthetic users `student_01` / `officer_01`
  with pinned subject UUIDs.

## Topology (loopback only; ports FIXED)

| Service | Bind | Published |
|---|---|---|
| Keycloak | 0.0.0.0:8080 inside its container | `127.0.0.1:8080` |
| Backend | 0.0.0.0:8000 inside its container | `127.0.0.1:8000` |
| Frontend | 0.0.0.0:5173 inside its container | `127.0.0.1:5173` |

Ports are FIXED (P1-14): 8080/8000/5173 are part of the issuer
identity. There are no `${..._PORT}` variables in Compose or
`.env.example`. If a port is in use, stop the conflicting service.

- **Canonical issuer** (browser-visible, in tokens, in discovery):
  `http://127.0.0.1:8080/realms/identityforge-lab`
- **Backend transport base:** `http://keycloak:8080` in Compose (the
  Keycloak service DNS name on the private bridge network; v3 P0-04 —
  `IDENTITYFORGE_IDP_TRANSPORT_BASE`, all `container_name:` lines
  removed so disposable `-p` namespaces can coexist with a running
  user stack), `http://127.0.0.1:8080` on a host run. `keycloak` is
  allowlisted ONLY as a transport host (`ALLOWED_TRANSPORT_HOSTS` in
  `protocol/jwks.py`); it is never a valid issuer, JWKS host, or
  loopback host — issuer and discovery validation still reject it.
  Discovery is fetched via transport, its issuer must equal the
  canonical issuer exactly, and backchannel endpoints are rewritten
  to the allowlisted transport host only. All IdP backchannel calls
  use `trust_env=False` (ambient proxy vars must never route or break
  pinned IdP traffic — P0-26). **Provenance transport fetch (v4,
  P0-01):** bare `fetch_jwks` / `validate_jwks_url` /
  `validate_issuer_url` still reject `keycloak:8080`
  (`SSRF_BLOCKED`). Only the provenance-carrying functions in
  `protocol/jwks.py` may use the transport host —
  `fetch_jwks_via_transport`, `post_token_via_transport`,
  `fetch_discovery_via_transport`, built on
  `transport_endpoint_url(canonical_url, transport_base,
  expected_path=...)`: the canonical URL is validated against the
  loopback SSRF guard and the exact pinned realm path BEFORE any
  rewrite, the transport base is validated as the configured
  `idp_transport_base` (allowlisted host, port 8080, bare
  host:port), and the rewritten URL is re-validated narrowly (host
  == configured transport host, port 8080, path == pinned realm
  path exactly). The rewritten URL is trusted only because it was
  derived from a validated canonical URL plus a validated
  configured transport base — never because `keycloak` is in a
  general allowlist. All three fetches use
  `follow_redirects=False, trust_env=False`.
- **Keycloak hostname-v2:** `KC_HOSTNAME=http://127.0.0.1:8080`,
  `KC_HOSTNAME_ADMIN=http://127.0.0.1:8080` (full URLs, mandatory),
  `start-dev --import-realm`. The realm JSON contains no `dockerFlow`
  field (26.8.2 rejects it at import).

## Trust boundary

Browser → backend BFF (auth-code exchange, token validation, session)
→ Keycloak. No tokens in `localStorage`/`sessionStorage`. The backend
is the only component that makes security decisions; the browser and
the frontend never do. Sessions are opaque random HttpOnly
`SameSite=Lax` cookies, server-side store (SQLite for evidence,
in-memory for sessions/transactions), rotation on login, revocation
on logout. Logout revokes the APP session only — it does NOT end the
IdP's SSO session.

## Login flow (observed)

1. `GET /auth/login` creates a server-side transaction (random state,
   nonce, PKCE verifier + S256 challenge), sets the HttpOnly
   per-transaction browser-binding cookie
   `identityforge_txn_<state>` (v3 P1-06 — one cookie per login;
   v4 P1-10 — at most 4 live transactions per browser, 20 globally;
   a browser evicts only its own oldest; global cap → 503
   `TRANSACTION_STORE_FULL`; login-start rate limit 30/min per
   browser key, 120/min globally → 429 `LOGIN_RATE_LIMITED`),
   redirects to the canonical Keycloak authorization endpoint.
2. Keycloak authenticates the synthetic user (BFF does NOT observe
   this step) and redirects to `/auth/callback?code&state`.
3. The backend verifies the browser binding, consumes `state`
   atomically (replay → `STATE_REUSED`; wrong browser →
   `STATE_BINDING_MISMATCH`, transaction NOT consumed), exchanges the
   code server-to-server, validates the ID token (RS256 only, known
   `kid`, `iss`/`aud`/`azp`/`nonce`/`exp`/`iat`/`nbf`), maps roles
   from the backend policy keyed by `(issuer, sub)` (never from token
   role claims), rotates the session id, and redirects to the portal.
   The JWKS parser skips non-signing keys (Keycloak's RSA-OAEP
   encryption key, non-RS256 `alg`) and fails closed only on
   malformed *signing* keys (v3 P1-07 + fix, 2026-11-11).
4. Each observed step is recorded as a redacted `LiveLoginEvent`
   (`GET /api/v1/live-logins`, namespace `LIVE_KEYCLOAK`) — stage,
   outcome, reason code, correlation id, SHA-256 subject hash. No
   token, code, state, verifier, secret, or cookie is stored.

## CSRF lifecycle (P0-02, v2)

- `GET /api/v1/csrf-token` is idempotent per browser: returns the
  existing token, mints only when absent. Cookie and returned value
  are always identical (double-submit).
- `GET /api/v1/lab/config` is a pure read — it never touches the token.
- `POST /api/v1/runs`, `POST /api/v1/lab/reset`, `POST /auth/logout`
  require the `x-csrf-token` header to equal the cookie plus a
  matching `Origin` (403 `csrf_denied` otherwise).
- Reset and logout ROTATE the token and return the fresh value
  in-band as `csrf_token` in the JSON body; the client adopts it and
  retries a 403 mutation at most once.
- **Reset is officer-gated in v3 (P0-01):** it requires an officer
  session + CSRF + body `{"confirm": "RESET_LAB"}` (401 no session,
  403 student, 422 bad confirmation). The v2 "unprivileged localhost
  action" description is withdrawn. Reset clears evidence (runs +
  live events), sessions, transactions, and `last_login`, and revokes
  the operator's own session. It does NOT reset the Keycloak realm
  or volume.

## Scenario engine

Deterministic offline fixtures (fresh RSA keys per run, synthetic
issuers) plus isolated flawed validators that omit exactly one check.
Flawed variants are pure functions in the offline test/CLI harness —
never HTTP endpoints, never toggleable in the portal, never able to
mint a real portal session. `ComparisonResult` records actual state
transitions (`secure_session_created` only when
`SessionStore.create/rotate` executed, `session_preexisted`,
`session_revoked`, `flawed_observed_result`,
`protected_resource_disclosed`, `evidence_provenance`
`OFFLINE_FIXTURE` / `EPHEMERAL` / `LIVE_KEYCLOAK`). Evidence is
SQLite-backed; `evidence_saved` is True only after the commit.

## Data flow / evidence

- Runs: `POST /api/v1/runs` → `ComparisonResult` → SQLite
  (`backend/data/identityforge.db`, runtime state, never shipped).
- Live logins: BFF-observed events → same store, separate table,
  `LIVE_KEYCLOAK` namespace, never mixed with offline runs.
- Reports: `GET /api/v1/runs/{id}/report` (JSON, or Markdown with
  `?format=md`); CSV is generated client-side with formula-injection
  neutralization. Server-down report downloads are labelled
  `LOCAL_UNSAVED_COPY` with `origin=browser_cache`.
