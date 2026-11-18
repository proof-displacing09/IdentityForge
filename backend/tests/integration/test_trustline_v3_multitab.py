"""Operation Trustline v3 — P1-06 multi-tab concurrent logins.

Design under test (see protocol/pkce.py): each login gets its OWN
HttpOnly binding cookie named ``identityforge_txn_<state>``, so a
second login in the same browser cannot overwrite the first tab's
binding. The callback reads exactly the cookie named for the presented
state; a wrong/missing binding does NOT consume the transaction, so
the legitimate tab can still complete. At most 4 live transactions
may exist per browser (v4, P1-10); creating a 5th evicts that
browser's own oldest unexpired one — never another browser's. The
global safety cap is 20, and a full store refuses new starts instead
of evicting.

Cross-browser binding, TTL, state unpredictability, one-time code
use, nonce, PKCE and failed-callback isolation are NOT relaxed by
this design — tests 7-10 below prove the attacker cases still fail.
Keycloak is NOT RUN here; logins use the fake-IdP stub.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from identityforge.api.app import create_app
from identityforge.config import Settings
from identityforge.protocol.pkce import (
    TransactionStore,
    txn_binding_cookie_name,
)
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
    """Fake IdP + app; returns (client, pem, app, verifier_map).

    The token endpoint mints with the nonce of the transaction whose
    code_verifier is presented, so callbacks may complete in ANY
    order — the fake IdP never confuses tab A's nonce with tab B's.
    """
    pem, _ = generate_rsa_keypair()
    jwks = jwks_for(pem)
    discovery = {
        "issuer": EXPECTED_ISSUER,
        "authorization_endpoint": EXPECTED_ISSUER + "/protocol/openid-connect/auth",
        "token_endpoint": EXPECTED_ISSUER + "/protocol/openid-connect/token",
        "jwks_uri": EXPECTED_ISSUER + "/protocol/openid-connect/certs",
    }
    verifier_map: dict[str, tuple[str, str]] = {}  # verifier -> (subject, nonce)

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
        subject, nonce = verifier_map[data["code_verifier"]]
        token = mint_id_token(private_pem=pem, subject=subject, nonce=nonce)
        return _Resp({"id_token": token, "token_type": "Bearer"})

    install_stream_fake(monkeypatch, get_fake=fake_get)
    install_stream_fake(monkeypatch, post_fake=fake_post)
    app = create_app(settings=Settings(), db_path=str(tmp_path / "test.db"))
    client = TestClient(app, raise_server_exceptions=False)
    return client, pem, app, verifier_map


def _start_login(client, app, verifier_map, subject):
    """Start a login (one tab); returns the state."""
    r = client.get("/auth/login", follow_redirects=False)
    assert r.status_code == 302, r.text
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    txn = app.state.txn_store.lookup_by_state(state)
    assert txn is not None
    verifier_map[txn.code_verifier] = (subject, txn.nonce)
    return state


def _callback(client, state, code="fake-code"):
    return client.get(f"/auth/callback?code={code}&state={state}", follow_redirects=False)


def _set_jar_cookie(client, name, value):
    """Replace one stored cookie's value in place (test introspection).

    httpx records response cookies under the request host with a
    ``.local`` suffix, so ``cookies.set(name, value, domain=...)``
    with a guessed domain can ADD a second entry instead of
    replacing — the jar would then send the real token first and a
    forged-cookie test would silently pass. Mutating the stored
    entry is exact.
    """
    matches = [ck for ck in client.cookies.jar if ck.name == name]
    assert len(matches) == 1, f"expected exactly one {name} cookie, got {len(matches)}"
    matches[0].value = value


def _assert_login_success(resp):
    assert resp.status_code == 302, resp.headers
    assert "/portal?login=success" in resp.headers["location"], resp.headers


def _assert_login_failed(resp, reason):
    assert resp.status_code == 302, resp.headers
    assert f"error={reason}" in resp.headers["location"], resp.headers


# ------------------------------------------------------------------ P1-06


def test_two_tabs_complete_b_then_a(fake_idp):
    """P1-06 (1): two tabs, second-started completes first — both
    succeed; the first tab's binding was never overwritten."""
    client, pem, app, vmap = fake_idp
    state_a = _start_login(client, app, vmap, STUDENT_SUB)
    state_b = _start_login(client, app, vmap, OFFICER_SUB)
    # Each login set its OWN cookie; both are present in the jar.
    assert client.cookies.get(txn_binding_cookie_name(state_a)) is not None
    assert client.cookies.get(txn_binding_cookie_name(state_b)) is not None
    # Complete B first: success, and ONLY B's cookie is deleted.
    r_b = _callback(client, state_b)
    _assert_login_success(r_b)
    assert client.get("/api/v1/portal/officer").status_code == 200
    deleted = " ".join(r_b.headers.get_list("set-cookie"))
    assert txn_binding_cookie_name(state_b) in deleted
    assert txn_binding_cookie_name(state_a) not in deleted
    assert client.cookies.get(txn_binding_cookie_name(state_a)) is not None
    # Complete A afterwards: still succeeds (binding intact).
    _assert_login_success(_callback(client, state_a))
    assert client.get("/api/v1/portal/me").json()["username"] == "student_01"
    assert client.get("/api/v1/portal/officer").status_code == 403


def test_two_tabs_complete_a_then_b(fake_idp):
    """P1-06 (2): two tabs, first-started completes first — both succeed."""
    client, pem, app, vmap = fake_idp
    state_a = _start_login(client, app, vmap, STUDENT_SUB)
    state_b = _start_login(client, app, vmap, OFFICER_SUB)
    _assert_login_success(_callback(client, state_a))
    assert client.get("/api/v1/portal/me").json()["username"] == "student_01"
    _assert_login_success(_callback(client, state_b))
    assert client.get("/api/v1/portal/officer").status_code == 200


def test_three_tabs_complete_in_reverse_order(fake_idp):
    """P1-06 (3): three tabs, completed C, B, A — all succeed."""
    client, pem, app, vmap = fake_idp
    state_a = _start_login(client, app, vmap, STUDENT_SUB)
    state_b = _start_login(client, app, vmap, OFFICER_SUB)
    state_c = _start_login(client, app, vmap, STUDENT_SUB)
    _assert_login_success(_callback(client, state_c))
    _assert_login_success(_callback(client, state_b))
    assert client.get("/api/v1/portal/officer").status_code == 200
    _assert_login_success(_callback(client, state_a))
    me = client.get("/api/v1/portal/me").json()
    assert me["username"] == "student_01"
    assert me["roles"] == ["member"]


def test_cancelled_tab_does_not_break_other_tab(fake_idp):
    """P1-06 (4): tab A is cancelled at the provider
    (?error=access_denied) while tab B completes normally."""
    client, pem, app, vmap = fake_idp
    state_a = _start_login(client, app, vmap, STUDENT_SUB)
    state_b = _start_login(client, app, vmap, STUDENT_SUB)
    r = client.get(f"/auth/callback?error=access_denied&state={state_a}", follow_redirects=False)
    _assert_login_failed(r, "PROVIDER_ERROR")
    _assert_login_success(_callback(client, state_b))
    assert client.get("/api/v1/portal/me").status_code == 200


def test_expired_transaction_does_not_break_other_tab(fake_idp):
    """P1-06 (5): tab A's transaction expires while tab B is live;
    B completes, A fails closed with STATE_REUSED (expired entries
    are purged lazily on access)."""
    client, pem, app, vmap = fake_idp
    state_a = _start_login(client, app, vmap, STUDENT_SUB)
    state_b = _start_login(client, app, vmap, STUDENT_SUB)
    txn_a = app.state.txn_store.lookup_by_state(state_a)
    assert txn_a is not None
    txn_a.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    _assert_login_success(_callback(client, state_b))
    assert client.get("/api/v1/portal/me").status_code == 200
    _assert_login_failed(_callback(client, state_a), "STATE_REUSED")


def test_logout_during_other_login(fake_idp):
    """P1-06 (6): a session is logged out while a second login is
    in flight; the in-flight login still completes and mints a fresh
    session (rotation revokes the already-revoked id harmlessly)."""
    client, pem, app, vmap = fake_idp
    state_first = _start_login(client, app, vmap, STUDENT_SUB)
    _assert_login_success(_callback(client, state_first))
    assert client.get("/api/v1/portal/me").status_code == 200
    state_second = _start_login(client, app, vmap, OFFICER_SUB)
    token = client.get("/api/v1/csrf-token").json()["csrf_token"]
    r = client.post("/auth/logout", headers={"X-CSRF-Token": token})
    assert r.status_code == 200, r.text
    assert client.get("/api/v1/portal/me").status_code == 401
    _assert_login_success(_callback(client, state_second))
    assert client.get("/api/v1/portal/officer").status_code == 200


def test_replay_of_tab_a_after_completion_tab_b_still_valid(fake_idp):
    """P1-06 (7): replaying tab A's state after it completed is
    STATE_REUSED (one-time code use), and tab B still completes."""
    client, pem, app, vmap = fake_idp
    state_a = _start_login(client, app, vmap, STUDENT_SUB)
    state_b = _start_login(client, app, vmap, STUDENT_SUB)
    _assert_login_success(_callback(client, state_a))
    _assert_login_failed(_callback(client, state_a), "STATE_REUSED")
    _assert_login_success(_callback(client, state_b))
    assert client.get("/api/v1/portal/me").status_code == 200


def test_forged_binding_cookie_does_not_consume_transaction(fake_idp):
    """P1-06 (8): a forged binding token for tab A's state is
    STATE_BINDING_MISMATCH and does NOT consume the transaction, so
    the legitimate tab completes afterwards with its real cookie."""
    client, pem, app, vmap = fake_idp
    state_a = _start_login(client, app, vmap, STUDENT_SUB)
    state_b = _start_login(client, app, vmap, STUDENT_SUB)
    cookie_a = txn_binding_cookie_name(state_a)
    real_token = client.cookies.get(cookie_a)
    assert real_token, "login did not set the per-transaction cookie"
    # Forge by mutating the stored cookie in place: httpx records
    # response cookies under domain "testserver.local", so a naive
    # cookies.set(..., domain="testserver") would ADD a second entry
    # and the jar would still send the real token first.
    _set_jar_cookie(client, cookie_a, "forged-binding-token")
    _assert_login_failed(_callback(client, state_a), "STATE_BINDING_MISMATCH")
    assert app.state.txn_store.lookup_by_state(state_a) is not None
    assert client.get("/api/v1/portal/me").status_code == 401
    # Restore the real token: the legitimate tab now completes.
    _set_jar_cookie(client, cookie_a, real_token)
    _assert_login_success(_callback(client, state_a))
    assert client.get("/api/v1/portal/me").status_code == 200
    _assert_login_success(_callback(client, state_b))


def test_browser_swap_rejected_and_legitimate_tab_still_completes(fake_idp):
    """P1-06 (9): a second browser (no binding cookies) cannot steal
    tab A's callback; both legitimate tabs still complete."""
    client, pem, app, vmap = fake_idp
    state_a = _start_login(client, app, vmap, STUDENT_SUB)
    state_b = _start_login(client, app, vmap, STUDENT_SUB)
    other = TestClient(app, raise_server_exceptions=False)
    _assert_login_failed(_callback(other, state_a), "STATE_BINDING_MISMATCH")
    assert other.get("/api/v1/portal/me").status_code == 401
    _assert_login_success(_callback(client, state_a))
    _assert_login_success(_callback(client, state_b))
    assert client.get("/api/v1/portal/me").status_code == 200


def test_stale_redirect_rejected(fake_idp):
    """P1-06 (10): a callback for an expired state fails closed with
    STATE_REUSED and creates no session."""
    client, pem, app, vmap = fake_idp
    state_a = _start_login(client, app, vmap, STUDENT_SUB)
    txn_a = app.state.txn_store.lookup_by_state(state_a)
    assert txn_a is not None
    txn_a.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    _assert_login_failed(_callback(client, state_a), "STATE_REUSED")
    assert client.get("/api/v1/portal/me").status_code == 401


def test_transaction_store_caps_live_transactions_per_browser():
    """P1-10 (v4) — CHANGED from the v3 global cap: the cap is PER
    BROWSER now, not global. Five transactions from one browser evict
    that browser's oldest (cap 4); the old behaviour — a 6th
    transaction evicting the globally oldest, which let one client
    kill another browser's waiting login — is gone (see
    test_trustline_v4_transactions.py for the cross-browser proof)."""
    from identityforge.protocol.pkce import (
        MAX_LIVE_TRANSACTIONS_GLOBAL,
        MAX_LIVE_TRANSACTIONS_PER_BROWSER,
        browser_key_hash,
        generate_browser_key,
    )

    store = TransactionStore()
    key_a = browser_key_hash(generate_browser_key())
    states = []
    for _ in range(MAX_LIVE_TRANSACTIONS_PER_BROWSER + 1):
        txn, _token = store.create_bound(
            redirect_uri="http://127.0.0.1:8000/auth/callback",
            client_id="campus-club-portal",
            issuer=EXPECTED_ISSUER,
            browser_key_hash=key_a,
        )
        states.append(txn.state)
    assert len(store) == MAX_LIVE_TRANSACTIONS_PER_BROWSER
    assert store.lookup_by_state(states[0]) is None  # own oldest evicted
    for state in states[1:]:
        assert store.lookup_by_state(state) is not None
    assert MAX_LIVE_TRANSACTIONS_GLOBAL == 20


def test_login_sets_per_transaction_cookie_attributes(fake_idp):
    """P1-06 cookie contract: the login response sets a cookie named
    for the transaction's state, HttpOnly, SameSite=Lax, Path=/auth,
    with the transaction TTL — never the old single global name."""
    client, pem, app, vmap = fake_idp
    r = client.get("/auth/login", follow_redirects=False)
    assert r.status_code == 302
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    name = txn_binding_cookie_name(state)
    raw = " ".join(r.headers.get_list("set-cookie"))
    assert f"{name}=" in raw
    assert "httponly" in raw.lower()
    assert "samesite=lax" in raw.lower()
    assert "path=/auth" in raw.lower()
    # No bare global cookie is set any more.
    assert "identityforge_txn=" not in raw
