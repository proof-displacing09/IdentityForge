"""P0-06/P0-07/P1-12/P1-13/P1-15: live login path against a fake IdP.

The fake IdP is a local httpx stub (no network, no Keycloak): it serves
pinned discovery metadata, a token endpoint, and a JWKS built from
fresh fixture keys. This tests the real login/callback code path —
discovery validation, transport rewrite, browser binding, subject
mapping — without claiming a real Keycloak run.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from identityforge.api.app import create_app
from identityforge.config import Settings
from identityforge.scenarios.fixtures import (
    EXPECTED_ISSUER,
    generate_rsa_keypair,
    jwks_for,
    mint_id_token,
)
from identityforge.security.policy import OFFICER_SUB, STUDENT_SUB
from tests.fake_http import install_stream_fake


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture()
def fake_idp(monkeypatch, tmp_path):
    """Install a fake IdP and return (client, pem, jwks, state store)."""
    pem, _ = generate_rsa_keypair()
    jwks = jwks_for(pem)
    issuer = EXPECTED_ISSUER
    discovery = {
        "issuer": issuer,
        "authorization_endpoint": issuer + "/protocol/openid-connect/auth",
        "token_endpoint": issuer + "/protocol/openid-connect/token",
        "jwks_uri": issuer + "/protocol/openid-connect/certs",
    }
    minted = {"sub": STUDENT_SUB}

    def fake_get(url, **kwargs):
        if "openid-configuration" in url:
            return _Resp(discovery)
        if url.endswith("/certs"):
            return _Resp(jwks)
        raise AssertionError(f"unexpected GET {url}")

    def fake_post(url, **kwargs):
        assert url.endswith("/protocol/openid-connect/token"), url
        data = kwargs.get("data", {})
        assert data.get("code") == "fake-code"
        token = mint_id_token(
            private_pem=pem,
            subject=minted["sub"],
            nonce=None,
            extra_claims={"nonce": kwargs.get("_nonce", "x")},
        )
        # nonce is validated against the transaction; the test sets it
        # through the login flow below, so mint here with the txn nonce.
        return _Resp({"id_token": token, "token_type": "Bearer"})

    # The token must carry the transaction nonce. Patch by minting inside
    # the callback: instead, fake_post reads the nonce from the txn store
    # via the app — simpler: the tests below use a wrapper that mints
    # with the correct nonce at callback time (see _login_and_callback).
    install_stream_fake(monkeypatch, get_fake=fake_get)
    install_stream_fake(monkeypatch, post_fake=fake_post)
    app = create_app(settings=Settings(), db_path=str(tmp_path / "test.db"))
    client = TestClient(app, raise_server_exceptions=False)
    return client, pem, jwks, minted, monkeypatch, app


def _login(client, pem, subject, monkeypatch, app):
    """Drive login -> callback with the fake IdP, minting a token whose
    nonce matches the transaction the login created."""
    captured = {}

    def fake_post(url, **kwargs):
        # The transaction is consumed before the token exchange, so the
        # nonce is captured at login time (see below).
        token = mint_id_token(private_pem=pem, subject=subject, nonce=captured["nonce"])
        return _Resp({"id_token": token, "token_type": "Bearer"})

    install_stream_fake(monkeypatch, post_fake=fake_post)
    r = client.get("/auth/login", follow_redirects=False)
    assert r.status_code == 302, r.text
    assert r.headers["location"].startswith(EXPECTED_ISSUER + "/protocol/openid-connect/auth?")
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    txn = app.state.txn_store.lookup_by_state(state)
    assert txn is not None
    captured["nonce"] = txn.nonce
    return state


def test_login_callback_student_member_only(fake_idp):
    client, pem, jwks, minted, monkeypatch, app = fake_idp
    state = _login(client, pem, STUDENT_SUB, monkeypatch, app)
    r = client.get(f"/auth/callback?code=fake-code&state={state}", follow_redirects=False)
    assert r.status_code == 302 and "/portal?login=success" in r.headers["location"]
    me = client.get("/api/v1/portal/me")
    assert me.status_code == 200
    assert me.json()["username"] == "student_01"
    assert me.json()["roles"] == ["member"]
    assert client.get("/api/v1/portal/member").status_code == 200
    assert client.get("/api/v1/portal/officer").status_code == 403
    status = client.get("/api/v1/lab/status").json()
    assert status["last_verified_login"]["username"] == "student_01"


def test_login_callback_officer_gets_both(fake_idp):
    client, pem, jwks, minted, monkeypatch, app = fake_idp
    state = _login(client, pem, OFFICER_SUB, monkeypatch, app)
    r = client.get(f"/auth/callback?code=fake-code&state={state}", follow_redirects=False)
    assert r.status_code == 302 and "/portal?login=success" in r.headers["location"]
    assert client.get("/api/v1/portal/member").status_code == 200
    assert client.get("/api/v1/portal/officer").status_code == 200


def test_cross_browser_callback_rejected_and_legitimate_browser_still_works(fake_idp):
    client, pem, jwks, minted, monkeypatch, app = fake_idp
    state = _login(client, pem, STUDENT_SUB, monkeypatch, app)
    # Browser B: a fresh client with no transaction cookie.
    other = TestClient(app, raise_server_exceptions=False)
    r = other.get(f"/auth/callback?code=fake-code&state={state}", follow_redirects=False)
    assert r.status_code == 302
    assert "error=STATE_BINDING_MISMATCH" in r.headers["location"]
    assert other.get("/api/v1/portal/me").status_code == 401
    # The transaction was NOT consumed by the failed attempt: the
    # legitimate browser (client A) can still complete the login.
    r = client.get(f"/auth/callback?code=fake-code&state={state}", follow_redirects=False)
    assert r.status_code == 302 and "/portal?login=success" in r.headers["location"]
    assert client.get("/api/v1/portal/me").status_code == 200


def test_unknown_subject_rejected(fake_idp):
    client, pem, jwks, minted, monkeypatch, app = fake_idp
    state = _login(client, pem, "99999999-9999-4999-8999-999999999999", monkeypatch, app)
    r = client.get(f"/auth/callback?code=fake-code&state={state}", follow_redirects=False)
    assert r.status_code == 302
    assert "error=UNKNOWN_SUBJECT" in r.headers["location"]
    assert client.get("/api/v1/portal/me").status_code == 401


def test_malformed_run_bodies_rejected(client):
    token = client.get("/api/v1/csrf-token").json()["csrf_token"]
    headers = {"Content-Type": "application/json", "X-CSRF-Token": token}
    r = client.post("/api/v1/runs", content='["I1"]', headers=headers)
    assert r.status_code == 400
    r = client.post("/api/v1/runs", content='{"scenario_id": 123}', headers=headers)
    assert r.status_code == 400
    r = client.post("/api/v1/runs", content="{not json", headers=headers)
    assert r.status_code == 400


def test_lab_status_when_provider_down(client, monkeypatch):
    # Deterministic: simulate the outage at the HTTP layer instead of
    # relying on ambient Keycloak state (a live IdP in the sandbox used
    # to make this test fail for the wrong reason).
    import httpx

    def _down(url, **kwargs):
        raise httpx.ConnectError("provider down")

    install_stream_fake(monkeypatch, get_fake=_down)
    status = client.get("/api/v1/lab/status").json()
    assert status["idp"]["reachable"] is False
    assert status["last_verified_login"] is None


def test_idp_backchannel_never_uses_ambient_proxies():
    """Regression test for the sandbox live-gate failure: httpx parses
    NO_PROXY/HTTP_PROXY from the environment, and a bracketed-IPv6
    NO_PROXY entry made every IdP call fail with InvalidURL even though
    Keycloak was healthy. IdP backchannel traffic is pinned loopback /
    internal, so it must never transit an ambient proxy: every httpx
    call in the IdP path must pass trust_env=False. (v8.0.1: the IdP
    path goes through httpx.stream in _bounded_fetch — the seam moved
    from httpx.get/post, the trust_env requirement did not.)"""
    import pathlib
    import re

    src = pathlib.Path(__file__).resolve().parents[2] / "src" / "identityforge"
    calls = []
    for path in (src / "api" / "app.py", src / "protocol" / "jwks.py"):
        text = path.read_text()
        for m in re.finditer(r"httpx\.(get|post|stream)\(", text):
            # take the call up to its closing paren at the same indent
            start = m.start()
            depth = 0
            i = text.index("(", start)
            while True:
                ch = text[i]
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            call = text[start : i + 1]
            calls.append((str(path), call))
    assert calls, "no httpx calls found in IdP path"
    missing = [(p, c) for p, c in calls if "trust_env=False" not in c]
    assert not missing, f"IdP httpx calls missing trust_env=False: {missing}"
