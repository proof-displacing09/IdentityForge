"""Shared test fixtures: temp evidence DB, TestClient, fresh keypairs."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from identityforge.api.app import create_app
from identityforge.config import Settings
from identityforge.scenarios.fixtures import (
    CLIENT_ID,
    EXPECTED_ISSUER,
    generate_rsa_keypair,
    jwks_for,
    mint_id_token,
)


@pytest.fixture()
def client(tmp_path):
    app = create_app(settings=Settings(), db_path=str(tmp_path / "test.db"))
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture()
def keys():
    pem, jwk = generate_rsa_keypair()
    return pem, {"keys": [jwk]}


@pytest.fixture()
def valid_token(keys):
    pem, jwks = keys
    token = mint_id_token(private_pem=pem, nonce="test-nonce")
    return token, jwks


def mint(keys, **kwargs):
    pem, _ = keys
    return mint_id_token(private_pem=pem, **kwargs)


__all__ = ["CLIENT_ID", "EXPECTED_ISSUER", "jwks_for"]
