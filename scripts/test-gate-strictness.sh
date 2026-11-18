#!/usr/bin/env bash
# IdentityForge gate-strictness negative test (P0-03).
#
# Proves the release gates cannot produce a green banner while a
# mandatory gate was skipped:
#   1. test-all.sh --full with Docker made unavailable -> exit != 0,
#      output names the NOT RUN live gates.
#   2. test-all.sh --offline --strict with a fake `npm` that reports
#      a clean audit -> exit 0 (offline gates pass). The fake is
#      needed because the real npm audit endpoint is blocked in this
#      sandbox (proxy 403), which correctly makes
#      NPM_FULL_LOCKFILE_AUDIT NOT RUN and a strict run fail closed.
#   3. verify-release.sh --strict on a tree with a required file
#      deleted -> exit != 0.
#   4. verify-release.sh on the good tree -> exit 0.
#   5. Blocked npm audit + clean GHSA fallback (seeded cache) ->
#      strict mode still FAILS (exit != 0) because
#      NPM_FULL_LOCKFILE_AUDIT is NOT RUN: the direct-only fallback
#      never satisfies the full audit.
#   6. npm audit reporting a TRANSITIVE-only advisory (fake report
#      naming lru-cache) -> NPM_FULL_LOCKFILE_AUDIT FAIL, strict
#      exit != 0, and GHSA_DIRECT_FALLBACK is NOT APPLICABLE (P1-05:
#      the full audit executed, so the fallback did not run and must
#      never be marked PASS beside a failed audit).
#   7. npm audit failing with an UNKNOWN error (exit 2, no blocked-
#      endpoint text) -> NPM_FULL_LOCKFILE_AUDIT NOT RUN with the
#      precise rc in the detail, strict exit != 0; the GHSA fallback
#      may run honestly from a seeded cache but cannot mask the
#      missing full audit (P1-05 case 5).
#   8. npm audit emitting MALFORMED (non-JSON) output -> CHECK_FAILED,
#      NPM_FULL_LOCKFILE_AUDIT NOT RUN, strict exit != 0 (IF-V4-09).
#   9. verify-release --strict on a tree where the Keycloak
#      healthcheck '$$resp' was reverted to '$resp' -> exit != 0
#      (IF-V4-01 static regression: the Compose interpolation trap
#      must fail the release audit).
#
# Docker is hidden via a stub executable that fails every invocation,
# simulating an environment where the Docker CLI cannot run (the same
# condition as a machine without Docker). No real Docker state is
# touched. Run: ./scripts/test-gate-strictness.sh
set -uo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PASS=0
FAIL=0

ok()   { echo "PASS: $1"; PASS=$((PASS + 1)); }
bad()  { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }

gate_status() {  # $1 = gates.json, $2 = gate id -> status
  python3 -c "import json,sys; print({g['id']: g['status'] for g in json.load(open(sys.argv[1]))['gates']}.get(sys.argv[2], 'MISSING'))" "$1" "$2"
}

# Fake npm: `npm audit` behaviour from FAKE_NPM_AUDIT, everything else
# delegates to the real npm. Written into a temp bin dir by the caller.
# IF-V4-09 (v5): audit output is the JSON report the real
# `npm audit --json` produces, so the classifier is exercised.
write_fake_npm() {  # $1 = dir, $2 = audit mode (clean|blocked|vuln|malformed|crash)
  local dir="$1" mode="$2" real_npm="$3"
  cat > "$dir/npm" <<EOF
#!/usr/bin/env bash
if [ "\$1" = "audit" ]; then
  case "$mode" in
    clean) echo '{"auditReportVersion":2,"vulnerabilities":{},"metadata":{"vulnerabilities":{"info":0,"low":0,"moderate":0,"high":0,"critical":0,"total":0},"dependencies":{"prod":1,"dev":0,"optional":0,"peer":0,"peerOptional":0,"total":1}}}'; exit 0 ;;
    blocked)
      echo '{"error":{"code":"E403","summary":"403 Forbidden - GET https://registry.npmjs.org/-/npm/v1/security/audits/quick","detail":"audit endpoint returned an error policy_denied"}}'
      exit 1 ;;
    vuln)
      echo '{"auditReportVersion":2,"vulnerabilities":{"lru-cache":{"name":"lru-cache","severity":"high","via":[{"source":1089785,"name":"lru-cache","dependency":"lru-cache","title":"Regular Expression Denial of Service","url":"https://github.com/advisories/GHSA-xxxx-yyyy-zzzz","severity":"high","range":">=0.0.0 <10.4.0"}]}},"metadata":{"vulnerabilities":{"info":0,"low":1,"moderate":0,"high":1,"critical":0,"total":2},"dependencies":{"prod":1,"dev":0,"optional":0,"peer":0,"peerOptional":0,"total":1}}}'
      exit 1 ;;
    malformed)
      # Not JSON at all: the classifier must report CHECK_FAILED and
      # the gate must be NOT RUN, never a finding or a clean pass.
      echo "npm error: something unexpected broke (not JSON at all)"
      exit 1 ;;
    crash)
      # Unknown failure: non-1/non-124 exit, no blocked-endpoint text.
      # The runner must record NOT RUN with the precise rc, never a
      # clean fallback that masks the unknown error (P1-05 case 5).
      echo "npm error: something unexpected broke (exit 2, no audit report)"
      exit 2 ;;
  esac
fi
exec "$real_npm" "\$@"
EOF
  chmod +x "$dir/npm"
}

# Seed a fresh GHSA cache covering the current lockfile pins, so the
# fallback returns clean without API calls (the script's designed
# 24h-cache reuse path). Removed by the caller after the step.
seed_ghsa_cache() {
  python3 - "$ROOT" <<'PY'
import importlib.util, json, sys, time
spec = importlib.util.spec_from_file_location(
    "nac", sys.argv[1] + "/scripts/npm-advisory-check.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
pins = m.resolved_pins()
now = int(time.time())
report = {
    "source": "GitHub Advisory Database (api.github.com/advisories)",
    "coverage": "direct dependencies only; transitive advisories require npm audit",
    "transitive_dependencies_examined": False,
    "checked_at_epoch": now,
    "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
    "pins": pins, "packages_checked": len(pins),
    "high_critical_count": 0, "unreachable": [],
    "results": [{"package": n, "version": v, "resolved_version": v,
                 "source": "GitHub Advisory Database (api.github.com/advisories)",
                 "advisories": []} for n, v in sorted(pins.items())],
}
open("test-results/audit-frontend-ghsa.json", "w").write(json.dumps(report, indent=2) + "\n")
print(f"seeded GHSA cache: {len(pins)} direct pins, 0 advisories")
PY
}

# --- 1. --full with Docker unavailable must fail and name the gates ------
# Only `docker` is shadowed (stub first on PATH); every other tool
# stays available, so the frontend gates genuinely run and the failure
# is attributable to the missing Docker daemon, not to a hidden npm.
STUB_BIN="$(mktemp -d)"
cat > "$STUB_BIN/docker" <<'EOF'
#!/usr/bin/env bash
echo "docker: command not found (stub for gate-strictness test)" >&2
exit 127
EOF
chmod +x "$STUB_BIN/docker"
OUT="$(PATH="$STUB_BIN:$PATH" ./scripts/test-all.sh --full 2>&1)"
RC=$?
if [ "$RC" -ne 0 ] && echo "$OUT" | grep -q "NOT RUN" && echo "$OUT" | grep -q "REAL_KEYCLOAK_LOGIN"; then
  ok "--full with Docker hidden exits nonzero and names NOT RUN live gates"
else
  bad "--full with Docker hidden should fail naming NOT RUN gates (rc=$RC)"
  echo "$OUT" | tail -20
fi
rm -rf "$STUB_BIN"

# --- 2. --offline --strict passes when offline gates pass ------------------
# Fake npm reports a clean audit (the real endpoint is proxy-blocked
# here); pip-audit runs for real. The GHSA fallback is NOT APPLICABLE
# (P1-05): the full audit executed, so the fallback did not run — and
# the strict run still passes, because NOT APPLICABLE is not a
# required NOT RUN.
FAKEBIN="$(mktemp -d)"
write_fake_npm "$FAKEBIN" clean "$(command -v npm)"
if PATH="$FAKEBIN:$PATH" ./scripts/test-all.sh --offline --strict >/tmp/if-strict-offline.log 2>&1; then
  if [ "$(gate_status test-results/gates.json GHSA_DIRECT_FALLBACK)" = "NOT APPLICABLE" ]; then
    ok "--offline --strict passes (offline gates green, fake clean npm audit, GHSA NOT APPLICABLE)"
  else
    bad "--offline --strict passed but GHSA should be NOT APPLICABLE, got $(gate_status test-results/gates.json GHSA_DIRECT_FALLBACK)"
  fi
else
  bad "--offline --strict should pass"
  tail -20 /tmp/if-strict-offline.log
fi
rm -rf "$FAKEBIN"

# --- 3. verify-release --strict fails on a missing required file -----------
TMP="$(mktemp -d)"
cp -r "$ROOT" "$TMP/tree"
rm "$TMP/tree/docs/UI_DESIGN_SYSTEM.md"
rm -f "$TMP/tree/backend/data/identityforge.db"  # runtime state, not the test subject
if (cd "$TMP/tree" && ./scripts/verify-release.sh --strict >/tmp/if-vr-strict.log 2>&1); then
  bad "verify-release --strict should fail when a required file is missing"
else
  ok "verify-release --strict fails on missing required file"
fi
rm -rf "$TMP"

# --- 4. verify-release on a fresh packaged tree passes ----------------------
# Mirror the real reviewer flow: copy with the packaging exclusion set
# (no venv, node_modules, test-results, runtime DB or egg-info), then
# run verify-release there.
TMP="$(mktemp -d)"
tar --exclude='.venv' --exclude='node_modules' --exclude='test-results' \
  --exclude='backend/data' --exclude='*.egg-info' --exclude='frontend/dist' \
  --exclude='.git' -cf - . | (cd "$TMP" && tar xf -)
if (cd "$TMP" && ./scripts/verify-release.sh >/tmp/if-vr-good.log 2>&1); then
  ok "verify-release passes on a fresh packaged tree"
else
  bad "verify-release should pass on a fresh packaged tree"
  tail -20 /tmp/if-vr-good.log
fi
rm -rf "$TMP"

# --- 5. Blocked npm audit + clean GHSA fallback must still FAIL strict -----
# The fallback is direct-deps-only; NPM_FULL_LOCKFILE_AUDIT stays
# NOT RUN and --offline --strict must fail closed on it.
FAKEBIN="$(mktemp -d)"
write_fake_npm "$FAKEBIN" blocked "$(command -v npm)"
seed_ghsa_cache
PATH="$FAKEBIN:$PATH" ./scripts/test-all.sh --offline --strict >/tmp/if-strict-blocked.log 2>&1
RC=$?
rm -f test-results/audit-frontend-ghsa.json  # seeded cache: do not leave behind
if [ "$RC" -ne 0 ] \
    && [ "$(gate_status test-results/gates.json NPM_FULL_LOCKFILE_AUDIT)" = "NOT RUN" ] \
    && [ "$(gate_status test-results/gates.json GHSA_DIRECT_FALLBACK)" = "PASS" ]; then
  ok "blocked npm audit + clean GHSA fallback still FAILS strict (NPM_FULL NOT RUN, GHSA PASS)"
else
  bad "blocked npm audit + clean GHSA fallback should fail strict with NPM_FULL NOT RUN / GHSA PASS (rc=$RC)"
  tail -20 /tmp/if-strict-blocked.log
fi
rm -rf "$FAKEBIN"

# --- 6. Transitive-only advisory must FAIL the full audit, not be masked ---
# Fake npm audit reports a vulnerability in transitive lru-cache only.
# The full audit executed, so the GHSA fallback is NOT APPLICABLE
# (P1-05) — it must never be marked PASS beside a failed full audit.
FAKEBIN="$(mktemp -d)"
write_fake_npm "$FAKEBIN" vuln "$(command -v npm)"
PATH="$FAKEBIN:$PATH" ./scripts/test-all.sh --offline --strict >/tmp/if-strict-vuln.log 2>&1
RC=$?
if [ "$RC" -ne 0 ] \
    && [ "$(gate_status test-results/gates.json NPM_FULL_LOCKFILE_AUDIT)" = "FAIL" ] \
    && [ "$(gate_status test-results/gates.json GHSA_DIRECT_FALLBACK)" = "NOT APPLICABLE" ] \
    && grep -q "lru-cache" test-results/audit-frontend.log; then
  ok "transitive-only advisory FAILS NPM_FULL_LOCKFILE_AUDIT (GHSA NOT APPLICABLE, not masked)"
else
  bad "transitive-only advisory should FAIL NPM_FULL_LOCKFILE_AUDIT with GHSA NOT APPLICABLE (rc=$RC)"
  tail -20 /tmp/if-strict-vuln.log
fi
rm -rf "$FAKEBIN"

# --- 7. Unknown npm audit error must NOT RUN with precise evidence ---------
# Fake npm exits 2 with generic text (no blocked-endpoint markers).
# NPM_FULL_LOCKFILE_AUDIT must be NOT RUN with the rc in the detail;
# the GHSA fallback may run from a seeded cache and PASS honestly, but
# strict must still FAIL on the missing full audit — never a clean
# fallback masking an unknown error (P1-05 case 5).
FAKEBIN="$(mktemp -d)"
write_fake_npm "$FAKEBIN" crash "$(command -v npm)"
seed_ghsa_cache
PATH="$FAKEBIN:$PATH" ./scripts/test-all.sh --offline --strict >/tmp/if-strict-crash.log 2>&1
RC=$?
rm -f test-results/audit-frontend-ghsa.json  # seeded cache: do not leave behind
if [ "$RC" -ne 0 ] \
    && [ "$(gate_status test-results/gates.json NPM_FULL_LOCKFILE_AUDIT)" = "NOT RUN" ] \
    && python3 -c "import json,sys; print({g['id']: g['detail'] for g in json.load(open('test-results/gates.json'))['gates']}.get('NPM_FULL_LOCKFILE_AUDIT',''))" | grep -q "rc=2"; then
  ok "unknown npm audit error (rc=2) records NPM_FULL NOT RUN with precise evidence, strict FAILS"
else
  bad "unknown npm audit error should record NPM_FULL NOT RUN with rc=2 and fail strict (rc=$RC)"
  tail -20 /tmp/if-strict-crash.log
fi
rm -rf "$FAKEBIN"

# --- 8. Malformed npm audit output must NOT RUN as CHECK_FAILED --------
# Fake npm emits garbage (not JSON). The classifier reports
# CHECK_FAILED; NPM_FULL_LOCKFILE_AUDIT is NOT RUN and strict fails.
# The GHSA fallback may run from a seeded cache and PASS honestly,
# but it cannot mask the missing full audit.
FAKEBIN="$(mktemp -d)"
write_fake_npm "$FAKEBIN" malformed "$(command -v npm)"
seed_ghsa_cache
PATH="$FAKEBIN:$PATH" ./scripts/test-all.sh --offline --strict >/tmp/if-strict-malformed.log 2>&1
RC=$?
rm -f test-results/audit-frontend-ghsa.json  # seeded cache: do not leave behind
if [ "$RC" -ne 0 ] \
    && [ "$(gate_status test-results/gates.json NPM_FULL_LOCKFILE_AUDIT)" = "NOT RUN" ] \
    && python3 -c "import json,sys; print({g['id']: g['detail'] for g in json.load(open('test-results/gates.json'))['gates']}.get('NPM_FULL_LOCKFILE_AUDIT',''))" | grep -q "CHECK_FAILED"; then
  ok "malformed npm audit output records NPM_FULL NOT RUN (CHECK_FAILED), strict FAILS"
else
  bad "malformed npm audit output should record NPM_FULL NOT RUN (CHECK_FAILED) and fail strict (rc=$RC)"
  tail -20 /tmp/if-strict-malformed.log
fi
rm -rf "$FAKEBIN"

# --- 9. Reverting '$$resp' to '$resp' must fail verify-release (IF-V4-01) -
# The Compose interpolation trap is a release blocker: the static
# regression in scripts/compose-config-check.py (wired into
# verify-release as COMPOSE_HEALTHCHECK) must catch a reverted
# healthcheck. Copy the tree, revert the two escapes with python
# (exact string replacement — no sed $ pitfalls), run verify-release.
TMP="$(mktemp -d)"
cp -r "$ROOT" "$TMP/tree"
rm -f "$TMP/tree/backend/data/identityforge.db"  # runtime state, not the test subject
# The copied dev tree also carries build artefacts the packager
# excludes (package-zip.py) but verify-release forbids — remove them
# so the ONLY failure in this run is the reverted healthcheck.
rm -rf "$TMP/tree/backend/src/identityforge.egg-info"
# Revert exactly the two escapes in the healthcheck TEST VALUE
# (`echo "$$resp"` ×2 on the `test:` line). The file also mentions
# '$$resp' once in an explanatory comment — that is not a shell
# variable reference, so the revert targets the test value only
# (a blanket replace would also rewrite the comment).
python3 - "$TMP/tree/docker-compose.yml" <<'PY'
import sys
p = sys.argv[1]
text = open(p).read()
needle = 'echo \\"$$resp\\"'
assert text.count(needle) == 2, f"expected 2 test-value $$resp, found {text.count(needle)}"
open(p, "w").write(text.replace(needle, 'echo \\"$resp\\"'))
print("reverted test-value $$resp -> $resp (2 occurrences; comment untouched)")
PY
if (cd "$TMP/tree" && ./scripts/verify-release.sh --strict >/tmp/if-vr-resp.log 2>&1); then
  bad "verify-release --strict should fail when the healthcheck '\$\$resp' is reverted to '\$resp'"
  tail -20 /tmp/if-vr-resp.log
else
  if grep -q "COMPOSE_HEALTHCHECK" /tmp/if-vr-resp.log && grep -q "FAIL: COMPOSE_HEALTHCHECK" /tmp/if-vr-resp.log; then
    ok "verify-release --strict fails on reverted '\$resp' (COMPOSE_HEALTHCHECK FAIL)"
  else
    bad "verify-release failed but not via COMPOSE_HEALTHCHECK (wrong gate?)"
    tail -20 /tmp/if-vr-resp.log
  fi
fi
rm -rf "$TMP"

echo
echo "gate-strictness: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
