"""JWKS handling and SSRF guard for issuer / JWKS URLs.

Security rule: the backend only ever fetches identity metadata from the
allowlisted loopback issuer. Any other host — public internet, cloud
metadata (169.254.169.254), internal LAN addresses, or a URL supplied by
an attacker — is refused before any network call (I18).
"""

from __future__ import annotations

import base64
import ipaddress
import json
import re
from urllib.parse import urlparse

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from ..models import FailureReason

ALLOWED_JWKS_HOSTS = {"127.0.0.1", "localhost", "::1", "host.docker.internal"}
# host.docker.internal is a Docker-managed alias for the host loopback
# (P0-03/P0-05). It is trusted ONLY as a transport route to the pinned
# Keycloak service, never as an issuer identity and never on its own:
# the JWKS path and port below are pinned alongside it.
REALM_JWKS_PATH = "/realms/identityforge-lab/protocol/openid-connect/certs"
REALM_TOKEN_PATH = "/realms/identityforge-lab/protocol/openid-connect/token"
REALM_DISCOVERY_PATH = "/realms/identityforge-lab/.well-known/openid-configuration"
REALM_PREFIX = "/realms/identityforge-lab"
# Transport hosts: the backend may REWRITE a validated canonical
# endpoint URL to one of these hosts on port 8080 (rewrite_to_transport
# below) to reach Keycloak from inside its container. "keycloak"
# (http://keycloak:8080) is the Compose service DNS name — a private
# Compose-bridge transport route ONLY. It is NOT in ALLOWED_JWKS_HOSTS
# and is NOT loopback: it must never validate as an issuer identity
# (validate_issuer_url rejects it) and must never appear as a browser
# URL, redirect URI, or token `iss`. Host-run (non-Docker) keeps the
# config default http://127.0.0.1:8080.
ALLOWED_TRANSPORT_HOSTS = {"127.0.0.1", "localhost", "::1", "host.docker.internal", "keycloak"}
BLOCKED_PATH_HINTS = ("/metadata", "169.254", "/latest/meta-data")


def is_loopback_host(host: str) -> bool:
    host = (host or "").lower().strip("[]")
    if host in ALLOWED_JWKS_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_issuer_url(url: str, allowed_issuers: tuple[str, ...]) -> FailureReason:
    """Return OK only for an exact allowlisted issuer URL on loopback."""
    if not url or len(url) > 2048:
        return FailureReason.UNTRUSTED_ISSUER_URL
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return FailureReason.UNTRUSTED_ISSUER_URL
    if parsed.hostname is None or not is_loopback_host(parsed.hostname):
        return FailureReason.SSRF_BLOCKED
    lowered = url.lower()
    if any(hint in lowered for hint in BLOCKED_PATH_HINTS):
        return FailureReason.SSRF_BLOCKED
    # IF-V8-01 (v8): exact comparison — no trailing-slash tolerance.
    # The previous rstrip("/") comparison accepted
    # "http://127.0.0.1:8080/realms/identityforge-lab/" as the pinned
    # issuer, so the "exact allowlisted issuer URL" check was not
    # exact. The configured issuer carries no trailing slash, and
    # discovery validation is exact, so nothing legitimate changes.
    if url not in set(allowed_issuers):
        return FailureReason.UNTRUSTED_ISSUER_URL
    return FailureReason.OK


def validate_jwks_url(url: str) -> FailureReason:
    """JWKS URL must be loopback, http(s), and not a metadata endpoint."""
    if not url or len(url) > 2048:
        return FailureReason.SSRF_BLOCKED
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return FailureReason.SSRF_BLOCKED
    if parsed.hostname is None or not is_loopback_host(parsed.hostname):
        return FailureReason.SSRF_BLOCKED
    lowered = url.lower()
    if any(hint in lowered for hint in BLOCKED_PATH_HINTS):
        return FailureReason.SSRF_BLOCKED
    if parsed.username or parsed.password:
        return FailureReason.SSRF_BLOCKED
    return FailureReason.OK


def validate_discovery(discovery: dict, *, canonical_issuer: str) -> dict[str, str]:
    """Validate OIDC discovery metadata against the pinned provider (P1-12).

    Requires: issuer == canonical issuer exactly; authorization_endpoint,
    token_endpoint and jwks_uri present and under the canonical issuer
    with the expected realm paths. Returns the canonical endpoint URLs.
    Raises ValueError with a safe reason on any mismatch — never trust
    discovery metadata at face value.
    """
    if not isinstance(discovery, dict):
        raise ValueError("discovery is not an object")
    issuer = discovery.get("issuer")
    if issuer != canonical_issuer:
        raise ValueError(f"discovery issuer mismatch: {issuer!r}")
    endpoints: dict[str, str] = {}
    expected = {
        "authorization_endpoint": "/protocol/openid-connect/auth",
        "token_endpoint": "/protocol/openid-connect/token",
        "jwks_uri": "/protocol/openid-connect/certs",
    }
    base = canonical_issuer.rstrip("/")
    for key, path in expected.items():
        url = discovery.get(key)
        if not isinstance(url, str) or url != f"{base}{path}":
            raise ValueError(f"discovery {key} is not the pinned endpoint")
        endpoints[key] = url
    return endpoints


def rewrite_to_transport(url: str, transport_base: str) -> str:
    """Rewrite a canonical endpoint URL to the backend transport route.

    Only the scheme/host/port change, and only to an allowlisted
    transport host on port 8080; the path is preserved exactly. Any
    other URL (different path, userinfo, redirect, external host) raises
    ValueError. This is what lets the backend reach Keycloak from inside
    its container while the issuer identity stays canonical (P0-03/05).
    """
    parsed = urlparse(url)
    base = urlparse(transport_base)
    if parsed.scheme not in ("http", "https") or base.scheme not in ("http", "https"):
        raise ValueError("transport rewrite requires http(s)")
    # IF-V8-03 (v8): a source URL carrying a query or fragment must not
    # be rewritten — the old code preserved the query string verbatim
    # onto the transport URL, so a query-bearing endpoint (e.g. a
    # ?next= redirect hint smuggled into a canonical-looking URL) was
    # transplanted onto the trusted transport route instead of being
    # rejected. The only caller (transport_endpoint_url) already
    # rejects queries before calling here; this makes the helper itself
    # safe to call directly. Fragments were silently dropped before;
    # they are now rejected too, for the same reason.
    if parsed.query or parsed.fragment:
        raise ValueError("transport rewrite forbids query/fragment in the source URL")
    if base.query or base.fragment:
        raise ValueError("transport rewrite forbids query/fragment in the transport base")
    if base.path not in ("", "/"):
        # IF-V8-03 (v8): a transport base carrying a path was silently
        # truncated before (only base.netloc is used in the result), so
        # "http://127.0.0.1:8080/extra/path" rewrote as if it were the bare
        # host:port. Reject it here; the only caller validates the base
        # as bare host:port first.
        raise ValueError("transport rewrite forbids a path in the transport base")
    if parsed.username or parsed.password or base.username or base.password:
        raise ValueError("transport rewrite forbids URL userinfo")
    # P1-17: the source must be a loopback issuer host on port 8080.
    # Rewrite only ever runs on endpoints from validated discovery,
    # which pins them to the canonical issuer — but the rewriter must
    # not silently transplant an EXTERNAL host's endpoint onto the
    # loopback transport if it is ever called with one (the previous
    # code checked only the path, so https://evil.example/realms/...
    # was rewritten instead of rejected, contradicting this function's
    # documented contract).
    source_host = (parsed.hostname or "").lower()
    if source_host not in ALLOWED_TRANSPORT_HOSTS or (parsed.port or 80) != 8080:
        raise ValueError("transport rewrite requires a loopback issuer host on port 8080")
    host = (base.hostname or "").lower()
    if host not in ALLOWED_TRANSPORT_HOSTS or (base.port or 80) != 8080:
        raise ValueError("transport host is not allowlisted")
    if not parsed.path.startswith(REALM_PREFIX):
        raise ValueError("transport rewrite forbids non-realm paths")
    return f"{base.scheme}://{base.netloc}{parsed.path}" + (
        f"?{parsed.query}" if parsed.query else ""
    )


def fetch_jwks(url: str, timeout: float = 5.0) -> dict:
    """Fetch a JWKS document, only after the SSRF guard passes.

    Returns the raw JWKS document (``{"keys": [...]}``); callers validate
    it with ``parse_jwks`` / ``validate_id_token``. Returning the parsed
    form here used to double-parse and break every real login."""
    reason = validate_jwks_url(url)
    if reason != FailureReason.OK:
        raise ValueError(f"JWKS URL rejected: {reason.value}")
    resp = _bounded_fetch("GET", url, timeout=timeout)
    return _jwks_response_to_doc(resp)


def _jwks_response_to_doc(resp: httpx.Response) -> dict:
    """Turn an HTTP response into a JWKS document (shared by the bare
    and transport fetchers). Malformed provider responses are controlled
    ValueErrors, never escaping JSON/TypeError from the HTTP layer."""
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ValueError(f"IdP response status {resp.status_code}") from exc
    _check_response_size(resp)
    try:
        doc = resp.json()
    except RecursionError as exc:
        # IF-V8-05 (v8): json.loads on pathologically nested input
        # raises RecursionError, not ValueError — map it to the same
        # controlled ValueError so no provider payload escapes as an
        # unexpected exception type.
        raise ValueError("JWKS response JSON is nested too deeply") from exc
    except (ValueError, TypeError) as exc:
        # P1-07: a malformed provider response is a controlled ValueError,
        # never an escaping JSON/TypeError from the HTTP layer.
        raise ValueError(f"JWKS response is not valid JSON: {type(exc).__name__}") from exc
    if not isinstance(doc, dict):
        raise ValueError("JWKS response is not an object")
    return doc


# ----------------------------------------------------------------------
# IF-V8-05 (v8, tightened v8.0.1): bounded IdP response bodies.
#
# Discovery/JWKS/token responses are capped at a hard 1 MiB (Keycloak's
# real discovery is ~2 KiB, JWKS ~2 KiB, token ~1-2 KiB). The cap is
# enforced TWICE: the declared Content-Length is checked before any
# body byte is read, and the body is then read with a bounded streaming
# read (``httpx.stream`` + ``iter_raw`` in 64 KiB pieces) that stops
# at 1 MiB + 1 byte and closes the connection — so an oversized
# provider response is rejected after at most ~1 MiB + 64 KiB of
# transport bytes, never after the whole body has been buffered.
#
# (v8 checked the cap only AFTER ``httpx.get``/``httpx.post`` had
# downloaded the whole response: the accepted/parsed size was bounded,
# but the transient transport read was not. Measured 2026-11-13 with
# a stub IdP serving 5 MiB: the v8 fetcher consumed all 5 MiB before
# rejecting it, with a ~10 MiB tracemalloc peak. The streaming
# fetcher rejects the same stub after ~1.1 MiB written (paced stub)
# with a ~1.5 MiB peak; per-case numbers are in the WS2 v8.0.1 evidence.)
#
# (v8.0.2 Fix A: the v8.0.1 streaming read used ``iter_bytes``, which
# transparently decompresses Content-Encoding BEFORE the 1 MiB check
# — and httpx's default request advertises gzip/deflate. A 12,253-byte
# gzip wire body expanding to 12 MiB raised the right ValueError but
# only after a ~38.9 MiB tracemalloc peak. The fetcher now requests
# ``Accept-Encoding: identity``, rejects every non-identity
# Content-Encoding before reading any body (``_check_content_encoding``),
# and reads raw wire bytes with ``iter_raw``, so no response can be
# decompressed implicitly; a peer that ignores the request header is
# still rejected by the header check. Per-case numbers are in the
# WS1 v8.0.2 evidence.)
#
# The test seam for the fetchers is ``httpx.stream`` (v8 used
# ``httpx.get``/``httpx.post``; the suite's fake-IdP layer was
# migrated to the new seam — see ``backend/tests/conftest.py``).
# Status/JSON semantics are unchanged: the streamed bytes are
# returned as a real ``httpx.Response`` and the existing
# ``_jwks_response_to_doc`` / ``_capped_json`` helpers run on it, so
# error statuses still map to ``ValueError("IdP response status N")``,
# malformed JSON to a controlled ValueError, and transport errors
# (RemoteProtocolError, ReadTimeout, ConnectError) still propagate as
# httpx errors, exactly as before.
#
# What streaming does NOT bound: the per-read timeout is httpx's (each
# read must complete within ``timeout``); a slow-but-steady drip that
# stays inside the per-read timeout can still stretch the total fetch
# time — a total deadline is a separate change and is not claimed here.
MAX_IDP_RESPONSE_BYTES = 1_048_576
# One iter_raw() yield: bounds each transport read and therefore the
# overshoot past the cap (at most one extra chunk past 1 MiB + 1 byte).
_STREAM_READ_CHUNK_SIZE = 65_536


def _check_content_encoding(headers: object) -> None:
    """Reject any IdP response that is not sent unencoded.

    Runs BEFORE any body byte is read (streaming path). httpx's
    ``iter_bytes`` transparently decompresses Content-Encoding, and
    its default request advertises gzip/deflate — so a gzip wire body
    far under the 1 MiB cap could expand to many MiB in memory before
    the size check ever ran (v8.0.2 Fix A: 12,253 gzip wire bytes
    expanding to 12 MiB peaked at ~38.9 MiB tracemalloc). The fetcher
    therefore requests ``Accept-Encoding: identity`` AND rejects every
    response whose Content-Encoding is anything other than absent or
    ``identity`` — a peer that ignores the request header is still
    rejected, because the header is a request, never a guarantee.
    Tokens are compared case-insensitively after comma-splitting, so
    duplicate headers (``gzip`` + ``gzip``), comma-joined lists
    (``gzip, identity``), and case variants (``GZIP``, ``GZip``) are
    all rejected; ``br``, ``deflate`` and unknown tokens are rejected
    too, even when httpx has no decoder for them — an encoding the
    backend cannot see through must never be trusted to stay small.
    A small encoded body is rejected as well: the rule is about the
    encoding, not the size.
    """
    raw_values: list[str] = []
    if headers is not None:
        if hasattr(headers, "get_list"):
            raw_values = [str(v) for v in headers.get_list("content-encoding", split_commas=True)]
        else:
            value = headers.get("content-encoding")
            if value is not None:
                raw_values = [str(value)]
    for raw in raw_values:
        for token in raw.split(","):
            if token.strip().lower() != "identity":
                raise ValueError("IdP response uses unsupported Content-Encoding")


def _check_declared_length(headers: object, *, limit: int = MAX_IDP_RESPONSE_BYTES) -> None:
    """Reject an IdP response whose declared Content-Length exceeds the cap.

    Runs BEFORE any body byte is read (streaming path). A malformed
    declared length is rejected, never ignored; a missing header simply
    means there is nothing declared to check — the streamed body is
    still capped byte by byte. Same messages as the v8 check, so the
    observable rejection for a lying/oversized declaration is unchanged.
    """
    raw_values: list[str] = []
    if headers is not None:
        if hasattr(headers, "get_list"):
            raw_values = [str(v) for v in headers.get_list("content-length", split_commas=False)]
        else:
            value = headers.get("content-length")
            if value is not None:
                raw_values = [str(value)]
    for raw in raw_values:
        try:
            declared = int(raw.strip())
        except ValueError as exc:
            raise ValueError("IdP response has a malformed Content-Length") from exc
        if declared < 0 or declared > limit:
            raise ValueError("IdP response exceeds the size limit")


def _bounded_fetch(
    method: str, url: str, *, timeout: float, data: dict | None = None
) -> httpx.Response:
    """Fetch one IdP response with a bounded streaming read.

    Returns a real ``httpx.Response`` whose ``.content`` is at most
    ``MAX_IDP_RESPONSE_BYTES`` bytes, so every existing caller (status
    checks, ``.json()``, ``raise_for_status()``) works unchanged. The
    transport read itself is bounded: the Content-Encoding is checked
    (only absent or ``identity`` is accepted — see
    ``_check_content_encoding``) and the declared length is checked
    before reading, then ``iter_raw`` accumulates in 64 KiB pieces
    and raises the moment the total passes the cap — exiting the
    stream context closes the connection, so the peer cannot push
    further bytes into this backend. ``iter_raw`` (not ``iter_bytes``)
    is deliberate: ``iter_bytes`` transparently decompresses
    Content-Encoding, so a small gzip wire body could expand past the
    cap in memory before the check ran. Transport errors (incomplete
    reads, timeouts, connection failures) propagate as the httpx
    errors they already were; only size/encoding violations raise
    ValueError.

    ``trust_env=False`` (and ``follow_redirects=False``) are passed
    literally at the call site, not via a kwargs dict:
    ``test_idp_backchannel_never_uses_ambient_proxies`` greps the IdP
    path for httpx calls and requires ``trust_env=False`` in each one.
    ``data=None`` for GET is identical to omitting ``data`` (httpx
    default) and sends no body — verified by direct probe.
    """
    with httpx.stream(
        method,
        url,
        timeout=timeout,
        follow_redirects=False,
        trust_env=False,
        data=data,
        headers={"Accept-Encoding": "identity"},
    ) as resp:
        _check_content_encoding(resp.headers)
        _check_declared_length(resp.headers)
        body = bytearray()
        for piece in resp.iter_raw(chunk_size=_STREAM_READ_CHUNK_SIZE):
            body += piece
            if len(body) > MAX_IDP_RESPONSE_BYTES:
                raise ValueError("IdP response exceeds the size limit")
        request = getattr(resp, "request", None)
        if request is None:
            # A duck-typed stream response without .request (test fakes
            # predate the seam): build one so raise_for_status() on the
            # returned response works instead of raising RuntimeError.
            request = httpx.Request(method, url)
        # Strip Content-Encoding from the synthesised response:
        # _check_content_encoding above only ever lets absent/identity
        # through, but the returned response's .content is already the
        # raw wire bytes — carrying the header would make httpx decode
        # .content on .json()/.read() (a real httpx.Response built with
        # Content-Encoding: gzip decompresses in __init__), so the
        # header must not survive the synthesis.
        headers = httpx.Headers(
            (key, value) for key, value in resp.headers.items() if key.lower() != "content-encoding"
        )
        return httpx.Response(
            resp.status_code, headers=headers, content=bytes(body), request=request
        )


def _check_response_size(resp: httpx.Response, *, limit: int = MAX_IDP_RESPONSE_BYTES) -> None:
    """Reject an IdP response whose declared or actual size exceeds the cap.

    Defence in depth on the (already bounded) response the fetchers
    return: the declared length is re-checked and the actual body
    length is checked before any JSON parsing or token use.
    Defensive about duck-typed responses: the suite's fake IdP layer
    returns minimal ``_Resp`` objects with only .json() /
    .raise_for_status() / .status_code, so missing .headers/.content
    simply means there is nothing to measure — real httpx responses
    always carry both, and the stub-server tests prove the cap on them.
    """
    _check_declared_length(getattr(resp, "headers", None), limit=limit)
    content = getattr(resp, "content", None)
    if content is not None and len(content) > limit:
        raise ValueError("IdP response exceeds the size limit")


def _capped_json(resp: httpx.Response) -> dict:
    """raise_for_status + size-checked JSON parse for an IdP response."""
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ValueError(f"IdP response status {resp.status_code}") from exc
    _check_response_size(resp)
    try:
        # resp.json() (not json.loads(resp.content)): the suite's fake
        # IdP layer returns payloads via .json() with no .content, and
        # real httpx responses parse identically. The size check above
        # already ran on the real body before any parsing.
        doc = resp.json()
    except RecursionError as exc:
        raise ValueError("IdP response JSON is nested too deeply") from exc
    except (ValueError, TypeError) as exc:
        raise ValueError(f"IdP response is not valid JSON: {type(exc).__name__}") from exc
    if not isinstance(doc, dict):
        raise ValueError("IdP response is not an object")
    return doc


# ----------------------------------------------------------------------
# P0-01 (v4): trusted transport fetch.
#
# The Docker backend reaches Keycloak via the Compose service DNS
# (http://keycloak:8080), but the bare JWKS fetcher's SSRF guard
# correctly rejects that host — so every Docker login failed at JWKS
# retrieval while host-process runs passed. The fix is NOT to add
# "keycloak" to any general allowlist: ``validate_jwks_url`` and
# ``validate_issuer_url`` still reject it. Instead, transport fetches
# carry provenance: the request URL is DERIVED from (a) a canonical
# URL that passed the loopback SSRF guard and matched the pinned
# realm path exactly, and (b) the explicitly configured transport
# base from Settings. The rewritten URL is then validated narrowly
# against those same two facts before any network call. A URL that
# arrives without that provenance — e.g. a bare
# http://keycloak:8080/... string passed to fetch_jwks — is still
# SSRF_BLOCKED, and "keycloak" is never an issuer, token iss, browser
# redirect target, or arbitrary SSRF-allowed host.


def validate_transport_base(transport_base: str) -> tuple[str, int]:
    """Validate a configured IdP transport base; return (host, port).

    The transport base is the network route the backend uses to reach
    Keycloak — it is NOT an issuer identity. It must be http(s), carry
    no userinfo, name an allowlisted transport host, use port 8080,
    and be a bare host:port (no path, query or fragment). Callers must
    pass ONLY the configured ``idp_transport_base`` from Settings,
    never a caller- or provider-supplied URL.
    """
    parsed = urlparse(transport_base)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("transport base requires http(s)")
    if parsed.username or parsed.password:
        raise ValueError("transport base forbids URL userinfo")
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_TRANSPORT_HOSTS:
        raise ValueError("transport base host is not allowlisted")
    port = parsed.port or 80
    if port != 8080:
        raise ValueError("transport base must use port 8080")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("transport base must be a bare host:port")
    return host, port


def _validate_canonical_endpoint_url(url: str, expected_path: str) -> None:
    """Validate a canonical (loopback) OIDC endpoint URL before rewrite.

    The URL must pass the loopback SSRF guard AND be exactly the
    pinned realm path — no query substitution, no extra path, no
    userinfo, no fragment. Raises ValueError otherwise.
    """
    reason = validate_jwks_url(url)
    if reason != FailureReason.OK:
        raise ValueError(f"canonical endpoint URL rejected: {reason.value}")
    parsed = urlparse(url)
    if parsed.path != expected_path or parsed.query or parsed.fragment:
        raise ValueError("canonical endpoint URL is not the pinned path")


def transport_endpoint_url(canonical_url: str, transport_base: str, *, expected_path: str) -> str:
    """Derive the trusted transport representation of a canonical endpoint.

    Provenance: the returned URL is trusted ONLY because it was
    derived from a canonical URL that passed the loopback SSRF guard
    and matched the pinned realm path exactly, plus a transport base
    that passed ``validate_transport_base``. The rewritten URL is then
    validated narrowly against those same two facts (host == transport
    host, port 8080, path == expected path exactly, no userinfo, no
    query). Nothing here adds "keycloak" to a general allowlist.
    """
    _validate_canonical_endpoint_url(canonical_url, expected_path)
    host, port = validate_transport_base(transport_base)
    rewritten = rewrite_to_transport(canonical_url, transport_base)
    parsed = urlparse(rewritten)
    if (parsed.hostname or "").lower() != host or (parsed.port or 80) != port:
        raise ValueError("transport rewrite produced an unexpected host/port")
    if parsed.path != expected_path or parsed.query or parsed.fragment:
        raise ValueError("transport rewrite produced an unexpected path")
    if parsed.username or parsed.password:
        raise ValueError("transport rewrite forbids URL userinfo")
    return rewritten


def fetch_jwks_via_transport(
    canonical_jwks_url: str, transport_base: str, timeout: float = 5.0
) -> dict:
    """Fetch a JWKS document via the trusted transport route (P0-01).

    Validates the canonical URL (loopback SSRF guard + exact pinned
    certs path) BEFORE any rewrite, validates the configured transport
    base, validates the rewritten URL narrowly, and only then fetches
    with follow_redirects=False and trust_env=False. The bare
    ``fetch_jwks`` still rejects keycloak:8080 (SSRF_BLOCKED): only
    this provenance-carrying function may use the transport host.
    """
    url = transport_endpoint_url(canonical_jwks_url, transport_base, expected_path=REALM_JWKS_PATH)
    resp = _bounded_fetch("GET", url, timeout=timeout)
    return _jwks_response_to_doc(resp)


def post_token_via_transport(
    canonical_token_url: str, transport_base: str, data: dict, timeout: float = 5.0
) -> httpx.Response:
    """POST a token exchange via the trusted transport route (P0-01).

    Same provenance rules as ``fetch_jwks_via_transport``: the
    canonical token URL must pass the loopback SSRF guard and match
    the pinned token path exactly before the rewrite. Returns the raw
    response; callers raise_for_status and parse it as before.
    """
    url = transport_endpoint_url(
        canonical_token_url, transport_base, expected_path=REALM_TOKEN_PATH
    )
    resp = _bounded_fetch("POST", url, timeout=timeout, data=data)
    _check_response_size(resp)
    return resp


def fetch_discovery_via_transport(
    transport_base: str, *, canonical_issuer: str, timeout: float = 3.0
) -> dict[str, str]:
    """Fetch + validate OIDC discovery via the trusted transport route.

    The discovery URL is built from the VALIDATED transport base and
    the pinned discovery path only — never from caller-supplied or
    provider-supplied text — and is checked narrowly (host/port/path)
    before the request. The returned document is validated against
    the canonical issuer by ``validate_discovery`` (issuer + pinned
    endpoint URLs), so a foreign or tampered discovery document is
    rejected before any endpoint from it is used.
    """
    host, port = validate_transport_base(transport_base)
    parsed_base = urlparse(transport_base)
    url = f"{parsed_base.scheme}://{parsed_base.netloc}{REALM_DISCOVERY_PATH}"
    parsed = urlparse(url)
    if (parsed.hostname or "").lower() != host or (parsed.port or 80) != port:
        raise ValueError("discovery transport URL host/port mismatch")
    if parsed.path != REALM_DISCOVERY_PATH:
        raise ValueError("discovery transport URL path mismatch")
    resp = _bounded_fetch("GET", url, timeout=timeout)
    discovery = _capped_json(resp)
    return validate_discovery(discovery, canonical_issuer=canonical_issuer)


# P1-07 bounds for untrusted JWKS documents: a provider (or an attacker
# who controls a JWKS response) must not be able to feed the validator
# an unbounded document, duplicate kids, or malformed key material.
MAX_JWKS_KEYS = 10
MAX_JWKS_BYTES = 65_536
MAX_KID_LENGTH = 128
_B64URL_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _b64url_component(value: object, field: str) -> None:
    """Validate one base64url key component (n or e) without leaking it.

    Raises ValueError on any malformed value; messages name the field
    only, never the value."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"RSA JWK field {field} must be a nonempty base64url string")
    if len(value) > 4096 or not _B64URL_RE.match(value):
        raise ValueError(f"RSA JWK field {field} is not valid base64url")
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except Exception as exc:
        raise ValueError(f"RSA JWK field {field} is not valid base64url") from exc
    if not raw:
        raise ValueError(f"RSA JWK field {field} decodes to empty bytes")


def _is_signing_key(key: dict) -> bool:
    """True if the JWK can verify RS256 signatures.

    Real Keycloak publishes an RSA-OAEP encryption key (``use: enc``)
    next to its RS256 signing key. Non-signing keys are SKIPPED, never
    allowed to break the whole document: rejecting them broke every
    real login (measured 2026-11-11 — live JWKS with an enc key made
    ``parse_jwks`` raise, and every callback failed JWKS_ERROR). A key
    is a signing candidate only when ``use`` is absent or ``'sig'``
    AND ``alg`` is absent or ``'RS256'``.
    """
    use = key.get("use")
    if use is not None and use != "sig":
        return False
    alg = key.get("alg")
    if alg is not None and alg != "RS256":
        return False
    return True


def _validate_rsa_jwk(key: dict) -> str:
    """Validate one RSA SIGNING JWK entry; return its kid. Raises ValueError.

    Call only after ``_is_signing_key`` — non-signing keys are skipped
    by the caller, never validated here. A malformed signing key still
    fails the whole document (fail closed): a bad ``n``/``e`` on a key
    that claims to sign must never be silently ignored.
    """
    if not isinstance(key, dict):
        raise ValueError("JWKS key entry must be an object")
    if key.get("kty") != "RSA":
        raise ValueError("JWKS key entry is not an RSA key")
    kid = key.get("kid")
    if not isinstance(kid, str) or not kid or len(kid) > MAX_KID_LENGTH:
        raise ValueError("RSA JWK requires a nonempty kid of at most 128 characters")
    if "n" not in key or "e" not in key:
        raise ValueError("RSA JWK requires kid, n and e")
    _b64url_component(key.get("n"), "n")
    _b64url_component(key.get("e"), "e")
    return kid


def parse_jwks(jwks: dict) -> dict[str, dict]:
    """Return {kid: JWK dict} for RSA keys only; raise ValueError on bad input.

    Accepts a raw JWKS document (``{"keys": [...]}``) or an already-parsed
    ``{kid: JWK}`` mapping (idempotent — ``fetch_jwks`` used to return the
    parsed form, and the validator re-parsed it, which made every real
    login fail with JWKS_ERROR; both forms must work).

    Hardened (P1-07): ``keys`` must be a list of at most 10 entries;
    the document must be at most 64 KiB serialised; duplicate kids
    among SIGNING keys are rejected (never last-one-wins); each signing
    key needs a nonempty kid (<=128 chars) and nonempty base64url
    ``n``/``e`` (decoded to prove validity). Non-signing keys
    (``use: enc``, ``alg`` other than RS256, non-RSA ``kty``) are
    SKIPPED, not rejected — real Keycloak publishes an RSA-OAEP
    encryption key beside its RS256 signing key, and rejecting the
    document for it broke every real login (measured 2026-11-11).
    A document with no usable signing key still raises ValueError.
    All failures raise ValueError with a safe message — no key material
    is ever included in an error message.
    """
    if not isinstance(jwks, dict):
        raise ValueError("JWKS must be an object")
    try:
        size = len(json.dumps(jwks, default=str))
    except (TypeError, ValueError) as exc:
        raise ValueError("JWKS document is not serialisable") from exc
    if size > MAX_JWKS_BYTES:
        raise ValueError("JWKS document exceeds the 64 KiB size limit")
    if "keys" not in jwks:
        # Already-parsed form: validate it as {kid: RSA JWK}.
        if not jwks:
            raise ValueError("JWKS must be an object with a 'keys' list")
        if len(jwks) > MAX_JWKS_KEYS:
            raise ValueError("JWKS contains too many keys")
        out: dict[str, dict] = {}
        for map_kid, key in jwks.items():
            if not isinstance(map_kid, str) or not map_kid:
                raise ValueError("JWKS mapping key must be a nonempty kid string")
            if not isinstance(key, dict):
                raise ValueError("JWKS key entry must be an object")
            if key.get("kty") != "RSA":
                continue
            if not _is_signing_key(key):
                continue
            kid = _validate_rsa_jwk(key)
            if kid != map_kid:
                raise ValueError("JWKS mapping kid does not match the JWK kid")
            if kid in out:
                raise ValueError("JWKS contains a duplicate kid")
            out[kid] = key
        if not out:
            raise ValueError("JWKS contains no usable RSA signing keys")
        return out
    keys = jwks["keys"]
    if not isinstance(keys, list):
        raise ValueError("JWKS 'keys' must be a list")
    if not keys:
        raise ValueError("JWKS 'keys' list is empty")
    if len(keys) > MAX_JWKS_KEYS:
        raise ValueError("JWKS contains too many keys")
    out = {}
    for key in keys:
        if not isinstance(key, dict):
            raise ValueError("JWKS key entry must be an object")
        if key.get("kty") != "RSA":
            continue
        if not _is_signing_key(key):
            continue
        kid = _validate_rsa_jwk(key)
        if kid in out:
            raise ValueError("JWKS contains a duplicate kid")
        out[kid] = key
    if not out:
        raise ValueError("JWKS contains no usable RSA signing keys")
    return out


def public_jwk_from_private(private_pem: bytes, kid: str) -> dict:
    """Build a public JWK from an RSA private key (fixture generation only)."""
    key = serialization.load_pem_private_key(private_pem, password=None)
    if not isinstance(key, rsa.RSAPublicKey) and hasattr(key, "public_key"):
        key = key.public_key()  # type: ignore[assignment]
    numbers = key.public_numbers()  # type: ignore[union-attr]
    import base64

    def b64u(n: int) -> str:
        raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    return {
        "kty": "RSA",
        "kid": kid,
        "use": "sig",
        "alg": "RS256",
        "n": b64u(numbers.n),
        "e": b64u(numbers.e),
    }
