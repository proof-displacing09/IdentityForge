"""Unit: backend-to-Keycloak transport route (P0-04, Trustline v3).

The Compose stack reaches Keycloak via the private bridge service DNS
``http://keycloak:8080``. That name is a TRANSPORT route only: it must
work in rewrite_to_transport, and it must NEVER validate as an issuer
identity, a browser URL, or a discovery issuer. The canonical issuer
stays http://127.0.0.1:8080/realms/identityforge-lab everywhere it
matters. Host-run (non-Docker) keeps the 127.0.0.1 transport default.
"""

from __future__ import annotations

import pytest

from identityforge.models import FailureReason
from identityforge.protocol.jwks import (
    is_loopback_host,
    rewrite_to_transport,
    validate_discovery,
    validate_issuer_url,
)
from identityforge.scenarios.fixtures import EXPECTED_ISSUER

CANONICAL = "http://127.0.0.1:8080/realms/identityforge-lab"
TOKEN = f"{CANONICAL}/protocol/openid-connect/token"
JWKS = f"{CANONICAL}/protocol/openid-connect/certs"


def test_rewrite_to_keycloak_service_dns_works():
    # P0-04: the Compose backend reaches Keycloak as keycloak:8080.
    assert rewrite_to_transport(TOKEN, "http://keycloak:8080") == (
        "http://keycloak:8080/realms/identityforge-lab/protocol/openid-connect/token"
    )
    assert rewrite_to_transport(JWKS, "http://keycloak:8080") == (
        "http://keycloak:8080/realms/identityforge-lab/protocol/openid-connect/certs"
    )


def test_rewrite_to_loopback_transports_still_work():
    # Host-run and legacy routes are preserved, not removed.
    assert rewrite_to_transport(TOKEN, "http://127.0.0.1:8080").startswith(
        "http://127.0.0.1:8080/realms/identityforge-lab/"
    )
    assert rewrite_to_transport(TOKEN, "http://host.docker.internal:8080").startswith(
        "http://host.docker.internal:8080/realms/identityforge-lab/"
    )


def test_keycloak_is_not_a_loopback_host():
    # "keycloak" must never validate as an issuer identity: it is not
    # loopback, so issuer/JWKS URL guards must reject it.
    assert is_loopback_host("keycloak") is False
    assert is_loopback_host("127.0.0.1") is True


def test_keycloak_url_rejected_as_issuer():
    assert (
        validate_issuer_url("http://keycloak:8080/realms/identityforge-lab", (EXPECTED_ISSUER,))
        != FailureReason.OK
    )


def test_discovery_with_keycloak_issuer_rejected():
    doc = {
        "issuer": "http://keycloak:8080/realms/identityforge-lab",
        "authorization_endpoint": f"{CANONICAL}/protocol/openid-connect/auth",
        "token_endpoint": f"{CANONICAL}/protocol/openid-connect/token",
        "jwks_uri": f"{CANONICAL}/protocol/openid-connect/certs",
    }
    with pytest.raises(ValueError):
        validate_discovery(doc, canonical_issuer=EXPECTED_ISSUER)


@pytest.mark.parametrize(
    "source,base",
    [
        # Wrong port on the service DNS.
        (TOKEN, "http://keycloak:8081"),
        # Lookalike host must not pass as the service DNS name.
        (TOKEN, "http://keycloak.evil.example:8080"),
        # Non-realm path on the service DNS.
        (
            "http://127.0.0.1:8080/something-else",
            "http://keycloak:8080",
        ),
        # External source host must not be rewritten onto the transport.
        (
            "https://evil.example/realms/identityforge-lab/protocol/openid-connect/token",
            "http://keycloak:8080",
        ),
    ],
)
def test_keycloak_transport_rejects_bad_rewrites(source, base):
    with pytest.raises(ValueError):
        rewrite_to_transport(source, base)
