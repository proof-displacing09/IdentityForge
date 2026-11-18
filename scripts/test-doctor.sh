#!/usr/bin/env bash
# IdentityForge doctor tests (P0-05).
#
# Drives ./scripts/doctor.sh against a stub lab (scripts/test-doctor-stub.py,
# stdlib only — no Docker or Keycloak needed) and asserts the readiness
# gating:
#   1. Stub IdP reachable=false -> doctor MUST exit nonzero (and
#      --brief prints NOT READY). A host that answers is not enough
#      when the backend reports the IdP unreachable.
#   2. Stub reachable=true + issuer_matches=true + all three identity
#      checks passing -> exit 0, and --brief prints exactly READY.
#   3. Dummy-200 squatter on 5173/8080/8000 -> exit nonzero (the v2
#      negative behaviour is preserved).
#   4. reachable=true + issuer_matches=false -> exit nonzero (issuer
#      mismatch alone fails readiness).
#   5. Nothing listening -> exit nonzero.
#
# The PowerShell mirror (doctor.ps1) cannot be executed in this sandbox
# (no PowerShell here); it is the same logic and is reviewer-gated on
# Windows. Run: ./scripts/test-doctor.sh
#
# The stub must OWN 8080/8000/5173. If the real lab (or anything else)
# already holds them, the stub cannot bind and the wait loop below
# would be fooled by the real services answering — the negative cases
# would then fail falsely. Skip honestly instead of reporting false
# FAILs: stop the lab first, or run in a network namespace.
for port in 8080 8000 5173; do
  if (exec 3<>/dev/tcp/127.0.0.1/$port) 2>/dev/null; then
    echo "SKIP: port $port is already listening (the lab is running?) — the stub cannot own the lab ports."
    echo "Stop the lab first (docker compose down) or run: unshare -rn bash -c 'bash scripts/test-doctor.sh'"
    echo "doctor: 0 passed, 0 failed, 1 skipped"
    exit 0
  fi
done
set -uo pipefail

cd "$(dirname "$0")/.."
PASS=0
FAIL=0

ok()  { echo "PASS: $1"; PASS=$((PASS + 1)); }
bad() { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }

STUB_PID=""
stop_stub() {
  if [ -n "$STUB_PID" ]; then kill "$STUB_PID" 2>/dev/null; wait "$STUB_PID" 2>/dev/null || true; STUB_PID=""; fi
}
trap stop_stub EXIT

start_stub() {  # args passed to the stub
  stop_stub
  python3 scripts/test-doctor-stub.py "$@" > /tmp/if-doctor-stub.log 2>&1 &
  STUB_PID=$!
  for _ in $(seq 1 20); do
    curl -fsS http://127.0.0.1:8000/api/v1/health >/dev/null 2>&1 && return 0
    curl -fsS http://127.0.0.1:5173/ >/dev/null 2>&1 && return 0
    sleep 0.25
  done
  echo "doctor test: stub did not come up ($*)" >&2
  cat /tmp/if-doctor-stub.log >&2
  return 1
}

# --- 1. IdP unreachable from the backend -> doctor MUST fail ---------------
start_stub --reachable false --issuer-matches false
if ./scripts/doctor.sh > /tmp/if-doctor-1.log 2>&1; then
  bad "doctor should fail when the stub reports idp.reachable=false"
  cat /tmp/if-doctor-1.log
else
  ok "doctor fails when stub reports idp.reachable=false"
fi
BRIEF_OUT="$(./scripts/doctor.sh --brief 2>/dev/null || true)"
if echo "$BRIEF_OUT" | grep -q "^NOT READY"; then
  ok "doctor --brief prints NOT READY when IdP unreachable"
else
  bad "doctor --brief should print NOT READY when IdP unreachable (got: '$BRIEF_OUT')"
fi
if grep -q "FAIL IdP readiness" /tmp/if-doctor-1.log; then
  ok "doctor names the failing IdP readiness check"
else
  bad "doctor should name the failing IdP readiness check"
fi

# --- 2. Fully ready stub -> exit 0, --brief prints READY --------------------
start_stub --reachable true --issuer-matches true
if ./scripts/doctor.sh > /tmp/if-doctor-2.log 2>&1; then
  ok "doctor passes when stub is fully ready (identity + IdP reachable + issuer matches)"
else
  bad "doctor should pass when stub is fully ready"
  cat /tmp/if-doctor-2.log
fi
BRIEF_OUT="$(./scripts/doctor.sh --brief 2>/dev/null)"
if [ "$BRIEF_OUT" = "READY" ]; then
  ok "doctor --brief prints exactly READY when fully ready"
else
  bad "doctor --brief should print exactly READY (got: '$BRIEF_OUT')"
fi

# --- 3. Dummy-200 squatter -> exit nonzero -----------------------------------
start_stub --squatter
if ./scripts/doctor.sh > /tmp/if-doctor-3.log 2>&1; then
  bad "doctor should fail a dummy-200 squatter on 5173/8080/8000"
  cat /tmp/if-doctor-3.log
else
  ok "doctor fails a dummy-200 squatter (identity checks, not bare 200)"
fi

# --- 4. Issuer mismatch alone -> exit nonzero --------------------------------
start_stub --reachable true --issuer-matches false
if ./scripts/doctor.sh > /tmp/if-doctor-4.log 2>&1; then
  bad "doctor should fail when issuer_matches=false even if reachable=true"
  cat /tmp/if-doctor-4.log
else
  ok "doctor fails when issuer_matches=false (reachable alone is not READY)"
fi

# --- 5. Nothing listening -> exit nonzero ------------------------------------
stop_stub
sleep 0.5
if ./scripts/doctor.sh > /tmp/if-doctor-5.log 2>&1; then
  bad "doctor should fail when nothing is listening"
else
  ok "doctor fails when nothing is listening"
fi

echo
echo "doctor: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
