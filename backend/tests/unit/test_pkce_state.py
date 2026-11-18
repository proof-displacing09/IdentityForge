"""Unit: PKCE, state/nonce, one-use transaction store."""

from __future__ import annotations

import re

from identityforge.protocol.pkce import (
    TransactionStore,
    code_challenge_s256,
    generate_nonce,
    generate_state,
    generate_verifier,
    verify_pkce,
)


def test_verifier_length_and_charset():
    v = generate_verifier()
    assert 43 <= len(v) <= 128
    assert re.fullmatch(r"[A-Za-z0-9\-_]+", v)


def test_challenge_is_s256_of_verifier():
    v = generate_verifier()
    assert code_challenge_s256(v) != v
    assert verify_pkce(v, code_challenge_s256(v)) is True


def test_wrong_verifier_fails():
    v = generate_verifier()
    assert verify_pkce("wrong-verifier", code_challenge_s256(v)) is False
    assert verify_pkce("", code_challenge_s256(v)) is False
    assert verify_pkce(v, "") is False


def test_state_and_nonce_unique_and_random():
    assert generate_state() != generate_state()
    assert generate_nonce() != generate_nonce()
    assert len(generate_state()) >= 32


def test_transaction_create_has_challenge():
    store = TransactionStore()
    txn = store.create(
        redirect_uri="http://127.0.0.1:8000/auth/callback",
        client_id="campus-club-portal",
        issuer="http://x/realms/y",
    )
    assert txn.code_challenge == code_challenge_s256(txn.code_verifier)
    assert txn.state and txn.nonce


def test_transaction_consume_is_one_use():
    store = TransactionStore()
    txn = store.create(
        redirect_uri="http://127.0.0.1:8000/auth/callback", client_id="c", issuer="i"
    )
    assert store.consume_by_state(txn.state) is not None
    assert store.consume_by_state(txn.state) is None  # replay rejected
    assert store.lookup_by_state(txn.state) is None


def test_transaction_unknown_state_returns_none():
    store = TransactionStore()
    assert store.lookup_by_state("no-such-state") is None
    assert store.consume_by_state("no-such-state") is None


def test_transaction_expired_is_purged():
    store = TransactionStore(ttl_seconds=-1)
    txn = store.create(
        redirect_uri="http://127.0.0.1:8000/auth/callback", client_id="c", issuer="i"
    )
    assert store.lookup_by_state(txn.state) is None


def test_pkce_downgrade_plain_challenge_rejected():
    # A 'plain' challenge (verifier == challenge) is not S256; our verifier
    # only accepts the S256 hash, so a plain value fails.
    v = generate_verifier()
    assert verify_pkce(v, v) is False
