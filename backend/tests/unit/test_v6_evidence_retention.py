"""Operation Trustline v6 — WS1 backend: IF-V5-02 / IF-V5-03 / IF-V5-04.

Failing-first regression tests, written BEFORE the fixes.

IF-V5-02: counts() conflated saved live-login EVENT rows with
logins: 2 correlations / 7 events reported live_logins==7. Counts
must separate saved event rows, distinct transactions (computed in
SQL, not from a limit-20 list), and successful transactions
(transactions containing a SESSION_CREATED event with outcome ok).
The old ``live_logins`` key survives ONLY as a deprecated alias for
the EVENT count, never silently redefined.

IF-V5-03: the run-event budget deleted oldest individual event rows,
splitting retained runs (a 3-step timeline kept 2 events, step-0
silently gone). Retention must evict the OLDEST COMPLETE RUN
instead; a single run larger than the cap is rejected with a
controlled error, never stored partial. After every save, each
retained run's events endpoint data and report.timeline must agree
exactly on ordered step ids, outcomes, reason codes and counts.

IF-V5-04: save_live_event retention had the same row-splitting flaw
for live-login transactions. Retention must prune the oldest WHOLE
correlation_id; a per-transaction event cap bounds pathological
transactions. Incomplete (legacy / truncated) transactions must
expose timeline_complete=false, missing_stages, truncated_at and a
retention_reason — never a green-looking success built from a
truncated tail.
"""

from __future__ import annotations

import sqlite3

import pytest

from identityforge.evidence.store import (
    EvidenceStore,
    EvidenceTooLargeError,
    assess_live_login_timeline,
)
from identityforge.security.redaction import canonical_hash


@pytest.fixture()
def store(tmp_path):
    return EvidenceStore(db_path=str(tmp_path / "evidence.db"))


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


def _live_event(corr="corr-1", stage="AUTH_STARTED", outcome="ok", at="2026-11-11T00:00:00Z"):
    return {
        "correlation_id": corr,
        "stage": stage,
        "outcome": outcome,
        "reason_code": "OK",
        "subject_hash": "",
        "username": "student_01",
        "detail": "",
        "at": at,
    }


_FULL_LOGIN = [
    "AUTH_STARTED",
    "CALLBACK_RECEIVED",
    "BINDING_VERIFIED",
    "TOKEN_ENDPOINT",
    "ID_TOKEN_VALIDATED",
    "SESSION_CREATED",
]


def _save_full_login(store, corr, *, final_outcome="ok"):
    for stage in _FULL_LOGIN:
        outcome = final_outcome if stage == "SESSION_CREATED" else "ok"
        store.save_live_event(_live_event(corr, stage, outcome))


# ------------------------------------------------------------------ IF-V5-02


def test_counts_separates_events_transactions_and_successful(store):
    """The v5 repro, fixed: 2 correlations / 7 events must report
    7 EVENTS, 2 TRANSACTIONS, 1 successful transaction — never 7
    'logins'."""
    for stage in _FULL_LOGIN:
        store.save_live_event(_live_event("corr-A", stage))
    store.save_live_event(_live_event("corr-B", "AUTH_STARTED"))
    counts = store.counts()
    assert counts["live_login_events"] == 7
    assert counts["live_login_transactions"] == 2
    assert counts["live_login_successful_transactions"] == 1
    # IF-V6-02 (v7): corr-A is a verified success (observed 1,
    # successful 1); corr-B (started only) is incomplete.
    assert counts["live_login_session_created_observed"] == 1
    assert counts["live_login_incomplete_transactions"] == 1
    assert counts["live_login_event_limit"] == 1000
    # Deprecated alias: still the EVENT count, labelled as such.
    assert counts["live_logins"] == 7
    assert counts["runs"] == 0


def test_counts_started_failed_and_successful_transactions(store):
    """Started-only and failed attempts count as transactions but
    NOT as successful logins: auth-start/error/rejected events are
    stored rows, not logins."""
    _save_full_login(store, "corr-ok")
    store.save_live_event(_live_event("corr-started", "AUTH_STARTED"))
    _save_full_login(store, "corr-failed", final_outcome="rejected")
    counts = store.counts()
    assert counts["live_login_events"] == 6 + 1 + 6
    assert counts["live_login_transactions"] == 3
    assert counts["live_login_successful_transactions"] == 1


def test_counts_empty_store_is_zeroed(store):
    counts = store.counts()
    assert counts == {
        "runs": 0,
        "live_login_events": 0,
        "live_login_transactions": 0,
        "live_login_session_created_observed": 0,
        "live_login_successful_transactions": 0,
        "live_login_incomplete_transactions": 0,
        "live_login_event_limit": 1000,
        "live_logins": 0,
    }


def test_counts_transactions_not_limited_to_list_window(store):
    """The transaction count is COUNT(DISTINCT correlation_id) in
    SQL: 25 transactions are all counted even though list_live_logins
    defaults to a 20-row window."""
    for i in range(25):
        store.save_live_event(_live_event(f"corr-{i}", "AUTH_STARTED"))
    assert store.counts()["live_login_transactions"] == 25
    assert len(store.list_live_logins()) == 20  # list window unchanged


def test_storage_budget_separates_live_login_counts(store):
    """storage_budget carries the same split, with the event limit."""
    _save_full_login(store, "corr-A")
    store.save_live_event(_live_event("corr-B", "AUTH_STARTED"))
    budget = store.storage_budget()
    assert budget["live_login_events"] == 7
    assert budget["live_login_transactions"] == 2
    assert budget["live_login_successful_transactions"] == 1
    # IF-V6-02 (v7): budget agrees with counts on the new split.
    assert budget["live_login_session_created_observed"] == 1
    assert budget["live_login_incomplete_transactions"] == 1
    assert budget["live_login_event_limit"] == 1000
    assert budget["live_logins"] == 7  # deprecated alias, still events
    assert "automatically prunes" in budget["policy"]
    assert "manual" in budget["policy"]


def test_counts_reset_pre_post(store):
    """Reset (clear) pre/post counts: 2 transactions / 7 events /
    1 run before, all zero after."""
    _save_full_login(store, "corr-A")
    store.save_live_event(_live_event("corr-B", "AUTH_STARTED"))
    store.save_run(_report("run-1", steps=2))
    before = store.counts()
    assert before["runs"] == 1
    assert before["live_login_events"] == 7
    assert before["live_login_transactions"] == 2
    # IF-V6-02 (v7): corr-A is a verified success; corr-B (started
    # only) is incomplete. Observed counts both SESSION_CREATED ok
    # rows — here just corr-A's.
    assert before["live_login_session_created_observed"] == 1
    assert before["live_login_successful_transactions"] == 1
    assert before["live_login_incomplete_transactions"] == 1
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


# ------------------------------------------------------------------ IF-V5-03


def test_run_event_budget_evicts_oldest_whole_run(store, monkeypatch):
    """The v5 repro, fixed: with MAX_RUN_EVENTS=2, a 3-step run must
    NOT be stored as 2 events. With a 5-event budget, saving 3+3
    steps evicts the whole oldest run; the survivor keeps all 3."""
    monkeypatch.setattr("identityforge.evidence.store.MAX_RUN_EVENTS", 5)
    store.save_run(_report("run-a", steps=3))
    store.save_run(_report("run-b", steps=3))
    assert store.get_run("run-a") is None
    assert store.get_events("run-a") == []
    assert [e["step"] for e in store.get_events("run-b")] == ["step-0", "step-1", "step-2"]
    assert store.storage_budget()["events"] == 3


def test_run_event_budget_boundary_cap_minus1_cap(store, monkeypatch):
    """cap-1 / cap: 2+2 steps fit a 4-event budget exactly (both
    whole); one more 1-step run pushes over, evicting the oldest
    WHOLE run (run-a), never trimming a step off run-b."""
    monkeypatch.setattr("identityforge.evidence.store.MAX_RUN_EVENTS", 4)
    store.save_run(_report("run-a", steps=2))
    store.save_run(_report("run-b", steps=2))
    assert store.storage_budget()["events"] == 4  # at cap, both whole
    assert len(store.get_events("run-a")) == 2
    store.save_run(_report("run-c", steps=1))
    assert store.get_run("run-a") is None
    assert [e["step"] for e in store.get_events("run-b")] == ["step-0", "step-1"]
    assert [e["step"] for e in store.get_events("run-c")] == ["step-0"]
    assert store.storage_budget()["events"] == 3


def test_single_run_exceeding_event_cap_is_rejected(store, monkeypatch):
    """cap+1: a single run with more steps than the whole event
    budget is rejected with a controlled error and stores NOTHING
    — never a partial timeline pretending to be complete."""
    monkeypatch.setattr("identityforge.evidence.store.MAX_RUN_EVENTS", 2)
    with pytest.raises(EvidenceTooLargeError):
        store.save_run(_report("run-big", steps=3))
    assert store.get_run("run-big") is None
    assert store.get_events("run-big") == []
    assert store.counts()["runs"] == 0
    # A run exactly at the cap still saves whole.
    assert store.save_run(_report("run-ok", steps=2)) == "run-ok"
    assert len(store.get_events("run-ok")) == 2


def test_retained_runs_events_match_report_timeline(store, monkeypatch):
    """After every save at the boundary, EVERY retained run's stored
    events and report.timeline agree exactly: ordered step ids,
    outcomes, reason codes and counts."""
    monkeypatch.setattr("identityforge.evidence.store.MAX_RUN_EVENTS", 5)
    for i in range(4):
        store.save_run(_report(f"run-{i}", steps=2))
        for run_id in [f"run-{j}" for j in range(i + 1)]:
            report = store.get_run(run_id)
            if report is None:
                continue  # evicted whole — allowed
            events = store.get_events(run_id)
            assert [e["step"] for e in events] == [s["step"] for s in report["timeline"]]
            assert [e["outcome"] for e in events] == [s["outcome"] for s in report["timeline"]]
            assert [e["reason_code"] for e in events] == [
                s["reason_code"] for s in report["timeline"]
            ]
            status = store.get_run_evidence_status(run_id)
            assert status["timeline_complete"] is True
            assert status["timeline_steps"] == status["events_stored"]
            assert status["events_deleted"] == 0


def test_resave_duplicate_run_at_boundary_stays_whole(store, monkeypatch):
    """Re-saving a run_id at the boundary replaces its event set
    exactly (atomic replacement), and the replacement is whole."""
    monkeypatch.setattr("identityforge.evidence.store.MAX_RUN_EVENTS", 5)
    store.save_run(_report("run-a", steps=3))
    store.save_run(_report("run-b", steps=2))
    store.save_run(_report("run-a", steps=1))
    assert [e["step"] for e in store.get_events("run-a")] == ["step-0"]
    assert len(store.get_run("run-a")["timeline"]) == 1
    assert [e["step"] for e in store.get_events("run-b")] == ["step-0", "step-1"]
    assert store.get_run_evidence_status("run-a")["timeline_complete"] is True
    assert store.get_run_evidence_status("run-b")["timeline_complete"] is True


def test_run_evidence_status_for_missing_run_is_none(store):
    assert store.get_run_evidence_status("no-such-run") is None


def test_report_hash_matches_stored_report(store):
    """The stored SHA-256 is the content hash of the stored report:
    canonical_hash(get_run(...)) equals the stored value, so the API
    returns the same hash the store recorded. (Hash, not signature.)"""
    store.save_run(_report("run-1", steps=2))
    row = store._conn.execute(
        "SELECT report_sha256 FROM runs WHERE run_id=?", ("run-1",)
    ).fetchone()
    assert row[0] == canonical_hash(store.get_run("run-1"))


def test_event_budget_never_deletes_legacy_orphan_events(store, monkeypatch, tmp_path):
    """Legacy orphan events are disclosed, never silently deleted by
    retention: with a 2-event budget and a pre-v5 orphan present, a
    save prunes whole runs only and the orphan survives."""
    legacy = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(legacy))
    conn.executescript(
        """
        CREATE TABLE runs (run_id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL,
            status TEXT NOT NULL, mode TEXT NOT NULL, secure_result TEXT NOT NULL,
            flawed_result TEXT NOT NULL, secure_reason TEXT,
            elapsed_ms INTEGER NOT NULL DEFAULT 0, report_json TEXT NOT NULL,
            report_sha256 TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL, step TEXT NOT NULL, outcome TEXT NOT NULL,
            reason_code TEXT, detail TEXT NOT NULL DEFAULT '', at TEXT NOT NULL);
        CREATE TABLE live_login_events (id INTEGER PRIMARY KEY AUTOINCREMENT,
            correlation_id TEXT NOT NULL, stage TEXT NOT NULL, outcome TEXT NOT NULL,
            reason_code TEXT NOT NULL DEFAULT 'OK', subject_hash TEXT NOT NULL DEFAULT '',
            username TEXT NOT NULL DEFAULT '', detail TEXT NOT NULL DEFAULT '',
            at TEXT NOT NULL);
        """
    )
    conn.execute(
        "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            "run-1",
            "K1",
            "passed",
            "SECURE",
            "DENIED",
            "ALLOWED",
            "OK",
            5,
            '{"run_id": "run-1"}',
            "deadbeef",
            "2026-11-11T00:00:00Z",
        ),
    )
    conn.execute(
        "INSERT INTO events (run_id, step, outcome, reason_code, detail, at) VALUES (?,?,?,?,?,?)",
        ("ghost-run", "step-0", "ok", "OK", "", "2026-11-11T00:00:00Z"),
    )
    conn.commit()
    conn.close()
    legacy_store = EvidenceStore(db_path=str(legacy))
    assert legacy_store.count_orphan_events() == 1
    monkeypatch.setattr("identityforge.evidence.store.MAX_RUN_EVENTS", 2)
    legacy_store.save_run(_report("run-2", steps=2))
    assert legacy_store.count_orphan_events() == 1
    total = legacy_store._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert total == 3  # 2 new + 1 orphan, orphan untouched


# ------------------------------------------------------------------ IF-V5-04


def test_live_login_retention_evicts_oldest_whole_transaction(store, monkeypatch):
    """With a 6-event budget, txn A (3 events) + txn B (3 events) sit
    at the cap; one more event evicts the whole of A — B keeps all 3
    of its events, never a truncated tail."""
    monkeypatch.setattr("identityforge.evidence.store.MAX_LIVE_LOGIN_EVENTS", 6)
    for stage in ["AUTH_STARTED", "CALLBACK_RECEIVED", "BINDING_VERIFIED"]:
        store.save_live_event(_live_event("txn-A", stage))
    for stage in ["AUTH_STARTED", "CALLBACK_RECEIVED", "BINDING_VERIFIED"]:
        store.save_live_event(_live_event("txn-B", stage))
    store.save_live_event(_live_event("txn-C", "AUTH_STARTED"))
    assert store.get_live_login("txn-A") is None
    assert [e["stage"] for e in store.get_live_login("txn-B")["events"]] == [
        "AUTH_STARTED",
        "CALLBACK_RECEIVED",
        "BINDING_VERIFIED",
    ]
    assert store.get_live_login("txn-C") is not None
    assert store.counts()["live_login_events"] == 4
    assert store.counts()["live_login_transactions"] == 2


def test_live_login_retention_boundary_cap_minus1_cap(store, monkeypatch):
    """cap-1 / cap: A(2) + B(2) fit a 4-event budget exactly; one more
    event evicts the oldest WHOLE transaction."""
    monkeypatch.setattr("identityforge.evidence.store.MAX_LIVE_LOGIN_EVENTS", 4)
    for corr in ("txn-A", "txn-B"):
        store.save_live_event(_live_event(corr, "AUTH_STARTED"))
        store.save_live_event(_live_event(corr, "CALLBACK_RECEIVED"))
    assert store.counts()["live_login_events"] == 4
    store.save_live_event(_live_event("txn-C", "AUTH_STARTED"))
    assert store.get_live_login("txn-A") is None
    assert len(store.get_live_login("txn-B")["events"]) == 2
    assert store.counts()["live_login_transactions"] == 2


def test_single_transaction_exceeding_total_cap_is_rejected(store, monkeypatch):
    """cap+1 for live logins: a lone transaction whose events alone
    exceed the total budget is rejected with a controlled error —
    the earlier events stay, the overflowing event is not stored,
    and the transaction is never silently split."""
    monkeypatch.setattr("identityforge.evidence.store.MAX_LIVE_LOGIN_EVENTS", 2)
    store.save_live_event(_live_event("txn-A", "AUTH_STARTED"))
    store.save_live_event(_live_event("txn-A", "CALLBACK_RECEIVED"))
    with pytest.raises(EvidenceTooLargeError):
        store.save_live_event(_live_event("txn-A", "BINDING_VERIFIED"))
    events = store.get_live_login("txn-A")["events"]
    assert [e["stage"] for e in events] == ["AUTH_STARTED", "CALLBACK_RECEIVED"]
    assert store.counts()["live_login_events"] == 2


def test_per_transaction_event_cap_enforced(store, monkeypatch):
    """The per-transaction cap bounds a pathological transaction:
    the (cap+1)-th event of one correlation is rejected, the
    transaction keeps exactly cap events, and other transactions
    are unaffected."""
    import identityforge.evidence.store as store_mod

    assert store_mod.MAX_LIVE_LOGIN_EVENTS_PER_TRANSACTION == 100  # documented default
    monkeypatch.setattr("identityforge.evidence.store.MAX_LIVE_LOGIN_EVENTS_PER_TRANSACTION", 3)
    for stage in ["AUTH_STARTED", "CALLBACK_RECEIVED", "BINDING_VERIFIED"]:
        store.save_live_event(_live_event("txn-A", stage))
    with pytest.raises(EvidenceTooLargeError):
        store.save_live_event(_live_event("txn-A", "TOKEN_ENDPOINT"))
    assert len(store.get_live_login("txn-A")["events"]) == 3
    store.save_live_event(_live_event("txn-B", "AUTH_STARTED"))
    assert store.get_live_login("txn-B") is not None


def test_full_login_timeline_is_complete_and_successful(store):
    """A fully observed 6-stage ok flow: complete, successful, no
    missing stages, no truncation."""
    _save_full_login(store, "txn-ok")
    login = store.get_live_login("txn-ok")
    assert login["timeline_complete"] is True
    assert login["successful"] is True
    assert login["missing_stages"] == []
    assert login["truncated_at"] is None
    assert login["retention_reason"] is None


def test_terminal_rejection_is_complete_but_not_successful(store):
    """A fully observed flow ending in a rejected SESSION_CREATED:
    complete (the failure was recorded in full) but NOT successful."""
    _save_full_login(store, "txn-fail", final_outcome="rejected")
    login = store.get_live_login("txn-fail")
    assert login["timeline_complete"] is True
    assert login["successful"] is False
    assert login["missing_stages"] == []
    assert login["retention_reason"] is None


def test_legacy_split_transaction_is_incomplete_not_successful(store):
    """The IF-V5-04 proof: a transaction whose LEADING events were
    truncated (legacy per-row retention kept only the tail) must NOT
    turn green. SESSION_CREATED ok without its prefix is incomplete,
    unsuccessful, and names the missing stages."""
    for stage in ["TOKEN_ENDPOINT", "ID_TOKEN_VALIDATED", "SESSION_CREATED"]:
        store.save_live_event(_live_event("txn-tail", stage))
    login = store.get_live_login("txn-tail")
    assert login["timeline_complete"] is False
    assert login["successful"] is False
    assert login["missing_stages"] == [
        "AUTH_STARTED",
        "CALLBACK_RECEIVED",
        "BINDING_VERIFIED",
    ]
    assert login["truncated_at"] == "SESSION_CREATED"
    assert login["retention_reason"] is not None
    assert "must not be read as a successful login" in login["retention_reason"]


def test_transaction_ending_early_is_incomplete(store):
    """A transaction that stops after CALLBACK_RECEIVED ok (no
    terminal stage): incomplete, missing the 4 later stages."""
    store.save_live_event(_live_event("txn-early", "AUTH_STARTED"))
    store.save_live_event(_live_event("txn-early", "CALLBACK_RECEIVED"))
    login = store.get_live_login("txn-early")
    assert login["timeline_complete"] is False
    assert login["successful"] is False
    assert login["missing_stages"] == [
        "BINDING_VERIFIED",
        "TOKEN_ENDPOINT",
        "ID_TOKEN_VALIDATED",
        "SESSION_CREATED",
    ]
    assert login["truncated_at"] == "CALLBACK_RECEIVED"
    assert login["retention_reason"] is not None


def test_rejection_without_a_start_is_incomplete(store):
    """A CALLBACK_RECEIVED rejection with no observed AUTH_STARTED
    (pre-lookup failure correlation): incomplete, not successful —
    there is no observed start to anchor it to."""
    store.save_live_event(_live_event("unknown-abc", "CALLBACK_RECEIVED", "rejected"))
    login = store.get_live_login("unknown-abc")
    assert login["timeline_complete"] is False
    assert login["successful"] is False
    assert login["missing_stages"] == ["AUTH_STARTED"]
    assert login["truncated_at"] == "CALLBACK_RECEIVED"


def test_assess_timeline_pure_function_edge_cases():
    """assess_live_login_timeline on raw event dicts: empty list,
    logout-only correlation, and a skipped middle stage."""
    empty = assess_live_login_timeline([])
    assert empty["timeline_complete"] is False
    assert empty["successful"] is False
    assert empty["missing_stages"] == list(_FULL_LOGIN)
    assert empty["truncated_at"] is None
    assert empty["retention_reason"] is not None
    assert "must not be read as a successful login" in empty["retention_reason"]
    logout_only = assess_live_login_timeline([{"stage": "LOGOUT", "outcome": "ok"}])
    assert logout_only["timeline_complete"] is False
    assert logout_only["successful"] is False
    assert logout_only["missing_stages"] == list(_FULL_LOGIN)
    skipped = assess_live_login_timeline(
        [
            {"stage": "AUTH_STARTED", "outcome": "ok"},
            {"stage": "TOKEN_ENDPOINT", "outcome": "ok"},
            {"stage": "ID_TOKEN_VALIDATED", "outcome": "ok"},
            {"stage": "SESSION_CREATED", "outcome": "ok"},
        ]
    )
    assert skipped["timeline_complete"] is False
    assert skipped["successful"] is False
    assert skipped["missing_stages"] == ["CALLBACK_RECEIVED", "BINDING_VERIFIED"]


def test_live_login_events_sorted_by_db_sequence_not_timestamp(store):
    """Predictable event sort: within a correlation, events come
    back in DB insertion (id) order even when `at` timestamps are
    out of order."""
    store.save_live_event(_live_event("txn-A", "AUTH_STARTED", at="2026-11-11T00:00:03Z"))
    store.save_live_event(_live_event("txn-A", "CALLBACK_RECEIVED", at="2026-11-11T00:00:01Z"))
    store.save_live_event(_live_event("txn-A", "BINDING_VERIFIED", at="2026-11-11T00:00:02Z"))
    stages = [e["stage"] for e in store.get_live_login("txn-A")["events"]]
    assert stages == ["AUTH_STARTED", "CALLBACK_RECEIVED", "BINDING_VERIFIED"]


def test_list_live_logins_deterministic_ordering(store):
    """Transaction ordering is deterministic: most recently active
    (highest event id) first, stable across repeated reads."""
    _save_full_login(store, "txn-first")
    _save_full_login(store, "txn-second")
    first = [t["correlation_id"] for t in store.list_live_logins()]
    second = [t["correlation_id"] for t in store.list_live_logins()]
    assert first == ["txn-second", "txn-first"]
    assert first == second
    # Every listed transaction carries its completeness assessment.
    for txn in store.list_live_logins():
        assert txn["timeline_complete"] is True
        assert txn["successful"] is True
        assert txn["missing_stages"] == []
