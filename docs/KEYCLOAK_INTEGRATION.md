# Keycloak Integration — Architecture Decision Record

## Decision (Operation Trustline, 2026-11-10)

Separate the **canonical OIDC issuer identifier** from the **network
route the backend uses to reach Keycloak**. Never substitute an internal
Docker hostname for the `iss` value in a token.

- Canonical issuer (browser-visible, in tokens, in discovery):
  `http://127.0.0.1:8080/realms/identityforge-lab`
- Backend transport base (Compose): `http://keycloak:8080` (v3 P0-04 —
  the Keycloak service DNS name on the private bridge network).
  `extra_hosts: ["host.docker.internal:host-gateway"]` was removed,
  and all `container_name:` lines were removed so disposable
  `-p` cold-start namespaces can coexist with a running user stack.
  Local host dev default: the canonical base itself.
  `IDENTITYFORGE_IDP_TRANSPORT_BASE` is set to
  `http://keycloak:8080` in `docker-compose.yml`; the backend
  default in `config.py` is unchanged
  (`http://127.0.0.1:8080`).
- Keycloak hostname-v2 configuration (26.8.2):
  `KC_HOSTNAME=http://127.0.0.1:8080`,
  `KC_HOSTNAME_ADMIN=http://127.0.0.1:8080`, `KC_HTTP_ENABLED=true`,
  `start-dev --import-realm`. Hostname values are FULL URLs including
  scheme and port — this is mandatory, not stylistic: the first
  Trustline fix used bare hosts (`KC_HOSTNAME=127.0.0.1`,
  `KC_HOSTNAME_PORT=8080`, `KC_HOSTNAME_ADMIN=127.0.0.1`) and 26.8.2
  refused to boot with "Provided hostname-admin is not a valid URL"
  and warned that `KC_HOSTNAME_PORT` is a v1 option. The removed
  `--hostname-url` / `--hostname-admin-url` flags and
  `--hostname-strict=false` are NOT used.
- Discovery is fetched from the transport base. The backend then requires
  `discovery["issuer"] == canonical issuer` exactly, and requires the
  authorization/token/JWKS endpoints to be under the canonical issuer
  with the expected realm path. For backchannel calls the backend rewrites
  only the host:port of those endpoints to the transport host, and only
  to an allowlisted transport host (`127.0.0.1:8080`, `localhost:8080`,
  `host.docker.internal:8080`, or `keycloak:8080`). The browser is always redirected to
  the canonical (127.0.0.1) authorization endpoint, which it can resolve.
- **Provenance fetch (v4, P0-01):** discovery, token exchange, and
  JWKS all go through provenance-carrying functions
  (`fetch_discovery_via_transport`, `post_token_via_transport`,
  `fetch_jwks_via_transport` in `protocol/jwks.py`, built on
  `transport_endpoint_url`): the canonical URL is validated
  (loopback SSRF guard + exact pinned realm path) BEFORE any
  rewrite, the transport base is validated as the configured
  `idp_transport_base`, and the rewritten URL is re-validated
  narrowly (host == configured transport host, port 8080, path ==
  pinned realm path exactly) before any network call. The bare
  `fetch_jwks` / `validate_jwks_url` still reject `keycloak:8080`
  (`SSRF_BLOCKED`) — the v3 code called `fetch_jwks` on the
  rewritten URL, so the shipped Docker backend would have failed
  every login at JWKS retrieval while the host-process path passed.
  Regression: `tests/unit/test_transport_fetch.py` (22 tests: fake
  HTTP bound to the exact service DNS, negatives rejected before
  any network call, callback integration test with transport base
  `http://keycloak:8080`).
- JWKS fetching accepts only the pinned JWKS path
  `/realms/identityforge-lab/protocol/openid-connect/certs` on an
  allowlisted transport host. `host.docker.internal` is a Docker-managed
  alias for the host loopback, not an arbitrary LAN host; it is allowed
  only with that exact path and port 8080. `keycloak` is allowlisted
  ONLY as a transport host (`ALLOWED_TRANSPORT_HOSTS` in
  `protocol/jwks.py`) — it is never a valid issuer, JWKS host, or
  loopback host, and issuer/discovery validation rejects it (v3
  P0-04 regression tests in `tests/unit/test_transport.py`, 9 tests).
  `rewrite_to_transport` also rejects external source hosts: it used
  to silently rewrite any host onto the loopback transport, which
  contradicted its own contract (found and fixed in v3; it was not a
  live exploit — the function is only ever fed validated pinned
  endpoints — but a false security claim).
- **JWKS two-key fact (v3 P1-07 + fix, 2026-11-11):** real Keycloak
  26.8.2 publishes TWO RSA keys at the JWKS endpoint — an RS256
  signing key (`use: sig`) and an RSA-OAEP encryption key
  (`use: enc`). The v3 P1-07 hardening initially required EVERY key
  to have `use == 'sig'` and `alg == 'RS256'`, so the encryption key
  made `parse_jwks` raise and EVERY real login failed with
  `/?error=JWKS_ERROR` (reproduced against the live JWKS: full
  document → `ValueError: RSA JWK use must be 'sig' when present`;
  sig-only subset → parses). The fix (`protocol/jwks.py`,
  `_is_signing_key`, `parse_jwks`): non-signing keys (`use: enc`,
  `alg` other than RS256, non-RSA `kty`) are SKIPPED, never allowed
  to break the document; the live JWKS now parses to exactly the
  RS256 signing key. A malformed *signing* key (bad base64 `n`/`e`,
  missing `kid`) still fails the whole document — fail closed.
  Hardening retained: `keys` must be a list of at most 10 entries,
  document at most 64 KiB, duplicate kid among signing keys rejected,
  `n`/`e` base64url-validated. Regression: 6 new tests in
  `tests/unit/test_jwks.py` (38 total); live-gate login 37/37 PASS
  after the fix (see "Live verification (2026-11-11, v3)" below).
- **Backchannel proxy rule (P0-26):** all backend IdP calls (discovery,
  token exchange, JWKS) are made with `trust_env=False`. The backend
  must never let ambient `HTTP_PROXY`/`NO_PROXY` variables route or
  break pinned IdP traffic: in the Trustline sandbox a bracketed-IPv6
  `NO_PROXY` entry made httpx reject every IdP call with `InvalidURL`
  while Keycloak was healthy. IdP traffic goes direct to the pinned
  host, always.
- **Realm import note:** the realm JSON must not contain a
  `"dockerFlow"` field — Keycloak 26.8.2 rejects the import with
  "Unrecognized field dockerFlow". The field was removed from
  `keycloak/realm-import/identityforge-lab-realm.json` (Docker registry
  auth is irrelevant to this lab); import then succeeded.

## Why not the alternatives

- `http://keycloak:8080` as the issuer: the browser cannot resolve the
  Docker service name, and tokens would carry an issuer the allowlist
  (correctly) rejects — the original P0-03 failure.
- Backend reaching Keycloak via `127.0.0.1:8080` from inside its own
  container: that is the backend container's loopback, not the host's —
  the original P0-02/P0-05 failure.
- A shared `/etc/hosts` name (e.g. `keycloak.local`): requires the
  reviewer to edit host files on Windows and Linux; rejected.
- Disabling issuer verification: never acceptable; see P0-05.

## Subject / role mapping

Keycloak `sub` values are stable UUIDs, not usernames. The realm import
pins deterministic synthetic subject IDs:

- `student_01`: sub `10000000-0000-4000-8000-000000000001` (member)
- `officer_01`: sub `10000000-0000-4000-8000-000000000002` (member, officer)

The backend policy map is keyed by `(issuer, sub)` and returns roles only
for those pinned pairs. The display name comes from the pinned mapping,
never from a raw `sub` or an untrusted token claim. Unknown subjects get
no roles and the login is rejected (`UNKNOWN_SUBJECT`). Offline fixtures
use the same policy function with the fixture issuer and the fixture
subject names `student_01` / `officer_01`.

## Versions

- Keycloak `quay.io/keycloak/keycloak:26.8.2` (released 2026-11-05;
  33 CVE fixes including critical SAML signature bypass
  CVE-2026-117691; the lab uses no SAML, so that CVE does not apply to
  this lab, but 26.8.2 is the supported line and 26.2 is not).
- The 26.2.5 pin is retained in git history only; do not use it.

## Live verification (2026-11-10, sandbox host-run)

Keycloak 26.8.2 was booted live from the official distribution tarball
with the shipped hostname config and realm import (the sandbox Docker
daemon cannot start any container — see `docs/REMEDIATION_FINDINGS.md`
— so the container supervisor path is NOT RUN here; the Keycloak
software, version, realm, and config are identical). Results:

- Discovery 200; `issuer` exactly
  `http://127.0.0.1:8080/realms/identityforge-lab`.
- Real logins: `student_01` member 200 / officer 403; `officer_01`
  member 200 / officer 200; session `sub` is the pinned UUID
  (`10000000-...-0001` / `...-0002`); logout revokes, stale cookie 401.
- Cross-browser callback swap rejected (`STATE_BINDING_MISMATCH`);
  legitimate browser still completes; replay rejected (`STATE_REUSED`).
- Playwright (real Chromium): 7/7 E2E pass, three independent runs.
- Backend `GET /api/v1/lab/status` reported reachable=true,
  issuer_matches=true once the P0-26 proxy fix landed.

## Live verification (2026-11-11, sandbox host-run, v2 code)

Re-run against the remediated v2 backend with `scripts/live-gate.py all`,
three independent runs, 80 checks each, all PASS (2026-11-11T02:04–02:06Z):

- Discovery 200; `issuer` exactly
  `http://127.0.0.1:8080/realms/identityforge-lab`.
- Real logins: `student_01` member 200 / officer 403; `officer_01`
  member 200 / officer 200; logout revokes, stale cookie 401 (each run).
- Cross-browser callback swap rejected (`STATE_BINDING_MISMATCH`);
  legitimate browser still completes; replay rejected (`STATE_REUSED`).
- **K2 (new in v2):** wrong PKCE verifier at the REAL token endpoint →
  400 `invalid_grant` "PKCE verification failed". **Measured Keycloak
  behaviour: the failed exchange BURNS the authorization code** — a
  second exchange of the same code returns 400 `invalid_grant` "Code
  not valid" (probed directly 2026-11-11). The first version of the v2
  live gate reused the attacked code for the legitimate callback and
  failed honestly (`PROVIDER_ERROR`); K2 now uses a disposable
  transaction and the legitimate flow is proven separately with a fresh
  code. Test drivers must not assume a failed exchange leaves the code
  usable.
- **K3 (new in v2):** unregistered redirect
  (`…/callback/evil`) rejected by real Keycloak before any code is
  issued (400, no `code` in the response).
- **Live events (new in v2):** 152 redacted `LiveLoginEvent`s across 20
  logins recorded via `GET /api/v1/live-logins`, including rejected
  events (`STATE_BINDING_MISMATCH` 4, `STATE_REUSED` 4,
  `PROVIDER_ERROR` 4, `POLICY_DENIED` 7); zero events contain
  secret-like content (DB scan 2026-11-11).
- **doctor.sh identity negatives (new in v2):** dummy HTTP 200 on 5173
  → Frontend FAIL, exit 1; dummy wrong-issuer discovery JSON on 8080 →
  Keycloak FAIL, exit 1. A bare 200 is never mistaken for the lab.
- The shipped `docker compose up` path itself remains NOT RUN here
  (no Docker binary or daemon in the sandbox); the Keycloak software,
  version, realm, and config are identical to the Compose stack.

## Live verification (2026-11-11, sandbox host-run, v3 code)

Re-run against the remediated v3 backend with `scripts/live-gate.py`,
after the JWKS fix (see above). The login flow alone ran **37/37
checks, 0 failures** (student + officer login, member 200 / officer
403 / officer 200, logout 200, stale 401, per-transaction binding
cookie). Full `live-gate.py all` runs >80 checks per run (the v3
`parallel` flow added: two same-browser logins hold two distinct
binding cookies, complete B-then-A, latest session valid, earlier
session revoked by rotation). Full Pass A/B/C counts are in
`docs/VERIFICATION_LOG.md` (v3 section, PENDING at docs time).

- **Healthcheck (v3 P1-15; v5 IF-V4-01):** the Keycloak healthcheck now requires
  BOTH an HTTP 200 status line (`HTTP/1.[01] 200`) AND `"issuer"` in
  the discovery body — a bare grep for `issuer` could pass on a
  stale/error body. It needs `bash`, `/dev/tcp`, and `grep` inside
  the `keycloak:26.8.2` image; in-image validation is NOT RUN in the
  build sandbox (no Docker). **v5 fix:** the in-container shell
  variable is written `$$resp`, NOT `$resp` — Compose interpolates
  `$VAR`/`${VAR}` in configuration values before the container shell
  runs, so the v4 single-dollar form was replaced by an empty string
  and the healthcheck inspected blank text (expected to fail, blocking
  backend/frontend via `depends_on: service_healthy` despite a healthy
  JVM). `$$` is Compose's escape for a literal dollar. Static
  regression: `scripts/compose-config-check.py` simulates Compose
  interpolation and asserts the resolved command keeps the literal
  `$resp` references; `scripts/test-compose-healthcheck.sh` checks the
  RESOLVED command via `docker compose config` and (with Docker) the
  live health state. **SOURCE FIXED; ACTUAL DOCKER HEALTHCHECK +
  COMPOSE BOOT NOT RUN** in the build sandbox. Reviewer probe on a running stack:
  `docker compose exec keycloak bash -c 'command -v bash grep; exec 3<>/dev/tcp/127.0.0.1/8080 && echo TCP_OK'`.
  If `bash`/`grep` are absent from the pinned image, replace the
  healthcheck with a supported readiness probe — do not weaken it to
  a bare TCP connect (that cannot prove discovery works).
- **Cold-start gate (v3 P1-13):** `-Full` no longer accepts "already
  running containers are healthy" as proof. It boots a disposable
  project namespace (`docker compose -p
  identityforge-coldstart-<timestamp> up --build -d` from a clean
  extract), waits for doctor READY (≤360 s), runs the live gates,
  collects config/health/logs into `test-results/coldstart/`, and
  tears down with `down -v` — never touching the user's own stack
  or volumes. Docker absent → NOT RUN, never PASS.
- **Live-gate container seam (v3 P0-02):** `live-gate.py` accepts
  `IDENTITYFORGE_LIVE_GATE_HOST_MAP` (e.g.
  `{"8080": "keycloak", "8000": "backend"}`), which rewrites only
  the TCP connection host; all URL strings, redirect targets, and
  issuer checks stay canonical. Unset = unchanged host behaviour.
  The shipped `docker compose up` path itself remains NOT RUN here
  (no Docker binary or daemon in the sandbox); the Keycloak software,
  version, realm, and config are identical to the Compose stack.
- **Host-map adapter (v4 P0-02):** the v3 seam changed the TCP
  route but not the Host header, so http.client derived
  `Host: backend:8000` and the backend answered 403
  HOST_NOT_ALLOWED. Mapped connections now send an explicit
  canonical Host header (`127.0.0.1:8000` / `127.0.0.1:8080`);
  unmapped connections keep http.client's default; the backend's
  `allowed_hosts` was NOT widened. Malformed maps fail loudly
  (exit 2, no connection attempted). Verified: live gate `all`
  **99/99** unmapped AND **99/99** with the localhost host map;
  adapter tests `scripts/test-live-gate-hostmap.py` **21/21**.

## Debugging

- `docker compose config -q` — validates the Compose file (run first).
- `docker compose ps` — Keycloak must show `(healthy)`; if it stays
  unhealthy while the discovery URL returns 200 from the host, see
  `docs/WINDOWS_SETUP.md` §6 (healthcheck contingency).
- `curl http://127.0.0.1:8080/realms/identityforge-lab/.well-known/openid-configuration`
  — `issuer` must equal the canonical issuer exactly.
- Backend `GET /api/v1/lab/status` — reports IdP reachability, issuer
  match, and the last verified login (or NOT RUN / ERROR, honestly).
