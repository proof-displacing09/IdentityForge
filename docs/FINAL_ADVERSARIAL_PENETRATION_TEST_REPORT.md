# Final Adversarial Penetration Test Report — Operation Trustline v8

IdentityForge OAuth/OIDC authentication attack laboratory — full
adversarial penetration test + immediate remediation, release label
**v8**, product version **1.8.0**.

> **Reading note.** Every number in this report names its log file
> in `docs/PENTEST_TEST_EVIDENCE_INDEX.md`. Status words are exactly
> PASS / FAIL / NOT RUN / NOT APPLICABLE. A TBD row is work still in
> flight — it is never a pass. Where a first run failed for a
> test-harness reason, the failure is reported with its cause, not
> hidden behind a re-run.

## A. Executive overview, authorization scope, dates, tools

**What this is.** Operation Trustline v8 is a full adversarial
penetration test of the entire IdentityForge app — backend, frontend,
login flows, validators, evidence store, docs, and supply chain —
plus immediate in-place remediation of what it found, a version bump
to 1.8.0, and a stale-prose fix that subsumes the pending v7.3.2
choice. It is not a greenfield rebuild: the app, its 12 views, its
routes, and its tests are preserved; only defects and their
regressions were added.

**Authorization scope.** The project owner (identity redacted for public release) commissioned the test on
2026-11-12 from the exact delivered v7.3.1 archive. All attacks ran
against the local synthetic lab only: loopback Keycloak 26.8.2,
synthetic accounts `student_01` / `officer_01`, disposable test
instances, and temp databases. No real IdPs, no real users, no
external systems, no publishing, no changes to the user's Windows
machine. Source-level mutation testing was explicitly forbidden and
was not performed. Three workstreams shared the work: WS1 (backend),
WS2 (frontend/E2E), WS3 (depth / property-testing + pentest report
docs + version bump + stale-prose fix — this report).

**Dates.** Baseline 2026-11-12; depth work, fixes, and verification
2026-11-12–13 (UTC). The live stack ran throughout: Keycloak 26.8.2
(java PID 3342), backend (python PID 3420, port 8000), Vite preview
(PID 3603, port 5173).

**Tools.** Python 3.12.3 + pytest + Hypothesis 6.170.15 (disposable
venv); Node 24.22.1 / npm 10.9.4; Vitest; Playwright + axe;
PowerShell 7.4.6 on Linux (`~/workspace/.pwsh/pwsh`); `curl`,
`httpx`, `http.client` raw-socket probes; `sqlite3` CLI; `pip-audit`
2.10.1; GHSA direct-deps check; `sha256sum` / `Get-FileHash`
equivalents. No Docker existed in the sandbox (no binary/socket) —
Docker-dependent proofs are NOT RUN, never passed.

**Headline result.** 16 findings with fixes or documented
dispositions (IF-V8-01–05 WS1; IF-V8-40/41/44/45 WS2; IF-V8-80–84
WS3), of which 2 remain OPEN hardening items (IF-V8-42 — app
Dockerfiles run as root; IF-V8-43 — CI actions pinned to major tags,
not SHAs — both need a Docker boot / CI run that cannot execute in
this sandbox) and the parent's Pass C packaging check. IF-V8-83
(WS1's three new test files failing `ruff format --check`) was
found during the `test-all.sh --offline` re-run and fixed
mechanically by WS3. The three WS1 TBD items (TBD-WS1-01/02/03) are **RESOLVED** (2026-11-13):
all three were concurrency artifacts / corrected probe
expectations, proven by two independent sequential full runs
(**482 passed, 0 failed**). No confirmed exploitable vulnerability was
found in the executed scope. The deepest validation layers — the
ID-token validator, the SSRF guards, PKCE/state/nonce handling,
callback replay protection, CSRF, role enforcement, evidence
redaction — withstood property-based, differential, fault-injection,
concurrency, and live adversarial testing with **no bypass**.

## B. Baseline + SHA-256 provenance, preserved original backup

- Source baseline: the delivered v7.3.1 archive
  `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V7.3.1_FINAL_20261112.zip`,
  333 files, 42,086,753 bytes, SHA-256
  `1bf0c6d91fa4fd7085061eea89b5ba18370112e4ec15936109e1e08412dc924d`.
- The v8 tree (`~/workspace/identityforge-v8`) is an exact copy of
  that archive. The preserved original is the immutable backup at
  `~/workspace/backups/v7.3.1/` (mode 444) — WS3 re-verified its
  SHA-256 against the delivery hash: **exact match**.
- Baseline gates on the untouched tree (WS3, before any edit):
  version-contract PASS (1.7.4), docs-contract PASS (0 violations),
  docs-contract-paths 33/33, version fixtures pass at 1.7.4.
  Logs: `~/workspace/ws3-v8-evidence/baseline-*.log`.
- v7.3.1 baseline test state (WS1): full pytest **397 passed**,
  CLI 18/18, ruff clean, Vitest 161/161, Playwright 71 passed +
  1 skipped, axe 25/25 0 violations.

## C. Architecture / trust-boundary diagram + attack surface

See `docs/PENTEST_ATTACK_SURFACE_AND_THREAT_MODEL.md` (the full
working view) and `docs/THREAT_MODEL.md` (standing model).

```
Browser ──5173──► Frontend (12 views) ──8000──► Backend (FastAPI)
                                                      │  ├─ SQLite evidence DB
                                                      │  ├─ session store (TTL 1800 s)
                                                      │  └─ transaction store (cap 20, TTL 600 s)
                                                      ▼
                                               Keycloak 26.8.2 (8080)
                                               realm identityforge-lab
```

Trust boundaries: B1 browser↔backend (session cookie, CSRF,
framing headers); B2 backend↔Keycloak (pinned issuer, discovery
validation, JWKS SSRF guard, transport provenance); B3 callback↔
browser session (one-use state/nonce/verifier, PKCE S256); B4
operator↔evidence (officer-only reset); B5 API↔evidence DB (caps,
failure reporting); B6 lab↔Internet (nothing leaves loopback by
design; `trust_env=False` on IdP fetches).

## D. Test inventory per endpoint / login stage / UI view

See `docs/PENTEST_TEST_MATRIX.md` for the full matrix. Summary:

| Area | Tests | Result |
| ---- | ----- | ------ |
| WS3 property tests (Hypothesis) | 24 | 24 passed |
| WS3 differential + negative controls | 12 | 12 passed |
| WS3 fault injection / concurrency / malformed corpus | 15 | 15 passed |
| WS3 stateful live sequence | 55 checks | 55 passed |
| WS3 extra live probes | 17 checks | 0 failed (post-recovery) |
| WS1 adversarial suite (postfix) | 78 | 78 passed |
| WS1 matrix suite | 60 | 60 passed |
| WS1 OIDC suite | 18 | 16 passed, 2 failed in the concurrent run — RESOLVED (all 18 pass in both sequential 482/482 runs) |
| WS1 raw HTTP framing probes | 22 | **21/21 passed** in the final run (earlier 19/22 was two wrong probe expectations + one staging artifact — TBD-WS1-02, RESOLVED) |
| Full backend pytest (concurrent runs) | 482 | 431 passed, 51 failed — concurrency artifact, superseded |
| Full backend pytest (sequential, WS1 + WS3, independent) | 482 | **482 passed, 0 failed** (TBD-WS1-03, RESOLVED) |
| Vitest | 161 | 161 passed |
| Playwright (postfix run 1) | 73 | 60 passed, 12 failed, 1 skipped — IF-V8-45 (transient) |
| Playwright portal re-run | 8 | 8 passed |
| Playwright screenshots re-run | 30 | 22 passed, 8 failed — IF-V8-45 |
| Contract gates | — | version 13/13, docs PASS, paths 42/42 |

## E. Individual verified findings with actual minimal attack evidence

The full §13 evidence tables are in
`docs/PENTEST_FINDINGS_AND_REMEDIATIONS.md`. Condensed here:

| ID | Finding (one line) | Class | Severity | Status |
| -- | ------------------ | ----- | -------- | ------ |
| IF-V8-01 | Issuer comparison accepted a trailing slash | Non-exploitable bug | Low | FIXED |
| IF-V8-02 | Callback missing-param reason codes were dead code | Non-exploitable bug | Low | FIXED (verified — OIDC suite passes sequentially) |
| IF-V8-03 | Transport rewrite transplanted query/fragment, truncated pathed base | Hardening | Low | FIXED |
| IF-V8-04 | Mid-body disconnect = bare close, no 400 (h11) | Intended behaviour | Info | DOCUMENTED |
| IF-V8-05 | Unbounded IdP bodies + RecursionError escape | Hardening | Low | FIXED |
| IF-V8-40 | Vite preview served no security headers | Hardening | Low | FIXED |
| IF-V8-41 | socat forwarders not bound to loopback | Hardening | Low | FIXED |
| IF-V8-42 | App Dockerfiles run as root (no USER) | Hardening | Low | OPEN — needs entrypoint/chown work + Docker boot test |
| IF-V8-43 | CI actions pinned to major tags, not SHAs | Hardening | Low | OPEN — SHAs must be fetched upstream; CI execution NOT RUN |
| IF-V8-44 | Realm client omits `fullScopeAllowed` (defaults true) | Hardening | Low | FIXED (Pass B — fresh Keycloak boot proof) |
| IF-V8-45 | Playwright failures under concurrent load | Env / false positive | Info | RESOLVED as concurrency artifact; clean validator PASS achieved in parent's Pass C (72 passed + 1 skipped, validator PASS) |
| IF-V8-80 | Stale release prose in quickstart guides | Non-exploitable bug (docs) | Low | FIXED |
| IF-V8-81 | Version-fixture negatives were vacuous | Harness false positive | Low | FIXED |
| IF-V8-82 | Login 503s under concurrent load (20-slot store) | Intended behaviour | Info | DOCUMENTED |
| IF-V8-83 | WS1's 3 new test files fail `ruff format --check` (OFFLINE_UNIT gate) | Harness false positive | Low | FIXED (confirmed by test-all run3: 11/0/7, rc=0) |
| IF-V8-84 | Playwright edge spec asserted the pre-fix reason code for a missing state | Test defect | Low | FIXED (spec updated to `STATE_MISSING`; edge spec 8/8 post-fix; clean full run 72 passed + 1 skipped with validator PASS in parent's Pass C) |

Minimal attack evidence (each reproduced before fixing):

- **IF-V8-01:** `validate_issuer_url("…/identityforge-lab/", …)` → `OK`
  pre-fix; → `UNTRUSTED_ISSUER_URL` post-fix.
- **IF-V8-02:** `GET /auth/callback` (no params) → `CALLBACK_MALFORMED`
  pre-fix (should be `STATE_MISSING`); presence-first ordering
  post-fix.
- **IF-V8-03:** `rewrite_to_transport("…/certs?next=http://evil.example", …)`
  → transport URL carrying the query pre-fix; `ValueError` post-fix.
- **IF-V8-05:** fake IdP serving an unbounded JWKS body was fully
  buffered pre-fix; post-fix the streamed read aborts past 1 MiB.
- **IF-V8-40:** `curl -i http://127.0.0.1:5173/` pre-fix showed no
  CSP / `X-Frame-Options`; post-fix the header spec passes.
- **IF-V8-80:** the four stale lines (guides §0/§3 and §492/§317)
  named v7.3 / 1.7.3; check 6 now fails on exactly those lines.
- **IF-V8-82:** 30 rapid login starts → 302s then 503s
  (`{"detail": "provider_unavailable", "reason":
  "TRANSACTION_STORE_FULL"}`, `transactions: 20`); recovery to 302
  after TTL expiry, no restart.
- **IF-V8-84:** pre-fix full Playwright run failed exactly one test
  (`edge.spec.ts:131`, missing state expected `CALLBACK_MALFORMED`
  but the app correctly returned `STATE_MISSING` after the IF-V8-02
  fix); post-fix the edge spec passes 8/8, and the clean full run in
  parent's Pass C passes 72 + 1 skipped with validator PASS.

## F. Severity / CVSS rationale, non-exploitability notes

No finding is network-exploitable from outside the lab: every
service is loopback-only, and no finding gives an unauthenticated
attacker a session, a role, a token, or evidence. The two
non-exploitable bugs (IF-V8-01, IF-V8-02) weaken trust-boundary
checks or diagnostic fidelity but have no live exploit path —
IF-V8-01 because the issuer is pinned in config and discovery is
validated exactly elsewhere; IF-V8-02 because every malformed
callback shape was still rejected, only mislabelled. The hardening
items (IF-V8-03, IF-V8-05, IF-V8-40, IF-V8-41) close defense-in-depth
gaps whose exploitation would each need a further precondition
(a compromised IdP, a framing victim, an E2E-run network observer).
CVSS-style reasoning is given per finding in the register; no CVSS
vector is claimed where the issue is not network-exploitable.
IF-V8-82 is availability-only by design (a shared 20-slot store in
a teaching lab).

## G. Fix table with failing-first + post-fix proof for EVERY fix

| ID | Failing-first proof | Post-fix proof |
| -- | ------------------- | -------------- |
| IF-V8-01 | WS3 oracle (pre-fix) asserted the slashed issuer was OK; WS1's code comment records the pre-fix `OK` | `test_issuer_trailing_slash_rejected_if_v8_01` passes; 24 property tests pass (`ws3-suites-postfix2.log`) |
| IF-V8-02 | Old order: no-state callback → `CALLBACK_MALFORMED` (WS1 code comment + OIDC suite) | Presence-first in tree; OIDC suite 18/18 in both sequential 482/482 full runs (TBD-WS1-01 RESOLVED — the 2 failures were concurrent-run artifacts) |
| IF-V8-03 | Pre-fix rewrite transplanted `?next=` (WS1 code comment) | `test_rewrite_rejects_query_fragment_and_base_path_if_v8_03` passes (6 rejections + control) |
| IF-V8-05 | Pre-fix unbounded buffering + `RecursionError` escape (WS1 code comment) | WS3 fault suite re-run 51 passed incl. updated `http500` → uniform `ValueError` |
| IF-V8-40 | `failing-first-preview-headers.txt` (headers absent) | Header spec 1 passed; WS2 regressions 11/11 |
| IF-V8-41 | Regression checks pre-fix (unbound socat) | WS2 regressions: socat 5173/8000/8080 bind checks PASS |
| IF-V8-80 | Planted stale lines → exactly 4 violations, rc=1 (`docs-contract-stale-planted-v2.log`) | Clean tree PASS rc=0; paths 42/42 |
| IF-V8-81 | First fixtures run 8/13 (five vacuous negatives) | Second clean run 13/13 |
| IF-V8-82 | Burst probe: 503s, store full (`extra-live-probes.log`, run-2) | Post-recovery probes 0 failed; stateful 55/55 |
| IF-V8-83 | `test-all.sh --offline` run2: OFFLINE_UNIT FAIL at `ruff format --check` (3 files would be reformatted; pytest never ran in the gate) | `ruff format` on the 3 files; whole-tree format check rc=0; the 3 files' tests 85/85 post-format; test-all run3 **11/0/7, rc=0** — OFFLINE_UNIT PASS |
| IF-V8-84 | Pre-fix full Playwright run: 71 passed, 1 failed, 1 skipped — `edge.spec.ts:131` expected `CALLBACK_MALFORMED`, app returned `STATE_MISSING` (correct after the IF-V8-02 fix); validator failed only on the edge floor | Spec updated to `STATE_MISSING`; edge spec **8/8** post-fix; parent's Pass C full run **72 passed + 1 skipped, rc=0**, validator **PASS** |

## H. Negative controls and what secure behaviour rejected

- **Differential (12 tests):** for each of issuer, audience, expiry,
  nonce, signature, subject, the flawed validator (with that check
  omitted) accepts the attack token while the secure validator
  rejects it with the documented reason — proving every check is
  load-bearing. With `omit=()` the two validators agree on the
  whole attack matrix (no drift).
- **Negative controls (subprocess):** corrupting an isolated fixture
  (wrong signing key / wrong issuer / empty JWKS) makes the "valid
  token passes" assertion FAIL; uncorrupted it passes. The tests
  measure security; they do not always pass.
- **What secure behaviour rejected (live):** callback replay (same
  code+state — no second session); cross-browser callback; forged
  binding cookie; unknown-state callback; `error=access_denied`
  callback (no session); session fixation (planted id replaced);
  student officer-access (403) and student reset (403); wrong-confirm
  reset (422); CSRF-less reset/logout (403); expired sessions (401,
  pruned, never resurrected); open-redirect params (ignored);
  `alg=none` / HS256 tokens (`ALG_NOT_ALLOWED`); unknown kid
  (`UNKNOWN_KEY`); malformed JWKS (`JWKS_ERROR`); wrong-issuer
  discovery (WS2: FAIL as expected).
- **Security headers (WS3 measured):** backend responses carry
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, `Content-Security-Policy:
  default-src 'none'; frame-ancestors 'none'`, `Cache-Control:
  no-store, no-cache, must-revalidate`.

## I. Redaction + SQLite integrity results with exact queries/counts

Queries run read-only against a copy of the live DB
(`~/workspace/.verify/ws3-devdb-copy.db`, copied from
`backend/data/identityforge.db`):

```sql
PRAGMA integrity_check;            -- ok
PRAGMA foreign_key_check;          -- (empty)
SELECT COUNT(*) FROM runs;         -- 64
SELECT COUNT(*) FROM events;       -- 97
SELECT COUNT(*) FROM live_login_events;  -- 501
SELECT COUNT(*) FROM events e LEFT JOIN runs r ON e.run_id = r.run_id
  WHERE r.run_id IS NULL;          -- 0 orphan events
SELECT MAX(LENGTH(detail)) FROM live_login_events;  -- 56
```

Redaction: `SELECT ... WHERE detail LIKE '%id_token%' OR detail LIKE
'%code=%' OR detail LIKE '%LabPass%' OR detail LIKE
'%client_secret%'` → 70 rows, all the fixed prose string "ID token
signature, issuer, audience and nonce verified" (stage
`ID_TOKEN_VALIDATED`) — stage labels, not raw values. The live
`/api/v1/live-logins` payload scan in the stateful sequence found no
`id_token` / `access_token` / `code=` / `code_verifier` /
`client_secret` / `LabPass-` substrings. No raw tokens, codes,
verifiers, states, or passwords are stored in evidence or in the DB.
Sessions live only in memory (no `sessions` table exists).

## J. Dependency / CI / OS / Docker availability + CVE analysis

- **pip-audit 2.10.1 (WS2):** clean — "No known vulnerabilities
  found" (full pinned runtime set; `test-all.sh --offline`
  `PYTHON_DEPENDENCY_AUDIT` PASS).
- **Full `npm audit`:** NOT RUN — registry endpoint returns 403
  `policy_denied` (`zz_managed_internal_spaces_package_registries`).
  This is a reviewer gate, not a pass.
- **GHSA direct-deps fallback:** INCOMPLETE / NOT RUN at last reading
  — 3 packages unreachable (`@types/react`, `@types/react-dom`,
  `typescript`); quota-volatile on the shared egress IP. It covers
  direct dependencies only and is never a substitute for the full
  audit.
- **Dependency gates:** 55/0 (WS2 baseline).
- **CI:** GitHub Actions execution NOT RUN (YAML validated locally
  only — 4 jobs, 20 scripts-lane steps).
- **OS:** Linux sandbox, Python 3.12.3, Node 24.22.1, npm 10.9.4,
  PowerShell 7.4.6 on Linux. Windows PowerShell 5.1 NOT RUN.
- **Docker:** no binary/socket in the sandbox. Compose boot,
  in-image Keycloak healthcheck, container live-gate, and `docker
  compose config` are NOT RUN (reviewer gates on Docker Desktop).
  `scripts/compose-config-check.py` passes (YAML-only validation).

## K. Three-pass test report with commands / environments / exit codes

Pass 1 — baselines (untouched tree): version-contract rc=0,
docs-contract rc=0, docs-contract-paths 33/33 rc=0, version fixtures
rc=0 (all at 1.7.4). WS1 baseline: pytest 397 passed rc=0, CLI 18/18,
ruff clean, Vitest 161/161.

Pass 2 — WS3 depth work (failing-first, then fixed; all honest
first runs preserved in `~/workspace/ws3-v8-evidence/`):

| Run | Command | Result |
| --- | -------- | ------ |
| Properties 1 | `pytest scripts/pentest/ws3/test_ws3_properties.py` | 5 failed — all WS3 harness bugs: Hypothesis deadline on slow RSA keygen (fixed: `deadline=None`); oracle missing the SSRF hint branch (`/metadata` → `SSRF_BLOCKED`, correct); duplicate `nonce` kwarg; corpus miscount (513 vs 500); no-op token mutations (same char / padding-bit-only changes yield the byte-identical token, correctly still valid — the corpus now skips byte-equivalent mutations and counts them) |
| Properties 2 | same | **22 passed** |
| Differential 1 | `pytest scripts/pentest/ws3/test_ws3_differential.py` | **12 passed** |
| Fault 1 | `pytest scripts/pentest/ws3/test_ws3_fault_injection.py` | 5 failed — fake-server Content-Length bug (16 not 18); root bypassing chmod (replaced with parent-is-a-file); httpx refusing control chars (client-refused, counted separately); wrong expectation (disk failure is reported via `evidence_saved=false`, not a 500 — P1-14); RLIMIT child crashing at store init (wrapped init too) |
| Fault 2 | same | **15 passed** |
| Stateful 1 | `stateful_live_sequence.py` | 55 checks, 5 failed — `api()` 3-tuple unpack bug (×12 call sites); expired sessions pruned, not resurrected (correct behaviour — test corrected); officer session pruned by the same clock move (test restructured) |
| Stateful 2 | same | **55 passed** |
| Extra probes 1–2 | `extra_live_probes.py` | 2 failed, then 1 failed — live login 503s (IF-V8-82 capacity window) |
| Extra probes 3 | same (post-recovery) | **0 failed** |
| Version fixtures 1 | `bash scripts/test-version-contract.sh` | 8/13 (IF-V8-81) |
| Version fixtures 2 | same | **13/13** |
| Docs-contract check 6 | planted stale lines | rc=1, exactly 4 violations; clean tree rc=0 |
| Full pytest (concurrent) | `pytest backend/tests` | 431 passed, 51 failed — concurrency artifact (TBD-WS1-03, RESOLVED by the two sequential runs below) |
| Full pytest (sequential, WS1) | `pytest backend/tests` | **482 passed, 3 warnings in 83.48s** (`full-pytest-postfix-final.txt`, 02:52 UTC) |
| Full pytest (sequential, WS3, independent) | `pytest backend/tests` | **482 passed, 0 failed**, rc=0 (`pytest-full-sequential-ws3.log`, ~02:55 UTC; 482 collected — see the note appended to that log: the summary line was truncated by WS3's own `tail -15` capture) |
| WS1 live gate `all` | `scripts/live-gate.py all` | **101/101 checks passed** (`live-gate-all.txt`, 02:52 UTC; 101 `"pass": true`, 0 false; `"passed": true`) |
| `test-all.sh --offline` | `bash scripts/test-all.sh --offline` | run1 rc=1 — OFFLINE_UNIT (51 pytest, concurrent artifact) + FRONTEND_UNIT (1 Settings test, fixed after) |
| `test-all.sh --offline` run2 | same | rc=1 — OFFLINE_UNIT at `ruff format --check` (IF-V8-83); FRONTEND_UNIT PASS (161/161) |
| `test-all.sh --offline` run3 | same | **rc=0 — 11 PASS / 0 FAIL / 7 NOT RUN** ("All required offline gates passed"); GHSA PASS (14 direct, 0 high/critical — advisory data cached from 02:57:18Z); NPM_FULL NOT RUN (blocked) + 6 full-profile gates NOT RUN |

Pass 3 — post-fix re-runs (after WS1 landed IF-V8-01/02/03/05):
WS3 suites **51 passed** (24 property incl. IF-V8-01/03 regressions
+ 12 differential + 15 fault); stateful **55/55**; extra probes
**0 failed**; Settings.test.tsx **15/15**; docs-contract PASS;
paths **42/42**; version-contract PASS (1.8.0); fixtures **13/13**.

Environment for every run: Linux sandbox, Python 3.12.3, Node
24.22.1, npm 10.9.4, pwsh 7.4.6, Keycloak 26.8.2 host process,
backend on 127.0.0.1:8000, Vite preview on 127.0.0.1:5173. No Docker.

## L. Accessibility / responsiveness / premium-design regression audit

(WS2-owned; summary from WS2 evidence.)

- axe scans: 25/25, 0 violations (v7.3.1 baseline; re-measured in
  v8 Playwright runs — `postfix-playwright.log` reports "axe
  findings: 0 violations").
- Screenshots: 131 PNGs re-rendered fresh in v7.3 (same filenames);
  v8 re-renders: screenshots re-run 22 passed / 8 failed, all 8
  failures login-dependent (IF-V8-45), not layout defects; single
  320x740 run passed alone. Those 8 failures stay recorded here as
  history — they were a concurrency artifact of the shared backend's
  20-slot transaction store (IF-V8-82), not a layout defect. Final
  state (parent's Pass C, 2026-11-13): the full Playwright run passed
  **72 passed + 1 skipped, rc=0**, and all 30 screenshots-spec checks
  passed in that run (`playwright-passc.txt`); the validator PASSED
  on the single report.
- Viewport probe: WS2 `viewport-probe.log` — **36 checks, 0
  overflow**: 3 widths (320 / 768 / 1440) × 12 routes (`/`, `/portal`,
  `/scenarios`, `/flows`, `/protocol`, `/validation`,
  `/secure-vs-flawed`, `/boundaries`, `/findings`, `/reports`,
  `/settings`, `/learn`), every line reporting
  `"overflow":false` (scroll width equals inner width at each
  width).
- Frontend build byte-identical to v7.1/v7.2/v7.3
  (`index-X2bsjLBG.js`, 170.04 kB / 55.20 kB gzip, SHA-256
  `a77dd7d5…`) — the UI is unchanged, as intended; the v8 frontend
  changes are test-only (version mocks + About assertion).
- Premium-design regression: no redesign in v8; no view, route, or
  control added or removed.

## M. Clean-extraction + final ZIP checksums / manifest

**Parent's Pass C (2026-11-13, own runs on the final v8 tree and the
final v8 ZIP).** The final v8 ZIP is
`IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V8_FINAL_20261113.zip`
— **352 files**, product version **1.8.0** (byte count and SHA-256 are
properties of the ZIP file itself, so they live in the delivery
message only, never inside the archive). The manifest section for v8
(`docs/RELEASE_MANIFEST.md`, "Operation Trustline v8") declares that
filename, version 1.8.0, and the 352-file count.

Three fresh extractions of the actual final ZIP bytes, each
`verify-release.sh` **rc=0 ("All executed checks passed")**:

| Extraction | Log | Result |
| ---------- | --- | ------ |
| Plain `~/workspace/.verify/v8-final-plain` (second run, after the re-pack fix below) | `verify-release-plain2.txt` | **23 PASS / 0 FAIL / 5 NOT RUN** (28 checks) |
| Path with spaces `~/workspace/.verify/v8 final spaces` | `verify-release-spaces.txt` | **23 PASS / 0 FAIL / 5 NOT RUN** (28 checks) |
| Ancestor named `data/` `~/workspace/.verify/data/v8-final-data` | `verify-release-data.txt` | **23 PASS / 0 FAIL / 5 NOT RUN** (28 checks) |
| Re-packaged bytes, plain extraction `~/workspace/.verify/v8-final-repack` | `verify-release-repack.txt` | **23 PASS / 0 FAIL / 5 NOT RUN** (28 checks) |

The 5 NOT RUN in every run are the same bare-extraction
deps/Docker checks (`BACKEND_PYTEST`, `FRONTEND_BUILD`,
`COMPOSE_CONFIG`, `PYTHON_DEPENDENCY_AUDIT`,
`NPM_FULL_LOCKFILE_AUDIT` — no deps/Docker in a fresh copy, honest
environment reasons); `GHSA_DIRECT_FALLBACK` **PASS** (14/14 direct
deps, 0 high/critical). Docs-contract **PASS from the
`data/`-ancestor extraction**.

> **Count correction (v8.0.1, WS1).** The v8 verification log stated
> this as 20/0/5. WS1 recounted the `verify-release` summary tables
> in the four clean logs above (28 rows each: 23 PASS, 0 FAIL,
> 5 NOT RUN) and corrected the v8 row in
> `docs/VERIFICATION_LOG.md` to **23/0/5**. The 5 NOT RUN names are
> unchanged; only the PASS count was wrong.

The first plain extraction (`verify-release-plain.txt`) was
**22 PASS / 1 FAIL / 5 NOT RUN**: `NO_INTERNAL_ISSUER` failed
because the two new pentest SSRF negative tests name
`http://keycloak:8080` as a *rejected* JWKS URL. The gate now exempts
those two files by the same precedent as the transport tests, with
the rationale documented in `scripts/verify-release.sh`, and the
re-packaged bytes re-verified 23/0/5 — docs/gate only, no product
code changed between the packagings.

Pass C gate battery on the final tree (after the sandbox write block
lifted 2026-11-13 06:10 UTC): pytest **482 passed, 3 warnings**
(`pytest-full-passc.txt`); CLI **18/18** (`cli-18-passc.txt`); ruff
check + format clean; version-contract PASS 1.8.0; docs-contract
PASS; docs-contract-paths **42/42** (`docs-paths-passc.txt`);
dep-gates **55/0** (`dep-gates-passc.txt`); test-all --offline
**11/0/7 rc=0** (`test-all-offline-passc.txt`); healthcheck
regressions **34/0/0** (`regressions-passc.txt`); PS matrix **26/0/0**
(`ps-matrix-passc.txt`); live gate `all` **101/101** +
`reset` **69/69** (`livegate-all-passc.txt`: 101 `"pass": true`,
0 false; `livegate-reset-passc.txt`: 69 `"pass": true`, 0 false —
disposable marker backend, temp DB; dev live-login counters
byte-identical on restore); full Playwright **72 passed + 1 skipped,
rc=0**, validator **PASS** (total 73, passed 72, failed 0, skipped 1)
(`playwright-passc.txt`, `playwright-validator-passc.txt`), axe
**25/25, 0 violations**; typecheck PASS; Vitest **161/161**
(`vitest-passc.txt`); build byte-identical
(`index-X2bsjLBG.js`, SHA-256 `a77dd7d5…`, `build-passc.txt`).

Plain-extraction deep check (same 352-file bytes):
pytest **482 passed** on the shipped code (import verified to resolve
to the extraction, version 1.8.0 — `pytest-extraction.txt`), CLI
**18/18**, docs-contract-paths **42/42**, dependency-gates **55/0**,
healthcheck regressions **32/0/2** (02-a/03-a correctly NOT RUN — no
baseline tree in a bare extraction), `npm ci` + Vitest **161/161** +
build byte-identical (`vitest-extraction.txt`,
`build-extraction.txt`). All Pass C logs are in
`~/workspace/passc-v8-evidence/`; verified excerpts are shipped in
`docs/pentest-evidence/` (see `docs/PENTEST_TEST_EVIDENCE_INDEX.md`).

## N. Explicit known residual risks, out-of-scope limits, NOT RUN

- **TBD-WS1-01/02/03 — RESOLVED (2026-11-13):** the full backend
  pytest's 51 concurrent-run failures and the OIDC suite's 2 failures
  were concurrency artifacts of three login-heavy suites sharing the
  live backend's 20-slot transaction store (IF-V8-82) — two independent
  sequential full runs agree **482 passed, 0 failed**; the raw-probe
  CL+TE 200 is standards-compliant (TE wins per RFC 7230 §3.3.3) and
  the final probe run is **21/21 passed**. See the register.
- **IF-V8-45:** Playwright screenshots 8 failures on re-run (load
  transient); RESOLVED as a concurrency artifact in Pass B.
- **IF-V8-82 (residual risk):** one unauthenticated local client can
  fill the 20-slot global transaction store and deny logins to other
  local operators for up to 600 s (designed 503). Reviewers should
  run login-heavy suites sequentially.
- **NOT RUN (reviewer gates):** Docker Compose boot; in-image
  Keycloak healthcheck; container live-gate; Windows PowerShell 5.1;
  full `npm audit`; GitHub Actions execution.
- **GHSA fallback incomplete** (3 packages unreachable) — the full
  audit is the only complete npm answer.
- **Out of scope:** real IdPs/users; anything beyond loopback;
  source-level mutation testing; physical host security.
- **WS3 self-report:** WS3's own login burst (30 rapid starts,
  ~02:32 UTC) filled the shared backend's transaction store and
  transiently blocked logins for all workstreams for up to ~10
  minutes. The burst is documented in IF-V8-82; probes now run
  rate-cap tests against disposable apps only.

## O. Beginner-friendly Windows PowerShell reproducibility instructions

On the reviewer's Windows machine with Docker Desktop (the only
place the full stack is reproducible — the sandbox has no Docker):

```powershell
# 1. Verify the archive you received (hash must equal the delivery message).
Get-FileHash .\IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V8_FINAL_20261113.zip -Algorithm SHA256

# 2. Extract with Info-ZIP unzip (Python's zipfile loses the .sh exec bit).
#    Then enter the extracted folder.

# 3. Boot the lab (first boot: Keycloak needs 60-120 s; keep other apps closed on 8 GB).
docker compose up --build -d

# 4. Run the offline gates first (no Docker needed for these):
.\scripts\test-all.ps1 -Full -Strict

# 5. Sign in as student_01 (member) and officer_01 (member + officer)
#    with the synthetic passwords in the README, at http://127.0.0.1:5173.
#    Member page works for both; officer page only for officer_01.

# 6. When finished, stop WITHOUT -v first (keeps evidence for review):
docker compose down
```

If a gate says NOT RUN, it did not execute — it is never a pass.
`.\scripts\test-all.ps1 -Full -Strict` fails closed (exit 1) when
any required gate is FAIL or NOT RUN. Full instructions, ports, and
troubleshooting are in `docs/WINDOWS_SETUP.md` and
`docs/REVIEWER_GUIDE.md`.

## P. Final concise verdict

**PARTIALLY VERIFIED** — with two open hardening items (IF-V8-42, IF-V8-43). Parent's Pass C is complete (§M, every number log-cited); no TBD row remains in this report.

What is verified: the validator and trust-boundary layers withstood
the full adversarial battery with no bypass; 14 of 16 findings are fixed
or documented with failing-first + post-fix proof (11 fixed, 1 documented
no-fix, 1 intended behaviour, 1 resolved as a concurrency artifact); the version bump
(13/13 fixtures, real-tree PASS) and the stale-prose fix (check 6,
42/42 paths) are proven; evidence is redacted and the SQLite store
is integral; the frontend is unchanged and its tests are green;
the full backend suite passes **482/482** sequentially (twice,
independently); the WS1 live gate is **101/101**; the raw-probe
final run is **21/21**.

What is not verified: the two open hardening items (IF-V8-42 Dockerfiles run as root, IF-V8-43 CI SHA pins), and the standing reviewer gates (Docker Compose boot,
in-image healthcheck, Windows PowerShell 5.1, full npm audit). None of those is claimed as passed. The verdict
becomes FULLY VERIFIED only when both open items are closed with
their reviewer checklists observed (see the register) and the
reviewer gates pass on a Docker/Windows machine — until then,
PARTIALLY VERIFIED is the honest verdict.
