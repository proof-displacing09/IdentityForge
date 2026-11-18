"""Operation Trustline v2: CSRF lifecycle (P0-02), honest scenario
semantics (P0-06), evidence provenance (P1-09), real-login events
(P0-05), and mutation sensitivity (P1-17, via the designed `omit`
mechanism — no source mutation, offline test-only process).

Keycloak is NOT RUN here; live-login events are exercised against the
same fake-IdP stub as test_login_binding.py.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from identityforge.api.app import create_app
from identityforge.config import Settings
from identityforge.protocol.validators import validate_id_token
from identityforge.protocol.validators_flawed import validate_id_token_flawed
from identityforge.scenarios import flawed as flawed_mod
from identityforge.scenarios.engine import run_scenario
from identityforge.scenarios.fixtures import (
    CLIENT_ID,
    EXPECTED_ISSUER,
    generate_rsa_keypair,
    jwks_for,
    mint_id_token,
    roles_for_fixture_subject,
)
from identityforge.security.policy import (
    STUDENT_SUB,
    can_access,
)
from identityforge.security.session import SessionStore
from tests.fake_http import install_stream_fake

# ---------------------------------------------------------------- P0-02 CSRF


def _csrf_headers(client):
    token = client.get("/api/v1/csrf-token").json()["csrf_token"]
    return {"X-CSRF-Token": token}, token


def test_config_get_does_not_set_csrf_cookie(client):
    """P0-02: GET /api/v1/lab/config is a pure read; it must not mint a
    CSRF cookie (the old behaviour silently invalidated the frontend's
    cached token after any Settings navigation)."""
    client.get("/api/v1/csrf-token")
    before = client.cookies.get("identityforge_csrf")
    r = client.get("/api/v1/lab/config")
    assert r.status_code == 200
    assert "identityforge_csrf" not in (r.headers.get("set-cookie") or "")
    assert client.cookies.get("identityforge_csrf") == before


def test_csrf_token_idempotent_per_browser(client):
    """P0-02: the token endpoint returns the browser's existing token
    instead of minting a new one, so a second tab or a re-fetch cannot
    invalidate the token the first tab cached."""
    t1 = client.get("/api/v1/csrf-token").json()["csrf_token"]
    t2 = client.get("/api/v1/csrf-token").json()["csrf_token"]
    assert t1 == t2
    assert client.cookies.get("identityforge_csrf") == t1


def test_csrf_repro_sequence_now_passes(client):
    """P0-02 acceptance repro (directive §01): token -> Settings (config
    GET) -> mutation with the SAME cached header token -> 200. The old
    build returned 403 here because the config GET minted a fresh
    cookie. The mutation used here is logout (session-optional,
    CSRF-required, rotates like reset): lab reset itself is
    officer-only since P0-01 (v3), so it cannot serve as the bare-CSRF
    repro any more. (A reset itself intentionally rotates the token;
    see test_trustline_v3_reset.py.)"""
    headers, token = _csrf_headers(client)
    client.get("/api/v1/lab/config")
    r = client.post("/auth/logout", headers={"X-CSRF-Token": token})
    assert r.status_code == 200


def test_logout_rotates_token_and_hands_fresh_value(client):
    """P0-02: a CSRF-protected mutation rotates the token; the old token
    is then denied and the fresh token (returned in-band) works for the
    next mutation. (Reset rotates the same way; its rotation is covered
    by the officer-reset tests in test_trustline_v3_reset.py.)"""
    headers, old_token = _csrf_headers(client)
    r = client.post("/auth/logout", headers=headers)
    assert r.status_code == 200
    fresh = r.json()["csrf_token"]
    assert fresh and fresh != old_token
    assert client.cookies.get("identityforge_csrf") == fresh
    assert client.post("/auth/logout", headers={"X-CSRF-Token": old_token}).status_code == 403
    assert client.post("/auth/logout", headers={"X-CSRF-Token": fresh}).status_code == 200


def test_csrf_missing_and_hostile_origin_denied(client):
    headers, _ = _csrf_headers(client)
    assert client.post("/auth/logout").status_code == 403
    hostile = dict(headers, Origin="https://evil.example")
    assert client.post("/auth/logout", headers=hostile).status_code == 403
    assert client.post("/auth/logout", headers=headers).status_code == 200


def test_two_tabs_share_one_token(client):
    """P0-02: two tabs (same cookie jar) fetch the same token, and a
    mutation from either tab succeeds."""
    token = client.get("/api/v1/csrf-token").json()["csrf_token"]
    other = TestClient(client.app, raise_server_exceptions=False)
    other.cookies.set("identityforge_csrf", token)
    assert other.get("/api/v1/csrf-token").json()["csrf_token"] == token
    assert other.post("/auth/logout", headers={"X-CSRF-Token": token}).status_code == 200


# ------------------------------------------------------- P0-06 / P1-09


def test_i10_i13_preserve_preexisting_session():
    for sid in ("I10", "I13"):
        res = run_scenario(sid, store=None)
        assert res.status == "PASS", sid
        assert res.session_preexisted is True, sid
        assert res.secure_session_created is False, sid
        assert res.secure_result in ("rejected", "denied"), sid


def test_i12_revocation_recorded():
    res = run_scenario("I12", store=None)
    assert res.status == "PASS"
    assert res.session_revoked is True
    assert res.session_preexisted is True
    assert res.secure_session_created is False
    assert res.flawed_session_created is False
    assert "still valid after logout" in res.flawed_observed_result


def test_i16_i17_i18_create_no_session():
    for sid in ("I16", "I17", "I18"):
        res = run_scenario(sid, store=None)
        assert res.status == "PASS", sid
        assert res.secure_session_created is False, sid
        assert res.flawed_session_created is False, sid
        assert res.flawed_observed_result, sid
    i16 = run_scenario("I16", store=None)
    assert "mutation" in i16.flawed_observed_result
    assert i16.flawed_guard_omitted == "csrf"


def test_i14_flawed_also_rejects_malformed():
    res = run_scenario("I14", store=None)
    assert res.status == "PASS"
    assert res.flawed_result == "rejected"
    assert "malformed" in res.flawed_observed_result


def test_i11_flawed_keeps_known_id_no_new_session():
    res = run_scenario("I11", store=None)
    assert res.status == "PASS"
    assert res.secure_session_created is True
    assert res.flawed_session_created is False
    assert "still valid after login" in res.flawed_observed_result


def test_evidence_saved_only_after_commit(tmp_path):
    """P1-09: run_scenario(store=None) reports evidence_saved=False and
    EPHEMERAL provenance; with a store it reports SAVED with a real DB row."""
    from identityforge.evidence.store import EvidenceStore

    ephemeral = run_scenario("I1", store=None)
    assert ephemeral.evidence_saved is False
    assert ephemeral.evidence_provenance == "EPHEMERAL"
    store = EvidenceStore(str(tmp_path / "ev.db"))
    saved = run_scenario("I1", store=store)
    assert saved.evidence_saved is True
    assert saved.evidence_provenance == "OFFLINE_FIXTURE"
    row = store.get_run(saved.run_id)
    assert row is not None and row["run_id"] == saved.run_id

    # A storage failure is reported, never hidden as saved.
    class _Boom:
        def save_run(self, report):
            raise RuntimeError("disk full")

    failed = run_scenario("I1", store=_Boom())
    assert failed.evidence_saved is False
    assert failed.evidence_error


# ------------------------------------------------- P1-17 mutation sensitivity
# The `omit` mechanism lives ONLY in the offline-only flawed module
# (protocol/validators_flawed.py) since P1-09 (v3); the production
# validator has no omit parameter. These tests prove each negative
# test is sensitive to its check: with the check intact the attack
# input is rejected; with exactly that check omitted (flawed module)
# the same input validates. No source file is mutated.


def _valid_setup(nonce="test-nonce"):
    pem, jwk = generate_rsa_keypair()
    return pem, {"keys": [jwk]}, mint_id_token(private_pem=pem, nonce=nonce)


def test_negative_tests_are_sensitive_to_each_check():
    pem, jwks, token = _valid_setup()
    cases = [
        ("signature", mint_id_token(private_pem=pem, nonce="test-nonce", tamper=True)),
        (
            "issuer",
            mint_id_token(
                private_pem=pem, nonce="test-nonce", issuer="http://127.0.0.1:8080/realms/evil-lab"
            ),
        ),
        (
            "audience",
            mint_id_token(private_pem=pem, nonce="test-nonce", audience="other-synthetic-client"),
        ),
        ("nonce", mint_id_token(private_pem=pem, nonce="different-nonce")),
        ("expiry", mint_id_token(private_pem=pem, nonce="test-nonce", expires_in=-300)),
    ]
    for check, bad_token in cases:
        secure = validate_id_token(
            bad_token,
            jwks=jwks,
            expected_issuer=EXPECTED_ISSUER,
            expected_audience=CLIENT_ID,
            expected_nonce="test-nonce",
        )
        assert secure.valid is False, check
        mutated = validate_id_token_flawed(
            bad_token,
            jwks=jwks,
            expected_issuer=EXPECTED_ISSUER,
            expected_audience=CLIENT_ID,
            expected_nonce="test-nonce",
            omit=frozenset({check}),
        )
        assert mutated.valid is True, f"negative test not sensitive to {check}"
        # The production path has no omit parameter at all: no call
        # site can silently skip a check by forgetting an argument.
        assert (
            validate_id_token(
                bad_token,
                jwks=jwks,
                expected_issuer=EXPECTED_ISSUER,
                expected_audience=CLIENT_ID,
                expected_nonce="test-nonce",
            ).valid
            is False
        )


def test_flawed_fixtures_are_sensitive_to_state_pkce_csrf_policy():
    assert flawed_mod.flawed_skip_state("attacker-state", "real-state") is True
    assert flawed_mod.flawed_skip_pkce("wrong-verifier", "real-challenge") is True
    assert flawed_mod.flawed_skip_csrf() is True
    # Secure counterparts reject the same inputs.
    from identityforge.protocol.pkce import TransactionStore, verify_pkce

    assert verify_pkce("wrong-verifier", "real-challenge") is False
    store = TransactionStore()
    assert store.lookup_by_state("attacker-state") is None
    assert (
        can_access(
            SessionStore().create(
                subject="student_01",
                username="student_01",
                roles=roles_for_fixture_subject("student_01"),
                issuer=EXPECTED_ISSUER,
            ),
            "officer",
        )
        is False
    )
    assert "officer" in flawed_mod.flawed_trust_token_roles(
        {"sub": "student_01", "roles": ["officer"]}
    )


# ------------------------------------------------------------ P0-05 live events


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


def _login(client, pem, subject, monkeypatch, app, tamper=False):
    captured = {}

    def fake_post(url, **kwargs):
        token = mint_id_token(
            private_pem=pem, subject=subject, nonce=captured["nonce"], tamper=tamper
        )
        return _Resp({"id_token": token, "token_type": "Bearer"})

    install_stream_fake(monkeypatch, post_fake=fake_post)
    r = client.get("/auth/login", follow_redirects=False)
    assert r.status_code == 302, r.text
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    txn = app.state.txn_store.lookup_by_state(state)
    assert txn is not None
    captured["nonce"] = txn.nonce
    return state


def test_live_login_events_recorded(fake_idp):
    client, pem, app, monkeypatch = fake_idp
    state = _login(client, pem, STUDENT_SUB, monkeypatch, app)
    r = client.get(f"/auth/callback?code=fake-code&state={state}", follow_redirects=False)
    assert r.status_code == 302 and "/portal?login=success" in r.headers["location"]
    assert client.get("/api/v1/portal/member").status_code == 200
    assert client.get("/api/v1/portal/officer").status_code == 403
    data = client.get("/api/v1/live-logins").json()
    assert data["mode"] == "LIVE_KEYCLOAK"
    assert len(data["logins"]) == 1
    login = data["logins"][0]
    stages = [e["stage"] for e in login["events"]]
    for expected in (
        "AUTH_STARTED",
        "CALLBACK_RECEIVED",
        "BINDING_VERIFIED",
        "TOKEN_ENDPOINT",
        "ID_TOKEN_VALIDATED",
        "SESSION_CREATED",
        "AUTHORIZATION_DECISION",
    ):
        assert expected in stages, stages
    assert all(e["outcome"] in ("ok", "rejected") for e in login["events"])
    # Redaction: no raw code, state, token or Bearer material anywhere.
    blob = repr(login)
    assert "fake-code" not in blob and "Bearer" not in blob
    assert state not in blob
    assert all(e["subject_hash"] for e in login["events"] if e["stage"] == "SESSION_CREATED")
    # Single-login fetch + reload persistence (SQLite-backed).
    one = client.get(f"/api/v1/live-logins/{login['correlation_id']}").json()
    assert one["correlation_id"] == login["correlation_id"]
    assert client.get("/api/v1/live-logins/nope").status_code == 404


def test_live_negative_events_recorded(fake_idp):
    client, pem, app, monkeypatch = fake_idp
    state = _login(client, pem, STUDENT_SUB, monkeypatch, app)
    other = TestClient(app, raise_server_exceptions=False)
    r = other.get(f"/auth/callback?code=fake-code&state={state}", follow_redirects=False)
    assert "error=STATE_BINDING_MISMATCH" in r.headers["location"]
    logins = client.get("/api/v1/live-logins").json()["logins"]
    assert any(
        e["stage"] == "BINDING_VERIFIED" and e["reason_code"] == "STATE_BINDING_MISMATCH"
        for login in logins
        for e in login["events"]
    )


def test_tampered_id_token_via_callback_creates_no_session(fake_idp):
    """P0-07: a tampered signature at the real callback fails closed —
    no session, no protected resource, reason BAD_SIGNATURE."""
    client, pem, app, monkeypatch = fake_idp
    state = _login(client, pem, STUDENT_SUB, monkeypatch, app, tamper=True)
    r = client.get(f"/auth/callback?code=fake-code&state={state}", follow_redirects=False)
    assert r.status_code == 302
    assert "error=BAD_SIGNATURE" in r.headers["location"]
    assert client.get("/api/v1/portal/me").status_code == 401
    assert client.get("/api/v1/portal/member").status_code == 401
    logins = client.get("/api/v1/live-logins").json()["logins"]
    assert any(
        e["stage"] == "ID_TOKEN_VALIDATED" and e["reason_code"] == "BAD_SIGNATURE"
        for login in logins
        for e in login["events"]
    )


def test_live_logout_event_recorded(fake_idp):
    client, pem, app, monkeypatch = fake_idp
    state = _login(client, pem, STUDENT_SUB, monkeypatch, app)
    assert (
        client.get(
            f"/auth/callback?code=fake-code&state={state}", follow_redirects=False
        ).status_code
        == 302
    )
    assert client.get("/api/v1/portal/me").status_code == 200
    headers, _ = _csrf_headers(client)
    r = client.post("/auth/logout", headers=headers)
    assert r.status_code == 200
    assert r.json().get("csrf_token")
    assert client.get("/api/v1/portal/me").status_code == 401
    logins = client.get("/api/v1/live-logins").json()["logins"]
    assert any(e["stage"] == "LOGOUT" for login in logins for e in login["events"])
