#!/usr/bin/env bash
# IdentityForge ps1 selection regression (v8.0.3, IF-V8.0.2-B follow-up).
#
# Proves the v8.0.2 ps1 defect is fixed: scripts/test-all.ps1 ran the
# OFFLINE_UNIT gate as unfiltered `python -m pytest -q` inside the
# backend-test container, so the four live_keycloak tests failed with
# 503 PROVIDER_UNAVAILABLE whenever no provider ran — while the Linux
# runner, CI and verify-release already used `-m "not live_keycloak"`.
# Reproduced v8.0.3 (WS1 evidence 04-unfiltered-no-provider-pre.log):
# unfiltered `pytest -q` with no provider -> rc=1, exactly the four
# marked tests FAILED (503 PROVIDER_UNAVAILABLE).
#
#   (a) OFFLINE_UNIT keeps the offline selection: the ps1 line contains
#       `-m 'not live_keycloak'` (single quotes — see the QUOTING note
#       in test-all.ps1), the exact ps1 string propagates through
#       PowerShell -> Invoke-Native -> stub docker -> sh -c -> pytest
#       as ONE argument, and the venv selection split is exact
#       (total = offline + 4 live) with the offline run green and no
#       provider present.
#   (b) LIVE_PROVIDER_PYTEST exists as a full-profile gate: it runs
#       `-m live_keycloak` in backend-test on the disposable project's
#       network with the loopback forwarder (127.0.0.1:8080 ->
#       keycloak:8080), is BOOT_OK-gated (NOT RUN when the cold-start
#       boot failed), has an offline Skip-Gate, requires "4 passed"
#       (positive proof the four tests executed), and the gate count
#       is 19 (12 offline + 7 full). --live additionally proves the
#       forwarder forwards real discovery (canonical issuer intact)
#       and the four tests pass against a live provider.
#   (c) No false-green when Docker is missing: with no `docker` on
#       PATH, and with a stub docker whose `docker info` fails, the
#       real test-all.ps1 exits 1 and never reports a pass.
#   (d) Cleanup stays inside the disposable Compose project: exactly
#       one executed `down` exists and it is the finally-block
#       `-p $ColdProject down -v`; no bare down, no volume removal,
#       no prune/kill. A stub-docker -Full run (cold-start `up`
#       failing) proves the teardown still runs with the disposable
#       project name and nothing else destructive is invoked.
#
# Usage:
#   bash scripts/test-ps1-selection.sh          # default (no Docker, no provider)
#   bash scripts/test-ps1-selection.sh --live   # + live forwarder + 4 live tests (needs Keycloak on 8080)
#
# Default mode REFUSES to run if something answers on 127.0.0.1:8080:
# the no-provider proof is only meaningful with no provider present.
# Live mode REFUSES to run unless discovery on 8080 returns 200 with
# the canonical issuer: a skipped live run must never read as a pass.
#
# pwsh 7.4.6 (Linux build) is used for the PowerShell probes; Windows
# PowerShell 5.1 execution of test-all.ps1 remains NOT RUN (5.1 is
# Windows-only) and real Docker execution of the new LIVE gate remains
# NOT RUN in this sandbox (no Docker here). One more sandbox limit:
# pwsh TcpClient connects to ANY loopback port here (even a dead one),
# so test-all.ps1 -Full always fails its port preflight in this
# sandbox and the (d) runtime teardown probe SKIPs here with that
# reason; it runs on Windows. Reviewer acceptance on
# Windows: .\scripts\test-all.ps1 -Full -Strict, then confirm
# LIVE_PROVIDER_PYTEST PASS with "4 passed" in
# test-results\live-provider-pytest.log.
#
# The ps1 probes run against a TEMP COPY of the tree on real disk (never
# a small tmpfs) so test-results/ and stub logs never pollute the
# deliverable tree. The copy is removed afterwards. The scratch root is
# portable (v8.0.4, WS2 — Coverage Closure 2): prefer the CI runner temp
# dir ($RUNNER_TEMP on GitHub Actions), then $TMPDIR, then the workspace
# home disk, then /tmp. The v8.0.3 form hard-coded "$HOME/workspace",
# which does not exist on a GitHub Actions runner. The small
# /tmp/ws1-v803-*.log/.json probe files stay on /tmp: they are a few KB
# and /tmp exists on every runner; only the 46 MB tree copy + venv need
# real disk. Stub-docker PASSes are control-flow/quoting artifacts ONLY
# — they prove the script drives the right commands, never that the
# gates' checks pass; the real gate evidence is the venv pytest runs below.
set -uo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

# Portable scratch root (v8.0.4, WS2): see the header note. Order matters:
# $RUNNER_TEMP is the CI runner's on-disk temp dir; $TMPDIR is the
# caller's override; $HOME/workspace is this sandbox's home disk
# (the v8.0.3 location — /tmp here is a 512 MB tmpfs, too small for a
# tree copy + venv); /tmp is the last resort on any other machine.
SCRATCH_ROOT="${RUNNER_TEMP:-${TMPDIR:-}}"
if [ -z "$SCRATCH_ROOT" ] && [ -d "$HOME/workspace" ]; then
  SCRATCH_ROOT="$HOME/workspace"
fi
SCRATCH_ROOT="${SCRATCH_ROOT:-/tmp}"
PASS=0
FAIL=0
SKIP=0
VENV_TMP=""
SCRATCH=""
cleanup_all() {
  [ -n "${VENV_TMP:-}" ] && rm -rf "$VENV_TMP"
  [ -n "${SCRATCH:-}" ] && rm -rf "$SCRATCH"
}
trap cleanup_all EXIT

ok()   { echo "PASS: $1"; PASS=$((PASS + 1)); }
bad()  { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }
skip() { echo "SKIP: $1"; SKIP=$((SKIP + 1)); }

LIVE=0
for arg in "$@"; do
  case "$arg" in
    --live) LIVE=1 ;;
    --help|-h) echo "Usage: $0 [--live]"; exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

EXPECTED_LIVE=(
  "tests/adversarial/test_ws1_v8_oidc.py::test_callback_replay_and_cross_browser_and_errors"
  "tests/adversarial/test_ws1_v8_oidc.py::test_callback_replay_after_consume"
  "tests/adversarial/test_ws1_v8_oidc.py::test_login_start_rate_limit"
  "tests/adversarial/test_ws1_v8_oidc.py::test_login_start_sets_browser_cookie_and_s256"
)

provider_up() { (exec 3<>/dev/tcp/127.0.0.1/8080) 2>/dev/null; }
port_busy() { (exec 3<>/dev/tcp/127.0.0.1/"$1") 2>/dev/null; }

if [ "$LIVE" -eq 0 ]; then
  if provider_up; then
    echo "FAIL: something listens on 127.0.0.1:8080 — stop Keycloak first; the offline no-provider proof needs no provider present"
    echo "ps1-selection: 0 passed, 1 failed"
    exit 1
  fi
  ok "no provider on 127.0.0.1:8080 (offline no-provider precondition holds)"
else
  if ! curl -fsS -o /tmp/ws1-v803-live-disc.json http://127.0.0.1:8080/realms/identityforge-lab/.well-known/openid-configuration 2>/dev/null \
      || ! grep -q '"issuer":"http://127.0.0.1:8080/realms/identityforge-lab"' /tmp/ws1-v803-live-disc.json; then
    echo "FAIL: live Keycloak discovery on 8080 is not 200 with the canonical issuer — start the lab first; a skipped live run must never read as a pass"
    echo "ps1-selection: 0 passed, 1 failed"
    exit 1
  fi
  ok "live Keycloak discovery 200 with the canonical issuer (live precondition holds)"
fi

# --- PowerShell resolution (7.4.6 Linux build in this sandbox) -----------
if command -v pwsh >/dev/null 2>&1; then
  PWSH="$(command -v pwsh)"
elif [ -x "$HOME/workspace/.pwsh/pwsh" ]; then
  PWSH="$HOME/workspace/.pwsh/pwsh"
else
  bad "pwsh not found (neither on PATH nor at ~/workspace/.pwsh/pwsh); PowerShell probes cannot run"
  echo "ps1-selection: $PASS passed, $FAIL failed"
  exit 1
fi
ok "pwsh found: $PWSH ($("$PWSH" --version 2>/dev/null))"

# --- (a) static: OFFLINE_UNIT keeps the offline selection -----------------
OFFLINE_LINE="$(grep -n "python -m pytest" scripts/test-all.ps1 | grep OFFLINE -i || true)"
grep -q "python -m pytest -q -m 'not live_keycloak'" scripts/test-all.ps1 \
  && ok "OFFLINE_UNIT runs -m 'not live_keycloak' (single quotes, see test-all.ps1 QUOTING note)" \
  || bad "OFFLINE_UNIT does not run -m 'not live_keycloak'"
if grep -q 'python -m pytest -q"))' scripts/test-all.ps1; then
  bad "an unfiltered 'python -m pytest -q' (no -m selection) is still present in test-all.ps1"
else
  ok "no unfiltered 'python -m pytest -q' remains in test-all.ps1"
fi
# Expected release version, derived from the version-contract checker's
# own --expected default (v8.0.4, WS2): the label must agree with the
# release version, whatever it is after the coordinator's bump. A
# literal here would go stale at every bump and turn the CI step that
# runs this suite red (the same class of miss as the v8.0.3
# test-version-contract.sh sed patterns, which still target 1.8.2).
EXPECTED_VERSION="$(grep -oE 'default="[0-9]+\.[0-9]+\.[0-9]+"' scripts/check-version-contract.py | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')"
if [ -z "$EXPECTED_VERSION" ]; then
  bad "cannot derive the expected release version from scripts/check-version-contract.py (--expected default)"
else
  grep -q "release version $EXPECTED_VERSION agrees everywhere" scripts/test-all.ps1 \
    && ok "VERSION_CONTRACT label says $EXPECTED_VERSION" \
    || bad "VERSION_CONTRACT label does not say $EXPECTED_VERSION"
  LABEL_VERSIONS="$(grep 'Invoke-Gate "VERSION_CONTRACT"' scripts/test-all.ps1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | sort -u)"
  if [ "$LABEL_VERSIONS" = "$EXPECTED_VERSION" ]; then
    ok "VERSION_CONTRACT label names no version other than $EXPECTED_VERSION"
  else
    bad "VERSION_CONTRACT label names unexpected version(s): $LABEL_VERSIONS"
  fi
fi
if grep -q '1\.7\.3' scripts/test-all.ps1; then
  bad "stale '1.7.3' still present in test-all.ps1"
else
  ok "no stale '1.7.3' remains in test-all.ps1"
fi

# --- (b) static: LIVE_PROVIDER_PYTEST wiring ------------------------------
grep -q 'Invoke-Gate "LIVE_PROVIDER_PYTEST" "full"' scripts/test-all.ps1 \
  && ok "LIVE_PROVIDER_PYTEST is an Invoke-Gate required by full" \
  || bad "LIVE_PROVIDER_PYTEST Invoke-Gate (full) missing"
[ "$(grep -c 'Skip-Gate "LIVE_PROVIDER_PYTEST" "full"' scripts/test-all.ps1)" = "2" ] \
  && ok "LIVE_PROVIDER_PYTEST has exactly two Skip-Gates (boot-failed + offline profile)" \
  || bad "LIVE_PROVIDER_PYTEST Skip-Gate count is not 2 (boot-failed + offline)"
grep -q 'loopback-forwarder.py 127.0.0.1:8080 keycloak:8080' scripts/test-all.ps1 \
  && ok "LIVE gate starts the loopback forwarder 127.0.0.1:8080 -> keycloak:8080" \
  || bad "LIVE gate does not start the loopback forwarder to keycloak:8080"
grep -q 'python -m pytest -v -m live_keycloak' scripts/test-all.ps1 \
  && ok "LIVE gate runs 'pytest -v -m live_keycloak' in backend-test" \
  || bad "LIVE gate does not run 'pytest -v -m live_keycloak'"
grep -q '"4 passed"' scripts/test-all.ps1 \
  && ok "LIVE gate requires '4 passed' in the log (positive proof the four tests executed)" \
  || bad "LIVE gate does not require '4 passed'"
if grep -v '^\s*#' scripts/test-all.ps1 | grep -q 'IDENTITYFORGE_IDP_TRANSPORT_BASE'; then
  bad "test-all.ps1 sets IDENTITYFORGE_IDP_TRANSPORT_BASE in executable code — the fixture builds Settings() from defaults, so that override would NOT reroute the test app"
else
  ok "test-all.ps1 sets no IDENTITYFORGE_IDP_TRANSPORT_BASE override in executable code (only header comments explain why it would not work; reachability comes from the forwarder)"
fi
grep -q 'backend-test.*run.*backend-test\|run", "--rm", "backend-test"' scripts/test-all.ps1 \
  && ok "LIVE gate runs in the backend-test container (not in the provider-less offline container path)" \
  || bad "LIVE gate container arrangement unclear"
# BOOT_OK gating: the LIVE Invoke-Gate must sit between `if ($bootOk)`
# and its `} else {` Skip-Gate.
if awk '/if \(\$bootOk\) \{/{seen=1} seen && /Invoke-Gate "LIVE_PROVIDER_PYTEST"/{found=1} seen && /Skip-Gate "LIVE_PROVIDER_PYTEST"/{if(found) ok_boot=1; exit} END{exit !ok_boot}' scripts/test-all.ps1; then
  ok "LIVE_PROVIDER_PYTEST is BOOT_OK-gated (Invoke inside if (\$bootOk), Skip in else)"
else
  bad "LIVE_PROVIDER_PYTEST is not BOOT_OK-gated"
fi
# Gate counts: 19 unique Invoke-Gate IDs (12 offline + 7 full).
OFFLINE_IDS="$(grep -oE 'Invoke-Gate "[A-Z0-9_]+" "offline"' scripts/test-all.ps1 | sort -u | wc -l)"
FULL_IDS="$(grep -oE 'Invoke-Gate "[A-Z0-9_]+" "full"' scripts/test-all.ps1 | sort -u | wc -l)"
TOTAL_IDS="$(grep -oE 'Invoke-Gate "[A-Z0-9_]+"' scripts/test-all.ps1 | sort -u | wc -l)"
if [ "$OFFLINE_IDS" = "12" ] && [ "$FULL_IDS" = "7" ] && [ "$TOTAL_IDS" = "19" ]; then
  ok "gate count is 19 (12 offline + 7 full)"
else
  bad "gate count is not 19 (12 offline + 7 full): offline=$OFFLINE_IDS full=$FULL_IDS total=$TOTAL_IDS"
fi
grep -q '(19 gates: 12 offline + 7 full' scripts/test-all.ps1 \
  && ok "header gate count says 19 (12 offline + 7 full)" \
  || bad "header gate count does not say 19 (12 offline + 7 full)"
# Forwarder helper: exists, stdlib-only, binds only the given address.
[ -f scripts/loopback-forwarder.py ] \
  && ok "scripts/loopback-forwarder.py exists" \
  || bad "scripts/loopback-forwarder.py missing"
if python3 - <<'PY' 2>/dev/null
import ast, sys
tree = ast.parse(open('scripts/loopback-forwarder.py').read())
mods = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        mods.update(a.name.split('.')[0] for a in node.names)
    elif isinstance(node, ast.ImportFrom):
        if node.module:
            mods.add(node.module.split('.')[0])
sys.exit(0 if mods <= {'socket', 'sys', 'threading', '__future__'} else 1)
PY
then
  ok "loopback-forwarder.py imports stdlib only (socket/sys/threading)"
else
  bad "loopback-forwarder.py imports more than stdlib socket/sys/threading"
fi
python3 scripts/loopback-forwarder.py >/tmp/ws1-v803-fwd-usage.log 2>&1
FWD_RC=$?
if [ "$FWD_RC" = "2" ] && grep -q "usage:" /tmp/ws1-v803-fwd-usage.log; then
  ok "loopback-forwarder.py rejects bad argv (usage, rc=2)"
else
  bad "loopback-forwarder.py does not reject bad argv (rc=$FWD_RC)"
fi

# --- (d) static: cleanup stays inside the disposable project --------------
DOWN_LINES="$(grep -n 'down' scripts/test-all.ps1 | grep -v '^\s*#' | grep -v 'Write-Host' || true)"
DOWN_EXEC="$(echo "$DOWN_LINES" | grep -c '"down", "-v"' || true)"
if [ "$DOWN_EXEC" = "1" ] && echo "$DOWN_LINES" | grep -q '"-p", $ColdProject, "down", "-v"'; then
  ok "exactly one executed 'down' exists and it is finally-block '-p \$ColdProject down -v'"
else
  bad "executed 'down' is not exactly one '-p \$ColdProject down -v' (see grep below)"; echo "$DOWN_LINES"
fi
if grep -qE 'docker (volume rm|system prune|container rm|kill)|"volume"|"prune"' scripts/test-all.ps1; then
  bad "test-all.ps1 contains a volume/prune/kill removal outside the disposable project"
else
  ok "no volume rm / system prune / container kill in test-all.ps1"
fi
if grep -qE 'Remove-Item .*-Recurse|rm -rf' scripts/test-all.ps1; then
  bad "test-all.ps1 contains a recursive delete"
else
  ok "no recursive delete in test-all.ps1"
fi
# The teardown lives in a finally block scoped to the disposable project.
if awk '/\} finally \{/{f=1} f && /"-p", \$ColdProject, "down", "-v"/{ok_fin=1} END{exit !ok_fin}' scripts/test-all.ps1; then
  ok "teardown is in a finally block (runs on Ctrl+C / exception too) scoped to \$ColdProject"
else
  bad "teardown is not in a finally block scoped to \$ColdProject"
fi

# --- Python for the selection proofs ---------------------------------------
# Preference: $IDENTITYFORGE_TEST_PY, tree .venv, system pytest, the
# sandbox v7.3.1 venv (task-prescribed backend), else a disposable
# venv built from backend/requirements-freeze.txt (PyPI).
resolve_py() {
  if [ -n "${IDENTITYFORGE_TEST_PY:-}" ] && [ -x "$IDENTITYFORGE_TEST_PY" ]; then echo "$IDENTITYFORGE_TEST_PY"; return 0; fi
  if [ -x "$ROOT/.venv/bin/python" ]; then echo "$ROOT/.venv/bin/python"; return 0; fi
  if python3 -m pytest --version >/dev/null 2>&1; then echo python3; return 0; fi
  if [ -x "$ROOT/../identityforge-v7.3.1/.venv/bin/python" ]; then echo "$ROOT/../identityforge-v7.3.1/.venv/bin/python"; return 0; fi
  return 1
}
PY=""
if PY="$(resolve_py)"; then
  ok "test python resolved: $PY"
else
  VENV_TMP="$(mktemp -d "$SCRATCH_ROOT/.tmp-ps1venv.XXXXXX")"
  python3 -m venv "$VENV_TMP/venv" && "$VENV_TMP/venv/bin/pip" install -q -r backend/requirements-freeze.txt \
    && PY="$VENV_TMP/venv/bin/python" && ok "disposable venv built from backend/requirements-freeze.txt" \
    || { bad "no usable test python and disposable venv build failed"; echo "ps1-selection: $PASS passed, $FAIL failed"; exit 1; }
fi

# --- (a)/(b) selection split: total = offline + 4 live, live set exact ----
cd backend
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT/backend/src"
TOTAL_N="$("$PY" -m pytest --collect-only 2>/dev/null | grep -c '::')"
OFFLINE_COUNT="$("$PY" -m pytest --collect-only -m "not live_keycloak" 2>/dev/null | grep -c '::')"
LIVE_COUNT="$("$PY" -m pytest --collect-only -m live_keycloak 2>/dev/null | grep -c '::')"
if [ "$LIVE_COUNT" = "4" ] && [ "$((OFFLINE_COUNT + LIVE_COUNT))" = "$TOTAL_N" ]; then
  ok "selection split is exact: $TOTAL_N total = $OFFLINE_COUNT offline + $LIVE_COUNT live_keycloak"
else
  bad "selection split is not exact: total=$TOTAL_N offline=$OFFLINE_COUNT live=$LIVE_COUNT"
fi
LIVE_IDS="$("$PY" -m pytest --collect-only -m live_keycloak 2>/dev/null | grep '::test_' | sort)"
EXPECTED_IDS="$(printf '%s\n' "${EXPECTED_LIVE[@]}" | sort)"
if [ "$LIVE_IDS" = "$EXPECTED_IDS" ]; then
  ok "the live_keycloak set is exactly the four provider-dependent tests"
else
  bad "the live_keycloak set is not the expected four: got [$LIVE_IDS]"
fi
"$PY" -m pytest --markers -q 2>/dev/null | grep -q 'live_keycloak' \
  && ok "pytest --markers lists live_keycloak (registered, not a typo)" \
  || bad "pytest --markers does not list live_keycloak"
cd "$ROOT"

# --- (a) offline mode: the offline selection passes with no provider ------
if [ "$LIVE" -eq 0 ]; then
  cd backend
  if "$PY" -m pytest -q -m "not live_keycloak" > /tmp/ws1-v803-offline-run.log 2>&1; then
    ok "offline selection passes with no provider ($OFFLINE_COUNT tests, rc=0)"
  else
    bad "offline selection FAILED with no provider (see /tmp/ws1-v803-offline-run.log)"
    tail -5 /tmp/ws1-v803-offline-run.log
  fi
  cd "$ROOT"
fi

# --- (b) live mode: forwarder + the four tests vs the real provider -------
if [ "$LIVE" -eq 1 ]; then
  # Forwarder on a scratch loopback port (18080 -> 8080): discovery
  # through it must carry the canonical issuer, proving the proxy
  # forwards the REAL provider byte-for-byte (no mock, no rewrite).
  python3 scripts/loopback-forwarder.py 127.0.0.1:18080 127.0.0.1:8080 > /tmp/ws1-v803-forwarder.log 2>&1 &
  FWD_PID=$!
  sleep 1
  if curl -fsS -o /tmp/ws1-v803-fwd-disc.json http://127.0.0.1:18080/realms/identityforge-lab/.well-known/openid-configuration 2>/dev/null \
      && grep -q '"issuer":"http://127.0.0.1:8080/realms/identityforge-lab"' /tmp/ws1-v803-fwd-disc.json; then
    ok "forwarder serves real discovery through 127.0.0.1:18080 with the canonical issuer intact"
  else
    bad "forwarder did not serve real discovery through 127.0.0.1:18080 (see /tmp/ws1-v803-forwarder.log)"
  fi
  kill "$FWD_PID" 2>/dev/null; wait "$FWD_PID" 2>/dev/null || true
  # Forwarder to a dead target must fail closed (no discovery, no pass).
  python3 scripts/loopback-forwarder.py 127.0.0.1:18081 127.0.0.1:18099 > /tmp/ws1-v803-forwarder-dead.log 2>&1 &
  FWD_PID=$!
  sleep 1
  if curl -fsS -m 3 http://127.0.0.1:18081/realms/identityforge-lab/.well-known/openid-configuration >/dev/null 2>&1; then
    bad "forwarder to a dead target answered discovery (false provider)"
  else
    ok "forwarder to a dead target fails closed (connection refused, no discovery)"
  fi
  kill "$FWD_PID" 2>/dev/null; wait "$FWD_PID" 2>/dev/null || true
  # The four live tests against the real provider, with the gate's own
  # positive proof ("4 passed" — pytest.ini forces -q, which prints no
  # count line, so -o addopts="" restores it).
  cd backend
  if "$PY" -m pytest -o addopts="" -m live_keycloak > /tmp/ws1-v803-live-run.log 2>&1 \
      && grep -q "4 passed" /tmp/ws1-v803-live-run.log; then
    ok "live selection passes against the live provider (rc=0 AND '4 passed' in the log)"
  else
    bad "live selection FAILED against the live provider (see /tmp/ws1-v803-live-run.log)"
    tail -5 /tmp/ws1-v803-live-run.log
  fi
  cd "$ROOT"
fi

# --- (c)+(d) PowerShell probes against a TEMP COPY (never the live tree) ---
# Temp copy under $SCRATCH_ROOT (portable, v8.0.4 — see the header note).
# Stub docker + fake tools live in a temp bin dir prepended to PATH.
SCRATCH="$(mktemp -d "$SCRATCH_ROOT/.tmp-ps1probe.XXXXXX")"
mkdir -p "$SCRATCH/tree"
cp -r "$ROOT/." "$SCRATCH/tree/"
rm -rf "$SCRATCH/tree/.venv" "$SCRATCH/tree/test-results" "$SCRATCH/tree/backend/data"
find "$SCRATCH/tree" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
FAKEBIN="$SCRATCH/fakebin"
mkdir -p "$FAKEBIN"
cat > "$FAKEBIN/docker" <<'EOF'
#!/usr/bin/env bash
# Stub docker for test-ps1-selection.sh: logs every argv, never touches
# a daemon. UP_FAIL=1 makes `compose up` fail (cold-start boot failure).
{
  printf 'DOCKER-ARGV:'
  printf ' <%s>' "$@"
  printf '\n'
} >> "$DOCKER_STUB_LOG"
cmd="$1"; shift || true
if [ "$cmd" = "info" ]; then
  if [ "${DOCKER_INFO_FAIL:-0}" = "1" ]; then echo "stub: daemon not running" >&2; exit 1; fi
  if [ "$1" = "--format" ]; then echo 8589934592; else echo "stub docker info ok"; fi
  exit 0
fi
if [ "$cmd" = "compose" ]; then
  sub=""
  prev=""
  payload=""
  for a in "$@"; do
    if [ "$prev" = "-c" ]; then payload="$a"; fi
    case "$a" in
      config|build|run|up|down|ps|logs) sub="$a" ;;
    esac
    prev="$a"
  done
  case "$sub" in
    config)
      if printf '%s\n' "$@" | grep -q '\-q'; then exit 0; fi
      printf '%s\n' 'services:'
      printf '%s\n' '  keycloak:'
      printf '%s\n' '    healthcheck:'
      printf '%s\n' '      test: ["CMD", "bash", "-c", "exec 3<>/dev/tcp/127.0.0.1/8080 && resp=$(cat <&3) && echo \"$resp\" | grep -qE .HTTP. && echo \"$resp\" | grep -q .issuer."]'
      exit 0 ;;
    up)
      if [ "${DOCKER_UP_FAIL:-0}" = "1" ]; then echo "stub: compose up failed" >&2; exit 1; fi
      exit 0 ;;
    run)
      # Execute the sh -c payload locally with the fake tools on PATH
      # (inherited from the pwsh invocation, which prepends $FAKEBIN).
      sh -c "$payload"
      exit $? ;;
    *) exit 0 ;;
  esac
fi
if [ "$cmd" = "run" ]; then exit 0; fi
exit 0
EOF
chmod +x "$FAKEBIN/docker"
cat > "$FAKEBIN/python" <<'EOF'
#!/usr/bin/env bash
# Fake python: logs every argv (one per line) for the quoting probe.
{
  printf 'PYTHON-ARGV:'
  printf ' <%s>' "$@"
  printf '\n'
  for a in "$@"; do printf 'ARG:[%s]\n' "$a"; done
} >> "$PYTHON_PROBE_LOG"
if [ "$1" = "-m" ] && [ "$2" = "pytest" ]; then exit 0; fi
if [ "$1" = "-m" ] && [ "$2" = "ruff" ]; then exit 0; fi
if [ "$1" = "-m" ] && [ "$2" = "pip_audit" ]; then exit 0; fi
if [ "$1" = "scripts/validate-docs-contract.py" ]; then exit 0; fi
exit 0
EOF
chmod +x "$FAKEBIN/python"
cat > "$FAKEBIN/npm" <<'EOF'
#!/usr/bin/env bash
if [ "$1" = "audit" ]; then
  printf '%s\n' '{"metadata":{"vulnerabilities":{"high":0,"critical":0}}}'
  exit 0
fi
exit 0
EOF
chmod +x "$FAKEBIN/npm"

# --- (c) no-docker and daemon-dead: the real ps1 must fail closed ---------
export DOCKER_STUB_LOG="$SCRATCH/docker-argv.log"
export PYTHON_PROBE_LOG="$SCRATCH/python-argv.log"
: > "$DOCKER_STUB_LOG"; : > "$PYTHON_PROBE_LOG"
# /usr/bin can contain a real Docker CLI on GitHub-hosted Linux runners.
# Test the actual "docker unavailable" branch with a private, EMPTY PATH.
# PWSH is an absolute executable path resolved above, so this hides only
# external commands during the preflight; no real Docker daemon is touched.
NO_DOCKER_PATH="$SCRATCH/no-docker-path"
mkdir -p "$NO_DOCKER_PATH"
(cd "$SCRATCH/tree" && PATH="$NO_DOCKER_PATH" "$PWSH" -NoProfile -File scripts/test-all.ps1 -Offline > "$SCRATCH/nodocker.log" 2>&1)
RC=$?
if [ "$RC" -ne 0 ] && grep -q "Docker is not available" "$SCRATCH/nodocker.log" && ! grep -q "All required gates passed" "$SCRATCH/nodocker.log"; then
  ok "no-docker run exits $RC with 'Docker is not available', never a pass (c)"
else
  bad "no-docker run did not fail closed (rc=$RC; see $SCRATCH/nodocker.log — copy kept only on failure path)"
fi
if [ -f "$SCRATCH/tree/test-results/gates.json" ]; then
  bad "no-docker run wrote test-results/gates.json (a gate report must not exist when the preflight failed)"
else
  ok "no-docker run wrote no gates.json (preflight failed before any gate)"
fi
export DOCKER_INFO_FAIL=1
(cd "$SCRATCH/tree" && PATH="$FAKEBIN:$PATH" DOCKER_STUB_LOG="$DOCKER_STUB_LOG" "$PWSH" -NoProfile -File scripts/test-all.ps1 -Offline > "$SCRATCH/deaddaemon.log" 2>&1)
RC=$?
unset DOCKER_INFO_FAIL
if [ "$RC" -ne 0 ] && grep -q "daemon is not running" "$SCRATCH/deaddaemon.log" && ! grep -q "All required gates passed" "$SCRATCH/deaddaemon.log"; then
  ok "daemon-dead run exits $RC with 'daemon is not running', never a pass (c)"
else
  bad "daemon-dead run did not fail closed (rc=$RC; see $SCRATCH/deaddaemon.log)"
fi

# --- (a) quoting probe: the REAL ps1 -Offline under stub docker -----------
# The stub executes the gate payloads locally with the fake tools, so
# the fake python argv log shows exactly what pytest received.
(cd "$SCRATCH/tree" && PATH="$FAKEBIN:$PATH" DOCKER_STUB_LOG="$DOCKER_STUB_LOG" PYTHON_PROBE_LOG="$PYTHON_PROBE_LOG" "$PWSH" -NoProfile -File scripts/test-all.ps1 -Offline > "$SCRATCH/offline-stub.log" 2>&1)
RC=$?
if grep -q 'ARG:\[not live_keycloak\]' "$PYTHON_PROBE_LOG" && ! grep -q 'ARG:\[not\]' "$PYTHON_PROBE_LOG"; then
  ok "quoting probe: pytest received ONE argument 'not live_keycloak' (no bare 'not' arg) through PowerShell -> Invoke-Native -> stub docker -> sh -c (a)"
else
  bad "quoting probe: pytest did NOT receive one 'not live_keycloak' argument (see $PYTHON_PROBE_LOG)"
  grep 'ARG:' "$PYTHON_PROBE_LOG" | head -20
fi
if python3 -c "import json; d=json.load(open('$SCRATCH/tree/test-results/gates.json')); ids=[g['id'] for g in d['gates']]; assert len(ids)==19, len(ids); assert d['summary']=={'PASS':11,'FAIL':0,'NOT RUN':7,'NOT APPLICABLE':1}, d['summary']; assert [g for g in d['gates'] if g['id']=='LIVE_PROVIDER_PYTEST'][0]['status']=='NOT RUN'" 2>/dev/null; then
  ok "stub -Offline run wrote gates.json: 19 gates, 11 PASS / 0 FAIL / 7 NOT RUN / 1 NOT APPLICABLE (GHSA superseded by the clean stub audit), LIVE_PROVIDER_PYTEST NOT RUN"
else
  bad "stub -Offline run gates.json is not 19 gates / 11 PASS / 7 NOT RUN / 1 NOT APPLICABLE with LIVE_PROVIDER_PYTEST NOT RUN (rc=$RC)"
  python3 -c "import json; print(json.load(open('$SCRATCH/tree/test-results/gates.json'))['summary'])" 2>/dev/null || echo "(no gates.json)"
fi

# --- (d) runtime teardown probe: -Full with a failing cold-start up -------
# Sandbox quirk: pwsh 7.4.6 TcpClient connects to ANY loopback port
# here (even dead 59999 — Python sockets correctly refuse), so
# test-all.ps1 -Full can never pass its port preflight in this
# sandbox and the runtime probe cannot execute here. Detect it: on
# Windows (or a sane Linux) TcpClient throws on a dead port and the
# probe runs. The static (d) checks above still run everywhere.
PWSH_LOOPBACK_BROKEN=0
if "$PWSH" -NoProfile -Command 'try { $c = New-Object System.Net.Sockets.TcpClient("127.0.0.1", 59999); $c.Close(); exit 0 } catch { exit 1 }' >/dev/null 2>&1; then
  PWSH_LOOPBACK_BROKEN=1
fi
if [ "$PWSH_LOOPBACK_BROKEN" = "1" ]; then
  skip "runtime teardown probe: this sandbox's pwsh TcpClient connects to any loopback port (even dead 59999), so test-all.ps1 -Full always fails its port preflight here; static checks above still cover (d); run on Windows for the runtime proof"
elif port_busy 8080 || port_busy 8000 || port_busy 5173; then
  skip "runtime teardown probe: ports 8080/8000/5173 not all free (full preflight would refuse); static checks above still cover (d)"
else
  : > "$DOCKER_STUB_LOG"
  (cd "$SCRATCH/tree" && rm -rf test-results && PATH="$FAKEBIN:$PATH" DOCKER_STUB_LOG="$DOCKER_STUB_LOG" PYTHON_PROBE_LOG="$PYTHON_PROBE_LOG" DOCKER_UP_FAIL=1 "$PWSH" -NoProfile -File scripts/test-all.ps1 -Full > "$SCRATCH/full-stub.log" 2>&1)
  RC=$?
  DOWN_LINES="$(grep -c 'DOCKER-ARGV:.* <down>' "$DOCKER_STUB_LOG" || true)"
  DOWN_SCOPED="$(grep -c 'DOCKER-ARGV:.* <-p> <identityforge-coldstart-[0-9]*> <down> <-v>' "$DOCKER_STUB_LOG" || true)"
  if [ "$RC" -ne 0 ] && [ "$DOWN_LINES" = "1" ] && [ "$DOWN_SCOPED" = "1" ]; then
    ok "runtime teardown probe: -Full with failing cold-start up exits $RC and issues exactly one 'down', scoped '-p identityforge-coldstart-* down -v' (d)"
  else
    bad "runtime teardown probe failed (rc=$RC, down lines=$DOWN_LINES, scoped=$DOWN_SCOPED); stub argv log:"
    grep 'DOCKER-ARGV' "$DOCKER_STUB_LOG" | grep -E 'down|volume|prune|kill' || echo "(no destructive argv logged)"
  fi
  if grep -qE 'DOCKER-ARGV:.* <(volume|prune|kill|rm)>' "$DOCKER_STUB_LOG"; then
    bad "runtime probe logged a destructive command outside the disposable project (d)"
  else
    ok "runtime probe logged no volume/prune/kill/rm command (d)"
  fi
  if python3 -c "import json; d=json.load(open('$SCRATCH/tree/test-results/gates.json')); g=[x for x in d['gates'] if x['id']=='LIVE_PROVIDER_PYTEST'][0]; assert g['status']=='NOT RUN', g" 2>/dev/null; then
    ok "runtime probe: LIVE_PROVIDER_PYTEST is NOT RUN when the cold-start boot failed (never PASS)"
  else
    bad "runtime probe: LIVE_PROVIDER_PYTEST is not NOT RUN after a failed cold-start boot"
  fi
fi

echo "ps1-selection: $PASS passed, $FAIL failed, $SKIP skipped"
[ "$FAIL" -eq 0 ]
