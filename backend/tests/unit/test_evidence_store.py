"""Operation Trustline v4 — P1-17 evidence-store transactions and
P1-10/P1-11 live-login retention.

``clear()`` and ``save_run()`` must be explicitly transactional:
a failure mid-write rolls everything back and the caller sees the
failure — no partial deletion or partial run save reported as full
success. ``save_live_event`` already had that discipline (v3 P1-11);
it is re-verified here, plus the v4 retention cap (latest 1000
live-login events, pruned on insert in the same transaction).
"""

from __future__ import annotations

import sqlite3

import pytest

from identityforge.evidence.store import MAX_LIVE_LOGIN_EVENTS, EvidenceStore


class _FailingConn:
    """Connection proxy that raises on the Nth execute() call, so a
    mid-write failure can be injected without touching sqlite3."""

    def __init__(self, conn, fail_on: int):
        self._conn = conn
        self._calls = 0
        self._fail_on = fail_on

    def execute(self, *args, **kwargs):
        self._calls += 1
        if self._calls == self._fail_on:
            raise sqlite3.OperationalError("simulated mid-write failure")
        return self._conn.execute(*args, **kwargs)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()


def _report(run_id="run-1", steps=2):
    return {
        "run_id": run_id,
        "scenario_id": "K1",
        "status": "passed",
        "mode": "SECURE",
        "secure_result": "DENIED",
        "flawed_result": "ALLOWED",
        "secure_reason": "OK",
        "elapsed_ms": 5,
        "started_at": "2026-11-11T00:00:00Z",
        "timeline": [
            {
                "step": f"step-{i}",
                "outcome": "ok",
                "reason_code": "OK",
                "detail": "",
                "at": "2026-11-11T00:00:00Z",
            }
            for i in range(steps)
        ],
    }


def _live_event(corr="corr-1", stage="AUTH_STARTED"):
    return {
        "correlation_id": corr,
        "stage": stage,
        "outcome": "success",
        "reason_code": "OK",
        "subject_hash": "",
        "username": "student_01",
        "detail": "",
        "at": "2026-11-11T00:00:00Z",
    }


@pytest.fixture()
def store(tmp_path):
    return EvidenceStore(db_path=str(tmp_path / "evidence.db"))


def test_save_run_is_atomic_on_mid_write_failure(store):
    """P1-17: a failure on the first events insert leaves NO run row
    and NO events — the caller sees the failure, not a partial save."""
    store._conn = _FailingConn(store._conn, fail_on=2)  # 1st = DELETE events, 2nd = runs insert
    with pytest.raises(sqlite3.OperationalError):
        store.save_run(_report())
    assert store.get_run("run-1") is None
    assert store.get_events("run-1") == []
    assert store.counts()["runs"] == 0


def test_save_run_succeeds_normally(store):
    """The same report saves fully when nothing fails (sanity: the
    try/except wrapper did not change the happy path)."""
    assert store.save_run(_report()) == "run-1"
    assert store.get_run("run-1") is not None
    assert len(store.get_events("run-1")) == 2
    assert store.counts()["runs"] == 1


def test_clear_is_atomic_on_mid_clear_failure(store):
    """P1-17: a failure on the second DELETE (runs) leaves the whole
    store intact — no half-deleted evidence reported as cleared."""
    store.save_run(_report())
    store.save_live_event(_live_event())
    before = store.counts()
    assert before == {
        "runs": 1,
        "live_login_events": 1,
        "live_login_transactions": 1,
        # IF-V6-02 (v7): the single AUTH_STARTED row is an incomplete
        # transaction — nothing observed a SESSION_CREATED ok.
        "live_login_session_created_observed": 0,
        "live_login_successful_transactions": 0,
        "live_login_incomplete_transactions": 1,
        "live_login_event_limit": 1000,
        "live_logins": 1,
    }
    store._conn = _FailingConn(store._conn, fail_on=2)  # 1st = DELETE events
    with pytest.raises(sqlite3.OperationalError):
        store.clear()
    after = store.counts()
    assert after == before
    assert store.get_run("run-1") is not None
    assert len(store.get_events("run-1")) == 2
    assert store.get_live_login("corr-1") is not None


def test_clear_succeeds_normally(store):
    """The happy path still wipes all three tables."""
    store.save_run(_report())
    store.save_live_event(_live_event())
    store.clear()
    assert store.counts() == {
        "runs": 0,
        "live_login_events": 0,
        "live_login_transactions": 0,
        "live_login_session_created_observed": 0,
        "live_login_successful_transactions": 0,
        "live_login_incomplete_transactions": 0,
        "live_login_event_limit": 1000,
        "live_logins": 0,
    }


def test_save_live_event_still_rolls_back_on_failure(store):
    """v3 P1-11 discipline re-verified: a failed live-event save
    leaves no partial row and the failure propagates."""
    store._conn = _FailingConn(store._conn, fail_on=1)
    with pytest.raises(sqlite3.OperationalError):
        store.save_live_event(_live_event())
    assert store.counts()["live_logins"] == 0


def test_live_login_retention_caps_at_1000(store):
    """P1-10/P1-11: only the latest 1000 live-login events are kept;
    saving 1005 prunes the 5 oldest, and the newest survive."""
    assert MAX_LIVE_LOGIN_EVENTS == 1000
    for i in range(MAX_LIVE_LOGIN_EVENTS + 5):
        store.save_live_event(_live_event(corr=f"corr-{i}", stage=f"stage-{i}"))
    assert store.counts()["live_logins"] == 1000
    assert store.get_live_login("corr-0") is None
    assert store.get_live_login("corr-4") is None
    assert store.get_live_login("corr-5") is not None
    assert store.get_live_login("corr-1004") is not None


def test_live_login_retention_prune_failure_rolls_back_insert(store):
    """A prune failure inside save_live_event rolls the insert back
    too — the event either lands with retention applied or not at
    all."""
    for i in range(3):
        store.save_live_event(_live_event(corr=f"corr-{i}"))
    # Fail on the prune DELETE (2nd execute: 1st = INSERT).
    store._conn = _FailingConn(store._conn, fail_on=2)
    with pytest.raises(sqlite3.OperationalError):
        store.save_live_event(_live_event(corr="corr-new"))
    assert store.counts()["live_logins"] == 3
    assert store.get_live_login("corr-new") is None
