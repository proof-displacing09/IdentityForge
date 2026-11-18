#!/usr/bin/env python3
"""Local stub for the GitHub Advisory Database (test-only).

Used by scripts/test-dependency-gates.sh to drive
scripts/npm-advisory-check.py deterministically, without network or
rate-limit luck. Serves two endpoints from a scenario JSON file:

  GET /rate_limit  -> {"resources": {"core": {"remaining": N, "reset": E}}}
  GET /advisories?ecosystem=npm&affects=<name>@<version>
                     -> the advisory list for that exact name@version
                        (default []), and logs the queried `affects`
                        value to the query-log file.

Scenario file format:
  {"rate_limit_remaining": 60, "rate_limit_reset": 1893456000,
   "advisories": {"vite@7.3.8": [{"ghsa_id": "...", "cve_id": "...",
                    "severity": "high", "summary": "..."}]}}

Stdlib only. Never used outside tests; never pointed at by production
code (the check script defaults to the real api.github.com).
"""
import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


def make_handler(scenario, query_log):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep test output clean
            pass

        def _send(self, obj):
            body = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/rate_limit":
                self._send({"resources": {"core": {
                    "remaining": scenario.get("rate_limit_remaining", 60),
                    "reset": scenario.get("rate_limit_reset", 1893456000),
                }}})
                return
            if parsed.path == "/advisories":
                qs = parse_qs(parsed.query)
                affects = (qs.get("affects") or [""])[0]
                if query_log:
                    with open(query_log, "a") as fh:
                        fh.write(affects + "\n")
                self._send(scenario.get("advisories", {}).get(affects, []))
                return
            self.send_response(404)
            self.end_headers()

    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--query-log", default="")
    args = ap.parse_args()
    with open(args.scenario) as fh:
        scenario = json.load(fh)
    server = ThreadingHTTPServer(
        ("127.0.0.1", args.port),
        make_handler(scenario, args.query_log),
    )
    print(f"GHSA stub on 127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
