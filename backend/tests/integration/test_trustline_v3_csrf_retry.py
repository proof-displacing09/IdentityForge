"""Operation Trustline v3 — P1-12 CSRF-retry safeguards (backend half).

Safety invariant under test: a mutation rejected 403 for CSRF is
rejected BEFORE any server-side write, so the frontend's retry-once
after a token refresh can never double-execute a destructive action.
The frontend half (retry exactly once on csrf_denied only; never on
policy_denied / 401 / network failure) is in frontend/src/api.test.ts.

Keycloak is NOT RUN here; logins use the fake-IdP stub.
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
    """Fake IdP + app; returns (client, pem, app, monkeypatch)."""
    pem, _ = generate_rsa_keypair()
    jwks = jwks_for(pem)
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
    return client, pem, app, monkeypatch


def _login_as(client, pem, subject, monkeypatch, app):
    captured = {}

    def fake_post(url, **kwargs):
        token = mint_id_token(private_pem=pem, subject=subject, nonce=captured["nonce"])
        return _Resp({"id_token": token, "token_type": "Bearer"})

    install_stream_fake(monkeypatch, post_fake=fake_post)
    r = client.get("/auth/login", follow_redirects=False)
    assert r.status_code == 302, r.text
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    captured["nonce"] = app.state.txn_store.lookup_by_state(state).nonce
    r = client.get(f"/auth/callback?code=fake-code&state={state}", follow_redirects=False)
    assert r.status_code == 302 and "/portal?login=success" in r.headers["location"], r.headers
    assert client.get("/api/v1/portal/me").status_code == 200


def _csrf_headers(client):
    token = client.get("/api/v1/csrf-token").json()["csrf_token"]
    return {"X-CSRF-Token": token}


def _create_run(client):
    r = client.post("/api/v1/runs", json={"scenario_id": "I6"}, headers=_csrf_headers(client))
    assert r.status_code == 200, r.text
    return r.json()["run_id"]


# ------------------------------------------------------------------ P1-12


def test_reset_wrong_csrf_writes_nothing(fake_idp):
    """P1-12 (a): officer reset with a WRONG CSRF token is 403
    csrf_denied and the evidence is untouched — the retry the client
    performs afterwards cannot double-execute, because the first
    attempt never wrote anything."""
    client, pem, app, mp = fake_idp
    run_id = _create_run(client)
    officer = TestClient(app, raise_server_exceptions=False)
    _login_as(officer, pem, OFFICER_SUB, mp, app)
    r = officer.post(
        "/api/v1/lab/reset",
        json={"confirm": "RESET_LAB"},
        headers={"X-CSRF-Token": "wrong-token"},
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "csrf_denied"
    assert client.get(f"/api/v1/runs/{run_id}").status_code == 200
    assert officer.get("/api/v1/portal/me").status_code == 200
    assert officer.get("/api/v1/lab/counts").json()["runs"] == 1


def test_logout_wrong_csrf_keeps_session(fake_idp):
    """P1-12 (b): logout with a WRONG CSRF token is 403 csrf_denied
    and the session stays valid — a retried logout cannot revoke a
    session the first attempt already revoked (it revoked nothing)."""
    client, pem, app, mp = fake_idp
    _login_as(client, pem, STUDENT_SUB, mp, app)
    r = client.post("/auth/logout", headers={"X-CSRF-Token": "wrong-token"})
    assert r.status_code == 403
    assert r.json()["detail"] == "csrf_denied"
    assert client.get("/api/v1/portal/me").status_code == 200
    assert client.get("/api/v1/portal/member").status_code == 200


def test_run_wrong_csrf_creates_nothing(fake_idp):
    """P1-12 (c): POST /runs with a WRONG CSRF token is 403
    csrf_denied and no run is created — the retried request is the
    only execution."""
    client, pem, app, mp = fake_idp
    r = client.post(
        "/api/v1/runs", json={"scenario_id": "I6"}, headers={"X-CSRF-Token": "wrong-token"}
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "csrf_denied"
    assert client.get("/api/v1/lab/counts").json()["runs"] == 0


def test_reset_denied_403s_have_distinct_details(fake_idp):
    """P1-12 (d/e) backend support: the client must be able to tell a
    retryable CSRF denial from a non-retryable one. Reset returns
    csrf_denied for a bad token, policy_denied for a student, and
    401 unauthenticated with no session — three distinct signals, so
    the client retries exactly the first and never the others."""
    client, pem, app, mp = fake_idp
    run_id = _create_run(client)
    # No session, valid CSRF -> 401 (never retried by the client).
    r = client.post(
        "/api/v1/lab/reset", json={"confirm": "RESET_LAB"}, headers=_csrf_headers(client)
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "unauthenticated"
    # Student, valid CSRF -> 403 policy_denied (never retried).
    student = TestClient(app, raise_server_exceptions=False)
    _login_as(student, pem, STUDENT_SUB, mp, app)
    r = student.post(
        "/api/v1/lab/reset", json={"confirm": "RESET_LAB"}, headers=_csrf_headers(student)
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "policy_denied"
    # Officer, bad CSRF -> 403 csrf_denied (the only retryable one).
    officer = TestClient(app, raise_server_exceptions=False)
    _login_as(officer, pem, OFFICER_SUB, mp, app)
    r = officer.post(
        "/api/v1/lab/reset",
        json={"confirm": "RESET_LAB"},
        headers={"X-CSRF-Token": "wrong-token"},
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "csrf_denied"
    # Nothing was cleared by any denied attempt.
    assert client.get(f"/api/v1/runs/{run_id}").status_code == 200
