"""Operation Trustline v3 — P1-17 backend negative matrix (gap coverage).

Every test names the exact security property it proves. Only cases
MISSING from the existing suite are added here; coverage that already
existed is listed in the P1-17 gap report (see the delivery notes)
and is NOT duplicated — e.g. alg=none, tampered signature, bad kid,
wrong iss/aud, expired token and nonce mismatch live in
unit/test_validators.py; state mismatch and duplicate callback live
in integration/test_api.py and the P1-06 multitab tests; the
login-503-when-IdP-down case lives in integration/test_api.py.

All tests are OFFLINE (fake IdP stub or pure unit calls) unless a
test says otherwise; none of them is claimed as proof against a live
Keycloak server. Keycloak is NOT RUN here.
"""

from __future__ import annotations

import base64
import time
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from identityforge.api.app import create_app
from identityforge.config import Settings
from identityforge.models import FailureReason
from identityforge.protocol.jwks import (
    fetch_jwks,
    rewrite_to_transport,
    validate_discovery,
    validate_issuer_url,
    validate_jwks_url,
)
from identityforge.protocol.pkce import code_challenge_s256
from identityforge.protocol.validators import validate_id_token
from identityforge.scenarios.fixtures import (
    CLIENT_ID,
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
    """Fake IdP + app; returns (client, pem, app, verifier_map).

    The token endpoint mirrors a real IdP: an unknown code or a
    verifier that does not match the transaction's challenge is
    rejected 400 invalid_grant (never minted). verifier_map maps
    code_verifier -> {"subject", "nonce", "challenge", "extra_claims"}.
    """
    pem, _ = generate_rsa_keypair()
    jwks = jwks_for(pem)
    discovery = {
        "issuer": EXPECTED_ISSUER,
        "authorization_endpoint": EXPECTED_ISSUER + "/protocol/openid-connect/auth",
        "token_endpoint": EXPECTED_ISSUER + "/protocol/openid-connect/token",
        "jwks_uri": EXPECTED_ISSUER + "/protocol/openid-connect/certs",
    }
    verifier_map: dict[str, dict] = {}

    def fake_get(url, **kwargs):
        if "openid-configuration" in url:
            return _Resp(discovery)
        if url.endswith("/certs"):
            return _Resp(jwks)
        raise AssertionError(f"unexpected GET {url}")

    def fake_post(url, **kwargs):
        assert url.endswith("/protocol/openid-connect/token"), url
        data = kwargs.get("data", {})
        if data.get("code") != "fake-code":
            return _Resp({"error": "invalid_grant"}, 400)
        entry = verifier_map.get(data.get("code_verifier", ""))
        if entry is None or code_challenge_s256(data["code_verifier"]) != entry["challenge"]:
            return _Resp(
                {"error": "invalid_grant", "error_description": "PKCE verification failed"}, 400
            )
        token = mint_id_token(
            private_pem=pem,
            subject=entry["subject"],
            nonce=entry["nonce"],
            extra_claims=entry["extra_claims"],
        )
        return _Resp({"id_token": token, "token_type": "Bearer"})

    install_stream_fake(monkeypatch, get_fake=fake_get)
    install_stream_fake(monkeypatch, post_fake=fake_post)
    app = create_app(settings=Settings(), db_path=str(tmp_path / "test.db"))
    client = TestClient(app, raise_server_exceptions=False)
    return client, pem, app, verifier_map


def _start_login(client, app, verifier_map, subject, extra_claims=None):
    """Start a login; returns the state."""
    r = client.get("/auth/login", follow_redirects=False)
    assert r.status_code == 302, r.text
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    txn = app.state.txn_store.lookup_by_state(state)
    assert txn is not None
    verifier_map[txn.code_verifier] = {
        "subject": subject,
        "nonce": txn.nonce,
        "challenge": txn.code_challenge,
        "extra_claims": extra_claims,
    }
    return state


def _callback(client, state, code="fake-code"):
    return client.get(f"/auth/callback?code={code}&state={state}", follow_redirects=False)


def _login_as(client, pem, subject, app, verifier_map, extra_claims=None):
    state = _start_login(client, app, verifier_map, subject, extra_claims)
    r = _callback(client, state)
    assert r.status_code == 302 and "/portal?login=success" in r.headers["location"], r.headers
    assert client.get("/api/v1/portal/me").status_code == 200
    return state


def _csrf_headers(client):
    return {"X-CSRF-Token": client.get("/api/v1/csrf-token").json()["csrf_token"]}


# ------------------------------------------------------- ID token (unit)


def test_not_yet_valid_token_rejected(keys):
    """Property: a token whose nbf is in the future cannot be used
    early — the validator enforces not-before within bounded skew,
    so a prematurely presented token grants no session."""
    pem, jwks = keys
    token = mint_id_token(private_pem=pem, extra_claims={"nbf": int(time.time()) + 600})
    dec = validate_id_token(
        token,
        jwks=jwks,
        expected_issuer=EXPECTED_ISSUER,
        expected_audience=CLIENT_ID,
        expected_nonce="test-nonce",
    )
    assert dec.valid is False
    assert dec.reason_code == FailureReason.NOT_YET_VALID


def test_header_without_alg_rejected(keys):
    """Property: a JWT header with no alg at all is rejected — the
    validator requires alg == RS256 explicitly, never defaults to an
    algorithm (or to none) when the header omits it."""
    _, jwks = keys
    header = base64.urlsafe_b64encode(b'{"typ":"JWT"}').rstrip(b"=").decode()
    token = f"{header}.AAAA.BBBB"
    dec = validate_id_token(
        token,
        jwks=jwks,
        expected_issuer=EXPECTED_ISSUER,
        expected_audience=CLIENT_ID,
        expected_nonce="test-nonce",
    )
    assert dec.valid is False
    assert dec.reason_code == FailureReason.ALG_NOT_ALLOWED


def test_malformed_header_segment_rejected(keys):
    """Property: a header segment that is not valid base64url JSON
    fails closed as MALFORMED_TOKEN — no partial parse, no session."""
    _, jwks = keys
    dec = validate_id_token(
        "!!!.AAAA.BBBB",
        jwks=jwks,
        expected_issuer=EXPECTED_ISSUER,
        expected_audience=CLIENT_ID,
        expected_nonce="test-nonce",
    )
    assert dec.valid is False
    assert dec.reason_code == FailureReason.MALFORMED_TOKEN


# ------------------------------------------------------- flow (fake IdP)


def test_wrong_pkce_verifier_rejected_and_code_burned(fake_idp):
    """Property: a wrong PKCE verifier cannot redeem the code, and the
    failed exchange consumes the transaction — a second callback with
    the same state is STATE_REUSED (mirrors the measured Keycloak
    code-burn: a failed exchange never leaves a redeemable code)."""
    client, pem, app, vmap = fake_idp
    state = _start_login(client, app, vmap, STUDENT_SUB)
    txn = app.state.txn_store.lookup_by_state(state)
    assert txn is not None
    txn.code_verifier = "wrong-verifier-that-matches-no-challenge"
    r = _callback(client, state)
    assert r.status_code == 302
    assert "error=PROVIDER_ERROR" in r.headers["location"], r.headers
    assert client.get("/api/v1/portal/me").status_code == 401
    r = _callback(client, state)
    assert "error=STATE_REUSED" in r.headers["location"], r.headers


def test_unregistered_redirect_uri_rejected(fake_idp, tmp_path):
    """Property: a login whose redirect_uri is not on the allowlist
    cannot complete — the callback checks the transaction's redirect
    URI against the allowlist AFTER binding verification, so an
    attacker-registered or misconfigured redirect never yields a
    session even with a valid code and token."""
    client, pem, app, vmap = fake_idp
    evil = create_app(
        settings=Settings(redirect_uri="http://127.0.0.1:8000/auth/evil-callback"),
        db_path=str(tmp_path / "evil.db"),
    )
    evil_client = TestClient(evil, raise_server_exceptions=False)
    state = _start_login(evil_client, evil, vmap, STUDENT_SUB)
    r = _callback(evil_client, state)
    assert r.status_code == 302
    assert "error=REDIRECT_URI_MISMATCH" in r.headers["location"], r.headers
    assert evil_client.get("/api/v1/portal/me").status_code == 401


def test_forged_role_claim_cannot_promote_student(fake_idp):
    """Property: token role claims are NEVER trusted — a token for the
    student subject carrying forged officer roles (roles claim and
    realm_access) still logs in as member-only; the officer resource
    stays 403. Roles come only from the server-side (issuer, sub)
    policy map."""
    client, pem, app, vmap = fake_idp
    forged = {"roles": ["officer"], "realm_access": {"roles": ["officer"]}}
    _login_as(client, pem, STUDENT_SUB, app, vmap, extra_claims=forged)
    me = client.get("/api/v1/portal/me").json()
    assert me["username"] == "student_01"
    assert me["roles"] == ["member"]
    assert client.get("/api/v1/portal/member").status_code == 200
    assert client.get("/api/v1/portal/officer").status_code == 403


def test_expired_session_denied_at_portal(fake_idp, tmp_path):
    """Property: an expired session grants nothing — a login against
    an app whose sessions expire immediately still completes the
    callback (the IdP validated the token), but every protected
    resource then returns 401."""
    client, pem, app, vmap = fake_idp
    app2 = create_app(settings=Settings(session_ttl_seconds=-1), db_path=str(tmp_path / "t2.db"))
    client2 = TestClient(app2, raise_server_exceptions=False)
    state = _start_login(client2, app2, vmap, OFFICER_SUB)
    # The fixture's fake token endpoint is shared (monkeypatched
    # httpx.post), so app2's transaction must be registered in the
    # same verifier map for the token exchange to mint.
    r = _callback(client2, state)
    assert r.status_code == 302 and "/portal?login=success" in r.headers["location"], r.headers
    assert client2.get("/api/v1/portal/me").status_code == 401
    assert client2.get("/api/v1/portal/member").status_code == 401
    assert client2.get("/api/v1/portal/officer").status_code == 401


def test_revoked_session_post_logout_401(fake_idp):
    """Property: logout revokes immediately and the old session id
    can never be resurrected — after logout, /portal/me, /member and
    /officer all return 401 (revocation is checked on every request,
    not just at login)."""
    client, pem, app, vmap = fake_idp
    _login_as(client, pem, OFFICER_SUB, app, vmap)
    assert client.get("/api/v1/portal/officer").status_code == 200
    r = client.post("/auth/logout", headers=_csrf_headers(client))
    assert r.status_code == 200, r.text
    assert client.get("/api/v1/portal/me").status_code == 401
    assert client.get("/api/v1/portal/member").status_code == 401
    assert client.get("/api/v1/portal/officer").status_code == 401


# ------------------------------------------------------- SSRF (unit)


def test_jwks_url_with_userinfo_blocked():
    """Property: a JWKS URL carrying userinfo is refused before any
    network call — userinfo can disguise the real host (credentialed
    loopback vs external host), so it is never allowed in a fetched
    metadata URL."""
    for url in (
        "http://user:pass@127.0.0.1:8080/realms/identityforge-lab/protocol/openid-connect/certs",
        "http://127.0.0.1@evil.example/jwks.json",
        "http://attacker:secret@127.0.0.1:8080/certs",
    ):
        assert validate_jwks_url(url) == FailureReason.SSRF_BLOCKED, url


def test_issuer_url_with_userinfo_rejected():
    """Property: an issuer URL carrying userinfo is never accepted —
    the allowlist comparison is exact, so a userinfo-disguised issuer
    fails closed (UNTRUSTED_ISSUER_URL, not OK)."""
    url = "http://user@127.0.0.1:8080/realms/identityforge-lab"
    assert validate_issuer_url(url, (EXPECTED_ISSUER,)) != FailureReason.OK


def test_transport_rewrite_rejects_userinfo_external_and_non_realm():
    """Property: the backend-to-Keycloak transport rewrite only ever
    changes scheme/host/port to an allowlisted transport host for
    realm paths — userinfo, an external host, or a non-realm path in
    either side raises instead of producing a fetchable URL."""
    good = f"{EXPECTED_ISSUER}/protocol/openid-connect/token"
    assert rewrite_to_transport(good, "http://127.0.0.1:8080") == (
        "http://127.0.0.1:8080/realms/identityforge-lab/protocol/openid-connect/token"
    )
    for bad_url, bad_base in (
        (
            "http://user@127.0.0.1:8080/realms/identityforge-lab/protocol/openid-connect/token",
            "http://127.0.0.1:8080",
        ),
        (good, "http://user@127.0.0.1:8080"),
        (
            "https://evil.example/realms/identityforge-lab/protocol/openid-connect/token",
            "http://127.0.0.1:8080",
        ),
        (good, "http://evil.example:8080"),
        ("http://127.0.0.1:8080/other/path", "http://127.0.0.1:8080"),
        (good, "http://127.0.0.1:9999"),
    ):
        with pytest.raises(ValueError):
            rewrite_to_transport(bad_url, bad_base)


def test_discovery_rejects_external_endpoints():
    """Property: discovery metadata is never trusted at face value —
    endpoints pointing at an external host (a redirect-style attack
    on the token/JWKS fetch) are rejected, because endpoints must
    equal the pinned canonical URLs exactly."""
    base = {
        "issuer": EXPECTED_ISSUER,
        "authorization_endpoint": EXPECTED_ISSUER + "/protocol/openid-connect/auth",
        "token_endpoint": EXPECTED_ISSUER + "/protocol/openid-connect/token",
        "jwks_uri": EXPECTED_ISSUER + "/protocol/openid-connect/certs",
    }
    for key in ("token_endpoint", "jwks_uri", "authorization_endpoint"):
        bad = dict(base)
        bad[key] = "https://evil.example" + bad[key][len(EXPECTED_ISSUER) :]
        with pytest.raises(ValueError):
            validate_discovery(bad, canonical_issuer=EXPECTED_ISSUER)
    bad_issuer = dict(base, issuer="https://evil.example/realms/identityforge-lab")
    with pytest.raises(ValueError):
        validate_discovery(bad_issuer, canonical_issuer=EXPECTED_ISSUER)


def test_fetch_jwks_does_not_follow_redirects(monkeypatch):
    """Property: a JWKS fetch never follows a redirect to an external
    host — the fetch uses follow_redirects=False, so a 302 response
    fails closed instead of fetching attacker-controlled key material
    from the redirect target."""
    calls = []

    class _Redirect:
        status_code = 302

        def raise_for_status(self):
            return None  # 3xx does not raise; the JSON parse must fail

        def json(self):
            raise ValueError("no JSON in a redirect body")

    def fake_get(url, **kwargs):
        calls.append(url)
        assert kwargs.get("follow_redirects") is False
        return _Redirect()

    install_stream_fake(monkeypatch, get_fake=fake_get)
    with pytest.raises(ValueError):
        fetch_jwks("http://127.0.0.1:8080/realms/identityforge-lab/protocol/openid-connect/certs")
    assert len(calls) == 1  # exactly one request; the redirect was NOT followed


# ------------------------------------------------------- input (API)


def test_run_malicious_json_variants_rejected(client):
    """Property: hostile run-request bodies cannot create evidence —
    nested garbage, a non-string scenario id and an overlong id are
    all 400, and no run is recorded for any of them."""
    headers = _csrf_headers(client)
    bodies = (
        '{"scenario_id": {"nested": "garbage"}}',
        '{"scenario_id": ["I1"]}',
        '{"scenario_id": "' + "I" * 3000 + '"}',
        '{"scenario_id": "' + "x" * 100_000 + '"}',
    )
    for body in bodies:
        r = client.post("/api/v1/runs", content=body, headers=headers)
        assert r.status_code == 400, body[:60]
    assert client.get("/api/v1/lab/counts").json()["runs"] == 0


def test_callback_overlong_state_rejected(fake_idp):
    """Property: an overlong state value cannot match (or collide
    with) a real transaction — it fails closed as STATE_REUSED and
    creates no session."""
    client, pem, app, vmap = fake_idp
    r = _callback(client, "s" * 5000)
    assert r.status_code == 302
    assert "error=STATE_REUSED" in r.headers["location"], r.headers
    assert client.get("/api/v1/portal/me").status_code == 401


def test_callback_overlong_code_rejected(fake_idp):
    """Property: a garbage overlong code cannot mint a session — the
    token endpoint rejects an unknown code (mirroring a real IdP),
    the callback fails PROVIDER_ERROR, and the transaction is
    consumed so the code cannot be retried."""
    client, pem, app, vmap = fake_idp
    state = _start_login(client, app, vmap, STUDENT_SUB)
    r = _callback(client, state, code="c" * 5000)
    assert r.status_code == 302
    assert "error=PROVIDER_ERROR" in r.headers["location"], r.headers
    assert client.get("/api/v1/portal/me").status_code == 401
    r = _callback(client, state)
    assert "error=STATE_REUSED" in r.headers["location"], r.headers


def test_rate_limit_boundary_30_ok_31st_429(client):
    """Property: the runs endpoint enforces MAX_RUNS_PER_MINUTE=30
    per client — the 30th run in a minute succeeds and the 31st is
    429 rate_limited, so one client cannot flood the evidence store
    (and the limit is a real boundary, not an off-by-one)."""
    headers = _csrf_headers(client)
    for i in range(30):
        r = client.post("/api/v1/runs", json={"scenario_id": "I6"}, headers=headers)
        assert r.status_code == 200, f"run {i + 1}: {r.text}"
    r = client.post("/api/v1/runs", json={"scenario_id": "I6"}, headers=headers)
    assert r.status_code == 429
    assert r.json()["detail"] == "rate_limited"
    assert client.get("/api/v1/lab/counts").json()["runs"] == 30


# ------------------------------------------------------- health / IdP


def test_lab_status_fake_200_wrong_issuer_reports_unreachable(client, monkeypatch):
    """Property: a provider that answers 200 with the WRONG issuer is
    not 'reachable' — lab/status reports idp.reachable False with the
    failure class recorded, so the doctor/readiness path cannot go
    green on a fake-200 impostor (cf. P0-05)."""

    def fake_get(url, **kwargs):
        return _Resp(
            {
                "issuer": "https://evil.example/realms/identityforge-lab",
                "authorization_endpoint": "https://evil.example/auth",
                "token_endpoint": "https://evil.example/token",
                "jwks_uri": "https://evil.example/certs",
            }
        )

    install_stream_fake(monkeypatch, get_fake=fake_get)
    status = client.get("/api/v1/lab/status").json()
    assert status["idp"]["reachable"] is False
    assert status["idp"]["issuer_matches"] is None
    assert status["idp"]["reason"] == "ValueError"
    assert status["last_verified_login"] is None


def test_lab_status_fake_200_non_object_reports_unreachable(client, monkeypatch):
    """Property: a provider that answers 200 with non-object JSON is
    not 'reachable' either — discovery must be a valid object with
    the pinned issuer, anything else is recorded as a failure."""

    def fake_get(url, **kwargs):
        return _Resp(["not", "a", "discovery", "object"])

    install_stream_fake(monkeypatch, get_fake=fake_get)
    status = client.get("/api/v1/lab/status").json()
    assert status["idp"]["reachable"] is False
    assert status["idp"]["reason"] == "ValueError"
    assert status["last_verified_login"] is None
