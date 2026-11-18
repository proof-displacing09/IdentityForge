# Test Matrix — IdentityForge

> How to read this file: every row is a test the lab intends to run, where
> it runs, and what counts as passing. **Passing means the asserted
> observation happened** — a rejection must carry the expected reason code
> *and* produce no session and no resource access. An HTTP 500 is never a
> pass. Statuses in this file are the *plan*; actual results live in run
> reports under `example-reports/` (templates only in this repo — real
> executed reports are added by the release process) and in
> `docs/VALIDATION_AND_LIMITATIONS.md`.
>
> Status words: PASS / FAIL / ERROR / NOT RUN / INCONCLUSIVE (see README.md).

## 1. Unit tests (backend, offline — no Keycloak, no Docker)

Run: `cd backend && python -m pytest -q` (or `./scripts/test-all.sh`).

| ID | Area | What is asserted | Scenario |
|---|---|---|---|
| U1 | State | Random state is unpredictable, unique per transaction, bound to the transaction, single-use, expires | I2 |
| U2 | State | Missing / altered / stale / swapped state is rejected with `STATE_MISMATCH` and no session | I2 |
| U3 | PKCE | Verifier is 43–128 chars, random; challenge = `BASE64URL(SHA256(verifier))`; `plain` never produced | I3 |
| U4 | PKCE | Wrong verifier is rejected with `PKCE_MISMATCH` and no token/session | I3 |
| U5 | Redirect | Exact registered redirect URI accepted; prefix, extra path/query, and look-alike URIs rejected | I4 |
| U6 | Callback schema | Missing `code`/`state`, duplicate parameters, wrong client context rejected safely | I15 |
| U7 | OIDC claims | Valid `iss`/`aud`/`exp`/`nonce`/`sub` accepted | I1 |
| U8 | OIDC claims | Wrong issuer → `WRONG_ISSUER`; wrong audience → `WRONG_AUDIENCE`; expired → `EXPIRED`; wrong nonce → `NONCE_MISMATCH` | I5, I6, I7, I8 |
| U9 | JWT / JWK | `alg=none`, wrong algorithm, wrong key, tampered payload/signature rejected; `jwk`/`jku` header material ignored | I9 |
| U10 | JWT / JWK | Missing/malformed token, unknown `kid`, JWKS fetch failure → safe rejection, no session | I14 |
| U11 | Session | Session ID rotates on login; pre-login ID invalidated (fixation) | I11 |
| U12 | Session | Logout revokes server-side; old cookie rejected afterwards | I12 |
| U13 | Authorization | Member can access member resource; member denied officer resource; officer allowed; cross-user access denied | I1, I13 |
| U14 | Evidence | Reports contain no token/code/verifier/cookie/password; hashes are canonical | All |
| U15 | Input limits | Overlong inputs, wrong content types, log-injection strings rejected or neutralised; parsers do not crash | I17 |
| U16 | Config/SSRF | External issuer/JWKS URL rejected with `UNTRUSTED_ISSUER_URL` (metadata / private-IP URLs → `SSRF_BLOCKED`); no outbound fetch to it | I18 |
| U17 | CSRF | State-changing request without valid CSRF/origin evidence rejected; legitimate request succeeds | I16 |
| U18 | Reason codes | Every rejection carries a stable reason code from the documented set (see `docs/AUTH_FLOW.md` §2) | All |
| U19 | CSRF lifecycle (v2) | Config GET never invalidates the cached token; reset/logout rotate and return the fresh token in-band; a 403 mutation is retried at most once after a token refresh; two-tab token sharing works | P0-02 |
| U20 | Evidence provenance (v2) | `evidence_saved` defaults False; a store-less run is `EPHEMERAL` and never claims persistence; an injected DB error reports NOT SAVED with no fabricated artifact | P1-09 |
| U21 | Live events (v2) | Real-login events carry correlation ids, redacted stages and reason codes; no token/code/verifier/cookie/password appears in any event; evidence failure never breaks a login | P0-05 |
| U22 | Mutation sensitivity (v2) | Omitting one validator check at a time (signature, issuer, audience, nonce, expiry, state, PKCE, CSRF, policy) via the designed `omit` mechanism flips the decision from reject to accept — proving the tests detect a disabled check. Source-level mutation is NOT attempted | P0-07 / P1-17 |
| U23 | Officer-only reset (v3) | Reset requires officer session + CSRF + `{"confirm": "RESET_LAB"}`; check order CSRF (403) → no session (401) → student (403) → bad confirm (422); two-stage clear (evidence first, 500 leaves sessions untouched); success revokes the operator's own session and returns operator + cleared counts + fresh CSRF token | v3 P0-01 |
| U24 | Per-transaction binding (v3; v4 P1-10) | One binding cookie per login (`identityforge_txn_<state>`); **per-browser cap 4, global cap 20** (v4: a browser evicts only its OWN oldest; the global cap returns 503 `TRANSACTION_STORE_FULL`); callback reads exactly the cookie named for the presented state; mismatch does NOT consume the transaction; success deletes only that cookie; reverse-order completion works | v3 P1-06 / v4 P1-10 |
| U25 | JWKS non-signing keys (v3) | Keycloak-style document (RS256 sig + RSA-OAEP enc) parses to exactly the sig key; enc-only / wrong-alg-only documents raise (no usable signing keys); same kid on enc + sig is not a duplicate; malformed *signing* key fails closed; malformed *enc* key is skipped | v3 P1-07 |
| U26 | Transport rewrite + provenance fetch (v3; v4 P0-01) | `keycloak:8080` rewrite works for token/JWKS endpoints; `keycloak` is not a loopback host; issuer/discovery reject `keycloak:8080` URLs; bad rewrites (wrong port, lookalike host, non-realm path, external source host) rejected; **v4:** canonical URL validated BEFORE the rewrite, transport base validated as the configured `idp_transport_base`, rewritten URL re-validated narrowly; bare `fetch_jwks` still rejects `keycloak:8080`; callback integration test with transport base `http://keycloak:8080` + mocked transport creates a session | v3 P0-04 / v4 P0-01 |
| U27 | Session counts = ACTIVE (v5, IF-V4-03) | Expired/revoked records are pruned on access: `len(store)` and `active_count()` count live, unexpired, unrevoked sessions only; `total_issued` is the separate process-lifetime total; `/api/v1/lab/counts` `sessions` is active-only with `sessions_total_issued` beside it; cleanup never removes another user's valid session | IF-V4-03 |
| U28 | Evidence atomic replacement + retention (v5, IF-V4-04/11) | Saving a run with an already-used `run_id` atomically replaces that run's events in the SAME transaction (no duplicated events); mid-write failure rolls both changes back; retention is bounded (latest 1000 runs / 20000 events / 1000 live-login events, oldest pruned on save); `storage_budget()` reports counts vs limits; orphan events are counted, never silently deleted from a user's volume | IF-V4-04 / IF-V4-11 |
| U29 | Bounded body slicing (v5, IF-V4-07) | Each ASGI chunk is sliced to the remaining allowance before buffering (at most max + 1 bytes ever buffered); a single huge chunk (10–50 MiB) is rejected 413 without being buffered whole; the inclusive 1,048,576 boundary, missing/duplicate/conflicting Content-Length, and client disconnect are preserved | IF-V4-07 |
| U30 | Docs-contract (v5, IF-V4-06) | `scripts/validate-docs-contract.py` parses the `FailureReason` enum + run-report model fields from `backend/src/identityforge/models.py` and fails on any retired code/key or non-model field in docs, example reports, or UI copy (34 enum values, 59 fields, 60 files scanned, 0 violations — docs workstream's own run; negative control: 58 violations on the untouched v4 tree). Wired as the `DOCS_CONTRACT` gate in both runners + CI | IF-V4-06 |
| U31 | Docs-contract path independence (v6, IF-V5-01) | `scripts/validate-docs-contract.py` must behave identically however the tree is checked out: the source-token harvest filters on path components RELATIVE TO THE PROJECT ROOT, never on absolute path parts. `scripts/test-docs-contract-paths.sh` builds equivalent fixtures in a normal path, under a `data/` ancestor, and under a path with spaces: clean docs PASS with 0 violations in all three; a deliberately stale reason code FAILS (nonzero) in all three; a token defined only under a skipped dir BELOW the root is NOT harvested; a token defined only via a symlink escaping the root is NOT harvested; an empty scan FAILS (no green gate on an empty scan). Wired as the `DOCS_CONTRACT_PATHS` gate in both runners + CI + verify-release (19 gates total as of v8.0.2 — the v8.0.2 gate LIVE_PROVIDER_PYTEST, IF-V8.0.2-B) | IF-V5-01 |
| U32 | Version contract (v6, IF-V5-05; v7 carries it at 1.7.0; v7.1 carries it at 1.7.1) | `scripts/check-version-contract.py` reads every authoritative version value from the tree and fails unless ALL equal the release version (1.7.0 for v7): `docs/RELEASE_MANIFEST.md` (Trustline v7 section), `backend/pyproject.toml`, `backend/src/identityforge/__init__.py`, `backend/src/identityforge/api/app.py` (FastAPI version + `/api/v1/health` version), `frontend/package.json` + `frontend/package-lock.json` (both — `npm ci` fails if they disagree), and the UI must hold NO hard-coded version literal (it reads the version from `GET /api/v1/health`). `scripts/test-version-contract.sh`: all-agree PASS + one-source-differs FAILS for every source + missing-source FAILS. Wired as the `VERSION_CONTRACT` gate in both runners + CI + verify-release. Never present a hard-coded version as proof of deployed source unless the artifact matches | IF-V5-05 |
| U33 | Canonical live-login assessment (v7, IF-V6-02) | `isVerifiedLiveLogin()` requires the full canonical prefix, all ok: AUTH_STARTED → CALLBACK_RECEIVED → BINDING_VERIFIED → TOKEN_ENDPOINT → ID_TOKEN_VALIDATED → SESSION_CREATED. A bare SESSION_CREATED-ok tail, a flow missing BINDING_VERIFIED, or a flow ending before SESSION_CREATED is NOT a verified login and does NOT count in `countSuccessfulTransactions()`. Backend assessment fields (`timeline_complete`, `successful`) win when present. Overview/Reports sign-in steps use the per-user verified assessment, never a generic count | IF-V6-02 |
| U34 | Stale evidence is never current-green (v7, IF-V6-03) | Overview reviewer steps whose evidence comes from a fetched resource carry a `stale` state while that fetch is STALE: an amber past-tense "Last verified at \<time\>" chip, and NO current-green Verified pill anywhere in the reviewer path. A later successful retry returns the step to Verified and the chip disappears; a retry that returns an issuer mismatch shows "Issuer mismatch", never green; a slow request shows no Verified until it resolves | IF-V6-03 |
| U35 | Retry aborts the superseded request (v7, IF-V6-05) | `useResource` retry aborts the previous in-flight request's AbortSignal; a second retry aborts the first retry's signal; disabling the resource aborts the in-flight request and leaves NOT RUN, never a stale READY; late responses from superseded requests are ignored (generation key) | IF-V6-05 |
| U36 | Export provenance — validated server report (v7, IF-V6-01) | `downloadRunReport()` re-fetches the server report and assembles CSV/Markdown from the SERVER run (title, status, fields), never from the stale browser-local run; JSON is the server report verbatim. When the server report cannot be fetched, the download is a labelled LOCAL UNSAVED COPY with a distinct filename, never a silent substitute | IF-V6-01 |

## 2. Protocol / integration tests (backend, offline fixtures + local HTTP)

Run: `cd backend && python -m pytest -q` (protocol/integration suites);
real-Keycloak integration is a separate lane (§3).

| ID | Area | What is asserted |
|---|---|---|
| P1 | Code flow (offline fixture) | Full transaction `CREATED → … → SESSION_CREATED` with a locally signed, valid token; member resource accessible afterwards |
| P2 | Code flow (offline fixture) | Each single deviation (I2–I7) stops the transaction at the documented step with the documented reason, no session, no resource access |
| P3 | Replay | Replayed callback / double code redemption: exactly one success at most, second attempt rejected with `CODE_REUSED` (code redemption) or `STATE_REUSED` (replayed callback) (I10) |
| P4 | Concurrency | Concurrent double redemption and concurrent sign-in tabs do not create two sessions or bypass single-use (repeat runs; see §5) |
| P5 | Provider failure | Keycloak unavailable / discovery stale / JWKS timeout / malformed IdP response → fail closed, safe error, no session |
| P6 | Host/origin/CORS | Requests with wrong `Host`/`Origin`, wildcard CORS, or non-loopback context are rejected on lab endpoints |
| P7 | Reset isolation | `POST /api/v1/lab/reset` (officer-guarded, v3) wipes fixture/session state transactionally; a fresh run after reset is independent; the operator's own session is revoked |
| P8 | Flawed-vs-secure | For each scenario, the flawed fixture (one check omitted) is compared with the secure validator and the comparison report records both — with honest session semantics: a flawed "allowed" mints a session only where the engine actually executes `SessionStore.create` (I1–I10, I15); I11/I12 flawed paths let an old session SURVIVE (no new session); I14 flawed also rejects (proven); I16/I17/I18 have no session concept. See `docs/SCENARIO_METHOD.md` §9 | All |

## 3. Real Keycloak integration (live gate 2026-11-11 — host-run stack, v3 code)

Run: `python3 scripts/live-gate.py all` (lab running), or the full gate
`./scripts/test-all.sh --full --strict` (reviewer machine with Docker)
or `.\scripts\test-all.ps1 -Full -Strict` (Windows PowerShell).

**Environment note (honest):** the sandbox has no Docker binary or
daemon at all, so `docker compose up` itself is NOT RUN here. The live
gate ran the identical software as host processes — Keycloak 26.8.2
from the official distribution tarball (same version, same realm, same
hostname-v2 config), backend from the project venv, frontend via Vite
preview (production build). The shipped Compose boot path remains a
reviewer gate on Docker Desktop. K2/K3, which were NOT RUN as separate
live probes in Trustline, WERE driven live in v2 (3× each) and the
v3 live gate adds a parallel-login flow (two same-browser logins,
B-then-A completion, latest session wins, earlier revoked).

**v3 result (2026-11-11, after the JWKS fix):** login flow **37/37
checks, 0 failures**; `live-gate.py all` runs >80 checks per run.
Full Pass A/B/C counts are PENDING in `docs/VERIFICATION_LOG.md`.

**v5 note (2026-11-11):** the v5 live-gate re-run against the v5
backend is **login flow 39/39, `live-gate.py all` 101/101, reset
sub-gate 66/66** (parent's own runs, 2026-11-11; includes 2 new
code-provenance checks per run). The v5 code changes that affect
this lane: the healthcheck `$$resp` fix (IF-V4-01 — Docker boot only,
no host-run behaviour change), session counts now active-only
(IF-V4-03 — `/lab/counts` gains `sessions_total_issued`), evidence
atomic replacement + retention caps (IF-V4-04/11), and the ASGI body
slicing (IF-V4-07). No live-gate expectation changed: student member
200 / officer 403, officer 200/200, logout + stale 401, K2/K3
negatives, replay/binding negatives, officer-only reset. Full Pass
A/B/C counts are in `docs/VERIFICATION_LOG.md`.

| ID | Area | What is asserted | Status in this sandbox |
|---|---|---|---|
| K1 | Real login | Browser → Keycloak → callback → session; member resource works | PASS live 2026-11-11 (`live-gate.py all` 3×, 80 checks each) |
| K2 | Real PKCE | Wrong verifier at the real token endpoint is denied by Keycloak | PASS live 2026-11-11 (3×): 400 `invalid_grant` "PKCE verification failed"; measured: the failed exchange BURNS the code (second exchange → "Code not valid") |
| K3 | Real redirect | Unregistered redirect rejected by Keycloak; no code delivered | PASS live 2026-11-11 (3×): 400, no `code` in the response |
| K4 | Real replay | Reused code/state at the real IdP rejected | PASS live — callback replay rejected `STATE_REUSED` (3 runs) |
| K5 | Real authorization | `student_01` denied officer resource; `officer_01` allowed, via real login | PASS live 2026-11-11 (3×) |
| K6 | Real logout | Logout via real session; old cookie rejected | PASS live 2026-11-11 (3×, incl. stale 401) |
| K7 | Provider down | Keycloak stopped → login fails closed with a safe error | PASS (deterministic simulation: patched `httpx.get` → 503 `PROVIDER_UNAVAILABLE`); live stop/start not exercised in this run |

These are **observed Keycloak behaviours**, not re-implementations. A
reviewer machine with Docker runs them; results are recorded in
`docs/VALIDATION_AND_LIMITATIONS.md` with date and environment.

## 4. Browser E2E (Playwright — v4 Atelier run, real Chromium)

Run: `cd frontend && npm run test:e2e` (requires the lab running + a browser).

| ID | Area | What is asserted | Status |
|---|---|---|---|
| E1 | Real login | Keycloak login in a real browser creates a secure session | RUN in v4 — `portal.spec.ts` 7/7 PASS, 2026-11-11 (62 passed, 1 skipped across all specs; see `docs/VERIFICATION_LOG.md`). v3: 56 passed, 1 skipped |
| E2 | Authorization UI | Member sees member page; officer page denied for `student_01` | RUN in v4 — `portal.spec.ts` student_01: member 200, officer 403; officer_01: 200/200 |
| E3 | Session UX | Expired session → sign-in prompt; logout → no resurrection via back button; provider error / user-cancel / unknown-state callbacks handled with safe, visible errors | RUN in v4 — `edge.spec.ts` 7/7 PASS (missing-state → CALLBACK_MALFORMED, empty-state → STATE_MISSING, replay → STATE_REUSED, 320 px drawer keyboard); user-cancel skipped — this realm's login page offers no cancel control |
| E4 | Console | Scenario list, flow timeline, error display, report download all work | RUN in v4 — `portal.spec.ts` + `screenshots.spec.ts` 23/23 PASS across 6 viewports |
| E5 | Accessibility | Keyboard navigation, focus, ARIA, contrast on critical paths; reduced-motion respected; axe scan with ZERO violations at ANY impact level on every tested view/state | RUN in v4 — `e2e/a11y.spec.ts` (axe) **25/25 PASS, 0 total violations** (v3: 22/22; 3 new: Settings identity-unknown, Overview error-with-retry, Atlas keyboard traversal; see `docs/VERIFICATION_LOG.md`) |
| E6 | Responsive | Usable at mobile widths; no overflow on key pages; real screenshots at 320/390/768/1280/1440/1920 inspected pixel-by-pixel | RUN in v4 — `npm run test:screenshots` 23/23 PASS; **99 PNGs, all fresh v4** in `frontend/e2e/screenshots/`; all 99 inspected (9 top-crop sheets + 13 full-width key crops); 3 inspection defects found and fixed (see `docs/VERIFICATION_LOG.md`) |

**v5 note (2026-11-11, IF-V4-10):** the E2E gates must assert test
execution, not just the Playwright exit code — JSON/JUnit output with
positive minimum counts for executed real-login assertions and every
required browser-spec group, with only the one documented Keycloak
cancel-skip permitted. The count-gate change **LANDED** (WS2):
`scripts/validate-playwright-report.py` parses the Playwright JSON
report and requires total ≥ 40, per-file floors (portal ≥ 8, edge ≥ 8,
a11y ≥ 24), the 4 named real-login/discovery tests PASSED, zero
failed/timed-out/flaky, and ONLY the documented cancel skip. Playwright
v5 counts (parent's own run): **65 passed + 1 skipped** (portal 8,
edge 8 + 1 skip, a11y 25, screenshots 24); the validator PASSES the
real report. The one honest skip (realm login page has no cancel
control) is preserved in v5.

## 5. Negative / adversarial tests

Covered by U2, U4–U6, U8–U10, U15–U17, P2–P4, and the I1–I7 scenario
definitions in `docs/SCENARIO_METHOD.md`. Each negative test asserts **both**
the expected reason code **and** the absence of a session and of protected
data disclosure. Concurrency-sensitive cases (I10, concurrent tabs) are run
repeatedly (minimum 3 repetitions, more where a race is suspected) and the
repetition count is recorded in the run report.

## 6. Build / static checks

| ID | Check | Command |
|---|---|---|
| B1 | Python lint/format | `cd backend && python -m ruff check src tests && python -m ruff format --check src tests` |
| B2 | Python types | `mypy` if configured (see backend `pyproject.toml`) |
| B3 | Frontend typecheck | `cd frontend && npm run typecheck` |
| B4 | Frontend tests + build | `cd frontend && npm test -- --run && npm run build` |
| B5 | Compose config | `docker compose config -q` (reviewer machine). In this sandbox: YAML-only fallback (`scripts/compose-config-check.py`) PASS — parses, services present, ports locked, image pinned 26.8.2; the real `docker compose config` is NOT RUN here (no Docker CLI). **v5 (IF-V4-01):** the fallback now also simulates Compose interpolation and asserts the resolved Keycloak healthcheck keeps the literal `$resp` (2×) with HTTP-200 + issuer greps on the exact realm discovery URL — measured PASS (docs workstream's own run); `scripts/test-compose-healthcheck.sh` checks the RESOLVED command via `docker compose config` and (with Docker) the live health state — the Docker half is NOT RUN here |
| B6 | Secret scan | No `.env`, `*.db`, `*.pem`, `*.key` in the release tree — enforced by `./scripts/verify-release.sh` |
| B7 | Dependency advisories | `pip audit` / `npm audit` (prod vs dev distinguished in the report; advisories are reported, not hidden) | pip-audit clean 2026-11-11; npm audit NOT RUN (registry proxy 403 `policy_denied`) — GHSA direct-dependency fallback in `scripts/npm-advisory-check.py`, result in `docs/VERIFICATION_LOG.md`. **v3: the three audit gates are split** (`PYTHON_DEPENDENCY_AUDIT`, `NPM_FULL_LOCKFILE_AUDIT`, `GHSA_DIRECT_FALLBACK`); GHSA is informational, direct-only, and NEVER satisfies NPM_FULL — a blocked audit + clean GHSA still FAILS strict (`test-gate-strictness.sh` 6/6). The last completed live GHSA result is the v2 one (14/14, 03:08:26 UTC); a v3 GHSA run is pending in Pass A/B/C. **v5 (IF-V4-09):** audit classification is now by structured result, not exit code alone — `scripts/npm-audit-classify.py` distinguishes `CLEAN` / `VULNERABILITIES_FOUND` / `NOT_RUN:<reason>` (blocked/DNS/timeout/429/offline) / `CHECK_FAILED` (malformed JSON, missing metadata, contradictory rc); pip-audit tool install is a separate measured step (`TOOL_UNAVAILABLE` vs `CHECK_FAILED` vs `VULNERABILITIES_FOUND`, recorded in `test-results/audit-tools.json`). v5 audit re-runs (parent, 2026-11-11): pip-audit 2.10.1 clean; GHSA 14/14 direct deps, 0 high/critical, checked 2026-11-11T21:07:31Z; dep-gates 55/55; strictness 9/9. |
| B8 | Broken links / dead UI | Manual + E2E check of navigation, buttons, downloads; see `docs/VALIDATION_AND_LIMITATIONS.md` |

## 7. CI

See `.github/workflows/ci.yml`. Default lanes (backend, frontend) run on
push/PR with read-only permissions and now include `pip-audit` (backend)
and `npm audit --audit-level=high` (frontend). **v5:** the backend lane
also runs `python3 scripts/validate-docs-contract.py` (DOCS_CONTRACT —
IF-V4-06), which fails the lane if a doc or example names a reason code
or report field the source does not define. **v6:** the scripts lane
also runs `bash scripts/test-docs-contract-paths.sh`
(DOCS_CONTRACT_PATHS — IF-V5-01, path independence) and
`python3 scripts/check-version-contract.py` (VERSION_CONTRACT —
IF-V5-05, every authoritative version equals the release version).
The Keycloak E2E lane is manual-only (`workflow_dispatch`), runs
`./scripts/test-all.sh --full --strict` (which fails if any required
live gate was skipped), and uploads `test-results/` + Playwright
reports on failure; it is never implied by a green default run.
**A green default CI run proves the offline gates only** — it is NOT
live-Keycloak proof while the keycloak-e2e lane is `workflow_dispatch`
only; that proof exists only after the manual lane runs. CI itself is
NOT RUN in this sandbox (no GitHub Actions here).

**Status vocabulary (v6, IF-V5-10):** a gate's status in
`test-results/gates.json` is exactly one of PASS / FAIL / NOT RUN /
NOT APPLICABLE. NOT RUN means the gate did not execute — it is never
a pass, never "skipped", and never interchangeable with NOT
APPLICABLE (superseded by a covering gate, P1-05) or FAIL (the gate
ran and its check did not hold). `--full --strict` (and
`-Full -Strict`) fail CLOSED when any required gate is FAIL or NOT
RUN, including when the required full npm audit, Docker cold-start
boot, Playwright E2E, PowerShell execution, or Keycloak healthcheck
is NOT RUN.

## 8. Trustline v7.2 additions (2026-11-12)

No v7.1 row is copied forward as a v7.2 result. All rows below are
WS2-measured in this session unless marked NOT RUN.

| Area | Command | Result |
|---|---|---|
| Healthcheck regressions (IF-V7.1-02/03/04) | `bash scripts/test-compose-healthcheck-regressions.sh` | **27 passed, 0 failed, 0 not run** — failing-first on the v7.1 source (02-a: redirection error + FAIL config, stub log shows ONLY `compose version`; 03-a: v7.1 raw-bytes `json.load` raises JSONDecodeError), then fixed: log dir before first redirection, config-failure injection, spaces path, 13-case HTTP matrix (valid Content-Length + valid chunked OK; 401/404/503, wrong issuer, missing issuer, malformed JSON, HTML, truncated, chunked malformed, chunked truncated, redirect FAIL with precise reasons), `--url` stub-server cases, port-occupied fail-fast (occupant alive), unique disposable project + scoped cleanup (incl. on failure and on SIGTERM), read-only mode (no `up`/`down`), no-Docker NOT RUN. Stub `docker` only — no daemon, no images. |
| Docs-contract (IF-V7.1-05) | `python3 scripts/validate-docs-contract.py` | **PASS, 0 violations** (34 FailureReason values, 59 report-model fields, 116 source files harvested, 64 files scanned). Check 5 (new): quickstart hash commands name the current final archive from the manifest, or `$ZIP`; `*CANDIDATE` names fail. |
| Docs-contract path independence | `bash scripts/test-docs-contract-paths.sh` | **27/27** in normal / `data/`-ancestor / spaces paths (was 15/15; +12 for the IF-V7.1-05 cases (f)–(i)). |
| Version contract | `python3 scripts/check-version-contract.py` + `bash scripts/test-version-contract.sh` | **PASS** (real tree, all authoritative versions equal 1.7.2) + **13/13** fixtures. |
| Typecheck | `cd frontend && npm run typecheck` | **PASS** (`tsc --noEmit`, no errors). |
| Vitest | `cd frontend && npm test` | **161 passed** (13 files). Includes the `Settings.test.tsx` `/health` mocks + About-version assertion updated 1.7.1 → 1.7.2 (mock/test-only). |
| Production build | `cd frontend && npm run build` | **PASS** — `index-X2bsjLBG.js` **170.04 kB / 55.20 kB gzip, SHA-256 `a77dd7d5…`** (byte-identical to the v7.1 build — the UI is unchanged, as intended). |
| Screenshots | `cd frontend && npx playwright test e2e/screenshots.spec.ts` | **30 passed** (2.9m), rc=0, against the final v7.2 build (Vite preview on 5173 + v7.2 backend on 8000 + live Keycloak 26.8.2). **131 PNGs**, all regenerated in this run (same 131 filenames as v7.1; no v7.1 PNG reused under a new name). The reset modal was opened and CANCELLED, never confirmed. |
| Compose config check (static) | `python3 scripts/compose-config-check.py` (via the rewritten healthcheck script's static part) | **PASS** (ports locked to 127.0.0.1:8080/8000/5173, Keycloak 26.8.2 pinned, healthcheck `$resp` literal kept; `docker compose config` itself NOT RUN without a Docker CLI). |
| Docker Compose boot | — | **NOT RUN** — reviewer gate on Docker Desktop (no Docker binary/socket in this build sandbox). The `--with-docker` disposable path and the in-image healthcheck were exercised only with a stub `docker` (regression suite above), never against a real daemon. |
| Keycloak healthcheck in-image validation | — | **NOT RUN** — no Docker in this build sandbox. Reviewer gate. |
| Windows PowerShell 5.1 execution | — | **NOT RUN** — 5.1 is Windows-only. Reviewer gate. |
| Full npm audit | — | **NOT RUN** — reviewer gate on a machine with registry access. GHSA direct-only is NOT a substitute for it. |
| Backend pytest / CLI | — | **NOT RUN by WS2** — WS1/coordinator own the backend; the full run is for Pass A/B. (WS1 updated the version assertions in `backend/tests/integration/test_v6_backend_api.py` to 1.7.2 during the parallel workstream.) |
| Playwright (non-screenshot E2E) / live gate | — | **NOT RUN by WS2** — WS1/coordinator own the live stack and the E2E gate. |
| Mutation test (source-level) | — | **NOT RUN by design** — source-level mutation testing is forbidden; sensitivity via the designed `omit` mechanism: PASS. |
