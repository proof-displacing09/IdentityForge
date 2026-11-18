#!/usr/bin/env bash
# IdentityForge dependency-gate tests (P0-03).
#
# Drives the REAL scripts/audit-gates.sh functions with a fake `npm`,
# fake `python` (-m pip_audit) and a local GHSA stub server on PATH,
# so every audit outcome is deterministic without network or quota
# luck. Each scenario runs in a fresh temp tree (real package-lock.json
# + real scripts), records gates.json with the same schema as
# test-all.sh, and exits 0 only when no gate FAILED and none was
# NOT RUN (NOT APPLICABLE is acceptable: the gate was superseded,
# not skipped).
#
# Scenarios:
#   1 npm-clean-pip-missing  npm audit clean, pip-audit unavailable.
#   2 npm-vuln               npm audit rc=1 with a TRANSITIVE advisory
#                            (lru-cache) in the report text.
#   3 npm-blocked-ghsa-clean npm audit 403-blocked, GHSA stub clean.
#   4 npm-timeout-ghsa-clean npm audit rc=124, GHSA stub clean.
#   5 ghsa-quota             npm audit blocked, GHSA rate limit 0.
#   6 ghsa-direct-advisory   npm audit blocked, GHSA HIGH advisory
#                            for direct dep vite@7.3.8.
#   7 ghsa-transitive-only   npm audit blocked, GHSA stub holds an
#                            advisory ONLY for transitive lru-cache:
#                            the fallback must never query it, must
#                            not mask the missing full audit.
#   8 clean-complete-tree    everything clean; assert the gates.json
#                            schema and summary counts exactly, plus
#                            audit-tools.json tool records (IF-V4-09).
#   9 pip-scan-garbage       pip-audit rc=1 with NO recognizable
#                            vulnerability report -> CHECK_FAILED, NOT
#                            RUN (never FAIL) (IF-V4-09).
#  10 pip-scan-rc2           pip-audit rc=2 -> CHECK_FAILED, NOT RUN.
#  11 npm-malformed          npm audit garbage (not JSON) -> CHECK_FAILED.
#  12 npm-dns                npm audit JSON ENOTFOUND -> NOT RUN:DNS.
#  13 npm-rate-ghsa-quota    npm audit JSON E429 + GHSA quota -> both NOT RUN.
#  14 npm-lowonly            JSON metadata low/moderate only -> PASS
#                            at --audit-level=high.
#
# Run: ./scripts/test-dependency-gates.sh
#
# IF-V7-02 (v7.1, P1): the scenario driver used to run with
# PATH="$FAKEBIN:/usr/bin:/bin", discarding the platform PATH. On an
# NVM/Volta/asdf/hosted-toolcache-style layout — node/npm ONLY outside
# /usr/bin and /bin — the real `npm` then could not find its `node`
# (`#!/usr/bin/env node` resolved to a dead /usr/bin/node), so
# `npm --version` failed, audit-gates recorded NPM_FULL_LOCKFILE_AUDIT
# as NOT RUN, and the GHSA fallback ran as if no full audit existed:
# 38 passed, 17 failed. The fix captures the platform PATH once
# (ORIGINAL_PATH) and prepends the per-scenario fake bin to it:
# PATH="$SCEN_FAKEBIN:$ORIGINAL_PATH" — no hard-coded /usr/bin:/bin,
# and every scenario gets a FRESH copy of the fake wrappers, so a fake
# npm from one scenario can never leak into the next. Verified in both
# layouts: (1) node under /usr/bin, (2) node/npm ONLY under a
# symlinked NVM-style dir outside /usr/bin and /bin, with /usr/bin/node
# hidden by a bind-mount of /dev/null inside a private mount namespace
# (unshare -rm) — 55/0 in both.
set -uo pipefail

# IF-V7-02: capture the platform PATH ONCE, before anything below
# can observe or mutate it. Every scenario driver runs with
# PATH="$SCEN_FAKEBIN:$ORIGINAL_PATH": the fake bin first (so the
# fixture npm/pip-audit/GHSA interception holds), then the caller's
# real PATH untouched — including an NVM-style node/npm directory.
ORIGINAL_PATH="$PATH"

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PASS=0
FAIL=0
STUB_PORT=18711

ok()  { echo "PASS: $1"; PASS=$((PASS + 1)); }
bad() { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }

REAL_NPM="$(command -v npm)"
REAL_PYTHON3="$(command -v python3)"
if [ -z "$REAL_NPM" ] || [ -z "$REAL_PYTHON3" ]; then
  echo "test-dependency-gates: npm and python3 are required on PATH" >&2
  exit 2
fi

# --- Fake bin template -----------------------------------------------------
# IF-V7-02 (v7.1): the wrappers below are a TEMPLATE. run_scenario()
# copies them into a FRESH per-scenario directory, so no fake npm (or
# fake python/pip) from one scenario can leak into the next: each
# scenario's driver sees exactly its own wrappers plus the platform
# PATH. The template itself is never on any scenario's PATH.
# IF-V4-09 (v5): the fake `npm audit` emits the JSON report the real
# `npm audit --json` produces, so the classifier in
# scripts/npm-audit-classify.py is exercised, not bypassed. Modes:
#   clean      JSON metadata, 0 high/critical (exit 0)
#   lowonly    JSON metadata, low/moderate only (exit 0)
#   vuln       JSON metadata, 1 high transitive advisory (exit 1)
#   blocked    JSON error E403 + policy_denied (exit 1)
#   dns        JSON error ENOTFOUND (exit 1)
#   rate       JSON error E429 (exit 1)
#   offline    JSON error ECONNREFUSED (exit 1)
#   malformed  garbage text, no JSON (exit 1)
#   timeout    exit 124
FAKEBIN_TEMPLATE="$(mktemp -d)"
cat > "$FAKEBIN_TEMPLATE/npm" <<EOF
#!/usr/bin/env bash
# Fake npm: only \`npm audit\` is faked (scenario via FAKE_NPM_AUDIT);
# every other subcommand delegates to the real npm.
if [ "\$1" = "audit" ]; then
  case "\${FAKE_NPM_AUDIT:-clean}" in
    clean) echo '{"auditReportVersion":2,"vulnerabilities":{},"metadata":{"vulnerabilities":{"info":0,"low":0,"moderate":0,"high":0,"critical":0,"total":0},"dependencies":{"prod":1,"dev":0,"optional":0,"peer":0,"peerOptional":0,"total":1}}}'; exit 0 ;;
    lowonly) echo '{"auditReportVersion":2,"vulnerabilities":{},"metadata":{"vulnerabilities":{"info":0,"low":2,"moderate":1,"high":0,"critical":0,"total":3},"dependencies":{"prod":1,"dev":0,"optional":0,"peer":0,"peerOptional":0,"total":1}}}'; exit 0 ;;
    vuln)
      cat <<'AUDIT'
{"auditReportVersion":2,"vulnerabilities":{"lru-cache":{"name":"lru-cache","severity":"high","via":[{"source":1089785,"name":"lru-cache","dependency":"lru-cache","title":"Regular Expression Denial of Service","url":"https://github.com/advisories/GHSA-xxxx-yyyy-zzzz","severity":"high","range":">=0.0.0 <10.4.0"}]}},"metadata":{"vulnerabilities":{"info":0,"low":1,"moderate":0,"high":1,"critical":0,"total":2},"dependencies":{"prod":1,"dev":0,"optional":0,"peer":0,"peerOptional":0,"total":1}}}
AUDIT
      exit 1 ;;
    blocked)
      echo '{"error":{"code":"E403","summary":"403 Forbidden - GET https://registry.npmjs.org/-/npm/v1/security/audits/quick","detail":"audit endpoint returned an error policy_denied"}}' >&2
      echo '{"error":{"code":"E403","summary":"403 Forbidden - GET https://registry.npmjs.org/-/npm/v1/security/audits/quick","detail":"audit endpoint returned an error policy_denied"}}'
      exit 1 ;;
    dns)
      echo '{"error":{"code":"ENOTFOUND","summary":"request to https://registry.npmjs.org/-/npm/v1/security/audits/quick failed","detail":"getaddrinfo ENOTFOUND registry.npmjs.org"}}'
      exit 1 ;;
    rate)
      echo '{"error":{"code":"E429","summary":"429 Too Many Requests - GET https://registry.npmjs.org/-/npm/v1/security/audits/quick","detail":"rate limit exceeded"}}'
      exit 1 ;;
    offline)
      echo '{"error":{"code":"ECONNREFUSED","summary":"request to https://registry.npmjs.org/-/npm/v1/security/audits/quick failed","detail":"connect ECONNREFUSED 104.16.0.0:443"}}'
      exit 1 ;;
    malformed)
      echo "npm error: something unexpected broke (not JSON at all)"
      exit 1 ;;
    timeout) exit 124 ;;
  esac
fi
exec "$REAL_NPM" "\$@"
EOF
cat > "$FAKEBIN_TEMPLATE/python" <<EOF
#!/usr/bin/env bash
# Fake python: only \`-m pip_audit\` is faked (scenario via
# FAKE_PIP_AUDIT); everything else delegates to real python3.
#   clean        --version prints a version; scan clean (exit 0)
#   vuln         scan reports 1 known vulnerability (exit 1)
#   missing      --version fails; install is refused (exit 2)
#   scan-garbage --version OK; scan exits 1 with NO recognizable
#                vulnerability report (IF-V4-09 CHECK_FAILED)
#   scan-rc2     --version OK; scan exits 2 (IF-V4-09 CHECK_FAILED)
if [ "\$1" = "-m" ] && [ "\$2" = "pip_audit" ]; then
  if [ "\${3:-}" = "--version" ]; then
    case "\${FAKE_PIP_AUDIT:-missing}" in clean|vuln|scan-garbage|scan-rc2) echo "pip-audit 2.10.1"; exit 0 ;; *) exit 2 ;; esac
  fi
  case "\${FAKE_PIP_AUDIT:-missing}" in
    clean) echo "No known vulnerabilities found"; exit 0 ;;
    vuln) echo "Found 1 known vulnerability in 1 package"; exit 1 ;;
    scan-garbage) echo "pip-audit crashed mid-scan: unexpected traceback"; exit 1 ;;
    scan-rc2) echo "pip-audit: error: could not read requirements file"; exit 2 ;;
    *) exit 2 ;;
  esac
fi
exec "$REAL_PYTHON3" "\$@"
EOF
cat > "$FAKEBIN_TEMPLATE/pip" <<'EOF'
#!/usr/bin/env bash
# Fake pip: installing pip-audit is refused in these tests, so a
# missing pip-audit stays missing (NOT RUN, never silently clean).
echo "fake pip: install refused in dependency-gate tests" >&2
exit 1
EOF
chmod +x "$FAKEBIN_TEMPLATE/npm" "$FAKEBIN_TEMPLATE/python" "$FAKEBIN_TEMPLATE/pip"

# --- Scenario driver (written per scenario into its temp tree) ---------------
write_driver() {  # $1 = scenario dir
  cat > "$1/driver.sh" <<'DRIVER'
#!/usr/bin/env bash
# Drives run_dependency_gates from scripts/audit-gates.sh with stub
# gate()/skip_gate() recorders, then writes gates.json with the same
# schema as test-all.sh and exits 0 only if all three gates PASS.
set -uo pipefail
cd "$(dirname "$0")"
mkdir -p test-results
RESULTS_TSV="test-results/gates.tsv"
: > "$RESULTS_TSV"
GATE_DETAIL=""
gate() {
  local id="$1" required_by="$2" label="$3"; shift 3
  if "$@"; then
    printf '%s\t%s\tPASS\t%s\t%s\n' "$id" "$required_by" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$GATE_DETAIL" >> "$RESULTS_TSV"
  else
    printf '%s\t%s\tFAIL\t%s\t%s\n' "$id" "$required_by" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$GATE_DETAIL" >> "$RESULTS_TSV"
  fi
  GATE_DETAIL=""
}
skip_gate() {
  local id="$1" required_by="$2" label="$3" reason="$4"
  printf '%s\t%s\tNOT RUN\t%s\t%s\n' "$id" "$required_by" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$reason" >> "$RESULTS_TSV"
}
na_gate() {
  local id="$1" required_by="$2" label="$3" reason="$4"
  printf '%s\t%s\tNOT APPLICABLE\t%s\t%s\n' "$id" "$required_by" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$reason" >> "$RESULTS_TSV"
}
PY="$FAKEBIN/python"
PIP="$FAKEBIN/pip"
export PY PIP
# shellcheck source=scripts/audit-gates.sh
source scripts/audit-gates.sh
run_dependency_gates
python3 - "$RESULTS_TSV" <<'PY'
import json, sys
gates = []
for line in open(sys.argv[1]):
    parts = line.rstrip("\n").split("\t")
    gates.append({"id": parts[0], "required_by": parts[1], "status": parts[2],
                  "at": parts[3], "detail": parts[4] if len(parts) > 4 else ""})
doc = {"profile": "offline", "gates": gates,
       "summary": {s: sum(1 for g in gates if g["status"] == s)
                   for s in ("PASS", "FAIL", "NOT RUN", "NOT APPLICABLE")}}
json.dump(doc, open("test-results/gates.json", "w"), indent=2)
PY
# Exit 0 only when nothing FAILED and nothing was NOT RUN. NOT
# APPLICABLE is acceptable: the gate was superseded, not skipped.
[ "$(python3 -c "import json; d=json.load(open('test-results/gates.json'))['summary']; print(d['FAIL'] + d['NOT RUN'])")" -eq 0 ]
DRIVER
  chmod +x "$1/driver.sh"
}

# --- Scenario runner ---------------------------------------------------------
# run_scenario <name> <FAKE_NPM_AUDIT> <FAKE_PIP_AUDIT> <ghsa-scenario-json|"">
#   Starts the GHSA stub when a scenario file is given; runs the driver;
#   leaves $SCEN_DIR/gates.json and $SCEN_RC for the assertions.
run_scenario() {
  local name="$1" npm_mode="$2" pip_mode="$3" ghsa_json="$4"
  # IF-V7-02 isolation: a FRESH fake bin per scenario, copied from the
  # template and never shared — a fake npm from one scenario cannot
  # leak into the next. The scenario modes must also not leak into
  # this shell: they are passed only as env to the driver subshell
  # below. A leak aborts the suite outright (not a counted check).
  if [ -n "${FAKE_NPM_AUDIT:-}" ] || [ -n "${FAKE_PIP_AUDIT:-}" ]; then
    echo "test-dependency-gates: scenario mode leaked into outer shell" >&2
    exit 2
  fi
  local SCEN_FAKEBIN
  SCEN_FAKEBIN="$(mktemp -d)"
  cp -p "$FAKEBIN_TEMPLATE/npm" "$FAKEBIN_TEMPLATE/python" \
    "$FAKEBIN_TEMPLATE/pip" "$SCEN_FAKEBIN/"
  SCEN_DIR="$(mktemp -d)"
  mkdir -p "$SCEN_DIR/frontend" "$SCEN_DIR/scripts" "$SCEN_DIR/backend" "$SCEN_DIR/test-results"
  cp "$ROOT/frontend/package-lock.json" "$SCEN_DIR/frontend/"
  cp "$ROOT/scripts/audit-gates.sh" "$ROOT/scripts/npm-advisory-check.py" "$ROOT/scripts/npm-audit-classify.py" "$SCEN_DIR/scripts/"
  cp "$ROOT/backend/requirements-freeze.txt" "$ROOT/backend/requirements-audit.txt" "$SCEN_DIR/backend/"
  write_driver "$SCEN_DIR"
  local stub_pid=""
  if [ -n "$ghsa_json" ]; then
    : > "$SCEN_DIR/query.log"
    python3 "$ROOT/scripts/test-ghsa-stub.py" --port "$STUB_PORT" \
      --scenario "$ghsa_json" --query-log "$SCEN_DIR/query.log" \
      > "$SCEN_DIR/stub.log" 2>&1 &
    stub_pid=$!
    for _ in $(seq 1 20); do
      curl -fsS "http://127.0.0.1:$STUB_PORT/rate_limit" >/dev/null 2>&1 && break
      sleep 0.25
    done
  fi
  # IF-V7-02: PATH is the per-scenario fake bin prepended to the
  # platform PATH captured once at startup (ORIGINAL_PATH) — never a
  # hard-coded /usr/bin:/bin, so an NVM-style node/npm directory
  # outside /usr/bin stays visible to the real npm the fake delegates
  # to. The fake npm intercepts exactly `npm audit` (scenario JSON);
  # every other subcommand delegates to the real npm, and no real
  # audit request runs in this suite (the registry is never contacted:
  # audit output is the canned fixture JSON; GHSA goes only to the
  # local 127.0.0.1 stub).
  (cd "$SCEN_DIR" && FAKEBIN="$SCEN_FAKEBIN" FAKE_NPM_AUDIT="$npm_mode" FAKE_PIP_AUDIT="$pip_mode" \
    PATH="$SCEN_FAKEBIN:$ORIGINAL_PATH" \
    IDENTITYFORGE_GHSA_API="http://127.0.0.1:$STUB_PORT/advisories" \
    IDENTITYFORGE_GHSA_RATE_LIMIT="http://127.0.0.1:$STUB_PORT/rate_limit" \
    ./driver.sh > driver.log 2>&1)
  SCEN_RC=$?
  rm -rf "$SCEN_FAKEBIN"
  if [ -n "$stub_pid" ]; then kill "$stub_pid" 2>/dev/null; wait "$stub_pid" 2>/dev/null || true; fi
}

gate_status() {  # $1 = gates.json, $2 = gate id -> status
  python3 -c "import json,sys; print({g['id']: g['status'] for g in json.load(open(sys.argv[1]))['gates']}.get(sys.argv[2], 'MISSING'))" "$1" "$2"
}
gate_detail() {  # $1 = gates.json, $2 = gate id -> detail
  python3 -c "import json,sys; print({g['id']: g['detail'] for g in json.load(open(sys.argv[1]))['gates']}.get(sys.argv[2], ''))" "$1" "$2"
}
expect() {  # $1 = description, $2 = actual, $3 = expected
  if [ "$2" = "$3" ]; then ok "$1 ($2)"; else bad "$1 — expected '$3', got '$2'"; fi
}

ghsa_json() {  # $1 = file, $2 = rate remaining, $3 = advisories JSON object
  python3 -c "import json,sys; json.dump({'rate_limit_remaining': int(sys.argv[2]), 'rate_limit_reset': 1893456000, 'advisories': json.loads(sys.argv[3])}, open(sys.argv[1], 'w'))" "$1" "$2" "$3"
}
TMP="$(mktemp -d)"

# --- 1. npm audit clean, pip-audit unavailable ------------------------------
run_scenario "npm-clean-pip-missing" clean missing ""
G="$SCEN_DIR/test-results/gates.json"
expect "1 PYTHON_DEPENDENCY_AUDIT is NOT RUN (pip-audit missing)" "$(gate_status "$G" PYTHON_DEPENDENCY_AUDIT)" "NOT RUN"
expect "1 NPM_FULL_LOCKFILE_AUDIT PASS (npm audit clean)" "$(gate_status "$G" NPM_FULL_LOCKFILE_AUDIT)" "PASS"
expect "1 GHSA_DIRECT_FALLBACK NOT APPLICABLE (full audit executed; fallback never ran)" "$(gate_status "$G" GHSA_DIRECT_FALLBACK)" "NOT APPLICABLE"
expect "1 driver exit nonzero (a required gate was NOT RUN)" "$SCEN_RC" "1"
rm -rf "$SCEN_DIR"

# --- 2. npm audit with findings (transitive advisory in report) ------------
run_scenario "npm-vuln" vuln clean ""
G="$SCEN_DIR/test-results/gates.json"
expect "2 PYTHON_DEPENDENCY_AUDIT PASS" "$(gate_status "$G" PYTHON_DEPENDENCY_AUDIT)" "PASS"
expect "2 NPM_FULL_LOCKFILE_AUDIT FAIL (findings)" "$(gate_status "$G" NPM_FULL_LOCKFILE_AUDIT)" "FAIL"
expect "2 GHSA_DIRECT_FALLBACK NOT APPLICABLE (full audit executed; never PASS beside a failed audit)" "$(gate_status "$G" GHSA_DIRECT_FALLBACK)" "NOT APPLICABLE"
expect "2 driver exit nonzero" "$SCEN_RC" "1"
if grep -q "lru-cache" "$SCEN_DIR/test-results/audit-frontend.log"; then
  ok "2 audit log names the transitive package (lru-cache)"
else bad "2 audit log should name the transitive package"; fi
rm -rf "$SCEN_DIR"

# --- 3. npm audit 403-blocked, GHSA clean ------------------------------------
ghsa_json "$TMP/clean.json" 60 '{}'
run_scenario "npm-blocked-ghsa-clean" blocked clean "$TMP/clean.json"
G="$SCEN_DIR/test-results/gates.json"
expect "3 NPM_FULL_LOCKFILE_AUDIT NOT RUN (blocked)" "$(gate_status "$G" NPM_FULL_LOCKFILE_AUDIT)" "NOT RUN"
expect "3 GHSA_DIRECT_FALLBACK PASS (direct only)" "$(gate_status "$G" GHSA_DIRECT_FALLBACK)" "PASS"
expect "3 GHSA detail states direct-only scope" \
  "$(gate_detail "$G" GHSA_DIRECT_FALLBACK | grep -c 'direct dependencies only — transitive advisories NOT checked')" "1"
expect "3 driver exit nonzero — fallback did NOT satisfy the full gate" "$SCEN_RC" "1"
rm -rf "$SCEN_DIR"

# --- 4. npm audit timeout, GHSA clean ----------------------------------------
run_scenario "npm-timeout-ghsa-clean" timeout clean "$TMP/clean.json"
G="$SCEN_DIR/test-results/gates.json"
expect "4 NPM_FULL_LOCKFILE_AUDIT NOT RUN (timeout)" "$(gate_status "$G" NPM_FULL_LOCKFILE_AUDIT)" "NOT RUN"
expect "4 GHSA_DIRECT_FALLBACK PASS (direct only)" "$(gate_status "$G" GHSA_DIRECT_FALLBACK)" "PASS"
expect "4 driver exit nonzero" "$SCEN_RC" "1"
rm -rf "$SCEN_DIR"

# --- 5. GHSA quota exhausted -------------------------------------------------
ghsa_json "$TMP/quota.json" 0 '{}'
run_scenario "ghsa-quota" blocked clean "$TMP/quota.json"
G="$SCEN_DIR/test-results/gates.json"
expect "5 NPM_FULL_LOCKFILE_AUDIT NOT RUN (blocked)" "$(gate_status "$G" NPM_FULL_LOCKFILE_AUDIT)" "NOT RUN"
expect "5 GHSA_DIRECT_FALLBACK NOT RUN (quota exhausted)" "$(gate_status "$G" GHSA_DIRECT_FALLBACK)" "NOT RUN"
expect "5 driver exit nonzero" "$SCEN_RC" "1"
rm -rf "$SCEN_DIR"

# --- 6. GHSA finds a HIGH advisory for a direct dep --------------------------
ghsa_json "$TMP/direct.json" 60 '{"vite@7.3.8": [{"ghsa_id": "GHSA-test-direct-1", "cve_id": "CVE-2099-0001", "severity": "high", "summary": "injected direct advisory (test)"}]}'
run_scenario "ghsa-direct-advisory" blocked clean "$TMP/direct.json"
G="$SCEN_DIR/test-results/gates.json"
expect "6 NPM_FULL_LOCKFILE_AUDIT NOT RUN (blocked)" "$(gate_status "$G" NPM_FULL_LOCKFILE_AUDIT)" "NOT RUN"
expect "6 GHSA_DIRECT_FALLBACK FAIL (direct advisory found)" "$(gate_status "$G" GHSA_DIRECT_FALLBACK)" "FAIL"
expect "6 driver exit nonzero" "$SCEN_RC" "1"
if grep -q "GHSA-test-direct-1" "$SCEN_DIR/test-results/audit-frontend-ghsa.json"; then
  ok "6 GHSA report records the injected advisory id"
else bad "6 GHSA report should record the injected advisory id"; fi
rm -rf "$SCEN_DIR"

# --- 7. GHSA holds an advisory ONLY for a transitive dep ----------------------
ghsa_json "$TMP/transitive.json" 60 '{"lru-cache@10.4.3": [{"ghsa_id": "GHSA-test-transitive-1", "cve_id": "CVE-2099-0002", "severity": "high", "summary": "injected TRANSITIVE advisory (test)"}]}'
run_scenario "ghsa-transitive-only" blocked clean "$TMP/transitive.json"
G="$SCEN_DIR/test-results/gates.json"
expect "7 NPM_FULL_LOCKFILE_AUDIT NOT RUN (blocked — not masked)" "$(gate_status "$G" NPM_FULL_LOCKFILE_AUDIT)" "NOT RUN"
expect "7 GHSA_DIRECT_FALLBACK PASS (its scope is direct deps only)" "$(gate_status "$G" GHSA_DIRECT_FALLBACK)" "PASS"
expect "7 driver exit nonzero — tree is NOT reported clean" "$SCEN_RC" "1"
if grep -q "lru-cache" "$SCEN_DIR/query.log"; then
  bad "7 GHSA fallback must never query a transitive package (lru-cache queried)"
else
  ok "7 GHSA fallback never queried the transitive package"
fi
if python3 -c "import json; r=json.load(open('$SCEN_DIR/test-results/audit-frontend-ghsa.json')); assert r['transitive_dependencies_examined'] is False and not any(x['package']=='lru-cache' for x in r['results'])"; then
  ok "7 GHSA report: transitive_dependencies_examined=false, no lru-cache entry"
else bad "7 GHSA report must mark transitive deps unexamined and omit lru-cache"; fi
rm -rf "$SCEN_DIR"

# --- 8. Clean complete tree ---------------------------------------------------
run_scenario "clean-complete-tree" clean clean ""
G="$SCEN_DIR/test-results/gates.json"
expect "8 PYTHON_DEPENDENCY_AUDIT PASS" "$(gate_status "$G" PYTHON_DEPENDENCY_AUDIT)" "PASS"
expect "8 NPM_FULL_LOCKFILE_AUDIT PASS" "$(gate_status "$G" NPM_FULL_LOCKFILE_AUDIT)" "PASS"
expect "8 GHSA_DIRECT_FALLBACK NOT APPLICABLE (full audit executed)" "$(gate_status "$G" GHSA_DIRECT_FALLBACK)" "NOT APPLICABLE"
expect "8 driver exit 0 (no FAIL, no NOT RUN)" "$SCEN_RC" "0"
if python3 -c "
import json
d = json.load(open('$G'))
assert set(d) == {'profile', 'gates', 'summary'}, set(d)
assert len(d['gates']) == 3
for g in d['gates']:
    assert set(g) == {'id', 'required_by', 'status', 'at', 'detail'}, set(g)
assert d['summary'] == {'PASS': 2, 'FAIL': 0, 'NOT RUN': 0, 'NOT APPLICABLE': 1}, d['summary']
"; then
  ok "8 gates.json schema matches test-all.sh exactly (3 gates, summary 2/0/0/1)"
else bad "8 gates.json schema mismatch"; fi
if python3 -c "
import json
d = json.load(open('$SCEN_DIR/test-results/audit-tools.json'))
assert d['pip_audit']['version'] == 'pip-audit 2.10.1', d['pip_audit']
assert d['pip_audit']['install_status'] == 'available', d['pip_audit']
assert d['pip_audit']['scan_status'] == 'clean', d['pip_audit']
assert d['npm_audit']['scan_status'] == 'clean', d['npm_audit']
assert d['npm_audit']['timeout_seconds'] == 120, d['npm_audit']
assert d['ghsa_direct_fallback']['status'] == 'not_applicable', d['ghsa_direct_fallback']
"; then
  ok "8 audit-tools.json records tool versions + statuses (pip-audit 2.10.1, npm clean, GHSA not_applicable)"
else bad "8 audit-tools.json mismatch"; fi
rm -rf "$SCEN_DIR"

# --- 9. pip-audit scan exits 1 with NO recognizable report (IF-V4-09) -------
# rc=1 without "Found N known vulnerabilities" is CHECK_FAILED, not a
# finding: it must be NOT RUN, never FAIL.
run_scenario "pip-scan-garbage" clean scan-garbage ""
G="$SCEN_DIR/test-results/gates.json"
expect "9 PYTHON_DEPENDENCY_AUDIT NOT RUN (CHECK_FAILED, not a finding)" "$(gate_status "$G" PYTHON_DEPENDENCY_AUDIT)" "NOT RUN"
expect "9 NPM_FULL_LOCKFILE_AUDIT PASS" "$(gate_status "$G" NPM_FULL_LOCKFILE_AUDIT)" "PASS"
expect "9 driver exit nonzero" "$SCEN_RC" "1"
if grep -q "CHECK_FAILED" "$SCEN_DIR/test-results/gates.json"; then
  ok "9 gate detail names CHECK_FAILED for the pip-audit scan"
else bad "9 gate detail should name CHECK_FAILED"; fi
rm -rf "$SCEN_DIR"

# --- 10. pip-audit scan exits 2 (IF-V4-09 CHECK_FAILED) ----------------------
run_scenario "pip-scan-rc2" clean scan-rc2 ""
G="$SCEN_DIR/test-results/gates.json"
expect "10 PYTHON_DEPENDENCY_AUDIT NOT RUN (CHECK_FAILED rc=2)" "$(gate_status "$G" PYTHON_DEPENDENCY_AUDIT)" "NOT RUN"
expect "10 driver exit nonzero" "$SCEN_RC" "1"
rm -rf "$SCEN_DIR"

# --- 11. npm audit malformed JSON (IF-V4-09 CHECK_FAILED) --------------------
run_scenario "npm-malformed" malformed clean "$TMP/clean.json"
G="$SCEN_DIR/test-results/gates.json"
expect "11 NPM_FULL_LOCKFILE_AUDIT NOT RUN (malformed JSON)" "$(gate_status "$G" NPM_FULL_LOCKFILE_AUDIT)" "NOT RUN"
expect "11 GHSA_DIRECT_FALLBACK PASS (direct only)" "$(gate_status "$G" GHSA_DIRECT_FALLBACK)" "PASS"
expect "11 driver exit nonzero — malformed output cannot mask the missing audit" "$SCEN_RC" "1"
if grep -q "CHECK_FAILED" "$SCEN_DIR/test-results/gates.json"; then
  ok "11 gate detail names CHECK_FAILED for the malformed npm output"
else bad "11 gate detail should name CHECK_FAILED"; fi
rm -rf "$SCEN_DIR"

# --- 12. npm audit JSON DNS error (IF-V4-09 NOT RUN:DNS) ---------------------
run_scenario "npm-dns" dns clean "$TMP/clean.json"
G="$SCEN_DIR/test-results/gates.json"
expect "12 NPM_FULL_LOCKFILE_AUDIT NOT RUN (DNS)" "$(gate_status "$G" NPM_FULL_LOCKFILE_AUDIT)" "NOT RUN"
expect "12 GHSA_DIRECT_FALLBACK PASS (direct only)" "$(gate_status "$G" GHSA_DIRECT_FALLBACK)" "PASS"
expect "12 driver exit nonzero" "$SCEN_RC" "1"
if grep -q "NOT_RUN:DNS" "$SCEN_DIR/test-results/gates.json"; then
  ok "12 gate detail names NOT_RUN:DNS"
else bad "12 gate detail should name NOT_RUN:DNS"; fi
rm -rf "$SCEN_DIR"

# --- 13. npm audit JSON 429 + GHSA quota (IF-V4-09 NOT RUN:RATE_LIMIT) -------
run_scenario "npm-rate-ghsa-quota" rate clean "$TMP/quota.json"
G="$SCEN_DIR/test-results/gates.json"
expect "13 NPM_FULL_LOCKFILE_AUDIT NOT RUN (rate limit)" "$(gate_status "$G" NPM_FULL_LOCKFILE_AUDIT)" "NOT RUN"
expect "13 GHSA_DIRECT_FALLBACK NOT RUN (quota exhausted)" "$(gate_status "$G" GHSA_DIRECT_FALLBACK)" "NOT RUN"
expect "13 driver exit nonzero" "$SCEN_RC" "1"
if grep -q "NOT_RUN:RATE_LIMIT" "$SCEN_DIR/test-results/gates.json"; then
  ok "13 gate detail names NOT_RUN:RATE_LIMIT"
else bad "13 gate detail should name NOT_RUN:RATE_LIMIT"; fi
rm -rf "$SCEN_DIR"

# --- 14. npm audit JSON: low/moderate only is CLEAN at --audit-level=high ---
run_scenario "npm-lowonly" lowonly clean ""
G="$SCEN_DIR/test-results/gates.json"
expect "14 NPM_FULL_LOCKFILE_AUDIT PASS (0 high/critical)" "$(gate_status "$G" NPM_FULL_LOCKFILE_AUDIT)" "PASS"
expect "14 GHSA_DIRECT_FALLBACK NOT APPLICABLE (full audit executed)" "$(gate_status "$G" GHSA_DIRECT_FALLBACK)" "NOT APPLICABLE"
expect "14 driver exit 0" "$SCEN_RC" "0"
rm -rf "$SCEN_DIR"

rm -rf "$FAKEBIN_TEMPLATE" "$TMP"
echo
echo "dependency-gates: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
