"""Typed configuration for IdentityForge backend.

Settings are read from environment variables (pydantic-settings style,
implemented without that extra dependency so the pinned lockfile stays
small). Defaults are loopback-only lab values; nothing here enables a
production deployment. See docs/ARCHITECTURE.md for the trust boundary.
"""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel, field_validator


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


class Settings(BaseModel):
    """All backend configuration. Safe defaults; overrides via env only."""

    model_config = {"frozen": True}

    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    frontend_url: str = "http://127.0.0.1:5173"
    issuer: str = "http://127.0.0.1:8080/realms/identityforge-lab"
    # Canonical issuer (above) is the identity in tokens/discovery. The
    # transport base is only the network route the backend uses to reach
    # Keycloak: loopback on a host dev machine, keycloak:8080 (service
    # DNS) in Compose. Never substitute the transport host for the
    # issuer (P0-03).
    idp_transport_base: str = "http://127.0.0.1:8080"
    client_id: str = "campus-club-portal"
    client_secret: str = ""  # public lab client; never a real secret
    redirect_uri: str = "http://127.0.0.1:8000/auth/callback"
    allowed_redirect_uris: tuple[str, ...] = ("http://127.0.0.1:8000/auth/callback",)
    allowed_issuers: tuple[str, ...] = ("http://127.0.0.1:8080/realms/identityforge-lab",)
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost", "testserver")
    allowed_origins: tuple[str, ...] = (
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
        "http://localhost:5173",
        "http://localhost:8000",
    )
    clock_skew_seconds: int = 120
    session_ttl_seconds: int = 1800  # 30 minutes
    transaction_ttl_seconds: int = 600  # 10 minutes
    max_request_bytes: int = 1_048_576  # 1 MiB
    max_input_chars: int = 2048
    db_path: str = "data/identityforge.db"
    fixture_revision: str = "1.0.0"
    provider_mode: str = "keycloak-local"  # or "offline-fixture"
    environment: str = "lab-local-http"  # NOT production; see SECURITY.md

    @field_validator("clock_skew_seconds")
    @classmethod
    def _skew_bounded(cls, v: int) -> int:
        if not 0 <= v <= 300:
            raise ValueError("clock_skew_seconds must be 0..300")
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Build Settings from the environment (cached; callers may pass their own)."""
    return Settings(
        backend_host=_env("IDENTITYFORGE_HOST", "127.0.0.1"),
        backend_port=_env_int("IDENTITYFORGE_PORT", 8000),
        frontend_url=_env("IDENTITYFORGE_FRONTEND_URL", "http://127.0.0.1:5173"),
        issuer=_env(
            "IDENTITYFORGE_ISSUER",
            "http://127.0.0.1:8080/realms/identityforge-lab",
        ),
        idp_transport_base=_env("IDENTITYFORGE_IDP_TRANSPORT_BASE", "http://127.0.0.1:8080"),
        client_id=_env("IDENTITYFORGE_CLIENT_ID", "campus-club-portal"),
        client_secret=_env("IDENTITYFORGE_CLIENT_SECRET", ""),
        redirect_uri=_env("IDENTITYFORGE_REDIRECT_URI", "http://127.0.0.1:8000/auth/callback"),
        clock_skew_seconds=_env_int("IDENTITYFORGE_CLOCK_SKEW", 120),
        session_ttl_seconds=_env_int("IDENTITYFORGE_SESSION_TTL", 1800),
        db_path=_env("IDENTITYFORGE_DB_PATH", "data/identityforge.db"),
        provider_mode=_env("IDENTITYFORGE_PROVIDER_MODE", "keycloak-local"),
    )


def public_config(settings: Settings | None = None) -> dict[str, object]:
    """Safe public metadata only — never secrets, keys, or session data."""
    s = settings or get_settings()
    return {
        "issuer": s.issuer,
        "client_id": s.client_id,
        "redirect_uri": s.redirect_uri,
        "frontend_url": s.frontend_url,
        "provider_mode": s.provider_mode,
        "environment": s.environment,
        "fixture_revision": s.fixture_revision,
        "clock_skew_seconds": s.clock_skew_seconds,
        "session_ttl_seconds": s.session_ttl_seconds,
        "synthetic_data_label": "SYNTHETIC LAB DATA — NOT REAL IDENTITY INFORMATION",
        "https_note": (
            "Local HTTP is a localhost development exception only; "
            "production use requires HTTPS, Secure cookies and a real IdP."
        ),
    }
