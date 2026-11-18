"""P1-07 (v3): JWKS hardening — malformed key material fails closed.

parse_jwks must reject every malformed document with a safe ValueError
(no key material in the message), never a TypeError, and the validator
must turn that into a controlled JWKS_ERROR — never a 500. The
callback-path proof (malformed JWKS from a fake IdP -> JWKS_ERROR,
no session) lives in test_trustline_v3_policy.py.
"""

from __future__ import annotations

import copy

import pytest

from identityforge.protocol.jwks import parse_jwks
from identityforge.scenarios.fixtures import generate_rsa_keypair


def _valid_jwk():
    _, jwk = generate_rsa_keypair()
    return jwk


def _valid_doc():
    return {"keys": [_valid_jwk()]}


def test_valid_jwks_still_parses():
    doc = _valid_doc()
    out = parse_jwks(doc)
    assert list(out) == ["lab-key-1"]
    assert out["lab-key-1"]["kty"] == "RSA"


def test_valid_already_parsed_mapping_parses():
    jwk = _valid_jwk()
    out = parse_jwks({"lab-key-1": jwk})
    assert list(out) == ["lab-key-1"]


@pytest.mark.parametrize(
    "bad",
    [
        None,
        42,
        "nope",
        [],
        {},
        {"keys": None},
        {"keys": 42},
        {"keys": "x"},
        {"keys": []},
        {"keys": [None]},
        {"keys": ["not-a-dict"]},
        {"keys": [{"kty": "RSA"}]},  # missing kid/n/e
        {"keys": [{"kty": "RSA", "kid": "k1"}]},  # missing n/e
        {"keys": [{"kty": "RSA", "kid": "k1", "n": "AQAB", "e": "AQAB", "use": "enc"}]},
        {"keys": [{"kty": "RSA", "kid": "k1", "n": "AQAB", "e": "AQAB", "alg": "HS256"}]},
        {"keys": [{"kty": "EC", "kid": "k1"}]},  # no usable RSA keys
        {"keys": [{"kty": "RSA", "kid": "", "n": "AQAB", "e": "AQAB"}]},
        {"keys": [{"kty": "RSA", "kid": 42, "n": "AQAB", "e": "AQAB"}]},
        {"keys": [{"kty": "RSA", "kid": "x" * 129, "n": "AQAB", "e": "AQAB"}]},
        {"keys": [{"kty": "RSA", "kid": "k1", "e": "AQAB"}]},  # missing n
        {"keys": [{"kty": "RSA", "kid": "k1", "n": "AQAB"}]},  # missing e
        {"keys": [{"kty": "RSA", "kid": "k1", "n": "", "e": "AQAB"}]},
        {"keys": [{"kty": "RSA", "kid": "k1", "n": "!!!not-base64!!!", "e": "AQAB"}]},
        {"keys": [{"kty": "RSA", "kid": "k1", "n": "AQAB", "e": "not*base64"}]},
        {"keys": [{"kty": "RSA", "kid": "k1", "n": {"nested": "garbage"}, "e": "AQAB"}]},
        {"keys": [{"kty": "RSA", "kid": "k1", "n": "AQAB", "e": ["AQAB"]}]},
    ],
)
def test_parse_jwks_rejects_malformed_documents(bad):
    with pytest.raises(ValueError) as excinfo:
        parse_jwks(bad)
    # Safe messages: no key material (n/e values) leaks into the error.
    assert "AQAB" not in str(excinfo.value)
    assert "not-base64" not in str(excinfo.value)


def test_parse_jwks_rejects_duplicate_kid():
    jwk = _valid_jwk()
    dup = copy.deepcopy(jwk)
    with pytest.raises(ValueError, match="duplicate kid"):
        parse_jwks({"keys": [jwk, dup]})


def test_parse_jwks_rejects_too_many_keys():
    keys = []
    for i in range(11):
        _, jwk = generate_rsa_keypair(kid=f"key-{i}")
        keys.append(jwk)
    with pytest.raises(ValueError, match="too many keys"):
        parse_jwks({"keys": keys})


def test_parse_jwks_rejects_oversized_document():
    doc = _valid_doc()
    doc["pad"] = "x" * 70_000  # serialised doc exceeds the 64 KiB cap
    with pytest.raises(ValueError, match="size limit"):
        parse_jwks(doc)


def test_parse_jwks_rejects_bad_already_parsed_mapping():
    jwk = _valid_jwk()
    with pytest.raises(ValueError):
        parse_jwks({"other-kid": jwk})  # mapping kid != JWK kid
    bad = copy.deepcopy(jwk)
    bad["n"] = "!!!"
    with pytest.raises(ValueError):
        parse_jwks({"lab-key-1": bad})
    with pytest.raises(ValueError):
        parse_jwks({"lab-key-1": "not-a-dict"})


def test_keycloak_two_key_document_parses_to_signing_key():
    """Regression (measured 2026-11-11): real Keycloak 26.8.2 publishes
    an RSA-OAEP encryption key (use: enc) beside its RS256 signing key.
    The v3 P1-07 hardening rejected the whole document for the enc key
    and every real login failed JWKS_ERROR. Non-signing keys are now
    skipped; only the signing key is returned."""
    sig = _valid_jwk()
    enc = copy.deepcopy(sig)
    enc["kid"] = "enc-key-1"
    enc["use"] = "enc"
    enc["alg"] = "RSA-OAEP"
    out = parse_jwks({"keys": [enc, sig]})
    assert list(out) == [sig["kid"]]
    out = parse_jwks({"keys": [sig, enc]})
    assert list(out) == [sig["kid"]]


def test_document_with_only_encryption_key_has_no_signing_key():
    enc = _valid_jwk()
    enc["use"] = "enc"
    enc["alg"] = "RSA-OAEP"
    with pytest.raises(ValueError, match="no usable RSA signing keys"):
        parse_jwks({"keys": [enc]})


def test_document_with_only_wrong_alg_key_has_no_signing_key():
    bad_alg = _valid_jwk()
    bad_alg["alg"] = "HS256"
    with pytest.raises(ValueError, match="no usable RSA signing keys"):
        parse_jwks({"keys": [bad_alg]})


def test_same_kid_on_enc_and_signing_keys_is_not_a_duplicate():
    sig = _valid_jwk()
    enc = copy.deepcopy(sig)
    enc["use"] = "enc"
    enc["alg"] = "RSA-OAEP"
    out = parse_jwks({"keys": [enc, sig]})
    assert list(out) == [sig["kid"]]
    assert out[sig["kid"]]["use"] == "sig"


def test_malformed_signing_key_still_fails_closed():
    """A bad n/e on a key that claims to sign rejects the document even
    when a valid signing key is present — fail closed, not skip."""
    good = _valid_jwk()
    bad = copy.deepcopy(good)
    bad["kid"] = "bad-key"
    bad["n"] = "!!!not-base64!!!"
    with pytest.raises(ValueError):
        parse_jwks({"keys": [good, bad]})


def test_malformed_encryption_key_is_skipped():
    """A bad n/e on a NON-signing key cannot break the document: the
    key is skipped because it can never verify a signature anyway."""
    good = _valid_jwk()
    bad_enc = copy.deepcopy(good)
    bad_enc["kid"] = "bad-enc"
    bad_enc["use"] = "enc"
    bad_enc["alg"] = "RSA-OAEP"
    bad_enc["n"] = "!!!not-base64!!!"
    out = parse_jwks({"keys": [bad_enc, good]})
    assert list(out) == [good["kid"]]
