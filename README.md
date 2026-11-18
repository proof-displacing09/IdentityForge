# IdentityForge — OAuth/OIDC Authentication Attack Laboratory

> **A localhost-only lab for learning how web logins are supposed to work —
> and proving it, one broken login at a time.**
>
> All data in this lab is synthetic: **SYNTHETIC LAB DATA — NOT REAL
> IDENTITY INFORMATION.** No real users, no real accounts, no real identity
> providers. Everything runs on your own machine, on loopback only.

## What is IdentityForge?

When you click "Sign in with Google" (or any "Sign in with …" button), a
lot has to go right behind the scenes: the website must check that the
reply really came from the login it started, that the code it received can
only be used once, that the identity token really came from the expected
provider, was meant for this website, hasn't expired, and is genuinely
signed. If any one of those checks is missing or wrong, an attacker can
sometimes sign in as someone else.

IdentityForge is a small, working laboratory for exactly those checks. It
contains:

1. **A fictional campus club portal** ("Cedarbridge Campus Club") with a
   real login: your browser is redirected to a local Keycloak identity
   provider, you sign in as a synthetic test user, and the backend verifies
   everything before creating a session.
2. **A research console** that runs controlled experiments — scenarios
   I1–I18 — against the login. Each experiment changes exactly one thing
   (a wrong state value, a wrong PKCE verifier, a token for the wrong app)
   and records what the secure version did versus what a deliberately
   weakened version did.
3. **Honest evidence:** every run produces a redacted report with a run
   ID, timestamps, reason codes, and a hash — and every report says
   clearly whether it came from the real Keycloak or from an offline
   deterministic fixture.

It is a research-and-validation lab, **not** an attack tool. It only talks
to its own localhost services, and its intentionally weak variants exist
only inside offline tests — never as a mode of the running application.

## Authentication vs authorization (one short example)

- **Authentication** — "Who are you?" `student_01` signs in and Keycloak
  confirms it. The backend checks the signed ID token and creates a
  session for that subject.
- **Authorization** — "Are you allowed to do this?" `student_01` is a
  *member*, so they can open the member page. They are **not** an officer,
  so the officer page says no — even though their login was perfectly
  valid.

A valid login is never, by itself, permission. The lab enforces the two
separately, on the server, on every request.

## The real login sequence

```
You click "Sign in"
  → backend creates a one-time transaction (random state, nonce, PKCE verifier)
  → browser is redirected to Keycloak (http://127.0.0.1:8080)
  → you sign in as a synthetic user
  → Keycloak redirects back to http://127.0.0.1:8000/auth/callback with a one-time code
  → backend checks the state, exchanges the code + PKCE verifier for tokens (server-to-server)
  → backend validates the ID token: signature (Keycloak's keys), issuer, audience, expiry, nonce
  → backend creates a server-side session and sets an HttpOnly cookie
  → you see the portal dashboard
```

Tokens never touch the browser. Nothing is stored in `localStorage`.
The full flow, state machine, and reason codes are in
[`docs/AUTH_FLOW.md`](docs/AUTH_FLOW.md).

## Architecture

```
┌─────────────┐   redirect / callback    ┌──────────────────┐
│   Browser   │ ◄──────────────────────► │  Backend (BFF)   │
│  (you)      │   session cookie only    │  127.0.0.1:8000  │
└──────┬──────┘                          │  code exchange,  │
       │                                 │  token validation│
       │ OIDC login                      │  sessions, authz │
       ▼                                 └──────┬───────────┘
┌──────────────────┐   server-to-server  ┌──────▼───────────┐
│  Keycloak (IdP)  │ ◄──────────────────►│  Research console│
│  127.0.0.1:8080  │   tokens, JWKS      │  127.0.0.1:5173  │
│  realm:          │                     │  scenarios,      │
│  identityforge-  │                     │  reports, learn  │
│  lab             │                     └──────────────────┘
└──────────────────┘
```

- **Backend:** Python 3.12, FastAPI, Pydantic, PyJWT + JWKS validation,
  Authlib, httpx. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
- **Identity provider:** Keycloak 26.8.2 (pinned image
  `quay.io/keycloak/keycloak:26.8.2`, released 2026-11-05), realm + client + synthetic users
  imported from version control — no manual Keycloak setup.
- **Frontend:** React + TypeScript + Vite, Vitest, Playwright.
- **Scenario engine:** deterministic offline fixtures (keys generated per
  run, synthetic issuers) plus isolated flawed validators. See
  [`docs/SCENARIO_METHOD.md`](docs/SCENARIO_METHOD.md).
- **Trust boundary:** the backend is the only component that makes
  security decisions. The browser and the frontend never do.
  See [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md).

## Real Keycloak vs offline fixture — read this first

Every result in the lab carries a **mode label**, and the label matters:

| Mode | What it means |
|---|---|
| `REAL KEYCLOAK` / `LIVE_KEYCLOAK` | Measured against the running local Keycloak over real HTTP. This is the real login. The Atlas shows these under the `LIVE_KEYCLOAK` namespace, with per-login correlation ids. |
| `DETERMINISTIC OFFLINE FIXTURE` / `OFFLINE_FIXTURE` | Measured against the offline harness: locally generated keys, synthetic issuers, deterministic inputs. Proves the validator logic; does **not** prove Keycloak behaved the same way. |
| `EPHEMERAL` | A run executed with no evidence store (CLI without a store). It was never persisted — it must never be presented as saved evidence. |
| `PREVIOUS SAVED EVIDENCE` | A stored report from an earlier run. Check its date and mode before trusting it. |
| `NOT RUN` / `BLOCKED` | Not attempted, or blocked (e.g. no Docker). Never read as a pass. |

A green offline run never implies the Keycloak integration passed. The
offline suite is the core that runs everywhere; the Keycloak lane runs
only on a machine with Docker. Current status for every gate is in
[`docs/VALIDATION_AND_LIMITATIONS.md`](docs/VALIDATION_AND_LIMITATIONS.md).

## Prerequisites

| Path | Needs |
|---|---|
| **Full lab (recommended)** | Docker Desktop (Windows/macOS) or Docker Engine + Compose v2 (Linux), 8 GB RAM recommended, ~5 GB free disk, a modern browser, internet **during installation only** (image/package downloads) |
| **Offline fixtures only** | Python 3.12 (no Docker, no Keycloak). Runs the real validators against local fixtures; the real-login gates stay NOT RUN. See [`docs/WINDOWS_SETUP.md`](docs/WINDOWS_SETUP.md) §4 |

No Ubuntu *distro* is required on Windows — but the WSL 2 *feature*
and BIOS virtualization ARE required for Docker Desktop's engine
(check with `wsl --status`; see
[`docs/WINDOWS_SETUP.md`](docs/WINDOWS_SETUP.md) §2). No paid service,
API key, cloud account, or GitHub authentication is required. Keycloak
needs ~1–1.5 GB RAM; the full hardware picture is in
[`docs/WINDOWS_SETUP.md`](docs/WINDOWS_SETUP.md).

## Quick start

```bash
# 1. Extract the release ZIP, open a terminal in the folder.
# 2. Secure first-time setup (generates a private password and boots the lab):
./scripts/setup.sh
#    For subsequent starts: ./scripts/start.sh

# 3. Check health (Keycloak needs 60–120 s on first boot):
./scripts/doctor.sh

# 4. Stop / reset:
./scripts/stop.sh              # stop, keep synthetic data
./scripts/reset.sh --confirm   # wipe synthetic data (re-imported on next start)
```

On Windows, run the `.sh` scripts from **Git Bash** (included with Git
for Windows); the `docker compose` commands work in PowerShell. Full
Windows instructions: [`docs/WINDOWS_SETUP.md`](docs/WINDOWS_SETUP.md).
Native PowerShell gate runner (no host Python/Node needed):
`.\scripts\test-all.ps1` (offline) or
`.\scripts\test-all.ps1 -Full -Strict` (full).

Full gate: stop the lab first (keeps your data), run the test, then
start it again — the `-Full` runner needs ports 8080/8000/5173 free
for its disposable cold-start stack:

```bash
docker compose down
.\scripts\test-all.ps1 -Full -Strict   # Windows
./scripts/test-all.sh --full --strict  # Linux/macOS (or Git Bash)
docker compose up -d
```

## First launch

| Service | URL |
|---|---|
| Research console + portal | http://127.0.0.1:5173 |
| Backend health | http://127.0.0.1:8000/api/v1/health |
| Lab status (measured IdP + last login) | http://127.0.0.1:8000/api/v1/lab/status |
| Keycloak admin (lab only) | http://127.0.0.1:8080/admin |

**Synthetic users** (fictional Cedarbridge Campus Club members — not real
people; passwords are synthetic lab credentials, localhost-only):

| Username | Password | Roles |
|---|---|---|
| `student_01` | `LabPass-Student-01!` | member |
| `officer_01` | `LabPass-Officer-01!` | member, officer |

Sign in as `student_01`, open the member page (works), then the officer
page (denied — 403). Sign in as `officer_01` and the officer page works.
That is scenarios I1 + I13 in one minute. The 10–15 minute guided tour
is in [`docs/REVIEWER_GUIDE.md`](docs/REVIEWER_GUIDE.md).

## Running the scenarios (I1–I7 and beyond)

Offline (no Docker needed — the deterministic harness):

```bash
cd backend
python -m identityforge.cli scenario I6        # one scenario
python -m identityforge.cli verify-all  # all offline scenarios
```

With the lab running (real Keycloak lane — reviewer machine with Docker,
or the host-run stack):

```bash
./scripts/test-all.sh --full --strict   # every gate; fails if any required gate was skipped
python3 scripts/live-gate.py all        # real Keycloak login + binding + K2/K3 negatives only
```

Or use the **Scenario Studio** in the research console — it runs the same
measured scenarios and shows the same reports. The scenario catalogue,
method, and the full I1–I18 list are in
[`docs/SCENARIO_METHOD.md`](docs/SCENARIO_METHOD.md).

### The seven core scenarios

| ID | Scenario | Secure result |
|---|---|---|
| I1 | Normal login (positive baseline) | Session created; member resource OK; officer action denied for a student |
| I2 | Incorrect state / transaction binding | Callback rejected, no session |
| I3 | Wrong PKCE verifier | Token exchange denied, no token/session |
| I4 | Invalid redirect URI | Authorization server rejects the unregistered redirect; no code sent elsewhere |
| I5 | Wrong issuer | Rejected despite a well-formed token/signature |
| I6 | Wrong audience | Rejected despite a valid signature |
| I7 | Expired or replayed transaction | Rejected per the relevant boundary; no renewed session from a replay |

Plus I8–I18 (nonce, bad signatures, code replay, session fixation,
logout, authorization boundary, malformed input, CSRF, SSRF/config).
Each scenario records the secure result **and** the isolated flawed
fixture result, the exact decision step, and the reason code.

## Tests

```bash
./scripts/test-all.sh                 # offline profile (default): offline gates required, live gates reported NOT RUN
./scripts/test-all.sh --offline --strict  # offline gates, failing if any required gate was skipped
./scripts/test-all.sh --full --strict # every gate; fails if any required gate was skipped or unavailable
./scripts/test-gate-strictness.sh     # negative test: proves --full cannot go green while live gates are skipped
cd backend && python -m pytest -q -m "not live_keycloak"  # backend offline suite (520 tests in total; 516 offline + 4 provider-dependent, see below)
cd frontend && npm run typecheck && npm test -- --run && npm run build
cd frontend && npm run test:e2e       # Playwright, lab running
cd frontend && npm run test:screenshots  # real screenshots at 320/390/768/1280/1440/1920
```

On Windows (PowerShell 5.1 or 7, no host Python/Node needed):

```powershell
.\scripts\test-all.ps1                # offline gates in containers
.\scripts\test-all.ps1 -Full -Strict  # + disposable cold-start + real Keycloak login + browser E2E
```

The gate runner reports **19 explicit gates** with PASS / FAIL / NOT RUN
/ NOT APPLICABLE (`test-results/gates.json`): OFFLINE_UNIT, OFFLINE_SCENARIOS,
DOCS_CONTRACT, DOCS_CONTRACT_PATHS, VERSION_CONTRACT, FRONTEND_TYPECHECK, FRONTEND_UNIT, FRONTEND_BUILD,
PYTHON_DEPENDENCY_AUDIT, NPM_FULL_LOCKFILE_AUDIT, GHSA_DIRECT_FALLBACK,
COMPOSE_CONFIG, CLEAN_COMPOSE_BUILD_BOOT, LIVE_PROVIDER_PYTEST, REAL_KEYCLOAK_LOGIN,
REAL_SECURITY_NEGATIVES, REAL_LAB_RESET, PLAYWRIGHT_E2E, RESPONSIVE_QA. Both
runners define the same 19 gates: `test-all.sh` and `test-all.ps1`
(v8.0.3 closed the v8.0.2 ps1 divergence — the ps1 OFFLINE_UNIT now
uses `-m "not live_keycloak"` and the ps1 full profile adds
LIVE_PROVIDER_PYTEST). (v5:
DOCS_CONTRACT is new — it fails the run if a doc or example names a reason
code or report field the source does not define; see
`scripts/validate-docs-contract.py`.) The offline
profile can pass while honestly reporting `LIVE E2E NOT RUN`; the full
profile cannot. A green run never implies a gate that was NOT RUN.
**Backend pytest totals 520 tests: 516 offline + 4 provider-dependent.**
The 4 (callback replay / cross-browser binding, replay-after-consume,
login-start rate limit, browser cookie + S256 — all in
`backend/tests/adversarial/test_ws1_v8_oidc.py`) are marked
`live_keycloak` and need a live Keycloak on 127.0.0.1:8080; without one
they fail with 503 PROVIDER_UNAVAILABLE, so the offline selection
(`-m "not live_keycloak"`, the default CI backend lane,
`test-all.sh --offline`, `verify-release.sh` BACKEND_PYTEST) excludes
them, and they run only in the full profile (`test-all.sh --full` gate
LIVE_PROVIDER_PYTEST, against the cold-started disposable Keycloak;
CI keycloak-e2e lane). The separate 51 WS3 depth tests are never added
to the 520. See `scripts/test-offline-provider-selection.sh`, which
regresses both halves (offline passes with no provider; live runs all
four against a real provider).
**Dependency gates are deliberately split:** `NPM_FULL_LOCKFILE_AUDIT`
is the real `npm audit` over the resolved lockfile tree;
`GHSA_DIRECT_FALLBACK` is informational, direct dependencies only,
and NEVER satisfies the full audit — a blocked `npm audit` plus a
clean GHSA fallback still FAILS strict mode. When the full npm audit
executes (clean or with findings), the fallback is NOT APPLICABLE —
it did not run, and a PASS there would be a phantom. `PYTHON_DEPENDENCY_AUDIT`
is `pip-audit` over the pinned freeze.

The full test matrix (unit, protocol, integration, browser, adversarial,
build checks) is in [`docs/TEST_MATRIX.md`](docs/TEST_MATRIX.md).
Status words used everywhere: **PASS** (executed, asserted observations
held), **FAIL** (observed outcome contradicts a requirement), **ERROR**
(execution interrupted), **NOT RUN** (blocked/not attempted),
**INCONCLUSIVE** (evidence insufficient for a verdict).

## Reports and exports

Every run produces a report (JSON or Markdown from the API;
`GET /api/v1/runs/{id}/report` — CSV is generated client-side by the
console, with formula-injection neutralization) from the console
(**Findings & Evidence** → download) or the API. Reports contain:
scenario id, mode, provenance (`OFFLINE_FIXTURE` / `EPHEMERAL` /
`LIVE_KEYCLOAK`), timestamps, code/fixture revision, provider,
expected vs observed outcome, verifier decisions, transaction
timeline, secure vs flawed results, actual session state
(`session_preexisted`, `session_revoked`, `flawed_observed_result`),
resource-access outcome, reason code, elapsed time, and a SHA-256 hash
of the canonical redacted record. Reports never contain tokens, codes,
verifiers, cookies, or passwords. If the server report fetch fails,
the console offers a visibly labelled `LOCAL_UNSAVED_COPY` download
instead — never a silent local substitute for a persisted report. Every
download now carries an explicit provenance label —
`SERVER_VERIFIED_ARTIFACT` (the server's own report),
`CLIENT_DERIVED_FROM_SERVER_RUN` (CSV/Markdown generated in the browser
from a re-fetched server run), or `LOCAL_UNSAVED_FALLBACK` (built from
the run held in the browser because the server fetch failed) — so a
download never looks server-verified when it is not (v5, IF-V4-12). A
labelled template is in
[`example-reports/REPORT_TEMPLATE.json`](example-reports/REPORT_TEMPLATE.json).

## How to read a secure-vs-flawed comparison (without exaggeration)

- **"Flawed fixture allowed it" ≠ "account takeover."** It means one
  weakened check accepted one synthetic input in an isolated harness. It
  proves the check matters; it does not prove a real attacker could
  exploit the real portal.
- **"Secure fixture denied it" ≠ "the system is fully safe."** It means
  this input, at this step, was rejected. Other inputs and steps need
  their own evidence.
- **A JWT being invalid is not a full attack, and a failed login is not
  proof of complete safety.** Judge by the asserted observations: the
  reason code, no session minted, no resource accessed.
- **Distinguish four facts** in every report: the input was accepted by a
  handler; the validator's decision; whether a session was minted;
  whether a protected resource was actually accessed.

## Known limitations

- **Local HTTP only** — a labelled development exception. Never deploy
  this lab beyond localhost as shipped; HTTPS is required for any other
  use (see [`SECURITY.md`](SECURITY.md)).
- **Keycloak 26.8.2 pin** — released 2026-11-05, the supported line
  (33 CVE fixes; see `docs/KEYCLOAK_INTEGRATION.md`). Do not downgrade
  the pin without re-running the full live gate.
- **Operation Trustline v6 (2026-11-11)** — sixth-archive independent
  source audit of v5 (findings IF-V5-01..12), repaired in place,
  version **1.6.0**. Headline fixes: the docs-contract checker no
  longer skips source files when the tree sits under a parent folder
  named `data` (it now filters on paths relative to the project root;
  15/15 path-independence checks in normal, `data/`-ancestor and
  spaces paths); live-login counts are now exact units —
  `live_login_events` (saved event rows), `live_login_transactions`
  (`COUNT DISTINCT correlation_id`) and `live_login_successful_transactions`
  (transactions containing a `SESSION_CREATED` event) — the old
  `live_logins` key survives only as a deprecated alias labelled
  EVENTS; retention now evicts the oldest **whole** run and the oldest
  **whole** login transaction, so a retained report can no longer
  contradict its retained events; a single version source
  (`identityforge.__version__`) feeds pyproject, FastAPI, `/health`,
  package.json/lockfile and the UI, enforced by a version-contract
  gate; Overview/Settings/Atlas model request states explicitly
  (IDLE/LOADING/READY/STALE/ERROR/NOT RUN) so a retry can never show
  stale green; the recent-20 logins list is labelled as a recent
  sample beside the retained transaction total; retention is disclosed
  honestly ("old evidence is automatically pruned at capacity; manual
  full reset requires an officer session + CSRF + two confirmations").
  Test-all now runs **18 gates**. Full evidence:
  `docs/VERIFICATION_LOG.md` (Operation Trustline v6 section).
  Backend pytest **374 passed**, Vitest **110/110**, Playwright and
  live-gate figures in that log (parent's own runs, 2026-11-11).
  **PARTIALLY VERIFIED** — Docker Compose boot, the in-image
  Keycloak healthcheck, Windows PowerShell 5.1, and the full `npm
  audit` remain the reviewer's gates (exact commands in
  `docs/REVIEWER_GUIDE.md` §7).
- **Operation Trustline v7 (2026-11-11)** — seventh-release targeted
  hardening of v6 (findings IF-V6-01..06), version **1.7.0**, NOT a
  rebuild and NOT an aesthetic overhaul. Headline fixes: a live login
  counts as verified only when the full canonical timeline is
  present and ok (AUTH_STARTED → CALLBACK_RECEIVED →
  BINDING_VERIFIED → TOKEN_ENDPOINT → ID_TOKEN_VALIDATED →
  SESSION_CREATED) — a bare SESSION_CREATED tail is no longer a
  verified sign-in; Overview never shows a current-green Verified
  pill for STALE data (it shows a past-tense "Last verified at …"
  chip instead); Reports attributes each sign-in step to the person
  who actually signed in, from a complete timeline; client-derived
  exports are assembled from the re-fetched server report, never
  from the stale browser-local run; `useResource` retries abort the
  superseded request; Settings keeps reset disabled while the
  operator identity is unconfirmed. Atelier v7 refines the v6 design
  in place (same ink/graphite/porcelain/brass/teal tokens): denser
  Data-requests card, a live-counts hero (retained transaction total
  large, event total small), a provenance legend with a visibly
  degraded LOCAL UNSAVED export, a 7-state Atlas legend with
  missing-stage reasons, persona/environment chips on the reviewer
  steps, and forced-colours support. Test-all still runs **18
  gates**. Full evidence: `docs/VERIFICATION_LOG.md` (Operation
  Trustline v7 section). WS3-measured in-session: docs-contract
  paths **15/15**, version-contract **PASS** (real tree, 1.7.0) and
  **13/13** (fixtures), docs-contract **PASS, 0 violations**, build
  `index-BXc-Ornr.js` **170.04 kB / 55.20 kB gzip** (v6 was 168.07 kB
  / 54.70 kB gzip). Backend pytest, Vitest, Playwright and live-gate
  figures are the coordinator's Pass A/B/C rows — WS2's
  failing-first suites were still landing when WS3 measured, so no
  v6 figure is copied forward as a v7 result.
  **PARTIALLY VERIFIED** — Docker Compose boot, the in-image
  Keycloak healthcheck, Windows PowerShell 5.1, the full `npm
  audit`, and CI execution remain the reviewer's gates (exact
  commands in `docs/REVIEWER_GUIDE.md` §7).
- **Operation Trustline v8.0.5 (2026-11-14)** — final two-item
  security hardening closure of the delivered v8.0.4 archive,
  version **1.8.5**, NOT a second pentest and NOT a redesign. It
  closes the last two open LOW-severity hardening items from the v8
  pentest: IF-V8-42 — the app Docker images now run as the dedicated
  non-root user `identityforge` (UID:GID 10001, no `USER root` in any
  Dockerfile), with a one-shot, fail-closed `backend-data-prep`
  service that repairs `/app/data` ownership for fresh AND existing
  root-owned volumes before the backend starts, pip-audit installed
  at build time (the ps1 audit gate no longer installs at gate
  time), and the E2E image non-root too; IF-V8-43 — every GitHub
  Action is pinned to an upstream-verified full commit SHA with a
  `# vX.Y.Z` comment, guarded by the repeatable checker
  `scripts/test-action-pins.sh` (new CI scripts-lane step, lane now
  26 steps). Honest statuses: IF-V8-42 is PATCH PREPARED / RUNTIME
  VERIFICATION PENDING (Docker build/boot/`id`/volume-migration/E2E
  NOT RUN in the build sandbox — reviewer closes it on Docker
  Desktop per `docs/WINDOWS_SETUP.md` §3); IF-V8-43 is SHA PIN
  VERIFIED, HOSTED CI PENDING (hosted Actions execution NOT RUN —
  reviewer closes it with the test-branch run in
  `docs/ACTION_SHA_PINS.md`). No product behaviour changed; the 12
  views, 18 scenarios, 520 backend tests (516 offline + 4 live),
  51 WS3 tests, and 19 gates are unchanged. Full evidence:
  `docs/RELEASE_MANIFEST.md` and `docs/VERIFICATION_LOG.md`
  (Operation Trustline v8.0.5 sections).
  **PARTIALLY VERIFIED** — Docker Compose boot, the in-image
  Keycloak healthcheck, Windows PowerShell 5.1, the Docker Desktop
  live-provider execution of the ps1 LIVE_PROVIDER_PYTEST gate, the
  full `npm audit`, and GitHub Actions execution remain the
  reviewer's gates (exact commands in `docs/REVIEWER_GUIDE.md` §7).
- **Operation Trustline v8.0.3 (2026-11-13)** — narrow
  Windows-runner correction + release clarity closure of the
  delivered v8.0.2 archive, version **1.8.3**, NOT a second pentest
  and NOT a redesign. It closes the one known v8.0.2 divergence:
  `test-all.ps1` now defines the same **19 gates** (12 offline + 7
  full) as `test-all.sh`, its OFFLINE_UNIT runs the offline selection
  (`-m "not live_keycloak"`), the full-profile gate
  LIVE_PROVIDER_PYTEST runs the four provider-dependent tests against
  the cold-started disposable Keycloak, and the stale VERSION_CONTRACT
  label ("1.7.3") is fixed. It also appends the parent's v8.0.2 Pass C
  outcome to the current-release report (see
  `docs/TRUSTLINE_V8.0.2_CURRENT_RELEASE_REPORT.md` §10) and isolates
  `verify-release.sh` BACKEND_PYTEST's database side effect to a
  disposable temp directory, so a second verifier run in the same
  extraction no longer false-fails FORBIDDEN_FILES. No product code
  changed; IF-V8-42/43 stay OPEN. Full evidence:
  `docs/RELEASE_MANIFEST.md` and `docs/VERIFICATION_LOG.md`
  (Operation Trustline v8.0.3 sections).
  **PARTIALLY VERIFIED** — Docker Compose boot, the in-image
  Keycloak healthcheck, Windows PowerShell 5.1, the full `npm
  audit`, and CI execution remain the reviewer's gates.
- **Operation Trustline v8.0.1 (2026-11-13)** — narrow
  documentation/security-evidence closure of the delivered v8
  archive, version **1.8.1**, NOT a second pentest and NOT a
  redesign. It completes the final report's Pass C section (§M) with
  the actual v8 Pass C evidence, reconciles every "fill before
  delivery" note in the pentest evidence index and test matrix,
  adds the missing IF-V8-84 row to the final report's findings
  table, corrects this README's stale active counts (340 → 491
  backend tests, 16 → 18 explicit gates) with a new docs-contract
  regression (check 7), and corrects the v8 verify-release count in
  the verification log to the log-verified **23 PASS / 0 FAIL /
  5 NOT RUN**. No product code changed; IF-V8-42/43 stay OPEN.
  Full evidence: `docs/RELEASE_MANIFEST.md` and
  `docs/VERIFICATION_LOG.md` (Operation Trustline v8.0.1 sections).
  **PARTIALLY VERIFIED** — Docker Compose boot, the in-image
  Keycloak healthcheck, Windows PowerShell 5.1, the full `npm
  audit`, and CI execution remain the reviewer's gates.
- **Operation Trustline v8 (2026-11-12–13)** — full adversarial
  penetration test + immediate remediation of the delivered v7.3.1
  archive, version **1.8.0**, release label v8. Findings fixed in
  the tree: issuer comparison rejected a trailing slash (IF-V8-01),
  callback missing-parameter reason codes were unreachable dead code
  (IF-V8-02), the transport rewrite transplanted query/fragment and
  truncated a pathed base (IF-V8-03), IdP response bodies were
  unbounded with a `RecursionError` escape (IF-V8-05), Vite preview
  served no security headers (IF-V8-40), socat forwarders were not
  bound to loopback (IF-V8-41); stale release prose in the
  quickstart guides fixed with a new docs-contract regression
  (IF-V8-80, check 6); the version-contract fixtures' vacuous
  negatives fixed (IF-V8-81); WS1's three new test files failed
  `ruff format --check` and blocked the offline gate (IF-V8-83,
  fixed mechanically). Depth work (WS3): Hypothesis property tests
  **24 passed**, differential **12 passed**, fault injection /
  concurrency / malformed corpus **15 passed**, stateful live
  sequence **55/55**, extra live probes **0 failed**. Full backend
  suite **482 passed, 0 failed** sequentially (twice,
  independently); the concurrent-run 431/51 was a transaction-store
  saturation artifact (IF-V8-82), as were the OIDC suite's 2
  failures and the raw-probe's CL+TE expectation (final probe run
  **21/21**). WS1 live gate **101/101**. Vitest **161/161**;
  `test-all.sh --offline` **11 PASS / 0 FAIL / 7 NOT RUN, rc=0**
  (GHSA 14/14 direct, 0 high/critical — advisory data cached from
  02:57:18Z); the frontend build is byte-identical to
  v7.1/v7.2/v7.3 (UI unchanged).
  Full evidence: `docs/FINAL_ADVERSARIAL_PENETRATION_TEST_REPORT.md`
  and `docs/VERIFICATION_LOG.md` (Operation Trustline v8 section).
  **PARTIALLY VERIFIED** — the final sequential Playwright run
  (IF-V8-42), Docker Compose boot, the in-image Keycloak
  healthcheck, Windows PowerShell 5.1, the full `npm audit`, and
  the final ZIP Pass C remain open (exact commands in
  `docs/REVIEWER_GUIDE.md` §7).
- **Operation Trustline v7.2 (2026-11-12)** — targeted maintenance
  of the delivered v7.1 archive (findings IF-V7.1-01..05), version
  **1.7.2**, NOT a redesign and NOT a v8. Headline fixes: the
  Compose healthcheck script no longer fails on a fresh extraction
  (the log directory is created before the first redirection, and a
  real `docker compose config` failure is reported with its own exit
  code instead of a shell redirection error); the discovery document
  is parsed by a real HTTP client (`scripts/discovery-check.py` —
  Content-Length and chunked framing, HTTP 200 + valid JSON + the
  exact canonical issuer, redirects never followed) with the exact
  in-image healthcheck command still proven separately inside the
  pinned Keycloak 26.8.2 image; the cold-start boots a disposable
  project with a unique name only after a port preflight proves the
  fixed ports free (fail fast with the stop/test/restart sequence,
  never touching the occupant), plus a read-only
  `--against-running-project` mode for an existing stack; the
  reviewer/beginner checklists no longer show an unguarded
  standalone reset (the lab reset is destructive and runs only
  inside the disposable cold-start run
  (`scripts/test-all.sh --full` / `scripts/test-all.ps1 -Full`),
  which generates a fresh disposable-project marker per run; never
  run `scripts/live-gate.py reset` by hand against a lab whose
  evidence you want to keep); and the quickstart hash commands name
  the real v7.2 final archive (the docs-contract gate now fails the
  run on a stale candidate name). Full evidence:
  `docs/VERIFICATION_LOG.md` (Operation Trustline v7.2 section).
  WS2-measured in-session: healthcheck regressions **27/27**
  (failing-first on the v7.1 source, then fixed), docs-contract
  paths **27/27**, version-contract **PASS** (real tree, 1.7.2) and
  **13/13** (fixtures), docs-contract **PASS, 0 violations**.
  Backend pytest, Vitest, Playwright and live-gate figures are the
  coordinator's Pass A/B/C rows — no v7.1 figure is copied forward
  as a v7.2 result for them.
  **PARTIALLY VERIFIED** — Docker Compose boot, the in-image
  Keycloak healthcheck, Windows PowerShell 5.1, the full `npm
  audit`, and CI execution remain the reviewer's gates (exact
  commands in `docs/REVIEWER_GUIDE.md` §7).
- **Operation Trustline v7.1 (2026-11-11)** — targeted maintenance
  of the delivered v7 archive (finding IF-V7-02), version
  **1.7.1**, NOT a redesign and NOT a v8. Headline fix: the
  dependency-gates fixture suite no longer hides node on
  NVM/Volta/asdf-style layouts — scenario drivers now run with the
  platform PATH preserved (`PATH="$SCEN_FAKEBIN:$ORIGINAL_PATH"`,
  fresh fake wrappers per scenario, no hard-coded `/usr/bin:/bin`),
  so the suite reads **55 passed, 0 failed** with node under
  `/usr/bin`, with node/npm only under an NVM-style directory, and
  with symlinked node/npm (failing-first with the old script on the
  NVM layout: 38 passed, 17 failed). The CI scripts lane now
  explicitly sets up Node 24 (`actions/setup-node@v4`) instead of
  depending on a preinstalled `/usr/bin/node`. Full evidence:
  `docs/VERIFICATION_LOG.md` (Operation Trustline v7.1 section).
  Backend pytest, Vitest, Playwright and live-gate figures were NOT
  RUN by WS2 (WS1 owns the frontend/backend/live stack) — no v7
  figure is copied forward as a v7.1 result for them.
  **PARTIALLY VERIFIED** — Docker Compose boot, the in-image
  Keycloak healthcheck, Windows PowerShell 5.1, the full `npm
  audit`, and CI execution remain the reviewer's gates (exact
  commands in `docs/REVIEWER_GUIDE.md` §7, which now also carries a
  two-minute starter checklist and a longer Windows Docker test
  checklist).
- **Operation Trustline v5 live gate (2026-11-11)** — fifth-archive
  independent source audit of v4 (findings IF-V4-01..12), repaired
  in place. Headline fix: the Keycloak healthcheck in
  `docker-compose.yml` used single-dollar `$resp` in a Compose value,
  which Compose interpolates before the container shell runs — the
  healthcheck inspected blank text and could block the backend and
  frontend from starting despite a healthy Keycloak JVM. It now uses
  `$$resp`, with a static regression that simulates Compose
  interpolation (`scripts/compose-config-check.py`) and a resolved-
  command check (`scripts/test-compose-healthcheck.sh`).
  **SOURCE FIXED; ACTUAL DOCKER HEALTHCHECK + COMPOSE BOOT NOT RUN**
  in the build sandbox (no Docker there) — the Docker boot, the
  in-image healthcheck, Windows PowerShell 5.1, and the full `npm
  audit` remain the reviewer's gates on Docker Desktop / Windows
  (exact commands in `docs/REVIEWER_GUIDE.md` §7). Other v5 fixes:
  `.dockerignore` files for both images (build contexts no longer
  carry the 99 shipped screenshots or a host `node_modules`); session
  counts now mean ACTIVE sessions only (`/api/v1/lab/counts` also
  reports the separate `sessions_total_issued`); repeated saves of a
  run ID atomically replace that run's events instead of duplicating
  them, with a documented retention budget (latest 1000 runs / 20000
  events / 1000 live-login events, visible via the storage budget);
  the Overview `Verified` step now requires backend ok + IdP
  reachable + issuer match; docs reason codes corrected to the exact
  `FailureReason` values with an automated docs-contract gate
  (`DOCS_CONTRACT`, 16 gates total); the ASGI body limit now slices
  each chunk to the remaining allowance (at most max + 1 bytes ever
  buffered). Full evidence: `docs/VERIFICATION_LOG.md` (Operation
  Trustline v5 section). Backend pytest **340 passed**, Vitest
  **92/92**, Playwright **65 passed + 1 skipped**, live gate `all`
  **101/101** (parent's own runs, 2026-11-11).
- **Operation Trustline v4 live gate (2026-11-11)** — real Keycloak
  26.8.2 login, authorization, logout, state binding, parallel
  logins, K2 wrong-PKCE and K3 unregistered-redirect negatives,
  Playwright E2E, and the new disposable REAL_LAB_RESET gate were
  verified live in the build sandbox (`scripts/live-gate.py all`,
  99/99 checks per run; login flow 37/37 PASS), where the stack ran
  as host processes because that sandbox has no Docker binary or
  daemon at all. The shipped `docker compose up` boot path itself
  was NOT RUN there and is the reviewer's first gate on Docker
  Desktop; the YAML-only compose validation passes. Full evidence:
  `docs/VERIFICATION_LOG.md` (Operation Trustline v4 section).
  Backend pytest **304 passed**, Vitest **64 passed**, Playwright
  **62 passed + 1 skipped**, axe zero-tolerance **25/25 with
  0 violations**, 99 fresh v4 screenshots at 6 widths. PowerShell
  7.4.6 execution of `test-all.ps1` WAS run in the build sandbox
  (on Linux, 18 checks); Windows PowerShell 5.1 execution remains
  NOT RUN.
- **Operation Trustline v3 live gate (2026-11-11)** — real Keycloak
  26.8.2 login, authorization, logout, state binding, parallel
  logins, K2 wrong-PKCE and K3 unregistered-redirect negatives, and
  Playwright E2E were verified live in the build sandbox
  (`scripts/live-gate.py all`, >80 checks per run; login flow 37/37
  PASS after the JWKS fix below), where the stack ran as host
  processes because that sandbox has no Docker binary or daemon at
  all. The shipped `docker compose up` boot path itself was NOT RUN
  there and is the reviewer's first gate on Docker Desktop; the
  YAML-only compose validation passes. Full evidence:
  `docs/VERIFICATION_LOG.md` (Operation Trustline v3 section).
  Backend pytest **246 passed**, Vitest **54 passed**, Playwright
  **56 passed + 1 skipped**, axe zero-tolerance **22/22 with
  0 violations**, 97 fresh v3 screenshots at 6 widths.
- **JWKS two-key fix (v3, 2026-11-11):** real Keycloak publishes an
  RSA-OAEP encryption key beside its RS256 signing key. The v3
  hardening initially rejected the whole JWKS document for that key
  and broke every real login (`/?error=JWKS_ERROR`). The parser now
  skips non-signing keys and fails closed only on malformed signing
  keys; the live JWKS parses to exactly the RS256 signing key.
- **Keycloak burns auth codes on failed PKCE exchanges** (measured
  2026-11-11): a wrong-verifier exchange returns 400 `invalid_grant`
  and the code is dead afterwards. Test drivers must use a disposable
  transaction for wrong-verifier probes.
- **Reset is officer-gated (v3)** — it requires a logged-in officer
  session + CSRF + `{"confirm": "RESET_LAB"}` (401/403/422 otherwise),
  and revokes the operator's own session. The v2 "unprivileged on
  loopback" description is withdrawn.
- **Offline fixtures are not Keycloak.** Fixture results prove validator
  logic, not IdP behaviour. They are labelled differently everywhere.
- **Keycloak-enforced controls are observed, not owned** (code single-use,
  exact redirect matching, PKCE at the token endpoint). Only the
  integration lane can catch a change in Keycloak's behaviour.
- **Two synthetic users, two roles, one issuer, one redirect URI.** No
  production federation, SAML, mobile flows, or multi-issuer support.
- Full list: [`docs/VALIDATION_AND_LIMITATIONS.md`](docs/VALIDATION_AND_LIMITATIONS.md).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `doctor.sh` fails on Keycloak | Still starting — wait 60 s and re-run `./scripts/doctor.sh` |
| Login fails with an issuer error | Do **not** disable issuer validation; see [`docs/AUTH_FLOW.md`](docs/AUTH_FLOW.md) §6 (issuer hostname trap) |
| Port already in use | Stop the conflicting service. Ports are fixed for this lab — do not change them in `.env` |
| Docker missing | Use the offline fallback in [`docs/WINDOWS_SETUP.md`](docs/WINDOWS_SETUP.md) §4; Keycloak gates stay NOT RUN |
| `docker compose config` fails | Run `docker compose config -q` first (5 seconds) — it catches Compose errors before the ~1 GB download |

## How a reviewer can validate results independently

1. Extract the release to a fresh folder and run
   `./scripts/verify-release.sh` (static release audit: file
   presence, forbidden files incl. `*.egg-info` and runtime DBs,
   realm JSON, Compose YAML + locked ports + hostname-v2, script
   syntax, offline tests, frontend build; Docker checks report NOT
   RUN where Docker is absent — it does NOT boot the stack).
2. Boot the lab and follow [`docs/REVIEWER_GUIDE.md`](docs/REVIEWER_GUIDE.md)
   (normal login, wrong audience, wrong PKCE, officer boundary, report).
   On a machine with Docker, run `./scripts/test-all.sh --full --strict`.
3. Re-run any scenario from the CLI and compare its run ID, reason code,
   and outcome with the shipped report.
4. Check [`docs/VALIDATION_AND_LIMITATIONS.md`](docs/VALIDATION_AND_LIMITATIONS.md)
   for what was actually executed and what is still NOT RUN — if a claim
   elsewhere contradicts it, this file wins.

## Documentation map

| Document | What it answers |
|---|---|
| `docs/ARCHITECTURE.md` | Components, versions, ports, trust boundary |
| `docs/THREAT_MODEL.md` | Who the lab-local attackers are, controls, residual risks |
| `docs/AUTH_FLOW.md` | The login sequence, state machine, sessions, reason codes |
| `docs/STANDARDS_TRACEABILITY.md` | Each control mapped to RFC 9700 / 7636 / OIDC Core / 9207 / 8725 / 10017 |
| `docs/TEST_MATRIX.md` | Every test, where it runs, what counts as passing |
| `docs/SCENARIO_METHOD.md` | How scenarios are designed, run, and read honestly |
| `docs/DECISIONS.md` | Architecture decisions and their trade-offs |
| `docs/API_CONTRACT.md` | Versioned API: endpoints, schemas, status codes, auth rules |
| `docs/KEYCLOAK_INTEGRATION.md` | Issuer vs transport, hostname-v2, live-gate evidence |
| `docs/REMEDIATION_FINDINGS.md` | Every finding (Trustline + v2 + v3 + v4), root cause, fix, retest |
| `docs/REMEDIATION_TRACEABILITY.md` | Finding → fix → test traceability |
| `docs/UI_DESIGN_SYSTEM.md` | Trustline Atelier visual language, tokens, accessibility |
| `docs/VERIFICATION_LOG.md` | Dated evidence: commands, counts, environments, NOT RUN gates |
| `docs/VALIDATION_AND_LIMITATIONS.md` | What was verified, what is NOT RUN, what is not tested |
| `docs/REVIEWER_GUIDE.md` | 10–15 minute walkthrough |
| `docs/WINDOWS_SETUP.md` | Windows 11 + Docker Desktop, RAM/disk, offline fallback |
| `docs/SECURITY_ASSESSMENT.md` | Assessment scope, method, findings log (live-Keycloak findings TBD) |
| `docs/RELEASE_MANIFEST.md` | Release archive details (completed at release time) |
| `SECURITY.md` | Security policy, scope, how to report a problem |

## Attribution and license

- **Keycloak** (Apache License 2.0) — the local identity provider.
- **FastAPI, Pydantic, PyJWT, Authlib, httpx, uvicorn** — backend
  libraries under their respective open-source licences.
- **React, TypeScript, Vite, Vitest, Playwright** — frontend and test
  tooling under their respective licences.
- IdentityForge's own lab code and documentation are released under the
  **MIT License** — see [`LICENSE`](LICENSE).
- Standards referenced: RFC 9700, RFC 7636, OpenID Connect Core 1.0,
  OpenID Connect Discovery 1.0, RFC 9207, RFC 8725, RFC 10017, and OWASP
  OAuth 2.0 / ASVS guidance — see
  [`docs/STANDARDS_TRACEABILITY.md`](docs/STANDARDS_TRACEABILITY.md).

This lab was built as an educational project. It makes no claim of full
RFC compliance, security certification, or production readiness.
