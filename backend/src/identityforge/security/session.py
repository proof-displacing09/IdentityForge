"""Server-side opaque sessions.

The browser holds only a random session id in an HttpOnly, SameSite=Lax
cookie. All identity/role data lives server-side. Sessions:
- are created only after a validated ID token (never from a raw cookie);
- rotate on login (a pre-login / attacker-known id is never promoted);
- expire after 30 minutes; logout revokes immediately and the old id
  can never be resurrected.
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from ..models import LabRole, SessionRecord

SESSION_COOKIE = "identityforge_session"
CSRF_COOKIE = "identityforge_csrf"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SessionStore:
    """Thread-safe in-memory session store (lab scale; SQLite holds evidence only).

    IF-V4-03 (v5): ``len(store)`` counts ACTIVE sessions only — live,
    unexpired, unrevoked — so ``/api/v1/lab/counts`` ``sessions`` means
    what the portal checks mean. Expired/revoked records are pruned
    under the lock on access (``get``/``create``/``len``), so dead
    records can neither inflate the count nor accumulate unboundedly
    over a long lab session. Pruning only ever removes a record that
    is already expired or revoked — never another user's valid
    session. ``total_issued`` is the separate, process-lifetime count
    of sessions ever created (diagnostic; not reset by lab reset).
    """

    def __init__(
        self, ttl_seconds: int = 1800, clock: Callable[[], datetime] | None = None
    ) -> None:
        self._ttl = ttl_seconds
        # Injectable clock (default: wall clock). Tests advance it to
        # prove future expiry without waiting out a real TTL.
        self._clock = clock or _now
        self._sessions: dict[str, SessionRecord] = {}
        self._lock = threading.Lock()
        self._total_issued = 0

    def create(
        self,
        *,
        subject: str,
        username: str,
        roles: list[LabRole],
        issuer: str,
        rotated_from: str | None = None,
        login_correlation_id: str = "",
    ) -> SessionRecord:
        now = self._clock()
        record = SessionRecord(
            session_id=secrets.token_urlsafe(32),
            subject=subject,
            username=username,
            roles=list(roles),
            issuer=issuer,
            created_at=now,
            expires_at=now + timedelta(seconds=self._ttl),
            rotated_from=rotated_from,
            login_correlation_id=login_correlation_id,
        )
        with self._lock:
            # Prune on create: login traffic is what grows the store,
            # so dead records are reaped at the same moment new ones
            # arrive — the store stays bounded by live sessions.
            self._prune_locked(now)
            self._sessions[record.session_id] = record
            self._total_issued += 1
        return record

    def rotate(
        self,
        *,
        old_session_id: str | None,
        subject: str,
        username: str,
        roles: list[LabRole],
        issuer: str,
        login_correlation_id: str = "",
    ) -> SessionRecord:
        """Login rotation: revoke any pre-existing id, mint a fresh one.

        If an attacker fixed a session id before login (I11), that id is
        revoked and the post-login session uses an unrelated fresh id.
        """
        if old_session_id:
            self.revoke(old_session_id)
        return self.create(
            subject=subject,
            username=username,
            roles=roles,
            issuer=issuer,
            rotated_from=old_session_id,
            login_correlation_id=login_correlation_id,
        )

    def get(self, session_id: str | None) -> SessionRecord | None:
        if not session_id:
            return None
        with self._lock:
            # Prune first: after this, every record left in the dict
            # is live, so a hit is a genuinely valid session.
            self._prune_locked(self._clock())
            return self._sessions.get(session_id)

    def revoke(self, session_id: str | None) -> bool:
        if not session_id:
            return False
        with self._lock:
            rec = self._sessions.get(session_id)
            if rec is None:
                return False
            # Marked, not deleted: is_revoked() can still answer
            # until the next prune, and get() already refuses the id.
            # The record is reaped (and stops being counted) at the
            # next prune; a revoked id can never be resurrected.
            rec.revoked = True
            return True

    def is_revoked(self, session_id: str) -> bool:
        with self._lock:
            rec = self._sessions.get(session_id)
            return rec is not None and rec.revoked

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()
            # total_issued is process-lifetime by design (like the
            # evidence-health counters): it is a diagnostic of how
            # many sessions this backend process ever minted, not
            # stored state, so a lab reset does not rewind it.

    def prune(self) -> int:
        """Remove expired/revoked records now; returns how many were
        removed. Normally unnecessary — get/create/len prune on
        access — but available for explicit reaping."""
        with self._lock:
            before = len(self._sessions)
            self._prune_locked(self._clock())
            return before - len(self._sessions)

    def active_count(self) -> int:
        """Live, unexpired, unrevoked sessions (same number as len())."""
        return len(self)

    @property
    def total_issued(self) -> int:
        """Sessions created since this process started (diagnostic).
        Never decremented by expiry, revocation or lab reset; compare
        with len() (active only) to see how many are dead."""
        with self._lock:
            return self._total_issued

    def _prune_locked(self, now: datetime) -> None:
        """Delete expired/revoked records. Caller must hold the lock.
        The decision is per-record (its own expiry/revocation), so
        pruning can never remove another user's valid session."""
        dead = [sid for sid, rec in self._sessions.items() if rec.revoked or rec.expires_at <= now]
        for sid in dead:
            del self._sessions[sid]

    def __len__(self) -> int:
        with self._lock:
            self._prune_locked(self._clock())
            return len(self._sessions)
