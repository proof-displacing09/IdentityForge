"""Operation Trustline v7.2 — IF-V7.1-01 disposable-project marker (backend).

GET /api/v1/lab/status gains `disposable_project_id`, present ONLY when
the backend was started with IDENTITYFORGE_DISPOSABLE_PROJECT_ID set to
a well-formed UUID. The marker is a NON-SECRET attestation (a random
UUID scoped to a disposable project), never a token or credential:
live-gate.py reset refuses to run unless the --disposable-project-id
flag it was given matches the value the responding backend itself
reports, so a persistent lab (no marker) can never be reset by mistake.

Failing-first for IF-V7.1-01: written against the v7.1 status payload
(no marker field at all) — test_lab_status_reports_marker_when_env_set
fails there; the rest pin the fail-closed shape (absent / malformed /
nil markers are never reported).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from identityforge.api.app import create_app
from identityforge.config import Settings

MARKER = "123e4567-e89b-12d3-a456-426614174000"
OTHER_MARKER = "123e4567-e89b-12d3-a456-426614174001"
NIL_MARKER = "00000000-0000-0000-0000-000000000000"


@pytest.fixture()
def client(tmp_path):
    app = create_app(settings=Settings(), db_path=str(tmp_path / "test.db"))
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_lab_status_omits_marker_when_env_unset(monkeypatch, client):
    """Persistent lab: no env var -> no marker field at all."""
    monkeypatch.delenv("IDENTITYFORGE_DISPOSABLE_PROJECT_ID", raising=False)
    resp = client.get("/api/v1/lab/status")
    assert resp.status_code == 200
    assert "disposable_project_id" not in resp.json()


def test_lab_status_reports_marker_when_env_set(monkeypatch, client):
    """Disposable backend: the exact marker it was started with."""
    monkeypatch.setenv("IDENTITYFORGE_DISPOSABLE_PROJECT_ID", MARKER)
    resp = client.get("/api/v1/lab/status")
    assert resp.status_code == 200
    assert resp.json()["disposable_project_id"] == MARKER


def test_lab_status_omits_malformed_marker(monkeypatch, client):
    """A malformed marker must never be reported (fail closed downstream)."""
    monkeypatch.setenv("IDENTITYFORGE_DISPOSABLE_PROJECT_ID", "not-a-uuid")
    resp = client.get("/api/v1/lab/status")
    assert resp.status_code == 200
    assert "disposable_project_id" not in resp.json()


def test_lab_status_omits_nil_marker(monkeypatch, client):
    """The nil UUID is not a project marker — never reported."""
    monkeypatch.setenv("IDENTITYFORGE_DISPOSABLE_PROJECT_ID", NIL_MARKER)
    resp = client.get("/api/v1/lab/status")
    assert resp.status_code == 200
    assert "disposable_project_id" not in resp.json()


def test_lab_status_normalises_marker_case(monkeypatch, client):
    """Uppercase UUID input is reported in canonical lowercase form."""
    monkeypatch.setenv("IDENTITYFORGE_DISPOSABLE_PROJECT_ID", MARKER.upper())
    resp = client.get("/api/v1/lab/status")
    assert resp.status_code == 200
    assert resp.json()["disposable_project_id"] == MARKER


def test_lab_status_marker_is_a_uuid(monkeypatch, client):
    """Whatever is reported parses as a UUID (gate compares canonical)."""
    monkeypatch.setenv("IDENTITYFORGE_DISPOSABLE_PROJECT_ID", OTHER_MARKER)
    resp = client.get("/api/v1/lab/status")
    assert resp.status_code == 200
    assert uuid.UUID(resp.json()["disposable_project_id"]) == uuid.UUID(OTHER_MARKER)
