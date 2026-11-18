"""Operation Trustline v3 — P1-10 username subjects denied on the live
path, and P1-07 malformed JWKS fails closed at the real callback.

Keycloak is NOT RUN here; logins use the fake-IdP stub, which serves
pinned discovery metadata, a token endpoint, and a JWKS built from
fresh fixture keys.
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


def _make_client(monkeypatch, tmp_path, jwks):
    discovery = {
        "issuer": EXPECTED_ISSUER,
        "authorization_endpoint": EXPECTED_ISSUER + "/protocol/openid-connect/auth",
        "token_endpoint": EXPECTED_ISSUER + "/protocol/openid-connect/token",
        "jwks_uri": EXPECTED_ISSUER + "/protocol/openid-connect/certs",
    }

    def fake_get(url, **kwargs):
        if "openid-configuration" in url:
            return _Resp(discovery)
        if url.endswith("/certs"):
            return _Resp(jwks)
        raise AssertionError(f"unexpected GET {url}")

    install_stream_fake(monkeypatch, get_fake=fake_get)
    app = create_app(settings=Settings(), db_path=str(tmp_path / "test.db"))
    client = TestClient(app, raise_server_exceptions=False)
    return client, app


def _callback(client, pem, subject, monkeypatch, app):
    """Drive login -> callback; return the callback response."""
    captured = {}

    def fake_post(url, **kwargs):
        token = mint_id_token(private_pem=pem, subject=subject, nonce=captured["nonce"])
        return _Resp({"id_token": token, "token_type": "Bearer"})

    install_stream_fake(monkeypatch, post_fake=fake_post)
    r = client.get("/auth/login", follow_redirects=False)
    assert r.status_code == 302, r.text
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    txn = app.state.txn_store.lookup_by_state(state)
    assert txn is not None
    captured["nonce"] = txn.nonce
    return client.get(f"/auth/callback?code=fake-code&state={state}", follow_redirects=False)


# ------------------------------------------------------------------ P1-10


def test_username_string_as_live_subject_denied(monkeypatch, tmp_path):
    """P1-10: a validly signed token whose sub is the fixture username
    "officer_01" (not a UUID) must be UNKNOWN_SUBJECT on the live path
    — fixture names never acquire live portal roles."""
    pem, _ = generate_rsa_keypair()
    client, app = _make_client(monkeypatch, tmp_path, jwks_for(pem))
    r = _callback(client, pem, "officer_01", monkeypatch, app)
    assert r.status_code == 302
    assert "error=UNKNOWN_SUBJECT" in r.headers["location"]
    assert client.get("/api/v1/portal/me").status_code == 401
    assert client.get("/api/v1/portal/officer").status_code == 401


def test_username_student_string_as_live_subject_denied(monkeypatch, tmp_path):
    pem, _ = generate_rsa_keypair()
    client, app = _make_client(monkeypatch, tmp_path, jwks_for(pem))
    r = _callback(client, pem, "student_01", monkeypatch, app)
    assert "error=UNKNOWN_SUBJECT" in r.headers["location"]
    assert client.get("/api/v1/portal/me").status_code == 401


def test_pinned_uuid_subjects_still_authorized(monkeypatch, tmp_path):
    """P1-10: the UUID removal must not break the real subjects."""
    pem, _ = generate_rsa_keypair()
    client, app = _make_client(monkeypatch, tmp_path, jwks_for(pem))
    r = _callback(client, pem, OFFICER_SUB, monkeypatch, app)
    assert "/portal?login=success" in r.headers["location"]
    assert client.get("/api/v1/portal/officer").status_code == 200
    student_client, student_app = _make_client(monkeypatch, tmp_path / "s", jwks_for(pem))
    r = _callback(student_client, pem, STUDENT_SUB, monkeypatch, student_app)
    assert "/portal?login=success" in r.headers["location"]
    assert student_client.get("/api/v1/portal/member").status_code == 200
    assert student_client.get("/api/v1/portal/officer").status_code == 403


# ------------------------------------------------------------------ P1-07


@pytest.mark.parametrize("bad_jwks", [{"keys": None}, {"keys": 42}, {"keys": []}])
def test_malformed_jwks_at_callback_fails_closed(monkeypatch, tmp_path, bad_jwks):
    """P1-07: a fake IdP returning malformed JWKS must produce a
    controlled JWKS_ERROR redirect — no session, no 500/traceback."""
    pem, _ = generate_rsa_keypair()
    client, app = _make_client(monkeypatch, tmp_path, bad_jwks)
    r = _callback(client, pem, STUDENT_SUB, monkeypatch, app)
    assert r.status_code == 302
    assert "error=JWKS_ERROR" in r.headers["location"]
    assert client.get("/api/v1/portal/me").status_code == 401
    assert client.get("/api/v1/portal/member").status_code == 401
