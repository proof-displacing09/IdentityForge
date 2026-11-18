"""PKCE (RFC 7636), state/nonce generation and one-use transaction store.

PKCE in plain language: the app invents a secret (the *verifier*), sends
only a hash of it (the *challenge*) to the identity provider, and later
proves it knows the original secret when exchanging the code. An attacker
who steals the code alone cannot redeem it without the verifier.

State binds the callback to the browser session that started the login;
nonce binds the ID token to that same login attempt. Both are single-use.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import threading
from datetime import datetime, timedelta, timezone

from ..models import Transaction, TransactionStatus


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_verifier() -> str:
    """Cryptographically random PKCE verifier (43-128 chars, RFC 7636)."""
    return _b64url(secrets.token_bytes(32))


def code_challenge_s256(verifier: str) -> str:
    """S256 challenge = BASE64URL(SHA256(ASCII(verifier)))."""
    return _b64url(hashlib.sha256(verifier.encode("ascii")).digest())


def verify_pkce(verifier: str, challenge: str) -> bool:
    """Constant-time-ish comparison of a verifier against its challenge."""
    if not verifier or not challenge:
        return False
    try:
        expected = code_challenge_s256(verifier)
    except (UnicodeEncodeError, ValueError):
        return False
    return secrets.compare_digest(expected, challenge)


def generate_state() -> str:
    return _b64url(secrets.token_bytes(32))


def generate_nonce() -> str:
    return _b64url(secrets.token_bytes(32))


def generate_code() -> str:
    """Synthetic authorization code (lab fixture only, never a real code)."""
    return _b64url(secrets.token_bytes(24))


# Browser-binding cookie name prefix for login transactions (P0-07).
# The cookie value is a random token; only its SHA-256 is stored
# server-side. P1-06: each transaction gets its OWN cookie named
# ``identityforge_txn_<state>`` (see txn_binding_cookie_name), so two
# tabs can hold two live logins in the same browser without the second
# login overwriting the first tab's binding. The state is 43 base64url
# characters (alphanumerics, '-', '_'), all legal in a cookie name.
TXN_BINDING_COOKIE = "identityforge_txn"


def txn_binding_cookie_name(state: str) -> str:
    """Per-transaction binding cookie name for the given state (P1-06)."""
    return f"{TXN_BINDING_COOKIE}_{state}"


# P1-10 (v4): the global cap above is REPLACED by a per-browser quota
# plus a global safety cap. A global eviction let one unauthenticated
# local client force ANOTHER browser's waiting login into STATE_REUSED
# (measured: creating 6 transactions evicted the 1st globally). Now:
# each browser may hold at most 4 live transactions (covers the 2-tab
# and 4-tab exercises); eviction happens ONLY within the SAME
# browser's own quota (its oldest). The global cap (20) is a safety
# bound: when it is reached, a new start is REFUSED (503) rather than
# evicting another browser's transaction.
MAX_LIVE_TRANSACTIONS_PER_BROWSER = 4
MAX_LIVE_TRANSACTIONS_GLOBAL = 20
# Back-compat alias (v3 name): the per-browser cap. The old global cap
# of 5 was removed by P1-10 because it let one unauthenticated client
# evict another browser's live login.
MAX_LIVE_TRANSACTIONS = MAX_LIVE_TRANSACTIONS_PER_BROWSER


class TransactionStoreFull(Exception):
    """Raised when the global live-transaction cap is reached.

    The login handler turns this into a 503 (capacity) — it must
    never evict another browser's transaction to make room.
    """


# Anonymous browser correlation (P1-10, v4): a random 128-bit cookie
# (``identityforge_browser``) set on the login-start response when the
# browser has none (or an invalid one). The store keys quota counts by
# the SHA-256 hash of that value ONLY — the raw value is never stored,
# logged, or put in evidence. The cookie is an anonymous correlation
# id, not a secret and not an authentication factor.
BROWSER_COOKIE = "identityforge_browser"


def generate_browser_key() -> str:
    """Random 128-bit anonymous browser key (22 base64url chars)."""
    return _b64url(secrets.token_bytes(16))


def parse_browser_key(value: str | None) -> str | None:
    """Return the browser key if it is well-formed, else None.

    A well-formed key is exactly 22 base64url characters decoding to
    16 bytes. Anything else (missing, truncated, wrong alphabet) is
    treated as absent and the login handler mints a fresh key.
    """
    if not value or len(value) != 22:
        return None
    if not all(c.isalnum() or c in "-_" for c in value):
        return None
    try:
        raw = base64.urlsafe_b64decode(value + "==")
    except Exception:
        return None
    if len(raw) != 16:
        return None
    return value


def browser_key_hash(value: str) -> str:
    """SHA-256 of a browser key — the only form the store ever sees."""
    return hashlib.sha256(value.encode("ascii", "ignore")).hexdigest()


def generate_binding_token() -> str:
    return _b64url(secrets.token_bytes(32))


def binding_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii", "ignore")).hexdigest()


class TransactionStore:
    """Thread-safe, in-memory, expiring, one-use transaction store.

    Transactions live only in memory (never in the SQLite evidence DB,
    which must never hold verifiers/nonces/codes). Expired entries are
    purged lazily on access.
    """

    def __init__(self, ttl_seconds: int = 600) -> None:
        self._ttl = ttl_seconds
        self._by_state: dict[str, Transaction] = {}
        self._by_id: dict[str, Transaction] = {}
        self._lock = threading.Lock()

    def create(
        self,
        *,
        redirect_uri: str,
        client_id: str,
        issuer: str,
        browser_key_hash: str = "",
    ) -> Transaction:
        now = datetime.now(timezone.utc)
        txn = Transaction(
            transaction_id=_b64url(secrets.token_bytes(16)),
            state=generate_state(),
            nonce=generate_nonce(),
            code_verifier=generate_verifier(),
            code_challenge="",
            redirect_uri=redirect_uri,
            client_id=client_id,
            issuer=issuer,
            browser_key_hash=browser_key_hash,
            created_at=now,
            expires_at=now + timedelta(seconds=self._ttl),
        )
        txn.code_challenge = code_challenge_s256(txn.code_verifier)
        with self._lock:
            self._purge_locked(now)
            # P1-10 (v4) per-browser quota: evict ONLY the oldest
            # transaction of THIS browser when it is at its cap.
            # Another browser's transactions are never touched.
            same_browser = [
                t for t in self._by_state.values() if t.browser_key_hash == browser_key_hash
            ]
            if len(same_browser) >= MAX_LIVE_TRANSACTIONS_PER_BROWSER:
                oldest = min(same_browser, key=lambda t: t.created_at)
                self._by_state.pop(oldest.state, None)
                self._by_id.pop(oldest.transaction_id, None)
            elif len(self._by_state) >= MAX_LIVE_TRANSACTIONS_GLOBAL:
                # Global safety cap: refuse rather than evict another
                # browser's live login.
                raise TransactionStoreFull("global live-transaction cap reached")
            self._by_state[txn.state] = txn
            self._by_id[txn.transaction_id] = txn
        return txn

    def _purge_locked(self, now: datetime) -> None:
        expired = [s for s, t in self._by_state.items() if t.expires_at <= now]
        for s in expired:
            txn = self._by_state.pop(s)
            self._by_id.pop(txn.transaction_id, None)

    def create_bound(
        self,
        *,
        redirect_uri: str,
        client_id: str,
        issuer: str,
        browser_key_hash: str = "",
    ) -> tuple[Transaction, str]:
        """Create a transaction bound to the initiating browser (P0-07).

        Returns (transaction, raw binding token). The raw token goes only
        into the HttpOnly browser cookie; the store keeps its hash.
        ``browser_key_hash`` is the SHA-256 of the anonymous browser
        key (P1-10) used for per-browser quota accounting.
        """
        txn = self.create(
            redirect_uri=redirect_uri,
            client_id=client_id,
            issuer=issuer,
            browser_key_hash=browser_key_hash,
        )
        token = generate_binding_token()
        txn.binding_token_hash = binding_token_hash(token)
        return txn, token

    def binding_matches(self, txn: Transaction, binding_token: str | None) -> bool:
        """True if the transaction has no binding, or the presented
        browser token matches the stored hash."""
        if not txn.binding_token_hash:
            return True
        if not binding_token:
            return False
        return secrets.compare_digest(txn.binding_token_hash, binding_token_hash(binding_token))

    def lookup_by_state(self, state: str) -> Transaction | None:
        now = datetime.now(timezone.utc)
        with self._lock:
            self._purge_locked(now)
            return self._by_state.get(state)

    def consume_by_state(self, state: str, binding_token: str | None = None) -> Transaction | None:
        """One-use consume: returns the transaction once, then removes it.

        A second callback with the same state finds nothing -> rejected
        with STATE_REUSED / STATE_MISSING. This is the replay defence.
        When the transaction is browser-bound (P0-07), a callback that
        presents the wrong/missing browser token is NOT consumed and
        returns None, so the legitimate browser can still complete it.
        """
        now = datetime.now(timezone.utc)
        with self._lock:
            self._purge_locked(now)
            txn = self._by_state.get(state)
            if txn is None:
                return None
            if not self.binding_matches(txn, binding_token):
                return None
            txn = self._by_state.pop(state, None)
            if txn is None:
                return None
            self._by_id.pop(txn.transaction_id, None)
            txn.consumed = True
            txn.status = TransactionStatus.CALLBACK_RECEIVED
            return txn

    def peek(self, state: str) -> Transaction | None:
        return self.lookup_by_state(state)

    def clear(self) -> None:
        with self._lock:
            self._by_state.clear()
            self._by_id.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._by_state)
