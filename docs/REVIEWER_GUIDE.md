# Reviewer Guide — IdentityForge (5–10 minute guided path)

> Audience: a reviewer with Docker installed who wants to verify the lab
> works, without reading the whole codebase first. The console itself
> now carries an **8-step guided 5–10 minute path** (Overview and
> Reports & Walkthrough): start services → secure student sign-in →
> deny officer → officer sign-in → run I1–I18 offline cases → inspect
> live Atlas events → compare one missing-check model → export
> redacted evidence. Each step shows `Verified` only from
> browser-held evidence, otherwise `Not run yet`. This guide is the
> same path in text, with the commands the UI cannot run for you.
>
> Total time: 5–10 minutes if the images are already downloaded; allow
> extra time on first run for the Keycloak image download (~1 GB).
>
> Everything here runs on your own machine, on loopback only. No real
> accounts are involved. All data is synthetic.

## 0. Before you start (1 minute)

- **Prerequisites:** Docker Desktop (Windows/macOS) or Docker Engine +
  Compose v2 (Linux), 8 GB RAM recommended (see `docs/WINDOWS_SETUP.md`
  for the 4 GB fallback), a modern browser.
- **Get the lab:** extract the release ZIP to a folder, open a terminal
  there. Do not run it from inside the ZIP.
  **Verify the archive first (v6, IF-V5-09):** check the SHA-256 of
  the ZIP against the hash in the delivery message *before*
  extracting — a mismatch means the download is corrupt or not the
  delivered file; do not run it. On Windows (PowerShell):
  ```powershell
  Get-FileHash .\IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V8.0.5_FINAL_20261114.zip -Algorithm SHA256
  ```
  On Linux/macOS:
  ```bash
  sha256sum IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V8.0.5_FINAL_20261114.zip
  ```
  (Use the actual ZIP filename from the delivery message — the name
  above is the v8.0.5 final release name. The docs-contract gate
  (IF-V7.1-05) fails the run if a quickstart command names a
  different archive: `scripts/validate-docs-contract.py` compares
  these commands against the **Filename:** of the current release
  in `docs/RELEASE_MANIFEST.md`.)
  The printed hash must equal the delivery message's hash exactly.
  (The hash is a property of the ZIP file itself, so it is not
  printed inside the archive — see `docs/RELEASE_MANIFEST.md`.)
  **Extraction quirk (measured):** extract with Info-ZIP `unzip`
  (Windows: the built-in "Extract All" or `Expand-Archive` also
  preserve the bits) — Python's `zipfile.extract` does NOT restore
  the stored Unix executable bit, so `.sh` files come out 0660
  instead of 0770. After a Python-based extraction, run scripts as
  `bash scripts/<name>.sh` instead of `./scripts/<name>.sh`, or
  restore the bits with `chmod +x scripts/*.sh`. Either fallback is
  fine; the dropped bit is an extraction-tool behaviour, explicitly
  NOT an application defect — the scripts themselves are unchanged
  and correct.
- **Not run in the build sandbox — your gates:** the Docker Compose
  boot and the Keycloak healthcheck in-image validation were NOT RUN
  where this release was built (no Docker there). The healthcheck
  *source* was fixed in v5 (IF-V4-01: the Compose `test:` value used
  single-dollar `$resp`, which Compose interpolates to empty before
  the container shell runs; it now uses `$$resp`, with a static
  regression in `scripts/compose-config-check.py` and a resolved-
  command check in `scripts/test-compose-healthcheck.sh`) — but the
  fix is proven at the source level only, not by a real container
  boot, so it stays a reviewer gate: **SOURCE FIXED; ACTUAL DOCKER
  HEALTHCHECK + COMPOSE BOOT NOT RUN**. PowerShell 7.4.6
  execution WAS run there (on Linux — see §7); Windows PowerShell 5.1
  execution remains NOT RUN (5.1 is Windows-only). They are reviewer
  gates; §7 lists the exact commands. Nothing in this guide claims
  they passed.

## 1. Boot the lab (2–3 minutes, first run longer)

```bash
./scripts/setup.sh
docker compose up --build -d
./scripts/doctor.sh
```

On Windows (PowerShell):

```powershell
.\scripts\setup.ps1
docker compose up --build -d
.\scripts\doctor.ps1
```

Wait for `doctor` to report all three services healthy. Keycloak takes
60–120 seconds on first boot. `doctor.sh --brief` / `doctor.ps1 -Brief`
prints exactly one line (`READY` or `NOT READY: <reasons>`). If it
reports a failure, wait a minute and re-run before doing anything else.
Note: doctor FAILS unless the backend reports `idp.reachable=true`
AND `idp.issuer_matches=true` — a reachable Keycloak with the wrong
issuer is NOT ready.

Keep the lab running while you review (§2–§6). When you reach §7,
stop it first — `-Full` needs ports 8080/8000/5173 free for its
disposable cold-start stack (see §7). The runner refuses with the
exact stop → test → restart sequence if the ports are busy.

Open the console: **http://127.0.0.1:5173**

You should see the IdentityForge research console. The header shows
one readiness pill — it should read **Ready — IdP verified** once
Keycloak answers discovery — with a `Details` toggle that opens the
diagnostics (backend, issuer, provider mode, IdP reachability +
issuer match, discovery URL, evidence health, last verified login).
If it reads `Not ready` or `Lab status unavailable`, Keycloak is not
up yet — do not proceed to the login test. The Overview's guided
path (step 1) tracks the same state.

## 2. Normal login — scenario I1 (3 minutes)

1. Go to the **Campus Club Portal** area and click **Sign in with local
   identity provider**.
2. You are redirected to Keycloak. Sign in as:
   - Username: `student_01`
   - Password: `LabPass-Student-01!`
   (Synthetic lab credentials — see the realm import. They work only on
   your localhost lab.)
3. You return to the portal, signed in as `student_01`. The dashboard
   shows fictional member information.
4. Open the **member-only** resource — it loads.
5. Open the **officer-only** resource — it is **denied** (403). This is
   the point: a valid login is not the same as permission. `student_01`
   is a member, not an officer.
6. In the console, open **Flow Inspector** for this login: you should see
   the transaction states `CREATED → AUTHORIZATION_STARTED →
   CALLBACK_RECEIVED → CODE_REDEEMED → TOKEN_VERIFIED → SESSION_CREATED`,
   with redacted steps (no tokens or codes shown).
7. Log out, then sign in again as `officer_01` / `LabPass-Officer-01!`.
   Now the officer-only resource loads.

**What you have verified:** the real OIDC code + PKCE login works end to
end, and authorization is enforced separately from authentication.

## 3. Wrong audience — scenario I6 (2 minutes)

1. Go to **Scenario Studio** and open **I6 — Wrong audience**.
2. Read the explanation, then run it (offline fixture). The run uses a
   correctly signed token that targets a *different* synthetic client.
3. Observe: the secure variant **rejects** it with reason
   `WRONG_AUDIENCE` (wrong audience — the token is for a different
   client), no session is created, and the member resource is
   not accessed. The flawed variant (audience check removed) **accepts**
   the same token.
4. Download the run report (JSON) and check the fields: `secure_result`,
   `flawed_result`, `resource_access_outcome`, `validation_reason`,
   and the `mode` label — it must say **DETERMINISTIC OFFLINE FIXTURE**,
   not "real Keycloak".

**What you have verified:** a valid signature is not enough — the token
has to be *for this application*. And the comparison is honest about
which mode produced it.

## 4. Wrong PKCE verifier — scenario I3 (2 minutes)

1. Open **I3 — Wrong PKCE verifier** in Scenario Studio and run it.
2. Observe: the token exchange is denied (`PKCE_MISMATCH` — the
   verifier does not match the challenge), no
   token and no session are issued.
3. Optional, with the lab running: this is also a Keycloak-enforced
   control. The integration lane (see `docs/TEST_MATRIX.md` §3) asserts
   the same denial against the real token endpoint. In the offline
   fixture you are seeing the lab's deterministic model of that denial.
   Do not conflate the two strings: the fixture reason is
   `PKCE_MISMATCH`; Keycloak itself refuses the real exchange with the
   OAuth error `invalid_grant` ("PKCE verification failed") — see
   `docs/AUTH_FLOW.md` §2.

**What you have verified:** stealing an authorization code is not enough
without the verifier — and the lab tells you which part is Keycloak's
enforcement and which part is its own model.

## 5. Officer boundary — scenario I13 (1 minute)

1. Sign in as `student_01` again (or stay signed in).
2. Try the officer-only resource directly: `GET /api/v1/portal/officer`
   in the console, or the officer page in the portal.
3. Observe a **403 FORBIDDEN** with a safe error — no stack trace, no
   data. Then sign in as `officer_01` and confirm it loads.

**What you have verified:** authorization is checked server-side on every
request, not once at login.

## 6. Report, portfolio summary, and reset (1 minute)

1. Open **Findings & Evidence** / **Reports**, pick any completed run,
   and download the JSON and Markdown reports. Confirm they contain no
   tokens, codes, or passwords (search for `LabPass` — it must not appear
   in a report). Read the **provenance legend** at the top of Findings &
   Evidence first (v7): a download is a Server-verified artifact, a
   Client-derived-from-server file, or a LOCAL UNSAVED COPY — and a
   LOCAL UNSAVED COPY looks intentionally different (dashed amber
   warning), so check the notice next to the download, not just the
   filename. A client-derived CSV/Markdown is assembled from the
   re-fetched server report (v7, IF-V6-01); if the server report cannot
   be reached, the fallback is a labelled LOCAL UNSAVED COPY — never a
   silent substitute.
2. In **Reports**, download the **portfolio evidence summary** — a
   privacy-safe JSON (counts, per-scenario latest outcomes, live-login
   counts + synthetic usernames only, gates-not-measured note, and an
   explicit note that the lab was built with AI-assisted development;
   sole manual authorship is not claimed).
3. Run a scenario a second time and compare the two runs — the outcome
   and reason code should match; timestamps and run IDs differ.
4. **Reset (officer-only):** in **Lab Settings**, the reset card
   shows who is signed in and the counts that would be cleared. It is
   enabled only for `officer_01` — a student session gets 403
   `policy_denied` and nothing is cleared. After a successful reset
   the officer's own session is revoked: sign in again to continue.
   This is the **manual full reset**: "Old evidence is automatically
   pruned at capacity; manual full reset requires an officer session
   + CSRF + two confirmations" (v6, IF-V5-08). It is not the same
   thing as automatic pruning (oldest evidence only, at capacity,
   on save), as session revocation (logout/expiry — deletes no
   evidence), or as deleting the Keycloak/evidence volumes — see
   `docs/EVIDENCE_RETENTION.md` for the four-way distinction.
5. When finished: `./scripts/stop.sh` (stops the containers, keeps
   data and volumes; PowerShell: `docker compose down` or
   `.\scripts\stop.ps1`). **Do not** run `docker compose down -v`
   or `./scripts/reset.sh --confirm` unless you mean to delete the
   volumes: those wipe the evidence database AND the Keycloak realm
   data on the host, with no officer session or CSRF involved, and
   nothing is kept (the realm is re-imported on the next start, but
   all recorded evidence and logins are gone).

   **Reading Overview honestly (v7, IF-V6-03):** a reviewer step that
   says "Last verified at …" in amber is HISTORICAL — the evidence
   was verified at that time, but a newer request failed, so it is
   not current live health. Retry the data requests (Overview,
   "Retry failed requests") to re-verify; a successful retry turns
   the step back to Verified. A step is never green for stale data.
   Likewise, a sign-in step is Verified only for the person who
   actually completed a full login timeline (v7, IF-V6-02/04) — a
   bare SESSION_CREATED tail, or the other user's login, does not
   verify it.

## 7. Gates that were NOT RUN in the build sandbox — run these

Docker Compose boot, the Keycloak healthcheck in-image validation
and Windows PowerShell 5.1 execution were NOT RUN in the historical
build environment (2026-11-11/12 sandbox) — they are your gates on
Docker Desktop / Windows, never a pass. The historical
build-environment statement about that sandbox is kept, explicitly
labelled, only in `docs/VERIFICATION_LOG.md` and
`docs/RELEASE_MANIFEST.md`. PowerShell 7.4.6 WAS
executed there (preflight / help / argument / ports paths with a stub
`docker` — see `scripts/test-ps1-preflight.sh`, 20 passed, 0 failed,
1 skipped; the skip is the ports-free cold-start path, which needs a
real daemon). The native healthcheck wrapper
`scripts/test-compose-healthcheck.ps1` was likewise executed there
under 7.4.6 on Linux with a stub `docker` (v7.3: 13 checks — help,
default, disposable cold-start, read-only, no-Docker explicit and
default modes, ports-occupied fail-fast, config-failure injection,
mutual exclusion, and the redirect/HTML/truncated discovery
negatives — all passing, plus a path-with-spaces run, 8 passed;
see `docs/VERIFICATION_LOG.md`). Windows PowerShell 5.1 execution
remains NOT RUN (5.1 is Windows-only). The 5.1 safety now rests on `scripts/native-invoke.ps1`
(IF-V4-08, v5): every native call goes through Start-Process with
stdout/stderr captured to SEPARATE files — no `2>&1` merge anywhere
in the runners — and the exit code comes from the process object.
Proven under 7.4.6 on Linux (`scripts/test-ps1-native.sh`: 22
PowerShell checks + 3 bash checks, all passing, incl. exit 0 + stderr
warning, exit 1/2, timeout → 124, spaces/Unicode/JSON args, and a
regression case proving a relative log path lands in the tree's
`test-results/`, not the launch directory). First real 5.1 execution
is yours — the commands below.
Run the commands below and record the result honestly; a NOT RUN gate
is never a pass.

### Two-minute starter checklist (v7.3)

Do this first, before the long full gate. Every command below is
copied verbatim from this section — nothing here is new syntax. If
any step fails, stop and fix Docker before running the full gate.
(First run downloads the ~1 GB Keycloak image and takes longer; the
two minutes is the command time once the images are built.)

- [ ] `.\scripts\test-all.ps1 -Help` — must exit 0 and print the
  stop-first workflow.
- [ ] `docker compose down` — stops the lab, keeps your data.
- [ ] `docker compose up -d` — restarts the lab.
- [ ] `.\scripts\test-all.ps1 -Offline` — offline gates in
  containers; the quick gate pass before the full one.

### Longer Windows Docker test checklist (v7.3)

Work through the blocks below in order, recording the exit code and
output of each. A NOT RUN gate is never a pass, and `--full --strict`
fails CLOSED (exit 1) when any required gate is FAIL or NOT RUN.

**Mandatory vs optional on Windows (v7.3, IF-V7.2-04).** Mandatory:
stop the lab, run `.\scripts\test-all.ps1 -Full -Strict`, restart —
that is the first and default Windows verification path, and it is
the only gate that proves the real Keycloak login end to end.
Optional extra proof: the standalone healthcheck wrapper below
(`.\scripts\test-compose-healthcheck.ps1 -WithDocker`) and the
manual native Docker commands after it. Heavy on 8 GB: the `-Full`
run is the heaviest step in the lab (Keycloak ~1–1.5 GB plus the E2E
image ~1–1.5 GB plus Docker itself; first boot 2–5 minutes for the
~1 GB image download, then Keycloak needs 60–120 seconds to start)
— run it with other apps closed, serially, never in parallel with
another gate. The standalone healthcheck wrapper is light by
comparison (one disposable cold-start stack, no E2E image). Nothing
here asks for a destructive bulk cleanup, an unrelated volume
deletion, or any publishing: the only `down -v` in this guide is the
disposable project's own scoped cleanup, and `docker system prune`
/ `wsl --unregister` are never run.

- [ ] Stop the lab, run the full gate, restart (the three-command
  Windows block below: `docker compose down`,
  `.\scripts\test-all.ps1 -Full -Strict`, `docker compose up -d`).
- [ ] Real Keycloak login + negatives only, lab running:
  `python3 scripts/live-gate.py all` — only if you have host
  Python 3 installed; otherwise the `-Full` runner above already
  runs the same live gates in containers, and no host Python is
  needed.
- [ ] Disposable reset sub-gate (REAL_LAB_RESET, never part of
  `all`): The lab reset is destructive and runs only inside the
  disposable cold-start run (`scripts/test-all.sh --full` /
  `scripts/test-all.ps1 -Full`), which generates a fresh
  disposable-project marker per run. Never run
  `scripts/live-gate.py reset` by hand against a lab whose evidence
  you want to keep.
- [ ] In-container live-gate on the Compose bridge (host map env):
  `docker compose -f docker-compose.yml -f docker-compose.test.yml --profile test run --rm live-gate python3 /scripts/live-gate.py all`.
- [ ] Compose healthcheck, resolved + live (v7.3, IF-V7.1-02/03/04,
  IF-V7.2-04): **Windows-first, no host Bash or Python needed.**
  Stop the lab first (`docker compose down` — WITHOUT `-v`, so your
  data is kept), then run the native wrapper, then restart:
  `.\scripts\test-compose-healthcheck.ps1 -WithDocker`
  (disposable cold-start: fails fast if the fixed ports are busy;
  read-only alternative for a running stack:
  `.\scripts\test-compose-healthcheck.ps1 -AgainstRunningProject`,
  which creates/deletes nothing — no up, no down, no reset).
  The Bash script `bash scripts/test-compose-healthcheck.sh
  --with-docker` is the **Linux/macOS or explicitly installed Bash
  environment only** form of the same check (Git Bash, or a Bash
  you installed yourself) — it is NOT required on Windows, and you
  do NOT need to install Ubuntu, any WSL distribution, or a WSL
  terminal to run the healthcheck: Docker Desktop's WSL 2 backend
  manages its own distros and does not give you a Bash prompt.
- [ ] Full npm audit (JSON form + classifier):
  `cd frontend && npm audit --audit-level=high --json > ../test-results/audit-frontend.json`,
  then `python3 ../scripts/npm-audit-classify.py --stdout ../test-results/audit-frontend.json`.
  This manual form needs host Node + Python; the `-Full` runner
  already runs the audit in containers, so skip the manual form if
  you do not have them installed.
- [ ] Playwright JSON report validation (after the `-Full` run):
  `python3 scripts/validate-playwright-report.py --report test-results/playwright-report.json --target identityforge-coldstart-<timestamp-from-gates.json>`.
  Needs host Python 3; if you do not have it, the `-Full` runner's
  own gates already validate the report in containers.
- [ ] Docker build-context check (both `docker build` commands
  below; the "transferring context" line must be a few MB, not
  ~160 MB).
- [ ] Windows reviewer commands (PowerShell 5.1 AND 7) below:
  `-Help`, `-Offline`, `-Full -Strict`, the two usage-error cases
  (exit 2), the missing-daemon case, the two occupied-ports cases,
  the blocked-audit-endpoint case, the failing-test case, and the
  path-with-spaces case.

**Five separate proofs — do not conflate them (v7.3, IF-V7.2-04).**
A green healthcheck is not a login proof. These are distinct
claims, each with its own command:
1. **Compose container health** — `docker compose ps` shows
   keycloak `(healthy)` (and backend/frontend `(healthy)` after
   it). Proves the containers reached their health state.
2. **In-image shell probe** — the exact healthcheck command runs
   inside the pinned Keycloak 26.8.2 image (`docker compose exec
   keycloak bash -c '...'`; the wrapper runs it for you). Proves
   the in-container command works — not merely that a host
   endpoint answered.
3. **`/lab/status` canonical issuer validation** — the backend
   reports `idp.reachable=true` AND `idp.issuer_matches=true`
   against the exact canonical issuer
   `http://127.0.0.1:8080/realms/identityforge-lab` (see `doctor`
   in §1, and the wrapper's host-side discovery check). Proves the
   IdP the backend trusts is the local lab, not just any reachable
   Keycloak.
4. **Successful student and officer login + policy checks** — §2
   (student signs in, member resource loads, officer resource
   denied 403) and §5 (officer signs in, officer resource loads).
   Only this proves the real OAuth/OIDC authorization-code + PKCE
   login works and authorization is enforced separately from
   authentication. A health 200 alone proves none of it.
5. **Full dependency audit** — the npm audit (and pip-audit) gates
   in `-Full -Strict`. A clean healthcheck says nothing about
   dependencies.

Stop the lab first — `-Full` needs ports 8080/8000/5173 free for its
disposable cold-start stack, and a disposable project name cannot fix
host-level port conflicts. The runner detects whether the occupant is
this project's lab and prints the exact sequence; it never kills
anything.

```powershell
# Windows: stop the lab (keeps your data), run the full gate, restart
docker compose down
.\scripts\test-all.ps1 -Full -Strict
docker compose up -d
```

```powershell
# Windows: standalone Compose healthcheck proof (native wrapper —
# no host Bash or Python needed; stop the lab first, then restart).
# -WithDocker boots a DISPOSABLE cold-start project (unique name,
# ports preflighted first, scoped cleanup of only that project);
# -AgainstRunningProject inspects a RUNNING stack read-only
# (creates/deletes nothing — no up, no down, no reset).
docker compose down
.\scripts\test-compose-healthcheck.ps1 -WithDocker
docker compose up -d
# Read-only alternative (lab already running):
.\scripts\test-compose-healthcheck.ps1 -AgainstRunningProject
# Manual native Docker equivalent of the same three sub-proofs
# (no Bash, no Python — the full in-image probe command itself is
# inside the wrapper; health 200 alone is NOT login proof, see
# the five-proofs list above):
docker compose config | Select-String -Pattern healthcheck -Context 0,2
#   the resolved test: value must still contain the literal $resp
#   references (2x) and resp=$(cat <&3)
docker compose exec keycloak bash -c 'command -v bash grep; exec 3<>/dev/tcp/127.0.0.1/8080 && echo TCP_OK'
docker compose ps
docker inspect --format='{{.State.Health.Status}}' identityforge-keycloak-1
```

```bash
# Linux/macOS (or Git Bash on Windows — this block is Bash-only;
# on Windows without Bash, use the PowerShell blocks above):
# same workflow
docker compose down
./scripts/test-all.sh --full --strict
docker compose up -d
# Real Keycloak login + negatives only (lab running):
python3 scripts/live-gate.py all
# Disposable reset sub-gate (REAL_LAB_RESET; never part of `all`):
# The lab reset is destructive and runs only inside the disposable
# cold-start run (`scripts/test-all.sh --full` /
# `scripts/test-all.ps1 -Full`), which generates a fresh
# disposable-project marker per run. Never run
# `scripts/live-gate.py reset` by hand against a lab whose evidence
# you want to keep.
# In-container live-gate on the Compose bridge (host map env):
docker compose -f docker-compose.yml -f docker-compose.test.yml --profile test run --rm live-gate python3 /scripts/live-gate.py all
# Keycloak healthcheck in-image validation (stack running) — see below
# Compose healthcheck, resolved + live (v5, IF-V4-01; v7.2 IF-V7.1-02/03/04):
#   --with-docker boots a DISPOSABLE project with a unique name, but
#   ONLY after a preflight proves the fixed ports 8080/8000/5173 are
#   free. If a port is busy it fails fast with the stop/test/restart
#   sequence and never touches the occupant. For a RUNNING stack, use
#   the read-only mode instead — it creates/deletes nothing:
#   bash scripts/test-compose-healthcheck.sh --against-running-project
#   (Linux/macOS or an explicitly installed Bash environment only.
#   On Windows, the native equivalent is
#   .\scripts\test-compose-healthcheck.ps1 -WithDocker /
#   -AgainstRunningProject — see the PowerShell block above.)
bash scripts/test-compose-healthcheck.sh --with-docker
# Full npm audit (the sandbox proxy blocks the audit endpoint, so it is NOT RUN there).
# Prefer the JSON form so the result is classified, not pattern-matched:
cd frontend && npm audit --audit-level=high --json > ../test-results/audit-frontend.json
python3 ../scripts/npm-audit-classify.py --stdout ../test-results/audit-frontend.json
#   exit 0 CLEAN / 1 VULNERABILITIES_FOUND / 2 NOT RUN (blocked/DNS/timeout/rate-limit)
#   / 3 CHECK_FAILED (malformed output). The runners use this classifier;
#   a blocked endpoint is NOT RUN, never "vulnerabilities found".
# Playwright JSON report (v5, IF-V4-10): after a -Full run the report is at
# test-results/playwright-report.json (the E2E container mounts test-results/
# to the host). Validate it directly:
python3 scripts/validate-playwright-report.py --report test-results/playwright-report.json --target identityforge-coldstart-<timestamp-from-gates.json>
#   PASS requires the discovery-issuer + 3 real-login tests passed, the
#   counts (total/passed/failed/skipped/timedOut), and ONLY the documented
#   cancel skip. Note the screenshots run overwrites the same file, so the
#   E2E report above is the pre-screenshots evidence; the screenshots
#   report validates with --profile screenshots.
# Docker build-context check (v5, IF-V4-02): the .dockerignore files keep
# host node_modules / screenshots / test output out of the build context.
# Static proof (no Docker needed): python3 scripts/test-dockerignore.py
# (82 passed). With Docker, confirm the transfer stays small:
docker build -f frontend/Dockerfile -t identityforge-frontend-check frontend/
docker build -f backend/Dockerfile -t identityforge-backend-check backend/
#   (the build log's "transferring context" line must be a few MB, not
#   ~160 MB — the pre-fix context carried 6812 extra files / 158.3 MiB.)
```

`test-all --full --strict` fails if any required gate was skipped or
unavailable, and writes the machine-readable report to
`test-results/gates.json` (19 gates: 12 offline + 7 full, including
REAL_LAB_RESET, the DOCS_CONTRACT gate (v5, IF-V4-06), the two
v6 gates DOCS_CONTRACT_PATHS (IF-V5-01: the docs-contract check must
behave identically under a `data/` ancestor or a path with spaces)
and VERSION_CONTRACT (IF-V5-05: every authoritative version value
must equal the release version 1.8.5), and the v8.0.2 gate
LIVE_PROVIDER_PYTEST (IF-V8.0.2-B: the four provider-dependent pytest
tests, marked live_keycloak, run only in --full against the
cold-started disposable Keycloak). The docs-contract check fails
the run if a doc or example names a reason code or report field the
source does not define). On 8 GB, run it with other apps closed — the E2E
image plus Keycloak is the heaviest combination in the lab.

`--full --strict` fails CLOSED (exit 1) when a required gate is FAIL
or NOT RUN — including when the required full npm audit, the Docker
cold-start boot, the Playwright E2E run, the PowerShell execution, or
the Keycloak healthcheck is NOT RUN. A NOT RUN gate is never a pass:
it is a distinct status in `test-results/gates.json`, alongside PASS,
FAIL, and NOT APPLICABLE (see `docs/TEST_MATRIX.md` §5 and the status
vocabulary note in `scripts/test-all.sh`). "Skipped" is a word test
suites use for an individual check inside a suite; it is never a gate
status and never appears in `gates.json`.

GHSA status (P1-05): when the full npm audit executed (clean or with
findings), GHSA_DIRECT_FALLBACK is NOT APPLICABLE — the fallback did
not run, and a PASS there would be a phantom. The `gates.json`
summary carries all four keys (PASS, FAIL, NOT RUN, NOT APPLICABLE);
NOT APPLICABLE never counts as NOT RUN for strictness.

### Windows reviewer commands (PowerShell 5.1 AND 7)
Run each and record exit code + output:

```powershell
.\scripts\test-all.ps1 -Help                    # exits 0, prints the stop-first workflow
.\scripts\test-all.ps1 -Offline                 # offline gates in containers
.\scripts\test-all.ps1 -Full -Strict            # full gate (stop the lab first)
.\scripts\test-all.ps1 -Offline -Full           # usage error, exit 2
.\scripts\test-all.ps1 -BogusParam              # usage error, exit 2 (unknown argument)
# Missing Docker daemon: stop Docker Desktop, run -Full, expect exit 1 naming the daemon
# Occupied ports, lab running: boot the lab, run -Full, expect exit 1 + the stop-first sequence
# Occupied ports, other app: free the lab ports, start another listener on 8080, run -Full,
#   expect exit 1 + "do NOT belong to this project's lab" and no `down` being run
# Blocked audit endpoint: run -Offline with the npm registry unreachable; NPM_FULL is NOT RUN
#   and GHSA may run honestly — strict still fails on the missing full audit
# Failing test: break a test (or stub `docker build` to fail) and confirm the gate FAILs, exit 1
# Path with spaces: copy the extracted folder to e.g. `C:\Users\<you>\Identity Forge\`
#   and run -Help and -Full from there
```

### Keycloak healthcheck in-image probe (v5, IF-V4-01)
The healthcheck in `docker-compose.yml` (Keycloak service) runs bash
`/dev/tcp` + an HTTP discovery request and requires BOTH an HTTP 200
status line AND `"issuer"` in the body. **v5 fix:** the in-container
shell variable is written `$$resp`, NOT `$resp`. Docker Compose
interpolates `$VAR`/`${VAR}` in configuration values BEFORE the
container shell runs, so the v4 single-dollar form was replaced by an
empty string and the healthcheck inspected blank text — expected to
fail and, via `depends_on: keycloak: condition: service_healthy`,
block the backend and frontend from starting despite a healthy
Keycloak JVM. `$$` is Compose's escape for a literal dollar sign, so
the container shell receives the intended `resp=$(cat <&3)` /
`echo "$resp"`. Three regressions guard it: `scripts/compose-config-check.py`
simulates Compose interpolation and asserts the resolved command still
contains the literal `$resp` references, and
`scripts/test-compose-healthcheck.sh` inspects the RESOLVED command
via `docker compose config` and (with Docker) the live health state
(Linux/macOS or an explicitly installed Bash environment only; the
native Windows equivalent is
`scripts/test-compose-healthcheck.ps1`, v7.3, IF-V7.2-04 — same
checks, no host Bash or Python).
**v7.2 (IF-V7.1-02/03/04):** the script creates `test-results/`
before the first redirection into it (v7.1 redirected into a
directory that did not exist yet on a fresh extraction, so a shell
error was misreported as a Compose failure and `compose config`
never ran); the discovery document is now fetched with
`scripts/discovery-check.py` (stdlib `http.client` — never follows
redirects; parses Content-Length and chunked framing correctly and
requires HTTP 200 + a valid JSON object + the exact canonical
issuer), replacing the v7.1 raw-bytes `json.load` that failed on
every real response; and the cold-start boots a disposable project
with a unique name only after a preflight proves the fixed ports
8080/8000/5173 free (fail fast with the stop/test/restart sequence
if busy, never touching the occupant), with a read-only
`--against-running-project` mode for inspecting an existing stack.
**SOURCE FIXED; ACTUAL DOCKER HEALTHCHECK + COMPOSE BOOT NOT RUN** in
the build sandbox — the in-image run below is yours:

```powershell
# 0. Resolved-command check (the v5 regression — run it first).
#    Windows-native (no Bash/Python needed — stop the lab first):
.\scripts\test-compose-healthcheck.ps1 -WithDocker
#    Read-only alternative (lab already running):
#    .\scripts\test-compose-healthcheck.ps1 -AgainstRunningProject
```

```bash
# 0. Resolved-command check (the v5 regression — run it first).
#    Linux/macOS or an explicitly installed Bash environment only:
bash scripts/test-compose-healthcheck.sh --with-docker
#    The static part (runs without Docker) simulates Compose
#    interpolation and asserts the resolved healthcheck still contains
#    the literal `$resp` references (2x) and `resp=$(cat <&3)`; the
#    --with-docker part inspects the RESOLVED command via
#    `docker compose config`, boots the pinned container in a
#    DISPOSABLE project (unique name; ports preflighted first), and
#    checks the final health state + discovered issuer. Or, manually:
#    Read-only alternative (lab already running — creates/deletes
#    nothing, so no stop-first dance):
#    bash scripts/test-compose-healthcheck.sh --against-running-project
docker compose config | grep -A2 healthcheck
#    the resolved `test:` value must still contain the literal
#    `$resp` references (Compose shows them as `$$resp` in the file,
#    resolved to `$resp` for the container shell). If the resolved
#    command shows empty text where `$resp` should be, the
#    interpolation bug is back — do not boot, report it.
# 1. TCP reachability inside the image (already in this guide):
docker compose exec keycloak bash -c 'command -v bash grep; exec 3<>/dev/tcp/127.0.0.1/8080 && echo TCP_OK'
# 2. Full healthcheck command (copy the `test:` value from docker-compose.yml,
#    Keycloak service — single quotes inside must be escaped as '"'"' when
#    pasting into bash -c '...'):
docker compose exec keycloak bash -c 'exec 3<>/dev/tcp/127.0.0.1/8080 && printf '"'"'GET /realms/identityforge-lab/.well-known/openid-configuration HTTP/1.1\r\nHost: 127.0.0.1:8080\r\nConnection: close\r\n\r\n'"'"' >&3 && resp=$(cat <&3) && echo "$resp" | grep -qE '"'"'HTTP/1\.[01] 200'"'"' && echo "$resp" | grep -q '"'"'"issuer"'"'"' && echo HEALTHCHECK_OK'
# 3. Health state:
docker compose ps
docker inspect --format='{{.State.Health.Status}}' identityforge-keycloak-1
```

Healthy: `docker compose ps` shows keycloak `(healthy)` and the probe
prints `HEALTHCHECK_OK`; discovery returns
`"issuer": "http://127.0.0.1:8080/realms/identityforge-lab"`.
Unhealthy loop: keycloak stays `(health: starting)` then `(unhealthy)`
after the timer is exhausted (30 retries × 10 s interval + 20 s
start_period ≈ 360 s); the container stays up but unhealthy and the
portal reports Not ready. Clean volume: Keycloak takes 60–120 s on
first boot (realm import). Reused volume: faster (no import). IdP
outage (Keycloak down while the backend runs): the backend
`/api/v1/lab/status` reports `idp.reachable=false`, `doctor` FAILS,
and the portal shows Not ready — the lab must not be called ready.

## 8. If something goes wrong

| Symptom | Likely cause | Fix |
|---|---|---|
| `doctor.sh` fails on Keycloak | Still starting (first boot is slow) | Wait 60 s, re-run `./scripts/doctor.sh` |
| Login fails with an issuer error | Issuer mismatch (see `docs/AUTH_FLOW.md` §6) | Do **not** disable issuer checks; check that Keycloak started with the hostname-v2 full URLs `KC_HOSTNAME=http://127.0.0.1:8080` and `KC_HOSTNAME_ADMIN=http://127.0.0.1:8080` (Compose does this; see `docs/KEYCLOAK_INTEGRATION.md`) |
| Port already in use | Something else on 8000/5173/8080 | Stop the other service. Ports are fixed for this lab (P1-14) — do not change them in `.env`; a single-port change breaks login |
| Everything fails, Docker missing | Docker not installed | Follow `docs/WINDOWS_SETUP.md`; offline fixture tests still run without Docker (`./scripts/test-all.sh`) |
| `npm`/`python` errors in tests | Dependencies not installed | Backend: `pip install -r backend/requirements-freeze.txt` then `pip install -e .` in `backend/` (the CLI needs the local package installed; pytest alone does not); frontend: `cd frontend && npm ci` |

## 9. What to check in the code (if you have 5 more minutes)

- `docs/STANDARDS_TRACEABILITY.md` — each control mapped to its RFC,
  with the test that proves it.
- `docs/THREAT_MODEL.md` §5 — the flawed-fixture boundary (the most
  important design rule in the lab).
- `docs/VALIDATION_AND_LIMITATIONS.md` — what was actually run and what
  is still NOT RUN. If a claim elsewhere contradicts it, this file wins.
