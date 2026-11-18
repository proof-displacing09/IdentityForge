#!/usr/bin/env bash
# Regression / checker for IF-V8-43 (Trustline v8.0.5): every external
# GitHub Action referenced by a workflow in .github/workflows/ must be
# pinned to a FULL 40-character lowercase hex commit SHA, with a
# human-readable `# vX.Y.Z` comment naming the exact release tag the
# SHA was resolved from upstream.
#
#   uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262  # v4.4.0
#
# The expected (action -> SHA + tag) mapping is the single source of
# truth in this file and is mirrored in docs/ACTION_SHA_PINS.md, which
# records the upstream evidence (API ref / tags-list / commit / release)
# for every SHA. The two must agree: this checker FAILS if a `uses:`
# line names an action that is not in the mapping (fail-closed on any
# NEW action, pinned or not), if the SHA differs from the mapped SHA,
# or if the version comment is missing or names a different tag.
#
# A mutable reference (`@v4`, `@v4.4.0`), a short/truncated SHA, a
# wrong SHA, a missing/wrong version comment, or an unmapped action
# all FAIL the checker. A built-in negative control (last check) builds
# a fixture workflow carrying exactly those defects and requires the
# checker to reject it — so a checker that silently passes everything
# cannot read as green.
#
# Offline, stdlib-only bash + grep/sed; no Docker, no network, no
# live Keycloak. Safe to run in the CI scripts lane.
# Usage: bash scripts/test-action-pins.sh [workflow-file ...]
#   With no argument, checks every .github/workflows/*.yml|*.yaml.
set -uo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

PASS_COUNT=0
FAIL_COUNT=0
failures=()

ok() { PASS_COUNT=$((PASS_COUNT + 1)); echo "PASS: $1"; }
not_ok() { FAIL_COUNT=$((FAIL_COUNT + 1)); failures+=("$1 -- $2"); echo "FAIL: $1 -- $2"; }

# --- Expected pins: action -> "<full 40-hex SHA> <release tag>" --------
# Verified upstream 2026-11-14 (see docs/ACTION_SHA_PINS.md):
#   * GET api.github.com/repos/actions/<repo>/tags?per_page=100
#   * GET api.github.com/repos/actions/<repo>/git/ref/tags/<tag>
#     (type: commit — lightweight tag, object IS the commit)
#   * GET api.github.com/repos/actions/<repo>/commits/<sha>
#   * GET api.github.com/repos/actions/<repo>/releases/tags/<tag>
#   All four surfaces agree for every action below. `git ls-remote`
#   was NOT usable in this sandbox (timed out at 240 s twice on the
#   git protocol while the HTTPS API answered in <1 s); the checkout
#   SHA additionally matches the coordinator's independent
#   `git ls-remote ... refs/tags/v4` probe (11d5960a...).
declare -A EXPECTED_SHA=(
  [actions/checkout]="11d5960a326750d5838078e36cf38b85af677262"
  [actions/setup-python]="a26af69be951a213d495a4c3e4e4022e16d87065"
  [actions/setup-node]="49933ea5288caeca8642d1e84afbd3f7d6820020"
  [actions/upload-artifact]="ea165f8d65b6e75b540449e92b4886f43607fa02"
)
declare -A EXPECTED_TAG=(
  [actions/checkout]="v4.4.0"
  [actions/setup-python]="v5.6.0"
  [actions/setup-node]="v4.4.0"
  [actions/upload-artifact]="v4.6.2"
)

# check_file <path>: validate every `uses:` line in one workflow file.
# Prints per-line PASS/FAIL and returns nonzero if any line is bad.
# Sets CHECK_FILE_BAD=1 on failure (for the negative control).
check_file() {
  local file="$1" bad=0
  local lineno=0 line action ref sha comment tag
  while IFS= read -r line || [ -n "$line" ]; do
    lineno=$((lineno + 1))
    # Only lines that actually reference an action: a YAML `uses:`
    # key at line start (possibly indented). A comment that merely
    # MENTIONS "uses:" (e.g. this checker's own documentation in a
    # workflow header) must not be treated as a reference.
    if ! printf '%s' "$line" | grep -Eq '^[[:space:]]*(-[[:space:]]+)?uses:[[:space:]]'; then
      continue
    fi
    # Local actions (./...) and docker:// actions are not external
    # GitHub Actions; none exist in this repo, but allow them
    # explicitly rather than misclassifying them.
    if printf '%s' "$line" | grep -Eq 'uses:[[:space:]]*(\./|docker://)'; then
      echo "PASS: $file:$lineno local/docker action (not an external GitHub Action): $line"
      continue
    fi
    # Extract `owner/repo@ref` and the trailing comment, if any.
    action="$(printf '%s' "$line" | sed -E 's/^[[:space:]]*(-[[:space:]]+)?uses:[[:space:]]*([^@#[:space:]]+).*/\2/')"
    ref="$(printf '%s' "$line" | sed -E 's/^[[:space:]]*(-[[:space:]]+)?uses:[[:space:]]*[^@#[:space:]]+@([^#[:space:]]+).*/\2/')"
    comment="$(printf '%s' "$line" | sed -nE 's/^[^#]*#([[:space:]]*v[0-9]+\.[0-9]+\.[0-9]+).*/\1/p')"
    tag="$(printf '%s' "$comment" | tr -d '[:space:]')"
    # 1. Full 40-hex SHA?
    if ! printf '%s' "$ref" | grep -Eq '^[0-9a-f]{40}$'; then
      echo "FAIL: $file:$lineno action '$action' is NOT pinned to a full 40-hex SHA (ref: '$ref')"
      bad=1
      continue
    fi
    sha="$ref"
    # 2. Known action with the exact mapped SHA and tag?
    if [ -z "${EXPECTED_SHA[$action]:-}" ]; then
      echo "FAIL: $file:$lineno action '$action' is not in the verified pin mapping (fail-closed on unmapped actions)"
      bad=1
      continue
    fi
    if [ "$sha" != "${EXPECTED_SHA[$action]}" ]; then
      echo "FAIL: $file:$lineno $action SHA $sha != verified ${EXPECTED_SHA[$action]} (${EXPECTED_TAG[$action]})"
      bad=1
      continue
    fi
    # 3. Version annotation comment present and naming the mapped tag?
    if [ -z "$tag" ]; then
      echo "FAIL: $file:$lineno $action@$sha has no '# vX.Y.Z' version comment"
      bad=1
      continue
    fi
    if [ "$tag" != "${EXPECTED_TAG[$action]}" ]; then
      echo "FAIL: $file:$lineno $action comment '# $tag' != verified tag '${EXPECTED_TAG[$action]}'"
      bad=1
      continue
    fi
    echo "PASS: $file:$lineno $action@$sha  # $tag"
  done < "$file"
  return "$bad"
}

# --- Resolve the workflow files to check --------------------------------
FILES=()
if [ "$#" -gt 0 ]; then
  FILES=("$@")
else
  for f in .github/workflows/*.yml .github/workflows/*.yaml; do
    [ -e "$f" ] && FILES+=("$f")
  done
fi
if [ "${#FILES[@]}" -eq 0 ]; then
  not_ok "workflow-files-found" "no workflow file under .github/workflows/"
else
  ok "workflow-files-found (${#FILES[@]}: ${FILES[*]})"
fi

# --- Check 1: every uses: line in every workflow file -------------------
for f in "${FILES[@]}"; do
  if [ ! -f "$f" ]; then
    not_ok "workflow-file-exists" "$f does not exist"
    continue
  fi
  if check_file "$f"; then
    ok "all-uses-pinned-in-$f"
  else
    not_ok "all-uses-pinned-in-$f" "see FAIL lines above for $f"
  fi
done

# --- Check 2: every mapped action is actually used at least once --------
# (guards against a pin silently disappearing with its step)
for action in "${!EXPECTED_SHA[@]}"; do
  found=0
  for f in "${FILES[@]}"; do
    [ -f "$f" ] || continue
    if grep -Eq "^[[:space:]]*(-[[:space:]]+)?uses:[[:space:]]*${action}@${EXPECTED_SHA[$action]}[[:space:]]+# ${EXPECTED_TAG[$action]}" "$f"; then
      found=1
    fi
  done
  if [ "$found" -eq 1 ]; then
    ok "mapped-action-used: $action@${EXPECTED_TAG[$action]}"
  else
    not_ok "mapped-action-used" "$action (expected ${EXPECTED_TAG[$action]} / ${EXPECTED_SHA[$action]}) is not used with its verified pin in any checked workflow"
  fi
done

# --- Check 3: mapping doc agrees with this checker ----------------------
# docs/ACTION_SHA_PINS.md must name every mapped SHA + tag; a doc that
# drifts from the checker is itself a defect (the reviewer reads the doc).
DOC="docs/ACTION_SHA_PINS.md"
if [ ! -f "$DOC" ]; then
  not_ok "mapping-doc-exists" "$DOC is missing"
else
  doc_bad=0
  for action in "${!EXPECTED_SHA[@]}"; do
    if grep -Fq "${EXPECTED_SHA[$action]}" "$DOC" && grep -Fq "${EXPECTED_TAG[$action]}" "$DOC"; then
      :
    else
      echo "FAIL: $DOC does not record $action ${EXPECTED_TAG[$action]} ${EXPECTED_SHA[$action]}"
      doc_bad=1
    fi
  done
  if [ "$doc_bad" -eq 0 ]; then
    ok "mapping-doc-agrees ($DOC records all ${#EXPECTED_SHA[@]} SHA+tag pairs)"
  else
    not_ok "mapping-doc-agrees" "$DOC is missing one or more SHA/tag pairs"
  fi
fi

# --- Check 4 (negative control): a mutable fixture MUST fail -----------
FIXTURE_DIR="$(mktemp -d)"
trap 'rm -rf "$FIXTURE_DIR"' EXIT
cat > "$FIXTURE_DIR/fixture.yml" <<'YAML'
name: fixture (negative control — must fail)
on: [push]
jobs:
  test:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4.4.0
      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d8706
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262
      - uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02  # v4.6.1
      - uses: actions/unknown-action@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa  # v1.0.0
YAML
# The fixture carries six distinct defects: a major tag, a full
# semver tag, a truncated (39-hex) SHA, a correct SHA with NO version
# comment, a correct SHA with the WRONG version comment, and an
# unmapped action with a well-formed SHA. The checker must reject it.
if check_file "$FIXTURE_DIR/fixture.yml" > "$FIXTURE_DIR/out.log" 2>&1; then
  not_ok "negative-control-mutable-fixture-rejected" "checker PASSED a fixture with mutable/short/uncommented/wrong/unmapped refs (see below)"; cat "$FIXTURE_DIR/out.log"
else
  nfail="$(grep -c '^FAIL:' "$FIXTURE_DIR/out.log")"
  if [ "$nfail" -eq 6 ]; then
    ok "negative-control-mutable-fixture-rejected (all 6 defective lines rejected)"
  else
    not_ok "negative-control-mutable-fixture-rejected" "checker rejected the fixture but only $nfail/6 defective lines (expected 6)"; cat "$FIXTURE_DIR/out.log"
  fi
fi

# --- Summary --------------------------------------------------------------
echo "---"
echo "test-action-pins: $PASS_COUNT passed, $FAIL_COUNT failed"
if [ "$FAIL_COUNT" -ne 0 ]; then
  printf 'FAILURES:\n'
  printf '  - %s\n' "${failures[@]}"
  exit 1
fi
exit 0
