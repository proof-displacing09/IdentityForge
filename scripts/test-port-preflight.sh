#!/usr/bin/env bash
# IdentityForge port-preflight + teardown tests (P0-03 stop-first).
#
# Covers scripts/test-all.sh --full:
#   1. Occupied ports, occupant IS this project's lab -> the exact
#      stop -> test -> restart sequence, exit 1, nothing stopped.
#   2. Occupied ports, occupant is NOT this project -> refuse with
#      instructions, exit 1, nothing stopped.
#   3. Same as (1) from a repo path WITH SPACES.
#   4. Ports-free path + teardown scoping, inside a network namespace
#      (unshare -rn): the cold-start proceeds, the stub `up` fails,
#      the trap teardown runs `down -v` scoped to the disposable
#      project name ONLY, and REAL_LAB_RESET is NOT RUN (no
#      disposable stack to reset — the destructive gate never runs
#      against a missing stack).
#
# The host stack (Keycloak 8080, backend 8000, frontend 5173) is
# expected to be RUNNING for cases 1-3: the occupied-ports cases use
# the real busy ports. Case 4 needs free ports, so it runs in a
# namespace where the host stack is not visible; if `unshare -rn` is
# unavailable it is SKIPped with the reviewer command.
#
# A STUB `docker` is on PATH for every case — no real Docker, no real
# containers. Every stub invocation is logged and asserted.
#
# Usage: bash scripts/test-port-preflight.sh
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PASSED=0; FAILED=0; SKIPPED=0
ok()   { PASSED=$((PASSED+1)); echo "PASS: $1"; }
bad()  { FAILED=$((FAILED+1)); echo "FAIL: $1"; }
skip() { SKIPPED=$((SKIPPED+1)); echo "SKIP: $1"; }

gate_status() {  # gate_status <gates.json> <id>
  python3 -c "import json,sys; print({g['id']: g['status'] for g in json.load(open(sys.argv[1]))['gates']}.get(sys.argv[2], 'MISSING'))" "$1" "$2"
}
gate_detail() {  # gate_detail <gates.json> <id>
  python3 -c "import json,sys; print({g['id']: g['detail'] for g in json.load(open(sys.argv[1]))['gates']}.get(sys.argv[2], ''))" "$1" "$2"
}

# --- Stub docker ------------------------------------------------------------
# IF_STUB_MODE: ok | project | empty | upfail
#   ok      : daemon up, `compose ps` prints nothing, build/up exit 0
#   project : `compose ps` prints one RUNNING keycloak container
#   empty   : like ok (explicit)
#   upfail  : `compose up` exits 1 (cold-start boot fails)
STUBDIR="$(mktemp -d)"
cat > "$STUBDIR/docker" <<'STUB'
#!/usr/bin/env bash
echo "docker $*" >> "${IF_STUB_LOG:-/tmp/if-docker-stub.log}"
mode="${IF_STUB_MODE:-ok}"
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
    up)
      if [ "$mode" = "upfail" ]; then echo "ERROR: up failed (stub)" >&2; exit 1; fi
      exit 0 ;;
    *) exit 0 ;;
  esac
fi
exit 0
STUB
chmod +x "$STUBDIR/docker"

# --- Minimal repo copy (the runner writes test-results/ in the repo root) ---
WORK="$(mktemp -d)"
cp -r scripts "$WORK/"
cp docker-compose.yml docker-compose.test.yml "$WORK/"
export IF_STUB_LOG="$WORK/docker-stub.log"
: > "$IF_STUB_LOG"

run_sh() {  # run_sh <mode> <tree> <args...> — exit code on stdout
  local mode="$1" tree="$2"; shift 2
  (cd "$tree" && IF_STUB_MODE="$mode" PATH="$STUBDIR:$PATH" \
    bash scripts/test-all.sh "$@" > "$WORK/out.txt" 2>&1; echo $?)
}
stub_ran_bare_down() {  # any `down` without `-p identityforge-coldstart-`
  grep -E '(^| )down( |$)' "$IF_STUB_LOG" 2>/dev/null | grep -v "identityforge-coldstart-" | grep -q .
}
stub_ran_scoped_down() {
  grep -qE 'down -v' "$IF_STUB_LOG" 2>/dev/null \
    && grep -E '(^| )down( |$)' "$IF_STUB_LOG" 2>/dev/null | grep -q "identityforge-coldstart-"
}

# --- Deterministic busy-port fixture for the occupied-port cases -----------
# On a fresh CI runner the three real lab ports are normally free. Without
# a listener, the cases below test the wrong branch of test-all.sh and fail
# before reaching their assertions. Supply a disposable loopback listener
# ONLY when all three ports are free. Never stop or replace an existing
# listener or Docker service; the docker CLI remains stubbed throughout.
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
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 8080))
    listener.listen(16)
    pathlib.Path(sys.argv[1]).touch()
    while True:
        connection, _address = listener.accept()
        connection.close()
PYLISTENER
  BUSY_LISTENER_PID=$!
  for _attempt in {1..50}; do
    if [ -f "$BUSY_READY" ]; then break; fi
    if ! kill -0 "$BUSY_LISTENER_PID" 2>/dev/null; then break; fi
    sleep 0.1
  done
  if [ ! -f "$BUSY_READY" ] || ! port_busy 8080; then
    bad "unable to prepare the loopback busy-port test fixture"
    cat "$WORK/busy-port.log"
    exit 1
  fi
fi

# --- 1. Occupied ports, occupant IS this project's lab -----------------------
: > "$IF_STUB_LOG"
RC="$(run_sh project "$WORK" --full)"
if [ "$RC" -eq 1 ] \
    && grep -q "belong to the IdentityForge lab" "$WORK/out.txt" \
    && grep -q "docker compose down" "$WORK/out.txt" \
    && grep -q "test-all.sh --full --strict" "$WORK/out.txt" \
    && grep -q "docker compose up -d" "$WORK/out.txt" \
    && grep -q "Nothing was stopped" "$WORK/out.txt"; then
  ok "--full with busy ports (project lab) prints the stop-first sequence and exits 1"
else bad "--full with busy ports (project lab) should print the stop-first sequence (rc=$RC)"; cat "$WORK/out.txt"; fi
if stub_ran_bare_down; then bad "preflight must never run a bare 'docker compose down' (project case)"; else ok "preflight ran no 'down' (project case)"; fi

# --- 2. Occupied ports, occupant is NOT this project -------------------------
: > "$IF_STUB_LOG"
RC="$(run_sh empty "$WORK" --full)"
if [ "$RC" -eq 1 ] \
    && grep -q "do NOT belong to this project's lab" "$WORK/out.txt" \
    && grep -q "Free the ports first" "$WORK/out.txt" \
    && grep -q "never kills" "$WORK/out.txt"; then
  ok "--full with busy ports (unknown occupant) refuses with instructions and exits 1"
else bad "--full with busy ports (unknown occupant) should refuse with instructions (rc=$RC)"; cat "$WORK/out.txt"; fi
if stub_ran_bare_down; then bad "preflight must never run a bare 'docker compose down' (unknown-occupant case)"; else ok "preflight ran no 'down' (unknown-occupant case)"; fi

# --- 3. Path WITH SPACES ------------------------------------------------------
WORK_SPACED="$WORK/identity forge v4"
mkdir -p "$WORK_SPACED"
cp -r scripts "$WORK_SPACED/"
cp docker-compose.yml docker-compose.test.yml "$WORK_SPACED/"
: > "$IF_STUB_LOG"
RC="$(run_sh project "$WORK_SPACED" --full)"
if [ "$RC" -eq 1 ] && grep -q "belong to the IdentityForge lab" "$WORK/out.txt" && grep -q "docker compose down" "$WORK/out.txt"; then
  ok "path with spaces: --full occupied-ports case prints the stop-first sequence"
else bad "path with spaces: --full should print the stop-first sequence (rc=$RC)"; cat "$WORK/out.txt"; fi
if stub_ran_bare_down; then bad "path with spaces: preflight must never run a bare 'down'"; else ok "path with spaces: preflight ran no 'down'"; fi

# --- 4. Ports-free path + teardown scoping (network namespace) ---------------
if unshare -rn true 2>/dev/null; then
  # Full tree (no frontend/ -> browser gates skip honestly; .venv
  # symlinked so the offline gates run without a network install).
  NSTREE="$(mktemp -d)"
  tar --exclude='.venv' --exclude='node_modules' --exclude='test-results' \
    --exclude='backend/data' --exclude='*.egg-info' --exclude='frontend/dist' \
    --exclude='frontend' --exclude='.git' -cf - . | (cd "$NSTREE" && tar xf -)
  ln -s "$ROOT/.venv" "$NSTREE/.venv"
  NSLOG="$WORK/ns-out.txt"
  : > "$IF_STUB_LOG"
  unshare -rn bash -c "
    ip link set lo up 2>/dev/null || true
    cd '$NSTREE' && IF_STUB_MODE=upfail PATH='$STUBDIR:$PATH' IF_STUB_LOG='$IF_STUB_LOG' \
      bash scripts/test-all.sh --full > '$NSLOG' 2>&1
    echo \$? > '$WORK/ns-rc.txt'
  "
  NSRC="$(cat "$WORK/ns-rc.txt")"
  if [ "$NSRC" -eq 1 ] && grep -q "OK   Ports 8080/8000/5173 free" "$NSLOG"; then
    ok "namespace: ports-free preflight passes and the --full run proceeds (exit 1: stub boot fails, as designed)"
  else bad "namespace: ports-free preflight should pass and the run should proceed (rc=$NSRC)"; tail -20 "$NSLOG"; fi
  if stub_ran_scoped_down && ! stub_ran_bare_down; then
    ok "namespace: teardown runs 'down -v' scoped to the disposable project only (no bare down)"
  else bad "namespace: teardown must run 'down -v' scoped to the disposable project only"; cat "$IF_STUB_LOG"; fi
  if [ -f "$NSTREE/test-results/gates.json" ]; then
    if [ "$(gate_status "$NSTREE/test-results/gates.json" REAL_LAB_RESET)" = "NOT RUN" ] \
        && gate_detail "$NSTREE/test-results/gates.json" REAL_LAB_RESET | grep -q "no disposable stack"; then
      ok "namespace: REAL_LAB_RESET is NOT RUN with the no-disposable-stack reason (never runs against a missing stack)"
    else bad "namespace: REAL_LAB_RESET should be NOT RUN with the no-disposable-stack reason"; grep -A2 REAL_LAB_RESET "$NSTREE/test-results/gates.json" | head -5; fi
    if [ "$(gate_status "$NSTREE/test-results/gates.json" CLEAN_COMPOSE_BUILD_BOOT)" = "FAIL" ]; then
      ok "namespace: CLEAN_COMPOSE_BUILD_BOOT FAILs honestly on the stub boot failure"
    else bad "namespace: CLEAN_COMPOSE_BUILD_BOOT should FAIL on the stub boot failure"; fi
  else bad "namespace: gates.json missing after the --full run"; fi
  rm -rf "$NSTREE"
else
  skip "namespace cases NOT RUN here: 'unshare -rn' unavailable — reviewer runs 'bash scripts/test-port-preflight.sh' on Linux with user namespaces, or 'docker compose up --build -d' then '.\\scripts\\test-all.ps1 -Full -Strict' on Windows"
fi

echo ""
echo "port-preflight: $PASSED passed, $FAILED failed, $SKIPPED skipped"
[ "$FAILED" -eq 0 ]
