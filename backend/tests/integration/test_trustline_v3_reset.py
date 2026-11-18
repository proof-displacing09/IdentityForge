"""Operation Trustline v3 — P0-01 authenticated officer-only lab reset
and P1-11 live-event save-failure surfacing.

Reset policy (v3, see api/app.py): a destructive reset requires ALL of
  (a) a valid, unexpired, unrevoked live session with the OFFICER role,
  (b) a valid CSRF token,
  (c) a confirmation body {"confirm": "RESET_LAB"}.
Check order is CSRF, session, role, confirmation; no writes happen
before authorization succeeds. The officer's own session IS invalidated
by the clear. Keycloak is NOT RUN here; logins use the fake-IdP stub.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from identityforge.api.app import create_app
from identityforge.config import Settings
from identityforge.evidence.store import EvidenceStore
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


def _login(client, pem, subject, monkeypatch, app):
    """Drive login -> callback with the fake IdP; returns the state."""
    from urllib.parse import parse_qs, urlparse

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
    return state


def _login_as(client, pem, subject, monkeypatch, app):
    state = _login(client, pem, subject, monkeypatch, app)
    r = client.get(f"/auth/callback?code=fake-code&state={state}", follow_redirects=False)
    assert r.status_code == 302 and "/portal?login=success" in r.headers["location"], r.headers
    assert client.get("/api/v1/portal/me").status_code == 200


def _csrf_headers(client):
    token = client.get("/api/v1/csrf-token").json()["csrf_token"]
    return {"X-CSRF-Token": token}, token


def _reset_body(client, headers, body):
    return client.post("/api/v1/lab/reset", json=body, headers=headers)


def _create_run(client):
    headers, _ = _csrf_headers(client)
    r = client.post("/api/v1/runs", json={"scenario_id": "I6"}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["run_id"]


# ------------------------------------------------------------------ P0-01


def test_two_client_proof_unauthenticated_reset_denied(fake_idp):
    """P0-01 repro: client B (no session, own CSRF token) must not wipe
    client A's evidence."""
    client_a, pem, app, monkeypatch = fake_idp
    run_id = _create_run(client_a)
    client_b = TestClient(app, raise_server_exceptions=False)
    # No CSRF at all -> 403 (CSRF is checked first).
    assert client_b.post("/api/v1/lab/reset", json={"confirm": "RESET_LAB"}).status_code == 403
    # Own CSRF token + confirmation, but NO session -> 401, not 200.
    headers_b, _ = _csrf_headers(client_b)
    r = client_b.post("/api/v1/lab/reset", json={"confirm": "RESET_LAB"}, headers=headers_b)
    assert r.status_code == 401
    assert r.json()["detail"] == "unauthenticated"
    # A's evidence survives.
    assert client_a.get(f"/api/v1/runs/{run_id}").status_code == 200


def test_student_reset_denied_and_evidence_survives(fake_idp):
    client_a, pem, app, monkeypatch = fake_idp
    run_id = _create_run(client_a)
    student = TestClient(app, raise_server_exceptions=False)
    _login_as(student, pem, STUDENT_SUB, monkeypatch, app)
    assert student.get("/api/v1/portal/officer").status_code == 403
    headers, _ = _csrf_headers(student)
    r = _reset_body(student, headers, {"confirm": "RESET_LAB"})
    assert r.status_code == 403
    assert r.json()["detail"] == "policy_denied"
    assert client_a.get(f"/api/v1/runs/{run_id}").status_code == 200
    assert student.get("/api/v1/portal/me").status_code == 200  # student session untouched


def test_officer_reset_succeeds_counts_and_revokes_own_session(fake_idp):
    client_a, pem, app, monkeypatch = fake_idp
    run_id = _create_run(client_a)
    officer = TestClient(app, raise_server_exceptions=False)
    _login_as(officer, pem, OFFICER_SUB, monkeypatch, app)
    before = officer.get("/api/v1/lab/counts").json()
    # IF-V4-03/IF-V4-11 (v5): sessions is ACTIVE only, and the counts
    # now carry the separate process-lifetime total plus the storage
    # budget (1 I6 run stores exactly 1 timeline event).
    assert before == {
        "runs": 1,
        "sessions": 1,
        "sessions_total_issued": 1,
        # IF-V5-02 (v6): 6 saved EVENT rows from 1 login transaction
        # (1 successful login), not 6 logins.
        # IF-V6-02 (v7): the login is a complete canonical sequence,
        # so it is a VERIFIED success (observed 1, successful 1) and
        # no transaction is incomplete.
        "live_login_events": 6,
        "live_login_transactions": 1,
        "live_login_session_created_observed": 1,
        "live_login_successful_transactions": 1,
        "live_login_incomplete_transactions": 0,
        "live_login_event_limit": 1000,
        "live_logins": 6,
        "transactions": 0,
        "events": 1,
        "runs_limit": 1000,
        "events_limit": 20000,
        "live_logins_limit": 1000,
    }
    headers, old_token = _csrf_headers(officer)
    r = _reset_body(officer, headers, {"confirm": "RESET_LAB"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "reset"
    assert body["operator"] == "officer_01"
    assert body["cleared"] == before
    assert body["operator_session_revoked"] is True
    fresh = body["csrf_token"]
    assert fresh and fresh != old_token
    assert officer.cookies.get("identityforge_csrf") == fresh
    # A's evidence is gone; the officer's own session is revoked.
    assert client_a.get(f"/api/v1/runs/{run_id}").status_code == 404
    assert officer.get("/api/v1/portal/me").status_code == 401
    assert officer.get("/api/v1/lab/counts").json() == {
        "runs": 0,
        "sessions": 0,
        # sessions_total_issued is process-lifetime by design (like
        # the evidence-health counters): the reset clears stored
        # sessions, it does not rewind how many were ever minted.
        "sessions_total_issued": 1,
        "live_login_events": 0,
        "live_login_transactions": 0,
        "live_login_session_created_observed": 0,
        "live_login_successful_transactions": 0,
        "live_login_incomplete_transactions": 0,
        "live_login_event_limit": 1000,
        "live_logins": 0,
        "transactions": 0,
        "events": 0,
        "runs_limit": 1000,
        "events_limit": 20000,
        "live_logins_limit": 1000,
    }
    # The fresh in-band token works for the next mutation (logout).
    assert officer.post("/auth/logout", headers={"X-CSRF-Token": fresh}).status_code == 200


def test_officer_reset_evidence_failure_aborts_before_sessions(fake_idp, monkeypatch):
    """P0-01 two-stage deletion: if the evidence clear raises, reset
    aborts with 500 and sessions (including the officer's) are NOT
    cleared — a half-cleared lab is worse than a failed reset."""
    client_a, pem, app, mp = fake_idp
    run_id = _create_run(client_a)
    officer = TestClient(app, raise_server_exceptions=False)
    _login_as(officer, pem, OFFICER_SUB, mp, app)
    real_clear = app.state.evidence.clear

    def _boom():
        raise RuntimeError("disk full")

    monkeypatch.setattr(app.state.evidence, "clear", _boom)
    headers, _ = _csrf_headers(officer)
    r = _reset_body(officer, headers, {"confirm": "RESET_LAB"})
    assert r.status_code == 500
    assert r.json()["detail"] == "reset_failed"
    monkeypatch.setattr(app.state.evidence, "clear", real_clear)
    # Nothing was cleared: evidence and sessions both survive.
    assert client_a.get(f"/api/v1/runs/{run_id}").status_code == 200
    assert officer.get("/api/v1/portal/me").status_code == 200


def test_officer_reset_missing_or_wrong_confirm_422(fake_idp):
    client_a, pem, app, monkeypatch = fake_idp
    run_id = _create_run(client_a)
    officer = TestClient(app, raise_server_exceptions=False)
    _login_as(officer, pem, OFFICER_SUB, monkeypatch, app)
    headers, _ = _csrf_headers(officer)
    for body in (None, {}, {"confirm": "yes"}, {"confirm": "RESET"}, {"confirm": 123}):
        if body is None:
            r = officer.post("/api/v1/lab/reset", headers=headers)
        else:
            r = _reset_body(officer, headers, body)
        assert r.status_code == 422, body
        assert r.json()["detail"] == "invalid_confirmation"
    # Invalid JSON and non-dict JSON are 422 too.
    r = officer.post("/api/v1/lab/reset", content="{not json", headers=headers)
    assert r.status_code == 422
    r = officer.post("/api/v1/lab/reset", content='["RESET_LAB"]', headers=headers)
    assert r.status_code == 422
    # Nothing was cleared by any denied attempt.
    assert client_a.get(f"/api/v1/runs/{run_id}").status_code == 200
    assert officer.get("/api/v1/portal/me").status_code == 200


def test_officer_reset_stale_or_cross_site_csrf_denied(fake_idp):
    client_a, pem, app, monkeypatch = fake_idp
    run_id = _create_run(client_a)
    officer = TestClient(app, raise_server_exceptions=False)
    _login_as(officer, pem, OFFICER_SUB, monkeypatch, app)
    headers, token = _csrf_headers(officer)
    # Wrong Origin.
    assert (
        _reset_body(officer, dict(headers, Origin="https://evil.example"), {"confirm": "RESET_LAB"})
    ).status_code == 403
    # Mismatched header token (cookie holds the real token).
    assert (
        _reset_body(officer, {"X-CSRF-Token": "wrong-token"}, {"confirm": "RESET_LAB"})
    ).status_code == 403
    # Missing header token.
    assert officer.post("/api/v1/lab/reset", json={"confirm": "RESET_LAB"}).status_code == 403
    # Truly stale token: logout rotates the cookie; log back in, then
    # replay the pre-logout header token against the new cookie.
    assert officer.post("/auth/logout", headers=headers).status_code == 200
    _login_as(officer, pem, OFFICER_SUB, monkeypatch, app)
    r = _reset_body(officer, {"X-CSRF-Token": token}, {"confirm": "RESET_LAB"})
    assert r.status_code == 403
    assert r.json()["detail"] == "csrf_denied"
    # Evidence survives every denied attempt.
    assert client_a.get(f"/api/v1/runs/{run_id}").status_code == 200
    assert officer.get("/api/v1/portal/me").status_code == 200


def test_expired_or_revoked_session_reset_denied_401(fake_idp, monkeypatch, tmp_path):
    # Revoked: logout, then reset with a fresh valid CSRF token -> 401.
    client, pem, app, mp = fake_idp
    _login_as(client, pem, OFFICER_SUB, mp, app)
    headers, _ = _csrf_headers(client)
    assert client.post("/auth/logout", headers=headers).status_code == 200
    headers, _ = _csrf_headers(client)
    r = _reset_body(client, headers, {"confirm": "RESET_LAB"})
    assert r.status_code == 401
    assert r.json()["detail"] == "unauthenticated"
    # Expired: a second app whose sessions expire immediately.
    pem2, _ = generate_rsa_keypair()
    jwks2 = jwks_for(pem2)
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
            return _Resp(jwks2)
        raise AssertionError(f"unexpected GET {url}")

    install_stream_fake(monkeypatch, get_fake=fake_get)
    app2 = create_app(settings=Settings(session_ttl_seconds=-1), db_path=str(tmp_path / "test2.db"))
    client2 = TestClient(app2, raise_server_exceptions=False)
    # The callback itself still succeeds (the IdP validated the token),
    # but the minted session is already expired.
    state2 = _login(client2, pem2, OFFICER_SUB, monkeypatch, app2)
    r = client2.get(f"/auth/callback?code=fake-code&state={state2}", follow_redirects=False)
    assert r.status_code == 302 and "/portal?login=success" in r.headers["location"]
    assert client2.get("/api/v1/portal/me").status_code == 401
    headers2, _ = _csrf_headers(client2)
    r = _reset_body(client2, headers2, {"confirm": "RESET_LAB"})
    assert r.status_code == 401
    assert r.json()["detail"] == "unauthenticated"


def test_lab_counts_is_read_only_metadata(fake_idp):
    client, pem, app, monkeypatch = fake_idp
    assert client.get("/api/v1/lab/counts").json() == {
        "runs": 0,
        "sessions": 0,
        "sessions_total_issued": 0,
        "live_login_events": 0,
        "live_login_transactions": 0,
        "live_login_session_created_observed": 0,
        "live_login_successful_transactions": 0,
        "live_login_incomplete_transactions": 0,
        "live_login_event_limit": 1000,
        "live_logins": 0,
        "transactions": 0,
        "events": 0,
        "runs_limit": 1000,
        "events_limit": 20000,
        "live_logins_limit": 1000,
    }
    _create_run(client)
    counts = client.get("/api/v1/lab/counts").json()
    assert counts["runs"] == 1
    assert counts["sessions"] == 0


# ------------------------------------------------------------------ P1-11


def _assert_evidence_failure_surfaced(client, *, live_logins_readable=True):
    """Login still works, but lab/status reports the save failures and
    does not claim a complete timeline."""
    status = client.get("/api/v1/lab/status").json()
    evidence = status["evidence"]
    assert evidence["event_save_errors"] > 0, evidence
    assert evidence["events_saved"] == 0, evidence
    assert evidence["evidence_available"] is False
    assert "partial_timeline_reason" in evidence
    assert "incomplete" in evidence["partial_timeline_reason"]
    if live_logins_readable:
        # No timeline was actually saved, so the Atlas shows nothing.
        assert client.get("/api/v1/live-logins").json()["logins"] == []
    else:
        # The read itself cannot execute against the corrupt schema:
        # it must fail closed (500), never return a fabricated timeline.
        assert client.get("/api/v1/live-logins").status_code == 500


def test_event_save_failure_readonly_db(fake_idp, monkeypatch):
    """Evidence DB read-only: login succeeds, failures are counted.

    Implemented with SQLite ``PRAGMA query_only`` on the store
    connection: this sandbox runs as root, and root bypasses POSIX
    file permissions, so chmod 0444 alone does NOT make writes fail
    here. ``query_only`` produces the identical failure mode a real
    read-only file gives — ``OperationalError: attempt to write a
    readonly database`` — at the SQLite layer.
    """
    client, pem, app, mp = fake_idp
    app.state.evidence._conn.execute("PRAGMA query_only = ON")  # noqa: SLF001
    _login_as(client, pem, STUDENT_SUB, mp, app)
    assert client.get("/api/v1/portal/member").status_code == 200
    _assert_evidence_failure_surfaced(client)


def test_event_save_failure_locked_db(fake_idp, monkeypatch):
    """Evidence DB locked by another connection: login succeeds, the
    blocked saves are counted (busy timeout kept short so the test
    does not wait out SQLite's 5 s default per event)."""
    client, pem, app, mp = fake_idp
    db_path = str(app.state.evidence._path)  # noqa: SLF001  (test introspection)
    locker = sqlite3.connect(db_path)
    locker.execute("BEGIN EXCLUSIVE")
    locker.execute(
        "INSERT INTO runs (run_id, scenario_id, status, mode, secure_result,"
        " flawed_result, report_json, report_sha256, created_at)"
        " VALUES ('lock', 'I1', 'PASS', 'x', 'x', 'x', '{}', 'x', 'x')"
    )
    app.state.evidence._conn.execute("PRAGMA busy_timeout = 200")  # noqa: SLF001
    try:
        _login_as(client, pem, STUDENT_SUB, mp, app)
        assert client.get("/api/v1/portal/member").status_code == 200
    finally:
        # Release the lock BEFORE asserting: while it is held, even
        # read endpoints (list_live_logins) block on busy_timeout and
        # 500 — pre-existing behaviour, out of scope here. The save
        # counters persist on app.state regardless.
        locker.rollback()
        locker.close()
    _assert_evidence_failure_surfaced(client)


def test_event_save_failure_corrupt_schema(fake_idp, monkeypatch, tmp_path):
    """live_login_events table replaced with an incompatible schema:
    login succeeds, failures are counted, no partial rows appear."""
    db_path = tmp_path / "corrupt.db"
    store = EvidenceStore(str(db_path))
    # Replace the table with one missing the `at` column: the store's
    # CREATE TABLE IF NOT EXISTS is then a no-op (the table exists) and
    # the CREATE INDEX on correlation_id still succeeds, but every
    # INSERT fails — no partial row can ever be written.
    store._conn.execute("DROP TABLE live_login_events")  # noqa: SLF001
    store._conn.execute(
        "CREATE TABLE live_login_events ("
        "id INTEGER PRIMARY KEY, correlation_id TEXT NOT NULL,"
        " stage TEXT NOT NULL, outcome TEXT NOT NULL,"
        " reason_code TEXT NOT NULL DEFAULT 'OK',"
        " subject_hash TEXT NOT NULL DEFAULT '',"
        " username TEXT NOT NULL DEFAULT '',"
        " detail TEXT NOT NULL DEFAULT '')"
    )
    store._conn.commit()
    store.close()
    app = create_app(settings=Settings(), db_path=str(db_path))
    client = TestClient(app, raise_server_exceptions=False)
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
    _login_as(client, pem, STUDENT_SUB, monkeypatch, app)
    assert client.get("/api/v1/portal/member").status_code == 200
    _assert_evidence_failure_surfaced(client, live_logins_readable=False)
