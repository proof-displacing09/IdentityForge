"""Unit + integration: trusted IdP transport fetch (P0-01, Trustline v4).

The Docker backend reaches Keycloak via the Compose service DNS
``http://keycloak:8080``, but the bare JWKS fetcher's SSRF guard
correctly rejects that host — so the v3 callback failed EVERY Docker
login at JWKS retrieval (PROVIDER_ERROR) while host-process runs
passed. The fix is provenance, not a wider allowlist: only
``fetch_jwks_via_transport`` / ``post_token_via_transport`` /
``fetch_discovery_via_transport`` may use the transport host, and
only for a URL DERIVED from a validated canonical URL + the
configured transport base. The bare ``fetch_jwks`` still rejects
``keycloak:8080`` (SSRF_BLOCKED), and ``validate_issuer_url`` still
rejects it as an issuer.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from identityforge.api.app import create_app
from identityforge.config import Settings
from identityforge.protocol.jwks import (
    REALM_DISCOVERY_PATH,
    REALM_JWKS_PATH,
    REALM_TOKEN_PATH,
    fetch_discovery_via_transport,
    fetch_jwks,
    fetch_jwks_via_transport,
    post_token_via_transport,
    transport_endpoint_url,
    validate_transport_base,
)
from identityforge.scenarios.fixtures import (
    EXPECTED_ISSUER,
    generate_rsa_keypair,
    jwks_for,
    mint_id_token,
)
from identityforge.security.policy import OFFICER_SUB, STUDENT_SUB
from tests.fake_http import install_stream_fake

CANONICAL = "http://127.0.0.1:8080/realms/identityforge-lab"
CANONICAL_JWKS = f"{CANONICAL}/protocol/openid-connect/certs"
CANONICAL_TOKEN = f"{CANONICAL}/protocol/openid-connect/token"
COMPOSE_BASE = "http://keycloak:8080"


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _discovery_doc():
    return {
        "issuer": EXPECTED_ISSUER,
        "authorization_endpoint": EXPECTED_ISSUER + "/protocol/openid-connect/auth",
        "token_endpoint": EXPECTED_ISSUER + "/protocol/openid-connect/token",
        "jwks_uri": EXPECTED_ISSUER + "/protocol/openid-connect/certs",
    }


# ------------------------------------------------------------------ positive


def test_jwks_fetch_via_compose_transport_succeeds(monkeypatch):
    """P0-01: canonical -> Compose transport -> JWKS fetch SUCCEEDS.

    The fake HTTP layer asserts the request actually went to the exact
    internal service DNS (host keycloak, port 8080, pinned certs path)
    — no real network is used."""
    pem, _ = generate_rsa_keypair()
    jwks = jwks_for(pem)
    seen: list[str] = []

    def fake_get(url, **kwargs):
        seen.append(url)
        assert kwargs.get("follow_redirects") is False
        assert kwargs.get("trust_env") is False
        return _Resp(jwks)

    install_stream_fake(monkeypatch, get_fake=fake_get)
    doc = fetch_jwks_via_transport(CANONICAL_JWKS, COMPOSE_BASE)
    assert doc == jwks
    assert len(seen) == 1
    parsed = urlparse(seen[0])
    assert parsed.hostname == "keycloak"
    assert parsed.port == 8080
    assert parsed.path == REALM_JWKS_PATH


def test_token_post_via_compose_transport_succeeds(monkeypatch):
    pem, _ = generate_rsa_keypair()
    seen: list[str] = []

    def fake_post(url, **kwargs):
        seen.append(url)
        assert kwargs.get("follow_redirects") is False
        assert kwargs.get("trust_env") is False
        return _Resp({"id_token": "not-a-real-token", "token_type": "Bearer"})

    install_stream_fake(monkeypatch, post_fake=fake_post)
    resp = post_token_via_transport(CANONICAL_TOKEN, COMPOSE_BASE, data={"code": "x"})
    assert resp.json()["token_type"] == "Bearer"
    parsed = urlparse(seen[0])
    assert parsed.hostname == "keycloak"
    assert parsed.port == 8080
    assert parsed.path == REALM_TOKEN_PATH


def test_discovery_via_compose_transport_succeeds(monkeypatch):
    seen: list[str] = []

    def fake_get(url, **kwargs):
        seen.append(url)
        assert kwargs.get("follow_redirects") is False
        assert kwargs.get("trust_env") is False
        return _Resp(_discovery_doc())

    install_stream_fake(monkeypatch, get_fake=fake_get)
    endpoints = fetch_discovery_via_transport(COMPOSE_BASE, canonical_issuer=EXPECTED_ISSUER)
    assert endpoints["jwks_uri"] == CANONICAL_JWKS
    assert endpoints["token_endpoint"] == CANONICAL_TOKEN
    parsed = urlparse(seen[0])
    assert parsed.hostname == "keycloak"
    assert parsed.port == 8080
    assert parsed.path == REALM_DISCOVERY_PATH


def test_host_transport_still_works(monkeypatch):
    """The host-process route (loopback transport base) is unchanged."""
    pem, _ = generate_rsa_keypair()
    jwks = jwks_for(pem)
    seen: list[str] = []
    install_stream_fake(monkeypatch, get_fake=lambda url, **kw: (seen.append(url), _Resp(jwks))[1])
    doc = fetch_jwks_via_transport(CANONICAL_JWKS, "http://127.0.0.1:8080")
    assert doc == jwks
    assert urlparse(seen[0]).hostname == "127.0.0.1"


# ------------------------------------------------------------------ negatives

# Each negative asserts rejection BEFORE any network call: the fake
# transport raises if it is ever invoked.


def _never_called(url, **kwargs):
    raise AssertionError(f"network call must not happen: {url}")


@pytest.mark.parametrize(
    "canonical,base",
    [
        # External host as the canonical URL.
        (
            "https://evil.example/realms/identityforge-lab/protocol/openid-connect/certs",
            COMPOSE_BASE,
        ),
        # Cloud metadata as the canonical URL.
        (
            "http://169.254.169.254/realms/identityforge-lab/protocol/openid-connect/certs",
            COMPOSE_BASE,
        ),
        # Wrong port on the canonical URL.
        (
            "http://127.0.0.1:8081/realms/identityforge-lab/protocol/openid-connect/certs",
            COMPOSE_BASE,
        ),
        # Wrong path on the canonical URL.
        (
            "http://127.0.0.1:8080/realms/identityforge-lab/protocol/openid-connect/auth",
            COMPOSE_BASE,
        ),
        # Wrong realm on the canonical URL.
        ("http://127.0.0.1:8080/realms/other/protocol/openid-connect/certs", COMPOSE_BASE),
        # Query substitution on the canonical URL.
        (CANONICAL_JWKS + "?next=https://evil.example", COMPOSE_BASE),
        # Credentials in the canonical URL.
        (
            "http://user:pass@127.0.0.1:8080/realms/identityforge-lab/protocol/openid-connect/certs",
            COMPOSE_BASE,
        ),
        # External host as the transport base.
        (CANONICAL_JWKS, "http://evil.example:8080"),
        # Metadata host as the transport base.
        (CANONICAL_JWKS, "http://169.254.169.254:8080"),
        # Wrong port on the transport base.
        (CANONICAL_JWKS, "http://keycloak:8081"),
        # Lookalike host as the transport base.
        (CANONICAL_JWKS, "http://keycloak.evil.example:8080"),
        # Userinfo in the transport base.
        (CANONICAL_JWKS, "http://user:pass@keycloak:8080"),
        # Path in the transport base.
        (CANONICAL_JWKS, "http://keycloak:8080/evil"),
    ],
)
def test_transport_fetch_rejects_bad_inputs_before_network(monkeypatch, canonical, base):
    install_stream_fake(monkeypatch, get_fake=_never_called, post_fake=_never_called)
    with pytest.raises(ValueError):
        fetch_jwks_via_transport(canonical, base)
    with pytest.raises(ValueError):
        transport_endpoint_url(canonical, base, expected_path=REALM_JWKS_PATH)


def test_unvalidated_keycloak_url_still_ssrf_blocked_by_bare_fetch(monkeypatch):
    """P0-01: a bare keycloak:8080 URL passed to fetch_jwks is STILL
    SSRF_BLOCKED — only the provenance-carrying fetcher may use it."""
    install_stream_fake(monkeypatch, get_fake=_never_called)
    with pytest.raises(ValueError, match="SSRF_BLOCKED"):
        fetch_jwks("http://keycloak:8080/realms/identityforge-lab/protocol/openid-connect/certs")


def test_transport_base_validation():
    assert validate_transport_base("http://keycloak:8080") == ("keycloak", 8080)
    assert validate_transport_base("http://127.0.0.1:8080") == ("127.0.0.1", 8080)
    assert validate_transport_base("http://host.docker.internal:8080") == (
        "host.docker.internal",
        8080,
    )
    for bad in (
        "http://evil.example:8080",
        "http://keycloak:8081",
        "http://keycloak:8080/evil",
        "http://user:pass@keycloak:8080",
        "ftp://keycloak:8080",
        "http://169.254.169.254:8080",
        "",
    ):
        with pytest.raises(ValueError):
            validate_transport_base(bad)


def test_foreign_discovery_rejected_before_endpoints_used(monkeypatch):
    """P0-01: a discovery document from the transport host whose issuer
    or endpoints are foreign is rejected — no endpoint from it is used."""
    install_stream_fake(monkeypatch, get_fake=_never_called)
    # Non-pinned issuer in the served document.
    foreign = _discovery_doc()
    foreign["issuer"] = "http://evil.example/realms/identityforge-lab"

    def fake_get_issuer(url, **kwargs):
        return _Resp(foreign)

    install_stream_fake(monkeypatch, get_fake=fake_get_issuer)
    with pytest.raises(ValueError):
        fetch_discovery_via_transport(COMPOSE_BASE, canonical_issuer=EXPECTED_ISSUER)

    # Foreign token endpoint in the served document.
    foreign_ep = _discovery_doc()
    foreign_ep["token_endpoint"] = (
        "https://evil.example/realms/identityforge-lab/protocol/openid-connect/token"
    )

    def fake_get_ep(url, **kwargs):
        return _Resp(foreign_ep)

    install_stream_fake(monkeypatch, get_fake=fake_get_ep)
    with pytest.raises(ValueError):
        fetch_discovery_via_transport(COMPOSE_BASE, canonical_issuer=EXPECTED_ISSUER)


# ------------------------------------------------------------------ callback


def _make_compose_client(monkeypatch, tmp_path):
    """App with the Compose transport base + fake IdP that ONLY serves
    the keycloak host; records every requested URL host. The token
    endpoint mints with the nonce of the transaction whose
    code_verifier is presented (verifier_map is filled in by the
    driving test after login, as in the multitab fixture)."""
    pem, _ = generate_rsa_keypair()
    jwks = jwks_for(pem)
    hosts: list[str] = []
    verifier_map: dict[str, tuple[str, str]] = {}

    def fake_get(url, **kwargs):
        hosts.append(urlparse(url).hostname or "")
        if "openid-configuration" in url:
            return _Resp(_discovery_doc())
        if url.endswith("/certs"):
            return _Resp(jwks)
        raise AssertionError(f"unexpected GET {url}")

    def fake_post(url, **kwargs):
        hosts.append(urlparse(url).hostname or "")
        assert url.endswith("/protocol/openid-connect/token"), url
        data = kwargs.get("data", {})
        subject, nonce = verifier_map[data["code_verifier"]]
        token = mint_id_token(private_pem=pem, subject=subject, nonce=nonce)
        return _Resp({"id_token": token, "token_type": "Bearer"})

    install_stream_fake(monkeypatch, get_fake=fake_get, post_fake=fake_post)
    settings = Settings(idp_transport_base=COMPOSE_BASE)
    app = create_app(settings=settings, db_path=str(tmp_path / "test.db"))
    client = TestClient(app, raise_server_exceptions=False)
    return client, app, pem, hosts, verifier_map


def _drive_callback(client, app, subject, verifier_map):
    """Login -> callback with the fake IdP; returns the callback response.

    The fake token endpoint mints with the transaction's own nonce, so
    the ID token validates; its issuer is the canonical issuer."""
    r = client.get("/auth/login", follow_redirects=False)
    assert r.status_code == 302, r.text
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    txn = app.state.txn_store.lookup_by_state(state)
    assert txn is not None
    verifier_map[txn.code_verifier] = (subject, txn.nonce)
    return client.get(f"/auth/callback?code=fake-code&state={state}", follow_redirects=False)


def test_callback_via_compose_transport_creates_session(monkeypatch, tmp_path):
    """P0-01 regression: with the transport base set to
    http://keycloak:8080, the callback MUST create a session. On the
    v3 code this fails: fetch_jwks(rewritten keycloak URL) raises
    SSRF_BLOCKED and the callback redirects to PROVIDER_ERROR with no
    session. The test also proves the backchannel actually used the
    keycloak host while the token issuer stayed canonical."""
    client, app, pem, hosts, verifier_map = _make_compose_client(monkeypatch, tmp_path)
    r = _drive_callback(client, app, STUDENT_SUB, verifier_map)
    assert r.status_code == 302, r.headers
    assert "/portal?login=success" in r.headers["location"], r.headers
    assert set(hosts) == {"keycloak"}, hosts
    me = client.get("/api/v1/portal/me")
    assert me.status_code == 200
    assert me.json()["username"] == "student_01"
    assert me.json()["issuer"] == EXPECTED_ISSUER
    assert client.get("/api/v1/portal/member").status_code == 200
    assert client.get("/api/v1/portal/officer").status_code == 403


def test_callback_via_compose_transport_officer(monkeypatch, tmp_path):
    client, app, pem, hosts, verifier_map = _make_compose_client(monkeypatch, tmp_path)
    r = _drive_callback(client, app, OFFICER_SUB, verifier_map)
    assert "/portal?login=success" in r.headers["location"], r.headers
    assert client.get("/api/v1/portal/officer").status_code == 200
    assert client.get("/api/v1/portal/member").status_code == 200
