#!/usr/bin/env bash
# Regression test for IF-V5-05 (Trustline v8.0.2): the version-contract
# check must PASS when every authoritative version equals the expected
# release version, and FAIL (nonzero) when any ONE source differs —
# for every source — and when a source is missing or unreadable.
#
# Builds minimal fixtures (all sources at the current release version —
# the literal in build_fixture below), runs the real
# scripts/check-version-contract.py with --root pointing at each
# fixture, then mutates one source at a time. Every mutation DERIVES
# the version literal from the fixture it mutates (fixture_version()
# reads __init__.__version__ from the freshly built fixture) and
# ASSERTS the mutation landed (mutate_version(): the old literal
# occurred >= 1 time before, is gone after, and the replacement count
# equals the pre-mutation count) — so a bump that moves the fixture
# version can never again turn a negative into a silent no-op the way
# the stale 1.8.2 seds did in v8.0.3 (8 passed / 5 failed on the
# released archive). Also runs the checker
# against the REAL tree for information only (it is expected to FAIL
# until the backend version source is bumped to 1.8.5 and the
# frontend package files are bumped together via npm; that failure
# is reported, never asserted here — the release gate in
# scripts/test-all.sh is what enforces the real tree).
#
# Stdlib-only python3; no Docker, no venv, no network.
set -uo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
CHECKER="$ROOT/scripts/check-version-contract.py"

PASS_COUNT=0
FAIL_COUNT=0
failures=()

ok() { PASS_COUNT=$((PASS_COUNT + 1)); echo "PASS: $1"; }
not_ok() { FAIL_COUNT=$((FAIL_COUNT + 1)); failures+=("$1 -- $2"); echo "FAIL: $1 -- $2"; }

build_fixture() {
  local dir="$1"
  mkdir -p "$dir/docs" "$dir/backend/src/identityforge/api" \
    "$dir/frontend/src"
  cat > "$dir/docs/RELEASE_MANIFEST.md" <<'MD'
# Release Manifest — IdentityForge

## Operation Trustline v8.0.5 — final two-item security hardening closure (2026-11-14)

- **Version:** 1.8.5 (Operation Trustline v8.0.5)
- **Date:** 2026-11-14 (ISO 8601)
MD
  cat > "$dir/backend/pyproject.toml" <<'TOML'
[project]
name = "identityforge"
version = "1.8.5"
TOML
  printf '%s' '{"name": "identityforge-frontend", "version": "1.8.5"}' \
    > "$dir/frontend/package.json"
  printf '%s' '{"name": "identityforge-frontend", "version": "1.8.5", "packages": {"": {"version": "1.8.5"}}}' \
    > "$dir/frontend/package-lock.json"
  printf '%s\n' '__version__ = "1.8.5"' \
    > "$dir/backend/src/identityforge/__init__.py"
  cat > "$dir/backend/src/identityforge/api/app.py" <<'PY'
from fastapi import FastAPI
app = FastAPI(title="IdentityForge", version="1.8.5", docs_url=None, redoc_url=None)
def health():
    return {"status": "ok", "service": "identityforge-backend", "version": "1.8.5"}
PY
  cat > "$dir/frontend/src/api.ts" <<'TS'
export function getHealth(): Promise<Health> { return req<Health>('/api/v1/health') }
TS
  cat > "$dir/frontend/src/types.ts" <<'TS'
export interface Health {
  status: string
  service?: string
  version?: string
}
TS
}

# fixture_version <fixture-dir>: the version the fixture actually
# carries, read from its own __init__.__version__ (the fixture's
# single backend version source, which every other fixture source
# must equal under the contract). Validated X.Y.Z; fails loudly if
# unreadable, so a caller can never mutate a stale literal.
fixture_version() {
  local ver
  ver="$(sed -n 's/^__version__ = "\([0-9][0-9.]*\)"$/\1/p' \
    "$1/backend/src/identityforge/__init__.py")"
  if ! printf '%s' "$ver" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then
    echo "FIXTURE-VERSION FAILED: no X.Y.Z __version__ in $1/backend/src/identityforge/__init__.py (got '$ver')" >&2
    return 1
  fi
  printf '%s' "$ver"
}

# mutate_version <fixture-dir> <relative-path> <old-literal> <new-literal>:
# literal (never regex — the sed-escaping trap of IF-V8-81) replace of
# ALL occurrences of <old-literal> with <new-literal> in the one file,
# with assertions that prove the mutation actually landed:
#   * <old-literal> occurs >= 1 time before (else the mutation would
#     be a no-op and the negative vacuous — fail loudly here, never
#     let the checker run on an unmutated fixture);
#   * <old-literal> occurs 0 times after;
#   * <new-literal> occurs exactly as many times after as
#     <old-literal> did before (every slot changed, no slot missed —
#     e.g. package-lock.json carries TWO version slots).
# Prints the mutated line(s) as evidence. Returns nonzero on any
# failed assertion, without touching the checker.
mutate_version() {
  local dir="$1" relpath="$2" old="$3" new="$4"
  local path="$dir/$relpath"
  local before after_old after_new
  before="$(grep -o -F "$old" "$path" | wc -l | tr -d ' ' || true)"
  if [ "$before" -lt 1 ]; then
    echo "MUTATION-ASSERT FAILED: '$old' occurs 0 times in $relpath — the mutation would be a no-op (stale literal? fixture carries a different version?)"
    return 1
  fi
  python3 - "$path" "$old" "$new" <<'PY'
import sys
path, old, new = sys.argv[1], sys.argv[2], sys.argv[3]
text = open(path, encoding="utf-8").read()
assert old in text, f"{old!r} not found in {path}"
open(path, "w", encoding="utf-8").write(text.replace(old, new))
PY
  after_old="$(grep -o -F "$old" "$path" | wc -l | tr -d ' ' || true)"
  after_new="$(grep -o -F "$new" "$path" | wc -l | tr -d ' ' || true)"
  if [ "$after_old" -ne 0 ] || [ "$after_new" -ne "$before" ]; then
    echo "MUTATION-ASSERT FAILED: $relpath: old literal left=$after_old (want 0), new literal count=$after_new (want $before)"
    return 1
  fi
  echo "  mutated $relpath: $before occurrence(s) of '$old' -> '$new'"
  grep -n -F "$new" "$path" | sed 's/^/  mutated line: /'
  return 0
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
FIX="$TMP/fixture"
build_fixture "$FIX"
# The version the pristine fixture carries (used in case labels only;
# every mutation re-derives it from its own fresh fixture below).
FIXTURE_VER="$(fixture_version "$FIX")" || {
  not_ok "fixture version derivation" "could not read __version__ from the freshly built fixture"
  FIXTURE_VER=""
}

# Positive: all sources agree -> exit 0.
out="$(python3 "$CHECKER" --root "$FIX" 2>&1)"; rc=$?
if [ "$rc" -eq 0 ] && echo "$out" | grep -q "version-contract: PASS"; then
  ok "all sources agree at $FIXTURE_VER -> PASS"
else
  not_ok "all-agree fixture" "expected exit 0 + PASS, got rc=$rc: $out"
fi

# Derivation: app.py uses __version__ (WS1 v6 single-source design, carried into v7:
# FastAPI version + health version derive from __init__.__version__)
# -> exit 0 when __init__ carries the fixture version.
dir="$TMP/derive"; rm -rf "$dir"; build_fixture "$dir"
derive_ver="$(fixture_version "$dir")" || {
  not_ok "__version__ derivation" "could not derive fixture version"
  derive_ver=""
}
if [ -n "$derive_ver" ]; then
  sed -i "s/version=\"$derive_ver\"/version=__version__/; s/\"version\": \"$derive_ver\"/\"version\": __version__/" \
    "$dir/backend/src/identityforge/api/app.py"
  # Guard against a vacuous positive: the rewrite must have landed in
  # BOTH version slots, or the checker would pass on plain literals
  # and the case would prove nothing about derivation.
  if [ "$(grep -o -F '__version__' "$dir/backend/src/identityforge/api/app.py" | wc -l | tr -d ' ')" -ne 2 ]; then
    not_ok "__version__ derivation" "app.py rewrite did not land in both version slots (fixture version $derive_ver?)"
  else
    out="$(python3 "$CHECKER" --root "$dir" 2>&1)"; rc=$?
    if [ "$rc" -eq 0 ] && echo "$out" | grep -q "version-contract: PASS"; then
      ok "__version__ derivation at $derive_ver -> PASS"
    else
      not_ok "__version__ derivation" "expected exit 0 + PASS, got rc=$rc: $out"
    fi
  fi
  # ... and FAILS when the derived __init__ value differs.
  if mutate_version "$dir" "backend/src/identityforge/__init__.py" "__version__ = \"$derive_ver\"" '__version__ = "1.5.0"'; then
    out="$(python3 "$CHECKER" --root "$dir" 2>&1)"; rc=$?
    if [ "$rc" -ne 0 ]; then
      ok "__version__ derivation at 1.5.0 -> FAILS (rc=$rc)"
    else
      not_ok "__version__ derivation negative" "expected nonzero exit, got rc=0: $out"
    fi
  else
    not_ok "__version__ derivation negative" "mutation assertion failed — the fixture was not actually mutated"
  fi
fi

# Negatives: mutate exactly ONE source to 1.5.0 -> exit NONZERO.
# Each case rebuilds the fixture so only that source differs. The
# mutation literal is DERIVED from the fresh fixture (fixture_version)
# and the mutation is ASSERTED (mutate_version) before the checker
# runs — a stale literal fails the case here with a precise
# MUTATION-ASSERT message instead of silently testing an unmutated
# fixture. %VERSION% in the old/new templates is the derived version.
neg_case() { # neg_case <label> <relative-path> <old-template> <new-template>
  local label="$1" relpath="$2" old_t="$3" new_t="$4"
  local dir="$TMP/neg"
  rm -rf "$dir"; build_fixture "$dir"
  local ver
  ver="$(fixture_version "$dir")" || {
    not_ok "$label negative" "could not derive fixture version — mutation not attempted"
    return
  }
  local old="${old_t//%VERSION%/$ver}" new="${new_t//%VERSION%/$ver}"
  if ! mutate_version "$dir" "$relpath" "$old" "$new"; then
    not_ok "$label negative" "mutation assertion failed — the fixture was not actually mutated (see MUTATION-ASSERT above)"
    return
  fi
  out="$(python3 "$CHECKER" --root "$dir" 2>&1)"; rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "$out" | grep -E 'MISMATCH' | sed 's/^/  checker: /'
    ok "$label differs -> FAILS (rc=$rc)"
  else
    not_ok "$label negative" "expected nonzero exit, got rc=0: $out"
  fi
}
neg_case "manifest version" \
  "docs/RELEASE_MANIFEST.md" "%VERSION%" "1.5.0"
neg_case "pyproject version" \
  "backend/pyproject.toml" "%VERSION%" "1.5.0"
neg_case "package.json version" \
  "frontend/package.json" "%VERSION%" "1.5.0"
neg_case "package-lock.json version" \
  "frontend/package-lock.json" "%VERSION%" "1.5.0"
neg_case "__init__ __version__" \
  "backend/src/identityforge/__init__.py" "%VERSION%" "1.5.0"
neg_case "FastAPI version" \
  "backend/src/identityforge/api/app.py" \
  'FastAPI(title="IdentityForge", version="%VERSION%"' \
  'FastAPI(title="IdentityForge", version="1.5.0"'
neg_case "health version" \
  "backend/src/identityforge/api/app.py" \
  '"version": "%VERSION%"' '"version": "1.5.0"'
# Hard-coded UI literal: appended, not replaced — assert the append
# landed (a missing append would be the same vacuous-negative trap).
dir="$TMP/neg"; rm -rf "$dir"; build_fixture "$dir"
printf '%s\n' 'export const UI_VERSION = "1.5.0";' >> "$dir/frontend/src/api.ts"
if ! grep -qF 'export const UI_VERSION = "1.5.0";' "$dir/frontend/src/api.ts"; then
  not_ok "hard-coded UI version literal negative" "append assertion failed — the literal did not land in frontend/src/api.ts"
else
  out="$(python3 "$CHECKER" --root "$dir" 2>&1)"; rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "$out" | grep -E 'MISMATCH' | sed 's/^/  checker: /'
    ok "hard-coded UI version literal differs -> FAILS (rc=$rc)"
  else
    not_ok "hard-coded UI version literal negative" "expected nonzero exit, got rc=0: $out"
  fi
fi

# Missing source -> exit NONZERO (exit 2).
dir="$TMP/missing"; rm -rf "$dir"; build_fixture "$dir"
rm "$dir/backend/pyproject.toml"
out="$(python3 "$CHECKER" --root "$dir" 2>&1)"; rc=$?
if [ "$rc" -ne 0 ]; then
  ok "missing pyproject -> FAILS (rc=$rc)"
else
  not_ok "missing source" "expected nonzero exit, got rc=0: $out"
fi

# Wrong --expected value -> exit NONZERO (bad usage, not a pass).
out="$(python3 "$CHECKER" --root "$FIX" --expected banana 2>&1)"; rc=$?
if [ "$rc" -ne 0 ]; then
  ok "malformed --expected -> FAILS (rc=$rc)"
else
  not_ok "malformed --expected" "expected nonzero exit, got rc=0: $out"
fi

echo
echo "version-contract test: $PASS_COUNT passed, $FAIL_COUNT failed"
if [ "$FAIL_COUNT" -gt 0 ]; then
  printf '  FAILED: %s\n' "${failures[@]}"
  exit 1
fi
echo "version-contract test: PASS (13 checks: all-agree, __version__ derivation + negative, 8 one-source negatives, missing source, malformed --expected)"
echo
echo "--- informational only: checker against the REAL tree ---"
echo "(expected to FAIL until every authoritative source agrees at"
echo " 1.8.5 — backend is a single __version__ source since WS1's"
echo " v6 change, carried into v7/v7.1/v7.2; the usual remaining gap is the frontend"
echo " package-lock.json, which must be bumped together with"
echo " package.json via npm; this run does not affect the verdict above)"
python3 "$CHECKER" --root "$ROOT" || true
