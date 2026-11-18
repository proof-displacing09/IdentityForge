#!/usr/bin/env bash
# IdentityForge ps1 preflight tests (P0-03 stop-first + P1-07 hardening).
#
# Runs scripts/test-all.ps1 under PowerShell 7.4.6 (pwsh) with a STUB
# `docker` on PATH — no real Docker, no real containers. Every case
# asserts the runner's observable behavior: exit code, the exact
# stop-first text, and that the stub log never shows a `down` (the
# preflight never stops or deletes anything).
#
# Occupied-port cases require a busy lab port; on a clean CI runner
# all ports may be free. A disposable loopback listener supplies this
# prerequisite when necessary (no real lab and no Docker daemon).
# The ports-free / cold-start path is NOT covered here — see the SKIP
# note at the end and docs/REVIEWER_GUIDE.md §7.
#
# Windows PowerShell 5.1 execution remains NOT RUN (5.1 is
# Windows-only); these runs prove the 7.4.6 paths only.
#
# Usage: bash scripts/test-ps1-preflight.sh
# Requires: pwsh (~/workspace/.pwsh/pwsh in this sandbox, or on PATH).
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PASSED=0; FAILED=0; SKIPPED=0
ok()   { PASSED=$((PASSED+1)); echo "PASS: $1"; }
bad()  { FAILED=$((FAILED+1)); echo "FAIL: $1"; }
skip() { SKIPPED=$((SKIPPED+1)); echo "SKIP: $1"; }

PWSH=""
if [ -x "$HOME/workspace/.pwsh/pwsh" ]; then PWSH="$HOME/workspace/.pwsh/pwsh";
elif command -v pwsh >/dev/null 2>&1; then PWSH="$(command -v pwsh)"; fi
if [ -z "$PWSH" ]; then
  skip "pwsh not found — install PowerShell 7.4+ and re-run; Windows reviewer commands are in docs/REVIEWER_GUIDE.md §7"
  echo "ps1-preflight: $PASSED passed, $FAILED failed, $SKIPPED skipped"
  exit 0
fi
echo "pwsh: $PWSH ($("$PWSH" -NoProfile -Command '$PSVersionTable.PSVersion.ToString()'))"

# --- Stub docker ------------------------------------------------------------
# IF_STUB_MODE: ok | project | empty | daemon-down | buildfail
#   ok         : daemon up, `compose ps` prints nothing (no containers)
#   project    : `compose ps` prints one RUNNING keycloak container
#   empty      : like ok (explicit)
#   daemon-down: `docker info` exits 1
#   buildfail  : `compose build` exits 1
# Every invocation is appended to $IF_STUB_LOG.
STUBDIR="$(mktemp -d)"
write_stub_docker() {
  cat > "$STUBDIR/docker" <<'STUB'
#!/usr/bin/env bash
echo "docker $*" >> "${IF_STUB_LOG:-/tmp/if-docker-stub.log}"
mode="${IF_STUB_MODE:-ok}"
if [ "$1" = "info" ]; then
  if [ "$mode" = "daemon-down" ]; then echo "Cannot connect to the Docker daemon" >&2; exit 1; fi
  if [ "$2" = "--format" ]; then echo "8589934592"; exit 0; fi
  echo "Server: Docker Engine (stub)"; exit 0
fi
if [ "$1" = "compose" ]; then
  sub=""; prev=""
  for a in "$@"; do
    case "$a" in
      -f|--file) prev="-f" ;;
      -p|--project-name|--profile) prev="$a" ;;
      *) if [ "$prev" = "-f" ] || [ "$prev" = "-p" ] || [ "$prev" = "--project-name" ] || [ "$prev" = "--profile" ]; then prev=""; continue; fi
         if [ -z "$sub" ] && [ "$a" != "compose" ]; then sub="$a"; fi ;;
    esac
  done
  case "$sub" in
    ps)
      if [ "$mode" = "project" ]; then echo '{"ID":"abc123","Name":"identityforge-keycloak-1","Service":"keycloak","State":"running"}'; fi
      exit 0 ;;
    build)
      if [ "$mode" = "buildfail" ]; then echo "ERROR: build failed (stub)" >&2; exit 1; fi
      exit 0 ;;
    config)
      # `config -q` prints nothing (quiet validation); plain `config`
      # prints the RESOLVED config — Compose resolves '$$' to '$', so
      # the resolved healthcheck must show the literal single-dollar
      # '$resp' (2x) and 'resp=$(cat <&3)', exactly what the runner's
      # COMPOSE_CONFIG gate (IF-V4-01) asserts. (Quoted heredoc: the
      # $resp references are emitted literally, not expanded here.)
      for a in "$@"; do if [ "$a" = "-q" ]; then exit 0; fi; done
      cat <<'YAML'
services:
  keycloak:
    image: quay.io/keycloak/keycloak:26.8.2
    healthcheck:
      test: ["CMD", "bash", "-c", "exec 3<>/dev/tcp/127.0.0.1/8080 && printf 'GET /realms/identityforge-lab/.well-known/openid-configuration HTTP/1.1\r\nHost: 127.0.0.1:8080\r\nConnection: close\r\n\r\n' >&3 && resp=$(cat <&3) && echo \"$resp\" | grep -qE 'HTTP/1\\.[01] 200' && echo \"$resp\" | grep -q '\"issuer\"'"]
      interval: 10s
      timeout: 5s
      retries: 30
      start_period: 20s
YAML
      exit 0 ;;
    run)
      # IF-V4-10 (v5): the stub stands in for Playwright AND for the
      # live-gate validator run. A frontend-e2e run "produces" the
      # JSON report by copying the matching synthetic fixture (target
      # substituted from $IDENTITYFORGE_E2E_TARGET, which test-all.ps1
      # exports before the run) to $IF_E2E_REPORT_PATH; a
      # validate-playwright-report.py run executes the REAL validator
      # against that file, translating the container report path to
      # the host path. This proves the runner wiring (delete stale
      # report, export target, validate before screenshots); the
      # validator's own correctness is proven by
      # scripts/test-validate-playwright-report.py against real +
      # fixture reports.
      is_e2e=0; is_shots=0; is_validator=0
      for a in "$@"; do
        case "$a" in
          frontend-e2e) is_e2e=1 ;;
          *test:screenshots*) is_shots=1 ;;
          *validate-playwright-report.py*) is_validator=1 ;;
        esac
      done
      if [ "$is_validator" -eq 1 ]; then
        target=""; profile="e2e"; since="0"; prev=""; seen_validator=0
        for a in "$@"; do
          # Only parse options AFTER the validator script path: the
          # compose invocation itself carries `--profile test`, which
          # must not be mistaken for the validator's --profile.
          case "$a" in *validate-playwright-report.py*) seen_validator=1 ;; esac
          if [ "$seen_validator" -eq 1 ]; then
            case "$prev" in
              --target) target="$a" ;;
              --profile) profile="$a" ;;
              --since-epoch) since="$a" ;;
            esac
          fi
          prev="$a"
        done
        if [ -z "$IF_VALIDATOR" ] || [ -z "$IF_E2E_REPORT_PATH" ]; then
          echo "stub: IF_VALIDATOR/IF_E2E_REPORT_PATH not set (preflight must export them)" >&2; exit 1
        fi
        python3 "$IF_VALIDATOR" --report "$IF_E2E_REPORT_PATH" --target "$target" --profile "$profile" --since-epoch "$since"
        exit $?
      fi
      if [ "$is_e2e" -eq 1 ]; then
        if [ -z "$IF_E2E_REPORT_PATH" ]; then
          echo "stub: IF_E2E_REPORT_PATH not set (preflight must export it)" >&2; exit 1
        fi
        stubdir="$(dirname "$0")"
        if [ "$is_shots" -eq 1 ]; then fixture="$stubdir/screenshots-report.json"; else fixture="$stubdir/e2e-report.json"; fi
        mkdir -p "$(dirname "$IF_E2E_REPORT_PATH")"
        sed "s/__TARGET__/${IDENTITYFORGE_E2E_TARGET:-host-lab}/g" "$fixture" > "$IF_E2E_REPORT_PATH"
        exit 0
      fi
      # Realistic command output for the two audit lanes (IF-V4-09):
      # a clean npm audit JSON report (metadata.vulnerabilities
      # present, all counts 0) and the pip-audit clean line. Other
      # `run` invocations (ruff/pytest/CLI/live-gate/e2e) need no
      # stdout — the runner gates on their exit code only.
      for a in "$@"; do
        case "$a" in
          *npm\ audit*)
            echo '{"metadata":{"vulnerabilities":{"info":0,"low":0,"moderate":0,"high":0,"critical":0},"dependencies":14,"devDependencies":0,"optionalDependencies":0,"totalDependencies":14},"vulnerabilities":{}}'
            exit 0 ;;
          *pip_audit*)
            echo "No known vulnerabilities found"
            exit 0 ;;
        esac
      done
      exit 0 ;;
    *) exit 0 ;;
  esac
fi
exit 0
STUB
  chmod +x "$STUBDIR/docker"
}
write_stub_docker

# --- Synthetic Playwright JSON reports (IF-V4-10) ---------------------------
# The stub "produces" these when the frontend-e2e service runs: the
# E2E fixture mirrors the real report shape (42 specs: portal 8 incl.
# the discovery + 3 real-login tests, edge 9 incl. the one allowed
# cancel skip, a11y 25) and the screenshots fixture has 24 specs, all
# passed. metadata.target is the __TARGET__ placeholder, substituted
# by the stub from $IDENTITYFORGE_E2E_TARGET at run time. The REAL
# validator (scripts/validate-playwright-report.py) runs against
# these files, so the namespace case proves the runner wiring with
# real validation logic — not a stubbed verdict.
python3 - "$STUBDIR" <<'PY'
import json, sys
stubdir = sys.argv[1]

def spec(title, status="expected"):
    return {"title": title, "ok": status == "expected",
            "tests": [{"status": status,
                       "results": [{"status": "passed" if status == "expected" else status}]}]}

def fsuite(fname, describes):
    return {"title": fname, "file": fname, "specs": [],
            "suites": [{"title": t, "file": fname, "specs": s, "suites": []}
                       for t, s in describes]}

def report(suites):
    return {"config": {"metadata": {"baseURL": "http://127.0.0.1:5173", "target": "__TARGET__"}},
            "errors": [], "stats": {}, "suites": suites}

portal = [spec("Keycloak discovery issuer is the pinned canonical issuer"),
          spec("student_01: member 200, officer 403"),
          spec("logout revokes the session; stale cookie is denied (401)"),
          spec("officer_01: member 200 and officer 200"),
          spec("deep link and refresh keep the portal view and session"),
          spec("callback error path shows a safe reason, no session"),
          spec("logout without a CSRF token is rejected 403 and the session survives"),
          spec("unknown route renders the 404 view")]
edge = [spec("menu button controls the sidebar nav; Escape closes and focus returns"),
        spec("provider error callback shows a safe reason, no session"),
        spec("user cancels at the Keycloak login page", status="skipped"),
        spec("browser back after logout shows the signed-out portal"),
        spec("unknown state at the callback is rejected (STATE_REUSED)"),
        spec("missing state parameter is rejected (CALLBACK_MALFORMED)"),
        spec("empty state is rejected (STATE_MISSING)"),
        spec("second callback replay is rejected (STATE_REUSED)"),
        spec("CSV is labelled CLIENT-DERIVED and JSON is a server artifact")]
a11y = [spec(f"axe view {i}") for i in range(25)]
with open(f"{stubdir}/e2e-report.json", "w") as fh:
    json.dump(report([fsuite("portal.spec.ts", [("real Keycloak login", portal)]),
                      fsuite("edge.spec.ts", [("login edge cases", edge)]),
                      fsuite("a11y.spec.ts", [("axe scans — all views", a11y)])]), fh)

shots = []
for vp in ["320x740", "390x844", "768x1024", "1280x800", "1440x900", "1920x1080"]:
    shots.append(spec(f"screenshots @ {vp}"))
    shots.append(spec(f"settings + reset modal @ {vp}"))
for t in ["findings empty state (fresh browser, no runs)",
          "overview loading state (status delayed)",
          "overview error state (status 500)",
          "portal access-denied state (student loads officer resource)",
          "overview provider-down state (IdP unreachable, honest not-ready)",
          "overview wrong-issuer state (reachable, issuer mismatch — never Verified)",
          "overview not-run state (no verified login, no live logins)",
          "settings identity-unknown state (/portal/me returns 500)",
          "200% zoom layout equivalent (720 CSS px viewport)",
          "400% zoom layout equivalent (360 CSS px viewport)",
          "increased text size (root font-size 125%)",
          "forced colours (high-contrast) overview"]:
    shots.append(spec(t))
with open(f"{stubdir}/screenshots-report.json", "w") as fh:
    json.dump(report([fsuite("screenshots.spec.ts", [("screenshots", shots)])]), fh)
print("synthetic Playwright reports written to $STUBDIR")
PY

# --- Minimal repo copy (the runner writes test-results/ in the repo root) ---
WORK="$(mktemp -d)"
cp -r scripts "$WORK/"
cp docker-compose.yml docker-compose.test.yml "$WORK/"
export IF_STUB_LOG="$WORK/docker-stub.log"
: > "$IF_STUB_LOG"

run_pwsh() {  # run_pwsh <mode> <ps1-args...> — stdout+stderr captured
  local mode="$1"; shift
  IF_STUB_MODE="$mode" PATH="$STUBDIR:$PATH" \
    "$PWSH" -NoProfile -File "$WORK/scripts/test-all.ps1" "$@" > "$WORK/out.txt" 2>&1
  echo $?
}
run_pwsh_here() {  # same, but with the script in a path WITH SPACES
  local mode="$1"; shift
  IF_STUB_MODE="$mode" PATH="$STUBDIR:$PATH" \
    "$PWSH" -NoProfile -File "$WORK_SPACED/scripts/test-all.ps1" "$@" > "$WORK/out.txt" 2>&1
  echo $?
}
stub_ran_down() { grep -qE '(^| )down( |$)' "$IF_STUB_LOG" 2>/dev/null; }
stub_ran_bare_down() {  # any `down` without `-p identityforge-coldstart-`
  grep -E '(^| )down( |$)' "$IF_STUB_LOG" 2>/dev/null | grep -v "identityforge-coldstart-" | grep -q .
}
stub_ran_scoped_down() {
  grep -qE 'down -v' "$IF_STUB_LOG" 2>/dev/null \
    && grep -E '(^| )down( |$)' "$IF_STUB_LOG" 2>/dev/null | grep -q "identityforge-coldstart-"
}

# --- 1. -Help ---------------------------------------------------------------
RC="$(run_pwsh ok -Help)"
if [ "$RC" -eq 0 ] \
    && grep -q "docker compose down" "$WORK/out.txt" \
    && grep -q "test-all.ps1 -Full -Strict" "$WORK/out.txt" \
    && grep -q "docker compose up -d" "$WORK/out.txt"; then
  ok "-Help exits 0 and prints the stop-first workflow (down / -Full -Strict / up -d)"
else bad "-Help should exit 0 with the stop-first workflow (rc=$RC)"; sed -n '1,12p' "$WORK/out.txt"; fi

# --- 2. Invalid parameters ---------------------------------------------------
RC="$(run_pwsh ok -Offline -Full)"
if [ "$RC" -eq 2 ] && grep -q "Usage error" "$WORK/out.txt"; then
  ok "-Offline -Full exits 2 with a usage error"
else bad "-Offline -Full should exit 2 with a usage error (rc=$RC)"; fi
RC="$(run_pwsh ok -BogusParam)"
if [ "$RC" -eq 2 ] && grep -q "Usage error: unknown argument" "$WORK/out.txt"; then
  ok "unknown parameter exits 2 with a usage error (not silently ignored)"
else bad "unknown parameter should exit 2 with a usage error (rc=$RC)"; cat "$WORK/out.txt"; fi

# --- Deterministic occupied-port fixture (GitHub CI has no running lab) ----
# The PowerShell -Full preflight must see a *real* occupied loopback port
# before it can test its stop-first safety behavior. Never stop or replace
# an existing listener. We run only the docker *stub* below, never Docker.
BUSY_LISTENER_PID=""
cleanup() {
  if [ -n "$BUSY_LISTENER_PID" ]; then
    kill "$BUSY_LISTENER_PID" 2>/dev/null || true
    wait "$BUSY_LISTENER_PID" 2>/dev/null || true
  fi
  rm -rf "$STUBDIR" "$WORK"
}
trap cleanup EXIT
port_busy() { (exec 3<>/dev/tcp/127.0.0.1/"$1") 2>/dev/null; }
if ! port_busy 8080 && ! port_busy 8000 && ! port_busy 5173; then
  BUSY_READY="$WORK/busy-port.ready"
  python3 -u - "$BUSY_READY" > "$WORK/busy-port.log" 2>&1 <<'PYLISTENER' &
import pathlib
import socket
import sys

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
    listener.bind(("127.0.0.1", 8080))
    listener.listen(16)
    pathlib.Path(sys.argv[1]).touch()
    while True:
        conn, _address = listener.accept()
        conn.close()
PYLISTENER
  BUSY_LISTENER_PID=$!
  for _attempt in {1..50}; do
    if [ -f "$BUSY_READY" ]; then break; fi
    if ! kill -0 "$BUSY_LISTENER_PID" 2>/dev/null; then break; fi
    sleep 0.1
  done
  if [ ! -f "$BUSY_READY" ] || ! port_busy 8080; then
    bad "unable to establish the temporary occupied-port fixture"
    cat "$WORK/busy-port.log"
    exit 1
  fi
fi

# --- 3. Occupied ports, occupant IS this project's lab -----------------------
# The real host stack holds 8080/8000/5173; the stub `compose ps`
# reports a running keycloak container for this folder's project.
: > "$IF_STUB_LOG"
RC="$(run_pwsh project -Full)"
if [ "$RC" -eq 1 ] \
    && grep -q "belong to the IdentityForge lab" "$WORK/out.txt" \
    && grep -q "docker compose down" "$WORK/out.txt" \
    && grep -q "test-all.ps1 -Full -Strict" "$WORK/out.txt" \
    && grep -q "docker compose up -d" "$WORK/out.txt" \
    && grep -q "Nothing was stopped" "$WORK/out.txt"; then
  ok "-Full with busy ports (project lab) prints the stop-first sequence and exits 1"
else bad "-Full with busy ports (project lab) should print the stop-first sequence (rc=$RC)"; cat "$WORK/out.txt"; fi
if stub_ran_down; then bad "preflight must never run 'docker compose down' (project case)"; else ok "preflight ran no 'down' (project case)"; fi

# --- 4. Occupied ports, occupant is NOT this project -------------------------
: > "$IF_STUB_LOG"
RC="$(run_pwsh empty -Full)"
if [ "$RC" -eq 1 ] \
    && grep -q "do NOT belong to this project's lab" "$WORK/out.txt" \
    && grep -q "Free the ports first" "$WORK/out.txt" \
    && grep -q "never kills" "$WORK/out.txt"; then
  ok "-Full with busy ports (unknown occupant) refuses with instructions and exits 1"
else bad "-Full with busy ports (unknown occupant) should refuse with instructions (rc=$RC)"; cat "$WORK/out.txt"; fi
if stub_ran_down; then bad "preflight must never run 'docker compose down' (unknown-occupant case)"; else ok "preflight ran no 'down' (unknown-occupant case)"; fi

# --- 5. Missing Docker daemon -------------------------------------------------
RC="$(run_pwsh daemon-down -Full)"
if [ "$RC" -eq 1 ] && grep -q "Docker daemon is not running" "$WORK/out.txt"; then
  ok "missing daemon exits 1 naming the daemon (before any port check)"
else bad "missing daemon should exit 1 naming the daemon (rc=$RC)"; cat "$WORK/out.txt"; fi

# --- 6. No docker on PATH ------------------------------------------------------
# /usr/bin may contain Docker on GitHub-hosted runners. Hide it with an
# empty private PATH, keeping the absolute pwsh executable path intact.
NO_DOCKER_PATH="$WORK/no-docker-path"
mkdir -p "$NO_DOCKER_PATH"
RC="$(PATH="$NO_DOCKER_PATH" "$PWSH" -NoProfile -File "$WORK/scripts/test-all.ps1" -Full > "$WORK/out.txt" 2>&1; echo $?)"
if [ "$RC" -eq 1 ] && grep -q "Docker is not available" "$WORK/out.txt"; then
  ok "no docker on PATH exits 1 naming Docker"
else bad "no docker on PATH should exit 1 naming Docker (rc=$RC)"; cat "$WORK/out.txt"; fi

# --- 7. Failing test (offline build fails via stub) -----------------------------
: > "$IF_STUB_LOG"
RC="$(run_pwsh buildfail -Offline)"
if [ "$RC" -eq 1 ] && grep -q "docker compose failed" "$WORK/out.txt"; then
  ok "-Offline with a failing build exits 1 with the gate failure"
else bad "-Offline with a failing build should exit 1 (rc=$RC)"; cat "$WORK/out.txt"; fi
if grep -q "compose.*build backend-test" "$IF_STUB_LOG"; then
  ok "stub log shows the failing build invocation (backend-test)"
else bad "stub log should show the failing build invocation"; cat "$IF_STUB_LOG"; fi

# --- 8. Path WITH SPACES --------------------------------------------------------
WORK_SPACED="$WORK/identity forge v4"
mkdir -p "$WORK_SPACED"
cp -r scripts "$WORK_SPACED/"
cp docker-compose.yml docker-compose.test.yml "$WORK_SPACED/"
RC="$(run_pwsh_here ok -Help)"
if [ "$RC" -eq 0 ] && grep -q "Usage:" "$WORK/out.txt"; then
  ok "path with spaces: -Help exits 0"
else bad "path with spaces: -Help should exit 0 (rc=$RC)"; cat "$WORK/out.txt"; fi
: > "$IF_STUB_LOG"
RC="$(run_pwsh_here project -Full)"
if [ "$RC" -eq 1 ] && grep -q "belong to the IdentityForge lab" "$WORK/out.txt" && grep -q "docker compose down" "$WORK/out.txt"; then
  ok "path with spaces: -Full occupied-ports case prints the stop-first sequence"
else bad "path with spaces: -Full should print the stop-first sequence (rc=$RC)"; cat "$WORK/out.txt"; fi
if stub_ran_down; then bad "path with spaces: preflight must never run 'down'"; else ok "path with spaces: preflight ran no 'down'"; fi

# --- 9. Full -Full -Strict flow with stubs (network namespace) -------------
# Ports are free in the namespace, the stub docker succeeds at
# everything, and a stub doctor.ps1 reports READY immediately, so
# the -Full flow runs end to end: offline gates, cold-start, live
# gates (incl. REAL_LAB_RESET), E2E, and the teardown. Asserts the
# wiring that the occupied-ports cases cannot reach: the reset gate
# runs when the boot succeeded, the teardown `down -v` is scoped to
# the disposable project only, NOT APPLICABLE never fails strict, and
# (IF-V4-10) the E2E + screenshots gates validate the Playwright JSON
# report against the disposable project via the real validator.
if unshare -rn true 2>/dev/null; then
  NSTREE="$(mktemp -d)"
  cp -r scripts "$NSTREE/"
  cp docker-compose.yml docker-compose.test.yml "$NSTREE/"
  printf '# stub doctor — always READY (test double for the readiness probe)\nexit 0\n' > "$NSTREE/scripts/doctor.ps1"
  NSLOG="$WORK/ns-ps1-out.txt"
  : > "$IF_STUB_LOG"
  unshare -rn bash -c "
    ip link set lo up 2>/dev/null || true
    cd '$NSTREE' && IF_STUB_MODE=ok PATH='$STUBDIR:$PATH' IF_STUB_LOG='$IF_STUB_LOG' \
      IF_E2E_REPORT_PATH='$NSTREE/test-results/playwright-report.json' \
      IF_VALIDATOR='$NSTREE/scripts/validate-playwright-report.py' \
      '$PWSH' -NoProfile -File '$NSTREE/scripts/test-all.ps1' -Full -Strict > '$NSLOG' 2>&1
    echo \$? > '$WORK/ns-ps1-rc.txt'
  "
  NSRC="$(cat "$WORK/ns-ps1-rc.txt")"
  if [ "$NSRC" -eq 0 ] && grep -q "All required gates passed (profile: full)" "$NSLOG"; then
    ok "namespace: stub -Full -Strict run passes end to end"
  else bad "namespace: stub -Full -Strict run should pass (rc=$NSRC)"; tail -25 "$NSLOG"; fi
  if stub_ran_scoped_down && ! stub_ran_bare_down; then
    ok "namespace: teardown runs 'down -v' scoped to the disposable project only (no bare down)"
  else bad "namespace: teardown must run 'down -v' scoped to the disposable project only"; cat "$IF_STUB_LOG"; fi
  if [ -f "$NSTREE/test-results/gates.json" ]; then
    RESET_STATUS="$("$PWSH" -NoProfile -Command "(Get-Content '$NSTREE/test-results/gates.json' | ConvertFrom-Json).gates | Where-Object { \$_.id -eq 'REAL_LAB_RESET' } | ForEach-Object { \$_.status }")"
    GHSA_STATUS="$("$PWSH" -NoProfile -Command "(Get-Content '$NSTREE/test-results/gates.json' | ConvertFrom-Json).gates | Where-Object { \$_.id -eq 'GHSA_DIRECT_FALLBACK' } | ForEach-Object { \$_.status }")"
    E2E_STATUS="$("$PWSH" -NoProfile -Command "(Get-Content '$NSTREE/test-results/gates.json' | ConvertFrom-Json).gates | Where-Object { \$_.id -eq 'PLAYWRIGHT_E2E' } | ForEach-Object { \$_.status }")"
    SHOTS_STATUS="$("$PWSH" -NoProfile -Command "(Get-Content '$NSTREE/test-results/gates.json' | ConvertFrom-Json).gates | Where-Object { \$_.id -eq 'RESPONSIVE_QA' } | ForEach-Object { \$_.status }")"
    if [ "$RESET_STATUS" = "PASS" ]; then
      ok "namespace: REAL_LAB_RESET PASSes when the cold-start boot succeeded (gate is wired)"
    else bad "namespace: REAL_LAB_RESET should PASS when the boot succeeded (got $RESET_STATUS)"; fi
    if [ "$GHSA_STATUS" = "NOT APPLICABLE" ]; then
      ok "namespace: GHSA_DIRECT_FALLBACK is NOT APPLICABLE when the full audit executed (strict still passes)"
    else bad "namespace: GHSA should be NOT APPLICABLE when the full audit executed (got $GHSA_STATUS)"; fi
    if [ "$E2E_STATUS" = "PASS" ] && [ "$SHOTS_STATUS" = "PASS" ]; then
      ok "namespace: PLAYWRIGHT_E2E + RESPONSIVE_QA PASS (JSON report validated against the disposable project)"
    else bad "namespace: PLAYWRIGHT_E2E/RESPONSIVE_QA should PASS (got E2E=$E2E_STATUS SHOTS=$SHOTS_STATUS)"; fi
  else bad "namespace: gates.json missing after the -Full -Strict run"; fi
  if grep -q "validate-playwright-report.py" "$IF_STUB_LOG"; then
    ok "namespace: the E2E validator ran inside live-gate (stub log shows the invocation)"
  else bad "namespace: stub log should show validate-playwright-report.py invocations"; fi
  rm -rf "$NSTREE"
else
  skip "namespace full-flow case NOT RUN here: 'unshare -rn' unavailable — reviewer runs '.\\scripts\\test-all.ps1 -Full -Strict' on Windows with Docker Desktop"
fi

# --- 10. Ports-free / cold-start path: NOT RUN here ------------------------------
skip "ports-free cold-start path NOT RUN here: the host stack occupies 8080/8000/5173 and there is no real Docker — reviewer runs '.\\scripts\\test-all.ps1 -Full -Strict' on Windows with Docker Desktop (see docs/REVIEWER_GUIDE.md §7)"

echo ""
echo "ps1-preflight: $PASSED passed, $FAILED failed, $SKIPPED skipped"
[ "$FAILED" -eq 0 ]
