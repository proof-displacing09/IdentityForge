#!/usr/bin/env bash
# IdentityForge verify-release — release-audit checks for the packaged archive.
# Run from an EXTRACTED copy of the release ZIP in a fresh directory, e.g.:
#   unzip IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_*.zip -d /tmp/if-check
#   cd /tmp/if-check && ./scripts/verify-release.sh [--strict]
#
# Every check is an explicit gate (PASS / FAIL / NOT RUN / NOT APPLICABLE)
# recorded in test-results/verify-release.json. --strict fails the run
# when ANY gate is NOT RUN. NOT APPLICABLE means the gate did not run
# because a superseding gate already covered it (P1-05: the GHSA
# fallback when the full npm audit executed) — it is neither a PASS
# nor a NOT RUN. This script is the STATIC release audit only: it does
# not boot Docker or perform a browser login, and must never be
# described as proof of end-to-end release readiness. The live gates
# live in ./scripts/test-all.sh --full --strict.
#
# Checks: required files; forbidden files (incl. generated egg-info);
# realm JSON; Compose YAML + port lock + hostname-v2 + admin-password
# consistency; script syntax; backend offline suite; frontend build;
# Compose config (when Docker exists); dependency audits (attempted:
# PYTHON_DEPENDENCY_AUDIT, NPM_FULL_LOCKFILE_AUDIT, GHSA_DIRECT_FALLBACK).
#
# Re-runs: a fresh extraction per run is the recommended audit shape
# (the script verifies the extracted copy, and a second run must see
# the same clean tree the first run saw). Since v8.0.3 a second run in
# the SAME extraction is also safe: BACKEND_PYTEST writes its database
# to a disposable temp directory (see section 5), so the first run
# leaves no `*.db` behind for FORBIDDEN_FILES to trip on. The script
# never deletes anything in the tree.
set -uo pipefail

STRICT=0
for arg in "$@"; do
  case "$arg" in
    --strict) STRICT=1 ;;
    --help|-h)
      echo "Usage: $0 [--strict]"
      exit 0 ;;
    *) echo "verify-release.sh: unknown argument: $arg" >&2; exit 2 ;;
  esac
done

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
mkdir -p test-results
RESULTS_TSV="test-results/verify-release.tsv"
: > "$RESULTS_TSV"

echo "== IdentityForge verify-release =="
echo "Directory: $ROOT"
echo

gate() {  # gate <id> <label> — runs "$@" as the check
  local id="$1" label="$2"; shift 2
  echo "--- [$id] $label ---"
  if "$@"; then
    echo "PASS: $id"
    printf '%s\tPASS\t%s\n' "$id" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$RESULTS_TSV"
  else
    echo "FAIL: $id"
    printf '%s\tFAIL\t%s\n' "$id" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$RESULTS_TSV"
  fi
}
skip_gate() {  # skip_gate <id> <label> <reason>
  local id="$1" label="$2" reason="$3"
  echo "--- [$id] $label ---"
  echo "NOT RUN: $id — $reason"
  printf '%s\tNOT RUN\t%s\t%s\n' "$id" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$reason" >> "$RESULTS_TSV"
}
na_gate() {  # na_gate <id> <label> <reason> — status NOT APPLICABLE
  local id="$1" label="$2" reason="$3"
  echo "--- [$id] $label ---"
  echo "NOT APPLICABLE: $id — $reason"
  printf '%s\tNOT APPLICABLE\t%s\t%s\n' "$id" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$reason" >> "$RESULTS_TSV"
}

# --- 1. Required files -----------------------------------------------------
missing=0
for f in README.md SECURITY.md LICENSE .env.example .gitignore docker-compose.yml \
         keycloak/realm-import/identityforge-lab-realm.json \
         scripts/setup.sh scripts/start.sh scripts/stop.sh scripts/reset.sh \
         scripts/test-all.sh scripts/test-all.ps1 scripts/doctor.sh scripts/verify-release.sh \
         scripts/live-gate.py scripts/test-gate-strictness.sh \
         scripts/compose-config-check.py scripts/npm-advisory-check.py \
         scripts/audit-gates.sh scripts/test-dependency-gates.sh \
         scripts/test-ghsa-stub.py scripts/test-doctor.sh \
         scripts/test-doctor-stub.py scripts/test-compose-healthcheck.sh \
         scripts/test-dockerignore.py scripts/npm-audit-classify.py \
         scripts/validate-playwright-report.py scripts/test-validate-playwright-report.py \
         scripts/test-ps1-native.sh scripts/native-invoke.ps1 \
         scripts/loopback-forwarder.py scripts/test-ps1-selection.sh \
         scripts/check-docker-nonroot.py scripts/test-prepare-data-volume.sh \
         backend/docker/prepare-data-volume.py \
         backend/requirements-audit.txt \
         frontend/.dockerignore backend/.dockerignore \
         docker-compose.test.yml \
         frontend/Dockerfile.e2e frontend/docker-e2e-entrypoint.sh \
         scripts/setup.ps1 scripts/start.ps1 scripts/stop.ps1 scripts/reset.ps1 \
         scripts/doctor.ps1 scripts/test-docs-contract-paths.sh \
         scripts/check-version-contract.py scripts/test-version-contract.sh \
         docs/ARCHITECTURE.md docs/THREAT_MODEL.md docs/AUTH_FLOW.md \
         docs/STANDARDS_TRACEABILITY.md docs/TEST_MATRIX.md docs/SCENARIO_METHOD.md \
         docs/DECISIONS.md docs/API_CONTRACT.md docs/VALIDATION_AND_LIMITATIONS.md \
         docs/REVIEWER_GUIDE.md docs/WINDOWS_SETUP.md docs/SECURITY_ASSESSMENT.md \
         docs/RELEASE_MANIFEST.md docs/VERIFICATION_LOG.md \
         docs/REMEDIATION_FINDINGS.md docs/REMEDIATION_TRACEABILITY.md \
         docs/KEYCLOAK_INTEGRATION.md docs/UI_DESIGN_SYSTEM.md \
         docs/EVIDENCE_RETENTION.md; do
  [ -f "$f" ] || { echo "  missing: $f"; missing=1; }
done
gate REQUIRED_FILES "required files present" test "$missing" -eq 0

# --- 2. Forbidden files (must not ship in a release) -----------------------
# Includes generated install metadata (P1-23: *.egg-info is regenerated
# on install and must not be packaged) and any secrets/DBs/archives.
# IF-V5-11 (v6): the list also covers the other sensitive-file shapes
# the packaging script excludes (scripts/package-zip.py): keystores
# (*.p12/*.jks), stray logs, and macOS sidecars. Client secrets,
# cookies, raw JWTs, PKCE verifiers and auth codes are runtime-only
# values, not files: they must never appear in the tree at all (the
# evidence redaction scan + the docs-contract gate cover the stored
# evidence; a secret that only ever lived in memory cannot be
# packaged — but a log or dump that captured one would be caught
# here by the *.log exclusion).
gate FORBIDDEN_FILES "no .env / DBs / archives / keys / keystores / logs / egg-info in release" bash -c '
  found=$(find . -type f \( -name ".env" -o -name "*.db" -o -name "*.sqlite*" \
    -o -name "*.zip" -o -name "*.pem" -o -name "*.key" -o -name "*.p12" \
    -o -name "*.jks" -o -name "*.log" -o -name ".DS_Store" \
    -o -name "*Zone.Identifier" \
    -o -path "*egg-info*" \) \
    -not -path "./.git/*" -not -path "./.venv/*" -not -path "./frontend/node_modules/*" \
    -not -path "./frontend/dist/*" -not -path "./test-results/*" -print)
  if [ -n "$found" ]; then echo "$found"; exit 1; fi
'

# --- 3. Realm JSON + Compose YAML parse ------------------------------------
gate REALM_JSON "realm import JSON parses" python3 -c \
  "import json; json.load(open('keycloak/realm-import/identityforge-lab-realm.json'))"
if python3 -c "import yaml" 2>/dev/null; then
  gate COMPOSE_YAML "docker-compose.yml parses as YAML" python3 -c \
    "import yaml; yaml.safe_load(open('docker-compose.yml'))"
else
  skip_gate COMPOSE_YAML "docker-compose.yml parses as YAML" "PyYAML not installed"
fi
# IF-V4-01: the static Compose healthcheck regression — rejects a
# single-$ shell variable in any healthcheck/command/entrypoint,
# proves the resolved Keycloak healthcheck keeps the literal '$resp'
# references, and verifies depends_on service_healthy wiring.
if python3 -c "import yaml" 2>/dev/null; then
  gate COMPOSE_HEALTHCHECK "no single-\$ trap in Compose healthchecks; resolved probe keeps '\$resp'; depends_on service_healthy (IF-V4-01)" python3 scripts/compose-config-check.py
else
  skip_gate COMPOSE_HEALTHCHECK "no single-\$ trap in Compose healthchecks (IF-V4-01)" "PyYAML not installed"
fi
# IF-V4-02: the .dockerignore exclusion proofs (fake host node_modules
# tree excluded, E2E specs + lockfiles kept, real 99-PNG exclusion).
gate DOCKERIGNORE "frontend/backend .dockerignore exclude host modules, screenshots, DBs; keep specs + lockfiles (IF-V4-02)" python3 scripts/test-dockerignore.py
# IF-V4-10: the Playwright report validator's own regression tests
# (pass / unexpected skip / zero real-login / wrong target / stale).
gate PLAYWRIGHT_VALIDATOR_SELFTEST "Playwright JSON report validator self-tests (IF-V4-10)" python3 scripts/test-validate-playwright-report.py
# IF-V4-06 (v5): docs-contract — every reason code / report field named
# in docs, example reports or UI copy must be exactly what the source
# defines (34 FailureReason values, 59 report-model fields).
gate DOCS_CONTRACT "docs-contract: reason codes + report fields match source (IF-V4-06)" python3 scripts/validate-docs-contract.py
# IF-V5-01 (v6): docs-contract path independence — the checker must
# behave identically under a `data/` ancestor or a path with spaces
# (v5: 104 false violations under a `data/` ancestor). 48 checks:
# clean docs PASS + stale-code / below-root exclusion / symlink-escape
# / empty-scan negatives + IF-V7.1-05 quickstart archive-name
# negatives (stale CANDIDATE, wrong final name) and positives
# ($ZIP variable, stale name in a historical section) in all three paths.
# (v7.3.1: 33, not 27 — the count was already stale in v7.3, when the
# suite had 30 checks; the v7.3.1 fixture adds case (k), 11 cases x 3 paths.)
# (v8.0.1: 48 — check-7 README-count cases (o)/(p) join the suite,
# 16 cases x 3 paths; the stale window moved to v8/v7.3.1/v7.3.)
gate DOCS_CONTRACT_PATHS "docs-contract path independence: normal / data ancestor / spaces (IF-V5-01)" bash scripts/test-docs-contract-paths.sh
# IF-V5-05 (v6): version contract — every authoritative version value
# must equal the release version 1.8.5 (manifest, backend pyproject +
# __init__ + FastAPI + health, frontend package.json + lockfile; the UI
# reads the version from GET /api/v1/health). Fails until the owning
# sources are bumped together.
gate VERSION_CONTRACT "every authoritative version equals 1.8.5 (IF-V5-05)" python3 scripts/check-version-contract.py
# IF-V4-09: the npm audit classifier's own regression (clean / vuln /
# blocked / DNS / malformed JSON exit codes).
gate AUDIT_CLASSIFIER_SELFTEST "npm audit classifier self-tests (IF-V4-09)" bash -c '
  tmp=$(mktemp -d)
  printf "%s" "{\"auditReportVersion\":2,\"vulnerabilities\":{},\"metadata\":{\"vulnerabilities\":{\"info\":0,\"low\":0,\"moderate\":0,\"high\":0,\"critical\":0,\"total\":0}}}" > "$tmp/clean.json"
  printf "%s" "{\"auditReportVersion\":2,\"vulnerabilities\":{\"lru-cache\":{\"name\":\"lru-cache\",\"severity\":\"high\"}},\"metadata\":{\"vulnerabilities\":{\"info\":0,\"low\":0,\"moderate\":0,\"high\":1,\"critical\":0,\"total\":1}}}" > "$tmp/vuln.json"
  printf "%s" "{\"error\":{\"code\":\"E403\",\"summary\":\"403 Forbidden\",\"detail\":\"policy_denied\"}}" > "$tmp/blocked.json"
  printf "%s" "not json at all" > "$tmp/malformed.txt"
  python3 scripts/npm-audit-classify.py "$tmp/clean.json" --rc 0 >/dev/null || exit 1
  python3 scripts/npm-audit-classify.py "$tmp/vuln.json" --rc 1 >/dev/null; [ $? -eq 1 ] || exit 1
  python3 scripts/npm-audit-classify.py "$tmp/blocked.json" --rc 1 >/dev/null; [ $? -eq 2 ] || exit 1
  python3 scripts/npm-audit-classify.py "$tmp/malformed.txt" --rc 1 >/dev/null; [ $? -eq 3 ] || exit 1
  rm -rf "$tmp"
'
gate COMPOSE_NO_0000 "no 0.0.0.0 host port bindings in docker-compose.yml" bash -c \
  '! grep -Eq "\"0\.0\.0\.0:[0-9]+" docker-compose.yml'
gate COMPOSE_PORTS_LOCKED "canonical ports are fixed (P1-14: no \${KEYCLOAK_PORT} etc.)" bash -c \
  '! grep -Eq "\\$\\{(KEYCLOAK_PORT|BACKEND_PORT|FRONTEND_PORT)" docker-compose.yml .env.example'
gate COMPOSE_HOSTNAME_V2 "Keycloak hostname-v2 only (no KC_HOSTNAME_PORT assignment in live config)" bash -c \
  '! grep -rEq "KC_HOSTNAME_PORT[[:space:]]*[:=]" docker-compose.yml .env.example README.md docs/REVIEWER_GUIDE.md docs/WINDOWS_SETUP.md'
gate ADMIN_PASSWORD_CONSISTENT "example password is a placeholder; Compose requires a private password" bash -c \
  'grep -Fxq "KEYCLOAK_ADMIN_PASSWORD=CHANGE_ME_TO_A_UNIQUE_LOCAL_PASSWORD" .env.example && grep -Fq "KEYCLOAK_ADMIN_PASSWORD:?" docker-compose.yml && ! grep -Fq "KEYCLOAK_ADMIN_PASSWORD:-" docker-compose.yml'
gate KEYCLOAK_PIN "Keycloak pinned to 26.8.2" bash -c \
  "grep -q 'keycloak/keycloak:26.8.2' docker-compose.yml"
gate CONTAINER_BINDS "backend + frontend bind 0.0.0.0 inside containers (host ports stay 127.0.0.1)" bash -c \
  'grep -q "\"0.0.0.0\"" backend/Dockerfile && grep -q "0.0.0.0" frontend/package.json'
gate NO_INTERNAL_ISSUER "keycloak:8080 only as backend transport (Compose) / transport allowlist (jwks.py), never as issuer/browser URL" bash -c '
  hits=$(grep -rn "http://keycloak:8080" --include="*.yml" --include="*.py" --include="*.example" --include="*.ts" --include="*.tsx" . --exclude-dir=.venv --exclude-dir=node_modules --exclude-dir=test-results 2>/dev/null || true)
  [ -z "$hits" ] && exit 0
  # Allowed: the Compose IDENTITYFORGE_IDP_TRANSPORT_BASE line, and any
  # line in protocol/jwks.py (ALLOWED_TRANSPORT_HOSTS + its scoping
  # comment). Also the gate itself, which names the string, and the
  # transport-boundary regression tests (backend/tests/unit/
  # test_transport.py and test_transport_fetch.py — their whole purpose
  # is asserting that keycloak:8080 rewrites as transport AND is
  # rejected as an issuer / discovery issuer). Same exemption, v8: the
  # pentest SSRF negative tests (backend/tests/adversarial/
  # test_ws1_v8_oidc.py::test_jwks_url_ssrf_guard and
  # scripts/pentest/ws3/test_ws3_properties.py — their whole purpose is
  # asserting a keycloak:8080 JWKS URL is SSRF_BLOCKED, never trusted).
  # Also one transport
  # comment in api/app.py (P0-01, v4) naming the Compose route in
  # prose — matched by its exact wording, NOT by file, so any other
  # keycloak:8080 in app.py still fails this gate. The cleaner fix is
  # to reword that comment to drop the literal URL (backend follow-up);
  # until then this precise exemption keeps the gate honest without
  # weakening it. Anything else — an issuer, browser redirect, or
  # externally visible auth URL using the internal service name —
  # fails the release check.
  bad=$(printf "%s\n" "$hits" | grep -v "docker-compose.yml:.*IDENTITYFORGE_IDP_TRANSPORT_BASE: http://keycloak:8080" | grep -v "\.env\.example:.*IDENTITYFORGE_IDP_TRANSPORT_BASE=http://keycloak:8080" | grep -v "protocol/jwks.py:.*keycloak:8080" | grep -v "backend/tests/unit/test_transport.py:" | grep -v "backend/tests/unit/test_transport_fetch.py:" | grep -v "backend/tests/adversarial/test_ws1_v8_oidc.py:" | grep -v "scripts/pentest/ws3/test_ws3_properties.py:" | grep -v "scripts/verify-release.sh:" || true)
  if [ -n "$bad" ]; then echo "$bad"; exit 1; fi
'
gate REALM_SUBJECT_UUIDS "realm pins deterministic subject UUIDs" python3 -c \
  "import json; u={x['username']: x.get('id') for x in json.load(open('keycloak/realm-import/identityforge-lab-realm.json'))['users']}; assert u['student_01']=='10000000-0000-4000-8000-000000000001' and u['officer_01']=='10000000-0000-4000-8000-000000000002'"

# --- 4. Scripts syntax ------------------------------------------------------
gate SCRIPT_SYNTAX "all .sh scripts pass bash -n" bash -c \
  'for s in scripts/*.sh; do bash -n "$s" || exit 1; done'
gate LIVE_GATE_SYNTAX "scripts/*.py helpers compile" python3 -m py_compile \
  scripts/live-gate.py scripts/loopback-forwarder.py scripts/compose-config-check.py scripts/npm-advisory-check.py \
  scripts/test-ghsa-stub.py scripts/test-doctor-stub.py scripts/npm-audit-classify.py \
  scripts/test-dockerignore.py scripts/validate-playwright-report.py \
  scripts/test-validate-playwright-report.py
# NOTE: .ps1 wrappers cannot be syntax-checked on Linux (no PowerShell in
# this sandbox); they are reviewer-gated on Windows. Their existence is
# covered by REQUIRED_FILES above, and test-all.ps1 gets a STATIC
# parameter-presence + 19-gate-wiring check below — a static check, not
# an execution proof. It asserts the offline/live wiring only: the
# OFFLINE_UNIT selection, the LIVE_PROVIDER_PYTEST full gate, the
# loopback forwarder, the "4 passed" positive proof, and 19 unique
# gate IDs. The live gates themselves run only in test-all.sh --full /
# test-all.ps1 -Full with a real Docker daemon + Keycloak; a green
# static gate here must never be read as "the live gates passed".
# IF-V8.0.4 (v8.0.4, Coverage Closure 3): without these assertions a
# future ZIP could ship a test-all.ps1 with the LIVE gate dropped (or
# the offline selection unfiltered) and this static audit would still
# pass — the wiring is now fail-closed here, and the regression suite
# scripts/test-ps1-selection.sh proves the same wiring by execution.
gate TEST_ALL_PS1 "scripts/test-all.ps1 uses Invoke-Native (no bare native docker calls) + 19-gate offline/live wiring (STATIC check only)" bash -c '
  grep -q "\-Offline" scripts/test-all.ps1 && grep -q "\-Full" scripts/test-all.ps1 && grep -q "\-Strict" scripts/test-all.ps1 && grep -q "\-Help" scripts/test-all.ps1 && grep -q "CLEAN_COMPOSE_BUILD_BOOT" scripts/test-all.ps1 && grep -q "NPM_FULL_LOCKFILE_AUDIT" scripts/test-all.ps1 && grep -q "DOCS_CONTRACT_PATHS" scripts/test-all.ps1 && grep -q "VERSION_CONTRACT" scripts/test-all.ps1 && grep -q "native-invoke.ps1" scripts/test-all.ps1 && grep -q "Invoke-Native" scripts/test-all.ps1 && grep -q "Get-NpmAuditClassification" scripts/test-all.ps1 && ! grep -qE "^[[:space:]]*& docker" scripts/test-all.ps1 && grep -q "LIVE_PROVIDER_PYTEST" scripts/test-all.ps1 && grep -q "python -m pytest -q -m " scripts/test-all.ps1 && grep -q "not live_keycloak" scripts/test-all.ps1 && ! grep -qF "python -m pytest -q\"))" scripts/test-all.ps1 && grep -q "loopback-forwarder.py 127.0.0.1:8080 keycloak:8080" scripts/test-all.ps1 && grep -q "python -m pytest -v -m live_keycloak" scripts/test-all.ps1 && grep -q "4 passed" scripts/test-all.ps1 && test "$(grep -oE "Invoke-Gate \"[A-Z0-9_]+\"" scripts/test-all.ps1 | sort -u | wc -l | tr -d " ")" = "19"
'

# --- 5. Backend offline suite (needs installed deps) ------------------------
# IF-V8.0.2-B (v8.0.2): the OFFLINE selection only (`-m "not
# live_keycloak"`). The four provider-dependent pytest tests (marked
# live_keycloak) need a live Keycloak and fail with 503
# PROVIDER_UNAVAILABLE without one; verify-release boots no provider,
# so an unfiltered run fails this gate on a correct tree (reproduced
# v8.0.1: 22 PASS / 1 FAIL / 5 NOT RUN, sole FAIL BACKEND_PYTEST).
# The marked tests are covered by test-all.sh --full gate
# LIVE_PROVIDER_PYTEST, not here.
#
# IF-V8.0.3 (v8.0.3): isolate the suite's database side effect. The
# offline suite creates backend/data/identityforge.db (the CLI store
# via Settings() defaults — even a bare --collect-only does it), so
# before this fix a second verify-release run in the same extraction
# false-failed FORBIDDEN_FILES on the first run's own DB (parent Pass
# C, v8.0.2: second run 22/1/5). BACKEND_PYTEST therefore runs with
# IDENTITYFORGE_DB_PATH pointed at a disposable temp directory, which
# is removed afterwards; the selection is unchanged (proven: 516
# offline + 4 live_keycloak collected with and without the redirect).
# The script never deletes anything in the tree — only the temp dir
# it created itself.
VR_TMPDB_DIR="$(mktemp -d)"
trap 'rm -rf "$VR_TMPDB_DIR"' EXIT
if [ -d backend ] && [ -f backend/requirements-freeze.txt ]; then
  if python3 -m pytest --version >/dev/null 2>&1; then
    gate BACKEND_PYTEST "backend pytest (offline selection, -m \"not live_keycloak\"; DB isolated to a temp dir)" env IDENTITYFORGE_DB_PATH="$VR_TMPDB_DIR/identityforge.db" bash -c 'cd backend && python3 -m pytest -q -m "not live_keycloak"'
  else
    skip_gate BACKEND_PYTEST "backend pytest (offline)" "pytest not installed — install backend deps first"
  fi
else
  gate BACKEND_PYTEST "backend pytest (offline)" false
fi

# --- 6. Frontend build (needs installed deps) -------------------------------
if [ -d frontend ] && [ -f frontend/package.json ] && [ -d frontend/node_modules ]; then
  gate FRONTEND_BUILD "frontend production build" bash -c 'cd frontend && npm run build'
else
  skip_gate FRONTEND_BUILD "frontend production build" "frontend deps not installed — run 'npm ci' in frontend/"
fi

# --- 7. Docker / Keycloak (config only; boot is a test-all --full gate) -----
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  gate COMPOSE_CONFIG "docker compose config validates" docker compose config -q
else
  skip_gate COMPOSE_CONFIG "docker compose config validates" "Docker not available in this environment"
  echo "  On a reviewer machine run: docker compose config -q && ./scripts/doctor.sh"
fi

# --- 8. Dependency audits (P0-03: three separate gates, attempted) -----------
# Each gate is PASS / FAIL / NOT RUN / NOT APPLICABLE honestly. A blocked
# audit is NOT RUN, never PASS — and the GHSA direct fallback never
# satisfies the full npm audit (it checks direct dependencies only).
# When the full audit executed, the fallback is NOT APPLICABLE (P1-05).
# IF-V4-09: the tool itself is verified first (pip-audit --version)
# and the scan result is classified, not read off a bare exit code —
# rc=1 without a recognizable report is CHECK_FAILED (NOT RUN),
# never a finding.
if python3 -m pip_audit --version >/dev/null 2>&1; then
  PIP_AUDIT_BIN=python3
elif [ -x .venv/bin/python ] && .venv/bin/python -m pip_audit --version >/dev/null 2>&1; then
  PIP_AUDIT_BIN=.venv/bin/python
else
  PIP_AUDIT_BIN=""
fi
if [ -n "$PIP_AUDIT_BIN" ]; then
  "$PIP_AUDIT_BIN" -m pip_audit -r backend/requirements-freeze.txt > test-results/audit-backend.log 2>&1
  py_rc=$?
  if [ "$py_rc" -eq 0 ]; then
    gate PYTHON_DEPENDENCY_AUDIT "pip-audit over backend/requirements-freeze.txt" true
  elif [ "$py_rc" -eq 1 ] && grep -qE "Found [0-9]+ known vulnerabilities? in" test-results/audit-backend.log; then
    gate PYTHON_DEPENDENCY_AUDIT "pip-audit over backend/requirements-freeze.txt" false
  elif [ "$py_rc" -eq 1 ]; then
    skip_gate PYTHON_DEPENDENCY_AUDIT "pip-audit over backend/requirements-freeze.txt" \
      "CHECK_FAILED: pip-audit exited rc=1 without a recognizable vulnerability report — see test-results/audit-backend.log"
  else
    skip_gate PYTHON_DEPENDENCY_AUDIT "pip-audit over backend/requirements-freeze.txt" \
      "CHECK_FAILED: pip-audit exited rc=$py_rc — see test-results/audit-backend.log"
  fi
else
  skip_gate PYTHON_DEPENDENCY_AUDIT "pip-audit over backend/requirements-freeze.txt" \
    "TOOL_UNAVAILABLE: pip-audit not installed — run ./scripts/test-all.sh (which installs it from backend/requirements-audit.txt) or pip install pip-audit"
fi
if ! command -v npm >/dev/null 2>&1; then
  skip_gate NPM_FULL_LOCKFILE_AUDIT "npm audit over the resolved lockfile tree" "TOOL_UNAVAILABLE: npm not installed"
elif [ -d frontend/node_modules ] && [ -f frontend/package-lock.json ]; then
  # JSON report + classifier (IF-V4-09): stdout and stderr are kept
  # separate so the JSON stays parseable.
  NPM_EXECUTED=0
  (cd frontend && timeout 120 npm audit --audit-level=high --json > ../test-results/audit-frontend.log 2> ../test-results/audit-frontend.err; echo $? > ../test-results/audit-frontend.rc)
  npm_rc="$(cat test-results/audit-frontend.rc)"
  npm_cls="$(python3 scripts/npm-audit-classify.py test-results/audit-frontend.log --stderr test-results/audit-frontend.err --rc "$npm_rc" 2>&1)"
  cls_rc=$?
  case "$cls_rc" in
    0) NPM_EXECUTED=1; gate NPM_FULL_LOCKFILE_AUDIT "npm audit over the resolved lockfile tree (package-lock.json)" true ;;
    1) NPM_EXECUTED=1; gate NPM_FULL_LOCKFILE_AUDIT "npm audit over the resolved lockfile tree (package-lock.json)" false ;;
    2) skip_gate NPM_FULL_LOCKFILE_AUDIT "npm audit over the resolved lockfile tree (package-lock.json)" "$npm_cls — see test-results/audit-frontend.log; run on a machine with registry access" ;;
    *) skip_gate NPM_FULL_LOCKFILE_AUDIT "npm audit over the resolved lockfile tree (package-lock.json)" "CHECK_FAILED: $npm_cls — see test-results/audit-frontend.log" ;;
  esac
else
  skip_gate NPM_FULL_LOCKFILE_AUDIT "npm audit over the resolved lockfile tree (package-lock.json)" \
    "frontend deps not installed — run 'npm ci' in frontend/"
fi
# GHSA direct fallback: informational only, and ONLY when the full npm
# audit could not execute. When the full audit executed (clean or with
# findings), the fallback is NOT APPLICABLE — it did not run, and a
# PASS there would be a phantom (P1-05, v4). Exit 0 = clean (direct
# deps only), 1 = high/critical advisory found, 2 = source unreachable.
if [ "${NPM_EXECUTED:-0}" -eq 1 ]; then
  na_gate GHSA_DIRECT_FALLBACK "GHSA direct-dependency fallback (informational, direct deps only)" \
    "not applicable — npm audit executed; the direct-only fallback did not run"
else
  python3 scripts/npm-advisory-check.py > test-results/audit-frontend-ghsa.log 2>&1
  ghsa_rc=$?
  if [ "$ghsa_rc" -eq 0 ]; then
    gate GHSA_DIRECT_FALLBACK "GHSA direct-dependency fallback (informational, direct deps only)" true
  elif [ "$ghsa_rc" -eq 1 ]; then
    gate GHSA_DIRECT_FALLBACK "GHSA direct-dependency fallback (informational, direct deps only)" false
  else
    skip_gate GHSA_DIRECT_FALLBACK "GHSA direct-dependency fallback (informational, direct deps only)" \
      "advisory source unreachable or rate-limited (rc=$ghsa_rc)"
  fi
fi

# --- Machine-readable report + summary --------------------------------------
python3 - "$RESULTS_TSV" <<'PY'
import json, sys
gates = []
for line in open(sys.argv[1]):
    parts = line.rstrip("\n").split("\t")
    gates.append({"id": parts[0], "status": parts[1], "at": parts[2],
                  "detail": parts[3] if len(parts) > 3 else ""})
doc = {"gates": gates,
       "summary": {s: sum(1 for g in gates if g["status"] == s)
                   for s in ("PASS", "FAIL", "NOT RUN", "NOT APPLICABLE")}}
json.dump(doc, open("test-results/verify-release.json", "w"), indent=2)
PY

echo
echo "===== verify-release summary ====="
column -t -s $'\t' "$RESULTS_TSV" 2>/dev/null || cat "$RESULTS_TSV"
echo "Machine-readable report: test-results/verify-release.json"
echo "NOTE: this is the STATIC audit only. Live gates (Compose boot, real"
echo "Keycloak login, browser E2E) run via ./scripts/test-all.sh --full --strict"
echo "on Linux/macOS, or .\\scripts\\test-all.ps1 -Full -Strict on Windows."

failures=$(grep -c $'\tFAIL\t' "$RESULTS_TSV" || true)
notrun=$(grep -c $'\tNOT RUN\t' "$RESULTS_TSV" || true)
if [ "$STRICT" -eq 1 ] && [ "$notrun" -gt 0 ]; then
  echo "$notrun gate(s) NOT RUN — --strict fails the release check."
  exit 1
fi
if [ "$failures" -gt 0 ]; then
  echo "$failures check(s) FAILED. Fix before release."
  exit 1
fi
echo "All executed checks passed. Checks marked NOT RUN above still need a"
echo "machine with the relevant tool installed (see the notes)."
