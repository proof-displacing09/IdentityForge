#!/usr/bin/env bash
# IdentityForge doctor — check lab health and report honest status.
# Exits 0 only when backend + Keycloak + frontend all answer on loopback
# AND prove their identity (P1-21) AND the backend can actually reach
# the IdP with the canonical issuer (P0-05): a bare HTTP 200 from any
# process squatting on the port is NOT enough, and a healthy-looking
# host is NOT enough if the backend cannot contact Keycloak. Uses only
# 127.0.0.1.
#   - Keycloak: discovery JSON must carry the canonical issuer exactly.
#   - Backend: /api/v1/health must name service identityforge-backend.
#   - Frontend: the HTML must contain the IdentityForge app root.
#   - Readiness: /api/v1/lab/status must report idp.reachable=true
#     AND idp.issuer_matches=true (measured from the BACKEND).
# Also prints the measured lab status (IdP reachability, issuer match,
# last verified real login) so "healthy" is never confused with
# "a real login was verified".
#   ./scripts/doctor.sh [--brief]   --brief prints one line: READY or
#   NOT READY: <reasons>, with the same exit code.
set -uo pipefail

cd "$(dirname "$0")/.."

BRIEF=0
for arg in "$@"; do
  case "$arg" in
    --brief) BRIEF=1 ;;
    --help|-h)
      echo "Usage: $0 [--brief]"
      exit 0 ;;
    *) echo "doctor.sh: unknown argument: $arg" >&2; exit 2 ;;
  esac
done

say() { [ "$BRIEF" -eq 0 ] && echo "$*"; }

status=0
REASONS=""
fail() { status=1; REASONS="$REASONS $1"; }

say "== IdentityForge doctor =="
say "Checking loopback services only (127.0.0.1)..."
say ""

if command -v docker >/dev/null 2>&1 && docker compose ps >/dev/null 2>&1; then
  say "$(docker compose ps)"
  say ""
else
  say "NOTE: Docker / 'docker compose' not available or lab not started."
  say "      (Offline fixture tests do not need Docker; see ./scripts/test-all.sh.)"
fi

# Keycloak: discovery must return the canonical issuer, not just 200.
KC_JSON="$(curl -s --max-time 10 http://127.0.0.1:8080/realms/identityforge-lab/.well-known/openid-configuration 2>/dev/null || true)"
if [ -n "$KC_JSON" ] && python3 -c "
import json, sys
d = json.loads(sys.argv[1])
assert d.get('issuer') == 'http://127.0.0.1:8080/realms/identityforge-lab', d.get('issuer')
" "$KC_JSON" 2>/dev/null; then
  say "OK   Keycloak OIDC discovery  (issuer exactly http://127.0.0.1:8080/realms/identityforge-lab)"
else
  say "FAIL Keycloak OIDC discovery  (no discovery JSON with the canonical issuer on 127.0.0.1:8080)"
  fail "keycloak-discovery"
fi

# Backend: health JSON must name this service.
BE_JSON="$(curl -s --max-time 10 http://127.0.0.1:8000/api/v1/health 2>/dev/null || true)"
if [ -n "$BE_JSON" ] && python3 -c "
import json, sys
d = json.loads(sys.argv[1])
assert d.get('service') == 'identityforge-backend', d.get('service')
assert d.get('status') == 'ok'
" "$BE_JSON" 2>/dev/null; then
  say "OK   Backend health  (service identityforge-backend, status ok)"
else
  say "FAIL Backend health  (no identityforge-backend health JSON on 127.0.0.1:8000)"
  fail "backend-health"
fi

# Frontend: the served HTML must be the IdentityForge app.
FE_HTML="$(curl -s --max-time 10 http://127.0.0.1:5173/ 2>/dev/null || true)"
if [ -n "$FE_HTML" ] && echo "$FE_HTML" | grep -q 'id="root"'; then
  say "OK   Frontend  (IdentityForge app root served on 127.0.0.1:5173)"
else
  say "FAIL Frontend  (no IdentityForge app root on 127.0.0.1:5173)"
  fail "frontend"
fi

# Readiness (P0-05): the BACKEND must be able to reach the IdP and see
# the canonical issuer. This is measured from the backend's point of
# view (/api/v1/lab/status), not from the host running this script:
# the host can reach Keycloak while the container cannot (transport
# problem), and the doctor must not call that READY.
say ""
LAB="$(curl -s --max-time 10 http://127.0.0.1:8000/api/v1/lab/status 2>/dev/null || true)"
if [ -n "$LAB" ]; then
  if [ "$BRIEF" -eq 0 ]; then
    say "Measured lab status:"
    echo "$LAB" | python3 -c "
import json, sys
d = json.load(sys.stdin)
idp = d.get('idp', {})
print(f\"  IdP reachable: {idp.get('reachable')}  issuer matches: {idp.get('issuer_matches')}  reason: {idp.get('reason')}\")
last = d.get('last_verified_login')
if last:
    print(f\"  Last verified real login: {last.get('at')} user={last.get('username')}\")
else:
    print('  Last verified real login: NONE YET (no real login verified by this backend process)')
" 2>/dev/null || say "  (lab status response is not valid JSON)"
  fi
  if echo "$LAB" | python3 -c "
import json, sys
d = json.load(sys.stdin)
idp = d.get('idp', {})
assert idp.get('reachable') is True and idp.get('issuer_matches') is True
" 2>/dev/null; then
    say "OK   IdP readiness  (backend reaches Keycloak, issuer matches)"
  else
    say "FAIL IdP readiness  (backend cannot reach Keycloak with the canonical issuer — see idp.reason above)"
    fail "idp-not-ready"
  fi
else
  say "FAIL IdP readiness  (no /api/v1/lab/status from the backend)"
  fail "idp-unknown"
fi

say ""
if [ "$BRIEF" -eq 1 ]; then
  if [ "$status" -eq 0 ]; then
    echo "READY"
  else
    echo "NOT READY:${REASONS}"
  fi
  exit "$status"
fi

if [ "$status" -eq 0 ]; then
  echo "All services healthy and identified."
  echo "Portal: http://127.0.0.1:5173"
  echo "(Healthy services are not proof of a real login: run"
  echo " ./scripts/test-all.sh --full or python3 scripts/live-gate.py all.)"
else
  echo "Some services are NOT healthy."
  echo "Troubleshooting: see README.md 'Troubleshooting' and"
  echo "docs/WINDOWS_SETUP.md. Common causes:"
  echo "  - Keycloak needs 60-120s on first boot; re-run ./scripts/doctor.sh after waiting."
  echo "  - If the host can reach Keycloak but the BACKEND cannot (IdP"
  echo "    readiness FAIL above), that is a backend-to-Keycloak"
  echo "    TRANSPORT problem (Compose service DNS / network), not a"
  echo "    'wait longer' problem — check the backend logs and the"
  echo "    IDENTITYFORGE_IDP_TRANSPORT_BASE route (keycloak:8080)."
fi
exit "$status"
