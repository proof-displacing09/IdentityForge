"""Isolated FLAWED validators — educational fixtures ONLY.

WARNING: every function in this module deliberately omits EXACTLY ONE
security check (P1-11) so a scenario can show *why* that check matters.
Each flawed validator runs the full secure validation with a single
check omitted (see ``validators_flawed.validate_id_token_flawed``) —
signature, issuer, audience, expiry, nonce and all other checks still
run, so the comparison isolates the omitted check instead of returning
a stub that always allows. They are pure functions used only by the
offline scenario engine (scenarios/engine.py) and tests. They are NEVER
exposed via HTTP, NEVER used by the portal login flow, NEVER toggleable
by configuration, and must never be copied into production code.

Checks that are a whole decision on their own (state binding, PKCE,
redirect-URI exactness, CSRF, issuer-URL trust) have no other check to
preserve: for those, the flawed variant is the omission of that one
predicate, and the engine labels it as such. A variant that cannot be
modelled as a single omission is reported NOT MODELED, never ALLOW.
"""

from __future__ import annotations

from ..models import ValidationDecision
from ..protocol.validators_flawed import validate_id_token_flawed


def _flawed_token(
    token: str,
    omit: str,
    *,
    jwks: dict | None = None,
    expected_issuer: str = "",
    expected_audience: str = "",
    expected_nonce: str | None = None,
) -> ValidationDecision:
    """Run full validation with exactly one check omitted."""
    return validate_id_token_flawed(
        token,
        jwks=jwks,
        expected_issuer=expected_issuer,
        expected_audience=expected_audience,
        expected_nonce=expected_nonce,
        omit=frozenset({omit}),
    )


def flawed_skip_audience(token: str, **kwargs: object) -> ValidationDecision:
    """Flawed (I6): full validation except audience."""
    return _flawed_token(token, "audience", **kwargs)  # type: ignore[arg-type]


def flawed_skip_issuer(token: str, **kwargs: object) -> ValidationDecision:
    """Flawed (I5): full validation except issuer."""
    return _flawed_token(token, "issuer", **kwargs)  # type: ignore[arg-type]


def flawed_skip_nonce(token: str, **kwargs: object) -> ValidationDecision:
    """Flawed (I8): full validation except nonce."""
    return _flawed_token(token, "nonce", **kwargs)  # type: ignore[arg-type]


def flawed_skip_signature(token: str, **kwargs: object) -> ValidationDecision:
    """Flawed (I9): full validation except signature verification."""
    return _flawed_token(token, "signature", **kwargs)  # type: ignore[arg-type]


def flawed_skip_expiry(token: str, **kwargs: object) -> ValidationDecision:
    """Flawed (I7): full validation except expiry."""
    return _flawed_token(token, "expiry", **kwargs)  # type: ignore[arg-type]


def flawed_skip_state(state: str | None, expected: str | None, **_: object) -> bool:
    """Flawed (I2): accepts any/missing state. State binding IS the check
    being omitted here, so there is no further check to preserve."""
    return True


def flawed_skip_pkce(verifier: str, challenge: str, **_: object) -> bool:
    """Flawed (I3): accepts any PKCE verifier. The verifier check IS the
    check being omitted here."""
    return True


def flawed_skip_redirect(uri: str, **_: object) -> bool:
    """Flawed (I4): accepts any redirect URI. Exact-match IS the check."""
    return True


def flawed_trust_token_roles(token_claims: dict, **_: object) -> list[str]:
    """Flawed (I13): trusts role claims inside the token instead of the
    server-side policy map."""
    roles = token_claims.get("roles") or token_claims.get("role") or []
    return [roles] if isinstance(roles, str) else list(roles)


def flawed_skip_csrf(**_: object) -> bool:
    """Flawed (I16): no CSRF check."""
    return True


def flawed_accept_any_url(url: str, **_: object) -> bool:
    """Flawed (I18): trusts any issuer/JWKS URL."""
    return True


# Re-export a registry so the engine can name the flaw it exercised.
FLAWED_VARIANTS: dict[str, str] = {
    "I2": "flawed_skip_state",
    "I3": "flawed_skip_pkce",
    "I4": "flawed_skip_redirect",
    "I5": "flawed_skip_issuer",
    "I6": "flawed_skip_audience",
    "I7": "flawed_skip_expiry",
    "I8": "flawed_skip_nonce",
    "I9": "flawed_skip_signature",
    "I13": "flawed_trust_token_roles",
    "I16": "flawed_skip_csrf",
    "I18": "flawed_accept_any_url",
}
