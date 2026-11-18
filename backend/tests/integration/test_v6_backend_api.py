"""Operation Trustline v6 — WS1 backend at the HTTP layer.

IF-V5-05: a single backend version source (1.8.5) propagated to
pyproject.toml, FastAPI metadata and /api/v1/health — the frontend
About page reads it via the API.
IF-V5-02: /api/v1/lab/counts separates live-login EVENTS,
TRANSACTIONS and SUCCESSFUL transactions (deprecated ``live_logins``
alias still counts events).
IF-V5-03: GET /api/v1/runs/{id}/events reports timeline completeness
and the stored report hash matches what the API returns.
IF-V5-04: GET /api/v1/live-logins/{id} exposes the completeness
assessment for truncated/legacy transactions.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import identityforge
from identityforge.api.app import create_app
from identityforge.config import Settings
from identityforge.security.redaction import canonical_hash

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture()
def app_client(tmp_path):
    app = create_app(settings=Settings(), db_path=str(tmp_path / "test.db"))
    client = TestClient(app, raise_server_exceptions=False)
    return app, client


def _csrf(client):
    return client.get("/api/v1/csrf-token").json()["csrf_token"]


def _live_event(corr, stage, outcome="ok"):
    return {
        "correlation_id": corr,
        "stage": stage,
        "outcome": outcome,
        "reason_code": "OK",
        "subject_hash": "",
        "username": "student_01",
        "detail": "",
        "at": "2026-11-11T00:00:00Z",
    }


# ------------------------------------------------------------------ IF-V5-05


def test_version_single_source_1_7_4():
    """One version source: identityforge.__version__ is 1.8.5 and
    backend/pyproject.toml agrees — no second literal to drift."""
    assert identityforge.__version__ == "1.8.5"
    pyproject = tomllib.loads((BACKEND_DIR / "pyproject.toml").read_text())
    assert pyproject["project"]["version"] == "1.8.5"


def test_health_and_fastapi_metadata_report_1_7_4(app_client):
    """FastAPI metadata and /api/v1/health report the same 1.8.5
    the backend source defines (what the frontend About reads)."""
    app, client = app_client
    assert app.version == "1.8.5"
    assert app.title == "IdentityForge"
    health = client.get("/api/v1/health").json()
    assert health["status"] == "ok"
    assert health["version"] == "1.8.5"


# ------------------------------------------------------------------ IF-V5-02


def test_lab_counts_separates_live_login_events_transactions_successful(app_client):
    """2 transactions / 7 events / 1 successful login: counts says
    exactly that — never 7 'live logins'."""
    app, client = app_client
    for stage in [
        "AUTH_STARTED",
        "CALLBACK_RECEIVED",
        "BINDING_VERIFIED",
        "TOKEN_ENDPOINT",
        "ID_TOKEN_VALIDATED",
        "SESSION_CREATED",
    ]:
        app.state.evidence.save_live_event(_live_event("txn-A", stage))
    app.state.evidence.save_live_event(_live_event("txn-B", "AUTH_STARTED"))
    counts = client.get("/api/v1/lab/counts").json()
    assert counts["live_login_events"] == 7
    assert counts["live_login_transactions"] == 2
    assert counts["live_login_successful_transactions"] == 1
    # IF-V6-02 (v7): the full login is a verified success (observed
    # 1, successful 1); the started-only transaction is incomplete.
    assert counts["live_login_session_created_observed"] == 1
    assert counts["live_login_incomplete_transactions"] == 1
    assert counts["live_login_event_limit"] == 1000
    assert counts["live_logins"] == 7  # deprecated alias, still EVENTS
    assert counts["runs"] == 0


def test_lab_counts_full_shape(app_client):
    """The whole counts payload, fresh store: new keys present,
    limits honest, alias present."""
    _, client = app_client
    assert client.get("/api/v1/lab/counts").json() == {
        "runs": 0,
        "sessions": 0,
        "sessions_total_issued": 0,
        "live_login_events": 0,
        "live_login_transactions": 0,
        "live_login_session_created_observed": 0,
        "live_login_successful_transactions": 0,
        "live_login_incomplete_transactions": 0,
        "live_login_event_limit": 1000,
        "live_logins": 0,
        "transactions": 0,
        "events": 0,
        "runs_limit": 1000,
        "events_limit": 20000,
        "live_logins_limit": 1000,
    }


# ------------------------------------------------------------------ IF-V5-03


def test_run_events_endpoint_reports_timeline_complete(app_client):
    """Events endpoint data matches the report timeline exactly and
    says so: timeline_complete, identical step ids/outcomes/reasons
    and counts."""
    app, client = app_client
    r = client.post(
        "/api/v1/runs",
        headers={"X-CSRF-Token": _csrf(client)},
        json={"scenario_id": "I6"},
    )
    assert r.status_code == 200
    run_id = r.json()["run_id"]
    report = client.get(f"/api/v1/runs/{run_id}").json()
    events_body = client.get(f"/api/v1/runs/{run_id}/events").json()
    assert events_body["timeline_complete"] is True
    assert events_body["timeline_steps"] == len(report["timeline"])
    assert events_body["events_stored"] == len(report["timeline"])
    assert [e["step"] for e in events_body["events"]] == [s["step"] for s in report["timeline"]]
    assert [e["outcome"] for e in events_body["events"]] == [
        s["outcome"] for s in report["timeline"]
    ]
    assert [e["reason_code"] for e in events_body["events"]] == [
        s["reason_code"] for s in report["timeline"]
    ]


def test_run_report_hash_matches_stored_hash(app_client):
    """The markdown report's SHA-256 is the stored report hash, and
    the stored hash equals canonical_hash of the JSON the API
    returns — one hash, one value, everywhere. (A content hash,
    not a signature.)"""
    app, client = app_client
    r = client.post(
        "/api/v1/runs",
        headers={"X-CSRF-Token": _csrf(client)},
        json={"scenario_id": "I6"},
    )
    run_id = r.json()["run_id"]
    report = client.get(f"/api/v1/runs/{run_id}").json()
    stored = app.state.evidence._conn.execute(  # noqa: SLF001 — test reads the stored row
        "SELECT report_sha256 FROM runs WHERE run_id=?", (run_id,)
    ).fetchone()[0]
    assert stored == canonical_hash(report)
    md = client.get(f"/api/v1/runs/{run_id}/report?format=md").text
    assert f"- Report SHA-256: {stored}" in md


# ------------------------------------------------------------------ IF-V5-04


def test_live_login_endpoint_reports_truncated_transaction(app_client):
    """A legacy split transaction (tail only) is exposed as
    incomplete, unsuccessful, with its missing stages — never as a
    green login."""
    app, client = app_client
    for stage in ["TOKEN_ENDPOINT", "ID_TOKEN_VALIDATED", "SESSION_CREATED"]:
        app.state.evidence.save_live_event(_live_event("txn-tail", stage))
    body = client.get("/api/v1/live-logins/txn-tail").json()
    assert body["timeline_complete"] is False
    assert body["successful"] is False
    assert body["missing_stages"] == ["AUTH_STARTED", "CALLBACK_RECEIVED", "BINDING_VERIFIED"]
    assert body["truncated_at"] == "SESSION_CREATED"
    assert body["retention_reason"] is not None
    assert client.get("/api/v1/live-logins").json()["logins"][0]["successful"] is False


def test_live_login_endpoint_reports_complete_login(app_client):
    """A fully observed login reads complete and successful through
    the API, with no missing stages."""
    app, client = app_client
    for stage in [
        "AUTH_STARTED",
        "CALLBACK_RECEIVED",
        "BINDING_VERIFIED",
        "TOKEN_ENDPOINT",
        "ID_TOKEN_VALIDATED",
        "SESSION_CREATED",
    ]:
        app.state.evidence.save_live_event(_live_event("txn-ok", stage))
    body = client.get("/api/v1/live-logins/txn-ok").json()
    assert body["timeline_complete"] is True
    assert body["successful"] is True
    assert body["missing_stages"] == []
    assert body["truncated_at"] is None
    assert body["retention_reason"] is None
