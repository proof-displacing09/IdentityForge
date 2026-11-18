#!/usr/bin/env bash
# IdentityForge dependency gates (P0-03) — sourced by scripts/test-all.sh
# and by scripts/test-dependency-gates.sh (which drives these same
# functions with fake npm/pip-audit on PATH).
#
# Three separate gates; the GHSA direct fallback NEVER satisfies the
# full npm audit:
#   PYTHON_DEPENDENCY_AUDIT  pip-audit over backend/requirements-freeze.txt
#                            (full pinned runtime set).
#   NPM_FULL_LOCKFILE_AUDIT  `npm audit` over the ACTUAL resolved tree
#                            (frontend/package-lock.json).
#   GHSA_DIRECT_FALLBACK     informational GHSA check, DIRECT deps only.
#                            Runs ONLY when the full npm audit could not
#                            execute. A clean fallback leaves
#                            NPM_FULL_LOCKFILE_AUDIT NOT RUN, and a
#                            strict run then FAILS CLOSED. When the
#                            full audit executed (clean or with findings),
#                            the fallback is NOT APPLICABLE: it did not
#                            run, and a PASS there would be a phantom
#                            (P1-05, v4) — a PASS must mean the named
#                            gate actually ran and satisfied its check.
#
# IF-V4-09 (v5) — audit classification: an exit code alone cannot
# tell "vulnerabilities found" from "the auditor could not run".
#   * Tool install/verification is a SEPARATE measured step: each
#     auditor's executable + version is verified BEFORE the scan, and
#     the outcome is recorded machine-readably in
#     test-results/audit-tools.json (tool, version, install status,
#     scan status, classification). A failed install or a missing
#     tool is TOOL_UNAVAILABLE, never a vulnerability finding.
#   * pip-audit is pinned separately from project deps in
#     backend/requirements-audit.txt (auditor version, not a runtime
#     dependency). The scan exit code is only trusted as
#     "vulnerabilities found" when the log names the findings
#     ("Found N known vulnerabilities"); any other rc=1 is
#     CHECK_FAILED.
#   * npm audit runs with --json and a 120s bound; the JSON report is
#     classified by scripts/npm-audit-classify.py (metadata counts,
#     error codes). DNS errors, proxy failures, 403, 429, offline,
#     registry timeouts and malformed JSON are NOT RUN, never
#     findings. The full lockfile audit is never replaced by the
#     direct-only GHSA fallback.
#
# Sourcing contract (provided by the caller):
#   PY, PIP       — python/pip executables for the backend venv.
#   gate          — gate <id> <required_by> <label> <check...>
#   skip_gate     — skip_gate <id> <required_by> <label> <reason>
#   na_gate       — na_gate <id> <required_by> <label> <reason>
#                   (records status NOT APPLICABLE; the gate did not
#                   run because a superseding gate already covered it)
#   GATE_DETAIL   — one-line provenance note consumed by gate().
#
# Internal return-code contract of audit_backend / audit_frontend_npm:
#   0 = clean, 1 = vulnerabilities found (FAIL),
#   2 = tool unavailable (NOT RUN), 3 = check failed (NOT RUN).
# run_dependency_gates maps 2/3 to the gate status NOT RUN with the
# precise reason in the gate detail — strict mode then fails closed
# on the missing audit instead of reporting a phantom clean/finding.

# Tool-measurement state, consumed by write_audit_tools_json().
PIP_AUDIT_VERSION=""
PIP_AUDIT_TOOL_STATUS="not_checked"
PIP_AUDIT_SCAN_STATUS="not_run"
PIP_AUDIT_SCAN_RC=""
NPM_VERSION=""
NPM_TOOL_STATUS="not_checked"
NPM_SCAN_STATUS="not_run"
NPM_SCAN_RC=""
NPM_CLASSIFICATION=""
GHSA_STATUS="not_run"

audit_backend() {
  # Step 1 — verify the auditor tool (separate measured step).
  PIP_AUDIT_VERSION="$("$PY" -m pip_audit --version 2>/dev/null || true)"
  if [ -z "$PIP_AUDIT_VERSION" ]; then
    if [ -f backend/requirements-audit.txt ]; then
      "$PIP" install -q -r backend/requirements-audit.txt >/dev/null 2>&1 || {
        PIP_AUDIT_TOOL_STATUS="install_failed"
        echo "pip-audit could not be installed (see backend/requirements-audit.txt)."
        return 2
      }
    else
      "$PIP" install -q pip-audit >/dev/null 2>&1 || {
        PIP_AUDIT_TOOL_STATUS="install_failed"
        echo "pip-audit could not be installed."
        return 2
      }
    fi
    PIP_AUDIT_VERSION="$("$PY" -m pip_audit --version 2>/dev/null || true)"
    if [ -z "$PIP_AUDIT_VERSION" ]; then
      PIP_AUDIT_TOOL_STATUS="unavailable_after_install"
      echo "pip-audit installed but --version still fails."
      return 2
    fi
    PIP_AUDIT_TOOL_STATUS="installed"
  else
    PIP_AUDIT_TOOL_STATUS="available"
  fi
  echo "pip-audit tool: $PIP_AUDIT_VERSION"
  # Step 2 — the scan itself. rc=1 means "vulnerabilities found"
  # ONLY when the log names them; any other rc=1 is a check failure.
  "$PY" -m pip_audit -r backend/requirements-freeze.txt > test-results/audit-backend.log 2>&1
  local rc=$?
  PIP_AUDIT_SCAN_RC="$rc"
  cat test-results/audit-backend.log
  if [ "$rc" -eq 0 ]; then
    PIP_AUDIT_SCAN_STATUS="clean"
    return 0
  fi
  if [ "$rc" -eq 1 ] && grep -qE "Found [0-9]+ known vulnerabilities? in" test-results/audit-backend.log; then
    PIP_AUDIT_SCAN_STATUS="vulnerabilities_found"
    return 1
  fi
  PIP_AUDIT_SCAN_STATUS="check_failed"
  echo "pip-audit exited rc=$rc without a recognizable vulnerability report (see test-results/audit-backend.log)."
  return 3
}

# npm audit over the resolved lockfile tree. Sets NPM_BLOCKED=1 when
# the classifier reports the endpoint/DNS/timeout as the reason the
# audit did not execute (kept for the run_dependency_gates branch
# below); NPM_CLASSIFICATION holds the full classifier verdict.
NPM_BLOCKED=0
audit_frontend_npm() {
  # Step 1 — verify the auditor tool (separate measured step).
  NPM_VERSION="$(npm --version 2>/dev/null || true)"
  if [ -z "$NPM_VERSION" ]; then
    NPM_TOOL_STATUS="unavailable"
    echo "npm is not available — cannot run the lockfile audit."
    return 2
  fi
  NPM_TOOL_STATUS="available"
  echo "npm tool: $NPM_VERSION"
  # Step 2 — the scan: JSON report + 120s bound, stdout and stderr
  # kept SEPARATE so the JSON stays parseable.
  (cd frontend && timeout 120 npm audit --audit-level=high --json > ../test-results/audit-frontend.log 2> ../test-results/audit-frontend.err; echo $? > ../test-results/audit-frontend.rc)
  local rc
  rc="$(cat test-results/audit-frontend.rc)"
  NPM_SCAN_RC="$rc"
  cat test-results/audit-frontend.log
  NPM_CLASSIFICATION="$(python3 scripts/npm-audit-classify.py test-results/audit-frontend.log --stderr test-results/audit-frontend.err --rc "$rc" 2>&1)"
  local cls_rc=$?
  echo "$NPM_CLASSIFICATION"
  case "$cls_rc" in
    0) NPM_SCAN_STATUS="clean"; return 0 ;;
    1) NPM_SCAN_STATUS="vulnerabilities_found"; return 1 ;;
    2)
      NPM_SCAN_STATUS="not_run"
      case "$NPM_CLASSIFICATION" in
        *BLOCKED*|*TIMEOUT*|*DNS*|*RATE_LIMIT*|*OFFLINE*|*REGISTRY_ERROR*) NPM_BLOCKED=1 ;;
      esac
      return 2 ;;
    *) NPM_SCAN_STATUS="check_failed"; return 3 ;;
  esac
}

# GHSA direct-dependency fallback (informational only). Records the
# GHSA_DIRECT_FALLBACK gate itself: 0 = fallback ran clean (direct
# deps only), 1 = high/critical advisory found (FAIL), 2 = source
# unreachable/rate-limited (NOT RUN). NEVER satisfies
# NPM_FULL_LOCKFILE_AUDIT — callers must not read it as full coverage.
run_ghsa_fallback() {
  echo "Full npm audit unavailable — falling back to the GitHub Advisory"
  echo "Database check of pinned DIRECT dependencies only"
  echo "(scripts/npm-advisory-check.py; transitive deps NOT checked)."
  python3 scripts/npm-advisory-check.py
  local grc=$?
  if [ "$grc" -eq 0 ]; then
    GHSA_STATUS="clean_direct_only"
    GATE_DETAIL="direct dependencies only — transitive advisories NOT checked; NPM_FULL_LOCKFILE_AUDIT remains NOT RUN (see test-results/audit-frontend-ghsa.json)"
    gate GHSA_DIRECT_FALLBACK offline "GHSA direct-dependency fallback (informational, direct deps only)" true
  elif [ "$grc" -eq 1 ]; then
    GHSA_STATUS="advisory_found"
    GATE_DETAIL="GHSA found high/critical advisories affecting direct deps — see test-results/audit-frontend-ghsa.json"
    gate GHSA_DIRECT_FALLBACK offline "GHSA direct-dependency fallback (informational, direct deps only)" false
  else
    GHSA_STATUS="unreachable"
    skip_gate GHSA_DIRECT_FALLBACK offline "GHSA direct-dependency fallback (informational, direct deps only)" \
      "advisory source unreachable or rate-limited (rc=$grc); npm audit also unavailable"
  fi
}

# Write the tool-measurement record (IF-V4-09): one JSON object per
# auditor with install/scan status and classification, so a later
# reader can tell TOOL_UNAVAILABLE / CHECK_FAILED /
# VULNERABILITIES_FOUND apart without re-running anything. Values
# pass via the environment so quotes/newlines in classifier output
# cannot break the JSON.
write_audit_tools_json() {
  PIP_AUDIT_VERSION="$PIP_AUDIT_VERSION" \
  PIP_AUDIT_TOOL_STATUS="$PIP_AUDIT_TOOL_STATUS" \
  PIP_AUDIT_SCAN_STATUS="$PIP_AUDIT_SCAN_STATUS" \
  PIP_AUDIT_SCAN_RC="$PIP_AUDIT_SCAN_RC" \
  NPM_VERSION="$NPM_VERSION" \
  NPM_TOOL_STATUS="$NPM_TOOL_STATUS" \
  NPM_SCAN_STATUS="$NPM_SCAN_STATUS" \
  NPM_SCAN_RC="$NPM_SCAN_RC" \
  NPM_CLASSIFICATION="$NPM_CLASSIFICATION" \
  GHSA_STATUS="$GHSA_STATUS" \
  python3 - test-results/audit-tools.json <<'PY'
import json, os, sys
env = os.environ
doc = {
  "pip_audit": {
    "tool": "pip-audit",
    "version": env.get("PIP_AUDIT_VERSION", ""),
    "install_status": env.get("PIP_AUDIT_TOOL_STATUS", ""),
    "scan_status": env.get("PIP_AUDIT_SCAN_STATUS", ""),
    "scan_rc": env.get("PIP_AUDIT_SCAN_RC", ""),
    "pin_file": "backend/requirements-audit.txt",
  },
  "npm_audit": {
    "tool": "npm audit",
    "version": env.get("NPM_VERSION", ""),
    "install_status": env.get("NPM_TOOL_STATUS", ""),
    "scan_status": env.get("NPM_SCAN_STATUS", ""),
    "scan_rc": env.get("NPM_SCAN_RC", ""),
    "classification": env.get("NPM_CLASSIFICATION", ""),
    "timeout_seconds": 120,
  },
  "ghsa_direct_fallback": {
    "tool": "scripts/npm-advisory-check.py (GitHub Advisory Database)",
    "coverage": "direct dependencies only; transitive advisories require npm audit",
    "status": env.get("GHSA_STATUS", ""),
  },
}
json.dump(doc, open(sys.argv[1], "w"), indent=2)
PY
}

# Run all three dependency gates and record them via gate()/skip_gate().
run_dependency_gates() {
  local backend_rc npm_rc
  audit_backend; backend_rc=$?
  if [ "$backend_rc" -eq 0 ]; then
    GATE_DETAIL="pip-audit $PIP_AUDIT_VERSION — clean (full pinned runtime set)"
    gate PYTHON_DEPENDENCY_AUDIT offline "pip-audit over backend/requirements-freeze.txt (full pinned runtime set)" true
  elif [ "$backend_rc" -eq 1 ]; then
    GATE_DETAIL="pip-audit $PIP_AUDIT_VERSION found vulnerabilities — see test-results/audit-backend.log"
    gate PYTHON_DEPENDENCY_AUDIT offline "pip-audit over backend/requirements-freeze.txt (full pinned runtime set)" false
  elif [ "$backend_rc" -eq 2 ]; then
    skip_gate PYTHON_DEPENDENCY_AUDIT offline "pip-audit over backend/requirements-freeze.txt (full pinned runtime set)" \
      "TOOL_UNAVAILABLE: pip-audit could not be installed or verified ($PIP_AUDIT_TOOL_STATUS) — see test-results/audit-tools.json"
  else
    skip_gate PYTHON_DEPENDENCY_AUDIT offline "pip-audit over backend/requirements-freeze.txt (full pinned runtime set)" \
      "CHECK_FAILED: pip-audit exited rc=$PIP_AUDIT_SCAN_RC without a recognizable vulnerability report — see test-results/audit-backend.log"
  fi

  audit_frontend_npm; npm_rc=$?
  if [ "$npm_rc" -eq 0 ]; then
    GATE_DETAIL="npm $NPM_VERSION audit clean at --audit-level=high (JSON metadata, 0 high/critical)"
    gate NPM_FULL_LOCKFILE_AUDIT offline "npm audit over the resolved lockfile tree (package-lock.json)" true
    # P1-05: the full audit executed clean, so the fallback is NOT
    # APPLICABLE — it did not run. Recording PASS here would be a
    # phantom: a PASS must mean the named gate actually ran.
    GHSA_STATUS="not_applicable"
    na_gate GHSA_DIRECT_FALLBACK offline "GHSA direct-dependency fallback (informational, direct deps only)" \
      "not applicable — npm audit executed clean; full lockfile coverage subsumes the direct-only fallback, which did not run"
  elif [ "$npm_rc" -eq 1 ]; then
    GATE_DETAIL="npm $NPM_VERSION audit found vulnerabilities — see test-results/audit-frontend.log"
    gate NPM_FULL_LOCKFILE_AUDIT offline "npm audit over the resolved lockfile tree (package-lock.json)" false
    # P1-05: the full audit executed (and found things), so the
    # fallback is NOT APPLICABLE — it did not run and must never be
    # marked PASS alongside a failed full audit.
    GHSA_STATUS="not_applicable"
    na_gate GHSA_DIRECT_FALLBACK offline "GHSA direct-dependency fallback (informational, direct deps only)" \
      "not applicable — npm audit executed and found vulnerabilities; the direct-only fallback did not run"
  elif [ "$npm_rc" -eq 2 ]; then
    # The audit did NOT execute (blocked/DNS/timeout/rate-limit/
    # offline/tool-unavailable): the full gate stays NOT RUN and a
    # strict run fails closed on it. The GHSA fallback may add
    # direct-dep information, but it never satisfies this gate.
    skip_gate NPM_FULL_LOCKFILE_AUDIT offline "npm audit over the resolved lockfile tree (package-lock.json)" \
      "$NPM_CLASSIFICATION — see test-results/audit-frontend.log; run on a machine with registry access"
    run_ghsa_fallback
  else
    skip_gate NPM_FULL_LOCKFILE_AUDIT offline "npm audit over the resolved lockfile tree (package-lock.json)" \
      "CHECK_FAILED: $NPM_CLASSIFICATION — see test-results/audit-frontend.log"
    run_ghsa_fallback
  fi
  write_audit_tools_json
}
