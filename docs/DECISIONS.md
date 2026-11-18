# Decisions — IdentityForge

> Architecture Decision Records, kept short. Each entry states the
> decision, the context, the alternatives considered, and the consequence.
> "Lab choice" means a decision the lab made for itself — not a claim that
> a standard requires it.

## D1 — Backend-for-frontend (BFF) session model

- **Decision:** The backend performs the OIDC code exchange and token
  validation; the browser holds only an opaque session cookie. No tokens
  in `localStorage`/`sessionStorage`.
- **Context:** Browser-based apps that keep tokens in JavaScript storage
  expose them to XSS. The lab's research question is about binding and
  validation boundaries, which are cleanest to test server-side.
- **Alternatives:** Token-mediated browser flow (access token in the
  browser) — rejected: weaker boundary, harder to test cleanly.
- **Consequence:** The frontend cannot call Keycloak or any resource server
  directly; all authenticated calls go through the backend. See
  `docs/AUTH_FLOW.md`.

## D2 — Public client + PKCE S256, no client secret

- **Decision:** Keycloak client `campus-club-portal` is a public client
  (`publicClient: true`) with PKCE `S256` as the code-binding mechanism.
  No client secret is issued or stored.
- **Context:** A localhost lab client cannot keep a secret confidential
  (the secret would ship in the repo). PKCE is the correct binding
  mechanism for a public client (RFC 7636, RFC 9700).
- **Alternatives:** Confidential client with a secret — rejected: the
  secret would be a committed credential and would teach the wrong lesson.
- **Consequence:** Scenario I3 (wrong PKCE verifier) is the central
  code-binding test. The lab must never claim a client secret protects the
  code.

## D3 — Single pinned issuer, single redirect URI

- **Decision:** One issuer (`http://127.0.0.1:8080/realms/identityforge-lab`)
  and one exact redirect URI (`http://127.0.0.1:8000/auth/callback`).
- **Context:** Multi-issuer/multi-redirect support multiplies the
  validation surface and the ways a test can be misread. The research
  question is about *whether* the boundaries are enforced, not about
  supporting many of them.
- **Consequence:** Multi-issuer mix-up is an optional advanced experiment,
  not a v1 feature. Issuer validation is a simple exact allowlist.

## D4 — Same issuer string for browser and backend (SUPERSEDED 2026-11-10)

- **Decision (original):** Keycloak is started with
  `--hostname-url=http://127.0.0.1:8080`, so the issuer claim is the
  loopback URL for both the browser and the backend (which reaches
  Keycloak internally as `keycloak:8080`).
- **Superseded by Operation Trustline (P0-01/P0-03/P0-05):** the
  `--hostname-url` / `--hostname-admin-url` flags were removed in
  Keycloak 26.x hostname-v2, and the internal-DNS issuer
  (`http://keycloak:8080/...`) contradicted the allowlist, so login
  would 503. The replacement ADR is `docs/KEYCLOAK_INTEGRATION.md`:
  canonical issuer `http://127.0.0.1:8080/realms/identityforge-lab`
  via `KC_HOSTNAME=127.0.0.1` / `KC_HOSTNAME_PORT=8080` /
  `KC_HOSTNAME_ADMIN=127.0.0.1`, with the backend reaching Keycloak
  over the transport route `http://host.docker.internal:8080` and
  discovery validated before any endpoint is used. **Amended in v3
  (P0-04): the transport route is now `http://keycloak:8080` (the
  Keycloak service DNS name); `extra_hosts` and all `container_name:`
  lines were removed.** The invariant is unchanged — the backend
  validates `iss` against the public string — but the mechanism no
  longer uses removed flags or an internal issuer.
- **Amended in v4 (P0-01):** the v3 transport route worked only
  because `fetch_jwks` was called on the rewritten URL *before*
  validation in some paths — the bare JWKS validator rejects the
  transport host (`SSRF_BLOCKED`), so the shipped Docker backend
  would have failed every login at JWKS retrieval. All backchannel
  fetches now go through provenance-carrying functions
  (`fetch_jwks_via_transport`, `post_token_via_transport`,
  `fetch_discovery_via_transport` in `protocol/jwks.py`): canonical
  URL validated before the rewrite, transport base validated as the
  configured `idp_transport_base`, rewritten URL re-validated
  narrowly. `keycloak` remains transport-only, never an issuer.
- **Context:** The classic Compose failure is a browser/backend issuer
  mismatch (`localhost` vs `keycloak` vs `127.0.0.1`), usually "fixed" by
  disabling issuer validation — which would defeat scenario I5.
- **Consequence:** The backend validates `iss` against the public string
  while fetching JWKS over the transport route. See `docs/AUTH_FLOW.md` §6
  and `docs/KEYCLOAK_INTEGRATION.md`.

## D5 — Flawed variants are offline functions, never a mode

- **Decision:** Intentionally weak validators exist only as
  dependency-injected functions in the offline pytest/CLI harness. There
  is no endpoint, UI toggle, or environment variable that selects them.
- **Context:** A toggleable "vulnerable mode" in a running app is a
  standing vulnerability and a common lab-design mistake.
- **Consequence:** The secure-vs-flawed comparison is honest but bounded:
  it proves the check matters in the harness, not that a live vulnerable
  service was exploited. See `docs/SCENARIO_METHOD.md` §2 and
  `docs/THREAT_MODEL.md` §5.

## D6 — Deterministic offline fixtures with per-run keys

- **Decision:** Offline protocol tests generate their own RSA signing keys
  per test run and use synthetic issuers; no private key is committed.
- **Context:** Committed test keys get copied into other projects and
  mistaken for real credentials. Per-run generation is cheap and removes
  the risk.
- **Consequence:** Offline test results are reproducible in *behaviour*,
  not in byte-identical keys. Reports record the fixture revision and key
  generation method, not key material.

## D7 — Evidence is redacted by construction

- **Decision:** The evidence layer accepts only redacted records (IDs,
  timestamps, outcomes, reason codes, hashes). It cannot receive a token,
  code, verifier, or cookie — the data model has no field for them.
- **Context:** Redaction as a post-processing step is easy to forget for
  one new field. Making the schema incapable of holding secrets is
  stronger.
- **Consequence:** Reports are safe to share, but a reviewer cannot
  reconstruct a full token from a report — which is the point.

## D8 — SQLite/in-memory store for lab sessions and evidence

- **Decision:** Server-side session and evidence metadata live in SQLite
  (or an in-memory store for tests). No external database is required.
- **Context:** The lab must run from one Compose file with no extra
  services. Keycloak keeps its own store in its named volume.
- **Consequence:** The backend store is ephemeral per container (no named
  volume — see `docker-compose.yml`); `reset.sh --confirm` recreates it.
  This is acceptable for a lab and is documented, not hidden.

## D9 — Keycloak 26.2.5 pin — SUPERSEDED by D9b (Operation Trustline, 2026-11-10)

- **Decision:** Pin `quay.io/keycloak/keycloak:26.2.5` (tag verified to
  exist 2026-11-09; Keycloak 26.2.5, released 2025-05-28).
- **Context:** Reproducibility requires a pin; `latest` would silently
  change the IdP under the tests.
- **Consequence:** The 26.2 line is no longer the actively supported
  Keycloak line, so the pin is a lab reproducibility choice, not a
  recommendation. Reviewers should check for a newer supported patch
  before any use beyond this lab. Recorded in `docker-compose.yml` and
  `docs/THREAT_MODEL.md` §6.

## D9b — Keycloak 26.8.2 pin (supersedes D9, Operation Trustline 2026-11-10)

- **Decision:** Pin `quay.io/keycloak/keycloak:26.8.2` (released
  2026-11-05; 33 CVE fixes including critical SAML signature bypass
  CVE-2026-117691 — the lab uses no SAML, so that CVE does not apply
  here, but 26.8.2 is the supported line and 26.2 is not).
- **Context:** D9's 26.2.5 pin was on a line that is no longer actively
  supported. 26.8.2 was verified to exist, boot, and import the realm
  live (2026-11-10 host run + 2026-11-11 v2 re-run).
- **Consequence:** Same reproducibility rule as D9 (never `latest`).
  Reviewers should still check for a newer 26.8.x patch before any use
  beyond this lab.

## D10 — React + Vite frontend, FastAPI backend

- **Decision:** Python 3.12 + FastAPI + Pydantic backend; React + TypeScript
  + Vite frontend; pytest + Vitest + Playwright for tests.
- **Context:** Matches the available environment (Python 3.12.3, Node 24)
  and the maintainers' ecosystem; Authlib/PyJWT are maintained libraries
  (no hand-rolled crypto — see `docs/STANDARDS_TRACEABILITY.md`).
- **Consequence:** A reviewer needs Python + Node + Docker Desktop; the
  offline fixture suite needs only Python. See `docs/WINDOWS_SETUP.md`
  for the lower-RAM fallback.

## D11 — No `0.0.0.0`, no wildcard CORS, no remote deployment

- **Decision:** Every Compose port binds `127.0.0.1`; CORS allows only the
  lab frontend origin; local HTTP is a labelled development exception.
- **Context:** The lab contains intentionally weak *offline* fixtures and
  synthetic credentials. Any network exposure would turn a teaching tool
  into a real risk.
- **Consequence:** The lab cannot be demoed from another machine without
  reconfiguration — deliberately. Anyone who reconfigures it owns the
  security consequences, and `SECURITY.md` says so.
