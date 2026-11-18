#!/usr/bin/env bash
# Regression suite for the Compose healthcheck script (Trustline v7.2).
#
# Covers IF-V7.1-02 (log dir before first redirection), IF-V7.1-03
# (HTTP framing parsed by a real client), and IF-V7.1-04 (disposable
# project + fixed-port preflight + read-only mode), each with a
# FAILING-FIRST demonstration against the v7.1 baseline where the
# parent reproduced the bug, then the fixed behaviour on the current
# tree. Everything runs with a stub `docker` (no daemon, no images,
# no network beyond loopback) plus a local stub discovery server,
# so the suite runs in CI without Docker. The stub `docker` records
# every invocation, which is how the suite proves which Compose
# commands actually ran (v7.1's stub log proved `compose config`
# never started) and that cleanup touches only the disposable
# project.
#
# Usage: bash scripts/test-compose-healthcheck-regressions.sh
#   [--baseline DIR]   v7.1 tree for the failing-first checks
#                      (default: the sibling ../identityforge-v7.1
#                      when it exists; the failing-first checks are
#                      NOT RUN — never PASS — when it is absent)
# python3 WITH PyYAML + bash + rsync + curl; no Docker, no venv, no
# network. (v7.2's header said "stdlib-only python3" — that was
# wrong: the nested checker scripts/compose-config-check.py imports
# third-party PyYAML. IF-V7.2-02, v7.3: PyYAML is an explicit
# prerequisite, preflighted in the SAME interpreter the nested runs
# use; a missing prerequisite exits 2 ENVIRONMENT NOT READY, never a
# traceback mislabelled as a Compose defect. The harness preserves
# the caller's PATH (ORIGINAL_PATH) and augments it only in a
# controlled way — stub docker first, caller's python3/PyYAML/bash/
# curl/Node intact — and hides docker for the no-Docker cases with a
# filtered PATH that removes ONLY the docker CLIs.)
# Exits 0 only if every case behaves as specified; exits 2 when a
# prerequisite (python3 with PyYAML, bash, curl, rsync) is missing.
#
# Cases (each labelled in output):
#   02-a  failing-first (v7.1): fresh copy, no test-results/, stub
#         docker -> "No such file or directory" + FAIL config, and
#         the stub log shows ONLY `compose version` (config never ran)
#   02-b  fixed: same shape on the current tree -> exit 0, log dir
#         created, `compose config` actually ran
#   02-c  config-failure injection: stub `compose config` exits 1 ->
#         script exits 1 naming the REAL config failure (exit code +
#         reason), never a shell redirection error
#   02-d  same as 02-b from a checkout path containing spaces
#   02-e  PyYAML preflight (IF-V7.2-02): a yaml-less interpreter is
#         ENVIRONMENT NOT READY (exit 2, actionable message, no
#         traceback); the caller's interpreter with PyYAML passes
#   02-f  venv python + Node managed outside /usr/bin survive the
#         harness's controlled PATH augmentation (stub docker still
#         wins; the venv python actually runs the checker; nothing
#         leaks between cases)
#   03-a  failing-first (v7.1): the v7.1 raw-bytes json.load snippet
#         on a representative valid HTTP/1.1 200 response ->
#         JSONDecodeError (nonzero)
#   03-b  HTTP matrix via scripts/discovery-check.py --raw: valid
#         Content-Length + valid chunked -> OK, exact issuer accepted;
#         401/404/503, wrong issuer, missing issuer, malformed JSON,
#         HTML, truncated response, chunked malformed, chunked
#         truncated, redirect -> FAIL each with a precise reason
#   03-c  --url mode against a local stub discovery server: good ->
#         OK; redirect -> FAIL (never followed); HTML -> FAIL
#   04-a  controlled test ports occupied (v7.3.1 Finding C): ONE of
#         the test ports is held by OUR OWN token-proven listener
#         (started on a reserved test port via the
#         IDENTITYFORGE_HCPROBE_TEST_PORTS override — never the
#         reviewer's real 8080/8000/5173) -> FAIL FAST before any
#         `compose up`, with the stop/test/restart instructions;
#         the occupant is proven alive afterwards by exact PID +
#         token greeting, never killed, and cleaned up with no
#         leak. If a candidate port is already held, its owner is
#         identified and a safe alternate is selected — an external
#         listener is never silently counted as the test's own.
#         Deterministic whether the live stack is up or down: the
#         old form started its own `http.server` on the REAL 8080,
#         which cannot bind while Keycloak holds it (parent Pass B:
#         33/1/0 with every asserted condition satisfied on the
#         logged values; WS2 also saw 33/1/0 with NO lab up).
#   04-b  ports free -> unique disposable project ID on each run,
#         boot + check, cleanup ONLY that project (down -v names it;
#         no bare `down`, no other project) even on failure
#   04-c  SIGTERM safety, synchronised (IF-V7.2-03): (A) TERM before any
#         project exists -> nonzero exit, no up/down, no project ID;
#         (B) TERM during the health wait -> exactly one `down -v`,
#         scoped to the run's own disposable project only. Both wait
#         on an observed stub-log phase (bounded); no fixed sleep
#         decides the outcome.
#   04-d  --against-running-project: read-only inspection, exit 0,
#         stub log shows NO `up` and NO `down` at all
#   04-e  no Docker at all, --with-docker explicitly selected -> the
#         script must exit NONZERO with the Docker parts NOT RUN
#         (IF-V7.2-01 exit contract; never a phantom PASS, never a
#         silent 0 when an explicitly requested probe could not run)
#   04-f  no Docker at all, default mode (no flag) -> static PASS,
#         Docker parts NOT RUN, exit 0 (the static regression is the
#         gate that runs everywhere)
set -uo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
BASELINE=""
for arg in "$@"; do
  case "$arg" in
    --baseline) shift; BASELINE="$1" ;;
    --baseline=*) BASELINE="${arg#--baseline=}" ;;
    --help|-h)
      echo "Usage: $0 [--baseline DIR]  (v7.1 tree for failing-first checks)"
      exit 0 ;;
    *) echo "test-compose-healthcheck-regressions: unknown argument: $arg" >&2; exit 2 ;;
  esac
done
if [ -z "$BASELINE" ] && [ -d "$ROOT/../identityforge-v7.1" ]; then
  BASELINE="$ROOT/../identityforge-v7.1"
fi

# IF-V7.2-02: preserve the caller's PATH. The v7.2 harness replaced
# PATH with "$STUBBIN:/usr/bin:/bin" (and "/usr/bin:/bin" for the
# no-Docker case), which silently switched python3 to the system
# /usr/bin/python3 — where PyYAML may NOT be installed — even when
# the caller's own python3 (a venv, /opt/pyvenv, an NVM-adjacent
# install) HAS it. The nested checker requires PyYAML, so the
# switch turned a present prerequisite into a ModuleNotFoundError
# traceback mislabelled as a Compose/healthcheck defect. Every
# nested run below uses PATH="$STUBBIN:$ORIGINAL_PATH" (stub docker
# first, caller's toolchain intact) or a filtered copy of it that
# hides ONLY the docker CLIs — never a bare /usr/bin:/bin.
ORIGINAL_PATH="$PATH"

PASS_COUNT=0
FAIL_COUNT=0
NOTRUN_COUNT=0
failures=()

ok() { PASS_COUNT=$((PASS_COUNT + 1)); echo "PASS: $1"; }
not_ok() { FAIL_COUNT=$((FAIL_COUNT + 1)); failures+=("$1 -- $2"); echo "FAIL: $1 -- $2"; }
notrun() { NOTRUN_COUNT=$((NOTRUN_COUNT + 1)); echo "NOT RUN: $1"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
STUBBIN="$TMP/stubbin"
STUB_LOG="$TMP/stub-docker.log"
mkdir -p "$STUBBIN"
CANONICAL_ISSUER="http://127.0.0.1:8080/realms/identityforge-lab"
TEST_PORTS="18080 18000 15173"
DISCOVERY_PORT=18081

# --- stub docker ------------------------------------------------------------
# Records every call as one line in $STUB_LOG, then behaves per
# STUB_CONFIG_MODE / STUB_HEALTH / STUB_EXEC_MODE / STUB_UP_MODE.
cat > "$STUBBIN/docker" <<'STUB'
#!/usr/bin/env bash
# Fake docker for the healthcheck regression suite. Logs "$*" then
# answers from canned behaviour. Never touches a daemon.
echo "docker $*" >> "$STUB_LOG"
case "$*" in
  "compose version"*)
    echo "Docker Compose version v2.99.0-stub"; exit 0 ;;
  "info"*)
    # Coordinator Pass A: the stub must be able to simulate a present
    # CLI with a dead daemon (IF-V7.2-01 gate 3) — `docker compose
    # version` still succeeds while `docker info` fails.
    if [ "${STUB_DAEMON_MODE:-ok}" = "missing" ]; then
      echo "Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?" >&2
      exit 1
    fi
    echo "Client: stub / Server: stub"; exit 0 ;;
  "compose config"*)
    if [ "${STUB_CONFIG_MODE:-ok}" = "fail" ]; then
      echo "ERROR: yaml: line 12: mapping values are not allowed in this context" >&2
      exit 1
    fi
    cat <<'YAML'
services:
  keycloak:
    healthcheck:
      test: ["CMD", "bash", "-c", "exec 3<>/dev/tcp/127.0.0.1/8080 && resp=$(cat <&3) && echo \"$resp\" | grep -qE 'HTTP/1\\.[01] 200' && echo \"$resp\" | grep -q '\"issuer\"'"]
YAML
    exit 0 ;;
  *" up --build -d"*)
    if [ "${STUB_UP_MODE:-ok}" = "fail" ]; then
      echo "ERROR: failed to build" >&2; exit 1
    fi
    echo "up ok"; exit 0 ;;
  *" down -v"*)
    echo "down ok"; exit 0 ;;
  "inspect"*)
    if [ "${STUB_HEALTH:-healthy}" = "healthy" ]; then
      printf '%s' '{"Status":"healthy","FailingStreak":0,"Log":[]}'
    else
      printf '%s' '{"Status":"starting","FailingStreak":0,"Log":[]}'
    fi
    exit 0 ;;
  *" exec -T keycloak"*)
    if [ "${STUB_EXEC_MODE:-ok}" = "fail" ]; then
      echo "exec probe failed" >&2; exit 1
    fi
    echo "exec ok"; exit 0 ;;
  *" ps -q keycloak"*) echo "fake-keycloak-id"; exit 0 ;;
  *" ps -q backend"*) echo "fake-backend-id"; exit 0 ;;
  *" ps -q frontend"*) echo "fake-frontend-id"; exit 0 ;;
  "compose ps"*)
    printf '%s\n' "NAME STATUS" "fake-keycloak-id healthy" "fake-backend-id healthy" "fake-frontend-id healthy"
    exit 0 ;;
  *)
    echo "stub: unhandled call: docker $*" >&2; exit 0 ;;
esac
STUB
chmod +x "$STUBBIN/docker"

# --- prerequisite preflight (IF-V7.2-02) ------------------------------------
# compose-config-check.py imports third-party PyYAML (it is NOT
# stdlib-only). Check it in the SAME interpreter the nested runs
# will use: python3 resolved through "$STUBBIN:$ORIGINAL_PATH".
# A missing prerequisite is ENVIRONMENT NOT READY (exit 2) with an
# actionable install hint — never a traceback, never a FAIL counted
# as a product defect, and never a PASS invented over a missing dep.
# check_prereqs [python] — python defaults to $PYTHON3.
check_prereqs() {
  local py="${1:-${PYTHON3:-}}"
  if [ -z "$py" ] || [ ! -x "$py" ]; then
    echo "ENVIRONMENT NOT READY: no python3 found on PATH ($STUBBIN:$ORIGINAL_PATH) — install Python 3.12+ and re-run; nothing was tested." >&2
    return 2
  fi
  local pyver yamlver
  pyver="$("$py" -c 'import sys; print(sys.version.split()[0])' 2>/dev/null || echo "?")"
  if ! "$py" -c 'import yaml' 2>/dev/null; then
    echo "ENVIRONMENT NOT READY: PyYAML is required by scripts/compose-config-check.py but is not installed for $py (Python $pyver)." >&2
    echo "  Install it for THAT interpreter, then re-run — this is a missing test prerequisite, not a Compose or healthcheck defect:" >&2
    echo "    $py -m pip install pyyaml     # or your system package (e.g. python3-yaml)" >&2
    echo "  (Do not re-run with a different python and claim the result: the checker runs under $py.)" >&2
    return 2
  fi
  yamlver="$("$py" -c 'import yaml; print(yaml.__version__)' 2>/dev/null || echo "?")"
  if ! "$py" -c 'import json, http.client, socket, sys' 2>/dev/null; then
    echo "ENVIRONMENT NOT READY: $py (Python $pyver) is missing stdlib modules (json/http.client/socket) the suite needs — repair that Python install and re-run." >&2
    return 2
  fi
  local tool
  for tool in bash curl rsync; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      echo "ENVIRONMENT NOT READY: required tool '$tool' not found on PATH — install it and re-run; nothing was tested." >&2
      return 2
    fi
  done
  echo "prerequisites ok: python3 $py (Python $pyver) with PyYAML $yamlver; bash/curl/rsync present"
  return 0
}

# Resolve python3 exactly as the nested runs will: stubbin first
# (it holds only `docker`, so this is the caller's python3), then
# the preserved caller PATH — never a bare /usr/bin lookup.
PYTHON3="$( ( PATH="$STUBBIN:$ORIGINAL_PATH"; command -v python3 ) 2>/dev/null || true)"
check_prereqs "$PYTHON3" || exit 2

# --- local stub discovery server (stdlib http.server) -----------------------
cat > "$TMP/discovery-server.py" <<'PY'
"""Stub discovery server for the --url regression case.

Serves the CANONICAL issuer JSON at /good (200), a 302 redirect at
/redirect, and HTML at /html. Binds loopback only; never leaves the
machine. The issuer VALUE is the canonical one even though the
server listens on a test port — discovery-check validates the
issuer field, not the URL host.
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

ISSUER = "http://127.0.0.1:8080/realms/identityforge-lab"


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, ctype, body, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/good":
            body = json.dumps({"issuer": ISSUER}).encode()
            self._send(200, "application/json", body)
        elif self.path == "/redirect":
            self._send(302, "text/plain", b"", {"Location": "http://127.0.0.1:18081/good"})
        else:
            self._send(200, "text/html", b"<html><body>not discovery</body></html>")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
PY
python3 "$TMP/discovery-server.py" "$DISCOVERY_PORT" &
DISCOVERY_PID=$!
trap 'kill $DISCOVERY_PID 2>/dev/null; rm -rf "$TMP"' EXIT
# Wait for the stub server to answer.
for _ in $(seq 1 20); do
  if curl -s -m 2 -o /dev/null "http://127.0.0.1:$DISCOVERY_PORT/good" 2>/dev/null; then break; fi
  sleep 0.5
done
DISCOVERY_URL="http://127.0.0.1:$DISCOVERY_PORT/good"

# --- 04-a occupant listener (Trustline v7.3.1, Finding C) -------------------
# A controlled loopback listener that proves its OWN identity: it
# binds one port, and answers every TCP connection with a per-run
# token line, then closes. The token is what makes ownership
# precise — a connect probe that merely "answers" cannot tell OUR
# listener from the real Keycloak or any other process, which is
# exactly the ambiguity the old 04-a raced on. SO_REUSEADDR is set
# so a re-bind after OUR OWN cleanup is not blocked by TIME_WAIT
# sockets from the previous run's accepted connections; bind still
# fails while ANY listener holds the port (that is the signal
# start_occupant uses to detect an external occupant). Exits
# nonzero immediately when the bind fails, so a dead-on-arrival
# occupant is observable instead of a stale PID.
cat > "$TMP/occupant-server.py" <<'PY'
"""04-a occupant listener: bind one loopback port, greet with a token.

Usage: python3 occupant-server.py <port> <token>
Answers each TCP connection with "<token>\n" and closes. Binds
127.0.0.1 only; never leaves the machine. Exits nonzero at once
when the port is already held (bind failure is the signal, not a
silent background death).
"""
import socket
import sys
import threading

port = int(sys.argv[1])
token = sys.argv[2].encode() + b"\n"
srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", port))
srv.listen(8)
print("occupant listening on 127.0.0.1:%d" % port, flush=True)


def serve(conn):
    try:
        conn.sendall(token)
    except OSError:
        pass
    finally:
        conn.close()


while True:
    conn, _ = srv.accept()
    threading.Thread(target=serve, args=(conn,), daemon=True).start()
PY

# --- tree copies ------------------------------------------------------------
copy_tree() { # copy_tree <src> <dest>
  mkdir -p "$(dirname "$2")"
  rsync -a --exclude=.venv --exclude=node_modules --exclude=frontend/dist \
    --exclude=test-results --exclude=.git "$1/" "$2/"
}

# --- raw HTTP fixtures for the 03-b matrix ----------------------------------
mkdir -p "$TMP/raw"
python3 - "$TMP/raw" <<'PY'
import json, sys
out = sys.argv[1]
ISS = "http://127.0.0.1:8080/realms/identityforge-lab"
good = json.dumps({"issuer": ISS}).encode()
wrong = json.dumps({"issuer": "http://127.0.0.1:8080/realms/other"}).encode()

def resp(status, headers, body):
    head = ("HTTP/1.1 %d X\r\n" % status) + "".join(
        "%s: %s\r\n" % kv for kv in headers) + "\r\n"
    return head.encode() + body

def chunked(body):
    return ("%x\r\n" % len(body)).encode() + body + b"\r\n0\r\n\r\n"

cases = {
    "valid-cl": resp(200, [("Content-Length", str(len(good))), ("Content-Type", "application/json")], good),
    "valid-chunked": resp(200, [("Transfer-Encoding", "chunked"), ("Content-Type", "application/json")], chunked(good)),
    "s401": resp(401, [("Content-Length", "2")], b"{}"),
    "s404": resp(404, [("Content-Length", "2")], b"{}"),
    "s503": resp(503, [("Content-Length", "2")], b"{}"),
    "wrong-issuer": resp(200, [("Content-Length", str(len(wrong))), ("Content-Type", "application/json")], wrong),
    "missing-issuer": resp(200, [("Content-Length", "2")], b"{}"),
    "bad-json": resp(200, [("Content-Length", "7")], b"{oops!}"),
    "html": resp(200, [("Content-Type", "text/html"), ("Content-Length", "20")], b"<html><body>x</body>"),
    "truncated": resp(200, [("Content-Length", "200")], good[:10]),
    "chunked-badsize": resp(200, [("Transfer-Encoding", "chunked")], b"zz\r\nabc\r\n0\r\n\r\n"),
    "chunked-trunc": resp(200, [("Transfer-Encoding", "chunked")], b"a\r\nabc"),
    "redirect": resp(302, [("Location", "http://127.0.0.1:18081/good"), ("Content-Length", "0")], b""),
}
for name, data in cases.items():
    open("%s/%s.raw" % (out, name), "wb").write(data)
print("wrote %d raw fixtures" % len(cases))
PY

# run_hc <tree> <mode> [extra env assignments...] — runs the tree's
# healthcheck script with the stub docker first on PATH and the
# test-only port/discovery overrides set. Prints stdout+stderr,
# returns the script's exit code.
run_hc() {
  local tree="$1" mode="$2"; shift 2
  (cd "$tree" && env -i PATH="$STUBBIN:$ORIGINAL_PATH" HOME="$HOME" \
    STUB_LOG="$STUB_LOG" \
    STUB_CONFIG_MODE="${STUB_CONFIG_MODE:-ok}" \
    STUB_HEALTH="${STUB_HEALTH:-healthy}" \
    STUB_EXEC_MODE="${STUB_EXEC_MODE:-ok}" \
    STUB_UP_MODE="${STUB_UP_MODE:-ok}" \
    STUB_DAEMON_MODE="${STUB_DAEMON_MODE:-ok}" \
    IDENTITYFORGE_HCPROBE_TEST_PORTS="$TEST_PORTS" \
    IDENTITYFORGE_HCPROBE_DISCOVERY_URL="$DISCOVERY_URL" \
    "$@" bash scripts/test-compose-healthcheck.sh "$mode")
}

reset_stub() { : > "$STUB_LOG"; }

echo "===== IF-V7.1-02 / 03 / 04 healthcheck regressions ====="

# --- 02-a: failing-first on the v7.1 baseline -------------------------------
if [ -n "$BASELINE" ] && [ -x "$BASELINE/scripts/test-compose-healthcheck.sh" ]; then
  V71="$TMP/baseline/identityforge-v7.1"
  copy_tree "$BASELINE" "$V71"
  rm -rf "$V71/test-results"
  reset_stub
  out="$(STUB_CONFIG_MODE=ok run_hc "$V71" --with-docker 2>&1)"; rc=$?
  if [ "$rc" -ne 0 ] \
     && echo "$out" | grep -q "No such file or directory" \
     && echo "$out" | grep -q "FAIL: docker compose config failed" \
     && grep -q "compose version" "$STUB_LOG" \
     && ! grep -q "compose config" "$STUB_LOG"; then
    ok "02-a failing-first (v7.1): fresh copy, no test-results/ -> redirection error + FAIL config, stub log shows ONLY 'compose version' (config never started)"
  else
    not_ok "02-a failing-first (v7.1)" "expected rc!=0 + redirection error + config never called, got rc=$rc out=[$out] stub=[$([ -f "$STUB_LOG" ] && cat "$STUB_LOG")]"
  fi

  # --- 03-a: failing-first on the v7.1 raw-bytes parse ----------------------
  if python3 -c 'import json,sys; print(json.load(sys.stdin).get("issuer",""))' \
       < "$TMP/raw/valid-cl.raw" >/dev/null 2>&1; then
    not_ok "03-a failing-first (v7.1 json.load)" "the v7.1 raw-bytes json.load snippet unexpectedly SUCCEEDED on a valid HTTP/1.1 200 response"
  else
    ok "03-a failing-first (v7.1): raw-bytes json.load on a valid HTTP/1.1 200 response raises JSONDecodeError (rc!=0)"
  fi
else
  notrun "02-a failing-first (v7.1) — baseline tree not found (pass --baseline DIR)"
  notrun "03-a failing-first (v7.1 json.load) — baseline tree not found (pass --baseline DIR)"
fi

# --- current-tree copies ----------------------------------------------------
CUR="$TMP/normal/identityforge"
copy_tree "$ROOT" "$CUR"
SPACES="$TMP/path with spaces/identityforge"
copy_tree "$ROOT" "$SPACES"

# --- 02-b: fixed behaviour, fresh copy, no test-results/ --------------------
rm -rf "$CUR/test-results"
reset_stub
out="$(STUB_CONFIG_MODE=ok run_hc "$CUR" --with-docker 2>&1)"; rc=$?
if [ "$rc" -eq 0 ] && [ -d "$CUR/test-results" ] \
   && grep -q "compose config" "$STUB_LOG" \
   && [ -f "$CUR/test-results/compose-healthcheck-config.out" ] \
   && echo "$out" | grep -q "port preflight"; then
  ok "02-b fixed: fresh copy, no test-results/ -> exit 0, log dir created, 'compose config' actually ran (stub log), config output recorded"
else
  not_ok "02-b fixed" "expected rc=0 + log dir + config call, got rc=$rc out=[$out] stub=[$([ -f "$STUB_LOG" ] && cat "$STUB_LOG")]"
fi

# --- 02-c: authentic config failure ----------------------------------------
rm -rf "$CUR/test-results"
reset_stub
out="$(STUB_CONFIG_MODE=fail run_hc "$CUR" --with-docker 2>&1)"; rc=$?
if [ "$rc" -ne 0 ] \
   && echo "$out" | grep -q "FAIL: docker compose config failed (exit 1" \
   && ! echo "$out" | grep -q "No such file or directory" \
   && grep -q "compose config" "$STUB_LOG"; then
  ok "02-c config-failure injection: stub config exits 1 -> script exits 1 naming the real config failure, never a redirection error"
else
  not_ok "02-c config-failure injection" "expected rc=1 + real config reason, got rc=$rc out=[$out]"
fi

# --- 02-d: path with spaces -------------------------------------------------
rm -rf "$SPACES/test-results"
reset_stub
out="$(STUB_CONFIG_MODE=ok run_hc "$SPACES" --with-docker 2>&1)"; rc=$?
if [ "$rc" -eq 0 ] && grep -q "compose config" "$STUB_LOG"; then
  ok "02-d path with spaces: exit 0, 'compose config' ran from '$SPACES'"
else
  not_ok "02-d path with spaces" "expected rc=0, got rc=$rc out=[$out]"
fi

# --- 02-e: PyYAML preflight — yaml-less interpreter -------------------------
# Negative control: the SAME interpreter with site-packages disabled
# (`-S`, so `import yaml` fails while the stdlib still works) must
# be ENVIRONMENT NOT READY (rc=2) with an actionable PyYAML hint
# and NO traceback — never a FAIL counted as a Compose defect.
# Positive control: the caller's interpreter passes the same check.
FAKEBIN="$TMP/fakebin-noyaml"
mkdir -p "$FAKEBIN"
REALPY="$(readlink -f "$PYTHON3" 2>/dev/null || echo "$PYTHON3")"
printf '#!/bin/sh\n# yaml-less python for the 02-e negative control: the real\n# interpreter with site-packages disabled, so `import yaml` fails\n# while the stdlib still works. Used ONLY by this case, via an\n# explicit argument — never added to any PATH, so it cannot leak.\nexec %s -S "$@"\n' "$REALPY" > "$FAKEBIN/python3"
chmod +x "$FAKEBIN/python3"
out="$(check_prereqs "$FAKEBIN/python3" 2>&1)"; rc=$?
if [ "$rc" -eq 2 ] && echo "$out" | grep -q "ENVIRONMENT NOT READY" \
   && echo "$out" | grep -qi "pyyaml" \
   && ! echo "$out" | grep -q "Traceback" \
   && ! echo "$out" | grep -q "ModuleNotFoundError"; then
  ok "02-e preflight negative: yaml-less python3 -> ENVIRONMENT NOT READY (rc=2), actionable PyYAML message, no traceback"
else
  not_ok "02-e preflight negative" "expected rc=2 + ENVIRONMENT NOT READY + PyYAML hint, no traceback, got rc=$rc out=[$out]"
fi
out="$(check_prereqs "$PYTHON3" 2>&1)"; rc=$?
if [ "$rc" -eq 0 ] && echo "$out" | grep -qi "prerequisites ok" \
   && echo "$out" | grep -qi "PyYAML"; then
  ok "02-e preflight positive: caller python3 ($PYTHON3) has PyYAML -> rc=0"
else
  not_ok "02-e preflight positive" "expected rc=0 + prerequisites ok, got rc=$rc out=[$out]"
fi

# --- 02-f: venv python + Node outside /usr/bin survive augmentation ---------
# A venv-style bin dir (its own python3 + a Node managed outside
# /usr/bin) put FIRST on the caller's PATH must survive the
# harness's controlled augmentation: the stub docker still wins,
# but the run still uses the venv python (proven by its invocation
# marker — the wrapper logs each call, then execs the real
# interpreter, so PyYAML stays available), and the external node
# stays visible. Nothing is added to the suite's own PATH, so the
# fake executables cannot leak into later cases.
VENVBIN="$TMP/fakevenv/bin"
mkdir -p "$VENVBIN"
VENV_MARKER="$TMP/fakevenv/python3-invocations.log"
: > "$VENV_MARKER"
cat > "$VENVBIN/python3" <<PYEOF
#!/bin/sh
# Fake venv python3 for case 02-f: logs the invocation, then execs
# the real interpreter (no -S, so PyYAML stays available).
echo "venv-python3 called: \$*" >> "$VENV_MARKER"
exec "$REALPY" "\$@"
PYEOF
chmod +x "$VENVBIN/python3"
cat > "$VENVBIN/node" <<'NODEEOF'
#!/bin/sh
# Fake Node managed outside /usr/bin, for case 02-f only.
echo "v99.99.99-fake-node"
NODEEOF
chmod +x "$VENVBIN/node"
rm -rf "$CUR/test-results"
reset_stub
out="$(ORIGINAL_PATH="$VENVBIN:$ORIGINAL_PATH" STUB_CONFIG_MODE=ok run_hc "$CUR" --with-docker 2>&1)"; rc=$?
node_found="$( ( PATH="$STUBBIN:$VENVBIN:$ORIGINAL_PATH"; command -v node ) 2>/dev/null || true)"
suite_node="$(command -v node 2>/dev/null || true)"
if [ "$rc" -eq 0 ] && grep -q "compose config" "$STUB_LOG" \
   && [ -s "$VENV_MARKER" ] \
   && [ "$node_found" = "$VENVBIN/node" ] \
   && [ "$suite_node" != "$VENVBIN/node" ] \
   && [ "$(ls "$STUBBIN")" = "docker" ]; then
  ok "02-f venv python + external Node preserved: run rc=0 via venv python3 (marker: $(wc -l < "$VENV_MARKER") invocations), stub docker still won, node resolves to fakevenv/node under augmentation and NOT in the suite's own PATH, stubbin holds only docker"
else
  not_ok "02-f venv python + external Node" "expected rc=0 + venv-python marker + node=$VENVBIN/node + no leak, got rc=$rc node_found=$node_found suite_node=$suite_node marker_lines=$(wc -l < "$VENV_MARKER" 2>/dev/null || echo 0) stubbin=[$(ls "$STUBBIN")] out=[$out]"
fi

# --- 03-b: HTTP matrix ------------------------------------------------------
check_raw() { # check_raw <fixture> <want_rc> <reason-substring> <label>
  local fixture="$1" want_rc="$2" reason="$3" label="$4"
  out="$(python3 "$CUR/scripts/discovery-check.py" --raw < "$TMP/raw/$fixture.raw" 2>&1)"; rc=$?
  if [ "$rc" -eq "$want_rc" ] && echo "$out" | grep -qF "$reason"; then
    ok "03-b $label"
  else
    not_ok "03-b $label" "expected rc=$want_rc + [$reason], got rc=$rc out=[$out]"
  fi
}
check_raw valid-cl 0 "discovery: OK issuer=$CANONICAL_ISSUER" "valid Content-Length 200 -> OK, exact issuer accepted"
check_raw valid-chunked 0 "discovery: OK issuer=$CANONICAL_ISSUER" "valid chunked 200 -> OK, exact issuer accepted"
check_raw s401 1 "HTTP status 401" "HTTP 401 -> FAIL with status reason"
check_raw s404 1 "HTTP status 404" "HTTP 404 -> FAIL with status reason"
check_raw s503 1 "HTTP status 503" "HTTP 503 -> FAIL with status reason"
check_raw wrong-issuer 1 "issuer mismatch" "wrong issuer -> FAIL with issuer reason"
check_raw missing-issuer 1 "no 'issuer' field" "missing issuer -> FAIL with reason"
check_raw bad-json 1 "not valid JSON" "malformed JSON -> FAIL with reason"
check_raw html 1 "HTML body" "HTML body -> FAIL with reason"
check_raw truncated 1 "truncated response" "truncated response -> FAIL with reason"
check_raw chunked-badsize 1 "malformed chunk size" "chunked malformed size -> FAIL with reason"
check_raw chunked-trunc 1 "truncated chunked body" "chunked truncated -> FAIL with reason"
check_raw redirect 1 "redirect (HTTP 302" "redirect 302 -> FAIL, never followed"

# --- 03-c: --url mode against the stub server -------------------------------
out="$(python3 "$CUR/scripts/discovery-check.py" --url "http://127.0.0.1:$DISCOVERY_PORT/good" 2>&1)"; rc=$?
if [ "$rc" -eq 0 ] && echo "$out" | grep -q "discovery: OK issuer=$CANONICAL_ISSUER"; then
  ok "03-c --url good: stub server 200 JSON -> OK, exact issuer accepted"
else
  not_ok "03-c --url good" "expected rc=0 + OK, got rc=$rc out=[$out]"
fi
out="$(python3 "$CUR/scripts/discovery-check.py" --url "http://127.0.0.1:$DISCOVERY_PORT/redirect" 2>&1)"; rc=$?
if [ "$rc" -ne 0 ] && echo "$out" | grep -q "redirect (HTTP 302"; then
  ok "03-c --url redirect: 302 -> FAIL, never followed"
else
  not_ok "03-c --url redirect" "expected rc!=0 + redirect reason, got rc=$rc out=[$out]"
fi
out="$(python3 "$CUR/scripts/discovery-check.py" --url "http://127.0.0.1:$DISCOVERY_PORT/html" 2>&1)"; rc=$?
if [ "$rc" -ne 0 ] && echo "$out" | grep -q "HTML body"; then
  ok "03-c --url HTML: 200 text/html -> FAIL with HTML reason"
else
  not_ok "03-c --url HTML" "expected rc!=0 + HTML reason, got rc=$rc out=[$out]"
fi

# --- 04-a: ports occupied -> fail fast (Trustline v7.3.1, Finding C) ------
# Root cause of the v7.3 flake (parent Pass B: first run 33/1/0 with
# 04-a failing although rc=1, occupant_alive=1 and every asserted
# condition held on the logged values; immediate re-run 34/0/0):
# the old case started its own `python3 -m http.server` occupant on
# the REAL 8080, which cannot bind while the real Keycloak holds
# that port — the occupant PID was dead on arrival
# (OSError: [Errno 98] Address already in use, rc=1; reproduced by
# WS2, see docs/VERIFICATION_LOG.md v7.3.1), so the kill/wait/
# `kill -0` sequence observed a transient PID state instead of a
# live listener, and the readiness poll (a bare connect) could not
# tell OUR listener from the real stack's. The same case also failed
# once in WS2's hands with NO lab up (33/1/0, rc=0, occupant_alive=0
# — the fire-and-forget occupant was not holding 8080 when the
# preflight ran, so the script booted the disposable project): the
# case was nondeterministic in both directions.
#
# Fix: the occupied branch is now tested on CONTROLLED loopback
# ports via the existing IDENTITYFORGE_HCPROBE_TEST_PORTS override
# — never on the reviewer's real 8080/8000/5173, which the suite
# does not own. The branch under test is the same code (the
# preflight checks CHECK_PORTS whatever they are; the override only
# changes WHERE it looks, never WHAT it accepts), so proving
# fail-fast on test ports proves the branch, deterministically,
# whether the live stack is up or down. Port selection is explicit:
#   * the occupied port is chosen from a candidate list; a port
#     that is already held is NEVER silently counted as ours — its
#     owner is identified (best-effort `ss -ltnp` + our own PID
#     set) and logged, and a safe alternate is selected;
#   * the other two ports must be FREE (first free from their own
#     candidate lists), so the only occupant in the run is ours;
#   * startup readiness is an OBSERVED event: our listener must
#     answer a connect with the run's unique token AND its exact
#     PID must be alive — a bare "something answers" is not
#     readiness. Only infrastructure setup is retried (port
#     selection / occupant start); an assertion failure is never
#     retried or suppressed.
# Ownership after the run is proven by exact PID (`kill -0`), and
# cleanup is verified (PID gone AND the port free again) — no
# leaked processes or listeners. 04-c-A/04-c-B expectations are
# untouched by this change: no unscoped cleanup; exactly one
# scoped cleanup when a disposable project was actually created.
port_is_free() { # port_is_free <port> -> 0 if nothing answers
  python3 -c 'import socket,sys; s=socket.socket(); s.settimeout(2); sys.exit(0 if s.connect_ex(("127.0.0.1",int(sys.argv[1])))!=0 else 1)' "$1" 2>/dev/null
}
port_owner_info() { # port_owner_info <port> — best-effort owner identification
  local port="$1" line pid
  line="$(ss -ltnp 2>/dev/null | grep -E "127\.0\.0\.1:$port\b" | head -1 || true)"
  if [ -n "$line" ]; then
    pid="$(echo "$line" | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2 || true)"
    if [ -n "$pid" ]; then
      if [ "$pid" = "$DISCOVERY_PID" ]; then
        echo "owner of 127.0.0.1:$port is OUR discovery server (PID $pid)"
      else
        echo "owner of 127.0.0.1:$port is an EXTERNAL process (PID ${pid:-unknown}; ss: $line)"
      fi
    else
      echo "127.0.0.1:$port is held but ss reports no PID (ss: $line)"
    fi
  else
    echo "127.0.0.1:$port is held (connect succeeds) but ss -ltnp shows no listener line for it — owner not identifiable here; treating as external"
  fi
}
occupant_token_ok() { # occupant_token_ok <port> <token> -> 0 iff the listener greets with the token
  python3 - "$1" "$2" <<'PY' 2>/dev/null
import socket, sys
s = socket.socket()
s.settimeout(2)
try:
    s.connect(("127.0.0.1", int(sys.argv[1])))
    data = s.recv(256)
    sys.exit(0 if data.strip() == sys.argv[2].encode() else 1)
except OSError:
    sys.exit(1)
PY
}
# start_occupant <port> <token> — sets OCCUPANT_PID on success.
# Returns 1 when the port is held by someone else (bind fails at
# once) or the listener never proves itself with the token.
start_occupant() {
  local port="$1" token="$2" i
  python3 "$TMP/occupant-server.py" "$port" "$token" > "$TMP/occupant-$port.log" 2>&1 &
  OCCUPANT_PID=$!
  for i in $(seq 1 40); do
    if ! kill -0 "$OCCUPANT_PID" 2>/dev/null; then
      echo "04-a setup: occupant for 127.0.0.1:$port exited during startup (bind failed — port held by someone else; see $TMP/occupant-$port.log)"
      return 1
    fi
    if occupant_token_ok "$port" "$token"; then
      return 0
    fi
    sleep 0.25
  done
  echo "04-a setup: occupant for 127.0.0.1:$port never greeted with the token within 10s"
  kill "$OCCUPANT_PID" 2>/dev/null || true
  wait "$OCCUPANT_PID" 2>/dev/null || true
  return 1
}
OCC_TOKEN="IDENTITYFORGE-04A-OCCUPANT-$$-$(date -u +%Y%m%d%H%M%S)"
OCC_PORT=""; OCCUPANT_PID=""
for cand in 18084 18085 18086 18087; do
  if port_is_free "$cand"; then
    if start_occupant "$cand" "$OCC_TOKEN"; then
      OCC_PORT="$cand"
      echo "04-a setup: occupant is OUR listener (PID $OCCUPANT_PID) on 127.0.0.1:$OCC_PORT, token-proven"
      break
    fi
    echo "04-a setup: candidate 127.0.0.1:$cand could not be started as our occupant — trying the next candidate"
  else
    echo "04-a setup: candidate 127.0.0.1:$cand is already held — $(port_owner_info "$cand") — selecting a safe alternate, never counting it as ours"
  fi
done
FREE2=""; FREE3=""
for cand in 18004 18005 18006; do
  if port_is_free "$cand"; then FREE2="$cand"; break; fi
  echo "04-a setup: 127.0.0.1:$cand is held — $(port_owner_info "$cand") — trying the next candidate for the free port"
done
for cand in 15177 15178 15179; do
  if port_is_free "$cand"; then FREE3="$cand"; break; fi
  echo "04-a setup: 127.0.0.1:$cand is held — $(port_owner_info "$cand") — trying the next candidate for the free port"
done
if [ -z "$OCC_PORT" ] || [ -z "$FREE2" ] || [ -z "$FREE3" ]; then
  [ -n "$OCCUPANT_PID" ] && kill "$OCCUPANT_PID" 2>/dev/null
  not_ok "04-a ports occupied" "HARNESS FAILURE: no usable controlled test ports (occupied=$OCC_PORT free2=$FREE2 free3=$FREE3) — infrastructure setup failed, the occupied branch was not tested and nothing was asserted"
else
  rm -rf "$CUR/test-results"
  reset_stub
  out="$( (cd "$CUR" && env -i PATH="$STUBBIN:$ORIGINAL_PATH" HOME="$HOME" \
    STUB_LOG="$STUB_LOG" STUB_CONFIG_MODE=ok STUB_HEALTH=healthy \
    STUB_EXEC_MODE=ok STUB_UP_MODE=ok \
    IDENTITYFORGE_HCPROBE_TEST_PORTS="$OCC_PORT $FREE2 $FREE3" \
    IDENTITYFORGE_HCPROBE_DISCOVERY_URL="$DISCOVERY_URL" \
    bash scripts/test-compose-healthcheck.sh --with-docker) 2>&1)"; rc=$?
  # Ownership is proven by EXACT PID, not by the port: after the
  # run our listener must still be alive (kill -0) AND still greet
  # with our token. A port probe alone would be ambiguous whenever
  # the live stack (or anything else) holds a port.
  occupant_alive=0
  if kill -0 "$OCCUPANT_PID" 2>/dev/null && occupant_token_ok "$OCC_PORT" "$OCC_TOKEN"; then
    occupant_alive=1
  fi
  # Cleanup of OUR listener only, by exact PID — then verify the
  # cleanup: the PID must be gone AND the port free again, so a
  # leaked listener can never masquerade as the next run's occupant.
  kill "$OCCUPANT_PID" 2>/dev/null || true
  wait "$OCCUPANT_PID" 2>/dev/null || true
  leak=""
  if kill -0 "$OCCUPANT_PID" 2>/dev/null; then
    leak="occupant listener (PID $OCCUPANT_PID) was still running after kill"
  elif ! port_is_free "$OCC_PORT"; then
    leak="127.0.0.1:$OCC_PORT still answers after our occupant (PID $OCCUPANT_PID) was killed"
  fi
  if [ "$rc" -ne 0 ] && [ "$occupant_alive" -eq 1 ] && [ -z "$leak" ] \
     && echo "$out" | grep -q "occupied" \
     && echo "$out" | grep -q "docker compose down" \
     && echo "$out" | grep -q "against-running-project" \
     && ! grep -q " up " "$STUB_LOG" && ! grep -q " up$" "$STUB_LOG" \
     && ! grep -q " down " "$STUB_LOG"; then
    ok "04-a ports occupied: FAIL FAST before 'compose up' on controlled test ports ($OCC_PORT occupied by OUR token-proven listener PID $OCCUPANT_PID, $FREE2/$FREE3 free), stop/test/restart + read-only alternative printed, occupant still alive (never killed), cleaned up with no leak"
  else
    not_ok "04-a ports occupied" "expected rc!=0 + fail-fast + our occupant alive + clean teardown, got rc=$rc occupant_alive=$occupant_alive leak=${leak:-<none>} ports=$OCC_PORT/$FREE2/$FREE3 out=[$out] stub=[$([ -f "$STUB_LOG" ] && cat "$STUB_LOG")]"
  fi
fi

# --- 04-b: ports free -> unique project, boot, cleanup ONLY that project ---
rm -rf "$CUR/test-results"
reset_stub
out1="$(STUB_CONFIG_MODE=ok run_hc "$CUR" --with-docker 2>&1)"; rc1=$?
proj1="$(grep -o "identityforge-hcprobe-[0-9-]*" "$STUB_LOG" | head -1)"
reset_stub
out2="$(STUB_CONFIG_MODE=ok run_hc "$CUR" --with-docker 2>&1)"; rc2=$?
proj2="$(grep -o "identityforge-hcprobe-[0-9-]*" "$STUB_LOG" | head -1)"
# (the bare-down check is done plainly below)
bare_down=0
while IFS= read -r line; do
  case "$line" in
    *" down -v"*) case "$line" in *" -p $proj2 down -v"*) ;; *) bare_down=1 ;; esac ;;
  esac
done < "$STUB_LOG"
if [ "$rc1" -eq 0 ] && [ "$rc2" -eq 0 ] \
   && [ -n "$proj1" ] && [ -n "$proj2" ] && [ "$proj1" != "$proj2" ] \
   && [ "$bare_down" -eq 0 ]; then
  ok "04-b ports free: two runs got unique projects ($proj1 != $proj2), boot+check passed, cleanup 'down -v' named only the run's own project"
else
  not_ok "04-b ports free" "expected rc=0/0 + unique projects + scoped cleanup, got rc1=$rc1 rc2=$rc2 proj1=$proj1 proj2=$proj2 bare_down=$bare_down out2=[$out2]"
fi

# --- 04-b2: cleanup on failure (exec probe fails) still scoped -------------
rm -rf "$CUR/test-results"
reset_stub
out="$(STUB_CONFIG_MODE=ok STUB_EXEC_MODE=fail run_hc "$CUR" --with-docker 2>&1)"; rc=$?
proj="$(grep -o "identityforge-hcprobe-[0-9-]*" "$STUB_LOG" | head -1)"
if [ "$rc" -ne 0 ] && [ -n "$proj" ] \
   && grep -q "compose -p $proj down -v" "$STUB_LOG"; then
  ok "04-b2 failure cleanup: exec probe failed (rc=$rc) but trap still ran 'down -v' for ONLY the disposable project ($proj)"
else
  not_ok "04-b2 failure cleanup" "expected rc!=0 + scoped down -v, got rc=$rc proj=$proj out=[$out]"
fi

# --- 04-c: SIGTERM safety, synchronised (IF-V7.2-03, v7.3) -----------------
# The old test slept a fixed 4s and then sent SIGTERM, assuming the
# disposable project existed by then. On a slow worker TERM arrived
# before any project was created (auditor: rc=143, empty project ID,
# stub log showed ONLY `compose version` + `compose config`), so the
# test accused the cleanup routine of a failure the harness caused.
# The safety property is "clean up only the disposable project IF it
# exists and we are inside the live health-wait phase", not "always
# create a project within 4 seconds". Both timings are therefore
# separate sub-cases with an explicit bounded synchronisation point —
# no fixed sleep decides the outcome:
#   04-c-A  TERM BEFORE PROJECT CREATION: the stub blocks inside
#           `compose config` (no project can exist yet); TERM is sent
#           only after the config call is OBSERVED in the case stub
#           log. Expect: nonzero exit, no `up`, no `down`, no project
#           ID anywhere, no false failure.
#   04-c-B  TERM DURING HEALTH WAIT: TERM is sent only after the case
#           stub log shows the disposable project's `up --build -d`
#           AND a following `inspect` (the health-wait phase).
#           Expect: nonzero exit (143 acceptable), exactly ONE
#           `down -v`, scoped to the run's own disposable project,
#           never the user's default project, never a bare `down`.
# Each sub-case has its OWN stub log, its OWN tree copy and its OWN
# test ports, so fixture PIDs/ports cannot leak between cases. If the
# synchronisation phase is never reached within the timeout, that is a
# genuine startup/harness failure (reported as such) — never a
# misleading early SIGTERM and never an accusation against cleanup.
# Sync mechanism: the fake docker records every call in the case stub
# log, so the log IS the synchronisation channel (the up/ps/health
# phase is observable there). No shared-stub change was needed: the
# 04-c-A wrapper stubbin below only adds a blocking delay and is local
# to this section. (If the shared stub ever gains a READY_FOR_TERM
# marker file, this poll can watch that file instead; the assertions
# stay the same.)
wait_for_log() { # wait_for_log <logfile> <grep-pattern> <timeout-secs>
  local log="$1" pat="$2" timeout="$3"
  local deadline=$((SECONDS + timeout))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if grep -q "$pat" "$log" 2>/dev/null; then return 0; fi
    sleep 0.2
  done
  grep -q "$pat" "$log" 2>/dev/null
}

# --- 04-c-A: TERM BEFORE PROJECT CREATION ----------------------------------
C04A_DIR="$TMP/04c-a/identityforge"
copy_tree "$ROOT" "$C04A_DIR"
C04A_WRAPBIN="$TMP/04c-a/wrapbin"
mkdir -p "$C04A_WRAPBIN"
cat > "$C04A_WRAPBIN/docker" <<WRAP
#!/usr/bin/env bash
# 04-c-A fixture ONLY: log the call, then BLOCK inside 'compose config'
# so the script provably cannot have created a project yet when TERM is
# sent. The base stub logs the call a second time after the block ends
# (a duplicate 'compose config' line is expected here and is not
# asserted on); this case asserts on up/down/project lines only.
echo "docker \$*" >> "\$STUB_LOG"
case "\$*" in
  "compose config"*) sleep 15 ;;
esac
exec "$STUBBIN/docker" "\$@"
WRAP
chmod +x "$C04A_WRAPBIN/docker"
C04A_LOG="$TMP/04c-a-stub.log"
: > "$C04A_LOG"
rm -rf "$C04A_DIR/test-results"
# `exec` so $! below IS the script's bash PID (without it, $! is
# the wrapper subshell and the TERM would kill the wrapper while the
# script kept running, orphaned — which is exactly what a sloppy
# version of this test did once).
(cd "$C04A_DIR" && exec env -i PATH="$C04A_WRAPBIN:$STUBBIN:$ORIGINAL_PATH" HOME="$HOME" \
  STUB_LOG="$C04A_LOG" STUB_CONFIG_MODE=ok STUB_HEALTH=starting \
  STUB_EXEC_MODE=ok STUB_UP_MODE=ok \
  IDENTITYFORGE_HCPROBE_TEST_PORTS="18082 18002 15175" \
  IDENTITYFORGE_HCPROBE_DISCOVERY_URL="$DISCOVERY_URL" \
  bash scripts/test-compose-healthcheck.sh --with-docker > "$TMP/04c-a.out" 2>&1) &
HC_PID=$!
# Bounded sync: TERM only after 'compose config' is OBSERVED in the
# case stub log (the wrapper logs it before blocking, so this proves
# the script is inside config — no project can exist yet).
if wait_for_log "$C04A_LOG" "compose config" 60; then
  kill -TERM "$HC_PID" 2>/dev/null || true
  waited=0
  while kill -0 "$HC_PID" 2>/dev/null && [ "$waited" -lt 30 ]; do sleep 1; waited=$((waited + 1)); done
  if kill -0 "$HC_PID" 2>/dev/null; then kill -KILL "$HC_PID" 2>/dev/null; fi
  wait "$HC_PID" 2>/dev/null; hc_rc=$?
  proj="$(grep -o "identityforge-hcprobe-[0-9-]*" "$C04A_LOG" | head -1)"
  if [ "$hc_rc" -ne 0 ] && [ -z "$proj" ] \
     && ! grep -q " up " "$C04A_LOG" && ! grep -q " down " "$C04A_LOG" \
     && grep -q "PASS: static" "$TMP/04c-a.out"; then
    ok "04-c-A TERM before project creation: script exited rc=$hc_rc, no project ID, no 'up', no 'down' (nothing to clean, no false failure)"
  else
    not_ok "04-c-A TERM before project creation" "expected rc!=0 + no project + no up/down + static PASS, got rc=$hc_rc proj=${proj:-<empty>} out=[$([ -f "$TMP/04c-a.out" ] && cat "$TMP/04c-a.out")] stub=[$([ -f "$C04A_LOG" ] && cat "$C04A_LOG")]"
  fi
else
  # Startup/harness failure: the phase was never reached. Kill the
  # hung process outright (KILL, not TERM — no signal semantics are
  # under test here) and report the harness failure, never accusing
  # the cleanup routine of anything.
  kill -KILL "$HC_PID" 2>/dev/null || true
  wait "$HC_PID" 2>/dev/null
  not_ok "04-c-A TERM before project creation" "HARNESS FAILURE: 'compose config' phase never reached within 60s (script did not start up; no SIGTERM sent, cleanup not accused) — stub=[$([ -f "$C04A_LOG" ] && cat "$C04A_LOG")]"
fi

# --- 04-c-B: TERM DURING HEALTH WAIT ---------------------------------------
C04B_DIR="$TMP/04c-b/identityforge"
copy_tree "$ROOT" "$C04B_DIR"
C04B_LOG="$TMP/04c-b-stub.log"
: > "$C04B_LOG"
rm -rf "$C04B_DIR/test-results"
(cd "$C04B_DIR" && exec env -i PATH="$STUBBIN:$ORIGINAL_PATH" HOME="$HOME" \
  STUB_LOG="$C04B_LOG" STUB_CONFIG_MODE=ok STUB_HEALTH=starting \
  STUB_EXEC_MODE=ok STUB_UP_MODE=ok \
  IDENTITYFORGE_HCPROBE_TEST_PORTS="18083 18003 15176" \
  IDENTITYFORGE_HCPROBE_DISCOVERY_URL="$DISCOVERY_URL" \
  bash scripts/test-compose-healthcheck.sh --with-docker > "$TMP/04c-b.out" 2>&1) &
HC_PID=$!
# Bounded sync: TERM only after the disposable project's `up` AND a
# following `inspect` (the health-wait phase) are OBSERVED in the case
# stub log. The wait loop runs 300s with STUB_HEALTH=starting, so once
# the first inspect is seen the script stays in the health wait for
# minutes — TERM cannot land after the phase has passed.
phase_ok=0
if wait_for_log "$C04B_LOG" " up --build -d" 60 && wait_for_log "$C04B_LOG" "^docker inspect " 60; then
  phase_ok=1
fi
if [ "$phase_ok" -eq 1 ]; then
  kill -TERM "$HC_PID" 2>/dev/null || true
  waited=0
  while kill -0 "$HC_PID" 2>/dev/null && [ "$waited" -lt 30 ]; do sleep 1; waited=$((waited + 1)); done
  if kill -0 "$HC_PID" 2>/dev/null; then kill -KILL "$HC_PID" 2>/dev/null; fi
  wait "$HC_PID" 2>/dev/null; hc_rc=$?
  proj="$(grep -o "identityforge-hcprobe-[0-9-]*" "$C04B_LOG" | head -1)"
  down_n="$(grep -c " down -v" "$C04B_LOG" || true)"
  scoped_n=0
  [ -n "$proj" ] && scoped_n="$(grep -c "compose -p $proj down -v" "$C04B_LOG" || true)"
  up_n="$(grep -c " up --build -d" "$C04B_LOG" || true)"
  # Any down/up NOT scoped to the run's own disposable project?
  bad_scoped=0
  while IFS= read -r line; do
    case "$line" in
      *" down -v"*|*" up --build -d"*)
        case "$line" in *" -p $proj "* ) ;; *) bad_scoped=1 ;; esac ;;
    esac
  done < "$C04B_LOG"
  if [ -n "$proj" ] && [ "$hc_rc" -ne 0 ] \
     && [ "$down_n" -eq 1 ] && [ "$scoped_n" -eq 1 ] \
     && [ "$up_n" -eq 1 ] && [ "$bad_scoped" -eq 0 ]; then
    ok "04-c-B TERM during health wait: script exited rc=$hc_rc, exactly ONE 'down -v' scoped to the run's own disposable project ($proj), no unscoped up/down"
  else
    not_ok "04-c-B TERM during health wait" "expected rc!=0 + exactly 1 scoped down -v + 1 scoped up, got rc=$hc_rc proj=${proj:-<empty>} down_n=$down_n scoped_n=$scoped_n up_n=$up_n bad_scoped=$bad_scoped stub=[$([ -f "$C04B_LOG" ] && cat "$C04B_LOG")]"
  fi
else
  kill -KILL "$HC_PID" 2>/dev/null || true
  wait "$HC_PID" 2>/dev/null
  not_ok "04-c-B TERM during health wait" "HARNESS FAILURE: health-wait phase (up + inspect) never reached within 60s (script did not start up; no SIGTERM sent, cleanup not accused) — stub=[$([ -f "$C04B_LOG" ] && cat "$C04B_LOG")]"
fi

# --- 04-d: read-only mode ----------------------------------------------------
rm -rf "$CUR/test-results"
reset_stub
out="$(STUB_CONFIG_MODE=ok run_hc "$CUR" --against-running-project 2>&1)"; rc=$?
if [ "$rc" -eq 0 ] \
   && ! grep -qE " (up|down)( |$)" "$STUB_LOG" \
   && grep -q "compose config" "$STUB_LOG" \
   && echo "$out" | grep -q "read-only"; then
  ok "04-d read-only: --against-running-project exit 0, stub log shows NO 'up' and NO 'down' (nothing created or deleted)"
else
  not_ok "04-d read-only" "expected rc=0 + no up/down, got rc=$rc out=[$out] stub=[$([ -f "$STUB_LOG" ] && cat "$STUB_LOG")]"
fi

# --- 04-g: fake Docker CLI present, daemon missing -> both explicit modes rc!=0
# Coordinator Pass A (IF-V7.2-01 gate 3): `docker compose version`
# succeeds while `docker info` fails. The script must name the daemon,
# record the live checks NOT RUN, never run `compose config`, never
# boot anything, and exit nonzero in BOTH explicit modes — no phantom
# PASS from the version check alone.
rm -rf "$CUR/test-results"
reset_stub
out="$(STUB_DAEMON_MODE=missing run_hc "$CUR" --with-docker 2>&1)"; rc=$?
if [ "$rc" -ne 0 ] && echo "$out" | grep -q "Docker daemon inaccessible" \
   && echo "$out" | grep -q "NOT RUN" \
   && grep -q "compose version" "$STUB_LOG" \
   && grep -q "docker info" "$STUB_LOG" \
   && ! grep -q "compose config" "$STUB_LOG" \
   && ! grep -qE " (up|down)( |$)" "$STUB_LOG"; then
  ok "04-g daemon missing (--with-docker): rc!=0, daemon named, 'compose version' + 'docker info' ran but 'compose config' never ran, no up/down, no phantom PASS"
else
  not_ok "04-g daemon missing (--with-docker)" "expected rc!=0 + 'Docker daemon inaccessible' + NOT RUN + version/info only, got rc=$rc out=[$out] stub=[$([ -f "$STUB_LOG" ] && cat "$STUB_LOG")]"
fi
rm -rf "$CUR/test-results"
reset_stub
out="$(STUB_DAEMON_MODE=missing run_hc "$CUR" --against-running-project 2>&1)"; rc=$?
if [ "$rc" -ne 0 ] && echo "$out" | grep -q "Docker daemon inaccessible" \
   && echo "$out" | grep -q "NOT RUN" \
   && grep -q "docker info" "$STUB_LOG" \
   && ! grep -q "compose config" "$STUB_LOG" \
   && ! grep -qE " (up|down)( |$)" "$STUB_LOG"; then
  ok "04-g daemon missing (--against-running-project): rc!=0, daemon named, no config/up/down, read-only mode never touched the stack"
else
  not_ok "04-g daemon missing (--against-running-project)" "expected rc!=0 + 'Docker daemon inaccessible' + NOT RUN, got rc=$rc out=[$out] stub=[$([ -f "$STUB_LOG" ] && cat "$STUB_LOG")]"
fi

# make_nodocker_path — build a PATH that hides ONLY the docker CLIs
# (IF-V7.2-02). The v7.2 04-e case used PATH="/usr/bin:/bin", which
# also hid the caller's python3 (and its PyYAML) — the same root
# cause as the run_hc bug. Instead, walk ORIGINAL_PATH in order: a
# directory with no docker/docker-compose executable is kept
# VERBATIM (so a venv python, a Node managed outside /usr/bin, and
# every other tool resolve exactly as the caller sees them); a
# directory that DOES contain a docker CLI is replaced by a fresh
# shadow dir under $TMP holding symlinks to all its OTHER
# executables. The result hides docker and nothing else, and nothing
# is deleted — the shadow dirs live under $TMP (the EXIT trap
# removes them). Sets $NODOCKER_PATH.
make_nodocker_path() {
  local dir shadow i f base
  local -a parts
  IFS=':' read -r -a parts <<< "$ORIGINAL_PATH"
  NODOCKER_PATH=""
  i=0
  for dir in "${parts[@]}"; do
    [ -n "$dir" ] || continue
    [ -d "$dir" ] || continue
    if [ -x "$dir/docker" ] || [ -x "$dir/docker-compose" ]; then
      i=$((i + 1))
      shadow="$TMP/nodocker/$i"
      mkdir -p "$shadow"
      for f in "$dir"/*; do
        [ -e "$f" ] || continue
        [ -x "$f" ] || continue
        [ -d "$f" ] && continue
        base="$(basename "$f")"
        case "$base" in docker|docker-compose) continue ;; esac
        ln -s "$f" "$shadow/$base" 2>/dev/null || true
      done
      dir="$shadow"
    fi
    if [ -n "$NODOCKER_PATH" ]; then
      NODOCKER_PATH="$NODOCKER_PATH:$dir"
    else
      NODOCKER_PATH="$dir"
    fi
  done
}

# --- 04-e: no Docker at all, --with-docker explicitly selected --------------
# IF-V7.2-01 exit contract (WS1): an explicitly requested Docker probe
# that cannot run is NONZERO with the Docker parts NOT RUN — never a
# silent exit 0, never a phantom PASS. The static part must still
# PASS (the caller's python3 WITH PyYAML is preserved by the
# filtered PATH — the v7.2 "/usr/bin:/bin" form hid it and turned
# this case into a yaml traceback). The default (no-flag) mode keeps
# exit 0; that is 04-f, not this case.
make_nodocker_path
rm -rf "$CUR/test-results"
out="$( (cd "$CUR" && env -i PATH="$NODOCKER_PATH" HOME="$HOME" bash scripts/test-compose-healthcheck.sh --with-docker) 2>&1)"; rc=$?
if [ "$rc" -ne 0 ] && echo "$out" | grep -q "PASS: static:" \
   && echo "$out" | grep -q "NOT RUN" \
   && echo "$out" | grep -q "Docker CLI unavailable" \
   && ! echo "$out" | grep -q "ModuleNotFoundError" \
   && ! echo "$out" | grep -q "FAIL: static:"; then
  ok "04-e no Docker, --with-docker: static PASS, Docker parts NOT RUN, exit $rc (nonzero — explicitly requested probe could not run, never a phantom PASS)"
else
  not_ok "04-e no Docker, --with-docker" "expected rc!=0 + static PASS + NOT RUN + 'Docker CLI unavailable', no yaml traceback, got rc=$rc out=[$out]"
fi

# --- 04-f: no Docker at all, default mode (no flag) -> exit 0 ----------------
# The static regression is the gate that runs everywhere; with no
# Docker mode requested, the Docker parts are NOT RUN and the script
# still exits 0 (IF-V7.2-01 changes only the explicit --with-docker
# contract, not the default).
rm -rf "$CUR/test-results"
out="$( (cd "$CUR" && env -i PATH="$NODOCKER_PATH" HOME="$HOME" bash scripts/test-compose-healthcheck.sh) 2>&1)"; rc=$?
if [ "$rc" -eq 0 ] && echo "$out" | grep -q "PASS: static:" \
   && echo "$out" | grep -q "NOT RUN" \
   && ! echo "$out" | grep -q "ModuleNotFoundError"; then
  ok "04-f no Docker, default mode: static PASS, Docker parts NOT RUN, exit 0"
else
  not_ok "04-f no Docker, default mode" "expected rc=0 + static PASS + NOT RUN, got rc=$rc out=[$out]"
fi

echo
echo "healthcheck-regressions: $PASS_COUNT passed, $FAIL_COUNT failed, $NOTRUN_COUNT not run"
if [ "$FAIL_COUNT" -gt 0 ]; then
  printf '  FAILED: %s\n' "${failures[@]}"
  exit 1
fi
echo "healthcheck-regressions: PASS"
