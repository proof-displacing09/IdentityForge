"""Security: request-size enforcement (P1-04, Trustline v4).

The old middleware trusted Content-Length only: a chunked/streamed
body with no Content-Length was never counted, so a 1,100,036-byte
streamed POST executed the scenario (measured 2026-11-11). The
bounded ASGI middleware counts actual streamed bytes before the app
ever sees the request.

Bound semantics: 1,048,576 bytes INCLUSIVE — exactly at the bound is
allowed, one byte over is 413. Rejected bodies never reach JSON
parsing, evidence persistence, CSRF verification or the rate limiter.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from identityforge.api.app import create_app
from identityforge.config import Settings

BOUND = 1_048_576


def _body_of(n: int) -> bytes:
    """A JSON body of exactly n bytes naming scenario I1."""
    prefix = b'{"scenario_id": "I1"'
    assert len(prefix) == 20
    return prefix + b" " * (n - 21) + b"}"


def _chunked(data: bytes):
    def gen():
        yield data[:500_000]
        yield data[500_000:]

    return gen()


@pytest.fixture()
def app_client(tmp_path):
    app = create_app(settings=Settings(), db_path=str(tmp_path / "test.db"))
    client = TestClient(app, raise_server_exceptions=False)
    return app, client


def _csrf(client):
    return client.get("/api/v1/csrf-token").json()["csrf_token"]


def _runs(app_client, **kwargs):
    _, client = app_client
    return client.post("/api/v1/runs", **kwargs)


# ------------------------------------------------------------ bound checks


def test_declared_length_at_bound_allowed(app_client):
    _, client = app_client
    r = _runs(app_client, headers={"X-CSRF-Token": _csrf(client)}, content=_body_of(BOUND))
    assert r.status_code == 200


def test_declared_length_one_over_bound_rejected(app_client):
    _, client = app_client
    r = _runs(app_client, headers={"X-CSRF-Token": _csrf(client)}, content=_body_of(BOUND + 1))
    assert r.status_code == 413
    assert r.json()["detail"] == "request_too_large"


def test_chunked_no_content_length_at_bound_allowed(app_client):
    _, client = app_client
    r = _runs(
        app_client,
        headers={"X-CSRF-Token": _csrf(client)},
        content=_chunked(_body_of(BOUND)),
    )
    assert r.status_code == 200


def test_chunked_no_content_length_over_bound_rejected(app_client):
    """P1-04 regression: the streamed body that used to execute (200)
    is now 413 — the byte count, not the header, rules."""
    _, client = app_client
    r = _runs(
        app_client,
        headers={"X-CSRF-Token": _csrf(client)},
        content=_chunked(_body_of(BOUND + 100_000)),
    )
    assert r.status_code == 413
    assert r.json()["detail"] == "request_too_large"


def test_declared_short_length_with_longer_actual_body_rejected(app_client):
    """Declared Content-Length says 10, the actual body is over the
    bound: the actual byte count rules, so this is 413, not a smuggled
    execution and not a silent truncation."""
    _, client = app_client
    r = _runs(
        app_client,
        headers={"X-CSRF-Token": _csrf(client), "Content-Length": "10"},
        content=_body_of(BOUND + 1),
    )
    assert r.status_code == 413


# ------------------------------------------------------- malformed lengths


@pytest.mark.parametrize("bad", ["abc", "-5", "1.5", "", "  ", "+5", "10, 10"])
def test_malformed_content_length_is_400(app_client, bad):
    _, client = app_client
    r = client.get("/api/v1/health", headers={"Content-Length": bad})
    assert r.status_code == 400
    assert r.json()["detail"] == "malformed_content_length"


def test_duplicate_conflicting_content_length_is_400(app_client):
    _, client = app_client
    r = client.get(
        "/api/v1/health",
        headers=[("Content-Length", "100"), ("Content-Length", "200")],
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "malformed_content_length"


def test_duplicate_identical_content_length_is_accepted(app_client):
    """Identical duplicate values collapse to one effective value."""
    _, client = app_client
    r = client.post(
        "/api/v1/runs",
        headers=[
            ("X-CSRF-Token", _csrf(client)),
            ("Content-Length", "21"),
            ("Content-Length", "21"),
        ],
        content=b'{"scenario_id": "I1"}',
    )
    assert r.status_code == 200


# ------------------------------------------------- in-bound validation kept


def test_inbound_json_validation_unchanged(app_client):
    _, client = app_client
    tok = _csrf(client)
    # Valid run still executes.
    assert (
        _runs(app_client, headers={"X-CSRF-Token": tok}, json={"scenario_id": "I1"}).status_code
        == 200
    )
    # Array body is still invalid JSON for the endpoint.
    assert _runs(app_client, headers={"X-CSRF-Token": tok}, json=[1, 2]).status_code == 400
    # Missing scenario id is still a controlled 400.
    assert _runs(app_client, headers={"X-CSRF-Token": tok}, json={}).status_code == 400
    # Unknown scenario is still a controlled 400.
    assert (
        _runs(app_client, headers={"X-CSRF-Token": tok}, json={"scenario_id": "I99"}).status_code
        == 400
    )


# --------------------------------------------- CSRF / rate-limit interaction


def test_oversized_request_needs_no_csrf_and_consumes_no_rate_budget(app_client):
    """A 413 must not require CSRF and must not consume rate budget:
    35 oversized requests (no CSRF token at all) are all 413 — never
    403 and never 429 — and a normal in-bound request afterwards
    still succeeds."""
    app, client = app_client
    for _ in range(35):
        r = _runs(app_client, content=_chunked(_body_of(BOUND + 1)))
        assert r.status_code == 413, r.status_code
    # Rate budget untouched: a normal run still works.
    r = _runs(app_client, headers={"X-CSRF-Token": _csrf(client)}, json={"scenario_id": "I1"})
    assert r.status_code == 200
    assert app.state.evidence.counts()["runs"] == 1


def test_inbound_request_still_requires_csrf(app_client):
    """The size gate does not weaken CSRF: an in-bound request without
    a token is still 403."""
    _, client = app_client
    r = _runs(app_client, json={"scenario_id": "I1"})
    assert r.status_code == 403
    assert r.json()["detail"] == "csrf_denied"


def test_no_evidence_row_saved_for_rejected_oversized_requests(app_client):
    """Rejected oversized requests write nothing to the evidence store."""
    app, client = app_client
    tok = _csrf(client)
    assert (
        _runs(app_client, headers={"X-CSRF-Token": tok}, content=_body_of(BOUND + 1)).status_code
        == 413
    )
    assert (
        _runs(
            app_client, headers={"X-CSRF-Token": tok}, content=_chunked(_body_of(BOUND + 5000))
        ).status_code
        == 413
    )
    assert app.state.evidence.counts() == {
        "runs": 0,
        "live_login_events": 0,
        "live_login_transactions": 0,
        "live_login_session_created_observed": 0,
        "live_login_successful_transactions": 0,
        "live_login_incomplete_transactions": 0,
        "live_login_event_limit": 1000,
        "live_logins": 0,
    }


def test_malformed_requests_never_crash_the_app(app_client):
    """Every malformed size case returns a controlled 4xx and the app
    keeps serving afterwards."""
    _, client = app_client
    for headers in (
        {"Content-Length": "abc"},
        {"Content-Length": "-1"},
    ):
        r = client.get("/api/v1/health", headers=headers)
        assert r.status_code == 400
    r = client.get(
        "/api/v1/health",
        headers=[("Content-Length", "1"), ("Content-Length", "2")],
    )
    assert r.status_code == 400
    assert client.get("/api/v1/health").status_code == 200
