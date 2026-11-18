"""Integration: TestClient over the real FastAPI app (Keycloak NOT RUN)."""

from __future__ import annotations

from identityforge.security.session import SESSION_COOKIE
from tests.fake_http import install_stream_fake


def _csrf(client):
    r = client.get("/api/v1/csrf-token")
    assert r.status_code == 200
    return r.json()["csrf_token"]


def _headers(client):
    token = _csrf(client)
    return {"X-CSRF-Token": token}


def test_health_and_config(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    r = client.get("/api/v1/lab/config")
    assert r.status_code == 200
    assert r.json()["client_id"] == "campus-club-portal"
    assert "client_secret" not in r.json()
    assert r.headers.get("cache-control", "").startswith("no-store")


def test_security_headers_present(client):
    r = client.get("/api/v1/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"


def test_host_check_blocks_foreign_host(client):
    r = client.get("/api/v1/health", headers={"Host": "evil.example"})
    assert r.status_code == 403


def test_scenarios_list_and_detail(client):
    r = client.get("/api/v1/scenarios")
    assert r.status_code == 200 and r.json()["count"] == 18
    r = client.get("/api/v1/scenarios/I6")
    assert r.status_code == 200 and r.json()["id"] == "I6"
    assert client.get("/api/v1/scenarios/I99").status_code == 404


def test_run_i1_via_api_and_fetch_report(client):
    r = client.post("/api/v1/runs", json={"scenario_id": "I1"}, headers=_headers(client))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "PASS" and body["scenario_id"] == "I1"
    run_id = body["run_id"]
    assert client.get(f"/api/v1/runs/{run_id}").status_code == 200
    ev = client.get(f"/api/v1/runs/{run_id}/events")
    assert ev.status_code == 200 and len(ev.json()["events"]) >= 1
    md = client.get(f"/api/v1/runs/{run_id}/report?format=md")
    assert md.status_code == 200 and "I1" in md.text and "SYNTHETIC" in md.text
    assert "Evidence saved: True" in md.text
    assert client.get("/api/v1/runs/no-such-run").status_code == 404


def test_run_each_core_scenario_via_api(client):
    for sid in ("I1", "I2", "I3", "I4", "I5", "I6", "I7"):
        r = client.post("/api/v1/runs", json={"scenario_id": sid}, headers=_headers(client))
        assert r.status_code == 200, sid
        assert r.json()["status"] == "PASS", sid


def test_run_requires_csrf(client):
    # P1-10: scenario creation writes evidence, so it enforces CSRF.
    assert client.post("/api/v1/runs", json={"scenario_id": "I1"}).status_code == 403
    r = client.post("/api/v1/runs", json={"scenario_id": "I1"}, headers=_headers(client))
    assert r.status_code == 200


def test_run_unknown_scenario_400(client):
    headers = _headers(client)
    assert (
        client.post("/api/v1/runs", json={"scenario_id": "I99"}, headers=headers).status_code == 400
    )
    assert client.post("/api/v1/runs", json={}, headers=headers).status_code == 400


def test_portal_requires_auth(client):
    assert client.get("/api/v1/portal/me").status_code == 401
    assert client.get("/api/v1/portal/member").status_code == 401
    assert client.get("/api/v1/portal/officer").status_code == 401


def test_forged_session_cookie_denied(client):
    client.cookies.set(SESSION_COOKIE, "forged-session-id")
    assert client.get("/api/v1/portal/me").status_code == 401
    assert client.get("/api/v1/portal/member").status_code == 401


def test_login_returns_503_when_keycloak_unavailable(client, monkeypatch):
    # Deterministic: simulate the outage at the HTTP layer. Login must
    # fail closed with 503 PROVIDER_UNAVAILABLE, whether or not a real
    # Keycloak happens to be running in the ambient environment.
    import httpx

    def _down(url, **kwargs):
        raise httpx.ConnectError("provider down")

    install_stream_fake(monkeypatch, get_fake=_down)
    r = client.get("/auth/login", follow_redirects=False)
    assert r.status_code == 503
    assert r.json()["reason"] == "PROVIDER_UNAVAILABLE"


def test_callback_unknown_state_redirects_with_safe_reason(client):
    r = client.get("/auth/callback?code=abc&state=no-such-state", follow_redirects=False)
    assert r.status_code == 302
    assert "error=STATE_REUSED" in r.headers["location"]
    assert "no-such-state" not in r.headers["location"]


def test_callback_duplicate_params_rejected(client):
    r = client.get("/auth/callback?code=a&code=b&state=s", follow_redirects=False)
    assert r.status_code == 302 and "error=CALLBACK_MALFORMED" in r.headers["location"]


def test_logout_csrf_denied_without_token(client):
    r = client.post("/auth/logout")
    assert r.status_code == 403


def test_reset_requires_csrf_session_and_officer(client):
    # P0-01 (v3): reset is officer-only. CSRF alone no longer suffices:
    # no CSRF -> 403 csrf_denied; CSRF but no session -> 401; a
    # student session -> 403 policy_denied. Full officer success (with
    # confirmation body) is covered in test_trustline_v3_reset.py.
    run = client.post("/api/v1/runs", json={"scenario_id": "I1"}, headers=_headers(client)).json()
    assert client.post("/api/v1/lab/reset").status_code == 403
    headers = _headers(client)
    r = client.post("/api/v1/lab/reset", json={"confirm": "RESET_LAB"}, headers=headers)
    assert r.status_code == 401
    assert r.json()["detail"] == "unauthenticated"
    # Nothing was cleared by the denied attempts.
    assert client.get(f"/api/v1/runs/{run['run_id']}").status_code == 200


def test_no_shortcut_login_endpoint(client):
    for path in ("/auth/dev-login", "/auth/test-login", "/api/v1/dev/session"):
        assert client.get(path).status_code == 404
