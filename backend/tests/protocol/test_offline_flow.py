"""Protocol: full offline transaction happy path + each negative (no session)."""

from __future__ import annotations

from identityforge.models import FailureReason
from identityforge.protocol.pkce import TransactionStore, verify_pkce
from identityforge.protocol.redirect import check_redirect_uri
from identityforge.protocol.validators import validate_id_token
from identityforge.scenarios.fixtures import (
    CLIENT_ID,
    EXPECTED_ISSUER,
    mint_id_token,
    roles_for_fixture_subject,
)
from identityforge.security.policy import can_access
from identityforge.security.session import SessionStore


def _happy_path(keys):
    """Simulate the whole code flow offline: txn -> token -> session."""
    pem, jwks = keys
    store = TransactionStore()
    txn = store.create(
        redirect_uri="http://127.0.0.1:8000/auth/callback",
        client_id=CLIENT_ID,
        issuer=EXPECTED_ISSUER,
    )
    assert (
        check_redirect_uri(txn.redirect_uri, ("http://127.0.0.1:8000/auth/callback",))
        == FailureReason.OK
    )
    assert verify_pkce(txn.code_verifier, txn.code_challenge) is True
    consumed = store.consume_by_state(txn.state)
    assert consumed is not None
    token = mint_id_token(private_pem=pem, nonce=txn.nonce)
    dec = validate_id_token(
        token,
        jwks=jwks,
        expected_issuer=EXPECTED_ISSUER,
        expected_audience=CLIENT_ID,
        expected_nonce=txn.nonce,
    )
    assert dec.valid, dec.reason_code
    sessions = SessionStore()
    rec = sessions.create(
        subject=dec.subject,
        username=dec.subject,
        roles=roles_for_fixture_subject(dec.subject),
        issuer=EXPECTED_ISSUER,
    )
    return rec, sessions


def test_full_offline_happy_path_creates_member_session(keys):
    rec, sessions = _happy_path(keys)
    assert sessions.get(rec.session_id) is not None
    assert can_access(rec, "member") is True
    assert can_access(rec, "officer") is False


def test_negative_token_never_creates_session(keys):
    pem, jwks = keys
    sessions = SessionStore()
    bad_tokens = [
        mint_id_token(private_pem=pem, issuer="http://127.0.0.1:8080/realms/evil"),
        mint_id_token(private_pem=pem, audience="other-client"),
        mint_id_token(private_pem=pem, expires_in=-300),
        mint_id_token(private_pem=pem, nonce="wrong"),
        mint_id_token(private_pem=pem, tamper=True),
        mint_id_token(private_pem=pem, algorithm="none"),
    ]
    for token in bad_tokens:
        dec = validate_id_token(
            token,
            jwks=jwks,
            expected_issuer=EXPECTED_ISSUER,
            expected_audience=CLIENT_ID,
            expected_nonce="test-nonce",
        )
        assert dec.valid is False
        assert len(sessions) == 0  # no session minted for any bad token


def test_replayed_callback_creates_no_second_session(keys):
    pem, jwks = keys
    store = TransactionStore()
    txn = store.create(
        redirect_uri="http://127.0.0.1:8000/auth/callback",
        client_id=CLIENT_ID,
        issuer=EXPECTED_ISSUER,
    )
    assert store.consume_by_state(txn.state) is not None
    assert store.consume_by_state(txn.state) is None
    # Even with a valid token, a replayed transaction must not mint a session.
    token = mint_id_token(private_pem=pem, nonce=txn.nonce)
    dec = validate_id_token(
        token,
        jwks=jwks,
        expected_issuer=EXPECTED_ISSUER,
        expected_audience=CLIENT_ID,
        expected_nonce=txn.nonce,
    )
    assert dec.valid is True  # token itself is fine; the transaction is the problem
    assert store.lookup_by_state(txn.state) is None
