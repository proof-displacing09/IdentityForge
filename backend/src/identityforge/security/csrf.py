"""CSRF protection: double-submit token + Origin check (I16).

State-changing browser requests (logout, lab reset) must carry a token
that matches the cookie value AND come from an allowed loopback origin
when an Origin header is present. API clients without a browser origin
still need the double-submit token for these endpoints.
"""

from __future__ import annotations

import secrets
from urllib.parse import urlparse

from fastapi import Request

from ..config import Settings
from ..models import FailureReason


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def rotate_csrf_token() -> str:
    """Mint a fresh token (used after reset/logout, when prior browser
    state is deliberately discarded)."""
    return secrets.token_urlsafe(32)


def _token_well_formed(token: str | None) -> bool:
    if not token or not isinstance(token, str):
        return False
    if not 16 <= len(token) <= 128:
        return False
    return all(c.isalnum() or c in "-_" for c in token)


def get_or_mint_csrf_token(request: Request) -> str:
    """Deterministic CSRF lifecycle (P0-02): the token is stable per
    browser until explicitly rotated. If the browser already carries a
    well-formed identityforge_csrf cookie, return THAT value (and re-set
    the same cookie) instead of minting a new one — so a second tab, a
    navigation, or a config fetch can never silently invalidate the
    token another tab cached. Only mint when no usable cookie exists."""
    existing = request.cookies.get("identityforge_csrf")
    if _token_well_formed(existing):
        return existing  # type: ignore[return-value]
    return new_csrf_token()


def _origin_allowed(origin: str | None, settings: Settings) -> bool:
    if not origin:
        return True  # non-browser client; double-submit token still required
    return origin.rstrip("/") in {o.rstrip("/") for o in settings.allowed_origins}


def verify_csrf(request: Request, settings: Settings) -> FailureReason:
    """Check Origin/Referer and double-submit token. Returns OK or CSRF_DENIED."""
    origin = request.headers.get("origin")
    if origin and not _origin_allowed(origin, settings):
        return FailureReason.CSRF_DENIED
    referer = request.headers.get("referer")
    if referer:
        parsed = urlparse(referer)
        ref_origin = f"{parsed.scheme}://{parsed.netloc}"
        if not _origin_allowed(ref_origin, settings):
            return FailureReason.CSRF_DENIED
    cookie_token = request.cookies.get("identityforge_csrf")
    header_token = request.headers.get("x-csrf-token")
    if not cookie_token or not header_token:
        return FailureReason.CSRF_DENIED
    if not secrets.compare_digest(cookie_token, header_token):
        return FailureReason.CSRF_DENIED
    return FailureReason.OK
