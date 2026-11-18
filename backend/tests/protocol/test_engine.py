"""Protocol/engine: every scenario I1–I18 runs and compares secure vs flawed."""

from __future__ import annotations

import pytest

from identityforge.models import FailureReason
from identityforge.scenarios.definitions import BY_ID
from identityforge.scenarios.engine import list_scenarios, run_all, run_scenario

ALL_IDS = sorted(BY_ID)


def test_all_18_definitions_present():
    assert len(BY_ID) == 18
    assert set(BY_ID) == {f"I{i}" for i in range(1, 19)}
    assert len(list_scenarios()) == 18


@pytest.mark.parametrize("sid", ALL_IDS)
def test_every_scenario_passes_offline(sid):
    result = run_scenario(sid)
    assert result.status == "PASS", (
        f"{sid}: secure={result.secure_result} reason={result.secure_reason}"
    )
    assert result.mode == "DETERMINISTIC OFFLINE FIXTURE"
    assert result.run_id.startswith("run-")
    assert result.elapsed_ms >= 0
    assert result.reproducibility is not None


def test_i1_member_yes_officer_no():
    r = run_scenario("I1")
    assert r.secure_session_created is True
    assert r.resource_access == {"member": True, "officer": False}


def test_i2_i3_i4_secure_rejects_flawed_allows():
    for sid, reason in (
        ("I2", FailureReason.STATE_MISMATCH),
        ("I3", FailureReason.PKCE_MISMATCH),
        ("I4", FailureReason.REDIRECT_URI_MISMATCH),
    ):
        r = run_scenario(sid)
        assert r.secure_reason == reason, sid
        assert r.secure_session_created is False, sid
        assert r.flawed_session_created is True, sid


def test_i5_i6_token_reasons():
    assert run_scenario("I5").secure_reason == FailureReason.WRONG_ISSUER
    assert run_scenario("I6").secure_reason == FailureReason.WRONG_AUDIENCE


def test_i7_expired_and_replay():
    r = run_scenario("I7")
    assert r.secure_reason == FailureReason.EXPIRED
    assert any(s.reason_code == FailureReason.STATE_REUSED for s in r.timeline)


def test_i8_i9_reasons():
    assert run_scenario("I8").secure_reason == FailureReason.NONCE_MISMATCH
    assert run_scenario("I9").secure_reason == FailureReason.BAD_SIGNATURE


def test_i10_exactly_one_redemption():
    r = run_scenario("I10")
    assert r.status == "PASS"
    assert any(s.reason_code == FailureReason.CODE_REUSED for s in r.timeline)


def test_i11_rotation_and_i12_logout():
    assert run_scenario("I11").status == "PASS"
    r12 = run_scenario("I12")
    assert r12.resource_access.get("member_after_logout") is False


def test_i13_officer_denied_but_flawed_would_allow():
    r = run_scenario("I13")
    assert r.resource_access["officer"] is False
    assert r.resource_access["officer_via_spoofed_claim"] is True
    assert r.secure_reason == FailureReason.POLICY_DENIED


def test_i15_i16_i17_i18_reasons():
    assert run_scenario("I15").secure_reason == FailureReason.CALLBACK_MALFORMED
    assert run_scenario("I16").secure_reason == FailureReason.CSRF_DENIED
    assert run_scenario("I17").secure_reason == FailureReason.INPUT_TOO_LONG
    assert run_scenario("I18").secure_reason in (
        FailureReason.SSRF_BLOCKED,
        FailureReason.UNTRUSTED_ISSUER_URL,
    )


def test_verify_all_runs_18():
    results = run_all()
    assert len(results) == 18
    assert all(r.status == "PASS" for r in results)


def test_unknown_scenario_raises():
    with pytest.raises(ValueError):
        run_scenario("I99")


def test_run_is_repeatable_and_fresh_keys():
    a, b = run_scenario("I1"), run_scenario("I1")
    assert a.run_id != b.run_id
    assert a.status == b.status == "PASS"
