"""WS1 v8.0.2 Fix A — Content-Encoding zip-bomb memory gap (§A).

Failing-first: v8.0.1's ``_bounded_fetch`` streamed with
``resp.iter_bytes()``, which transparently decompresses
Content-Encoding BEFORE the 1 MiB check — and httpx's default
Accept-Encoding advertises gzip/deflate, so a peer that answers
``Content-Encoding: gzip`` gets its body decompressed in full. A
12,253-byte gzip wire body expanding to 12,582,912 bytes (12 MiB)
raised the right ValueError but only after a ~38.9 MiB tracemalloc
peak (reproduced 2026-11-13, three runs: 38,943,247 / 38,943,107 /
38,943,185 bytes; see ``~/workspace/ws1-v802-evidence/``).

The fix (in ``identityforge.protocol.jwks._bounded_fetch``):
request ``Accept-Encoding: identity``, REJECT every non-identity
Content-Encoding BEFORE reading any body, and read the raw wire
bytes (``iter_raw``) so nothing can be decompressed implicitly.
A peer that ignores the header is still rejected by the header
check — the header is a request, never a guarantee.

These tests drive the fetchers against a local loopback stub only
(no external egress) plus the suite's fake-``httpx.stream`` seam
for the transport fetchers, whose URLs are pinned to port 8080.
The memory test asserts the tracemalloc peak stays bounded: a mere
ValueError after full allocation is NOT a passing proof.
"""

from __future__ import annotations

import gc
import gzip
import json
import threading
import tracemalloc
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from identityforge.protocol.jwks import (
    MAX_IDP_RESPONSE_BYTES,
    fetch_discovery_via_transport,
    fetch_jwks,
    fetch_jwks_via_transport,
    post_token_via_transport,
)
from identityforge.scenarios.fixtures import EXPECTED_ISSUER
from tests.fake_http import install_stream_fake

EXPANDED_LEN = 12_582_912  # 12 MiB exactly
WIRE_GZIP = gzip.compress(b"a" * EXPANDED_LEN, compresslevel=9, mtime=0)
WIRE_DEFLATE = zlib.compress(b"a" * EXPANDED_LEN, 9)
SMALL_JSON = b'{"keys": []}'
SMALL_GZIP = gzip.compress(SMALL_JSON, compresslevel=9, mtime=0)
# 12,253 gzip / 12,241 deflate wire bytes, both expanding to 12 MiB:
# far under the 1 MiB cap on the wire, 12x over it expanded.
assert len(WIRE_GZIP) == 12_253, len(WIRE_GZIP)
assert len(WIRE_DEFLATE) == 12_241, len(WIRE_DEFLATE)
assert len(WIRE_GZIP) < MAX_IDP_RESPONSE_BYTES
assert len(WIRE_DEFLATE) < MAX_IDP_RESPONSE_BYTES

# Memory bound for the expanding-body tests: the fixed fetcher rejects
# before reading any body, so its peak is httpx + socket overhead
# (measured ~1–2 MiB post-fix). 4 MiB leaves headroom for allocator
# noise while the pre-fix ~38.9 MiB peak fails it by ~10x.
MEM_BOUND_BYTES = 4 * 1024 * 1024


class _Stub(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # Last Accept-Encoding the stub saw per path (pins the request).
    seen_accept_encoding: dict[str, str | None] = {}

    def log_message(self, *args):  # silence the stub
        pass

    def _record(self) -> None:
        _Stub.seen_accept_encoding[self.path] = self.headers.get("Accept-Encoding")

    def _send_ce(self, status, wire, encoding, *, extra_headers=(), declared=None):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        if isinstance(encoding, (list, tuple)):
            for value in encoding:
                self.send_header("Content-Encoding", value)
        elif encoding is not None:
            self.send_header("Content-Encoding", encoding)
        self.send_header("Content-Length", str(declared if declared is not None else len(wire)))
        for key, value in extra_headers:
            self.send_header(key, value)
        self.end_headers()
        if wire:
            self.wfile.write(wire)

    def do_GET(self):
        self._record()
        if self.path == "/jwks":
            self._send_ce(200, SMALL_JSON, None)
        elif self.path == "/gzip-big":
            self._send_ce(200, WIRE_GZIP, "gzip")
        elif self.path == "/deflate-big":
            self._send_ce(200, WIRE_DEFLATE, "deflate")
        elif self.path == "/gzip-small":
            # Expands to 12 bytes — under the cap — and must STILL be
            # rejected: no non-identity encoding is ever accepted.
            self._send_ce(200, SMALL_GZIP, "gzip")
        elif self.path == "/gzip-upper":
            self._send_ce(200, WIRE_GZIP, "GZIP")
        elif self.path == "/gzip-mixed":
            self._send_ce(200, WIRE_GZIP, "GZip")
        elif self.path == "/gzip-dupe":
            self._send_ce(200, WIRE_GZIP, ["gzip", "gzip"])
        elif self.path == "/gzip-comma":
            self._send_ce(200, WIRE_GZIP, "gzip, gzip")
        elif self.path == "/gzip-identity":
            self._send_ce(200, WIRE_GZIP, "gzip, identity")
        elif self.path == "/identity-gzip":
            self._send_ce(200, WIRE_GZIP, "identity, gzip")
        elif self.path == "/br":
            # No brotli decoder in this httpx build, so a real br body
            # would not even decode here — the rejection is by header,
            # which is what makes it hold on any build.
            self._send_ce(200, b"br-bytes-not-brotli", "br")
        elif self.path == "/unknown":
            self._send_ce(200, SMALL_JSON, "x-custom")
        elif self.path == "/compress":
            self._send_ce(200, SMALL_JSON, "compress")
        elif self.path == "/identity":
            self._send_ce(200, SMALL_JSON, "identity")
        elif self.path == "/Identity":
            self._send_ce(200, SMALL_JSON, "Identity")
        elif self.path == "/gzip-chunked":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            frame = b"%x\r\n" % len(WIRE_GZIP) + WIRE_GZIP + b"\r\n"
            try:
                self.wfile.write(frame)
                self.wfile.write(b"0\r\n\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass
        elif self.path == "/gzip-no-cl":
            # HTTP/1.0 close-delimited gzip body, no Content-Length.
            self.protocol_version = "HTTP/1.0"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Encoding", "gzip")
            self.end_headers()
            self.wfile.write(WIRE_GZIP)
            self.close_connection = True
        elif self.path == "/gzip-declared-huge":
            # Declares 5 MiB AND gzip: the encoding rejection fires
            # first (both are checked before any body byte is read).
            self._send_ce(200, WIRE_GZIP, "gzip", declared=5 * 1024 * 1024)
        elif self.path == "/gzip-500":
            self._send_ce(500, WIRE_GZIP, "gzip")
        elif self.path == "/gzip-redir":
            self._send_ce(302, b"", "gzip", extra_headers=[("Location", "/jwks")])
        elif self.path == "/gzip-short":
            # Declares 100 bytes, sends 10 wire bytes, then closes:
            # the encoding check fires before the body is read, so
            # this is a ValueError — not a transport error.
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", "100")
            self.end_headers()
            self.wfile.write(WIRE_GZIP[:10])
            self.close_connection = True
        else:
            self._send_ce(404, b"{}", None)

    def do_POST(self):
        self._record()
        self._send_ce(404, b"{}", None)


@pytest.fixture(scope="module")
def stub_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


# ------------------------------------------------------------------
# The memory proof: expanding bodies must be rejected WITHOUT the
# allocation. Pre-fix these FAIL the peak assertion (~38.9 MiB);
# a ValueError alone does not pass them.


@pytest.mark.parametrize("path", ["/gzip-big", "/deflate-big"])
def test_expanding_body_rejected_with_bounded_memory(stub_url, path):
    gc.collect()
    tracemalloc.start()
    try:
        # Any ValueError is accepted here on purpose: pre-fix the
        # fetcher DOES raise ("size limit") — but only after full
        # decompression. What must fail pre-fix is the PEAK assertion
        # below, not the raise. The Content-Encoding message itself
        # is pinned by the matrix tests.
        with pytest.raises(ValueError):
            fetch_jwks(f"{stub_url}{path}")
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < MEM_BOUND_BYTES, f"peak={peak} bytes on {path}"


def test_request_advertises_identity_only(stub_url):
    doc = fetch_jwks(f"{stub_url}/jwks")
    assert doc == {"keys": []}
    assert _Stub.seen_accept_encoding["/jwks"] == "identity"


# ------------------------------------------------------------------
# Encoding matrix: every non-identity spelling is rejected, even
# when the expanded body would fit under the cap.


@pytest.mark.parametrize(
    "path",
    [
        "/gzip-big",
        "/gzip-small",
        "/gzip-upper",
        "/gzip-mixed",
        "/gzip-dupe",
        "/gzip-comma",
        "/gzip-identity",
        "/identity-gzip",
        "/br",
        "/unknown",
        "/compress",
        "/gzip-chunked",
        "/gzip-no-cl",
        "/gzip-declared-huge",
        "/gzip-500",
        "/gzip-redir",
        "/gzip-short",
    ],
)
def test_non_identity_content_encoding_rejected(stub_url, path):
    with pytest.raises(ValueError, match="Content-Encoding"):
        fetch_jwks(f"{stub_url}{path}")


@pytest.mark.parametrize("path", ["/identity", "/Identity"])
def test_identity_content_encoding_accepted(stub_url, path):
    doc = fetch_jwks(f"{stub_url}{path}")
    assert doc == {"keys": []}


def test_plain_response_without_content_encoding_accepted(stub_url):
    doc = fetch_jwks(f"{stub_url}/jwks")
    assert doc == {"keys": []}


# ------------------------------------------------------------------
# All four fetchers share _bounded_fetch: the transport fetchers
# (pinned to port 8080, so driven through the fake-httpx.stream
# seam) must reject a gzip response the same way, and must send
# Accept-Encoding: identity. A plain response still works.


def _gzip_response(*, content: bytes = SMALL_JSON) -> httpx.Response:
    # Duck-typed, NOT a real httpx.Response: constructing a real one
    # with Content-Encoding: gzip makes httpx decompress .content in
    # __init__ (Response.read -> iter_bytes -> GZipDecoder), so a
    # plain-JSON body + gzip header cannot be expressed that way —
    # the construction itself raises httpx.DecodingError. The fake
    # seam (_StreamResp) accepts duck-typed responses with .content /
    # .headers / .status_code / .request, which is exactly what this
    # models: a peer that sent a gzip header.
    req = httpx.Request(
        "GET", "http://127.0.0.1:8080/realms/identityforge-lab/protocol/openid-connect/certs"
    )

    class _GzipResp:
        status_code = 200
        headers = httpx.Headers({"Content-Encoding": "gzip"})
        request = req

        def __init__(self, body: bytes) -> None:
            self.content = body

        def json(self) -> object:
            return json.loads(self.content)

        def raise_for_status(self) -> None:
            pass

    return _GzipResp(content)  # type: ignore[return-value]


def _plain_response(*, content: bytes = SMALL_JSON) -> httpx.Response:
    req = httpx.Request(
        "GET", "http://127.0.0.1:8080/realms/identityforge-lab/protocol/openid-connect/certs"
    )
    return httpx.Response(200, content=content, request=req)


def _discovery_doc() -> dict:
    return {
        "issuer": EXPECTED_ISSUER,
        "authorization_endpoint": f"{EXPECTED_ISSUER}/protocol/openid-connect/auth",
        "token_endpoint": f"{EXPECTED_ISSUER}/protocol/openid-connect/token",
        "jwks_uri": f"{EXPECTED_ISSUER}/protocol/openid-connect/certs",
    }


def test_transport_jwks_fetcher_rejects_gzip(monkeypatch):
    seen: dict = {}

    def fake_get(url, **kwargs):
        seen.update(kwargs)
        return _gzip_response()

    install_stream_fake(monkeypatch, get_fake=fake_get)
    with pytest.raises(ValueError, match="Content-Encoding"):
        fetch_jwks_via_transport(
            f"{EXPECTED_ISSUER}/protocol/openid-connect/certs",
            "http://127.0.0.1:8080",
        )
    assert seen.get("headers") == {"Accept-Encoding": "identity"}
    assert seen.get("trust_env") is False
    assert seen.get("follow_redirects") is False


def test_transport_jwks_fetcher_plain_ok(monkeypatch):
    install_stream_fake(monkeypatch, get_fake=lambda url, **kw: _plain_response())
    doc = fetch_jwks_via_transport(
        f"{EXPECTED_ISSUER}/protocol/openid-connect/certs",
        "http://127.0.0.1:8080",
    )
    assert doc == {"keys": []}


def test_discovery_fetcher_rejects_gzip(monkeypatch):
    seen: dict = {}

    def fake_get(url, **kwargs):
        seen.update(kwargs)
        return _gzip_response(content=json.dumps(_discovery_doc()).encode())

    install_stream_fake(monkeypatch, get_fake=fake_get)
    with pytest.raises(ValueError, match="Content-Encoding"):
        fetch_discovery_via_transport("http://127.0.0.1:8080", canonical_issuer=EXPECTED_ISSUER)
    assert seen.get("headers") == {"Accept-Encoding": "identity"}


def test_discovery_fetcher_plain_ok(monkeypatch):
    install_stream_fake(
        monkeypatch,
        get_fake=lambda url, **kw: _plain_response(content=json.dumps(_discovery_doc()).encode()),
    )
    endpoints = fetch_discovery_via_transport(
        "http://127.0.0.1:8080", canonical_issuer=EXPECTED_ISSUER
    )
    assert endpoints["jwks_uri"] == f"{EXPECTED_ISSUER}/protocol/openid-connect/certs"


def test_token_fetcher_rejects_gzip(monkeypatch):
    seen: dict = {}

    def fake_post(url, **kwargs):
        seen.update(kwargs)
        return _gzip_response(content=b'{"access_token": "t"}')

    install_stream_fake(monkeypatch, post_fake=fake_post)
    with pytest.raises(ValueError, match="Content-Encoding"):
        post_token_via_transport(
            f"{EXPECTED_ISSUER}/protocol/openid-connect/token",
            "http://127.0.0.1:8080",
            data={"grant_type": "authorization_code", "code": "x"},
        )
    assert seen.get("headers") == {"Accept-Encoding": "identity"}
    assert seen.get("trust_env") is False
    assert seen.get("follow_redirects") is False


def test_token_fetcher_plain_ok(monkeypatch):
    install_stream_fake(
        monkeypatch,
        post_fake=lambda url, **kw: _plain_response(
            content=b'{"access_token": "t", "id_token": "i"}'
        ),
    )
    resp = post_token_via_transport(
        f"{EXPECTED_ISSUER}/protocol/openid-connect/token",
        "http://127.0.0.1:8080",
        data={"grant_type": "authorization_code", "code": "x"},
    )
    assert resp.json()["access_token"] == "t"
