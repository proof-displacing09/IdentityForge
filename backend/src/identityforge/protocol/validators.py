"""ID-token validation (OIDC Core / RFC 8725 subset, lab profile).

PRODUCTION validator — closed interface. There is deliberately NO
``omit`` / bypass / test-hook parameter on :func:`validate_id_token`:
every check below always runs on the live portal path. One-check
omission research lives in the separate offline-only module
``protocol.validators_flawed`` (imported only by the offline scenario
engine and its tests); the live API cannot import or invoke it, and no
environment flag, query parameter, form field or toggle can enable a
flawed validator on the portal. See ``tests/security/
test_validator_separation.py`` for the separation proofs.

Uses PyJWT + cryptography — no hand-rolled signatures. Checks, in order:
  1. token is a well-formed 3-part JWT, header alg is exactly RS256
     (alg=none, HS256 and algorithm confusion are rejected);
  2. kid resolves to a key in the trusted JWKS (never from a token-supplied URL);
  3. signature verifies against that key;
  4. iss is exactly the allowlisted issuer;
  5. aud satisfies the strict lab audience policy (see
     :func:`check_audience_policy`): every audience value must be the
     registered client_id, multi-audience tokens require azp == client_id,
     and any present azp must equal client_id;
  6. exp / iat / nbf are valid within bounded clock skew;
  7. sub is present; nonce matches the transaction nonce when one is expected.

Every failure returns a structured ValidationDecision with a stable
reason code — never an exception or stack trace to the caller.
"""

from __future__ import annotations

import time
from typing import Any

import jwt
from jwt import PyJWKClient  # noqa: F401  (re-exported for callers that need it)

from ..models import FailureReason, ValidationCheck, ValidationDecision
from .jwks import parse_jwks

ALLOWED_ALGORITHMS = ("RS256",)


def _check(name: str, passed: bool, reason: FailureReason, detail: str = "") -> ValidationCheck:
    return ValidationCheck(name=name, passed=passed, reason_code=reason, detail=detail)


def check_audience_policy(aud: Any, azp: Any, expected_audience: str) -> FailureReason | None:
    """Strict lab audience / azp policy (P1-08; OIDC Core §3.1.3.7, §2).

    This lab has exactly one registered client, so the policy is
    deliberately stricter than the OIDC minimum (which only requires
    the client to be *among* the audiences and azp to match when
    multiple audiences are present):

    * ``aud`` must be a nonempty string or a list of distinct nonempty
      strings; any other type/shape is rejected.
    * EVERY audience value must equal ``expected_audience`` — an
      unapproved extra audience is never accepted just because the
      client also appears.
    * If ``aud`` is a list with more than one element, ``azp`` is
      REQUIRED and must equal ``expected_audience``.
    * If ``azp`` is present at all, it must equal ``expected_audience``.

    Returns ``None`` when the claims satisfy the policy, otherwise the
    ``WRONG_AUDIENCE`` reason to fail with. The offline flawed module
    reuses this helper for its non-omitted path so the policy cannot
    drift between the two validators.
    """
    if isinstance(aud, str):
        aud_values = [aud]
    elif isinstance(aud, list):
        aud_values = aud
    else:
        return FailureReason.WRONG_AUDIENCE
    if not aud_values:
        return FailureReason.WRONG_AUDIENCE
    if any(not isinstance(v, str) or not v for v in aud_values):
        return FailureReason.WRONG_AUDIENCE
    if len(set(aud_values)) != len(aud_values):
        return FailureReason.WRONG_AUDIENCE
    if any(v != expected_audience for v in aud_values):
        return FailureReason.WRONG_AUDIENCE
    if len(aud_values) > 1 and azp != expected_audience:
        return FailureReason.WRONG_AUDIENCE
    if azp is not None and azp != expected_audience:
        return FailureReason.WRONG_AUDIENCE
    return None


def validate_id_token(
    token: str | None,
    *,
    jwks: dict | None,
    expected_issuer: str,
    expected_audience: str,
    expected_nonce: str | None = None,
    clock_skew_seconds: int = 120,
    now: float | None = None,
) -> ValidationDecision:
    """Validate an ID token against the pinned issuer/audience/JWKS.

    Closed interface: there is no way for any caller to skip a check.
    Every check runs, in order; the first failure short-circuits with
    its stable reason code.
    """
    checks: list[ValidationCheck] = []
    now_s = now if now is not None else time.time()

    def fail(reason: FailureReason, name: str, detail: str = "") -> ValidationDecision:
        checks.append(_check(name, False, reason, detail))
        return ValidationDecision(valid=False, reason_code=reason, checks=checks)

    if not token or not isinstance(token, str) or token.count(".") != 2:
        return fail(FailureReason.MALFORMED_TOKEN, "token_structure", "token is not a 3-part JWT")
    if len(token) > 8192:
        return fail(FailureReason.MALFORMED_TOKEN, "token_structure", "token exceeds size limit")

    try:
        header = jwt.get_unverified_header(token)
    except Exception as exc:  # malformed header
        return fail(
            FailureReason.MALFORMED_TOKEN,
            "token_header",
            f"unreadable header: {type(exc).__name__}",
        )

    alg = header.get("alg")
    if alg != "RS256":
        return fail(
            FailureReason.ALG_NOT_ALLOWED,
            "algorithm",
            f"alg must be RS256, got {alg!r}",
        )
    checks.append(_check("algorithm", True, FailureReason.OK, "RS256"))

    kid = header.get("kid")
    if not kid:
        return fail(FailureReason.UNKNOWN_KEY, "key_id", "token header has no kid")
    if not jwks:
        return fail(FailureReason.JWKS_ERROR, "jwks", "no JWKS available")
    try:
        keys = parse_jwks(jwks)
    except (ValueError, TypeError) as exc:
        # P1-07: malformed upstream key material is a controlled
        # JWKS_ERROR, never a 500/traceback. The message carries the
        # failure class only — parse_jwks never includes key material.
        return fail(FailureReason.JWKS_ERROR, "jwks", f"unusable JWKS: {type(exc).__name__}")
    jwk = keys.get(str(kid))
    if jwk is None:
        return fail(FailureReason.UNKNOWN_KEY, "key_id", f"kid {kid!r} not in trusted JWKS")
    checks.append(_check("key_id", True, FailureReason.OK, f"kid {kid} found in JWKS"))

    try:
        key_obj = jwt.PyJWK(jwk).key
    except Exception as exc:
        return fail(FailureReason.JWKS_ERROR, "jwks", f"unusable JWK: {type(exc).__name__}")

    # Signature + registered claims, verified by PyJWT. We verify iss/aud
    # ourselves afterwards so the reason code distinguishes them.
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            key_obj,
            algorithms=list(ALLOWED_ALGORITHMS),
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iat": True,
                "verify_nbf": True,
                "verify_aud": False,
                "verify_iss": False,
                "require": ["exp", "iat", "iss", "aud", "sub"],
            },
            leeway=clock_skew_seconds,
        )
    except jwt.ExpiredSignatureError:
        return fail(FailureReason.EXPIRED, "expiry", "token is expired")
    except jwt.ImmatureSignatureError:
        return fail(FailureReason.NOT_YET_VALID, "not_before", "token not yet valid")
    except jwt.InvalidSignatureError:
        return fail(FailureReason.BAD_SIGNATURE, "signature", "signature verification failed")
    except jwt.MissingRequiredClaimError as exc:
        return fail(FailureReason.MISSING_CLAIM, "required_claims", str(exc))
    except jwt.InvalidTokenError as exc:
        return fail(FailureReason.MALFORMED_TOKEN, "token", f"{type(exc).__name__}: {exc}")

    checks.append(_check("signature", True, FailureReason.OK, "RS256 signature valid"))

    iss = claims.get("iss")
    if iss != expected_issuer:
        return fail(FailureReason.WRONG_ISSUER, "issuer", f"iss {iss!r} != expected issuer")
    checks.append(_check("issuer", True, FailureReason.OK, "issuer matches allowlist"))

    aud = claims.get("aud")
    azp = claims.get("azp")
    aud_failure = check_audience_policy(aud, azp, expected_audience)
    if aud_failure is not None:
        return fail(aud_failure, "audience", f"aud {aud!r} / azp {azp!r} do not satisfy lab policy")
    checks.append(_check("audience", True, FailureReason.OK, "audience matches client_id"))
    if azp is not None:
        checks.append(_check("azp", True, FailureReason.OK, "azp matches client_id"))

    exp = claims.get("exp")
    if not isinstance(exp, (int, float)) or exp + clock_skew_seconds < now_s:
        return fail(FailureReason.EXPIRED, "expiry", "exp claim is in the past")
    checks.append(_check("expiry", True, FailureReason.OK, "token not expired"))

    sub = claims.get("sub")
    if not sub or not isinstance(sub, str):
        return fail(FailureReason.MISSING_CLAIM, "subject", "sub claim missing")
    checks.append(_check("subject", True, FailureReason.OK, "sub present"))

    if expected_nonce is not None:
        if claims.get("nonce") != expected_nonce:
            return fail(
                FailureReason.NONCE_MISMATCH,
                "nonce",
                "nonce does not match the login transaction",
            )
        checks.append(_check("nonce", True, FailureReason.OK, "nonce matches transaction"))

    summary = {
        "iss": iss,
        "aud": expected_audience,
        "sub": sub,
        "exp": exp,
        "iat": claims.get("iat"),
    }
    return ValidationDecision(
        valid=True,
        reason_code=FailureReason.OK,
        checks=checks,
        subject=str(sub),
        issuer=str(iss),
        audience=expected_audience,
        claims_summary=summary,
    )
