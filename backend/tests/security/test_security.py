"""Security/adversarial: SSRF, overlong input, log injection, duplicate callback,
CSRF origin, flawed-fixture isolation, evidence redaction."""

from __future__ import annotations

import pytest

from identityforge.evidence.store import EvidenceStore
from identityforge.models import FailureReason
from identityforge.protocol.jwks import validate_issuer_url, validate_jwks_url
from identityforge.scenarios import flawed
from identityforge.scenarios.engine import run_scenario
from identityforge.security.redaction import sanitize_log_value


def test_ssrf_metadata_and_external_blocked():
    for url in (
        "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
        "http://169.254.170.2/v2/credentials",
        "https://attacker.example/jwks.json",
        "http://192.168.1.10:8080/realms/x",
        "ftp://127.0.0.1/file",
    ):
        assert validate_jwks_url(url) == FailureReason.SSRF_BLOCKED, url
    assert (
        validate_issuer_url("http://169.254.169.254/", ("http://169.254.169.254/",))
        == FailureReason.SSRF_BLOCKED
    )


def test_overlong_input_rejected_by_engine():
    assert run_scenario("I17").secure_reason == FailureReason.INPUT_TOO_LONG


def test_log_injection_never_reaches_raw_log():
    payload = "user\n[2026-01-01] FAKE admin login\n"
    assert "\n" not in sanitize_log_value(payload)


def test_evidence_store_redacts_tokens(tmp_path):
    store = EvidenceStore(str(tmp_path / "ev.db"))
    report = {
        "run_id": "run-test1",
        "scenario_id": "I1",
        "status": "PASS",
        "mode": "DETERMINISTIC OFFLINE FIXTURE",
        "secure_result": "session_created",
        "flawed_result": "allowed",
        "secure_reason": "OK",
        "elapsed_ms": 1,
        "started_at": "2026-11-09T00:00:00Z",
        "timeline": [],
        "id_token": "eyJhbGciOiJSUzI1NiJ9.payload.signature",
    }
    store.save_run(report)
    saved = store.get_run("run-test1")
    assert saved is not None
    assert "eyJhbGciOiJSUzI1NiJ9" not in str(saved)
    assert store.get_events("run-test1") == []


def test_flawed_module_never_used_by_portal():
    # The flawed functions are importable for the engine, but the API app
    # must not reference them anywhere in its route handlers.
    import pathlib

    import identityforge.api.app as app_mod

    source = pathlib.Path(app_mod.__file__).read_text()
    # Reporting the flawed-fixture *result* is fine; importing/using the
    # flawed validators in the portal is not.
    assert "flawed_skip" not in source
    assert "scenarios.flawed" not in source
    assert "from ..scenarios import flawed" not in source


def test_csrf_wrong_origin_denied(client):
    token_resp = client.get("/api/v1/csrf-token")
    token = token_resp.json()["csrf_token"]
    r = client.post(
        "/auth/logout",
        headers={"X-CSRF-Token": token, "Origin": "https://evil.example"},
    )
    assert r.status_code == 403


def test_csrf_mismatched_token_denied(client):
    client.get("/api/v1/csrf-token")
    r = client.post("/auth/logout", headers={"X-CSRF-Token": "not-the-cookie-token"})
    assert r.status_code == 403


def test_duplicate_callback_via_engine():
    assert run_scenario("I15").secure_reason == FailureReason.CALLBACK_MALFORMED


def test_flawed_fixtures_are_marked_and_isolated():
    assert flawed.FLAWED_VARIANTS["I6"] == "flawed_skip_audience"
    # Flawed validators accept what secure rejects — that is their purpose,
    # and they return a ValidationDecision, never a real session. A flawed
    # validator is NOT a stub: it runs the full validation with exactly one
    # check omitted, so a malformed token is still rejected (P1-11).
    assert flawed.flawed_skip_audience("anything").valid is False
    assert flawed.flawed_skip_state(None, "x") is True


@pytest.mark.parametrize("sid", ["I2", "I5", "I6", "I9"])
def test_secure_rejects_flawed_accepts(sid):
    r = run_scenario(sid)
    assert r.secure_session_created is False
    assert r.flawed_session_created is True
    assert r.secure_reason != FailureReason.OK
