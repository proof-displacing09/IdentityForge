"""SQLite evidence store: redacted runs and events only.

The evidence DB holds run metadata, reason codes, timelines and report
hashes — never raw tokens, codes, verifiers, nonces, secrets or cookies.
Callers must redact before calling save_*. Separate from the in-memory
session/transaction stores, so a reset can wipe runs without touching
live login state (and vice versa).

Retention vs reset — four DIFFERENT operations, never conflated
(IF-V5-08, v6):
- Retention pruning is AUTOMATIC: when a save would exceed a
  documented cap, the store itself evicts the oldest WHOLE run (or
  the oldest WHOLE live-login transaction) in the same transaction
  as the insert. No operator action, no credentials involved.
- Manual reset is the officer-only, CSRF-protected,
  double-confirmed POST /api/v1/lab/reset API action: the ONLY
  manual destructive API action, and the only way to wipe evidence
  on demand. It also revokes all sessions (including the officer's
  own) and clears in-memory transactions.
- Session revocation only ends a portal session (SessionStore,
  in-memory); it deletes no evidence and touches no IdP state.
- Keycloak realm / volume deletion is outside this store entirely:
  it destroys the IdP itself, not lab evidence.

IF-V4-04 (v5): re-saving a run_id is an ATOMIC REPLACEMENT — the old
report AND its exact event set are replaced in the same transaction
(see save_run). A foreign key from events.run_id to runs.run_id
(ON DELETE CASCADE) enforces the same rule at the schema level for
new databases; pre-v5 databases are migrated only when they hold no
orphan events, and orphans are never silently deleted (see
_migrate_events_foreign_key and count_orphan_events).

IF-V4-11 (v5): retention is a documented, bounded FIFO — latest
MAX_RUNS scenario runs, latest MAX_RUN_EVENTS timeline events, latest
MAX_LIVE_LOGIN_EVENTS live-login events (pruned on save, in the same
transaction as the insert). The budget is user-visible via
storage_budget() / GET /api/v1/lab/counts.

IF-V5-02 (v6): live-login counts are split honestly. Saved EVENT
rows, distinct TRANSACTIONS (COUNT(DISTINCT correlation_id) in SQL)
and SUCCESSFUL transactions (transactions containing a
SESSION_CREATED event with outcome ok) are three different numbers.
Auth-start / error / rejected events are stored rows, not logins:
they count as events and as transactions, never as successful
logins. The old ``live_logins`` key survives ONLY as a deprecated
alias for the EVENT count, labelled as such wherever it appears.

IF-V6-02 (v7) — MEANING CHANGE, READ FIRST: the v6 definition of
``live_login_successful_transactions`` ("any transaction containing
a SESSION_CREATED ok row") CONTRADICTED assess_live_login_timeline(),
which correctly requires a COMPLETE canonical stage sequence ending
in SESSION_CREATED ok. A lone SESSION_CREATED ok (leading stages
never recorded) counted as 1 success while the same transaction's
detail said timeline_complete=False, successful=False. From v7 the
canonical predicate IS assess_live_login_timeline(): a verified
successful transaction is one whose recorded events form the
complete canonical sequence ending in SESSION_CREATED ok. The old
v6 meaning survives ONLY under the new, honest key
``live_login_session_created_observed`` (distinct transactions in
which a SESSION_CREATED ok row was observed — observation, not
verification), and ``live_login_incomplete_transactions`` counts
distinct transactions whose timeline is NOT complete. A complete
terminal denial (fully observed flow ending rejected/error) is
complete but not successful, so it is in NEITHER bucket. counts(),
storage_budget(), list_live_logins() and get_live_login() all share
this one predicate (_live_login_success_counts_locked); no call
site re-implements it, and no earlier stage is ever fabricated to
make an incomplete flow look VERIFIED.

IF-V5-03 (v6): the event budget evicts the OLDEST COMPLETE RUN —
all of its timeline events together — never individual event rows,
so a retained run's stored events always equal its report timeline
exactly (ordered step ids, outcomes, reason codes, counts; see
get_run_evidence_status). A single run larger than the whole event
cap is rejected with EvidenceTooLargeError before any write — never
stored partial and reported complete.

IF-V5-04 (v6): live-login retention evicts the OLDEST WHOLE
correlation_id, never individual event rows, and each transaction
is bounded by MAX_LIVE_LOGIN_EVENTS_PER_TRANSACTION. A transaction
whose recorded stages do not form a complete observed flow exposes
timeline_complete=false with missing_stages, truncated_at and a
retention_reason (see assess_live_login_timeline) — a truncated
tail can never be read as a successful login.

Nothing here claims cryptographic tamper-proofing: report_sha256 is
a content hash of the stored report (integrity check for the
download), not a signature.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from ..security.redaction import canonical_hash, redact_dict

RUNS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS runs (
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
)"""

# IF-V4-04 (v5): events.run_id references runs.run_id (ON DELETE
# CASCADE), so an event can never outlive its run and deleting a run
# deletes exactly its events. Single source of truth for the events
# DDL — the v4->v5 migration reuses it (without IF NOT EXISTS).
EVENTS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    step TEXT NOT NULL,
    outcome TEXT NOT NULL,
    reason_code TEXT,
    detail TEXT NOT NULL DEFAULT '',
    at TEXT NOT NULL
)"""

SCHEMA = (
    RUNS_TABLE_DDL
    + ";"
    + EVENTS_TABLE_DDL
    + """;
-- P0-05: redacted, BFF-observed steps of REAL Keycloak logins. One row
-- per stage; never a raw token, code, state, verifier, secret or cookie.
CREATE TABLE IF NOT EXISTS live_login_events (
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
CREATE INDEX IF NOT EXISTS idx_live_login_corr ON live_login_events(correlation_id);
"""
)

# P1-10/P1-11 (v4): retention cap for live-login events. Only the
# latest N rows are kept; older ones are pruned on insert (inside the
# same transaction as the insert), so an unprivileged actor cannot
# exhaust storage unboundedly by starting logins.
MAX_LIVE_LOGIN_EVENTS = 1000

# IF-V5-04 (v6): per-transaction cap for live-login events. A normal
# login records a handful of stages (AUTH_STARTED through
# SESSION_CREATED, plus later AUTHORIZATION_DECISION / LOGOUT rows);
# 100 bounds a pathological transaction without ever coming near a
# legitimate one. A transaction at the cap rejects further events
# with EvidenceTooLargeError instead of being pruned mid-flight —
# pruning inside a transaction would split it, which IF-V5-04
# forbids.
MAX_LIVE_LOGIN_EVENTS_PER_TRANSACTION = 100

# IF-V4-11 (v5): retention caps for scenario evidence, same discipline
# as the live-login cap. On an 8 GB laptop a run report is a few KB of
# JSON and a timeline is a handful of rows, so 1000 runs / 20000 events
# is a few MB of SQLite — far inside budget — while a long lab session
# can no longer grow the DB without bound. Pruning evicts the oldest
# WHOLE runs (IF-V5-03, v6), never individual event rows.
MAX_RUNS = 1000
MAX_RUN_EVENTS = 20000

# IF-V5-04 (v6): canonical login flow, in the order the BFF observes
# it. Post-login stages (AUTHORIZATION_DECISION, LOGOUT) may follow a
# successful SESSION_CREATED but are not part of the login flow
# itself, so they never affect completeness.
LOGIN_STAGES = (
    "AUTH_STARTED",
    "CALLBACK_RECEIVED",
    "BINDING_VERIFIED",
    "TOKEN_ENDPOINT",
    "ID_TOKEN_VALIDATED",
    "SESSION_CREATED",
)

# IF-V5-04 (v6): why a recorded transaction is incomplete. Kept as
# module constants so tests and API responses use identical wording.
_RETENTION_REASON_SKIPPED = (
    "a login stage was skipped in the recorded sequence: leading events were "
    "not recorded (pre-v6 per-row retention, an evidence save failure, or an "
    "interrupted login); the recorded outcome must not be read as a "
    "successful login"
)
_RETENTION_REASON_ENDED_EARLY = (
    "timeline ends before a terminal stage: trailing events were not recorded "
    "(interrupted login, evidence save failure, or pre-v6 per-row retention); "
    "the recorded outcome must not be read as a successful login"
)


class EvidenceTooLargeError(ValueError):
    """A single run / live-login transaction is larger than the whole
    retention budget for its kind (IF-V5-03 / IF-V5-04, v6).

    Raised BEFORE any write, so nothing partial is stored: the caller
    sees a controlled error instead of a truncated timeline reported
    as complete. The scenario engine maps this to evidence_saved=False
    (see scenarios/engine.py); the live-login path counts it as an
    evidence save failure in /api/v1/lab/status.
    """


def assess_live_login_timeline(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Assess whether recorded live-login events form a complete,
    fully observed login flow (IF-V5-04, v6). Pure function: no I/O,
    deterministic on the given (DB-sequence-ordered) events.

    Complete means the login-phase stages start at AUTH_STARTED,
    proceed in canonical order with no gaps, and reach a terminal
    stage — a SESSION_CREATED with outcome ok (success) or any stage
    with outcome rejected/error (a fully recorded failure). Post-login
    stages (AUTHORIZATION_DECISION, LOGOUT) are ignored here.

    A transaction is NOT successful merely because it contains a
    SESSION_CREATED ok row: without its observed prefix, a green tail
    proves nothing, so ``successful`` requires ``timeline_complete``.
    Incomplete results name the missing stages, the stage recording
    stopped at (``truncated_at``), and a ``retention_reason`` —
    instead of inventing the missing flow.
    """
    login = [e for e in events if e.get("stage") in LOGIN_STAGES]
    missing: list[str] = []
    gap = False
    terminal = False
    expected_idx = 0
    last_stage: str | None = None
    for event in login:
        stage = str(event.get("stage", ""))
        idx = LOGIN_STAGES.index(stage)
        last_stage = stage
        if idx < expected_idx:
            # Repeated / out-of-order stage: the recorded sequence is
            # not a clean prefix of the canonical flow.
            gap = True
            continue
        if idx > expected_idx:
            missing.extend(LOGIN_STAGES[expected_idx:idx])
            gap = True
        expected_idx = max(expected_idx, idx + 1)
        if str(event.get("outcome", "")) in ("rejected", "error"):
            terminal = True
            break
        if stage == "SESSION_CREATED" and str(event.get("outcome", "")) == "ok":
            terminal = True
            break
    if not terminal:
        # Ended before any terminal stage: everything from the first
        # gap (or the next expected stage) to the end is missing.
        missing.extend(LOGIN_STAGES[expected_idx:])
    complete = (not gap) and terminal
    successful = bool(
        complete
        and any(e.get("stage") == "SESSION_CREATED" and e.get("outcome") == "ok" for e in login)
    )
    if complete:
        reason = None
    elif gap:
        reason = _RETENTION_REASON_SKIPPED
    else:
        reason = _RETENTION_REASON_ENDED_EARLY
    return {
        "timeline_complete": complete,
        "successful": successful,
        "missing_stages": missing,
        # Nothing was truncated on a complete timeline.
        "truncated_at": None if complete else last_stage,
        "retention_reason": reason,
    }


class EvidenceStore:
    def __init__(self, db_path: str | Path = "data/identityforge.db") -> None:
        self._path = Path(db_path)
        self._lock = threading.Lock()
        if str(self._path) != ":memory:":
            self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # IF-V4-04: enforce the events -> runs foreign key. Must be
        # set outside any transaction, before the schema is created.
        self._conn.execute("PRAGMA foreign_keys = ON")
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._migrate_events_foreign_key()
            self._conn.commit()

    def _migrate_events_foreign_key(self) -> None:
        """Controlled migration (IF-V4-04, v5) for databases created
        before v5, whose events table has no runs FK.

        - No orphan events: rebuild the table with the FK (same
          columns, same ids, data preserved) inside one transaction.
        - Orphan events present: leave the schema untouched and
          delete NOTHING. count_orphan_events() reports them; the
          operator decides what to do with their data.
        """
        row = self._conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='events'"
        ).fetchone()
        if row is None or "REFERENCES runs" in (row["sql"] or ""):
            return  # new schema already (or table absent — just created)
        if self._count_orphan_events_locked() > 0:
            return  # preserve user data; do not silently delete
        try:
            self._conn.execute("BEGIN")
            self._conn.execute("ALTER TABLE events RENAME TO events_legacy_v4")
            self._conn.execute(
                EVENTS_TABLE_DDL.replace("CREATE TABLE IF NOT EXISTS", "CREATE TABLE")
            )
            self._conn.execute(
                "INSERT INTO events (id, run_id, step, outcome, reason_code, detail, at)"
                " SELECT id, run_id, step, outcome, reason_code, detail, at"
                " FROM events_legacy_v4"
            )
            self._conn.execute("DROP TABLE events_legacy_v4")
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def _count_orphan_events_locked(self) -> int:
        """Orphan count; caller must hold the lock."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM events WHERE run_id NOT IN (SELECT run_id FROM runs)"
        ).fetchone()
        return int(row[0])

    def count_orphan_events(self) -> int:
        """Events whose run_id has no runs row. Only possible in a
        pre-v5 database (the v5 FK forbids new orphans). Read-only:
        this never deletes anything."""
        with self._lock:
            return self._count_orphan_events_locked()

    def _live_login_success_counts_locked(self) -> dict[str, int]:
        """Canonical live-login counters (IF-V6-02, v7). Caller MUST
        hold the lock. The ONE shared success predicate: each
        transaction's DB-sequence-ordered events are assessed with
        assess_live_login_timeline() — the same function the
        list/detail endpoints use — so counts(), storage_budget()
        and the endpoints can never disagree again.

        - ``live_login_events``: saved event rows.
        - ``live_login_transactions``: distinct correlation_ids.
        - ``live_login_session_created_observed``: distinct
          transactions in which a SESSION_CREATED ok row was
          OBSERVED (the old v6 meaning of
          ``live_login_successful_transactions``, kept under an
          honest name — observation, not verification).
        - ``live_login_successful_transactions`` (MEANING CHANGED
          in v7): distinct transactions whose timeline is complete
          AND successful — a complete canonical stage sequence
          ending in SESSION_CREATED ok. A lone SESSION_CREATED ok
          without its observed prefix is incomplete, never a
          verified success.
        - ``live_login_incomplete_transactions``: distinct
          transactions whose timeline is NOT complete. A complete
          terminal denial is in NEITHER the successful nor the
          incomplete bucket.

        Bounded: the store holds at most MAX_LIVE_LOGIN_EVENTS
        (1000) rows, so one ordered scan + one assessment per
        transaction is O(events) and is re-run from the stored
        rows on every call — retention evicting a whole
        transaction is reflected exactly on the next read, with
        no cached counter to go stale.
        """
        rows = self._conn.execute(
            "SELECT correlation_id, stage, outcome FROM live_login_events ORDER BY id"
        ).fetchall()
        by_corr: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            by_corr.setdefault(row["correlation_id"], []).append(
                {"stage": row["stage"], "outcome": row["outcome"]}
            )
        observed = successful = incomplete = 0
        for events in by_corr.values():
            if any(e["stage"] == "SESSION_CREATED" and e["outcome"] == "ok" for e in events):
                observed += 1
            assessment = assess_live_login_timeline(events)
            if assessment["successful"]:
                successful += 1
            elif not assessment["timeline_complete"]:
                incomplete += 1
        return {
            "live_login_events": len(rows),
            "live_login_transactions": len(by_corr),
            "live_login_session_created_observed": observed,
            "live_login_successful_transactions": successful,
            "live_login_incomplete_transactions": incomplete,
        }

    def storage_budget(self) -> dict[str, Any]:
        """User-visible storage budget (IF-V4-11, v5; split counts
        IF-V5-02, v6; canonical success predicate IF-V6-02, v7): current
        stored counts against the documented retention caps, plus any
        orphan events found in a pre-v5 database. Lab metadata, not
        secrets.

        ``live_logins`` is a DEPRECATED alias for ``live_login_events``
        (saved event rows) — kept so existing readers do not silently
        change meaning; new readers must use the explicit keys.
        ``live_login_successful_transactions`` counts ONLY verified
        successes (complete canonical sequence ending in
        SESSION_CREATED ok); a lone SESSION_CREATED ok is reported
        under ``live_login_session_created_observed`` instead.
        """
        with self._lock:
            runs = self._conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            events = self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            live = self._live_login_success_counts_locked()
            orphans = self._conn.execute(
                "SELECT COUNT(*) FROM events WHERE run_id NOT IN (SELECT run_id FROM runs)"
            ).fetchone()[0]
        return {
            "runs": int(runs),
            "runs_limit": MAX_RUNS,
            "events": int(events),
            "events_limit": MAX_RUN_EVENTS,
            "live_login_events": int(live["live_login_events"]),
            "live_login_transactions": int(live["live_login_transactions"]),
            "live_login_session_created_observed": int(live["live_login_session_created_observed"]),
            "live_login_successful_transactions": int(live["live_login_successful_transactions"]),
            "live_login_incomplete_transactions": int(live["live_login_incomplete_transactions"]),
            "live_login_event_limit": MAX_LIVE_LOGIN_EVENTS,
            "live_logins": int(live["live_login_events"]),
            "live_logins_limit": MAX_LIVE_LOGIN_EVENTS,
            "orphan_events": int(orphans),
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

    def _prune_retention_locked(self) -> None:
        """Retention bounds (IF-V4-11, v5; whole-run eviction IF-V5-03,
        v6). Caller must hold the lock and be inside the save
        transaction: a prune failure rolls the whole save back.
        Keeps the latest MAX_RUNS runs by insertion order (rowid) and
        the latest MAX_RUN_EVENTS events — by evicting the OLDEST
        COMPLETE RUN, never by deleting individual event rows, so a
        retained run's stored events always equal its report timeline.

        Precision matters: only events of runs pruned RIGHT NOW are
        deleted (RETURNING gives their ids for the runs-cap step; the
        events-cap step deletes the victim run's events explicitly
        before the run row, so legacy databases without the FK stay
        consistent), and the events backstop counts only events whose
        run_id has a runs row — so pre-existing orphan events from a
        pre-v5 database are never silently deleted;
        count_orphan_events() keeps reporting them.

        Termination: each loop iteration deletes one whole run, and
        save_run rejects a single run larger than MAX_RUN_EVENTS
        before inserting, so the loop always reaches the budget.
        """
        cur = self._conn.execute(
            "DELETE FROM runs WHERE run_id NOT IN "
            "(SELECT run_id FROM runs ORDER BY rowid DESC LIMIT ?) RETURNING run_id",
            (MAX_RUNS,),
        )
        for (run_id,) in cur.fetchall():
            self._conn.execute("DELETE FROM events WHERE run_id=?", (run_id,))
        while True:
            total = self._conn.execute(
                "SELECT COUNT(*) FROM events WHERE run_id IN (SELECT run_id FROM runs)"
            ).fetchone()[0]
            if int(total) <= MAX_RUN_EVENTS:
                return
            victim = self._conn.execute(
                "SELECT run_id FROM runs ORDER BY rowid ASC LIMIT 1"
            ).fetchone()
            if victim is None:
                # No runs left: only legacy orphans remain, and those
                # are never deleted by retention.
                return
            victim_id = victim[0]
            self._conn.execute("DELETE FROM events WHERE run_id=?", (victim_id,))
            self._conn.execute("DELETE FROM runs WHERE run_id=?", (victim_id,))

    def save_run(self, report: dict[str, Any]) -> str:
        safe = redact_dict(report)
        payload = json.dumps(safe, sort_keys=True, default=str)
        run_id = str(safe.get("run_id", ""))
        # IF-V5-03 (v6): a single run larger than the whole event cap
        # can never be retained whole, so reject it BEFORE any write
        # with a controlled error — never store a truncated timeline
        # and report the save as complete. The engine maps this to
        # evidence_saved=False.
        timeline_steps = [s for s in (safe.get("timeline", []) or []) if isinstance(s, dict)]
        if len(timeline_steps) > MAX_RUN_EVENTS:
            raise EvidenceTooLargeError(
                f"run {run_id} has {len(timeline_steps)} timeline steps, exceeding "
                f"the {MAX_RUN_EVENTS}-event retention cap; the run was not saved — "
                "a single run larger than the cap cannot be retained whole"
            )
        with self._lock:
            try:
                # IF-V4-04 (v5), Option 2 — ATOMIC REPLACEMENT.
                # A re-save of the same run_id replaces the report AND
                # its exact event set: old events are deleted in the
                # SAME transaction as the run-row replace and the new
                # inserts, so a mid-write failure rolls everything
                # back and the previously stored report/events survive
                # intact. (Option 1 — refuse duplicates with 409 —
                # was rejected: re-saves happen on legitimate
                # retries/imports, and refusing them would turn a
                # retry into a data-loss error for the caller.
                # Collisions are also near-impossible in normal use:
                # run_ids are fresh UUIDs.)
                self._conn.execute("DELETE FROM events WHERE run_id=?", (run_id,))
                self._conn.execute(
                    "INSERT OR REPLACE INTO runs "
                    "(run_id, scenario_id, status, mode, secure_result, flawed_result,"
                    " secure_reason, elapsed_ms, report_json, report_sha256, created_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        run_id,
                        str(safe.get("scenario_id", "")),
                        str(safe.get("status", "")),
                        str(safe.get("mode", "")),
                        str(safe.get("secure_result", "")),
                        str(safe.get("flawed_result", "")),
                        str(safe.get("secure_reason", "")),
                        int(safe.get("elapsed_ms", 0) or 0),
                        payload,
                        canonical_hash(safe),
                        str(safe.get("started_at", "")),
                    ),
                )
                for step in timeline_steps:
                    self._conn.execute(
                        "INSERT INTO events (run_id, step, outcome, reason_code, detail, at)"
                        " VALUES (?,?,?,?,?,?)",
                        (
                            run_id,
                            str(step.get("step", "")),
                            str(step.get("outcome", "")),
                            str(step.get("reason_code") or ""),
                            str(step.get("detail", ""))[:500],
                            str(step.get("at", "")),
                        ),
                    )
                # IF-V4-11 (v5) / IF-V5-03 (v6): retention prune in
                # the same transaction — a prune failure rolls the
                # insert back too, so a save either lands with
                # retention applied or not at all.
                self._prune_retention_locked()
                self._conn.commit()
            except Exception:
                # P1-17 (v4): a mid-write failure must not leave a
                # partial run (run row without events, or vice versa)
                # reported as a successful save.
                self._conn.rollback()
                raise
        return run_id

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT report_json FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
        return json.loads(row["report_json"]) if row else None

    def get_run_evidence_status(self, run_id: str) -> dict[str, Any] | None:
        """Completeness of a retained run's evidence (IF-V5-03, v6):
        stored events vs the stored report's timeline — ordered step
        ids, outcomes and reason codes must agree exactly, or the run
        is explicitly partial. With whole-run retention a retained
        run is always complete; a missing run returns None (it was
        evicted whole by retention, or never saved). ``report_sha256``
        is the stored content hash of the stored report — the same
        value the API returns, so a client can verify it. Hash, not
        signature: no tamper-proofing is claimed.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT report_json, report_sha256 FROM runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if row is None:
                return None
            report = json.loads(row["report_json"])
            stored = self._conn.execute(
                "SELECT step, outcome, reason_code FROM events WHERE run_id=? ORDER BY id",
                (run_id,),
            ).fetchall()
        timeline = [s for s in (report.get("timeline") or []) if isinstance(s, dict)]
        complete = len(stored) == len(timeline) and all(
            e["step"] == str(s.get("step", ""))
            and e["outcome"] == str(s.get("outcome", ""))
            and (e["reason_code"] or "") == str(s.get("reason_code") or "")
            for e, s in zip(stored, timeline)
        )
        lost = max(0, len(timeline) - len(stored))
        return {
            "run_id": run_id,
            "timeline_complete": complete,
            "partial_evidence": not complete,
            "timeline_steps": len(timeline),
            "events_stored": len(stored),
            "events_retained": len(stored),
            "events_deleted": lost,
            "report_sha256": row["report_sha256"],
        }

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT report_json FROM runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [json.loads(r["report_json"]) for r in rows]

    def get_events(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT step, outcome, reason_code, detail, at FROM events"
                " WHERE run_id=? ORDER BY id",
                (run_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ---- P0-05: real Keycloak login events -------------------------------
    def save_live_event(self, event: dict[str, Any]) -> int:
        safe = redact_dict(event)
        correlation_id = str(safe.get("correlation_id", ""))
        with self._lock:
            try:
                # IF-V5-04 (v6): per-transaction cap, checked BEFORE
                # the insert. A transaction at the cap rejects further
                # events instead of being pruned mid-flight — pruning
                # inside a transaction would split it.
                per_txn = self._conn.execute(
                    "SELECT COUNT(*) FROM live_login_events WHERE correlation_id=?",
                    (correlation_id,),
                ).fetchone()[0]
                if int(per_txn) >= MAX_LIVE_LOGIN_EVENTS_PER_TRANSACTION:
                    raise EvidenceTooLargeError(
                        f"live-login transaction {correlation_id} already holds "
                        f"{int(per_txn)} events (cap "
                        f"{MAX_LIVE_LOGIN_EVENTS_PER_TRANSACTION}); the event was "
                        "not saved — a transaction is never pruned mid-flight"
                    )
                cur = self._conn.execute(
                    "INSERT INTO live_login_events "
                    "(correlation_id, stage, outcome, reason_code, subject_hash,"
                    " username, detail, at) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        correlation_id,
                        str(safe.get("stage", "")),
                        str(safe.get("outcome", "")),
                        str(safe.get("reason_code", "OK")),
                        str(safe.get("subject_hash", "")),
                        str(safe.get("username", "")),
                        str(safe.get("detail", ""))[:500],
                        str(safe.get("at", "")),
                    ),
                )
                # P1-10/P1-11 (v4) retention, whole-transaction form
                # (IF-V5-04, v6): prune the oldest WHOLE transaction
                # when the budget would otherwise split one, in the
                # SAME transaction as the insert (before commit), so a
                # prune failure rolls the insert back too. The
                # transaction just inserted is never the victim: if
                # it alone exceeds the budget, that is a controlled
                # rejection, not a silent deletion.
                while True:
                    total = self._conn.execute("SELECT COUNT(*) FROM live_login_events").fetchone()[
                        0
                    ]
                    if int(total) <= MAX_LIVE_LOGIN_EVENTS:
                        break
                    victim = self._conn.execute(
                        "SELECT correlation_id FROM live_login_events"
                        " WHERE correlation_id != ?"
                        " GROUP BY correlation_id ORDER BY MIN(id) ASC LIMIT 1",
                        (correlation_id,),
                    ).fetchone()
                    if victim is None:
                        raise EvidenceTooLargeError(
                            f"live-login transaction {correlation_id} alone exceeds "
                            f"the {MAX_LIVE_LOGIN_EVENTS}-event retention cap; "
                            "the event was not saved"
                        )
                    self._conn.execute(
                        "DELETE FROM live_login_events WHERE correlation_id=?",
                        (victim[0],),
                    )
                self._conn.commit()
                return int(cur.lastrowid)
            except Exception:
                # P1-11: a failed save must not leave a partial event row.
                self._conn.rollback()
                raise

    def counts(self) -> dict[str, int]:
        """Lab evidence counts (runs + live-login events) for the reset
        confirmation UI. Lab metadata, not secrets.

        IF-V5-02 (v6): three separate live-login numbers. Saved EVENT
        rows (``live_login_events``), distinct TRANSACTIONS
        (distinct correlation_ids — never a limit-20 list count), and
        SUCCESSFUL transactions. ``live_logins`` is a DEPRECATED alias
        for the EVENT count only, kept so existing readers do not
        silently change meaning.

        IF-V6-02 (v7) — MEANING CHANGE: ``live_login_successful_
        transactions`` now counts ONLY verified successes, i.e.
        transactions whose recorded events form a COMPLETE canonical
        stage sequence ending in SESSION_CREATED ok, as assessed by
        assess_live_login_timeline() — the same predicate the
        list/detail endpoints use. A lone SESSION_CREATED ok row
        without its observed prefix is NOT a success: it is counted
        under ``live_login_session_created_observed`` (distinct
        transactions where such a row was observed) and under
        ``live_login_incomplete_transactions`` (distinct transactions
        whose timeline is NOT complete). A complete terminal denial
        is in NEITHER the successful nor the incomplete bucket.
        """
        with self._lock:
            runs = self._conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            live = self._live_login_success_counts_locked()
        return {
            "runs": int(runs),
            "live_login_events": int(live["live_login_events"]),
            "live_login_transactions": int(live["live_login_transactions"]),
            "live_login_session_created_observed": int(live["live_login_session_created_observed"]),
            "live_login_successful_transactions": int(live["live_login_successful_transactions"]),
            "live_login_incomplete_transactions": int(live["live_login_incomplete_transactions"]),
            "live_login_event_limit": MAX_LIVE_LOGIN_EVENTS,
            # DEPRECATED alias: counts saved EVENT rows, NOT logins.
            "live_logins": int(live["live_login_events"]),
        }

    def list_live_logins(self, limit: int = 20) -> list[dict[str, Any]]:
        """Most recent real logins, each with its recorded events.

        Ordering is deterministic: most recently active transaction
        (highest event id) first. Every transaction carries its
        completeness assessment (IF-V5-04, v6) — see
        assess_live_login_timeline. Events within a transaction are
        in DB insertion order (id), never re-sorted by timestamp.
        """
        with self._lock:
            # MAX(at) is selected deliberately: a live_login_events
            # table with a corrupt/incompatible schema (e.g. a missing
            # `at` column) must fail this read closed (500), never
            # return an empty atlas as if nothing had ever been
            # recorded. The ORDER is by MAX(id) — deterministic DB
            # sequence — not by the timestamp.
            corr_rows = self._conn.execute(
                "SELECT correlation_id, MAX(id) AS last_seq, MAX(at) AS last_at"
                " FROM live_login_events"
                " GROUP BY correlation_id ORDER BY last_seq DESC LIMIT ?",
                (limit,),
            ).fetchall()
            out: list[dict[str, Any]] = []
            for row in corr_rows:
                events = self._conn.execute(
                    "SELECT correlation_id, stage, outcome, reason_code,"
                    " subject_hash, username, detail, at FROM live_login_events"
                    " WHERE correlation_id=? ORDER BY id",
                    (row["correlation_id"],),
                ).fetchall()
                event_dicts = [dict(e) for e in events]
                out.append(
                    {
                        "correlation_id": row["correlation_id"],
                        "mode": "LIVE_KEYCLOAK",
                        "last_at": row["last_at"],
                        "events": event_dicts,
                        **assess_live_login_timeline(event_dicts),
                    }
                )
            return out

    def get_live_login(self, correlation_id: str) -> dict[str, Any] | None:
        with self._lock:
            rows = self._conn.execute(
                "SELECT correlation_id, stage, outcome, reason_code,"
                " subject_hash, username, detail, at FROM live_login_events"
                " WHERE correlation_id=? ORDER BY id",
                (correlation_id,),
            ).fetchall()
        if not rows:
            return None
        event_dicts = [dict(r) for r in rows]
        return {
            "correlation_id": correlation_id,
            "mode": "LIVE_KEYCLOAK",
            "events": event_dicts,
            **assess_live_login_timeline(event_dicts),
        }

    def clear(self) -> None:
        """Manual wipe of all stored evidence (IF-V5-08, v6).

        This is the storage half of the officer-only manual reset
        (POST /api/v1/lab/reset): it deletes runs, their events, and
        live-login events. It is NOT retention pruning — retention
        prunes automatically, oldest-whole-first, at capacity, on
        save — and it is NOT session revocation (SessionStore) and
        does NOT touch Keycloak. The API layer revokes sessions
        separately and only after this clear succeeds.
        """
        with self._lock:
            try:
                self._conn.execute("DELETE FROM events")
                self._conn.execute("DELETE FROM runs")
                self._conn.execute("DELETE FROM live_login_events")
                self._conn.commit()
            except Exception:
                # P1-17 (v4): a mid-clear failure must not leave a
                # half-deleted store reported as a successful clear.
                self._conn.rollback()
                raise

    def close(self) -> None:
        with self._lock:
            self._conn.close()
