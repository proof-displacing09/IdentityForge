"""Unit: ID-token validator — issuer, audience, expiry, nonce, alg, keys."""

from __future__ import annotations

import pytest

from identityforge.models import FailureReason
from identityforge.protocol.validators import validate_id_token
from identityforge.scenarios.fixtures import (
    CLIENT_ID,
    EXPECTED_ISSUER,
    generate_rsa_keypair,
    mint_id_token,
)


def _validate(token, jwks, **kw):
    return validate_id_token(
        token,
        jwks=jwks,
        expected_issuer=EXPECTED_ISSUER,
        expected_audience=CLIENT_ID,
        expected_nonce="test-nonce",
        **kw,
    )


def test_valid_token_passes(valid_token):
    token, jwks = valid_token
    dec = _validate(token, jwks)
    assert dec.valid is True and dec.reason_code == FailureReason.OK
    assert dec.subject == "student_01"


def test_wrong_issuer_rejected(keys):
    pem, jwks = keys
    token = mint_id_token(private_pem=pem, issuer="http://127.0.0.1:8080/realms/evil-lab")
    dec = _validate(token, jwks)
    assert dec.valid is False and dec.reason_code == FailureReason.WRONG_ISSUER


def test_wrong_audience_rejected(keys):
    pem, jwks = keys
    token = mint_id_token(private_pem=pem, audience="other-synthetic-client")
    dec = _validate(token, jwks)
    assert dec.valid is False and dec.reason_code == FailureReason.WRONG_AUDIENCE


def test_expired_token_rejected(keys):
    pem, jwks = keys
    # -300s is beyond the 120s clock skew, so it must be rejected.
    token = mint_id_token(private_pem=pem, expires_in=-300)
    dec = _validate(token, jwks)
    assert dec.valid is False and dec.reason_code == FailureReason.EXPIRED


def test_nonce_mismatch_rejected(keys):
    pem, jwks = keys
    token = mint_id_token(private_pem=pem, nonce="other-nonce")
    dec = _validate(token, jwks)
    assert dec.valid is False and dec.reason_code == FailureReason.NONCE_MISMATCH


def test_missing_nonce_rejected(keys):
    pem, jwks = keys
    token = mint_id_token(private_pem=pem, nonce=None)
    dec = _validate(token, jwks)
    assert dec.valid is False and dec.reason_code == FailureReason.NONCE_MISMATCH


def test_alg_none_rejected(keys):
    pem, jwks = keys
    token = mint_id_token(private_pem=pem, algorithm="none")
    dec = _validate(token, jwks)
    assert dec.valid is False and dec.reason_code == FailureReason.ALG_NOT_ALLOWED


def test_hs256_rejected(keys):
    pem, jwks = keys
    # HS256 with the PEM as HMAC secret — algorithm confusion attempt.
    token = mint_id_token(private_pem=pem, algorithm="HS256")
    dec = _validate(token, jwks)
    assert dec.valid is False and dec.reason_code == FailureReason.ALG_NOT_ALLOWED


def test_wrong_key_rejected(keys):
    pem_other, _ = generate_rsa_keypair(kid="lab-key-1")
    _, jwks = keys  # JWKS holds the first key, token signed by the second
    token = mint_id_token(private_pem=pem_other)
    dec = _validate(token, jwks)
    assert dec.valid is False and dec.reason_code == FailureReason.BAD_SIGNATURE


def test_unknown_kid_rejected(keys):
    pem, jwks = keys
    token = mint_id_token(private_pem=pem, kid="unknown-kid")
    dec = _validate(token, jwks)
    assert dec.valid is False and dec.reason_code == FailureReason.UNKNOWN_KEY


def test_tampered_token_rejected(keys):
    pem, jwks = keys
    token = mint_id_token(private_pem=pem, tamper=True)
    dec = _validate(token, jwks)
    assert dec.valid is False and dec.reason_code == FailureReason.BAD_SIGNATURE


def test_malformed_tokens_rejected(keys):
    _, jwks = keys
    for bad in (None, "", "abc", "a.b", "a.b.c.d", "x" * 9000):
        dec = _validate(bad, jwks)  # type: ignore[arg-type]
        assert dec.valid is False
        assert dec.reason_code == FailureReason.MALFORMED_TOKEN


def test_missing_sub_rejected(keys):
    pem, jwks = keys
    token = mint_id_token(private_pem=pem, extra_claims={"sub": ""})
    dec = _validate(token, jwks)
    assert dec.valid is False
    assert dec.reason_code in (FailureReason.MISSING_CLAIM, FailureReason.MALFORMED_TOKEN)


def test_no_jwks_fails_closed(keys):
    pem, _ = keys
    token = mint_id_token(private_pem=pem)
    dec = _validate(token, None)
    assert dec.valid is False and dec.reason_code == FailureReason.JWKS_ERROR


def test_empty_jwks_fails_closed(keys):
    pem, _ = keys
    token = mint_id_token(private_pem=pem)
    dec = _validate(token, {"keys": []})
    assert dec.valid is False and dec.reason_code == FailureReason.JWKS_ERROR


def test_clock_skew_tolerance(keys):
    # Token expired 60s ago is within the 120s skew; expired 300s ago is not.
    pem, jwks = keys
    assert _validate(mint_id_token(private_pem=pem, expires_in=-60), jwks).valid is True
    assert _validate(mint_id_token(private_pem=pem, expires_in=-300), jwks).valid is False


# ------------------------------------------------- P1-08 strict audience/azp
# Lab policy: EVERY aud value must be the registered client_id; a
# multi-audience token requires azp == client_id; any present azp must
# equal client_id; aud must be a nonempty string or a list of distinct
# nonempty strings.


def test_audience_single_element_array_valid(keys):
    pem, jwks = keys
    token = mint_id_token(private_pem=pem, audience=[CLIENT_ID])
    dec = _validate(token, jwks)
    assert dec.valid is True and dec.reason_code == FailureReason.OK


def test_audience_string_with_matching_azp_valid(keys):
    pem, jwks = keys
    token = mint_id_token(private_pem=pem, extra_claims={"azp": CLIENT_ID})
    assert _validate(token, jwks).valid is True


def test_multi_audience_missing_azp_rejected(keys):
    pem, jwks = keys
    token = mint_id_token(private_pem=pem, audience=[CLIENT_ID, "other-client"])
    dec = _validate(token, jwks)
    assert dec.valid is False and dec.reason_code == FailureReason.WRONG_AUDIENCE


def test_multi_audience_wrong_azp_rejected(keys):
    pem, jwks = keys
    token = mint_id_token(
        private_pem=pem,
        audience=[CLIENT_ID, "other-client"],
        extra_claims={"azp": "other-client"},
    )
    dec = _validate(token, jwks)
    assert dec.valid is False and dec.reason_code == FailureReason.WRONG_AUDIENCE


def test_multi_audience_valid_azp_but_extra_aud_rejected(keys):
    # azp is correct, but the extra audience is unapproved: the token
    # is still rejected — membership is not enough.
    pem, jwks = keys
    token = mint_id_token(
        private_pem=pem,
        audience=[CLIENT_ID, "other-client"],
        extra_claims={"azp": CLIENT_ID},
    )
    dec = _validate(token, jwks)
    assert dec.valid is False and dec.reason_code == FailureReason.WRONG_AUDIENCE


def test_audience_wrong_azp_rejected(keys):
    pem, jwks = keys
    token = mint_id_token(private_pem=pem, extra_claims={"azp": "other-client"})
    dec = _validate(token, jwks)
    assert dec.valid is False and dec.reason_code == FailureReason.WRONG_AUDIENCE


def test_audience_duplicate_values_rejected(keys):
    pem, jwks = keys
    token = mint_id_token(private_pem=pem, audience=[CLIENT_ID, CLIENT_ID])
    dec = _validate(token, jwks)
    assert dec.valid is False and dec.reason_code == FailureReason.WRONG_AUDIENCE


@pytest.mark.parametrize(
    "bad_aud",
    [123, "", [], ["other-client"], [CLIENT_ID, 42], [""]],
)
def test_audience_malformed_rejected(keys, bad_aud):
    pem, jwks = keys
    token = mint_id_token(private_pem=pem, audience=bad_aud)
    dec = _validate(token, jwks)
    assert dec.valid is False and dec.reason_code == FailureReason.WRONG_AUDIENCE
