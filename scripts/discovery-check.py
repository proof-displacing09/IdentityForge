#!/usr/bin/env python3
"""Discovery-document check for the Compose healthcheck (Trustline v7.2, IF-V7.1-03).

The v7.1 healthcheck script piped the RAW bytes of an HTTP/1.1 response
(status line + headers + body) into ``json.load`` — which raises
``JSONDecodeError`` at char 0 on any real response, because the bytes
before the body are not JSON. This module parses HTTP framing
correctly (status line, headers, Content-Length AND chunked transfer
encoding) or, for live use, fetches through the stdlib HTTP client
(``http.client`` — no redirects are ever followed) and then enforces,
in both paths, the same three rules:

  * HTTP status must be exactly 200 (a 3xx is reported as a redirect,
    never followed; 4xx/5xx are reported with their status);
  * the body must be a valid JSON object (HTML is rejected with its
    Content-Type named, never parsed as JSON);
  * the ``issuer`` field must be present and exactly equal to the
    canonical issuer ``http://127.0.0.1:8080/realms/identityforge-lab``.

Every failure carries a precise, deterministic reason on stdout
(``discovery: FAIL: <reason>``) and exit 1; success prints
``discovery: OK issuer=<issuer>`` and exits 0. Stdlib only; no
network beyond the single requested URL, no Docker, no venv needed.

Usage:
  python3 scripts/discovery-check.py --url URL [--issuer EXPECTED]
      Fetch URL with http.client and validate the discovery document.
  python3 scripts/discovery-check.py --raw [--issuer EXPECTED]
      Read one complete raw HTTP/1.1 response from stdin and validate
      it (framing + status + body). Used by the regression matrix in
      scripts/test-compose-healthcheck-regressions.sh, which feeds it
      representative responses (valid, chunked, truncated, malformed,
      HTML, wrong issuer, ...) without any server.

The in-image check is deliberately separate: scripts/
test-compose-healthcheck.sh runs the exact healthcheck command from
docker-compose.yml inside the pinned Keycloak 26.8.2 container
(``docker compose exec``). That proves the in-image command works;
this module proves the published discovery document is the right
one. One passing does not imply the other.
"""

from __future__ import annotations

import argparse
import http.client
import json
import sys
from urllib.parse import urlparse

CANONICAL_ISSUER = "http://127.0.0.1:8080/realms/identityforge-lab"


class DiscoveryError(Exception):
    """A precise, user-facing reason the discovery check failed."""


def validate(status: int, headers: dict[str, str], body: bytes,
             expected_issuer: str) -> dict:
    """Validate a framed response (status + headers + body bytes).

    Returns the parsed JSON object on success; raises DiscoveryError
    with a precise reason otherwise. Redirects are never followed:
    any 3xx is a failure naming the Location.
    """
    if 300 <= status < 400:
        location = headers.get("location", "")
        detail = f" to {location}" if location else ""
        raise DiscoveryError(
            f"redirect (HTTP {status}{detail}) — redirects are never "
            f"followed; the discovery URL must answer 200 directly"
        )
    if status != 200:
        raise DiscoveryError(
            f"HTTP status {status} (expected 200)"
        )
    content_type = headers.get("content-type", "")
    if "text/html" in content_type.lower():
        raise DiscoveryError(
            f"HTML body (Content-Type: {content_type}), not a JSON "
            f"discovery document"
        )
    if not body:
        raise DiscoveryError("empty body (expected a JSON discovery document)")
    if body.lstrip().startswith(b"<"):
        raise DiscoveryError(
            "body looks like HTML (starts with '<'), not JSON"
        )
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DiscoveryError(f"body is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise DiscoveryError(
            f"discovery body is not a JSON object (got "
            f"{type(parsed).__name__})"
        )
    issuer = parsed.get("issuer")
    if issuer is None:
        raise DiscoveryError("discovery JSON has no 'issuer' field")
    if issuer != expected_issuer:
        raise DiscoveryError(
            f"issuer mismatch: got {issuer!r}, expected "
            f"{expected_issuer!r}"
        )
    return parsed


def parse_raw(data: bytes, expected_issuer: str) -> dict:
    """Parse one complete raw HTTP/1.1 response and validate it.

    Framing: status line, CRLF headers, then a body delimited by
    Transfer-Encoding: chunked, by Content-Length, or (neither
    present) by end-of-data. Truncation and malformed framing are
    failures with precise reasons, never silent partial parses.
    """
    # Header terminator: CRLF CRLF per RFC 9112; tolerate a bare
    # LF LF terminator so a hand-built fixture is not rejected for
    # line endings alone — the framing rules below still apply.
    terminator = b"\r\n\r\n"
    head_end = data.find(terminator)
    if head_end < 0:
        terminator = b"\n\n"
        head_end = data.find(terminator)
    if head_end < 0:
        raise DiscoveryError(
            "truncated response: header terminator not found"
        )
    head = data[:head_end].decode("iso-8859-1")
    rest = data[head_end + len(terminator):]
    lines = head.splitlines()
    if not lines:
        raise DiscoveryError("truncated response: empty response")
    status_parts = lines[0].split(None, 2)
    if len(status_parts) < 2 or not status_parts[0].startswith("HTTP/"):
        raise DiscoveryError(
            f"malformed status line: {lines[0]!r}"
        )
    try:
        status = int(status_parts[1])
    except ValueError as exc:
        raise DiscoveryError(
            f"malformed status line: {lines[0]!r}"
        ) from exc
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            raise DiscoveryError(f"malformed header line: {line!r}")
        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()

    transfer_encoding = headers.get("transfer-encoding", "").lower()
    if "chunked" in transfer_encoding:
        body = _read_chunked(rest)
    elif "content-length" in headers:
        try:
            length = int(headers["content-length"])
        except ValueError as exc:
            raise DiscoveryError(
                f"malformed Content-Length: "
                f"{headers['content-length']!r}"
            ) from exc
        if length < 0:
            raise DiscoveryError(
                f"malformed Content-Length: {length}"
            )
        if len(rest) < length:
            raise DiscoveryError(
                f"truncated response: Content-Length {length} but only "
                f"{len(rest)} body byte(s) received"
            )
        if len(rest) > length:
            raise DiscoveryError(
                f"trailing bytes after Content-Length body "
                f"({length} expected, {len(rest)} received)"
            )
        body = rest
    else:
        # No length framing: the body runs to end-of-data (HTTP/1.0
        # close-delimited). Nothing more can be checked here; the
        # JSON/issuer validation below still applies.
        body = rest
    return validate(status, headers, body, expected_issuer)


def _read_chunked(data: bytes) -> bytes:
    """Decode a chunked transfer-encoded body (RFC 9112 section 7.1).

    Raises DiscoveryError on a malformed chunk size, a truncated
    chunk, missing CRLF framing, or trailing bytes after the
    terminal chunk.
    """
    body = bytearray()
    pos = 0
    while True:
        eol = data.find(b"\r\n", pos)
        if eol < 0:
            raise DiscoveryError(
                "truncated chunked body: chunk-size line not terminated"
            )
        size_line = data[pos:eol].decode("iso-8859-1")
        size_str = size_line.split(";", 1)[0].strip()
        try:
            size = int(size_str, 16)
        except ValueError as exc:
            raise DiscoveryError(
                f"malformed chunk size: {size_line!r}"
            ) from exc
        pos = eol + 2
        if size == 0:
            # Terminal chunk: trailers follow until an empty line.
            end = data.find(b"\r\n", pos)
            if end < 0:
                raise DiscoveryError(
                    "truncated chunked body: trailer terminator not found"
                )
            # Trailers are lines until an empty line; a single CRLF
            # right after the 0-chunk means no trailers.
            if end == pos:
                pos = end + 2
            else:
                # Consume trailer lines until the empty line.
                while True:
                    eol2 = data.find(b"\r\n", pos)
                    if eol2 < 0:
                        raise DiscoveryError(
                            "truncated chunked body: trailer terminator "
                            "not found"
                        )
                    if eol2 == pos:
                        pos = eol2 + 2
                        break
                    pos = eol2 + 2
            if pos != len(data):
                raise DiscoveryError(
                    f"trailing bytes after chunked body "
                    f"({len(data) - pos} byte(s))"
                )
            return bytes(body)
        if len(data) - pos < size:
            raise DiscoveryError(
                f"truncated chunked body: chunk of {size} byte(s) "
                f"incomplete ({len(data) - pos} byte(s) received)"
            )
        body += data[pos:pos + size]
        pos += size
        if data[pos:pos + 2] != b"\r\n":
            raise DiscoveryError(
                "malformed chunk framing: missing CRLF after chunk data"
            )
        pos += 2


def fetch_url(url: str, expected_issuer: str) -> dict:
    """Fetch URL with http.client (never follows redirects) and validate."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise DiscoveryError(
            f"unsupported URL scheme: {parsed.scheme!r} (expected http/https)"
        )
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    conn_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    conn = conn_cls(host, port, timeout=10)
    try:
        conn.request(
            "GET", path,
            headers={"Host": parsed.netloc, "Accept": "application/json"},
        )
        resp = conn.getresponse()
        body = resp.read()
        headers = {k.lower(): v for k, v in resp.getheaders()}
        return validate(resp.status, headers, body, expected_issuer)
    except (OSError, http.client.HTTPException) as exc:
        raise DiscoveryError(f"request failed: {exc}") from exc
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a Keycloak discovery document: HTTP 200, "
        "valid JSON object, exact canonical issuer (IF-V7.1-03)."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", help="discovery URL to fetch (http.client)")
    group.add_argument(
        "--raw", action="store_true",
        help="read one raw HTTP/1.1 response from stdin and validate it",
    )
    parser.add_argument(
        "--issuer", default=CANONICAL_ISSUER,
        help="expected exact issuer (default: %(default)s)",
    )
    args = parser.parse_args(argv)
    try:
        if args.raw:
            parsed = parse_raw(sys.stdin.buffer.read(), args.issuer)
        else:
            parsed = fetch_url(args.url, args.issuer)
    except DiscoveryError as exc:
        print(f"discovery: FAIL: {exc}")
        return 1
    print(f"discovery: OK issuer={parsed['issuer']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
