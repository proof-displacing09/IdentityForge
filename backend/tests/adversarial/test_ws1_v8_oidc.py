"""WS1 v8 OIDC audit — §5: PKCE, state/nonce, callback, discovery/JWKS,
ID-token validation. Failing-first: each test asserts the secure behaviour.
Local-only fixtures; no real IdP is contacted except the loopback Keycloak
already running for the TestClient login-start tests.
"""

from __future__ import annotations

import base64
import json
import time

import pytest
from fastapi.testclient import TestClient

from identityforge.api.app import create_app
from identityforge.config import Settings
from identityforge.models import FailureReason
from identityforge.protocol.jwks import (
    parse_jwks,
    rewrite_to_transport,
    validate_discovery,
    validate_issuer_url,
    validate_jwks_url,
)
from identityforge.protocol.pkce import (
    TransactionStore,
    TransactionStoreFull,
    code_challenge_s256,
    generate_verifier,
    verify_pkce,
)
from identityforge.protocol.validators import check_audience_policy, validate_id_token
from identityforge.scenarios.fixtures import (
    CLIENT_ID,
    EXPECTED_ISSUER,
    generate_rsa_keypair,
    mint_id_token,
)
from identityforge.security.policy import OFFICER_SUB, STUDENT_SUB
from identityforge.security.session import SESSION_COOKIE


@pytest.fixture()
def app_client(tmp_path):
    app = create_app(settings=Settings(), db_path=str(tmp_path / "t.db"))
    with TestClient(app, raise_server_exceptions=False) as c:
        yield app, c


@pytest.fixture()
def keys():
    pem, jwk = generate_rsa_keypair()
    return pem, {"keys": [jwk]}


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _tamper_payload(token: str, mutate: dict) -> str:
    h, p, s = token.split(".")
    payload = json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))
    payload.update(mutate)
    p2 = _b64u(json.dumps(payload, separators=(",", ":")).encode())
    return f"{h}.{p2}.{s}"


def _reheader(token: str, header: dict) -> str:
    h, p, s = token.split(".")
    h2 = _b64u(json.dumps(header, separators=(",", ":")).encode())
    return f"{h2}.{p}.{s}"


# ---------------------------------------------------------------- §5 PKCE
def test_pkce_verifier_entropy_and_challenge():
    vs = {generate_verifier() for _ in range(200)}
    assert len(vs) == 200  # no collisions in 200 draws
    for v in vs:
        assert 43 <= len(v) <= 128
        assert all(c.isalnum() or c in "-_" for c in v)
        assert len(v) == 43  # 32 bytes -> 43 chars
        assert verify_pkce(v, code_challenge_s256(v))
        assert not verify_pkce(v, code_challenge_s256(generate_verifier()))
        assert not verify_pkce("", code_challenge_s256(v))
        assert not verify_pkce(v, "")
        assert not verify_pkce(v + "x", code_challenge_s256(v))
    # No 'plain' challenge method exists anywhere in the protocol module:
    # only the S256 construction is defined, and /auth/login hard-codes S256.
    import inspect

    import identityforge.protocol.pkce as pkce_mod

    src = inspect.getsource(pkce_mod)
    assert '"plain"' not in src and "'plain'" not in src
    assert "code_challenge_method" not in src or "S256" in src


def test_transaction_store_quotas_and_expiry():
    store = TransactionStore(ttl_seconds=600)
    txns = [
        store.create(
            redirect_uri="http://127.0.0.1:8000/auth/callback",
            client_id="c",
            issuer="i",
            browser_key_hash="b1",
        )
        for _ in range(4)
    ]
    assert len(store) == 4
    # 5th for the SAME browser evicts only that browser's oldest.
    t5 = store.create(
        redirect_uri="http://127.0.0.1:8000/auth/callback",
        client_id="c",
        issuer="i",
        browser_key_hash="b1",
    )
    assert len(store) == 4
    assert store.lookup_by_state(txns[0].state) is None
    assert store.lookup_by_state(t5.state) is not None
    # Another browser's transactions are untouched by b1's churn.
    other = store.create(
        redirect_uri="http://127.0.0.1:8000/auth/callback",
        client_id="c",
        issuer="i",
        browser_key_hash="b2",
    )
    assert store.lookup_by_state(other.state) is not None
    # Global cap: 20 distinct browsers -> 21st refused, never evicts others.
    store2 = TransactionStore(ttl_seconds=600)
    for i in range(20):
        store2.create(redirect_uri="u", client_id="c", issuer="i", browser_key_hash=f"browser-{i}")
    with pytest.raises(TransactionStoreFull):
        store2.create(redirect_uri="u", client_id="c", issuer="i", browser_key_hash="browser-21")
    assert len(store2) == 20


def test_transaction_expiry_and_consume_once():
    store = TransactionStore(ttl_seconds=0)  # immediate expiry
    txn, tok = store.create_bound(redirect_uri="u", client_id="c", issuer="i", browser_key_hash="b")
    assert store.lookup_by_state(txn.state) is None  # expired on access
    store = TransactionStore(ttl_seconds=600)
    txn, tok = store.create_bound(redirect_uri="u", client_id="c", issuer="i", browser_key_hash="b")
    assert store.consume_by_state(txn.state, tok) is not None
    assert store.consume_by_state(txn.state, tok) is None  # replay: gone
    assert store.consume_by_state(txn.state, "wrong") is None


def test_binding_mismatch_does_not_consume():
    store = TransactionStore(ttl_seconds=600)
    txn, tok = store.create_bound(redirect_uri="u", client_id="c", issuer="i", browser_key_hash="b")
    assert store.consume_by_state(txn.state, "wrong-token") is None
    assert store.lookup_by_state(txn.state) is not None  # still alive for the real browser
    assert store.consume_by_state(txn.state, tok) is not None


# ---------------------------------------------------------------- §5 ID-token validation
def test_valid_token_accepted_and_tampered_rejected(keys):
    pem, jwks = keys
    good = mint_id_token(private_pem=pem, subject=STUDENT_SUB, nonce="n1")
    d = validate_id_token(
        good,
        jwks=jwks,
        expected_issuer=EXPECTED_ISSUER,
        expected_audience=CLIENT_ID,
        expected_nonce="n1",
    )
    assert d.valid and d.subject == STUDENT_SUB
    # Tampered payload (signature must fail) — including role-escalation claims.
    for mutate in (
        {"sub": OFFICER_SUB},
        {"roles": ["officer"]},
        {"iss": "http://evil.example"},
        {"aud": "other-client"},
        {"nonce": "other"},
        {"exp": 9999999999},
        {"sub": "student_01"},
        {"preferred_username": "officer_01"},
    ):
        bad = _tamper_payload(good, mutate)
        d = validate_id_token(
            bad,
            jwks=jwks,
            expected_issuer=EXPECTED_ISSUER,
            expected_audience=CLIENT_ID,
            expected_nonce="n1",
        )
        assert not d.valid, mutate
    # Tampered header
    for hdr in (
        {"alg": "none", "typ": "JWT"},
        {"alg": "HS256", "typ": "JWT"},
        {"alg": "RS256", "typ": "JWT", "kid": "unknown-kid"},
        {"alg": "RS256", "typ": "JWT"},  # no kid
        {"alg": "RS256", "typ": "JWT", "kid": "x", "jku": "http://evil.example/jwks"},
        {"alg": "RS256", "typ": "JWT", "kid": "x", "x5u": "http://evil.example/cert"},
    ):
        bad = _reheader(good, hdr)
        d = validate_id_token(
            bad,
            jwks=jwks,
            expected_issuer=EXPECTED_ISSUER,
            expected_audience=CLIENT_ID,
            expected_nonce="n1",
        )
        assert not d.valid, hdr
    # Malformed shapes
    for bad in (
        "",
        "a.b",
        "a.b.c.d",
        "....",
        "x" * 9000,
        "a..c",
        "é.é.é",
        good + ".extra",
        good[:-5],
    ):
        d = validate_id_token(
            bad,
            jwks=jwks,
            expected_issuer=EXPECTED_ISSUER,
            expected_audience=CLIENT_ID,
            expected_nonce="n1",
        )
        assert not d.valid, bad[:20]


def test_token_signed_with_wrong_key_rejected(keys):
    pem, jwks = keys
    pem2, _ = generate_rsa_keypair()
    bad = mint_id_token(private_pem=pem2, subject=STUDENT_SUB, nonce="n1")
    d = validate_id_token(
        bad,
        jwks=jwks,
        expected_issuer=EXPECTED_ISSUER,
        expected_audience=CLIENT_ID,
        expected_nonce="n1",
    )
    assert not d.valid and d.reason_code == FailureReason.BAD_SIGNATURE


def test_token_time_boundaries(keys):
    pem, jwks = keys
    now = int(time.time())
    # Expired long ago
    t = mint_id_token(private_pem=pem, subject=STUDENT_SUB, nonce="n1", expires_in=-1000)
    assert not validate_id_token(
        t,
        jwks=jwks,
        expected_issuer=EXPECTED_ISSUER,
        expected_audience=CLIENT_ID,
        expected_nonce="n1",
    ).valid
    # exp 60s in the past is inside the 120s clock skew -> accepted.
    t = mint_id_token(private_pem=pem, subject=STUDENT_SUB, nonce="n1", expires_in=-60)
    assert validate_id_token(
        t,
        jwks=jwks,
        expected_issuer=EXPECTED_ISSUER,
        expected_audience=CLIENT_ID,
        expected_nonce="n1",
    ).valid
    # exp 1000s in the past is beyond skew -> rejected.
    t = mint_id_token(private_pem=pem, subject=STUDENT_SUB, nonce="n1", expires_in=-1000)
    assert not validate_id_token(
        t,
        jwks=jwks,
        expected_issuer=EXPECTED_ISSUER,
        expected_audience=CLIENT_ID,
        expected_nonce="n1",
    ).valid
    # nbf 1000s in the future is beyond skew -> rejected.
    t = mint_id_token(
        private_pem=pem, subject=STUDENT_SUB, nonce="n1", extra_claims={"nbf": now + 1000}
    )
    assert not validate_id_token(
        t,
        jwks=jwks,
        expected_issuer=EXPECTED_ISSUER,
        expected_audience=CLIENT_ID,
        expected_nonce="n1",
    ).valid
    # Empty subject -> rejected.
    t = mint_id_token(private_pem=pem, subject="", nonce="n1")
    assert not validate_id_token(
        t,
        jwks=jwks,
        expected_issuer=EXPECTED_ISSUER,
        expected_audience=CLIENT_ID,
        expected_nonce="n1",
    ).valid


def test_audience_policy_strict():
    assert check_audience_policy(CLIENT_ID, None, CLIENT_ID) is None
    assert check_audience_policy([CLIENT_ID, CLIENT_ID], None, CLIENT_ID) is not None  # dup
    assert check_audience_policy([CLIENT_ID, "other"], CLIENT_ID, CLIENT_ID) is not None
    assert check_audience_policy([CLIENT_ID, CLIENT_ID], CLIENT_ID, CLIENT_ID) is not None
    assert check_audience_policy(CLIENT_ID, "other", CLIENT_ID) is not None
    assert check_audience_policy([], None, CLIENT_ID) is not None
    assert check_audience_policy(None, None, CLIENT_ID) is not None
    assert check_audience_policy(123, None, CLIENT_ID) is not None
    assert check_audience_policy("", None, CLIENT_ID) is not None
    assert check_audience_policy([CLIENT_ID], CLIENT_ID, CLIENT_ID) is None  # single aud + azp ok


def test_hs256_token_with_rsa_key_as_hmac_rejected(keys):
    """Algorithm confusion: an HS256 token (signed with a symmetric
    secret) must be rejected — the validator allows RS256 only."""
    pem, jwks = keys
    token = mint_id_token(private_pem=pem, subject=STUDENT_SUB, nonce="n1", algorithm="HS256")
    d = validate_id_token(
        token,
        jwks=jwks,
        expected_issuer=EXPECTED_ISSUER,
        expected_audience=CLIENT_ID,
        expected_nonce="n1",
    )
    assert not d.valid and d.reason_code == FailureReason.ALG_NOT_ALLOWED


def test_none_alg_token_rejected(keys):
    pem, jwks = keys
    now = int(time.time())
    payload = {
        "iss": EXPECTED_ISSUER,
        "aud": CLIENT_ID,
        "sub": OFFICER_SUB,
        "nonce": "n1",
        "exp": now + 600,
        "iat": now,
    }
    p = _b64u(json.dumps(payload, separators=(",", ":")).encode())
    h = _b64u(json.dumps({"alg": "none", "typ": "JWT"}, separators=(",", ":")).encode())
    token = f"{h}.{p}."
    d = validate_id_token(
        token,
        jwks=jwks,
        expected_issuer=EXPECTED_ISSUER,
        expected_audience=CLIENT_ID,
        expected_nonce="n1",
    )
    assert not d.valid


# ---------------------------------------------------------------- §5 JWKS / discovery
def test_parse_jwks_enc_key_skipped_still_holds(keys):
    pem, jwks = keys
    sig = jwks["keys"][0]
    enc = dict(sig, kid="enc-key-1", use="enc", alg="RSA-OAEP")
    doc = {"keys": [enc, sig]}
    out = parse_jwks(doc)
    assert list(out) == [sig["kid"]]
    # Enc-only document fails closed.
    with pytest.raises(ValueError):
        parse_jwks({"keys": [enc]})


def test_parse_jwks_adversarial():
    pem, jwk = generate_rsa_keypair()
    good = {"keys": [jwk]}
    assert parse_jwks(good)
    bad_docs = [
        None,
        "x",
        [],
        {"keys": "notalist"},
        {"keys": []},
        {"keys": [None]},
        {"keys": [{"kty": "RSA"}]},  # no kid/n/e
        {"keys": [dict(jwk, kid="")]},
        {"keys": [dict(jwk, kid="x" * 200)]},
        {"keys": [dict(jwk, n="!!!")]},
        {"keys": [dict(jwk, n="")]},
        {"keys": [dict(jwk, e="!!!")]},
        {"keys": [jwk, jwk]},  # duplicate kid
        {"keys": [dict(jwk, kid="k2"), dict(jwk, kid="k2")]},
        {"keys": [dict(jwk, kty="EC", kid="ec1")]},  # no usable RSA sig key
        {"keys": [dict(jwk, use="enc")]},  # non-signing only
        {"keys": [dict(jwk, alg="RS384")]},  # wrong alg only
        {"keys": [jwk] * 11},  # too many keys
        {"keys": [{"kty": "RSA", "kid": "big", "n": "A" * 5000, "e": "AQAB"}]},
    ]
    for doc in bad_docs:
        with pytest.raises((ValueError, TypeError)):
            parse_jwks(doc)  # type: ignore[arg-type]
    # Oversized document rejected.
    big = {"keys": [dict(jwk, extra="x" * 70000)]}
    with pytest.raises(ValueError):
        parse_jwks(big)
    # Already-parsed form with mismatched map kid rejected.
    with pytest.raises(ValueError):
        parse_jwks({"other-kid": jwk})


def test_validate_issuer_and_discovery_adversarial():
    allowed = (EXPECTED_ISSUER,)
    assert validate_issuer_url(EXPECTED_ISSUER, allowed) == FailureReason.OK
    bad = [
        "",
        "http://evil.example/realms/identityforge-lab",
        "http://127.0.0.1:8080/realms/other",
        "http://127.0.0.1:8080/realms/identityforge-lab?x=1",
        "http://127.0.0.1:8080/realms/identityforge-lab#frag",
        "http://127.0.0.1:8080@evil.example/realms/identityforge-lab",
        "http://keycloak:8080/realms/identityforge-lab",  # transport host, never issuer
        "http://169.254.169.254/latest/meta-data/",
        "http://127.0.0.1:8080/realms/identityforge-lab/metadata",
        "https://127.0.0.1:8080/realms/identityforge-lab",  # scheme differs from pinned
        "http://127.0.0.1:8081/realms/identityforge-lab",
        "http://[::1]:8080/realms/identityforge-lab",
        "http://localhost:8080/realms/identityforge-lab",
        "http://127.0.0.1:8080/REALMS/identityforge-lab",
        "ftp://127.0.0.1:8080/realms/identityforge-lab",
        "x" * 3000,
        "http://0x7f.0.0.1:8080/realms/identityforge-lab",
        "http://0177.0.0.1:8080/realms/identityforge-lab",
    ]
    for url in bad:
        assert validate_issuer_url(url, allowed) != FailureReason.OK, url
    # IF-V8-01 (failing-first): a trailing slash was tolerated by the
    # old rstrip("/") comparison; the "exact" check is now exact.
    assert validate_issuer_url(EXPECTED_ISSUER + "/", allowed) != FailureReason.OK
    # Discovery validation: exact issuer + exact pinned endpoints.
    base = EXPECTED_ISSUER
    good_disc = {
        "issuer": base,
        "authorization_endpoint": f"{base}/protocol/openid-connect/auth",
        "token_endpoint": f"{base}/protocol/openid-connect/token",
        "jwks_uri": f"{base}/protocol/openid-connect/certs",
    }
    assert validate_discovery(good_disc, canonical_issuer=base)
    for mutated in (
        dict(good_disc, issuer="http://evil.example"),
        dict(good_disc, token_endpoint=f"{base}/protocol/openid-connect/token?x=1"),
        dict(
            good_disc,
            jwks_uri="http://keycloak:8080/realms/identityforge-lab/protocol/openid-connect/certs",
        ),
        dict(
            good_disc,
            authorization_endpoint="http://127.0.0.1:8080/realms/other/protocol/openid-connect/auth",
        ),
        {k: v for k, v in good_disc.items() if k != "jwks_uri"},
        dict(good_disc, token_endpoint=123),
    ):
        with pytest.raises(ValueError):
            validate_discovery(mutated, canonical_issuer=base)
    # Transport rewrite: evil hosts / wrong ports / wrong paths rejected.
    for bad_url in (
        "https://evil.example/realms/identityforge-lab/protocol/openid-connect/token",
        "http://127.0.0.1:9999/realms/identityforge-lab/protocol/openid-connect/token",
        "http://127.0.0.1:8080/other/protocol/openid-connect/token",
        "http://user:pass@127.0.0.1:8080/realms/identityforge-lab/protocol/openid-connect/token",
        "http://127.0.0.1:8080/realms/identityforge-lab/protocol/openid-connect/token?next=http://evil.example",
        # IF-V8-03 (failing-first): the old code preserved this query
        # onto the transport URL instead of rejecting it.
        "http://127.0.0.1:8080/realms/identityforge-lab/protocol/openid-connect/token#frag",
    ):
        with pytest.raises(ValueError):
            rewrite_to_transport(bad_url, "http://127.0.0.1:8080")
    with pytest.raises(ValueError):
        rewrite_to_transport(f"{base}/protocol/openid-connect/token", "http://evil.example:8080")
    with pytest.raises(ValueError):
        rewrite_to_transport(
            f"{base}/protocol/openid-connect/token", "http://127.0.0.1:8080/extra/path"
        )


def test_jwks_url_ssrf_guard():
    assert validate_jwks_url(f"{EXPECTED_ISSUER}/protocol/openid-connect/certs") == FailureReason.OK
    for bad in (
        "http://169.254.169.254/latest/meta-data/",
        "http://evil.example/certs",
        "http://keycloak:8080/realms/identityforge-lab/protocol/openid-connect/certs",
        "http://user:pass@127.0.0.1:8080/certs",
        "ftp://127.0.0.1:8080/certs",
        "http://127.0.0.1:8080/realms/identityforge-lab/metadata",
    ):
        assert validate_jwks_url(bad) != FailureReason.OK, bad


# ---------------------------------------------------------------- §5 callback behaviour (TestClient, real discovery)
# live_keycloak (v8.0.2, IF-V8.0.2-B): the four tests in this section
# call GET /auth/login, which fetches OIDC discovery from the live
# loopback Keycloak (127.0.0.1:8080). With no provider they fail with
# 503 PROVIDER_UNAVAILABLE — a missing-provider failure, not a product
# failure — so they are marked and EXCLUDED from the offline selection
# (`pytest -m "not live_keycloak"`: the default CI backend lane,
# test-all.sh --offline and verify-release BACKEND_PYTEST). They run
# in the full profile only: test-all.sh --full gate LIVE_PROVIDER_PYTEST,
# against the cold-started disposable Keycloak, and in the CI
# keycloak-e2e lane (test-all.sh --full --strict). Never delete, skip
# silently, or stub these tests: they are the only pytest coverage of
# callback replay / cross-browser binding / login rate-limit /
# browser-cookie behaviour against a real provider.
def _start_login(c: TestClient):
    """GET /auth/login against the live loopback Keycloak; return (state, binding cookie)."""
    r = c.get("/auth/login", follow_redirects=False)
    assert r.status_code == 302, (r.status_code, r.text[:200])
    loc = r.headers["location"]
    assert loc.startswith(
        "http://127.0.0.1:8080/realms/identityforge-lab/protocol/openid-connect/auth?"
    )
    assert "code_challenge_method=S256" in loc
    assert "code_challenge=" in loc
    from urllib.parse import parse_qs, urlparse

    q = parse_qs(urlparse(loc).query)
    state = q["state"][0]
    assert len(q["code_challenge"][0]) == 43
    return state, q


@pytest.mark.live_keycloak
def test_callback_replay_and_cross_browser_and_errors(app_client):
    app, c = app_client

    def fresh_login():
        with TestClient(app, raise_server_exceptions=False) as cc:
            state, _q = _start_login(cc)
            # Copy the jar state we need: binding cookie + browser cookie.
            binding = cc.cookies.get(f"identityforge_txn_{state}")
            browser = cc.cookies.get("identityforge_browser")
            return state, binding, browser

    # No binding cookie at all -> denied, transaction NOT consumed.
    state, _b, _br = fresh_login()
    with TestClient(app, raise_server_exceptions=False) as cc:
        r = cc.get(f"/auth/callback?state={state}&code=fake-code-1", follow_redirects=False)
        assert r.status_code == 302 and "STATE_BINDING_MISMATCH" in r.headers["location"]
    assert app.state.txn_store.lookup_by_state(state) is not None
    # Wrong binding cookie -> denied, transaction NOT consumed.
    with TestClient(app, raise_server_exceptions=False) as cc:
        cc.cookies.set(f"identityforge_txn_{state}", "wrong-binding-token")
        r = cc.get(f"/auth/callback?state={state}&code=fake-code-1", follow_redirects=False)
        assert "STATE_BINDING_MISMATCH" in r.headers["location"]
    assert app.state.txn_store.lookup_by_state(state) is not None
    # Duplicate state/code params -> rejected, not consumed.
    with TestClient(app, raise_server_exceptions=False) as cc:
        r = cc.get(f"/auth/callback?state={state}&state={state}&code=x", follow_redirects=False)
        assert "CALLBACK_MALFORMED" in r.headers["location"]
    assert app.state.txn_store.lookup_by_state(state) is not None
    # Missing code -> rejected, not consumed.
    with TestClient(app, raise_server_exceptions=False) as cc:
        r = cc.get(f"/auth/callback?state={state}", follow_redirects=False)
        assert "CALLBACK_MALFORMED" in r.headers["location"]
    assert app.state.txn_store.lookup_by_state(state) is not None
    # Missing state -> rejected.
    with TestClient(app, raise_server_exceptions=False) as cc:
        r = cc.get("/auth/callback?code=x", follow_redirects=False)
        assert "STATE_MISSING" in r.headers["location"]
    # Provider error with a live state must NOT consume the transaction.
    with TestClient(app, raise_server_exceptions=False) as cc:
        r = cc.get(f"/auth/callback?state={state}&error=access_denied", follow_redirects=False)
        assert "PROVIDER_ERROR" in r.headers["location"]
    assert app.state.txn_store.lookup_by_state(state) is not None
    # Unknown state -> STATE_REUSED, no session.
    with TestClient(app, raise_server_exceptions=False) as cc:
        r = cc.get("/auth/callback?state=nonexistentstate123&code=x", follow_redirects=False)
        assert "STATE_REUSED" in r.headers["location"]
        assert SESSION_COOKIE not in r.headers.get("set-cookie", "")


@pytest.mark.live_keycloak
def test_callback_replay_after_consume(app_client, monkeypatch, keys):
    """Once a transaction is consumed (here by a fault-injected token
    exchange), a second callback with the same state is denied and mints
    no session. The token exchange is fixture-injected: the real
    Keycloak is used only for discovery/login-start, never for a forged
    token — the injected token is signed by a throwaway key and must be
    rejected by the real validator, proving an invalid ID token never
    creates a session."""
    import identityforge.api.app as app_mod

    app, c = app_client
    pem, jwks = keys
    state, _q = _start_login(c)
    binding = c.cookies.get(f"identityforge_txn_{state}")
    assert binding

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "id_token": mint_id_token(private_pem=pem, subject=STUDENT_SUB, nonce="WRONG-NONCE")
            }

    monkeypatch.setattr(app_mod, "post_token_via_transport", lambda *a, **k: FakeResp())
    monkeypatch.setattr(app_mod, "fetch_jwks_via_transport", lambda *a, **k: jwks)
    # Correct binding + consumed transaction, but the token's nonce is wrong
    # (and its issuer/audience are fixture values) -> rejected, no session.
    r = c.get(f"/auth/callback?state={state}&code=code-1", follow_redirects=False)
    assert r.status_code == 302
    assert "login=success" not in r.headers["location"], r.headers["location"]
    assert SESSION_COOKIE not in r.headers.get("set-cookie", "")
    assert app.state.txn_store.lookup_by_state(state) is None  # consumed exactly once
    # Replay of the same callback -> STATE_REUSED, still no session.
    r2 = c.get(f"/auth/callback?state={state}&code=code-1", follow_redirects=False)
    assert "STATE_REUSED" in r2.headers["location"]
    assert SESSION_COOKIE not in r2.headers.get("set-cookie", "")


@pytest.mark.live_keycloak
def test_login_start_rate_limit(app_client):
    app, c = app_client
    codes = []
    for _ in range(35):
        r = c.get("/auth/login", follow_redirects=False)
        codes.append(r.status_code)
    assert 429 in codes, codes
    assert codes.count(302) <= 30
    # A fresh browser key gets its own per-browser bucket but the global
    # bucket (120/min) still bounds total starts.
    with TestClient(app, raise_server_exceptions=False) as c2:
        r = c2.get("/auth/login", follow_redirects=False)
        assert r.status_code in (302, 429)


@pytest.mark.live_keycloak
def test_login_start_sets_browser_cookie_and_s256(app_client):
    app, c = app_client
    r = c.get("/auth/login", follow_redirects=False)
    assert r.status_code == 302
    set_cookie = r.headers.get("set-cookie", "")
    assert "identityforge_browser=" in set_cookie
    assert "httponly" in set_cookie.lower()
    # Second start reuses the browser key (no new cookie minted).
    r2 = c.get("/auth/login", follow_redirects=False)
    assert r2.status_code == 302
    assert "identityforge_browser=" not in r2.headers.get("set-cookie", "")
