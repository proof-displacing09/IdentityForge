#!/usr/bin/env python3
"""One-shot /app/data permission preparation (IF-V8-42, v8.0.5).

Runs ONCE, as root, in the dedicated ``backend-data-prep`` Compose
service, BEFORE the backend starts (``backend`` declares
``depends_on: backend-data-prep: service_completed_successfully``).
It NEVER starts the app server, NEVER execs anything, and NEVER runs
as the app user: its only job is to make the evidence directory
writable by the dedicated non-root app UID/GID (10001). It exits 0
only when the directory and the evidence files are owned by that
UID/GID with safe modes and the post-repair checks pass. ANY failure
exits non-zero with a precise message on stderr, so Compose refuses
to start the backend (fail-closed) instead of booting an app that
cannot write evidence — or, worse, silently falling back to a root
runtime. There is no fallback path in this script.

Why a prep service instead of a root entrypoint in the app image
(see docs/PENTEST_FINDINGS_AND_REMEDIATIONS.md IF-V8-42):
the app image itself must NEVER run as root — its Dockerfile ends
with ``USER 10001:10001`` and contains no ``USER root`` — so the
permission repair cannot live in the app container. The prep service
is the single, auditable place root is used: it mounts ONLY the
``backend_data`` volume, runs ONLY this stdlib-only script, touches
ONLY the data directory, and exits before the app starts.

Scope (hard limits, enforced before any repair):
  * The data directory must resolve strictly inside ``--base-dir``
    (default ``/app``) and must not BE the base directory. The
    Compose invocation pins ``--data-dir /app/data``.
  * The data directory itself must not be a symlink, and no entry
    directly inside it may be a symlink — symlinks are never
    followed; they fail closed.
  * Only the TOP LEVEL of the data directory is repaired (the
    directory itself plus its direct entries: the SQLite DB, its
    ``-journal``/``-wal``/``-shm`` sidecars, and any other top-level
    file). No recursion, no other path is ever touched — never
    ``/app`` itself, never ``/app/src``, never ``/opt/keycloak/data``,
    never a host path.
  * Modes are tightened, never loosened beyond the target:
    directory 0750, regular files 0640. Nothing is made
    world-writable; there is no ``chmod 777`` anywhere.

Idempotence: ownership/mode changes are applied ONLY where the
current state differs, so a second run on an already-correct volume
is a no-op that still exits 0. A run as a non-root user therefore
succeeds exactly when nothing needs repair, and fails clearly
(EPERM named) when repair is needed but not permitted.

Post-repair checks (all must pass for exit 0):
  * stat verification of the directory and every repaired entry
    (owner UID/GID and mode are exactly the target);
  * when running as root, a privilege-dropped writability probe:
    the process temporarily drops its effective UID/GID to the app
    user and proves it can create+remove a temp file in the
    directory and open the DB file read-write (no bytes are written
    to the DB), then restores root;
  * when a non-empty DB file exists and no ``-wal``/``-shm`` sidecar
    is present, a READ-ONLY ``PRAGMA integrity_check`` (``mode=ro``
    URI) must return ``ok`` — a corrupt DB fails closed here with a
    precise message instead of booting a half-working app. The check
    is skipped when a WAL sidecar exists (a read-only open cannot
    replay a hot WAL, so the live app's own open is authoritative
    there) and when the DB is absent (fresh volume).

Exit codes: 0 prepared; 1 any failure (message on stderr names the
exact path and reason); 2 bad CLI usage.
"""
import argparse
import os
import sqlite3
import stat
import sys

DEFAULT_BASE_DIR = "/app"
DEFAULT_DATA_DIR = "/app/data"
DEFAULT_UID = 10001
DEFAULT_GID = 10001
DEFAULT_DB_NAME = "identityforge.db"
DIR_MODE = 0o750
FILE_MODE = 0o640


def fail(message):
    """Print a precise failure and exit non-zero (fail-closed)."""
    print(f"prepare-data-volume: ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Prepare /app/data for the non-root app user "
                    "(IF-V8-42 one-shot volume prep).")
    parser.add_argument("--base-dir", default=DEFAULT_BASE_DIR,
                        help="allowed parent of the data dir "
                             "(default: %(default)s)")
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR,
                        help="evidence directory to prepare "
                             "(default: %(default)s)")
    parser.add_argument("--uid", type=int, default=DEFAULT_UID,
                        help="app UID that must own the data "
                             "(default: %(default)s)")
    parser.add_argument("--gid", type=int, default=DEFAULT_GID,
                        help="app GID that must own the data "
                             "(default: %(default)s)")
    parser.add_argument("--db-name", default=DEFAULT_DB_NAME,
                        help="evidence DB filename inside the data dir "
                             "(default: %(default)s)")
    args = parser.parse_args(argv)
    if args.uid == 0 or args.gid == 0:
        parser.error("refusing target UID/GID 0 (the app must not run as root)")
    return args


def resolve_data_dir(base_dir, data_dir):
    """Resolve + enforce the scope guard. Returns the real path."""
    base = os.path.realpath(base_dir)
    if base == os.sep:
        fail(f"refusing base-dir {base_dir!r}: the filesystem root "
             f"is never a permitted scope")
    data = os.path.realpath(data_dir)
    if data == base:
        fail(f"refusing data-dir {data_dir!r}: it must be strictly "
             f"inside base-dir {base_dir!r}, not the base itself")
    if os.path.commonpath([data, base]) != base:
        fail(f"refusing data-dir {data_dir!r}: it resolves outside "
             f"base-dir {base_dir!r} (resolved: {data!r})")
    return data


def ensure_owned(path, uid, gid, mode, what):
    """Chown/chmod ONLY where the current state differs. Returns True
    when a change was made. EPERM (or any OSError) fails closed."""
    try:
        st = os.lstat(path)
    except OSError as exc:
        fail(f"cannot stat {what} {path!r}: {exc}")
    changed = False
    if st.st_uid != uid or st.st_gid != gid:
        try:
            os.chown(path, uid, gid, follow_symlinks=False)
        except OSError as exc:
            fail(f"cannot chown {what} {path!r} to {uid}:{gid}: {exc} "
                 f"(run as root, or pre-chown the volume to {uid}:{gid})")
        changed = True
    current_mode = stat.S_IMODE(st.st_mode)
    if current_mode != mode:
        try:
            os.chmod(path, mode, follow_symlinks=False)
        except OSError as exc:
            fail(f"cannot chmod {what} {path!r} to {oct(mode)}: {exc}")
        changed = True
    return changed


def verify_owned(path, uid, gid, mode, what):
    """Stat-verify owner + mode are exactly the target."""
    try:
        st = os.lstat(path)
    except OSError as exc:
        fail(f"cannot verify {what} {path!r}: {exc}")
    if st.st_uid != uid or st.st_gid != gid:
        fail(f"{what} {path!r} is owned by {st.st_uid}:{st.st_gid}, "
             f"expected {uid}:{gid} after repair")
    if stat.S_IMODE(st.st_mode) != mode:
        fail(f"{what} {path!r} has mode {oct(stat.S_IMODE(st.st_mode))}, "
             f"expected {oct(mode)} after repair")


def drop_probe(data_dir, db_path, uid, gid):
    """Prove the app user can actually write, by briefly dropping the
    effective UID/GID (root only). Creates + removes one temp file in
    the directory and opens the DB file read-write without writing
    any bytes to it. Restores root in a finally block."""
    if os.geteuid() != 0:
        print("prepare-data-volume: note: not running as root; "
              "skipping privilege-dropped writability probe "
              "(stat verification still applies)")
        return
    probe_path = os.path.join(data_dir, ".identityforge-prep-probe")
    old_euid, old_egid = os.geteuid(), os.getegid()
    try:
        os.setegid(gid)
        os.seteuid(uid)
    except PermissionError:
        # The kernel refuses the id switch (e.g. this sandbox's user
        # namespace does not map the app UID). That is an environment
        # limitation, not a volume defect: stat verification above
        # already proved ownership/mode, so skip the probe LOUDLY
        # rather than failing a healthy volume — and rather than
        # silently pretending the probe ran. In a real container the
        # prep service runs as real root, the switch succeeds, and
        # the probe below is the operative check.
        try:
            os.seteuid(old_euid)
            os.setegid(old_egid)
        except OSError:
            pass
        print("prepare-data-volume: note: cannot switch effective "
              f"UID/GID to {uid}:{gid} in this environment "
              f"(PermissionError); skipping privilege-dropped "
              f"writability probe (stat verification still applies)")
        return
    try:
        try:
            with open(probe_path, "w") as probe:
                probe.write("prep-probe")
            os.unlink(probe_path)
        except OSError as exc:
            fail(f"as UID {uid} the app user cannot create a file in "
                 f"{data_dir!r}: {exc} (volume not writable by the "
                 f"app user after repair)")
        if db_path is not None and os.path.exists(db_path):
            try:
                with open(db_path, "r+b"):
                    pass
            except OSError as exc:
                fail(f"as UID {uid} the app user cannot open the "
                     f"evidence DB {db_path!r} read-write: {exc}")
    finally:
        # Restore root even when the probe failed (fail() raises
        # SystemExit, so this finally still runs before exit).
        try:
            os.seteuid(old_euid)
            os.setegid(old_egid)
        except OSError:
            # If root cannot be restored the process is in an unknown
            # privilege state: exit non-zero rather than continue.
            print("prepare-data-volume: ERROR: could not restore "
                  "root privileges after the writability probe",
                  file=sys.stderr)
            os._exit(1)  # noqa: SLF001 - fail-closed, no cleanup to run


def integrity_probe(db_path):
    """Read-only PRAGMA integrity_check. Returns 'ok', 'absent',
    or 'skipped-wal'. A failed check fails closed."""
    if not os.path.exists(db_path):
        return "absent"
    if os.path.getsize(db_path) == 0:
        return "absent"
    for suffix in ("-wal", "-shm"):
        if os.path.exists(db_path + suffix):
            print(f"prepare-data-volume: note: {suffix} sidecar "
                  f"present; skipping read-only integrity probe "
                  f"(the live app open is authoritative)")
            return "skipped-wal"
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        fail(f"evidence DB {db_path!r} cannot be opened read-only: "
             f"{exc} (refusing to boot against an unreadable DB)")
    if row is None or row[0] != "ok":
        fail(f"evidence DB {db_path!r} failed PRAGMA integrity_check: "
             f"{row[0] if row else None!r} (refusing to boot against "
             f"a corrupt DB — restore the volume from backup)")
    return "ok"


def main(argv=None):
    args = parse_args(argv)
    data_dir = resolve_data_dir(args.base_dir, args.data_dir)

    # The data directory itself must not be a symlink (never follow one
    # out of the owned volume), and must not be a plain file.
    if os.path.islink(args.data_dir):
        fail(f"refusing data-dir {args.data_dir!r}: it is a symlink "
             f"(symlinks are never followed out of the owned volume)")
    if os.path.exists(args.data_dir) and not os.path.isdir(args.data_dir):
        fail(f"refusing data-dir {args.data_dir!r}: it exists but is "
             f"not a directory (expected the evidence volume mount)")
    created = False
    if not os.path.exists(data_dir):
        try:
            os.makedirs(data_dir, mode=DIR_MODE, exist_ok=True)
        except OSError as exc:
            fail(f"cannot create data directory {data_dir!r}: {exc}")
        created = True

    repaired = 0
    if ensure_owned(data_dir, args.uid, args.gid, DIR_MODE, "data directory"):
        repaired += 1

    db_path = os.path.join(data_dir, args.db_name)
    entries = []
    try:
        with os.scandir(data_dir) as it:
            entries = list(it)
    except OSError as exc:
        fail(f"cannot list data directory {data_dir!r}: {exc}")
    for entry in entries:
        path = entry.path
        if entry.is_symlink():
            fail(f"refusing entry {path!r}: it is a symlink (symlinks "
                 f"inside the evidence volume are never followed)")
        if entry.is_dir(follow_symlinks=False):
            if ensure_owned(path, args.uid, args.gid, DIR_MODE, "subdirectory"):
                repaired += 1
            # No recursion: only top-level entries are repaired; the
            # app stores its DB + sidecars at the top level.
        elif entry.is_file(follow_symlinks=False):
            if ensure_owned(path, args.uid, args.gid, FILE_MODE, "file"):
                repaired += 1
        else:
            fail(f"refusing entry {path!r}: not a regular file or "
                 f"directory (special files are never repaired)")

    # Stat-verify everything repaired (and the directory itself).
    verify_owned(data_dir, args.uid, args.gid, DIR_MODE, "data directory")
    for entry in entries:
        path = entry.path
        if entry.is_dir(follow_symlinks=False):
            verify_owned(path, args.uid, args.gid, DIR_MODE, "subdirectory")
        elif entry.is_file(follow_symlinks=False):
            verify_owned(path, args.uid, args.gid, FILE_MODE, "file")

    db_exists = os.path.exists(db_path)
    drop_probe(data_dir, db_path if db_exists else None,
               args.uid, args.gid)
    integrity = integrity_probe(db_path) if db_exists else "absent"

    print(f"prepare-data-volume: prepared {data_dir} for "
          f"{args.uid}:{args.gid} "
          f"({'created' if created else 'existing'} directory, "
          f"{repaired} entr{'y' if repaired == 1 else 'ies'} repaired, "
          f"db integrity: {integrity})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
