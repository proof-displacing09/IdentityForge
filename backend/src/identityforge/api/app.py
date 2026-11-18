"""FastAPI application: portal (real OIDC BFF login) + research console API.

Trust boundary: the browser talks only to this backend; the backend
talks to Keycloak. Tokens are exchanged and validated server-side only.
No token ever reaches the browser, localStorage, or a URL.

Endpoints that mint a session: only /auth/callback, only after a
validated ID token. There is no shortcut / test / dev login endpoint.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse

from .. import __version__
from ..config import Settings, get_settings, public_config
from ..evidence.store import EvidenceStore
from ..models import FailureReason, LabRole, LiveLoginEvent
from ..protocol.jwks import (
    fetch_discovery_via_transport,
    fetch_jwks_via_transport,
    post_token_via_transport,
    validate_issuer_url,
)
from ..protocol.pkce import (
    BROWSER_COOKIE,
    TransactionStore,
    TransactionStoreFull,
    browser_key_hash,
    generate_browser_key,
    parse_browser_key,
    txn_binding_cookie_name,
)
from ..protocol.redirect import check_redirect_uri
from ..protocol.validators import validate_id_token
from ..scenarios.definitions import BY_ID, get_definition
from ..scenarios.engine import run_scenario
from ..security import csrf as csrf_mod
from ..security.policy import can_access, lookup_subject
from ..security.redaction import canonical_hash
from ..security.session import CSRF_COOKIE, SESSION_COOKIE, SessionStore

logger = logging.getLogger(__name__)

MAX_RUNS_PER_MINUTE = 30
# P1-11 (v4): /auth/login start rate limits. Generous for reviewers
# (2-tab and 4-tab exercises use a handful of starts), but a flooding
# client cannot mint transactions unboundedly. Per-browser key: 30
# starts/min; global: 120 starts/min across all browsers.
MAX_LOGIN_STARTS_PER_BROWSER_PER_MINUTE = 30
MAX_LOGIN_STARTS_GLOBAL_PER_MINUTE = 120


def _disposable_project_id() -> str | None:
    """Disposable-project attestation marker (IF-V7.1-01, v7.2).

    Returns the canonical UUID from IDENTITYFORGE_DISPOSABLE_PROJECT_ID
    when the backend was started with a well-formed UUID, else None.
    The marker is a NON-SECRET attestation (a random UUID scoped to a
    disposable project), never a token or credential: live-gate.py reset
    refuses to run unless its --disposable-project-id flag matches the
    value the responding backend itself reports here, so a persistent
    lab (no marker) can never be reset by mistake. Malformed values
    and the nil UUID are never reported — fail closed downstream.
    Read from the environment per request (not cached in Settings) so
    the field tracks the process the caller actually reached."""
    raw = os.environ.get("IDENTITYFORGE_DISPOSABLE_PROJECT_ID", "")
    if not raw:
        return None
    try:
        parsed = uuid.UUID(raw.strip())
    except (ValueError, AttributeError, TypeError):
        return None
    if parsed.int == 0:
        return None
    return str(parsed)


def _security_headers(scope: dict) -> list[tuple[bytes, bytes]]:
    """Response security headers (same set the old middleware added)."""
    headers = [
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"referrer-policy", b"no-referrer"),
        (
            b"content-security-policy",
            b"default-src 'none'; frame-ancestors 'none'",
        ),
    ]
    if str(scope.get("path", "")).startswith(("/api/", "/auth/")):
        headers.append((b"cache-control", b"no-store, no-cache, must-revalidate"))
        headers.append((b"pragma", b"no-cache"))
    return headers


class BoundedBodyMiddleware:
    """Pure-ASGI middleware: host check, Content-Length semantics, and a
    genuinely bounded request-body read (P1-04).

    The previous middleware trusted Content-Length only: a chunked /
    streamed body with no Content-Length was never counted, so a
    1,100,036-byte streamed POST executed the scenario (measured
    2026-11-11). This middleware reads the request body itself, in
    bounded chunks, BEFORE invoking the downstream app.

    IF-V4-07 (v5): each chunk is SLICED to the remaining allowance
    before it is appended, so at most max_bytes + 1 bytes are ever
    buffered — even for a single 50 MiB chunk — and the 413 fires as
    soon as the delivered total is known to exceed the bound, without
    reading the rest of the stream. An oversized body gets a 413
    without the app ever seeing it — no JSON parsing, no evidence
    writes, no CSRF verification, no rate-limit consumption. A client
    that disconnects before sending a complete body gets a 400
    client_disconnected from THIS middleware whenever the ASGI server
    delivers the disconnect — but note (IF-V8-04, v8): through
    uvicorn/h11 a mid-body EOF tears the connection down at the HTTP
    layer first, so a real client observes a bare connection close
    with no response bytes instead of the 400. Either way the partial
    body is never handed to the app as if it were a complete request.

    Content-Length semantics (decided explicitly):
    - missing: count the actual streamed bytes; 413 iff actual > bound.
    - duplicate, identical raw values: use the single effective value.
    - duplicate, conflicting raw values: 400 malformed_content_length.
    - negative or non-integer: 400 malformed_content_length.
    - declared value > bound: 413 without reading the body.
    - declared short + longer actual body: the actual byte count rules;
      413 iff actual > bound (Transfer-Encoding takes precedence for
      framing; the count is authoritative either way).
    The bound is INCLUSIVE: exactly max_bytes bytes are allowed,
    max_bytes + 1 is rejected (413). Streaming is NOT banned:
    legitimate chunked browser bodies within the bound work normally.
    """

    def __init__(self, app, settings: Settings) -> None:  # type: ignore[no-untyped-def]
        self.app = app
        self._allowed_hosts = settings.allowed_hosts
        self._max_bytes = settings.max_request_bytes
        # IF-V4-07 (v5): peak bytes buffered by the most recent body
        # read (diagnostic, for the overbuffer regression test).
        self.last_peak_buffered = 0

    async def __call__(self, scope, receive, send):  # type: ignore[no-untyped-def]
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        raw_headers: list[tuple[bytes, bytes]] = scope.get("headers", [])

        def header_values(name: bytes) -> list[str]:
            return [value.decode("latin-1") for key, value in raw_headers if key.lower() == name]

        # ---- host check (unchanged from the old middleware) ------------
        hosts = header_values(b"host")
        host = (hosts[0] if hosts else "").split(":")[0].lower()
        if host and host not in self._allowed_hosts:
            await self._send_json(
                scope, send, 403, {"detail": "host_not_allowed", "reason": "HOST_NOT_ALLOWED"}
            )
            return
        # ---- Content-Length semantics ----------------------------------
        cl_values = header_values(b"content-length")
        declared: int | None = None
        if cl_values:
            if len(set(cl_values)) > 1:
                await self._send_json(scope, send, 400, {"detail": "malformed_content_length"})
                return
            raw = cl_values[0].strip()
            if not raw.isdigit():
                await self._send_json(scope, send, 400, {"detail": "malformed_content_length"})
                return
            declared = int(raw)
            if declared > self._max_bytes:
                await self._send_json(scope, send, 413, {"detail": "request_too_large"})
                return
        # ---- bounded body read (before the app ever sees the request) --
        # IF-V4-07 (v5): slice each chunk to the remaining allowance
        # BEFORE appending — the old code appended the whole chunk and
        # checked afterwards, so one huge chunk was buffered entirely.
        body = bytearray()
        exceeded = False
        complete = False
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                break
            chunk = message.get("body", b"") or b""
            if chunk:
                allowance = self._max_bytes + 1 - len(body)
                if len(chunk) > allowance:
                    body += chunk[:allowance]
                    exceeded = True
                    break
                body += chunk
                if len(body) > self._max_bytes:
                    exceeded = True
                    break
            if not message.get("more_body", False):
                complete = True
                break
        self.last_peak_buffered = len(body)
        if exceeded:
            await self._send_json(scope, send, 413, {"detail": "request_too_large"})
            return
        if not complete:
            # The client went away mid-body. Never hand a partial (or
            # empty) body to the app as a complete request — a
            # truncated-but-valid JSON body must not execute.
            await self._send_json(scope, send, 400, {"detail": "client_disconnected"})
            return
        buffered = bytes(body)
        sent = False

        async def replay_receive():  # type: ignore[no-untyped-def]
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": buffered, "more_body": False}
            return {"type": "http.disconnect"}

        async def send_with_headers(message):  # type: ignore[no-untyped-def]
            if message["type"] == "http.response.start":
                existing = {k.lower() for k, _ in message.get("headers", [])}
                extra = [(k, v) for k, v in _security_headers(scope) if k.lower() not in existing]
                message = {
                    **message,
                    "headers": list(message.get("headers", [])) + extra,
                }
            await send(message)

        await self.app(scope, replay_receive, send_with_headers)

    async def _send_json(self, scope, send, status: int, payload: dict):  # type: ignore[no-untyped-def]
        body = json.dumps(payload).encode()
        headers = [(b"content-type", b"application/json")] + _security_headers(scope)
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})


def _backend_dir() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve_db_path(settings: Settings, db_path: str | None) -> str:
    if db_path:
        return db_path
    p = Path(settings.db_path)
    if p.is_absolute():
        return str(p)
    return str(_backend_dir() / p)


def create_app(settings: Settings | None = None, db_path: str | None = None) -> FastAPI:
    s = settings or get_settings()
    app = FastAPI(title="IdentityForge", version=__version__, docs_url=None, redoc_url=None)
    app.state.settings = s
    app.state.txn_store = TransactionStore(ttl_seconds=s.transaction_ttl_seconds)
    app.state.session_store = SessionStore(ttl_seconds=s.session_ttl_seconds)
    app.state.evidence = EvidenceStore(_resolve_db_path(s, db_path))
    app.state.rate: dict[str, list[float]] = {}
    # P1-11 (v4): login-start rate buckets (per browser-key hash, and
    # one global bucket). Process lifetime; never persisted.
    app.state.login_rate: dict[str, list[float]] = {}
    app.state.login_rate_global: list[float] = []
    # Last REAL browser login verified by this backend process (P1-15).
    # None until a callback actually succeeds; never inferred from a
    # running Keycloak container or a 200 discovery response.
    app.state.last_login: dict[str, str] | None = None
    # P1-11: live-event evidence counters (process lifetime, NOT reset
    # by lab reset — they describe save health, not stored contents).
    # A broken evidence store must never silently imply a complete
    # timeline: saves are counted, failures are counted and logged
    # (sanitized) instead of swallowed. Exposed via /api/v1/lab/status.
    app.state.evidence_stats: dict[str, Any] = {
        "events_saved": 0,
        "event_save_errors": 0,
        "last_event_save_error": "",
    }

    # ---- middleware: host check, size limit, security headers ----------
    # Pure-ASGI bounded-body middleware (P1-04): counts streamed bytes,
    # so chunked bodies without Content-Length cannot bypass the limit.
    # Registered here (before any route handles a request); the class
    # lives at module level so tests can exercise it directly.
    app.add_middleware(BoundedBodyMiddleware, settings=s)

    def _session(request: Request):  # current session or None
        return app.state.session_store.get(request.cookies.get(SESSION_COOKIE))

    def _require_session(request: Request):  # raise 401 if absent/expired/revoked
        sess = _session(request)
        if sess is None:
            raise HTTPException(status_code=401, detail="unauthenticated")
        return sess

    def _check_rate(request: Request) -> None:
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        bucket = [t for t in app.state.rate.get(ip, []) if now - t < 60]
        if len(bucket) >= MAX_RUNS_PER_MINUTE:
            raise HTTPException(status_code=429, detail="rate_limited")
        bucket.append(now)
        app.state.rate[ip] = bucket

    # ---- P0-05: redacted real-login event capture -------------------------
    def _subject_hash(subject: str | None) -> str:
        if not subject:
            return ""
        return hashlib.sha256(subject.encode()).hexdigest()

    def _corr_for_state(state: str | None) -> str:
        # Pre-lookup failures have no transaction id; derive a safe
        # correlation id from a hash of the presented state (never the
        # raw value — state is a one-use secret).
        if not state:
            return "unknown"
        return "unknown-" + hashlib.sha256(state.encode()).hexdigest()[:12]

    def _live_event(
        correlation_id: str,
        stage: str,
        outcome: str,
        reason: str = "OK",
        subject: str | None = None,
        username: str = "",
        detail: str = "",
    ) -> None:
        # Best-effort: evidence failure must never break a login — but it
        # must also never be silent (P1-11). Successes and failures are
        # counted on app.state.evidence_stats and failures are logged at
        # WARNING with sanitized fields only (no tokens, codes, states,
        # verifiers, subjects, cookies or passwords).
        try:
            event = LiveLoginEvent(
                correlation_id=correlation_id,
                stage=stage,  # type: ignore[arg-type]
                outcome=outcome,  # type: ignore[arg-type]
                reason_code=reason,
                subject_hash=_subject_hash(subject),
                username=username,
                detail=detail,
                at=datetime.now(timezone.utc),
            )
            app.state.evidence.save_live_event(event.model_dump(mode="json"))
            app.state.evidence_stats["events_saved"] += 1
        except Exception as exc:
            app.state.evidence_stats["event_save_errors"] += 1
            app.state.evidence_stats["last_event_save_error"] = type(exc).__name__
            logger.warning(
                "live event save failed: stage=%s outcome=%s reason=%s error=%s",
                stage,
                outcome,
                reason,
                type(exc).__name__,
            )

    # ---- health / config -------------------------------------------------
    @app.get("/api/v1/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "identityforge-backend",
            "version": __version__,
            "provider_mode": s.provider_mode,
            "keycloak": "see /api/v1/lab/status for measured IdP status",
            "synthetic_data_label": "SYNTHETIC LAB DATA — NOT REAL IDENTITY INFORMATION",
        }

    @app.get("/api/v1/lab/status")
    def lab_status() -> dict[str, Any]:
        """Measured lab status: backend health, IdP reachability, issuer
        match, and the last REAL login verified by this backend process.
        States are honest: NOT RUN / ERROR / OK, never inferred."""
        transport_discovery = (
            f"{s.idp_transport_base.rstrip('/')}/realms/identityforge-lab"
            "/.well-known/openid-configuration"
        )
        idp: dict[str, Any] = {
            "reachable": False,
            "issuer_matches": None,
            "discovery_url": transport_discovery,
            "reason": "NOT RUN",
        }
        try:
            # P0-01 (v4): discovery is fetched via the trusted transport
            # route — the transport base is validated before the request
            # and the document is validated against the canonical issuer
            # before any endpoint from it is used.
            fetch_discovery_via_transport(s.idp_transport_base, canonical_issuer=s.issuer)
            idp["reachable"] = True
            idp["issuer_matches"] = True
            idp["reason"] = "OK"
        except Exception as exc:
            idp["reason"] = type(exc).__name__
        # P1-11: evidence save health. evidence_available is False when
        # saves have failed and nothing was ever saved — the Atlas must
        # not pretend a timeline is complete when no event was captured.
        stats = app.state.evidence_stats
        errors = int(stats["event_save_errors"])
        saved = int(stats["events_saved"])
        evidence: dict[str, Any] = {
            "events_saved": saved,
            "event_save_errors": errors,
            "evidence_available": not (errors > 0 and saved == 0),
        }
        if errors > 0:
            evidence["partial_timeline_reason"] = (
                f"{errors} live-login event save(s) failed "
                f"({stats['last_event_save_error']}); recorded timelines "
                "may be incomplete"
            )
        return {
            "backend": "ok",
            "issuer": s.issuer,
            "provider_mode": s.provider_mode,
            "idp": idp,
            "evidence": evidence,
            "last_verified_login": app.state.last_login,
            "synthetic_data_label": "SYNTHETIC LAB DATA — NOT REAL IDENTITY INFORMATION",
            **({"disposable_project_id": marker} if (marker := _disposable_project_id()) else {}),
        }

    @app.get("/api/v1/lab/config")
    def lab_config() -> dict[str, Any]:
        # P0-02: pure read. This endpoint MUST NOT mint or set a CSRF
        # cookie — an earlier version did, which silently invalidated
        # the token the frontend had cached from /api/v1/csrf-token and
        # broke reset/logout after any Settings navigation.
        return public_config(s)

    @app.get("/api/v1/csrf-token")
    def csrf_token(request: Request) -> dict[str, str]:
        # P0-02 deterministic lifecycle: return the browser's existing
        # token when it has one; mint only when it does not. The cookie
        # value and the returned header value are always identical.
        token = csrf_mod.get_or_mint_csrf_token(request)
        resp = JSONResponse({"csrf_token": token})
        resp.set_cookie(CSRF_COOKIE, token, httponly=False, samesite="lax", path="/")
        return resp

    # ---- scenarios / runs ------------------------------------------------
    @app.get("/api/v1/scenarios")
    def list_scenarios() -> dict[str, Any]:
        return {"scenarios": [d.model_dump() for d in BY_ID.values()], "count": len(BY_ID)}

    @app.get("/api/v1/scenarios/{scenario_id}")
    def get_scenario(scenario_id: str) -> dict[str, Any]:
        d = get_definition(scenario_id)
        if d is None:
            raise HTTPException(status_code=404, detail="scenario_not_found")
        return d.model_dump()

    @app.post("/api/v1/runs")
    async def create_run(request: Request) -> dict[str, Any]:
        # P1-10: scenario creation is state-changing (it writes evidence
        # to the store), so it enforces the same CSRF contract as logout
        # and reset. The CLI uses the engine directly and is unaffected.
        if csrf_mod.verify_csrf(request, s) != FailureReason.OK:
            raise HTTPException(status_code=403, detail="csrf_denied")
        _check_rate(request)
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="invalid_json")
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="invalid_json")
        raw_id = body.get("scenario_id", "")
        if not isinstance(raw_id, str):
            raise HTTPException(status_code=400, detail="invalid_json")
        scenario_id = raw_id.upper()
        if get_definition(scenario_id) is None:
            raise HTTPException(status_code=400, detail="unknown_scenario")
        result = run_scenario(scenario_id, settings=s, store=app.state.evidence)
        return result.model_dump(mode="json")

    @app.get("/api/v1/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        report = app.state.evidence.get_run(run_id)
        if report is None:
            raise HTTPException(status_code=404, detail="run_not_found")
        return report

    @app.get("/api/v1/runs/{run_id}/events")
    def get_run_events(run_id: str) -> dict[str, Any]:
        if app.state.evidence.get_run(run_id) is None:
            raise HTTPException(status_code=404, detail="run_not_found")
        # IF-V5-03 (v6): the events endpoint states completeness
        # explicitly — stored events vs the stored report timeline —
        # and carries the stored report hash, so a client can verify
        # the report it fetched is the report the store recorded.
        status = app.state.evidence.get_run_evidence_status(run_id)
        assert status is not None  # get_run above proved the run exists
        return {
            "run_id": run_id,
            "events": app.state.evidence.get_events(run_id),
            "timeline_complete": status["timeline_complete"],
            "partial_evidence": status["partial_evidence"],
            "timeline_steps": status["timeline_steps"],
            "events_stored": status["events_stored"],
            "events_retained": status["events_retained"],
            "events_deleted": status["events_deleted"],
            "report_sha256": status["report_sha256"],
        }

    # ---- P0-05: real Keycloak login evidence ------------------------------
    @app.get("/api/v1/live-logins")
    def list_live_logins() -> dict[str, Any]:
        """Redacted, BFF-observed timelines of REAL Keycloak logins.
        Namespace LIVE_KEYCLOAK — never mixed with OFFLINE_FIXTURE runs.
        No raw tokens, codes, states, verifiers or cookies are stored."""
        return {
            "mode": "LIVE_KEYCLOAK",
            "logins": app.state.evidence.list_live_logins(limit=20),
        }

    @app.get("/api/v1/live-logins/{correlation_id}")
    def get_live_login(correlation_id: str) -> dict[str, Any]:
        login = app.state.evidence.get_live_login(correlation_id)
        if login is None:
            raise HTTPException(status_code=404, detail="live_login_not_found")
        return login

    @app.get("/api/v1/runs/{run_id}/report")
    def get_run_report(run_id: str, format: str = "json"):  # noqa: A002
        report = app.state.evidence.get_run(run_id)
        if report is None:
            raise HTTPException(status_code=404, detail="run_not_found")
        if format == "md":
            lines = [
                f"# IdentityForge run {run_id}",
                "",
                f"- Scenario: {report.get('scenario_id')} — {report.get('title')}",
                f"- Mode: {report.get('mode')}",
                f"- Provenance: {report.get('evidence_provenance', 'OFFLINE_FIXTURE')}",
                f"- Evidence saved: {report.get('evidence_saved')}",
                f"- Status: {report.get('status')}",
                f"- Expected: {report.get('expected_outcome')}",
                f"- Secure result: {report.get('secure_result')} ({report.get('secure_reason')})",
                f"- Flawed fixture result: {report.get('flawed_result')}",
                f"- Flawed check omitted: {report.get('flawed_guard_omitted', '')}",
                f"- Flawed observed result: {report.get('flawed_observed_result', '')}",
                f"- Secure session created in test: {report.get('secure_session_created')}",
                f"- Flawed session created in test: {report.get('flawed_session_created')}",
                f"- Session preexisted: {report.get('session_preexisted')}",
                f"- Session revoked: {report.get('session_revoked')}",
                f"- Protected resource disclosed (flawed): {report.get('protected_resource_disclosed')}",
                f"- Elapsed: {report.get('elapsed_ms')} ms",
                f"- Report SHA-256: {canonical_hash(report)}",
                "",
                "SYNTHETIC LAB DATA — NOT REAL IDENTITY INFORMATION. "
                "Offline fixture; not a live Keycloak execution.",
            ]
            return PlainTextResponse("\n".join(lines), media_type="text/markdown")
        return report

    def _lab_counts() -> dict[str, int]:
        """Current lab evidence counts (lab metadata, not secrets).

        IF-V4-03 (v5): ``sessions`` is ACTIVE sessions only (live,
        unexpired, unrevoked — len(SessionStore) after pruning);
        ``sessions_total_issued`` is the separate process-lifetime
        total, so the two are never confused. IF-V4-11 (v5): ``events``
        and the ``*_limit`` fields expose the storage budget, so the
        UI can show "342 / 1000 runs" instead of the store silently
        pruning old evidence. IF-V5-02 (v6): live-login counts are
        split — ``live_login_events`` is saved EVENT rows,
        ``live_login_transactions`` is distinct login transactions,
        ``live_login_successful_transactions`` is transactions with a
        SESSION_CREATED ok event. ``live_logins`` is a DEPRECATED
        alias for the EVENT count only, kept so the existing frontend
        does not silently change meaning; new readers must use the
        explicit keys. IF-V6-02 (v7) — MEANING CHANGE:
        ``live_login_successful_transactions`` now counts ONLY
        verified successes (a complete canonical stage sequence
        ending in SESSION_CREATED ok, per
        assess_live_login_timeline()); a lone SESSION_CREATED ok is
        reported instead under the new
        ``live_login_session_created_observed`` (observation, not
        verification) and ``live_login_incomplete_transactions``
        counts transactions whose timeline is NOT complete. A
        complete terminal denial is in NEITHER bucket. IF-V5-08
        (v6): retention pruning is automatic at capacity; the
        officer-only reset is only the *manual* destructive API
        action."""
        ev = app.state.evidence.counts()
        budget = app.state.evidence.storage_budget()
        return {
            "runs": ev["runs"],
            "sessions": len(app.state.session_store),
            "sessions_total_issued": app.state.session_store.total_issued,
            "live_login_events": ev["live_login_events"],
            "live_login_transactions": ev["live_login_transactions"],
            "live_login_session_created_observed": ev["live_login_session_created_observed"],
            "live_login_successful_transactions": ev["live_login_successful_transactions"],
            "live_login_incomplete_transactions": ev["live_login_incomplete_transactions"],
            "live_login_event_limit": ev["live_login_event_limit"],
            "live_logins": ev["live_logins"],
            "transactions": len(app.state.txn_store),
            "events": budget["events"],
            "runs_limit": budget["runs_limit"],
            "events_limit": budget["events_limit"],
            "live_logins_limit": budget["live_logins_limit"],
        }

    @app.get("/api/v1/lab/counts")
    def lab_counts() -> dict[str, int]:
        """Read-only counts of what a reset would clear, so Settings can
        show the affected evidence before the operator confirms. No auth:
        counts are lab metadata, not secrets."""
        return _lab_counts()

    @app.post("/api/v1/lab/reset")
    async def lab_reset(request: Request):  # type: ignore[no-untyped-def]
        # P0-01 (v3): destructive reset requires ALL of:
        #   (a) a valid, unexpired, unrevoked live session whose roles
        #       include OFFICER (a logged-in lab operator, not just any
        #       browser that can fetch a CSRF token);
        #   (b) a valid CSRF token;
        #   (c) a deliberate confirmation body {"confirm": "RESET_LAB"}.
        # CSRF is NOT authentication: GET /api/v1/csrf-token is
        # intentionally public, so a token alone can never authorize
        # wiping another operator's evidence. Check order is CSRF,
        # session, role, confirmation — matching the existing convention
        # that CSRF is validated before any other work. No writes happen
        # before authorization succeeds. The officer's own session IS
        # invalidated by the clear; the response says so explicitly.
        if csrf_mod.verify_csrf(request, s) != FailureReason.OK:
            raise HTTPException(status_code=403, detail="csrf_denied")
        sess = _session(request)
        if sess is None:
            raise HTTPException(status_code=401, detail="unauthenticated")
        if LabRole.OFFICER not in sess.roles:
            raise HTTPException(status_code=403, detail="policy_denied")
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=422, detail="invalid_confirmation")
        if not isinstance(body, dict) or body.get("confirm") != "RESET_LAB":
            raise HTTPException(status_code=422, detail="invalid_confirmation")
        cleared = _lab_counts()
        # Two-stage deletion: evidence first. If the evidence clear
        # raises, abort with 500 and do NOT touch sessions — a
        # half-cleared lab (evidence gone, sessions live) is worse
        # than a failed reset.
        try:
            app.state.evidence.clear()
        except Exception:
            raise HTTPException(status_code=500, detail="reset_failed")
        app.state.session_store.clear()
        app.state.txn_store.clear()
        app.state.last_login = None
        # P0-02: reset discards prior browser state, so rotate the CSRF
        # token and hand the fresh value to the caller in-band — the
        # frontend updates its cache from this response instead of
        # discovering the rotation via a 403 on its next mutation.
        fresh = csrf_mod.rotate_csrf_token()
        resp = JSONResponse(
            {
                "status": "reset",
                "operator": sess.username,
                "cleared": cleared,
                "operator_session_revoked": True,
                "csrf_token": fresh,
            }
        )
        resp.set_cookie(CSRF_COOKIE, fresh, httponly=False, samesite="lax", path="/")
        return resp

    # ---- real OIDC login (Keycloak) --------------------------------------
    # Topology (P0-03/P0-05, see docs/KEYCLOAK_INTEGRATION.md): the browser
    # only ever sees the canonical issuer http://127.0.0.1:8080/... The
    # backend reaches Keycloak via the transport base
    # (the Compose service DNS name in Compose, loopback locally).
    # Discovery is fetched via transport, its issuer must equal the
    # canonical issuer exactly, and backchannel endpoints are rewritten
    # to the transport host only after that validation.
    def _fetch_validated_discovery() -> dict[str, str]:
        # P0-01 (v4): the discovery document is fetched through the
        # trusted transport route (transport base validated, document
        # validated against the canonical issuer) — never from a raw
        # URL assembled without provenance.
        return fetch_discovery_via_transport(s.idp_transport_base, canonical_issuer=s.issuer)

    @app.get("/auth/login")
    def login(request: Request):  # type: ignore[no-untyped-def]
        if validate_issuer_url(s.issuer, s.allowed_issuers) != FailureReason.OK:
            return JSONResponse(
                {"detail": "provider_unavailable", "reason": "UNTRUSTED_ISSUER_URL"},
                status_code=503,
            )
        # P1-10/P1-11 (v4): anonymous browser correlation + login-start
        # rate limiting. The browser key is a random 128-bit cookie;
        # only its SHA-256 is used for quota/rate accounting — the raw
        # value is never stored, logged, or put in evidence. A browser
        # without a valid key is minted one, and the key is set on
        # EVERY login response (including 429/503) so the limit sticks
        # to that browser instead of being bypassed by discarding
        # cookies; the global bucket still bounds cookie-discarding
        # clients.
        raw_key = parse_browser_key(request.cookies.get(BROWSER_COOKIE))
        minted = raw_key is None
        if minted:
            raw_key = generate_browser_key()
        key_hash = browser_key_hash(raw_key)

        def _with_browser_cookie(resp):  # type: ignore[no-untyped-def]
            if minted:
                resp.set_cookie(
                    BROWSER_COOKIE, raw_key, httponly=True, samesite="lax", path="/auth"
                )
            return resp

        now = time.time()
        rate_key = f"browser:{key_hash}"
        per_key = [t for t in app.state.login_rate.get(rate_key, []) if now - t < 60]
        global_bucket = [t for t in app.state.login_rate_global if now - t < 60]
        if (
            len(per_key) >= MAX_LOGIN_STARTS_PER_BROWSER_PER_MINUTE
            or len(global_bucket) >= MAX_LOGIN_STARTS_GLOBAL_PER_MINUTE
        ):
            return _with_browser_cookie(
                JSONResponse(
                    {"detail": "rate_limited", "reason": "LOGIN_RATE_LIMITED"},
                    status_code=429,
                )
            )
        per_key.append(now)
        app.state.login_rate[rate_key] = per_key
        global_bucket.append(now)
        app.state.login_rate_global = global_bucket
        try:
            endpoints = _fetch_validated_discovery()
        except Exception:
            return _with_browser_cookie(
                JSONResponse(
                    {"detail": "provider_unavailable", "reason": "PROVIDER_UNAVAILABLE"},
                    status_code=503,
                )
            )
        # Browser-bound transaction (P0-07, P1-06): the raw binding
        # token goes only into an HttpOnly cookie named for THIS
        # transaction, so a second login in another tab does not
        # overwrite the first tab's binding; the store keeps its hash.
        # P1-10 (v4): the transaction is accounted to this browser's
        # quota; a full global store is a 503, never another browser's
        # eviction.
        try:
            txn, binding_token = app.state.txn_store.create_bound(
                redirect_uri=s.redirect_uri,
                client_id=s.client_id,
                issuer=s.issuer,
                browser_key_hash=key_hash,
            )
        except TransactionStoreFull:
            return _with_browser_cookie(
                JSONResponse(
                    {"detail": "provider_unavailable", "reason": "TRANSACTION_STORE_FULL"},
                    status_code=503,
                )
            )
        _live_event(
            txn.transaction_id,
            "AUTH_STARTED",
            "ok",
            detail="authorization redirect issued to the canonical issuer",
        )
        params = {
            "response_type": "code",
            "client_id": s.client_id,
            "redirect_uri": s.redirect_uri,
            "scope": "openid profile email",
            "state": txn.state,
            "nonce": txn.nonce,
            "code_challenge": txn.code_challenge,
            "code_challenge_method": "S256",
        }
        resp = RedirectResponse(
            f"{endpoints['authorization_endpoint']}?{urlencode(params)}", status_code=302
        )
        resp.set_cookie(
            txn_binding_cookie_name(txn.state),
            binding_token,
            httponly=True,
            samesite="lax",
            path="/auth",
            max_age=s.transaction_ttl_seconds,
        )
        return _with_browser_cookie(resp)

    @app.get("/auth/callback")
    def callback(request: Request):  # type: ignore[no-untyped-def]
        frontend = s.frontend_url.rstrip("/")

        def fail(reason: str):  # redirect to frontend with a safe reason code only
            return RedirectResponse(f"{frontend}/?error={reason}", status_code=302)

        qp = request.query_params
        if qp.get("error"):
            _live_event(
                _corr_for_state(qp.get("state")),
                "CALLBACK_RECEIVED",
                "rejected",
                "PROVIDER_ERROR",
                detail="provider returned an error to the callback",
            )
            return fail("PROVIDER_ERROR")
        # IF-V8-02 (v8): presence checks come FIRST. The old order ran
        # the duplicate-parameter check before the missing-parameter
        # checks, so a callback with NO state (or NO code) hit
        # CALLBACK_MALFORMED via getlist() length 0 != 1 and the
        # STATE_MISSING / missing-code branches below were unreachable
        # dead code — the documented reason codes were never emitted.
        # Presence first, duplication second: both are still rejected,
        # now with the correct reason.
        state = qp.get("state")
        code = qp.get("code")
        if not state:
            _live_event(
                "unknown",
                "CALLBACK_RECEIVED",
                "rejected",
                "STATE_MISSING",
                detail="callback without a state parameter",
            )
            return fail("STATE_MISSING")
        if not code:
            _live_event(
                _corr_for_state(state),
                "CALLBACK_RECEIVED",
                "rejected",
                "CALLBACK_MALFORMED",
                detail="callback without a code parameter",
            )
            return fail("CALLBACK_MALFORMED")
        # Duplicate parameters are ambiguous -> reject (I15).
        if len(qp.getlist("state")) != 1 or len(qp.getlist("code")) != 1:
            _live_event(
                _corr_for_state(qp.get("state")),
                "CALLBACK_RECEIVED",
                "rejected",
                "CALLBACK_MALFORMED",
                detail="duplicate state/code parameters",
            )
            return fail("CALLBACK_MALFORMED")
        # Browser binding (P0-07, P1-06): the callback must come from
        # the browser that started THIS login, proven by the cookie
        # named for the presented state. A wrong/missing binding cookie
        # does NOT consume the transaction, so the legitimate browser
        # can still complete it; a different browser cannot steal it.
        txn = app.state.txn_store.lookup_by_state(state)
        if txn is None:
            _live_event(
                _corr_for_state(state),
                "CALLBACK_RECEIVED",
                "rejected",
                "STATE_REUSED",
                detail="no live transaction for the presented state",
            )
            return fail("STATE_REUSED")
        _live_event(
            txn.transaction_id,
            "CALLBACK_RECEIVED",
            "ok",
            detail="callback received from the browser",
        )
        binding_token = request.cookies.get(txn_binding_cookie_name(state))
        if not app.state.txn_store.binding_matches(txn, binding_token):
            _live_event(
                txn.transaction_id,
                "BINDING_VERIFIED",
                "rejected",
                "STATE_BINDING_MISMATCH",
                detail="callback browser is not the browser that started the login",
            )
            return fail("STATE_BINDING_MISMATCH")
        txn = app.state.txn_store.consume_by_state(state, binding_token)
        if txn is None:
            _live_event(
                _corr_for_state(state),
                "CALLBACK_RECEIVED",
                "rejected",
                "STATE_REUSED",
                detail="transaction already consumed",
            )
            return fail("STATE_REUSED")
        _live_event(
            txn.transaction_id,
            "BINDING_VERIFIED",
            "ok",
            detail="callback browser matches the login transaction",
        )
        if check_redirect_uri(txn.redirect_uri, s.allowed_redirect_uris) != FailureReason.OK:
            _live_event(
                txn.transaction_id,
                "CALLBACK_RECEIVED",
                "rejected",
                "REDIRECT_URI_MISMATCH",
                detail="transaction redirect URI not in the allowlist",
            )
            return fail("REDIRECT_URI_MISMATCH")
        try:
            endpoints = _fetch_validated_discovery()
            # P0-01 (v4): token + JWKS go through the trusted transport
            # route — canonical URLs validated before the rewrite, the
            # rewritten URLs validated narrowly, no bare fetch of a
            # transport-host URL. In Compose this reaches the configured
            # transport host; on a host run it stays loopback.
            token_resp = post_token_via_transport(
                endpoints["token_endpoint"],
                s.idp_transport_base,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": s.redirect_uri,
                    "client_id": s.client_id,
                    "code_verifier": txn.code_verifier,
                    **({"client_secret": s.client_secret} if s.client_secret else {}),
                },
            )
            token_resp.raise_for_status()
            tokens = token_resp.json()
            if not isinstance(tokens, dict):
                raise ValueError("token response is not an object")
            id_token = tokens.get("id_token")
            if not isinstance(id_token, str) or not id_token:
                raise ValueError("token response has no id_token")
            jwks = fetch_jwks_via_transport(endpoints["jwks_uri"], s.idp_transport_base)
        except Exception:
            _live_event(
                txn.transaction_id,
                "TOKEN_ENDPOINT",
                "error",
                "PROVIDER_ERROR",
                detail="token exchange or JWKS fetch failed",
            )
            return fail("PROVIDER_ERROR")
        _live_event(
            txn.transaction_id,
            "TOKEN_ENDPOINT",
            "ok",
            detail="authorization code exchanged at the token endpoint",
        )
        decision = validate_id_token(
            id_token,
            jwks=jwks,
            expected_issuer=s.issuer,
            expected_audience=s.client_id,
            expected_nonce=txn.nonce,
            clock_skew_seconds=s.clock_skew_seconds,
        )
        if not decision.valid or not decision.subject:
            _live_event(
                txn.transaction_id,
                "ID_TOKEN_VALIDATED",
                "rejected",
                decision.reason_code.value,
                detail="ID token failed validation",
            )
            return fail(decision.reason_code.value)
        _live_event(
            txn.transaction_id,
            "ID_TOKEN_VALIDATED",
            "ok",
            subject=decision.subject,
            detail="ID token signature, issuer, audience and nonce verified",
        )
        # Subject-to-policy mapping (P0-06): only pinned (issuer, sub)
        # pairs get roles; an unknown subject is rejected, never shown
        # as a username and never granted a role.
        mapped = lookup_subject(decision.subject, decision.issuer or s.issuer)
        if mapped is None:
            _live_event(
                txn.transaction_id,
                "SESSION_CREATED",
                "rejected",
                "UNKNOWN_SUBJECT",
                subject=decision.subject,
                detail="validated subject is not in the policy map",
            )
            return fail("UNKNOWN_SUBJECT")
        username, roles = mapped
        old = request.cookies.get(SESSION_COOKIE)
        record = app.state.session_store.rotate(
            old_session_id=old,
            subject=decision.subject,
            username=username,
            roles=roles,
            issuer=s.issuer,
            login_correlation_id=txn.transaction_id,
        )
        _live_event(
            txn.transaction_id,
            "SESSION_CREATED",
            "ok",
            subject=decision.subject,
            username=username,
            detail="session created and rotated on login",
        )

        app.state.last_login = {
            "at": datetime.now(timezone.utc).isoformat(),
            "username": username,
            "subject": decision.subject,
            "issuer": s.issuer,
        }
        resp = RedirectResponse(f"{frontend}/portal?login=success", status_code=302)
        resp.set_cookie(
            SESSION_COOKIE,
            record.session_id,
            httponly=True,
            samesite="lax",
            path="/",
            max_age=s.session_ttl_seconds,
        )
        # Delete ONLY this transaction's binding cookie (P1-06); other
        # tabs' in-flight logins keep their own cookies and can still
        # complete afterwards.
        resp.delete_cookie(txn_binding_cookie_name(state), path="/auth")
        return resp

    @app.post("/auth/logout")
    def logout(request: Request) -> dict[str, str]:
        if csrf_mod.verify_csrf(request, s) != FailureReason.OK:
            raise HTTPException(status_code=403, detail="csrf_denied")
        sid = request.cookies.get(SESSION_COOKIE)
        sess = app.state.session_store.get(sid)
        app.state.session_store.revoke(sid)
        # App-local revocation only: this does NOT end the IdP's SSO
        # session (see docs/AUTH_FLOW.md). The event records the local
        # revocation, nothing more.
        _live_event(
            (sess.login_correlation_id if sess else "")
            or ("sess-" + hashlib.sha256((sid or "").encode()).hexdigest()[:12]),
            "LOGOUT",
            "ok",
            subject=sess.subject if sess else None,
            username=sess.username if sess else "",
            detail="local portal session revoked (IdP SSO session untouched)",
        )
        # P0-02: hand the caller a fresh CSRF token in-band (same pattern
        # as reset) so the next mutation does not 403 on a stale cache.
        fresh = csrf_mod.rotate_csrf_token()
        resp = JSONResponse({"status": "logged_out", "csrf_token": fresh})
        resp.set_cookie(CSRF_COOKIE, fresh, httponly=False, samesite="lax", path="/")
        resp.delete_cookie(SESSION_COOKIE, path="/")
        return resp

    # ---- protected portal resources --------------------------------------
    @app.get("/api/v1/portal/me")
    def portal_me(request: Request) -> dict[str, Any]:
        sess = _require_session(request)
        return {
            "sub": sess.subject,
            "username": sess.username,
            "roles": [r.value for r in sess.roles],
            "issuer": sess.issuer,
            "expires_at": sess.expires_at.isoformat(),
            "synthetic_data_label": "SYNTHETIC LAB DATA — NOT REAL IDENTITY INFORMATION",
        }

    @app.get("/api/v1/portal/member")
    def portal_member(request: Request) -> dict[str, Any]:
        sess = _require_session(request)
        allowed = can_access(sess, "member")
        _live_event(
            sess.login_correlation_id
            or ("sess-" + hashlib.sha256((sess.session_id or "").encode()).hexdigest()[:12]),
            "AUTHORIZATION_DECISION",
            "ok" if allowed else "rejected",
            "OK" if allowed else "POLICY_DENIED",
            subject=sess.subject,
            username=sess.username,
            detail="member resource allowed" if allowed else "member resource denied",
        )
        if not allowed:
            raise HTTPException(status_code=403, detail="policy_denied")
        return {
            "resource": "member",
            "message": "Member-only club resource (synthetic).",
            "sub": sess.subject,
        }

    @app.get("/api/v1/portal/officer")
    def portal_officer(request: Request) -> dict[str, Any]:
        sess = _require_session(request)
        allowed = can_access(sess, "officer")
        _live_event(
            sess.login_correlation_id
            or ("sess-" + hashlib.sha256((sess.session_id or "").encode()).hexdigest()[:12]),
            "AUTHORIZATION_DECISION",
            "ok" if allowed else "rejected",
            "OK" if allowed else "POLICY_DENIED",
            subject=sess.subject,
            username=sess.username,
            detail="officer resource allowed" if allowed else "officer resource denied",
        )
        if not allowed:
            raise HTTPException(status_code=403, detail="policy_denied")
        return {
            "resource": "officer",
            "message": "Officer-only club resource (synthetic).",
            "sub": sess.subject,
        }

    return app


app = create_app()
