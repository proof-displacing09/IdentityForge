"""P1-11: flawed validators omit EXACTLY ONE check and run all others.
P1-18: azp / multi-audience handling."""

from identityforge.protocol.validators import validate_id_token
from identityforge.scenarios import flawed
from identityforge.scenarios.fixtures import (
    CLIENT_ID,
    EXPECTED_ISSUER,
    generate_rsa_keypair,
    jwks_for,
    mint_id_token,
)

CTX = dict(
    expected_issuer=EXPECTED_ISSUER, expected_audience=CLIENT_ID, expected_nonce="test-nonce"
)


def _setup():
    pem, _ = generate_rsa_keypair()
    return pem, jwks_for(pem)


def test_flawed_audience_allows_wrong_aud_but_rejects_tampered_and_wrong_issuer():
    pem, jwks = _setup()
    wrong_aud = mint_id_token(private_pem=pem, audience="other-client")
    assert validate_id_token(wrong_aud, jwks=jwks, **CTX).valid is False
    assert flawed.flawed_skip_audience(wrong_aud, jwks=jwks, **CTX).valid is True
    tampered = mint_id_token(private_pem=pem, tamper=True)
    assert flawed.flawed_skip_audience(tampered, jwks=jwks, **CTX).valid is False
    wrong_iss = mint_id_token(private_pem=pem, issuer="https://evil.example/realm")
    assert flawed.flawed_skip_audience(wrong_iss, jwks=jwks, **CTX).valid is False


def test_flawed_issuer_allows_wrong_iss_but_rejects_wrong_aud():
    pem, jwks = _setup()
    wrong_iss = mint_id_token(private_pem=pem, issuer="https://evil.example/realm")
    assert flawed.flawed_skip_issuer(wrong_iss, jwks=jwks, **CTX).valid is True
    wrong_aud = mint_id_token(private_pem=pem, audience="other-client")
    assert flawed.flawed_skip_issuer(wrong_aud, jwks=jwks, **CTX).valid is False


def test_flawed_signature_allows_tampered_but_rejects_expired():
    pem, jwks = _setup()
    tampered = mint_id_token(private_pem=pem, tamper=True)
    assert validate_id_token(tampered, jwks=jwks, **CTX).valid is False
    assert flawed.flawed_skip_signature(tampered, jwks=jwks, **CTX).valid is True
    expired = mint_id_token(private_pem=pem, expires_in=-300)
    assert flawed.flawed_skip_signature(expired, jwks=jwks, **CTX).valid is False
    # Skipping signature does not rescue a malformed token (I14).
    assert flawed.flawed_skip_signature("not.a.jwt", jwks=jwks, **CTX).valid is False


def test_flawed_expiry_allows_expired_but_rejects_tampered():
    pem, jwks = _setup()
    expired = mint_id_token(private_pem=pem, expires_in=-300)
    assert flawed.flawed_skip_expiry(expired, jwks=jwks, **CTX).valid is True
    tampered = mint_id_token(private_pem=pem, tamper=True)
    assert flawed.flawed_skip_expiry(tampered, jwks=jwks, **CTX).valid is False


def test_flawed_nonce_allows_wrong_nonce_but_rejects_wrong_aud():
    pem, jwks = _setup()
    wrong_nonce = mint_id_token(private_pem=pem, nonce="someone-elses-nonce")
    assert flawed.flawed_skip_nonce(wrong_nonce, jwks=jwks, **CTX).valid is True
    wrong_aud = mint_id_token(private_pem=pem, audience="other-client")
    assert flawed.flawed_skip_nonce(wrong_aud, jwks=jwks, **CTX).valid is False


def test_azp_mismatch_rejected_for_multi_audience_token():
    pem, jwks = _setup()
    token = mint_id_token(
        private_pem=pem,
        audience=[CLIENT_ID, "other-client"],
        extra_claims={"azp": "other-client"},
    )
    dec = validate_id_token(token, jwks=jwks, **CTX)
    assert dec.valid is False
    assert dec.reason_code.value == "WRONG_AUDIENCE"
