"""Exact redirect-URI allowlist comparison (I4).

OAuth redirect URIs must be compared exactly — no prefix matching, no
trailing-slash tolerance, no extra query/path forgiveness. A look-alike
URI (different host, extra path, added query) must be rejected, because
an authorization code sent to the wrong destination is a code leak.
"""

from __future__ import annotations

from ..models import FailureReason


def is_allowed_redirect_uri(uri: str | None, allowed: tuple[str, ...] | list[str]) -> bool:
    if not uri or not isinstance(uri, str):
        return False
    if len(uri) > 2048:
        return False
    # Exact, case-sensitive string equality against the registered list.
    return uri in set(allowed)


def check_redirect_uri(uri: str | None, allowed: tuple[str, ...] | list[str]) -> FailureReason:
    return (
        FailureReason.OK
        if is_allowed_redirect_uri(uri, allowed)
        else FailureReason.REDIRECT_URI_MISMATCH
    )
