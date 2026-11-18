#!/usr/bin/env python3
"""Live-gate code-provenance regression (v5 venv lesson, updated for v6).

`code_provenance()` in scripts/live-gate.py must PASS when the serving
backend returns the v6-only /lab/counts fields and FAIL when it returns
a v5-shaped counts object without them. Uses stub HTTP servers on
ephemeral loopback ports — no Keycloak, no real backend needed.

Run: python3 scripts/test-live-gate-provenance.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

_spec = importlib.util.spec_from_file_location("live_gate", ROOT / "scripts" / "live-gate.py")
lg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lg)

V6_COUNTS = {
    "runs": 3, "sessions": 1, "sessions_total_issued": 2, "live_logins": 1,
    "transactions": 0, "events": 5,
    "runs_limit": 1000, "events_limit": 20000, "live_logins_limit": 1000,
    "live_login_events": 1, "live_login_transactions": 1,
    "live_login_successful_transactions": 1, "live_login_event_limit": 1000,
}
V5_COUNTS = {
    "runs": 3, "sessions": 1, "sessions_total_issued": 2, "live_logins": 1,
    "transactions": 0, "events": 5,
    "runs_limit": 1000, "events_limit": 20000, "live_logins_limit": 1000,
}


def _serve(payload):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main():
    passed = failed = 0

    def ok(name, cond):
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"PASS: {name}")
        else:
            failed += 1
            print(f"FAIL: {name}")

    # 1. v6-shaped counts -> provenance passes.
    server = _serve(V6_COUNTS)
    lg.BASE_PORT = server.server_address[1]
    try:
        lg.RESULTS.clear()
        lg.code_provenance()
        ok("v6-shaped counts pass code_provenance", True)
    except AssertionError as exc:
        ok(f"v6-shaped counts pass code_provenance (raised {exc})", False)
    finally:
        server.shutdown()

    # 2. v5-shaped counts (no v6-only fields) -> provenance fails.
    server = _serve(V5_COUNTS)
    lg.BASE_PORT = server.server_address[1]
    try:
        lg.RESULTS.clear()
        lg.code_provenance()
        ok("v5-shaped counts fail code_provenance", False)
    except AssertionError:
        ok("v5-shaped counts fail code_provenance", True)
    finally:
        server.shutdown()

    print(f"\nlive-gate-provenance: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
