#!/usr/bin/env python3
"""Live-gate host-map adapter tests (P0-02, v4) — stdlib only.

Proves the IDENTITYFORGE_LIVE_GATE_HOST_MAP seam changes ONLY the TCP
route, never the HTTP authority:

  1. Canonical request (no mapping): Host is 127.0.0.1:<port>.
  2. Mapped request (127.0.0.1:<port> -> localhost): the TCP connection
     goes to the mapped host, but the Host header stays canonical
     127.0.0.1:<port> — the exact header the backend's allowed-hosts
     check accepts (Host: backend:8000 used to be rejected 403).
  3. Caller-supplied Host header is respected (never overwritten).
  4. Invalid mappings fail BEFORE any connection: empty host, host
     with a scheme/path/embedded port, non-numeric port key, port out
     of range, non-object JSON, non-JSON text.
  5. A mapped request logs route + Host as HOST/PORT metadata on
     stderr (once per route), never tokens/cookies/codes.

A fake HTTP server on 127.0.0.1 captures the Host header it receives;
`localhost` stands in for the Compose service DNS name (it resolves
to the same loopback stack on this host). No real Keycloak/backend
needed. Run: python3 scripts/test-live-gate-hostmap.py
"""
from __future__ import annotations

import importlib.util
import io
import os
import subprocess
import sys
import threading
from contextlib import redirect_stderr
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS = 0
FAIL = 0


def ok(msg):
    global PASS
    PASS += 1
    print(f"PASS: {msg}")


def bad(msg):
    global FAIL
    FAIL += 1
    print(f"FAIL: {msg}")


def expect(desc, actual, wanted):
    if actual == wanted:
        ok(f"{desc} ({actual!r})")
    else:
        bad(f"{desc} — expected {wanted!r}, got {actual!r}")


def load_live_gate():
    spec = importlib.util.spec_from_file_location(
        "live_gate", os.path.join(ROOT, "scripts", "live-gate.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CaptureHandler(BaseHTTPRequestHandler):
    seen: list[dict] = []

    def _capture(self):
        CaptureHandler.seen.append({
            "method": self.command,
            "path": self.path,
            "host": self.headers.get("Host"),
            "cookie": self.headers.get("Cookie"),
        })
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = _capture
    do_POST = _capture

    def log_message(self, *args):  # keep test output clean
        pass


def start_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), CaptureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


# --- 1. Canonical request: no mapping -> Host 127.0.0.1:<port> -----------
lg = load_live_gate()
lg._HOST_MAP = {}
server = start_server()
port = server.server_address[1]
CaptureHandler.seen.clear()
lg.request(lg.Jar(), "GET", "127.0.0.1", port, "/probe")
expect("canonical Host header (no mapping)",
       CaptureHandler.seen[-1]["host"], f"127.0.0.1:{port}")

# --- 2. Mapped request: TCP to localhost, Host stays canonical ------------
lg._HOST_MAP = {port: "localhost"}
lg._LOGGED_ROUTES.clear()
err = io.StringIO()
with redirect_stderr(err):
    lg.request(lg.Jar(), "GET", "127.0.0.1", port, "/probe")
expect("mapped Host header stays canonical",
       CaptureHandler.seen[-1]["host"], f"127.0.0.1:{port}")
log = err.getvalue()
if f"route 127.0.0.1:{port} -> localhost:{port}" in log \
        and f"Host header: 127.0.0.1:{port}" in log:
    ok("mapped route logged as HOST/PORT metadata (route + Host)")
else:
    bad(f"mapped route log missing or wrong: {log!r}")
# Second request on the same route: no duplicate log line.
err = io.StringIO()
with redirect_stderr(err):
    lg.request(lg.Jar(), "GET", "127.0.0.1", port, "/probe")
if err.getvalue() == "":
    ok("mapped route logged once, not per request")
else:
    bad(f"duplicate route log line: {err.getvalue()!r}")

# --- 3. Caller-supplied Host header is respected ---------------------------
lg._HOST_MAP = {port: "localhost"}
CaptureHandler.seen.clear()
lg.request(lg.Jar(), "GET", "127.0.0.1", port, "/probe",
           headers={"Host": "custom.example:9999"})
expect("caller Host header is not overwritten",
       CaptureHandler.seen[-1]["host"], "custom.example:9999")

# --- 4. Invalid mappings fail before any connection ------------------------
bad_maps = {
    "empty host": '{"8000": ""}',
    "host with scheme": '{"8000": "http://backend"}',
    "host with path": '{"8000": "backend/evil"}',
    "host with embedded port": '{"8000": "backend:8000"}',
    "host with whitespace": '{"8000": "back end"}',
    "non-numeric port key": '{"abc": "backend"}',
    "port zero": '{"0": "backend"}',
    "port too large": '{"70000": "backend"}',
    "non-object JSON": '["backend"]',
    "non-JSON text": 'not json at all',
    "null host": '{"8000": null}',
}
for desc, raw in bad_maps.items():
    try:
        lg._parse_host_map(raw)
    except ValueError as exc:
        ok(f"invalid mapping rejected: {desc} ({exc})")
    else:
        bad(f"invalid mapping NOT rejected: {desc} ({raw})")

# Valid mappings still parse (including the shipped Compose values).
expect("shipped Compose map parses",
       lg._parse_host_map('{"8080": "keycloak", "8000": "backend"}'),
       {8080: "keycloak", 8000: "backend"})
expect("empty map parses", lg._parse_host_map(""), {})

# --- 5. Invalid mapping via the environment exits 2, no connection ---------
# Run the real script as a subprocess with a bad map: it must exit
# before main() (no HTTP traffic at all — the fake server sees nothing
# new) and print the mapping error on stderr.
CaptureHandler.seen.clear()
env = dict(os.environ)
env["IDENTITYFORGE_LIVE_GATE_HOST_MAP"] = '{"8000": "http://backend"}'
proc = subprocess.run(
    [sys.executable, os.path.join(ROOT, "scripts", "live-gate.py"), "login"],
    env=env, capture_output=True, text=True, timeout=30)
expect("bad env map exits 2 (not 0, not 1)", proc.returncode, 2)
if "IDENTITYFORGE_LIVE_GATE_HOST_MAP" in proc.stderr \
        and "no connection was attempted" in proc.stderr:
    ok("bad env map prints the mapping error on stderr")
else:
    bad(f"bad env map stderr wrong: {proc.stderr!r}")
expect("bad env map attempted no HTTP request", len(CaptureHandler.seen), 0)

server.shutdown()
print()
print(f"live-gate-hostmap: {PASS} passed, {FAIL} failed")
sys.exit(0 if FAIL == 0 else 1)
