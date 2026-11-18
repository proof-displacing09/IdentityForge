#!/usr/bin/env bash
# IdentityForge offline/provider selection regression (IF-V8.0.2-B, v8.0.2).
#
# Proves the v8.0.1 defect is fixed: the four provider-dependent pytest
# tests (marked live_keycloak) failed the offline gates with 503
# PROVIDER_UNAVAILABLE whenever no Keycloak ran, because every offline
# runner invoked unfiltered `python -m pytest -q` while labelling the
# gate OFFLINE. Reproduced v8.0.1: the four tests fail with Keycloak
# absent; verify-release on a fresh extraction reads 22 PASS / 1 FAIL /
# 5 NOT RUN, sole FAIL BACKEND_PYTEST.
#
#   (a) The default offline selection succeeds WITHOUT a provider on
#       correctly functioning code: `pytest -q -m "not live_keycloak"`
#       passes with nothing listening on 127.0.0.1:8080, and the
#       deselected set is exactly the four marked tests.
#   (b) The genuine live integration lane still runs all four security
#       tests: the wiring is asserted statically in every mode
#       (LIVE_PROVIDER_PYTEST gate in test-all.sh --full, keycloak-e2e
#       lane runs test-all.sh --full --strict), and `--live` runs the
#       four tests against a live provider and requires 4 passed.
#
# Usage:
#   bash scripts/test-offline-provider-selection.sh          # offline mode (CI-safe)
#   bash scripts/test-offline-provider-selection.sh --live   # live mode (needs Keycloak on 8080)
#
# Offline mode REFUSES to run if something answers on 127.0.0.1:8080:
# the no-provider proof is only meaningful with no provider present.
# Live mode REFUSES to run unless discovery on 8080 returns 200 with
# the canonical issuer: a skipped live run must never read as a pass.
#
# No Docker daemon is needed. A disposable venv is built in a temp dir
# from backend/requirements-freeze.txt (PyPI, like the WS3 CI step) and
# deleted afterwards; the tree's own .venv is never touched. No
# login-heavy suites run here: the four live tests use TestClient apps
# with temp DBs, never the persistent lab backend.
set -uo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PASS=0
FAIL=0

ok()  { echo "PASS: $1"; PASS=$((PASS + 1)); }
bad() { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }

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

provider_up() { # true when discovery on 8080 answers at all
  (exec 3<>/dev/tcp/127.0.0.1/8080) 2>/dev/null
}

if [ "$LIVE" -eq 0 ]; then
  if provider_up; then
    echo "FAIL: something listens on 127.0.0.1:8080 — stop Keycloak first; the offline no-provider proof needs no provider present"
    echo "offline-provider-selection: 0 passed, 1 failed"
    exit 1
  fi
  ok "no provider on 127.0.0.1:8080 (offline no-provider precondition holds)"
else
  if ! curl -fsS -o /tmp/ws2-v802-live-disc.json http://127.0.0.1:8080/realms/identityforge-lab/.well-known/openid-configuration 2>/dev/null \
      || ! grep -q '"issuer":"http://127.0.0.1:8080/realms/identityforge-lab"' /tmp/ws2-v802-live-disc.json; then
    echo "FAIL: live Keycloak discovery on 8080 is not 200 with the canonical issuer — start the lab first; a skipped live run must never read as a pass"
    echo "offline-provider-selection: 0 passed, 1 failed"
    exit 1
  fi
  ok "live Keycloak discovery 200 with the canonical issuer (live precondition holds)"
fi

# --- Static wiring: the selection is named the same way everywhere ------
grep -q 'python -m pytest -q -m .not live_keycloak.' .github/workflows/ci.yml \
  && ok "CI backend lane runs the offline selection (-m 'not live_keycloak')" \
  || bad "CI backend lane does not run the offline selection"
grep -q 'test-all.sh --full --strict' .github/workflows/ci.yml \
  && ok "CI keycloak-e2e lane runs test-all.sh --full --strict" \
  || bad "CI keycloak-e2e lane does not run test-all.sh --full --strict"
grep -q 'LIVE_PROVIDER_PYTEST' scripts/test-all.sh \
  && grep -q 'pytest -q -m live_keycloak' scripts/test-all.sh \
  && ok "test-all.sh --full defines LIVE_PROVIDER_PYTEST running -m live_keycloak" \
  || bad "test-all.sh --full has no LIVE_PROVIDER_PYTEST gate running -m live_keycloak"
grep -q 'pytest -q -m \\"not live_keycloak\\"' scripts/test-all.sh \
  && ok "test-all.sh OFFLINE_UNIT runs the offline selection" \
  || bad "test-all.sh OFFLINE_UNIT does not run the offline selection"
grep -q 'pytest -q -m "not live_keycloak"' scripts/verify-release.sh \
  && ok "verify-release BACKEND_PYTEST runs the offline selection" \
  || bad "verify-release BACKEND_PYTEST does not run the offline selection"
grep -q 'live_keycloak' backend/pytest.ini \
  && ok "backend/pytest.ini registers the live_keycloak marker" \
  || bad "backend/pytest.ini does not register the live_keycloak marker"

# --- Disposable venv (freeze only; Hypothesis not needed here) ------------
VENV="$(mktemp -d)/venv"
cleanup() { rm -rf "$(dirname "$VENV")"; }
trap cleanup EXIT
python3 -m venv "$VENV" || { bad "venv creation failed"; echo "offline-provider-selection: $PASS passed, $((FAIL + 1)) failed"; exit 1; }
"$VENV/bin/pip" install -q -r backend/requirements-freeze.txt || { bad "pip install of backend/requirements-freeze.txt failed"; echo "offline-provider-selection: $PASS passed, $((FAIL + 1)) failed"; exit 1; }
PY="$VENV/bin/python"

# --- Counts: total = offline + live, live set is exactly the four -------
# Non-quiet --collect-only lists one node ID per line, so the counts are
# counted node IDs, never parsed summary text (the -q per-file form and
# the summary line move after the warnings block). No count is
# hardcoded: WS1's Fix A work lands in the same tree and moves the
# total; only the live set (exactly 4) is pinned.
cd backend
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

# --- (a) offline mode: the offline selection passes with no provider -----
if [ "$LIVE" -eq 0 ]; then
  if "$PY" -m pytest -q -m "not live_keycloak" > /tmp/ws2-v802-offline-run.log 2>&1; then
    ok "offline selection passes with no provider ($OFFLINE_COUNT tests, rc=0)"
  else
    bad "offline selection FAILED with no provider (see /tmp/ws2-v802-offline-run.log)"
    tail -5 /tmp/ws2-v802-offline-run.log
  fi
fi

# --- (b) live mode: the four marked tests pass against the provider ------
if [ "$LIVE" -eq 1 ]; then
  if "$PY" -m pytest -q -m live_keycloak > /tmp/ws2-v802-live-run.log 2>&1; then
    ok "live selection passes against the live provider (4 tests, rc=0)"
  else
    bad "live selection FAILED against the live provider (see /tmp/ws2-v802-live-run.log)"
    tail -5 /tmp/ws2-v802-live-run.log
  fi
fi

cd "$ROOT"
echo "offline-provider-selection: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
