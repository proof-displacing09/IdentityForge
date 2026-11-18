# Security Assessment — IdentityForge

> Status: **Operation Trustline v4 live gate completed 2026-11-11.**
> The Keycloak integration lane was re-run live against real Keycloak
> 26.8.2 in the sandbox — as host processes, because the sandbox has
> no Docker binary or daemon (see §3). Live gate `all` **99/99 checks
> PASS** (unmapped and with the localhost host map), login flow
> **37/37**, reset sub-gate **64/64**. K2 and K3, which were NOT RUN as
> live probes in Trustline, were driven live in v2 (3×), v3 (4×), and
> v4 (99/99). The shipped `docker compose up` path itself remains
> unexecuted here and is a reviewer gate on Docker Desktop.

## 1. Scope

**In scope:**

- The IdentityForge backend (BFF): login, callback, token validation,
  sessions, logout, CSRF, portal authorization, scenario-run and reset
  endpoints.
- The research console frontend: what it displays, what it can trigger,
  and whether it can reach any security decision.
- The scenario engine and its flawed-fixture boundary (can a flawed
  variant affect a real session? can a scenario run change portal config?).
- The Keycloak realm import and Compose configuration (loopback bindings,
  client settings, synthetic users).
- Evidence handling: redaction, report contents, log output.

**Out of scope:**

- Keycloak as a product (upstream CVEs, clustering, database security).
- Real identity providers, real users, production deployment, TLS.
- The reviewer's host OS, Docker Desktop itself, or the network.
- Anything outside the lab's loopback services.

## 2. Method

1. **Trust-boundary trace:** browser → callback → token exchange → JWKS
   validation → session → resource authorization → evidence report.
   Each boundary was checked for what it trusts and what it verifies.
2. **Negative testing:** every scenario in `docs/SCENARIO_METHOD.md`
   (I1–I18) was run against the secure validator and the isolated flawed
   variant; each negative test asserted the expected reason code **and**
   the absence of a session and of resource access.
3. **Regression (mutation) testing:** a validator check was deliberately
   inverted in an isolated test run to confirm the tests detect the
   regression, then restored and the suite re-run. (Record the mutation,
   the detection, and the restore in the findings log below.)
   **Status 2026-11-11: NOT RUN as source mutation, by design.** An
   attempt at the mutation step in Trustline was stopped by a runtime
   safety intervention and was not re-attempted in any form (see the
   Trustline note below). In v2, mutation SENSITIVITY is proven instead
   in an offline test-only process via the designed `omit` mechanism:
   each validator check is omitted one at a time (signature, issuer,
   audience, nonce, expiry, state, PKCE, CSRF, policy) and the suite
   asserts the secure path rejects while the omit-one-check path
   accepts — `tests/integration/test_trustline_v2.py`. No flawed
   validator is reachable from production imports or HTTP routing.
   **Status 2026-11-10: NOT RUN as a formal gate.** An attempt at the mutation step was
   stopped by a runtime safety intervention and was not re-attempted in
   any form. The attempt left the disabled-signature line in
   `validators.py`; the final verification run caught it at once (10
   pytest failures, CLI 17/18), the exact original line was restored,
   and the suite returned to 111/111 + 18/18 (see
   `docs/VERIFICATION_LOG.md`, Trustline Pass B). The adversarial coverage therefore rests on the negative
   tests (U2, U4–U6, U8–U10, U15–U17, P2–P4), the flawed-one-check
   suite (6 tests), and the live negative proofs (cross-browser
   callback rejection, replay rejection, CSRF rejection, officer
   denial) — not on a mutation run. This gap is recorded, not hidden.
4. **Configuration review:** Compose bindings, realm client settings,
   CORS/origin rules, cookie flags, and the `.gitignore`/release checks
   were inspected against `docs/THREAT_MODEL.md`.
5. **Evidence review:** sample reports, logs, and screenshots were
   searched for tokens, codes, verifiers, cookies, and passwords.

## 3. Limits

- The live gate ran Keycloak 26.8.2, the backend, and the frontend as
  host processes (same software, version, realm, and config as the
  Compose stack). The shipped `docker compose up` boot path and the
  Docker image builds were NOT RUN here: the sandbox has no Docker
  binary or daemon at all (`docker: command not found`, no socket).
  A reviewer on Docker Desktop must run the Compose path; the
  YAML-only compose validation passes (`scripts/compose-config-check.py`).
- K2 (wrong PKCE verifier at the real token endpoint) and K3
  (unregistered redirect rejected by Keycloak) WERE driven as live
  probes in v2 (3×), v3 (4×, 99/99), and v4 (99/99)
  (see §4 and `docs/KEYCLOAK_INTEGRATION.md`).
  Measured Keycloak behaviour: a failed PKCE exchange burns the auth
  code (second exchange → 400 `invalid_grant` "Code not valid").
- `npm audit` is NOT RUN in this sandbox (registry proxy 403). The
  frontend dependencies were upgraded to maintained versions (Vite
  7.3.8, Vitest 5.1.0, Playwright 1.65.0) after reviewing the published
  Vite 5.4.11 advisories, and a GitHub Advisory Database check of the
  pinned direct dependencies is the shipped fallback — see
  `docs/VERIFICATION_LOG.md` for its result. Transitive advisories
  need `npm audit` on a machine with registry access.
- No external auditor was involved. This is a self-assessment by the
  lab's authors, recorded honestly — not an independent audit and not a
  certification.
- The assessment covers the lab as shipped on loopback. Any
  reconfiguration for remote access invalidates these findings.

## 4. Findings log

Severity: Critical / High / Medium / Low / Informational.
Status: Open / Fixed (with retest) / Accepted risk (with justification) /
TBD.

| ID | Severity | Finding | Reproduction | Fix / mitigation | Status |
|---|---|---|---|---|---|
| P0-01 (amended) | High | Keycloak hostname-v2: bare-host `KC_HOSTNAME_ADMIN` rejected at boot; `KC_HOSTNAME_PORT` is a deprecated v1 option; realm `dockerFlow` field rejected at import | Live boot 2026-11-10: "Provided hostname-admin is not a valid URL"; import error "Unrecognized field dockerFlow" | Full-URL hostnames (`http://127.0.0.1:8080`), port option removed, `dockerFlow` removed from realm JSON; boot + discovery 200 verified live | Fixed (retest: live boot + discovery + logins) |
| P0-25 | High | `fetch_jwks()` returned a parsed map; `validate_id_token()` re-parsed it as a raw document — every real login would have failed with `JWKS_ERROR` | Fake-IdP login tests before the fix | `fetch_jwks` returns the raw document; `parse_jwks` idempotent | Fixed (retest: fake-IdP suite + live login) |
| P1-07 (v3) | High | v3 JWKS hardening rejected Keycloak's RSA-OAEP encryption key (`use: enc`) — every real login failed with `/?error=JWKS_ERROR` | Reproduced against the live JWKS 2026-11-11: full document → `ValueError: RSA JWK use must be 'sig' when present`; sig-only subset → parses | Non-signing keys skipped (`_is_signing_key`); malformed *signing* keys still fail closed; 6 new tests in `tests/unit/test_jwks.py` (38 total) | Fixed (retest: live JWKS parses to exactly the RS256 sig key; live-gate login 37/37 PASS) |
| P0-01 (v4) | High | Docker JWKS transport breaker: the callback rewrote the canonical JWKS URL to `http://keycloak:8080` and then called the bare `fetch_jwks`, whose SSRF guard rejects non-loopback hosts — the shipped Docker backend would fail every login at JWKS retrieval | Reproduced by executing the shipped v3 code: `validate_jwks_url(rewrite_to_transport(canonical JWKS, 'http://keycloak:8080')) == SSRF_BLOCKED` | Provenance-carrying fetches (`fetch_jwks_via_transport`, `post_token_via_transport`, `fetch_discovery_via_transport`): canonical validated before the rewrite, transport base validated, rewritten URL re-validated narrowly; bare validators still reject `keycloak:8080` | Fixed (retest: 22 tests in `tests/unit/test_transport_fetch.py`; live gate 99/99 host-run; Docker Compose E2E NOT RUN here — reviewer gate) |
| P1-10 (v4) | High | Global transaction cap evicted other browsers' logins: a 6th transaction evicted the 1st, so one unauthenticated client could force another browser's waiting login into STATE_REUSED | Reproduced by executing `TransactionStore`: 6 created, first lookup None, 5 live | Per-browser cap 4 + global cap 20; own-oldest eviction only; anonymous `identityforge_browser` cookie (SHA-256 hash only); global cap → 503 `TRANSACTION_STORE_FULL` | Fixed (retest: 10 tests in `tests/integration/test_trustline_v4_transactions.py`; second browser unaffected while the first is saturated) |
| P1-04 (v4) | High | 1 MiB request limit trusted Content-Length only: a chunked body with no Content-Length (1,100,036 bytes) executed a scenario (200 vs 413) | Streamed ASGI test (reviewer-confirmed) | Bounded ASGI receive wrapper: 1,048,576 bytes inclusive, streamed counting, malformed/duplicate/negative CL → 400, over → 413 before JSON parse/evidence/CSRF/rate-limit | Fixed (retest: 19 tests in `tests/security/test_request_size.py`; parent probe: chunked 1,100,036 → 413) |
| P0-26 | High | Ambient proxy env vars broke all IdP backchannel calls (`httpx.InvalidURL` from a bracketed-IPv6 `NO_PROXY` entry) while Keycloak was healthy | Live gate: `lab/status` reachable=false / reason=InvalidURL with discovery 200 via curl | `trust_env=False` on all 4 IdP calls; regression test `test_idp_backchannel_never_uses_ambient_proxies` | Fixed (retest: live status OK + full login flow) |
| P0-27 | Medium | Provider-down tests relied on ambient Keycloak absence instead of simulating an outage | Live gate: both tests failed once a real Keycloak was running | Tests now patch `httpx.get` to raise `ConnectError` | Fixed (retest: 111/111 pytest) |
| P0-06 | High | Policy keyed on usernames; real Keycloak `sub` is a UUID | Inspection + live `/portal/me` | Pinned subject UUIDs; policy keyed by (issuer, sub) | Fixed (retest: live `sub` = pinned UUID, roles correct) |
| P0-07 | High | Login `state` not browser-bound | Inspection + live cross-browser test | HttpOnly transaction cookie, atomic single-use consumption | Fixed (retest: cross-browser rejection ×3 live) |
| P0-02 (v2) | High | CSRF cookie reissue invalidated the frontend's cached token: GET /api/v1/lab/config minted a fresh cookie per call, so navigating to Settings broke reset/logout with 403 | Live repro 2026-11-10 (directive audit): token → reset 200 → config GET → reset with cached token 403 | Config GET is a pure read; `csrf-token` idempotent per browser; reset/logout rotate and return the fresh token in-band; client retries a 403 mutation at most once | Fixed (retest: directive repro sequence + two-tab + rotation tests; live gate 3×) |
| P0-05 (v2) | Medium | Real Keycloak logins left no Atlas evidence (only `last_login`; Atlas KEYCLOAK stage empty) | Static inspection + live check | Redacted `LiveLoginEvent` capture (8 stages, correlation ids, SHA-256 subjects); `GET /api/v1/live-logins` | Fixed (retest: 152 events / 20 logins live, 0 secret-like content) |
| P0-06 (v2) | Medium | Scenario results invented sessions (`flawed_session_created=True` for I16/I17/I18; I10/I13 labels overstated) | Static inspection of engine + reports | Split model fields (`session_preexisted`, `session_revoked`, `flawed_model_status`, `flawed_observed_result`, `protected_resource_disclosed`); flawed sessions only when `SessionStore.create` executed | Fixed (retest: scenario-semantics tests; CLI 18/18) |
| P1-09 (v2) | Low | `evidence_saved` defaulted True with no store | Static inspection + `run_scenario(store=None)` probe | Defaults False; True only after SQLite commit; store-less runs are `EPHEMERAL` | Fixed (retest: provenance tests incl. injected DB error) |
| P1-21 (v2) | Medium | Health checks returned 200 for any process on the port | Inspection of doctor.ps1 | Identity-validating probes (canonical issuer, `service=identityforge-backend`, frontend `id="root"`); negative-tested with dummy 200 servers on 5173 and 8080 | Fixed (retest: doctor FAILs + exit 1 on both dummies, 2026-11-11) |
| P1-16 (v2) | Medium | K2/K3 not executed live; live-gate design assumed a failed PKCE exchange leaves the code usable — Keycloak actually burns the code | First v2 live-gate run failed honestly at the contaminated callback (`PROVIDER_ERROR`); direct probe confirmed second exchange → "Code not valid" | K2 uses a disposable transaction; legitimate flow proven separately with a fresh code; behaviour documented in API_CONTRACT §4 | Fixed (retest: live gate 3×, 80 checks each, all PASS) |
| IF-V8-01 (v8, WS1) | Low | Issuer URL comparison accepted a trailing slash: `validate_issuer_url("…/identityforge-lab/", …)` returned `OK` — the "exact allowlisted issuer URL" check was not exact | `validate_issuer_url` probe pre-fix | Exact comparison (`url not in set(allowed_issuers)`) | Fixed (retest: WS3 property test `test_issuer_trailing_slash_rejected_if_v8_01` + exact-equality oracle, 24 property tests pass post-fix) |
| IF-V8-02 (v8, WS1) | Low | Callback missing-parameter reason codes were unreachable dead code: the duplicate-parameter check ran first, so a callback with NO state hit `CALLBACK_MALFORMED` and `STATE_MISSING` was never emitted | `GET /auth/callback` (no params) pre-fix → `CALLBACK_MALFORMED` | Presence checks first, duplication second | Fixed in tree; OIDC suite 18/18 in the two sequential 482/482 full runs (TBD-WS1-01, RESOLVED) |
| IF-V8-03 (v8, WS1) | Low | Transport rewrite transplanted query/fragment onto the trusted route and silently truncated a pathed transport base | `rewrite_to_transport("…/certs?next=http://evil.example", …)` pre-fix → transport URL carrying the query | Explicit rejects for query/fragment in source or base and path in base | Fixed (retest: WS3 property test `test_rewrite_rejects_query_fragment_and_base_path_if_v8_03`, 6 rejections + control) |
| IF-V8-04 (v8, WS1) | Informational | Mid-body disconnect observed as a bare connection close, no 400/413 bytes — uvicorn/h11 tears the connection down before the middleware can answer; the partial body is never processed | WS1 raw probe: truncated body / 1 MiB+1 declared → no response bytes | Documentation note in the middleware; no code change (no app code can answer on a torn-down connection) | Documented as intended behaviour |
| IF-V8-05 (v8, WS1) | Low | Unbounded IdP response bodies (httpx buffered the whole body) + `RecursionError` escaping JWKS parsing on pathologically nested JSON | Fake IdP with oversized / deeply-nested JWKS pre-fix | All IdP fetches via `httpx.stream` with a 1 MiB cap; `RecursionError` and HTTP error statuses mapped to controlled `ValueError` | Fixed (retest: WS3 fault suite re-run 51 passed incl. updated `http500` expectation) |
| IF-V8-40 (v8, WS2) | Low | Vite preview served no security headers (no CSP / X-Frame-Options on HTML/JS) | `curl -i http://127.0.0.1:5173/` pre-fix → headers absent | Vite security-headers plugin wired to dev + preview servers | Fixed (retest: Playwright header spec passes; WS2 regressions 11/11) |
| IF-V8-41 (v8, WS2) | Low | E2E socat forwarders listened on all interfaces instead of loopback | Compose-file inspection pre-fix | socat binds pinned to `127.0.0.1` (5173/8000/8080) | Fixed (retest: WS2 regressions, bind checks PASS) |
| IF-V8-80 (v8, WS3) | Low | Stale release prose in quickstart guides: "the v7.3 final release name" ×2 and "release version 1.7.3" ×2 after the release moved to v8 / 1.8.0; the existing 33/33 docs-contract-paths checks did not cover prose | Read the four lines in the v7.3.1 tree | Four lines updated to v8 / 1.8.0 (+ the three hash commands updated to the v8 ZIP, required by check 5); new docs-contract check 6 | Fixed (retest: planted stale lines fail with exactly 4 violations, rc=1; clean tree PASS; paths 42/42) |
| IF-V8-81 (v8, WS3) | Low | Version-contract fixture negatives were vacuous: the five one-source patterns still held the sed-escaped `1\.7\.4`, so `sed` matched nothing and the "negative" could not fail | First clean fixtures run 8/13 | Python literal replaces of the five patterns to `1\.8\.0` | Fixed (retest: second clean run 13/13) |
| IF-V8-82 (v8, WS3) | Informational | Live login starts return designed 503s under concurrent load: the 20-slot global transaction store saturates and denies logins for up to 600 s (one unauthenticated client can fill it) | 30 rapid login starts → 302s then 503 `TRANSACTION_STORE_FULL`, `transactions: 20` | None in product code (by design); reviewers run login-heavy suites sequentially; WS3 probes run rate-cap tests on disposable apps only | Documented as intended behaviour + residual risk (see accepted risks) |
| IF-V8-42 (v8.0.5, WS1) | Low | App Dockerfiles ran as root (no USER instruction) | `grep ^USER backend/Dockerfile frontend/Dockerfile` → no matches (v8) | Dedicated user `identityforge` UID:GID 10001 in all three app images (`USER 10001:10001`, no `USER root`); one-shot root-only `backend-data-prep` service repairs /app/data ownership (top level only, fail-closed) for fresh AND existing root-owned volumes; pip-audit installed at build time; E2E non-root too | **Patch prepared, runtime verification pending** — static checker 29/29 + negative control on pristine v8.0.4 (14/29, rc=1); volume-prep stub tests 42/42; full non-Docker gate battery green (see VERIFICATION_LOG v8.0.5). Docker build/boot/in-container `id`/volume-migration/E2E NOT RUN in the sandbox — reviewer closes it on Docker Desktop per the checklist in `docs/PENTEST_FINDINGS_AND_REMEDIATIONS.md` IF-V8-42 |
| IF-V8-43 (v8.0.5, WS2) | Low | CI actions pinned to mutable major tags, not commit SHAs | `grep uses: .github/workflows/ci.yml` → `@v4`/`@v5` tags, no 40-hex SHAs (v8) | All 11 `uses:` lines pinned to upstream-verified full SHAs with `# vX.Y.Z` comments (checkout v4.4.0 `11d5960a…`, setup-python v5.6.0 `a26af69b…`, setup-node v4.4.0 `49933ea5…`, upload-artifact v4.6.2 `ea165f8d…`); repeatable checker `scripts/test-action-pins.sh` wired into the CI scripts lane (25 → 26 steps) | **SHA pin verified, hosted CI pending** — checker 8/0 + negative control 6/6 rejected; YAML valid (4 jobs, 26 steps); all four SHAs independently re-resolved from the official GitHub API by the coordinator. GitHub Actions execution NOT RUN — reviewer closes it with the test-branch run in `docs/ACTION_SHA_PINS.md` |
| — | — | No other live-gate findings. The live negative proofs (cross-browser swap, replay, CSRF-less logout, officer denial, unknown subject, malformed bodies) all behaved as designed. | — | — | — |

### Known accepted risks (by design, not oversights)

| Risk | Why it is accepted | Mitigation |
|---|---|---|
| Local HTTP on loopback | Lab-only development exception; TLS would add setup friction with no benefit on loopback | Loopback-only bindings; documented in `SECURITY.md` and `docs/VALIDATION_AND_LIMITATIONS.md`; HTTPS required for any other use |
| Synthetic credentials in the realm import | The lab must be runnable without manual Keycloak setup | Clearly synthetic, localhost-only, documented; rotate if shared |
| Keycloak 26.8.2 pin (26.8 line is the supported line as of 2026-11-05; 33 CVE fixes incl. critical SAML bypass CVE-2026-117691) | The lab uses no SAML, so that CVE does not apply here; the pin is verified to exist and boot | Reviewers check for a newer 26.8.x patch before non-lab use; `docs/KEYCLOAK_INTEGRATION.md` records the version |
| Offline fixtures are not Keycloak | Fixtures model validator logic; they cannot prove IdP behaviour | Labelled `DETERMINISTIC OFFLINE FIXTURE` everywhere; Keycloak lane separate |
| Lab reset is officer-gated (v3, P0-01) | Reset requires a logged-in officer session + CSRF + `{"confirm": "RESET_LAB"}`; the v2 "unprivileged on loopback" description is withdrawn | Documented localhost boundary (API_CONTRACT §2); reset cannot touch the Keycloak realm or volume; the operator's own session is revoked |
| npm audit cannot run in this sandbox | The audit endpoint is blocked by the sandbox proxy (403 `policy_denied`) | Frontend deps upgraded to maintained versions after advisory review; GHSA direct-dep fallback shipped (`scripts/npm-advisory-check.py`); transitive coverage needs `npm audit` on a machine with registry access |
| Shared live backend's 20-slot transaction store saturates under parallel login load (v8, IF-V8-82) | By design (P1-10, v4): a full global store is a 503, never another browser's eviction; per-browser quota 4 + rate cap 30/min bound one browser, but the global cap is shared | Reviewers run login-heavy suites sequentially; the 503 is a capacity answer with no partial state and recovery by TTL expiry (600 s), no restart; documented in the v8 pentest report §N |

## 5. Retest notes

- After any fix, re-run the affected suite **and** the full offline suite
  (`./scripts/test-all.sh`), and record the new result here with the date.
- A finding is only "Fixed" when the failing test now passes *and* the
  legitimate path still works (positive test re-run). Fixing a negative
  test by breaking the happy path is a new defect.
- **v8.0.5 retest (2026-11-14, sandbox — no Docker, no hosted CI):**
  IF-V8-42 retested by static checker (`scripts/check-docker-nonroot.py`
  29/29 PASS; 14/29 on the pristine v8.0.4 tree) and volume-prep stub
  tests (`scripts/test-prepare-data-volume.sh` 42/42 PASS, real SQLite
  DBs + `setpriv` app-user write proofs); the full non-Docker gate
  battery was re-run by the coordinator on the final 1.8.5 tree and is
  all green (pytest 520, offline 516/4, live 4/516, WS3 51, CLI 18/18,
  Vitest 161/161, build byte-identical `a77dd7d5…`, test-all --offline
  11/0/8, live gate 101/101 + reset 69/69 with dev counts
  byte-identical on restore, Playwright 72+1 validator PASS, axe
  25/25) — see `docs/VERIFICATION_LOG.md` v8.0.5 Pass B rows for the
  measured numbers. Docker runtime proof (build, boot, in-container
  `id`, fresh/existing-volume login + persistence + `integrity_check`,
  E2E) is NOT RUN and stays the reviewer's Docker Desktop gate.
  IF-V8-43 retested by the new checker (`scripts/test-action-pins.sh`
  8/0 positive, 6/6 defects rejected in the negative control) and by
  the coordinator independently re-resolving all four SHAs from the
  official GitHub API; hosted Actions execution is NOT RUN and stays
  the reviewer's test-branch gate (see `docs/ACTION_SHA_PINS.md`).
