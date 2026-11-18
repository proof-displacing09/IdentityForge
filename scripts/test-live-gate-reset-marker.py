#!/usr/bin/env python3
"""Live-gate reset safety (IF-V7.1-01, v7.2) — stdlib only.

`live-gate.py reset` is DESTRUCTIVE by design (officer reset wipes all
runs / live evidence / sessions). It must now require
`--disposable-project-id <uuid>` and verify the flag matches the
`disposable_project_id` the responding backend itself reports via
GET /api/v1/lab/status — BEFORE the first login, run creation, or POST.
Mismatched, absent, stale, malformed, forged, and default-project
markers FAIL CLOSED with a specific safety message and a nonzero exit
BEFORE any destructive call.

Fake HTTP servers on ephemeral loopback ports record every request, so
each negative case also asserts ZERO POSTs / auth requests reached the
server. No Keycloak, no real backend, no Docker needed.

Run: python3 scripts/test-live-gate-reset-marker.py
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

_spec = importlib.util.spec_from_file_location("live_gate", ROOT / "scripts" / "live-gate.py")
lg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lg)

MARKER_A = "123e4567-e89b-12d3-a456-426614174000"
MARKER_B = "123e4567-e89b-12d3-a456-426614174001"  # a different, valid UUID (stale)
NIL_MARKER = "00000000-0000-0000-0000-000000000000"

V6_COUNTS = {
    "runs": 3, "sessions": 1, "sessions_total_issued": 2, "live_logins": 1,
    "transactions": 0, "events": 5,
    "runs_limit": 1000, "events_limit": 20000, "live_logins_limit": 1000,
    "live_login_events": 1, "live_login_transactions": 1,
    "live_login_successful_transactions": 1, "live_login_event_limit": 1000,
}

PASSED = 0
FAILED = 0


def ok(name):
    global PASSED
    PASSED += 1
    print(f"PASS: {name}")


def bad(name, detail=""):
    global FAILED
    FAILED += 1
    print(f"FAIL: {name} {detail}")


def check_fn(name, fn_name):
    """The new function must exist (failing-first: absent on old code)."""
    fn = getattr(lg, fn_name, None)
    if fn is None:
        bad(f"{name} — live-gate.py has no {fn_name}() (unguarded reset)")
        return None
    return fn


def make_server(status_payload, status_code=200):
    """Fake backend: records every request; serves /lab/status and
    /lab/counts, 404s everything else (no login / reset can succeed)."""
    seen: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def _serve(self):
            seen.append({"method": self.command, "path": self.path})
            if self.path == "/api/v1/lab/status":
                code, payload = status_code, status_payload
            elif self.path == "/api/v1/lab/counts":
                code, payload = 200, V6_COUNTS
            else:
                code, payload = 404, {"detail": "not_found"}
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = _serve
        do_POST = _serve

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, seen


def no_destructive_requests(seen):
    """No POST and no auth/login request reached the fake backend."""
    bad_reqs = [r for r in seen
                if r["method"] == "POST" or r["path"].startswith("/auth/")]
    return not bad_reqs, bad_reqs


def main():
    parse_fn = check_fn("reset arg parsing", "_parse_reset_args")
    verify_fn = check_fn("disposable-marker verification", "verify_disposable_project")

    # --- 1. Argument parsing: flag REQUIRED, no default, strict UUID ----
    if parse_fn is not None:
        for argv, label in (
            ([], "no flag"),
            (["--disposable-project-id"], "flag with no value"),
            (["--disposable-project-id", "not-a-uuid"], "malformed flag value"),
            (["--disposable-project-id", NIL_MARKER], "nil-UUID flag value"),
            (["--disposable-project-id", MARKER_A, "--surprise"], "unknown extra arg"),
        ):
            try:
                parse_fn(argv)
                bad(f"reset rejects {label} (exit nonzero, no connection)")
            except SystemExit as exc:
                if exc.code not in (0, None):
                    ok(f"reset rejects {label} (exit nonzero, no connection)")
                else:
                    bad(f"reset rejects {label} (exit nonzero, no connection)",
                        f"exited {exc.code}")
            except Exception as exc:  # noqa: BLE001 - any other raise is a fail
                bad(f"reset rejects {label} (exit nonzero, no connection)",
                    f"raised {type(exc).__name__}: {exc}")
        try:
            got = parse_fn(["--disposable-project-id", MARKER_A.upper()])
            if got == MARKER_A:
                ok("reset accepts a valid UUID flag (canonicalised)")
            else:
                bad("reset accepts a valid UUID flag (canonicalised)", f"got {got!r}")
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            bad("reset accepts a valid UUID flag (canonicalised)",
                f"raised {type(exc).__name__}: {exc}")

    # --- 2. Verification against the fake backend -----------------------
    if verify_fn is not None:
        def run_verify(expected, status_payload, label, status_code=200):
            server, seen = make_server(status_payload, status_code)
            lg.BASE_PORT = server.server_address[1]
            try:
                lg.RESULTS.clear()
                verify_fn(expected)
                return server, seen, None
            except AssertionError as exc:
                return server, seen, str(exc)
            finally:
                server.shutdown()

        # 2a. Matching marker -> verification passes, only a status GET.
        server, seen, err = run_verify(
            MARKER_A, {"backend": "ok", "disposable_project_id": MARKER_A},
            "matching marker")
        clean, bad_reqs = no_destructive_requests(seen)
        if err is None and clean and seen == [
                {"method": "GET", "path": "/api/v1/lab/status"}]:
            ok("matching marker verifies (single read-only status GET)")
        else:
            bad("matching marker verifies (single read-only status GET)",
                f"err={err} seen={seen}")

        # 2b-2g. Every other marker shape FAILS CLOSED, zero destructive.
        negative_cases = [
            (MARKER_B, {"backend": "ok", "disposable_project_id": MARKER_A},
             "mismatched marker fails closed"),
            (MARKER_A, {"backend": "ok", "disposable_project_id": MARKER_B},
             "stale marker fails closed"),
            (MARKER_A, {"backend": "ok"},
             "absent marker (persistent/default lab) fails closed"),
            (MARKER_A, {"backend": "ok", "disposable_project_id": "not-a-uuid"},
             "malformed reported marker fails closed"),
            (MARKER_A, {"backend": "ok", "disposable_project_id": NIL_MARKER},
             "nil (default-project) reported marker fails closed"),
            (MARKER_B, {"backend": "ok", "disposable_project_id": MARKER_A},
             "forged caller marker fails closed"),
        ]
        for expected, payload, label in negative_cases:
            server, seen, err = run_verify(expected, payload, label)
            clean, bad_reqs = no_destructive_requests(seen)
            if err is not None and clean and "REFUSING" in err:
                ok(f"{label} (zero POSTs/auth, safety message)")
            else:
                bad(f"{label} (zero POSTs/auth, safety message)",
                    f"err={err!r} destructive={bad_reqs}")
        # 2h. Backend status unreadable -> fail closed, zero destructive.
        server, seen, err = run_verify(
            MARKER_A, {"detail": "boom"}, "status 500", status_code=500)
        clean, bad_reqs = no_destructive_requests(seen)
        if err is not None and clean:
            ok("unreadable backend status fails closed (zero POSTs/auth)")
        else:
            bad("unreadable backend status fails closed (zero POSTs/auth)",
                f"err={err!r} destructive={bad_reqs}")

        # 2i. Two fake projects: A's marker verifies against A only; B
        #     (a different disposable project) is untouched — zero POSTs.
        server_a, seen_a = make_server(
            {"backend": "ok", "disposable_project_id": MARKER_A})
        server_b, seen_b = make_server(
            {"backend": "ok", "disposable_project_id": MARKER_B})
        try:
            lg.BASE_PORT = server_a.server_address[1]
            lg.RESULTS.clear()
            verify_fn(MARKER_A)
            ok("project A verifies with its own marker")
        except AssertionError as exc:
            bad("project A verifies with its own marker", str(exc))
        finally:
            server_a.shutdown()
        try:
            lg.BASE_PORT = server_b.server_address[1]
            lg.RESULTS.clear()
            verify_fn(MARKER_A)
            bad("project B refuses project A's marker")
        except AssertionError as exc:
            clean, bad_reqs = no_destructive_requests(seen_b)
            if clean and "REFUSING" in str(exc):
                ok("project B refuses project A's marker (zero POSTs/auth)")
            else:
                bad("project B refuses project A's marker (zero POSTs/auth)",
                    f"destructive={bad_reqs}")
        finally:
            server_b.shutdown()

    # --- 3. CLI: `reset` with no flag exits nonzero BEFORE any network --
    # SAFETY: this must NEVER run a bare `reset` subprocess against a
    # listening backend — on the OLD unguarded code that would execute
    # the destructive flow against whatever listens on 8000. So the
    # CLI path is proven in-process (fake server, argv patched) and the
    # subprocess variant runs ONLY when nothing listens on 8000.
    import socket

    def _port_8000_listening():
        try:
            with socket.create_connection(("127.0.0.1", 8000), timeout=2):
                return True
        except OSError:
            return False

    if verify_fn is not None and parse_fn is not None:
        for argv, label in ((["live-gate.py", "reset"], "bare `reset`"),
                            (["live-gate.py", "reset", "--disposable-project-id",
                              "not-a-uuid"], "`reset` with malformed flag")):
            server, seen = make_server(
                {"backend": "ok", "disposable_project_id": MARKER_A})
            lg.BASE_PORT = server.server_address[1]
            old_argv, old_kc_port = sys.argv, lg.KC_PORT
            lg.KC_PORT = server.server_address[1]  # discovery hits the fake too
            try:
                lg.RESULTS.clear()
                sys.argv = argv
                try:
                    lg.main()
                    bad(f"main() {label} exits nonzero before any request")
                except SystemExit as exc:
                    clean, bad_reqs = no_destructive_requests(seen)
                    if exc.code not in (0, None) and not seen:
                        ok(f"main() {label} exits nonzero with zero requests "
                           f"(rc={exc.code})")
                    else:
                        bad(f"main() {label} exits nonzero before any request",
                            f"rc={exc.code} seen={seen}")
            finally:
                sys.argv = old_argv
                lg.KC_PORT = old_kc_port
                server.shutdown()

    if _port_8000_listening():
        print("SKIP: subprocess bare-`reset` cases (something listens on "
              "8000 — refusing to run them against a live stack)")
    else:
        for argv, label in ((["reset"], "bare `reset`"),
                            (["reset", "--disposable-project-id", "not-a-uuid"],
                             "`reset` with malformed flag")):
            proc = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "live-gate.py"), *argv],
                capture_output=True, text=True, timeout=60)
            out = proc.stdout + proc.stderr
            if proc.returncode != 0 and (
                    "--disposable-project-id" in out or "REFUSING" in out):
                ok(f"CLI {label} exits nonzero with the safety message "
                   f"(rc={proc.returncode}, no server needed)")
            else:
                bad(f"CLI {label} exits nonzero with the safety message "
                    f"(rc={proc.returncode})", f"out={out[:300]!r}")

    # --- 4. Runner wiring (static): the -Full runners generate a fresh
    # UUID per run, inject it into the disposable backend, pass it to
    # live-gate reset, and tear down ONLY that project's volumes. ------
    sh = (ROOT / "scripts" / "test-all.sh").read_text()
    ps1 = (ROOT / "scripts" / "test-all.ps1").read_text()
    compose = (ROOT / "docker-compose.yml").read_text()
    if "IDENTITYFORGE_DISPOSABLE_PROJECT_ID" in sh and "uuid" in sh.lower():
        ok("test-all.sh generates a per-run disposable project ID")
    else:
        bad("test-all.sh generates a per-run disposable project ID")
    if "live-gate.py reset --disposable-project-id" in sh:
        ok("test-all.sh passes --disposable-project-id to live-gate reset")
    else:
        bad("test-all.sh passes --disposable-project-id to live-gate reset")
    if "[guid]::NewGuid()" in ps1 and "IDENTITYFORGE_DISPOSABLE_PROJECT_ID" in ps1:
        ok("test-all.ps1 generates a per-run disposable project ID")
    else:
        bad("test-all.ps1 generates a per-run disposable project ID")
    if "--disposable-project-id" in ps1 and "live-gate.py" in ps1:
        ok("test-all.ps1 passes --disposable-project-id to live-gate reset")
    else:
        bad("test-all.ps1 passes --disposable-project-id to live-gate reset")
    if "IDENTITYFORGE_DISPOSABLE_PROJECT_ID" in compose:
        ok("docker-compose.yml passes the marker into the backend service")
    else:
        bad("docker-compose.yml passes the marker into the backend service")
    # Teardown scoping: every `down -v` in both runners names the
    # disposable project (-p $COLD_PROJECT / -p $ColdProject); a bare
    # `down -v` would destroy a persistent project's volumes.
    bare_sh = [ln for ln in sh.splitlines()
               if "down -v" in ln and "-p" not in ln and "COLD_PROJECT" not in ln
               and "COMPOSE_COLD" not in ln and ln.strip() and not ln.strip().startswith("#")]
    bare_ps1 = [ln for ln in ps1.splitlines()
                if "down" in ln and '"-v"' in ln and "ColdProject" not in ln
                and ln.strip() and not ln.strip().startswith("#")]
    if not bare_sh and not bare_ps1:
        ok("disposable teardown is scoped to the cold-start project only")
    else:
        bad("disposable teardown is scoped to the cold-start project only",
            f"sh={bare_sh} ps1={bare_ps1}")

    print(f"\nlive-gate-reset-marker: {PASSED} passed, {FAILED} failed")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
