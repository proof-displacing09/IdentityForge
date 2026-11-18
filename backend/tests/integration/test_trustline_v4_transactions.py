"""Operation Trustline v4 — P1-10/P1-11 per-browser transaction quotas
and auth-start rate limiting.

The v3 global cap (5 live transactions, 6th evicts the globally
oldest) let one unauthenticated local client force ANOTHER browser's
waiting login into STATE_REUSED (measured). The v4 design: per-browser
quota 4 (eviction only within the same browser), global safety cap 20
(refuse new starts instead of evicting), anonymous browser key
correlation (SHA-256 only, never the raw value), and /auth/login rate
limits (30/min per browser key, 120/min global).

Keycloak is NOT RUN here; logins use the fake-IdP stub.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from identityforge.api.app import (
    MAX_LOGIN_STARTS_GLOBAL_PER_MINUTE,
    MAX_LOGIN_STARTS_PER_BROWSER_PER_MINUTE,
    create_app,
)
from identityforge.config import Settings
from identityforge.protocol.pkce import (
    BROWSER_COOKIE,
    MAX_LIVE_TRANSACTIONS_GLOBAL,
    MAX_LIVE_TRANSACTIONS_PER_BROWSER,
    TransactionStore,
    TransactionStoreFull,
    browser_key_hash,
    generate_browser_key,
)
from identityforge.scenarios.fixtures import (
    EXPECTED_ISSUER,
    generate_rsa_keypair,
    jwks_for,
    mint_id_token,
)
from identityforge.security.policy import STUDENT_SUB
from tests.fake_http import install_stream_fake

LOGIN = "http://127.0.0.1:8000/auth/callback"


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
    verifier_map: dict[str, tuple[str, str]] = {}

    def fake_get(url, **kwargs):
        if "openid-configuration" in url:
            return _Resp(discovery)
        if url.endswith("/certs"):
            return _Resp(jwks)
        raise AssertionError(f"unexpected GET {url}")

    def fake_post(url, **kwargs):
        data = kwargs.get("data", {})
        subject, nonce = verifier_map[data["code_verifier"]]
        return _Resp({"id_token": mint_id_token(private_pem=pem, subject=subject, nonce=nonce)})

    install_stream_fake(monkeypatch, get_fake=fake_get)
    install_stream_fake(monkeypatch, post_fake=fake_post)
    app = create_app(settings=Settings(), db_path=str(tmp_path / "test.db"))
    client = TestClient(app, raise_server_exceptions=False)
    return client, app, verifier_map


def _start_login(client, app, verifier_map, subject=STUDENT_SUB):
    r = client.get("/auth/login", follow_redirects=False)
    assert r.status_code == 302, r.text
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    txn = app.state.txn_store.lookup_by_state(state)
    assert txn is not None
    verifier_map[txn.code_verifier] = (subject, txn.nonce)
    return state


def _callback(client, state):
    return client.get(f"/auth/callback?code=fake-code&state={state}", follow_redirects=False)


# ------------------------------------------------------------- store-level


def test_six_starts_from_one_actor_evict_only_own_oldest():
    """P1-10: six starts from ONE browser evict only that browser's own
    two oldest; nothing else in the store is touched."""
    store = TransactionStore()
    key_a = browser_key_hash(generate_browser_key())
    key_b = browser_key_hash(generate_browser_key())
    other = store.create_bound(
        redirect_uri=LOGIN,
        client_id="campus-club-portal",
        issuer=EXPECTED_ISSUER,
        browser_key_hash=key_b,
    )[0]
    states = []
    for _ in range(6):
        txn, _ = store.create_bound(
            redirect_uri=LOGIN,
            client_id="campus-club-portal",
            issuer=EXPECTED_ISSUER,
            browser_key_hash=key_a,
        )
        states.append(txn.state)
    assert len(store) == MAX_LIVE_TRANSACTIONS_PER_BROWSER + 1  # 4 of A + 1 of B
    assert store.lookup_by_state(states[0]) is None  # A's oldest evicted
    assert store.lookup_by_state(states[1]) is None  # A's 2nd oldest evicted
    for state in states[2:]:
        assert store.lookup_by_state(state) is not None
    assert store.lookup_by_state(other.state) is not None  # B untouched


def test_second_browser_unaffected_by_first_browser_saturation():
    """P1-10: browser B's transaction survives browser A saturating its
    own quota, and still completes (consumes) normally."""
    store = TransactionStore()
    key_a = browser_key_hash(generate_browser_key())
    key_b = browser_key_hash(generate_browser_key())
    txn_b, token_b = store.create_bound(
        redirect_uri=LOGIN,
        client_id="campus-club-portal",
        issuer=EXPECTED_ISSUER,
        browser_key_hash=key_b,
    )
    for _ in range(6):
        store.create_bound(
            redirect_uri=LOGIN,
            client_id="campus-club-portal",
            issuer=EXPECTED_ISSUER,
            browser_key_hash=key_a,
        )
    assert store.lookup_by_state(txn_b.state) is not None
    consumed = store.consume_by_state(txn_b.state, token_b)
    assert consumed is not None and consumed.state == txn_b.state


def test_global_cap_refuses_instead_of_evicting():
    """P1-10: at the global cap (20 across distinct browsers), a new
    start raises TransactionStoreFull and every live transaction
    survives — no cross-browser eviction, ever."""
    store = TransactionStore()
    keys = [browser_key_hash(generate_browser_key()) for _ in range(5)]
    states = []
    for key in keys:
        for _ in range(MAX_LIVE_TRANSACTIONS_PER_BROWSER):
            txn, _ = store.create_bound(
                redirect_uri=LOGIN,
                client_id="campus-club-portal",
                issuer=EXPECTED_ISSUER,
                browser_key_hash=key,
            )
            states.append(txn.state)
    assert len(store) == MAX_LIVE_TRANSACTIONS_GLOBAL == 20
    with pytest.raises(TransactionStoreFull):
        store.create_bound(
            redirect_uri=LOGIN,
            client_id="campus-club-portal",
            issuer=EXPECTED_ISSUER,
            browser_key_hash=browser_key_hash(generate_browser_key()),
        )
    assert len(store) == 20
    for state in states:
        assert store.lookup_by_state(state) is not None


def test_expired_transactions_do_not_count_toward_quota():
    """Expiry still frees quota: expired entries are purged on access,
    so a browser with 4 expired transactions can start 4 fresh ones
    with no live eviction."""
    store = TransactionStore()
    key = browser_key_hash(generate_browser_key())
    for _ in range(MAX_LIVE_TRANSACTIONS_PER_BROWSER):
        txn, _ = store.create_bound(
            redirect_uri=LOGIN,
            client_id="campus-club-portal",
            issuer=EXPECTED_ISSUER,
            browser_key_hash=key,
        )
        txn.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    states = []
    for _ in range(MAX_LIVE_TRANSACTIONS_PER_BROWSER):
        txn, _ = store.create_bound(
            redirect_uri=LOGIN,
            client_id="campus-club-portal",
            issuer=EXPECTED_ISSUER,
            browser_key_hash=key,
        )
        states.append(txn.state)
    assert len(store) == MAX_LIVE_TRANSACTIONS_PER_BROWSER
    for state in states:
        assert store.lookup_by_state(state) is not None


# --------------------------------------------------------------- HTTP-level


def test_second_browser_login_completes_while_first_saturated(fake_idp):
    """P1-10 (HTTP): browser A starts 6 logins (only its own 4 stay
    live); browser B then starts and COMPLETES a login normally."""
    client_a, app, vmap = fake_idp
    states_a = [_start_login(client_a, app, vmap) for _ in range(6)]
    assert app.state.txn_store.lookup_by_state(states_a[0]) is None
    client_b = TestClient(app, raise_server_exceptions=False)
    state_b = _start_login(client_b, app, vmap)
    r = _callback(client_b, state_b)
    assert r.status_code == 302
    assert "/portal?login=success" in r.headers["location"]
    assert client_b.get("/api/v1/portal/member").status_code == 200


def test_login_returns_503_when_global_store_full(fake_idp):
    """P1-10 (HTTP): a full global store refuses the start with 503
    TRANSACTION_STORE_FULL and leaves every live transaction intact."""
    client, app, vmap = fake_idp
    keys = [browser_key_hash(generate_browser_key()) for _ in range(5)]
    for key in keys:
        for _ in range(MAX_LIVE_TRANSACTIONS_PER_BROWSER):
            app.state.txn_store.create(
                redirect_uri=LOGIN,
                client_id="campus-club-portal",
                issuer=EXPECTED_ISSUER,
                browser_key_hash=key,
            )
    assert len(app.state.txn_store) == 20
    r = client.get("/auth/login", follow_redirects=False)
    assert r.status_code == 503
    assert "TRANSACTION_STORE_FULL" in r.text
    assert len(app.state.txn_store) == 20


def test_login_rate_limit_boundary(fake_idp):
    """P1-11: 30 starts from one browser key succeed; the 31st is 429;
    a different browser key is unaffected by the first browser's
    limit."""
    assert MAX_LOGIN_STARTS_PER_BROWSER_PER_MINUTE == 30
    assert MAX_LOGIN_STARTS_GLOBAL_PER_MINUTE == 120
    client, app, vmap = fake_idp
    for i in range(MAX_LOGIN_STARTS_PER_BROWSER_PER_MINUTE):
        r = client.get("/auth/login", follow_redirects=False)
        assert r.status_code == 302, f"start {i + 1}: {r.status_code}"
    r = client.get("/auth/login", follow_redirects=False)
    assert r.status_code == 429
    assert "rate_limited" in r.text
    # A different browser (fresh cookie jar) still starts fine.
    other = TestClient(app, raise_server_exceptions=False)
    r = other.get("/auth/login", follow_redirects=False)
    assert r.status_code == 302


def test_browser_key_cookie_contract(fake_idp):
    """P1-10: login sets an anonymous browser cookie (HttpOnly,
    SameSite=Lax, Path=/auth, 22 base64url chars); the transaction
    stores only its SHA-256, and the same browser keeps the same key
    across logins."""
    client, app, vmap = fake_idp
    r = client.get("/auth/login", follow_redirects=False)
    assert r.status_code == 302
    raw = " ".join(r.headers.get_list("set-cookie"))
    assert f"{BROWSER_COOKIE}=" in raw
    assert "httponly" in raw.lower()
    assert "samesite=lax" in raw.lower()
    assert "path=/auth" in raw.lower()
    value = client.cookies.get(BROWSER_COOKIE)
    assert value is not None and len(value) == 22
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    txn = app.state.txn_store.lookup_by_state(state)
    assert txn is not None
    assert txn.browser_key_hash == hashlib.sha256(value.encode()).hexdigest()
    assert txn.browser_key_hash != value
    # Second login reuses the same browser key (stable correlation).
    r2 = client.get("/auth/login", follow_redirects=False)
    assert r2.status_code == 302
    assert client.cookies.get(BROWSER_COOKIE) == value
    state2 = parse_qs(urlparse(r2.headers["location"]).query)["state"][0]
    txn2 = app.state.txn_store.lookup_by_state(state2)
    assert txn2 is not None and txn2.browser_key_hash == txn.browser_key_hash


def test_invalid_browser_key_is_replaced(fake_idp):
    """A malformed browser cookie is treated as absent: the login
    mints a fresh well-formed key instead of trusting the presented
    value for quota accounting."""
    client, app, vmap = fake_idp
    # Same name/domain/path as the app sets, so the jar replaces it
    # cleanly on the next response (a path-/ cookie would coexist
    # with the app's path-/auth one and make the jar ambiguous).
    client.cookies.set(BROWSER_COOKIE, "not-a-valid-key!!", domain="testserver.local", path="/auth")
    r = client.get("/auth/login", follow_redirects=False)
    assert r.status_code == 302
    value = client.cookies.get(BROWSER_COOKIE)
    assert value is not None and value != "not-a-valid-key!!" and len(value) == 22


def test_raw_browser_key_never_in_evidence(fake_idp):
    """P1-10: the raw browser key appears nowhere in evidence or in
    the store — only its SHA-256 is stored server-side, and live-login
    events carry no browser key at all."""
    client, app, vmap = fake_idp
    state = _start_login(client, app, vmap)
    raw = client.cookies.get(BROWSER_COOKIE)
    assert raw
    txn = app.state.txn_store.lookup_by_state(state)
    assert txn is not None
    assert txn.browser_key_hash == hashlib.sha256(raw.encode()).hexdigest()
    assert raw not in txn.browser_key_hash
    _callback(client, state)
    blob = json.dumps(app.state.evidence.list_live_logins(limit=20), default=str)
    assert raw not in blob
