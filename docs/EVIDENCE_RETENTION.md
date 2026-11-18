# Evidence retention, session counts, and storage budget (Trustline v5)

This note documents the v5 fixes for IF-V4-03 (misleading session
counts), IF-V4-04 (duplicated evidence events) and IF-V4-11
(evidence retention). It is the operator-facing statement of what is
kept, for how long, and what the numbers on screen mean.

## Session counts mean ACTIVE sessions (IF-V4-03)

`SessionStore` is in-memory and lab-scale. `len(store)` — and therefore
`GET /api/v1/lab/counts` field `sessions` — counts **active sessions
only: live, unexpired, unrevoked**. Expired and revoked records are
pruned under the store lock on access (`get` / `create` / `len`), so
dead records can neither inflate the count nor accumulate over a long
lab session. Pruning only ever removes a record that is already
expired or revoked; it can never remove another user's valid session.

`GET /api/v1/lab/counts` also carries `sessions_total_issued`: the
separate, process-lifetime count of sessions ever minted by this
backend process. It is a diagnostic, not stored state — a lab reset
clears stored sessions but does not rewind it (like the
process-lifetime evidence-health counters in `GET /api/v1/lab/status`).

## Re-saving a run replaces it atomically (IF-V4-04)

`EvidenceStore.save_run()` uses **Option 2 — atomic replacement**.
Re-saving the same `run_id` replaces the report **and** its exact
event set in one SQL transaction: old events are deleted, the run row
is replaced, the new events are inserted, and the retention prune
runs — all before commit. A mid-write failure rolls everything back
and the previously stored report/events survive intact.

Option 1 (refuse duplicate run IDs with 409) was rejected: re-saves
happen on legitimate retries and imports, and refusing them would
turn a retry into a data-loss error for the caller. Normal collisions
are near-impossible anyway — run IDs are fresh UUIDs.

A foreign key, `events.run_id REFERENCES runs(run_id) ON DELETE
CASCADE`, enforces the same rule at the schema level for databases
created by v5 (with `PRAGMA foreign_keys = ON`). Pre-v5 databases
are migrated on open **only when they hold no orphan events**; the
rebuild preserves every row and id. If orphans exist, the schema is
left untouched and **nothing is deleted** — `count_orphan_events()`
(and the `orphan_events` budget field) reports them for the operator
to decide about. The retention prune is equally precise: it deletes
only events of runs pruned in that same save, and the events backstop
skips orphan rows.

## Retention policy (IF-V4-11)

Scenario evidence is a documented, bounded FIFO, pruned on save in
the same transaction as the insert (a prune failure rolls the save
back too):

| Store | Cap | What happens at the cap |
|---|---|---|
| Scenario runs (`runs`) | latest **1000** | Oldest runs pruned, with their events |
| Run timeline events (`events`) | latest **20000** | Oldest events pruned (backstop; a run's timeline is a handful of rows) |
| Live-login events (`live_login_events`) | latest **1000** | Oldest pruned (unchanged since v4, P1-10/P1-11) |

Sizing for the target machine (8 GB Windows laptop): a run report is
a few KB of JSON and a timeline is a handful of rows, so 1000 runs /
20000 events is a few MB of SQLite — far inside budget — while a long
lab session can no longer grow the database without bound.

Pruning is **not** silent arbitrary deletion: the caps and the current
counts are user-visible (see below), the prune only ever removes the
oldest evidence past a published bound, and the only way to wipe
evidence on demand *through the API* is the officer-only,
CSRF-protected, double-confirmed lab reset (`POST /api/v1/lab/reset`).
No unauthenticated caller can invoke destructive cleanup — there is
no cleanup endpoint at all. Data integrity during reset, concurrent run
writes, DB error injection and restart is covered by the v4 P1-17
transaction discipline (explicit BEGIN/COMMIT/ROLLBACK) plus the v5
tests in `backend/tests/unit/test_v5_evidence_store.py`.

> **The honest retention sentence (v6, IF-V5-08 — use this wording
> everywhere, in docs and in UI copy):** "Old evidence is
> automatically pruned at capacity; manual full reset requires an
> officer session + CSRF + two confirmations."

## Four different things — do not confuse them (v6, IF-V5-08)

"Deleting lab data" means four different actions with different
scopes, different authorization, and different reversibility. Every
doc and UI label must name which one it means:

| Action | What it removes | Who can do it | Reversible? |
|---|---|---|---|
| **Automatic pruning at capacity** | Only the OLDEST evidence past a published cap (1000 runs / 20000 events / 1000 live-login events), one save at a time, oldest first (FIFO) | Nobody — it happens on save, by the store itself | No — pruned rows are gone. Export first (see below) |
| **Manual full reset (in-app)** | ALL stored evidence (runs + live-login events), in-memory sessions, transactions, and `last_login` — in one officer action | A signed-in officer (`officer_01`) only, with a valid CSRF token and two confirmations (two dialogs in Lab Settings; the API additionally requires `{"confirm": "RESET_LAB"}`). A student gets 403 `policy_denied`; no session gets 401; bad CSRF gets 403. The operator's own session is revoked by the reset | No — cleared counts are reported, nothing is kept |
| **Session revocation** | Only the session(s): logout revokes one session; a reset revokes the operator's own session; expiry revokes by time. Revocation removes NO evidence and NO other user's session | The session owner (logout) or the reset operator; expiry is automatic | No, but nothing else is lost — evidence and the realm survive |
| **Keycloak realm / volume deletion** | EVERYTHING on disk for that service: the evidence database, the Keycloak realm data, and the volume itself (`docker compose down -v`, `scripts/reset.ps1 -Confirm` / `scripts/reset.sh --confirm`). The realm is re-imported from `keycloak/realm-import/identityforge-lab-realm.json` on the next start, but all recorded evidence and logins are gone | Whoever runs the command on the host — this is a HOST action, not an API action, and it is NOT gated by an officer session or CSRF. Do not run it on a lab whose evidence you still need; it needs your explicit decision first (see `docs/WINDOWS_SETUP.md` §5) | No — the volume and its database are deleted, not archived |

In particular: a lab reset does **not** touch Keycloak or its
volume (see `docs/API_CONTRACT.md` §2 — "It does not reset
Keycloak"), and deleting a volume is **not** a lab reset — it is a
host-side destructive cleanup that also destroys the realm. Session
revocation is **not** evidence deletion: signing out, or letting a
session expire, leaves every run and login event exactly where it
was.

## As capacity approaches — warning and safe export (v6, IF-V5-08)

The caps are visible before they bite: `GET /api/v1/lab/counts`
exposes `runs` / `runs_limit`, `events` / `events_limit` and
`live_logins` / `live_logins_limit`, and Lab Settings shows the same
counts with the sentence "The run store is AT its cap: the next
saved run will evict the oldest run" (and the equivalent for
live-login events) once a store is full. Treat "at cap" as the
warning: **export anything you still need before saving more runs
or performing more logins**, because the next save evicts the
oldest record at that cap and a pruned run cannot be recovered
from this lab.

Safe export, before eviction:

1. In the console, open **Findings & Evidence** and download the run
   report (JSON / CSV / Markdown) for each run that matters, or
   download the portfolio evidence summary for the whole lab. The
   same report is available directly as
   `GET /api/v1/runs/{run_id}/report` (JSON by default,
   `?format=md` for Markdown).
2. Check the download's provenance label
   (`SERVER_VERIFIED_ARTIFACT` / `CLIENT_DERIVED_FROM_SERVER_RUN` /
   `LOCAL_UNSAVED_FALLBACK` — see `docs/API_CONTRACT.md` §5): only
   a server-verified artifact is the backend's own report.
3. Exported files contain only redacted evidence (run decisions,
   timelines, reason codes). They never contain passwords, client
   secrets, authorization codes, ID tokens, or session cookies —
   and no exported file is signed or tamper-proof: a downloaded
   file proves only what it contains, not that it came from this
   backend. The stored report's `report_sha256` is a **content
   hash** of the stored report — an integrity check for the
   download, not a signature. Nothing in this lab claims
   cryptographic tamper-proofing from the presence of a SHA-256.

Surviving runs keep their original report and `report_sha256`
(provenance and hashes survive the prune). That hash is a **content
hash of the stored report** — an integrity check for the download,
not a signature. Nothing in this lab claims cryptographic
tamper-proofing from the presence of a SHA-256.

## Storage budget API

`EvidenceStore.storage_budget()` and `GET /api/v1/lab/counts` expose
the budget so the UI can show e.g. "342 / 1000 runs" instead of the
store silently pruning:

- `runs`, `runs_limit` (1000)
- `events`, `events_limit` (20000)
- `live_logins`, `live_logins_limit` (1000)
- `orphan_events` (pre-v5 databases only; 0 on a v5 database)
- `policy` (human-readable one-line statement of the caps)

`GET /api/v1/lab/counts` additionally carries `sessions` (active
only) and `sessions_total_issued` (process lifetime). See
`docs/API_CONTRACT.md` for the exact response shape.

## Request-body bound (IF-V4-07, for completeness)

`BoundedBodyMiddleware` buffers at most `max_request_bytes + 1`
(1,048,577) bytes even for a single 50 MiB chunk: each chunk is
sliced to the remaining allowance before it is appended, the 413
fires as soon as the delivered total is known to exceed the bound,
and a client that disconnects mid-body gets `400
client_disconnected` — the partial body is never handed to the app as
a complete request. Regression tests:
`backend/tests/security/test_v5_bounded_body.py`.
