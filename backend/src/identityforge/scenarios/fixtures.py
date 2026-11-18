"""Synthetic fixtures: identities and per-run RSA test keys.

SYNTHETIC LAB DATA — NOT REAL IDENTITY INFORMATION.
All identities are made-up (student_01, officer_01). Test passwords are
never stored here; Keycloak realm import (outside this backend) provisions
them on a reviewer's machine. RSA keys are generated fresh at runtime
per scenario run and never written to disk.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from ..models import LabRole, TestIdentity
from ..protocol.jwks import public_jwk_from_private

SYNTHETIC_LABEL = "SYNTHETIC LAB DATA — NOT REAL IDENTITY INFORMATION"

STUDENT = TestIdentity(
    sub="student_01",
    username="student_01",
    display_name="Sam Student (synthetic)",
    roles=[LabRole.MEMBER],
    email="student_01@lab.example",
)
OFFICER = TestIdentity(
    sub="officer_01",
    username="officer_01",
    display_name="Olivia Officer (synthetic)",
    roles=[LabRole.MEMBER, LabRole.OFFICER],
    email="officer_01@lab.example",
)
UNAUTHENTICATED = TestIdentity(
    sub="",
    username="guest",
    display_name="Guest (not signed in)",
    roles=[LabRole.UNAUTHENTICATED],
)

IDENTITIES: dict[str, TestIdentity] = {
    "student_01": STUDENT,
    "officer_01": OFFICER,
}

# OFFLINE-ONLY fixture subject -> roles (P1-10). The offline scenario
# engine mints tokens whose `sub` is a fixture name ("student_01"), not
# a live Keycloak UUID. Those names MUST NOT be live policy subjects:
# the live map (security/policy.py TRUSTED_SUBJECTS) holds exactly the
# two pinned UUIDs. This mapping exists only so the offline engine can
# build local SessionStore records for its simulations; it is never
# consulted by the portal login path or any authorization decision.
FIXTURE_ROLES: dict[str, list[LabRole]] = {
    "student_01": [LabRole.MEMBER],
    "officer_01": [LabRole.MEMBER, LabRole.OFFICER],
}


def roles_for_fixture_subject(subject: str) -> list[LabRole]:
    """Offline-only roles for a fixture subject name. Never a live lookup."""
    return list(FIXTURE_ROLES.get(subject, []))


EXPECTED_ISSUER = "http://127.0.0.1:8080/realms/identityforge-lab"
CLIENT_ID = "campus-club-portal"


def generate_rsa_keypair(kid: str = "lab-key-1") -> tuple[bytes, dict]:
    """Generate a fresh 2048-bit RSA keypair; returns (private PEM, public JWK)."""
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return pem, public_jwk_from_private(pem, kid)


def mint_id_token(
    *,
    private_pem: bytes,
    kid: str = "lab-key-1",
    issuer: str = EXPECTED_ISSUER,
    audience: str = CLIENT_ID,
    subject: str = "student_01",
    nonce: str | None = "test-nonce",
    expires_in: int = 300,
    algorithm: str = "RS256",
    extra_claims: dict | None = None,
    tamper: bool = False,
    now: float | None = None,
) -> str:
    """Mint a synthetic ID token for offline fixture tests only.

    ``tamper=True`` flips a character in the payload after signing so the
    signature no longer matches. ``algorithm="none"`` produces an unsigned
    token (PyJWT will still encode it; the validator must reject it).
    """
    now_s = int(now if now is not None else time.time())
    claims: dict = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "exp": now_s + expires_in,
        "iat": now_s,
        "nbf": now_s - 5,
        "nonce": nonce,
        "auth_time": now_s,
    }
    if extra_claims:
        claims.update(extra_claims)
    if nonce is None:
        claims.pop("nonce", None)
    if algorithm == "none":
        token = jwt.encode(claims, key="", algorithm="none", headers={"kid": kid})
    elif algorithm == "HS256":
        # Algorithm-confusion attempt: sign with a symmetric secret.
        token = jwt.encode(claims, key=b"lab-hmac-secret", algorithm="HS256", headers={"kid": kid})
    else:
        token = jwt.encode(claims, key=private_pem, algorithm=algorithm, headers={"kid": kid})
    if tamper:
        # Corrupt the SIGNATURE segment only: the payload JSON stays
        # readable, so a validator that skips signature verification
        # reads the claims, while a correct validator rejects the
        # signature. (Flipping a payload byte would corrupt the JSON
        # itself, which is a malformed-token case, not a signature case.)
        head, payload, sig = token.split(".")
        flipped = ("A" if sig[0] != "A" else "B") + sig[1:]
        token = f"{head}.{payload}.{flipped}"
    return token


def jwks_for(private_pem: bytes, kid: str = "lab-key-1") -> dict:
    return {"keys": [public_jwk_from_private(private_pem, kid)]}


def new_run_id() -> str:
    return f"run-{uuid.uuid4().hex[:12]}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
