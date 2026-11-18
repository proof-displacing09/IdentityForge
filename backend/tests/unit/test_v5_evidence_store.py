"""Operation Trustline v5 — IF-V4-04 duplicated evidence events and
IF-V4-11 evidence retention.

IF-V4-04: re-saving a run_id is an ATOMIC REPLACEMENT (Option 2) —
the old report AND its exact event set are replaced in the same
transaction; a mid-write failure rolls everything back and the
previously stored report/events survive. A foreign key from
events.run_id to runs.run_id enforces the same rule at the schema
level; pre-v5 databases are migrated only when they hold no orphan
events, and orphans are never silently deleted.

IF-V4-11: scenario evidence is retention-bounded (latest 1000 runs /
20000 events, pruned on save in the same transaction), with the
budget exposed via storage_budget().
"""

from __future__ import annotations

import sqlite3
import threading

import pytest

from identityforge.evidence.store import (
    MAX_LIVE_LOGIN_EVENTS,
    MAX_RUN_EVENTS,
    MAX_RUNS,
    EvidenceStore,
)
from identityforge.security.redaction import canonical_hash


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


@pytest.fixture()
def store(tmp_path):
    return EvidenceStore(db_path=str(tmp_path / "evidence.db"))


# ------------------------------------------------------------------ IF-V4-04


def test_save_run_same_id_twice_replaces_events_atomically(store):
    """The v4 repro: same run_id saved twice with a 1-step timeline
    stored 2 events. Now the second save replaces the event set —
    exactly 1 stored event, matching the report."""
    assert store.save_run(_report("same-id", steps=2)) == "same-id"
    assert len(store.get_events("same-id")) == 2
    assert store.save_run(_report("same-id", steps=1)) == "same-id"
    events = store.get_events("same-id")
    assert [e["step"] for e in events] == ["step-0"]
    assert store.counts()["runs"] == 1
    assert len(store.get_run("same-id")["timeline"]) == 1


def test_save_run_different_ids_are_independent(store):
    store.save_run(_report("run-1", steps=2))
    store.save_run(_report("run-2", steps=1))
    assert [e["step"] for e in store.get_events("run-1")] == ["step-0", "step-1"]
    assert [e["step"] for e in store.get_events("run-2")] == ["step-0"]
    assert store.counts()["runs"] == 2


def test_save_run_resave_failure_on_delete_keeps_original(store):
    """Fail on the events DELETE (1st execute) of a re-save: the
    original report and its events survive untouched."""
    store.save_run(_report("run-1", steps=2))
    store._conn = _FailingConn(store._conn, fail_on=1)
    with pytest.raises(sqlite3.OperationalError):
        store.save_run(_report("run-1", steps=1))
    assert store.get_run("run-1") is not None
    assert len(store.get_events("run-1")) == 2
    assert len(store.get_run("run-1")["timeline"]) == 2


def test_save_run_resave_failure_on_run_insert_keeps_original(store):
    """Fail on the runs INSERT (2nd execute, after the DELETE) of a
    re-save: rollback restores the deleted events — the original is
    whole again, not half-replaced."""
    store.save_run(_report("run-1", steps=2))
    store._conn = _FailingConn(store._conn, fail_on=2)
    with pytest.raises(sqlite3.OperationalError):
        store.save_run(_report("run-1", steps=1))
    assert store.get_run("run-1") is not None
    assert [e["step"] for e in store.get_events("run-1")] == ["step-0", "step-1"]
    assert store.counts()["runs"] == 1


def test_save_run_retry_after_failure_succeeds_with_exact_events(store):
    """A failed re-save followed by a retry lands exactly once."""
    store.save_run(_report("run-1", steps=2))
    store._conn = _FailingConn(store._conn, fail_on=2)
    with pytest.raises(sqlite3.OperationalError):
        store.save_run(_report("run-1", steps=1))
    # Retry against the real connection (the proxy is discarded).
    store._conn = store._conn._conn
    assert store.save_run(_report("run-1", steps=1)) == "run-1"
    assert [e["step"] for e in store.get_events("run-1")] == ["step-0"]
    assert store.counts()["runs"] == 1


def test_save_run_multiple_steps_replaced_exactly(store):
    """3 steps -> 1 step -> 4 steps: the stored set always equals
    the latest report, never a union of saves."""
    store.save_run(_report("run-1", steps=3))
    assert len(store.get_events("run-1")) == 3
    store.save_run(_report("run-1", steps=1))
    assert len(store.get_events("run-1")) == 1
    store.save_run(_report("run-1", steps=4))
    assert [e["step"] for e in store.get_events("run-1")] == [
        "step-0",
        "step-1",
        "step-2",
        "step-3",
    ]


def test_events_foreign_key_enforced_on_new_database(store):
    """New databases enforce events.run_id -> runs.run_id: an event
    for a nonexistent run is rejected by SQLite, not stored."""
    assert store._conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    with pytest.raises(sqlite3.IntegrityError):
        store._conn.execute(
            "INSERT INTO events (run_id, step, outcome, reason_code, detail, at)"
            " VALUES (?,?,?,?,?,?)",
            ("no-such-run", "step-0", "ok", "OK", "", "2026-11-11T00:00:00Z"),
        )
    assert store.count_orphan_events() == 0


# Pre-v5 DDL, verbatim (no REFERENCES clause), to build legacy DBs.
_LEGACY_SCHEMA = """
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL,
    status TEXT NOT NULL,
    mode TEXT NOT NULL,
    secure_result TEXT NOT NULL,
    flawed_result TEXT NOT NULL,
    secure_reason TEXT,
    elapsed_ms INTEGER NOT NULL DEFAULT 0,
    report_json TEXT NOT NULL,
    report_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    step TEXT NOT NULL,
    outcome TEXT NOT NULL,
    reason_code TEXT,
    detail TEXT NOT NULL DEFAULT '',
    at TEXT NOT NULL
);
CREATE TABLE live_login_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    correlation_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    outcome TEXT NOT NULL,
    reason_code TEXT NOT NULL DEFAULT 'OK',
    subject_hash TEXT NOT NULL DEFAULT '',
    username TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '',
    at TEXT NOT NULL
);
"""


def _legacy_db(path, *, orphan: bool):
    conn = sqlite3.connect(str(path))
    conn.executescript(_LEGACY_SCHEMA)
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
        ("run-1", "step-0", "ok", "OK", "", "2026-11-11T00:00:00Z"),
    )
    conn.execute(
        "INSERT INTO events (run_id, step, outcome, reason_code, detail, at) VALUES (?,?,?,?,?,?)",
        ("run-1", "step-1", "ok", "OK", "", "2026-11-11T00:00:00Z"),
    )
    if orphan:
        conn.execute(
            "INSERT INTO events (run_id, step, outcome, reason_code, detail, at)"
            " VALUES (?,?,?,?,?,?)",
            ("ghost-run", "step-0", "ok", "OK", "", "2026-11-11T00:00:00Z"),
        )
    conn.commit()
    conn.close()


def test_legacy_schema_migrates_with_fk_preserving_data(tmp_path):
    """A pre-v5 database with no orphans is migrated to the FK
    schema on open: same rows, same ids, FK present afterwards."""
    path = tmp_path / "legacy.db"
    _legacy_db(path, orphan=False)
    store = EvidenceStore(db_path=str(path))
    sql = store._conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='events'"
    ).fetchone()[0]
    assert "REFERENCES runs" in sql
    assert store.get_run("run-1") is not None
    assert [e["step"] for e in store.get_events("run-1")] == ["step-0", "step-1"]
    assert store.count_orphan_events() == 0
    # The migrated store still saves and replaces normally.
    assert store.save_run(_report("run-1", steps=1)) == "run-1"
    assert [e["step"] for e in store.get_events("run-1")] == ["step-0"]


def test_legacy_schema_with_orphans_preserves_them(tmp_path):
    """A pre-v5 database WITH orphan events is NOT migrated and
    NOTHING is deleted: the orphan survives, is reported, and later
    saves still work."""
    path = tmp_path / "legacy-orphan.db"
    _legacy_db(path, orphan=True)
    store = EvidenceStore(db_path=str(path))
    sql = store._conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='events'"
    ).fetchone()[0]
    assert "REFERENCES runs" not in sql  # migration skipped, deliberately
    assert store.count_orphan_events() == 1
    total = store._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert total == 3  # 2 legit + 1 orphan, all preserved
    assert store.save_run(_report("run-1", steps=1)) == "run-1"
    assert [e["step"] for e in store.get_events("run-1")] == ["step-0"]
    assert store.count_orphan_events() == 1  # orphan still there


def test_clear_then_save_and_clean_restart(tmp_path):
    """Reset clears runs and events; a save after clear works; a
    close/reopen (clean restart) preserves the saved run exactly."""
    path = tmp_path / "evidence.db"
    store = EvidenceStore(db_path=str(path))
    store.save_run(_report("run-1", steps=2))
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
    assert store.get_events("run-1") == []
    store.save_run(_report("run-2", steps=1))
    store.close()
    reopened = EvidenceStore(db_path=str(path))
    assert reopened.counts()["runs"] == 1
    assert [e["step"] for e in reopened.get_events("run-2")] == ["step-0"]
    assert reopened.get_run("run-2")["run_id"] == "run-2"


# ------------------------------------------------------------------ IF-V4-11


def test_runs_retention_caps_at_1000(store):
    """Saving 1005 runs keeps exactly the latest 1000; the 5 oldest
    runs and their events are gone, the newest survive."""
    assert MAX_RUNS == 1000
    for i in range(MAX_RUNS + 5):
        store.save_run(_report(f"run-{i}", steps=1))
    assert store.counts()["runs"] == 1000
    assert store.get_run("run-0") is None
    assert store.get_events("run-0") == []
    assert store.get_run("run-4") is None
    assert store.get_run("run-5") is not None
    assert store.get_run("run-1004") is not None
    total_events = store._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert total_events == 1000


def test_events_retention_backstop_evicts_oldest_whole_run(store, monkeypatch):
    """The global events cap (mechanism check with a small bound),
    whole-run form (IF-V5-03, v6): with MAX_RUN_EVENTS=5, saving 3+3
    steps evicts the ENTIRE oldest run — run-a is gone, run-b keeps
    all 3 of its steps, and no run is ever left split."""
    monkeypatch.setattr("identityforge.evidence.store.MAX_RUN_EVENTS", 5)
    store.save_run(_report("run-a", steps=3))
    store.save_run(_report("run-b", steps=3))
    assert store.get_run("run-a") is None
    assert store.get_events("run-a") == []
    assert [e["step"] for e in store.get_events("run-b")] == ["step-0", "step-1", "step-2"]
    assert store.storage_budget()["events"] == 3


def test_retention_prune_failure_rolls_back_save(store):
    """A failure in the retention prune (4th execute: 1st DELETE
    events, 2nd runs insert, 3rd event insert, 4th prune) rolls the
    whole save back — the new run is absent, the old data intact."""
    store.save_run(_report("run-old", steps=1))
    store._conn = _FailingConn(store._conn, fail_on=4)
    with pytest.raises(sqlite3.OperationalError):
        store.save_run(_report("run-new", steps=1))
    assert store.get_run("run-new") is None
    assert store.get_run("run-old") is not None
    assert len(store.get_events("run-old")) == 1
    assert store.counts()["runs"] == 1


def test_concurrent_save_run_writes_stay_consistent(store):
    """Concurrent saves (distinct ids + one shared id re-saved) leave
    every run with exactly its own report's events — no duplicates,
    no interleaving, no lost writes, within the retention bound."""
    errors: list[BaseException] = []
    barrier = threading.Barrier(9)

    def save_many(prefix: str) -> None:
        try:
            barrier.wait(timeout=30)
            for i in range(25):
                store.save_run(_report(f"{prefix}-{i}", steps=2))
        except BaseException as exc:  # noqa: BLE001 — collected, asserted below
            errors.append(exc)

    def resave_shared() -> None:
        try:
            barrier.wait(timeout=30)
            for _ in range(25):
                store.save_run(_report("shared", steps=1))
        except BaseException as exc:  # noqa: BLE001 — collected, asserted below
            errors.append(exc)

    threads = [threading.Thread(target=save_many, args=(f"t{j}",)) for j in range(8)]
    threads.append(threading.Thread(target=resave_shared))
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert not errors
    assert store.counts()["runs"] == 8 * 25 + 1
    assert [e["step"] for e in store.get_events("shared")] == ["step-0"]
    for j in range(8):
        for i in range(25):
            events = store.get_events(f"t{j}-{i}")
            assert [e["step"] for e in events] == ["step-0", "step-1"]
    assert store.storage_budget()["runs"] == 201


def test_storage_budget_reports_counts_and_limits(store):
    """The budget is honest: counts track saves, limits are the
    documented caps, orphans are 0 on a fresh database."""
    budget = store.storage_budget()
    assert budget == {
        "runs": 0,
        "runs_limit": 1000,
        "events": 0,
        "events_limit": 20000,
        "live_login_events": 0,
        "live_login_transactions": 0,
        "live_login_session_created_observed": 0,
        "live_login_successful_transactions": 0,
        "live_login_incomplete_transactions": 0,
        "live_login_event_limit": 1000,
        "live_logins": 0,
        "live_logins_limit": 1000,
        "orphan_events": 0,
        "policy": (
            "latest 1000 scenario runs, latest 20000 run events, "
            "latest 1000 live-login events; retention automatically prunes "
            "the oldest whole runs / whole login transactions at capacity; "
            "officer-only reset is the only manual destructive API action "
            "(it also revokes sessions); session revocation and Keycloak "
            "realm/volume deletion are separate operations; a successful "
            "live login is a complete canonical stage sequence ending in "
            "SESSION_CREATED ok — a lone SESSION_CREATED ok is observed, "
            "not a verified success"
        ),
    }
    assert MAX_LIVE_LOGIN_EVENTS == 1000
    assert MAX_RUN_EVENTS == 20000
    for i in range(3):
        store.save_run(_report(f"run-{i}", steps=2))
    budget = store.storage_budget()
    assert budget["runs"] == 3
    assert budget["events"] == 6


def test_report_hash_preserved_for_surviving_runs(store):
    """After retention pruning, surviving runs still return their
    original report with a matching stored SHA-256 — provenance and
    hashes survive the prune."""
    for i in range(MAX_RUNS + 5):
        store.save_run(_report(f"run-{i}", steps=1))
    row = store._conn.execute(
        "SELECT report_sha256 FROM runs WHERE run_id=?", ("run-1004",)
    ).fetchone()
    assert row is not None
    assert row[0] == canonical_hash(store.get_run("run-1004"))


def test_db_error_injection_on_event_insert_rolls_back(store):
    """Fail on the event INSERT (3rd execute, new DELETE-first order):
    no run row, no events, no count — the save is atomic."""
    store._conn = _FailingConn(store._conn, fail_on=3)
    with pytest.raises(sqlite3.OperationalError):
        store.save_run(_report("run-1", steps=2))
    assert store.get_run("run-1") is None
    assert store.get_events("run-1") == []
    assert store.counts()["runs"] == 0
