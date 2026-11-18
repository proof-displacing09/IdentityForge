#!/usr/bin/env bash
# Regression test for IF-V5-01 (Trustline v6): the docs-contract checker
# must be independent of the path the tree is checked out under.
#
# v5 bug: scripts/validate-docs-contract.py filtered harvested source
# files on ABSOLUTE path parts (p.parts) against SKIP_DIRS containing
# "data". Any ancestor directory named `data` (e.g. /tmp/data/...) made
# the harvest skip EVERY source file, so legitimate constants
# (OFFLINE_FIXTURE, LIVE_KEYCLOAK, AUTH_STARTED, ...) looked
# undocumented and the gate failed with 104 false violations.
#
# This test builds equivalent minimal fixtures in three checkout
# locations and asserts the gate behaves identically in all three:
#   1. a normal path
#   2. under an ancestor directory named `data`
#   3. under a path containing SPACES
# For each path it asserts:
#   a. clean docs  -> exit 0, "0 violation(s)" (no false positives)
#   b. docs with a deliberately stale reason code (assembled at
#      runtime as STALE_TOKEN — the literal must not appear in this
#      file: the checker scans scripts/ too, and the denylist would
#      flag the test itself)
#      -> exit NONZERO (the gate still catches real drift)
#   c. a token that exists ONLY below a skipped directory under the
#      root (backend/src/data/) -> exit NONZERO (below-root exclusions
#      are preserved: the fix must not whitelist everything)
#   d. a token that exists ONLY via a symlink escaping the root
#      -> exit NONZERO (symlink escapes are skipped, not harvested)
#   e. an empty scan directory -> exit NONZERO (no green gate on an
#      empty scan)
#
# IF-V7.1-05 (Trustline v7.2): the quickstart archive-name check.
# The checker reads the current final archive filename from the
# LAST "Operation Trustline" section of docs/RELEASE_MANIFEST.md
# and requires the CURRENT quickstart sections (REVIEWER_GUIDE.md
# section 0, WINDOWS_SETUP.md section 3) to name it, or an explicit
# variable. Added cases, in all three paths:
#   f. a stale *CANDIDATE archive name in a quickstart section
#      -> exit NONZERO (the v6 REVIEW_CANDIDATE name must fail)
#   g. a different concrete final name (the v7.1 FINAL) in a
#      quickstart section -> exit NONZERO
#   h. an explicit variable ($ZIP) in a quickstart section -> exit 0
#   i. a stale *CANDIDATE name in a HISTORICAL narrative section of
#      the same file (outside the quickstart region) -> exit 0
#      (history may name old archives; only quickstart may not)
# The fixture manifest + a clean quickstart (current filename) are
# part of build_fixture, so case (a) also proves the clean
# quickstart passes. Zip names are assembled at runtime, never
# written as literals in this file (same discipline as the probe
# tokens above: the checker harvests scripts/, and a literal would
# defeat the probe it is meant to exercise).
#
# v7.3: the fixture manifest moves to the v7.3 release, so the v7.2
# FINAL name is now the newly-stale name: case (g) plants the v7.2
# FINAL name (was the v7.1 FINAL in v7.2), and new case (j) plants
# the v7.1 FINAL name, so the regression proves staleness for more
# than just the immediately-previous release. Total: 30 checks
# (10 cases x 3 paths).
#
# v7.3.1: the fixture manifest moves to the v7.3.1 release (product
# version 1.7.4), so the v7.3 FINAL name is now the newly-stale
# name: case (g) plants the v7.3 FINAL name, case (j) plants the
# older-stale v7.2 FINAL name, and new case (k) plants the
# oldest-stale v7.1 FINAL name — staleness is proven across three
# releases, not just the immediately-previous one. Total: 33 checks
# (11 cases x 3 paths).
#
# v8 (IF-V8-80, WS3): the fixture manifest moves to the v8 release
# (product version 1.8.0), so the v7.3.1 FINAL name joins the stale
# set (cases (g)/(j)/(k) still plant older names). New check-6 cases:
#   l. stale release-label prose ("the v7.3 final release name") in a
#      quickstart region -> exit NONZERO (check 6a)
#   m. stale "release version 1.7.3" prose anywhere in a guide
#      -> exit NONZERO (check 6b)
#   n. CURRENT release prose ("the v8 final release name",
#      "release version 1.8.0") -> exit 0 (no false positives)
# Total: 42 checks (14 cases x 3 paths).
#
# v8.0.1: the fixture manifest moves to the v8.0.1 release (product
# version 1.8.1), so the v8 FINAL name is now the newly-stale name:
# case (g) plants the v8 FINAL name, case (j) plants the older-stale
# v7.3.1 FINAL name, and case (k) plants the oldest-stale v7.3 FINAL
# name. Check-6 stale prose moves with it: case (l) plants "the v8
# final release name", case (m) plants "release version 1.8.0", and
# case (n) proves the CURRENT prose ("the v8.0.1 final release name",
# "release version 1.8.1") passes. New check-7 cases (o)/(p) prove the
# README active-count regression (see scripts/validate-docs-contract.py
# check 7): (o) plants stale active counts ("(340 tests",
# "**16 explicit gates**" with the 16-name list) -> exit NONZERO;
# (p) proves the current active counts ("(482 tests",
# "**18 explicit gates**" with all 18 names) -> exit 0. Total: 48
# checks (16 cases x 3 paths).
#
# The checker under test is the real scripts/validate-docs-contract.py,
# invoked with --root pointing at each fixture. Stdlib-only python3;
# no Docker, no venv, no network. Exits 0 only if every case behaves
# as specified in all three paths.
set -uo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
CHECKER="$ROOT/scripts/validate-docs-contract.py"
MODELS="$ROOT/backend/src/identityforge/models.py"

PASS_COUNT=0
FAIL_COUNT=0
failures=()

ok() { # ok <label>
  PASS_COUNT=$((PASS_COUNT + 1))
  echo "PASS: $1"
}
not_ok() { # not_ok <label> <detail>
  FAIL_COUNT=$((FAIL_COUNT + 1))
  failures+=("$1 -- $2")
  echo "FAIL: $1 -- $2"
}

# build_fixture <dir> — minimal tree the checker can run against:
# real models.py (FailureReason values + report fields), a small
# source file with legitimate event-stage constants, and docs that
# quote them in backticks.
build_fixture() {
  local dir="$1"
  mkdir -p "$dir/backend/src/identityforge" "$dir/docs" "$dir/docs-probe" \
    "$dir/docs-escape" "$dir/emptydir" "$dir/backend/src/data" \
    "$dir/frontend/src/node_modules"
  cp "$MODELS" "$dir/backend/src/identityforge/models.py"
  cat > "$dir/backend/src/identityforge/stages.py" <<'PY'
"""Fixture source: legitimate API event-stage constants.

These are NOT FailureReason codes — they are the stage names the API
records on live transactions — but they are real constants defined in
source, so the docs-contract gate must accept them when quoted in docs.
"""
AUTH_STARTED = "AUTH_STARTED"
CALLBACK_RECEIVED = "CALLBACK_RECEIVED"
TOKEN_EXCHANGED = "TOKEN_EXCHANGED"
PY
  cat > "$dir/docs/NOTES.md" <<'MD'
# Fixture notes

The live flow records `AUTH_STARTED`, then `CALLBACK_RECEIVED`, then
`TOKEN_EXCHANGED`. A rejected token carries `WRONG_AUDIENCE`.
Provenance is `LIVE_KEYCLOAK` for real logins and `OFFLINE_FIXTURE`
for offline fixtures.
MD
  # Token that exists ONLY under a skipped directory BELOW the root.
  # backend/src/data/ is excluded by SKIP_DIRS ("data") — but only
  # because it is below the project root, never because of an ancestor.
  printf '%s = "%s"\n' "$PROBE_DATA_TOKEN" "$PROBE_DATA_TOKEN" \
    > "$dir/backend/src/data/only.py"
  printf '# Exclusion probe\n\nThis token is defined only under backend/src/data/ below the root:\n`%s`.\n' \
    "$PROBE_DATA_TOKEN" > "$dir/docs-probe/EXCLUSION.md"
  # Token that exists ONLY outside the root, reached via a symlink.
  # $OUTSIDE_PY lives next to the fixtures (outside every fixture
  # root); the symlink inside backend/src points at it.
  ln -s "$OUTSIDE_PY" "$dir/backend/src/escape_link.py"
  printf '# Symlink-escape probe\n\nThis token is defined only outside the project root: `%s`.\n' \
    "$PROBE_ESCAPE_TOKEN" > "$dir/docs-escape/ESCAPE.md"
  # IF-V7.1-05 fixture manifest: the current release is v8.0.1 and
  # its final archive is $CURRENT_ZIP. The checker reads this file
  # to learn the expected quickstart filename (check 5) and the
  # current release label + version (check 6, IF-V8-80).
  cat > "$dir/docs/RELEASE_MANIFEST.md" <<MD
# Release Manifest — IdentityForge (fixture)

## Operation Trustline v8.0.1 — targeted documentation closure (2026-11-13)

- **Version:** 1.8.1 (Operation Trustline v8.0.1)
- **Filename:** \`$CURRENT_ZIP\`
- **Counts (current release):** backend pytest 482; test-all gates 18.
MD
  # Check-7 fixture runners: the 18 gate IDs as real call sites, so
  # the checker's gate count has code ground truth in the fixture
  # (15 direct call sites in test-all.sh + 3 dependency gates in
  # audit-gates.sh, the same split as the real tree).
  mkdir -p "$dir/scripts"
  cat > "$dir/scripts/test-all.sh" <<'SH'
gate OFFLINE_UNIT offline "backend" true
gate OFFLINE_SCENARIOS offline "scenarios" true
gate DOCS_CONTRACT offline "docs" true
gate DOCS_CONTRACT_PATHS offline "paths" true
gate VERSION_CONTRACT offline "version" true
gate FRONTEND_TYPECHECK offline "typecheck" true
gate FRONTEND_UNIT offline "unit" true
gate FRONTEND_BUILD offline "build" true
gate COMPOSE_CONFIG offline "compose" true
gate CLEAN_COMPOSE_BUILD_BOOT full "boot" true
gate REAL_KEYCLOAK_LOGIN full "login" true
gate REAL_SECURITY_NEGATIVES full "negatives" true
gate REAL_LAB_RESET full "reset" true
gate PLAYWRIGHT_E2E full "e2e" true
gate RESPONSIVE_QA full "responsive" true
SH
  cat > "$dir/scripts/audit-gates.sh" <<'SH'
gate PYTHON_DEPENDENCY_AUDIT offline "pip-audit" true
gate NPM_FULL_LOCKFILE_AUDIT offline "npm audit" true
gate GHSA_DIRECT_FALLBACK offline "GHSA fallback" true
SH
  # Clean quickstart (case (a) also proves this passes): the
  # REVIEWER_GUIDE section 0 hash commands name the current archive.
  cat > "$dir/docs/REVIEWER_GUIDE.md" <<MD
# Reviewer Guide (fixture)

## 0. Before you start

Verify the archive first:

\`\`\`powershell
Get-FileHash .\\$CURRENT_ZIP -Algorithm SHA256
\`\`\`

\`\`\`bash
sha256sum $CURRENT_ZIP
\`\`\`

## 1. Boot the lab

Not a quickstart region.
MD
}

# run_checker <fixture> <scan...> — runs the real checker, prints its
# one-line summary, returns its exit code.
run_checker() {
  local fixture="$1"; shift
  python3 "$CHECKER" --root "$fixture" --scan "$@"
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
# Probe tokens are assembled at runtime, never written as literals:
# the checker harvests UPPER_SNAKE tokens from scripts/, so a literal
# probe token in this file would itself be harvested and defeat the
# probe it is meant to exercise.
PROBE_DATA_TOKEN="ONLY_IN_DATA_$(printf 'DIR')"
PROBE_ESCAPE_TOKEN="ESCAPED_$(printf 'TOKEN')"
# Deliberately stale reason code for the negative control, assembled
# at runtime for the same reason (never a literal in this file).
STALE_TOKEN="AUDIENCE_$(printf 'MISMATCH')"
# Archive names for the IF-V7.1-05 cases, assembled at runtime for
# the same reason: the checker harvests scripts/, and a literal
# stale name in this file would defeat the probe.
ZIP_BASE="IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE"
CURRENT_ZIP="${ZIP_BASE}_V8.0.1_FINAL_20261113.zip"
STALE_ZIP="${ZIP_BASE}_V6_REVIEW_$(printf 'CANDIDATE').zip"
# v8.0.1: the v8 FINAL name is now the newly-stale name (case (g));
# (j) plants the older-stale v7.3.1 FINAL name; (k) the oldest-stale
# v7.3 FINAL name.
WRONG_ZIP="${ZIP_BASE}_V8_FINAL_20261113.zip"
WRONG2_ZIP="${ZIP_BASE}_V7.3.1_FINAL_20261112.zip"
WRONG3_ZIP="${ZIP_BASE}_V7.3_FINAL_20261112.zip"
# Check-6 stale prose, assembled at runtime like the zip names above.
STALE_LABEL="v$(printf '8')"
STALE_VERSION="1.$(printf '8.0')"
# Shared "outside the root" file for the symlink-escape probe.
OUTSIDE_PY="$TMP/outside.py"
printf '%s = "%s"\n' "$PROBE_ESCAPE_TOKEN" "$PROBE_ESCAPE_TOKEN" > "$OUTSIDE_PY"

# The three checkout locations. The `data` ancestor is the exact v5
# failure shape; the spaces path is the second classic checkout trap
# (Pass B clean-extraction shape).
declare -a PATHS=(
  "$TMP/normal/identityforge"
  "$TMP/data/identityforge"
  "$TMP/path with spaces/identityforge"
)

for fixture in "${PATHS[@]}"; do
  echo
  echo "===== fixture: $fixture ====="
  build_fixture "$fixture"

  # (a) clean docs -> exit 0, zero violations.
  out="$(run_checker "$fixture" docs 2>&1)"; rc=$?
  if [ "$rc" -eq 0 ] && echo "$out" | grep -q "0 violation(s)"; then
    ok "clean docs PASS in $fixture"
  else
    not_ok "clean docs in $fixture" "expected exit 0 + 0 violations, got rc=$rc: $out"
  fi

  # (b) deliberately stale reason code -> exit NONZERO.
  mkdir -p "$fixture/docs-stale"
  cp "$fixture/docs/NOTES.md" "$fixture/docs-stale/NOTES.md"
  printf '\nA stale code must never pass: `%s`.\n' "$STALE_TOKEN" >> "$fixture/docs-stale/NOTES.md"
  out="$(run_checker "$fixture" docs-stale 2>&1)"; rc=$?
  if [ "$rc" -ne 0 ]; then
    ok "stale code FAILS (rc=$rc) in $fixture"
  else
    not_ok "stale code in $fixture" "expected nonzero exit, got rc=0: $out"
  fi

  # (c) token only under a skipped dir BELOW the root -> NONZERO.
  out="$(run_checker "$fixture" docs-probe 2>&1)"; rc=$?
  if [ "$rc" -ne 0 ]; then
    ok "below-root data/ exclusion still applies (rc=$rc) in $fixture"
  else
    not_ok "below-root data/ exclusion in $fixture" "expected nonzero exit ($PROBE_DATA_TOKEN must not be harvested), got rc=0: $out"
  fi

  # (d) token only via a symlink escaping the root -> NONZERO.
  out="$(run_checker "$fixture" docs-escape 2>&1)"; rc=$?
  if [ "$rc" -ne 0 ]; then
    ok "symlink escape skipped (rc=$rc) in $fixture"
  else
    not_ok "symlink escape in $fixture" "expected nonzero exit ($PROBE_ESCAPE_TOKEN must not be harvested), got rc=0: $out"
  fi

  # (e) empty scan directory -> NONZERO (no green gate on empty scan).
  out="$(run_checker "$fixture" emptydir 2>&1)"; rc=$?
  if [ "$rc" -ne 0 ]; then
    ok "empty scan FAILS (rc=$rc) in $fixture"
  else
    not_ok "empty scan in $fixture" "expected nonzero exit, got rc=0: $out"
  fi

  # (f) stale *CANDIDATE name in a quickstart section -> NONZERO.
  mkdir -p "$fixture/docs-stalezip"
  cat > "$fixture/docs-stalezip/REVIEWER_GUIDE.md" <<MD
# Reviewer Guide (stale-zip fixture)

## 0. Before you start

\`\`\`powershell
Get-FileHash .\\$STALE_ZIP -Algorithm SHA256
\`\`\`

## 1. Boot the lab
MD
  out="$(run_checker "$fixture" docs-stalezip 2>&1)"; rc=$?
  if [ "$rc" -ne 0 ] && echo "$out" | grep -q "CANDIDATE archive"; then
    ok "stale CANDIDATE name in quickstart FAILS (rc=$rc) in $fixture"
  else
    not_ok "stale CANDIDATE name in $fixture" "expected nonzero exit + CANDIDATE reason, got rc=$rc: $out"
  fi

  # (g) a different concrete final name (v8 FINAL — the newly-stale
  # name in v8.0.1) in a quickstart section -> NONZERO.
  mkdir -p "$fixture/docs-wrongzip"
  cat > "$fixture/docs-wrongzip/REVIEWER_GUIDE.md" <<MD
# Reviewer Guide (wrong-zip fixture)

## 0. Before you start

\`\`\`bash
sha256sum $WRONG_ZIP
\`\`\`

## 1. Boot the lab
MD
  out="$(run_checker "$fixture" docs-wrongzip 2>&1)"; rc=$?
  if [ "$rc" -ne 0 ] && echo "$out" | grep -q "current release filename is"; then
    ok "wrong final name in quickstart FAILS (rc=$rc) in $fixture"
  else
    not_ok "wrong final name in $fixture" "expected nonzero exit + current-filename reason, got rc=$rc: $out"
  fi

  # (h) an explicit variable ($ZIP) in a quickstart section -> exit 0.
  mkdir -p "$fixture/docs-varzip"
  cat > "$fixture/docs-varzip/REVIEWER_GUIDE.md" <<'MD'
# Reviewer Guide (variable-zip fixture)

## 0. Before you start

```powershell
Get-FileHash $ZIP -Algorithm SHA256
```

```bash
sha256sum $ZIP
```

## 1. Boot the lab
MD
  out="$(run_checker "$fixture" docs-varzip 2>&1)"; rc=$?
  if [ "$rc" -eq 0 ] && echo "$out" | grep -q "0 violation(s)"; then
    ok "variable \$ZIP in quickstart PASSES in $fixture"
  else
    not_ok "variable \$ZIP in $fixture" "expected exit 0 + 0 violations, got rc=$rc: $out"
  fi

  # (j) an OLDER stale final name (v7.3.1 FINAL) in a quickstart
  # section -> NONZERO (staleness is not only about the
  # immediately-previous release).
  mkdir -p "$fixture/docs-wrongzip2"
  cat > "$fixture/docs-wrongzip2/REVIEWER_GUIDE.md" <<MD
# Reviewer Guide (wrong-zip-2 fixture)

## 0. Before you start

\`\`\`bash
sha256sum $WRONG2_ZIP
\`\`\`

## 1. Boot the lab
MD
  out="$(run_checker "$fixture" docs-wrongzip2 2>&1)"; rc=$?
  if [ "$rc" -ne 0 ] && echo "$out" | grep -q "current release filename is"; then
    ok "older stale final name in quickstart FAILS (rc=$rc) in $fixture"
  else
    not_ok "older stale final name in $fixture" "expected nonzero exit + current-filename reason, got rc=$rc: $out"
  fi

  # (k) the OLDEST stale final name (v7.3 FINAL) in a quickstart
  # section -> NONZERO (v8.0.1: staleness is proven across three
  # releases — the newly-stale v8, the older-stale v7.3.1, and the
  # oldest-stale v7.3 — so a quickstart naming any retired release
  # fails, not just the immediately-previous one).
  mkdir -p "$fixture/docs-wrongzip3"
  cat > "$fixture/docs-wrongzip3/REVIEWER_GUIDE.md" <<MD
# Reviewer Guide (wrong-zip-3 fixture)

## 0. Before you start

\`\`\`bash
sha256sum $WRONG3_ZIP
\`\`\`

## 1. Boot the lab
MD
  out="$(run_checker "$fixture" docs-wrongzip3 2>&1)"; rc=$?
  if [ "$rc" -ne 0 ] && echo "$out" | grep -q "current release filename is"; then
    ok "oldest stale final name in quickstart FAILS (rc=$rc) in $fixture"
  else
    not_ok "oldest stale final name in $fixture" "expected nonzero exit + current-filename reason, got rc=$rc: $out"
  fi

  # (i) a stale *CANDIDATE name in a HISTORICAL narrative section of
  # the same file (outside the quickstart region) -> exit 0.
  mkdir -p "$fixture/docs-history"
  cat > "$fixture/docs-history/REVIEWER_GUIDE.md" <<MD
# Reviewer Guide (history fixture)

## 0. Before you start

\`\`\`bash
sha256sum $CURRENT_ZIP
\`\`\`

## History

The v6 archive was named $STALE_ZIP; that name is history now.
MD
  out="$(run_checker "$fixture" docs-history 2>&1)"; rc=$?
  if [ "$rc" -eq 0 ] && echo "$out" | grep -q "0 violation(s)"; then
    ok "stale name in historical section PASSES in $fixture"
  else
    not_ok "stale name in historical section in $fixture" "expected exit 0 + 0 violations, got rc=$rc: $out"
  fi

  # (l) CHECK 6a (IF-V8-80, v8; stale window moved in v8.0.1): stale release-label prose ("the v8
  # final release name") in a quickstart region -> NONZERO, even
  # though the archive command itself names the current file.
  mkdir -p "$fixture/docs-staleprose"
  cat > "$fixture/docs-staleprose/REVIEWER_GUIDE.md" <<MD
# Reviewer Guide (stale-prose fixture)

## 0. Before you start

\`\`\`bash
sha256sum $CURRENT_ZIP
\`\`\`

(Use the actual ZIP filename from the delivery message — the name
above is the $STALE_LABEL final release name.)

## 1. Boot the lab
MD
  out="$(run_checker "$fixture" docs-staleprose 2>&1)"; rc=$?
  if [ "$rc" -ne 0 ] && echo "$out" | grep -q "older release label"; then
    ok "stale release-label prose in quickstart FAILS (rc=$rc) in $fixture"
  else
    not_ok "stale release-label prose in $fixture" "expected nonzero exit + older-label reason, got rc=$rc: $out"
  fi

  # (m) CHECK 6b (IF-V8-80, v8; stale window moved in v8.0.1): stale "release version 1.8.0" prose
  # anywhere in a guide -> NONZERO (the version prose must match the
  # manifest's current version; the guides carry no history sections).
  mkdir -p "$fixture/docs-staleversion"
  cat > "$fixture/docs-staleversion/REVIEWER_GUIDE.md" <<MD
# Reviewer Guide (stale-version fixture)

## 0. Before you start

\`\`\`bash
sha256sum $CURRENT_ZIP
\`\`\`

## 1. Gates

Every authoritative version value must equal the release version $STALE_VERSION.
MD
  out="$(run_checker "$fixture" docs-staleversion 2>&1)"; rc=$?
  if [ "$rc" -ne 0 ] && echo "$out" | grep -q "release version $STALE_VERSION"; then
    ok "stale release-version prose FAILS (rc=$rc) in $fixture"
  else
    not_ok "stale release-version prose in $fixture" "expected nonzero exit + release-version reason, got rc=$rc: $out"
  fi

  # (n) CHECK 6 positive control: CURRENT release prose ("the v8.0.1
  # final release name", "release version 1.8.1") -> exit 0.
  mkdir -p "$fixture/docs-currentprose"
  cat > "$fixture/docs-currentprose/REVIEWER_GUIDE.md" <<MD
# Reviewer Guide (current-prose fixture)

## 0. Before you start

\`\`\`bash
sha256sum $CURRENT_ZIP
\`\`\`

(Use the actual ZIP filename from the delivery message — the name
above is the v8.0.1 final release name.)

## 1. Gates

Every authoritative version value must equal the release version 1.8.1.
MD
  out="$(run_checker "$fixture" docs-currentprose 2>&1)"; rc=$?
  if [ "$rc" -eq 0 ] && echo "$out" | grep -q "0 violation(s)"; then
    ok "current release prose PASSES in $fixture"
  else
    not_ok "current release prose in $fixture" "expected exit 0 + 0 violations, got rc=$rc: $out"
  fi

  # (o) CHECK 7 (v8.0.1, WS1): planted-STALE active counts in the
  # README's ## Tests section ("(340 tests", "**16 explicit gates**"
  # with the 16-name list) -> NONZERO. The dated history below the
  # Tests section is NOT planted here — case (o) proves the active
  # prose fails, not the history.
  mkdir -p "$fixture/readme-stale"
  cat > "$fixture/readme-stale/README.md" <<MD
# IdentityForge (fixture)

## Tests

\`\`\`bash
cd backend && python -m pytest -q     # backend offline suite (340 tests, parent-verified)
\`\`\`

The gate runner reports **16 explicit gates** with PASS / FAIL / NOT RUN
/ NOT APPLICABLE: OFFLINE_UNIT, OFFLINE_SCENARIOS,
DOCS_CONTRACT, FRONTEND_TYPECHECK, FRONTEND_UNIT, FRONTEND_BUILD,
PYTHON_DEPENDENCY_AUDIT, NPM_FULL_LOCKFILE_AUDIT, GHSA_DIRECT_FALLBACK,
COMPOSE_CONFIG, CLEAN_COMPOSE_BUILD_BOOT, REAL_KEYCLOAK_LOGIN,
REAL_SECURITY_NEGATIVES, REAL_LAB_RESET, PLAYWRIGHT_E2E, RESPONSIVE_QA.
MD
  out="$(run_checker "$fixture" readme-stale 2>&1)"; rc=$?
  if [ "$rc" -ne 0 ] && echo "$out" | grep -q "340 tests"; then
    ok "stale active README counts FAIL (rc=$rc) in $fixture"
  else
    not_ok "stale active README counts in $fixture" "expected nonzero exit + 340-tests reason, got rc=$rc: $out"
  fi

  # (p) CHECK 7 positive control: CURRENT active counts ("(482 tests",
  # "**18 explicit gates**" with all 18 names) -> exit 0. A dated
  # history bullet naming the OLD counts must ALSO pass: only the
  # ## Tests region is scanned, never the history below it.
  mkdir -p "$fixture/readme-current"
  cat > "$fixture/readme-current/README.md" <<MD
# IdentityForge (fixture)

## Tests

\`\`\`bash
cd backend && python -m pytest -q     # backend offline suite (482 tests, parent-verified)
\`\`\`

The gate runner reports **18 explicit gates** with PASS / FAIL / NOT RUN
/ NOT APPLICABLE: OFFLINE_UNIT, OFFLINE_SCENARIOS,
DOCS_CONTRACT, DOCS_CONTRACT_PATHS, VERSION_CONTRACT, FRONTEND_TYPECHECK, FRONTEND_UNIT, FRONTEND_BUILD,
PYTHON_DEPENDENCY_AUDIT, NPM_FULL_LOCKFILE_AUDIT, GHSA_DIRECT_FALLBACK,
COMPOSE_CONFIG, CLEAN_COMPOSE_BUILD_BOOT, REAL_KEYCLOAK_LOGIN,
REAL_SECURITY_NEGATIVES, REAL_LAB_RESET, PLAYWRIGHT_E2E, RESPONSIVE_QA.

## Known limitations

- **Operation Trustline v5 (2026-11-11)** — backend pytest **340 passed**, 16 gates total. History, not current prose.
MD
  out="$(run_checker "$fixture" readme-current 2>&1)"; rc=$?
  if [ "$rc" -eq 0 ] && echo "$out" | grep -q "0 violation(s)"; then
    ok "current active README counts + old-count history PASS in $fixture"
  else
    not_ok "current active README counts in $fixture" "expected exit 0 + 0 violations, got rc=$rc: $out"
  fi
done

echo
echo "docs-contract-paths: $PASS_COUNT passed, $FAIL_COUNT failed"
if [ "$FAIL_COUNT" -gt 0 ]; then
  printf '  FAILED: %s\n' "${failures[@]}"
  exit 1
fi
echo "docs-contract-paths: PASS"
