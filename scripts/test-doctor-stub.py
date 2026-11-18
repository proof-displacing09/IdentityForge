#!/usr/bin/env python3
"""Stub lab services for scripts/test-doctor.sh (test-only, stdlib only).

Serves Keycloak discovery (8080), backend health + lab/status (8000)
and the frontend root (5173) with configurable IdP readiness, so the
doctor's identity + readiness gating can be tested without Docker or
Keycloak.

  --reachable true|false        idp.reachable in /api/v1/lab/status
  --issuer-matches true|false   idp.issuer_matches
  --squatter                    all three ports answer plain 200 "OK"
                                with no identity markers (dummy-200 test)
"""
import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ISSUER = "http://127.0.0.1:8080/realms/identityforge-lab"


def make_handler(mode, reachable, issuer_matches):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _text(self, text, code=200):
            body = text.encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if mode == "squatter":
                return self._text("OK")
            if self.path.startswith(
                    "/realms/identityforge-lab/.well-known/openid-configuration"):
                return self._json({"issuer": ISSUER})
            if self.path == "/api/v1/health":
                return self._json({"status": "ok", "service": "identityforge-backend"})
            if self.path == "/api/v1/lab/status":
                ok = reachable and issuer_matches
                return self._json({
                    "idp": {"reachable": reachable,
                            "issuer_matches": issuer_matches,
                            "reason": "OK" if ok else "STUB_NOT_READY"},
                    "last_verified_login": None})
            if self.path == "/":
                return self._text('<html><body><div id="root"></div></body></html>')
            return self._text("not found", 404)

    return H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reachable", default="true")
    ap.add_argument("--issuer-matches", default="true")
    ap.add_argument("--squatter", action="store_true")
    args = ap.parse_args()
    mode = "squatter" if args.squatter else "lab"
    reachable = args.reachable.lower() == "true"
    issuer_matches = args.issuer_matches.lower() == "true"
    servers = []
    for port in (8080, 8000, 5173):
        server = ThreadingHTTPServer(
            ("127.0.0.1", port),
            make_handler(mode, reachable, issuer_matches))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
    print("stub lab up: mode=%s reachable=%s issuer_matches=%s"
          % (mode, reachable, issuer_matches), flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
