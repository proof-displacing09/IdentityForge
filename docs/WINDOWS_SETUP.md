# Windows Setup — IdentityForge

> **P1-14 precision (v3): no Ubuntu *distro* is required — but the
> WSL 2 *feature* and BIOS virtualization ARE.** Docker Desktop on
> Windows runs its Linux engine on WSL 2. You do not need to install
> or use an Ubuntu (or any Linux) distribution yourself, and you do
> not need the WSL terminal for the lab — but if WSL 2 is disabled
> or virtualization is off in the BIOS/UEFI, Docker Desktop will not
> start. Check first: `wsl --status` in PowerShell (see §2).
>
> This guide assumes **Windows 11** with Docker Desktop. If you do not
> have Docker, the last section explains the offline-only fallback (no
> Docker, no Keycloak, real fixture tests only).

## 1. What you need

| Item | Minimum | Recommended | Why |
|---|---|---|---|
| Windows | Windows 11 (64-bit) | Windows 11, up to date | Docker Desktop requirement |
| Docker Desktop | Latest stable, with Compose v2 | Same | Runs Keycloak + the lab services |
| WSL 2 feature + BIOS virtualization | **Required** (Docker Desktop's engine) | Same | Without them Docker Desktop will not start; no Linux *distro* install is needed — check with `wsl --status` (§2) |
| RAM | 4 GB free for Docker | 8 GB total system RAM | Keycloak alone uses ~1–1.5 GB; see §4 — **8 GB is restrictive**: run gates serially, give Docker ≥4 GB, expect a slow first boot |
| Disk | 5 GB free | 10 GB free | Keycloak image ~1 GB, plus Python/Node images and caches |
| CPU | 2 cores | 4 cores | Keycloak startup is CPU-heavy for ~1 minute |
| Browser | Edge, Chrome, or Firefox (current) | Same | The lab UI and Keycloak login page |
| Internet | Required **during installation only** | — | Image and package downloads; afterwards the lab runs fully locally |
| Python / Node | Not required for the Docker path | Python 3.12 + Node 24 if you want to run tests outside Docker | The containers already contain the runtimes |
| PowerShell | Windows PowerShell 5.1 or PowerShell 7 | Same | `scripts/test-all.ps1` runs on both; if script execution is blocked, run `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser` once (§2) |

## 2. Install Docker Desktop

1. **Preflight — WSL 2 and virtualization.** In PowerShell, run
   `wsl --status`. It must report a WSL version (2) — if it says
   WSL is not installed or not enabled, enable it (Docker Desktop's
   installer usually does this; otherwise run
   `wsl --install --no-distribution` in an elevated PowerShell and
   restart). Plain `wsl --install` installs Ubuntu by default
   (Microsoft docs); `--no-distribution` installs only the WSL 2
   feature with no Linux distro, which is all Docker Desktop needs —
   it manages its own distros itself. If Docker
   Desktop later reports a virtualization error, enable
   virtualization in the BIOS/UEFI (Intel VT-x / AMD-V) — this is a
   firmware setting, not a Windows setting, and no Linux distro
   install is involved at any point.

Check WSL 2 without installing anything:

```
wsl --status            # must report a WSL version (2)
wsl --list --verbose    # shows Docker Desktop's own managed distros
                        # (e.g. docker-desktop) — do not remove them
```

Virtualization is a BIOS/UEFI setting (Intel VT-x / AMD-V), not a
Windows setting. No Linux distro install is involved at any point.
Lab-only cleanup: `docker compose down -v` in the extracted folder
removes lab containers and volumes only; it does not touch WSL or
Docker Desktop.
2. Download Docker Desktop for Windows from the official Docker website
   (docker.com — use the site's download page, not a third-party mirror).
3. Run the installer. Accept the defaults. When asked, keep the WSL 2
   backend enabled — Docker Desktop manages it itself; you do **not**
   need to install or use Ubuntu/WSL yourself.
4. Restart if prompted, then start Docker Desktop and wait until the
   Docker icon in the system tray says the engine is running.
5. **Preflight — ports free.** Before booting, check nothing else
   holds the lab's fixed ports:
   ```powershell
   Get-NetTCPConnection -LocalPort 8080,8000,5173 -State Listen -ErrorAction SilentlyContinue
   ```
   Any output means a conflicting service — stop it first. Ports are
   fixed (P1-14); do not change them.
6. **Execution policy (only if scripts are blocked).** If PowerShell
   refuses to run `.ps1` files ("running scripts is disabled on this
   system"), run once, as your own user (no admin needed):
   ```powershell
   Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
   ```
7. Verify in PowerShell:
   ```powershell
   docker --version
   docker compose version
   ```
   Both commands must print a version. If `docker compose` fails, update
   Docker Desktop — Compose v2 ships with it.

## 3. Install and start the lab

**Verify the archive first (v6, IF-V5-09).** Before extracting,
check the ZIP's SHA-256 against the hash in the delivery message —
a mismatch means the download is corrupt or not the delivered file;
do not run it:

```powershell
Get-FileHash .\IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V8.0.5_FINAL_20261114.zip -Algorithm SHA256
```

(Use the actual ZIP filename from the delivery message — the name
above is the v8.0.5 final release name. The docs-contract gate
(IF-V7.1-05) fails the run if a quickstart command names a
different archive.) The printed hash must equal the
delivery message's hash exactly.

**Extraction quirk (measured, v7 note):** extract with Info-ZIP
`unzip` — Python's `zipfile.extract` does NOT restore the stored
Unix executable bit, so `.sh` files come out 0660 instead of 0770.
After a Python-based extraction, run scripts as
`bash scripts/<name>.sh` instead of `./scripts/<name>.sh`, or
restore the bits with `chmod +x scripts/*.sh`. Either fallback is
fine; the dropped bit is an extraction-tool behaviour, explicitly
NOT an application defect — the scripts themselves are unchanged
and correct. (On Windows, use the built-in "Extract All" or
`Expand-Archive`, which preserve the bits.)

In PowerShell, from the extracted release folder (native PowerShell
wrappers — no Git Bash needed for these):

```powershell
.\scripts\setup.ps1     # checks Docker, copies .env, boots the lab
.\scripts\doctor.ps1    # health checks (Keycloak needs 60-120 s on first boot)
```

Or the same steps by hand:

```powershell
.\scripts\setup.ps1
docker compose config -q   # 5-second pre-flight: catches Compose errors before the ~1 GB download
docker compose up --build -d
.\scripts\doctor.ps1
```

The `.sh` helper scripts also still work from **Git Bash** (included
with Git for Windows). The `docker compose` commands themselves work
in PowerShell; only the `.sh` scripts need Bash.

Notes for Windows users:

- The main actions have native PowerShell wrappers: `setup.ps1`,
  `start.ps1`, `stop.ps1`, `reset.ps1`, `doctor.ps1` — run those in
  PowerShell. The `.sh` helper scripts need **Git Bash** (included
  with Git for Windows) or another explicitly installed Bash
  environment — not plain PowerShell/`cmd`, which cannot run `.sh`
  files. Docker Desktop's WSL 2 backend does **not** give you a Bash
  prompt and does **not** require installing Ubuntu or any WSL
  distribution: it manages its own distros itself. Do not reinstall
  Ubuntu, install a WSL distro, or unregister any WSL distribution
  for this lab — none of the Windows steps in this guide needs one.
  The `docker compose` commands themselves work in PowerShell; only
  the `.sh` scripts need Bash.
- If you do not have Git Bash, install **Git for Windows** (git-scm.com),
  which includes it, then right-click the lab folder → "Git Bash Here".
  You only need it if you choose to run a `.sh` script directly —
  every Windows step in this guide has a native PowerShell form.
- First boot downloads the Keycloak image (~1 GB) and takes 2–5 minutes
  on a typical connection. Keycloak then needs 60–120 seconds to start.
  `doctor.sh` will fail until then — wait and re-run it.
- **Do not** run Docker Desktop as Administrator unless your IT policy
  requires it, and do not share the lab's ports beyond your machine.

Then open: **http://127.0.0.1:5173**

Follow the walkthrough in `docs/REVIEWER_GUIDE.md`.

### Running the gates on Windows (v7.3)

The full gate runner has a native PowerShell version — no host
Python/Node needed (the gates run in containers):

```powershell
.\scripts\test-all.ps1                # offline gates in containers
.\scripts\test-all.ps1 -Full -Strict  # + disposable cold-start + real Keycloak login + browser E2E
```

**First and default Windows verification path (v7.3, IF-V7.2-04):**
stop your normal lab first (`docker compose down`, WITHOUT `-v`,
so your data is kept — the disposable project needs the fixed
ports 8080/8000/5173 free), run
`.\scripts\test-all.ps1 -Full -Strict`, then restart
(`docker compose up -d`). That one command is the mandatory gate.
Everything else in the checklists below is optional extra proof.
Do not assume Bash, a Linux environment, Python 3, or PyYAML is
available on the Windows host just because Docker Desktop works —
the Windows steps below need Docker Desktop only, unless a step
says otherwise in so many words.

#### Two-minute starter checklist (v7.3)

Do this first, before the long full gate. Every command below is
copied verbatim from `docs/REVIEWER_GUIDE.md` §7 — nothing here is
new syntax. If any step fails, stop and fix Docker before running
the full gate. (First run downloads the ~1 GB Keycloak image and
takes longer; the two minutes is the command time once the images
are built.)

- [ ] `.\scripts\test-all.ps1 -Help` — must exit 0 and print the
  stop-first workflow.
- [ ] `docker compose down` — stops the lab, keeps your data.
- [ ] `docker compose up -d` — restarts the lab.
- [ ] `.\scripts\test-all.ps1 -Offline` — offline gates in
  containers; the quick gate pass before the full one.

#### Longer Windows Docker test checklist (v7.3)

Work through these in order, recording the exit code and output of
each. Every command is copied verbatim from
`docs/REVIEWER_GUIDE.md` §7. A NOT RUN gate is never a pass, and
`-Full -Strict` fails CLOSED (exit 1) when any required gate is
FAIL or NOT RUN.

**Mandatory vs optional (v7.3, IF-V7.2-04).** Mandatory: stop the
lab, run `.\scripts\test-all.ps1 -Full -Strict`, restart. Optional
extra proof: the standalone healthcheck wrapper and the manual
Docker commands below. Heavy on 8 GB: the `-Full` run (Keycloak
~1–1.5 GB plus the E2E image ~1–1.5 GB; first boot 2–5 minutes,
then Keycloak needs 60–120 seconds to start) — run it with other
apps closed, serially. The standalone healthcheck wrapper is light
by comparison (one disposable cold-start stack, no E2E image).
Nothing here asks for a destructive bulk cleanup, an unrelated
volume deletion, or any publishing.

- [ ] Stop the lab, run the full gate, restart:
  `docker compose down`, then
  `.\scripts\test-all.ps1 -Full -Strict`, then
  `docker compose up -d`.
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
  IF-V7.2-04): **Windows-first, Docker Desktop only (NOT Git Bash,
  Ubuntu, host Python, or host Node).** Stop the lab first
  (`docker compose down` — WITHOUT `-v`), then run the native
  wrapper, then restart:
  `.\scripts\test-compose-healthcheck.ps1 -WithDocker`
  (disposable cold-start: fails fast if the fixed ports are busy;
  check them first with the §2 step-5 `Get-NetTCPConnection`
  command). For a RUNNING stack, the read-only mode
  creates/deletes nothing (no up, no down, no reset):
  `.\scripts\test-compose-healthcheck.ps1 -AgainstRunningProject`.
  Run it from a PowerShell prompt exactly as shown (or with
  `pwsh -File`); do NOT wrap it as
  `pwsh -Command "& { .\scripts\test-compose-healthcheck.ps1 ... }"` —
  that form swallows the script's exit code and always reports 0,
  even when the check failed (verified in Pass A on pwsh 7.4.6).
  The Bash form of the same check —
  `bash scripts/test-compose-healthcheck.sh --with-docker` /
  `--against-running-project` — is **Linux/macOS or an explicitly
  installed Bash environment only**; it is NOT required on Windows.
  Do not install Ubuntu or any WSL distribution for it: Docker
  Desktop's WSL 2 backend manages its own distros and does not
  require a user distro.
  Manual native Docker equivalent (no Bash, no Python — the full
  in-image probe command itself is inside the wrapper):
  `docker compose config | Select-String -Pattern healthcheck -Context 0,2`
  (the resolved `test:` value must still contain the literal
  `$resp` references, 2x, and `resp=$(cat <&3)`),
  `docker compose exec keycloak bash -c 'command -v bash grep; exec 3<>/dev/tcp/127.0.0.1/8080 && echo TCP_OK'`,
  `docker compose ps`, and
  `docker inspect --format='{{.State.Health.Status}}' identityforge-keycloak-1`.
  **Five separate proofs** (see `docs/REVIEWER_GUIDE.md` §7 — do not
  conflate them): Compose container health; the in-image shell
  probe; `/lab/status` canonical issuer validation
  (`idp.reachable=true` AND `idp.issuer_matches=true` for exactly
  `http://127.0.0.1:8080/realms/identityforge-lab`); successful
  student AND officer login + policy checks (only this proves the
  real login works — a health 200 alone proves none of it); and
  the full dependency audit.
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
- [ ] Docker build-context check: `docker build -f frontend/Dockerfile -t identityforge-frontend-check frontend/` and `docker build -f backend/Dockerfile -t identityforge-backend-check backend/` (the build log's "transferring context" line must be a few MB, not ~160 MB).
- [ ] Windows reviewer commands (PowerShell 5.1 AND 7):
  `.\scripts\test-all.ps1 -Help`, `.\scripts\test-all.ps1 -Offline`,
  `.\scripts\test-all.ps1 -Full -Strict`,
  `.\scripts\test-all.ps1 -Offline -Full` (usage error, exit 2),
  `.\scripts\test-all.ps1 -BogusParam` (usage error, exit 2), plus
  the missing-daemon, occupied-ports, blocked-audit-endpoint,
  failing-test and path-with-spaces cases in
  `docs/REVIEWER_GUIDE.md` §7.

Full gate: the `-Full` runner needs ports 8080/8000/5173 free for its
disposable cold-start stack. Stop the lab first (keeps your data),
run the test, then start the lab again:

```powershell
docker compose down
.\scripts\test-all.ps1 -Full -Strict
docker compose up -d
```

If the ports are busy, the runner refuses and prints the same
stop-first sequence instead of killing anything. See
`.\scripts\test-all.ps1 -Help` for the workflow.

It reports the same gate IDs and the same
`test-results\gates.json` schema as `test-all.sh` (see README) —
the v8.0.2 divergence is CLOSED in v8.0.3: `test-all.ps1` now
defines the same 19 gates (12 offline + 7 full) as `test-all.sh`,
its OFFLINE_UNIT runs the offline selection
`pytest -q -m "not live_keycloak"` inside the backend-test
container (which has no IdP), and the full-profile gate
LIVE_PROVIDER_PYTEST (IF-V8.0.2-B: the four provider-dependent pytest
tests, marked live_keycloak, run only in -Full against the
cold-started disposable Keycloak) is present in both runners.
The ps1 -Full live run executes the four tests inside the
backend-test container with a loopback forwarder to the disposable
Keycloak (see the LIVE_PROVIDER_PYTEST header note in
`scripts/test-all.ps1`; the offline/live split is 516/4 by
collect-only, measured by WS2 in this round). The stale VERSION_CONTRACT label
("1.7.3") was fixed in v8.0.3 and now reads the release version 1.8.5.
Windows PowerShell 5.1 execution of the fixed runner remains NOT RUN
(5.1 is Windows-only) — the reviewer gate.
(v6: DOCS_CONTRACT_PATHS — the docs-contract check must behave
identically under a `data/` ancestor or a path with spaces — and
VERSION_CONTRACT — every authoritative version value must equal the
release version 1.8.5 — join DOCS_CONTRACT as offline gates.
`-Full -Strict` fails CLOSED (exit 1) when any required gate is FAIL
or NOT RUN — including when the required full npm audit, the Docker
cold-start boot, the Playwright E2E run, the PowerShell execution,
or the Keycloak healthcheck is NOT RUN. A NOT RUN gate is never a
pass: it is a distinct status in `gates.json`, alongside PASS, FAIL,
and NOT APPLICABLE. "Skipped" is a word test suites use for an
individual check inside a suite; it is never a gate status.)
**PowerShell execution of `test-all.ps1` was run in the build
sandbox under PowerShell 7.4.6 on Linux** (preflight / help /
argument / ports paths with a stub `docker` — see
`scripts/test-ps1-preflight.sh`, 20 passed, 0 failed, 1 skipped
— re-measured in the v7.1 battery, 2026-11-12 ~02:17 UTC); the
native healthcheck wrapper `scripts/test-compose-healthcheck.ps1`
was likewise executed there under 7.4.6 on Linux with a stub
`docker` (v7.3: 13 checks + a path-with-spaces run, all passing —
see `docs/VERIFICATION_LOG.md`). **Windows
PowerShell 5.1 execution remains NOT RUN** (5.1 is Windows-only),
so running it on Windows 5.1 is still the reviewer's gate. On 8 GB,
run gates serially — the runner already does — and do not run other
heavy apps during `-Full`: the E2E image (~1–1.5 GB) plus Keycloak
(~1 GB) plus Docker itself is the heaviest combination in the lab.

#### Docker Desktop acceptance — IF-V8-42 non-root images (v8.0.5)

Audience: the owner on an 8 GB Windows laptop, Docker Desktop
installed. NON-DESTRUCTIVE throughout: never delete a volume, never
`down -v` against the real lab, never reset against the owner's main
DB/volumes. The existing-volume migration is exercised FIRST on a
disposable copy.

**0. Before you start — safety rules (read once)**

- Work ONLY inside a fresh extraction of the v8.0.5 ZIP. Keep your
  existing lab folder and its volumes untouched until step 5 passes.
- Never run `docker compose down -v` except inside a disposable
  project (steps 2–4 use `-p <disposable-name>` for exactly this).
- If any step fails, STOP, copy the exact error text, and do not
  "fix" it by deleting volumes, running as Administrator, or
  editing files. A failed step is a result, not a mess to clean up.
- Close other heavy apps first: Keycloak (~1 GB) + Chromium (~1 GB)
  + the app containers share your 8 GB.

**1. Extract and verify**

1. Extract the v8.0.5 ZIP to a NEW folder, e.g.
   `C:\Users\<you>\Downloads\identityforge-v805\`.
2. In PowerShell, `cd` into that folder and check the hash the
   delivery message gives for the ZIP matches the file you
   downloaded.
3. Confirm Docker Desktop is running: `docker compose version`
   prints a version, and `docker info` succeeds.

**2. Disposable cold-start boot (fresh volume)**

1. `docker compose -p identityforge-v805-check up --build -d`
   (first build takes several minutes; Keycloak needs 60–120 s
   on first boot — wait for it, do not Ctrl-C).
2. `.\scripts\doctor.ps1` — expect READY for Keycloak, backend,
   frontend (all three).
3. Record the exact READY lines.

**3. Prove the app runs as non-root (checklist item 2)**

1. `docker compose -p identityforge-v805-check exec backend id`
   — expect `uid=10001(identityforge) gid=10001(identityforge)`,
   NOT `uid=0(root)`.
2. `docker compose -p identityforge-v805-check exec frontend id`
   — expect the same `uid=10001(identityforge)`.
3. The `backend-data-prep` service has already exited; check its
   log instead:
   `docker compose -p identityforge-v805-check logs backend-data-prep`
   must show `prepare-data-volume: prepared /app/data for
   10001:10001`, and the service must show `Exited (0)` in
   `docker compose -p identityforge-v805-check ps -a`.
4. Also confirm NO app Dockerfile contains `USER root`:
   `Select-String -Pattern '^USER root' backend/Dockerfile,
   frontend/Dockerfile, frontend/Dockerfile.e2e` — expect no matches.

**4. Fresh-volume regression (checklist item 4)**

1. In the portal (http://127.0.0.1:5173), log in as `student_01`,
   run one scenario, and confirm it saves (the run appears under
   Reports / evidence). Log out.
2. `python scripts/live-gate.py all` — expect `101/101`
   (or run `.\scripts\test-all.ps1 -Full -Strict` — see step 6).
3. `docker compose -p identityforge-v805-check down -v`
   (DISPOSABLE project only — this deletes the disposable volume).
4. Repeat steps 2.1–2.2 from scratch: boot must succeed again and
   the live gate must pass on the clean volume.

**5. Existing-volume migration (checklist item 3) — disposable copy FIRST**

Do NOT test this against your real lab volume first. The trick is
the project name: a Compose volume is named
`<project>_backend_data`, so booting the SAME `-p` project name
from two different folders reuses the same volume. That is how the
disposable copy below carries a real root-owned DB into the v8.0.5
tree without touching your lab.

1. Extract the v8.0.4 ZIP to a separate folder, e.g.
   `C:\Users\<you>\Downloads\identityforge-v804\`, and `cd` into
   it. Boot the disposable project from the CURRENT release:
   `docker compose -p identityforge-mig-check up --build -d`
   (wait for doctor READY).
2. Confirm the volume holds a root-owned DB: 
   `docker compose -p identityforge-mig-check exec backend id`
   must show `uid=0(root)`. Log in as `student_01`, run one
   scenario, confirm it saves, and note the run count (Reports /
   evidence, or `GET /api/v1/lab/counts`).
3. Stop it WITHOUT deleting the volume:
   `docker compose -p identityforge-mig-check down`
   (no `-v` — the `identityforge-mig-check_backend_data` volume
   stays, holding the root-owned DB).
4. Now `cd` into the v8.0.5 folder and start the SAME disposable
   project name from the v8.0.5 tree:
   `docker compose -p identityforge-mig-check up --build -d`.
5. Watch the prep service:
   `docker compose -p identityforge-mig-check logs backend-data-prep`
   must show the `prepared /app/data for 10001:10001` line, and the
   backend must reach healthy (`.\scripts\doctor.ps1` READY).
6. Log in as `student_01` AND `officer_01`, run a scenario, save
   evidence, and confirm no `Permission denied` appears in
   `docker compose -p identityforge-mig-check logs backend` or
   `... frontend`.
7. Confirm the old evidence is still there: the run counts in the
   portal (or `GET /api/v1/lab/counts`) must include the runs from
   before the upgrade — the migration repairs ownership, it never
   deletes or replaces the DB.
8. Tear the disposable project down (only now that 5.1–5.7 pass):
   `docker compose -p identityforge-mig-check down -v`
   (DISPOSABLE project only).
9. Only when 5.1–5.8 pass on the disposable copy, repeat the same
   upgrade against your real lab folder
   (`docker compose up --build -d` there), and check the same three
   things (prep log line, logins + evidence save, old runs still
   present).
10. If the prep service ever exits non-zero, the backend will NOT
    start — that is the fail-closed design working. Read
    `docker compose logs backend-data-prep` for the precise reason
    (e.g. corrupt DB, a file where the directory belongs) and
    report it; do not delete the volume to "fix" it.

**6. Full gate run (one command)**

1. `.\scripts\test-all.ps1 -Full -Strict` — expect exit 0, 19 gates
   in `test-results\gates.json`, and `LIVE_PROVIDER_PYTEST` PASS
   with `4 passed` in `test-results\live-provider-pytest.log`.
2. This also runs the browser E2E (Playwright) as the non-root user.
   If E2E fails at the entrypoint with a "not writable by UID
   10001" message about the screenshots/report folders, pre-create
   them first (`mkdir test-results\e2e-screenshots` in the
   extracted folder) and re-run — and report it, because that
   tells us the bind-mount ownership needs a docs fix.

**7. What to record for closing IF-V8-42**

- The `id` output for backend and frontend (uid 10001).
- The `doctor READY` lines and the prep-service `prepared` line.
- The live-gate count (101/101) and the reset count (69/69).
- Confirmation that pre-upgrade runs survived the migration.
- The `test-all.ps1 -Full -Strict` exit code and gate count (19).
- Any step that failed, with its exact error text.

Known non-proofs in the v8.0.5 sandbox (do not mistake for passes)

- Docker image build, Compose boot, in-container `id`, volume
  migration, and browser E2E were NOT RUN in the build sandbox
  (no Docker there). The steps above are the first real execution.
- Windows PowerShell 5.1 execution itself is a reviewer gate:
  run the commands in Windows PowerShell 5.1 (not only pwsh 7).

## 4. RAM: the honest numbers

- Keycloak (Java/Quarkus) is the heavy service: expect roughly 1–1.5 GB
  of RAM while running, with a startup spike.
- Backend + frontend together: a few hundred MB.
- **8 GB total system RAM: restrictive, not comfortable.** Give Docker
  Desktop at least 4 GB in Settings → Resources, run gates one at a
  time (the runners already run sequentially — do not parallelise
  them), close other applications, and expect a slow first boot.
  Keycloak needs 60–120 seconds on first boot; `doctor.ps1` will
  fail until then — wait and re-run it.
- **4 GB total system RAM: tight but possible.** Give Docker Desktop
  2.5–3 GB, close other applications, and expect a slow first boot.
  If Keycloak fails to start or is killed, use the fallback below.

### Lower-RAM fallback (no Docker, offline fixtures only)

If your machine cannot run Keycloak, you can still run the honest core
of the lab — the deterministic offline fixture suite — with only Python:

```powershell
# Install Python 3.12 from python.org, then:
cd backend
pip install -r requirements-freeze.txt
pip install -e .   # installs the local identityforge package itself;
                   # without this, `python -m identityforge.cli` fails
                   # with ModuleNotFoundError (pytest works without it
                   # because pytest.ini sets pythonpath = src)
python -m pytest -q
python -m identityforge.cli verify-all
```

This exercises the real validators (state, PKCE, issuer, audience,
signature, expiry, sessions, authorization) against local fixtures.
What it does **not** do: the real browser login against Keycloak. That
gate stays **NOT RUN** until you have a machine with Docker — say so in
any report, and do not present fixture results as Keycloak results.

## 5. Stopping, resetting, and cleaning up

**Four different things (v6, IF-V5-08) — do not confuse them.**
"Deleting lab data" means four different actions; see
`docs/EVIDENCE_RETENTION.md` for the full distinction. In short:

- **Stop** (`docker compose down`, `.\scripts\stop.ps1`) — stops the
  containers and **keeps your data and volumes**. Nothing is deleted.
- **Manual full reset, in-app** (Lab Settings, officer-only) —
  clears all stored evidence, sessions and transactions at once.
  Requires an officer session + CSRF + two confirmations. It does
  NOT touch Keycloak or its volume. "Old evidence is automatically
  pruned at capacity; manual full reset requires an officer session
  + CSRF + two confirmations."
- **Automatic pruning** — the store itself drops only the OLDEST
  evidence past a published cap (1000 runs / 20000 events / 1000
  live-login events), one save at a time. Nobody invokes it; export
  anything you still need before the store fills.
- **Volume deletion** (`docker compose down -v`,
  `.\scripts\reset.ps1 -Confirm`) — deletes the evidence database
  AND the Keycloak realm data on the host. This is a HOST action:
  no officer session or CSRF gates it, and nothing is kept. Only
  run it when you have deliberately decided the evidence can go.

In PowerShell (native wrappers — no Git Bash needed):

```powershell
.\scripts\stop.ps1              # stop, keep synthetic data and volumes
.\scripts\reset.ps1 -Confirm    # DELETE the volumes: evidence DB + Keycloak realm data (re-imported on next start; recorded evidence is gone)
docker compose down -v          # same as reset, via Compose directly
```

The same actions from Git Bash:

```bash
./scripts/stop.sh            # stop, keep synthetic data and volumes
./scripts/reset.sh --confirm # DELETE the volumes: evidence DB + Keycloak realm data
```

To remove the downloaded images as well (frees ~2 GB) — lab-scoped
only, so it touches nothing outside this lab:

```powershell
docker compose down -v --rmi local
```

**Do NOT run image/volume cleanup beyond the lab without deciding
it explicitly.** Commands such as `docker system prune` or
`docker image prune -a` delete Docker data machine-wide — every
unused image and volume, not just this lab's — and
`wsl --unregister` deletes a whole WSL distribution. This guide
never asks you to run them: if you are out of disk, prefer the
lab-scoped `docker compose down -v --rmi local` above, and only run
a machine-wide prune after you have checked what it will delete
(`docker system df`) and decided, yourself, that the loss is
acceptable. Never run a machine-wide prune or unregister a WSL
distribution on a suggestion alone.

## 6. Troubleshooting (Windows)

| Symptom | Fix |
|---|---|
| `wsl --status` says WSL is not installed / not enabled | WSL 2 feature off | Run `wsl --install --no-distribution` in an elevated PowerShell, restart, re-run `wsl --status` |
| Docker Desktop reports a virtualization error | Virtualization off in BIOS/UEFI | Enable Intel VT-x / AMD-V in the firmware settings, then restart; no Linux distro install is needed |
| PowerShell refuses to run `.ps1` files | Execution policy | `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser` (once, as your user) |
| `docker: command not found` in PowerShell | Docker Desktop is not running, or its CLI is not on PATH — restart Docker Desktop, then open a new PowerShell window |
| `docker compose` fails | Update Docker Desktop; Compose v2 is bundled with recent versions |
| Port 8080/8000/5173 already in use | Stop the conflicting app. Ports are fixed for this lab (P1-14) — do not change them in `.env`; a single-port change breaks login |
| Keycloak container exits immediately | Usually out of memory — increase Docker Desktop's memory in Settings → Resources, or use the §4 fallback |
| Keycloak stays `(unhealthy)` but the discovery URL returns 200 in a browser | The healthcheck probe is not seeing the response — first check the resolved command: `docker compose config \| grep -A2 healthcheck` must still show the literal `$resp` references (v5, IF-V4-01: the Compose file writes `$$resp`; a resolved command with empty text where `$resp` should be means the interpolation bug is back — do not edit the file further, report it). Otherwise run `docker compose ps` and `docker compose logs keycloak`, then report the exact output to Muse rather than editing the Compose file further. The healthcheck already uses the explicit `bash -c` form (see `docs/KEYCLOAK_INTEGRATION.md`) |
| `.sh` script "cannot be executed" | Run it from Git Bash, not PowerShell — or use the native `.ps1` equivalent where one exists (`test-compose-healthcheck.ps1` for the healthcheck); `.sh` files are Linux/macOS-or-Bash-only, never a reason to install Ubuntu or a WSL distro |
| Files show a `Zone.Identifier` sidecar | Windows marks downloaded files; the release `.gitignore` excludes these, and they are harmless — delete them if they bother you |
| Very slow first boot | Normal: image download + Keycloak startup. Wait, then re-run `./scripts/doctor.sh` |

## 7. Linux quick reference (for completeness)

```bash
# Docker Engine + Compose v2 installed per docs.docker.com
./scripts/setup.sh
docker compose up --build -d
./scripts/doctor.sh
# Open http://127.0.0.1:5173
```

The Linux path is identical apart from installation; the lab itself is
the same Compose file, realm, and scripts.
