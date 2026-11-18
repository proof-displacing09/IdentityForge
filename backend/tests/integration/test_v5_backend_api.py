"""Operation Trustline v5 — IF-V4-03 / IF-V4-11 at the HTTP layer.

GET /api/v1/lab/counts reports ACTIVE sessions only (plus the
separate process-lifetime total and the storage budget), and there
is no unauthenticated destructive-cleanup route: the officer-only
lab reset stays the only MANUAL way to wipe evidence (retention
pruning is automatic, at capacity, on save — see IF-V5-08).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from identityforge.api.app import create_app
from identityforge.config import Settings
from identityforge.models import LabRole

ISSUER = "http://127.0.0.1:8080/realms/identityforge-lab"


@pytest.fixture()
def app_client(tmp_path):
    app = create_app(settings=Settings(), db_path=str(tmp_path / "test.db"))
    client = TestClient(app, raise_server_exceptions=False)
    return app, client


def _csrf(client):
    return client.get("/api/v1/csrf-token").json()["csrf_token"]


def test_lab_counts_exposes_storage_budget(app_client):
    """counts carries the budget fields; creating a run moves the
    counts but never the limits."""
    app, client = app_client
    before = client.get("/api/v1/lab/counts").json()
    assert before == {
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
    r = client.post(
        "/api/v1/runs",
        headers={"X-CSRF-Token": _csrf(client)},
        json={"scenario_id": "I6"},
    )
    assert r.status_code == 200
    after = client.get("/api/v1/lab/counts").json()
    assert after["runs"] == 1
    assert after["events"] == 1  # one I6 run stores one timeline event
    assert after["runs_limit"] == 1000
    assert after["events_limit"] == 20000
    assert after["live_logins_limit"] == 1000


def test_lab_counts_sessions_is_active_only(app_client):
    """A revoked session stops being counted as a session, while the
    separate total-issued count still records that it existed."""
    app, client = app_client
    store = app.state.session_store
    rec = store.create(subject="sub-1", username="u", roles=[LabRole.MEMBER], issuer=ISSUER)
    counts = client.get("/api/v1/lab/counts").json()
    assert counts["sessions"] == 1
    assert counts["sessions_total_issued"] == 1
    assert store.revoke(rec.session_id) is True
    counts = client.get("/api/v1/lab/counts").json()
    assert counts["sessions"] == 0
    assert counts["sessions_total_issued"] == 1


def test_no_unauthenticated_cleanup_route_exists(app_client):
    """There is no destructive-cleanup endpoint to call without
    auth: wrong-method on counts is 405, and a guessed cleanup path
    is 404. The officer-only POST /api/v1/lab/reset (CSRF + session
    + role + confirmation) remains the only manual wipe (retention
    pruning is automatic, at capacity, on save)."""
    _, client = app_client
    assert client.post("/api/v1/lab/counts").status_code == 405
    assert client.delete("/api/v1/lab/counts").status_code == 405
    assert client.post("/api/v1/lab/cleanup").status_code == 404
    assert client.post("/api/v1/lab/purge").status_code == 404
    assert client.delete("/api/v1/lab/storage").status_code == 404
