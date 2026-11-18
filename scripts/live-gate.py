#!/usr/bin/env python3
"""IdentityForge live gate (P0-01 / P1-16): real Keycloak checks.

Drives the REAL Keycloak 26.8.2 + backend stack with plain HTTP
(stdlib only, no browser needed for these checks):

  python3 scripts/live-gate.py login     # student + officer flows
  python3 scripts/live-gate.py binding   # cross-browser + replay
  python3 scripts/live-gate.py parallel  # P1-06: two same-browser logins
  python3 scripts/live-gate.py negatives # K2 wrong PKCE, K3 bad redirect
  python3 scripts/live-gate.py reset --disposable-project-id <uuid>
                                         # P1-13: officer-only lab reset
                                         # (DESTRUCTIVE — disposable stack only;
                                         #  DEVELOPER-ONLY standalone use. The
                                         #  UUID is REQUIRED and must match the
                                         #  marker the responding backend itself
                                         #  reports via /api/v1/lab/status,
                                         #  IF-V7.1-01. Never in reviewer or
                                         #  beginner guides.)
  python3 scripts/live-gate.py all       # everything except reset (default)

Exit 0 only when every check passes; prints a step log and a JSON
summary. Requires the lab to be running (docker compose up -d, or the
host-run stack on the same loopback ports). No secrets are printed:
passwords below are the documented synthetic lab credentials (see
README.md / realm import) and are never real accounts.

Cookie note: this driver sends ALL stored cookies, including Secure
ones, over http://127.0.0.1 — mirroring a real browser (127.0.0.1 is
a secure context, so browsers send Secure cookies there over plain
HTTP). Strict HTTP clients withhold Secure cookies on http:// URLs and
get Keycloak's "Restart login cookie not found" — a driver artifact,
not an app bug.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import sys
import urllib.parse
import uuid

BASE_HOST = "127.0.0.1"
BASE_PORT = 8000
KC_PORT = 8080
REALM = "identityforge-lab"
CLIENT_ID = "campus-club-portal"
REDIRECT_URI = "http://127.0.0.1:8000/auth/callback"

# Container mode (Docker test profile, scripts/test-all.ps1): when this
# driver runs inside a container on the Compose network, 127.0.0.1 is
# the container itself, not the lab. IDENTITYFORGE_LIVE_GATE_HOST_MAP
# maps loopback ports to Compose service names, e.g.
# '{"8080": "keycloak", "8000": "backend"}'. Only the TCP connection
# host is rewritten — every URL string, redirect target, issuer check
# and cookie stays canonical, so the security assertions are
# unchanged. Unset (default): host behaviour, no rewrite. This seam is
# NOT verified in the build sandbox (no Docker there); the cold-start
# gate (CLEAN_COMPOSE_BUILD_BOOT) is the proof on a real machine.
#
# P0-02 (v4): the rewrite is TCP-route ONLY. Python http.client builds
# its default Host header FROM THE CONNECTION HOST, so connecting to
# 'backend' used to send 'Host: backend:8000' — which the backend's
# allowed-hosts check correctly rejects with 403 HOST_NOT_ALLOWED.
# request() therefore sets an explicit canonical Host header
# ('127.0.0.1:<port>') on every MAPPED connection, while unmapped
# connections keep http.client's default. Route and authority are
# different things: the log line for a mapped route records both.
def _parse_host_map(raw):
    """Parse the host-map env value strictly; raise ValueError on any
    malformed entry BEFORE any connection is attempted. A bad mapping
    must fail loudly, never silently fall back to unmapped behaviour
    (which would test the wrong thing and fail confusingly). Keys are
    loopback ports (1-65535); values are bare hostnames (no scheme,
    no path, no embedded port, no whitespace)."""
    if raw is None or raw == "":
        return {}
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"invalid IDENTITYFORGE_LIVE_GATE_HOST_MAP (not JSON): {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("IDENTITYFORGE_LIVE_GATE_HOST_MAP must be a JSON object {port: host}")
    out = {}
    for key, value in parsed.items():
        try:
            port = int(key)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"invalid host-map port key {key!r}: must be numeric") from exc
        if not 1 <= port <= 65535:
            raise ValueError(f"invalid host-map port {port}: out of range 1-65535")
        if not isinstance(value, str) or not value:
            raise ValueError(f"invalid host-map host for port {port}: must be a nonempty hostname")
        if any(c in value for c in ("/", ":", " ", "\t", "\n", "\r")) or "://" in value:
            raise ValueError(
                f"invalid host-map host {value!r} for port {port}: "
                "bare hostname only (no scheme, path, or embedded port)")
        out[port] = value
    return out


try:
    _HOST_MAP = _parse_host_map(os.environ.get("IDENTITYFORGE_LIVE_GATE_HOST_MAP", ""))
except ValueError as exc:
    print(f"live-gate: {exc}", file=sys.stderr)
    print("live-gate: fix IDENTITYFORGE_LIVE_GATE_HOST_MAP and re-run; "
          "no connection was attempted.", file=sys.stderr)
    sys.exit(2)


def _resolve_host(host, port):
    if host == "127.0.0.1" and port in _HOST_MAP:
        return _HOST_MAP[port]
    return host


def _canonical_host_header(host, port):
    """The Host header for a request to (host, port), or None to let
    http.client use its default. Mapped connections get the canonical
    loopback authority '127.0.0.1:<port>' — the backend and Keycloak
    only ever accept that authority, never the internal service DNS."""
    if host == "127.0.0.1" and port in _HOST_MAP:
        return f"127.0.0.1:{port}"
    return None


# Routes already logged (one log line per mapped route, not per request).
_LOGGED_ROUTES: set[tuple[str, int]] = set()

# Synthetic lab credentials (documented in README.md; NOT real accounts).
USERS = {
    "student": ("student_01", "LabPass-Student-01!"),
    "officer": ("officer_01", "LabPass-Officer-01!"),
}

RESULTS: list[dict[str, object]] = []


class Jar:
    def __init__(self):
        self.cookies: dict[str, str] = {}

    def store(self, headers):
        for value in headers.get_all("Set-Cookie", []):
            name_value = value.split(";", 1)[0]
            if "=" in name_value:
                name, val = name_value.split("=", 1)
                self.cookies[name.strip()] = val.strip()

    def header(self):
        return "; ".join(f"{k}={v}" for k, v in self.cookies.items())


def request(jar, method, host, port, path, body=None, headers=None):
    # P0-02: on a mapped connection the TCP route changes but the HTTP
    # authority must not: set the canonical Host header explicitly,
    # else http.client derives 'Host: <mapped-host>:<port>' from the
    # connection host and the backend rejects it (403 HOST_NOT_ALLOWED).
    route_host = _resolve_host(host, port)
    h = dict(headers or {})
    if "host" not in {k.lower() for k in h}:
        canonical = _canonical_host_header(host, port)
        if canonical is not None:
            h["Host"] = canonical
            route_key = (route_host, port)
            if route_key not in _LOGGED_ROUTES:
                _LOGGED_ROUTES.add(route_key)
                # HOST/PORT metadata only — never tokens, cookies,
                # codes, or credentials. Route (TCP) vs authority (Host)
                # are logged as separate fields on purpose.
                print(f"[hostmap] route 127.0.0.1:{port} -> {route_host}:{port}; "
                      f"Host header: {canonical}", file=sys.stderr)
    conn = http.client.HTTPConnection(route_host, port, timeout=10)
    if jar.cookies:
        h["Cookie"] = jar.header()
    if body is not None:
        # Default is form-encoded (all existing callers); a caller may
        # override with application/json via headers (reset / runs).
        h.setdefault("Content-Type", "application/x-www-form-urlencoded")
        h["Content-Length"] = str(len(body))
    conn.request(method, path, body=body, headers=h)
    resp = conn.getresponse()
    data = resp.read().decode("utf-8", "replace")
    jar.store(resp.headers)
    conn.close()
    lower = {}
    for k, v in resp.headers.items():
        lower.setdefault(k.lower(), v)
    return resp.status, lower, data


def check(name, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")
    RESULTS.append({"name": name, "pass": bool(cond), "detail": str(detail)[:200]})
    if not cond:
        raise AssertionError(name)


def code_provenance():
    """Prove the serving backend is v6-or-later code before any login is attempted.

    Lesson from the v4 record: a copied venv's editable install can point
    at an older tree, so a live gate can pass against the wrong backend
    version without noticing (the v3/v4 backend differences are invisible
    to most gate checks). The v6-era /lab/counts fields below exist in no
    earlier release, so their presence pins the serving code to v6+.
    """
    status, _, data = probe(Jar(), "/api/v1/lab/counts")
    check("backend counts readable", status == 200, f"got {status}")
    counts = json.loads(data)
    v6_fields = ("live_login_transactions", "live_login_events", "live_login_successful_transactions", "live_login_event_limit")
    missing = [f for f in v6_fields if f not in counts]
    check(
        "backend is v6-or-later code (counts carry v6-era fields)",
        not missing,
        f"missing v6-era fields: {missing} (serving backend is older than v6?)" if missing else "live_login_transactions/live_login_events/live_login_successful_transactions/live_login_event_limit present",
    )


def discovery():
    jar = Jar()
    status, _, data = request(
        jar, "GET", BASE_HOST, KC_PORT,
        f"/realms/{REALM}/.well-known/openid-configuration",
    )
    check("discovery 200", status == 200, f"got {status}")
    doc = json.loads(data)
    check(
        "discovery issuer is canonical",
        doc.get("issuer") == f"http://127.0.0.1:{KC_PORT}/realms/{REALM}",
        doc.get("issuer"),
    )
    return doc


def start_login(jar):
    status, headers, _ = request(jar, "GET", BASE_HOST, BASE_PORT, "/auth/login")
    check("login redirects to Keycloak", status == 302, f"got {status}")
    loc = headers.get("location", "")
    check(
        "redirect target is canonical auth endpoint",
        loc.startswith(
            f"http://127.0.0.1:{KC_PORT}/realms/{REALM}/protocol/openid-connect/auth?"
        ),
        loc[:80],
    )
    check(
        "txn binding cookie set (per-transaction)",
        any(name.startswith("identityforge_txn_") for name in jar.cookies),
        sorted(jar.cookies),
    )
    return loc


def submit_credentials(jar, loc, username, password):
    """Follow the Keycloak login form; return the callback Location
    (with code) WITHOUT following it to the backend.

    SSO skip (measured 2026-11-11): when the jar already holds an
    authenticated Keycloak session — the second login in one browser
    during parallel_flow — Keycloak answers the auth URL with a 302
    straight to the callback with a code instead of the login page.
    That is correct IdP behaviour, not a failure: the Location IS the
    callback, so return it directly. A 302 anywhere else still fails
    the check below."""
    u = urllib.parse.urlparse(loc)
    status, headers, body = request(
        jar, "GET", u.hostname, u.port or 80, u.path + "?" + u.query
    )
    if status == 302:
        target = headers.get("location", "")
        check(
            "Keycloak SSO skip redirects to callback with code",
            "/auth/callback?" in target and "code=" in target,
            f"got {status} {target[:80]}",
        )
        return target
    check("Keycloak login page loads", status == 200, f"got {status}")
    m = re.search(r'action="([^"]+login-actions/authenticate[^"]*)"', body)
    check("login form action found", bool(m))
    action = m.group(1).replace("&amp;", "&")
    au = urllib.parse.urlparse(action)
    form = urllib.parse.urlencode(
        {"username": username, "password": password, "credentialId": ""}
    )
    status, headers, _ = request(
        jar, "POST", au.hostname, au.port or 80, au.path + "?" + au.query, body=form
    )
    check(
        "Keycloak accepts credentials, redirects to callback",
        status == 302
        and "/auth/callback?" in headers.get("location", "")
        and "code=" in headers.get("location", ""),
        f"got {status}",
    )
    return headers["location"]


def complete_callback(jar, callback_location):
    cb = urllib.parse.urlparse(callback_location)
    status, headers, _ = request(
        jar, "GET", cb.hostname, cb.port or 80, cb.path + "?" + cb.query
    )
    check(
        "callback completes, redirects to portal",
        status == 302 and "/portal?login=success" in headers.get("location", ""),
        f"got {status} {headers.get('location', '')}",
    )
    check("session cookie set", "identityforge_session" in jar.cookies)


def probe(jar, path, method="GET", headers=None, body=None):
    return request(jar, method, BASE_HOST, BASE_PORT, path, body=body, headers=headers)


def login_flow(who):
    username, password = USERS[who]
    jar = Jar()
    loc = start_login(jar)
    cb = submit_credentials(jar, loc, username, password)
    complete_callback(jar, cb)
    status, _, data = probe(jar, "/api/v1/portal/me")
    check("portal/me 200", status == 200, f"got {status}")
    me = json.loads(data)
    check("me username matches", me.get("username") == username)
    check("me roles sane", isinstance(me.get("roles"), list) and "member" in me["roles"])
    status, _, _ = probe(jar, "/api/v1/portal/member")
    check("member resource 200", status == 200, f"got {status}")
    status, _, _ = probe(jar, "/api/v1/portal/officer")
    if who == "student":
        check("officer resource 403 for student", status == 403, f"got {status}")
    else:
        check("officer resource 200 for officer", status == 200, f"got {status}")
        check("officer role present", "officer" in me.get("roles", []))
    status, _, data = probe(jar, "/api/v1/csrf-token")
    check("csrf token fetch 200", status == 200, f"got {status}")
    token = json.loads(data).get("csrf_token")
    check("csrf token present", bool(token))
    status, _, data = probe(
        jar, "/auth/logout", method="POST",
        headers={"x-csrf-token": token}, body=urllib.parse.urlencode({}),
    )
    check("logout 200", status == 200, f"got {status}: {data[:120]}")
    status, _, _ = probe(jar, "/api/v1/portal/me")
    check("stale session denied after logout (401)", status == 401, f"got {status}")
    print(f"  live login flow passed for {who} ({username})")


def binding_flow():
    username, password = USERS["student"]
    jar_a = Jar()
    loc = start_login(jar_a)
    cb = submit_credentials(jar_a, loc, username, password)
    # Browser B (fresh jar, no binding cookie) tries the same callback.
    jar_b = Jar()
    u = urllib.parse.urlparse(cb)
    status, headers, _ = request(
        jar_b, "GET", u.hostname, u.port or 80, u.path + "?" + u.query
    )
    check(
        "cross-browser callback rejected",
        status == 302 and "error=STATE_BINDING_MISMATCH" in headers.get("location", ""),
        f"got {status} {headers.get('location', '')}",
    )
    status, _, _ = probe(jar_b, "/api/v1/portal/me")
    check("cross-browser attempt created no session (401)", status == 401, f"got {status}")
    # The legitimate browser can still complete (transaction not consumed).
    complete_callback(jar_a, cb)
    status, _, _ = probe(jar_a, "/api/v1/portal/me")
    check("legitimate browser completes after rejected attempt", status == 200, f"got {status}")
    # Replay of the consumed callback is rejected.
    status, headers, _ = request(
        jar_a, "GET", u.hostname, u.port or 80, u.path + "?" + u.query
    )
    check(
        "callback replay rejected",
        status == 302 and "error=STATE_REUSED" in headers.get("location", ""),
        f"got {status} {headers.get('location', '')}",
    )


def parallel_flow():
    """P1-06: two logins started in the SAME browser (one jar) both
    complete. Each transaction has its own binding cookie
    (identityforge_txn_<state>), so the second login must not
    invalidate the first. The browser ends with the LATEST session:
    completing the second callback rotates (revokes) the first
    session — one browser, one active session, latest login wins."""
    username, password = USERS["student"]
    jar = Jar()
    loc_a = start_login(jar)
    loc_b = start_login(jar)
    txn_cookies = [n for n in jar.cookies if n.startswith("identityforge_txn_")]
    check("two parallel logins hold two distinct binding cookies",
          len(txn_cookies) == 2, str(txn_cookies))
    cb_a = submit_credentials(jar, loc_a, username, password)
    cb_b = submit_credentials(jar, loc_b, username, password)
    # Complete B first, then A (reverse order).
    complete_callback(jar, cb_b)
    first_session = jar.cookies.get("identityforge_session")
    check("first completed login minted a session", bool(first_session))
    complete_callback(jar, cb_a)
    second_session = jar.cookies.get("identityforge_session")
    check("second completed login rotated the session",
          bool(second_session) and second_session != first_session)
    status, _, _ = probe(jar, "/api/v1/portal/me")
    check("latest session is valid (200)", status == 200, f"got {status}")
    # The earlier session is revoked by the rotation.
    stale = Jar()
    stale.cookies["identityforge_session"] = first_session
    status, _, _ = probe(stale, "/api/v1/portal/me")
    check("earlier session revoked after rotation (401)", status == 401, f"got {status}")


def negatives_flow():
    """K2 wrong PKCE verifier + K3 unregistered redirect at REAL Keycloak.

    Keycloak behaviour measured 2026-11-11 (probe /tmp/k2-probe.py):
    a failed PKCE exchange BURNS the authorization code — the first
    wrong-verifier exchange returns 400 invalid_grant "PKCE verification
    failed", and any later exchange of the same code returns 400
    invalid_grant "Code not valid". So K2 must use its OWN disposable
    login transaction: attacking the legitimate transaction's code would
    (correctly) break the legitimate login too. The legitimate flow is
    then proven separately with a fresh, untouched code.
    """
    doc = discovery()
    token_url = doc["token_endpoint"]
    username, password = USERS["student"]
    # K2: disposable transaction; the attacker's code, not the user's.
    jar = Jar()
    loc = start_login(jar)
    cb = submit_credentials(jar, loc, username, password)
    code = urllib.parse.parse_qs(urllib.parse.urlparse(cb).query)["code"][0]
    tu = urllib.parse.urlparse(token_url)

    def exchange(verifier):
        body = urllib.parse.urlencode(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "client_id": CLIENT_ID,
                "code_verifier": verifier,
            }
        )
        return request(Jar(), "POST", tu.hostname, tu.port or 80, tu.path, body=body)

    status, _, data = exchange("deliberately-wrong-verifier")
    check("K2 wrong PKCE verifier rejected at real token endpoint",
          status == 400, f"got {status}: {data[:160]}")
    check("K2 error is invalid_grant (PKCE verification failed)",
          "invalid_grant" in data and "PKCE verification failed" in data,
          data[:120])
    status, _, data = exchange("deliberately-wrong-verifier-2")
    check("K2 failed exchange burned the code (second attempt: Code not valid)",
          status == 400 and "Code not valid" in data,
          f"got {status}: {data[:160]}")
    # The legitimate callback for the burned code is rejected, no session.
    u = urllib.parse.urlparse(cb)
    status, headers, _ = request(
        jar, "GET", u.hostname, u.port or 80, u.path + "?" + u.query
    )
    check("legitimate callback for burned code rejected (PROVIDER_ERROR)",
          status == 302 and "error=PROVIDER_ERROR" in headers.get("location", ""),
          f"got {status} {headers.get('location', '')}")
    status, _, _ = probe(jar, "/api/v1/portal/me")
    check("burned-code callback created no session (401)", status == 401,
          f"got {status}")
    # K3: unregistered redirect URI at the REAL authorization endpoint.
    auth_url = doc["authorization_endpoint"]
    au = urllib.parse.urlparse(auth_url)
    evil = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": CLIENT_ID,
            "redirect_uri": "http://127.0.0.1:8000/auth/callback/evil",
            "scope": "openid",
            "state": "k3-probe",
            "nonce": "k3-nonce",
            "code_challenge": "k3challenge",
            "code_challenge_method": "S256",
        }
    )
    status, _, body = request(
        Jar(), "GET", au.hostname, au.port or 80, au.path + "?" + evil
    )
    check(
        "K3 unregistered redirect rejected before code issued",
        "code=" not in body and "redirect_uri" in body.lower(),
        f"got {status}",
    )
    # The lab still works after the negatives: fresh untouched login.
    login_flow("student")


def _csrf_token(jar):
    status, _, data = probe(jar, "/api/v1/csrf-token")
    check("csrf token fetch 200", status == 200, f"got {status}")
    token = json.loads(data).get("csrf_token")
    check("csrf token present", bool(token))
    return token


def _lab_counts():
    status, _, data = probe(Jar(), "/api/v1/lab/counts")
    check("lab counts readable", status == 200, f"got {status}")
    return json.loads(data)


def _login_no_logout(who):
    """Log in and return (jar, csrf_token) with the session alive."""
    username, password = USERS[who]
    jar = Jar()
    loc = start_login(jar)
    cb = submit_credentials(jar, loc, username, password)
    complete_callback(jar, cb)
    status, _, data = probe(jar, "/api/v1/portal/me")
    check(f"{who} portal/me 200 after login", status == 200, f"got {status}")
    me = json.loads(data)
    check(f"{who} username matches", me.get("username") == username)
    return jar, _csrf_token(jar)


def _post_json(jar, path, csrf_token, payload):
    return request(
        jar, "POST", BASE_HOST, BASE_PORT, path,
        body=json.dumps(payload),
        headers={"x-csrf-token": csrf_token, "Content-Type": "application/json"},
    )


def _refuse_reset(reason):
    """Fail closed BEFORE any destructive call: print the specific safety
    message and exit nonzero (2). Called before any login, run creation,
    or POST — and before ANY network contact at all when the flag itself
    is missing or malformed. This is the IF-V7.1-01 guard: the old
    unguarded `reset` ran on argv[1] == 'reset' with no precondition
    beyond a docstring warning."""
    print(f"live-gate: REFUSING destructive reset — {reason}", file=sys.stderr)
    print("live-gate: reset runs ONLY against a disposable stack whose "
          "marker the responding backend itself reports via "
          "GET /api/v1/lab/status (IF-V7.1-01). Pass the runner-generated "
          "UUID with --disposable-project-id <uuid>; never run reset "
          "against a lab whose evidence you want to keep.", file=sys.stderr)
    sys.exit(2)


def _parse_reset_args(argv):
    """Parse `reset` arguments: --disposable-project-id <uuid> is
    REQUIRED, with no default and no fallback to an environment variable
    alone. Returns the canonical (lowercase) UUID string. Any missing,
    malformed, nil, repeated, or unknown argument refuses the reset
    via _refuse_reset() (exit 2) before any connection is attempted."""
    expected = None
    i = 0
    while i < len(argv):
        if argv[i] != "--disposable-project-id":
            _refuse_reset(f"unknown reset argument {argv[i]!r}: the only "
                          "accepted argument is "
                          "--disposable-project-id <uuid>.")
        if expected is not None:
            _refuse_reset("--disposable-project-id given more than once.")
        if i + 1 >= len(argv):
            _refuse_reset("--disposable-project-id requires a UUID value.")
        raw = argv[i + 1]
        try:
            parsed = uuid.UUID(raw)
        except (ValueError, AttributeError, TypeError):
            _refuse_reset(f"--disposable-project-id value {raw!r} is not "
                          "a valid UUID.")
        if parsed.int == 0:
            _refuse_reset("the nil UUID 00000000-0000-0000-0000-000000000000 "
                          "is not a disposable-project marker.")
        expected = str(parsed)
        i += 2
    if expected is None:
        _refuse_reset("no --disposable-project-id given: the destructive "
                      "reset requires --disposable-project-id <uuid> "
                      "matching the marker the responding backend reports.")
    return expected


def verify_disposable_project(expected_id):
    """Verify the runner-supplied marker against the value the responding
    backend itself reports (IF-V7.1-01). GETs /api/v1/lab/status — a
    single read-only request — and fails closed (AssertionError, caught
    by main() as a gate failure) on ANY mismatch BEFORE the first login,
    run creation, or POST: absent marker (persistent/default lab),
    stale or forged marker, malformed or nil reported value, or an
    unreadable status. The check compares the expected ID against the
    backend's own report; a caller-controlled environment variable alone
    is never accepted as protection. On match, records a PASS check."""
    status, _, data = probe(Jar(), "/api/v1/lab/status")
    check("backend status readable", status == 200, f"got {status}")
    try:
        payload = json.loads(data)
    except ValueError:
        check("REFUSING destructive reset — backend status is not valid JSON",
              False, data[:120])
    reported = payload.get("disposable_project_id")
    if not isinstance(reported, str) or not reported:
        check("REFUSING destructive reset — backend reports no "
              "disposable_project_id (persistent/default lab?)",
              False,
              f"expected marker {expected_id}; the responding backend "
              "carries no disposable-project marker, so this is not a "
              "disposable stack — refusing to reset it")
    try:
        parsed = uuid.UUID(reported)
    except (ValueError, AttributeError, TypeError):
        check("REFUSING destructive reset — backend reports a malformed "
              "disposable_project_id",
              False, f"reported {reported!r}, expected {expected_id}")
    if parsed.int == 0:
        check("REFUSING destructive reset — backend reports the nil UUID "
              "as its disposable_project_id (default project?)",
              False, f"expected {expected_id}")
    if str(parsed) != expected_id:
        check("REFUSING destructive reset — disposable-project marker mismatch",
              False,
              f"expected {expected_id}, backend reported {reported}; "
              "the reset target is not the disposable project this run "
              "was authorised for")
    check("disposable-project marker matches the responding backend",
          True, f"marker {expected_id}")


def reset_flow():
    """P1-13: officer-only lab reset against the REAL stack.

    Creates synthetic evidence (a student login + one offline run),
    proves unauthenticated and student resets CANNOT delete it, proves
    the officer reset CAN (with CSRF + explicit confirmation), proves
    the stale officer session is 401 afterwards, and proves Keycloak /
    the realm still works after the reset — the reset clears local app
    state only, not the realm or the SSO session.

    DESTRUCTIVE BY DESIGN: a successful reset wipes runs, sessions,
    live_logins and transactions in the backend it runs against. Run
    it ONLY against a disposable stack (the -Full cold-start namespace)
    or a host stack whose evidence is synthetic test data. NEVER run
    it against a lab whose evidence you want to keep. It is a separate
    sub-gate, not part of `all`, for exactly this reason.

    Precondition (IF-V7.1-01, v7.2): main() requires
    --disposable-project-id <uuid> and verifies it against the
    responding backend's own /api/v1/lab/status marker BEFORE this flow
    runs — before any login, run creation, or POST. Standalone use is
    DEVELOPER-ONLY behind that same precondition; the flag is never
    documented in reviewer or beginner guides. This function itself
    performs no reset until that check has passed, and the API still
    enforces officer role + CSRF + confirm=RESET_LAB (unchanged)."""
    before = _lab_counts()
    # 1. Synthetic evidence: a student login + one offline run (I1).
    student_jar, student_csrf = _login_no_logout("student")
    status, _, data = _post_json(
        student_jar, "/api/v1/runs", student_csrf, {"scenario_id": "I1"})
    check("synthetic run created (I1)", status == 200, f"got {status}: {data[:120]}")
    run_id = json.loads(data).get("run_id")
    check("synthetic run has a run_id", bool(run_id))
    status, _, _ = probe(Jar(), f"/api/v1/runs/{run_id}")
    check("synthetic run retrievable before reset", status == 200, f"got {status}")
    mid = _lab_counts()
    # v5 retention (IF-V4-11) caps runs at runs_limit with FIFO pruning,
    # so when the store is already at the cap, adding one run keeps the
    # total at the cap instead of incrementing it. The retrievability
    # check above proves the new run is stored; the count check only
    # proves the total moved as the cap allows.
    _cap = before.get("runs_limit") or (before.get("runs", 0) + 1)
    check("synthetic run counted before reset",
          mid.get("runs", 0) == min(before.get("runs", 0) + 1, _cap),
          f"before={before} mid={mid}")
    _login_cap = before.get("live_login_event_limit") or 1000
    _at_event_cap = before.get("live_login_events", 0) >= _login_cap
    # v6 (IF-V5-02): one login is ONE transaction but writes several stage
    # EVENTS, so the deprecated `live_logins` event alias grows by >1 per
    # login and must never be asserted +1. Assert the transaction count
    # instead: exactly +1 below the event cap. At the cap, whole-transaction
    # eviction can hold the total flat, so only assert a transaction exists
    # (retention accounting itself is covered by WS1 unit tests).
    check("synthetic login counted before reset",
          (mid.get("live_login_transactions", 0) == before.get("live_login_transactions", 0) + 1
           and mid.get("live_login_events", 0) >= before.get("live_login_events", 0) + 1)
          if not _at_event_cap else
          (mid.get("live_login_transactions", 0) >= 1
           and mid.get("live_login_events", 0) >= 1),
          f"before={before} mid={mid}")

    # 2. Unauthenticated reset cannot delete it (no session, no CSRF).
    status, _, data = _post_json(Jar(), "/api/v1/lab/reset", "", {"confirm": "RESET_LAB"})
    check("unauthenticated reset denied (403)", status == 403, f"got {status}: {data[:120]}")
    check("evidence intact after unauthenticated reset",
          _lab_counts().get("runs", -1) == mid.get("runs"), f"mid={mid}")

    # 3. Student reset cannot delete it (session + CSRF, wrong role).
    status, _, data = _post_json(
        student_jar, "/api/v1/lab/reset", student_csrf, {"confirm": "RESET_LAB"})
    check("student reset denied (403 policy_denied)", status == 403 and "policy_denied" in data,
          f"got {status}: {data[:120]}")
    check("evidence intact after student reset",
          _lab_counts().get("runs", -1) == mid.get("runs"), f"mid={mid}")
    status, _, _ = probe(student_jar, "/api/v1/portal/me")
    check("student session still valid after denied reset", status == 200, f"got {status}")

    # 4. Officer reset with CSRF + explicit confirmation succeeds.
    officer_jar, officer_csrf = _login_no_logout("officer")
    status, _, data = _post_json(
        officer_jar, "/api/v1/lab/reset", officer_csrf, {"confirm": "RESET_LAB"})
    check("officer reset succeeds (200)", status == 200, f"got {status}: {data[:160]}")
    resp = json.loads(data)
    check("reset response names the officer operator",
          resp.get("operator") == "officer_01", str(resp)[:120])
    check("reset response reports operator session revoked",
          resp.get("operator_session_revoked") is True, str(resp)[:120])
    check("reset response reports the cleared counts",
          resp.get("cleared", {}).get("runs", -1) == mid.get("runs"),
          f"cleared={resp.get('cleared')} mid={mid}")
    after = _lab_counts()
    # v5 counts carry extra diagnostic fields (events, *_limit,
    # sessions_total_issued) — assert the four cleared counters are 0,
    # not exact dict equality with the v4 shape. v6 adds the explicit
    # transaction/event counters, which must also be 0 after reset.
    check("evidence fully cleared after officer reset",
          all(after.get(k, -1) == 0 for k in ("runs", "sessions", "live_logins", "transactions",
                                              "live_login_events", "live_login_transactions")),
          f"after={after}")
    status, _, _ = probe(Jar(), f"/api/v1/runs/{run_id}")
    check("synthetic run gone after reset (404)", status == 404, f"got {status}")

    # 5. Stale sessions are 401 afterwards (officer AND student).
    status, _, _ = probe(officer_jar, "/api/v1/portal/me")
    check("stale officer session denied after reset (401)", status == 401, f"got {status}")
    status, _, _ = probe(student_jar, "/api/v1/portal/me")
    check("stale student session denied after reset (401)", status == 401, f"got {status}")

    # 6. Keycloak / the realm still work: fresh login succeeds, and the
    # lab records the new login (reset cleared app state only).
    fresh_jar, _ = _login_no_logout("student")
    post = _lab_counts()
    # live_logins counts recorded EVENTS (one login writes several
    # stage events — measured: 6 for a single student login), not
    # logins, so assert >= 1 from the cleared 0, not exactly 1.
    # The v6 transaction counter must show exactly the one new login.
    check("lab records the post-reset login (live_logins >= 1)",
          post.get("live_logins", 0) >= 1, f"post={post}")
    check("lab records the post-reset login as one transaction",
          post.get("live_login_transactions", 0) == 1, f"post={post}")
    status, _, _ = probe(fresh_jar, "/api/v1/portal/member")
    check("member resource works after reset", status == 200, f"got {status}")
    print("  live reset flow passed (officer-only, evidence cleared, realm intact)")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    expected_marker = None
    if mode == "reset":
        # IF-V7.1-01: parse the REQUIRED flag (exits 2 before any network
        # contact when it is missing or malformed) and verify it against
        # the responding backend's own status marker (one read-only GET)
        # BEFORE code_provenance, discovery, any login, or any POST.
        expected_marker = _parse_reset_args(sys.argv[2:])
    try:
        if mode == "reset":
            verify_disposable_project(expected_marker)
        code_provenance()
        if mode in ("login", "all"):
            discovery()
            login_flow("student")
            login_flow("officer")
        if mode in ("binding", "all"):
            binding_flow()
        if mode in ("parallel", "all"):
            parallel_flow()
        if mode in ("negatives", "all"):
            negatives_flow()
        if mode == "reset":
            discovery()
            reset_flow()
    except AssertionError as exc:
        print(f"\nLIVE GATE FAILED at: {exc}")
        print(json.dumps({"passed": False, "results": RESULTS}, indent=2))
        sys.exit(1)
    print("\nLIVE GATE PASSED")
    print(json.dumps({"passed": True, "results": RESULTS}, indent=2))


if __name__ == "__main__":
    main()
