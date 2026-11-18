"""Operation Trustline v7 — WS1 backend: IF-V6-02.

Failing-first regression tests, written BEFORE the fix.

IF-V6-02 (P1): backend evidence-semantic contradiction. A lone
SESSION_CREATED/ok event for a correlation made
counts()['live_login_successful_transactions'] == 1 while
get_live_login()['timeline_complete'] == False and
['successful'] == False. assess_live_login_timeline() correctly
requires a COMPLETE canonical stage sequence ending in
SESSION_CREATED ok, but counts() and storage_budget() counted ANY
distinct correlation_id with a SESSION_CREATED/ok row, regardless
of gaps. The fix adopts assess_live_login_timeline() as the ONE
canonical success predicate shared by counts(), storage_budget(),
and the list/detail endpoints, and splits the old conflated
number into three explicitly named counters:

- ``live_login_session_created_observed``: distinct transactions
  in which a SESSION_CREATED event with outcome ok was OBSERVED
  (the old v6 meaning of ``live_login_successful_transactions``,
  kept under an honest name — observation, not verification).
- ``live_login_successful_transactions`` (MEANING CHANGED in v7):
  distinct transactions whose recorded events form a COMPLETE
  canonical stage sequence ending in SESSION_CREATED ok, i.e.
  assess_live_login_timeline()['successful'] is True. A lone
  SESSION_CREATED ok without its observed prefix is incomplete
  and is NOT a verified success.
- ``live_login_incomplete_transactions``: distinct transactions
  whose timeline is NOT complete (gaps, reordering, duplicates,
  truncated/legacy tails, or an early end). A complete terminal
  denial (fully observed flow ending rejected/error) is complete
  but not successful, so it counts in NEITHER the successful nor
  the incomplete bucket.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from identityforge.api.app import create_app
from identityforge.config import Settings
from identityforge.evidence.store import (
    EvidenceStore,
    assess_live_login_timeline,
)

_FULL_LOGIN = [
    "AUTH_STARTED",
    "CALLBACK_RECEIVED",
    "BINDING_VERIFIED",
    "TOKEN_ENDPOINT",
    "ID_TOKEN_VALIDATED",
    "SESSION_CREATED",
]


@pytest.fixture()
def store(tmp_path):
    return EvidenceStore(db_path=str(tmp_path / "evidence.db"))


@pytest.fixture()
def app_client(tmp_path):
    app = create_app(settings=Settings(), db_path=str(tmp_path / "test.db"))
    client = TestClient(app, raise_server_exceptions=False)
    return app, client


def _live_event(corr, stage, outcome="ok", at="2026-11-11T00:00:00Z"):
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


def _save_stages(store, corr, stages, *, final_outcome="ok"):
    for stage in stages:
        outcome = final_outcome if stage == "SESSION_CREATED" else "ok"
        store.save_live_event(_live_event(corr, stage, outcome))


def _save_full_login(store, corr, *, final_outcome="ok"):
    _save_stages(store, corr, _FULL_LOGIN, final_outcome=final_outcome)


# ------------------------------------------------------------------ the repro


def test_lone_session_created_ok_is_observed_not_verified(store):
    """The IF-V6-02 repro, exact: EvidenceStore(':memory:'), one
    lone SESSION_CREATED/ok event for 'synthetic-gap-01' — the
    counts must say observed 1, verified successes 0, incomplete 1,
    and the detail endpoint must agree (timeline_complete False,
    successful False). Pre-fix, counts() reported 1 success."""
    mem = EvidenceStore(db_path=":memory:")
    mem.save_live_event(_live_event("synthetic-gap-01", "SESSION_CREATED"))
    counts = mem.counts()
    assert counts["live_login_events"] == 1
    assert counts["live_login_transactions"] == 1
    assert counts["live_login_session_created_observed"] == 1
    assert counts["live_login_successful_transactions"] == 0
    assert counts["live_login_incomplete_transactions"] == 1
    detail = mem.get_live_login("synthetic-gap-01")
    assert detail is not None
    assert detail["timeline_complete"] is False
    assert detail["successful"] is False
    assert detail["missing_stages"] == [
        "AUTH_STARTED",
        "CALLBACK_RECEIVED",
        "BINDING_VERIFIED",
        "TOKEN_ENDPOINT",
        "ID_TOKEN_VALIDATED",
    ]
    # storage_budget agrees with counts on the shared keys.
    budget = mem.storage_budget()
    assert budget["live_login_session_created_observed"] == 1
    assert budget["live_login_successful_transactions"] == 0
    assert budget["live_login_incomplete_transactions"] == 1


def test_complete_six_stage_success_is_verified(store):
    """A fully observed 6-stage canonical success: verified
    successes 1, observed 1, incomplete 0."""
    _save_full_login(store, "txn-ok")
    counts = store.counts()
    assert counts["live_login_session_created_observed"] == 1
    assert counts["live_login_successful_transactions"] == 1
    assert counts["live_login_incomplete_transactions"] == 0
    detail = store.get_live_login("txn-ok")
    assert detail["timeline_complete"] is True
    assert detail["successful"] is True


def test_terminal_denial_is_complete_not_successful_not_incomplete(store):
    """AUTH_STARTED + CALLBACK_RECEIVED/rejected: a complete
    terminal denial — verified successes 0 AND incomplete 0. A
    fully recorded failure is complete, not a gap."""
    store.save_live_event(_live_event("txn-denied", "AUTH_STARTED"))
    store.save_live_event(_live_event("txn-denied", "CALLBACK_RECEIVED", "rejected"))
    counts = store.counts()
    assert counts["live_login_transactions"] == 1
    assert counts["live_login_session_created_observed"] == 0
    assert counts["live_login_successful_transactions"] == 0
    assert counts["live_login_incomplete_transactions"] == 0
    detail = store.get_live_login("txn-denied")
    assert detail["timeline_complete"] is True
    assert detail["successful"] is False
    assert detail["missing_stages"] == []


# ------------------------------------------------------- gaps / dupes / order


@pytest.mark.parametrize(
    "corr,stages",
    [
        # Gap: BINDING_VERIFIED skipped, SESSION_CREATED ok present.
        (
            "txn-gap",
            [
                "AUTH_STARTED",
                "CALLBACK_RECEIVED",
                "TOKEN_ENDPOINT",
                "ID_TOKEN_VALIDATED",
                "SESSION_CREATED",
            ],
        ),
        # Duplicate stage: AUTH_STARTED recorded twice.
        (
            "txn-dupe",
            [
                "AUTH_STARTED",
                "AUTH_STARTED",
                "CALLBACK_RECEIVED",
                "BINDING_VERIFIED",
                "TOKEN_ENDPOINT",
                "ID_TOKEN_VALIDATED",
                "SESSION_CREATED",
            ],
        ),
        # Reordered: CALLBACK_RECEIVED before AUTH_STARTED.
        (
            "txn-reordered",
            [
                "CALLBACK_RECEIVED",
                "AUTH_STARTED",
                "BINDING_VERIFIED",
                "TOKEN_ENDPOINT",
                "ID_TOKEN_VALIDATED",
                "SESSION_CREATED",
            ],
        ),
        # Legacy truncated tail: only the last three stages recorded.
        ("txn-tail", ["TOKEN_ENDPOINT", "ID_TOKEN_VALIDATED", "SESSION_CREATED"]),
        # Lone SESSION_CREATED ok, no prefix at all.
        ("txn-lone", ["SESSION_CREATED"]),
        # Started-only: never reaches a terminal stage.
        ("txn-early", ["AUTH_STARTED", "CALLBACK_RECEIVED"]),
    ],
)
def test_broken_sequences_are_never_verified_successes(store, corr, stages):
    """Gaps, duplicate stages, reordered stages, legacy truncated
    data and early ends: verified successes 0, incomplete 1 — even
    when a SESSION_CREATED ok row IS present (observed 1)."""
    _save_stages(store, corr, stages)
    counts = store.counts()
    assert counts["live_login_successful_transactions"] == 0
    assert counts["live_login_incomplete_transactions"] == 1
    has_session_created_ok = "SESSION_CREATED" in stages
    assert counts["live_login_session_created_observed"] == (1 if has_session_created_ok else 0)
    detail = store.get_live_login(corr)
    assert detail["timeline_complete"] is False
    assert detail["successful"] is False


def test_post_login_stages_do_not_change_success(store):
    """AUTHORIZATION_DECISION / LOGOUT after a complete success are
    post-login stages: the transaction stays verified-successful,
    and a lone SESSION_CREATED followed by LOGOUT stays incomplete."""
    _save_full_login(store, "txn-ok")
    store.save_live_event(_live_event("txn-ok", "AUTHORIZATION_DECISION"))
    store.save_live_event(_live_event("txn-ok", "LOGOUT"))
    assert store.counts()["live_login_successful_transactions"] == 1
    assert store.counts()["live_login_incomplete_transactions"] == 0
    _save_stages(store, "txn-lone-logout", ["SESSION_CREATED", "LOGOUT"])
    assert store.counts()["live_login_successful_transactions"] == 1
    assert store.counts()["live_login_incomplete_transactions"] == 1
    assert store.counts()["live_login_session_created_observed"] == 2


def test_assess_timeline_is_the_canonical_predicate(store):
    """The counts agree with assess_live_login_timeline() applied to
    each transaction's own events — the predicate is shared, not
    re-implemented per call site."""
    _save_full_login(store, "txn-ok")
    _save_stages(store, "txn-tail", ["TOKEN_ENDPOINT", "ID_TOKEN_VALIDATED", "SESSION_CREATED"])
    store.save_live_event(_live_event("txn-denied", "AUTH_STARTED"))
    store.save_live_event(_live_event("txn-denied", "CALLBACK_RECEIVED", "rejected"))
    by_corr = {}
    for txn in store.list_live_logins(limit=50):
        by_corr[txn["correlation_id"]] = txn
    expected_success = sum(1 for t in by_corr.values() if t["successful"])
    expected_incomplete = sum(1 for t in by_corr.values() if not t["timeline_complete"])
    counts = store.counts()
    assert counts["live_login_successful_transactions"] == expected_success == 1
    assert counts["live_login_incomplete_transactions"] == expected_incomplete == 1
    # Same predicate, applied directly to raw event dicts.
    for corr, txn in by_corr.items():
        direct = assess_live_login_timeline(txn["events"])
        assert direct["successful"] == txn["successful"]
        assert direct["timeline_complete"] == txn["timeline_complete"]


# ------------------------------------------------------------- sample vs total


def test_20_recent_sample_vs_retained_total(store):
    """25 retained successful transactions: counts report the EXACT
    total (25), while list_live_logins() defaults to a 20-row recent
    sample — the total is never the sample size."""
    for i in range(25):
        _save_full_login(store, f"corr-{i:02d}")
    counts = store.counts()
    assert counts["live_login_transactions"] == 25
    assert counts["live_login_successful_transactions"] == 25
    assert counts["live_login_incomplete_transactions"] == 0
    assert counts["live_login_session_created_observed"] == 25
    sample = store.list_live_logins()  # default limit 20
    assert len(sample) == 20
    assert all(t["successful"] for t in sample)
    full = store.list_live_logins(limit=50)
    assert len(full) == 25
    assert sum(1 for t in full if t["successful"]) == 25


def test_list_sample_vs_total_via_api(app_client):
    """Same sample/total split at the HTTP layer: /api/v1/lab/counts
    says 25 verified successes while /api/v1/live-logins returns
    the 20 most recent — and the counts payload carries the new
    observed / incomplete counters."""
    app, client = app_client
    for i in range(25):
        for stage in _FULL_LOGIN:
            app.state.evidence.save_live_event(_live_event(f"corr-{i:02d}", stage))
    counts = client.get("/api/v1/lab/counts").json()
    assert counts["live_login_transactions"] == 25
    assert counts["live_login_successful_transactions"] == 25
    assert counts["live_login_session_created_observed"] == 25
    assert counts["live_login_incomplete_transactions"] == 0
    listed = client.get("/api/v1/live-logins").json()
    assert listed["mode"] == "LIVE_KEYCLOAK"
    assert len(listed["logins"]) == 20
    detail = client.get("/api/v1/live-logins/corr-00").json()
    assert detail["timeline_complete"] is True
    assert detail["successful"] is True


# ------------------------------------------------------------------ retention


def test_retention_evicts_oldest_whole_transaction_recalculates(store, monkeypatch):
    """With a 12-event budget, txn-A (complete success, 6) + txn-B
    (complete success, 6) sit at the cap; one more event evicts the
    WHOLE of A and the counts are recalculated exactly: successes
    drop 2 -> 1, observed drops 2 -> 1 (B) + 1 (lone C) = 2,
    incomplete rises 0 -> 1 (lone C). No false success, and B's
    retained chronology is unmixed."""
    monkeypatch.setattr("identityforge.evidence.store.MAX_LIVE_LOGIN_EVENTS", 12)
    _save_full_login(store, "txn-A")
    _save_full_login(store, "txn-B")
    assert store.counts()["live_login_successful_transactions"] == 2
    store.save_live_event(_live_event("txn-C", "SESSION_CREATED"))
    assert store.get_live_login("txn-A") is None
    assert [e["stage"] for e in store.get_live_login("txn-B")["events"]] == _FULL_LOGIN
    assert store.get_live_login("txn-B")["successful"] is True
    counts = store.counts()
    assert counts["live_login_events"] == 7
    assert counts["live_login_transactions"] == 2
    assert counts["live_login_session_created_observed"] == 2  # B + lone C
    assert counts["live_login_successful_transactions"] == 1  # B only
    assert counts["live_login_incomplete_transactions"] == 1  # lone C only
    budget = store.storage_budget()
    assert budget["live_login_successful_transactions"] == 1
    assert budget["live_login_incomplete_transactions"] == 1


def test_retention_evicting_incomplete_transaction_drops_incomplete(store, monkeypatch):
    """Evicting the oldest WHOLE transaction when it is the
    incomplete one drops the incomplete count to 0 — the evicted
    gap does not linger in any counter."""
    monkeypatch.setattr("identityforge.evidence.store.MAX_LIVE_LOGIN_EVENTS", 9)
    _save_stages(store, "txn-gap", ["TOKEN_ENDPOINT", "ID_TOKEN_VALIDATED", "SESSION_CREATED"])
    _save_full_login(store, "txn-ok")
    assert store.counts()["live_login_events"] == 9  # 3 + 6, at cap
    assert store.counts()["live_login_incomplete_transactions"] == 1
    assert store.counts()["live_login_successful_transactions"] == 1
    # One more event pushes past the cap and evicts the oldest WHOLE
    # transaction (txn-gap); txn-ok keeps all 6 of its events.
    store.save_live_event(_live_event("txn-new", "AUTH_STARTED"))
    counts = store.counts()
    assert store.get_live_login("txn-gap") is None
    assert counts["live_login_incomplete_transactions"] == 1  # txn-new only
    assert counts["live_login_successful_transactions"] == 1  # txn-ok kept
    assert counts["live_login_session_created_observed"] == 1  # txn-ok only


# ------------------------------------------------------- cross-surface agreement


def test_counts_storage_budget_list_detail_agree(store):
    """One mixed fixture, four surfaces, one answer: counts(),
    storage_budget(), list_live_logins() and get_live_login()
    agree on observed / successful / incomplete."""
    _save_full_login(store, "txn-ok")
    _save_stages(store, "txn-lone", ["SESSION_CREATED"])
    store.save_live_event(_live_event("txn-denied", "AUTH_STARTED"))
    store.save_live_event(_live_event("txn-denied", "CALLBACK_RECEIVED", "rejected"))
    store.save_live_event(_live_event("txn-started", "AUTH_STARTED"))
    counts = store.counts()
    budget = store.storage_budget()
    # Shared keys agree exactly.
    for key in (
        "live_login_events",
        "live_login_transactions",
        "live_login_session_created_observed",
        "live_login_successful_transactions",
        "live_login_incomplete_transactions",
    ):
        assert budget[key] == counts[key], key
    assert counts["live_login_events"] == 6 + 1 + 2 + 1
    assert counts["live_login_transactions"] == 4
    assert counts["live_login_session_created_observed"] == 2  # ok + lone
    assert counts["live_login_successful_transactions"] == 1  # ok only
    assert counts["live_login_incomplete_transactions"] == 2  # lone + started
    # List agrees: per-transaction assessments sum to the counts.
    listed = store.list_live_logins(limit=50)
    assert len(listed) == 4
    assert sum(1 for t in listed if t["successful"]) == 1
    assert sum(1 for t in listed if not t["timeline_complete"]) == 2
    assert sum(1 for t in listed if t["timeline_complete"] and not t["successful"]) == 1
    # Detail agrees per correlation.
    assert store.get_live_login("txn-ok")["successful"] is True
    assert store.get_live_login("txn-lone")["successful"] is False
    assert store.get_live_login("txn-lone")["timeline_complete"] is False
    assert store.get_live_login("txn-denied")["timeline_complete"] is True
    assert store.get_live_login("txn-denied")["successful"] is False
    assert store.get_live_login("txn-started")["timeline_complete"] is False


def test_counts_storage_budget_list_detail_agree_via_api(app_client):
    """The same agreement at the HTTP layer: /api/v1/lab/counts,
    /api/v1/live-logins and /api/v1/live-logins/{id} all report the
    same verified-success count for the same fixture."""
    app, client = app_client
    for stage in _FULL_LOGIN:
        app.state.evidence.save_live_event(_live_event("txn-ok", stage))
    app.state.evidence.save_live_event(_live_event("txn-lone", "SESSION_CREATED"))
    counts = client.get("/api/v1/lab/counts").json()
    assert counts["live_login_session_created_observed"] == 2
    assert counts["live_login_successful_transactions"] == 1
    assert counts["live_login_incomplete_transactions"] == 1
    listed = client.get("/api/v1/live-logins").json()["logins"]
    assert sum(1 for t in listed if t["successful"]) == 1
    assert sum(1 for t in listed if not t["timeline_complete"]) == 1
    lone = client.get("/api/v1/live-logins/txn-lone").json()
    assert lone["timeline_complete"] is False
    assert lone["successful"] is False
    assert client.get("/api/v1/live-logins/no-such").status_code == 404
