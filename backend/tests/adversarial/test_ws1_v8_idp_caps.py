"""WS1 v8 — IF-V8-05: bounded IdP response bodies (§5).

Failing-first: before the fix, fetch_jwks/post_token/discovery used
httpx.get/post with no size bound and buffered the whole body. These
tests drive the fetchers against a local stub IdP (loopback only) that
serves oversized / redirecting / pathologically nested responses.

v8.0.1 tightened the cap from an after-download check to a bounded
streaming read (httpx.stream, 1 MiB + 1 early stop): the tests below
prove the transport read itself stops early — a paced chunked body
is rejected after the stub has written ~1.1 MiB, not the full 5 MiB
— and that declared-vs-actual length, missing Content-Length,
single-chunk, early-EOF, redirect and timeout shapes keep their
controlled outcomes.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from identityforge.protocol.jwks import (
    MAX_IDP_RESPONSE_BYTES,
    fetch_jwks,
    post_token_via_transport,
)
from tests.fake_http import install_stream_fake

SMALL_JWKS = {"keys": []}  # parses as JSON; parse step is not under test here
_BIG = 5 * 1024 * 1024  # 5 MiB — 5x the cap
_PIECE = 64 * 1024
_PACED_INTERVAL = 0.05  # seconds between chunked pieces on /chunked-paced


class _Stub(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # Shared observations for the streaming tests (module-scoped stub):
    # per-path request counts and bytes the paced writer got out.
    hits: dict[str, int] = {}
    paced_written = 0

    def log_message(self, *args):  # silence the stub
        pass

    def handle_error(self, request, client_address):
        # The client closing mid-body (the early-stop proof) resets
        # the keep-alive socket; that is the expected outcome, not a
        # stub failure — keep its traceback out of the test log.
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)

    def _count(self) -> None:
        _Stub.hits[self.path] = _Stub.hits.get(self.path, 0) + 1

    def _write_counted(self, data: bytes) -> bool:
        """Write, counting bytes; False if the client went away."""
        try:
            self.wfile.write(data)
            self.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionResetError):
            return False

    def _send(
        self,
        status: int,
        body: bytes,
        ctype: str = "application/json",
        extra: dict | None = None,
        declared: int | None = None,
    ):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(declared if declared is not None else len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        self._count()
        if self.path == "/jwks":
            self._send(200, json.dumps(SMALL_JWKS).encode())
        elif self.path == "/big":
            self._send(200, b"x" * (MAX_IDP_RESPONSE_BYTES + 1))
        elif self.path == "/big-declared":
            # Declares AND sends 2 MiB: the declared length alone must
            # trip the cap before any JSON parsing.
            self._send(200, b"x" * (2 * 1024 * 1024))
        elif self.path == "/redir":
            self._send(302, b"", extra={"Location": "/jwks"})
        elif self.path == "/redir-big":
            self._send(302, b"", extra={"Location": "/big"})
        elif self.path == "/deep":
            nested = b"[" * 50000 + b"]" * 50000
            self._send(200, b'{"keys": ' + nested + b"}")
        elif self.path == "/bad-cl":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "not-a-number")
            self.end_headers()
            self.wfile.write(b"{}")
        elif self.path == "/declared-small-actual-huge":
            # Declares 100 bytes, then sends 5 MiB: httpx honours the
            # declared length and reads 100 bytes. Written in pieces so
            # the client's early close ends the handler cleanly instead
            # of raising BrokenPipe out of a single 5 MiB write.
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "100")
            self.end_headers()
            body = b"x" * _BIG
            for i in range(0, _BIG, _PIECE):
                if not self._write_counted(body[i : i + _PIECE]):
                    return
        elif self.path == "/declared-huge-short":
            # Declares 5 MiB, sends 100 bytes, then closes: the declared
            # oversize is rejected before the truncated body is diagnosed.
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(_BIG))
            self.end_headers()
            self.wfile.write(b"x" * 100)
            self.close_connection = True
        elif self.path == "/short-read":
            # Declares 100 bytes (inside the cap), sends 10, then closes.
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "100")
            self.end_headers()
            self.wfile.write(b'{"keys": []')
            self.close_connection = True
        elif self.path == "/chunked-huge":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            body = b"x" * _BIG
            for i in range(0, _BIG, _PIECE):
                chunk = body[i : i + _PIECE]
                if not self._write_counted(b"%x\r\n" % len(chunk) + chunk + b"\r\n"):
                    return
            self._write_counted(b"0\r\n\r\n")
        elif self.path == "/chunked-paced":
            # Same 5 MiB chunked body, paced at one 64 KiB piece per
            # 0.05 s, with bytes written counted: an early-stopping
            # client closes the connection after ~1.1 MiB, while a
            # buffering client lets the stub write all 5 MiB.
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            body = b"x" * _BIG
            for i in range(0, _BIG, _PIECE):
                chunk = body[i : i + _PIECE]
                frame = b"%x\r\n" % len(chunk) + chunk + b"\r\n"
                if not self._write_counted(frame):
                    return
                _Stub.paced_written += len(frame)
                time.sleep(_PACED_INTERVAL)
            self._write_counted(b"0\r\n\r\n")
        elif self.path == "/chunked-single":
            # ONE 5 MiB chunk in a single chunk frame.
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            frame = b"%x\r\n" % _BIG + b"x" * _BIG + b"\r\n"
            if self._write_counted(frame):
                self._write_counted(b"0\r\n\r\n")
        elif self.path == "/no-cl-huge":
            # HTTP/1.0 close-delimited body, no Content-Length.
            self.protocol_version = "HTTP/1.0"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            body = b"x" * _BIG
            for i in range(0, _BIG, _PIECE):
                if not self._write_counted(body[i : i + _PIECE]):
                    return
            self.close_connection = True
        elif self.path == "/slow-drip":
            # 1 byte per 3 s: each read exceeds a 2 s client timeout.
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "100")
            self.end_headers()
            for _ in range(20):
                if not self._write_counted(b"x"):
                    return
                time.sleep(3.0)
        else:
            self._send(404, b"{}")

    def do_POST(self):
        if self.path == "/token":
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            self._send(200, b"x" * (MAX_IDP_RESPONSE_BYTES + 1))
        elif self.path == "/token-ok":
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            self._send(200, json.dumps({"access_token": "t", "id_token": "i"}).encode())
        else:
            self._send(404, b"{}")


@pytest.fixture(scope="module")
def stub_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_fetch_jwks_small_ok(stub_url):
    doc = fetch_jwks(f"{stub_url}/jwks")
    assert doc == SMALL_JWKS


def test_fetch_jwks_oversized_body_rejected(stub_url):
    with pytest.raises(ValueError, match="size limit"):
        fetch_jwks(f"{stub_url}/big")


def test_fetch_jwks_oversized_declared_length_rejected(stub_url):
    with pytest.raises(ValueError, match="size limit"):
        fetch_jwks(f"{stub_url}/big-declared")


def test_fetch_jwks_malformed_content_length_rejected(stub_url):
    import httpx

    with pytest.raises((ValueError, httpx.HTTPError)):
        fetch_jwks(f"{stub_url}/bad-cl")


def test_fetch_jwks_redirect_not_followed(stub_url):
    # 302 with follow_redirects=False: the redirect target is never
    # fetched; the 302 body is not a JWKS document.
    with pytest.raises(ValueError):
        fetch_jwks(f"{stub_url}/redir")


def test_fetch_jwks_deeply_nested_json_rejected(stub_url):
    with pytest.raises(ValueError):
        fetch_jwks(f"{stub_url}/deep")


def test_token_post_oversized_body_rejected(monkeypatch):
    # post_token_via_transport size-checks BEFORE returning, using the
    # same monkeypatched-httpx.stream seam the rest of the suite fakes
    # (v8.0.1: httpx.stream, was httpx.post in v8).
    import httpx

    from identityforge.scenarios.fixtures import EXPECTED_ISSUER

    canonical = f"{EXPECTED_ISSUER}/protocol/openid-connect/token"

    req = httpx.Request(
        "POST", "http://127.0.0.1:8080/realms/identityforge-lab/protocol/openid-connect/token"
    )

    def fake_big(*args, **kwargs):
        return httpx.Response(200, content=b"x" * (MAX_IDP_RESPONSE_BYTES + 1), request=req)

    def fake_ok(*args, **kwargs):
        return httpx.Response(
            200, content=json.dumps({"access_token": "t", "id_token": "i"}).encode(), request=req
        )

    install_stream_fake(monkeypatch, post_fake=fake_big)
    with pytest.raises(ValueError, match="size limit"):
        post_token_via_transport(
            canonical,
            "http://127.0.0.1:8080",
            data={"grant_type": "authorization_code", "code": "x"},
        )
    install_stream_fake(monkeypatch, post_fake=fake_ok)
    resp = post_token_via_transport(
        canonical, "http://127.0.0.1:8080", data={"grant_type": "authorization_code", "code": "x"}
    )
    resp.raise_for_status()
    assert resp.json()["access_token"] == "t"


# ------------------------------------------------------------------ v8.0.1
# Bounded streaming read: the transport read itself must stop at
# 1 MiB + 1 byte. These tests drive the same stub shapes the WS2
# reproduction harness measured (chunked, no Content-Length, single
# chunk, declared-vs-actual, early EOF, redirect-to-big, slow drip)
# and pin the controlled outcome of each.


def test_fetch_jwks_chunked_oversized_stops_early(stub_url):
    """Chunked 5 MiB (no Content-Length) is rejected AND the stub only
    got ~1.1 MiB out: the paced writer proves the client closed the
    connection at the cap instead of consuming the whole body."""
    _Stub.paced_written = 0
    t0 = time.monotonic()
    with pytest.raises(ValueError, match="size limit"):
        fetch_jwks(f"{stub_url}/chunked-paced")
    assert time.monotonic() - t0 < 5.0
    # The client read 1 MiB + 1 byte before rejecting, so the stub must
    # have written more than 1 MiB — and far less than the 5 MiB a
    # buffering client would have let through (measured ~1.1 MiB).
    assert MAX_IDP_RESPONSE_BYTES < _Stub.paced_written < 2 * 1024 * 1024, _Stub.paced_written


def test_fetch_jwks_chunked_huge_rejected(stub_url):
    with pytest.raises(ValueError, match="size limit"):
        fetch_jwks(f"{stub_url}/chunked-huge")


def test_fetch_jwks_chunked_single_huge_rejected(stub_url):
    """One 5 MiB chunk frame: the read still stops at the cap even
    though the whole body arrives in a single chunk."""
    with pytest.raises(ValueError, match="size limit"):
        fetch_jwks(f"{stub_url}/chunked-single")


def test_fetch_jwks_no_content_length_oversized_rejected(stub_url):
    """Close-delimited 5 MiB with no Content-Length: capped by the
    streamed byte count, not by any declared length."""
    with pytest.raises(ValueError, match="size limit"):
        fetch_jwks(f"{stub_url}/no-cl-huge")


def test_fetch_jwks_declared_small_actual_huge_reads_declared_only(stub_url):
    """Declares 100 bytes but sends 5 MiB: httpx honours the declared
    length, so the client sees 100 non-JSON bytes — a controlled
    JSON error, never a 5 MiB parse."""
    with pytest.raises(ValueError, match="not valid JSON"):
        fetch_jwks(f"{stub_url}/declared-small-actual-huge")


def test_fetch_jwks_declared_huge_short_read_rejected_by_size_first(stub_url):
    """Declares 5 MiB but sends 100 bytes then dies: the declared
    oversize is rejected BEFORE the truncated body is diagnosed, so
    this raises ValueError (size limit) rather than the v8
    RemoteProtocolError. Deliberate precedence — the declared-length
    check runs before any body byte is read — and both are controlled
    provider errors at the app layer (PROVIDER_ERROR)."""
    with pytest.raises(ValueError, match="size limit"):
        fetch_jwks(f"{stub_url}/declared-huge-short")


def test_fetch_jwks_short_read_still_transport_error(stub_url):
    """Declares 100 bytes (inside the cap), sends 10, then closes:
    the transport error still surfaces as the httpx error it was."""
    import httpx

    with pytest.raises(httpx.RemoteProtocolError):
        fetch_jwks(f"{stub_url}/short-read")


def test_fetch_jwks_redirect_to_oversized_never_followed(stub_url):
    """302 to an oversized target: not followed, and the target is
    never even requested."""
    before_big = _Stub.hits.get("/big", 0)
    before_redir = _Stub.hits.get("/redir-big", 0)
    with pytest.raises(ValueError):
        fetch_jwks(f"{stub_url}/redir-big")
    assert _Stub.hits.get("/redir-big", 0) == before_redir + 1
    assert _Stub.hits.get("/big", 0) == before_big


def test_fetch_jwks_slow_drip_times_out(stub_url):
    """1 byte per 3 s with a 2 s timeout: the per-read timeout fires."""
    import httpx

    t0 = time.monotonic()
    with pytest.raises(httpx.ReadTimeout):
        fetch_jwks(f"{stub_url}/slow-drip", timeout=2.0)
    assert time.monotonic() - t0 < 5.0
