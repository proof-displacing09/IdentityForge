"""Fake-IdP transport seam for the backend suite (v8.0.1).

The fetchers in ``identityforge.protocol.jwks`` read IdP responses
through ``httpx.stream`` (bounded streaming read, IF-V8-05 tightened
in v8.0.1), so the suite's fake IdP layer monkeypatches
``httpx.stream`` — not ``httpx.get``/``httpx.post`` (the v8 seam).
``install_stream_fake`` adapts the suite's existing fake responses
(the minimal ``_Resp`` duck-types and real ``httpx.Response``
objects) to the stream protocol: a context manager exposing
``status_code``, ``headers``, ``iter_raw(chunk_size=...)`` and
``request``. (v8.0.2 Fix A: the production fetcher reads raw wire
bytes with ``iter_raw`` — ``iter_bytes`` transparently decompresses
Content-Encoding — so the fake exposes ``iter_raw`` as its primary
seam; ``iter_bytes`` is kept for compatibility and yields the same
already-plain fake body.)

The wrapper is deliberately thin: it routes by HTTP method, passes
every keyword argument (``timeout``, ``follow_redirects``,
``trust_env``, ``data``) through to the underlying fake unchanged, and
never touches the network itself — a missing fake for the requested
method raises AssertionError instead of performing a real request.
A fake that raises (e.g. a ``ConnectError`` "provider down" fake)
propagates unchanged.

Composition mirrors the v8 two-attribute seam: the suite installs the
GET fake in a fixture and adds the POST fake later in a login helper,
and patching one side must never disturb the other. So installing
twice in one test REPLACES ONLY the fakes the later call names,
leaving the other side in place — exactly as patching ``httpx.post``
never disturbed ``httpx.get`` before.
"""

from __future__ import annotations

import json

import httpx


class _StreamResp:
    """Context-manager view of one fake IdP response for httpx.stream."""

    def __init__(self, resp: object, method: str, url: str) -> None:
        if isinstance(resp, httpx.Response):
            body = resp.content
            headers = resp.headers
            status_code = resp.status_code
            request = resp.request
        else:
            content = getattr(resp, "content", None)
            if isinstance(content, (bytes, bytearray)):
                body = bytes(content)
            else:
                body = json.dumps(resp.json()).encode()
            raw_headers = getattr(resp, "headers", None)
            if raw_headers is None:
                headers = httpx.Headers({"content-length": str(len(body))})
            elif isinstance(raw_headers, httpx.Headers):
                headers = raw_headers
            else:
                headers = httpx.Headers(raw_headers)
            status_code = getattr(resp, "status_code", 200)
            request = getattr(resp, "request", None)
        self._body = body
        self._resp = resp
        self.status_code = status_code
        self.headers = headers
        self.request = request if request is not None else httpx.Request(method, url)

    def __enter__(self) -> "_StreamResp":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def iter_raw(self, chunk_size: int | None = None):
        # Raw wire bytes: fake bodies are already plain (never
        # Content-Encoded), so raw and decoded iteration coincide.
        # This is the seam _bounded_fetch reads (v8.0.2 Fix A).
        if not self._body:
            return
        if chunk_size is None or chunk_size <= 0:
            yield self._body
            return
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i : i + chunk_size]

    def iter_bytes(self, chunk_size: int | None = None):
        if not self._body:
            return
        if chunk_size is None or chunk_size <= 0:
            yield self._body
            return
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i : i + chunk_size]

    def raise_for_status(self) -> None:
        # Mirrors the real Response interface; the production fetcher
        # never calls it on the stream response (status is handled on
        # the synthesised response), but a fake that models an error
        # status keeps its own behaviour here.
        raise_for_status = getattr(self._resp, "raise_for_status", None)
        if raise_for_status is not None:
            raise_for_status()


class _StreamFake:
    """One fake ``httpx.stream``: routes GET/POST to the installed fakes."""

    def __init__(self, get_fake=None, post_fake=None) -> None:
        self.get_fake = get_fake
        self.post_fake = post_fake

    def update(self, get_fake=None, post_fake=None) -> None:
        # Replace only the sides this call names; the other side keeps
        # the fake installed earlier in the test (fixture GET + helper
        # POST composition — see the module docstring).
        if get_fake is not None:
            self.get_fake = get_fake
        if post_fake is not None:
            self.post_fake = post_fake

    def __call__(self, method: str, url: str, **kwargs):
        fake = self.get_fake if str(method).upper() == "GET" else self.post_fake
        if fake is None:
            raise AssertionError(f"no fake IdP response for {method} {url}")
        return _StreamResp(fake(url, **kwargs), str(method).upper(), url)


def install_stream_fake(monkeypatch, get_fake=None, post_fake=None):
    """Monkeypatch ``httpx.stream`` with a fake routing GET/POST.

    Each fake keeps its v8 signature ``fake(url, **kwargs)`` and its
    own assertions (e.g. ``follow_redirects is False``); only the
    transport entry point changes. If a fake is already installed in
    this test (e.g. the fixture installed the GET fake), this call
    extends it instead of replacing it.
    """
    current = httpx.stream
    if isinstance(current, _StreamFake):
        current.update(get_fake=get_fake, post_fake=post_fake)
        return current
    fake = _StreamFake(get_fake=get_fake, post_fake=post_fake)
    monkeypatch.setattr("httpx.stream", fake)
    return fake
