"""Operation Trustline v5 — IF-V4-03 misleading session counts.

``len(SessionStore)`` counts ACTIVE sessions only: live, unexpired,
unrevoked. Expired/revoked records are pruned under the lock on
access, so they can neither inflate ``/api/v1/lab/counts`` nor
accumulate unboundedly over a long lab session. ``total_issued`` is
the separate, process-lifetime diagnostic.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from identityforge.models import LabRole
from identityforge.security.session import SessionStore

ISSUER = "http://127.0.0.1:8080/realms/identityforge-lab"


def _make(store, subject="sub-1"):
    return store.create(subject=subject, username="u", roles=[LabRole.MEMBER], issuer=ISSUER)


class _Clock:
    """Mutable injected clock: now() returns the held time."""

    def __init__(self) -> None:
        self.now = datetime.now(timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def test_expired_session_not_counted():
    """Zero TTL: get() is None AND len() is 0 (the v4 repro had
    get None but len 1)."""
    store = SessionStore(ttl_seconds=0)
    rec = _make(store)
    assert store.get(rec.session_id) is None
    assert len(store) == 0
    assert store.active_count() == 0
    assert store.total_issued == 1  # issued, but dead — tracked separately


def test_revoked_session_not_counted():
    """Revocation: get() is None AND len() is 0 (the v4 repro had
    get None but len 1)."""
    store = SessionStore(ttl_seconds=1800)
    rec = _make(store)
    assert store.is_revoked(rec.session_id) is False
    assert store.revoke(rec.session_id) is True
    assert store.is_revoked(rec.session_id) is True
    assert store.get(rec.session_id) is None
    assert len(store) == 0
    assert store.total_issued == 1
    # After the prune the id is simply gone: get() and is_revoked()
    # agree it is not a live session (no access is possible either
    # way — the record cannot be resurrected).
    assert store.is_revoked(rec.session_id) is False


def test_future_expiry_via_injected_clock():
    """Advancing the injected clock past the TTL expires the session
    without waiting out a real TTL."""
    clock = _Clock()
    store = SessionStore(ttl_seconds=100, clock=clock)
    rec = _make(store)
    assert store.get(rec.session_id) is not None
    assert len(store) == 1
    clock.advance(99)
    assert store.get(rec.session_id) is not None
    clock.advance(2)  # now past expires_at
    assert store.get(rec.session_id) is None
    assert len(store) == 0


def test_active_count_only_counts_live_mixed():
    """Mixed live/expired/revoked: only the live session counts."""
    clock = _Clock()
    store = SessionStore(ttl_seconds=100, clock=clock)
    a = _make(store, "sub-a")  # expires at T+100
    clock.advance(60)
    b = _make(store, "sub-b")  # expires at T+160
    c = _make(store, "sub-c")  # expires at T+160
    assert store.revoke(b.session_id) is True
    # At T+60: A and C live, B revoked.
    assert len(store) == 2
    assert store.get(b.session_id) is None
    assert store.get(a.session_id) is not None
    assert store.get(c.session_id) is not None
    clock.advance(50)  # T+110: A expired, C still live.
    assert store.get(a.session_id) is None
    assert store.get(c.session_id) is not None
    assert len(store) == 1
    assert store.active_count() == 1
    assert store.total_issued == 3


def test_total_issued_tracked_separately_and_survives_clear():
    """total_issued is process-lifetime (like the evidence-health
    counters): clear() wipes stored sessions, not history."""
    store = SessionStore(ttl_seconds=1800)
    _make(store, "sub-a")
    rec = _make(store, "sub-b")
    store.revoke(rec.session_id)
    assert len(store) == 1
    assert store.total_issued == 2
    store.clear()
    assert len(store) == 0
    assert store.total_issued == 2
    _make(store, "sub-c")
    assert len(store) == 1
    assert store.total_issued == 3


def test_prune_on_create_bounds_dead_records():
    """Creating sessions with zero TTL never grows the store: each
    create prunes the dead ones first."""
    store = SessionStore(ttl_seconds=0)
    for i in range(50):
        _make(store, f"sub-{i}")
    assert len(store) == 0
    assert len(store._sessions) == 0
    assert store.total_issued == 50


def test_rotation_prunes_old_revoked_record():
    """rotate() revokes the old id; the next access reaps it, so the
    store holds exactly the one live session."""
    store = SessionStore(ttl_seconds=1800)
    old = _make(store)
    new = store.rotate(
        old_session_id=old.session_id,
        subject="sub-1",
        username="u",
        roles=[LabRole.MEMBER],
        issuer=ISSUER,
    )
    assert new.session_id != old.session_id
    assert store.get(old.session_id) is None
    assert store.get(new.session_id) is not None
    assert len(store) == 1
    assert store.total_issued == 2


def test_simultaneous_logout_and_get():
    """Concurrent revoke/get on one session never errors, never
    resurrects the revoked id, and never touches another user's
    valid session."""
    store = SessionStore(ttl_seconds=1800)
    victim = _make(store, "sub-victim")
    other = _make(store, "sub-other")
    errors: list[BaseException] = []
    barrier = threading.Barrier(9)

    def hammer():
        try:
            barrier.wait(timeout=10)
            for _ in range(200):
                store.revoke(victim.session_id)
                store.get(victim.session_id)
                len(store)
        except BaseException as exc:  # noqa: BLE001 — collected, asserted below
            errors.append(exc)

    threads = [threading.Thread(target=hammer) for _ in range(8)]
    for t in threads:
        t.start()
    barrier.wait(timeout=10)
    for _ in range(200):
        assert store.get(other.session_id) is not None  # untouched throughout
    for t in threads:
        t.join(timeout=30)
    assert not errors
    assert store.get(victim.session_id) is None
    assert store.get(other.session_id) is not None
    assert len(store) == 1
    assert store.total_issued == 2
