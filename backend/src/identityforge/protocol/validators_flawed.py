"""OFFLINE-ONLY flawed ID-token validator — research fixture, NEVER production.

WARNING: :func:`validate_id_token_flawed` deliberately omits EXACTLY ONE
security check (``omit={"signature"|"issuer"|"audience"|"expiry"|"nonce"|
"algorithm"|"subject"}``) so the offline scenario engine can show *why*
that check matters: the flawed validator runs the full secure validation
with a single check omitted, so a comparison isolates the omitted check
instead of returning a stub that always allows.

This module is imported ONLY by ``scenarios/flawed.py`` and offline
tests. It is NEVER imported by ``api/app.py`` or any live-portal code
path, NEVER exposed via HTTP, NEVER toggleable by configuration, and
must never be copied into production code. Separation is proven by
``tests/security/test_validator_separation.py`` (signature inspection,
import-closure walk, static grep of ``api/``).

The audience/azp policy itself is shared with production via
``validators.check_audience_policy`` (imported, not duplicated), so the
strict lab policy cannot drift — only its *omission* is fixture-only.
This module is a research copy of the production validator's decode
flow; its behaviour is pinned by ``tests/protocol/
test_flawed_one_check.py`` and the 18 offline scenarios.
"""

from __future__ import annotations

import time
from typing import Any

import jwt

from ..models import FailureReason, ValidationCheck, ValidationDecision
from .jwks import parse_jwks
from .validators import ALLOWED_ALGORITHMS, _check, check_audience_policy


def validate_id_token_flawed(
    token: str | None,
    *,
    jwks: dict | None,
    expected_issuer: str,
    expected_audience: str,
    expected_nonce: str | None = None,
    clock_skew_seconds: int = 120,
    now: float | None = None,
    omit: frozenset[str],
) -> ValidationDecision:
    """Full validation with exactly one named check omitted (offline only).

    ``omit`` must name exactly one check. The caller is a flawed
    fixture; the secure path never calls this function.
    """
    omitted = omit or frozenset()
    checks: list[ValidationCheck] = []
    now_s = now if now is not None else time.time()

    def omitted_check(name: str) -> None:
        checks.append(_check(name, True, FailureReason.OK, "check omitted by flawed fixture"))

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
    if alg != "RS256" and "algorithm" not in omitted:
        return fail(
            FailureReason.ALG_NOT_ALLOWED,
            "algorithm",
            f"alg must be RS256, got {alg!r}",
        )
    if "algorithm" in omitted:
        omitted_check("algorithm")
    else:
        checks.append(_check("algorithm", True, FailureReason.OK, "RS256"))

    kid = header.get("kid")
    if not kid:
        return fail(FailureReason.UNKNOWN_KEY, "key_id", "token header has no kid")
    if not jwks:
        return fail(FailureReason.JWKS_ERROR, "jwks", "no JWKS available")
    try:
        keys = parse_jwks(jwks)
    except (ValueError, TypeError) as exc:
        return fail(FailureReason.JWKS_ERROR, "jwks", f"unusable JWKS: {type(exc).__name__}")
    jwk = keys.get(str(kid))
    if jwk is None:
        return fail(FailureReason.UNKNOWN_KEY, "key_id", f"kid {kid!r} not in trusted JWKS")
    checks.append(_check("key_id", True, FailureReason.OK, f"kid {kid} found in JWKS"))

    try:
        key_obj = jwt.PyJWK(jwk).key
    except Exception as exc:
        return fail(FailureReason.JWKS_ERROR, "jwks", f"unusable JWK: {type(exc).__name__}")

    # A flawed fixture omitting "signature" decodes without verification
    # (and still runs every other check); the secure path never does this.
    verify_sig = "signature" not in omitted
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            key_obj if verify_sig else "",
            algorithms=list(ALLOWED_ALGORITHMS) if verify_sig else ["RS256", "HS256", "none"],
            options={
                "verify_signature": verify_sig,
                "verify_exp": "expiry" not in omitted,
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

    if "signature" in omitted:
        omitted_check("signature")
    else:
        checks.append(_check("signature", True, FailureReason.OK, "RS256 signature valid"))

    iss = claims.get("iss")
    if iss != expected_issuer and "issuer" not in omitted:
        return fail(FailureReason.WRONG_ISSUER, "issuer", f"iss {iss!r} != expected issuer")
    if "issuer" in omitted:
        omitted_check("issuer")
    else:
        checks.append(_check("issuer", True, FailureReason.OK, "issuer matches allowlist"))

    aud = claims.get("aud")
    azp = claims.get("azp")
    if "audience" not in omitted:
        aud_failure = check_audience_policy(aud, azp, expected_audience)
        if aud_failure is not None:
            return fail(
                aud_failure,
                "audience",
                f"aud {aud!r} / azp {azp!r} do not satisfy lab policy",
            )
        checks.append(_check("audience", True, FailureReason.OK, "audience matches client_id"))
        if azp is not None:
            checks.append(_check("azp", True, FailureReason.OK, "azp matches client_id"))
    else:
        omitted_check("audience")

    exp = claims.get("exp")
    if (
        not isinstance(exp, (int, float)) or exp + clock_skew_seconds < now_s
    ) and "expiry" not in omitted:
        return fail(FailureReason.EXPIRED, "expiry", "exp claim is in the past")
    if "expiry" in omitted:
        omitted_check("expiry")
    else:
        checks.append(_check("expiry", True, FailureReason.OK, "token not expired"))

    sub = claims.get("sub")
    if (not sub or not isinstance(sub, str)) and "subject" not in omitted:
        return fail(FailureReason.MISSING_CLAIM, "subject", "sub claim missing")
    if "subject" in omitted:
        omitted_check("subject")
    else:
        checks.append(_check("subject", True, FailureReason.OK, "sub present"))

    if expected_nonce is not None:
        if claims.get("nonce") != expected_nonce and "nonce" not in omitted:
            return fail(
                FailureReason.NONCE_MISMATCH,
                "nonce",
                "nonce does not match the login transaction",
            )
        if "nonce" in omitted:
            omitted_check("nonce")
        else:
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
