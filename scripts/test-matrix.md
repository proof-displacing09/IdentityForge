# Cross-product test matrix — IdentityForge (Trustline v6)

Which combinations of *where the lab runs* and *what is tested* are
covered, and by what. A cell marked **RAN** was executed in this
workspace and its numbers are in the v4 handover (v5 re-runs are
marked v5 below; v6 re-runs are marked v6). A cell marked **NOT RUN**
needs Docker (or Windows PowerShell 5.1) and was not executed here;
the exact command the reviewer runs is given. Never read a NOT RUN
cell as a pass.

**v6 (WS2):** the runners now have **18 gates** (12 offline + 6
full): `DOCS_CONTRACT_PATHS` (IF-V5-01 — the docs-contract check
must behave identically under a `data/` ancestor or a path with
spaces; `scripts/test-docs-contract-paths.sh`, 15 checks) and
`VERSION_CONTRACT` (IF-V5-05 — every authoritative version value
must equal the release version 1.7.0;
`scripts/check-version-contract.py`) join the 16 v5 gates. In
`test-all.ps1` both new gates run in a throwaway `python:3.12-slim`
container with the repo mounted (the GHSA pattern) — no host
Python needed. **v7.2 note (2026-11-12):** the figures above are the
v6 state. Current values: `scripts/test-docs-contract-paths.sh` has
**27 checks** (v7.2 added cases for stale archive names in
quickstart commands) and the release version is **1.7.2**. **v7.3
note (2026-11-12):** the release version is **1.7.3** (single-source
bump: backend `__version__` / pyproject, FastAPI + `/api/v1/health`
derive from it, frontend `package.json` + lockfile via
`npm install --package-lock-only`, version-contract fixtures at
1.7.3). `scripts/test-docs-contract-paths.sh` has **30 checks**
(v7.3 adds a case for the newly-stale v7.2 FINAL archive name in a
quickstart command, plus an older-stale v7.1 FINAL case). `scripts/test-compose-healthcheck-regressions.sh`
has **32 checks** (v7.3 adds the IF-V7.2-02 PyYAML preflight
negative/positive, the venv-python + external-Node preservation
case, and the no-Docker default-mode case; the 04-e case now
expects the IF-V7.2-01 exit contract — explicit `--with-docker`
with no Docker exits nonzero — and WS1's IF-V7.2-03 split 04-c
into 04-c-A/04-c-B, for a 32/0/0 green run once both workstreams
landed). **v7.3.1 note (2026-11-12):** the release label is
**v7.3.1** but the product version is **1.7.4** — a patch on the
1.7.3 line (npm semver is 3-part, so 1.7.3.1 is invalid); the
single-source bump covers the backend version source, pyproject,
frontend package files (lockfile via
`npm install --package-lock-only`), the version-contract checker
(now reads the Trustline v7.3.1 manifest section, expects 1.7.4)
and its fixtures, the test-only version assertions, and the
version labels in the runners. `scripts/test-docs-contract-paths.sh`
has **33 checks** (v7.3.1 adds a case for the newly-stale v7.3 FINAL
archive name in a quickstart command, plus an oldest-stale v7.1
FINAL case — staleness is now proven across three releases).
`scripts/test-compose-healthcheck-regressions.sh` still has **34
checks** (the v7.3.1 change reworks case 04-a in place — the
port-occupied branch is now tested on controlled loopback test
ports via the test-ports override instead of the reviewer's real
8080, so it is deterministic whether the live stack is up or down;
no case was added or removed). New native PowerShell matrix
`scripts/test-compose-healthcheck-ps-matrix.ps1` (WS1, 26 cases)
covers the healthcheck wrapper with a stub docker only. New native Windows wrapper
`scripts/test-compose-healthcheck.ps1` (same checks as the `.sh`
form, no host Bash/Python — tested 13/13 + a path-with-spaces run
under PowerShell 7.4.6 on Linux with a stub `docker`). Gate statuses in `test-results/gates.json` are
exactly PASS / FAIL / NOT RUN / NOT APPLICABLE (IF-V5-10): NOT RUN
is never a pass, never "skipped", and never interchangeable with
NOT APPLICABLE or FAIL.

**v8 note (2026-11-12, WS3):** the release label is **v8** and the
product version is **1.8.0** (full adversarial penetration test +
remediation, not a patch on the 1.7.x line). The single-source bump
covers the backend version source, pyproject, frontend package files
(lockfile via `npm install --package-lock-only`), the
version-contract checker (now reads the Trustline v8 manifest
section, expects 1.8.0) and its fixtures (**13/13** — the five
one-source negative patterns still held the sed-escaped literal
`1\.7\.4` after a plain-text bump, the exact trap the v7.2/v7.3
notes warn about; fixed with Python literal replaces, second clean
run 13/13), the test-only version assertions, and the version
labels in the runners. `scripts/test-docs-contract-paths.sh` has
**42 checks** (v8 adds check-6 cases (l)/(m)/(n): stale
release-label prose in a quickstart region FAILS, stale "release
version 1.7.3" prose FAILS, current v8 prose PASSES — the new
`scripts/validate-docs-contract.py` check 6, IF-V8-80). New depth
suites under `scripts/pentest/ws3/`: Hypothesis property tests
(**24 passed** post-fix, incl. the IF-V8-01/03 regression tests), differential secure-vs-flawed tests (**12
passed**), fault injection + concurrency + malformed-input corpus
(**15 passed**), stateful live sequence (**55 checks passed**,
real Keycloak), extra live probes (session fixation, cookie
flags, callback error paths, open-redirect params, per-browser
login rate cap 429 on a disposable app). The live backend's global
transaction store (cap 20, TTL 600 s) saturates under concurrent
multi-workstream Playwright load and answers login starts with a
designed 503 capacity response until entries expire — see
`docs/FINAL_ADVERSARIAL_PENETRATION_TEST_REPORT.md` §H and the
WS3 evidence log `extra-live-probes-run2.log`; it is capacity
behaviour, not a defect, but it is a real reviewer-visible
availability note for parallel runs. **Never run two login-heavy
suites concurrently against the shared live backend** — that is
what produced the concurrent-run 431/51 scare (resolved: full
backend suite **482 passed, 0 failed** sequentially, twice,
independently; the OIDC suite's 2 failures were the same artifact;
the raw-probe CL+TE 200 is standards-compliant, final probe run
**21/21**; WS1 live gate **101/101**). WS1's three new
adversarial test files failed `ruff format --check` and blocked
OFFLINE_UNIT (IF-V8-83); fixed mechanically with `ruff format`
(whitespace only, 85/85 post-format).

**v8.0.3 note (2026-11-13, WS2):** the release label is **v8.0.3**
and the target product version is **1.8.3** (narrow Windows-runner
correction + release clarity closure of the delivered v8.0.2
archive — NOT a second pentest, NOT a redesign). The one known
v8.0.2 divergence is CLOSED: `test-all.ps1` now defines the same
**19 gates** (12 offline + 7 full) as `test-all.sh` — its
OFFLINE_UNIT runs the offline selection (`-m "not live_keycloak"`,
the same defect class Fix B repaired on the sh/CI/verify-release
path), the full profile adds gate LIVE_PROVIDER_PYTEST (the four
provider-dependent pytest tests, marked live_keycloak, against the
cold-started disposable Keycloak — in the ps1 the four tests run
inside the backend-test container with a loopback forwarder to the
disposable Keycloak; the offline/live split is 516/4 by collect-only
(WS2 probe, this round)), and the stale VERSION_CONTRACT
label ("1.7.3") is fixed to the release version 1.8.3. The 18-gate
figures above are v6 history; the current state is 19 gates in both
runners. Backend pytest is still **520 tests (516 offline + 4
provider-dependent)**; the 51 WS3 depth tests stay separate and are
never added to the 520. `scripts/test-docs-contract-paths.sh` still
has **48 checks**. `scripts/verify-release.sh` BACKEND_PYTEST now
isolates its database side effect: the suite creates
`backend/data/identityforge.db` even on `--collect-only` (the CLI
store via `Settings()` defaults), which made a second verifier run
in the same extraction false-fail FORBIDDEN_FILES (parent Pass C,
v8.0.2: 22/1/5) — the gate now runs with `IDENTITYFORGE_DB_PATH`
pointed at a disposable temp directory that is removed afterwards
(the script never deletes anything in the tree), proven by a
double-run on a fresh extraction copy; a fresh extraction per run is
still the recommended audit shape. Version-bump dependency: the
1.8.3 contract bump (code sources, `scripts/check-version-contract.py`
retarget, fixtures, test-only version assertions, runner version
labels) is applied by the coordinator in Pass B, following the
v8.0.2 precedent — at WS2 finish the in-tree code still reports
1.8.3, so `VERSION_CONTRACT` verifies 1.8.3 (bump landed in v8.0.3).

Conventions: **host-run** = Keycloak 26.8.2 as a host process, backend
on 8000, frontend preview on 5173 (the build-sandbox stack).
**Compose bridge** = `docker compose up --build -d` (default project,
services keycloak/backend/frontend on the `identityforge-net`
network, ports 8080/8000/5173 published on the host).
**Test profile** = `docker-compose.test.yml` on top of the Compose
stack (`--profile test`): `live-gate` (python:3.12-slim, host map
`{"8080": "keycloak", "8000": "backend"}`) and `frontend-e2e`
(Playwright, reaches the frontend through socat loopback
forwarders — a container browser cannot reach the host's
127.0.0.1:8080).

Ports are FIXED (8080/8000/5173). The canonical issuer is
`http://127.0.0.1:8080/realms/identityforge-lab`. Keycloak burns the
auth code on a failed PKCE exchange (second exchange → 400
invalid_grant "Code not valid"), and skips the login page when the
browser already holds a session (SSO skip) — tests must account for
both.

## 1. Live-gate sub-gates (`scripts/live-gate.py`)

| Sub-gate | Host-run | Compose bridge (via `live-gate` container) | Command |
| --- | --- | --- | --- |
| `all` — 99 checks: login, binding, negatives | RAN 99/99 (no map) and 99/99 (localhost map) | NOT RUN | host: `python3 scripts/live-gate.py all`; with map: `IDENTITYFORGE_LIVE_GATE_HOST_MAP='{"8080": "localhost", "8000": "localhost"}' python3 scripts/live-gate.py all`; container: `docker compose -f docker-compose.yml -f docker-compose.test.yml --profile test run --rm live-gate python3 /scripts/live-gate.py all` |
| `login` — student + officer login, role probes, logout + stale 401 | RAN (inside `all`) | NOT RUN | `python3 scripts/live-gate.py login` / container as above with `login` |
| `binding` — cross-browser binding + replay | RAN (inside `all`) | NOT RUN | `python3 scripts/live-gate.py binding` / container as above with `binding` |
| `negatives` — K2 wrong PKCE, K3 unregistered redirect, issuer pinning | RAN (inside `all`) | NOT RUN | `python3 scripts/live-gate.py negatives` / container as above with `negatives` |
| `reset` — 64 checks: synthetic run, unauthenticated/student reset cannot delete it, officer + CSRF + `{"confirm": "RESET_LAB"}` can, stale officer AND student cookies 401 afterwards, fresh login still works | RAN 64/64 | NOT RUN | host: `python3 scripts/live-gate.py reset`; container: same container command with `reset`. **Destructive by design — never part of `live-gate.py all`, and never run against the persistent lab; only inside the disposable cold-start namespace (`test-all.ps1 -Full` / `test-all.sh --full`, gate REAL_LAB_RESET) and only when the cold-start boot succeeded — with no disposable stack there is nothing safe to reset.** |

Host-map adapter unit tests (`scripts/test-live-gate-hostmap.py`):
RAN 21/21 — fake server captures the Host header; canonical request
→ `Host: 127.0.0.1:<port>`; mapped request → TCP to the mapped name
with the Host header still canonical; caller-supplied Host
respected; 11 invalid mappings rejected before any connection; bad
env map exits 2 with 0 requests attempted. The adapter (P0-02) only
changes the TCP route; the Host header stays canonical
`127.0.0.1:<port>` on mapped connections, and the backend's
allowed-hosts check is unchanged (still strict).

## 2. Full runners

| Runner | Host-run | Compose bridge | Notes |
| --- | --- | --- | --- |
| `bash scripts/test-all.sh --offline` | RAN (gates.json summary in the handover) | n/a — offline gates do not boot Docker | Backend pytest + CLI + frontend Vitest/build + dependency gates. GHSA_DIRECT_FALLBACK is NOT APPLICABLE when the full npm audit executed (P1-05); with the registry blocked in this sandbox the offline run exercises the blocked-audit path (NPM_FULL NOT RUN, GHSA may run honestly). |
| `bash scripts/test-all.sh --full --strict` | NOT RUN (needs Docker for the cold-start stack; the host stack is already on 8080/8000/5173) | NOT RUN with real Docker — but the full flow WAS executed in a network namespace with a stub `docker` (ports free in the namespace, `up` fails): preflight passes, teardown `down -v` scoped to the disposable project only, REAL_LAB_RESET NOT RUN with the no-disposable-stack reason, CLEAN_COMPOSE_BUILD_BOOT FAILs honestly. See `scripts/test-port-preflight.sh` (10/10). | `bash scripts/test-all.sh --full --strict` — cold-start in disposable project `identityforge-coldstart-<timestamp>`, live gates on the host against published ports, REAL_LAB_RESET in the disposable namespace (only when the boot succeeded), `down -v` scoped to that project only. **Stop-first (P0-03): if 8080/8000/5173 are busy, the runner refuses and prints the exact stop → test → restart sequence; it never kills anything.** |
| `.\scripts\test-all.ps1 -Offline` | NOT RUN on Windows PowerShell 5.1; PowerShell 7.4.6 paths exercised on Linux with a stub `docker` (see §4) | n/a | `.\scripts\test-all.ps1 -Offline` |
| `.\scripts\test-all.ps1 -Full -Strict` | NOT RUN on Windows | NOT RUN with real Docker — but the full flow WAS executed in a network namespace under pwsh 7.4.6 with a stub `docker` and a stub `doctor.ps1` (READY immediately): all 16 gates run (v5; v6 re-run with 18 gates: 20 passed, 0 failed, 1 skipped, 2026-11-11), REAL_LAB_RESET PASSes when the boot succeeded, GHSA NOT APPLICABLE, PLAYWRIGHT_E2E + RESPONSIVE_QA PASS via the real JSON validator against synthetic reports bound to the disposable project, teardown `down -v` scoped to the disposable project only, exit 0. See `scripts/test-ps1-preflight.sh` (v5: 20 passed, 0 failed, 1 skipped). | `.\scripts\test-all.ps1 -Full -Strict` — cold-start in the disposable project, live gates via the `live-gate` container on the Compose network (host map env), REAL_LAB_RESET in the disposable namespace (only when the boot succeeded), Playwright via the `frontend-e2e` container. Stop-first preflight as above. |

## 3. Browser E2E (Playwright) + accessibility

| Suite | Host-run | Compose bridge (socat forwarders) | Command |
| --- | --- | --- | --- |
| Playwright (4 spec files, 66 tests in v5) | RAN (v5): E2E specs 41 passed + 1 honest skip (portal 8/8 incl. the new discovery-issuer test, edge 8 passed + 1 skip, a11y 25/25) against the live v5 stack; screenshots spec 24/24 (WS3 live run). The E2E run emits `test-results/playwright-report.json`, validated PASS by `scripts/validate-playwright-report.py` (target `host-lab-verify`) — the gate no longer trusts the exit code alone (IF-V4-10). Full-suite single-run count: 65 passed + 1 skipped | NOT RUN | `cd frontend && npx playwright test e2e/portal.spec.ts e2e/edge.spec.ts e2e/a11y.spec.ts` / `npx playwright test` |
| axe zero-tolerance (25 views) + screenshots at 6 widths | RAN (v5, WS3): axe 25/25, 0 violations; screenshots 24/24, 100 PNGs | NOT RUN | `cd frontend && npx playwright test e2e/a11y.spec.ts e2e/screenshots.spec.ts` |
| Playwright workers | config: `workers: 1` default, `PLAYWRIGHT_WORKERS` override (P1-09) | same config | `PLAYWRIGHT_WORKERS=4 npx playwright test` on a stronger machine |
| Playwright JSON validator (`scripts/validate-playwright-report.py`) | RAN (v5, WS2): self-test 12/12 — pass, unexpected skip, zero real-login assertions, wrong-target evidence, missing/stale/malformed report, failed discovery test, screenshots pass/skip, profile mismatch, plus the captured live report validating PASS | NOT RUN (real Docker E2E path) — the ps1 container path is proven by the preflight stub + real validator | `python3 scripts/test-validate-playwright-report.py` |

## 4. PowerShell 5.1 vs 7 (P1-07)

| Check | PowerShell 5.1 (Windows) | PowerShell 7.4.6 |
| --- | --- | --- |
| `test-all.ps1 -Help` | NOT RUN | RAN on Linux (pwsh 7.4.6) — prints the stop-first workflow text, exits 0 |
| Invalid parameters (incl. unknown args → exit 2, not silently ignored) | NOT RUN | RAN on Linux (pwsh 7.4.6) — `-Offline -Full` exits 2; `-BogusParam` exits 2 with "unknown argument" (P1-07 fix: PowerShell otherwise swallows unknown args into `$args`) |
| Missing Docker daemon | NOT RUN | RAN on Linux (pwsh 7.4.6, stub `docker` failing `docker info`) |
| Occupied ports, occupant = this project's lab | NOT RUN | RAN on Linux (pwsh 7.4.6, real busy ports + stub `docker compose ps` showing running containers) — prints the stop-first sequence, runs no `down` |
| Occupied ports, occupant NOT this project | NOT RUN | RAN on Linux (pwsh 7.4.6, real busy ports + stub `docker compose ps` empty) — refuses with instructions, kills nothing, runs no `down` |
| Blocked npm audit endpoint | NOT RUN | RAN on Linux (pwsh 7.4.6, stub audit log) — GHSA NOT APPLICABLE when the full audit executed |
| Failing test | NOT RUN | RAN on Linux (pwsh 7.4.6, stub `docker` failing the build) — gate FAIL, exit != 0 |
| Path with spaces | NOT RUN on Windows | RAN on Linux (pwsh 7.4.6, repo copied to a path with spaces) — -Help and the occupied-ports -Full case both behave identically |
| Full -Full -Strict flow (stub docker + stub doctor) | NOT RUN | RAN on Linux (pwsh 7.4.6, network namespace, stub `docker`, stub `doctor.ps1` READY) — all 16 gates run (v5; v6 re-run with 18 gates: 20 passed, 0 failed, 1 skipped, 2026-11-11), REAL_LAB_RESET PASS, GHSA NOT APPLICABLE, PLAYWRIGHT_E2E + RESPONSIVE_QA PASS (JSON report validated against the disposable project), teardown `down -v` scoped to the disposable project only, exit 0 |
| Relative log path resolves to the session location (IF-V4-08 regression) | NOT RUN | RAN on Linux (pwsh 7.4.6) — pwsh launched from a different directory than the tree still writes the `Invoke-Native` log into the tree's `test-results/` (case 18 of `scripts/test-ps1-native.sh`); negative control against the old `GetFullPath` code fails it |

Native-call audit (IF-V4-08, v5 — supersedes the v4 P1-07 note):
every native call in `scripts/test-all.ps1` (and the `setup` /
`start` / `stop` / `reset` wrappers) goes through
`scripts/native-invoke.ps1` — Start-Process with stdout/stderr
captured to SEPARATE files (never merged with `2>&1`), the exit
code read from the process object, `-NoStderrMerge` for parseable
stdout (npm audit JSON), and `-TimeoutSeconds` returning 124. No
bare `2>&1` merge remains in the runners. `scripts/test-ps1-native.sh`
proves it under PowerShell 7.4.6 on Linux (23 PowerShell cases + 3
bash checks); `scripts/test-ps1-preflight.sh` proves the whole
runner end to end (20 passed, 0 failed, 1 skipped). Windows
PowerShell 5.1 execution remains NOT RUN (5.1 is Windows-only); the
exact reviewer commands are in `docs/REVIEWER_GUIDE.md` §7.

## 5. Dependency gates (P1-05 truth table)

| Case | NPM_FULL_LOCKFILE_AUDIT | GHSA_DIRECT_FALLBACK | Strict |
| --- | --- | --- | --- |
| npm audit executed, clean | PASS | NOT APPLICABLE (did not run) | pass |
| npm audit executed, findings (incl. transitive-only) | FAIL | NOT APPLICABLE (never PASS beside a failed audit) | fail |
| npm registry 403 / endpoint blocked | NOT RUN | may run honestly (PASS/FAIL/NOT RUN by its own evidence) | fail |
| GHSA rate limit / unreachable | (own result) | NOT RUN, never PASS | fail |
| npm audit unknown error (exit 2, no blocked text) | NOT RUN with `rc=2` in the detail | may run honestly; cannot mask the missing full audit | fail |
| npm audit malformed JSON / empty output (v5, IF-V4-09) | NOT RUN CHECK_FAILED | may run honestly; cannot mask the missing full audit | fail |
| npm audit JSON with contradictory rc (vulns found but rc 0) (v5, IF-V4-09) | NOT RUN CHECK_FAILED | may run honestly; cannot mask the missing full audit | fail |
| pip-audit install fails / scan garbage / rc 2 (v5, IF-V4-09) | NOT RUN TOOL_UNAVAILABLE / CHECK_FAILED | n/a (Python lane) | fail |

Covered by `scripts/test-dependency-gates.sh` (55 checks, RAN
55/55, v5 — was 33/33) and `scripts/test-gate-strictness.sh` (9 cases,
RAN 9/9, v5 — was 7/7),
both with fake npm/pip and a local GHSA stub server. The same semantics hold in both runners
(`scripts/audit-gates.sh`, `scripts/test-all.ps1`,
`scripts/verify-release.sh`): the `gates.json` summary carries all
four keys (`PASS`, `FAIL`, `NOT RUN`, `NOT APPLICABLE`). The npm
audit is classified from its JSON report by
`scripts/npm-audit-classify.py` (PowerShell mirror
`Get-NpmAuditClassification` in `test-all.ps1`); tool install/version
is a separate measured step before each scan, recorded in
`test-results/audit-tools.json`.

## 6. Doctor / readiness + Keycloak healthcheck (P1-08)

| Check | Result |
| --- | --- |
| `scripts/doctor.sh` / `scripts/doctor.ps1` verify discovery (canonical issuer exactly) AND backend reachability via `/api/v1/lab/status` (`idp.reachable=true` AND `idp.issuer_matches=true`) | RAN 8/8 in a network namespace (ports free); on the host with the lab running the suite SKIPped honestly (exit 0) — the stub cannot own the lab ports, so the negative cases would fail falsely (see the guard in `scripts/test-doctor.sh`); doctor.ps1 verified by reading |
| Keycloak healthcheck bash syntax (`docker-compose.yml` `keycloak.healthcheck.test`) | RAN — `bash -n` on the YAML-decoded command: SYNTAX OK; requires HTTP 200 status line AND `"issuer"` in the discovery body |
| Healthcheck probe logic against a live Keycloak | RAN — the decoded `/dev/tcp` probe exits 0 against the host Keycloak 26.8.2; discovery issuer is the canonical one |
| Healthcheck Compose interpolation (IF-V4-01, v5) | RAN — `scripts/compose-config-check.py` simulates Compose interpolation and asserts the resolved command keeps the literal `$resp` (2×) with HTTP-200 + issuer greps on the exact realm discovery URL; negative control (revert `$$resp` → `$resp`) FAILS as designed. `scripts/test-compose-healthcheck.sh` static part: 1 passed, 0 failed, 3 NOT RUN (Docker half needs a daemon). The runners also inspect the RESOLVED config (`test-all.sh` Docker-present branch, `test-all.ps1` COMPOSE_CONFIG gate) |
| Healthcheck in-image (`docker compose exec keycloak bash -c '...'`, `docker compose ps`, healthy vs unhealthy loop / 360-s timer exhaustion, clean vs reused volume, IdP outage) | NOT RUN — exact reviewer probe is in the doc-changes list for `docs/REVIEWER_GUIDE.md` |

## 7. What is NOT covered by any cell above (Docker-gated)

- Real `docker compose up --build -d` boot of the shipped Compose
  stack (no Docker in this sandbox).
- In-container `live-gate` run on the Compose bridge (the P0-02
  fix's intended environment) — host-map adapter proven host-side
  (99/99 with the localhost map) and by unit tests (21/21); the
  container run itself is NOT RUN.
- Windows PowerShell 5.1 execution of any script.
- Full `npm audit` against the real registry (proxy 403 in this
  sandbox) — the GHSA direct-only fallback covers direct deps only
  and never satisfies the full audit.
- Source-level mutation testing — NOT RUN by design (v1-era
  incident); sensitivity is proven via the designed `omit`
  mechanism (offline test-only).

## 8. Build contexts (IF-V4-02, v5)

| Check | Result |
| --- | --- |
| `frontend/.dockerignore` + `backend/.dockerignore` semantics | RAN — `scripts/test-dockerignore.py` 82/82: a fake host `frontend/node_modules` tree (incl. a fake native binary) is EXCLUDED from the build context; the 99 shipped screenshots, `dist/`, caches, `test-results/`, `.env*` are excluded; `package.json`, lockfile, `src/`, e2e SPEC FILES, Dockerfiles, entrypoint, `index.html`, configs are kept. Real frontend context: 51 files kept (0.4 MiB), 6812 files excluded (158.3 MiB) |
| Actual `docker build` context-transfer size | NOT RUN — no Docker in this sandbox. Reviewer: `docker build -f frontend/Dockerfile -t identityforge-frontend-check frontend/` and check the "transferring context" line (must be a few MB, not ~160 MB) |
| E2E screenshot output path | RAN by construction — `docker-compose.test.yml` mounts `./test-results/e2e-screenshots:/app/e2e/screenshots`, and the Playwright JSON report mounts `./test-results:/app/test-results`; no run depends on the pre-shipped PNGs |
