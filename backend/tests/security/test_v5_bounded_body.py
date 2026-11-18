"""Security: request-size enforcement, single-chunk overbuffer
(IF-V4-07, Trustline v5).

The v4 middleware appended each chunk whole and checked afterwards,
so one huge single chunk was buffered entirely before the 413 — a
20 MiB chunk peaked at ~42 MB traced memory (measured 2026-11-11).
The v5 middleware slices each chunk to the remaining allowance
before appending: at most max_bytes + 1 bytes are ever buffered,
the 413 fires as soon as the delivered total is known to exceed the
bound, and a mid-body disconnect never hands a partial body to the
app as a complete request.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from identityforge.api.app import BoundedBodyMiddleware, create_app
from identityforge.config import Settings

BOUND = 1_048_576


class _Downstream:
    """Records every body the middleware lets through."""

    def __init__(self) -> None:
        self.calls: list[bytes] = []

    async def __call__(self, scope, receive, send):  # type: ignore[no-untyped-def]
        body = b""
        while True:
            msg = await receive()
            if msg["type"] == "http.disconnect":
                break
            body += msg.get("body", b"") or b""
            if not msg.get("more_body", False):
                break
        self.calls.append(body)
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": b"{}"})


async def _call(mw, messages):
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/runs",
        "headers": [(b"host", b"127.0.0.1:8000")],
    }
    sent: list[dict] = []
    it = iter(messages)

    async def receive():
        try:
            return next(it)
        except StopIteration:
            return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    await mw(scope, receive, send)
    return sent


def _run(mw, messages):
    downstream = mw.app
    sent = asyncio.run(_call(mw, messages))
    assert sent, "middleware sent no response"
    return sent[0]["status"], downstream


def _middleware():
    downstream = _Downstream()
    return BoundedBodyMiddleware(downstream, Settings()), downstream


def _msg(body: bytes, more: bool):
    return {"type": "http.request", "body": body, "more_body": more}


# ------------------------------------------------- single-chunk buffering


def test_single_huge_chunk_buffered_at_most_bound_plus_one():
    """The v4 repro, direct ASGI: one 20 MiB chunk -> 413, the app
    never runs, and peak buffered bytes are exactly BOUND + 1."""
    mw, downstream = _middleware()
    status, _ = _run(mw, [_msg(b"x" * (20 * 1024 * 1024), False)])
    assert status == 413
    assert downstream.calls == []
    assert mw.last_peak_buffered == BOUND + 1


def test_single_50_mib_chunk_peak_still_bound_plus_one():
    """Same guarantee at 50 MiB: the buffered peak does not grow
    with the chunk size."""
    mw, downstream = _middleware()
    status, _ = _run(mw, [_msg(b"x" * (50 * 1024 * 1024), False)])
    assert status == 413
    assert downstream.calls == []
    assert mw.last_peak_buffered == BOUND + 1


def test_single_chunk_exactly_at_bound_allowed():
    """The inclusive bound: one chunk of exactly BOUND bytes is
    allowed and reaches the app whole."""
    mw, downstream = _middleware()
    status, _ = _run(mw, [_msg(b"x" * BOUND, False)])
    assert status == 200
    assert downstream.calls == [b"x" * BOUND]
    assert mw.last_peak_buffered == BOUND


def test_single_chunk_one_over_bound_rejected_with_minimal_buffer():
    """One chunk of BOUND + 1 -> 413 with peak BOUND + 1 (one byte
    of over-read, not a whole extra chunk)."""
    mw, downstream = _middleware()
    status, _ = _run(mw, [_msg(b"x" * (BOUND + 1), False)])
    assert status == 413
    assert downstream.calls == []
    assert mw.last_peak_buffered == BOUND + 1


def test_multi_chunk_straddling_boundary():
    """Two chunks whose total crosses the bound mid-stream -> 413,
    peak BOUND + 1, app never runs."""
    mw, downstream = _middleware()
    status, _ = _run(mw, [_msg(b"x" * (BOUND - 10), True), _msg(b"y" * 20, False)])
    assert status == 413
    assert downstream.calls == []
    assert mw.last_peak_buffered == BOUND + 1


# ------------------------------------------------------------- disconnects


def test_disconnect_mid_post_never_reaches_app():
    """Partial body then disconnect: 400 client_disconnected, and
    the truncated body is never handed to the app as a request."""
    mw, downstream = _middleware()
    status, _ = _run(
        mw,
        [
            _msg(b'{"scenario_id": "I1"', True),
            {"type": "http.disconnect"},
        ],
    )
    assert status == 400
    assert downstream.calls == []


def test_disconnect_before_any_body_never_reaches_app():
    """Client goes away before sending anything: 400, app not run."""
    mw, downstream = _middleware()
    status, _ = _run(mw, [{"type": "http.disconnect"}])
    assert status == 400
    assert downstream.calls == []


# ------------------------------------------------------- app-level (TestClient)


@pytest.fixture()
def app_client(tmp_path):
    app = create_app(settings=Settings(), db_path=str(tmp_path / "test.db"))
    client = TestClient(app, raise_server_exceptions=False)
    return app, client


def test_huge_single_body_via_testclient_is_413_without_side_effects(app_client):
    """End to end: a 20 MiB POST is 413, writes no evidence, and
    consumes no rate budget (a normal run afterwards still works)."""
    app, client = app_client
    tok = client.get("/api/v1/csrf-token").json()["csrf_token"]
    r = client.post(
        "/api/v1/runs",
        headers={"X-CSRF-Token": tok},
        content=b"x" * (20 * 1024 * 1024),
    )
    assert r.status_code == 413
    assert r.json()["detail"] == "request_too_large"
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
    r = client.post(
        "/api/v1/runs",
        headers={"X-CSRF-Token": tok},
        json={"scenario_id": "I1"},
    )
    assert r.status_code == 200
