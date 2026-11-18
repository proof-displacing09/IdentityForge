#!/usr/bin/env pwsh
# IdentityForge Compose healthcheck — PowerShell matrix test (Trustline v7.3.1).
#
# Stub-only PowerShell matrix for scripts/test-compose-healthcheck.ps1
# (findings IF-V7.3.1-A: default-mode false pass with zero static checks;
# IF-V7.3.1-B: missing `docker info` daemon preflight; IF-V7.3.1-E:
# runtime smoke checks for Test-PortFree / Test-Discovery).
#
# Every case asserts BOTH the child process exit code AND the PASS / FAIL /
# NOT RUN counts parsed from the child's summary line — never a text
# substring alone. No real Docker is ever invoked: the stub `docker` logs
# every call, so each case also proves which Compose commands actually ran
# (zero up/down/reset before a live check is justified; exactly one scoped
# `down -v` for a disposable success; zero up/down in read-only mode).
#
# Usage (from the extracted release folder):
#   pwsh -File scripts/test-compose-healthcheck-ps-matrix.ps1 [-SourceRoot <tree>]
#     -SourceRoot  tree to copy the healthcheck script from (default: this
#                  script's own tree). Point it at a tree with the UNFIXED
#                  script to prove the matrix catches A/B failing-first.
#   Run with `pwsh -File` (note: `pwsh -Command "& {...}"` swallows a
#   script's exit code — use -File). Exit 0 only when every case passes;
#   exit 1 when any case fails. NOT RUN cases (e.g. no Python for the
#   synthetic responder) are reported, never counted as PASS.
#
# PowerShell 5.1-compatible syntax (no ??, no ternary, no ForEach-Object
# -Parallel, no $IsWindows, no Select-String -Raw), so it can run on the
# reviewer's Windows PowerShell 5.1. Tested on PowerShell 7.4.6 on Linux;
# Windows PowerShell 5.1 execution remains a reviewer gate. The Windows
# stub branch (docker.cmd forwarder + docker-stub.ps1) is NOT RUN here —
# only the docker-stub.ps1 LOGIC was exercised standalone under pwsh 7.4.6;
# the Linux branch uses the bash stub below and is fully exercised.
#
# Cases:
#   PS-A1  default, no static checker at all -> rc 1, 0/0/4, ENVIRONMENT NOT READY
#   PS-A2  default, static PASS via Python+PyYAML -> rc 0, 1/0/3, Docker NOT RUN loud
#   PS-A2b default, static PASS via `docker compose config` -> rc 0, 1/0/3
#   PS-A3  default, static PASS via Python, daemon missing -> rc 0, 1/0/3
#   PS-B1  -WithDocker, Docker CLI missing -> rc 1, CLI named, zero up/down/reset
#   PS-B2  -WithDocker, Compose plugin missing -> rc 1, Compose named, no config/up/down
#   PS-B3  -WithDocker, daemon missing -> rc 1, daemon named, version+info only
#   PS-B3b -AgainstRunningProject, daemon missing -> rc 1, daemon named, no config/up/down
#   PS-B4  -AgainstRunningProject, Docker CLI missing -> rc 1, CLI named
#   PS-C1  -WithDocker, full fake success (x2 runs) -> rc 0, 8/0/0, unique
#          disposable projects, exactly one scoped `down -v` per run
#   PS-C2  -AgainstRunningProject, full fake success -> rc 0, 7/0/0, zero up/down
#   PS-D1  -WithDocker, fixed port occupied -> fail fast rc 1, occupant alive,
#          stop/test/restart + read-only hint, zero up/down
#   PS-D2  flag conflict -> rc 2; unknown argument -> rc 2; -Help -> rc 0
#   PS-D3  stale probe artifacts -> no phantom PASS (stale exec/config logs
#          are cleared/overwritten before the probe reads them)
#   PS-E0  TcpClient InterNetwork overload (same constructor form as the
#          script): connects to a listener, refused on a free port
#   PS-E1..E8  Test-Discovery via the real script + synthetic HTTP responder:
#          200 good / 200 chunked -> rc 0; 302 / 401 / malformed JSON /
#          truncated Content-Length / truncated chunked / wrong issuer -> rc 1
#          with the precise reason (6/1/0 each)
[CmdletBinding()]
param(
    [switch]$Help,
    [string]$SourceRoot
)

$ErrorActionPreference = "Continue"

if ($Help) {
    Write-Host "Usage: pwsh -File scripts/test-compose-healthcheck-ps-matrix.ps1 [-SourceRoot <tree>]"
    Write-Host "  Stub-only PowerShell matrix for scripts/test-compose-healthcheck.ps1."
    Write-Host "  Exit 0 only when every case passes; exit 1 when any case fails."
    exit 0
}

$ScriptRoot = $PSScriptRoot
if ([string]::IsNullOrEmpty($ScriptRoot)) { $ScriptRoot = (Get-Location).Path }
$Root = Split-Path -Parent $ScriptRoot
if (-not [string]::IsNullOrEmpty($SourceRoot)) { $Root = $SourceRoot }
if (-not (Test-Path (Join-Path $Root "scripts\test-compose-healthcheck.ps1"))) {
    Write-Host "MATRIX SETUP FAIL: no scripts/test-compose-healthcheck.ps1 under $Root" -ForegroundColor Red
    exit 2
}

# --- helpers: child pwsh / python -------------------------------------------
function Get-ChildPwsh {
    # Prefer the process running THIS matrix (so a 5.1 run spawns 5.1
    # children); fall back to `pwsh` on PATH.
    $p = Get-Process -Id $PID -ErrorAction SilentlyContinue
    if ($p -and $p.Path) { return $p.Path }
    $c = Get-Command pwsh -ErrorAction SilentlyContinue
    if ($c -and $c.Source) { return $c.Source }
    return "pwsh"
}
$script:PwshExe = Get-ChildPwsh
$script:PythonExe = $null
$script:PythonHasYaml = $false
foreach ($name in @("python3", "python")) {
    $c = Get-Command $name -ErrorAction SilentlyContinue
    if (-not $c) { continue }
    $script:PythonExe = $c.Source
    & $script:PythonExe -c "import yaml" > $null 2> $null
    if ($LASTEXITCODE -eq 0) { $script:PythonHasYaml = $true }
    break
}

$script:CasePass = 0
$script:CaseFail = 0
$script:CaseNotRun = 0
$script:Failures = @()
function Add-CaseResult {
    param([string]$Id, [string]$Name, [bool]$Ok, [string]$Detail)
    if ($Ok) {
        $script:CasePass++
        Write-Host "CASE ${Id}: PASS - ${Name} -- ${Detail}"
    } else {
        $script:CaseFail++
        $script:Failures += "${Id} ${Name} -- ${Detail}"
        Write-Host "CASE ${Id}: FAIL - ${Name} -- ${Detail}" -ForegroundColor Red
    }
}
function Add-CaseNotRun {
    param([string]$Id, [string]$Name, [string]$Detail)
    $script:CaseNotRun++
    Write-Host "CASE ${Id}: NOT RUN - ${Name} -- ${Detail}" -ForegroundColor Yellow
}

function Test-TcpConnect {
    param([int]$Port)
    # Same constructor form as Test-PortFree in the script under test:
    # New-Object TcpClient([AddressFamily]::InterNetwork) forces IPv4.
    $client = New-Object System.Net.Sockets.TcpClient([System.Net.Sockets.AddressFamily]::InterNetwork)
    try {
        $client.Connect("127.0.0.1", $Port)
        $client.Close()
        return $true
    } catch {
        return $false
    } finally {
        if ($client) { $client.Dispose() }
    }
}

function New-VisibleLink {
    param([string]$Dir, [string]$Name, [string]$Target)
    $link = Join-Path $Dir $Name
    if (Test-Path $link) { return }
    try {
        New-Item -ItemType SymbolicLink -Path $link -Value $Target -ErrorAction Stop | Out-Null
    } catch {
        Copy-Item -Force $Target $link -ErrorAction SilentlyContinue
    }
}

# --- work area ---------------------------------------------------------------
$Sep = [System.IO.Path]::PathSeparator
$WorkRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("hc-ps-matrix-" + (Get-Date).ToUniversalTime().ToString("yyyyMMddHHmmss") + "-" + $PID)
New-Item -ItemType Directory -Force -Path $WorkRoot | Out-Null
$Tree = Join-Path $WorkRoot "identityforge"
New-Item -ItemType Directory -Force -Path $Tree | Out-Null
$StubBin = Join-Path $WorkRoot "stubbin"
$VisibleBin = Join-Path $WorkRoot "visiblebin"
$EmptyBin = Join-Path $WorkRoot "emptybin"
New-Item -ItemType Directory -Force -Path $StubBin | Out-Null
New-Item -ItemType Directory -Force -Path $VisibleBin | Out-Null
New-Item -ItemType Directory -Force -Path $EmptyBin | Out-Null
$script:StubLog = Join-Path $WorkRoot "stub-docker.log"
$script:HcScript = Join-Path $Tree "scripts\test-compose-healthcheck.ps1"
$ResponderPort = 18381
$TestPorts = "18380 18300 18673"
$GoodDiscoveryUrl = "http://127.0.0.1:$ResponderPort/good"

if ($script:PythonExe) { New-VisibleLink $VisibleBin "python3" $script:PythonExe; New-VisibleLink $VisibleBin "python" $script:PythonExe }

Write-Host "== test-compose-healthcheck.ps1 matrix (IF-V7.3.1-A/B/E) =="
Write-Host "pwsh: $script:PwshExe ($(& $script:PwshExe -NoProfile -Command '$PSVersionTable.PSVersion.ToString()'))"
if ($script:PythonExe) {
    Write-Host "python: $script:PythonExe (PyYAML: $script:PythonHasYaml)"
} else {
    Write-Host "python: none on PATH (Python-dependent cases will be NOT RUN)"
}
Write-Host "source tree: $Root"
Write-Host "work dir: $WorkRoot"

Copy-Item -Recurse -Force (Join-Path $Root "*") $Tree -ErrorAction Stop
if (-not (Test-Path $script:HcScript)) {
    Write-Host "MATRIX SETUP FAIL: tree copy did not produce $script:HcScript" -ForegroundColor Red
    Remove-Item -Recurse -Force $WorkRoot -ErrorAction SilentlyContinue
    exit 2
}

function Reset-Tree {
    $tr = Join-Path $Tree "test-results"
    if (Test-Path $tr) { Remove-Item -Recurse -Force $tr -ErrorAction SilentlyContinue }
}
function Reset-StubLog {
    if (Test-Path $script:StubLog) { Remove-Item -Force $script:StubLog -ErrorAction SilentlyContinue }
}
function Get-StubText {
    if (Test-Path $script:StubLog) {
        $t = Get-Content $script:StubLog -Raw -ErrorAction SilentlyContinue
        if ($t -eq $null) { return "" }
        return $t
    }
    return ""
}
function Count-Needle {
    param([string]$Text, [string]$Needle)
    return ([regex]::Matches($Text, [regex]::Escape($Needle))).Count
}
function Get-ProjectId {
    param([string]$Text)
    $m = [regex]::Match($Text, 'identityforge-hcprobe-[0-9]+-[0-9]+')
    if ($m.Success) { return $m.Value }
    return ""
}

function New-BaseEnv {
    param([string]$Ports, [string]$DiscoveryUrl)
    $h = @{}
    $h["STUB_LOG"] = $script:StubLog
    $h["STUB_CONFIG_MODE"] = "ok"
    $h["STUB_HEALTH"] = "healthy"
    $h["STUB_EXEC_MODE"] = "ok"
    $h["STUB_UP_MODE"] = "ok"
    $h["STUB_DAEMON_MODE"] = "ok"
    $h["STUB_COMPOSE_MODE"] = "ok"
    $h["IDENTITYFORGE_HCPROBE_TEST_PORTS"] = $Ports
    $h["IDENTITYFORGE_HCPROBE_DISCOVERY_URL"] = $DiscoveryUrl
    return $h
}

# Invoke-Hc: run the script under test as a CHILD pwsh with a controlled
# PATH + env, capturing stdout/stderr to a file and the real exit code.
# Returns @{ Rc; Out; Pass; Fail; NotRun } with counts parsed from the
# child's summary line (Pass/Fail/NotRun are -1 when no summary was printed).
function Invoke-Hc {
    param([string[]]$ModeArgs, [string]$ChildPath, [hashtable]$ExtraEnv, [string]$OutFile)
    $savedPath = $env:PATH
    $saved = @{}
    $env:PATH = $ChildPath
    foreach ($k in $ExtraEnv.Keys) {
        if (Test-Path ("Env:" + $k)) { $saved[$k] = (Get-Item ("Env:" + $k)).Value } else { $saved[$k] = $null }
        Set-Item ("Env:" + $k) $ExtraEnv[$k]
    }
    try {
        & $script:PwshExe -NoProfile -File $script:HcScript @ModeArgs > $OutFile 2>&1
        $rc = $LASTEXITCODE
    } finally {
        $env:PATH = $savedPath
        foreach ($k in $ExtraEnv.Keys) {
            if ($saved[$k] -eq $null) {
                Remove-Item ("Env:" + $k) -ErrorAction SilentlyContinue
            } else {
                Set-Item ("Env:" + $k) $saved[$k]
            }
        }
    }
    $out = ""
    if (Test-Path $OutFile) {
        $o = Get-Content $OutFile -Raw -ErrorAction SilentlyContinue
        if ($o -ne $null) { $out = $o }
    }
    $pass = -1; $fail = -1; $notrun = -1
    $m = [regex]::Match($out, 'compose-healthcheck: (\d+) passed, (\d+) failed, (\d+) not run')
    if ($m.Success) {
        $pass = [int]$m.Groups[1].Value
        $fail = [int]$m.Groups[2].Value
        $notrun = [int]$m.Groups[3].Value
    }
    return @{ Rc = $rc; Out = $out; Pass = $pass; Fail = $fail; NotRun = $notrun }
}
function Out-FileFor { param([string]$Name) return (Join-Path $WorkRoot ("case-" + $Name + ".out")) }

# --- stub docker -------------------------------------------------------------
# One behaviour spec, two shims: a bash `docker` on non-Windows (exercised
# here), and docker.cmd -> docker-stub.ps1 on Windows (the .ps1 logic was
# exercised standalone under pwsh 7.4.6; the .cmd forwarding itself is
# NOT RUN in this sandbox). Both log every call as one line in $STUB_LOG
# and answer from STUB_CONFIG_MODE / STUB_HEALTH / STUB_EXEC_MODE /
# STUB_UP_MODE / STUB_DAEMON_MODE / STUB_COMPOSE_MODE. Never touches a daemon.
$BashStub = @'
#!/bin/bash
# Fake docker for the PS healthcheck matrix. Logs "docker $*" then
# answers from canned behaviour. Never touches a daemon.
# Self-contained by design: the child runs with a MINIMAL PATH (stubbin
# only, so no real python/docker can leak in), so the shebang is an
# absolute /bin/bash (never /usr/bin/env, which resolves via PATH) and
# the only external used is /bin/cat (absolute path). Everything else
# (echo, printf, case) is a bash builtin.
echo "docker $*" >> "$STUB_LOG"
case "$*" in
  "compose version"*)
    if [ "${STUB_COMPOSE_MODE:-ok}" = "fail" ]; then echo "docker: 'compose' is not a docker command" >&2; exit 1; fi
    echo "Docker Compose version v2.99.0-stub"; exit 0 ;;
  "info"*)
    if [ "${STUB_DAEMON_MODE:-ok}" = "missing" ]; then
      echo "Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?" >&2
      exit 1
    fi
    echo "Client: stub / Server: stub"; exit 0 ;;
  "compose config"*)
    if [ "${STUB_CONFIG_MODE:-ok}" = "fail" ]; then echo "ERROR: yaml: line 12: mapping values are not allowed in this context" >&2; exit 1; fi
    /bin/cat <<'YAML'
services:
  keycloak:
    healthcheck:
      test: ["CMD", "bash", "-c", "exec 3<>/dev/tcp/127.0.0.1/8080 && resp=$(cat <&3) && echo \"$resp\" | grep -qE 'HTTP/1\\.[01] 200' && echo \"$resp\" | grep -q '\"issuer\"'"]
YAML
    exit 0 ;;
  *" up --build -d"*)
    if [ "${STUB_UP_MODE:-ok}" = "fail" ]; then echo "ERROR: failed to build" >&2; exit 1; fi
    echo "up ok"; exit 0 ;;
  *" down -v"*)
    echo "down ok"; exit 0 ;;
  "inspect"*)
    if [ "${STUB_HEALTH:-healthy}" = "healthy" ]; then printf '%s' '{"Status":"healthy","FailingStreak":0,"Log":[]}';
    else printf '%s' '{"Status":"starting","FailingStreak":0,"Log":[]}'; fi
    exit 0 ;;
  *" exec -T keycloak"*)
    if [ "${STUB_EXEC_MODE:-ok}" = "fail" ]; then echo "exec probe failed" >&2; exit 1; fi
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
'@
$PsStub = @'
# Fake docker for the PS healthcheck matrix (Windows branch).
# Same behaviour spec as the bash stub: logs "docker <args>" to
# $env:STUB_LOG, then answers from STUB_* env vars. Never touches a daemon.
$log = $env:STUB_LOG
if ($log) { Add-Content -Path $log -Value ("docker " + ($args -join " ")) }
$joined = $args -join " "
switch -Wildcard ($joined) {
    "compose version*" {
        if ($env:STUB_COMPOSE_MODE -eq "fail") { Write-Error "docker: 'compose' is not a docker command"; exit 1 }
        Write-Output "Docker Compose version v2.99.0-stub"; exit 0
    }
    "info*" {
        if ($env:STUB_DAEMON_MODE -eq "missing") { Write-Error "Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?"; exit 1 }
        Write-Output "Client: stub / Server: stub"; exit 0
    }
    "compose config*" {
        if ($env:STUB_CONFIG_MODE -eq "fail") { Write-Error "ERROR: yaml: line 12: mapping values are not allowed in this context"; exit 1 }
        $yaml = @"
services:
  keycloak:
    healthcheck:
      test: ["CMD", "bash", "-c", "exec 3<>/dev/tcp/127.0.0.1/8080 && resp=`$(cat <&3) && echo "`$resp" | grep -qE 'HTTP/1\.[01] 200' && echo "`$resp" | grep -q '"issuer"']
"@
        Write-Output $yaml; exit 0
    }
    "* up --build -d*" {
        if ($env:STUB_UP_MODE -eq "fail") { Write-Error "ERROR: failed to build"; exit 1 }
        Write-Output "up ok"; exit 0
    }
    "* down -v*" { Write-Output "down ok"; exit 0 }
    "inspect*" {
        if ($env:STUB_HEALTH -eq "healthy") { Write-Output '{"Status":"healthy","FailingStreak":0,"Log":[]}' } else { Write-Output '{"Status":"starting","FailingStreak":0,"Log":[]}' }
        exit 0
    }
    "* exec -T keycloak*" {
        if ($env:STUB_EXEC_MODE -eq "fail") { Write-Error "exec probe failed"; exit 1 }
        Write-Output "exec ok"; exit 0
    }
    "* ps -q keycloak*" { Write-Output "fake-keycloak-id"; exit 0 }
    "* ps -q backend*" { Write-Output "fake-backend-id"; exit 0 }
    "* ps -q frontend*" { Write-Output "fake-frontend-id"; exit 0 }
    "compose ps*" { Write-Output "NAME STATUS"; Write-Output "fake-keycloak-id healthy"; exit 0 }
    default { Write-Error ("stub: unhandled call: docker " + $joined); exit 0 }
}
'@
if ($env:OS -eq "Windows_NT") {
    Set-Content -Path (Join-Path $StubBin "docker-stub.ps1") -Value $PsStub -Encoding ASCII
    Set-Content -Path (Join-Path $StubBin "docker.cmd") -Value @("@echo off", '"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0docker-stub.ps1" %*', "exit /b %ERRORLEVEL%") -Encoding ASCII
    Write-Host "stub docker: Windows branch (docker.cmd -> docker-stub.ps1; forwarding NOT RUN in this sandbox)"
} else {
    Set-Content -Path (Join-Path $StubBin "docker") -Value $BashStub -Encoding ASCII
    & chmod +x (Join-Path $StubBin "docker")
    Write-Host "stub docker: bash stub at $(Join-Path $StubBin 'docker')"
}
$StubPath = $StubBin + $Sep + $VisibleBin
$StubOnlyPath = $StubBin + $Sep + $EmptyBin
$PythonOnlyPath = $VisibleBin

# --- synthetic HTTP responder (finding E) ------------------------------------
$ResponderCode = @'
"""Stub discovery responder for the PS healthcheck matrix (finding E).

Serves raw HTTP responses per path on loopback only (ThreadingHTTPServer):
 /good          200 Content-Length JSON, canonical issuer
 /chunked-good  200 chunked JSON, canonical issuer
 /redirect      302 Location
 /s401          401
 /badjson       200 malformed JSON
 /truncated     200 Content-Length 200, only 10 body bytes, then close
 /chunked-trunc 200 chunked, incomplete chunk, then close
 /wrong-issuer  200 JSON with a different issuer
 /html          200 text/html
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ISSUER = "http://127.0.0.1:8080/realms/identityforge-lab"
GOOD = json.dumps({"issuer": ISSUER}).encode()
WRONG = json.dumps({"issuer": "http://127.0.0.1:8080/realms/other"}).encode()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _raw(self, head, body=b""):
        self.wfile.write(head + body)

    def do_GET(self):
        p = self.path
        if p == "/good":
            self._raw(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % len(GOOD), GOOD)
        elif p == "/chunked-good":
            body = b"%x\r\n" % len(GOOD) + GOOD + b"\r\n0\r\n\r\n"
            self._raw(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n", body)
        elif p == "/redirect":
            self._raw(b"HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1:18381/good\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        elif p == "/s401":
            self._raw(b"HTTP/1.1 401 Unauthorized\r\nContent-Length: 2\r\nConnection: close\r\n\r\n", b"{}")
        elif p == "/badjson":
            self._raw(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 7\r\nConnection: close\r\n\r\n", b"{oops!}")
        elif p == "/truncated":
            self._raw(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 200\r\nConnection: close\r\n\r\n", GOOD[:10])
        elif p == "/chunked-trunc":
            self._raw(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n", b"a\r\nabc")
        elif p == "/wrong-issuer":
            self._raw(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % len(WRONG), WRONG)
        elif p == "/html":
            body = b"<html><body>x</body></html>"
            self._raw(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % len(body), body)
        else:
            self._raw(b"HTTP/1.1 404 Not Found\r\nContent-Length: 2\r\nConnection: close\r\n\r\n", b"{}")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
'@
$ResponderPy = Join-Path $WorkRoot "responder.py"
$ResponderProc = $null
$ResponderReady = $false
if ($script:PythonExe) {
    Set-Content -Path $ResponderPy -Value $ResponderCode -Encoding ASCII
    try {
        $ResponderProc = Start-Process -FilePath $script:PythonExe -ArgumentList @($ResponderPy, "$ResponderPort") -NoNewWindow -PassThru -RedirectStandardOutput (Join-Path $WorkRoot "responder.out") -RedirectStandardError (Join-Path $WorkRoot "responder.err")
        for ($i = 0; $i -lt 60 -and -not $ResponderReady; $i++) {
            Start-Sleep -Milliseconds 500
            if (Test-TcpConnect $ResponderPort) { $ResponderReady = $true }
        }
    } catch {
        Write-Host "responder start failed: $_" -ForegroundColor Yellow
        $ResponderProc = $null
        $ResponderReady = $false
    }
}
if ($ResponderReady) {
    Write-Host "responder: listening on 127.0.0.1:$ResponderPort (pid $($ResponderProc.Id))"
} else {
    Write-Host "responder: NOT RUN (no Python 3, or the responder did not answer on 127.0.0.1:$ResponderPort) — E discovery cases will be NOT RUN" -ForegroundColor Yellow
}

# --- cases: A (static accounting) --------------------------------------------
# PS-A1: default, no static checker at all -> rc 1, 0/0/4, ENVIRONMENT NOT READY.
Reset-Tree $Tree
Reset-StubLog
$r = Invoke-Hc @() $EmptyBin (New-BaseEnv $TestPorts $GoodDiscoveryUrl) (Out-FileFor "a1")
Add-CaseResult "PS-A1" "default no-static -> nonzero ENVIRONMENT NOT READY" `
    (($r.Rc -eq 1) -and ($r.Pass -eq 0) -and ($r.Fail -eq 0) -and ($r.NotRun -eq 4) -and ($r.Out -match "ENVIRONMENT NOT READY") -and ($r.Out -match "docker compose config")) `
    "rc=$($r.Rc) counts=$($r.Pass)/$($r.Fail)/$($r.NotRun)"

# PS-A2: default, static PASS via Python+PyYAML -> rc 0, 1/0/3, Docker NOT RUN loud.
if ($script:PythonHasYaml) {
    Reset-Tree $Tree
    Reset-StubLog
    $r = Invoke-Hc @() $PythonOnlyPath (New-BaseEnv $TestPorts $GoodDiscoveryUrl) (Out-FileFor "a2")
    $stub = Get-StubText
    Add-CaseResult "PS-A2" "default static-PASS via Python -> rc 0, Docker NOT RUN loud" `
        (($r.Rc -eq 0) -and ($r.Pass -eq 1) -and ($r.Fail -eq 0) -and ($r.NotRun -eq 3) -and ($r.Out -match "PASS: static:") -and ($r.Out -match "Docker probe NOT RUN") -and ($stub -eq "")) `
        "rc=$($r.Rc) counts=$($r.Pass)/$($r.Fail)/$($r.NotRun)"
} else {
    Add-CaseNotRun "PS-A2" "default static-PASS via Python" "no Python 3 with PyYAML on PATH"
}

# PS-A2b: default, static PASS via `docker compose config` (no Python) -> rc 0, 1/0/3.
Reset-Tree $Tree
Reset-StubLog
$r = Invoke-Hc @() $StubOnlyPath (New-BaseEnv $TestPorts $GoodDiscoveryUrl) (Out-FileFor "a2b")
$stub = Get-StubText
Add-CaseResult "PS-A2b" "default static-PASS via docker compose config -> rc 0" `
    (($r.Rc -eq 0) -and ($r.Pass -eq 1) -and ($r.Fail -eq 0) -and ($r.NotRun -eq 3) -and ($r.Out -match "static: docker compose config") -and ((Count-Needle $stub "compose config") -ge 1) -and ((Count-Needle $stub " up ") -eq 0) -and ((Count-Needle $stub " down ") -eq 0)) `
    "rc=$($r.Rc) counts=$($r.Pass)/$($r.Fail)/$($r.NotRun) stub=[$stub]"

# PS-A3: default, static PASS via Python, daemon missing -> rc 0 (default never needs the daemon).
if ($script:PythonHasYaml) {
    Reset-Tree $Tree
    Reset-StubLog
    $env1 = New-BaseEnv $TestPorts $GoodDiscoveryUrl
    $env1["STUB_DAEMON_MODE"] = "missing"
    $r = Invoke-Hc @() $StubPath $env1 (Out-FileFor "a3")
    $stub = Get-StubText
    Add-CaseResult "PS-A3" "default static-PASS via Python, daemon missing -> rc 0" `
        (($r.Rc -eq 0) -and ($r.Pass -eq 1) -and ($r.Fail -eq 0) -and ($r.NotRun -eq 3) -and ((Count-Needle $stub "compose config") -eq 0) -and ((Count-Needle $stub " up ") -eq 0) -and ((Count-Needle $stub " down ") -eq 0)) `
        "rc=$($r.Rc) counts=$($r.Pass)/$($r.Fail)/$($r.NotRun) stub=[$stub]"
} else {
    Add-CaseNotRun "PS-A3" "default static-PASS via Python, daemon missing" "no Python 3 with PyYAML on PATH"
}

# --- cases: B (daemon preflight) ---------------------------------------------
# PS-B1: -WithDocker, Docker CLI missing -> rc 1, CLI named, zero up/down/reset.
Reset-Tree $Tree
Reset-StubLog
$r = Invoke-Hc @("-WithDocker") $PythonOnlyPath (New-BaseEnv $TestPorts $GoodDiscoveryUrl) (Out-FileFor "b1")
$stub = Get-StubText
Add-CaseResult "PS-B1" "-WithDocker CLI missing -> rc 1, CLI named, zero up/down/reset" `
    (($r.Rc -eq 1) -and ($r.Pass -eq 1) -and ($r.Fail -eq 0) -and ($r.NotRun -eq 3) -and ($r.Out -match "Docker CLI unavailable") -and ($r.Out -notmatch "PASS: Keycloak") -and ($stub -eq "")) `
    "rc=$($r.Rc) counts=$($r.Pass)/$($r.Fail)/$($r.NotRun)"

# PS-B2: -WithDocker, Compose plugin missing -> rc 1, Compose named, config never ran.
Reset-Tree $Tree
Reset-StubLog
$env2 = New-BaseEnv $TestPorts $GoodDiscoveryUrl
$env2["STUB_COMPOSE_MODE"] = "fail"
$r = Invoke-Hc @("-WithDocker") $StubPath $env2 (Out-FileFor "b2")
$stub = Get-StubText
Add-CaseResult "PS-B2" "-WithDocker Compose missing -> rc 1, Compose named, no config/up/down" `
    (($r.Rc -eq 1) -and ($r.Pass -eq 1) -and ($r.Fail -eq 0) -and ($r.NotRun -eq 3) -and ($r.Out -match "Docker Compose plugin unavailable") -and ((Count-Needle $stub "compose version") -eq 1) -and ((Count-Needle $stub "docker info") -eq 0) -and ((Count-Needle $stub "compose config") -eq 0) -and ((Count-Needle $stub " up ") -eq 0) -and ((Count-Needle $stub " down ") -eq 0)) `
    "rc=$($r.Rc) counts=$($r.Pass)/$($r.Fail)/$($r.NotRun) stub=[$stub]"

# PS-B3: -WithDocker, daemon missing -> rc 1, daemon named, version+info only.
Reset-Tree $Tree
Reset-StubLog
$env3 = New-BaseEnv $TestPorts $GoodDiscoveryUrl
$env3["STUB_DAEMON_MODE"] = "missing"
$r = Invoke-Hc @("-WithDocker") $StubPath $env3 (Out-FileFor "b3")
$stub = Get-StubText
Add-CaseResult "PS-B3" "-WithDocker daemon missing -> rc 1, daemon named, no config/up/down" `
    (($r.Rc -eq 1) -and ($r.Pass -eq 1) -and ($r.Fail -eq 0) -and ($r.NotRun -eq 3) -and ($r.Out -match "Docker daemon inaccessible") -and ($r.Out -notmatch "PASS: Keycloak") -and ((Count-Needle $stub "compose version") -eq 1) -and ((Count-Needle $stub "docker info") -eq 1) -and ((Count-Needle $stub "compose config") -eq 0) -and ((Count-Needle $stub " up ") -eq 0) -and ((Count-Needle $stub " down ") -eq 0)) `
    "rc=$($r.Rc) counts=$($r.Pass)/$($r.Fail)/$($r.NotRun) stub=[$stub]"

# PS-B3b: -AgainstRunningProject, daemon missing -> rc 1, daemon named, no config/up/down.
Reset-Tree $Tree
Reset-StubLog
$env3b = New-BaseEnv $TestPorts $GoodDiscoveryUrl
$env3b["STUB_DAEMON_MODE"] = "missing"
$r = Invoke-Hc @("-AgainstRunningProject") $StubPath $env3b (Out-FileFor "b3b")
$stub = Get-StubText
Add-CaseResult "PS-B3b" "-AgainstRunningProject daemon missing -> rc 1, daemon named, no config/up/down" `
    (($r.Rc -eq 1) -and ($r.Pass -eq 1) -and ($r.Fail -eq 0) -and ($r.NotRun -eq 3) -and ($r.Out -match "Docker daemon inaccessible") -and ((Count-Needle $stub "docker info") -eq 1) -and ((Count-Needle $stub "compose config") -eq 0) -and ((Count-Needle $stub " up ") -eq 0) -and ((Count-Needle $stub " down ") -eq 0)) `
    "rc=$($r.Rc) counts=$($r.Pass)/$($r.Fail)/$($r.NotRun) stub=[$stub]"

# PS-B4: -AgainstRunningProject, Docker CLI missing -> rc 1, CLI named.
Reset-Tree $Tree
Reset-StubLog
$r = Invoke-Hc @("-AgainstRunningProject") $PythonOnlyPath (New-BaseEnv $TestPorts $GoodDiscoveryUrl) (Out-FileFor "b4")
$stub = Get-StubText
Add-CaseResult "PS-B4" "-AgainstRunningProject CLI missing -> rc 1, CLI named, zero up/down/reset" `
    (($r.Rc -eq 1) -and ($r.Pass -eq 1) -and ($r.Fail -eq 0) -and ($r.NotRun -eq 3) -and ($r.Out -match "Docker CLI unavailable") -and ($stub -eq "")) `
    "rc=$($r.Rc) counts=$($r.Pass)/$($r.Fail)/$($r.NotRun)"

# --- cases: C (full fake success) --------------------------------------------
# PS-C1: -WithDocker, full fake success, run twice -> rc 0, 8/0/0 each, unique
# disposable projects, exactly one scoped `down -v` and one `up` per run.
$C1Projects = @()
$C1Ok = $true
$C1Detail = ""
for ($run = 1; $run -le 2; $run++) {
    Reset-Tree $Tree
    Reset-StubLog
    $r = Invoke-Hc @("-WithDocker") $StubPath (New-BaseEnv $TestPorts $GoodDiscoveryUrl) (Out-FileFor ("c1-" + $run))
    $stub = Get-StubText
    $proj = Get-ProjectId $stub
    $C1Projects += $proj
    $downN = Count-Needle $stub " down -v"
    $upN = Count-Needle $stub " up --build -d"
    $scopedDown = 0
    if ($proj -ne "") { $scopedDown = Count-Needle $stub ("compose -p " + $proj + " down -v") }
    $okRun = ($r.Rc -eq 0) -and ($r.Pass -eq 8) -and ($r.Fail -eq 0) -and ($r.NotRun -eq 0) -and ($proj -ne "") -and ($downN -eq 1) -and ($scopedDown -eq 1) -and ($upN -eq 1)
    if (-not $okRun) { $C1Ok = $false }
    $C1Detail += "run${run}: rc=$($r.Rc) counts=$($r.Pass)/$($r.Fail)/$($r.NotRun) proj=$proj down=$downN scopedDown=$scopedDown up=$upN; "
}
if (($C1Projects.Count -eq 2) -and ($C1Projects[0] -ne "") -and ($C1Projects[0] -eq $C1Projects[1])) { $C1Ok = $false }
Add-CaseResult "PS-C1" "-WithDocker full fake success x2 -> rc 0, 8/0/0, unique projects, exactly one scoped down -v" $C1Ok ($C1Detail + "projects=$($C1Projects -join ' | ')")

# PS-C2: -AgainstRunningProject, full fake success -> rc 0, 7/0/0, zero up/down.
Reset-Tree $Tree
Reset-StubLog
$r = Invoke-Hc @("-AgainstRunningProject") $StubPath (New-BaseEnv $TestPorts $GoodDiscoveryUrl) (Out-FileFor "c2")
$stub = Get-StubText
Add-CaseResult "PS-C2" "-AgainstRunningProject full fake success -> rc 0, 7/0/0, zero up/down" `
    (($r.Rc -eq 0) -and ($r.Pass -eq 7) -and ($r.Fail -eq 0) -and ($r.NotRun -eq 0) -and ($r.Out -match "read-only") -and ((Count-Needle $stub " up ") -eq 0) -and ((Count-Needle $stub " down ") -eq 0)) `
    "rc=$($r.Rc) counts=$($r.Pass)/$($r.Fail)/$($r.NotRun) stub=[$stub]"

# --- cases: D (ports, flags, stale logs) -------------------------------------
# PS-D1: fixed port occupied -> fail fast rc 1, occupant alive, zero up/down.
if ($script:PythonExe) {
    $OccupantPort = 18390
    $OccupantPorts = "18390 18301 18674"
    $OccupantProc = $null
    try {
        $OccupantProc = Start-Process -FilePath $script:PythonExe -ArgumentList @("-m", "http.server", "$OccupantPort", "--bind", "127.0.0.1") -NoNewWindow -PassThru -RedirectStandardOutput (Join-Path $WorkRoot "occupant.out") -RedirectStandardError (Join-Path $WorkRoot "occupant.err")
        $occReady = $false
        for ($i = 0; $i -lt 40 -and -not $occReady; $i++) {
            Start-Sleep -Milliseconds 500
            if (Test-TcpConnect $OccupantPort) { $occReady = $true }
        }
        if (-not $occReady) {
            Add-CaseNotRun "PS-D1" "ports occupied -> fail fast, occupant alive" "occupant listener on 127.0.0.1:$OccupantPort did not answer in 20s"
        } else {
            Reset-Tree $Tree
            Reset-StubLog
            $r = Invoke-Hc @("-WithDocker") $StubPath (New-BaseEnv $OccupantPorts $GoodDiscoveryUrl) (Out-FileFor "d1")
            $stub = Get-StubText
            $aliveAfter = Test-TcpConnect $OccupantPort
            Add-CaseResult "PS-D1" "ports occupied -> fail fast rc 1, occupant alive, zero up/down" `
                (($r.Rc -eq 1) -and ($r.Out -match "occupied") -and ($r.Out -match "docker compose down") -and ($r.Out -match "AgainstRunningProject") -and $aliveAfter -and ((Count-Needle $stub " up ") -eq 0) -and ((Count-Needle $stub " down ") -eq 0)) `
                "rc=$($r.Rc) counts=$($r.Pass)/$($r.Fail)/$($r.NotRun) occupant_alive=$aliveAfter stub=[$stub]"
        }
    } catch {
        Add-CaseNotRun "PS-D1" "ports occupied -> fail fast, occupant alive" "occupant start failed: $_"
    } finally {
        if ($OccupantProc -ne $null) {
            Stop-Process -Id $OccupantProc.Id -Force -ErrorAction SilentlyContinue
        }
    }
} else {
    Add-CaseNotRun "PS-D1" "ports occupied -> fail fast, occupant alive" "no Python 3 for the occupant listener"
}

# PS-D2: flag conflict -> rc 2; unknown argument -> rc 2; -Help -> rc 0.
Reset-Tree $Tree
Reset-StubLog
$r = Invoke-Hc @("-WithDocker", "-AgainstRunningProject") $StubPath (New-BaseEnv $TestPorts $GoodDiscoveryUrl) (Out-FileFor "d2-conflict")
Add-CaseResult "PS-D2a" "flag conflict -> rc 2" (($r.Rc -eq 2) -and ($r.Out -match "mutually exclusive")) "rc=$($r.Rc)"
$r = Invoke-Hc @("-BogusFlag") $StubPath (New-BaseEnv $TestPorts $GoodDiscoveryUrl) (Out-FileFor "d2-bogus")
Add-CaseResult "PS-D2b" "unknown argument -> rc 2" (($r.Rc -eq 2) -and ($r.Out -match "unknown argument")) "rc=$($r.Rc)"
$r = Invoke-Hc @("-Help") $StubPath (New-BaseEnv $TestPorts $GoodDiscoveryUrl) (Out-FileFor "d2-help")
Add-CaseResult "PS-D2c" "-Help -> rc 0" ($r.Rc -eq 0) "rc=$($r.Rc)"

# PS-D3a: stale probe artifacts + failing exec probe -> rc 1, no phantom PASS;
# the stale exec log is overwritten and the stale discovery log is cleared.
Reset-Tree $Tree
Reset-StubLog
$trDir = Join-Path $Tree "test-results"
New-Item -ItemType Directory -Force -Path $trDir | Out-Null
Set-Content -Path (Join-Path $trDir "compose-healthcheck-exec.log") "STALE-SUCCESS-MARKER in-container probe passed"
Set-Content -Path (Join-Path $trDir "compose-healthcheck-discovery.log") "STALE-SUCCESS-MARKER discovery ok"
Set-Content -Path (Join-Path $trDir "compose-healthcheck-kc-health.json") '{"Status":"healthy"} STALE-SUCCESS-MARKER'
Set-Content -Path (Join-Path $trDir "compose-healthcheck-config.out") "STALE-SUCCESS-MARKER resolved config"
$envD3a = New-BaseEnv $TestPorts $GoodDiscoveryUrl
$envD3a["STUB_EXEC_MODE"] = "fail"
$r = Invoke-Hc @("-AgainstRunningProject") $StubPath $envD3a (Out-FileFor "d3a")
$execLog = ""
if (Test-Path (Join-Path $trDir "compose-healthcheck-exec.log")) { $execLog = Get-Content (Join-Path $trDir "compose-healthcheck-exec.log") -Raw -ErrorAction SilentlyContinue }
if ($execLog -eq $null) { $execLog = "" }
$kcHealth = ""
if (Test-Path (Join-Path $trDir "compose-healthcheck-kc-health.json")) { $kcHealth = Get-Content (Join-Path $trDir "compose-healthcheck-kc-health.json") -Raw -ErrorAction SilentlyContinue }
if ($kcHealth -eq $null) { $kcHealth = "" }
$configOut = ""
if (Test-Path (Join-Path $trDir "compose-healthcheck-config.out")) { $configOut = Get-Content (Join-Path $trDir "compose-healthcheck-config.out") -Raw -ErrorAction SilentlyContinue }
if ($configOut -eq $null) { $configOut = "" }
Add-CaseResult "PS-D3a" "stale logs + failing probe -> rc 1, stale markers gone, no phantom probe PASS" `
    (($r.Rc -eq 1) -and ($r.Fail -ge 1) -and ($r.Out -match "FAIL: read-only: in-container probe failed") -and ($r.Out -notmatch "PASS: read-only: in-container probe") -and ($execLog -notmatch "STALE-SUCCESS-MARKER") -and ($kcHealth -notmatch "STALE-SUCCESS-MARKER") -and ($configOut -notmatch "STALE-SUCCESS-MARKER") -and (-not (Test-Path (Join-Path $trDir "compose-healthcheck-discovery.log")))) `
    "rc=$($r.Rc) counts=$($r.Pass)/$($r.Fail)/$($r.NotRun) execLog=[$execLog]"

# PS-D3b: stale config.out + failing `docker compose config` -> rc 1, stale marker gone.
Reset-Tree $Tree
Reset-StubLog
$trDir = Join-Path $Tree "test-results"
New-Item -ItemType Directory -Force -Path $trDir | Out-Null
Set-Content -Path (Join-Path $trDir "compose-healthcheck-config.out") "STALE-SUCCESS-MARKER resolved config"
$envD3b = New-BaseEnv $TestPorts $GoodDiscoveryUrl
$envD3b["STUB_CONFIG_MODE"] = "fail"
$r = Invoke-Hc @("-WithDocker") $StubPath $envD3b (Out-FileFor "d3b")
$configOut = ""
if (Test-Path (Join-Path $trDir "compose-healthcheck-config.out")) { $configOut = Get-Content (Join-Path $trDir "compose-healthcheck-config.out") -Raw -ErrorAction SilentlyContinue }
if ($configOut -eq $null) { $configOut = "" }
Add-CaseResult "PS-D3b" "stale config.out + failing compose config -> rc 1, stale marker gone" `
    (($r.Rc -eq 1) -and ($r.Out -match "FAIL: docker compose config failed") -and ($configOut -notmatch "STALE-SUCCESS-MARKER")) `
    "rc=$($r.Rc) counts=$($r.Pass)/$($r.Fail)/$($r.NotRun) configOut=[$configOut]"

# --- cases: E (Test-PortFree / Test-Discovery smoke) -------------------------
# PS-E0: the exact TcpClient InterNetwork constructor form used by the script
# connects to a listener and is refused on a free port (pwsh 7.4.6 here;
# Windows PowerShell 5.1 is NOT RUN — Windows-only, see the report).
if ($ResponderReady) {
    $connectsToListener = Test-TcpConnect $ResponderPort
    $refusedOnFreePort = -not (Test-TcpConnect 18999)
    Add-CaseResult "PS-E0" "TcpClient InterNetwork overload: listener connects, free port refused" `
        ($connectsToListener -and $refusedOnFreePort) `
        "listener_127.0.0.1:${ResponderPort}=$connectsToListener free_127.0.0.1:18999_refused=$refusedOnFreePort"
} else {
    Add-CaseNotRun "PS-E0" "TcpClient InterNetwork overload probe" "responder not running (no Python 3)"
}

# PS-E1..E8: Test-Discovery through the REAL script (read-only mode) against
# the synthetic responder. Good/chunked-good -> rc 0, 7/0/0; every bad
# framing/status/issuer -> rc 1, 6/1/0, with the precise reason.
$DiscoveryCases = @(
    @{ Id = "PS-E1"; Path = "good";         WantRc = 0; WantCounts = "7/0/0"; Reason = "discovered issuer is exactly the canonical issuer" },
    @{ Id = "PS-E2"; Path = "chunked-good"; WantRc = 0; WantCounts = "7/0/0"; Reason = "discovered issuer is exactly the canonical issuer" },
    @{ Id = "PS-E3"; Path = "redirect";     WantRc = 1; WantCounts = "6/1/0"; Reason = "redirect (HTTP 302" },
    @{ Id = "PS-E4"; Path = "s401";         WantRc = 1; WantCounts = "6/1/0"; Reason = "HTTP status 401" },
    @{ Id = "PS-E5"; Path = "badjson";      WantRc = 1; WantCounts = "6/1/0"; Reason = "not valid JSON" },
    @{ Id = "PS-E6"; Path = "truncated";    WantRc = 1; WantCounts = "6/1/0"; Reason = "truncated response" },
    @{ Id = "PS-E7"; Path = "chunked-trunc"; WantRc = 1; WantCounts = "6/1/0"; Reason = "truncated chunked body" },
    @{ Id = "PS-E8"; Path = "wrong-issuer"; WantRc = 1; WantCounts = "6/1/0"; Reason = "issuer mismatch" }
)
foreach ($dc in $DiscoveryCases) {
    if (-not $ResponderReady) {
        Add-CaseNotRun $dc.Id "discovery /$($dc.Path) -> rc $($dc.WantRc)" "responder not running (no Python 3)"
        continue
    }
    Reset-Tree $Tree
    Reset-StubLog
    $url = "http://127.0.0.1:$ResponderPort/$($dc.Path)"
    $r = Invoke-Hc @("-AgainstRunningProject") $StubPath (New-BaseEnv $TestPorts $url) (Out-FileFor ("e-" + $dc.Path))
    $counts = "$($r.Pass)/$($r.Fail)/$($r.NotRun)"
    Add-CaseResult $dc.Id "discovery /$($dc.Path) -> rc $($dc.WantRc), $($dc.WantCounts)" `
        (($r.Rc -eq $dc.WantRc) -and ($counts -eq $dc.WantCounts) -and ($r.Out -match [regex]::Escape($dc.Reason))) `
        "rc=$($r.Rc) counts=$counts reason_expected=[$($dc.Reason)]"
}

# --- summary + cleanup --------------------------------------------------------
Write-Host ""
Write-Host "ps-matrix: $($script:CasePass) passed, $($script:CaseFail) failed, $($script:CaseNotRun) not run"
if ($script:CaseFail -gt 0) {
    foreach ($f in $script:Failures) { Write-Host "  FAILED: $f" -ForegroundColor Red }
}
if ($ResponderProc -ne $null) {
    Stop-Process -Id $ResponderProc.Id -Force -ErrorAction SilentlyContinue
}
Remove-Item -Recurse -Force $WorkRoot -ErrorAction SilentlyContinue
if ($script:CaseFail -gt 0) { exit 1 } else { exit 0 }
