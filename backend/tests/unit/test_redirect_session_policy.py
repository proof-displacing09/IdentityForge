"""Unit: redirect exactness, sessions, policy, redaction, CSRF, JWKS guard."""

from __future__ import annotations

from identityforge.models import FailureReason, LabRole
from identityforge.protocol.jwks import parse_jwks, validate_issuer_url, validate_jwks_url
from identityforge.protocol.redirect import check_redirect_uri, is_allowed_redirect_uri
from identityforge.scenarios.fixtures import EXPECTED_ISSUER, roles_for_fixture_subject
from identityforge.security.policy import (
    OFFICER_SUB,
    STUDENT_SUB,
    can_access,
    lookup_subject,
    roles_for_subject,
)
from identityforge.security.redaction import canonical_hash, redact_dict, sanitize_log_value
from identityforge.security.session import SessionStore

ALLOWED = ("http://127.0.0.1:8000/auth/callback",)


def test_redirect_exact_match_only():
    assert is_allowed_redirect_uri("http://127.0.0.1:8000/auth/callback", ALLOWED) is True
    for bad in (
        "http://127.0.0.1:8000/auth/callback/",
        "http://127.0.0.1:8000/auth/callback?next=/evil",
        "http://127.0.0.1:8000/auth/callback/evil",
        "http://evil.example/auth/callback",
        "http://127.0.0.1:8000/auth/callback%2Fevil",
        None,
        "",
    ):
        assert is_allowed_redirect_uri(bad, ALLOWED) is False
    assert (
        check_redirect_uri("http://evil.example/", ALLOWED) == FailureReason.REDIRECT_URI_MISMATCH
    )


def test_session_create_get_revoke():
    store = SessionStore()
    rec = store.create(
        subject="student_01", username="student_01", roles=[LabRole.MEMBER], issuer=EXPECTED_ISSUER
    )
    assert store.get(rec.session_id) is not None
    assert store.revoke(rec.session_id) is True
    assert store.get(rec.session_id) is None
    assert store.revoke("no-such-id") is False


def test_session_rotation_revokes_old_id():
    store = SessionStore()
    old = store.create(
        subject="student_01", username="student_01", roles=[LabRole.MEMBER], issuer=EXPECTED_ISSUER
    )
    new = store.rotate(
        old_session_id=old.session_id,
        subject="student_01",
        username="student_01",
        roles=[LabRole.MEMBER],
        issuer=EXPECTED_ISSUER,
    )
    assert new.session_id != old.session_id
    assert store.get(old.session_id) is None
    assert store.get(new.session_id) is not None


def test_session_expired_denied():
    store = SessionStore(ttl_seconds=-1)
    rec = store.create(
        subject="student_01", username="student_01", roles=[LabRole.MEMBER], issuer=EXPECTED_ISSUER
    )
    assert store.get(rec.session_id) is None


def test_policy_member_vs_officer():
    """P1-10 (v3): the LIVE policy is keyed by pinned UUIDs only.
    Fixture subject names are NOT live subjects: a token carrying
    sub="student_01"/"officer_01" gets no live roles (UNKNOWN_SUBJECT
    at the callback). The offline fixture mapping is tested below."""
    assert roles_for_subject(STUDENT_SUB) == [LabRole.MEMBER]
    assert LabRole.OFFICER in roles_for_subject(OFFICER_SUB)
    assert roles_for_subject("unknown-sub") == []
    assert roles_for_subject("student_01") == []
    assert roles_for_subject("officer_01") == []
    assert lookup_subject("officer_01") is None
    assert lookup_subject("student_01") is None
    assert lookup_subject(STUDENT_SUB, issuer="http://127.0.0.1:8080/realms/evil-lab") is None
    store = SessionStore()
    student = store.create(
        subject=STUDENT_SUB,
        username="student_01",
        roles=roles_for_subject(STUDENT_SUB),
        issuer=EXPECTED_ISSUER,
    )
    officer = store.create(
        subject=OFFICER_SUB,
        username="officer_01",
        roles=roles_for_subject(OFFICER_SUB),
        issuer=EXPECTED_ISSUER,
    )
    assert can_access(student, "member") is True
    assert can_access(student, "officer") is False
    assert can_access(officer, "officer") is True
    assert can_access(None, "member") is False
    assert can_access(student, "nonexistent-resource") is False


def test_fixture_roles_are_offline_only():
    """P1-10 (v3): fixture subject names map to roles ONLY in the
    offline fixture module — never through the live policy."""
    assert roles_for_fixture_subject("student_01") == [LabRole.MEMBER]
    assert LabRole.OFFICER in roles_for_fixture_subject("officer_01")
    assert roles_for_fixture_subject("unknown-sub") == []
    assert roles_for_fixture_subject("student_01") != roles_for_subject("student_01")


def test_redaction_removes_secrets():
    data = {
        "id_token": "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxIn0.sig",
        "username": "student_01",
        "code_verifier": "secret-verifier",
    }
    redacted = redact_dict(data)
    assert "secret-verifier" not in str(redacted)
    assert "eyJhbGciOiJSUzI1NiJ9" not in str(redacted)
    assert redacted["username"] == "student_01"
    assert "[REDACTED" in redacted["id_token"]


def test_log_injection_sanitized():
    dirty = "student_01\nFAKE: admin logged in\r\nsecond line"
    clean = sanitize_log_value(dirty)
    assert "\n" not in clean and "\r" not in clean
    assert "FAKE" in clean  # content preserved, line breaks escaped


def test_canonical_hash_stable_and_sensitive_to_change():
    assert canonical_hash({"b": 1, "a": 2}) == canonical_hash({"a": 2, "b": 1})
    assert canonical_hash({"a": 1}) != canonical_hash({"a": 2})


def test_jwks_url_ssrf_guard():
    assert (
        validate_jwks_url("http://127.0.0.1:8080/realms/x/protocol/openid-connect/certs")
        == FailureReason.OK
    )
    assert validate_jwks_url("https://evil.example/jwks.json") == FailureReason.SSRF_BLOCKED
    assert (
        validate_jwks_url("http://169.254.169.254/latest/meta-data/") == FailureReason.SSRF_BLOCKED
    )
    assert validate_jwks_url("http://10.0.0.5/jwks") == FailureReason.SSRF_BLOCKED
    assert validate_jwks_url("file:///etc/passwd") == FailureReason.SSRF_BLOCKED


def test_issuer_url_allowlist():
    assert validate_issuer_url(EXPECTED_ISSUER, (EXPECTED_ISSUER,)) == FailureReason.OK
    assert (
        validate_issuer_url("http://127.0.0.1:8080/realms/other", (EXPECTED_ISSUER,))
        == FailureReason.UNTRUSTED_ISSUER_URL
    )
    assert (
        validate_issuer_url("https://evil.example/realms/x", (EXPECTED_ISSUER,))
        == FailureReason.SSRF_BLOCKED
    )


def test_parse_jwks_rejects_bad_documents():
    for bad in ({}, {"keys": []}, {"keys": [{"kty": "RSA"}]}, {"keys": "nope"}):
        try:
            parse_jwks(bad)  # type: ignore[arg-type]
        except ValueError:
            continue
        raise AssertionError(f"parse_jwks should reject {bad!r}")
