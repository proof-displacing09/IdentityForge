#!/usr/bin/env bash
# IdentityForge test-all — the honest gate runner (P0-03).
#
# Explicit gates (each reports PASS / FAIL / NOT RUN with a timestamp):
#   OFFLINE_UNIT, OFFLINE_SCENARIOS, DOCS_CONTRACT, DOCS_CONTRACT_PATHS,
#   VERSION_CONTRACT, FRONTEND_TYPECHECK,
#   FRONTEND_UNIT, FRONTEND_BUILD, PYTHON_DEPENDENCY_AUDIT,
#   NPM_FULL_LOCKFILE_AUDIT, GHSA_DIRECT_FALLBACK, COMPOSE_CONFIG,
#   CLEAN_COMPOSE_BUILD_BOOT, LIVE_PROVIDER_PYTEST, REAL_KEYCLOAK_LOGIN,
#   REAL_SECURITY_NEGATIVES, REAL_LAB_RESET, PLAYWRIGHT_E2E, RESPONSIVE_QA
# (19 gates: 12 offline + 7 full. DOCS_CONTRACT is new in v5, IF-V4-06;
# DOCS_CONTRACT_PATHS + VERSION_CONTRACT are new in v6, IF-V5-01/05;
# LIVE_PROVIDER_PYTEST is new in v8.0.2, IF-V8.0.2-B: the four
# provider-dependent pytest tests, marked live_keycloak, run only in
# --full against the cold-started disposable Keycloak.)
#
# Status vocabulary (IF-V5-10, v6): a gate's status in
# test-results/gates.json is exactly one of PASS / FAIL / NOT RUN /
# NOT APPLICABLE. NOT RUN means the gate did not execute (tool absent,
# profile did not ask for it, prerequisite failed) — it is never a
# pass, never "skipped", and never interchangeable with NOT
# APPLICABLE (the gate was superseded by a covering gate, P1-05) or
# with FAIL (the gate ran and its check did not hold). "Skipped" is a
# word test suites use internally for an individual check inside a
# suite (e.g. the ps1-preflight counts); it is NEVER a gate status
# and never appears in gates.json. A --full or --strict run fails
# closed (exit 1) when any required gate is FAIL or NOT RUN.
#
# P0-03 (v4): --full needs ports 8080/8000/5173 free for its disposable
# cold-start stack. If they are busy, the preflight below detects
# whether the occupant is this project's lab and prints the exact
# stop -> test -> restart sequence; it never kills anything. Workflow:
# docker compose up -d (review) -> docker compose down (stop, keeps
# data) -> ./scripts/test-all.sh --full --strict -> docker compose up -d.
#
# Dependency gates (P0-03) are deliberately separate — the GHSA direct
# fallback NEVER satisfies the full npm audit:
#   PYTHON_DEPENDENCY_AUDIT  pip-audit over the pinned runtime set.
#   NPM_FULL_LOCKFILE_AUDIT  `npm audit` over the resolved lockfile tree.
#   GHSA_DIRECT_FALLBACK     informational GHSA check, DIRECT deps only.
#     Runs only when the full npm audit could not execute; a clean
#     fallback leaves NPM_FULL_LOCKFILE_AUDIT NOT RUN, and a strict
#     run then FAILS CLOSED. When the full audit executed (clean or
#     with findings), the fallback is NOT APPLICABLE — it did not run,
#     and a PASS there would be a phantom (P1-05, v4). NOT APPLICABLE
#     is a distinct status: it never counts as NOT RUN for strictness,
#     because the gate was superseded, not skipped.
#
# Profiles:
#   --offline (default)  offline gates are required; live gates are
#                        reported NOT RUN and the banner says so.
#   --full               every gate is required; any FAIL or NOT RUN
#                        fails the run (with or without --strict).
#   --strict             additionally fail if any gate REQUIRED BY the
#                        profile was NOT RUN (a required gate that was
#                        skipped/unavailable fails the run).
#   --with-keycloak      legacy alias for --full.
#
# Results are written machine-readable to test-results/gates.json and
# printed as a human table. A green run never implies a gate that was
# NOT RUN: the summary lists every NOT RUN gate by name.
#
#   ./scripts/test-all.sh                      # offline profile
#   ./scripts/test-all.sh --full --strict      # full release gate
set -uo pipefail

cd "$(dirname "$0")/.."

PROFILE=offline
STRICT=0
for arg in "$@"; do
  case "$arg" in
    --offline) PROFILE=offline ;;
    --full) PROFILE=full ;;
    --with-keycloak) PROFILE=full ;;  # legacy alias
    --strict) STRICT=1 ;;
    --help|-h)
      echo "Usage: $0 [--offline|--full] [--strict] [--with-keycloak]"
      exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

mkdir -p test-results
RESULTS_TSV="test-results/gates.tsv"
: > "$RESULTS_TSV"
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# --- P0-03 stop-first preflight (only for --full) ---------------------------
# Runs BEFORE any gate, so a busy port fails fast with the exact
# stop -> test -> restart sequence instead of a bare error after
# minutes of offline testing. A disposable Compose project name
# cannot fix HOST-level port conflicts. Never kills anything; only
# prints instructions. Skipped when Docker is absent OR non-functional
# (same availability test as the --full block below: `docker compose
# version` must succeed) — in that case the --full block records
# every live gate NOT RUN, which is the honest result for a missing
# daemon, not a port error.
if [ "$PROFILE" = "full" ] && command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  busy=""
  for port in 8080 8000 5173; do
    if (exec 3<>/dev/tcp/127.0.0.1/$port) 2>/dev/null; then
      busy="$busy $port"
    fi
  done
  if [ -n "$busy" ]; then
    # Detect whether the occupant is this project's lab: running
    # containers in this folder's default Compose project.
    project_running=""
    if command -v python3 >/dev/null 2>&1; then
      project_running="$(docker compose ps --format json 2>/dev/null | python3 -c '
import json, sys
names = []
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        c = json.loads(line)
    except ValueError:
        continue
    if c.get("State") == "running":
        names.append(c.get("Service") + " (" + c.get("Name") + ")")
print(", ".join(names))' 2>/dev/null)"
    elif docker compose ps --format json 2>/dev/null | grep -qE '"State": ?"running"'; then
      project_running="(running containers found — names unavailable without python3)"
    fi
    echo "ERROR: ports${busy} are already in use — the cold-start gate publishes 8080/8000/5173." >&2
    if [ -n "$project_running" ]; then
      echo "These ports belong to the IdentityForge lab in this folder ($project_running)." >&2
      echo "A disposable test project cannot share host ports with the running lab." >&2
      echo "" >&2
      echo "Stop the main lab first (keeps your data and volumes):" >&2
      echo "    docker compose down" >&2
      echo "" >&2
      echo "Then re-run this test:" >&2
      echo "    ./scripts/test-all.sh --full --strict" >&2
      echo "" >&2
      echo "When the test finishes, start the lab again:" >&2
      echo "    docker compose up -d" >&2
      echo "" >&2
      echo "Nothing was stopped or deleted by this check — run the commands above yourself." >&2
    else
      echo "These ports do NOT belong to this project's lab (no running IdentityForge containers found in this folder)." >&2
      echo "Free the ports first — stop whatever is using${busy} — then re-run this test." >&2
      echo "This script never kills other processes or containers for you." >&2
    fi
    exit 1
  fi
  echo "OK   Ports 8080/8000/5173 free"
fi

# gate <id> <required_by: offline|full> <label> — runs "$@" as the check.
# Set GATE_DETAIL before calling to record a one-line provenance note
# (e.g. which fallback actually ran) in the machine-readable report.
GATE_DETAIL=""
gate() {
  local id="$1" required_by="$2" label="$3"; shift 3
  echo
  echo "===== [$id] $label (required by: $required_by) ====="
  local at
  at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if "$@"; then
    echo "PASS: $id"
    printf '%s\t%s\tPASS\t%s\t%s\n' "$id" "$required_by" "$at" "$GATE_DETAIL" >> "$RESULTS_TSV"
  else
    echo "FAIL: $id"
    printf '%s\t%s\tFAIL\t%s\t%s\n' "$id" "$required_by" "$at" "$GATE_DETAIL" >> "$RESULTS_TSV"
  fi
  GATE_DETAIL=""
}

# skip_gate <id> <required_by> <label> <reason>
skip_gate() {
  local id="$1" required_by="$2" label="$3" reason="$4"
  echo
  echo "===== [$id] $label (required by: $required_by) ====="
  echo "NOT RUN: $id — $reason"
  printf '%s\t%s\tNOT RUN\t%s\t%s\n' "$id" "$required_by" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$reason" >> "$RESULTS_TSV"
}

# na_gate <id> <required_by> <label> <reason>
# Records status NOT APPLICABLE: the gate did not run because a
# superseding gate already covered it (P1-05: GHSA fallback when the
# full npm audit executed). NOT APPLICABLE is not a failure to run and
# never counts toward required NOT RUN in the strictness check below.
na_gate() {
  local id="$1" required_by="$2" label="$3" reason="$4"
  echo
  echo "===== [$id] $label (required by: $required_by) ====="
  echo "NOT APPLICABLE: $id — $reason"
  printf '%s\t%s\tNOT APPLICABLE\t%s\t%s\n' "$id" "$required_by" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$reason" >> "$RESULTS_TSV"
}

# --- Backend venv (offline fixtures need the pinned deps) -----------------
if [ -x .venv/Scripts/python.exe ]; then
  PY=.venv/Scripts/python.exe
  PIP=.venv/Scripts/pip.exe
elif [ -x .venv/bin/python ]; then
  PY=.venv/bin/python
  PIP=.venv/bin/pip
else
  echo "Creating .venv and installing backend/requirements.txt ..."
  python3 -m venv .venv
  if [ -x .venv/Scripts/python.exe ]; then PY=.venv/Scripts/python.exe; PIP=.venv/Scripts/pip.exe;
  else PY=.venv/bin/python; PIP=.venv/bin/pip; fi
  "$PIP" install -q -r backend/requirements.txt
  "$PIP" install -q -e backend
fi

# --- Offline gates (required by both profiles) ----------------------------
# IF-V8.0.2-B (v8.0.2): OFFLINE_UNIT runs the OFFLINE selection only
# (`-m "not live_keycloak"`). The four provider-dependent pytest tests
# (marked live_keycloak in backend/tests/adversarial/test_ws1_v8_oidc.py)
# need a live Keycloak and fail with 503 PROVIDER_UNAVAILABLE without
# one, so an unfiltered run here mislabels a missing provider as a
# product failure. They run in --full only, gate LIVE_PROVIDER_PYTEST.
gate OFFLINE_UNIT offline "backend: ruff lint + format + pytest (offline selection, -m \"not live_keycloak\")" bash -c \
  "cd backend && ../$PY -m ruff check src tests && ../$PY -m ruff format --check src tests && ../$PY -m pytest -q -m \"not live_keycloak\""
gate OFFLINE_SCENARIOS offline "backend: scenario CLI verify-all (offline)" bash -c \
  "cd backend && ../$PY -m identityforge.cli verify-all"
# IF-V4-06 (v5): docs-contract — every reason code / report field named
# in the docs, example reports and UI copy must be exactly what the
# source defines. Stdlib-only python3; no venv, Docker or network.
gate DOCS_CONTRACT offline "docs: reason codes + report fields match source" python3 scripts/validate-docs-contract.py
# IF-V5-01 (v6): docs-contract path independence — the checker must
# behave identically when the tree is checked out under a `data/`
# ancestor or a path with spaces (v5 failed with 104 false violations
# under a `data/` ancestor). Fixture-based regression: clean docs
# PASS + stale-code / below-root-exclusion / symlink-escape /
# empty-scan negatives in all three paths (15 checks).
gate DOCS_CONTRACT_PATHS offline "docs-contract: path-independent (normal / data ancestor / spaces)" bash scripts/test-docs-contract-paths.sh
# IF-V5-05 (v6): version contract — every authoritative version value
# (release manifest, backend pyproject + __init__ + FastAPI + health,
# frontend package.json + lockfile; UI reads the version from the
# health endpoint) must equal the release version 1.8.5. Fails until
# the owning sources are bumped together; see
# scripts/check-version-contract.py.
gate VERSION_CONTRACT offline "release version 1.8.5 agrees everywhere (manifest, backend, frontend, health)" python3 scripts/check-version-contract.py

if [ -d frontend ] && [ ! -d frontend/node_modules ]; then
  echo "Installing frontend dependencies (npm ci) ..."
  (cd frontend && npm ci)
fi
if [ -d frontend ] && [ -f frontend/package.json ]; then
  gate FRONTEND_TYPECHECK offline "frontend: typecheck" bash -c 'cd frontend && npm run typecheck'
  gate FRONTEND_UNIT offline "frontend: unit/component tests" bash -c 'cd frontend && npm test -- --run'
  gate FRONTEND_BUILD offline "frontend: production build" bash -c 'cd frontend && npm run build'
else
  skip_gate FRONTEND_TYPECHECK offline "frontend: typecheck" "frontend/ or package.json missing"
  skip_gate FRONTEND_UNIT offline "frontend: unit/component tests" "frontend/ or package.json missing"
  skip_gate FRONTEND_BUILD offline "frontend: production build" "frontend/ or package.json missing"
fi

# --- Dependency audits: three separate gates (P0-03) -----------------------
# Implemented in scripts/audit-gates.sh (sourced below): the same three
# gates and exit-code contract are unit-driven by
# scripts/test-dependency-gates.sh with fake npm/pip-audit on PATH.
# shellcheck source=scripts/audit-gates.sh
source scripts/audit-gates.sh
run_dependency_gates

# --- Compose config (static; required by both profiles) --------------------
# With Docker: the real `docker compose config -q` PLUS the resolved
# config inspection (IF-V4-01, v5): the resolved Keycloak healthcheck
# must still contain the literal '$resp' (2x) and 'resp=$(cat <&3)' —
# if Compose had interpolated a single-dollar '$resp' away, the
# resolved text would show empty 'echo ""' instead. The YAML-only
# fallback (scripts/compose-config-check.py) performs the same
# resolved-healthcheck simulation when no Docker CLI exists.
# Without a Docker CLI (e.g. this sandbox): a YAML parse + locked-port
# invariant check. That fallback is labelled in the gate detail — it
# is NOT a substitute for `docker compose config`, and
# CLEAN_COMPOSE_BUILD_BOOT still requires Docker.
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  check_compose_config_resolved() {
    # Parse Compose's rendered model instead of grepping serialized YAML.
    # Modern Compose may re-escape literal $ as $$ when displaying config,
    # so searching rendered text for resp=$(cat ...) gives a false negative.
    # Do not persist rendered config: it contains expanded private values.
    docker compose config -q || return 1
    docker compose config --format json | python3 scripts/check-compose-resolved.py
  }
  GATE_DETAIL="resolved healthcheck keeps literal '\$resp' (IF-V4-01)"
  gate COMPOSE_CONFIG offline "docker compose config validates (resolved healthcheck keeps literal '\$resp')" check_compose_config_resolved
elif python3 -c "import yaml" >/dev/null 2>&1; then
  echo "Docker CLI unavailable — validating the compose file as YAML plus"
  echo "locked-port invariants (docker compose config NOT RUN here)."
  GATE_DETAIL="YAML-only validation (no Docker CLI); docker compose config NOT RUN here"
  gate COMPOSE_CONFIG offline "compose file validates (YAML-only fallback — no Docker CLI)" python3 scripts/compose-config-check.py
else
  skip_gate COMPOSE_CONFIG offline "docker compose config validates" "Docker CLI unavailable and no PyYAML for the fallback check"
fi

# --- Live gates (required only by --full) ----------------------------------
# P1-13: a health check of already-running containers is NOT a
# cold-start proof. --full always boots a DISPOSABLE project namespace
# from a fresh build, runs the live gates against it, and tears it
# down (down -v) — never touching the user's own stack or volumes
# (the Compose file sets no fixed container_name, so the disposable
# namespace cannot collide with a running lab). If Docker is absent,
# every live gate is NOT RUN, never PASS.
if [ "$PROFILE" = "full" ]; then
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    COLD_PROJECT="identityforge-coldstart-$(date -u +%Y%m%d%H%M%S)"
    COMPOSE_COLD="docker compose -p $COLD_PROJECT"
    # IF-V7.1-01 (v7.2): fresh disposable-project marker for this run.
    # The backend reports it via /api/v1/lab/status; live-gate.py reset
    # refuses to run unless its --disposable-project-id flag matches the
    # value the backend itself reports. A new UUID per run, so a stale
    # marker from an earlier run can never authorise a reset. Exported
    # so `docker compose up` interpolates it into the disposable
    # backend service (docker-compose.yml).
    DISPOSABLE_PROJECT_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')"
    export IDENTITYFORGE_DISPOSABLE_PROJECT_ID="$DISPOSABLE_PROJECT_ID"
    mkdir -p test-results/coldstart
    cold_cleanup() {
      echo "Tearing down the disposable cold-start namespace ($COLD_PROJECT) ..."
      $COMPOSE_COLD down -v >/dev/null 2>&1 || true
      unset IDENTITYFORGE_DISPOSABLE_PROJECT_ID
    }
    trap cold_cleanup EXIT
    # Avoid writing resolved Compose configuration: its environment includes
    # private Keycloak credentials, and test-results may be uploaded on CI failure.
    # COMPOSE_CONFIG already performed the full resolved-healthcheck inspection.
    # Preserve the existing cold-start behavior: an invalid disposable config
    # is reported here, then 'up' fails the required CLEAN_COMPOSE_BUILD_BOOT gate.
    if ! $COMPOSE_COLD config -q >/dev/null 2>&1; then
      echo "WARN: disposable Compose configuration invalid (details withheld to protect credentials)" >&2
    fi
    echo "Cold-starting the lab in disposable namespace $COLD_PROJECT ..."
    BOOT_OK=0
    if $COMPOSE_COLD up --build -d > test-results/coldstart/up.log 2>&1; then
      $COMPOSE_COLD ps --format json > test-results/coldstart/containers.json 2>/dev/null || true
      # Wait for readiness (Keycloak needs 60-120s on first boot).
      waited=0
      until ./scripts/doctor.sh > test-results/coldstart/doctor.log 2>&1; do
        waited=$((waited + 10))
        if [ "$waited" -ge 360 ]; then break; fi
        sleep 10
      done
      if [ "$waited" -lt 360 ]; then
        BOOT_OK=1
      else
        GATE_DETAIL="doctor never became READY within 360s — see test-results/coldstart/doctor.log"
      fi
    else
      GATE_DETAIL="docker compose up --build -d failed — see test-results/coldstart/up.log"
    fi
    if [ "$BOOT_OK" -eq 1 ]; then
      gate CLEAN_COMPOSE_BUILD_BOOT full "cold-start: compose up --build -d + doctor READY in disposable namespace" true
    else
      gate CLEAN_COMPOSE_BUILD_BOOT full "cold-start: compose up --build -d + doctor READY in disposable namespace" false
    fi
    # IF-V8.0.2-B (v8.0.2): the four provider-dependent pytest tests
    # (marked live_keycloak) run HERE, against the cold-started
    # disposable Keycloak on 127.0.0.1:8080 — never against the user's
    # persistent stack, and never in the offline profile. They are
    # excluded from OFFLINE_UNIT above, so without this gate they
    # would run nowhere. Runs only when the cold-start boot succeeded
    # (BOOT_OK); otherwise NOT RUN honestly, and --strict fails closed.
    if [ "$BOOT_OK" -eq 1 ]; then
      gate LIVE_PROVIDER_PYTEST full "backend: provider-dependent pytest (live Keycloak, -m live_keycloak)" \
        bash -c "cd backend && ../$PY -m pytest -q -m live_keycloak"
    else
      skip_gate LIVE_PROVIDER_PYTEST full "backend: provider-dependent pytest (live Keycloak)" "cold-start boot failed; no disposable provider for the marked tests"
    fi
    # Live gates run against the cold-started stack. If the boot
    # failed they fail honestly here (the checks themselves report
    # the unreachable services) rather than being skipped.
    # The host run must NOT inherit a stale IDENTITYFORGE_LIVE_GATE_HOST_MAP
    # (e.g. exported for a container run): on the host there is no
    # mapping — the adapter code is the same live-gate.py, and the
    # container path (with the host map) is exercised by
    # test-all.ps1 -Full and by the manual `docker compose ... run
    # live-gate` command (see scripts/test-matrix.md).
    gate REAL_KEYCLOAK_LOGIN full "real Keycloak login (student + officer, logout, stale 401)" \
      env -u IDENTITYFORGE_LIVE_GATE_HOST_MAP python3 scripts/live-gate.py login
    gate REAL_SECURITY_NEGATIVES full "real Keycloak negatives (binding, replay, K2, K3)" \
      bash -c 'env -u IDENTITYFORGE_LIVE_GATE_HOST_MAP python3 scripts/live-gate.py binding && env -u IDENTITYFORGE_LIVE_GATE_HOST_MAP python3 scripts/live-gate.py negatives'
    # P1-13: disposable real-Keycloak reset test. The reset is
    # DESTRUCTIVE, so unlike the login/negatives gates it runs ONLY
    # when the cold-start boot succeeded (BOOT_OK): with no disposable
    # stack there is nothing safe to reset, and the host run must
    # never touch whatever happens to listen on 8000. Runs before the
    # browser E2E so the E2E starts from a clean lab.
    if [ "$BOOT_OK" -eq 1 ]; then
      gate REAL_LAB_RESET full "real Keycloak reset in the disposable namespace (synthetic run, unauthenticated/student denied, officer reset, stale cookies 401)" \
        env -u IDENTITYFORGE_LIVE_GATE_HOST_MAP python3 scripts/live-gate.py reset --disposable-project-id "$DISPOSABLE_PROJECT_ID"
    else
      skip_gate REAL_LAB_RESET full "real Keycloak reset in the disposable namespace" "cold-start boot failed; no disposable stack for the reset test"
    fi
    if [ -d frontend ] && [ -f frontend/package.json ]; then
      # IF-V4-10 (v5): the Playwright exit code alone is NOT the E2E
      # verdict. The report is deleted first (freshness), the run is
      # bound to this disposable project via IDENTITYFORGE_E2E_TARGET
      # (recorded in the report's config.metadata.target), and the
      # JSON report is parsed by scripts/validate-playwright-report.py
      # immediately after the run — BEFORE the screenshots run, which
      # overwrites the same report file. The gate passes only when
      # the run AND the validator both succeed.
      run_playwright_e2e() {
        rm -f frontend/test-results/playwright-report.json
        local start e2e_rc val_rc
        start="$(date +%s)"
        IDENTITYFORGE_E2E_TARGET="$COLD_PROJECT" bash -c 'cd frontend && npm run test:e2e'
        e2e_rc=$?
        python3 scripts/validate-playwright-report.py --report frontend/test-results/playwright-report.json --target "$COLD_PROJECT" --since-epoch "$start"
        val_rc=$?
        [ "$e2e_rc" -eq 0 ] && [ "$val_rc" -eq 0 ]
      }
      run_playwright_screenshots() {
        local start shots_rc val_rc
        start="$(date +%s)"
        IDENTITYFORGE_E2E_TARGET="$COLD_PROJECT" bash -c 'cd frontend && npm run test:screenshots'
        shots_rc=$?
        python3 scripts/validate-playwright-report.py --report frontend/test-results/playwright-report.json --target "$COLD_PROJECT" --profile screenshots --since-epoch "$start"
        val_rc=$?
        [ "$shots_rc" -eq 0 ] && [ "$val_rc" -eq 0 ]
      }
      gate PLAYWRIGHT_E2E full "browser E2E (real Keycloak, JSON evidence validated)" run_playwright_e2e
      if grep -q '"test:screenshots"' frontend/package.json; then
        gate RESPONSIVE_QA full "responsive screenshots (320/390/768/1440/1920)" \
          run_playwright_screenshots
      else
        skip_gate RESPONSIVE_QA full "responsive screenshots" "no test:screenshots script (spec not shipped)"
      fi
    else
      skip_gate PLAYWRIGHT_E2E full "browser E2E (real Keycloak)" "frontend/ missing"
      skip_gate RESPONSIVE_QA full "responsive screenshots" "frontend/ missing"
    fi
    # Diagnostics for local troubleshooting only: Compose logs can contain tokens.
    # Public CI artifacts must not include these raw files.
    $COMPOSE_COLD logs --no-log-prefix > test-results/coldstart/compose.log 2>&1 || true
    $COMPOSE_COLD ps --format json > test-results/coldstart/containers-final.json 2>/dev/null || true
  else
    skip_gate CLEAN_COMPOSE_BUILD_BOOT full "cold-start: compose up --build -d + doctor READY in disposable namespace" "Docker CLI unavailable"
    skip_gate LIVE_PROVIDER_PYTEST full "backend: provider-dependent pytest (live Keycloak)" "Docker CLI unavailable"
    skip_gate REAL_KEYCLOAK_LOGIN full "real Keycloak login" "Docker CLI unavailable"
    skip_gate REAL_SECURITY_NEGATIVES full "real Keycloak negatives" "Docker CLI unavailable"
    skip_gate REAL_LAB_RESET full "real Keycloak reset in the disposable namespace" "Docker CLI unavailable"
    skip_gate PLAYWRIGHT_E2E full "browser E2E (real Keycloak)" "Docker CLI unavailable"
    skip_gate RESPONSIVE_QA full "responsive screenshots" "Docker CLI unavailable"
  fi
else
  skip_gate CLEAN_COMPOSE_BUILD_BOOT full "cold-start: compose up --build -d + doctor READY in disposable namespace" "offline profile — opt in with --full"
  skip_gate LIVE_PROVIDER_PYTEST full "backend: provider-dependent pytest (live Keycloak)" "offline profile — opt in with --full"
  skip_gate REAL_KEYCLOAK_LOGIN full "real Keycloak login" "offline profile — opt in with --full"
  skip_gate REAL_SECURITY_NEGATIVES full "real Keycloak negatives" "offline profile — opt in with --full"
  skip_gate REAL_LAB_RESET full "real Keycloak reset in the disposable namespace" "offline profile — opt in with --full"
  skip_gate PLAYWRIGHT_E2E full "browser E2E (real Keycloak)" "offline profile — opt in with --full"
  skip_gate RESPONSIVE_QA full "responsive screenshots" "offline profile — opt in with --full"
fi

# --- Machine-readable report + summary --------------------------------------
python3 - "$RESULTS_TSV" "$PROFILE" "$STARTED_AT" <<'PY'
import json, sys
tsv, profile, started = sys.argv[1], sys.argv[2], sys.argv[3]
gates = []
for line in open(tsv):
    parts = line.rstrip("\n").split("\t")
    gates.append({"id": parts[0], "required_by": parts[1], "status": parts[2],
                  "at": parts[3], "detail": parts[4] if len(parts) > 4 else ""})
doc = {"profile": profile, "started_at": started,
       "gates": gates,
       "summary": {s: sum(1 for g in gates if g["status"] == s)
                   for s in ("PASS", "FAIL", "NOT RUN", "NOT APPLICABLE")}}
json.dump(doc, open("test-results/gates.json", "w"), indent=2)
PY

echo
echo "===== test-all summary (profile: $PROFILE) ====="
column -t -s $'\t' "$RESULTS_TSV" 2>/dev/null || cat "$RESULTS_TSV"
echo
echo "Machine-readable report: test-results/gates.json"

required_failed=0
required_notrun=0
any_notrun=0
while IFS=$'\t' read -r id required_by status _at _detail; do
  [ "$status" = "NOT RUN" ] && any_notrun=$((any_notrun + 1))
  if [ "$required_by" = "$PROFILE" ] || { [ "$PROFILE" = "full" ] && [ "$required_by" = "offline" ]; }; then
    [ "$status" = "FAIL" ] && required_failed=$((required_failed + 1))
    [ "$status" = "NOT RUN" ] && required_notrun=$((required_notrun + 1))
  fi
done < "$RESULTS_TSV"

if [ "$required_failed" -gt 0 ]; then
  echo "$required_failed required gate(s) FAILED. See the output above; fix and re-run."
  exit 1
fi
# A required gate that was skipped/unavailable fails the run when the
# profile demands it (--full always) or when --strict is set. Without
# --strict, an offline run still passes but the banner below names the
# missing gates — a NOT RUN gate is never silently read as a pass.
if [ "$required_notrun" -gt 0 ] && { [ "$PROFILE" = "full" ] || [ "$STRICT" -eq 1 ]; }; then
  echo "GATE FAILED: $required_notrun required gate(s) NOT RUN"
  echo "(profile: $PROFILE, strict: $STRICT)."
  echo "A full release gate must not pass while a required gate was skipped or unavailable."
  exit 1
fi
if [ "$PROFILE" = "offline" ]; then
  echo "All required offline gates passed. LIVE E2E NOT RUN in this profile"
  echo "(CLEAN_COMPOSE_BUILD_BOOT, REAL_KEYCLOAK_LOGIN, REAL_SECURITY_NEGATIVES,"
  echo "REAL_LAB_RESET, PLAYWRIGHT_E2E, RESPONSIVE_QA) — re-run with --full to execute them."
else
  echo "All required gates passed (profile: full)."
fi
