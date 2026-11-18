"""Authorization policy — authentication is NOT authorization.

A validated ID token proves *who* signed in (subject). Whether that
subject may do something is decided here, server-side, from a trusted
policy map keyed by subject (issuer + sub). Role claims inside a token
are never trusted on their own: a token that merely *says* "officer"
does not make a student an officer (I13).
"""

from __future__ import annotations

from ..models import LabRole, SessionRecord

CANONICAL_ISSUER = "http://127.0.0.1:8080/realms/identityforge-lab"
# Pinned synthetic subject IDs (P0-06). Real Keycloak `sub` values are
# stable UUIDs, not usernames; the realm import pins these exact IDs for
# student_01 / officer_01.
STUDENT_SUB = "10000000-0000-4000-8000-000000000001"
OFFICER_SUB = "10000000-0000-4000-8000-000000000002"

# Trusted server-side policy: (issuer, subject) -> (display username, roles).
# LIVE map only: exactly the two pinned UUIDs under the canonical issuer.
# Offline fixture subject names ("student_01"/"officer_01") are NOT live
# subjects and MUST NOT appear here — a provider-issued token carrying
# a fixture-like `sub` must be denied (UNKNOWN_SUBJECT), never inherit
# live roles. Fixture subject->role mappings live in the offline-only
# scenarios/fixtures.py and are used only by the offline engine/tests.
TRUSTED_SUBJECTS: dict[tuple[str, str], tuple[str, list[LabRole]]] = {
    (CANONICAL_ISSUER, STUDENT_SUB): ("student_01", [LabRole.MEMBER]),
    (CANONICAL_ISSUER, OFFICER_SUB): ("officer_01", [LabRole.MEMBER, LabRole.OFFICER]),
}

RESOURCE_ROLES: dict[str, list[LabRole]] = {
    "member": [LabRole.MEMBER, LabRole.OFFICER],
    "officer": [LabRole.OFFICER],
}


def lookup_subject(
    subject: str, issuer: str = CANONICAL_ISSUER
) -> tuple[str, list[LabRole]] | None:
    """Return (display username, roles) for a pinned (issuer, sub), else None."""
    entry = TRUSTED_SUBJECTS.get((issuer, subject))
    if entry is None:
        return None
    username, roles = entry
    return username, list(roles)


def roles_for_subject(subject: str, issuer: str = CANONICAL_ISSUER) -> list[LabRole]:
    found = lookup_subject(subject, issuer)
    return found[1] if found else []


def can_access(session: SessionRecord | None, resource: str) -> bool:
    """Independent authorization check for a protected resource."""
    if session is None or session.revoked:
        return False
    required = RESOURCE_ROLES.get(resource)
    if required is None:
        return False
    return any(role in session.roles for role in required)


def has_role(session: SessionRecord | None, role: LabRole) -> bool:
    return bool(session) and role in (session.roles if session else [])
