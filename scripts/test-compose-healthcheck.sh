#!/usr/bin/env bash
# IdentityForge Compose healthcheck regression (IF-V4-01, P0;
# Trustline v7.2: IF-V7.1-02, IF-V7.1-03, IF-V7.1-04;
# Trustline v7.3: IF-V7.2-01 — explicitly requested Docker probe is a
# REQUIRED live gate, never exit 0 when it could not run).
#
# Two parts:
#   1. STATIC (always runs, no Docker): scripts/compose-config-check.py
#      rejects single-$ shell variables in Compose healthchecks and
#      simulates Compose interpolation to prove the Keycloak
#      healthcheck resolves to the intended shell command.
#   2. DOCKER-PROBED (needs Docker): inspects the RESOLVED command via
#      `docker compose config`, then EITHER boots a disposable
#      cold-start project and checks the final health state plus the
#      discovered issuer (--with-docker), OR read-only inspects an
#      EXISTING stack without creating or deleting anything
#      (--against-running-project). Without Docker, or without a mode
#      flag, the Docker part is reported NOT RUN with the exact
#      reviewer commands (never PASS) — run it on a machine with
#      Docker Desktop.
#
# IF-V7.1-02 (v7.2): the log directory (test-results/) is created
# BEFORE the first redirection into it. The v7.1 script redirected
# `docker compose config` stderr to test-results/... before the
# mkdir, so on a fresh extraction the shell redirection itself
# failed ("No such file or directory") and the script reported a
# Compose config failure that never happened — and the stub log
# proved `compose config` was never even started. This version
# captures `docker compose config` output to files AND reads its
# real exit status, so a shell redirection failure and a real
# Compose failure are different, honestly labelled outcomes.
#
# IF-V7.1-03 (v7.2): the discovery document is fetched with
# scripts/discovery-check.py (stdlib http.client — never follows
# redirects; parses Content-Length and chunked framing correctly)
# and must answer HTTP 200 with a valid JSON object whose issuer is
# exactly the canonical issuer. The v7.1 script piped raw HTTP/1.1
# bytes (headers included) into json.load, which fails on every real
# response. The DISTINCT in-image check is kept: the exact
# healthcheck command from docker-compose.yml is run inside the
# pinned Keycloak 26.8.2 container (docker compose exec), which
# proves the in-image command works — not merely that a host
# endpoint answered.
#
# IF-V7.1-04 (v7.2): --with-docker boots a DISPOSABLE project with a
# unique name, only after a preflight proves the fixed host ports
# (127.0.0.1:8080/8000/5173) are free. If a port is occupied the
# script FAILS FAST — before any `compose up` — and prints the
# stop/test/restart sequence; it never touches the occupant, never
# kills anything, and never runs `down -v` against anything but its
# own disposable project (trap cleanup is scoped to -p $PROJECT).
# --against-running-project is the read-only alternative: it
# inspects the existing stack (resolved config, container health,
# in-image probe, host discovery) and creates/deletes nothing.
#
# Usage:
#   ./scripts/test-compose-healthcheck.sh [--with-docker | --against-running-project]
# Exit 0 only when the static part passes AND (when a Docker mode was
# given) the Docker probe passes. Without a Docker mode the Docker
# part is NOT RUN and the script still exits 0 (the static regression
# is the gate that runs everywhere); the NOT RUN banner names the
# missing probe explicitly.
#
# IF-V7.2-01 (v7.3): an explicitly requested Docker probe is a REQUIRED
# live gate, never a best-effort one. --with-docker and
# --against-running-project exit NONZERO whenever the live probe cannot
# run or fails: Docker CLI absent, Compose plugin missing, daemon
# inaccessible (`docker info` is checked separately — `docker compose
# version` never contacts the daemon, so a CLI can exist while Docker
# Desktop is not running), project cannot boot, healthcheck fails,
# issuer differs, tools missing, services not healthy, or ANY mandatory
# live check NOT RUN. Missing capability stays labelled NOT RUN; it
# just never yields exit 0 when explicitly requested. --help exits 0;
# unknown or mutually exclusive modes exit 2. Per-run probe artifacts
# are cleared before the live probe so stale success files can never
# read as this run's evidence, and the disposable-project cleanup is
# idempotent (exactly one scoped `down -v` even on TERM/INT).
#
# Logs: test-results/compose-healthcheck-*. All paths are quoted, so
# the script works from a checkout path containing spaces. Nothing
# is written outside test-results/ (gitignored, packaging-excluded).
set -uo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
WITH_DOCKER=0
AGAINST_RUNNING=0
for arg in "$@"; do
  case "$arg" in
    --with-docker) WITH_DOCKER=1 ;;
    --against-running-project) AGAINST_RUNNING=1 ;;
    --help|-h)
      echo "Usage: $0 [--with-docker | --against-running-project]"
      echo "  (default) static interpolation regression only; Docker probe NOT RUN"
      echo "  --with-docker              disposable cold-start probe (needs Docker + ~2 min;"
      echo "                             fails fast if the fixed ports 8080/8000/5173 are busy)"
      echo "  --against-running-project  read-only inspection of an EXISTING stack;"
      echo "                             creates/deletes nothing (no up, no down, no volumes)"
      exit 0 ;;
    *) echo "test-compose-healthcheck.sh: unknown argument: $arg" >&2; exit 2 ;;
  esac
done
if [ "$WITH_DOCKER" -eq 1 ] && [ "$AGAINST_RUNNING" -eq 1 ]; then
  echo "test-compose-healthcheck.sh: --with-docker and --against-running-project are mutually exclusive" >&2
  exit 2
fi

# IF-V7.1-02: the log directory is created FIRST — before any
# redirection into it, before any Docker call. If the directory
# cannot be created there is nowhere honest to log to, so fail
# here with that exact reason (never as a fake Compose failure).
LOG_DIR="$ROOT/test-results"
if ! mkdir -p "$LOG_DIR"; then
  echo "FAIL: cannot create log directory $LOG_DIR (check permissions / disk)" >&2
  exit 1
fi

PASS=0
FAIL=0
NOTRUN=0
ok()   { echo "PASS: $1"; PASS=$((PASS + 1)); }
bad()  { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }
notrun() { echo "NOT RUN: $1"; NOTRUN=$((NOTRUN + 1)); }

echo "== IdentityForge Compose healthcheck regression (IF-V4-01) =="

# --- 1. Static regression ---------------------------------------------------
if python3 scripts/compose-config-check.py; then
  ok "static: no single-\$ trap; resolved healthcheck keeps literal '\$resp' (2x); depends_on service_healthy"
else
  bad "static: compose-config-check.py failed (see above)"
fi

# --- 2. Docker-probed regression --------------------------------------------
if [ "$WITH_DOCKER" -eq 0 ] && [ "$AGAINST_RUNNING" -eq 0 ]; then
  notrun "docker compose config resolved-healthcheck inspection — run: docker compose config | grep -A2 healthcheck (expect literal '\$resp', 2x)"
  notrun "live Keycloak health state + discovered issuer — run: ./scripts/test-compose-healthcheck.sh --with-docker (disposable cold-start) or --against-running-project (read-only, stack running)"
  notrun "backend/frontend healthy after Keycloak healthy — run: ./scripts/test-compose-healthcheck.sh --with-docker"
  echo
  echo "compose-healthcheck: $PASS passed, $FAIL failed, $NOTRUN not run (Docker probe NOT RUN — re-run with --with-docker or --against-running-project on a Docker machine)"
  echo "SOURCE FIXED; ACTUAL DOCKER HEALTHCHECK + COMPOSE BOOT NOT RUN"
  [ "$FAIL" -eq 0 ]
  exit $?
fi

# IF-V7.2-01 (v7.3): an EXPLICITLY requested Docker probe is a REQUIRED
# live gate — it must NEVER exit 0 when it could not run. The v7.2 code
# recorded the three Docker checks as NOT RUN and then evaluated
# `[ "$FAIL" -eq 0 ]`, which is true when nothing failed, so
# `--with-docker` / `--against-running-project` exited 0 with no Docker
# at all (a false pass: "NOT RUN" text beside a zero exit code). The
# default (no-flag) mode above is the ONLY mode that may exit 0 with
# Docker checks NOT RUN. Missing capability stays labelled NOT RUN, but
# an explicitly requested probe that cannot run exits 1.
#
# Three separate gates, so the reason is named exactly:
#   1. `docker` CLI present at all;
#   2. the Compose plugin (`docker compose version` — a CLI can exist
#      with no Compose plugin);
#   3. daemon connectivity (`docker info` — `docker compose version`
#      does NOT contact the daemon, so a CLI can exist while Docker
#      Desktop is not running; a missing socket must never read as a
#      passing static probe).
DOCKER_REASON=""
if ! command -v docker >/dev/null 2>&1; then
  DOCKER_REASON="Docker CLI unavailable in this environment (no 'docker' binary on PATH)"
elif ! docker compose version >"$LOG_DIR/compose-healthcheck-compose-version.log" 2>&1; then
  DOCKER_REASON="Docker Compose plugin unavailable ('docker compose version' failed; see $LOG_DIR/compose-healthcheck-compose-version.log)"
elif ! docker info >"$LOG_DIR/compose-healthcheck-docker-info.log" 2>&1; then
  DOCKER_REASON="Docker daemon inaccessible ('docker info' failed — Docker Desktop may not be running; see $LOG_DIR/compose-healthcheck-docker-info.log)"
fi
if [ -n "$DOCKER_REASON" ]; then
  notrun "docker compose config resolved-healthcheck inspection — $DOCKER_REASON"
  notrun "live Keycloak health state + discovered issuer — $DOCKER_REASON"
  notrun "backend/frontend healthy after Keycloak healthy — $DOCKER_REASON"
  echo
  echo "compose-healthcheck: $PASS passed, $FAIL failed, $NOTRUN not run ($DOCKER_REASON)"
  echo "SOURCE FIXED; ACTUAL DOCKER HEALTHCHECK + COMPOSE BOOT NOT RUN — explicitly requested Docker probe could not run, exit 1"
  exit 1
fi

CANONICAL_ISSUER="http://127.0.0.1:8080/realms/identityforge-lab"
# Test-only overrides (regression suite only — never set these in
# normal use): IDENTITYFORGE_HCPROBE_TEST_PORTS="18080 18000 15173"
# lets the stub suite exercise the free-ports path while a developer
# live stack holds the real fixed ports, and
# IDENTITYFORGE_HCPROBE_DISCOVERY_URL lets it point the host-side
# discovery check at a local stub server instead of the live
# Keycloak. The shipped defaults are always the fixed lab ports and
# the canonical discovery URL, and the validation (HTTP 200 + valid
# JSON + exact issuer) is identical either way — these overrides
# change WHERE the check looks, never WHAT it accepts.
CHECK_PORTS="${IDENTITYFORGE_HCPROBE_TEST_PORTS:-8080 8000 5173}"
DISCOVERY_URL="${IDENTITYFORGE_HCPROBE_DISCOVERY_URL:-$CANONICAL_ISSUER/.well-known/openid-configuration}"
CONFIG_OUT="$LOG_DIR/compose-healthcheck-config.out"
CONFIG_ERR="$LOG_DIR/compose-healthcheck-config.err"

# Resolved command: `docker compose config` prints the config AFTER
# interpolation, so the healthcheck must contain the literal '$resp'
# (not an empty echo) in the resolved output.
# IF-V7.1-02: output goes to files in the ALREADY-CREATED log dir,
# and the command's REAL exit status is captured — a redirection
# failure and a Compose failure are different outcomes and are
# reported as such. Never `$(docker compose config 2>file)`: on a
# fresh extraction that hides a shell error as a Compose error.
# IF-V7.2-01 (v7.3): drop the previous run's per-probe artifacts BEFORE
# the live probe writes its own, so a stale success (resolved config,
# healthy-state JSON, discovery log, exec log) can never be mistaken
# for this run's evidence when a later step fails or never runs. These
# files are regenerated by the steps below on every run that reaches
# them; a failed or never-started probe leaves no success artifacts
# behind to mislead a reader.
rm -f "$CONFIG_OUT" "$CONFIG_ERR" \
  "$LOG_DIR/compose-healthcheck-kc-health.json" \
  "$LOG_DIR/compose-healthcheck-exec-tools.log" \
  "$LOG_DIR/compose-healthcheck-exec.log" \
  "$LOG_DIR/compose-healthcheck-discovery.log" \
  "$LOG_DIR/compose-healthcheck-up.log"
if docker compose config >"$CONFIG_OUT" 2>"$CONFIG_ERR"; then
  CONFIG_RC=0
else
  CONFIG_RC=$?
fi
if [ "$CONFIG_RC" -ne 0 ]; then
  bad "docker compose config failed (exit $CONFIG_RC; see $CONFIG_ERR)"
  echo "compose-healthcheck: $PASS passed, $FAIL failed, $NOTRUN not run"
  exit 1
fi
RESOLVED="$(cat "$CONFIG_OUT")"
# The resolved command must still carry the literal '$resp'
# references (2x, one per echo) and `resp=$(cat <&3)`. Count the
# literal '$resp' token rather than matching `echo "$resp"` exactly:
# `docker compose config` renders the command as YAML, where the
# inner double quotes are escaped (echo \"$resp\"), so an exact
# `echo "$resp"` match fails on real output too. A '$$resp' in the
# resolved output would mean Compose did NOT resolve the escape and
# the container shell would see a PID expansion instead — reject it.
RESP_COUNT="$(echo "$RESOLVED" | grep -o '\$resp' | wc -l)"
if echo "$RESOLVED" | grep -q 'resp=$(cat <&3)' \
   && [ "$RESP_COUNT" -ge 2 ] \
   && ! echo "$RESOLVED" | grep -q '\$\$resp'; then
  ok "docker compose config: resolved healthcheck contains literal '\$resp' (2x) and resp=\$(cat <&3)"
else
  bad "docker compose config: resolved healthcheck lost the '\$resp' references (Compose interpolated them away)"
  echo "$RESOLVED" | grep -A3 -B1 healthcheck | head -20
fi

# Port preflight (IF-V7.1-04): a connect() that succeeds means
# something listens on the fixed port. Python stdlib only; no
# ss/lsof dependency, and nothing is killed or probed beyond a TCP
# connect to loopback.
port_free() { # port_free <port> -> 0 if free, 1 if occupied
  python3 -c 'import socket,sys; s=socket.socket(); s.settimeout(2)
try:
    s.connect(("127.0.0.1", int(sys.argv[1]))); sys.exit(1)
except OSError:
    sys.exit(0)
finally:
    s.close()' "$1"
}

# The in-image probe command: the exact healthcheck `test:` value
# from docker-compose.yml (Keycloak service), run inside the
# container. It requires bash + /dev/tcp + grep inside the pinned
# keycloak:26.8.2 image, and BOTH an HTTP 200 status line AND the
# "issuer" field in the discovery body.
IN_IMAGE_PROBE="exec 3<>/dev/tcp/127.0.0.1/8080 && printf 'GET /realms/identityforge-lab/.well-known/openid-configuration HTTP/1.1\r\nHost: 127.0.0.1:8080\r\nConnection: close\r\n\r\n' >&3 && resp=\$(cat <&3) && echo \"\$resp\" | grep -qE 'HTTP/1\.[01] 200' && echo \"\$resp\" | grep -q '\"issuer\"'"

# Container health via `docker inspect` (pure JSON — json.load is
# correct here; the v7.1 bug was feeding it raw HTTP bytes, which
# never happens in this script anymore).
container_health() { # container_health <container-id> -> healthy|starting|unhealthy|unknown
  docker inspect "$1" --format '{{json .State.Health}}' 2>/dev/null \
    | python3 -c 'import json,sys; print(json.load(sys.stdin).get("Status","unknown"))' 2>/dev/null \
    || echo unknown
}

if [ "$AGAINST_RUNNING" -eq 1 ]; then
  # --- Read-only mode: inspect the EXISTING stack. No `up`, no
  # `down`, no volume ever touches this path; PROJECT stays empty so
  # no cleanup trap can delete anything. ---------------------------
  echo "read-only mode: inspecting the existing stack (nothing will be started, stopped, or deleted)"
  KC_NAME="$(docker compose ps -q keycloak 2>/dev/null || true)"
  if [ -z "$KC_NAME" ]; then
    bad "read-only: no running keycloak container found (is the lab up? start it with: docker compose up --build -d)"
    echo "compose-healthcheck: $PASS passed, $FAIL failed, $NOTRUN not run"
    exit 1
  fi
  kc_health="$(container_health "$KC_NAME")"
  docker inspect "$KC_NAME" --format '{{json .State.Health}}' > "$LOG_DIR/compose-healthcheck-kc-health.json" 2>&1 || true
  if [ "$kc_health" = "healthy" ]; then
    ok "read-only: Keycloak container is healthy (health state recorded in $LOG_DIR/compose-healthcheck-kc-health.json)"
  else
    bad "read-only: Keycloak container health is '$kc_health' (expected healthy)"
  fi
  # In-image check (read-only: exec runs the probe, changes nothing):
  # the exact healthcheck command, inside the pinned image.
  if docker compose exec -T keycloak bash -c 'command -v bash grep >/dev/null 2>&1' > "$LOG_DIR/compose-healthcheck-exec-tools.log" 2>&1; then
    ok "read-only: in-image tools present (bash + grep in keycloak:26.8.2)"
  else
    bad "read-only: bash/grep missing inside the Keycloak image (see $LOG_DIR/compose-healthcheck-exec-tools.log)"
  fi
  if docker compose exec -T keycloak bash -c "$IN_IMAGE_PROBE" > "$LOG_DIR/compose-healthcheck-exec.log" 2>&1; then
    ok "read-only: in-container probe: discovery 200 + issuer field present ($LOG_DIR/compose-healthcheck-exec.log)"
  else
    bad "read-only: in-container probe failed (see $LOG_DIR/compose-healthcheck-exec.log)"
  fi
  # Host-side discovery (IF-V7.1-03): real HTTP client, exact issuer.
  if python3 scripts/discovery-check.py --url "$DISCOVERY_URL" --issuer "$CANONICAL_ISSUER" > "$LOG_DIR/compose-healthcheck-discovery.log" 2>&1; then
    ok "read-only: discovered issuer is exactly the canonical issuer ($(cat "$LOG_DIR/compose-healthcheck-discovery.log"))"
  else
    bad "read-only: discovery check failed ($(cat "$LOG_DIR/compose-healthcheck-discovery.log"))"
  fi
  be_health="$(container_health "$(docker compose ps -q backend 2>/dev/null || true)")"
  fe_health="$(container_health "$(docker compose ps -q frontend 2>/dev/null || true)")"
  if [ "$be_health" = "healthy" ] && [ "$fe_health" = "healthy" ]; then
    ok "read-only: backend and frontend are healthy"
  else
    bad "read-only: backend/frontend are not both healthy (backend=$be_health, frontend=$fe_health)"
  fi
  echo
  echo "compose-healthcheck: $PASS passed, $FAIL failed, $NOTRUN not run (read-only mode — nothing was started, stopped, or deleted)"
  # IF-V7.2-01 (v7.3): read-only mode is an explicitly requested live
  # gate — ANY mandatory live check left NOT RUN is a failure, not a
  # pass, exactly like any FAIL.
  [ "$FAIL" -eq 0 ] && [ "$NOTRUN" -eq 0 ]
  exit $?
fi

# --- Disposable cold-start mode (--with-docker) --------------------------
# IF-V7.1-04: BEFORE booting, prove the fixed ports are free. If any
# is occupied, FAIL FAST here — no `compose up` runs, nothing is
# stopped or killed, and the message prints the exact stop/test/
# restart sequence (or the read-only alternative).
OCCUPIED=""
for port in $CHECK_PORTS; do
  if ! port_free "$port"; then
    OCCUPIED="$OCCUPIED $port"
  fi
done
if [ -n "$OCCUPIED" ]; then
  bad "fixed lab port(s)${OCCUPIED} occupied — refusing to boot a disposable project on conflicting ports (no containers were started, nothing was stopped or killed)"
  echo "  The disposable cold-start needs 127.0.0.1:8080, 8000 and 5173 free."
  echo "  If the occupant is this project's running lab, stop it first, run the test, then restart it:"
  echo "    docker compose down"
  echo "    bash scripts/test-compose-healthcheck.sh --with-docker"
  echo "    docker compose up -d"
  echo "  If the occupant is another application, stop that application first —"
  echo "  never change the lab's fixed ports (8080 is part of the issuer identity)."
  echo "  To inspect the EXISTING stack without booting anything, use read-only mode:"
  echo "    bash scripts/test-compose-healthcheck.sh --against-running-project"
  echo
  echo "compose-healthcheck: $PASS passed, $FAIL failed, $NOTRUN not run"
  exit 1
fi
ok "port preflight: lab ports ($CHECK_PORTS) are free (no occupant to disturb)"

# Unique disposable project: timestamp + PID, so two runs (or a
# stale project) can never collide, and cleanup can only ever name
# this run's project.
PROJECT="identityforge-hcprobe-$(date -u +%Y%m%d%H%M%S)-$$"
CLEANED_UP=0
cleanup() {
  # Scoped to this run's disposable project ONLY. Never a bare
  # `docker compose down -v` (that would delete the user's running
  # project's volumes) and never any other project's name.
  # Idempotent: the INT/TERM traps call cleanup() and then `exit`,
  # which fires the EXIT trap — without this guard `down -v` ran
  # TWICE for the same project (observed in the v7.3 failing-first
  # 04-c repro: down_v_lines=2). Exactly one scoped `down -v`.
  # The flag is set BEFORE the docker call so a re-entrant signal
  # during cleanup cannot start a second one.
  if [ "$CLEANED_UP" -eq 1 ]; then return 0; fi
  CLEANED_UP=1
  docker compose -p "$PROJECT" down -v >/dev/null 2>&1 || true
}
trap cleanup EXIT
trap 'cleanup; exit 130' INT
trap 'cleanup; exit 143' TERM
docker compose -p "$PROJECT" up --build -d > "$LOG_DIR/compose-healthcheck-up.log" 2>&1 || {
  bad "docker compose up --build -d failed (see $LOG_DIR/compose-healthcheck-up.log)"
  echo "compose-healthcheck: $PASS passed, $FAIL failed, $NOTRUN not run"
  exit 1
}
KC_NAME="$(docker compose -p "$PROJECT" ps -q keycloak)"
waited=0
kc_health="unknown"
while [ "$waited" -lt 300 ]; do
  kc_health="$(container_health "$KC_NAME")"
  if [ "$kc_health" = "healthy" ]; then break; fi
  sleep 5
  waited=$((waited + 5))
done
docker inspect "$KC_NAME" --format '{{json .State.Health}}' > "$LOG_DIR/compose-healthcheck-kc-health.json" 2>&1 || true
if [ "$kc_health" = "healthy" ]; then
  ok "Keycloak container reached healthy (health state recorded in $LOG_DIR/compose-healthcheck-kc-health.json)"
else
  bad "Keycloak container did not reach healthy within 300s (last state: $kc_health)"
fi
# In-image check FIRST (the tools the healthcheck itself needs),
# then the exact healthcheck command inside the pinned image.
if docker compose -p "$PROJECT" exec -T keycloak bash -c 'command -v bash grep >/dev/null 2>&1' > "$LOG_DIR/compose-healthcheck-exec-tools.log" 2>&1; then
  ok "in-image tools present (bash + grep in keycloak:26.8.2)"
else
  bad "bash/grep missing inside the Keycloak image (see $LOG_DIR/compose-healthcheck-exec-tools.log)"
fi
if docker compose -p "$PROJECT" exec -T keycloak bash -c "$IN_IMAGE_PROBE" > "$LOG_DIR/compose-healthcheck-exec.log" 2>&1; then
  ok "in-container probe: discovery 200 + issuer field present ($LOG_DIR/compose-healthcheck-exec.log)"
else
  bad "in-container probe failed (see $LOG_DIR/compose-healthcheck-exec.log)"
fi
# Host-side discovery (IF-V7.1-03): real HTTP client, exact issuer.
# This replaces the v7.1 raw-socket + json.load parse, which failed
# on every real response (headers are not JSON).
if python3 scripts/discovery-check.py --url "$DISCOVERY_URL" --issuer "$CANONICAL_ISSUER" > "$LOG_DIR/compose-healthcheck-discovery.log" 2>&1; then
  ok "discovered issuer is exactly the canonical issuer ($(cat "$LOG_DIR/compose-healthcheck-discovery.log"))"
else
  bad "discovery check failed ($(cat "$LOG_DIR/compose-healthcheck-discovery.log"))"
fi
# Backend/frontend must follow Keycloak to healthy (depends_on
# service_healthy is what the healthcheck gates).
be_health="unknown"; fe_health="unknown"
waited=0
while [ "$waited" -lt 180 ]; do
  be_health="$(container_health "$(docker compose -p "$PROJECT" ps -q backend)")"
  fe_health="$(container_health "$(docker compose -p "$PROJECT" ps -q frontend)")"
  if [ "$be_health" = "healthy" ] && [ "$fe_health" = "healthy" ]; then break; fi
  sleep 5
  waited=$((waited + 5))
done
if [ "$be_health" = "healthy" ] && [ "$fe_health" = "healthy" ]; then
  ok "backend and frontend reached healthy after Keycloak healthy"
else
  bad "backend/frontend did not both reach healthy (backend=$be_health, frontend=$fe_health)"
fi

echo
echo "compose-healthcheck: $PASS passed, $FAIL failed, $NOTRUN not run (disposable project $PROJECT cleaned up by trap)"
# IF-V7.2-01 (v7.3): --with-docker is an explicitly requested live
# gate — ANY mandatory live check left NOT RUN is a failure, not a
# pass, exactly like any FAIL.
[ "$FAIL" -eq 0 ] && [ "$NOTRUN" -eq 0 ]
