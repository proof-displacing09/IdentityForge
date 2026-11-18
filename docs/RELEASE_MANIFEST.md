# Release Manifest — IdentityForge

> Completed from the **actual** extracted archive and the real test runs
> recorded in `docs/VERIFICATION_LOG.md`. Every measured row below was
> executed; gates that could not run in the build sandbox are marked
> **NOT RUN** with the reason and the exact reviewer command — never
> filled in in advance.
>
> Historical build-environment note (v7.1): every "no Docker
> binary/socket in this sandbox" statement in this manifest describes
> the 2026-11-11/12 build sandbox only — never the end user's runtime
> state. It is kept in this manifest and in `docs/VERIFICATION_LOG.md`
> only, with this label.

## Release

- **Release name:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V2_20261111.zip`
- **Version:** 1.2.0 (Operation Trustline v2 — second-release remediation + Trustline Atelier redesign)
- **Date:** 2026-11-11 (ISO 8601)
- **Built from:** unversioned working tree at `~/workspace/identityforge-v2`
  (no git repository was used for this build; no commit SHA exists)
- **Built by:** Linux sandbox, Python 3.12.3, Node 24.22.1, npm 10.9.4.
  **No Docker binary or socket exists in this sandbox** — the shipped
  `docker compose up` path is NOT RUN here (see below).

## Archive

- **Filename:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V2_20261111.zip`
- **Size (bytes) and SHA-256:** not printed inside the archive — either
  value is a property of the ZIP file itself, so printing it here would
  change it. Check the delivery message for the SHA-256 of the shipped
  file, and verify with `ls -l` / `sha256sum <archive>` on Linux/macOS
  or `Get-FileHash <archive> -Algorithm SHA256` on Windows.
- **File count:** **188** (verified from the shipped ZIP's namelist;
  includes 50 Atelier screenshots in `frontend/e2e/screenshots/`)
- **Archive verified by:** extraction to two fresh directories followed
  by `./scripts/verify-release.sh` and the offline gates — see
  `docs/VERIFICATION_LOG.md`, Operation Trustline v2 Pass C.

## Contents

| Area | Notes |
|---|---|
| Backend (`backend/src`, `backend/tests`) | src modules + tests; CSRF lifecycle, live-login events, v2 scenario semantics, omit-mechanism mutation-sensitivity tests |
| Frontend (`frontend/src`, `frontend/e2e`) | Trustline Atelier redesign (12 views), Vitest tests, Playwright specs (portal / edge / a11y / screenshots), 50 screenshots in `e2e/screenshots/` |
| Keycloak realm import | `keycloak/realm-import/identityforge-lab-realm.json` (pinned subject UUIDs, no `dockerFlow`) |
| Docs (`docs/`) | + REMEDIATION_FINDINGS, REMEDIATION_TRACEABILITY, KEYCLOAK_INTEGRATION, UI_DESIGN_SYSTEM (Atelier), VERIFICATION_LOG (v2 Pass A/B/C) |
| Scripts (`scripts/`) | setup, start, stop, reset (+ `reset.ps1`), test-all (12 gates), doctor (+ `doctor.ps1`), verify-release, live-gate.py, compose-config-check.py, npm-advisory-check.py, test-gate-strictness.sh (+ PowerShell wrappers) |
| Root files | README, SECURITY, LICENSE, .env.example, .gitignore, docker-compose.yml (ports locked, 127.0.0.1 only) |
| CI | `.github/workflows/ci.yml` (backend lane with pip-audit + editable install; frontend lane with npm audit; keycloak-e2e lane runs `test-all.sh --full --strict`) |
| Example reports | REPORT_TEMPLATE.json + README + executed-2026-11-09/verify-all.json + executed-2026-11-11/verify-all.json |

## Test results at release time

One row per gate, with the command, environment, date, and result —
taken from the actual runs in `docs/VERIFICATION_LOG.md`, never from
memory.

| Gate | Command | Environment | Date | Result |
|---|---|---|---|---|
| Backend offline (pytest) | `cd backend && .venv/bin/python -m pytest -q` | Linux sandbox, Python 3.12.3 | 2026-11-11 | **PASS — 130 passed, 0 failed, 21.40 s** |
| Backend lint/format | `ruff check src tests` / `ruff format --check src tests` | Linux sandbox | 2026-11-11 | **PASS — clean** |
| Backend scenario CLI | `python -m identityforge.cli verify-all` | Linux sandbox, Python 3.12.3 | 2026-11-11 | **PASS — 18/18** |
| Frontend typecheck/tests/build | `cd frontend && npm run typecheck && npm test -- --run && npm run build` | Linux sandbox, Node 24.22.1 | 2026-11-11 | **PASS — tsc ok, Vitest 38/38, build ok (JS 236.69 kB, 72.06 kB gzip)** |
| Browser E2E (Playwright) | `cd frontend && npx playwright test` | Linux sandbox, Playwright 1.65.0 + Chrome-for-Testing 158.0.8127.18 headless shell (sandbox workaround — the Microsoft download gateway 400s from this sandbox; see VERIFICATION_LOG) | 2026-11-11 | **PASS — 24 passed, 1 skipped** (portal 7/7, edge 6/6, axe 6/6, screenshots 5/5) |
| Accessibility (axe) | `e2e/a11y.spec.ts` | Same as above | 2026-11-11 | **PASS — 6/6 scans, 0 violations** (6 violations found and fixed first) |
| Screenshots / responsive | `npm run test:screenshots` | Same as above | 2026-11-11 | **PASS — 5/5; 50 PNGs at 320/390/768/1440/1920**, 2 real defects found and fixed |
| Live Keycloak gate | `python3 scripts/live-gate.py all` (×3) | Linux sandbox, Keycloak 26.8.2 host process, Temurin JRE 21.0.13 | 2026-11-11 | **PASS — 80 checks each, 3 runs** (student+officer login, role probes, logout+stale 401, binding+replay, K2 wrong PKCE, K3 unregistered redirect); 152 redacted live events across 20 logins |
| Compose config | `python3 scripts/compose-config-check.py` (YAML-only — no Docker CLI) | Linux sandbox | 2026-11-11 | **PASS** — ports locked to 127.0.0.1:8080/8000/5173, Keycloak image pinned 26.8.2. The real `docker compose config -q` is NOT RUN here |
| Compose boot (Docker) | `docker compose up` | — | — | **NOT RUN** — no Docker binary/socket in this sandbox. Reviewer gate on Docker Desktop |
| pip-audit | `python -m pip_audit -r backend/requirements-freeze.txt` | Linux sandbox | 2026-11-11 | **PASS — 0 vulnerable project deps** |
| npm audit | `npm audit --audit-level=high` | Linux sandbox | 2026-11-11 | **NOT RUN** — registry proxy 403 `policy_denied` on the audit endpoint |
| npm audit fallback (GHSA) | `python3 scripts/npm-advisory-check.py` | Linux sandbox | 2026-11-11 | **CLEAN — 14/14 direct packages, 0 affecting advisories at any severity, 0 at high/critical** (retry #2, 03:08:26 UTC, rc=0). Direct deps only; transitive advisories need `npm audit` on a machine with registry access |
| Gate strictness | `./scripts/test-gate-strictness.sh` | Linux sandbox | 2026-11-11 | **PASS — 4/4** (2026-11-11 03:10:38 UTC) |
| Mutation test (source-level) | — | — | 2026-11-11 | **NOT RUN by design** — source-level mutation is not attempted (see SECURITY_ASSESSMENT §2). Mutation *sensitivity* via the designed `omit` mechanism: PASS (secure rejects / omit-one-check accepts, 9 checks) |

## Example reports included

- `example-reports/REPORT_TEMPLATE.json` — **template only**, clearly
  labelled; not an executed result.
- `example-reports/executed-2026-11-09/verify-all.json` — **executed
  2026-11-09** against the running backend: 18/18 runs,
  mode `DETERMINISTIC OFFLINE FIXTURE`, Keycloak NOT RUN. Redacted
  evidence only; no tokens, codes or verifiers.
- `example-reports/executed-2026-11-11/verify-all.json` — **executed
  2026-11-11** (v2 engine, `run_all(store=None)`): 18/18 runs, all
  PASS, provenance EPHEMERAL / `evidence_saved=false` (the file
  itself is the artifact), per-scenario session fields matching
  `docs/SCENARIO_METHOD.md` §9. Secret scan clean.

## Excluded from the archive (verified by `verify-release.sh`)

`.git/`, virtual environments, `node_modules/`, `frontend/dist/`,
build caches, coverage reports, `test-results/`, runtime SQLite
databases (`backend/data/`), log archives, auth cookies, `.env`,
local secret files, temporary Keycloak state, container volumes,
downloaded Docker images, private signing keys, personal data,
`*.egg-info`, `*.zip` files, `Zone.Identifier` files.

---

## Operation Trustline v3 — third-release remediation (2026-11-11)

> Every row below is filled from the FINAL packaged ZIP's namelist
> and the actual Pass A/B/C runs in `docs/VERIFICATION_LOG.md`
> (v3 section) — never from memory, and never in advance.

- **Release name:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V3_FINAL_20261111.zip`
- **Version:** 1.3.0 (Operation Trustline v3 — third-release
  remediation + Atelier v3 redesign)
- **Date:** 2026-11-11 (ISO 8601)
- **Built from:** working tree at `~/workspace/identityforge-v3`
  (no git repository was used for this build; no commit SHA exists)
- **Built by:** Linux sandbox, Python 3.12.3, Node 24.22.1, npm 10.9.4.
  **No Docker binary or socket exists in this sandbox** — the shipped
  `docker compose up` path is NOT RUN here (see below).

### Archive (file count verified from the final ZIP's namelist; size/SHA-256 in the delivery message)

- **Filename:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V3_FINAL_20261111.zip`
- **Size (bytes) and SHA-256:** not printed inside the archive — either
  value is a property of the ZIP file itself, so printing it here would
  change it. Check the delivery message for the SHA-256 of the shipped
  file, and verify with `ls -l` / `sha256sum <archive>` on Linux/macOS
  or `Get-FileHash <archive> -Algorithm SHA256` on Windows.
- **File count:** **254** (verified from the shipped ZIP's namelist;
  includes 97 Atelier v3 screenshots in `frontend/e2e/screenshots/`)
- **Archive verified by:** extraction to two fresh directories followed
  by `./scripts/verify-release.sh` and the offline gates — see
  `docs/VERIFICATION_LOG.md`, Operation Trustline v3 Pass C.

### Contents (v3 changes vs v2)

| Area | Notes |
|---|---|
| Backend (`backend/src`, `backend/tests`) | Officer-only reset + `lab/counts`; validator separation (`validators_flawed.py` offline-only); policy = two pinned UUIDs; JWKS hardening + non-signing-key skip; strict audience policy; `lab/status.evidence`; per-transaction cookies; transport rewrite guard; 246 pytest |
| Frontend (`frontend/src`, `frontend/e2e`) | Atelier v3 redesign (12 views), reset UI with operator identity + counts, lazy loading (165.18 kB), Vitest 54, Playwright specs (portal / edge / a11y / screenshots), **97 fresh v3 screenshots** in `e2e/screenshots/` |
| Keycloak realm import | `keycloak/realm-import/identityforge-lab-realm.json` (pinned subject UUIDs, no `dockerFlow`) |
| Docs (`docs/`) | + v3 sections in REMEDIATION_FINDINGS, REMEDIATION_TRACEABILITY, KEYCLOAK_INTEGRATION, UI_DESIGN_SYSTEM, VERIFICATION_LOG; WINDOWS_SETUP P1-14 precision; REVIEWER_GUIDE 8-step path + reviewer gates §7 |
| Scripts (`scripts/`) | setup, start, stop, reset (+ `reset.ps1`), test-all (14 gates) + **test-all.ps1 (409 lines)**, doctor (+ `doctor.ps1`, `--brief`), verify-release, live-gate.py (parallel flow + host-map seam), compose-config-check.py, npm-advisory-check.py, audit-gates.sh, test-gate-strictness.sh (+ PowerShell wrappers) |
| Root files | README, SECURITY, LICENSE, .env.example, .gitignore, docker-compose.yml (keycloak:8080 transport, no `container_name:`, ports locked, 127.0.0.1 only), docker-compose.test.yml |
| CI | `.github/workflows/ci.yml` (backend lane with pip-audit + editable install; frontend lane with npm audit; GHSA step split out, informational; keycloak-e2e lane runs `test-all.sh --full --strict`) |
| Example reports | REPORT_TEMPLATE.json + README + executed-2026-11-09/verify-all.json + executed-2026-11-11/verify-all.json |

### Test results at release time (Pass A/B/C)

One row per gate, with the command, environment, date, and result —
taken from the actual runs in `docs/VERIFICATION_LOG.md`, never from
memory:

| Gate | Result (Pass A/B/C, 2026-11-11) |
|---|---|
| Backend offline (pytest) | **246 passed, 0 failed** (tree runs + 246 in both clean extractions) |
| Backend lint/format | **PASS — clean (51 files)** |
| Backend scenario CLI | **PASS — 18/18** (tree + both clean extractions) |
| Frontend typecheck/tests/build | **PASS — tsc ok, Vitest 54/54, build ok (JS 165.18 kB, 53.73 kB gzip)** (tree + both clean extractions) |
| Browser E2E (Playwright) | **PASS — 56 passed, 1 skipped** (portal 7/7, edge 7/7 + 1 honest skip, axe 22/22, screenshots 20/20) |
| Accessibility (axe) | **PASS — 22/22 tests, 0 violations at any impact level** |
| Screenshots / responsive | **PASS — 20/20; 97 PNGs, all fresh v3, at 6 widths** |
| Live Keycloak gate (`live-gate.py all` ×4) | **PASS — 99/99 checks ×4, 0 failures** (login 37/37 also run separately after the JWKS fix) |
| Dependency gates | **PASS — 33/33 assertions** |
| Doctor | **PASS — 8/8** |
| Gate strictness | **PASS — 6/6** (strict mode fails closed: 2 required NOT RUN gates fail the run) |
| pip-audit | **PASS — 0 vulnerable project deps** |
| npm audit | **NOT RUN** — registry proxy 403 `policy_denied` |
| npm audit fallback (GHSA, v3) | **PASS — 14/14 direct deps, 0 affecting advisories, 0 high/critical, checked 2026-11-11T06:04:31Z** (direct-only; transitive advisories still require `npm audit`) |
| verify-release (clean extraction 1, plain path) | **16 PASS / 0 FAIL / 5 NOT RUN** (NOT RUN: system pytest/pip-audit absent, no Docker, npm audit blocked, GHSA rate-limited at that moment) |
| verify-release (clean extraction 2, path with spaces) | **17 PASS / 0 FAIL / 4 NOT RUN** (GHSA PASS after quota recovery) |
| Compose boot (Docker) | **NOT RUN** — no Docker binary/socket in this sandbox. Reviewer gate on Docker Desktop |
| Windows PowerShell execution | **NOT RUN** — no PowerShell in this sandbox. Reviewer gate |
| Keycloak healthcheck in-image validation | **NOT RUN** — no Docker in this sandbox. Reviewer gate |
| Mutation test (source-level) | **NOT RUN by design** — sensitivity via the designed `omit` mechanism: PASS |

---

## Operation Trustline v4 — fourth-release remediation (2026-11-11)

> Every row below is filled from the workstream-verified runs in
> `docs/VERIFICATION_LOG.md` (v4 section) — never from memory, and
> never in advance. The file count is from the current v4 tree using
> `scripts/package-zip.py`'s exclusion list; the parent confirms it
> against the FINAL ZIP's namelist before delivery (Pass A/B/C).

- **Release name:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V4_FINAL_20261111.zip`
- **Version:** 1.4.0 (Operation Trustline v4 — fourth-release
  remediation + Atelier v4 premium finish)
- **Date:** 2026-11-11 (ISO 8601)
- **Built from:** working tree at `~/workspace/identityforge-v4`
  (no git repository was used for this build; no commit SHA exists)
- **Built by:** Linux sandbox, Python 3.12.3, Node 24.22.1, npm 10.9.4.
  **No Docker binary or socket exists in this sandbox** — the shipped
  `docker compose up` path is NOT RUN here (see below). PowerShell
  7.4.6 on Linux (`~/workspace/.pwsh/pwsh`) WAS executed here;
  Windows PowerShell 5.1 was NOT.

### Archive (file count from the tree; size/SHA-256 in the delivery message)

- **Filename:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V4_FINAL_20261111.zip`
- **Size (bytes) and SHA-256:** not printed inside the archive — either
  value is a property of the ZIP file itself, so printing it here would
  change it. Check the delivery message for the SHA-256 of the shipped
  file, and verify with `ls -l` / `sha256sum <archive>` on Linux/macOS
  or `Get-FileHash <archive> -Algorithm SHA256` on Windows.
- **File count:** **265** (counted from the v4 tree with
  `scripts/package-zip.py`'s exclusion list — v3 was 254; +11: 4 new
  backend test files, 3 new script test/matrix files,
  `FlowInspector.test.tsx`, and 2 net new screenshots; includes 99
  Atelier v4 screenshots in `frontend/e2e/screenshots/`). To be
  confirmed against the FINAL ZIP's namelist in Pass A/B/C.
- **Archive verified by:** extraction to two fresh directories followed
  by `./scripts/verify-release.sh` and the offline gates — see
  `docs/VERIFICATION_LOG.md`, Operation Trustline v4 Pass A/B/C
  (COMPLETE 2026-11-11; FINAL ZIP namelist confirmed 265 files).

### Contents (v4 changes vs v3)

| Area | Notes |
|---|---|
| Backend (`backend/src`, `backend/tests`) | Provenance transport fetch (`fetch_jwks_via_transport`, `post_token_via_transport`, `fetch_discovery_via_transport`); bounded ASGI body (1,048,576 inclusive); per-browser transaction cap 4 + global cap 20 + `/auth/login` rate limit + `identityforge_browser` cookie; evidence store transactions + 1000-event retention; 304 pytest (58 new tests) |
| Frontend (`frontend/src`, `frontend/e2e`) | Atelier v4 premium finish (12 views), Identity Transaction Atlas (7 stages, recorded events only), settled screenshots (`waitSettled()`), Settings error truthfulness + ModeBadge correction, lazy loading (165.14 kB), Vitest 64, Playwright specs (portal / edge / a11y / screenshots), **99 fresh v4 screenshots** in `e2e/screenshots/` |
| Keycloak realm import | `keycloak/realm-import/identityforge-lab-realm.json` (pinned subject UUIDs, no `dockerFlow`) |
| Docs (`docs/`) | + v4 sections in REMEDIATION_FINDINGS, REMEDIATION_TRACEABILITY, KEYCLOAK_INTEGRATION, UI_DESIGN_SYSTEM, VERIFICATION_LOG, RELEASE_MANIFEST; WSL `--no-distribution` precision; REVIEWER_GUIDE stop-first workflow + §7 rewrite (15 gates, pwsh 7.4.6 executed / 5.1 NOT RUN, GHSA NOT APPLICABLE, healthcheck probe) |
| Scripts (`scripts/`) | setup, start, stop, reset (+ `reset.ps1`), test-all (**15 gates**, incl. new REAL_LAB_RESET) + **test-all.ps1 (528 lines)**, doctor (+ `doctor.ps1`, `--brief`), verify-release (GHSA NOT APPLICABLE + NO_INTERNAL_ISSUER allowlist), live-gate.py (parallel flow + host-map adapter + `reset` sub-gate), compose-config-check.py, npm-advisory-check.py, audit-gates.sh, test-gate-strictness.sh (7 steps), test-live-gate-hostmap.py, test-port-preflight.sh, test-ps1-preflight.sh, test-matrix.md (+ PowerShell wrappers) |
| Root files | README, SECURITY, LICENSE, .env.example, .gitignore, docker-compose.yml (keycloak:8080 transport, no `container_name:`, ports locked, 127.0.0.1 only), docker-compose.test.yml |
| CI | `.github/workflows/ci.yml` (backend lane with pip-audit + editable install; frontend lane with npm audit; GHSA step split out, informational; keycloak-e2e lane runs `test-all.sh --full --strict`) |
| Example reports | REPORT_TEMPLATE.json + README + executed-2026-11-09/verify-all.json + executed-2026-11-11/verify-all.json |

### Test results at release time (workstream-verified + Pass A/B/C COMPLETE 2026-11-11)

One row per gate, with the command, environment, date, and result —
taken from the actual runs in `docs/VERIFICATION_LOG.md`, never from
memory:

| Gate | Result (workstream verification, 2026-11-11) |
|---|---|
| Backend offline (pytest) | **304 passed, 0 failed** (246 v3 + 58 new) |
| Backend lint/format | **PASS — clean (55 files)** |
| Backend scenario CLI | **PASS — 18/18** |
| Frontend typecheck/tests/build | **PASS — tsc ok, Vitest 64/64, build ok (JS 165.14 kB, 53.71 kB gzip, 14 JS assets)** |
| Browser E2E (Playwright) | **PASS — 62 passed, 1 skipped** (portal 7/7, edge 7/7 + 1 honest skip, axe 25/25, screenshots 23/23) |
| Accessibility (axe) | **PASS — 25/25 tests, 0 violations at any impact level** |
| Screenshots / responsive | **PASS — 23/23; 99 PNGs, all fresh v4, at 6 widths** (all 99 inspected) |
| Live Keycloak gate (`live-gate.py all`) | **PASS — 99/99 checks** (unmapped AND with the localhost host map; login 37/37 ×2; reset sub-gate 64/64) |
| Dependency gates | **PASS — 33/33 assertions** |
| Doctor | **PASS — 8/8** (in a network namespace; SKIPped honestly on the host with the lab running) |
| Gate strictness | **PASS — 7/7** (new step 7: unknown npm error rc=2 → NPM_FULL NOT RUN) |
| Port preflight | **PASS — 10/10** |
| ps1 preflight | **PASS — 18/18, 1 skipped** (ports-free cold-start path NOT RUN here, no real Docker) |
| Host-map adapter | **PASS — 21/21** |
| pip-audit | **PASS — 0 vulnerable project deps** (freeze; venv-wide run reports 12 advisories against the venv's own `pip 24.0` tooling only) |
| npm audit | **NOT RUN** — registry proxy 403 `policy_denied` |
| npm audit fallback (GHSA, v4) | **PASS — 14/14 direct deps, 0 affecting advisories, 0 high/critical, checked 2026-11-11T08:23:25Z** (direct-only; transitive advisories still require `npm audit`) |
| verify-release (working tree) | **NO_INTERNAL_ISSUER PASS**; FORBIDDEN_FILES FAIL only because the live runtime DB `backend/data/identityforge.db` is present (excluded from packaging) |
| Compose boot (Docker) | **NOT RUN** — no Docker binary/socket in this sandbox. Reviewer gate on Docker Desktop |
| Windows PowerShell 5.1 execution | **NOT RUN** — 5.1 is Windows-only. PowerShell 7.4.6 on Linux WAS executed (18 checks). Reviewer gate |
| Keycloak healthcheck in-image validation | **NOT RUN** — no Docker in this sandbox. Reviewer gate |
| Mutation test (source-level) | **NOT RUN by design** — sensitivity via the designed `omit` mechanism: PASS |
| Pass A repetition (parent) | **PASS — pytest 304, CLI 18/18, Vitest 64/64, build identical (165.14 kB), pip-audit clean, strictness 7/7, dep-gates 33/33, port-preflight 10/10, ps1-preflight 18/18 + 1 skip, hostmap 21/21, doctor 8/8 (namespace), live gate 99/99 ×4, test-all --offline PASS 7 / NOT RUN 8** |
| Pass B clean extractions | **PASS — candidate ZIP (265 files) extracted to a plain path and a path with spaces; both reproduce pytest 304, CLI 18/18, Vitest 64/64, identical build; verify-release 8 PASS / 0 FAIL / 5 NOT RUN pre-deps, 15 PASS / 1 FAIL (runtime DB only) / 5 NOT RUN post-deps** |

## Operation Trustline v5 — fifth-release remediation (2026-11-11)

> Every row below is filled from the measured runs in
> `docs/VERIFICATION_LOG.md` (v5 section) — never from memory, and
> never in advance. All rows now carry parent-verified values from
> Pass A/B/C; the file count is confirmed against the FINAL ZIP's
> namelist.

- **Release name:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V5_REVIEW_CANDIDATE.zip` (suggested name from the v5 directive; the parent confirms the final filename at packaging)
- **Version:** 1.5.0 (Operation Trustline v5 — fifth-release
  remediation + Atelier v5 premium finish)
- **Date:** 2026-11-11 (ISO 8601)
- **Built from:** working tree at `~/workspace/identityforge-v5`
  (no git repository was used for this build; no commit SHA exists)
- **Built by:** Linux sandbox, Python 3.12.3, Node 24.22.1, npm 10.9.4.
  **No Docker binary or socket exists in this sandbox** — the shipped
  `docker compose up` path is NOT RUN here (see below). PowerShell
  7.4.6 on Linux (`~/workspace/.pwsh/pwsh`) WAS executed here;
  Windows PowerShell 5.1 was NOT.

### Archive (file count from the tree; size/SHA-256 in the delivery message)

- **Filename:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V5_REVIEW_CANDIDATE.zip`
- **Size (bytes) and SHA-256:** not printed inside the archive — either
  value is a property of the ZIP file itself, so printing it here would
  change it. Check the delivery message for the SHA-256 of the shipped
  file, and verify with `ls -l` / `sha256sum <archive>` on Linux/macOS
  or `Get-FileHash <archive> -Algorithm SHA256` on Windows.
- **File count:** **286 files** (confirmed against the FINAL ZIP's namelist; v4 was 265; v5 adds
  `frontend/.dockerignore`, `backend/.dockerignore`,
  `scripts/validate-docs-contract.py`,
  `scripts/test-compose-healthcheck.sh`,
  `scripts/test-dockerignore.py`,
  `scripts/npm-audit-classify.py`, `scripts/native-invoke.ps1`,
  `scripts/validate-playwright-report.py`,
  `scripts/test-live-gate-provenance.py`, new v5 backend tests
  (`test_v5_session_counts.py`, `test_v5_evidence_store.py`,
  `test_v5_bounded_body.py`, `test_v5_backend_api.py`), new frontend
  tests (`Findings.test.tsx`, `Overview.test.tsx`, `Reports.test.tsx`),
  `docs/EVIDENCE_RETENTION.md`, `backend/requirements-audit.txt`,
  and removes nothing). Size/SHA-256 are in the delivery message only
  (printing them here would change the archive they describe).
- **Archive verified by:** extraction to two fresh directories followed
  by `./scripts/verify-release.sh` and the offline gates — see
  `docs/VERIFICATION_LOG.md`, Operation Trustline v5 Pass A/B/C
  (parent-verified: plain path + path-with-spaces extractions, both
  reproducing pytest 340, CLI 18/18, Vitest 92/92, build byte-identical
  `index-DgdhM3ou.js`; verify-release 20 PASS / 0 FAIL / 5 NOT RUN on
  the fresh spaces-path extraction).

### Contents (v5 changes vs v4)

| Area | Notes |
|---|---|
| Backend (`backend/src`, `backend/tests`) | Healthcheck-adjacent: none (the fix is Compose-side). Session counts active-only (`active_count()` / `total_issued` / prune-on-access; `/lab/counts` gains `sessions_total_issued`); evidence atomic replacement on repeated `run_id` + retention caps (1000 runs / 20000 events / 1000 live logins) + `storage_budget()`; ASGI body chunk slicing (at most max + 1 buffered); pytest **340 passed** (parent's own run, incl. 36 new v5 tests) |
| Frontend (`frontend/src`, `frontend/e2e`) | Atelier v5 premium finish (12 views); Overview `Verified` step requires backend ok + IdP reachable + issuer match (IF-V4-05); report provenance labels `SERVER_VERIFIED_ARTIFACT` / `CLIENT_DERIVED_FROM_SERVER_RUN` / `LOCAL_UNSAVED_FALLBACK` (IF-V4-12); Vitest **92/92**, Playwright **65 passed + 1 skipped**, screenshots **100 PNGs** (parent's own runs) |
| Keycloak realm import | `keycloak/realm-import/identityforge-lab-realm.json` (unchanged from v4: pinned subject UUIDs, no `dockerFlow`) |
| Docs (`docs/`) | + v5 sections in REMEDIATION_FINDINGS, REMEDIATION_TRACEABILITY, KEYCLOAK_INTEGRATION, VERIFICATION_LOG, RELEASE_MANIFEST; IF-V4-06 reason-code corrections in AUTH_FLOW / REVIEWER_GUIDE / TEST_MATRIX / SCENARIO_METHOD / API_CONTRACT / REPORT_TEMPLATE + new `scripts/validate-docs-contract.py` (DOCS_CONTRACT gate); REVIEWER_GUIDE §7 healthcheck rewrite (`$$resp`, resolved-config check, SOURCE FIXED label); TEST_MATRIX U27–U30, B5/B7 updates; gate count 15 → 16 (README, REVIEWER_GUIDE, WINDOWS_SETUP) |
| Scripts (`scripts/`) | test-all (**16 gates**, incl. new DOCS_CONTRACT) in `test-all.sh` + `test-all.ps1` (+ docs/scripts mounts in `docker-compose.test.yml` backend-test for the ps1 container run); `compose-config-check.py` (Compose interpolation simulation); `test-compose-healthcheck.sh` (resolved command + live health state); `test-dockerignore.py` (82 checks); `npm-audit-classify.py` + `audit-gates.sh` (IF-V4-09 structured audit classification, `audit-tools.json`); CI backend lane runs the docs-contract check |
| Root files | README, SECURITY, LICENSE, .env.example, .gitignore, docker-compose.yml (Keycloak healthcheck `$$resp`, ports locked, 127.0.0.1 only), docker-compose.test.yml (backend-test mounts docs/scripts/example-reports/README/SECURITY read-only), frontend/.dockerignore, backend/.dockerignore |
| CI | `.github/workflows/ci.yml` (backend lane + docs-contract step; frontend lane with npm audit; GHSA step split out, informational; keycloak-e2e lane runs `test-all.sh --full --strict`) |
| Example reports | REPORT_TEMPLATE.json rewritten to the real `ComparisonResult` shape (`flawed_result`, `timeline`, `decisions`, `WRONG_AUDIENCE`); executed-2026-11-09/verify-all.json + executed-2026-11-11/verify-all.json unchanged (executed evidence) |

### Test results at release time (parent-verified, Pass A/B/C complete)

One row per gate, with the command, environment, date, and result —
taken from the actual runs in `docs/VERIFICATION_LOG.md`, never from
memory:

| Gate | Result (workstream verification, 2026-11-11) |
|---|---|
| Backend offline (pytest) | **340 passed, 2 warnings** (parent's own run, 67.39 s; v4 was 304 passed, 0 failed) |
| Backend lint/format | **ruff check clean; ruff format clean, 59 files** (parent's own run) |
| Backend scenario CLI | **18/18 scenarios PASS** (parent's own run; v4 was 18/18) |
| Docs-contract | **PASS — 34 FailureReason values, 59 report-model fields, 60 files scanned, 0 violations** (docs workstream's own run; pre-fix 35 violations on the v5 tree; 58 violations on the untouched v4 tree) |
| Dockerignore check | **PASS — 82/82** (docs workstream's own run; real frontend context 51 files kept / 6812 excluded; actual `docker build` transfer inspection NOT RUN) |
| Compose-config check | **PASS** (docs workstream's own run; resolved healthcheck keeps literal `$resp` 2×; real `docker compose config` NOT RUN) |
| Frontend typecheck/tests/build | **typecheck PASS; Vitest 92/92 (11 files); build `index-DgdhM3ou.js` 166.43 kB / 54.14 kB gzip** (parent's own run; v4 was tsc ok, Vitest 64/64, build 165.14 kB / 53.71 kB gzip) |
| Browser E2E (Playwright) | **65 passed + 1 skipped, 0 failed** (parent's own run on the live host stack, 66 total; v4 was 62 passed, 1 skipped). Report validator PASSES the real report |
| Accessibility (axe) | **25/25, 0 violations** (parent's own run; v4 was 25/25, 0 violations) |
| Screenshots / responsive | **100 PNGs at 6 widths** (parent's own run; v4 was 23/23, 99 PNGs). Parent inspected the wrong-issuer state and the 390 px Overview personally |
| Live Keycloak gate (`live-gate.py all`) | **101/101 passed** (parent's own run; v4 was 99/99 ×4; login 39/39; reset sub-gate 66/66 after a cap-aware gate fix — see VERIFICATION_LOG). Includes 2 new code-provenance checks per run |
| Dependency gates | **55 passed, 0 failed** (parent's own run; v4 was 33/33) |
| Doctor | **8 passed, 0 failed** (parent's own run in a network namespace; v4 was 8/8 in a namespace; host run honestly SKIPs when the lab occupies the ports) |
| Gate strictness | **9 passed, 0 failed** (parent's own run; v4 was 7/7) |
| Port preflight | **10 passed, 0 failed, 0 skipped** (parent's own run; v4 was 10/10) |
| ps1 preflight | **20 passed, 0 failed, 1 skipped** (parent's own run; v4 was 18/18, 1 skipped; ports-free cold-start path NOT RUN, no real Docker) |
| Host-map adapter | **21 passed, 0 failed** (parent's own run; v4 was 21/21) |
| pip-audit | **Clean — "No known vulnerabilities found"** (pip-audit 2.10.1, parent's own run; v4 was 0 vulnerable project deps) |
| npm audit | **NOT RUN** — registry proxy 403 `policy_denied` |
| npm audit fallback (GHSA, v5) | **14/14 direct deps, 0 high/critical affecting advisories**, checked 2026-11-11T21:07:31Z (fresh GHSA check during the parent's final offline run; v4 was 14/14 direct deps, 0 affecting advisories, checked 2026-11-11T08:23:25Z; direct-only; transitive advisories still require `npm audit`) |
| verify-release (working tree) | **20 PASS / 0 FAIL / 5 NOT RUN** on a fresh FINAL-ZIP extraction (spaces path; parent's own run). The 5 NOT RUN need installed deps/Docker. A verify-release run on a tree where the gates have already run fails FORBIDDEN_FILES on the editable-install `egg-info` + the runtime DB — both are created by running the gates, both are excluded from the ZIP, and the script header requires a fresh extracted copy |
| Compose boot (Docker) | **NOT RUN** — no Docker binary/socket in this sandbox. Reviewer gate on Docker Desktop |
| Windows PowerShell 5.1 execution | **NOT RUN** — 5.1 is Windows-only. PowerShell 7.4.6 on Linux WAS executed (ps1 parse 0 errors; full preflight 20/0/1, ps1-native 22 PowerShell checks + 3 bash checks, all passing). Reviewer gate |
| Keycloak healthcheck in-image validation | **NOT RUN** — no Docker in this sandbox. Source fixed (`$$resp`); reviewer gate |
| Mutation test (source-level) | **NOT RUN by design** — sensitivity via the designed `omit` mechanism: PASS |
| Pass A repetition (parent) | **Done 2026-11-11** — pytest 340, ruff clean, CLI 18/18, typecheck, Vitest 92/92, build, docs-contract PASS, strictness 9/9, dep-gates 55/55, dockerignore 82/82, healthcheck 1/0/3, port 10/10, ps1-preflight 20/0/1, hostmap 21/21, doctor 8/8, ps1-native 22+3, validator 12/12, provenance 2/2, test-all.sh --offline 9 PASS / 0 FAIL / 7 NOT RUN |
| Pass B clean extractions | **Done 2026-11-11** — two fresh extractions of the FINAL ZIP (plain path + path with spaces), both reproducing pytest 340, CLI 18/18, Vitest 92/92, build byte-identical `index-DgdhM3ou.js`; verify-release 20/0/5 on the fresh spaces-path extraction |

## Operation Trustline v6 — sixth-release remediation (2026-11-11)

> Every row below is filled from the measured runs in
> `docs/VERIFICATION_LOG.md` (v6 section) — never from memory, and
> never in advance. All rows are filled at release time (WS2, WS1/WS3
> via the Pass A coordinator, and the parent's own Pass B/C re-runs);
> no v5 figure is copied forward as a v6 result. Status words in
> this section are exactly PASS / FAIL / NOT RUN / NOT APPLICABLE
> (v6, IF-V5-10): NOT RUN means the gate did not execute and is never
> a pass, never "skipped", and never interchangeable with NOT
> APPLICABLE (superseded by a covering gate) or FAIL. "Skipped" is a
> suite-internal word for an individual check inside a suite and is
> never a gate status.

- **Release name:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V6_REVIEW_CANDIDATE.zip` (suggested name from the v6 directive; the parent confirms the final filename at packaging)
- **Version:** 1.6.0 (Operation Trustline v6 — sixth-release
  remediation + Atelier v6 premium finish)
- **Date:** 2026-11-11 (ISO 8601)
- **Built from:** working tree at `~/workspace/identityforge-v6`
  (no git repository was used for this build; no commit SHA exists)
- **Built by:** Linux sandbox, Python 3.12.3, Node 24.22.1, npm 10.9.4.
  **No Docker binary or socket exists in this sandbox** — the shipped
  `docker compose up` path is NOT RUN here (see below). PowerShell
  7.4.6 on Linux (`~/workspace/.pwsh/pwsh`) WAS executed here;
  Windows PowerShell 5.1 was NOT.

### Archive (file count from the tree; size/SHA-256 in the delivery message)

- **Filename:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V6_FINAL_20261111.zip`
- **Size (bytes) and SHA-256:** not printed inside the archive — either
  value is a property of the ZIP file itself, so printing it here would
  change it. Check the delivery message for the SHA-256 of the shipped
  file, and verify with `ls -l` / `sha256sum <archive>` on Linux/macOS
  or `Get-FileHash <archive> -Algorithm SHA256` on Windows.
- **File count:** **324 files** (v5 was 286; v6 adds
  `scripts/test-docs-contract-paths.sh`,
  `scripts/check-version-contract.py`,
  `scripts/test-version-contract.sh`, v6 docs sections, and the WS1/WS3
  v6 files. Corrected by the parent during the v7 packaging pass —
  the v6 section had carried a stale candidate filename and an
  unfilled count forward from the v6 draft.)
- **Archive verified by:** parent's Pass C — extraction of the actual
  final ZIP bytes to three fresh directories (plain path, path with
  spaces, path under an ancestor literally named `data`), each
  followed by `./scripts/verify-release.sh` (**23 PASS / 0 FAIL /
  5 NOT RUN in all three**), plus pytest **374 passed** and CLI
  **18/18** on the plain extraction's shipped code, docs-contract
  **PASS from the `data/`-ancestor extraction**, and `npm ci` +
  Vitest **110/110** + build byte-identical (`index-DqMbd3aH.js`,
  SHA-256 `1d2a1718…`) on the plain extraction — see
  `docs/VERIFICATION_LOG.md`, Operation Trustline v6 Pass A/B/C.

### Contents (v6 changes vs v5)

| Area | Notes |
|---|---|
| Backend (`backend/src`, `backend/tests`) | IF-V5-02: `/lab/counts` now exposes `live_login_events` (rows), `live_login_transactions` (COUNT DISTINCT `correlation_id`), `live_login_successful_transactions` (transactions containing a `SESSION_CREATED` event) and `live_login_event_limit`; `live_logins` kept only as a deprecated alias labelled EVENTS. IF-V5-03: retention evicts the oldest whole run (events + report together); a single run over the event cap is rejected with a controlled error; `get_run_evidence_status()` + `/runs/{id}/events` completeness fields + stored `report_sha256`. IF-V5-04: live-login retention evicts the oldest whole `correlation_id` (per-transaction cap 100); `assess_live_login_timeline()` marks incomplete timelines with `timeline_complete=false`, `missing_stages`, `truncated_at`, `retention_reason`. IF-V5-05: single version source `identityforge.__version__ = "1.6.0"` in `__init__.py`; `app.py` derives BOTH its FastAPI version and its `/api/v1/health` version from it. 34 new tests (`test_v6_evidence_retention.py` 26, `test_v6_backend_api.py` 8); pytest 374 passed (parent re-ran, 2026-11-11 ~23:20 UTC). |
| Frontend (`frontend/src`, `frontend/e2e`) | IF-V5-02/07: `frontend/src/lib/liveLogins.ts` is the single source of truth for live-login units; Overview/Settings/Reports/Atlas show exact event vs transaction counts, "Recent transactions displayed (max 20)" and the retained transaction total; failed fetch → Unknown. IF-V5-06: new `frontend/src/lib/useResource.ts` (IDLE/LOADING/READY/STALE/ERROR/NOT RUN, timestamps, real useEffect cleanup, AbortController, generation key); later success clears stale errors. IF-V5-05: UI version comes only from `GET /api/v1/health` (no hard-coded version literal in `frontend/src`); `package-lock.json` was synced to 1.6.0 by the Pass A coordinator via `npm install --package-lock-only` (never hand-edited) — version-contract now PASSES on the real tree (parent re-ran, 2026-11-11 ~23:20 UTC). Atelier v6: all 12 views redesigned (see `docs/UI_DESIGN_SYSTEM.md`); 129 fresh v6 PNGs in `frontend/e2e/screenshots` at 8 widths; Vitest 110/110 (parent re-ran). |
| Keycloak realm import | `keycloak/realm-import/identityforge-lab-realm.json` (unchanged from v5: pinned subject UUIDs, no `dockerFlow`) |
| Docs (`docs/`) | + v6 sections in REMEDIATION_FINDINGS, REMEDIATION_TRACEABILITY, VERIFICATION_LOG, RELEASE_MANIFEST; honest retention wording + four-way distinction + capacity warning + export instructions in EVIDENCE_RETENTION / API_CONTRACT / REVIEWER_GUIDE / WINDOWS_SETUP (IF-V5-08); reviewer-gate commands with archive SHA-256 check + lab-scoped cleanup only (IF-V5-09); status vocabulary + CI default-green note + fail-closed scope (IF-V5-10); measured-values honesty + packaging-list exclusions (IF-V5-11); TEST_MATRIX U31/U32 (IF-V5-01/05) |
| Scripts (`scripts/`) | `scripts/validate-docs-contract.py` path-independence fix (IF-V5-01) + new `scripts/test-docs-contract-paths.sh` (15 checks); new `scripts/check-version-contract.py` + `scripts/test-version-contract.sh` (IF-V5-05, 13 checks); test-all now **18 gates** (DOCS_CONTRACT_PATHS + VERSION_CONTRACT added) in `test-all.sh` + `test-all.ps1` (throwaway `python:3.12-slim` container pattern); `scripts/verify-release.sh` gains DOCS_CONTRACT / DOCS_CONTRACT_PATHS / VERSION_CONTRACT gates, extended FORBIDDEN_FILES (`*.p12`/`*.jks`/`*.log`/`.DS_Store`), and `docs/EVIDENCE_RETENTION.md` in REQUIRED_FILES; CI scripts lane runs both new checks |
| Root files | README, SECURITY, LICENSE, `.env.example`, `.gitignore`, `docker-compose.yml` (unchanged: Keycloak healthcheck `$$resp`, ports locked, 127.0.0.1 only), `docker-compose.test.yml`, `frontend/.dockerignore`, `backend/.dockerignore` |
| CI | `.github/workflows/ci.yml` (backend lane + docs-contract step; scripts lane + docs-contract-paths + version-contract steps; frontend lane with npm audit; GHSA step informational; keycloak-e2e lane `workflow_dispatch` only — a green default run proves the OFFLINE gates only and is NOT live-Keycloak proof) |
| Example reports | Unchanged from v5 (`REPORT_TEMPLATE.json` in the real `ComparisonResult` shape; executed reports unchanged — executed evidence) |

### Test results at release time (all rows measured in-session; see `docs/VERIFICATION_LOG.md`)

One row per gate, with the command, environment, date, and result —
taken from the actual runs in `docs/VERIFICATION_LOG.md`, never from
memory:

| Gate | Result (v6) |
|---|---|
| Backend offline (pytest) | **374 passed, 0 failed** (measured by WS2's own run in this tree, 2026-11-11 ~22:30 UTC; `374 passed, 2 warnings in 68.77s`, rc=0; v5 was 340 — the +34 are WS1's new `test_v6_backend_api.py` (8) and `test_v6_evidence_retention.py` (26). WS1 owns the backend and should confirm as the Pass A figure) |
| Backend lint/format | **ruff clean** (WS2's own run, 2026-11-11 ~22:30 UTC: `ruff check src tests` — all checks passed; `ruff format --check src tests` — 61 files already formatted; v5 was 59 files) |
| Backend scenario CLI | **18/18 PASS** (WS2's own run, `python -m identityforge.cli verify-all`, offline fixture, 2026-11-11 ~22:32 UTC; v5 was 18/18) |
| Docs-contract | **PASS — 34 FailureReason values, 59 report-model fields, 113 source files harvested, 64 files scanned, 0 violations** (WS2's own run, 2026-11-11 ~22:15 UTC; the scan count was 60 at the start of the session and moved to 64 as WS3 added frontend lib files) |
| Docs-contract path independence | **PASS — 15/15** (WS2's own run, `bash scripts/test-docs-contract-paths.sh`; clean docs PASS in normal / `data/`-ancestor / spaces paths; stale-code, below-root exclusion, symlink-escape and empty-scan negatives in all three). Pre-fix: 9/15 (clean docs under `data/` failed with 5 false violations) |
| Version contract (fixtures) | **PASS — 13/13** (WS2's own run, `bash scripts/test-version-contract.sh`, 2026-11-11 ~22:20 UTC; all-agree PASS; `__version__`-derivation PASS + negative; one-source-differs FAILS (rc=1) for manifest, pyproject, package.json, package-lock.json, `__init__`, FastAPI version, health version, and a hard-coded UI version literal; missing-source FAILS (rc=2); malformed `--expected` FAILS (rc=2)) |
| Version contract (real tree) | **PASS — all authoritative versions equal 1.6.0** (Pass A coordinator's fix + parent re-run, 2026-11-11 ~23:20 UTC: `python3 scripts/check-version-contract.py` → "version-contract: PASS"). History: WS2's runs at ~22:20 and ~22:33 UTC FAILED honestly on exactly one source (`package-lock.json` root version 1.0.0 vs 1.6.0); the Pass A coordinator synced it via `npm install --package-lock-only` (never hand-edited). Manifest, pyproject, `__init__`, FastAPI, health, package.json and lockfile all agree at 1.6.0; UI reads the version from `GET /api/v1/health`. |
| Dockerignore check | **82 passed, 0 failed** (WS2's own run, `python3 scripts/test-dockerignore.py`, battery run 2026-11-11 ~22:18 UTC; v5 was 82/82) |
| Compose-config check | **PASS** (WS2's own run, `python3 scripts/compose-config-check.py`, 2026-11-11 ~22:20 UTC; YAML-only — the real `docker compose config` is NOT RUN here, no Docker CLI) |
| Frontend typecheck/tests/build | **Typecheck PASS; Vitest 110 passed / 110 (13 files); build `index-DqMbd3aH.js` 168.07 kB / 54.70 kB gzip** (measured by WS2 inside the `test-all.sh --offline` run, 2026-11-11 ~22:32–22:33 UTC; v5 was typecheck PASS, Vitest 92/92, build `index-DgdhM3ou.js` 166.43 kB / 54.14 kB gzip. WS3 owns the frontend and should confirm as the Pass A figure) |
| Browser E2E (Playwright) | **69 passed, 1 skipped, 0 failed** (parent's own run, 2026-11-11 ~23:25 UTC, `npx playwright test --workers=1`; validator PASS, target `host-lab`; the 1 skip is the documented Keycloak cancel case). First full run read 68/1/1 — a real test defect (screenshots "not-run" test did not mock `/lab/counts`), fixed test-only, full suite re-run green. (v5 was 65 passed + 1 skipped) |
| Accessibility (axe) | **25/25 tests, 0 violations at any impact level** (parent's own run, same Playwright run; verified from the real report JSON; zero-tolerance). (v5 was 25/25, 0 violations) |
| Screenshots / responsive | **129 fresh v6 PNGs at 8 widths** in `frontend/e2e/screenshots` (all v5 PNGs deleted first; parent's run regenerated them from the actual v6 build). (v5 was 100 PNGs at 6 widths) |
| Live Keycloak gate (`live-gate.py all`) | **101/101 checks PASS, 0 fail** (parent's own run, 2026-11-11 ~23:28 UTC, host-process Keycloak 26.8.2 — NOT Compose). Reset gate separately: **67/67 PASS**. (v5 was 101/101; login 39/39; reset 66/66) |
| Dependency gates | **55 passed, 0 failed** (WS2's own run, `bash scripts/test-dependency-gates.sh`, battery run 2026-11-11 ~22:18 UTC; v5 was 55/55) |
| Doctor | **8 passed, 0 failed** (WS2's own run in a network namespace with loopback up, 2026-11-11 ~22:25 UTC; v5 was 8/8. Host run skips honestly while the live stack holds the ports) |
| Gate strictness | **9 passed, 0 failed** (Pass A coordinator's re-run after the lockfile sync, 2026-11-11 ~23:00 UTC; v5 was 9/9). History: WS2's runs at ~22:18 and ~22:38–22:51 UTC read 7 passed / 2 failed, both failures being cases 2 and 4 failing on the new `VERSION_CONTRACT` gate because `package-lock.json` was still 1.0.0 — the gate working as designed, not a wiring regression; see `docs/VERIFICATION_LOG.md`. |
| Port preflight | **10 passed, 0 failed, 0 skipped** (WS2's own run, `bash scripts/test-port-preflight.sh`, battery run 2026-11-11 ~22:18 UTC; v5 was 10/10) |
| ps1 preflight | **20 passed, 0 failed, 1 skipped** (WS2's own run, `bash scripts/test-ps1-preflight.sh`, 2026-11-11 ~22:36 UTC; v5 was 20/0/1. The skip is the ports-free cold-start path — no real Docker here; reviewer runs `.\scripts\test-all.ps1 -Full -Strict` on Windows) |
| Host-map adapter | **21 passed, 0 failed** (WS2's own run, 2026-11-11 ~22:20 UTC; v5 was 21/21) |
| pip-audit | **PASS — clean** (measured in the `test-all.sh --offline` run, 2026-11-11 ~22:26 UTC: pip-audit 2.10.1, full pinned runtime set; v5 was clean, pip-audit 2.10.1) |
| npm audit | **NOT RUN** — registry proxy 403 `policy_denied`, measured in the `test-all.sh --offline` run 2026-11-11 ~22:26 UTC (`NPM_FULL_LOCKFILE_AUDIT` NOT RUN, `STATUS=NOT_RUN:BLOCKED`); expected, same as v3/v4/v5 |
| npm audit fallback (GHSA) | **PASS — 14/14 direct deps, 0 high/critical, checked 2026-11-11T22:34:15Z** (measured in the fresh-extraction `verify-release.sh` run under a `data/` ancestor; direct-only, transitive advisories still require `npm audit`. v5 was 14/14, 0 high/critical, 2026-11-11T21:07:31Z) |
| verify-release (fresh extraction) | **23 PASS / 0 FAIL / 5 NOT RUN in all three fresh extractions of the actual final ZIP bytes** (parent's Pass C, 2026-11-11 ~23:32 UTC: plain path, path with spaces, path under an ancestor literally named `data`). History: Pass A coordinator's re-run on a packaging-exclusion copy after the lockfile sync (~23:00 UTC) also read 23/0/5; WS2's runs at ~22:34 UTC (`/tmp/data/if6-verify`) and ~22:35 UTC (`/tmp/if6 verify spaces/`) read 22 PASS / 1 FAIL / 5 NOT RUN, the single FAIL being `VERSION_CONTRACT` (lockfile 1.0.0). `DOCS_CONTRACT` and `DOCS_CONTRACT_PATHS` PASS in all runs. The 5 NOT RUN are `BACKEND_PYTEST`, `FRONTEND_BUILD`, `COMPOSE_CONFIG`, `PYTHON_DEPENDENCY_AUDIT`, `NPM_FULL_LOCKFILE_AUDIT` (no deps/Docker in a fresh copy — honest environment reasons, never passes) |
| Compose boot (Docker) | **NOT RUN** — no Docker binary/socket in this sandbox. Reviewer gate on Docker Desktop |
| Windows PowerShell 5.1 execution | **NOT RUN** — 5.1 is Windows-only. PowerShell 7.4.6 on Linux WAS executed (ps1 suites re-run in the v6 battery — see VERIFICATION_LOG). Reviewer gate |
| Keycloak healthcheck in-image validation | **NOT RUN** — no Docker in this sandbox. Source fixed (`$$resp`); reviewer gate |
| Mutation test (source-level) | **NOT RUN by design** — sensitivity via the designed `omit` mechanism: PASS |
| Pass A repetition | **Parent re-ran the headline gates at the final code state** (2026-11-11 ~23:20–23:31 UTC): pytest **374 passed**, ruff clean, CLI **18/18**, docs-contract paths **15/15**, version-contract **PASS**, typecheck **PASS**, Vitest **110/110**, build byte-identical (`index-DqMbd3aH.js`, SHA-256 `1d2a1718…`), `test-all.sh --offline` **11 PASS / 0 FAIL / 7 NOT RUN, rc=0**. |
| Pass B clean extractions | **Three fresh extractions of the actual final ZIP bytes** (2026-11-11 ~23:32 UTC): plain path, path with spaces, and a path under an ancestor literally named `data` — `verify-release.sh` **23 PASS / 0 FAIL / 5 NOT RUN in all three**; docs-contract **PASS from the `data/`-ancestor extraction**; pytest on the plain extraction's shipped code **374 passed** (import verified to resolve to the extraction, version 1.6.0); CLI **18/18** and docs-contract-paths **15/15** on the plain extraction; frontend `npm ci` + Vitest + build re-run on the plain extraction — see `docs/VERIFICATION_LOG.md`. |

## Operation Trustline v7 — seventh-release targeted hardening (2026-11-11)

> Every row below is filled from the measured runs in
> `docs/VERIFICATION_LOG.md` (v7 section) — never from memory, and
> never in advance. No v6 figure is copied forward as a v7 result.
> All rows are filled at release time (WS1/WS2/WS3 via the Pass A
> coordinator, and the parent's own Pass B/C re-runs); no v6 figure
> is copied forward as a v7 result. Status words in this section are
> exactly PASS / FAIL / NOT RUN / NOT APPLICABLE (v6, IF-V5-10):
> NOT RUN means the gate did not execute and is never a pass, never
> "skipped", and never interchangeable with NOT APPLICABLE or FAIL.

- **Release name:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V7_FINAL_20261111.zip`
- **Version:** 1.7.0 (Operation Trustline v7 — seventh-release
  targeted hardening + Atelier v7 refinements)
- **Date:** 2026-11-11 (ISO 8601)
- **Built from:** working tree at `~/workspace/identityforge-v7`
  (no git repository was used for this build; no commit SHA exists)
- **Built by:** Linux sandbox, Python 3.12.3, Node 24.22.1, npm 10.9.4.
  **No Docker binary or socket exists in this sandbox** — the shipped
  `docker compose up` path is NOT RUN here (see below). PowerShell
  7.4.6 on Linux (`~/workspace/.pwsh/pwsh`) WAS executed here;
  Windows PowerShell 5.1 was NOT.

### Archive (file count from the tree; size/SHA-256 in the delivery message)

- **Filename:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V7_FINAL_20261111.zip`
- **Size (bytes) and SHA-256:** not printed inside the archive — either
  value is a property of the ZIP file itself, so printing it here would
  change it. Check the delivery message for the SHA-256 of the shipped
  file, and verify with `ls -l` / `sha256sum <archive>` on Linux/macOS
  or `Get-FileHash <archive> -Algorithm SHA256` on Windows.
- **File count:** **325 files** (v6 was 324; the +1 is the new
  `backend/tests/unit/test_v7_success_predicate.py` — do not copy the
  v6 count forward.)
- **Archive verified by:** parent's Pass C — extraction of the actual
  final ZIP bytes to three fresh directories (plain path, path with
  spaces, path under an ancestor literally named `data`), each
  followed by `./scripts/verify-release.sh` (**23 PASS / 0 FAIL /
  5 NOT RUN in all three**), plus pytest **391 passed** and CLI
  **18/18** on the plain extraction's shipped code, docs-contract
  **PASS from the `data/`-ancestor extraction**, and `npm ci` +
  Vitest **153/153** + build byte-identical (`index-CpvwjTcU.js`,
  SHA-256 `78f5536d…`) on the plain extraction — see
  `docs/VERIFICATION_LOG.md`, Operation Trustline v7 Pass B/C.

### Contents (v7 changes vs v6)

| Area | Notes |
|---|---|
| Backend (`backend/src`, `backend/tests`) | IF-V6-02: `assess_live_login_timeline()` is now the ONE canonical success predicate shared by `counts()`, `storage_budget()`, `list_live_logins()` and `get_live_login()` (`backend/src/identityforge/evidence/store.py`, new `_live_login_success_counts_locked()`; old `SESSION_CREATED ok` SQL shortcut removed from both counts paths). Three explicitly named counters: `live_login_session_created_observed` (distinct transactions where a `SESSION_CREATED`/`ok` row was observed — the old v6 meaning, kept under an honest name), `live_login_successful_transactions` (**meaning changed in v7**: only verified successes — complete canonical 6-stage sequence ending in `SESSION_CREATED`/`ok`), `live_login_incomplete_transactions` (timeline not complete; a complete terminal denial is in neither bucket). Recomputed from stored rows on every call, so whole-transaction eviction is reflected exactly. 17 new tests (`backend/tests/unit/test_v7_success_predicate.py`, failing-first 17/17 pre-fix). Coordinator also updated the two v6 version tests to 1.7.0 (`test_version_single_source_1_7_0`, `test_health_and_fastapi_metadata_report_1_7_0`) and the Settings mock/assertion version literals. |
| Frontend (`frontend/src`, `frontend/e2e`) | IF-V6-02: canonical live-login assessment in `frontend/src/lib/liveLogins.ts` (`isVerifiedLiveLogin`, `assessLiveLoginTimeline`, `findVerifiedLogin`). IF-V6-03: Overview stale-green fix — reviewer steps carry a `stale` state; STALE data shows a past-tense "Last verified at …" chip, never a current-green Verified pill (Overview.test.tsx 17/17 at WS3's re-runs). IF-V6-04: Reports reviewer attribution (per-person, timeline-complete; incomplete tails and out-of-sample transactions are NOT verified sign-ins). IF-V6-05: `useResource` retry abort. IF-V6-06 / P2-06: Settings reset disabled during a pending identity re-check, with a Re-check identity control. IF-V6-01: export provenance — validated server report. All six: **Vitest 153/153 (13 files), typecheck PASS** (WS3 re-runs, 2026-11-12 ~00:59 and ~01:00 UTC). Atelier v7 (WS3): Overview Data-requests two-across density + aria-live, live-counts hero strip (retained transaction total large, event total small, retained-vs-all-time + last-20-sample wording), stale-vs-current chips, Findings provenance legend + dashed-amber degraded export, Atlas 7-state legend + missing-stage reasons, Reports persona/environment step chips, Settings identity-state pill + dialog scroll-lock (focus trap / Escape / return-focus already in ConfirmDialog, v6) + `aria-describedby` on reset; `frontend/src/styles.css` gains forced-colours support. Same v6 ink/graphite/porcelain/brass/teal tokens; no theme change. |
| Keycloak realm import | `keycloak/realm-import/identityforge-lab-realm.json` (unchanged from v6: pinned subject UUIDs, no `dockerFlow`) |
| Docs (`docs/`) | + v7 sections in REMEDIATION_FINDINGS, REMEDIATION_TRACEABILITY, VERIFICATION_LOG, RELEASE_MANIFEST; version advertised as 1.7.0 everywhere current (API_CONTRACT health example, WINDOWS_SETUP, README v7 changelog entry); extraction-permission note (Info-ZIP `unzip` preserves 0770 `.sh` bits; Python `zipfile` may drop them — `chmod +x scripts/*.sh` is the documented fallback, explicitly NOT an application defect); honest NOT RUN reviewer gates; 18-gate test-all shape. Historical v6 sections keep 1.6.0. |
| Scripts (`scripts/`) | Version-contract machinery moved to v7: `scripts/check-version-contract.py` now reads the Trustline v7 manifest section and expects 1.7.0 by default; `scripts/test-version-contract.sh` fixtures at 1.7.0; `test-all.sh` / `test-all.ps1` / `verify-release.sh` / `test-matrix.md` gate text now names 1.7.0. No gate logic changed. |
| Root files | README (v7 changelog entry), SECURITY, LICENSE, `.env.example`, `.gitignore`, `docker-compose.yml` (unchanged: Keycloak healthcheck `$$resp`, ports locked, 127.0.0.1 only), `docker-compose.test.yml`, `frontend/.dockerignore`, `backend/.dockerignore` |
| CI | `.github/workflows/ci.yml` (unchanged from v6; CI execution itself is NOT RUN in this sandbox — reviewer gate) |
| Example reports | Unchanged from v6 (executed evidence) |

### Test results at release time (all rows measured in-session; see `docs/VERIFICATION_LOG.md`)

One row per gate, with the command, environment, date, and result —
taken from the actual runs in `docs/VERIFICATION_LOG.md`, never from
memory:

| Gate | Result (v7) |
|---|---|
| Backend offline (pytest) | **391 passed, 0 failed, 2 warnings** (coordinator's own run, 2026-11-12 ~01:03 UTC, `374 passed` v6 baseline + 17 new WS1 tests; the two pre-existing warnings unchanged). WS1's run also read 391 passed / 2 failed — the 2 failures were the v6 version tests asserting 1.6.0 after WS3's 1.7.0 bump; coordinator updated them to 1.7.0 and the full suite is green. |
| Backend lint/format | **ruff clean** (coordinator's own run, 2026-11-12 ~01:03 UTC: `ruff check src tests` all checks passed; `ruff format --check src tests` 62 files already formatted; v6 was 59→61 files) |
| Backend scenario CLI | **18/18 PASS** (coordinator's own run, `python -m identityforge.cli verify-all`, offline fixture, 2026-11-12 ~01:03 UTC; v6 was 18/18) |
| Docs-contract | **PASS — 0 violations, 34 FailureReason values, 59 report-model fields, 113 source files harvested, 64 files scanned** (WS3, `python3 scripts/validate-docs-contract.py`, 2026-11-12 ~00:53 UTC; re-run after all v7 doc edits — see `docs/VERIFICATION_LOG.md`) |
| Docs-contract path independence | **PASS — 15/15** (WS3, `bash scripts/test-docs-contract-paths.sh`, 2026-11-12 ~00:53 UTC; clean docs PASS in normal / `data/`-ancestor / spaces paths; stale-code, below-root exclusion, symlink-escape and empty-scan negatives in all three). P2-09 regression preservation: no v3/v4/v5/v6 invariant broken by WS3's changes (issuer vs transport DNS, docs-contract paths, Host header — static checks only). |
| Version contract (fixtures) | **PASS — 13/13** (WS3, `bash scripts/test-version-contract.sh`, 2026-11-12 ~00:53 UTC; fixtures rebuilt at 1.7.0; all-agree PASS; `__version__`-derivation PASS + negative; one-source-differs FAILS for every source; missing-source FAILS; malformed `--expected` FAILS) |
| Version contract (real tree) | **PASS — all authoritative versions equal 1.7.0** (WS3, `python3 scripts/check-version-contract.py`, 2026-11-12 ~00:53 UTC. The checker itself was moved to v7: it now reads the Trustline v7 manifest section and expects 1.7.0 by default; `package-lock.json` was synced via `npm install --package-lock-only`, never hand-edited. Manifest, pyproject, `__init__`, FastAPI via `__version__`, health via `__version__`, package.json and lockfile all agree at 1.7.0; UI reads the version from `GET /api/v1/health`.) |
| Dockerignore check | **82 passed, 0 failed** (coordinator's own run, `python3 scripts/test-dockerignore.py`, 2026-11-12 ~01:17 UTC; v6 was 82/82) |
| Compose-config check | **PASS** (coordinator's own run, `python3 scripts/compose-config-check.py`, 2026-11-12 ~01:17 UTC; YAML-only — the real `docker compose config` is NOT RUN here, no Docker CLI; v6 was PASS, YAML-only) |
| Frontend typecheck/tests/build | **Typecheck PASS; Vitest 153 passed / 153 (13 files); build `index-CpvwjTcU.js` 170.04 kB / 55.20 kB gzip, SHA-256 `78f5536d1b4c2bee8f53a9646b52c56c83789e5c22e03e318d36aeb9f44a9d9d`** (coordinator's own runs at final code, 2026-11-12 ~01:07 UTC: `npm run typecheck` clean, `npm test -- --run` 153/153, `npm run build` full path; the build was run twice with byte-identical output, confirming determinism at final code. WS3's mid-session build was `index-BXc-Ornr.js` at the same size; WS2's was `index-DqGKTKs0.js` — hashes differ because source was still changing between those builds. History: at WS3's ~00:47 UTC run typecheck failed with errors in WS2's in-progress `liveLogins.test.ts` and Vitest read 30 failed / 121 passed (151) — WS2's failing-first suites before their implementations landed; at ~00:51 UTC Overview was 16/17 and Findings 2/4. v6 was typecheck PASS, Vitest 110/110, build `index-DqMbd3aH.js` 168.07 kB / 54.70 kB gzip) |
| Browser E2E (Playwright) | **69 passed, 1 skipped, 0 failed** (coordinator's own runs, 2026-11-12 ~01:12 UTC, `npx playwright test --workers=1`; validator **PASS** [e2e] total=70 passed=69 failed=0 skipped=1, target `host-lab`; the 1 skip is the documented Keycloak cancel case). First full run read 68/1/1 — a real test defect found by the coordinator: `edge.spec.ts` "CSV is labelled CLIENT-DERIVED…" failed strict-mode (WS2's new IF-V6-01 status notice also contains the text "Server-verified artifact", so the regex matched 2 elements). Test-only fix: the assertion now uses exact text; edge spec re-ran 8/8, then the full suite 69+1. No product change. (v6 was 69 passed, 1 skipped) |
| Accessibility (axe) | **25/25 tests, 0 violations at any impact level** (coordinator's own run, same Playwright run; verified from the real report JSON; zero-tolerance). (v6 was 25/25, 0 violations) |
| Screenshots / responsive | **27 passed, 1 failed on the first full run** (`npx playwright test e2e/screenshots.spec.ts --workers=1`, WS3, 2026-11-12 ~00:55–00:58 UTC, live v7 stack: Keycloak 26.8.2 host process + v7 backend + Vite preview); the single failure was `screenshots @ 360x740` at the Reports shot — an immediate re-run of that viewport PASSED, so the failure did not reproduce (transient; likely CPU contention with WS2's concurrent Vitest runs in the same tree — no overflow defect: the 360px Reports PNG renders the WS3 step chips with no horizontal overflow, and the overflow assertion passed on re-run). **129 PNGs in `frontend/e2e/screenshots/` at 8 widths, all regenerated from the actual v7 build** (95 changed by hash vs the v6 set, 34 byte-identical); changed-view PNGs (overview, atlas-rejected, findings, reports, settings, modal-reset at all widths + state shots) were inspected by WS3 (1440x900 overview/findings/reports/atlas-rejected, 1280x800 settings — no clipping, overlap or contrast defect found). (v6 was 129 fresh PNGs at 8 widths) |
| Live Keycloak gate (`live-gate.py all`) | **101/101 checks PASS, 0 fail** (coordinator's own run, 2026-11-12 ~01:10 UTC, host-process Keycloak 26.8.2 — NOT Compose). Reset gate separately: **67/67 PASS**. Post-reset counts prove the v7 units live: runs 0, events 0, `live_login_transactions` 1, `live_login_events` 7, `live_login_session_created_observed` 1, `live_login_successful_transactions` 1, `live_login_incomplete_transactions` 0 after the gate's post-reset login; `sessions_total_issued` 27 (process-lifetime, survives reset by design). (v6 was 101/101; reset 67/67) |
| Dependency gates | **55 passed, 0 failed** (coordinator's own run, `bash scripts/test-dependency-gates.sh`, 2026-11-12 ~01:17 UTC; v6 was 55/55) |
| Doctor | **8 passed, 0 failed** (coordinator's own run in a network namespace with loopback up, 2026-11-12 ~01:19 UTC; v6 was 8/8. Host run skips honestly while the live stack holds the ports) |
| Gate strictness | **9 passed, 0 failed** (coordinator's own run, `bash scripts/test-gate-strictness.sh`, 2026-11-12 ~01:20–01:35 UTC, rc=0; v6 was 9/9) |
| Port preflight | **10 passed, 0 failed, 0 skipped** (coordinator's own run, `bash scripts/test-port-preflight.sh`, 2026-11-12 ~01:17 UTC; v6 was 10/10) |
| ps1 preflight | **20 passed, 0 failed, 1 skipped** (coordinator's own run, `bash scripts/test-ps1-preflight.sh`, 2026-11-12 ~01:19 UTC, pwsh 7.4.6; the skip is the ports-free cold-start path — no real Docker here; v6 was 20/0/1). ps1-native suite separately: **22 PowerShell checks + 3 bash checks passed** (pwsh 7.4.6; WinPS 5.1 remains NOT RUN) |
| Host-map adapter | **21 passed, 0 failed** (coordinator's own run, `python3 scripts/test-live-gate-hostmap.py`, 2026-11-12 ~01:19 UTC; v6 was 21/21). Live-gate provenance regression separately: **2/2** (v7-shaped counts pass, v6-shaped fail) |
| pip-audit | **PASS — clean** (coordinator's `test-all.sh --offline` re-run, 2026-11-12 ~01:09 UTC: pip-audit 2.10.1, full pinned runtime set; v6 was clean, pip-audit 2.10.1) |
| npm audit | **NOT RUN** — registry proxy 403 `policy_denied` (same as v3/v4/v5/v6); reviewer gate on a machine with registry access |
| npm audit fallback (GHSA) | **PASS — 14/14 direct deps, 0 high/critical, checked 2026-11-12T01:06:26Z** (coordinator's `test-all.sh --offline` re-run; direct-only, transitive advisories still require `npm audit`. v6 was 14/14, 0 high/critical, 2026-11-11T22:34:15Z) |
| verify-release (fresh extraction) | **23 PASS / 0 FAIL / 5 NOT RUN in all three fresh extractions of the actual final ZIP bytes** (parent's Pass C, 2026-11-12 ~01:41 UTC: plain path, path with spaces, path under an ancestor literally named `data`). The 5 NOT RUN are the dep/Docker-dependent checks (honest environment reasons). (v6 was 23/0/5 in all three extractions) |
| Compose boot (Docker) | **NOT RUN** — no Docker binary/socket in this sandbox. Reviewer gate on Docker Desktop |
| Windows PowerShell 5.1 execution | **NOT RUN** — 5.1 is Windows-only. PowerShell 7.4.6 on Linux WAS executed (ps1 suites re-run in the v6 battery — see VERIFICATION_LOG). Reviewer gate |
| Keycloak healthcheck in-image validation | **NOT RUN** — no Docker in this sandbox. Source fixed (`$$resp`); reviewer gate |
| Mutation test (source-level) | **NOT RUN by design** — sensitivity via the designed `omit` mechanism: PASS |
| Pass A repetition | **Coordinator re-ran the headline gates at the final code state** (2026-11-12 ~01:03–01:20 UTC): pytest **391 passed**, ruff clean, CLI **18/18**, docs-contract paths **15/15**, version-contract **PASS**, typecheck **PASS**, Vitest **153/153**, build byte-identical across two runs (`index-CpvwjTcU.js`, SHA-256 `78f5536d…`), `test-all.sh --offline` **11 PASS / 0 FAIL / 7 NOT RUN, rc=0**, live gate `all` **101/101** + `reset` **67/67**, Playwright **69 passed + 1 skipped** (validator PASS), axe **25/25**. Two coordinator test-only fixes during Pass A (v6 version tests → 1.7.0 + Settings mock/assertion; edge.spec strict-mode exact-text assertion) — see `docs/VERIFICATION_LOG.md`. |
| Pass B clean extractions | **Three fresh extractions of the actual final ZIP bytes** (parent's Pass C, 2026-11-12 ~01:41 UTC): plain `~/workspace/.verify/v7-final-plain`, `~/workspace/.verify/v7 final spaces`, `~/workspace/.verify/data/v7-final-data` — `verify-release.sh` **23/0/5 in all three**; docs-contract **PASS from the `data/`-ancestor extraction**; plain extraction: pytest **391 passed** on the shipped code (import verified to resolve to the extraction, version 1.7.0), CLI **18/18**, docs-contract-paths **15/15**, `npm ci` + Vitest **153/153** + build byte-identical (`index-CpvwjTcU.js`, SHA-256 `78f5536d…`). |

## Operation Trustline v7.1 — targeted maintenance (2026-11-11)

> Every row below is filled from the measured runs in
> `docs/VERIFICATION_LOG.md` (v7.1 section) — never from memory, and
> never in advance. No v7 figure is copied forward as a v7.1 result.
> Status words in this section are exactly PASS / FAIL / NOT RUN /
> NOT APPLICABLE: NOT RUN means the gate did not execute and is never
> a pass, never "skipped", and never interchangeable with
> NOT APPLICABLE or FAIL. v7.1 is targeted maintenance, NOT a
> redesign and NOT a v8: it fixes IF-V7-02 (dependency-gates PATH),
> adds explicit Node 24 setup to the CI scripts lane, and bumps the
> release version to 1.7.1. All other v7 behaviour is unchanged.

- **Release name:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V7.1_FINAL_20261112.zip`
- **Version:** 1.7.1 (Operation Trustline v7.1 — targeted maintenance)
- **Date:** 2026-11-11 (ISO 8601)
- **Built from:** working tree at `~/workspace/identityforge-v7.1`
  (no git repository was used for this build; no commit SHA exists)
- **Built by:** Linux sandbox, Python 3.12.3, Node 24.22.1, npm 10.9.4.
  PowerShell 7.4.6 on Linux (`~/workspace/.pwsh/pwsh`) WAS executed here;
  Windows PowerShell 5.1 was NOT.
  **Historical build environment (2026-11-11/12 sandbox):** no Docker
  binary or socket existed in that build sandbox — the shipped
  `docker compose up` path was NOT RUN there. This describes the
  historical build sandbox only, never the end user's runtime state.

### Archive (file count from the tree; size/SHA-256 in the delivery message)

- **Filename:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V7.1_FINAL_20261112.zip`
- **Size (bytes) and SHA-256:** not printed inside the archive — either value is a property of the ZIP file itself, so printing it here would change it. Check the delivery message for the SHA-256 of the shipped file, and verify with `ls -l` / `sha256sum <archive>` on Linux/macOS or `Get-FileHash <archive> -Algorithm SHA256` on Windows.
- **File count:** **327 files** (v7 was 325; the +2 are the two new Reports state screenshots — no new source files).
- **Archive verified by:** parent's Pass C — extraction of the actual final ZIP bytes to three fresh directories (plain path, path with spaces, path under an ancestor literally named `data`), each followed by `./scripts/verify-release.sh` (**23 PASS / 0 FAIL / 5 NOT RUN in all three**), plus pytest **391 passed** and CLI **18/18** on the plain extraction's shipped code, docs-contract **PASS from the `data/`-ancestor extraction**, dependency-gates **55/0**, and `npm ci` + Vitest **161/161** + build byte-identical (`index-X2bsjLBG.js`, SHA-256 `a77dd7d5…`) on the plain extraction — see `docs/VERIFICATION_LOG.md`, Operation Trustline v7.1 Pass B/C.

### Scope (WS2 — scripts/docs/CI/version)

| Area | Change |
| ---- | ------ |
| Scripts (`scripts/test-dependency-gates.sh`) | IF-V7-02: scenario drivers now run with `PATH="$SCEN_FAKEBIN:$ORIGINAL_PATH"` — the platform PATH captured once at startup, with a FRESH per-scenario copy of the fake npm/python/pip wrappers prepended. No hard-coded `/usr/bin:/bin`; no fake npm can leak across scenarios. Fail-closed gate semantics and the GHSA direct-only scope distinction are unchanged (a blocked full `npm audit` is still NOT RUN, never PASS; GHSA PASS never satisfies the full gate). |
| Scripts (`scripts/audit-gates.sh`) | Checked: no `PATH=` / hard-coded-bin pattern exists in this file — no change needed. |
| CI (`.github/workflows/ci.yml`) | Scripts lane now explicitly sets up Node 24 (`actions/setup-node@v4`, `node-version: "24"`) after Python 3.12 and before the PowerShell install, so the dependency-gates suite never depends on a preinstalled `/usr/bin/node`. Python 3.12 and the PowerShell test setup are unchanged. YAML validated by parse (see VERIFICATION_LOG). The version-contract comment now names 1.7.1. |
| Version (`backend/src/identityforge/__init__.py`, `backend/pyproject.toml`, `frontend/package.json` + `frontend/package-lock.json`) | Single-source bump to **1.7.1**. FastAPI metadata and `/api/v1/health` derive from `__version__` (unchanged design, WS1's v6 single-source). Lockfile synced via `npm install --package-lock-only`, never hand-edited. Version-contract machinery moved to v7.1: `scripts/check-version-contract.py` now reads the Trustline v7.1 manifest section and expects 1.7.1 by default; `scripts/test-version-contract.sh` fixtures at 1.7.1. Test-only version assertions updated to 1.7.1 (`backend/tests/integration/test_v6_backend_api.py`); the frontend `Settings.test.tsx` `/health` mocks still state 1.7.0 — WS1 owns the frontend tests (see VERIFICATION_LOG). |
| Docs (`docs/`) | v7.1 sections in REMEDIATION_FINDINGS, REMEDIATION_TRACEABILITY, VERIFICATION_LOG, RELEASE_MANIFEST; version advertised as 1.7.1 everywhere current (API_CONTRACT health example, README v7.1 changelog entry); two-minute starter checklist + longer Windows Docker test checklist in REVIEWER_GUIDE / WINDOWS_SETUP (PowerShell-tested syntax only, reusing the exact commands from the v7 REVIEWER_GUIDE §7); extraction-permission note retained (Info-ZIP `unzip` preserves 0770 `.sh` bits; Python `zipfile` may drop them). The historic "no Docker binary/socket in this sandbox" statement now appears ONLY in this manifest and `docs/VERIFICATION_LOG.md`, explicitly labelled as the historical build environment (2026-11-11/12 sandbox) — never as the end user's runtime state. Historical v7 sections keep 1.7.0. |

### Measured results (WS2, v7.1)

| Gate | Result |
| ---- | ------ |
| Dependency gates, layout (1) — node under /usr/bin | **55 passed, 0 failed** (WS2, `bash scripts/test-dependency-gates.sh`, 2026-11-12 ~02:13 UTC, re-confirmed ~02:21 UTC; all 14 scenarios, all subassertions) |
| Dependency gates, layout (2) — node/npm ONLY under an NVM-style dir outside /usr/bin and /bin | **55 passed, 0 failed** (WS2, `unshare -rm` private mount namespace, `/dev/null` bind-mounted over `/usr/bin/node`, `PATH=/tmp/nvm-sim/bin:/usr/bin:/bin`, 2026-11-12 ~02:13 UTC, re-confirmed ~02:22 UTC; live node v24.22.1 + npm 10.9.4 via the NVM-style dir; all 14 scenarios, all subassertions) |
| Dependency gates, layout (2) with symlinked node/npm | **55 passed, 0 failed** (WS2, same namespace harness with `node` as a symlink to a real node copy outside `/usr/bin` and `npm` a symlink chain to the real npm-cli.js, 2026-11-12 ~02:13 UTC) |
| Dependency gates, failing-first (OLD script, layout 2) | **38 passed, 17 failed** (WS2, pre-fix reproduction with the v7 script, live NVM-style node v24.22.1 / npm 10.9.4, 2026-11-12 ~02:12 UTC — the exact failure the auditor reported: `npm audit` clean mislabelled NOT RUN, GHSA fallback running as if no full audit existed) |
| No-real-audit probe | **0 real `npm audit` invocations** (WS2, fixed suite re-run in layout 2 with the real npm replaced by a logging stand-in: 14 real-npm calls, all `--version`, zero `audit`; the fake intercepts exactly `npm audit`, 2026-11-12 ~02:14 UTC) |
| Version contract (fixtures) | **PASS — 13/13** (WS2, `bash scripts/test-version-contract.sh`, 2026-11-12 ~02:16 UTC; fixtures rebuilt at 1.7.1; all-agree PASS; `__version__`-derivation PASS + negative; one-source-differs FAILS for every source; missing-source FAILS; malformed `--expected` FAILS. First run read 8 passed / 5 failed — the five one-source negatives still mutated the old `1.7.0` literal, so they matched nothing and were no-ops; the mutation patterns were corrected to `1.7.1` and the suite re-ran 13/13.) |
| Version contract (real tree) | **PASS — all authoritative versions equal 1.7.1** (WS2, `python3 scripts/check-version-contract.py`, 2026-11-12 ~02:15 UTC. The checker itself was moved to v7.1: it now reads the Trustline v7.1 manifest section and expects 1.7.1 by default; `package-lock.json` was synced via `npm install --package-lock-only`, never hand-edited. Manifest, pyproject, `__init__`, FastAPI via `__version__`, health via `__version__`, package.json and lockfile all agree at 1.7.1; UI reads the version from `GET /api/v1/health`.) |
| Docs-contract paths (3 paths) | **15/15** in normal / spaces / `data/`-ancestor paths (WS2, `bash scripts/test-docs-contract-paths.sh`, 2026-11-12 ~02:16 UTC) |
| Docs-contract (real tree) | **PASS — 0 violations** (WS2, `python3 scripts/validate-docs-contract.py`, 2026-11-12 ~02:16 UTC: 34 FailureReason values, 59 report-model fields, 107 source files harvested, 64 files scanned. v7 harvested 113 — the 6-file difference is the gate-created `backend/src/identityforge.egg-info` (PKG-INFO, SOURCES.txt, dependency_links.txt, entry_points.txt, requires.txt, top_level.txt) that still sat under `backend/src` in the v7 tree; it was removed in v7.1 as a stale build artifact, so the v7.1 harvest is 107. No v7 figure is copied forward.) |
| CI YAML validation | **PASS** (WS2, `python3 -c "yaml.safe_load(...)"`, 2026-11-12 ~02:15 UTC: 4 jobs parsed — backend, frontend, scripts, keycloak-e2e; scripts lane lists Set up Node 24 via `actions/setup-node@v4` after Python 3.12) |
| Compose config check | **PASS** (WS2, `python3 scripts/compose-config-check.py`, 2026-11-12 ~02:16 UTC: Compose parses; services keycloak/backend/frontend present; published ports locked to 127.0.0.1:8080/8000/5173; Keycloak image pinned 26.8.2; healthcheck keeps literal `$resp` (2x) with HTTP-200 + issuer greps; `docker compose config` itself NOT RUN without a Docker CLI) |
| Dockerignore semantics | **82 passed, 0 failed** (WS2, `python3 scripts/test-dockerignore.py`, 2026-11-12 ~02:17 UTC) |
| ps1 preflight | **20 passed, 0 failed, 1 skipped** (WS2, `bash scripts/test-ps1-preflight.sh`, 2026-11-12 ~02:17 UTC, pwsh 7.4.6; the skip is the ports-free cold-start path — no real Docker here; unaffected by the v7.1 changes, re-run as a regression check) |
| ps1 native invocation | **22 PowerShell checks + 3 bash checks passed** (WS2, `bash scripts/test-ps1-native.sh`, 2026-11-12 ~02:17 UTC, pwsh 7.4.6; unaffected by the v7.1 changes, re-run as a regression check) |
| Backend offline (pytest) | **NOT RUN by WS2** — WS1 owns the backend; the version-test assertions were updated to 1.7.1 as test-only changes and the full pytest run is for the Pass A coordinator / WS1. |
| Frontend (Vitest / typecheck / build) | **NOT RUN by WS2** — WS1 owns the frontend. The frontend `Settings.test.tsx` `/health` mocks still state 1.7.0 (WS1 to bump). |
| Live gate (real Keycloak) | **NOT RUN by WS2** — WS1 owns the live stack. No live-stack state was touched by WS2. |
| Docker Compose boot | **NOT RUN** — reviewer gate on Docker Desktop (historical build environment, 2026-11-11/12 sandbox, had no Docker binary/socket; see the note under "Built by" above). |
| Windows PowerShell 5.1 execution | **NOT RUN** — 5.1 is Windows-only. PowerShell 7.4.6 on Linux WAS executed (ps1 suites re-run in the v7.1 battery — see VERIFICATION_LOG). Reviewer gate. |
| Keycloak healthcheck in-image validation | **NOT RUN** — no Docker in the historical build sandbox. Reviewer gate. |
| Full npm audit | **NOT RUN** — registry proxy 403 `policy_denied` (same as v3/v4/v5/v6/v7); reviewer gate on a machine with registry access. GHSA direct-only is NOT a substitute for it. |
| Mutation test (source-level) | **NOT RUN by design** — source-level mutation testing is forbidden; sensitivity via the designed `omit` mechanism: PASS. |
| Pass B clean extractions | **Three fresh extractions of the actual final ZIP bytes** (parent's Pass C, 2026-11-12 ~03:19 UTC): plain `~/workspace/.verify/v71-final-plain`, `~/workspace/.verify/v71 final spaces`, `~/workspace/.verify/data/v71-final-data` — `verify-release.sh` **23/0/5 in all three**; docs-contract **PASS from the `data/`-ancestor extraction**; plain extraction: pytest **391 passed** on the shipped code (import verified to resolve to the extraction, version 1.7.1), CLI **18/18**, docs-contract-paths **15/15**, dependency-gates **55/0**, `npm ci` + Vitest **161/161** + build byte-identical (`index-X2bsjLBG.js`, SHA-256 `a77dd7d5…`). |
| verify-release (fresh extraction) | **23 PASS / 0 FAIL / 5 NOT RUN in all three fresh extractions of the actual final ZIP bytes** (parent's Pass C, 2026-11-12 ~03:19 UTC: plain path, path with spaces, path under an ancestor literally named `data`). The 5 NOT RUN are the dep/Docker-dependent checks (honest environment reasons). (v7 was 23/0/5 in all three extractions) |

## Operation Trustline v7.2 — targeted maintenance (2026-11-12)

> Every row below is filled from the measured runs in
> `docs/VERIFICATION_LOG.md` (v7.2 section) — never from memory, and
> never in advance. No v7.1 figure is copied forward as a v7.2 result.
> Status words in this section are exactly PASS / FAIL / NOT RUN /
> NOT APPLICABLE: NOT RUN means the gate did not execute and is never
> a pass, never "skipped", and never interchangeable with
> NOT APPLICABLE or FAIL. v7.2 is targeted maintenance, NOT a
> redesign and NOT a v8: it fixes IF-V7.1-01 (docs part — unguarded
> standalone reset removed from beginner/reviewer checklists),
> IF-V7.1-02 (healthcheck log dir created before first redirection),
> IF-V7.1-03 (HTTP framing parsed via a real HTTP client),
> IF-V7.1-04 (disposable-project ports + read-only
> --against-running-project mode), and IF-V7.1-05 (stale V6 candidate
> filename in the REVIEWER_GUIDE quickstart), and bumps the release
> version to 1.7.2. All other v7.1 behaviour is unchanged.

- **Release name:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V7.2_FINAL_20261112.zip`
- **Version:** 1.7.2 (Operation Trustline v7.2 — targeted maintenance)
- **Date:** 2026-11-12 (ISO 8601)
- **Built from:** working tree at `~/workspace/identityforge-v7.2`
  (no git repository was used for this build; no commit SHA exists)
- **Built by:** Linux sandbox, Python 3.12.3, Node 24.22.1, npm 10.9.4.
  PowerShell 7.4.6 on Linux (`~/workspace/.pwsh/pwsh`) WAS executed here;
  Windows PowerShell 5.1 was NOT.
  **Historical build environment (2026-11-12 sandbox):** no Docker
  binary or socket existed in that build sandbox — the shipped
  `docker compose up` path was NOT RUN there. This describes the
  historical build sandbox only, never the end user's runtime state.

### Archive (file count from the tree; size/SHA-256 in the delivery message)

- **Filename:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V7.2_FINAL_20261112.zip`
- **Size (bytes) and SHA-256:** not printed inside the archive — either value is a property of the ZIP file itself, so printing it here would change it. Check the delivery message for the SHA-256 of the shipped file, and verify with `ls -l` / `sha256sum <archive>` on Linux/macOS or `Get-FileHash <archive> -Algorithm SHA256` on Windows.
- **File count:** **331 files** (v7.1 was 327; the +4 are `scripts/discovery-check.py`, `scripts/test-compose-healthcheck-regressions.sh`, `scripts/test-live-gate-reset-marker.py`, and `backend/tests/integration/test_v72_disposable_marker.py`).
- **Archive verified by:** parent's Pass C — extraction of the actual final ZIP bytes to three fresh directories (plain path, path with spaces, path under an ancestor literally named `data`), each followed by `./scripts/verify-release.sh` (**22 PASS / 0 FAIL / 6 NOT RUN in all three** — the 6th NOT RUN vs v7.1's 5 is GHSA_DIRECT_FALLBACK, rate-limited on the shared egress IP at packaging time, not a code change), plus pytest **397 passed** and CLI **18/18** on the plain extraction's shipped code, docs-contract **PASS from the `data/`-ancestor extraction**, dependency-gates **55/0**, healthcheck regressions **27/27**, and `npm ci` + Vitest **161/161** + build byte-identical (`index-X2bsjLBG.js`, SHA-256 `a77dd7d5…`) on the plain extraction — see `docs/VERIFICATION_LOG.md`, Operation Trustline v7.2 Pass B/C.

### Scope (WS2 — healthcheck script/docs/version/screenshots)

| Area | Change |
| ---- | ------ |
| Version (`backend/src/identityforge/__init__.py`, `backend/pyproject.toml`, `frontend/package.json` + `frontend/package-lock.json`) | Single-source bump to **1.7.2**. FastAPI metadata and `/api/v1/health` derive from `__version__` (unchanged design, WS1's v6 single-source). Lockfile synced via `npm install --package-lock-only`, never hand-edited. Version-contract machinery moved to v7.2: `scripts/check-version-contract.py` now reads the Trustline v7.2 manifest section and expects 1.7.2 by default; `scripts/test-version-contract.sh` fixtures at 1.7.2; `scripts/verify-release.sh` version labels at 1.7.2. Test-only version assertions in `backend/tests/integration/test_v6_backend_api.py` were updated to 1.7.2 by WS1 during the parallel workstream (verified by grep). The frontend `Settings.test.tsx` `/health` mocks + About-version assertion were updated to 1.7.2 by WS2 at WS1's request (mock/test-only); Vitest re-ran 161/161. |
| Scripts (`scripts/test-compose-healthcheck.sh`) | IF-V7.1-02: log directory created before the first redirection; IF-V7.1-03: discovery parsed with a real HTTP client (Content-Length and chunked); IF-V7.1-04: disposable project with unique name, fixed-port preflight, and `--against-running-project` read-only mode. See REMEDIATION_FINDINGS. |
| Docs (`docs/`) | v7.2 sections in REMEDIATION_FINDINGS, REMEDIATION_TRACEABILITY, VERIFICATION_LOG, RELEASE_MANIFEST; IF-V7.1-01: unguarded standalone `live-gate.py reset` removed from beginner/reviewer checklists, replaced by the scoped `-Full -Strict` disposable runner; IF-V7.1-05: REVIEWER_GUIDE quickstart now names the real v7.2 final archive. |
| Screenshots (`frontend/e2e/screenshots/`) | Regenerated against the final v7.2 build (UI unchanged — same set, regenerated; never reused v7.1 PNGs under new names). |

### Measured results (WS2, v7.2)

| Gate | Result |
| ---- | ------ |
| Version contract (fixtures) | **PASS — 13/13** (WS2, `bash scripts/test-version-contract.sh`, 2026-11-12; fixtures rebuilt at 1.7.2; all-agree PASS; `__version__`-derivation PASS + negative; one-source-differs FAILS for every source; missing-source FAILS; malformed `--expected` FAILS. First run read 8 passed / 5 failed — the five one-source negatives still mutated the old `1.7.1` literal in a form `sed` could not match; the mutation patterns were corrected via a Python literal replace and the suite re-ran 13/13.) |
| Version contract (real tree) | **PASS — all authoritative versions equal 1.7.2** (WS2, `python3 scripts/check-version-contract.py`, 2026-11-12. The checker itself was moved to v7.2: it now reads the Trustline v7.2 manifest section and expects 1.7.2 by default; `package-lock.json` was synced via `npm install --package-lock-only`, never hand-edited. Manifest, pyproject, `__init__`, FastAPI via `__version__`, health via `__version__`, package.json and lockfile all agree at 1.7.2; UI reads the version from `GET /api/v1/health`.) |
| Healthcheck regressions | **PASS — 27 passed, 0 failed, 0 not run** (WS2, `bash scripts/test-compose-healthcheck-regressions.sh`, 2026-11-12; failing-first on the v7.1 source: 02-a redirection error + FAIL config with stub log showing ONLY `compose version`, 03-a v7.1 raw-bytes `json.load` JSONDecodeError; then fixed across fresh-copy / config-failure-injection / spaces-path / 13-case HTTP matrix / `--url` stub-server / port-ownership / interrupt-cleanup / read-only / no-Docker cases. Stub `docker` only — no daemon.) |
| Docs-contract (real tree) | **PASS — 0 violations** (WS2, `python3 scripts/validate-docs-contract.py`, 2026-11-12: 34 FailureReason values, 59 report-model fields, 116 source files harvested, 64 files scanned. Pre-fix run read 3 violations — the stale V6 candidate filename in the quickstarts, caught by the new check 5.) |
| Docs-contract paths (3 paths) | **27/27** in normal / spaces / `data/`-ancestor paths (WS2, `bash scripts/test-docs-contract-paths.sh`, 2026-11-12; was 15/15 — the +12 are the IF-V7.1-05 cases (f)–(i)) |
| Compose config check | **PASS** (WS2, static part of the rewritten `scripts/test-compose-healthcheck.sh`, 2026-11-12: Compose parses; services keycloak/backend/frontend present; published ports locked to 127.0.0.1:8080/8000/5173; Keycloak image pinned 26.8.2; healthcheck keeps literal `$resp` (2x) with HTTP-200 + issuer greps; `docker compose config` itself NOT RUN without a Docker CLI) |
| Typecheck | **PASS** (WS2, `cd frontend && npm run typecheck`, 2026-11-12; `tsc --noEmit`, no errors) |
| Vitest | **161 passed** (WS2, `cd frontend && npm test`, 2026-11-12; 13 files. The `Settings.test.tsx` `/health` mocks + About-version assertion were updated 1.7.1 → 1.7.2; first post-bump run read 160/1, fixed, re-ran 161/161.) |
| Production build | **PASS** (WS2, `cd frontend && npm run build`, 2026-11-12; `index-X2bsjLBG.js` **170.04 kB / 55.20 kB gzip, SHA-256 `a77dd7d5…`** — byte-identical to the v7.1 build; the UI is unchanged, as intended) |
| Screenshots | **30 passed** (WS2, `cd frontend && npx playwright test e2e/screenshots.spec.ts`, 2.9m, rc=0, 2026-11-12; against the final v7.2 build — Vite preview on 5173, v7.2 backend on 8000 reporting 1.7.2, live Keycloak 26.8.2. **131 PNGs**, all regenerated in this run, same 131 filenames as v7.1; reset modal opened and CANCELLED, never confirmed.) |
| Backend offline (pytest) | **NOT RUN by WS2** — WS1 owns the backend; the full pytest run is for the Pass A coordinator / WS1. |
| Frontend Playwright (non-screenshot E2E) | **NOT RUN by WS2** — WS1/coordinator own the E2E gate. |
| Live gate (real Keycloak) | **NOT RUN by WS2** — WS1 owns the live stack. No live-stack state was touched by WS2 except the screenshots run above (no reset was run by WS2). |
| Docker Compose boot | **NOT RUN** — reviewer gate on Docker Desktop (historical build environment, 2026-11-12 sandbox, had no Docker binary/socket; see the note under "Built by" above). |
| Windows PowerShell 5.1 execution | **NOT RUN** — 5.1 is Windows-only. PowerShell 7.4.6 on Linux WAS executed in the v7.1 battery (ps1 suites; unaffected by the v7.2 changes, not re-run). Reviewer gate. |
| Keycloak healthcheck in-image validation | **NOT RUN** — no Docker in the historical build sandbox. Reviewer gate. |
| Full npm audit | **NOT RUN** — reviewer gate on a machine with registry access. GHSA direct-only is NOT a substitute for it. |
| Mutation test (source-level) | **NOT RUN by design** — source-level mutation testing is forbidden; sensitivity via the designed `omit` mechanism: PASS. |
| Pass B clean extractions | **Three fresh extractions of the actual final ZIP bytes** (parent's Pass C, 2026-11-12 ~04:43 UTC): plain `~/workspace/.verify/v72-final-plain`, `~/workspace/.verify/v72 final spaces`, `~/workspace/.verify/data/v72-final-data` — `verify-release.sh` **22/0/6 in all three** (see the GHSA note above); docs-contract **PASS from the `data/`-ancestor extraction**; plain extraction: pytest **397 passed** on the shipped code (import verified to resolve to the extraction, version 1.7.2), CLI **18/18**, docs-contract-paths **27/27**, dependency-gates **55/0**, healthcheck regressions **27/27**, `npm ci` + Vitest **161/161** + build byte-identical (`index-X2bsjLBG.js`, SHA-256 `a77dd7d5…`). |
| verify-release (fresh extraction) | **22 PASS / 0 FAIL / 6 NOT RUN in all three fresh extractions of the actual final ZIP bytes** (parent's Pass C, 2026-11-12 ~04:43 UTC: plain path, path with spaces, path under an ancestor literally named `data`). The 6 NOT RUN are the bare-extraction deps/Docker checks plus GHSA_DIRECT_FALLBACK, rate-limited on the shared egress IP (rc=2) at packaging time — the gate correctly records NOT RUN rather than failing. (v7.1 was 23/0/5 when GHSA was reachable.) |

## Operation Trustline v7.3 — targeted maintenance (2026-11-12)

> Every row below is filled from the measured runs in
> `docs/VERIFICATION_LOG.md` (v7.3 section) — never from memory, and
> never in advance. No v7.2 figure is copied forward as a v7.3 result.
> Status words in this section are exactly PASS / FAIL / NOT RUN /
> NOT APPLICABLE: NOT RUN means the gate did not execute and is never
> a pass, never "skipped", and never interchangeable with
> NOT APPLICABLE or FAIL. v7.3 is targeted maintenance, NOT a
> redesign and NOT a v8: it fixes IF-V7.2-02 (regression harness hid
> Python/PyYAML behind a hardcoded `PATH`), IF-V7.2-04
> (beginner-safe Windows documentation + a native PowerShell
> healthcheck wrapper), and the 1.7.3 version bump, and it extends
> the docs-contract regression so the newly-stale v7.2 FINAL archive
> name fails in quickstart commands. IF-V7.2-01 (explicit Docker
> modes exiting 0 when Docker is absent) and IF-V7.2-03 (SIGTERM
> test synchronization) are WS1's workstream in the same release;
> their rows below are marked as such. All other v7.2 behaviour is
> unchanged.

- **Release name:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V7.3_FINAL_20261112.zip`
- **Version:** 1.7.3 (Operation Trustline v7.3 — targeted maintenance)
- **Date:** 2026-11-12 (ISO 8601)
- **Built from:** working tree at `~/workspace/identityforge-v7.3`
  (no git repository was used for this build; no commit SHA exists)
- **Built by:** Linux sandbox, Python 3.12.3, Node 24.22.1, npm 10.9.4.
  PowerShell 7.4.6 on Linux (`~/workspace/.pwsh/pwsh`) WAS executed here;
  Windows PowerShell 5.1 was NOT.
  **Historical build environment (2026-11-12 sandbox):** no Docker
  binary or socket existed in that build sandbox — the shipped
  `docker compose up` path was NOT RUN there. This describes the
  historical build sandbox only, never the end user's runtime state.

### Archive (file count from the tree; size/SHA-256 in the delivery message)

- **Filename:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V7.3_FINAL_20261112.zip`
- **Size (bytes) and SHA-256:** not printed inside the archive — either value is a property of the ZIP file itself, so printing it here would change it. Check the delivery message for the SHA-256 of the shipped file, and verify with `ls -l` / `sha256sum <archive>` on Linux/macOS or `Get-FileHash <archive> -Algorithm SHA256` on Windows.
- **File count:** **332 files** (v7.2's 331 + `scripts/test-compose-healthcheck.ps1`). Confirmed by the parent at packaging: the packaged ZIP itself contains exactly 332 entries.
- **Archive verified by:** parent's Pass C — extraction of the actual final ZIP bytes to three fresh directories (plain path, path with spaces, path under an ancestor literally named `data`), each followed by `./scripts/verify-release.sh` (**23 PASS / 0 FAIL / 5 NOT RUN in all three** — GHSA PASS this round, 14/14 direct deps, 0 high/critical, 2026-11-12T08:10:12Z, so the count is back to v7.1's 23/0/5 shape; the 5 NOT RUN are the bare-extraction deps/Docker checks), plus pytest **397 passed** and CLI **18/18** on the plain extraction's shipped code, docs-contract **PASS from the `data/`-ancestor extraction**, docs-contract-paths **30/30**, dependency-gates **55/0**, healthcheck regressions **32/0/2** (the 2 NOT RUN are the failing-first baseline cases 02-a/03-a, correctly NOT RUN in a bare extraction with no baseline tree), and `npm ci` + Vitest **161/161** + build byte-identical (`index-X2bsjLBG.js`, SHA-256 `a77dd7d5…`) on the plain extraction — see `docs/VERIFICATION_LOG.md`, Operation Trustline v7.3 Pass B/C.

### Scope (WS2 — regression harness / docs / version)

| Area | Change |
| ---- | ------ |
| Version (`backend/src/identityforge/__init__.py`, `backend/pyproject.toml`, `frontend/package.json` + `frontend/package-lock.json`) | Single-source bump to **1.7.3**. FastAPI metadata and `/api/v1/health` derive from `__version__` (unchanged design, WS1's v6 single-source). Lockfile synced via `npm install --package-lock-only`, never hand-edited (only the two root version fields changed; no dependency changed). Version-contract machinery moved to v7.3: `scripts/check-version-contract.py` now reads the Trustline v7.3 manifest section and expects 1.7.3 by default; `scripts/test-version-contract.sh` fixtures at 1.7.3. Test-only version assertions in `backend/tests/integration/test_v6_backend_api.py` were moved to 1.7.3 by WS1 (coordinator follow-up: 9 occurrences — module docstring, both test names/docstrings, `__version__`, pyproject, FastAPI `app.version`, health assertions; the 2 version tests pass, rc=0). The frontend `Settings.test.tsx` `/health` mocks (3×) + About-version assertion were moved to 1.7.3 by the coordinator (mock/test-only; the UI reads the version from `GET /api/v1/health`); Vitest re-verified 161/161 afterwards and the build hash is unchanged. |
| Scripts (`scripts/test-compose-healthcheck-regressions.sh`, `scripts/compose-config-check.py`) | IF-V7.2-02: the harness preserves the caller's PATH (`ORIGINAL_PATH`) and augments it only in a controlled way (`$STUBBIN:$ORIGINAL_PATH`); the no-Docker case hides ONLY the docker CLIs via a filtered PATH instead of a bare `/usr/bin:/bin`. PyYAML is now an explicit prerequisite, preflighted in the SAME interpreter the nested checker uses (exit 2 ENVIRONMENT NOT READY, never a traceback mislabelled as a defect); `compose-config-check.py` itself now fails the same way (exit 2) instead of a bare `ModuleNotFoundError`. New cases: 02-e (preflight negative/positive), 02-f (venv python + Node outside `/usr/bin` preserved), 04-f (no-Docker default mode stays exit 0); 04-e now expects the IF-V7.2-01 exit contract (explicit `--with-docker` with no Docker → nonzero). The 04-c SIGTERM section is WS1's and was not touched. See REMEDIATION_FINDINGS. |
| Scripts (`scripts/test-compose-healthcheck.ps1`, NEW) | IF-V7.2-04: native PowerShell healthcheck wrapper — same checks as the `.sh` form (static check via host python+PyYAML when available, else the authoritative `docker compose config` resolved check; disposable cold-start with port preflight and scoped cleanup; read-only `-AgainstRunningProject`), no host Bash/Python/Node required. Discovery uses a forced-IPv4 raw socket (never follows redirects; Content-Length + chunked framing) and the port preflight a forced-IPv4 `TcpClient` — both measured necessary in the build sandbox, where .NET's default dual-mode socket is diverted to the egress proxy. Tested 13/13 + a path-with-spaces run under PowerShell 7.4.6 on Linux with a stub `docker`; Windows PowerShell 5.1 execution remains NOT RUN. |
| Docs (`docs/`) | v7.3 sections in REMEDIATION_FINDINGS, VERIFICATION_LOG, RELEASE_MANIFEST; IF-V7.2-04: `docs/REVIEWER_GUIDE.md` §7 and `docs/WINDOWS_SETUP.md` §3 now lead with the native PowerShell path (`.\scripts\test-all.ps1 -Full -Strict` after `docker compose down` WITHOUT `-v`; standalone `.\scripts\test-compose-healthcheck.ps1 -WithDocker` / `-AgainstRunningProject`), label the Bash script Linux/macOS-or-explicitly-installed-Bash-only, state that no Ubuntu/WSL distro reinstall is needed, and distinguish the five separate proofs (container health, in-image probe, `/lab/status` canonical issuer validation, student+officer login/policy checks, full dependency audit) — health 200 alone is NOT login proof. Both quickstarts now name the real v7.3 final archive. |
| Docs-contract regression (`scripts/test-docs-contract-paths.sh`) | Fixture manifest moved to the v7.3 release; case (g) now plants the newly-stale v7.2 FINAL name and new case (j) plants the older-stale v7.1 FINAL name, so staleness is proven for more than the immediately-previous release. Check 5 itself (`scripts/validate-docs-contract.py`) needed no logic change: it already compares any `.zip` name in quickstart regions against the manifest's current Filename. |

### Measured results (WS2, v7.3)

| Gate | Result |
| ---- | ------ |
| Version contract (fixtures) | **PASS — 13/13** (WS2, `bash scripts/test-version-contract.sh`, 2026-11-12; fixtures rebuilt at 1.7.3; all-agree PASS; `__version__`-derivation PASS + negative; one-source-differs FAILS for every source; missing-source FAILS; malformed `--expected` FAILS.) |
| Version contract (real tree) | **PASS — all authoritative versions equal 1.7.3** (WS2, `python3 scripts/check-version-contract.py`, 2026-11-12. The checker itself was moved to v7.3: it now reads the Trustline v7.3 manifest section and expects 1.7.3 by default; `package-lock.json` was synced via `npm install --package-lock-only`, never hand-edited — only the two root version fields changed. Manifest, pyproject, `__init__`, FastAPI via `__version__`, health via `__version__`, package.json and lockfile all agree at 1.7.3; UI reads the version from `GET /api/v1/health`.) |
| Healthcheck regressions | **PASS — 32 passed, 0 failed, 0 not run** (WS2 + WS1, `bash scripts/test-compose-healthcheck-regressions.sh`, 2026-11-12; log `22-postfix-post-ws1-landing.log` in the WS2 evidence dir. This is the post-landing run, after WS1's IF-V7.2-01 exit-code change and IF-V7.2-03 SIGTERM rework landed in the tree: 04-e now passes (exit 1), the new 04-c-A/04-c-B cases pass, and all other cases pass, with a dummy loopback listener on 8080 for the 04-a port-occupancy proof. History: before WS1 landed, the same suite read **30 passed / 1 failed / 0 not run** in three repeat normal runs — the single failure was 04-e, which waited on WS1's `test-compose-healthcheck.sh` change (the script still exited 0 then; everything 04-e asserts except the nonzero exit was already true in the output). Failing-first on the shipped v7.2 suite under a yaml-less `/usr/bin/python3`: **21 passed / 6 failed / 0 not run** — every failure a `ModuleNotFoundError: No module named 'yaml'` from the static step, mislabelled as a Compose defect. Post-fix, same environment with PyYAML present in the caller's python and a listener for 04-a: **31 passed / 1 failed / 0 not run** — the single failure is **04-c-A, a residual IF-V7.2-02 instance in WS1-owned lines**: WS1's new 04-c-A section hardcodes `PATH="$C04A_WRAPBIN:$STUBBIN:/usr/bin:/bin"` (regression script line 671; 04-c-B line 711 is the same shape but its assertion does not require static PASS, so it passes), bypassing `ORIGINAL_PATH` and running the static check under the yaml-less system python. The import guard labels it correctly (ENVIRONMENT NOT READY, no bare traceback) but the case requires static PASS, so it fails. WS1's fix is one line per section (use `$ORIGINAL_PATH`); WS2 did not touch those lines (WS1-owned). With prerequisites genuinely unavailable: **ENVIRONMENT NOT READY, rc=2**, no traceback, no FAIL counts. Spaces path and `data/`-ancestor runs: **28/1/2** each pre-landing (the 2 NOT RUN are the v7.1-baseline cases — no sibling v7.1 tree next to those copies — and the 1 FAIL was 04-e). Stub `docker` only — no daemon.) |
| Docs-contract (real tree) | **PASS — 0 violations** (WS2, `python3 scripts/validate-docs-contract.py`, 2026-11-12. Pre-manifest run read **3 violations** — the new v7.3 quickstart names against a manifest still naming v7.2, caught by check 5 before the manifest section was added; a planted stale v7.2 FINAL name in a quickstart region fails the same way.) |
| Docs-contract paths (3 paths) | **30/30** (WS2, `bash scripts/test-docs-contract-paths.sh`, 2026-11-12; normal / spaces / `data/`-ancestor paths; was 27/27 — the +3 are the new case (j): older-stale v7.1 FINAL name FAILS in all three paths; case (g) now plants the newly-stale v7.2 FINAL name.) |
| Compose config check | **PASS** (WS2, `python3 scripts/compose-config-check.py`, 2026-11-12: Compose parses; services keycloak/backend/frontend present; published ports locked to 127.0.0.1:8080/8000/5173; Keycloak image pinned 26.8.2; healthcheck keeps literal `$resp` (2x) with HTTP-200 + issuer greps; `docker compose config` itself NOT RUN without a Docker CLI. The new import guard was also proven: under a yaml-less interpreter it prints ENVIRONMENT NOT READY and exits 2 instead of a traceback.) |
| PowerShell healthcheck wrapper | **PASS — 13/13 + spaces-path run 8/0/0** (WS2, PowerShell 7.4.6 on Linux with a stub `docker`, 2026-11-12: help, default, disposable cold-start with scoped cleanup, read-only (no up/down), no-Docker explicit mode nonzero, no-Docker default mode exit 0, ports-occupied fail-fast with occupant alive, config-failure injection, mutual exclusion, and redirect/HTML/truncated discovery negatives; the in-image probe string extracted from the wrapper runs under bash against a stub discovery server on 8080. Two sandbox findings fixed during testing: .NET's default dual-mode socket is diverted to the egress proxy, so the port preflight forces IPv4 `TcpClient` and discovery uses a forced-IPv4 raw socket instead of `HttpClient`. Windows PowerShell 5.1 execution remains NOT RUN — reviewer gate.) |
| Typecheck | **PASS** (WS2, `cd frontend && npm run typecheck`, 2026-11-12; `tsc --noEmit`, no errors, rc=0. `npm ci` worked in this sandbox — 178 packages — so the frontend gates ran; `node_modules/` and `dist/` were removed afterwards as build artifacts.) |
| Vitest | **161 passed** (WS2, `cd frontend && npm test`, 2026-11-12; 13 files, rc=0. The `Settings.test.tsx` `/health` mocks + About-version assertion still state 1.7.2 (mock-only, self-consistent — hence the pass) and should be updated to 1.7.3 by WS1/coordinator for consistency; the UI reads the version from `GET /api/v1/health`.) |
| Production build | **PASS** (WS2, `cd frontend && npm run build`, 2026-11-12; `index-X2bsjLBG.js` **170.04 kB / 55.20 kB gzip, SHA-256 `a77dd7d52bed856267bf155df61acebbf2ebd2e37d18da34f9862f8e61de67c8`** — byte-identical to the v7.1/v7.2 build; the UI is unchanged, as intended. `dist/` removed afterwards.) |
| Screenshots | **REGENERATED in v7.3 (coordinator update)** — the coordinator ran the full Playwright suite against the live v7.3 stack, so all **131 PNGs are fresh renders from the actual v7.3 build** (same 131 filenames as v7.1/v7.2). Frontend src is unchanged and the build hash is byte-identical to v7.1/v7.2 (`a77dd7d5…`); the PNG bytes changed because they were re-rendered, not because the UI changed. |
| Backend offline (pytest) | **NOT RUN by WS2** — WS1 owns the backend; the full run is for the Pass A coordinator / WS1. (Coordinator: pytest **397 passed**, see the Pass A table below; the version assertions were moved to 1.7.3 by WS1.) |
| Frontend Playwright (non-screenshot E2E) | **NOT RUN by WS2** — WS1/coordinator own the E2E gate. (Coordinator: **71 passed + 1 skipped**, validator PASS, axe 25/25 — see the Pass A table below.) |

### Measured results (coordinator Pass A, v7.3)

All numbers below are the coordinator's own runs on the merged v7.3 tree (2026-11-12 ~07:04–07:45 UTC), never copied from a workstream report without re-running.

| Gate | Result |
| ---- | ------ |
| Backend pytest | **397 passed, 2 warnings in 98.80 s**, rc=0 (`cd backend && <v7.2 venv>/bin/python -m pytest -p no:cacheprovider`; the v7.3 tree ships no `.venv` — the ZIP excludes it — so the v7.2 venv python was used with `PYTHONPATH=v7.3/backend/src`, import verified to resolve to the v7.3 tree, `__version__ 1.7.3`). |
| Offline CLI I1–I18 | **18/18 scenarios PASS**. |
| Ruff (broad scope) | **Clean** — `ruff check backend/src backend/tests scripts` + `ruff format --check backend/src backend/tests` (63 files). Three F401 unused imports removed by the coordinator (one from WS2's `compose-config-check.py` edit, two pre-existing in v7.2 under this broader scope — the established `test-all.sh` gate checks backend only). |
| Typecheck / Vitest / build | Typecheck **PASS** (`tsc --noEmit`, rc=0); Vitest **161 passed** (13 files); build `index-X2bsjLBG.js` **170.04 kB / 55.20 kB gzip, SHA-256 `a77dd7d52bed856267bf155df61acebbf2ebd2e37d18da34f9862f8e61de67c8`** — byte-identical to v7.1/v7.2. |
| Version contract (real tree) | **PASS — all authoritative versions equal 1.7.3** (re-run by the coordinator after the WS1/WS2 bumps). |
| Docs-contract / paths | **PASS, 0 violations**; paths **30/30** (re-run by the coordinator). |
| Healthcheck regressions | **PASS — 34 passed, 0 failed, 0 not run** in every run below (suite grew from WS2's 32 to 34: the coordinator added case 04-g daemon-missing, two sub-cases, and fixed 04-a to start its own 8080 occupant so it no longer depends on a live stack holding the ports). Runs: (1) normal, no live stack; (2b) normal with the live stack up (run 2 first exposed a coordinator bug in the 04-a leak check — a port probe after kill false-failed whenever Keycloak held 8080; fixed to test the listener PID, not the port); (3) normal repeat; (4) under a `data/` ancestor; (5) yaml-less `/usr/bin/python3` via the unshare bind-mount trick, caller python with PyYAML — **34/0/0**. With prerequisites genuinely unavailable (caller python also yaml-less, my first yaml-less attempt): **ENVIRONMENT NOT READY, rc=2**, actionable `pip install pyyaml` hint, no traceback. Slowed-startup 04-c standalone (WS1's script, re-run by the coordinator): **2/0** — TERM at t=7 s (A) and t=13 s (B), both rc=143, exactly one scoped `down -v`. |
| Dependency-gates | **55 passed, 0 failed** in both layouts (system Node; NVM-style with `/usr/bin/node` hidden via unshare bind-mount, node + env-node npm from `/tmp/nvmreal`). |
| Gate-strictness | See `docs/VERIFICATION_LOG.md`, Operation Trustline v7.3 (coordinator Pass A rows). |
| `test-all.sh --offline` | **rc=0, 10 PASS / 0 FAIL / 8 NOT RUN** (18 gates). NOT RUN: NPM_FULL_LOCKFILE_AUDIT (registry proxy 403), GHSA_DIRECT_FALLBACK (GitHub API rate limit exhausted on the shared egress IP — six direct retries 07:49–07:58 UTC all rc=2, each showing a different reset window and 0–2 packages still unreachable; the quota refills in drips while other tenants on the shared IP keep consuming it, so further retries were stopped and the gate stays NOT RUN for v7.3; the last successful GHSA check remains v7.1's, 2026-11-12T02:30:34Z, 14/14, 0 high/critical), + 6 full-profile gates. |
| Playwright (live host stack) | **71 passed + 1 skipped** (6.9 m, slower than usual under concurrent `test-all` CPU load), validator **PASS** (target `host-lab`), axe **25/25, 0 violations** from the real report JSON; **131 PNGs regenerated fresh** in this run. |
| Live gate (real Keycloak 26.8.2, host process) | `all` **101/101 PASS**; `reset` **69/69 PASS** against a disposable marker backend on port 8000 with a temp DB (marker `f18aaf32-…`, health 1.7.3, marker reported in `/lab/status`); post-reset counts 1 txn / 7 events / observed 1 / verified 1 / incomplete 0. Dev backend restored afterwards: all DB-persisted counts byte-identical to the pre-swap snapshot (runs 41, events 234, txns 40, observed 34, verified 34, incomplete 5); the in-memory `sessions`/`sessions_total_issued`/`transactions` fields reset to 0 on the process restart, which is their documented process-lifetime semantics (`backend/src/identityforge/api/app.py:568`, `security/session.py:49`), not data loss. No marker field on the restored dev backend. **Re-run after the 2026-11-12 ~07:46 UTC runtime restart** (parent restarted the stack; coordinator re-ran from final code): `all` **101/101 PASS** again, `reset` **69/69 PASS** again against a fresh marker backend (marker `ad296d0e-5d3a-4f5c-b04d-f092df1d96ce`, temp DB, post-reset 1 txn / 7 events / observed 1 / verified 1 / incomplete 0); dev backend restored with all DB-persisted counts byte-identical to the new pre-swap snapshot (runs 149, events 250, txns 48, observed 40, verified 40, incomplete 6). Evidence in `~/workspace/passa-v73-evidence/` (home disk, survives restarts — the original `/tmp` logs were lost in the restart). |
| PowerShell healthcheck wrapper (smoke) | `-WithDocker` **rc=1**, `-AgainstRunningProject` **rc=1**, default **rc=0** on pwsh 7.4.6 with no Docker (run via `pwsh -File`; the coordinator first measured rc=0 for all three via `pwsh -Command "& { ... }"` and proved with a minimal repro that that invocation form swallows a script's exit code — a pwsh quirk, not a wrapper bug; a one-line warning was added to `docs/WINDOWS_SETUP.md`). |
| pip-audit | Clean (2.10.1) — via `test-all.sh --offline`. |
| Live gate (real Keycloak) | **NOT RUN by WS2** — WS1 owns the live stack. No live-stack state was touched by WS2 except the loopback listeners used for the 04-a port-occupancy proof (a Python `http.server` on 127.0.0.1:8080, started and killed by exact PID, never a lab process; no reset was run by WS2). |
| Docker Compose boot | **NOT RUN** — reviewer gate on Docker Desktop (historical build environment, 2026-11-12 sandbox, had no Docker binary/socket; see the note under "Built by" above). |
| Windows PowerShell 5.1 execution | **NOT RUN** — 5.1 is Windows-only. PowerShell 7.4.6 on Linux WAS executed (ps1 suites + the new healthcheck wrapper, see above). Reviewer gate. |
| Keycloak healthcheck in-image validation | **NOT RUN** — no Docker in the historical build sandbox. Reviewer gate. |
| Full npm audit | **NOT RUN** — reviewer gate on a machine with registry access. GHSA direct-only is NOT a substitute for it. |
| Mutation test (source-level) | **NOT RUN by design** — source-level mutation testing is forbidden; sensitivity via the designed `omit` mechanism: PASS. |
| Pass B clean extractions | **Three fresh extractions of the actual final ZIP bytes** (parent's Pass C, 2026-11-12 ~08:10 UTC): plain `~/workspace/.verify/v73-final-plain`, `~/workspace/.verify/v73 final spaces`, `~/workspace/.verify/data/v73-final-data` — `verify-release.sh` **23/0/5 in all three**; docs-contract **PASS from the `data/`-ancestor extraction**; plain extraction: pytest **397 passed** on the shipped code (import verified to resolve to the extraction, version 1.7.3), CLI **18/18**, docs-contract-paths **30/30**, dependency-gates **55/0**, healthcheck regressions **32/0/2** (02-a/03-a NOT RUN — no baseline tree in a bare extraction, correctly labelled), `npm ci` + Vitest **161/161** + build byte-identical (`index-X2bsjLBG.js`, SHA-256 `a77dd7d5…`). |
| verify-release (fresh extraction) | **23 PASS / 0 FAIL / 5 NOT RUN in all three fresh extractions of the actual final ZIP bytes** (parent's Pass C, 2026-11-12 ~08:10 UTC: plain path, path with spaces, path under an ancestor literally named `data`). GHSA_DIRECT_FALLBACK **PASS** this round (14/14 direct deps, 0 high/critical, 2026-11-12T08:10:12Z, and again in the test-all retry at 08:14:31Z) — the quota had refilled in drips after the rate-limited runs earlier the same morning; the 5 NOT RUN are the bare-extraction deps/Docker checks (honest environment reasons). (v7.2 was 22/0/6 when GHSA was rate-limited.) NOTE: after the doc-fill re-packaging, a fresh-extraction re-verification read **22/0/6** — GHSA flipped back to NOT RUN (rate-limited, rc=2, 08:15:18Z). GHSA is quota-volatile on the shared egress IP; no code changed between the two packagings. |

## Operation Trustline v7.3.1 — targeted maintenance (2026-11-12)

> Every row below is filled from the measured runs in
> `docs/VERIFICATION_LOG.md` (v7.3.1 section) — never from memory, and
> never in advance. No v7.3 figure is copied forward as a v7.3.1 result.
> Status words in this section are exactly PASS / FAIL / NOT RUN /
> NOT APPLICABLE: NOT RUN means the gate did not execute and is never
> a pass, never "skipped", and never interchangeable with
> NOT APPLICABLE or FAIL. v7.3.1 is targeted maintenance, NOT a
> redesign and NOT a v8: it fixes IF-V7.3.1-C (regression-harness
> flake, case 04-a) and IF-V7.3.1-D (CI coverage for the healthcheck
> regression suite and the PowerShell matrix), and it carries the
> 1.7.4 version bump. The release label is v7.3.1 but the product
> version is **1.7.4** — a patch on the 1.7.3 line (npm semver is
> 3-part, so 1.7.3.1 is invalid). IF-V7.3.1-A/B/E (PowerShell wrapper
> fixes and the new matrix script) are WS1's workstream in the same
> release; their rows below are marked as such. All other v7.3
> behaviour is unchanged.

- **Release name:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V7.3.1_FINAL_20261112.zip`
- **Version:** 1.7.4 (Operation Trustline v7.3.1 — targeted maintenance)
- **Date:** 2026-11-12 (ISO 8601)
- **Built from:** working tree at `~/workspace/identityforge-v7.3.1`
  (no git repository was used for this build; no commit SHA exists)
- **Built by:** Linux sandbox, Python 3.12.3, Node 24.22.1, npm 10.9.4.
  PowerShell 7.4.6 on Linux (`~/workspace/.pwsh/pwsh`) WAS executed here;
  Windows PowerShell 5.1 was NOT.
  **Historical build environment (2026-11-12 sandbox):** no Docker
  binary or socket existed in that build sandbox — the shipped
  `docker compose up` path was NOT RUN there. This describes the
  historical build sandbox only, never the end user's runtime state.

### Archive (file count from the tree; size/SHA-256 in the delivery message)

- **Filename:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V7.3.1_FINAL_20261112.zip`
- **Size (bytes) and SHA-256:** not printed inside the archive — either value is a property of the ZIP file itself, so printing it here would change it. Check the delivery message for the SHA-256 of the shipped file, and verify with `ls -l` / `sha256sum <archive>` on Linux/macOS or `Get-FileHash <archive> -Algorithm SHA256` on Windows.
- **File count:** **333 files** (v7.3's 332 + `scripts/test-compose-healthcheck-ps-matrix.ps1`, WS1's new matrix script — the only added file). Tree count by the packager's exclusion shape; confirmed by the parent at packaging — 333 entries in the final ZIP, testzip clean (see Pass C below).
- **Archive verified by:** parent's Pass C — three fresh extractions of the actual final ZIP bytes (plain, path with spaces, path under an ancestor literally named `data/`), verify-release 22/0/6 in all three; see the Pass C row below.

### Scope (WS2 — regression harness 04-a / CI / docs / version)

| Area | Change |
| ---- | ------ |
| Version (`backend/src/identityforge/__init__.py`, `backend/pyproject.toml`, `frontend/package.json` + `frontend/package-lock.json`) | Single-source bump to **1.7.4** — release label v7.3.1, product version 1.7.4 (a patch on the 1.7.3 line; npm semver is 3-part, so 1.7.3.1 is invalid). FastAPI metadata and `/api/v1/health` derive from `__version__` (unchanged design, WS1's v6 single-source). Lockfile synced via `npm install --package-lock-only`, never hand-edited (only the two root version fields changed; no dependency changed). Version-contract machinery moved to v7.3.1: `scripts/check-version-contract.py` now reads the Trustline v7.3.1 manifest section and expects 1.7.4 by default; `scripts/test-version-contract.sh` fixtures at 1.7.4 (the five one-source mutation patterns hold the backslash-escaped literal `1\.7\.4`, corrected via a Python literal replace — the same escaping trap as v7.2/v7.3, avoided on the first pass this time: fixtures 13/13 on the first run). Test-only version assertions in `backend/tests/integration/test_v6_backend_api.py` were moved to 1.7.4 by WS2 (9 occurrences — module docstring, both test names/docstrings, `__version__`, pyproject, FastAPI `app.version`, health assertions). The frontend `Settings.test.tsx` `/health` mocks (3×) + About-version assertion were moved to 1.7.4 by WS2 (mock/test-only; the UI reads the version from `GET /api/v1/health`). The version labels in `scripts/test-all.sh` and `scripts/verify-release.sh` were moved to 1.7.4; the docs-contract-paths count label in `verify-release.sh` was corrected 27 → 33 (it was already stale in v7.3, when the suite had 30 checks). |
| Scripts (`scripts/test-compose-healthcheck-regressions.sh`, case 04-a only) | IF-V7.3.1-C: the port-occupied branch is now tested on CONTROLLED loopback test ports via the existing test-ports override — never on the reviewer's real 8080/8000/5173, which the suite does not own. The occupied port is held by the suite's own listener, which proves its identity by greeting each connection with a per-run token (a bare "something answers" probe cannot tell the suite's listener from the real Keycloak); the other two test ports must be free, so the only occupant in the run is the suite's own. If a candidate port is already held, its owner is identified (best-effort `ss -ltnp` + the suite's own PID set) and logged, and a safe alternate is selected — an external listener is never silently counted as the test's own. Startup readiness is an observed event (token greeting + exact PID alive, bounded poll); only infrastructure setup is retried, never an assertion failure. Ownership after the run is proven by exact PID and cleanup is verified (PID gone AND the port free again). The 04-c-A/04-c-B expectations are unchanged (no unscoped cleanup; exactly one scoped cleanup when a disposable project was actually created), and no other case was reworked. `scripts/test-compose-healthcheck.sh` itself was NOT edited (the Bash checker is correct; the flake was in the harness). See REMEDIATION_FINDINGS. |
| CI (`.github/workflows/ci.yml`, scripts job) | IF-V7.3.1-D: the scripts job now runs the full healthcheck regression suite (stub `docker` only; prerequisites PyYAML/curl/rsync/bash installed and PROVEN first — a missing dep can never be mislabelled as a Compose defect) and the deterministic PowerShell matrix over the healthcheck wrapper (`pwsh -File scripts/test-compose-healthcheck-ps-matrix.ps1`, WS1's new script; `-File`, never `-Command "& { ... }"`, which swallows exit codes). The historical-baseline comparisons (02-a/03-a) remain honestly NOT RUN in CI (no sibling v7.1 tree in a checkout); their absence is not a red/green substitute for the current-tree tests. No Docker daemon and no network-dependent `npm ci` on this lane. GitHub Actions execution itself is NOT RUN — the YAML syntax was validated locally with python yaml, and a YAML-valid workflow is never presented as executed. |
| Scripts (`scripts/test-compose-healthcheck-ps-matrix.ps1`, NEW, WS1) | WS1's file (IF-V7.3.1-A/B/E); WS2 did not edit it. Referenced by the CI scripts job and dry-run locally by WS2 (see below). |
| Docs (`docs/`) | v7.3.1 sections in REMEDIATION_FINDINGS, VERIFICATION_LOG, RELEASE_MANIFEST; both quickstarts now name the real v7.3.1 final archive (`docs/REVIEWER_GUIDE.md` §0, `docs/WINDOWS_SETUP.md` §3). `scripts/test-matrix.md` carries a v7.3.1 note (release label v7.3.1 = product version 1.7.4; docs-contract-paths 33 checks; healthcheck regressions still 34 checks — 04-a was reworked in place, no case added or removed; PS matrix 26 cases). |
| Docs-contract regression (`scripts/test-docs-contract-paths.sh`) | Fixture manifest moved to the v7.3.1 release (current = v7.3.1 FINAL, version 1.7.4); case (g) now plants the newly-stale v7.3 FINAL name, case (j) plants the older-stale v7.2 FINAL name, and new case (k) plants the oldest-stale v7.1 FINAL name — staleness is proven across three releases, not just the immediately-previous one. Check 5 itself (`scripts/validate-docs-contract.py`) needed no logic change: it already compares any `.zip` name in quickstart regions against the manifest's current Filename. |

### Measured results (WS2, v7.3.1)

| Gate | Result |
| ---- | ------ |
| Version contract (fixtures) | **PASS — 13/13** (WS2, `bash scripts/test-version-contract.sh`, 2026-11-12; fixtures rebuilt at 1.7.4; all-agree PASS; `__version__`-derivation PASS + negative; one-source-differs FAILS for every source; missing-source FAILS; malformed `--expected` FAILS. First run, no escaping-trap repeat.) |
| Version contract (real tree) | **PASS — all authoritative versions equal 1.7.4** (WS2, `python3 scripts/check-version-contract.py`, 2026-11-12. The checker itself was moved to v7.3.1: it now reads the Trustline v7.3.1 manifest section and expects 1.7.4 by default; `package-lock.json` was synced via `npm install --package-lock-only`, never hand-edited — only the two root version fields changed. Manifest, pyproject, `__init__`, FastAPI via `__version__`, health via `__version__`, package.json and lockfile all agree at 1.7.4; UI reads the version from `GET /api/v1/health`. Before this manifest section existed, the same check correctly failed with rc=2, manifest unreadable, all other sources already at 1.7.4.) |
| Healthcheck regressions | **PASS — 34 passed, 0 failed, 0 not run** (WS2, `bash scripts/test-compose-healthcheck-regressions.sh --baseline=~/workspace/identityforge-v7.1`, 2026-11-12; first post-fix run, no lab up; log `05-postfix-no-lab-run1.log`. 04-a passes on controlled test ports: occupant is the suite's own token-proven listener on 127.0.0.1:18084, 18004/15177 free.) |
| Healthcheck regressions (external-occupant alternate) | **PASS — 34 passed, 0 failed, 0 not run** (WS2, same suite, 2026-11-12, with an external listener holding the preferred test port 18084; log `06-postfix-ext-occupant-18084.log`. The suite identified the owner as an EXTERNAL process (PID 8512, via `ss -ltnp`), selected the safe alternate 18085, and passed; the external listener was killed afterwards by its exact PID and 18084 verified free.) |
| Healthcheck regressions (20x stress) | **PASS — 20/20 runs 34 passed, 0 failed, 0 not run, rc=0, WITHOUT a simulated background lab, and 20/20 runs 34 passed, 0 failed, 0 not run, rc=0, WITH one** (WS2, `bash stress-04a.sh nolab 20` then `bash stress-04a.sh lab 20`, 2026-11-12; logs `stress-04a-nolab.log` + per-run `stress-04a-nolab-run1..20.log` and `stress-04a-lab.log` + per-run `stress-04a-lab-run1..20.log` in `~/workspace/ws2-v731-evidence/`. The lab batch held a fake listener on the real 8080/8000/5173 for the whole batch (PID 46083, killed afterwards by exact PID), simulating the live stack up — the condition that flaked 04-a in v7.3. Zero failures in 40 consecutive full-suite runs; every run's 04-a line verifies its own occupant teardown ("cleaned up with no leak", 20/20 per mode in the per-run logs). Post-stress leak check (log `21-post-stress-leak-check.log`): zero listeners anywhere (`ss -ltn` header only), real 8080/8000/5173 free, no occupant/fake-lab/http.server processes remain. NOTE: the first stress attempt is discounted, not hidden — a concurrent second suite run filled `/tmp` (512 MiB tmpfs) and truncated the copies (nolab run 20 33/1/0 on 04-g; lab run 1 33/1/0 on 02-b); those logs were archived as `stress-04a-nolab-CONTAMINATED.log` / `stress-04a-lab-CONTAMINATED.log` and both batches re-run cleanly, sequentially. The driver's batch leak-check lines are absent from the batch logs (a `tee || echo` pipeline bug: `tee` exits 0, so the "none found" echo never fires) — the substantive leak evidence is the 40 in-case verifications plus the direct post-stress check above.) |
| Docs-contract (real tree) | **PASS — 0 violations** (WS2, `python3 scripts/validate-docs-contract.py`, 2026-11-12. 34 FailureReason values, 59 report-model fields, 112 source files harvested, 64 files scanned — 112 vs v7.3's 111 is WS1's new matrix script. A planted stale v7.3 FINAL name in a quickstart region fails check 5 with exactly **2 violations, rc=1** (both `REVIEWER_GUIDE.md:31,35`, naming the current v7.3.1 filename), proven on a full tree copy.) |
| Docs-contract paths (3 paths) | **33/33** (WS2, `bash scripts/test-docs-contract-paths.sh`, 2026-11-12; normal / spaces / `data/`-ancestor paths; was 30/30 — the +3 are the new case (k): oldest-stale v7.1 FINAL name FAILS in all three paths; case (g) now plants the newly-stale v7.3 FINAL name and case (j) the older-stale v7.2 FINAL name.) |
| PowerShell healthcheck matrix (WS1 script, dry-run by WS2) | **PASS — 26 passed, 0 failed, 0 not run** (WS2, `~/workspace/.pwsh/pwsh -NoProfile -File scripts/test-compose-healthcheck-ps-matrix.ps1`, PowerShell 7.4.6 on Linux, 2026-11-12; log `13-ps-matrix-dryrun.log`. Stub docker only; no real Docker. Windows PowerShell 5.1 execution remains NOT RUN — reviewer gate.) |
| CI workflow syntax | **PASS** (WS2, `python3 -c "import yaml; yaml.safe_load(...)"` on `.github/workflows/ci.yml`, 2026-11-12; 4 jobs, 20 scripts-lane steps. GitHub Actions execution itself is NOT RUN — see below.) |
| GitHub Actions execution | **NOT RUN** — no CI run has been observed by the authors; the first real run is the reviewer's. The YAML-valid workflow must never be presented as executed. |
| Compose config check | **PASS** (WS2, `python3 scripts/compose-config-check.py`, 2026-11-12: Compose parses; services keycloak/backend/frontend present; published ports locked to 127.0.0.1:8080/8000/5173; Keycloak image pinned 26.8.2; healthcheck keeps literal `$resp` (2x) with HTTP-200 + issuer greps; `docker compose config` itself NOT RUN without a Docker CLI.) |
| Backend offline (pytest) | **NOT RUN by WS2** — WS1 owns the backend; the full run is for the Pass A coordinator / WS1. (The 2 version tests were moved to 1.7.4 by WS2; the coordinator runs them.) |
| Frontend typecheck / Vitest / build | **All PASS** (WS2, `cd frontend && npm ci` then `npm run typecheck`, `npm test`, `npm run build`, 2026-11-12; logs `22-npm-ci.log`, `23-typecheck.log`, `24-vitest.log`, `25-build.log` in `~/workspace/ws2-v731-evidence/`. `npm ci` rc=0; typecheck `tsc --noEmit` rc=0; Vitest **161 passed** (13 files, rc=0); build rc=0, `index-X2bsjLBG.js` **170.04 kB / 55.20 kB gzip, SHA-256 `a77dd7d52bed856267bf155df61acebbf2ebd2e37d18da34f9862f8e61de67c8`** — byte-identical to the v7.1/v7.2/v7.3 build; the UI is unchanged, as intended — the `Settings.test.tsx` change is mock-only. `node_modules/` and `dist/` were removed afterwards as build artifacts.) |
| Docker Compose boot | **NOT RUN** — reviewer gate on Docker Desktop (historical build environment, 2026-11-12 sandbox, had no Docker binary/socket; see the note under "Built by" above). |
| Windows PowerShell 5.1 execution | **NOT RUN** — 5.1 is Windows-only. PowerShell 7.4.6 on Linux WAS executed (PS matrix dry-run, see above). Reviewer gate. |
| Keycloak healthcheck in-image validation | **NOT RUN** — no Docker in the historical build sandbox. Reviewer gate. |
| Full npm audit | **NOT RUN** — reviewer gate on a machine with registry access. GHSA direct-only is NOT a substitute for it. |
| Mutation test (source-level) | **NOT RUN by design** — source-level mutation testing is forbidden; sensitivity via the designed `omit` mechanism: PASS. |
| Pass B clean extractions | **PASS — three fresh extractions of the actual final ZIP bytes** (parent's Pass C, 2026-11-12): plain `~/workspace/.verify/v731-final-plain`, `~/workspace/.verify/v731 final spaces`, `~/workspace/.verify/data/v731-final-data`. verify-release **22 PASS / 0 FAIL / 6 NOT RUN in all three** — the 6th NOT RUN vs v7.3's first-packaging 23/0/5 is GHSA_DIRECT_FALLBACK flipping back to NOT RUN (advisory source rate-limited, rc=2, 2026-11-12T10:17:00Z/10:17:14Z); GHSA PASSED as a v7.3.1 run the same morning (test-all --offline, 10:12:18Z, 14/14 direct deps, 0 high/critical) and is quota-volatile on the shared egress IP. Docs-contract **PASS from the `data/`-ancestor extraction**. Plain extraction: pytest **397 passed** on the shipped code (import verified to resolve to the extraction, version 1.7.4), CLI **18/18**, docs-contract-paths **33/33**, dependency-gates **55/0**, healthcheck regressions **32/0/2** (02-a/03-a correctly NOT RUN — no baseline tree in a bare extraction), `npm ci` + Vitest **161/161** + build byte-identical (`index-X2bsjLBG.js`, SHA-256 `a77dd7d5…`). ZIP integrity: testzip clean, 0 forbidden entries, 131 screenshots, all 19 `.sh` entries mode 0770, `scripts/test-compose-healthcheck.ps1` + `scripts/test-compose-healthcheck-ps-matrix.ps1` present, no egg-info, no `.db`/`.pem`/`.key`/`.p12` inside. |
| verify-release (fresh extraction) | **22/0/6 in all three extractions** (see row above). |

### Measured results (coordinator Pass A, v7.3.1)

Coordinator's own runs, 2026-11-12 (evidence `~/workspace/passa-v731-evidence/`).

| Gate | Result |
| ---- | ------ |
| Backend pytest | **397 passed, 2 warnings**, rc=0 (124.80 s; v7.3 venv python + `PYTHONPATH=v7.3.1/backend/src`, import verified → v7.3.1 tree, 1.7.4). |
| Healthcheck regressions | **34/0/0 rc=0 ×3** (live stack UP); CI-shape (no sibling baseline) **32/0/2 rc=0** (02-a/03-a honestly NOT RUN). 04-a PASS in every run. |
| PS matrix | **26/0/0 rc=0** (pwsh 7.4.6, `pwsh -File`). PS default controls: no-static rc=**1** ENVIRONMENT NOT READY 0/0/4; normal rc=**0** 1/0/3. |
| Version contract (real tree) | **PASS 1.7.4**; fixtures **13/13**. |
| Docs-contract / paths | **PASS, 0 violations**; paths **33/33** (planted stale v7.3 FINAL fails with exactly 2 violations, rc=1). |
| `test-all.sh --offline` | **rc=0, 10 PASS / 0 FAIL / 8 NOT RUN** (18 gates). NOT RUN: NPM_FULL_LOCKFILE_AUDIT (registry proxy 403), GHSA_DIRECT_FALLBACK (rate-limited, remaining=0, resets 10:11:27 UTC), + 6 full-profile gates. pip-audit clean 2.10.1. |
| Dependency-gates | **55/0** both layouts (system Node; NVM-style with `/usr/bin/node` hidden via unshare bind-mount). First layout-2 attempt read 52/3 while `test-all.sh --offline` ran concurrently in the same tree (shared `test-results/`); two sequential re-runs read 55/0 — harness interference, not a product defect. |
| Live gate (real Keycloak) | `all` **101/101 PASS**; `reset` **69/69 PASS** (disposable marker backend, temp DB; marker `cd794978-1007-43e5-b875-f9224173574e`, health 1.7.4; post-reset 1 txn / 7 events / observed 1 / verified 1 / incomplete 0). Dev backend restored by exact PID (marker uvicorn PID 11877 via `ss -ltnp`); counts byte-identical to pre-swap snapshot (runs 36, all live counters 0 — fresh dev DB in this clean tree) with no marker field. Guard negatives re-verified: no-flag rc=2, wrong-id rc=1, malformed rc=2. |
| Playwright (live host stack) | **71 passed + 1 skipped** (3.4 m), validator **PASS** (target `host-lab`; 1 skip = allowed edge-case cancel), axe **25/25, 0 violations** from the real report JSON; **131 PNGs re-rendered fresh** (same filenames; UI unchanged, build hash identical). |
| CI YAML | Syntax PASS (python yaml; 4 jobs, 20 scripts-lane steps; regressions at line 239, matrix at line 251). **GitHub Actions execution NOT RUN.** |

## Operation Trustline v8 — full adversarial penetration test + remediation (2026-11-12)

> Every row below is filled from the measured runs in
> `docs/VERIFICATION_LOG.md` (v8 section) — never from memory, and
> never in advance. No v7.3.1 figure is copied forward as a v8 result.
> Status words in this section are exactly PASS / FAIL / NOT RUN /
> NOT APPLICABLE. v8 is a full adversarial penetration test of the
> entire IdentityForge app with immediate in-place remediation, a
> premium-finish pentest report set, the version bump to **1.8.0**,
> and the stale-prose fix subsuming the pending v7.3.2 choice (four
> lines). The release label is v8 and the product version is **1.8.0**.
> Workstreams: WS1 (backend), WS2 (frontend/E2E), WS3 (depth /
> property-testing + pentest report docs + version bump + stale-prose
> fix — this section's docs rows are WS3's).

- **Release name:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V8_FINAL_20261113.zip`
- **Version:** 1.8.0 (Operation Trustline v8 — full adversarial penetration test + remediation)
- **Date:** 2026-11-12 (ISO 8601)
- **Built from:** working tree at `~/workspace/identityforge-v8`
  (no git repository was used for this build; no commit SHA exists)
- **Built by:** Linux sandbox, Python 3.12.3, Node 24.22.1, npm 10.9.4.
  PowerShell 7.4.6 on Linux (`~/workspace/.pwsh/pwsh`) WAS executed here;
  Windows PowerShell 5.1 was NOT.
  **Historical build environment (2026-11-12 sandbox):** no Docker
  binary or socket existed in that build sandbox — the shipped
  `docker compose up` path was NOT RUN there. This describes the
  historical build sandbox only, never the end user's runtime state.

### Archive (file count from the tree; size/SHA-256 in the delivery message)

- **Filename:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V8_FINAL_20261113.zip`
- **Size (bytes) and SHA-256:** not printed inside the archive — either value is a property of the ZIP file itself, so printing it here would change it. Check the delivery message for the SHA-256 of the shipped file, and verify with `ls -l` / `sha256sum <archive>` on Linux/macOS or `Get-FileHash <archive> -Algorithm SHA256` on Windows.
- **File count:** **352** (verified from the shipped ZIP's namelist; 333 in v7.3.1 + 19 new: 3 adversarial test files, 5 pentest report docs, 1 security-headers spec, 10 pentest scripts/docs; 0 removed)
- **Archive verified by:** parent's Pass C — three fresh extractions of the actual final ZIP bytes (plain `~/workspace/.verify/v8-final-plain`, `~/workspace/.verify/v8 final spaces`, `~/workspace/.verify/data/v8-final-data`); see the Pass C row below.

### Scope (WS3 — depth / pentest docs / version / stale prose)

| Area | Change |
| ---- | ------ |
| Version (`backend/src/identityforge/__init__.py`, `backend/pyproject.toml`, `frontend/package.json` + `frontend/package-lock.json`) | Single-source bump to **1.8.0** — release label v8, product version 1.8.0. FastAPI metadata and `/api/v1/health` derive from `__version__` (unchanged design). Lockfile synced via `npm install --package-lock-only`, never hand-edited. Version-contract machinery moved to v8: `scripts/check-version-contract.py` now reads the Trustline v8 manifest section and expects 1.8.0 by default; `scripts/test-version-contract.sh` fixtures at 1.8.0 (Python literal replaces, not sed — the sed-escaping trap hit v7.2/v7.3). Test-only version assertions in `backend/tests/integration/test_v6_backend_api.py` (7 occurrences) and the frontend `Settings.test.tsx` `/health` mocks (3×) moved to 1.8.0 — plus a fourth `Settings.test.tsx` occurrence, the About-version assertion `/1\.7\.4/` → `/1\.8\.0/`, which the first `test-all.sh --offline` FRONTEND_UNIT failure exposed (regex-escaped, same trap as IF-V8-81). The version labels in `scripts/test-all.sh` and `scripts/verify-release.sh` moved to 1.8.0. |
| Stale prose (4 lines, subsumes the pending v7.3.2 choice) | `docs/REVIEWER_GUIDE.md:38` and `docs/WINDOWS_SETUP.md:99` now name the v8 final release under the Get-FileHash commands (the v7.3.1 name is now stale); `docs/REVIEWER_GUIDE.md:492` and `docs/WINDOWS_SETUP.md:317` now say release version **1.8.0** (was 1.7.3). Historical 1.7.3 mentions in `docs/RELEASE_MANIFEST.md` and `docs/VERIFICATION_LOG.md` history sections are CORRECT and unchanged. New docs-contract regression (check 6 in `scripts/validate-docs-contract.py`, exercised by new cases in `scripts/test-docs-contract-paths.sh`): quickstart/hash-check prose must not name an older release version/label, and any "release version X.Y.Z" prose must equal the manifest's current version. Proven failing-first (stale lines planted, check fails) and passing-after. |
| Depth tests (`scripts/pentest/ws3/`) | Hypothesis property tests (24 tests post-fix: audience-policy oracle, redirect-URI exactness, issuer/JWKS-URL SSRF matrix, transport-rewrite provenance, JWKS bounds, PKCE, ID-token tamper matrix, 500-case seeded malformed-token corpus, plus the IF-V8-01 trailing-slash and IF-V8-03 rewrite-reject regression tests); differential secure-vs-flawed tests (12 tests, every omitted check proven load-bearing); negative controls (corrupted-fixture subprocess controls); fault injection + concurrency + malformed-input corpus (15 tests: fake-IdP malformed/timeout/short-read/truncated-chunked, SQLite failure modes incl. RLIMIT_FSIZE ENOSPC-like, two-callbacks-one-state, concurrent save/read/reset with integrity_check, 200-request malformed corpus + 12 malformed POST bodies); stateful live sequence (55 checks: real Keycloak login → replay → logout → stale 401 → officer identity switch → reset negatives → evidence retention + redaction scan; in-process expiry via injectable clock + positive officer reset). Hypothesis 6.170.15 in a disposable venv; no source-level mutation testing. |
| Pentest report docs (`docs/`) | NEW `docs/FINAL_ADVERSARIAL_PENETRATION_TEST_REPORT.md`, `docs/PENTEST_ATTACK_SURFACE_AND_THREAT_MODEL.md`, `docs/PENTEST_TEST_MATRIX.md`, `docs/PENTEST_FINDINGS_AND_REMEDIATIONS.md`, `docs/PENTEST_TEST_EVIDENCE_INDEX.md`; updated `docs/SECURITY_ASSESSMENT.md`, `docs/VERIFICATION_LOG.md`, `docs/VALIDATION_AND_LIMITATIONS.md`, `docs/RELEASE_MANIFEST.md` (this section), `docs/REVIEWER_GUIDE.md`, `docs/WINDOWS_SETUP.md`, `README.md`, `SECURITY.md` where necessary. WS1/WS2 findings collected from `~/workspace/ws1-v8-evidence/` and `~/workspace/ws2-v8-evidence/`; TBD rows filled before delivery. Finding IDs IF-V8-80 and up (WS3 range). |
| Attack scripts (`scripts/pentest/ws3/`) | Sanitized minimal repro scripts with strict local-only guardrails, stable seeds, and a README; run ONLY against disposable synthetic test instances, never default to arbitrary Internet hosts, never delete user data. |

### Measured results (WS3, v8)

| Gate | Result |
| ---- | ------ |
| Version contract (fixtures) | **PASS — 13/13 on the second clean run.** First clean run 8/13 (IF-V8-81 — five vacuous negatives holding the sed-escaped `1\.7\.4`); fixed with Python literal replaces; second clean run 13/13 (`version-fixtures-v8-run2.log`). |
| Version contract (real tree) | **PASS — all authoritative versions equal 1.8.0** (manifest v8 section, pyproject, `__init__`, FastAPI + health via `__version__`, package.json + lockfile). |
| Docs-contract (real tree) | **PASS — 0 violations** (34 FailureReason values, 59 report-model fields, 119 source files harvested, 64 files scanned; `docs-contract-v8-clean.log`). |
| Docs-contract paths | **PASS — 42/42** (was 33/33; +3 check-6 cases (l)/(m)/(n); `docs-contract-paths-v8.log`). |
| Property tests (Hypothesis) | **PASS — 24 tests** (Hypothesis 6.170.15, derandomized, seed `random.Random(20261112)`; first run 5 failed — all WS3 harness bugs; second run 22 passed; post-WS1-fix re-run 24 passed with the IF-V8-01/03 regression tests; `ws3-suites-postfix2.log`). |
| Differential + negative controls | **PASS — 12 tests** (every omitted check proven load-bearing; corrupted-fixture subprocess controls fail as required). |
| Fault injection / concurrency / malformed corpus | **PASS — 15 tests** (first run 5 failed — harness bugs + one wrong expectation; second run 15 passed; post-WS1-fix re-run 15 passed with the IF-V8-05 `ValueError` expectation). |
| Stateful live sequence | **PASS — 55/55 checks** (first run 5 failed — WS3 script bugs; second run 55 passed; `stateful-live-sequence-run2.log`). |
| Extra live probes | **PASS — 0 failed on run 3** (runs 1–2 failed on the transient login-start 503 capacity window, IF-V8-82; run 3 post-recovery `extra-live-probes-run3.log`). |
| Backend offline (pytest) | **PASS — 482 passed, 0 failed, sequentially, twice independently.** WS1 `full-pytest-postfix-final.txt` (02:52 UTC): 482 passed, 3 warnings in 83.48s. WS3 `pytest-full-sequential-ws3.log` (~02:55 UTC): rc=0, 482 collected. The earlier concurrent-run 431/51 was a concurrency artifact of three login-heavy suites sharing the live backend's 20-slot transaction store (TBD-WS1-03, RESOLVED). |
| Frontend typecheck / Vitest / build | Typecheck **PASS**; Vitest **161/161** (WS2 baseline + postfix); build **byte-identical to v7.1/v7.2/v7.3** (`index-X2bsjLBG.js`, 170.04 kB / 55.20 kB gzip, SHA-256 `a77dd7d5…`) — UI unchanged. |
| Playwright / axe / screenshots | **RESOLVED as a concurrency artifact (IF-V8-45, Pass B; clean validator PASS in parent's Pass C)** — postfix run 1: 60 passed / 12 failed / 1 skipped; portal re-run 8/8 passed; screenshots re-run 22 passed / 8 failed; single 320x740 passed alone. Failures track the transaction-store saturation window (IF-V8-82), not a stable product defect. Pass B: pre-fix full run failed exactly one test (IF-V8-84, fixed); post-fix edge spec **8/8** isolated; second full run reached **53 passed + 1 skipped** (a11y 25/25, edge 8/8, portal 8/8) before Chromium died mid-screenshots. A clean single-report validator PASS was **NOT RUN in Pass B** — Chromium could not launch in the sandbox then (SIGTRAP/SIGILL, the same sandbox event that blocked all file writes). **Parent's Pass C (2026-11-13, after the sandbox recovered): full Playwright 72 passed + 1 skipped, rc=0; validator PASS on the single report (total 73, passed 72, failed 0, skipped 1).** Axe **25/25, 0 violations** (WS2 baseline + postfix + Pass B partial run + Pass C full run). |
| `test-all.sh --offline` | **PASS — rc=0, 11 PASS / 0 FAIL / 7 NOT RUN** (`test-all-offline-v8-run3.log`, 03:01:14Z): OFFLINE_UNIT PASS (pytest 482 + ruff clean), FRONTEND_UNIT PASS (161/161), GHSA PASS (14 direct, 0 high/critical — advisory data cached from 02:57:18Z). NOT RUN: NPM_FULL (blocked, registry 403) + 6 full-profile gates. pip-audit clean 2.10.1. (Run1 rc=1: OFFLINE_UNIT 51 pytest concurrent artifact + FRONTEND_UNIT 1 Settings test; run2 rc=1: OFFLINE_UNIT at `ruff format --check`, IF-V8-83.) |
| Parent's Pass C (2026-11-13, final tree, own runs) | **PASS — all gates re-run on the final tree after the sandbox write block lifted (06:10 UTC).** pytest **482 passed, 3 warnings**; CLI **18/18**; ruff check + format clean (66 files); version-contract PASS 1.8.0; docs-contract PASS; docs-contract-paths **42/42**; dep-gates **55/0**; test-all --offline **11/0/7 rc=0** (GHSA PASS on cached data, 14 direct, 0 high/critical); healthcheck regressions **34/0/0**; PS matrix **26/0/0**, PS default 1/0/3; live gate `all` **101/101** + `reset` **69/69** (disposable marker backend, temp DB; dev live-login counters byte-identical on restore: runs 253, live events 997, txns 191, observed/verified 138, incomplete 50); guard negatives no-flag rc=2 / wrong-id rc=1 / malformed rc=2; full Playwright **72 passed + 1 skipped, rc=0**, validator **PASS** (total 73, passed 72, failed 0, skipped 1), axe **25/25, 0 violations**; typecheck PASS; Vitest **161/161**; build byte-identical (`a77dd7d5…`). Pass C also found and fixed one release-gate issue: verify-release `NO_INTERNAL_ISSUER` failed on the first packaging because the two new pentest SSRF negative tests name `http://keycloak:8080` as a *rejected* JWKS URL — the gate now exempts those two files by the same precedent as the transport tests, with the rationale documented in `scripts/verify-release.sh`. |
| GHSA direct-deps fallback | **PASS — 14/14 direct deps, 0 high/critical** (run3, advisory data cached from 2026-11-13T02:57:18Z). Earlier runs: INCOMPLETE/NOT RUN (3 packages unreachable, quota-volatile). |
| Docker Compose boot | **NOT RUN** — reviewer gate on Docker Desktop (no Docker binary/socket in the build sandbox). |
| Windows PowerShell 5.1 execution | **NOT RUN** — 5.1 is Windows-only. PowerShell 7.4.6 on Linux executed where noted. Reviewer gate. |
| Keycloak healthcheck in-image validation | **NOT RUN** — no Docker in the build sandbox. Reviewer gate. |
| Full npm audit | **NOT RUN** — reviewer gate on a machine with registry access. GHSA direct-only is NOT a substitute for it. |
| Mutation test (source-level) | **NOT RUN by design** — source-level mutation testing is forbidden; sensitivity via the designed `omit` mechanism: PASS. |

## Operation Trustline v8.0.1 — targeted documentation closure (2026-11-13)

> Every row below is filled from the measured runs in
> `docs/VERIFICATION_LOG.md` (v8.0.1 section) — never from memory, and
> never in advance. No v8 figure is copied forward as a v8.0.1 result.
> Status words in this section are exactly PASS / FAIL / NOT RUN /
> NOT APPLICABLE. v8.0.1 is a NARROW documentation/security-evidence
> closure of the v8 pentest, NOT a second pentest: it completes the
> final report's Pass C section (§M), reconciles every "fill before
> delivery" note in the pentest evidence index and test matrix, adds
> the missing IF-V8-84 row to the final report's findings table,
> corrects the README's stale active test/gate counts (340 → 491
> tests, 16 → 18 gates) with a new docs-contract regression (check 7),
> and carries the 1.8.1 version bump. The release label is v8.0.1 and
> the product version is **1.8.1**. No product code changed, no test
> removed, no view added or removed, and IF-V8-42/43 stay OPEN (see
> the reviewer checklists in the findings register).
> Workstreams: WS1 (docs + version bump + check 7) and WS2 (IdP-cap
> streaming + WS3 CI wiring + Hypothesis pin); the parent's Pass C
> re-ran every gate on the final tree (see the Pass C rows).

- **Release name:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V8.0.1_FINAL_20261113.zip`
- **Version:** 1.8.1 (Operation Trustline v8.0.1 — targeted documentation closure)
- **Date:** 2026-11-13 (ISO 8601)
- **Built from:** working tree at `~/workspace/identityforge-v8.0.1`
  (no git repository was used for this build; no commit SHA exists)
- **Built by:** Linux sandbox, Python 3.12.3, Node 24.22.1, npm 10.9.4.
  PowerShell 7.4.6 on Linux (`~/workspace/.pwsh/pwsh`) WAS executed
  in the parent's Pass C (healthcheck PS matrix 26/0/0); Windows
  PowerShell 5.1 was NOT (5.1 is Windows-only).
  **Historical build environment (2026-11-13 sandbox):** no Docker
  binary or socket existed in that build sandbox — the shipped
  `docker compose up` path was NOT RUN there. This describes the
  historical build sandbox only, never the end user's runtime state.
- **Counts (current release):** backend pytest 491; test-all gates 18.

### Archive (file count from the tree; size/SHA-256 in the delivery message)

- **Filename:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V8.0.1_FINAL_20261113.zip`
- **Size (bytes) and SHA-256:** not printed inside the archive — either value is a property of the ZIP file itself, so printing it here would change it. Check the delivery message for the SHA-256 of the shipped file, and verify with `ls -l` / `sha256sum <archive>` on Linux/macOS or `Get-FileHash <archive> -Algorithm SHA256` on Windows.
- **File count:** **364 files** (v8's 352 + 12 new — 10 in `docs/pentest-evidence/` (the verified excerpt bundle), `backend/tests/fake_http.py` (WS2's stream-fake seam), and `backend/requirements-test.txt` (the pinned Hypothesis test-only dependency); 0 removed). Tree count by the packager's exclusion shape (caches, venvs, `node_modules`, `dist`, `test-results`, `*.db`, `.hypothesis`, `egg-info` excluded); confirmed by the parent at packaging from the final ZIP's namelist. [Parent's Pass C correction: WS1's row stated 363 — it counted only 11 new files and missed `backend/requirements-test.txt`. The draft ZIP's namelist gives 364.]
- **Archive verified by:** parent's Pass C — three fresh extractions of the actual final ZIP bytes (plain, path with spaces, path under an ancestor literally named `data/`), `verify-release.sh` rc=0 in all three; see the Pass C row below.

### Scope (WS1 — docs closure / version / check 7)

| Area | Change |
| ---- | ------ |
| Version (`backend/src/identityforge/__init__.py`, `backend/pyproject.toml`, `frontend/package.json` + `frontend/package-lock.json`) | Single-source bump to **1.8.1** — release label v8.0.1, product version 1.8.1 (a patch on the 1.8.0 line). FastAPI metadata and `/api/v1/health` derive from `__version__` (unchanged design). Lockfile synced via `npm install --package-lock-only`, never hand-edited (only the two root version fields changed; no dependency changed). Version-contract machinery moved to v8.0.1: `scripts/check-version-contract.py` now reads the Trustline v8.0.1 manifest section and expects 1.8.1 by default; `scripts/test-version-contract.sh` fixtures at 1.8.1 (plain + sed-escaped `1\\.8\\.1` literals both moved — the IF-V8-81 escaping trap). Test-only version assertions in `backend/tests/integration/test_v6_backend_api.py` (7 occurrences: module docstring, both test docstrings, `__version__`, pyproject, FastAPI `app.version`, health assertions; test function names stay `1_7_4`, the v8 precedent) and the frontend `Settings.test.tsx` `/health` mocks (3×) + the About-version assertion `/1\\.8\\.0/` → `/1\\.8\\.1/` moved to 1.8.1. The version labels in `scripts/test-all.sh` and `scripts/verify-release.sh` moved to 1.8.1. |
| Final report (`docs/FINAL_ADVERSARIAL_PENETRATION_TEST_REPORT.md`) | §M: the pre-delivery "TBD — parent's Pass C" note replaced with the actual v8 Pass C evidence, read from the Pass C logs in `~/workspace/passc-v8-evidence/` (see §M for the log filenames behind every number). §L: the "Viewport probe: fill before delivery" note replaced with the measured probe outcome (36/36 routes × widths, no overflow — `viewport-probe.log`); the concurrent-run screenshot failures stay recorded as history, the final state is the Pass C full run (72 passed + 1 skipped, validator PASS). §E summary table: the missing IF-V8-84 row added (test defect, FIXED) — the table now has all 16 findings and agrees exactly with the register and the §P verdict (11 FIXED, 2 OPEN, 2 intended/documented, 1 resolved concurrency artifact). No pentest result changed: every number in §M/§L is a v8 Pass C measurement, not a v8.0.1 re-run. |
| Evidence index + test matrix (`docs/PENTEST_TEST_EVIDENCE_INDEX.md`, `docs/PENTEST_TEST_MATRIX.md`) | All three "(TBD — fill before delivery)" rows replaced with measured outcomes read from the cited logs: IdP-capability suite (first run 3 failed / 4 passed failing-first, second run 7 passed), viewport probe (36 checks, 0 overflow), probe-evidence helper (metachar save OK, oversize rejected, 200-run concurrency + retention caps). Test matrix §7: healthcheck regressions and PS matrix re-runs no longer "TBD in v8" — parent's Pass C confirms **34/0/0** and **26/0/0** (`regressions-passc.txt`, `ps-matrix-passc.txt`). Raw build logs are NOT shipped in the ZIP (they live outside the archive); a small verified excerpt bundle is shipped instead — see `docs/pentest-evidence/README.md`. Every excerpt in the bundle was read and verified by WS1; anything not verified is marked NOT SHIPPED, never paraphrased as a log. |
| README counts + docs-contract check 7 (`README.md`, `scripts/validate-docs-contract.py`, `scripts/test-docs-contract-paths.sh`) | README `## Tests`: "backend offline suite (340 tests" → **491** (482 was the v8 baseline; WS2's streaming work adds 9 tests, so the v8.0.1 suite is 491 — parent's Pass C correction, verified by the parent's own 491-passed run); "16 explicit gates" → **18**, and the gate list now names all 18 (DOCS_CONTRACT_PATHS and VERSION_CONTRACT were missing). New docs-contract regression (check 7): the README's active `## Tests` counts must agree with the current release — the pytest count against this section's `**Counts (current release):**` line, the gate number against the listed IDs and against the gate IDs the runners define (`scripts/test-all.sh` + `scripts/audit-gates.sh` call sites, 15 + 3 = 18). Only the `## Tests` region is scanned, so the dated release-history bullets below it (which legitimately name old counts like 340/397 in historical context) still pass. Proven failing-first (planted 340/16 counts fail) and passing-after; the paths suite grows 42 → **48 checks** (new cases (o)/(p) × 3 paths). The parent re-verified check 7 on the final tree: planted 340/16 → FAIL with the exact violation, restored byte-identical, clean → PASS. |
| Findings register (`docs/PENTEST_FINDINGS_AND_REMEDIATIONS.md`) | IF-V8-42 and IF-V8-43 stay **OPEN**. Each now carries a safe reviewer checklist stating exactly what the reviewer must observe before closing (Docker boot + volume-permission regression checks against the final image for 42; upstream SHA verification + an observed CI run for 43). No Docker/CI pass is claimed. IF-V8-84's register entry gains its Pass C closure: the full Playwright run (72 passed + 1 skipped, validator PASS) is the clean single-report pass that was NOT RUN in Pass B. |
| IdP response-size cap → bounded streaming (WS2, `backend/src/identityforge/protocol/jwks.py`, `backend/tests/fake_http.py`) | Required B, DECISION: STREAMING IMPLEMENTED. The v8 1 MiB acceptance cap ran after `httpx.get/post` had downloaded the whole response; all four fetchers (`fetch_jwks`, `fetch_jwks_via_transport`, `post_token_via_transport`, `fetch_discovery_via_transport`) now read via `httpx.stream` + `iter_bytes` in 64 KiB pieces with a 1 MiB+1 early stop, and the declared `Content-Length` is checked before any body byte. SSRF/issuer/transport guards untouched (`trust_env=False`, `follow_redirects=False` at the call site — verified by the parent's grep). Reproduction first: pristine v8 code rejected 5 MiB stub bodies only after the stub wrote the full 5.0 MiB (tracemalloc peak ~10.0 MiB); after streaming, all 14 enumerated stub cases green (declared-vs-actual ×2, chunked, paced chunked — stub wrote 1.125 MiB vs 5.001 MiB pristine — no-Content-Length, massive single chunk — peak 1.49 vs 10.04 MiB — early EOF, truncated chunked `RemoteProtocolError`, redirect-to-big never fetched, timeout ×2, slow-steady documented, normal Keycloak discovery/JWKS/token). One disclosed precedence change: declared->1 MiB + truncated body now raises `ValueError: size limit` instead of `RemoteProtocolError` (both are controlled `PROVIDER_ERROR` at the app layer; pinned by a new test). Test seam migrated `httpx.get/post` → `httpx.stream` via new `backend/tests/fake_http.py` (`install_stream_fake`); 38 monkeypatch sites across 11 test files migrated; **9 new tests** (idp-caps file 16/16). Full backend suite is now **491** (482 + 9). |
| WS3 51 tests + Hypothesis pin (WS2, `backend/requirements-test.txt`, `backend/pyproject.toml`, `scripts/pentest/ws3/README.md`) | Required C. Pin: `hypothesis==6.170.15` + `sortedcontainers==2.4.0` in the new test-only `backend/requirements-test.txt`, mirrored in `pyproject.toml` dev extras; the runtime freeze is untouched (Hypothesis is never shipped, audited, or imported by the app). One-command independent offline run documented in `scripts/pentest/ws3/README.md` (disposable venv from the freeze + test pins, then the three WS3 files) — the parent ran it verbatim: **51 passed (24 + 12 + 15), rc=0** (hypothesis 6.170.15 / pytest 9.0.3). The 51 are NOT part of the 491-test backend suite (`testpaths = ["tests"]` never collects them) and the counts are kept separate everywhere. |
| WS3 CI lane (WS2, `.github/workflows/ci.yml`) | Required C. New step in the `scripts` job (installs freeze + test pins, runs the three WS3 files, honest NOT RUN scope, counts kept separate: backend 491, WS3 51). YAML valid (4 jobs); GitHub Actions execution NOT RUN. The frontend security-headers Playwright spec runs under `npm run test:e2e` in the `keycloak-e2e` lane and the WS2 11-check static suite is already in the scripts lane — both re-verified live by WS2 (11/11 PASS; spec 1 passed against `vite preview`), no CI change needed. |
| Quickstarts (`docs/REVIEWER_GUIDE.md`, `docs/WINDOWS_SETUP.md`) | Mechanical version-bump consequence, same class as the v7.3.1 delivery: the hash commands now name the v8.0.1 final archive (check 5), and the "release version" prose now says **1.8.1** (check 6b). Four lines changed in each guide's quickstart region; historical 1.8.0 mentions elsewhere are v8 history and unchanged. |
| Verify-release count correction (`docs/VERIFICATION_LOG.md`, v8 Pass C row) | WS1's recount of the Pass C `verify-release` summary tables in `~/workspace/passc-v8-evidence/` gives **23 PASS / 0 FAIL / 5 NOT RUN** (28 checks) in each clean extraction — not the 20/0/5 the v8 row stated. The v8 row is corrected to 23/0/5 with a correction note; the 5 NOT RUN names are unchanged (BACKEND_PYTEST, FRONTEND_BUILD, COMPOSE_CONFIG, PYTHON_DEPENDENCY_AUDIT, NPM_FULL_LOCKFILE_AUDIT). The first plain extraction's 22/1/5 (NO_INTERNAL_ISSUER FAIL before the re-pack exemption fix) is unchanged history. |

### Measured results (WS1, v8.0.1)

| Gate | Result |
| ---- | ------ |
| Version contract (fixtures) | **PASS — 13/13** (WS1, `bash scripts/test-version-contract.sh`, 2026-11-13; fixtures at 1.8.1, plain + sed-escaped `1\\.8\\.1` literals both moved; all-agree PASS, `__version__`-derivation PASS + negative, one-source-differs FAILS for every source, missing-source FAILS, malformed `--expected` FAILS. First run 11/13: the fixture manifest heading still said "Trustline v8" — fixed, second run 13/13. Log `version-fixtures-v801-rerun.log`.) |
| Version contract (real tree) | **PASS — all authoritative versions equal 1.8.1** (WS1, `python3 scripts/check-version-contract.py`, 2026-11-13; manifest v8.0.1 section, pyproject, `__init__`, FastAPI + health via `__version__`, package.json + lockfile. Failing-first: rc=2 before the manifest section existed, all code sources already at 1.8.1. Log `version-contract-v801.log`.) |
| Docs-contract (real tree) | **PASS — 0 violations** (WS1, `python3 scripts/validate-docs-contract.py`, 2026-11-13; 34 FailureReason values, 59 report-model fields, 122 source files harvested, 69 files scanned. Failing-first on the stale README: 5 violations, rc=1 — check 6a twice (guides §0/§3 "v8 final release name") + check 7 three times (340 tests, 16 gates, 2 missing gate names); clean tree PASS rc=0 after the fixes. Logs `docs-contract-check7-failing-first.log`, `docs-contract-check7-clean.log`. The `test-all.sh --offline` DOCS_CONTRACT gate also PASSED with 0 violations.) |
| Docs-contract paths | **PASS — 48/48** (was 42/42; +2 check-7 cases (o)/(p) × 3 paths. Case (o) plants stale active README counts → checker fails rc=1; case (p) proves current counts + old-count history pass. Log `docs-contract-paths-v801.log`.) |
| Backend offline (pytest) | **PASS — 482 passed, 0 failed** (WS1, `pytest -q` in `backend/`, 2026-11-13 08:09 UTC, v8 venv with `PYTHONPATH=src` so the import resolves to this tree at 1.8.1; JUnit report `pytest-v801.xml`: testsuite tests="482" failures="0" errors="0" skipped="0", 482 testcase elements, rc=0 — the terminal summary line is missing in the captured log, the known sandbox capture artifact also seen in v8. Both version tests pass. Ruff check + format clean at the same time (66 files). **Caveat:** this run predates WS2's concurrent `jwks.py` streaming edit (08:15 UTC, IdP-cap work — not WS1's); the parent's Pass C must re-run pytest on the final tree after WS2 lands.) |
| Frontend typecheck / Vitest / build | Typecheck **PASS**; Vitest **161/161** (WS1, `npm ci` + `npm test -- --run`, 2026-11-13; includes the `Settings.test.tsx` version mocks + About assertion at 1.8.1); build **byte-identical to v8** (`index-X2bsjLBG.js`, 170.04 kB / 55.20 kB gzip, SHA-256 `a77dd7d5…` — same hash as v7.1/v7.2/v7.3/v8). Logs `typecheck-v801.log`, `vitest-v801.log`, `build-v801.log`. |
| Scenario CLI | **PASS — 18/18** (WS1, `python -m identityforge.cli verify-all`, offline fixture mode. Log `cli-v801.log`.) |
| `test-all.sh --offline` | **rc=1 — 10 PASS / 1 FAIL / 7 NOT RUN** (WS1, 2026-11-13 08:14–08:16 UTC; log `test-all-offline-v801.log`). The single FAIL is OFFLINE_UNIT at `ruff format --check`: `src/identityforge/protocol/jwks.py` "would be reformatted" — WS2's concurrent in-flight streaming edit (modified 08:15:50 UTC, during this run; the v8 ZIP's `jwks.py` is format-clean under the project config, and WS1's own ruff check at 08:05 passed 66 files). WS1 did not touch that file and did not reformat it. **Re-run required after WS2 lands** (format the file, then re-run `test-all.sh --offline`); the parent's Pass C covers the final tree. All other gates PASSED, including DOCS_CONTRACT, DOCS_CONTRACT_PATHS (48), VERSION_CONTRACT, FRONTEND_* (typecheck/unit/build), PYTHON_DEPENDENCY_AUDIT (pip-audit 2.10.1 clean), GHSA_DIRECT_FALLBACK, COMPOSE_CONFIG. NOT RUN: NPM_FULL (blocked, registry 403) + 6 full-profile gates. |
| `verify-release.sh` (clean copy) | **PASS — 23 PASS / 0 FAIL / 5 NOT RUN, rc=0** (WS1, on a clean copy of this tree simulating an extraction, 2026-11-13; log `verify-release-v801-clean.log`). The 5 NOT RUN are the bare-extraction deps/Docker checks (same five as v8 Pass C). A first run on the dirty working tree failed FORBIDDEN_FILES on `backend/data/identityforge.db` — a DB created by WS1's own CLI run, removed afterwards; the shipped tree contains no `.db`. |
| Docker Compose boot | **NOT RUN** — reviewer gate on Docker Desktop (no Docker binary/socket in the build sandbox). |
| Windows PowerShell 5.1 execution | **NOT RUN** — 5.1 is Windows-only. Reviewer gate. |
| Keycloak healthcheck in-image validation | **NOT RUN** — no Docker in the build sandbox. Reviewer gate. |
| Full npm audit | **NOT RUN** — reviewer gate on a machine with registry access. GHSA direct-only is NOT a substitute for it. |
| Mutation test (source-level) | **NOT RUN by design** — source-level mutation testing is forbidden; sensitivity via the designed `omit` mechanism: PASS. |

### Measured results (parent's Pass C, v8.0.1)

| Gate | Result |
| ---- | ------ |
| Backend offline (pytest) | **PASS — 491 passed, 3 warnings, rc=0** (parent, `pytest` in `backend/`, 100.87s, import verified to resolve to this tree at 1.8.1; 482 v8 baseline + 9 new streaming tests). |
| WS3 51 (separate) | **PASS — 51 passed (24 + 12 + 15), rc=0** (parent, the documented one-command run verbatim in a disposable venv from the freeze + test pins: hypothesis 6.170.15 / pytest 9.0.3, 33.31s). Never added to the 491. |
| Scenario CLI | **PASS — 18/18** (parent, `python -m identityforge.cli verify-all`, offline fixture mode). |
| Ruff | **Clean** (parent: `ruff check` all checks passed; `ruff format --check` 67 files already formatted). |
| Frontend typecheck / Vitest / build | Typecheck **PASS**; Vitest **161/161** (13 files); build **byte-identical to v8** (`index-X2bsjLBG.js`, 170.04 kB / 55.20 kB gzip, SHA-256 `a77dd7d5…`). |
| Version contract / docs-contract / docs-contract-paths | **PASS 1.8.1** / **PASS, 0 violations** / **48/48** (parent, final tree). Check 7 re-verified by the parent: planted 340/16 → FAIL with the exact violation, restored byte-identical, clean → PASS. |
| Dependency gates | **PASS — 55/0** (parent). |
| `test-all.sh --offline` | **PASS — rc=0, 11 PASS / 0 FAIL / 7 NOT RUN** (parent; GHSA_DIRECT_FALLBACK PASS on direct-only data; NPM_FULL_LOCKFILE_AUDIT NOT RUN — registry 403). |
| Healthcheck regressions / PS matrix | **34/0/0** / **26/0/0** (parent; pwsh 7.4.6 on Linux). |
| Live gate / Playwright | **Live gate `all` 101/101 + `reset` 69/69** (disposable marker backend, temp DB; dev counters byte-identical on restore); guard negatives 2/1/2. **Full Playwright 72 passed + 1 skipped**, validator **PASS**, axe **25/25, 0 violations**. |
| Docker Compose boot / Windows PowerShell 5.1 / in-image Keycloak healthcheck / full npm audit | **NOT RUN** — reviewer gates (no Docker in the build sandbox; 5.1 is Windows-only; npm audit registry 403). |
| Mutation test (source-level) | **NOT RUN by design** — source-level mutation testing is forbidden; sensitivity via the designed `omit` mechanism: PASS. |


## Operation Trustline v8.0.2 — offline pytest + current-release report (2026-11-13)

> Every row below is filled from the measured runs in
> `docs/VERIFICATION_LOG.md` (v8.0.2 section) — never from memory, and
> never in advance. No v8 or v8.0.1 figure is copied forward as a
> v8.0.2 result. Status words in this section are exactly PASS / FAIL /
> NOT RUN / NOT APPLICABLE. v8.0.2 is a NARROW targeted patch on the
> delivered v8.0.1 archive: Fix B makes the offline pytest/CI gates
> truly offline (the four provider-dependent tests are marked and run
> only in the full profile), and Fix C delivers a current-release
> report that labels which evidence is historical v8 and which belongs
> to this patch. It is NOT a second pentest, NOT a rebuild, and it does
> NOT rewrite v8 history. The release label is v8.0.2 and the target
> product version is **1.8.2**. IF-V8-42/43 stay OPEN (see the reviewer
> checklists in the findings register). Workstreams: WS1 (Fix A — IdP
> encoding; WS1 owns `backend/src/identityforge/protocol/jwks.py`,
> `backend/tests/fake_http.py`, `backend/tests/adversarial/test_ws1_v8_idp_caps.py`)
> and WS2 (Fix B + Fix C, this section). The parent's Pass C re-runs
> every gate on the final tree (see the Pass C rows, added at packaging).

- **Release name:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V8.0.2_FINAL_20261113.zip`
- **Version:** 1.8.2 (Operation Trustline v8.0.2 — offline pytest + current-release report)
- **Date:** 2026-11-13 (ISO 8601)
- **Built from:** working tree at `~/workspace/identityforge-v8.0.2`
  (no git repository was used for this build; no commit SHA exists)
- **Built by:** Linux sandbox, Python 3.12.3, Node 24.22.1, npm 10.9.4.
  PowerShell 7.4.6 on Linux (`~/workspace/.pwsh/pwsh`) WAS executed
  in the coordinator's Pass B (healthcheck PS matrix 26/0/0).
  Windows PowerShell 5.1 was NOT RUN (5.1 is Windows-only).
  **Historical build environment (2026-11-13 sandbox):** no Docker
  binary or socket existed in that build sandbox — the shipped
  `docker compose up` path was NOT RUN there. This describes the
  historical build sandbox only, never the end user's runtime state.
- **Counts (current release):** backend pytest 520; test-all gates 19.

### Archive (file count from the tree; size/SHA-256 in the delivery message)

- **Filename:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V8.0.2_FINAL_20261113.zip`
- **Size (bytes) and SHA-256:** not printed inside the archive — either value is a property of the ZIP file itself, so printing it here would change it. Check the delivery message for the SHA-256 of the shipped file, and verify with `ls -l` / `sha256sum <archive>` on Linux/macOS or `Get-FileHash <archive> -Algorithm SHA256` on Windows.
- **File count:** **369 files in the working tree by the packager's exclusion shape** (caches, venvs, `node_modules`, `dist`, `test-results`, `*.db`, `.hypothesis`, `egg-info` excluded) — v8.0.1's 364 + WS1's new Fix A test file (`backend/tests/adversarial/test_ws1_v802_idp_encoding.py`) + WS2's new regression script (`scripts/test-offline-provider-selection.sh`) + the Fix C report files (`docs/TRUSTLINE_V8.0.2_CURRENT_RELEASE_REPORT.md` + `.pdf`) + the report build script (`scripts/build-current-release-report.py`). The parent confirms the final count from the final ZIP's namelist at packaging.
- **Archive verified by:** parent's Pass C — three fresh extractions of the actual final ZIP bytes (plain, path with spaces, path under an ancestor literally named `data/`), `verify-release.sh` rc=0 in all three; see the Pass C row below (added at packaging).

### Scope (WS2 — Fix B offline pytest/CI + Fix C current-release report)

| Area | Change |
| ---- | ------ |
| Fix B — markers (`backend/tests/adversarial/test_ws1_v8_oidc.py`, `backend/pytest.ini`) | The four provider-dependent tests (`test_callback_replay_and_cross_browser_and_errors`, `test_callback_replay_after_consume`, `test_login_start_rate_limit`, `test_login_start_sets_browser_cookie_and_s256`) carry `@pytest.mark.live_keycloak`; the marker is registered in `backend/pytest.ini` (the effective pytest config — it takes precedence over the shadowed `[tool.pytest.ini_options]` in `backend/pyproject.toml`, which carries no markers). Markers ONLY — no test logic, assertion, fixture, or production code changed; no test removed, skipped silently, weakened, or stubbed away. |
| Fix B — offline selection (`.github/workflows/ci.yml`, `scripts/test-all.sh`, `scripts/verify-release.sh`) | One named selection, `-m "not live_keycloak"`, in all three offline runners: the default CI backend lane, `test-all.sh` OFFLINE_UNIT, and `verify-release.sh` BACKEND_PYTEST. The marked tests run only in the full profile: new `test-all.sh --full` gate LIVE_PROVIDER_PYTEST (`-m live_keycloak`, against the cold-started disposable Keycloak, only when the cold-start boot succeeded; otherwise NOT RUN honestly), reached in CI by the keycloak-e2e lane (`test-all.sh --full --strict`). Gate count 18 → **19** (12 offline + 7 full); README `## Tests`, the manifest counts line, and the guides carry the new count (docs-contract check 7 enforces all three against the runner call sites). |
| Fix B — regression (`scripts/test-offline-provider-selection.sh`, CI scripts lane) | New suite proving (a) the offline selection passes with no provider and the deselected set is exactly the four tests, and (b) the live lane wiring runs all four (statically in every mode; `--live` runs them against a real provider and requires 4 passed). No count is hardcoded — the suite counts the live/ offline split dynamically (WS1's Fix A work lands in the same tree and moves the total; only the live set, exactly 4, is pinned). Wired into the CI scripts lane (offline mode; the --live mode runs locally and is covered in CI by the keycloak-e2e lane). |
| Fix C — current-release report (`docs/TRUSTLINE_V8.0.2_CURRENT_RELEASE_REPORT.md` + `.pdf`) | New report/addendum (this section's companion): the external reviewer PDF names v8.0.1 but carries a historical v8 / product 1.8.0 cover and documents the old 352-file v8 ZIP with 482 backend tests, while the actual v8.0.1 archive is 364 files / 491 tests / version 1.8.1. The report states explicitly which evidence is historical v8 and which tests/fixes belong to v8.0.2 (520 backend tests = 516 offline + 4 provider-dependent; 19 gates; IF-V8-42/43 still OPEN; Windows/Docker/npm gates NOT RUN). The PDF is real and verifiable: Markdown source → markdown-it-py → HTML → LibreOffice 24.2 headless → PDF, checked with `pdfinfo`/`pdftotext`. The ZIP hash is a property of the external archive and appears only outside the ZIP, never inside it. |
| Fix A — IdP encoding (WS1; observed, not owned by WS2) | WS1's Fix A work lands in the same tree (new file `backend/tests/adversarial/test_ws1_v802_idp_encoding.py`, 29 collected tests; `backend/src/identityforge/protocol/jwks.py` and `backend/tests/fake_http.py` modified by WS1). WS2 did not touch those files. The backend suite grows 491 → **520** (491 v8.0.1 + 29 Fix A); the offline/provider split is 516 + 4. Full Fix A scope and evidence are in the WS1 handover, not this section. |
| Version 1.8.2 — contract bump (coordinator, Pass B) | APPLIED by the coordinator in Pass B, following the v8.0.1 precedent (WS1's version-bump scope row): code sources (`__init__.py`, `pyproject.toml`, `package.json` + `package-lock.json` via `npm install --package-lock-only`), `scripts/check-version-contract.py` (now reads the Trustline v8.0.2 section, expects 1.8.2 by default), `scripts/test-version-contract.sh` fixtures (13/13 PASS), the test-only version assertions (`test_v6_backend_api.py`, `Settings.test.tsx`), the version labels in `test-all.sh` / `verify-release.sh`, and the CI version-contract comment. `VERSION_CONTRACT` now verifies **1.8.2** on the real tree and the running backend's `/api/v1/health` reports 1.8.2. [Coordinator correction: this row first said the bump was still pending at packaging — it has now landed before packaging.] |
| Guides + counts (`docs/REVIEWER_GUIDE.md`, `docs/WINDOWS_SETUP.md`, `README.md`, `docs/TEST_MATRIX.md`, `scripts/pentest/ws3/README.md`) | Quickstart regions name the v8.0.2 final archive and say release version 1.8.2 (docs-contract checks 5/6b); the reviewer guide carries the 19-gate full-profile description with the new LIVE_PROVIDER_PYTEST gate. Windows setup records the ONE known divergence honestly: `test-all.ps1` still defines 18 gates and its OFFLINE_UNIT still runs unfiltered `pytest -q` in the backend-test container (no IdP there) — the same defect class Fix B repaired on the sh/CI/verify-release path. The ps1 follow-up is OPEN (see the Fix C report §5); it is not claimed fixed. `scripts/pentest/ws3/README.md` count 491 → 520 (same count fix as README; the 51 WS3 tests stay separate and are never added to the 520). |
| Findings register (`docs/PENTEST_FINDINGS_AND_REMEDIATIONS.md`) | No change. IF-V8-42 (Dockerfiles run as root) and IF-V8-43 (CI SHA pins) stay **OPEN** with their reviewer checklists. No Docker/CI pass is claimed. |

### Measured results (WS2, v8.0.2)

| Gate | Result |
| ---- | ------ |
| Failing-first — four tests, Keycloak absent | **REPRODUCED (v8.0.1 code, before the fix).** Live stack restarted from the v8.0.2 tree (Keycloak 26.8.2 host process, discovery 200, issuer exactly `http://127.0.0.1:8080/realms/identityforge-lab`); the four tests PASS with Keycloak up (rc=0). Keycloak stopped by exact PID (java 2610); the four tests then FAIL, each with 503 `PROVIDER_UNAVAILABLE` (rc=1). Logs `four-tests-live-pass.txt`, `four-tests-no-keycloak-fail.txt` in `~/workspace/ws2-v802-evidence/`. |
| Failing-first — verify-release, fresh extraction, no Keycloak | **REPRODUCED (v8.0.1 code).** Fresh extraction of the delivered v8.0.1 ZIP (364 entries, testzip clean) to `~/workspace/.verify/ws2-v802-fresh/`, deps on PATH (v7.3.1 venv python3/pytest/ruff/pip-audit), Keycloak absent: `verify-release.sh` **22 PASS / 1 FAIL / 5 NOT RUN, rc=1** — sole FAIL BACKEND_PYTEST. Log `verify-release-fresh-nokeycloak.txt`. |
| Backend suite counts | **520 collected = 516 offline + 4 live_keycloak** (WS2, `pytest --collect-only` on the merged tree: the four `-m live_keycloak` IDs are exactly the expected four; the 51 WS3 tests are a separate count and never added). Baseline v8.0.1 was 491; WS1's Fix A adds 29. |
| Offline/provider regression (WS2) | **11/11 PASS offline mode** (no provider on 8080: selection split exact 520 = 516 + 4; live set exactly the four; offline selection passes, 516 tests, rc=0) and **11/11 PASS live mode** (live Keycloak discovery 200, canonical issuer; live selection passes, 4 tests, rc=0). Logs `regression-offline.txt`, `regression-live.txt`. |
| `verify-release.sh` (fixed tree, Keycloak absent) | **22 PASS / 1 FAIL / 5 NOT RUN, rc=1** (WS2, fresh copy of the fixed tree, `~/workspace/.verify/ws2-v802-fixed/`, deps on PATH, Keycloak absent). BACKEND_PYTEST now **PASSES** (offline selection, 516 tests). The single FAIL is DOCS_CONTRACT — docs-contract check 7 correctly refusing the intermediate state: the new gate makes the runners define 19 IDs while the manifest/README still said 18. Resolved by the manifest + README updates in this same delivery; the final verify-release row (re-run on the final tree) is below. Log `verify-release-fixed-nokeycloak.txt`. |
| `verify-release.sh` (final tree, Keycloak absent) | **23 PASS / 0 FAIL / 5 NOT RUN, rc=0** (WS2, fresh copy of the finished tree, `~/workspace/.verify/ws2-v802-final2/`, deps on PATH, Keycloak absent; a first final-tree copy failed FORBIDDEN_FILES on `backend/src/identityforge.egg-info/` — an editable-install artifact created in the working tree by `test-all.sh`'s `pip install -e backend`, removed afterwards; the packager's exclusion shape excludes egg-info, so the re-run used a copy without it). BACKEND_PYTEST **PASS** (offline selection), DOCS_CONTRACT **PASS**, DOCS_CONTRACT_PATHS **PASS**. The 5 NOT RUN are the bare-extraction deps/Docker checks (same five as v8.0.1 Pass C). Log `verify-release-final2.txt`. |
| Docs-contract (real tree) | **PASS — 0 violations** (WS2, `python3 scripts/validate-docs-contract.py` on the finished tree: 34 FailureReason values, 59 report-model fields, 123 source files harvested, 70 files scanned). Check 7 green: README `## Tests` 520 tests / 19 gates agree with the manifest counts line and the 19 runner gate IDs. Log `docs-contract-final.txt`. |
| Docs-contract paths | **PASS — 48/48** (WS2, `bash scripts/test-docs-contract-paths.sh` on the finished tree). Log `docs-contract-paths-final.txt`. |
| `test-all.sh --offline` (final tree) | **rc=0 — 11 PASS / 0 FAIL / 8 NOT RUN across the 19 gates** (WS2, clean run without a PATH override, `test-all-offline-final2.txt`; `test-results/gates.json` confirms). PASS: OFFLINE_UNIT (offline selection), OFFLINE_SCENARIOS, DOCS_CONTRACT, DOCS_CONTRACT_PATHS, VERSION_CONTRACT, FRONTEND_TYPECHECK, FRONTEND_UNIT, FRONTEND_BUILD, PYTHON_DEPENDENCY_AUDIT, GHSA_DIRECT_FALLBACK, COMPOSE_CONFIG (YAML-only fallback). NOT RUN: NPM_FULL_LOCKFILE_AUDIT (registry 403) + the 7 full-profile gates (including the new LIVE_PROVIDER_PYTEST — offline profile, opt in with --full). A first run with the venv bin prepended to PATH read 10/0/9 with COMPOSE_CONFIG NOT RUN ("no PyYAML for the fallback check") — the venv python3 has no PyYAML and shadowed the system python3 that does; an invocation artifact, not a tree defect, and the clean re-run proves it. Log `test-all-offline-final.txt` (first run) and `test-all-offline-final2.txt` (clean run). |
| Docker Compose boot / Windows PowerShell 5.1 / in-image Keycloak healthcheck / full npm audit | **NOT RUN** — reviewer gates (no Docker in the build sandbox; 5.1 is Windows-only; npm audit registry 403). |
| Mutation test (source-level) | **NOT RUN by design** — source-level mutation testing is forbidden; sensitivity via the designed `omit` mechanism: PASS. |

### Measured results (WS1, v8.0.2 — Fix A)

| Gate | Result |
| ---- | ------ |
| Failing-first — zip-bomb memory gap (pre-fix v8.0.1 code) | **REPRODUCED.** Local loopback stub: 12,253 gzip wire bytes (`Content-Encoding: gzip`, true wire Content-Length 12,253) expanding to exactly 12,582,912 bytes. `_bounded_fetch('GET', stub_url, timeout=2)` raised the correct `ValueError`, but tracemalloc peaked at **38,943,247 / 38,943,107 / 38,943,185 bytes** across three runs (~37× the 1 MiB cap). The parent reproduced the same defect independently on the pristine v8.0.1 tree before fan-out: peak **38,926,945 bytes** (owner's audit: 41,406,664). A mere `ValueError` after full allocation is not a memory-bound proof. |
| The patch | **Smallest safe fix** in `backend/src/identityforge/protocol/jwks.py`: request `Accept-Encoding: identity`; new `_check_content_encoding()` rejects every non-identity token **before any body byte is read** (case-insensitive, comma-split, duplicate headers, `br`/`deflate`/unknown all rejected); `iter_bytes` → `iter_raw` in 64 KiB pieces with the 1 MiB+1 early stop; defence-in-depth strip of `Content-Encoding` on synthesized responses. Retained: 1 MiB limit, 64 KiB per-read cap, ValueError semantics, `trust_env=False`, `follow_redirects=False`, issuer pins, transport provenance, SSRF guards. |
| After-patch proof | **CLOSED.** Oversized gzip now raises `ValueError: IdP response uses unsupported Content-Encoding` before decompression; tracemalloc peak **1,183,534 bytes (1.13× cap)** (coordinator's re-run) and **1,174,476 bytes** (parent's own re-run on the final tree). Rejection matrix covers gzip/GZIP/GZip/small gzip/duplicates/comma-joined/`gzip, identity`/`identity, gzip`/br/x-custom/compress/chunked+gzip/no-CL+gzip/declared-huge+gzip/500+gzip/redirect+gzip/short-EOF+gzip; all four fetchers exercised; duplicate Content-Length probed (agreeing → OK, disagreeing → `RemoteProtocolError`, both over cap → `ValueError`). New tests: pre-fix **23 failed / 6 passed**; post-fix **29/29**; with the 16 existing caps tests, **45 passed, rc=0**. |

### Measured results (parent's Pass C, v8.0.2)

| Gate | Result |
| ---- | ------ |
| pytest (backend, full) | **520 passed, 3 warnings, rc=0** (115.49s). |
| pytest offline, Keycloak ABSENT | **516 passed, 4 deselected, rc=0** (Keycloak stopped by exact PID, kc 000, port 8080 free). |
| pytest live_keycloak, Keycloak PRESENT | **4 passed, 516 deselected, rc=0**. |
| WS3 51 (separate, disposable venv from pins) | **51 passed, rc=0** (hypothesis 6.170.15). |
| CLI verify-all | **18/18 PASS**. |
| ruff check / format | clean / 68 files formatted. |
| typecheck | rc=0. |
| Vitest | **161/161** (13 files). |
| frontend build | rc=0, `a77dd7d5…` byte-identical to v8. |
| version-contract / docs-contract | PASS 1.8.2 / PASS 0 violations. |
| docs-contract-paths | **48/48**. |
| dependency-gates | **55/0**. |
| test-all.sh --offline | **rc=0, 11 PASS / 0 FAIL / 8 NOT RUN** (19 gates; NOT RUN = NPM_FULL_LOCKFILE_AUDIT registry 403 + 7 full-profile gates incl. LIVE_PROVIDER_PYTEST). |
| healthcheck regressions | **34/0/0, rc=0**. |
| PS matrix (pwsh 7.4.6) | **26/0/0, rc=0**. |
| offline-provider-selection regression | **11/11 offline + 11/11 live**. |
| live gate `all` | **rc=0, 101/0** (real Keycloak host process). |
| live gate `reset` (marker backend 6bbca7ad-…, temp DB removed after) | **rc=0, 69/0**. Dev backend restored with DB-backed counters byte-identical to the pre-reset snapshot (runs 131, live events 356, observed/verified 48, incomplete 7, events 219); only in-memory `sessions` 30→0 and `sessions_total_issued` 40→0 changed (documented restart semantics). |
| guard negatives | no-flag rc=2, wrong-id rc=1, malformed rc=2 (dev counts untouched). |
| Playwright full | **72 passed + 1 skipped, rc=0**; validator **PASS** (total 73, passed 72, failed 0, skipped 1 — the allowed edge-cancel skip). |
| axe (a11y.spec, zero-tolerance) | **25/25, 0 violations** from the real report JSON; 133 PNG screenshots. |
| CI YAML | valid, 4 jobs (backend, frontend, scripts, keycloak-e2e). **GitHub Actions execution NOT RUN.** |
| OPEN follow-up (not claimed fixed) | **`test-all.ps1` still defines 18 gates and its OFFLINE_UNIT still runs unfiltered `pytest -q`** — the same defect class Fix B repaired on the sh/CI/verify-release path. Recorded in `docs/WINDOWS_SETUP.md:315-323` and the Fix C report §7. Needs a ps1 edit + a Windows run. |
| Pass C — final ZIP (parent, after packaging) | Three fresh extractions of the actual final ZIP bytes (plain `~/workspace/.verify/v802-final-plain`, `~/workspace/.verify/v802 final spaces`, `~/workspace/.verify/data/v802-final-data`): `verify-release.sh` **23 PASS / 0 FAIL / 5 NOT RUN, rc=0 in all three** (28 checks; the 5 NOT RUN are the bare-extraction deps/Docker checks). Final ZIP: **369 entries, testzip clean, 0 forbidden entries, all `.sh` entries mode 0770, 131 PNGs, the real Fix C PDF present, all 5 new files present.** Plain-extraction deep check: pytest **520 passed** (import verified → extraction, version 1.8.2), CLI **18/18**, docs-contract-paths **48/48**, dep-gates **55/0**, regressions **32/0/2** (02-a/03-a correctly NOT RUN — no baseline tree in a bare extraction), `npm ci` + Vitest **161/161** + build byte-identical (`index-X2bsjLBG.js`, SHA-256 `a77dd7d5…`). Pass C incident: the first verification pass ran verify-release twice in the same extraction dirs and the second run read 22/1/5 with FORBIDDEN_FILES FAIL on `backend/data/identityforge.db` — a DB created by the first run's own BACKEND_PYTEST, not a ZIP defect (the ZIP namelist holds no DB; a fresh extraction has no `backend/data/` at all). Re-extracted fresh and ran once per dir: 23/0/5 rc=0 in all three. Evidence: `~/workspace/passc-v802-evidence/verify-release-v802-final-plain-passc.txt` (+ spaces/data). |

## Operation Trustline v8.0.3 — Windows-runner correction + release clarity (2026-11-13)

> Every row below is filled from the measured runs in
> `docs/VERIFICATION_LOG.md` (v8.0.3 section) — never from memory, and
> never in advance. No v8.0.2 figure is copied forward as a v8.0.3
> result. Status words in this section are exactly PASS / FAIL /
> NOT RUN / NOT APPLICABLE. v8.0.3 is a NARROW targeted patch on the
> delivered v8.0.2 archive: WS1 closes the one known v8.0.2 divergence
> (`test-all.ps1` 18 vs `test-all.sh` 19 gates) and WS2 closes the
> release-clarity items (guides + counts, the parent Pass C outcome
> appended to the current-release report, the verify-release double-run
> false-fail). It is NOT a second pentest, NOT a rebuild, and it does
> NOT rewrite v8.0.2 history. The release label is v8.0.3 and the target
> product version is **1.8.3**. IF-V8-42/43 stay OPEN (see the reviewer
> checklists in the findings register). Workstreams: WS1 (ps1 fix) and
> WS2 (docs + report addendum + verify-release isolation, this section).
> The parent's Pass C re-runs every gate on the final tree (see the Pass C
> rows, added at packaging).

- **Release name:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V8.0.3_FINAL_20261113.zip`
- **Version:** 1.8.3 (Operation Trustline v8.0.3 — Windows-runner correction + release clarity)
- **Date:** 2026-11-13 (ISO 8601)
- **Built from:** working tree at `~/workspace/identityforge-v8.0.3`
  (no git repository was used for this build; no commit SHA exists)
- **Built by:** Linux sandbox, Python 3.12.3, Node 24.22.1, npm 10.9.4, PowerShell 7.4.6 on Linux (`~/workspace/.pwsh/pwsh`, executed in the coordinator's Pass B: healthcheck PS matrix 26/0/0, ps1 parse 0 errors, real ps1 `-Offline` run with Docker absent). Windows PowerShell 5.1 was NOT RUN (5.1 is Windows-only). **Historical build environment (2026-11-13 sandbox):** no Docker binary or socket existed in that build sandbox — the shipped `docker compose up` path was NOT RUN there. This describes the historical build sandbox only, never the end user's runtime state.
- **Counts (current release):** backend pytest 520; test-all gates 19.

### Archive (file count from the tree; size/SHA-256 in the delivery message)

- **Filename:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V8.0.3_FINAL_20261113.zip`
- **Size (bytes) and SHA-256:** not printed inside the archive — either value is a property of the ZIP file itself, so printing it here would change it. Check the delivery message for the SHA-256 of the shipped file, and verify with `ls -l` / `sha256sum <archive>` on Linux/macOS or `Get-FileHash <archive> -Algorithm SHA256` on Windows.
- **File count:** **371 files in the working tree by the packager's exclusion shape** (caches, venvs, `node_modules`, `dist`, `test-results`, `*.db`, `.hypothesis`, `egg-info` excluded) — the v8.0.2 tree's 369 + WS1's two new files (`scripts/loopback-forwarder.py`, `scripts/test-ps1-selection.sh`); the regenerated Fix C PDF replaces the v8.0.2 one in place. Counted with the packager's own `excluded()` logic (`scripts/package-zip.py`). The parent confirms the final count from the final ZIP's namelist at packaging.
- **Archive verified by:** parent's Pass C — three fresh extractions of the actual final ZIP bytes (plain, path with spaces, path under an ancestor literally named `data/`), `verify-release.sh` rc=0 in all three; see the Pass C row below (added at packaging).

### Scope (WS1 — ps1 fix; WS2 — docs + report addendum + verify-release isolation)

| Area | Change |
| ---- | ------ |
| WS1 — ps1 parity (`scripts/test-all.ps1`, `scripts/loopback-forwarder.py`, `scripts/test-ps1-selection.sh`) | The v8.0.2 divergence is CLOSED: `test-all.ps1` now defines the same **19 gates (12 offline + 7 full)** as `test-all.sh`, with the identical gate-ID set (verified from the tree by WS2: 19 unique `Invoke-Gate` IDs, 12 offline + 7 full). OFFLINE_UNIT runs the offline selection `python -m pytest -q -m 'not live_keycloak'` (single quotes — the ps1 QUOTING header note explains why: the selection must arrive at pytest as one argument through PowerShell → Invoke-Native → docker CLI → container `sh -c`). New full-profile gate LIVE_PROVIDER_PYTEST (`-m live_keycloak`, only in `-Full`, against the cold-started disposable Keycloak, never against the user's persistent stack): the four tests run inside the backend-test container with new stdlib-only `scripts/loopback-forwarder.py` forwarding container loopback 127.0.0.1:8080 → `keycloak:8080` (30 s discovery-readiness wait; the backend still validates the discovery issuer against the canonical `http://127.0.0.1:8080/realms/identityforge-lab` — the forwarder changes only the network route, never the identity). The stale VERSION_CONTRACT label ("1.7.3") now reads release version **1.8.3**. Proof: new `scripts/test-ps1-selection.sh` (514 lines; landed 21:50 UTC, after WS2's first tree read — WS2 re-ran it, see the measured-results rows: 33 passed, 0 failed, 1 skipped). The runtime teardown probe SKIPs in this sandbox (pwsh TcpClient loopback quirk, documented in the script); real-Docker execution of the new LIVE gate and Windows PowerShell 5.1 execution remain reviewer gates. |
| WS2 — guides + counts (`docs/WINDOWS_SETUP.md`, `README.md`, `scripts/test-matrix.md`) | WINDOWS_SETUP: quickstart hash command + release-name prose now name the v8.0.3 final archive (docs-contract checks 5/6a); the §3 divergence paragraph now states the CLOSED state (ps1 19 gates, OFFLINE_UNIT `-m "not live_keycloak"`, LIVE_PROVIDER_PYTEST in both runners, loopback-forwarder arrangement, VERSION_CONTRACT label fixed to 1.8.3); "release version" prose 1.8.2 → 1.8.3 (check 6b). README: new v8.0.3 history bullet; `## Tests` now states both runners define the same 19 gates (counts unchanged: 520 tests, 19 gates — check 7 green). test-matrix: new v8.0.3 note (current state 19 gates both runners, 520 tests, docs-contract-paths 48 checks, verify-release isolation, 1.8.3 bump dependency); the 18-gate lines above it are v6 history and are left as history, per the file's own prospective-note convention. |
| WS2 — report addendum (`docs/TRUSTLINE_V8.0.2_CURRENT_RELEASE_REPORT.md` + `.pdf`) | New §10 (dated 2026-11-13, Operation Trustline v8.0.3): the parent's v8.0.2 Pass C outcome on the final v8.0.2 tree and final ZIP (full battery table, final-ZIP facts, the double-run incident, the ps1 follow-up now closed). §§1–9 byte-identical WS2 evidence — nothing rewritten. The full v8.0.2 ZIP SHA-256 appears in §10 as a historical fact about the already-delivered v8.0.2 archive; the v8.0.3 archive's own hash is, as §1 states, only in the delivery message. PDF regenerated with the shipped `scripts/build-current-release-report.py` (markdown-it-py → HTML → LibreOffice 24.2 headless): **12 pages, A4, 223,792 bytes**, text-extractable, verified with `pdfinfo`/`pdftotext`. |
| WS2 — verify-release isolation (`scripts/verify-release.sh`) | BACKEND_PYTEST now runs with `IDENTITYFORGE_DB_PATH` pointed at a disposable temp directory (`mktemp -d`, removed by an EXIT trap). The offline suite creates `backend/data/identityforge.db` even on `--collect-only` (the CLI store via `Settings()` defaults), which made a second verifier run in the same extraction false-fail FORBIDDEN_FILES (parent Pass C, v8.0.2: 22/1/5). Proven: unredirected offline run creates the in-tree DB (rc=0); redirected run creates no in-tree DB and the DB lands in the temp dir (rc=0); collect-only split identical with/without the redirect (516 offline + 4 live). The script never deletes anything in the tree — only the temp dir it created itself. Header documents that a fresh extraction per run is still the recommended audit shape. |
| Version 1.8.3 — contract bump (coordinator, Pass B) | **LANDED by the coordinator in Pass B**, following the v8.0.2 precedent: code sources (`__init__.py`, `pyproject.toml`, `package.json` + `package-lock.json` via `npm install --package-lock-only`), `scripts/check-version-contract.py` (retargeted to the v8.0.3 manifest section / 1.8.3 default, including the escaped `v8\.0\.3` regex the coordinator's first pass missed — the same trap as v8.0.1), `scripts/test-version-contract.sh` fixtures (13/13 PASS), the test-only version assertions (`test_v6_backend_api.py`, `Settings.test.tsx` — including the `/1\.8\.3/` About assertion the coordinator's first pass missed, which failed Vitest 160/161 until fixed; now 161/161), the version labels in `test-all.sh` / `verify-release.sh` (ps1 label was fixed by WS1 to 1.8.3 in this round), and the CI version-contract comment. `VERSION_CONTRACT` now verifies **1.8.3** on the real tree and the running backend's `/api/v1/health` reports 1.8.3. `docs/REVIEWER_GUIDE.md` was ALSO fixed in Pass B (the WS2 Pass B item): lines 31/35 name the v8.0.3 final archive, line 38 says the v8.0.3 final release name, line 492 says release version 1.8.3 — docs-contract is green on the finished tree (see the Pass B measured-results rows). |
| Findings register (`docs/PENTEST_FINDINGS_AND_REMEDIATIONS.md`) | No change. IF-V8-42 (Dockerfiles run as root) and IF-V8-43 (CI SHA pins) stay **OPEN** with their reviewer checklists. No Docker/CI pass is claimed. |

### Measured results (WS2, v8.0.3)

| Gate | Result |
| ---- | ------ |
| ps1 gate parity (WS2 static verification of WS1's landing) | **19 unique `Invoke-Gate` IDs, 12 offline + 7 full, identical set to `test-all.sh`** (grep-verified on the landed tree). OFFLINE_UNIT: `pytest -q -m 'not live_keycloak'` (single quotes). LIVE_PROVIDER_PYTEST "full": backend-test container + loopback forwarder, `pytest -v -m live_keycloak`, log `test-results\live-provider-pytest.log`. VERSION_CONTRACT label: "release version 1.8.3 agrees everywhere". ps1 parse: **0 errors** (PowerShell 7.4.6 on Linux, WS2's own run, log `ps1-parse.txt`). New files `scripts/loopback-forwarder.py` (stdlib-only, 4,707 bytes) and `scripts/test-ps1-selection.sh` (514 lines; landed 21:50 UTC) present. WS2 re-ran the selection suite (see the next row). |
| ps1 selection suite — WS2 independent re-run | **33 passed, 0 failed, 1 skipped, rc=0** (`bash scripts/test-ps1-selection.sh`, default mode, WS2's own run, ports 8080/8000/5173 free, no provider on 8080). PASS: OFFLINE_UNIT `-m 'not live_keycloak'`; no unfiltered `pytest -q` remains; VERSION_CONTRACT label 1.8.3, no stale 1.7.3; LIVE_PROVIDER_PYTEST Invoke-Gate (full) + exactly 2 Skip-Gates + loopback forwarder + `pytest -v -m live_keycloak` + "4 passed" requirement + BOOT_OK gating; gate count 19 (12 offline + 7 full); forwarder stdlib-only + bad-argv rc=2; exactly one executed `down` (`-p $ColdProject down -v`, finally block); no volume/prune/kill/recursive delete; selection split exact **520 = 516 offline + 4 live_keycloak** with the live set exactly the four tests; **offline selection passes with no provider (516 tests, rc=0)**; no-docker and daemon-dead runs fail closed (rc=1, no gates.json); quoting probe proves pytest received ONE argument `not live_keycloak`; stub `-Offline` run wrote gates.json 19 gates, 11 PASS / 0 FAIL / 7 NOT RUN / 1 NOT APPLICABLE, LIVE_PROVIDER_PYTEST NOT RUN. SKIP (1): the runtime teardown probe — this sandbox's pwsh TcpClient connects to any loopback port (even dead 59999), so `-Full` always fails its port preflight here; static checks cover (d); run on Windows for the runtime proof. Log `ps1-selection-ws2-rerun.txt`. |
| Backend suite counts (WS2 probe) | **520 collected = 516 offline + 4 live_keycloak** (probe copy of the v8.0.3 tree, v7.3.1 venv python, `PYTHONPATH=src`: `--collect-only -q -m "not live_keycloak"` sums to 516; `-m live_keycloak` sums to 4). The 51 WS3 tests are a separate count and never added. |
| verify-release isolation proof (WS2 probe) | **PROVEN on a probe copy:** unredirected offline pytest (rc=0) creates `backend/data/identityforge.db` in-tree; redirected run (`IDENTITYFORGE_DB_PATH=<tmp>/identityforge.db`, rc=0) creates NO in-tree `backend/data/` and the 28,672-byte DB lands in the temp dir; collect-only split identical with/without the redirect (516/4). Logs `probe-pytest-offline.txt`, `probe-pytest-offline-redirected.txt`, `probe-collect-redirected.txt`, `probe-collect-live.txt`. The double-run proof on the finished tree (two consecutive `verify-release.sh` runs in one fresh copy, second run must not false-fail) is the row below. |
| `verify-release.sh` double-run (WS2, finished tree) | **PROVEN — run 1 and run 2 identical: 22 PASS / 1 FAIL / 5 NOT RUN, rc=1 in both** (fresh copy of the finished tree, `~/workspace/.verify/ws2-v803-final/`, deps on PATH, Keycloak absent; run 1 21:48–21:50 UTC, run 2 21:51–21:53 UTC). **FORBIDDEN_FILES PASS and BACKEND_PYTEST PASS in both runs**; no `*.db` left in-tree after either run. The single FAIL in both runs is DOCS_CONTRACT — the REVIEWER_GUIDE.md Pass B item (4 violations, see the row below), NOT the double-run defect. The pre-fix shape (parent Pass C, v8.0.2) was run 2 = 22/1/5 with FORBIDDEN_FILES FAIL; the fix removes exactly that delta. A single fresh run reads 23/0/5 once the coordinator applies the 4-line REVIEWER_GUIDE.md update. Logs `verify-release-double-run1.txt`, `verify-release-double-run2.txt`. |
| Docs-contract (real tree) | **FAIL — 4 violations, all in `docs/REVIEWER_GUIDE.md`** (34 FailureReason values, 59 report-model fields, 126 source files harvested, 71 files scanned): lines 31/35 name the v8.0.2 archive (check 5), line 38 names label v8.0.2 (check 6a), line 492 says "release version 1.8.2" (check 6b). That file is OUTSIDE WS2's scope; the coordinator's Pass B applies the mechanical 4-line update. **Everything WS2 owns is clean:** check 7 green (README `## Tests` 520 tests / 19 gates agree with the manifest counts line and the 19 runner gate IDs), WINDOWS_SETUP.md checks 5/6a/6b green. Log `docs-contract-final.txt`. |
| Docs-contract paths | **PASS — 48/48** (WS2, `bash scripts/test-docs-contract-paths.sh` on the finished tree). Log `docs-contract-paths-final.txt`. |
| PDF regeneration (WS2) | **12 pages, A4, 223,792 bytes, Producer LibreOffice 24.2** (`scripts/build-current-release-report.py`, rc=0; `pdfinfo`/`pdftotext` verified: §10 addendum present, full v8.0.2 SHA-256, "516 passed, 4 deselected", "23 PASS / 0 FAIL / 5 NOT RUN" all extractable). Log `pdf-build.txt`, `pdf-text.txt`. |
| Stray-artifact cleanup (WS2) | A pytest-created `backend/data/identityforge.db` (28,672 bytes, 2026-11-13 21:37 UTC) and `backend/.pytest_cache/` were found in the working tree (created by a concurrent pytest run during the round — WS1's selection proof and/or the WS2 probe window; no live stack ever ran against this tree). Both are packager-excluded artifacts (`*.db`, caches), not shipped files and not user data; removed from the working tree. They reappeared at 21:49–21:52 UTC (WS1's proof run) and again after WS2's own re-run of `scripts/test-ps1-selection.sh` (21:57 UTC) — each time the suite's in-tree pytest run recreating them — and were removed again after that run. At 21:59 UTC they were present again (`backend/data/identityforge.db`, `backend/.ruff_cache/`): WS1 had started a live `ruff + pytest -q -m 'not live_keycloak'` run at 21:58 UTC (PID 19444) — WS2 did NOT delete them out from under that running process. That run finished; the artifacts recurred once more at 22:00 UTC (a further in-tree pytest run) and were gone again by 22:01 UTC (cleaned up, no process running): the final tree is clean (no `*.db`, no `.pytest_cache`, no `.ruff_cache`, no `test-results/`), verified 22:01 UTC. All are packager-excluded in any case, so the packaged ZIP is unaffected. The final diff vs the delivered v8.0.2 ZIP is exactly the WS1/WS2 files (see the log). |
| Docker Compose boot / Windows PowerShell 5.1 / in-image Keycloak healthcheck / full npm audit | **NOT RUN** — reviewer gates (no Docker in the build sandbox; 5.1 is Windows-only; npm audit registry 403). |
| Mutation test (source-level) | **NOT RUN by design** — source-level mutation testing is forbidden; sensitivity via the designed `omit` mechanism: PASS. |

### Measured results (coordinator's Pass B, v8.0.3)

| Gate | Result |
| ---- | ------ |
| Version bump 1.8.3 (coordinator) | **LANDED + verified.** Code sources, lockfile via `npm install --package-lock-only`, `check-version-contract.py` retargeted to the v8.0.3 section / 1.8.3 (including the escaped `v8\.0\.3` regex — the first pass missed it, same trap as v8.0.1), `test-version-contract.sh` fixtures **13/13 PASS**, test-only assertions, runner labels, CI comment. **Version-contract PASS 1.8.3** on the finished tree; backend `/api/v1/health` reports 1.8.3. Two bump defects the coordinator caught by running the gates (not by inspection): the checker regex miss above, and the `Settings.test.tsx` About assertion `/1\.8\.2/` (missed by the mock-only grep — the regex literal is single-backslash in the file), which failed Vitest 160/161 until fixed; now **161/161**. `docs/REVIEWER_GUIDE.md` 4-line fix applied (lines 31/35/38/492) — **docs-contract PASS, 0 violations** on the finished tree (was 4 violations, all REVIEWER_GUIDE.md, at WS2 finish). |
| pytest (backend, full) | **520 passed, 3 warnings, rc=0** (90.39s). |
| pytest offline, Keycloak ABSENT | **516 passed, 4 deselected, rc=0** (Keycloak stopped by exact PID, kc 000, port 8080 free). |
| pytest live_keycloak, Keycloak PRESENT | **4 passed, 516 deselected, rc=0**. |
| WS3 51 (separate, disposable venv from pins) | **51 passed, rc=0** (hypothesis 6.170.15). |
| CLI verify-all | **18/18 PASS**. |
| ruff check / format | clean / 68 files formatted. |
| typecheck | rc=0. |
| Vitest | **161/161** (13 files). |
| frontend build | rc=0, `a77dd7d5…` byte-identical to v8. |
| version-contract / docs-contract | PASS 1.8.3 / PASS 0 violations. |
| docs-contract-paths | **48/48**. |
| dependency-gates | **55/0**. |
| test-all.sh --offline | **rc=0, 11 PASS / 0 FAIL / 8 NOT RUN** (19 gates; NOT RUN = NPM_FULL_LOCKFILE_AUDIT registry 403 + 7 full-profile gates incl. LIVE_PROVIDER_PYTEST). |
| healthcheck regressions | **34/0/0, rc=0**. |
| PS matrix (pwsh 7.4.6) | **26/0/0, rc=0**. |
| offline-provider-selection regression | **11/11 offline + 11/11 live**. |
| ps1-selection regression (coordinator re-runs) | **33 passed, 0 failed, 1 skipped** (default mode, Keycloak down) and **35 passed, 0 failed, 1 skipped** (`--live`, Keycloak up). The 1 skip in both is the runtime teardown probe (pwsh TcpClient loopback quirk — see the WS1 row). A later re-run attempt while Keycloak was UP read 0/1 — the suite's own guard refusing the offline no-provider proof while a provider listens on 8080 (correct behavior, not a suite failure). |
| Real ps1 under pwsh 7.4.6, Docker absent | **TRUE rc=1, fails closed:** `ERROR: Docker is not available. Install Docker Desktop for Windows and make sure the Docker daemon is running, then re-run this script.` No gates.json written (the `test-results/gates.json` mtime is the earlier `test-all.sh` run's). Windows PowerShell 5.1 + Docker Desktop execution is NOT RUN here — reviewer acceptance: `.\scripts\test-all.ps1 -Full -Strict` on Windows with Docker Desktop running → exit 0, 19 gates in `test-results\gates.json`, LIVE_PROVIDER_PYTEST PASS with "4 passed" in `test-results\live-provider-pytest.log`. |
| ps1 static verification (coordinator re-read) | **19 unique `Invoke-Gate` IDs** (12 offline + 7 full, identical set to `test-all.sh`); OFFLINE_UNIT `-m 'not live_keycloak'`; **0 unfiltered `pytest -q"`** remain; VERSION_CONTRACT label 1.8.3; header 19 gates; **ps1 parse 0 errors** (pwsh 7.4.6). LIVE gate: BOOT_OK-gated, backend-test container on the disposable project's network, `scripts/loopback-forwarder.py` (stdlib-only, parses OK) at `/app/scripts/loopback-forwarder.py` — the path resolves because `docker-compose.test.yml` mounts `./scripts:/app/scripts:ro` into backend-test; 30 s discovery wait through the forwarder; `pytest -v -m live_keycloak`; PASS requires rc 0 AND "4 passed"; Skip-Gate when the boot failed. Cleanup: exactly one executed `down` (`-p $ColdProject down -v`, finally block); no prune/volume-rm/recursive delete. |
| live gate `all` | **rc=0, 101/0** (real Keycloak host process). |
| live gate `reset` (marker backend 627b9431-…, temp DB removed after) | **rc=0, 69/0**. Dev backend restored with DB-backed counters byte-identical to the pre-reset snapshot (runs 36, live events 52, observed/verified 6, incomplete 1, events 62); only in-memory `sessions` 2→0 and `sessions_total_issued` 6→0 changed (documented restart semantics). |
| guard negatives | no-flag rc=2, wrong-id rc=1, malformed rc=2 (dev counts untouched). |
| Playwright full | **72 passed + 1 skipped, rc=0**; validator **PASS** (total 73, passed 72, failed 0, skipped 1 — the allowed edge-cancel skip). |
| axe (a11y.spec, zero-tolerance) | **25/25, 0 violations** from the real report JSON; 131 PNG screenshots. Security headers live on preview (CSP + `X-Frame-Options: DENY`, coordinator's own curl). |
| CI YAML | valid, 4 jobs (backend, frontend, scripts, keycloak-e2e). **GitHub Actions execution NOT RUN.** |
| verify-release double-run (coordinator, clean copy of the final tree) | **PROVEN — run 1 and run 2 identical: rc=0, 23 PASS / 0 FAIL / 5 NOT RUN in both; FORBIDDEN_FILES PASS and BACKEND_PYTEST PASS in both; no `backend/data/` left in-tree after either run; gate lines identical.** (Clean copy = packager-exclusion shape: no `*.db`, no egg-info, no node_modules/dist/test-results.) The coordinator's FIRST double-run attempt read 23/1/4 in run 1 with FORBIDDEN_FILES FAIL — the copy was made with `cp -r` from the working tree, which carried the dev DB (created by Pass B's own test-all --offline run) plus an egg-info dir; that dirt, not the fix, failed the gate. Re-copied clean: 23/0/5 twice. This confirms WS2's fix and the v8.0.2 Pass C lesson: never copy a live working tree as a "fresh" extraction. |
| PDF regeneration (coordinator re-verified) | **12 pages, A4, 223,792 bytes, Producer LibreOffice 24.2**; `pdftotext` confirms §10, the full v8.0.2 SHA-256, "516 passed, 4 deselected", "23 PASS / 0 FAIL / 5 NOT RUN". |
| NOT RUN (reviewer gates) | Docker Compose boot, in-image Keycloak healthcheck, Windows PowerShell 5.1 execution of test-all.ps1 (-Offline and -Full -Strict), Docker Desktop live-provider execution of the new ps1 LIVE_PROVIDER_PYTEST gate, full `npm audit` (registry 403), GitHub Actions execution of the changed CI. No source-level mutation testing (standing instruction). IF-V8-42/43 stay OPEN. |

### Measured results (parent's Pass C, v8.0.3)

| Gate | Result |
| ---- | ------ |
| pytest (backend, full) | **520 passed, 3 warnings, rc=0** (134.48s, parent's own run on the final tree). |
| pytest offline, Keycloak ABSENT | **516 passed, 4 deselected, rc=0** (Keycloak stopped by exact PID 28277, kc 000, port 8080 free; 85.46s). |
| pytest live_keycloak, Keycloak PRESENT | **4 passed, 516 deselected, rc=0** (2.28s). |
| WS3 51 (separate, disposable venv from pins) | **51 passed, rc=0** (hypothesis 6.170.15; 33.27s). |
| CLI verify-all | **18/18 PASS**. |
| ruff check / format | clean / 68 files formatted. |
| typecheck | rc=0. |
| Vitest | **161/161** (13 files). |
| frontend build | rc=0, `a77dd7d5…` byte-identical to v8 (`index-X2bsjLBG.js`, SHA-256 `a77dd7d52bed856267bf155df61acebbf2ebd2e37d18da34f9862f8e61de67c8`). Pass C incident: the tree the coordinator handed over had no `frontend/dist/` and the running preview returned 404 on `/` — the coordinator's build had not left dist/ in the tree. The parent rebuilt in-tree (`npm ci` + `npm run build`, byte-identical) and restarted the preview from the v8.0.3 tree → 200. `dist/` is packager-excluded, so the packaged ZIP is unaffected; the 404 was a tree artifact, not a product defect. |
| version-contract / docs-contract | PASS 1.8.3 / PASS 0 violations. |
| version-contract fixtures | **13/13 PASS**. |
| docs-contract-paths | **48/48**. |
| dependency-gates | **55/0**. |
| test-all.sh --offline | **rc=0, 11 PASS / 0 FAIL / 8 NOT RUN** (19 gates; NOT RUN = NPM_FULL_LOCKFILE_AUDIT registry 403 + 7 full-profile gates incl. LIVE_PROVIDER_PYTEST, which reads NOT RUN in the offline profile). |
| healthcheck regressions | **34/0/0, rc=0**. |
| PS matrix (pwsh 7.4.6) | **26/0/0, rc=0**. |
| offline-provider-selection regression | **11/11 offline + 11/11 live**. |
| ps1-selection regression (parent re-runs) | **33 passed, 0 failed, 1 skipped** (default mode, Keycloak down) and **35 passed, 0 failed, 1 skipped** (`--live`, Keycloak up). The 1 skip in both is the runtime teardown probe (pwsh TcpClient loopback quirk — see below). The quoting probe proves pytest received ONE argument `not live_keycloak` through PowerShell → Invoke-Native → stub docker → sh -c; the stub `-Offline` run wrote gates.json with 19 gates, 11 PASS / 0 FAIL / 7 NOT RUN / 1 NOT APPLICABLE, LIVE_PROVIDER_PYTEST NOT RUN. |
| live gate `all` | **rc=0, 101/0** (real Keycloak host process; 101 `[PASS]`, 0 `[FAIL]`, `passed: true`). |
| live gate `reset` (marker backend f3645359-6055-4cb8-be85-bb163d61c2d1, temp DB removed after) | **rc=0, 69/0**. Dev backend restored with DB-backed counters byte-identical to the pre-reset snapshot (runs 95, live events 286, observed/verified 40, incomplete 6, events 157); only in-memory `sessions` 2→0 and `sessions_total_issued` 34→0 changed (documented restart semantics). |
| guard negatives | no-flag rc=2, wrong-id rc=1, malformed rc=2 (dev counts untouched). |
| Playwright full | **72 passed + 1 skipped, rc=0**; validator **PASS** (total 73, passed 72, failed 0, skipped 1 — the allowed edge-cancel skip). |
| axe (a11y.spec, zero-tolerance) | **25/25, 0 violations** (25 a11y tests in the spec; the zero-tolerance assertion runs in-suite, so the 0-failure Playwright run is the proof); 131 PNG screenshots in `frontend/e2e/screenshots/`. Security headers live on preview (CSP + `X-Frame-Options: DENY` + `X-Content-Type-Options: nosniff`, parent's own curl on `/` and on the JS asset). |
| CI YAML | valid, 4 jobs (backend, frontend, scripts, keycloak-e2e). **GitHub Actions execution NOT RUN.** |
| Real ps1 under pwsh 7.4.6, Docker absent (parent re-run) | **TRUE rc=1, fails closed:** `ERROR: Docker is not available. Install Docker Desktop for Windows and make sure the Docker daemon is running, then re-run this script.` No gates.json written. |
| Sandbox quirk confirmed by the parent (new) | pwsh 7.4.6 `TcpClient` **connects to ANY loopback port** — the parent's own probe connected to dead port 59999, while Python sockets correctly refuse (111). So the pre-existing `Test-PortFree` (v4 code, not changed, out of scope) always reports "busy" in this sandbox and `test-all.ps1 -Full` always fails its port preflight here. Windows behavior is unaffected. This is why the (d) runtime teardown probe SKIPs here; static checks cover (d) in this sandbox. |
| ps1 static verification (parent re-read) | **19 unique `Invoke-Gate` IDs** (12 offline + 7 full, identical set to `test-all.sh`); OFFLINE_UNIT `-m 'not live_keycloak'`; **0 unfiltered `pytest -q"`** remain; VERSION_CONTRACT label 1.8.3; header 19 gates; **ps1 parse 0 errors** (pwsh 7.4.6). LIVE gate: BOOT_OK-gated, backend-test container on the disposable project's network, `scripts/loopback-forwarder.py` (stdlib-only, 129 lines) at `/app/scripts/loopback-forwarder.py` — the path resolves because `docker-compose.test.yml` mounts `./scripts:/app/scripts:ro` into backend-test; 30 s discovery wait through the forwarder; `pytest -v -m live_keycloak`; PASS requires rc 0 AND "4 passed"; Skip-Gate when the boot failed. Cleanup: exactly one executed `down` (`-p $ColdProject down -v`, finally block); no prune/volume-rm/recursive delete. |
| PDF re-verification (parent) | **12 pages, A4, 223,792 bytes, Producer LibreOffice 24.2**; `pdftotext` confirms §10, the full v8.0.2 SHA-256, "516 passed, 4 deselected", "23 PASS / 0 FAIL / 5 NOT RUN". |
| Pass C correction (parent) | The manifest's WS1 rows said `scripts/test-ps1-selection.sh` is 498 lines — the file is **514 lines** (`wc -l`). Corrected to 514 in both manifest rows before packaging (docs-only). `scripts/loopback-forwarder.py` is 129 lines and `scripts/test-all.ps1` is 838 lines, as stated. |
| NOT RUN (reviewer gates) | Docker Compose boot, in-image Keycloak healthcheck, Windows PowerShell 5.1 execution of test-all.ps1 (-Offline and -Full -Strict), Docker Desktop live-provider execution of the new ps1 LIVE_PROVIDER_PYTEST gate, full `npm audit` (registry 403), GitHub Actions execution of the changed CI. No source-level mutation testing (standing instruction). IF-V8-42/43 stay OPEN. |
| Pass C — final ZIP (parent, after packaging) | Three fresh extractions of the actual final ZIP bytes (plain `~/workspace/.verify/v803-final-plain`, `~/workspace/.verify/v803 final spaces`, `~/workspace/.verify/data/v803-final-data`): `verify-release.sh` **23 PASS / 0 FAIL / 5 NOT RUN, rc=0 in the plain and spaces extractions; 22/0/6, rc=0 in the `data/` extraction** (28 checks; the single delta is GHSA_DIRECT_FALLBACK NOT RUN in the `data/` run — the advisory source was rate-limited at that moment, rc=2; the known quota volatility on the shared egress IP, not a ZIP defect; 0 FAIL in all three). **Double-run proof in the plain extraction: run 1 and run 2 identical, 23/0/5 rc=0 in both, 170 gate lines identical after normalizing the mktemp dir names, 0 FAIL lines in both, no `backend/data/` left in-tree after either run** — WS2's isolation fix (BACKEND_PYTEST runs with `IDENTITYFORGE_DB_PATH` in a disposable temp dir) works; the v8.0.2 double-run false-fail is gone. Final ZIP: **371 entries, testzip clean, 0 forbidden entries, all `.sh` entries mode 0770, 131 PNGs, the real Fix C PDF present (12 pages), both new files present.** Plain-extraction deep check: pytest **520 passed** (import verified → extraction, version 1.8.3) with Keycloak up — the first deep run with Keycloak down read 4 failed / 516 passed, exactly the four live_keycloak tests failing 503 with no provider, the behavior Fix B's offline selection exists for; re-run with Keycloak up: 520 passed. CLI **18/18**, docs-contract-paths **48/48**, dep-gates **55/0**, regressions **32/0/2** (02-a/03-a correctly NOT RUN — no baseline tree in a bare extraction), `npm ci` + Vitest **161/161** + build byte-identical (`index-X2bsjLBG.js`, SHA-256 `a77dd7d5…`). Pass C recheck defect fixed by the parent before packaging: the new `scripts/test-ps1-selection.sh` shipped at mode 0660 (WS1 created it with the default umask) while every other `.sh` entry is 0770 — chmod 770 in the tree, re-packaged, all 22 `.sh` entries 0770 in the final ZIP. The final ZIP was re-packaged once more after the parent filled this row (docs-only: this row + the log's final row); verify-release was re-run once per fresh extraction of the re-packaged bytes and read 23/0/5, rc=0 in all three. Evidence: `~/workspace/passc-v803-evidence/verify-release-*-passc.txt`. |

## Operation Trustline v8.0.4 — version-contract harness correction (2026-11-13)

> Every row below is filled from the measured runs in
> `docs/VERIFICATION_LOG.md` (v8.0.4 section) — never from memory, and
> never in advance. No v8.0.3 figure is copied forward as a v8.0.4
> result. Status words in this section are exactly PASS / FAIL /
> NOT RUN / NOT APPLICABLE. v8.0.4 is a SINGLE targeted
> verification-harness correction on the delivered v8.0.3 archive: WS1
> fixes the five vacuous one-source version negatives in
> `scripts/test-version-contract.sh` (stale 1.8.2 seds that matched
> nothing in the 1.8.3 fixtures) with a dynamic derivation + mutation
> assertion, and corrects the v8.0.3 13/13 claim in the record. WS2
> (this section's second half) closes the two coverage gaps the v8.0.3
> delivery left behind it: the new ps1 selection regression and the
> version fixtures were never executed by CI (Coverage Closure 2), and
> verify-release did not require the new helper/regression files or
> the 19-gate ps1 wiring (Coverage Closure 3). It is
> NOT a pentest, NOT a rebuild, NOT a UI redesign, and it does NOT
> rewrite v8.0.3 history — the v8.0.3 section above stands as history,
> including its 13/13 rows, which this section corrects (see the
> correction row). The release label is v8.0.4 and the target product
> version is **1.8.4**. The 1.8.4 contract bump itself (code sources,
> checker retarget, fixture literals, test-only assertions, runner
> labels, CI comment, guide archive names) is the coordinator's Pass B
> item and is NOT LANDED at WS1 finish — see the bump-status row. The
> parent's Pass C re-runs every gate on the final tree (see the Pass C
> rows, added at packaging).

- **Release name:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V8.0.4_FINAL_20261113.zip`
- **Version:** 1.8.4 (Operation Trustline v8.0.4 — version-contract harness correction)
- **Date:** 2026-11-13 (ISO 8601)
- **Built from:** working tree at `~/workspace/identityforge-v8.0.4`
  (exact copy of the delivered v8.0.3 ZIP — 371 files, 42,428,259 bytes,
  SHA-256 `d1721d207f5f931573e14aebc2709bc9e2f1ae853116904ac275886cb29b1f3a`,
  product 1.8.3; tree verified exact: 0 missing / 0 extra; no git
  repository was used for this build; no commit SHA exists)
- **Built by:** Linux sandbox, Python 3.12.3, Node 24.22.1, npm 10.9.4, PowerShell 7.4.6 on Linux. Windows PowerShell 5.1 was NOT RUN (5.1 is Windows-only). **Historical build environment (2026-11-13 sandbox):** no Docker binary or socket existed in that build sandbox — the shipped `docker compose up` path was NOT RUN there. This describes the historical build sandbox only, never the end user's runtime state.
- **Counts (current release):** backend pytest 520; test-all gates 19.

### Archive (file count from the tree; size/SHA-256 in the delivery message)

- **Filename:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V8.0.4_FINAL_20261113.zip`
- **Size (bytes) and SHA-256:** not printed inside the archive — either value is a property of the ZIP file itself, so printing it here would change it. Check the delivery message for the SHA-256 of the shipped file, and verify with `ls -l` / `sha256sum <archive>` on Linux/macOS or `Get-FileHash <archive> -Algorithm SHA256` on Windows.
- **File count:** **371 files in the working tree by the packager's exclusion shape** (caches, venvs, `node_modules`, `dist`, `test-results`, `*.db`, `.hypothesis`, `egg-info` excluded) — the same 371 as v8.0.3: no file was added or removed in this round. Changed files vs the delivered v8.0.3 ZIP, measured at WS1 finish (2026-11-14 ~02:58 UTC): 3 files changed by WS1 — `scripts/test-version-contract.sh`, `docs/RELEASE_MANIFEST.md`, `docs/VERIFICATION_LOG.md`. Two further files were changing concurrently under WS2's v8.0.4 work (Coverage Closure 2) while WS1 measured — `scripts/test-ps1-selection.sh` (portable scratch root; VERSION_CONTRACT label expectation derived from the checker's `--expected` default) and `.github/workflows/ci.yml` (new CI steps running the version-contract fixtures suite and the ps1 selection regression) — NOT WS1's work; WS1 did not touch either file. WS2's work was still landing when WS1 finished, so the parent/coordinator confirms the final changed-file list from the final ZIP's namelist + diff at packaging. **WS2 addendum (2026-11-14 ~03:15 UTC):** WS2 landed. Final diff vs the delivered v8.0.3 ZIP, measured by WS2 after landing (`diff -rq` of the working tree vs a fresh extraction of the delivered ZIP): exactly **6 files differ, none added or removed** — the 3 WS1 files above plus WS2's 3: `scripts/test-ps1-selection.sh`, `.github/workflows/ci.yml`, `scripts/verify-release.sh` (the two docs files are shared between the workstreams). File count stays **371**. (The coordinator's Pass B bump landed 2026-11-14: 11 further files — code sources `backend/src/identityforge/__init__.py`, `backend/pyproject.toml`, `frontend/package.json`, `frontend/package-lock.json`; `scripts/check-version-contract.py`; `backend/tests/integration/test_v6_backend_api.py`, `frontend/src/pages/Settings.test.tsx`; `scripts/test-all.sh`, `scripts/test-all.ps1`, `scripts/verify-release.sh`; `.github/workflows/ci.yml`; `docs/REVIEWER_GUIDE.md`, `docs/WINDOWS_SETUP.md` — with no file added or removed by the bump. Final changed-file list vs the delivered v8.0.3 ZIP, measured by the coordinator after the bump: **17 files** (the 6 above + the 11 bump files). The Playwright run regenerated 91 of the 131 in-tree screenshots (byte changes only, same count, same names — the packager includes them as-is; Pass C re-runs Playwright and re-verifies the count). File count stays **371**.)
- **Archive verified by:** parent's Pass C — three fresh extractions of the actual final ZIP bytes (plain `~/workspace/.verify/v804-final-plain`, `~/workspace/.verify/v804 final spaces`, `~/workspace/.verify/data/v804-final-data`), `verify-release.sh` **23 PASS / 0 FAIL / 5 NOT RUN, rc=0 in all three**; double-run proof in the plain extraction (run 1 and run 2 identical 23/0/5, 28 gate lines identical, 0 FAIL, no `backend/data/` left in-tree); plain-extraction deep check (pytest 520, CLI 18/18, docs-paths 48/48, dep-gates 55/0, `npm ci` + Vitest 161/161 + build byte-identical); see the Pass C row below.

### Scope (WS1 — version-contract harness correction)

| Area | Change |
| ---- | ------ |
| WS1 — five vacuous version negatives (`scripts/test-version-contract.sh`) | The v8.0.3 defect is CLOSED: the five one-source negatives mutated the stale literal `1.8.2` (`sed -i 's/1\.8\.2/1.5.0/'`, lines 120–129) while the generated fixtures carry 1.8.3, so the seds changed nothing, the checker correctly passed on the unmutated fixture, and each negative reported a failure (8 passed / 5 failed on the released archive). Fix: every mutation now DERIVES the version literal from the fixture it mutates (`fixture_version()` reads `__init__.__version__` from the freshly built fixture, validated X.Y.Z) and ASSERTS the mutation landed (`mutate_version()`: Python literal replace — never regex, the IF-V8-81 sed-escaping trap — with before-count >= 1, old literal gone after, replacement count equal to the pre-mutation count). `neg_case` takes label + file + old/new templates (`%VERSION%` = derived version); the FastAPI/health negatives use distinctive context literals so exactly one version slot changes; the hard-coded-UI append is asserted to have landed. The two `__version__`-derivation cases use the derived version too, with a rewrite-landing guard on the positive (both slots must carry `__version__`). `scripts/check-version-contract.py` is READ-ONLY in this round and untouched — it was proven not defective (passes on real code, fails on a genuinely mutated fixture). No exit codes swallowed, no cases skipped, no checker semantics weakened. Proof: failing-first 8/5, after-fix **13/13, rc=0**, per-case mutated-line + MISMATCH evidence in the log (see the measured-results rows). |
| WS1 — correction of the v8.0.3 13/13 claim (this section + `docs/VERIFICATION_LOG.md` v8.0.4 section) | **CORRECTED, not rewritten.** The v8.0.3 coordinator's Pass B claimed "`scripts/test-version-contract.sh` fixtures (13/13 PASS)" (manifest rows "Version 1.8.3 — contract bump" and "Version bump 1.8.3", and the Pass C battery row "version-contract fixtures 13/13 PASS"; VERIFICATION_LOG row "Pass B — version bump 1.8.3"). That claim was wrong and uncaught: the parent's v8.0.3 Pass C ran `check-version-contract.py` (PASS on the real tree) but never ran `test-version-contract.sh` itself. The parent reproduced the defect on the pristine v8.0.3 tree 2026-11-13 ~20:50 CST: `bash scripts/test-version-contract.sh` returns **rc=1, 8 passed / 5 failed** — the five FAILED cases are `manifest version negative`, `pyproject version negative`, `package.json version negative`, `package-lock.json version negative`, `__init__ __version__ negative`, each "expected nonzero exit, got rc=0: version-contract: expected 1.8.3". The v8.0.3 rows above stay as history; the correction lives here and in the v8.0.4 VERIFICATION_LOG section. Corrected rerun on v8.0.4: **13/13 PASS, rc=0** (WS1, this round; the coordinator re-runs 13/13 after the last 1.8.4 bump). |
| Version 1.8.4 — contract bump (coordinator, Pass B) | **LANDED 2026-11-14.** Code sources: `backend/src/identityforge/__init__.py`, `backend/pyproject.toml`, `frontend/package.json` + `frontend/package-lock.json` via `npm install --package-lock-only` (lockfile root + `packages.""` both 1.8.4). `scripts/check-version-contract.py` retargeted to the Trustline v8.0.4 manifest section / 1.8.4 default (Python literal replaces — the section regex is `v8\.0\.4` with single backslashes; a double-backslash sed would miss it, the v8.0.1 trap). `scripts/test-version-contract.sh` fixture literals moved FIRST (build_fixture 1.8.3 → 1.8.4 + the two informational 1.8.3 mentions + the fixture manifest `##` heading, which the first 13/13 attempt caught: the heading still read v8.0.3 while the Version line read 1.8.4, so the checker returned rc=2 "missing source" on both positives — 11/2; the heading fix restored 13/13). The mutation code needed NO edit — derivation tracked 1.8.4, exactly as WS1's guard proof predicted. Test-only version assertions: `backend/tests/integration/test_v6_backend_api.py` (7 literals) and `frontend/src/pages/Settings.test.tsx` (3 mock versions + the `/1\.8\.4/` regex literal — single backslash, replaced literally, the v8.0.3 trap). Runner labels: `test-all.sh`, `test-all.ps1`, `verify-release.sh`. CI comment: `.github/workflows/ci.yml:290`. Guides: `docs/REVIEWER_GUIDE.md` 31/35 (v8.0.4 ZIP name), 38 (label), 492 (release version); `docs/WINDOWS_SETUP.md` 95/99 (ZIP name + label), 327 ("was fixed in v8.0.3 and now reads the release version 1.8.4" — history preserved, current version correct per the checker's no-history-sections rule for the guides), 333 (release version). Historical 1.8.3 mentions left untouched: `scripts/test-matrix.md` v8.0.3 note, `README.md:419` (v8.0.2 history), the v8.0.3 manifest/log sections, and the `1.8.2` header comment in `test-version-contract.sh` documenting the defect. **13/13 re-run after the LAST bump: PASS, rc=0** (see the measured-results rows). || WS2 — CI regression coverage (Coverage Closure 2) (`.github/workflows/ci.yml`, `scripts/test-ps1-selection.sh`) | The delivered `ci.yml` executed neither the new `scripts/test-ps1-selection.sh` nor the separate `scripts/test-version-contract.sh` negative fixtures (the only version step ran the checker on the real tree). Two new scripts-lane steps: **Version-contract negative fixtures (IF-V5-05)** — `bash scripts/test-version-contract.sh` (stdlib-only; no Docker, no venv, no network, no live Keycloak); and **PowerShell selection regression (IF-V8.0.2-B, v8.0.3/v8.0.4)** — the pinned backend freeze is installed first (PyPI, like the WS3 step), then `bash scripts/test-ps1-selection.sh` in default mode (static wiring, exact 520 = 516 + 4 split, real offline pytest with no provider on 8080, no-docker / daemon-dead / quoting / stub `-Offline` probes under the pwsh installed earlier in the lane). **Portability:** the v8.0.3 script hard-coded `"$HOME/workspace"` scratch (`mktemp -d` lines for the disposable venv and the temp tree copy), which does not exist on a GitHub Actions runner; the scratch root is now `$RUNNER_TEMP`, then `$TMPDIR`, then `$HOME/workspace` if it exists, then `/tmp` — the small `/tmp/ws1-v803-*.log` probe files stay on `/tmp` (a few KB; only the 46 MB tree copy + venv need real disk). The `VERSION_CONTRACT` label expectation is also derived from the checker's own `--expected` default (plus a label-version-exclusivity check), so the suite stays green across the coordinator's 1.8.4 bump — a literal here would go stale the way the 1.8.2 seds did. **What runs vs what stays NOT RUN:** in CI, the version fixtures (13 checks) and the ps1 regression default mode (34 checks) run, stub/offline-only; the ps1 `--live` mode, Windows PowerShell 5.1, real-Docker execution of the LIVE gate, and GitHub Actions execution itself stay NOT RUN — the workflow comments say so at each step, and the keycloak-e2e lane (manual `workflow_dispatch`) remains the only CI path that runs the live gates. **YAML validated locally** (`yaml.safe_load`: 4 jobs; scripts lane 25 steps). |
| WS2 — verify-release fail-closed checks (Coverage Closure 3) (`scripts/verify-release.sh`) | `REQUIRED_FILES` did not name `scripts/loopback-forwarder.py` or `scripts/test-ps1-selection.sh`, and the `TEST_ALL_PS1` static gate checked only parameters + `Invoke-Native` — a future ZIP could omit either file or drop the LIVE gate while the static audit passed. Both files are now in `REQUIRED_FILES`; `scripts/loopback-forwarder.py` is added to the `LIVE_GATE_SYNTAX` py-compile list; and `TEST_ALL_PS1` additionally asserts the 19-gate offline/live wiring (OFFLINE_UNIT `python -m pytest -q -m 'not live_keycloak'` with no unfiltered `pytest -q` remaining, `LIVE_PROVIDER_PYTEST` present, the forwarder `127.0.0.1:8080 keycloak:8080`, `pytest -v -m live_keycloak`, `"4 passed"`, 19 unique `Invoke-Gate` IDs) — all still STATIC greps, and the gate comment says so: the live gates themselves run only in `test-all.sh --full` / `test-all.ps1 -Full` with a real daemon + Keycloak, and a green static gate here must never be read as "the live gates passed". No new gate is added, so the check count stays 28 (23 PASS / 0 FAIL / 5 NOT RUN shape on a clean tree). Proof: disposable-copy negative controls (see the measured-results rows) — removing either file makes `verify-release.sh` exit 1 with `REQUIRED_FILES` FAIL. |
| Findings register (`docs/PENTEST_FINDINGS_AND_REMEDIATIONS.md`) | No change. IF-V8-42 (Dockerfiles run as root) and IF-V8-43 (CI SHA pins) stay **OPEN** with their reviewer checklists. No Docker/CI pass is claimed. |

### Measured results (WS1, v8.0.4)

| Gate | Result |
| ---- | ------ |
| version-contract fixtures, failing-first (WS1) | **REPRODUCED on the pristine tree: rc=1, 8 passed / 5 failed** (`bash scripts/test-version-contract.sh`, 2026-11-13 ~20:52 CST, before any edit). FAILED: `manifest version negative`, `pyproject version negative`, `package.json version negative`, `package-lock.json version negative`, `__init__ __version__ negative` — each "expected nonzero exit, got rc=0: version-contract: expected 1.8.3". Root cause, exact lines: `scripts/test-version-contract.sh:120–129` — five `sed -i 's/1\.8\.2/1.5.0/'` mutations (manifest, pyproject, package.json, package-lock with `/g`, `__init__`); the generated fixtures contain 1.8.3, so the seds change nothing. The other three negatives (FastAPI version, health version, hard-coded UI literal — 1.8.3 literals) pass; all positives pass. Evidence: `~/workspace/ws1-v804-evidence/failing-first-8-5.log`, `failing-first-lines-120-129.txt`. |
| version-contract fixtures, after fix (WS1) | **13/13 PASS, rc=0** (`bash scripts/test-version-contract.sh`, same tree after the fix). All 13 cases: all-agree PASS at 1.8.3; `__version__`-derivation PASS at 1.8.3 + negative FAILS (rc=1); one-source-differs FAILS (rc=1) for manifest, pyproject, package.json, package-lock.json, `__init__`, FastAPI version, health version, hard-coded UI literal; missing-source FAILS (rc=2); malformed `--expected` FAILS (rc=2). Per-case mutated-fixture evidence in the log: each negative prints the mutated line (e.g. manifest `- **Version:** 1.5.0 (Operation Trustline v8.0.3)`, lockfile both slots `1.5.0`/`1.5.0` — 2 occurrences mutated) and the checker's MISMATCH line (e.g. `MISMATCH docs/RELEASE_MANIFEST.md (Trustline v8.0.3 section): 1.5.0 (expected 1.8.3)`). Evidence: `~/workspace/ws1-v804-evidence/after-fix-13-13.log`. |
| version-contract, real tree (WS1) | **PASS 1.8.3, rc=0** (`python3 scripts/check-version-contract.py` on the v8.0.4 tree, pre-bump: all sources agree at 1.8.3, FastAPI + health via `__init__.__version__`). The coordinator re-runs it after the 1.8.4 bump + checker retarget. |
| future-bump guard proof (WS1) | **PROVEN in disposable copies** (home disk, deleted after; logs kept): the simulated coordinator bump (`~/workspace/ws1-v804-evidence/bump-to-184.py` — fixture literals 1.8.3 → 1.8.4 in `build_fixture` only, checker default + section regex → 1.8.4 / v8.0.4; diff-verified to touch ONLY those lines, never the mutation code) was applied identically to two copies. Fixed script: **13/13 PASS, rc=0** — derivation tracked 1.8.4 (`mutated docs/RELEASE_MANIFEST.md: 1 occurrence(s) of '1.8.4' -> '1.5.0'`, lockfile 2 occurrences, checker `expected 1.8.4`). Pristine v8.0.3 script under the same bump: **5 passed / 8 failed, rc=1** — all eight negatives fail (the five stale 1.8.2 seds, the FastAPI/health 1.8.3 seds, and the derivation negative), proving the derivation + assertion is what makes the suite bump-proof. Evidence: `guard-proof-184-new-script-13-13.log`, `guard-proof-184-old-script.log`, `bump-to-184.py`. |
| docs-contract (WS1) | **FAIL — 8 violations, all in the two guides** (`python3 scripts/validate-docs-contract.py`, after the v8.0.4 sections landed; baseline before the doc edits was PASS, 0 violations — `docs-contract-baseline.txt`). Adding the v8.0.4 section as the last manifest section makes checks 5/6a/6b compare the guides against the v8.0.4 archive / 1.8.4, which the coordinator's Pass B has not applied yet: check 5 — `docs/REVIEWER_GUIDE.md:31`, `:35` and `docs/WINDOWS_SETUP.md:95` name the v8.0.3 ZIP; check 6a — `REVIEWER_GUIDE.md:38`, `WINDOWS_SETUP.md:99` name label `v8.0.3`; check 6b — `REVIEWER_GUIDE.md:492`, `WINDOWS_SETUP.md:327`, `:333` say "release version 1.8.3". All 8 are the expected, pre-announced Pass B mechanical items (same shape as v8.0.3 WS2 finish: 4 violations, all REVIEWER_GUIDE). Check 7 stays green (counts line unchanged: 520 / 19); no other check flags. Evidence: `~/workspace/ws1-v804-evidence/docs-contract-after-manifest.txt`. |
| docs-contract-paths (WS1) | **48/48 PASS** (re-run after the doc edits; the suite builds its own fixtures, so the new sections cannot change it — verified by re-running, not assumed). |
| CI gap evidence — Coverage Closure 2 (WS2) | `grep` on the delivered v8.0.3 tree (exact file/line evidence, `~/workspace/ws2-v804-evidence/00-gap-evidence.txt`) | **REPRODUCED.** `.github/workflows/ci.yml`: **0 occurrences** of `test-ps1-selection` and **0 occurrences** of `test-version-contract.sh` — the only version step ran `python3 scripts/check-version-contract.py` (ci.yml:284); the ps1-adjacent steps present were `test-ps1-native.sh`, `test-ps1-preflight.sh`, `test-offline-provider-selection.sh`. `scripts/verify-release.sh`: `loopback-forwarder.py` and `test-ps1-selection.sh` **absent** from `REQUIRED_FILES` (both files exist in the tree); the `TEST_ALL_PS1` gate (line 246) checked only parameters + `Invoke-Native` — the sole `LIVE_PROVIDER_PYTEST` mention in the file was a comment ("LIVE_PROVIDER_PYTEST, not here"). `scripts/test-ps1-selection.sh`: hard-coded scratch at lines 264 (`VENV_TMP`, `mktemp -d "$HOME/workspace/.tmp-ps1venv.XXXXXX"`) and 348 (`SCRATCH`, `mktemp -d "$HOME/workspace/.tmp-ps1probe.XXXXXX"`); lines 124–125 are a pwsh binary lookup fallback, not scratch, and are kept. |
| ps1-selection portability (WS2) | `scripts/test-ps1-selection.sh` (portable scratch root + derived label expectation) | **LANDED.** New `SCRATCH_ROOT`: `${RUNNER_TEMP:-${TMPDIR:-}}`, then `$HOME/workspace` if it exists, then `/tmp`; both `mktemp -d` lines use it. The `VERSION_CONTRACT` label expectation is derived from the checker's own `--expected` default (`grep -oE 'default="[0-9]+\.[0-9]+\.[0-9]+"'` on `scripts/check-version-contract.py`) with a fail-loud empty check, plus a new label-version-exclusivity check (the label line must name no version other than the derived one) — the suite gains **+1 check** (33 → 34 default, 35 → 36 live) so it stays green across the coordinator's 1.8.4 bump. `bash -n` clean. The remaining `$HOME/workspace` references are the documented fallback (lines 83–84), the pwsh lookup (141–142), and comments. |
| ps1-selection proof — portable form (WS2) | `bash scripts/test-ps1-selection.sh` (default + `--live`, working tree, v7.3.1 venv python, `import identityforge` verified to resolve to the v8.0.4 tree) | **Default: 34 passed, 0 failed, 1 skipped, rc=0** (Keycloak down, 8080 free). **`--live`: 36 passed, 0 failed, 1 skipped, rc=0** (Keycloak 26.8.2 host process started by WS2 from `~/workspace/.trustline-live/` — `kc.sh start-dev --import-realm`, Temurin JRE, `KC_HOSTNAME=http://127.0.0.1:8080`; discovery 200 with the canonical issuer `http://127.0.0.1:8080/realms/identityforge-lab`; stopped cleanly after, 8080 free). Live checks pass: forwarder serves real discovery through 127.0.0.1:18080 with the canonical issuer intact, live selection passes with rc=0 AND "4 passed". Baseline before the change (v8.0.3 form): 33/0/1 default — the +1 in both modes is the new label-version-exclusivity check. The 1 skip in both is the runtime teardown probe (pwsh TcpClient loopback quirk, same as v8.0.3). Logs `02-ps1-selection-baseline-default.log`, `03-ps1-selection-portable-live.log`, `04-ps1-selection-portable-default.log`, `keycloak-v804.log`. |
| CI steps + clean-checkout proof (WS2) | `.github/workflows/ci.yml` (two new scripts-lane steps); fresh extraction-shaped copy `~/workspace/.verify/ws2-v804-clean/` + disposable venv from the freeze | **LANDED + PROVEN.** Scripts lane grows 23 → **25 steps**: `Version-contract negative fixtures (IF-V5-05)` (`bash scripts/test-version-contract.sh`, stdlib-only) after the Version contract step, and `PowerShell selection regression (IF-V8.0.2-B, v8.0.3/v8.0.4)` (freeze install + `bash scripts/test-ps1-selection.sh`, default mode) after the Offline/provider selection step; lane + step comments state what runs vs what stays NOT RUN. **YAML valid** (`yaml.safe_load`: 4 jobs; scripts lane 25 steps). **Clean-checkout proof:** the exact CI step commands run in a fresh copy of the tree (not the live working tree) with a disposable venv from `backend/requirements-freeze.txt`: version fixtures **13/13 PASS, rc=0**; ps1 selection **34 passed, 0 failed, 1 skipped, rc=0** — run with `HOME` pointed at a nonexistent dir and `RUNNER_TEMP` set, proving the portable `$RUNNER_TEMP` branch end-to-end (no `$HOME/workspace` anywhere on that path). **GitHub Actions execution NOT RUN** — the workflow must still run for real on a runner; a YAML-valid workflow is not an executed one. Logs `05-ci-clean-version-fixtures.log`, `06-ci-clean-ps1-selection.log`. |
| ps1 negative controls (WS2) | Disposable copies `~/workspace/.verify/ws2-v804-neg-a/` (OFFLINE_UNIT selection removed) and `ws2-v804-neg-b/` (LIVE gate dropped); `bash scripts/test-ps1-selection.sh`, default mode | **PROVEN — both FAIL as required, rc=1.** (a) `python -m pytest -q -m 'not live_keycloak'` → `python -m pytest -q` in `test-all.ps1:483`: **31 passed, 3 failed, 1 skipped** — FAILs: "OFFLINE_UNIT does not run -m 'not live_keycloak'", "an unfiltered 'python -m pytest -q' (no -m selection) is still present", quoting probe "pytest did NOT receive one 'not live_keycloak' argument". (b) `Invoke-Gate "LIVE_PROVIDER_PYTEST" "full"` → `"LIVE_PROVIDER_PYTEST_X"` (`test-all.ps1:696`, Skip-Gates untouched): **32 passed, 2 failed, 1 skipped** — FAILs: "LIVE_PROVIDER_PYTEST Invoke-Gate (full) missing", "LIVE_PROVIDER_PYTEST is not BOOT_OK-gated". Note: the 19-unique-gate count check still passes in (b) — a rename preserves the count; the presence + BOOT_OK checks are the tripwire for that mutation. The working tree was never mutated; both copies are disposable. Logs `07-neg-a-offline-selection-removed.log`, `08-neg-b-live-gate-dropped.log`. |
| verify-release fail-closed checks + negative controls (WS2) | `scripts/verify-release.sh` (REQUIRED_FILES + LIVE_GATE_SYNTAX + TEST_ALL_PS1 wiring); disposable copies `~/workspace/.verify/ws2-v804-vr-neg-fwd/` (helper removed) and `ws2-v804-vr-neg-sel/` (regression removed); full `verify-release.sh` on each + on an intact fresh copy `~/workspace/.verify/ws2-v804-final/` | **PROVEN.** Helper removed → **exit 1, 20 PASS / 3 FAIL / 5 NOT RUN**: `REQUIRED_FILES` **FAIL**, `LIVE_GATE_SYNTAX` **FAIL** (`[Errno 2] No such file or directory: 'scripts/loopback-forwarder.py'`), `TEST_ALL_PS1` **PASS** (the wiring in `test-all.ps1` is intact — only the file is gone). Regression removed → **exit 1, 21 PASS / 2 FAIL / 5 NOT RUN**: `REQUIRED_FILES` **FAIL**, `LIVE_GATE_SYNTAX` **PASS**, `TEST_ALL_PS1` **PASS**. The third/second FAIL in each run is `DOCS_CONTRACT` — the 8 pre-announced guide violations (Pass B item, same as WS1's row). NOT RUN in both: `COMPOSE_YAML`, `COMPOSE_HEALTHCHECK` (venv python lacks PyYAML — same as v8.0.3), `FRONTEND_BUILD`, `COMPOSE_CONFIG`, `NPM_FULL_LOCKFILE_AUDIT`. **Intact tree (positive proof): 22 PASS / 1 FAIL / 5 NOT RUN, exit 1** — sole FAIL `DOCS_CONTRACT` (guides); `REQUIRED_FILES`, `LIVE_GATE_SYNTAX`, `TEST_ALL_PS1` (extended wiring gate), `BACKEND_PYTEST` all **PASS**. The check count is unchanged at 28 — no gate was added. The owner's original ZIP and the working tree were never modified; the removals happened only in the disposable copies. Logs `09-vr-neg-forwarder-removed.log`, `10-vr-neg-ps1selection-removed.log`, `11-verify-release-intact-tree.log`. |
| version fixtures — independent re-runs (WS2) | `bash scripts/test-version-contract.sh` (working tree + clean copy, after WS1's concurrent fix) | **13/13 PASS, rc=0 in both** (working tree re-run 2026-11-14 ~03:01 UTC; clean-checkout copy — see the CI proof row). WS2's own failing-first capture, taken before WS1's fix landed in the shared tree, read **8 passed / 5 failed, rc=1** (log `01-version-contract-baseline.log`; evidence `00-gap-evidence.txt` lines 120–129) — the same defect WS1's rows describe; WS2 did not touch the file (WS1 owns it) and the fix arrived concurrently at 02:53:53 UTC. The coordinator still re-runs 13/13 after the LAST 1.8.4 bump (fixture literals + checker default move then; the mutation code needs no edit). |
| Docs-contract + docs-contract-paths after WS2 doc edits (WS2) | `python3 scripts/validate-docs-contract.py`; `bash scripts/test-docs-contract-paths.sh` on the finished tree | **Docs-contract: FAIL — 8 violations, all in the two guides** (34 FailureReason values, 59 report-model fields, 126 source files harvested, 71 files scanned) — the same 8 WS1 reported (check 5: `REVIEWER_GUIDE.md:31`, `:35`, `WINDOWS_SETUP.md:95` name the v8.0.3 ZIP; check 6a: `REVIEWER_GUIDE.md:38`, `WINDOWS_SETUP.md:99` name label `v8.0.3`; check 6b: `REVIEWER_GUIDE.md:492`, `WINDOWS_SETUP.md:327`, `:333` say "release version 1.8.3"). **No new violation from WS2's rows** — check 7 stays green (counts line unchanged: 520 / 19). All 8 are the expected Pass B mechanical items (guides + bump). **Docs-contract-paths: PASS — 48/48.** Logs `12-docs-contract-after-ws2.log`, `13-docs-contract-paths-after-ws2.log`. |
| Stray-artifact cleanup + final tree diff (WS2) | Working tree; `diff -rq` vs a fresh extraction of the delivered v8.0.3 ZIP | **Final tree clean and final diff exactly 6 files, none added or removed.** The in-tree pytest runs recreated `backend/data/identityforge.db` + `backend/.pytest_cache/` in the working tree (known behavior — even `--collect-only` creates the DB; WS1's log row records the same recurrence from WS2's PID 6655 run); removed after the runs, verified gone before the final diff (no `*.db`, no caches, no `test-results/`). Final `diff -rq` vs the fresh ZIP extraction: **6 files differ** — `.github/workflows/ci.yml`, `scripts/test-ps1-selection.sh`, `scripts/verify-release.sh` (WS2); `scripts/test-version-contract.sh` (WS1); `docs/RELEASE_MANIFEST.md`, `docs/VERIFICATION_LOG.md` (shared). File count stays **371**. Evidence dir `~/workspace/ws2-v804-evidence/` lives outside the tree. |

| Pass B — 1.8.4 bump (coordinator) | Code sources + checker + fixtures + assertions + labels + CI comment + guides (see the Scope row) | **LANDED 2026-11-14.** Fixture literals moved FIRST, then the checker retarget, then code, assertions, labels, CI comment, guides. Intermediate proof the derivation works: after the fixture literals moved but before the checker retarget, fixtures read **11 passed / 2 failed** — the two positives failed because the checker still expected 1.8.3 while the fixtures carried 1.8.4 (mutated lines already showed `1.8.4 -> 1.5.0`); after the heading fix + checker retarget, **13/13 PASS, rc=0**. The only remaining `1.8.2` in `test-version-contract.sh` is the header comment documenting the defect. Evidence: `~/workspace/passa-v804-evidence/version-fixtures-after-fixture-bump.txt` (11/2), `version-fixtures-after-bump.txt` (11/2, heading), `version-fixtures-after-bump-final.txt` (13/13). |
| Pass B — version fixtures 13/13 after the LAST bump (coordinator) | `bash scripts/test-version-contract.sh` on the bumped tree | **13 passed, 0 failed, rc=0.** All 13 cases green at 1.8.4. Per-case mutated-fixture evidence in the log: `mutated docs/RELEASE_MANIFEST.md: 1 occurrence(s) of '1.8.4' -> '1.5.0'`, line 5 `- **Version:** 1.5.0 (Operation Trustline v8.0.4)`, checker `MISMATCH docs/RELEASE_MANIFEST.md (Trustline v8.0.4 section): 1.5.0 (expected 1.8.4)` rc=1; pyproject `version = "1.5.0"` rc=1; package.json `"version": "1.5.0"` rc=1; package-lock 2 occurrences `1.5.0`/`1.5.0` rc=1; `__init__` `__version__ = "1.5.0"` rc=1; FastAPI/health/UI-literal likewise rc=1. Evidence: `~/workspace/passa-v804-evidence/version-fixtures-after-bump-final.txt`. |
| Pass B — source version contract (coordinator) | `python3 scripts/check-version-contract.py` on the bumped tree | **PASS — all authoritative versions equal 1.8.4, rc=0** (manifest v8.0.4 section, pyproject, `__init__`, FastAPI + health, package.json + lockfile). |
| Pass B — backend pytest (coordinator) | `python -m pytest -p no:cacheprovider` (v7.3.1 venv python, `PYTHONPATH=backend/src`, Keycloak up) | **520 passed, 3 warnings, rc=0** (166.81s). Evidence: `~/workspace/passa-v804-evidence/pytest-full-passb.txt`. |
| Pass B — offline selection, Keycloak ABSENT (coordinator) | Keycloak stopped by exact PID (java 21639, port 8080 free, discovery 000); `pytest -m "not live_keycloak"` | **516 passed, 4 deselected, 3 warnings, rc=0** (101.14s). Evidence: `~/workspace/passa-v804-evidence/pytest-offline-kc-absent-passb.txt`. |
| Pass B — live selection, Keycloak PRESENT (coordinator) | Keycloak 26.8.2 restarted (discovery 200); `pytest -m "live_keycloak"` | **4 passed, 516 deselected, 1 warning, rc=0** (3.95s). Evidence: `~/workspace/passa-v804-evidence/pytest-live-kc-present-passb.txt`. |
| Pass B — WS3 (coordinator) | Disposable venv from `backend/requirements-freeze.txt` + `backend/requirements-test.txt` (hypothesis 6.170.15); `pytest scripts/pentest/ws3/` | **51 passed, 3 warnings, rc=0** (46.88s). Evidence: `~/workspace/passa-v804-evidence/ws3-51-passb.txt`. |
| Pass B — CLI (coordinator) | `python -m identityforge.cli verify-all` | **18/18 scenarios PASS.** |
| Pass B — ruff / typecheck (coordinator) | `ruff check` + `ruff format --check` (68 files); `npm run typecheck` | **Ruff: all checks passed, 68 files already formatted. Typecheck rc=0.** |
| Pass B — Vitest / build (coordinator) | `npm run test -- --run`; `npm run build` | **Vitest 161/161 (13 files). Build byte-identical: `dist/assets/index-X2bsjLBG.js`, SHA-256 `a77dd7d5…` — UI unchanged.** Preview 200 after rebuild (the extracted tree ships no `dist/`; same tree artifact as v8.0.3 Pass C). |
| Pass B — docs contracts (coordinator) | `validate-docs-contract.py`; `test-docs-contract-paths.sh`; `test-dependency-gates.sh` | **Docs-contract PASS. Docs-contract-paths 48/48 PASS. Dependency-gates 55 passed, 0 failed.** The 8 guide violations WS1/WS2 reported are CLOSED by the bump (guides now name the v8.0.4 archive / 1.8.4). |
| Pass B — test-all.sh --offline (coordinator) | `bash scripts/test-all.sh --offline` | **rc=0, 11 PASS / 0 FAIL / 8 NOT RUN, 19 gates** (`test-results/gates.json`: Counter PASS 11, NOT RUN 8). Evidence: `~/workspace/passa-v804-evidence/test-all-offline-passb.txt`. |
| Pass B — regressions / PS matrix (coordinator) | `test-compose-healthcheck-regressions.sh`; `test-compose-healthcheck-ps-matrix.ps1` (pwsh 7.4.6) | **Regressions 34 passed, 0 failed, 0 not run, rc=0. PS matrix 26 passed, 0 failed, 0 not run, rc=0.** Evidence: `~/workspace/passa-v804-evidence/regressions-passb.txt`, `ps-matrix-passb.txt`. |
| Pass B — provider-selection regression (coordinator) | `test-offline-provider-selection.sh` (offline + `--live`) | **Offline 11 passed, 0 failed, rc=0** (Keycloak absent). **`--live` 11 passed, 0 failed, rc=0** (Keycloak present; live selection passes, 4 tests). Evidence: `~/workspace/passa-v804-evidence/provider-selection-offline-passb.txt`, `provider-selection-live-passb.txt`. |
| Pass B — ps1-selection regression, portable form (coordinator) | `test-ps1-selection.sh` (default + `--live`) | **Default 34 passed, 0 failed, 1 skipped, rc=0** (Keycloak absent). **`--live` 36 passed, 0 failed, 1 skipped, rc=0** (Keycloak present; forwarder + live selection PASS rc=0 AND "4 passed"). The 1 skip in both is the runtime teardown probe (pwsh TcpClient loopback quirk, same as v8.0.3). Evidence: `~/workspace/passa-v804-evidence/ps1-selection-default-passb.txt`, `ps1-selection-live-passb.txt`. |
| Pass B — CI steps, local proof (coordinator) | Exact CI step commands from a fresh copy of the bumped tree (`~/workspace/.verify/ws2-v804-clean-passb/`, tar copy; tar ownership warnings cosmetic, files extracted) | **Version fixtures 13/13 PASS, rc=0** from the clean copy (evidence `~/workspace/passa-v804-evidence/ci-clean-version-fixtures-passb.txt`). The ps1 default step was proven on the working tree above (34/0/1) and by WS2 from a clean copy with `HOME` at a nonexistent dir + `RUNNER_TEMP` set (34/0/1). **CI YAML valid** (`yaml.safe_load`: 4 jobs; scripts lane 25 steps; both new steps present). **GitHub Actions execution NOT RUN.** |
| Pass B — live gate all (coordinator) | `scripts/live-gate.py all` (host-process Keycloak + dev backend, v8.0.4 tree) | **101 PASS / 0 FAIL, rc=0** (run twice; both rc=0, second run 101/101). Dev counts before: runs 36, live_login_events 0, events 62; after: live_login_events 104, live_logins 104, successful 12, incomplete 2. Evidence: `~/workspace/passa-v804-evidence/live-gate-all-full-passb.txt`. |
| Pass B — live gate reset (coordinator) | Disposable marker backend (marker `38020498-51ca-4012-b250-20e4efd14fb8`, temp DB `/tmp/tmp.kNcy0u7cOS`, port 8000) | **69 PASS / 0 FAIL, rc=0.** Marker matched the backend-reported `disposable_project_id`. Temp DB removed after; dev backend restored. Dev DB-backed counts byte-identical on restore (runs 36, live_login_events 104, live_login_transactions 16, observed 12, successful 12, incomplete 2, live_logins 104, events 62); only in-memory `sessions` 4→0 and `sessions_total_issued` 12→0 changed — documented restart semantics. Evidence: `~/workspace/passa-v804-evidence/live-gate-reset-passb.txt`, `counts-pre-reset-passb.json`, `counts-after-restore-passb.json`. |
| Pass B — guard negatives (coordinator) | `live-gate.py reset` (no flag / wrong id / malformed) against the restored dev backend | **no-flag rc=2, wrong-id rc=1, malformed rc=2.** Dev counts untouched after (runs 36, live_login_events 104, events 62). |
| Pass B — Playwright + validator + axe (coordinator) | `npx playwright test` (no `--project`; the config defines no named projects — the first attempt with `--project=chromium` failed immediately, "Project(s) chromium not found", and was discarded, not counted) | **72 passed + 1 skipped, rc=0** (3.8m). **Validator PASS**: total 73, passed 72, failed 0, skipped 1, timedOut 0, flaky 0 (target `host-lab`); allowed skip kept: edge.spec.ts 'user cancels at the Keycloak login page'. **Axe 25/25 passed, 0 violations** (each a11y test asserts `violations` toEqual `[]`, from the real report JSON). **131 PNGs** in the tree screenshots dir. **Security headers live on preview**: CSP + `X-Frame-Options: DENY` + `X-Content-Type-Options: nosniff`. Evidence: `~/workspace/passa-v804-evidence/playwright-passb-stdout.txt`, `playwright-epoch-passb.txt` (epoch 1794628177). |
| Pass B — test-all.ps1, Docker absent (coordinator) | `~/workspace/.pwsh/pwsh -File scripts/test-all.ps1` (pwsh 7.4.6, Linux; no docker/dockerd/podman binary) | **TRUE rc=1** (measured without a pipe — a piped run reads tail's rc=0, the same trap as v8.0.3's coordinator note): `ERROR: Docker is not available. Install Docker Desktop for Windows and make sure the Docker daemon is running, then re-run this script.` **No `test-results/gates.json` written.** Evidence: `~/workspace/passa-v804-evidence/test-all-ps1-docker-absent-passb.txt`. Windows PowerShell 5.1 + Docker Desktop execution NOT RUN — reviewer gate. |
| Pass C — version fixtures 13/13 after the LAST bump (parent) | `bash scripts/test-version-contract.sh` on the final tree (parent's own run, 2026-11-13 ~21:50 CST) | **13 passed, 0 failed, rc=0.** Summary line: `version-contract test: 13 passed, 0 failed`. Per-case mutated-fixture proof in the log: `mutated backend/src/identityforge/__init__.py: 1 occurrence(s) of '__version__ = "1.8.4"' -> '__version__ = "1.5.0"'`, `mutated line: 1:__version__ = "1.5.0"`, `PASS: __version__ derivation at 1.5.0 -> FAILS (rc=1)`; manifest `- **Version:** 1.5.0 (Operation Trustline v8.0.4)` / `MISMATCH … (Trustline v8.0.4 section): 1.5.0 (expected 1.8.4)` rc=1; pyproject `version = "1.5.0"` rc=1; package.json `"version": "1.5.0"` rc=1; package-lock 2 occurrences rc=1; FastAPI/health/UI-literal likewise rc=1. **Clean-copy re-run: 13/13, rc=0** (fresh `cp -r` copy `~/workspace/.verify/v804-ci-clean/`, same command). Evidence: `~/workspace/passc-v804-evidence/test-version-contract-passc.txt`, `ci-clean-fixtures-passc.txt`. |
| Pass C — source version contract (parent) | `python3 scripts/check-version-contract.py` on the final tree | **PASS — all authoritative versions equal 1.8.4, rc=0.** |
| Pass C — gate battery (parent) | pytest full / offline (KC absent) / live (KC present) / WS3 / CLI / ruff / typecheck / Vitest+build / docs / dep-gates / test-all --offline / regressions / PS matrix / provider-selection / ps1-selection / CI steps locally | **All green, parent's own runs, sequential:** pytest **520 passed, 3 warnings, rc=0** (159.07s); offline selection **516 passed, 4 deselected, rc=0** (Keycloak ABSENT — discovery 000, java stopped by exact PID); live selection **4 passed, 516 deselected, rc=0** (Keycloak PRESENT, discovery 200); WS3 **51 passed, rc=0** (disposable venv, hypothesis 6.170.15); CLI **18/18 scenarios PASS**; ruff check clean + format clean (68 files); typecheck rc=0; Vitest **161/161** (13 files); build byte-identical **`a77dd7d5…`** (`index-X2bsjLBG.js`, 170.04 kB / 55.20 kB gzip); docs-contract **PASS**; docs-contract-paths **48/48**; dep-gates **55/0**; test-all --offline **11 PASS / 0 FAIL / 8 NOT RUN, 19 gates, rc=0** (LIVE_PROVIDER_PYTEST correctly NOT RUN in the offline profile); regressions **34/0/0**; PS matrix **26/0/0**; provider-selection **11/11 offline + 11/11 live**; ps1-selection **34/0/1 default + 36/0/1 --live** (portable form; 1 skip = runtime teardown probe, pwsh TcpClient loopback quirk); CI steps locally from a clean copy: fixtures **13/13** + ps1 default **34/0/1** twice — variant A (real HOME + `RUNNER_TEMP` set) and variant B (`HOME` at a nonexistent dir + pwsh on PATH + `RUNNER_TEMP` set), proving no `$HOME/workspace` dependency. CI YAML valid (4 jobs, scripts lane 25 steps). Evidence: `~/workspace/passc-v804-evidence/`. |
| Pass C — live gate all + reset (parent) | `scripts/live-gate.py all`; `reset` on a disposable marker backend (temp DB) | **all 101 PASS / 0 FAIL, rc=0** (101 `[PASS]` lines, 0 `[FAIL]`, `"passed": true`). **reset 69 PASS / 0 FAIL, rc=0** (marker `00a90d6e-7694-4107-8a10-3a69fbf9b7c6`, temp DB `/tmp/marker-v804-passc.db`, removed after; marker matched the backend-reported `disposable_project_id`; dev backend stopped for the whole swap, `dev 000`). Guard negatives against the marker backend: **no-flag rc=2, wrong-id rc=1, malformed rc=2.** Dev counts, honestly: the parent's pre-live-gate snapshot read runs 95, live_login_events 286, live_logins 286, observed/verified 40, incomplete 6, events 157; after the restore it read runs 95, live_login_events 338, live_logins 338, observed/verified 46, incomplete 7, events 157. The live_login_* growth (+52 events, +6 successful, +1 incomplete) is the live-gate `all` run's own real logins against the dev backend, recorded BEFORE the reset swap — the reset itself touched nothing in the dev DB (marker backend + temp DB only, dev backend stopped). **runs (95) and events (157) are unchanged across the reset** — the counters a reset would have wiped. Only in-memory `sessions` 26→0 and `sessions_total_issued` 28→0 changed on restart (documented restart semantics). Evidence: `~/workspace/passc-v804-evidence/live-gate-all-passc.txt`, `live-gate-reset-passc.txt`, `counts-before-live-gate-passc.json`, `counts-after-restore-passc.json`, `marker-id-passc.txt`. |
| Pass C — Playwright + validator + axe (parent) | `npx playwright test` (no `--project`) | **72 passed + 1 skipped, rc=0** (3.8m). **Validator PASS**: total 73, passed 72, failed 0, skipped 1, timedOut 0, flaky 0 (target `host-lab`, epoch 1794629723); allowed skip kept: edge.spec.ts 'user cancels at the Keycloak login page'. **Axe 25/25 passed, 0 violations** — 25 a11y tests in the real report JSON, all passed; the in-suite zero-tolerance assertion is `expect(results.violations, …).toEqual([])` (`e2e/a11y.spec.ts:49`); 23 `axe <label>: 0 violations` lines in the report (the other 2 a11y tests are keyboard/focus tests with no axe scan). **131 PNGs.** **Security headers live on preview**: CSP + `X-Frame-Options: DENY` + `X-Content-Type-Options: nosniff` (parent's own curl). Evidence: `~/workspace/passc-v804-evidence/playwright-passc.txt`. |
| Pass C — test-all.ps1, Docker absent (parent) | `~/workspace/.pwsh/pwsh -File scripts/test-all.ps1` (pwsh 7.4.6, Linux) | **TRUE rc=1** (measured without a pipe): `ERROR: Docker is not available. Install Docker Desktop for Windows and make sure the Docker daemon is running, then re-run this script.` **No `test-results/gates.json` written by this run** — the gates.json present in the tree is the earlier `test-all.sh --offline` artifact (mtime 2026-11-13 22:06:13, 19 gates, 11 PASS / 8 NOT RUN), untouched by the ps1 attempt. Windows PowerShell 5.1 + Docker Desktop execution NOT RUN — reviewer gate. Evidence: `~/workspace/passc-v804-evidence/ps1-docker-absent-passc.txt`. |
| Pass C — FINAL ZIP clean-room (parent) | `python3 scripts/package-zip.py` then fresh extractions of the actual ZIP bytes + `./scripts/verify-release.sh`, pytest, CLI, docs-contract, dependency-gates, `npm ci` + Vitest + build | **Final ZIP: `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V8.0.4_FINAL_20261113.zip` — 371 files, testzip clean, 0 forbidden entries, 131 screenshots, all 32 `.sh` entries mode 0770, `scripts/loopback-forwarder.py` + `scripts/test-ps1-selection.sh` present, no egg-info, no `.db`/`.pem`/`.key`/`.p12` inside.** (Byte count and SHA-256 are properties of the ZIP file itself, so they live in the delivery message only.) Three fresh extractions (plain `~/workspace/.verify/v804-final-plain`, `~/workspace/.verify/v804 final spaces`, `~/workspace/.verify/data/v804-final-data`): `verify-release.sh` **23 PASS / 0 FAIL / 5 NOT RUN in all three, rc=0** (counted from each run's `test-results/verify-release.json` summary — the authoritative count; the 5 NOT RUN are the bare-extraction deps/Docker checks, honest environment reasons). Docs-contract **PASS from the `data/`-ancestor extraction** (in that run's 23 PASS). Double-run proof in the plain extraction: run 1 and run 2 identical 23/0/5 rc=0, 28 gate lines identical, 0 FAIL, no `backend/data/` left in-tree — the v8.0.2 double-run false-fail is gone (the v8.0.3 isolation fix holds). Plain extraction: pytest **520 passed** on the shipped code (import verified to resolve to the extraction, version 1.8.4), CLI **18/18**, docs-contract-paths **48/48**, dependency-gates **55/0**, healthcheck regressions **32/0/2** (02-a/03-a correctly NOT RUN — no baseline tree in a bare extraction), `npm ci` + Vitest **161/161** + build byte-identical (`index-X2bsjLBG.js`, SHA-256 `a77dd7d5…`). 92 of the 131 screenshots differ in bytes from v8.0.3 (91 from the Pass B Playwright run + 1 from the parent's Pass C re-run; same count, same names). Immutable backup at `~/workspace/backups/v8.0.4/` (mode 444, hash verified equal). NOTE: the manifest/log Pass C rows landed after the first packaging, so the archive was re-packaged from the same tree with only doc text changed and re-verified on a fresh extraction of the new bytes (verify-release 23/0/5). |
| NOT RUN (reviewer gates) | Docker Compose boot, in-image Keycloak healthcheck, Windows PowerShell 5.1 execution, Docker Desktop live-provider execution of the ps1 LIVE_PROVIDER_PYTEST gate, full `npm audit` (registry 403), GitHub Actions execution of the changed CI. No source-level mutation testing (standing instruction). IF-V8-42/43 stay OPEN. |

## Operation Trustline v8.0.5 — final two-item security hardening closure (2026-11-14)

> Every row below is filled from the measured runs in
> `docs/VERIFICATION_LOG.md` (v8.0.5 section) — never from memory, and
> never in advance. No v8.0.4 figure is copied forward as a v8.0.5
> result. Status words in this section are exactly PASS / FAIL /
> NOT RUN / NOT APPLICABLE. v8.0.5 is a NARROW implement-test-verify
> closure of the last two open LOW-severity hardening items from the
> v8 pentest — IF-V8-42 (app Dockerfiles run as root) and IF-V8-43 (CI
> actions pinned to mutable major tags) — on the delivered v8.0.4
> archive. It is NOT a pentest, NOT a rebuild, NOT a UI redesign, and
> it does NOT rewrite v8.0.4 history — the v8.0.4 section above stands
> as history. WS1 runs the app as non-root (UID 10001) with a
> one-shot, fail-closed evidence-volume preparation service for the
> existing root-owned `backend_data` volume; WS2 pins every GitHub
> Action to an upstream-verified full commit SHA with a repeatable
> checker. The release label is v8.0.5 and the target product version
> is **1.8.5**. The 1.8.5 contract bump itself (code sources, checker
> retarget, fixture literals, test-only assertions, runner labels, CI
> comment, guide archive names) is the coordinator's Pass B item.
> The parent's Pass C re-runs every gate on the final tree and
> packages the final ZIP (see the Pass C rows, added at packaging).

- **Release name:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V8.0.5_FINAL_20261114.zip`
- **Version:** 1.8.5 (Operation Trustline v8.0.5 — final two-item security hardening closure)
- **Date:** 2026-11-14 (ISO 8601)
- **Built from:** working tree at `~/workspace/identityforge-v8.0.5`
  (exact copy of the delivered v8.0.4 ZIP — 371 files, 42,409,551 bytes,
  SHA-256 `a81453e4f8eb256d58b6e5de8b3700fc66023809216cd618a3d877291f461ea3`,
  product 1.8.4; tree verified exact by the parent: 0 missing / 0 extra; no git
  repository was used for this build; no commit SHA exists)
- **Built by:** Linux sandbox, Python 3.12.3, Node 24.22.1, npm 10.9.4, PowerShell 7.4.6 on Linux. Windows PowerShell 5.1 was NOT RUN (5.1 is Windows-only). **Historical build environment (2026-11-14 sandbox):** no Docker binary or socket existed in that build sandbox — the shipped `docker compose up` path was NOT RUN there. This describes the historical build sandbox only, never the end user's runtime state.
- **Counts (current release):** backend pytest 520; test-all gates 19.

### Archive (file count from the tree; size/SHA-256 in the delivery message)

- **Filename:** `IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V8.0.5_FINAL_20261114.zip`
- **Size (bytes) and SHA-256:** not printed inside the archive — either value is a property of the ZIP file itself, so printing it here would change it. Check the delivery message for the SHA-256 of the shipped file, and verify with `ls -l` / `sha256sum <archive>` on Linux/macOS or `Get-FileHash <archive> -Algorithm SHA256` on Windows.
- **File count:** **376 files in the working tree by the packager's exclusion shape** (caches, venvs, `node_modules`, `dist`, `test-results`, `*.db`, `.hypothesis`, `egg-info` excluded) — 371 from v8.0.4 + 5 added in this round, none removed: `backend/docker/prepare-data-volume.py`, `scripts/test-prepare-data-volume.sh`, `scripts/check-docker-nonroot.py` (WS1); `scripts/test-action-pins.sh`, `docs/ACTION_SHA_PINS.md` (WS2). Verified by the coordinator's dry-run package of the final tree: **376 entries, testzip clean** (the first dry run read 399 — 23 extra `.hypothesis/` files from the WS3 run; the packager has no `.hypothesis` exclusion, so the directory was deleted from the tree before the re-run). Changed files vs the delivered v8.0.4 ZIP, measured by the coordinator from the final diff: **27 files differ + 5 added, none removed** — the 5 added above plus WS1 (12 files), WS2 (3 files), the 1.8.5 bump (11 files, some shared), and the Pass B docs (`README.md`, `docs/PENTEST_FINDINGS_AND_REMEDIATIONS.md`, `docs/RELEASE_MANIFEST.md`, `docs/VERIFICATION_LOG.md`, `docs/SECURITY_ASSESSMENT.md`, `docs/VALIDATION_AND_LIMITATIONS.md`, `docs/WINDOWS_SETUP.md`, `docs/ACTION_SHA_PINS.md` line-number correction). **95 of the 131 screenshots differ in bytes** (same count, same names — the Playwright run regenerated them). The parent confirms the final list from the final ZIP's namelist + diff at packaging.
- **Archive verified by:** parent's Pass C — three fresh extractions of the actual final ZIP bytes (plain, spaces, `data/` ancestor), `verify-release.sh` 23/0/5 in all three; double-run proof in the plain extraction; plain-extraction deep check; see the Pass C row below.

### Scope (WS1 — IF-V8-42 non-root Docker images)

| Area | Change |
| ---- | ------ |
| WS1 — app processes run as non-root UID 10001 (`backend/Dockerfile`, `frontend/Dockerfile`, `frontend/Dockerfile.e2e`) | Dedicated user `identityforge`, UID:GID **10001**, own group only, no other groups, no capabilities, in all three app images; each Dockerfile ends with numeric `USER 10001:10001` and contains no `USER root`. 10001 (not 1000) avoids collision with the host first-user UID and the node image's built-in `node` user (UID 1000). All build steps (apt, pip, npm ci, build, Playwright install) run as root at build time; ownership is handed to 10001 via chown *before* the USER switch; nothing runs as root after the drop. Listeners still bind 0.0.0.0:8000/5173 inside containers; all host-published ports stay 127.0.0.1-only; healthchecks/startup commands unchanged; no `privileged: true`, no docker.sock mounts, no host network, no host-user escalation, no chmod 777. Keycloak untouched: no `user:` override, image still `quay.io/keycloak/keycloak:26.8.2`, data-volume ownership, realm import, canonical issuer, service-DNS transport, `fullScopeAllowed`, and pinned version intact. |
| WS1 — existing-volume migration (`docker-compose.yml`, `backend/docker/prepare-data-volume.py`) | New one-shot service `backend-data-prep` — the ONLY root process in the lab. It reuses the backend image with explicit `user: "0:0"`, mounts ONLY `backend_data`, no ports, runs only `python3 /app/prepare-data-volume.py --data-dir /app/data --uid 10001 --gid 10001`, then exits; the backend starts only when it exits 0 (`depends_on: backend-data-prep: service_completed_successfully`, alongside keycloak `service_healthy`). The app image itself never runs as root, so the checklist's "no `USER root` in the Dockerfiles" holds by construction. The script (stdlib-only, 334 lines, never execs/subprocesses anything, never starts the app server) repairs ONLY the top level of /app/data (dir + direct entries: DB, `-journal`/`-wal`/`-shm` sidecars), never follows symlinks, never recurses, tightens modes to 0750 dirs / 0640 files, never loosens, deletes/replaces nothing. Scope guard: the data dir must resolve strictly inside `--base-dir` (default `/app`) and must not BE the base dir. Idempotent (second run is a no-op, `0 entries repaired`, rc 0). Post-repair checks: stat verification of owner/mode; a privilege-dropped writability probe (temporarily seteuid/setegid to 10001, creates+removes a temp file, opens the DB read-write without writing bytes, restores root — loudly skipped, not failed, when the kernel cannot switch ids); a read-only `PRAGMA integrity_check` when a DB exists and no `-wal`/`-shm` sidecar is present (explicitly skipped with a WAL sidecar, since a read-only open cannot replay a hot WAL). Any failure exits non-zero with a precise message and the backend never starts — fail-closed, no fallback to a root app runtime. |
| WS1 — pip-audit at build time (`backend/Dockerfile`, `scripts/test-all.ps1`) | pip-audit 2.10.1 is now installed AT BUILD TIME from `backend/requirements-audit.txt` into the system site-packages (readable/executable by UID 10001). `scripts/test-all.ps1` PYTHON_DEPENDENCY_AUDIT no longer installs at gate time (a non-root user cannot write system site-packages); it verifies the tool (`python -m pip_audit --version`) and runs the scan with UNCHANGED classification (rc=0 clean; rc=1 + "Found N known vulnerabilities" FAIL; rc=1 + "No module named pip_audit" TOOL_UNAVAILABLE/NOT RUN; other rc=1 CHECK_FAILED/NOT RUN). `test-all.sh` is unchanged — its audit runs host-side in the venv (`audit-gates.sh`), unaffected by Docker USER. No gate is quietly skipped; pytest, pip-audit, CLI, typecheck, Vitest, and the 19 gates are all preserved, as are the test mounts and the offline 516 / live 4 selection. |
| WS1 — frontend preview + E2E as non-root (`frontend/Dockerfile`, `frontend/Dockerfile.e2e`, `frontend/docker-e2e-entrypoint.sh`, `docker-compose.test.yml`) | Frontend preview reads built dist/ + node_modules as 10001 (npm ci + build as root, then `chown -R /app /home/identityforge` before the USER switch; npm has a writable HOME). E2E is non-root too (assessed separately, not left as root): socat binds 127.0.0.1:5173/8000/8080 (all >1024); Playwright launches Chromium with `--no-sandbox` by default (`chromiumSandbox` defaults to false), so non-root changes nothing about the browser sandbox; browsers install at build time to `PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright` (user-owned) instead of the installing user's home cache — a root install into `/root/.cache/ms-playwright` would be unreadable at runtime. The `--with-deps` apt step still runs as root at build time. The E2E entrypoint gained a fail-closed writability preflight for `/app/e2e/screenshots` + `/app/test-results` (`mkdir -p`, then `-w` test, `exit 1` with a precise message) before socat starts. Residual risk (NOT RUN): Docker Desktop bind-mount ownership for `./test-results/` — if the host dir arrives root-owned/read-only in the VM, the preflight fails closed with instructions instead of a cryptic Playwright error. The `live-gate` service (`docker-compose.test.yml`) also runs as `user: "10001:10001"` (stdlib-only driver, read-only mounts, writes nothing). |
| WS1 — static checker + stub tests (NEW `scripts/check-docker-nonroot.py`, NEW `scripts/test-prepare-data-volume.sh`) | `check-docker-nonroot.py` (29 rules, PyYAML, same ENVIRONMENT NOT READY exit-2 guard as `compose-config-check.py`): D1 numeric non-root USER in all Dockerfiles; D2 no `USER root`; D3 no chmod 777; D4 one UID:GID everywhere (10001); D5 no gosu/setpriv/su; D6 no RUN after USER; C1 loopback-only ports; C2 no privileged/host-network/docker.sock; C3 Keycloak untouched; C4 only `backend-data-prep` runs as root; C5 prep service mounts only `backend_data`, no ports, exact prep command; C6 `depends_on` wiring (prep completed + keycloak healthy; frontend←backend healthy); C7 host-mount allowlist + named volumes only; P1 prep script stdlib-only, no subprocess/exec/spawn, never starts the app; P2 prep defaults 10001:10001; S1 ps1 runs pip-audit without gate-time install; S2 backend Dockerfile installs pip-audit at build time; E1 E2E entrypoint preflight. `test-prepare-data-volume.sh` (42 checks, real SQLite DBs with rows, real chown to 10001 on /tmp tmpfs + `setpriv` app-user write proofs): fresh volume, existing root-owned DB + stale `-journal`, idempotent re-run, non-root caller vs root-owned volume, data-is-a-file, corrupt DB, symlinked dir/DB, scope violations, WAL sidecar, no-subprocess + canary, non-root no-op, no-recursion. |
| WS1 — verify-release coverage (`scripts/verify-release.sh`, `backend/.dockerignore`) | `verify-release.sh` REQUIRED_FILES now names the three new WS1 files (`scripts/check-docker-nonroot.py`, `scripts/test-prepare-data-volume.sh`, `backend/docker/prepare-data-volume.py`). `backend/.dockerignore` gained only a kept-list comment line naming `docker/prepare-data-volume.py` (the file was already kept: `*.py[cod]` never matched `.py`). |
| WS1 — `config.py` / `evidence/store.py` | READ-ONLY in this round and untouched — no defect was proven in either, so neither was edited. |

### Scope (WS2 — IF-V8-43 pinned GitHub Action SHAs)

| Area | Change |
| ---- | ------ |
| WS2 — all 11 `uses:` lines pinned (`.github/workflows/ci.yml`) | Every `uses:` line now pins a full 40-hex commit SHA with a `# vX.Y.Z` comment, one identical SHA per action, latest patch within the same major line already in use (no major-version jump): `actions/checkout` v4.4.0 → `11d5960a326750d5838078e36cf38b85af677262`; `actions/setup-python` v5.6.0 → `a26af69be951a213d495a4c3e4e4022e16d87065`; `actions/setup-node` v4.4.0 → `49933ea5288caeca8642d1e84afbd3f7d6820020`; `actions/upload-artifact` v4.6.2 → `ea165f8d65b6e75b540449e92b4886f43607fa02`. All 11 lines replaced (checkout ×4, setup-python ×3, setup-node ×3, upload-artifact ×1). `.github/workflows/` contains only `ci.yml` (no other workflow, no reusable workflow, no nested action, no `docker://`); `grep -rn "@v[0-9]" .github/` returns nothing; the one remaining `uses:`-mention is a header *comment* (ci.yml:183), not a reference. `permissions: contents: read`, triggers, jobs, Python 3.12 / Node 24, backend selection, WS3 step, scripts lane contents, PS matrix, keycloak-e2e lane, artifact publishing unchanged. |
| WS2 — upstream verification (`docs/ACTION_SHA_PINS.md`) | Each SHA resolved DIRECTLY from the official upstream repository `github.com/actions/<action>` through three independent GitHub API surfaces that all agree — (1) `GET /tags?per_page=100`, (2) `GET /git/ref/tags/<tag>`, (3) `GET /commits/<sha>` — plus (4) `GET /releases/tags/<tag>` (published, non-draft, non-prerelease). All four tags are lightweight (`ref type: commit` — the tag object IS the commit, so no annotated-tag dereference applies). Per-action evidence (commit date/message, release date) and cross-checks (checkout SHA matches the coordinator's independent `git ls-remote` probe of `refs/tags/v4`; major-tag entries agree) are in the doc; raw API responses are in `~/workspace/ws2-v805-evidence/`. `git ls-remote` over the git protocol was NOT usable as the primary method — it timed out at 240 s twice while the HTTPS API answered each call in <1 s. No SHA was invented, no random hex, no third-party list. |
| WS2 — repeatable checker (NEW `scripts/test-action-pins.sh`, CI scripts lane) | Offline bash+grep/sed, no network, no Docker; checks (1) full 40-hex lowercase SHA, (2) SHA exactly equals the embedded verified mapping, (3) `# vX.Y.Z` comment present and naming the mapped tag, (4) every mapped action actually used with its pin, (5) `docs/ACTION_SHA_PINS.md` records all SHA+tag pairs, (6) fail-closed on any unmapped action, (7) built-in negative control. Two bugs found and fixed by its own runs: a header comment mentioning "`uses:`" was first misread as a reference (filter tightened to real YAML keys), and inline `- uses:` fixture lines were first missed (extraction now accepts the optional `- ` prefix). Wired into the scripts lane as the step `Action SHA pins (IF-V8-43, v8.0.5)` right after the syntax gate; lane **25 → 26 steps**. Other lanes unchanged: backend 9, frontend 8, keycloak-e2e 8. YAML valid (`yaml.safe_load`, 4 jobs). |
| WS2 — doc line-number correction (coordinator, Pass B) | `docs/ACTION_SHA_PINS.md` listed stale `uses:` line numbers (checkout 76/132/188/403, setup-python 78/190/405, setup-node 134/201/409, upload-artifact 430) — recorded from an earlier ci.yml state. The actual lines are checkout 76/132/193/420, setup-python 78/195/422, setup-node 134/206/426, upload-artifact 447 (verified by `grep -n "uses:" .github/workflows/ci.yml` in Pass B). The SHAs/tags in the doc were correct; only the line numbers were wrong. Fixed in Pass B. |

### Scope (coordinator — Pass B)

| Area | Change |
| ---- | ------ |
| Pass B — 1.8.5 bump (coordinator) | Code sources: `backend/src/identityforge/__init__.py`, `backend/pyproject.toml`, `frontend/package.json` + `frontend/package-lock.json` via `npm install --package-lock-only` (lockfile root + `packages.""` both 1.8.5). `scripts/check-version-contract.py` retargeted to the Trustline v8.0.5 manifest section / 1.8.5 default (Python literal replaces; the section regex is `v8\.0\.5` with single backslashes in source — a plain `"v8.0.4"` literal replace missed it, the v8.0.1 trap, caught by the first 13/13 attempt reading 11/2: the two positives failed rc=2 "missing source" until the regex moved). `scripts/test-version-contract.sh` fixture literals moved FIRST (build_fixture 1.8.4 → 1.8.5 + the two informational 1.8.4 mentions + the fixture manifest `##` heading, now "final two-item security hardening closure (2026-11-14)"). The mutation code needed NO edit — derivation tracked 1.8.5, exactly as the v8.0.4 guard proof predicted. Test-only version assertions: `backend/tests/integration/test_v6_backend_api.py` (7 literals) and `frontend/src/pages/Settings.test.tsx` (3 mock versions + the `/1\.8\.5/` regex literal — single backslash, replaced literally, the v8.0.3 trap). Runner labels: `test-all.sh`, `test-all.ps1`, `verify-release.sh`. CI comment: `.github/workflows/ci.yml:307`. Guides: `docs/REVIEWER_GUIDE.md` 31/35 (v8.0.5 ZIP name), 38 (label), 492 (release version); `docs/WINDOWS_SETUP.md` 95/99 (ZIP name + label), 327, 333 (release version). Historical 1.8.4 mentions left untouched: the v8.0.4 manifest/log sections, and the `1.8.2` header comment in `test-version-contract.sh` documenting the defect. **13/13 re-run after the LAST bump: PASS, rc=0** (see the measured-results rows). |
| Pass B — hot-journal review probe (coordinator) | WS1's prep script fails closed on an unreadable DB via a read-only `integrity_check`. The coordinator probed the crash-recovery edge — a leftover `-journal` from a SIGKILLed mid-transaction writer — in three scenarios (1-row txn, 500-row txn with `PRAGMA cache_size=1`, exact mid-transaction on-disk snapshot of DB + journal): in all three the read-only open succeeded with pre-transaction rows and integrity ok, and prep returned rc=0; the app-side read-write open then read pre-transaction rows with integrity ok (the stale journal file remains on disk, ignored by SQLite and overwritten on the next write). Conclusion: the hypothesised "hot journal blocks boot" case does not reproduce for this workload (evidence writes are a few KB; a genuinely hot journal needs a multi-MB mid-transaction page spill), so NO script change was made — the fail-closed behaviour on a genuinely unreadable DB stands. Evidence: `~/workspace/passa-v805-evidence/hot-journal-probe-passb.txt`. |
| Pass B — docs (coordinator) | `docs/PENTEST_FINDINGS_AND_REMEDIATIONS.md` IF-V8-42 (PATCH PREPARED / RUNTIME VERIFICATION PENDING + full Windows Docker Desktop acceptance procedure, incl. the disposable-copy existing-volume migration with literal `-p` project commands) and IF-V8-43 (SHA PIN VERIFIED, HOSTED CI PENDING + GitHub test-branch/run steps); `docs/ACTION_SHA_PINS.md` line-number correction above; `SECURITY.md`, `docs/SECURITY_ASSESSMENT.md`, `docs/VALIDATION_AND_LIMITATIONS.md`, `docs/WINDOWS_SETUP.md`, `README.md` (v8.0.5 history entry) as needed. Historic findings/statuses preserved; changes and remaining environment proof marked transparently. |

### Measured results (WS1 / WS2, own runs on this tree, product 1.8.4 pre-bump)

| Check | Command / scope | Result |
|---|---|---|
| WS1 — non-root static checker | `python3 scripts/check-docker-nonroot.py` | **29/29 PASS, rc=0** on the changed tree. Negative control on a pristine v8.0.4 extraction: **14/29 PASS, rc=1** (fails exactly D1×3, D6×3, D4, E1, C4, C5, C6, P1, P2, S1, S2 — the checker detects the defect, not just passes). Evidence: `~/workspace/ws1-v805-evidence/`. |
| WS1 — volume-prep stub tests | `bash scripts/test-prepare-data-volume.sh` | **42/42 PASS.** Real SQLite DBs with rows, real chown to 10001 + `setpriv` app-user write proofs. Evidence: `~/workspace/ws1-v805-evidence/`. |
| WS1 — gate battery (pre-bump) | pytest full / offline / live / WS3 / CLI / ruff / typecheck / Vitest+build / docs / dep-gates / test-all --offline / regressions / PS matrix / provider-selection / ps1-selection / live gate + reset / doctor / headers / verify-release | **All green, WS1's own runs:** pytest **520 passed**; offline **516 passed / 4 deselected**; live-only **4 passed / 516 deselected**; WS3 **51 passed**; CLI **18/18**; ruff clean (68 files); typecheck rc=0; Vitest **161/161** (13 files); build byte-identical **`a77dd7d5…`** (`index-X2bsjLBG.js`); version fixtures **13/13** at 1.8.4; test-all --offline **11 PASS / 0 FAIL / 8 NOT RUN, rc=0** (19 gates; NPM_FULL_LOCKFILE_AUDIT NOT RUN — registry blocked, pre-existing; GHSA PASS); dependency-gates **55/0**; healthcheck regressions **34/0/0** (first run 32/2/0 was a /tmp ENOSPC harness failure — the gate-run venvs/node_modules bloated the tree to 425 MB and the suite's /tmp copies ran out of space; after removing the regenerable bloat the re-run is 34/0/0, not a product defect); PS matrix **26/0/0**; provider-selection **11/11 + 11/11**; ps1-selection **34/0/1 + 36/0/1** (1 skip = known pwsh TcpClient sandbox quirk); docs-contract-paths **48/48**; gate-strictness **9 passed, 0 failed**; live gate **all 101/101** + reset **69/69** (disposable marker backend `7d42f6bb-453b-43d3-a8a9-fe9d9298f5f5`, temp DB; dev DB untouched — SHA-256 `eb1bc9c5…` before AND after, counts 0/0/0); doctor READY; security headers live on preview (CSP + X-Frame-Options: DENY + nosniff); verify-release on a clean copy **23/0/5, rc=0** (first run failed FORBIDDEN_FILES on `backend/src/identityforge.egg-info`, the known regenerable editable-install artifact from test-all.sh; removed, re-ran 23/0/5). `bash -n` (test-all.sh, test-prepare-data-volume.sh), `sh -n` (E2E entrypoint), pwsh parse of test-all.ps1: **0 errors**; compose-config-check.py: PASS (YAML-only; `docker compose config` NOT RUN). Playwright E2E (72+1) + axe (25/25): NOT RUN — browser E2E is a Docker runtime proof per the task scope. Evidence: `~/workspace/ws1-v805-evidence/`. |
| WS2 — action-pin checker | `bash scripts/test-action-pins.sh` | **Positive 8 passed, 0 failed, rc=0. Negative: fixture with 6 defects — all 6 rejected, standalone proof rc=1.** `bash -n` clean. YAML valid (`yaml.safe_load`, 4 jobs; scripts lane 26 steps; `permissions: contents: read`). Evidence: `~/workspace/ws2-v805-evidence/`. |
| WS2 — gate battery (pre-bump) | version fixtures / source version-contract / docs-contract / docs-paths / pytest collect-only + offline | **All green, WS2's own runs:** version fixtures **13/13, rc=0**; source version-contract **PASS 1.8.4, rc=0**; docs-contract **PASS, rc=0** (`34 FailureReason values, 59 report-model fields, 135 source files harvested, 72 files scanned, 0 violation(s)`); docs-contract-paths **48/48, rc=0**; pytest `--collect-only` **520 collected, rc=0**; pytest offline `-m 'not live_keycloak'` **516 passed / 4 deselected, rc=0**. Caveats, stated exactly: (a) the first offline pytest attempt failed `sqlite3.OperationalError: database or disk is full` because **/tmp was 100% full** (512 MB tmpfs, 4.0K avail) — environmental, unrelated; re-ran with `TMPDIR=~/workspace/.verify/ws2-tmp` and it passed; (b) in the passing run's log the `516 passed, 4 deselected in …` summary line is absent (only progress dots + warnings summary); the 516 count is derived from progress dots (485 on progress lines + 31 on two loopback `ConnectionResetError` noise lines) and matches the 520-collected / 4-live split exactly, with 0 failures/errors and rc=0; (c) WS2 removed the `backend/data/identityforge.db` artifact its pytest runs created (packager-excluded; tree clean again); (d) `test-results/` in the tree is from a concurrent test-all run, not WS2's — left untouched. Evidence: `~/workspace/ws2-v805-evidence/`. |
| Coordinator — WS2 independent re-verification | `grep -n "uses:" .github/workflows/ci.yml`; `bash scripts/test-action-pins.sh`; GitHub API re-resolution of all four SHAs | **All 11 `uses:` lines pinned with `# vX.Y.Z`** (lines 76, 78, 132, 134, 193, 195, 206, 420, 422, 426, 447); new CI step at ci.yml:222; checker re-run **8 passed, 0 failed, rc=0**; all four SHAs re-resolved directly from the official GitHub API (checkout v4.4.0 → `11d5960a…`, setup-python v5.6.0 → `a26af69b…`, setup-node v4.4.0 → `49933ea5…`, upload-artifact v4.6.2 → `ea165f8d…`), each tag object type `commit`. /tmp was 5% used (23M / 512M) at that re-check. The `docs/ACTION_SHA_PINS.md` line numbers were wrong (see the Scope correction row) — SHAs/tags were correct. |
| Coordinator — WS1 checker re-runs | `bash scripts/test-prepare-data-volume.sh`; `python3 scripts/check-docker-nonroot.py`; `bash scripts/test-action-pins.sh` | **Prep stub tests 42/42 PASS; non-root checker 29/29 PASS, rc=0; action-pin checker 8/0, rc=0** — all re-run by the coordinator on the shared tree. Evidence: `~/workspace/passa-v805-evidence/prep-stub-tests-passb.txt`, `check-docker-nonroot-passb.txt`, `action-pins-passb.txt`. |
| Pass B — gate battery (coordinator) | pytest full / offline (KC absent) / live (KC present) / WS3 / CLI / ruff / typecheck / Vitest+build / docs / dep-gates / test-all --offline / regressions / PS matrix / provider-selection / ps1-selection / CI steps locally / live gate + reset / guard negatives / Playwright + validator + axe / ps1 Docker-absent | **All green, own runs, sequential:** pytest **520 passed, 3 warnings, rc=0** (89.31s, Keycloak up); offline selection **516 passed, 4 deselected, rc=0** (Keycloak ABSENT — discovery 000); live selection **4 passed, 516 deselected, rc=0** (Keycloak PRESENT, discovery 200); WS3 **51 passed, rc=0** (disposable venv, hypothesis 6.170.15, import verified to the v8.0.5 tree, 1.8.5); CLI **18/18**; ruff check clean + format clean (68 files); typecheck rc=0; Vitest **161/161** (13 files); build byte-identical **`a77dd7d5…`** (`index-X2bsjLBG.js`, 170.04 kB / 55.20 kB gzip); docs-contract **PASS** (129 source files harvested on the clean tree — WS2's 135 was measured on a working tree carrying regenerable egg-info artifacts the packager excludes; 0 violations either way); docs-contract-paths **48/48**; dep-gates **55/0**; gate-strictness **9/0**; test-all --offline **11 PASS / 0 FAIL / 8 NOT RUN, 19 gates, rc=0**; healthcheck regressions **34/0/0**; PS matrix **26/0/0**; provider-selection **11/11 offline + 11/11 --live**; ps1-selection **34/0/1 default + 36/0/1 --live** (1 skip = runtime teardown probe, pwsh TcpClient loopback quirk); CI steps locally from a clean copy: fixtures **13/13** + ps1 default **34/0/1** in two env variants (real HOME + `RUNNER_TEMP`; fake HOME + pwsh on PATH + `RUNNER_TEMP`) — no `$HOME/workspace` dependency; CI YAML valid (4 jobs, scripts lane 26 steps, `permissions: contents: read`, backend 9 / frontend 8 / e2e 8 steps); live gate **all 101/101, rc=0** (`"passed": true`); reset **69/69, rc=0** (disposable marker backend `4d49ae88-1b97-4fbe-9a0c-96157bdf6d10`, temp DB removed; dev counts byte-identical on restore: runs 144, events 248, live_login_events 52); guard negatives **no-flag rc=2, wrong-id rc=1, malformed rc=2**; Playwright **72 passed + 1 skipped, rc=0** (3.4m); validator **PASS** (total 73, passed 72, failed 0, skipped 1, target `host-lab`, epoch 1794647045); axe **25/25, 0 violations** (25 a11y specs all `expected`; 23 `axe <label>: 0 violations` lines); **131 PNGs** (95 differ in bytes from v8.0.4, same count/names); security headers live on preview + backend (CSP + X-Frame-Options: DENY + nosniff); doctor READY; ps1 Docker-absent **TRUE rc=1** (`ERROR: Docker is not available…`, no gates.json written by that run — the gates.json in-tree is the earlier test-all.sh --offline artifact, 19 gates, 11/0/8, untouched). Evidence: `~/workspace/passa-v805-evidence/`. |
| Pass B — verify-release on the packaged tree (coordinator) | `python3 scripts/package-zip.py` (dry run) + fresh extraction + `./scripts/verify-release.sh` | **Dry-run package: 376 entries, testzip clean, 0 forbidden entries, 24 `.sh` entries all mode 0770, all 5 new files present, 42,543,753 bytes.** (First dry run read 399 entries — the 23 extra were `.hypothesis/` files from the WS3 run; the packager has no `.hypothesis` exclusion, so the directory was deleted from the tree before the re-run, per the standing packaging rule.) Fresh extraction of the dry-run ZIP: `verify-release.sh` **23 PASS / 0 FAIL / 5 NOT RUN, rc=0** (summary from `test-results/verify-release.json`). The parent re-verifies from the final ZIP bytes in Pass C. Evidence: `~/workspace/passa-v805-evidence/package-dryrun2-passb.txt`, `verify-release-dryrun-passb.txt`. |
| Pass B — measurement traps / incidents, disclosed (coordinator) | Own runs | (1) The first clean-copy ps1-selection variant-A run failed 0/1 — my sequencing error: Keycloak was still UP from the live battery, and the default mode requires no provider on 8080 ("stop Keycloak first"). Keycloak was stopped by exact PID (java 68346) and both variants re-run green (34/0/1 each). Not a product defect. (2) A service restart interrupted the variant-B run mid-flight ("Terminated" in the log) and killed the whole live stack (backend + preview 000); the run was re-executed cleanly (34/0/1) and the stack restarted (Keycloak 200, backend 1.8.5, preview 200). (3) The ps-matrix run was first invoked with `bash` on the `.ps1` file (syntax error, rc=2) — rerun correctly under `pwsh -File`: 26/0/0. (4) The first 13/13 attempt after the fixture bump read 11/2 because the checker regex fix had not landed yet (see the bump row) — the regex was fixed and the run repeated 13/13. (5) All exit codes measured without pipes. |
| Pass B — live stack state left for Pass C (coordinator) | Keycloak 26.8.2 + dev backend (v8.0.5 tree, 1.8.5) + preview, all on 127.0.0.1 | **All three UP at Pass B finish**: Keycloak discovery 200 (java, restarted twice during the battery — stop by exact PID only); dev backend 1.8.5 on :8000 (PID 3589, restored after the reset proof; final counts runs 167, live_login_events 234, live_logins 234, events 281 — the growth from the reset-proof snapshot (runs 144, live_login_events 52, events 248) is the Playwright run's own real logins; sessions 0 / sessions_total_issued 0 — in-memory, reset on restart, documented semantics); preview 200 on :5173 (rebuilt in-tree, `a77dd7d5…`). `backend/data/identityforge.db` is packager-excluded and was left in place — do NOT delete it out from under the running backend (v8.0.3 Pass C incident); the parent's packaging cleanup handles it. The v8.0.4 dev DB (`~/workspace/identityforge-v8.0.4/backend/data/`) was never touched in this round. Tree left clean otherwise: `.hypothesis` deleted (packager has no exclusion for it); node_modules/dist/caches remain in-tree (regenerable, packager-excluded) — the parent removes them or lets the packager exclude them at packaging. |
| Pass C — independent SHA re-verification (parent) | Official GitHub API, re-resolved by the parent 2026-11-14 | **All four SHAs confirmed upstream, exactly as pinned:** checkout v4.4.0 → `11d5960a326750d5838078e36cf38b85af677262` (also matches the parent's independent `git ls-remote` probe of `refs/tags/v4`); setup-python v5.6.0 → `a26af69be951a213d495a4c3e4e4022e16d87065`; setup-node v4.4.0 → `49933ea5288caeca8642d1e84afbd3f7d6820020`; upload-artifact v4.6.2 → `ea165f8d65b6e75b540449e92b4886f43607fa02`. All tags lightweight (`type: commit`); all releases published, non-draft, non-prerelease. |
| Pass C — gate battery (parent) | Own runs, sequential, final 1.8.5 tree | **All green:** fixtures **13/13**; version-contract **PASS 1.8.5**; pytest **520** (offline 516/4 KC absent, live 4/516 KC present); WS3 **51**; CLI **18/18**; ruff clean (68 files); frontend typecheck rc=0; Vitest **161/161**; build byte-identical **`a77dd7d5…`**; docs-contract **PASS** (0 violations); docs-paths **48/48**; dep-gates **55/0**; gate-strictness **9/0**; test-all --offline **11/0/8** (19 gates); healthcheck regressions **34/0/0**; PS matrix **26/0/0**; provider-selection **11/11 + 11/11**; ps1-selection **34/0/1 + 36/0/1**; CI steps locally from a clean copy **13/13 + 34/0/1** (two env variants); CI YAML valid (4 jobs, scripts lane 26 steps, `permissions: contents: read`); action-pin checker **8/0** (6-defect negative rejected); prep stub tests **42/42**; non-root checker **29/29**; ps1 Docker-absent **TRUE rc=1** (no gates.json written). |
| Pass C — live gate + reset + Playwright (parent) | Own runs against the live stack | Live gate **all 101/101** (`"passed": true`); reset **69/69** (disposable marker backend `090282cb-00aa-4727-bf0d-fcf4a9a4efce`, temp DB removed; marker post-reset counts `runs: 0`; dev runs 311 / events 529 byte-identical across the swap); guard negatives **rc 2 / 1 / 2**; Playwright **72 passed + 1 skipped**, validator **PASS**, axe **25/25, 0 violations**; doctor **8/8** (network namespace); security headers live on preview + backend. |
| Pass C — FINAL ZIP clean-room (parent) | `package-zip.py` + three fresh extractions + `verify-release.sh` ×3 + double-run + deep check | **Final ZIP: 376 files, testzip clean, 0 forbidden entries, 131 PNGs, 24 `.sh` entries mode 0770, all 5 new files present.** (Byte count and SHA-256 live in the delivery message only.) verify-release **23/0/5, rc=0 in all three fresh extractions** (plain, spaces, `data/` ancestor); double-run proof in one clean extraction: run 1 and run 2 identical 23/0/5 rc=0, 28 gate lines identical, 0 FAIL, no `backend/data/` left in-tree. Plain-extraction deep check: pytest **520**, CLI **18/18**, docs-paths **48/48**, dep-gates **55/0**, regressions **32/0/2**, `npm ci` + Vitest **161/161** + build byte-identical. 95 of 131 screenshots differ in bytes from v8.0.4 (same count/names). Immutable backup at `~/workspace/backups/v8.0.5/` (mode 444, hash verified equal). |
| NOT RUN (reviewer gates) | Docker Compose boot, in-image Keycloak healthcheck, Windows PowerShell 5.1 execution, Docker Desktop live-provider execution of the ps1 LIVE_PROVIDER_PYTEST gate, full `npm audit` (registry 403), GitHub Actions execution of the pinned CI. No source-level mutation testing (standing instruction). IF-V8-42 PATCH PREPARED / RUNTIME VERIFICATION PENDING; IF-V8-43 SHA PIN VERIFIED, HOSTED CI PENDING. |
