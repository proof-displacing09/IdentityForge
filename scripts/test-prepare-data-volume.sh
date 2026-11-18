#!/usr/bin/env bash
# Stub tests for backend/docker/prepare-data-volume.py (IF-V8-42, v8.0.5).
#
# Docker is absent here, so the REAL proof (image build, Compose boot,
# `id` in the running prep/backend containers, live volume migration)
# is NOT RUN and stays a reviewer gate. What this suite DOES prove,
# with stubbed filesystems on /tmp (the only filesystem in this
# sandbox where chown to the app UID works — the workspace mount
# refuses chown to any non-zero UID; fixtures here are a few KB, so
# the 512 MB tmpfs is ample):
#
#   1 fresh-volume            no data dir -> created, owned 10001:10001,
#                             mode 0750, app user can write in it
#   2 existing-root-owned-DB  real SQLite DB with rows, root-owned
#                             0600 + stale -journal -> repaired to
#                             10001:10001/0640, rows + integrity kept,
#                             app user (setpriv 10001) can write
#   3 idempotency             second run on a correct volume: rc 0,
#                             "0 entries repaired", nothing changes
#   4 unwritable-volume       run as the app user against a root-owned
#                             volume -> non-zero, precise message, the
#                             DB is byte/mode-identical afterwards
#                             (no partial repair, no root fallback)
#   5 data-is-a-file          /app/data is a file -> non-zero, named
#   6 corrupt-DB              DB is garbage -> non-zero, integrity
#                             named, file bytes unchanged
#   7 symlinked-data-dir      data dir is a symlink -> non-zero
#   8 symlinked-DB-file       DB is a symlink -> non-zero, target
#                             untouched
#   9 scope-guard             --data-dir outside --base-dir, and
#                             --data-dir == --base-dir -> non-zero
#  10 wal-sidecar              -wal present -> rc 0, integrity probe
#                             explicitly skipped (read-only open
#                             cannot replay a hot WAL)
#  11 never-starts-app         the script contains no subprocess /
#                             exec / spawn / system call and never
#                             mentions uvicorn; a canary outside every
#                             data dir is untouched after all cases
#  12 non-root-noop            already-correct volume, run as the app
#                             user -> rc 0 (no-op needs no root)
#  13 top-level-only           a subdirectory is repaired itself but
#                             its CONTENTS are not recursed into
#
# Every failure case must FAIL CLEARLY (non-zero exit + a precise
# message naming the path/reason) and must NEVER silently fall back
# to a root app runtime — the script has no such path at all (case
# 11 greps for it), and failed runs leave the fixture untouched.
#
# Requirements: run as root (or a user-namespace root that can chown
# to UID 10001), `setpriv` on PATH, python3 with sqlite3. Otherwise
# the suite exits 2 ENVIRONMENT NOT READY — a missing prerequisite,
# never a prep-script defect. Usage: bash scripts/test-prepare-data-volume.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PREP="$ROOT/backend/docker/prepare-data-volume.py"
APP_UID=10001
APP_GID=10001
PASS=0
FAIL=0
FAILED_CASES=""

if [ "$(id -u)" -ne 0 ]; then
  echo "ENVIRONMENT NOT READY: this suite must run as root (it creates root-owned fixtures and chowns them to UID $APP_UID); current uid is $(id -u)."
  exit 2
fi
command -v setpriv >/dev/null 2>&1 || { echo "ENVIRONMENT NOT READY: setpriv not on PATH."; exit 2; }
command -v python3 >/dev/null 2>&1 || { echo "ENVIRONMENT NOT READY: python3 not on PATH."; exit 2; }
python3 -c "import sqlite3" 2>/dev/null || { echo "ENVIRONMENT NOT READY: python3 sqlite3 module missing."; exit 2; }

SCRATCH="$(mktemp -d /tmp/ws1-prep-test.XXXXXX)"
chmod 0755 "$SCRATCH"
cleanup() { rm -rf "$SCRATCH"; }
trap cleanup EXIT

# The tmpfs must allow chown to the app UID, or every case would fail
# for an environment reason. Probe once, up front.
touch "$SCRATCH/.chown-probe"
if ! chown "$APP_UID:$APP_GID" "$SCRATCH/.chown-probe" 2>/dev/null; then
  echo "ENVIRONMENT NOT READY: cannot chown to $APP_UID:$APP_GID on $SCRATCH (this filesystem refuses it); run this suite where chown to the app UID works."
  exit 2
fi
rm -f "$SCRATCH/.chown-probe"

ok()   { PASS=$((PASS + 1)); echo "PASS [$1] $2"; }
bad()  { FAIL=$((FAIL + 1)); FAILED_CASES="$FAILED_CASES $1"; echo "FAIL [$1] $2"; }
expect() { # expect <case> <desc> <actual> <wanted>
  if [ "$3" = "$4" ]; then ok "$1" "$2"; else bad "$1" "$2 (got '$3', wanted '$4')"; fi
}

# make_db <path> — a real SQLite DB with a runs table and 3 rows.
make_db() {
  python3 - "$1" <<'EOF'
import sqlite3, sys
p = sys.argv[1]
c = sqlite3.connect(p)
c.execute("CREATE TABLE runs (run_id TEXT PRIMARY KEY, n INT)")
for i in (1, 2, 3):
    c.execute("INSERT INTO runs VALUES (?, ?)", (f"run-{i}", i * 10))
c.commit()
print("rows:", c.execute("SELECT COUNT(*) FROM runs").fetchone()[0])
c.close()
EOF
}
db_rows() { python3 -c "import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute('SELECT run_id, n FROM runs ORDER BY run_id').fetchall())" "$1"; }
stat_fmt() { stat -c '%u:%g %a' "$1"; }

# Canary outside every data dir: nothing may touch it (case 11).
mkdir -p "$SCRATCH/canary"
echo "canary-content" > "$SCRATCH/canary/file.txt"
CANARY_SUM="$(sha256sum "$SCRATCH/canary/file.txt" | cut -d' ' -f1)"

# --- 1. fresh volume ---------------------------------------------------------
C="$SCRATCH/case1"; mkdir -p "$C"; chmod 0755 "$C"
OUT="$(python3 "$PREP" --base-dir "$C" --data-dir "$C/data" --uid "$APP_UID" --gid "$APP_GID" 2>&1)"; RC=$?
expect 1 "fresh volume exits 0" "$RC" "0"
expect 1 "fresh data dir owned $APP_UID:$APP_GID mode 750" "$(stat_fmt "$C/data")" "$APP_UID:$APP_GID 750"
setpriv --reuid="$APP_UID" --regid="$APP_GID" --clear-groups \
  python3 -c "import os; open('$C/data/.w','w').write('x'); os.unlink('$C/data/.w'); print('app-user write ok')" >/dev/null 2>&1 \
  && ok 1 "app user (setpriv $APP_UID) can create a file in the fresh volume" \
  || bad 1 "app user cannot write in the fresh volume"

# --- 2. existing root-owned DB ----------------------------------------------
C="$SCRATCH/case2"; mkdir -p "$C/data"; chmod 0755 "$C" "$C/data"
make_db "$C/data/identityforge.db" >/dev/null
touch "$C/data/identityforge.db-journal"
chmod 0700 "$C/data"; chmod 0600 "$C/data/identityforge.db" "$C/data/identityforge.db-journal"
BEFORE_ROWS="$(db_rows "$C/data/identityforge.db")"
OUT="$(python3 "$PREP" --base-dir "$C" --data-dir "$C/data" --uid "$APP_UID" --gid "$APP_GID" 2>&1)"; RC=$?
expect 2 "existing root-owned DB exits 0" "$RC" "0"
expect 2 "DB owned $APP_UID:$APP_GID mode 640" "$(stat_fmt "$C/data/identityforge.db")" "$APP_UID:$APP_GID 640"
expect 2 "stale -journal repaired to $APP_UID:$APP_GID mode 640" "$(stat_fmt "$C/data/identityforge.db-journal")" "$APP_UID:$APP_GID 640"
expect 2 "data dir owned $APP_UID:$APP_GID mode 750" "$(stat_fmt "$C/data")" "$APP_UID:$APP_GID 750"
expect 2 "rows preserved across repair" "$(db_rows "$C/data/identityforge.db")" "$BEFORE_ROWS"
case "$OUT" in *"db integrity: ok"*) ok 2 "read-only integrity probe reported ok";; *) bad 2 "integrity probe did not report ok (out: $OUT)";; esac
case "$OUT" in *"skipping privilege-dropped"*) bad 2 "drop probe was skipped (it must run as root here)";; *) ok 2 "privilege-dropped writability probe ran (not skipped)";; esac
setpriv --reuid="$APP_UID" --regid="$APP_GID" --clear-groups \
  python3 -c "
import sqlite3, os
p = '$C/data/identityforge.db'
open(p, 'r+b').close()
open('$C/data/.w', 'w').write('x'); os.unlink('$C/data/.w')
c = sqlite3.connect(p)
c.execute('CREATE TABLE probe_t (x INT)'); c.execute('INSERT INTO probe_t VALUES (1)'); c.commit()
c.execute('DROP TABLE probe_t'); c.commit(); c.close()
print('app-user sqlite write ok')" >/dev/null 2>&1 \
  && ok 2 "app user can write the repaired DB (real SQLite write + drop)" \
  || bad 2 "app user cannot write the repaired DB"
expect 2 "rows still intact after the app-user write" "$(db_rows "$C/data/identityforge.db")" "$BEFORE_ROWS"

# --- 3. idempotency ----------------------------------------------------------
OUT="$(python3 "$PREP" --base-dir "$C" --data-dir "$C/data" --uid "$APP_UID" --gid "$APP_GID" 2>&1)"; RC=$?
expect 3 "second run on a correct volume exits 0" "$RC" "0"
case "$OUT" in *"0 entries repaired"*) ok 3 "second run is a no-op (0 entries repaired)";; *) bad 3 "second run was not a no-op (out: $OUT)";; esac
expect 3 "DB ownership/mode unchanged by the second run" "$(stat_fmt "$C/data/identityforge.db")" "$APP_UID:$APP_GID 640"

# --- 4. unwritable volume (run as the app user) ------------------------------
# NOTE: like case 12, this runs a world-readable COPY of the script:
# the shipped file is mode 660, so a non-root user could not even
# open it — and this case must exercise the script's own chown
# failure, not the file-permission failure.
D="$SCRATCH/case4"; mkdir -p "$D/data"; chmod 0755 "$D" "$D/data"
make_db "$D/data/identityforge.db" >/dev/null
chmod 0700 "$D/data"; chmod 0600 "$D/data/identityforge.db"
cp "$PREP" "$D/prep-copy.py"; chmod 0644 "$D/prep-copy.py"
BEFORE_STAT="$(stat_fmt "$D/data/identityforge.db")"
BEFORE_SUM="$(sha256sum "$D/data/identityforge.db" | cut -d' ' -f1)"
OUT="$(setpriv --reuid="$APP_UID" --regid="$APP_GID" --clear-groups \
  python3 "$D/prep-copy.py" --base-dir "$D" --data-dir "$D/data" --uid "$APP_UID" --gid "$APP_GID" 2>&1)"; RC=$?
if [ "$RC" -ne 0 ]; then ok 4 "non-root run against a root-owned volume exits non-zero (rc=$RC)"; else bad 4 "non-root run against a root-owned volume exited 0 (must fail closed)"; fi
case "$OUT" in *"cannot chown"*|*"Permission denied"*|*"Operation not permitted"*) ok 4 "failure names the permission problem";; *) bad 4 "failure does not name the permission problem (out: $OUT)";; esac
expect 4 "failed run leaves the DB ownership/mode untouched" "$(stat_fmt "$D/data/identityforge.db")" "$BEFORE_STAT"
expect 4 "failed run leaves the DB bytes untouched" "$(sha256sum "$D/data/identityforge.db" | cut -d' ' -f1)" "$BEFORE_SUM"

# --- 5. data path is a file ---------------------------------------------------
D="$SCRATCH/case5"; mkdir -p "$D"; chmod 0755 "$D"
echo "not a directory" > "$D/data"
BEFORE_SUM="$(sha256sum "$D/data" | cut -d' ' -f1)"
OUT="$(python3 "$PREP" --base-dir "$D" --data-dir "$D/data" --uid "$APP_UID" --gid "$APP_GID" 2>&1)"; RC=$?
if [ "$RC" -ne 0 ]; then ok 5 "data-is-a-file exits non-zero (rc=$RC)"; else bad 5 "data-is-a-file exited 0"; fi
case "$OUT" in *"not a directory"*) ok 5 "failure names the malformed path";; *) bad 5 "failure does not name the problem (out: $OUT)";; esac
expect 5 "malformed file untouched" "$(sha256sum "$D/data" | cut -d' ' -f1)" "$BEFORE_SUM"

# --- 6. corrupt DB ------------------------------------------------------------
D="$SCRATCH/case6"; mkdir -p "$D/data"; chmod 0755 "$D" "$D/data"
head -c 2048 /dev/urandom > "$D/data/identityforge.db"
chmod 0600 "$D/data/identityforge.db"
BEFORE_SUM="$(sha256sum "$D/data/identityforge.db" | cut -d' ' -f1)"
OUT="$(python3 "$PREP" --base-dir "$D" --data-dir "$D/data" --uid "$APP_UID" --gid "$APP_GID" 2>&1)"; RC=$?
if [ "$RC" -ne 0 ]; then ok 6 "corrupt DB exits non-zero (rc=$RC)"; else bad 6 "corrupt DB exited 0 (must fail closed)"; fi
case "$OUT" in *"integrity_check"*|*"cannot be opened"*) ok 6 "failure names the integrity problem";; *) bad 6 "failure does not name the integrity problem (out: $OUT)";; esac
expect 6 "corrupt DB bytes untouched" "$(sha256sum "$D/data/identityforge.db" | cut -d' ' -f1)" "$BEFORE_SUM"

# --- 7. symlinked data dir -----------------------------------------------------
D="$SCRATCH/case7"; mkdir -p "$D/real" "$D"; chmod 0755 "$D" "$D/real"
make_db "$D/real/identityforge.db" >/dev/null
ln -s "$D/real" "$D/data"
BEFORE_SUM="$(sha256sum "$D/real/identityforge.db" | cut -d' ' -f1)"
OUT="$(python3 "$PREP" --base-dir "$D" --data-dir "$D/data" --uid "$APP_UID" --gid "$APP_GID" 2>&1)"; RC=$?
if [ "$RC" -ne 0 ]; then ok 7 "symlinked data dir exits non-zero (rc=$RC)"; else bad 7 "symlinked data dir exited 0"; fi
case "$OUT" in *"symlink"*) ok 7 "failure names the symlink";; *) bad 7 "failure does not name the symlink (out: $OUT)";; esac
expect 7 "symlink target untouched" "$(sha256sum "$D/real/identityforge.db" | cut -d' ' -f1)" "$BEFORE_SUM"

# --- 8. symlinked DB file -------------------------------------------------------
D="$SCRATCH/case8"; mkdir -p "$D/data" "$D/outside"; chmod 0755 "$D" "$D/data" "$D/outside"
make_db "$D/outside/target.db" >/dev/null
ln -s "$D/outside/target.db" "$D/data/identityforge.db"
BEFORE_SUM="$(sha256sum "$D/outside/target.db" | cut -d' ' -f1)"
OUT="$(python3 "$PREP" --base-dir "$D" --data-dir "$D/data" --uid "$APP_UID" --gid "$APP_GID" 2>&1)"; RC=$?
if [ "$RC" -ne 0 ]; then ok 8 "symlinked DB file exits non-zero (rc=$RC)"; else bad 8 "symlinked DB file exited 0"; fi
case "$OUT" in *"symlink"*) ok 8 "failure names the symlink";; *) bad 8 "failure does not name the symlink (out: $OUT)";; esac
expect 8 "symlink target untouched" "$(sha256sum "$D/outside/target.db" | cut -d' ' -f1)" "$BEFORE_SUM"

# --- 9. scope guard --------------------------------------------------------------
D="$SCRATCH/case9"; mkdir -p "$D"; chmod 0755 "$D"
OUT="$(python3 "$PREP" --base-dir "$D" --data-dir /etc --uid "$APP_UID" --gid "$APP_UID" 2>&1)"; RC=$?
if [ "$RC" -ne 0 ]; then ok 9 "data-dir outside base-dir exits non-zero (rc=$RC)"; else bad 9 "data-dir outside base-dir exited 0"; fi
OUT="$(python3 "$PREP" --base-dir "$D" --data-dir "$D" --uid "$APP_UID" --gid "$APP_UID" 2>&1)"; RC=$?
if [ "$RC" -ne 0 ]; then ok 9 "data-dir == base-dir exits non-zero (rc=$RC)"; else bad 9 "data-dir == base-dir exited 0"; fi

# --- 10. WAL sidecar: integrity probe skipped, run still succeeds ----------------
D="$SCRATCH/case10"; mkdir -p "$D/data"; chmod 0755 "$D" "$D/data"
make_db "$D/data/identityforge.db" >/dev/null
touch "$D/data/identityforge.db-wal" "$D/data/identityforge.db-shm"
chmod 0600 "$D/data/identityforge.db" "$D/data/identityforge.db-wal" "$D/data/identityforge.db-shm"
BEFORE_ROWS="$(db_rows "$D/data/identityforge.db")"
OUT="$(python3 "$PREP" --base-dir "$D" --data-dir "$D/data" --uid "$APP_UID" --gid "$APP_GID" 2>&1)"; RC=$?
expect 10 "WAL-sidecar volume exits 0" "$RC" "0"
case "$OUT" in *"skipping read-only integrity probe"*) ok 10 "integrity probe explicitly skipped with a WAL sidecar";; *) bad 10 "no skip note for the WAL sidecar (out: $OUT)";; esac
expect 10 "rows preserved with WAL sidecar" "$(db_rows "$D/data/identityforge.db")" "$BEFORE_ROWS"

# --- 11. never starts the app; canary untouched -----------------------------------
if grep -Eq "subprocess|os\.exec|os\.system|os\.spawn|os\.posix_spawn|uvicorn" "$PREP"; then
  bad 11 "prep script contains a subprocess/exec/spawn call or an app-server reference"
else
  ok 11 "prep script contains no subprocess/exec/spawn call and never starts the app server"
fi
expect 11 "canary outside every data dir untouched" "$(sha256sum "$SCRATCH/canary/file.txt" | cut -d' ' -f1)" "$CANARY_SUM"

# --- 12. non-root no-op on an already-correct volume -------------------------------
# NOTE: the shipped script is mode 660 (root-only read, like the
# other repo .py files), so a non-root user cannot even open it —
# which is fine, because the prep service ALWAYS runs it as root.
# This case therefore runs a world-readable COPY to exercise the
# no-op code path itself (nothing needs repair -> rc 0 without root).
D="$SCRATCH/case12"; mkdir -p "$D/data"; chmod 0755 "$D"
make_db "$D/data/identityforge.db" >/dev/null
chown "$APP_UID:$APP_GID" "$D/data" "$D/data/identityforge.db"
chmod 0750 "$D/data"; chmod 0640 "$D/data/identityforge.db"
cp "$PREP" "$D/prep-copy.py"; chmod 0644 "$D/prep-copy.py"
OUT="$(setpriv --reuid="$APP_UID" --regid="$APP_GID" --clear-groups \
  python3 "$D/prep-copy.py" --base-dir "$D" --data-dir "$D/data" --uid "$APP_UID" --gid "$APP_GID" 2>&1)"; RC=$?
expect 12 "non-root run on an already-correct volume exits 0 (no-op)" "$RC" "0"

# --- 13. top-level only: a subdirectory is repaired, its contents are not -----------
D="$SCRATCH/case13"; mkdir -p "$D/data/sub"; chmod 0755 "$D" "$D/data"
make_db "$D/data/identityforge.db" >/dev/null
echo "inner" > "$D/data/sub/inner.txt"
chmod 0700 "$D/data/sub"; chmod 0600 "$D/data/sub/inner.txt" "$D/data/identityforge.db"
OUT="$(python3 "$PREP" --base-dir "$D" --data-dir "$D/data" --uid "$APP_UID" --gid "$APP_GID" 2>&1)"; RC=$?
expect 13 "volume with a subdirectory exits 0" "$RC" "0"
expect 13 "subdirectory itself repaired to $APP_UID:$APP_GID 750" "$(stat_fmt "$D/data/sub")" "$APP_UID:$APP_GID 750"
expect 13 "contents inside the subdirectory are NOT recursed into (still root-owned)" "$(stat_fmt "$D/data/sub/inner.txt")" "0:0 600"

echo
echo "prepare-data-volume stub tests: $PASS passed, $FAIL failed"
[ -n "$FAILED_CASES" ] && echo "failing cases:$FAILED_CASES"
[ "$FAIL" -eq 0 ]
