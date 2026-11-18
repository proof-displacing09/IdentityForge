# Validation and Limitations — IdentityForge (v8, 2026-11-13)

> **v8 note (2026-11-13):** Operation Trustline v8 was a full
> adversarial penetration test + remediation on the v7.3.1 tree (product
> 1.8.0). The full report is `docs/FINAL_ADVERSARIAL_PENETRATION_TEST_REPORT.md`.
> Verdict: **PARTIALLY VERIFIED**. What ran and passed in v8: WS3 depth
> suites 51/51 (property 24, differential 12, fault injection 15);
> stateful live sequence 55/55; WS1 adversarial 78 + matrix 60; docs
> contract PASS (check 6 new, paths 42/42); version fixtures 13/13
> (second clean run — first was 8/13, IF-V8-81); Vitest 161/161; pip-audit
> clean; full backend suite **482/482 sequentially** (twice,
> independently — the concurrent-run 431/51, the OIDC suite's 2
> failures, and the raw-probe CL+TE expectation are all RESOLVED as
> concurrency artifacts / a corrected probe expectation, final probe
> run **21/21**); WS1 live gate **101/101**; `test-all.sh --offline`
> **11/0/7, rc=0**. What is **NOT** passing at WS3's writing and closed in Pass B: the final sequential Playwright run (IF-V8-45 — postfix
> 60/12/1 with transient failures tracking the shared-backend
> transaction-store saturation window, IF-V8-82; Pass B: edge 8/8 post-fix, second full run 53+1 before Chromium died, clean validator PASS NOT RUN on the Chromium environment blocker). Still NOT RUN (reviewer gates): Docker
> Compose boot, in-image Keycloak healthcheck, Windows PowerShell 5.1,
> full npm audit. The §2 rows below are the v5-measured values unless a
> row carries a v8 note; where this file and the v8 pentest report
> disagree, the pentest report's measured v8 numbers win.
>
> **v5 note (2026-11-11):** the v5 code changes are in the tree and the
> rows below carry the v5 measured values (parent-verified, Pass A/B/C)
> where noted. The rows added or rewritten for v5 are the healthcheck
> row, the docs-contract row, the session-counts / evidence-retention
> rows, and the Docker boot row (unchanged: still NOT RUN). **WS2
> update (2026-11-11):** the scripts/Docker/CI rows below (Compose
> config, dockerignore, dependency gates, gate strictness, CI workflow,
> PowerShell execution, healthcheck, npm audit, Playwright E2E +
> validator) now carry WS2's measured v5 values, confirmed by the
> parent's own re-runs. Nothing in this file marks a NOT RUN gate as
> PASS.

## 1. Environment where this release was built

- **Sandbox used for development:** Python 3.12.3, Node 24.22.1, npm 10.9.4,
  git 2.43, OpenSSL 3.0.13, Linux, ~7.7 GB RAM. **Docker / Docker Compose:
  NOT INSTALLED** in this sandbox (`docker: command not found`, no
  `/var/run/docker.sock`, no `dockerd`/`podman` binary anywhere).
- **Consequence:** anything requiring Docker could not be executed here.
  Those gates are labelled **NOT RUN** below, with the exact command a
  reviewer machine needs to run them. The live Keycloak gate instead ran
  the identical software as host processes — Keycloak 26.8.2 from the
  official distribution tarball (same version, same realm, same
  hostname-v2 config), the backend from the project venv, the frontend
  via Vite preview — which is exactly the stack `docker compose up`
  would run, minus the container supervisor. The shipped Compose path
  itself remains unexecuted here and is a reviewer gate on Docker
  Desktop.

## 2. Verification status (as of 2026-11-11, this release)

| Gate | Status | Evidence / command |
|---|---|---|
| Backend offline fixture tests (pytest) | **PASS — 340 passed, 0 failed** (parent's own run, 2026-11-11; v4 was 304) | `cd backend && ../.venv/bin/python -m pytest -q` |
| Frontend typecheck / tests / build | **PASS — tsc exit 0; Vitest 92/92 (11 files); vite build ok (JS 166.43 kB, 54.14 kB gzip, `index-DgdhM3ou.js`)** (parent's own run, 2026-11-11; v4 was 64/64, 165.14 kB) | `cd frontend && npm run typecheck && npm test -- --run && npm run build` |
| Scenario CLI (offline) | **PASS — 18/18** | `python -m identityforge.cli verify-all` |
| `docker compose config` validation | **PARTIAL — YAML-only fallback PASS** (parses; services present; ports locked to 127.0.0.1:8080/8000/5173; Keycloak image pinned 26.8.2). The real `docker compose config -q` is **NOT RUN** — no Docker CLI here. **v5 (IF-V4-01):** the fallback now also simulates Compose interpolation and asserts the resolved Keycloak healthcheck keeps the literal `$resp` (2×) — measured PASS (WS2, 2026-11-11). The `test-all.sh` Docker-present branch now also inspects the RESOLVED config (same `$resp` ×2 + `resp=$(cat <&3)` assertion as `test-all.ps1`); source-delivered, unexecuted here | `python3 scripts/compose-config-check.py`; reviewer: `docker compose config -q` |
| Docs-contract (reason codes + report fields) | **PASS — 0 violations** (docs workstream's own run, 2026-11-11): `scripts/validate-docs-contract.py` parses 34 `FailureReason` values + 59 report-model fields from `models.py` and scans 60 files (docs, example reports, frontend/src, scripts/test-matrix.md). Pre-fix on the v5 tree: 35 violations; negative control on the untouched v4 tree: 58 violations. Wired as the `DOCS_CONTRACT` gate in both runners + CI (16 gates total). **v6 (IF-V5-01/05, WS2, 2026-11-11):** the checker is now checkout-path-independent — the same tree passes with 0 violations under a normal path, under a `data/` ancestor, and under a path with spaces (v5 failed with 104 false violations under a `data/` ancestor); regression `scripts/test-docs-contract-paths.sh` **15/15**; real-tree run **PASS, 0 violations, 64 files scanned**. The runners now have **18 gates** (DOCS_CONTRACT_PATHS + VERSION_CONTRACT added). The version-contract gate FAILS honestly on the real tree until the frontend `package-lock.json` is synced to 1.6.0 via npm (see `docs/VERIFICATION_LOG.md`) | `python3 scripts/validate-docs-contract.py` |
| Session counts | **v5 semantics (IF-V4-03):** `/api/v1/lab/counts` `sessions` counts ACTIVE sessions only (live, unexpired, unrevoked); `sessions_total_issued` is the separate process-lifetime total. Measured test outcome: **8/8 passing as part of the parent-verified pytest 340**; parent re-measured expired → len 0 and live counts sessions 2 active of 5 issued | `backend/tests/unit/test_v5_session_counts.py` |
| Evidence atomicity + retention | **v5 semantics (IF-V4-04/11):** repeated saves of a `run_id` atomically replace that run's events (no duplicates); retention is bounded (latest 1000 runs / 20000 events / 1000 live-login events, oldest pruned on save); `storage_budget()` reports counts vs limits. Measured test outcome: **17/17 passing as part of the parent-verified pytest 340**; parent re-measured same run_id saved twice → 1 event, 0 orphans; live DB capped at 1000 runs / 1000 live logins | `backend/tests/unit/test_v5_evidence_store.py` |
| Dockerignore build contexts | **PASS — 82/82** (docs workstream's own run, 2026-11-11): `scripts/test-dockerignore.py` — fake host `node_modules` tree excluded, 99 shipped screenshots excluded, spec files + src + lockfile kept; real frontend context 51 files kept (0.4 MiB) / 6812 excluded (158.3 MiB). Actual `docker build` transfer inspection **NOT RUN** (no Docker) | `python3 scripts/test-dockerignore.py` |
| Docker Compose boot + realm import | **NOT RUN** — no Docker in this sandbox. **v8.0.5 (IF-V8-42):** the app images now declare `USER 10001:10001` (dedicated `identityforge` user) and a one-shot `backend-data-prep` service repairs /app/data ownership for fresh AND existing root-owned volumes before the backend starts (fail-closed; static checker `scripts/check-docker-nonroot.py` 29/29 PASS + volume-prep stub tests `scripts/test-prepare-data-volume.sh` 42/42 PASS, real SQLite DBs). The Docker runtime proof — image build, Compose boot, in-container `id`, fresh/existing-volume login + persistence + `integrity_check`, in-image healthcheck, containerized E2E — is still NOT RUN here and stays the reviewer's Docker Desktop gate (exact acceptance procedure in `docs/WINDOWS_SETUP.md` §3 and `docs/PENTEST_FINDINGS_AND_REMEDIATIONS.md` IF-V8-42) | Reviewer: `.\scripts\test-all.ps1 -Full -Strict` (Windows) or `./scripts/test-all.sh --full --strict` (Linux/macOS) |
| Real Keycloak login (live gate) | **PASS, host-run — login flow 39/39 checks, 0 failures** (student + officer login, member 200 / officer 403 / officer 200, logout + stale 401, per-transaction binding cookie; `live-gate.py all` runs **101 checks** per run incl. the parallel-login flow and 2 new code-provenance checks; reset sub-gate **66/66**). Full Pass A/B/C counts are in `docs/VERIFICATION_LOG.md` | `python3 scripts/live-gate.py login` (2026-11-11, Keycloak 26.8.2 host process, v5 backend) |
| Real Keycloak login events (Atlas) | **PASS — live events recorded via `/api/v1/live-logins`**; zero secret-like content (DB scan) | `GET /api/v1/live-logins`; see VERIFICATION_LOG |
| Browser E2E (Playwright, real Keycloak) | **PASS — v5 host run 65 passed, 1 skipped** (parent's own run, full suite; portal 8/8 incl. the new discovery-issuer test, edge 8 passed + 1 honest cancel skip, axe 25/25, screenshots 24/24). **v5 (IF-V4-10):** the run now emits `test-results/playwright-report.json` (JSON reporter + `config.metadata.target`/`baseURL`) and the `PLAYWRIGHT_E2E` gate validates it with `scripts/validate-playwright-report.py` instead of trusting the exit code — the captured live report validates PASS (65 passed, 1 allowed skip, target `host-lab`). The screenshots run (24 specs in v5) overwrites the same report file, so the E2E report is validated BEFORE the screenshots run; the screenshots report validates with `--profile screenshots` | `cd frontend && npm run test:e2e` (lab running, 2026-11-11, live v5 stack); `python3 scripts/validate-playwright-report.py --report frontend/test-results/playwright-report.json --target host-lab` |
| Playwright JSON validator (IF-V4-10) | **PASS — 12/12 self-test scenarios** (WS2, 2026-11-11): full E2E report passes; an extra skip, a report without the real-login tests, a wrong-target report, a missing/stale/malformed report, and a failed discovery test all FAIL; screenshots profile passes 24/24 and fails on one skip. The validator also passes on the captured live report (see Browser E2E row). Wired into both runners: the `PLAYWRIGHT_E2E` gate requires the run AND the validator; `RESPONSIVE_QA` requires the screenshots run AND the `--profile screenshots` validation. The container path is proven by the ps1 preflight (stub + real validator); the real Docker E2E path is NOT RUN here | `python3 scripts/test-validate-playwright-report.py` |
| Responsive screenshots (6 viewports) | **PASS — 24/24 in v5** (WS3, live host stack, 2026-11-11); **100 PNGs** at 320/390/768/1280/1440/1920 (99 v4 + new `state-overview-wrong-issuer.png`) with programmatic overflow assertions | `cd frontend && npm run test:screenshots` |
| Accessibility (axe) | **PASS — 25/25 tests, 0 violations at ANY impact level** (zero-tolerance contract; 3 new scans in v4: Settings identity-unknown, Overview error-with-retry, Atlas keyboard traversal) | `cd frontend && npx playwright test e2e/a11y.spec.ts` |
| pip-audit | **PASS — no known vulnerabilities** | `python -m pip_audit -r backend/requirements-freeze.txt` |
| npm audit | **NOT RUN** — the sandbox proxy blocks the audit endpoint (403 `policy_denied` on `/-/npm/v1/security/audits/quick`, verified 2026-11-11). Fallback: GitHub Advisory Database direct-dependency check (`scripts/npm-advisory-check.py`) — result in VERIFICATION_LOG. Never read as "zero vulnerable dependencies". **v5 (IF-V4-09):** the runners now classify `npm audit --json` with `scripts/npm-audit-classify.py` (CLEAN / VULNERABILITIES_FOUND / NOT RUN:BLOCKED|DNS|TIMEOUT|RATE_LIMIT|OFFLINE / CHECK_FAILED, exit 0/1/2/3) instead of pattern-matching stderr; a blocked endpoint is NOT RUN, and strict mode fails closed on it. The auditor version is pinned separately in `backend/requirements-audit.txt` (pip-audit 2.10.1) | Reviewer: `cd frontend && npm audit --audit-level=high --json` then `python3 ../scripts/npm-audit-classify.py --stdout ../test-results/audit-frontend.json` |
| npm audit fallback (GHSA, v5) | **PASS — 14/14 direct deps, 0 affecting advisories, 0 high/critical, checked 2026-11-11T21:07:31Z** (parent's final offline run; lockfile-resolved pins; direct-only, transitive advisories still require `npm audit`). When the full audit executes, GHSA is NOT APPLICABLE (v4, P1-05) — it did not run and must never be marked PASS. | `python3 scripts/npm-advisory-check.py` |
| doctor.sh / doctor.ps1 identity checks | **PASS + NEGATIVE-TESTED — 8/8** — dummy HTTP 200 on 5173 → Frontend FAIL, exit 1; dummy wrong-issuer discovery JSON on 8080 → Keycloak FAIL, exit 1; issuer mismatch alone (reachable) → NOT READY | `./scripts/test-doctor.sh` (2026-11-11; in a network namespace — on the host with the lab running it SKIPped honestly because the real stack holds the ports) |
| Dependency gates | **PASS — 55/55 assertions** (WS2, 2026-11-11; was 33/33 in v4): `test-dependency-gates.sh` now drives JSON audit reports through the classifier (clean / low-only / vuln / blocked-E403 / DNS / malformed / rate-limit / offline / timeout) plus pip-audit garbage-output and rc=2 cases, and asserts `test-results/audit-tools.json` contents. Tool install/version is a separate measured step before each scan | `./scripts/test-dependency-gates.sh` (2026-11-11) |
| Gate strictness (negative test) | **PASS — 9/9** (WS2, 2026-11-11; was 7/7 in v4) — `--offline --strict` passes; `verify-release --strict` fails on a missing file; `verify-release` passes on a fresh packaged tree; blocked npm audit + clean GHSA fallback still FAILS strict (NPM_FULL NOT RUN, GHSA PASS); transitive-only advisory FAILS NPM_FULL (not masked by GHSA); unknown npm error (rc=2) → NPM_FULL NOT RUN with `rc=2` in the detail; malformed npm audit JSON → NOT RUN CHECK_FAILED and strict fails; `verify-release --strict` fails when the Compose healthcheck `$$resp` is reverted to `$resp` in a copied tree | `./scripts/test-gate-strictness.sh` |
| CI workflow (GitHub Actions) | **NOT RUN** — no GitHub Actions in this sandbox. Workflow validated by reading + YAML parse; its e2e lane runs the same `test-all.sh --full --strict` executed locally. **v5:** new `scripts` lane (14 steps: syntax gate, strictness, dependency gates, dockerignore, Compose healthcheck static part, port preflight, doctor, live-gate host-map, Playwright validator self-test, ps1 native + ps1 preflight with PowerShell installed on the runner); backend lane pins pip-audit via `backend/requirements-audit.txt`; e2e artifact paths fixed (`frontend/test-results/` carries the Playwright JSON report). **v8.0.4:** scripts lane 25 steps (version fixtures + ps1 selection regression, stub/offline-only). **v8.0.5 (IF-V8-43):** all 11 `uses:` lines pinned to upstream-verified full SHAs with `# vX.Y.Z` comments (checkout v4.4.0 `11d5960a…`, setup-python v5.6.0 `a26af69b…`, setup-node v4.4.0 `49933ea5…`, upload-artifact v4.6.2 `ea165f8d…`); new scripts-lane step `Action SHA pins (IF-V8-43, v8.0.5)` running `scripts/test-action-pins.sh` (8/0 positive, 6/6 defects rejected in the negative control) — lane now **26 steps**. Hosted Actions execution of the pinned workflow is NOT RUN; the reviewer's test-branch/run steps are in `docs/ACTION_SHA_PINS.md` | `.github/workflows/ci.yml` |
| Windows PowerShell execution (`test-all.ps1`) | **PARTIAL — PowerShell 7.4.6 executed in the build sandbox (on Linux; `~/workspace/.pwsh/pwsh`). v5 (IF-V4-08): `scripts/test-ps1-preflight.sh` 20 passed, 0 failed, 1 skipped (the skip is the ports-free cold-start path, which needs a real daemon); `scripts/test-ps1-native.sh` 22 PowerShell checks + 3 bash checks, all passing (parent's own re-run). All native calls now go through `scripts/native-invoke.ps1` (Start-Process, separate stdout/stderr files, exit code from the process object); a log-path regression found by the preflight (relative log paths resolved against the .NET process cwd instead of the session location, so logs leaked into the launch directory) is fixed and covered by a new case-18 regression test. Windows PowerShell 5.1 execution remains NOT RUN** (5.1 is Windows-only) | Reviewer: `.\scripts\test-all.ps1 -Full -Strict` (see REVIEWER_GUIDE §7 for the 5.1 AND 7 command list) |
| Keycloak healthcheck in-image validation | **NOT RUN** — no Docker in this sandbox (bash//dev/tcp/grep inside the `keycloak:26.8.2` image unproven). **v5 (IF-V4-01): SOURCE FIXED** — the Compose `test:` value now writes `$$resp` (Compose escape for a literal dollar); the static regression (`compose-config-check.py`, measured PASS) and the resolved-command check (`test-compose-healthcheck.sh`, static part measured 2026-11-11: 1 passed, 0 failed, 3 NOT RUN — the Docker half needs a daemon) guard it, but no container has run it yet | Reviewer: `bash scripts/test-compose-healthcheck.sh --with-docker` (see REVIEWER_GUIDE §7) |
| Keycloak image tag `26.8.2` exists | **Verified** 2026-11-10 via official Keycloak sources (released 2026-11-05) | See `docker-compose.yml` comment |
| No `0.0.0.0` bindings in Compose | **Verified** (`grep` + `verify-release.sh` check) | `grep 0.0.0.0 docker-compose.yml` (no matches) |
| No secrets in the release tree | **Verified** by `verify-release.sh` checks (run on the extracted archive) | `./scripts/verify-release.sh` |

No test counts, hashes, or pass totals are stated in this file unless they
were actually measured and recorded by the agent that ran them. The release
manifest (`docs/RELEASE_MANIFEST.md`) is the place where measured numbers
are collected.

## 3. What this tool does NOT test

- Real identity providers (Google, Microsoft, GitHub, university IdPs,
  banks). The lab never connects to them.
- Real users, real credentials, or production federation.
- Keycloak itself as a product (its CVEs, its clustering, its database).
  The lab *uses* Keycloak and *observes* its behaviour; it does not audit it.
- TLS/HTTPS deployment, production hardening, or remote exposure.
- SAML, native/mobile flows, implicit/hybrid flows, resource-owner-password
  grant, device flow, or token exchange.
- Phishing, social engineering, or host/OS compromise.
- Full RFC compliance. The lab implements a deliberate subset — see
  `docs/STANDARDS_TRACEABILITY.md` for the exact scope and limits.
- Performance, load, or availability under attack. The lab bounds
  concurrency and input sizes, but it is not a load-testing tool.

## 4. Known limitations of the lab design

1. **Local HTTP only.** Cookies and codes travel over plain HTTP on
   loopback. Safe on your own machine; unsafe on any shared network.
   HTTPS is required for any non-localhost use (see `SECURITY.md`).
2. **Keycloak 26.8.2 pin.** The 26.8 line is the actively supported
   Keycloak line at this release (26.8.2 released 2026-11-05). The pin
   is chosen for reproducibility; reviewers should still check current
   Keycloak advisories before a long-lived deployment.
3. **Two synthetic users, two roles.** `student_01` (member) and
   `officer_01` (member + officer). No groups, no multi-tenancy, no
   fine-grained permissions beyond the two roles.
4. **Single issuer, single redirect URI.** Multi-issuer and multi-redirect
   behaviour is not implemented.
5. **Offline fixtures are not Keycloak.** A fixture result proves the
   validator logic; it does not prove Keycloak behaved the same way.
   The two are labelled differently everywhere (`LIVE_KEYCLOAK` vs
   `OFFLINE_FIXTURE`) and must never be confused.
6. **Keycloak-enforced controls are observed, not owned.** Code
   single-use, exact redirect matching at the authorization server, and
   PKCE enforcement at the token endpoint are Keycloak behaviours. If
   Keycloak's behaviour changed, only the integration lane would catch
   it. Measured 2026-11-11: a failed PKCE exchange BURNS the
   authorization code — a second exchange returns 400 `invalid_grant`
   ("Code not valid"). Test drivers must use a disposable transaction
   for wrong-verifier probes.
7. **Clock sensitivity.** Token expiry checks use bounded clock skew. A
   badly skewed reviewer clock causes false rejections; check the system
   clock if logins fail with expiry errors.
8. **Synthetic credentials in the archive.** Anyone with the release archive
   can sign in as the synthetic users. That is by design for a lab — and
   exactly why the lab must stay on loopback.
9. **Browser E2E depends on a real browser + a running lab.** On a machine
   without them, the offline suite is the fallback and the E2E gates stay
   NOT RUN.
10. **Reset is officer-gated (v3, P0-01).** Reset requires a
    logged-in officer session + CSRF + `{"confirm": "RESET_LAB"}`.
    The v2 "unprivileged on loopback" description is withdrawn: a
    CSRF token alone can no longer authorize a reset, and the
    operator's own session is revoked by a successful reset. The lab
    must still not be shared on a multi-user machine — any officer
    session on the machine can reset synthetic lab state.
11. **Ports are fixed.** 8080/8000/5173 cannot be changed via `.env`
    (P1-14, option A). If a port is in use, stop the conflicting
    service; changing a published port would break the issuer identity
    and the login flow.
12. **npm audit cannot run in this sandbox.** The audit endpoint is
    blocked by the sandbox proxy (403). The shipped fallback is a
    GitHub Advisory Database check of direct dependencies only;
    transitive advisories need `npm audit` on a machine with registry
    access. The GHSA fallback is informational and NEVER satisfies
    the full audit gate — a blocked audit plus a clean GHSA fallback
    still FAILS strict mode (verified by `test-gate-strictness.sh`
    7/7). When the full audit executes, GHSA is NOT APPLICABLE (v4,
    P1-05). The last completed live GHSA result is the v4 one (14/14
    direct deps, 0 advisories, 08:23:25 UTC 2026-11-11).
13. **Forced-colours screenshots are not high-contrast proof.** The
    headless shell used for Playwright screenshots did not visibly
    restyle the page under forced colours, so those shots are not
    claimed as high-contrast evidence; axe contrast ratios pass
    instead (see `docs/UI_DESIGN_SYSTEM.md` §9).
14. **JWKS blocker — found and fixed in v3 (P1-07).** The v3 JWKS
    hardening initially rejected Keycloak's RSA-OAEP encryption key
    and broke every real login (`/?error=JWKS_ERROR`). Fixed
    2026-11-11: non-signing keys are skipped, malformed signing keys
    still fail closed; live-gate login 37/37 PASS after the fix.
    Kept here as a resolved finding so the failure mode is not
    reintroduced by a future hardening pass.
15. **JWKS transport breaker — found and fixed in v4 (P0-01).** The
    v3 code rewrote the canonical JWKS URL to the Compose transport
    base (`http://keycloak:8080`) and then called the bare
    `fetch_jwks`, whose SSRF guard rejects non-loopback hosts — so
    the shipped Docker backend would have failed every login at
    JWKS retrieval while the host-process path passed. Fixed
    2026-11-11: all backchannel fetches go through
    provenance-carrying functions (`fetch_jwks_via_transport`,
    `post_token_via_transport`, `fetch_discovery_via_transport`)
    that validate the canonical URL before the rewrite, validate
    the configured transport base, and re-validate the rewritten
    URL narrowly. The bare validators still reject `keycloak:8080`.
    Docker Compose E2E remains NOT RUN here, so the in-container
    proof is the reviewer's gate (`docker compose up -d --build &&
    python3 scripts/live-gate.py login`).

## 5. How to update this file

When a gate runs, the person who ran it adds a dated row to §2 with the
command, the environment, and the result (including failures). A failed
gate is a defect to fix, not a line to delete. Never edit a NOT RUN entry
to PASS without running the command.
