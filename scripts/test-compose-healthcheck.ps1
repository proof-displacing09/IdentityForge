#!/usr/bin/env pwsh
# IdentityForge Compose healthcheck — native PowerShell wrapper
# (Trustline v7.3, IF-V7.2-04).
#
# The native Windows equivalent of scripts/test-compose-healthcheck.sh.
# It needs Docker Desktop only — no host Bash, no Git Bash, no host
# Python, no host Node, and no WSL distribution beyond the WSL 2
# backend Docker Desktop manages itself. (A Ubuntu user distro is
# NOT required; do not reinstall one for this script.)
#
# Two parts, mirroring the .sh script:
#   1. STATIC (always runs when its prerequisite exists): EITHER the
#      YAML-only check scripts/compose-config-check.py (when a
#      python3 with PyYAML is available on the host) OR the
#      authoritative RESOLVED check via `docker compose config`
#      (when Docker is available). Both prove the Keycloak
#      healthcheck still contains the literal '$resp' references
#      (2x) and 'resp=$(cat <&3)' after Compose interpolation
#      (IF-V4-01). When neither prerequisite exists, the static part
#      is reported NOT RUN (never PASS) with the exact reason.
#   2. DOCKER-PROBED (needs Docker): inspects the RESOLVED command
#      via `docker compose config`, then EITHER boots a disposable
#      cold-start project and checks the final health state plus the
#      discovered issuer (-WithDocker), OR read-only inspects an
#      EXISTING stack without creating or deleting anything
#      (-AgainstRunningProject). Without Docker, an explicitly
#      requested Docker mode is reported NOT RUN and exits NONZERO
#      (IF-V7.2-01 exit contract); without a mode flag the Docker
#      part is NOT RUN and the script still exits 0 (the static
#      regression is the gate that runs everywhere).
#
# IF-V7.1-02 (v7.2): the log directory (test-results/) is created
# BEFORE the first redirection into it. IF-V7.1-03: the discovery
# document is fetched with a real HTTP client over a forced-IPv4 raw
# socket (never follows redirects; parses Content-Length and chunked
# framing correctly) and must answer HTTP 200 with a valid JSON
# object whose issuer is exactly the canonical issuer. A raw socket
# on purpose: HttpClient honours the machine's proxy settings and
# its default dual-mode socket can be diverted to a proxy instead
# of the loopback endpoint, so it cannot prove anything about a
# loopback URL. IF-V7.1-04: -WithDocker boots a DISPOSABLE project with a
# unique name, only after a preflight proves the fixed host ports
# (127.0.0.1:8080/8000/5173) are free. If a port is occupied the
# script FAILS FAST — before any `docker compose up` — and prints
# the stop/test/restart sequence; it never touches the occupant,
# never kills anything, and never runs `down -v` against anything
# but its own disposable project (cleanup is scoped to -p $Project
# in a finally block). -AgainstRunningProject is the read-only
# alternative: it inspects the existing stack (resolved config,
# container health, in-image probe, host discovery) and
# creates/deletes nothing — no up, no down, no reset, no volumes.
#
# Health 200 alone is NOT successful OAuth login proof: this script
# proves container health, the in-image probe, and the canonical
# issuer. A successful student + officer login and the authorization
# policy checks are separate proofs — run them with
# .\scripts\test-all.ps1 -Full -Strict (which also runs the real
# Keycloak login gates) or follow docs/REVIEWER_GUIDE.md §2/§5.
#
# Usage (from the extracted release folder):
#   .\scripts\test-compose-healthcheck.ps1 [-WithDocker | -AgainstRunningProject]
# Exit 0 only when the static part EXECUTED and passed AND (when a Docker mode was
# given) the Docker probe passes. Default mode with NO static checker available
# (no Python+PyYAML and no `docker compose config`) exits 1 with ENVIRONMENT NOT
# READY — a default run that performed zero static checks must never exit 0
# (IF-V7.3.1-A). Without a Docker mode the Docker part is NOT RUN and the script
# still exits 0 when the static part passed; the NOT RUN banner names the missing
# probe explicitly. An explicitly requested Docker mode with no Docker CLI, no
# Compose plugin, or an unreachable daemon exits 1 (IF-V7.3.1-B: `docker info` is
# checked separately — `docker compose version` never contacts the daemon).
# Usage errors (mutually exclusive flags, unknown arguments) exit 2.
#
# Logs: test-results\compose-healthcheck-*. All paths are built with
# Join-Path, so the script works from a checkout path containing
# spaces. Nothing is written outside test-results/.
#
# PowerShell 5.1-compatible syntax (no ??, no ternary, no
# ForEach-Object -Parallel). Tested on PowerShell 7.4.6 on Linux
# with a stub `docker` (see docs/VERIFICATION_LOG.md, v7.3);
# Windows PowerShell 5.1 execution remains a reviewer gate.
# IF-V7.3.1-A/B: explicit profile/state accounting for the static proof and
# a daemon-specific Docker preflight (parity with
# scripts/test-compose-healthcheck.sh IF-V7.2-01 gates 1-3).
[CmdletBinding()]
param(
    [switch]$WithDocker,
    [switch]$AgainstRunningProject,
    [switch]$Help,
    [Parameter(ValueFromRemainingArguments=$true)][string[]]$RemainingArgs
)

$ErrorActionPreference = "Stop"

if ($Help) {
    Write-Host "Usage: .\scripts\test-compose-healthcheck.ps1 [-WithDocker | -AgainstRunningProject]"
    Write-Host "  (default) static check only; Docker probe NOT RUN"
    Write-Host "  -WithDocker              disposable cold-start probe (needs Docker + ~2 min;"
    Write-Host "                           fails fast if the fixed ports 8080/8000/5173 are busy)"
    Write-Host "  -AgainstRunningProject   read-only inspection of an EXISTING stack;"
    Write-Host "                           creates/deletes nothing (no up, no down, no volumes)"
    exit 0
}
if ($WithDocker -and $AgainstRunningProject) {
    Write-Host "test-compose-healthcheck.ps1: -WithDocker and -AgainstRunningProject are mutually exclusive" -ForegroundColor Red
    exit 2
}
if ($RemainingArgs -and $RemainingArgs.Count -gt 0) {
    Write-Host "test-compose-healthcheck.ps1: unknown argument(s): $($RemainingArgs -join ' ')" -ForegroundColor Red
    Write-Host "Usage: .\scripts\test-compose-healthcheck.ps1 [-WithDocker | -AgainstRunningProject]"
    exit 2
}

$ScriptRoot = $PSScriptRoot
if ([string]::IsNullOrEmpty($ScriptRoot)) { $ScriptRoot = (Get-Location).Path }
$Root = Split-Path -Parent $ScriptRoot
$LogDir = Join-Path $Root "test-results"
try {
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
} catch {
    Write-Host "FAIL: cannot create log directory $LogDir (check permissions / disk): $_" -ForegroundColor Red
    exit 1
}

$script:Pass = 0
$script:Fail = 0
$script:NotRun = 0
# IF-V7.3.1-A: explicit static-proof accounting. $script:StaticExecuted is
# $true only when a static check actually RAN (Python+PyYAML checker, or
# `docker compose config`); $script:StaticPassed only when it PASSED. A
# default run with no static checker executed must exit NONZERO — the old
# code recorded zero static checks as NOT RUN and then exited 0 because
# $script:Fail was 0 (a false pass: "0 passed, 0 failed, 4 not run", rc 0).
$script:StaticExecuted = $false
$script:StaticPassed = $false
# IF-V7.3.1-B: Docker prerequisite state, one of cli-missing /
# compose-missing / daemon-missing / ok, with the exact reason in
# $script:DockerReason. $script:DockerOk requires CLI + Compose plugin +
# reachable daemon; $script:ComposeOk requires only CLI + Compose plugin
# (enough for the client-side `docker compose config` static check, which
# never contacts the daemon).
$script:DockerState = "unknown"
$script:DockerReason = ""
$script:ComposeOk = $false
$script:DaemonOk = $false
$script:DockerOk = $false
function Write-Ok { param([string]$Message) Write-Host "PASS: $Message"; $script:Pass++ }
function Write-Bad { param([string]$Message) Write-Host "FAIL: $Message" -ForegroundColor Red; $script:Fail++ }
function Write-NotRun { param([string]$Message) Write-Host "NOT RUN: $Message" -ForegroundColor Yellow; $script:NotRun++ }
function Write-Summary {
    param([string]$Suffix)
    Write-Host ""
    Write-Host "compose-healthcheck: $($script:Pass) passed, $($script:Fail) failed, $($script:NotRun) not run $Suffix"
}

$CanonicalIssuer = "http://127.0.0.1:8080/realms/identityforge-lab"
# Test-only overrides (regression testing only — never set these in
# normal use): IDENTITYFORGE_HCPROBE_TEST_PORTS="18080 18000 15173"
# lets a stub suite exercise the free-ports path while a developer
# live stack holds the real fixed ports, and
# IDENTITYFORGE_HCPROBE_DISCOVERY_URL lets it point the host-side
# discovery check at a local stub server instead of the live
# Keycloak. The shipped defaults are always the fixed lab ports and
# the canonical discovery URL, and the validation (HTTP 200 + valid
# JSON + exact issuer) is identical either way — these overrides
# change WHERE the check looks, never WHAT it accepts.
$CheckPorts = @(8080, 8000, 5173)
if ($env:IDENTITYFORGE_HCPROBE_TEST_PORTS) {
    $CheckPorts = @($env:IDENTITYFORGE_HCPROBE_TEST_PORTS -split '\s+' | Where-Object { $_ -ne "" } | ForEach-Object { [int]$_ })
}
$DiscoveryUrl = $CanonicalIssuer + "/.well-known/openid-configuration"
if ($env:IDENTITYFORGE_HCPROBE_DISCOVERY_URL) { $DiscoveryUrl = $env:IDENTITYFORGE_HCPROBE_DISCOVERY_URL }

# Find a host python3 (python3, then python) that has PyYAML — the
# YAML-only static check needs it. A missing PyYAML is NOT a
# failure here: the resolved `docker compose config` check below is
# the authoritative equivalent when Docker is available.
function Get-PythonWithYaml {
    foreach ($name in @("python3", "python")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        $exe = $cmd.Source
        & $exe -c "import yaml" > $null 2> $null
        if ($LASTEXITCODE -eq 0) { return $exe }
    }
    return $null
}

function Test-PortFree {
    param([int]$Port)
    # Force an IPv4 socket (AddressFamily.InterNetwork): the default
    # TcpClient() is a dual-mode IPv6 socket, and an IPv6-mapped
    # loopback connect can be diverted by a middlebox/proxy instead
    # of testing the port (measured in the build sandbox: the
    # default socket "connected" to the egress proxy on port 3128
    # with nothing listening on the probed port, while the IPv4
    # socket is correctly refused when free and connects when a
    # real listener is present). The lab ports are IPv4 127.0.0.1.
    $client = New-Object System.Net.Sockets.TcpClient([System.Net.Sockets.AddressFamily]::InterNetwork)
    try {
        $client.Connect("127.0.0.1", $Port)
        $client.Close()
        return $false
    } catch {
        return $true
    } finally {
        if ($client) { $client.Dispose() }
    }
}

# Container health via `docker inspect` (pure JSON — ConvertFrom-Json
# is correct here; the v7.1 bug was feeding raw HTTP bytes to a JSON
# parser, which never happens in this script anymore).
function Get-ContainerHealth {
    param([string]$ContainerId)
    if ([string]::IsNullOrEmpty($ContainerId)) { return "unknown" }
    $errFile = Join-Path $LogDir "compose-healthcheck-inspect.err"
    $raw = & docker inspect $ContainerId --format '{{json .State.Health}}' 2> $errFile
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrEmpty("$raw")) { return "unknown" }
    try {
        $parsed = "$raw" | ConvertFrom-Json
        if ($parsed -and $parsed.Status) { return [string]$parsed.Status }
        return "unknown"
    } catch {
        return "unknown"
    }
}

# Host-side discovery (IF-V7.1-03): a real HTTP client over a
# forced-IPv4 raw socket — never follows redirects, requires HTTP
# 200 + a valid JSON object + the exact canonical issuer. It is a
# raw socket on purpose: System.Net.Http.HttpClient honours the
# machine's proxy settings and, on the build sandbox, its default
# dual-mode socket is diverted to the egress proxy even with
# UseProxy=$false, so it cannot prove anything about a loopback
# endpoint. A loopback-only probe must not depend on proxy or DNS
# behaviour at all. Framing is parsed exactly like
# scripts/discovery-check.py (Content-Length and chunked both
# supported; a truncated body is a FAIL, never a partial read
# presented as a result). Returns $true on success and prints the
# one-line discovery result; on failure prints the precise reason.
function Test-Discovery {
    param([string]$Url, [string]$ExpectedIssuer)
    # The discovery URL is always the canonical loopback issuer
    # (or a test-only stub on loopback): parse host/port/path here
    # rather than trusting a URI resolver to pick an address family.
    $uri = $null
    if (-not [System.Uri]::TryCreate($Url, [System.UriKind]::Absolute, [ref]$uri)) {
        Write-Host "FAIL: discovery check failed (not a valid absolute URL: $Url)"
        return $false
    }
    if ($uri.Host -ne "127.0.0.1" -and $uri.Host -ne "localhost") {
        Write-Host "FAIL: discovery check failed (discovery URL host must be loopback, got '$($uri.Host)')"
        return $false
    }
    $port = $uri.Port
    if ($port -eq -1) { $port = 80 }
    $path = $uri.PathAndQuery
    if ([string]::IsNullOrEmpty($path)) { $path = "/" }
    $client = New-Object System.Net.Sockets.TcpClient([System.Net.Sockets.AddressFamily]::InterNetwork)
    $client.ReceiveTimeout = 15000
    $client.SendTimeout = 15000
    try {
        $client.Connect("127.0.0.1", $port)
        $stream = $client.GetStream()
        $stream.ReadTimeout = 15000
        $stream.WriteTimeout = 15000
        $request = "GET $path HTTP/1.1`r`nHost: 127.0.0.1:$port`r`nConnection: close`r`n`r`n"
        $reqBytes = [System.Text.Encoding]::ASCII.GetBytes($request)
        $stream.Write($reqBytes, 0, $reqBytes.Length)
        $stream.Flush()
        # Read until the response is complete (headers + full body
        # per Content-Length / chunked framing) or the server closes
        # the connection or the read times out.
        $buf = New-Object byte[] 8192
        $bytes = New-Object System.Collections.Generic.List[byte]
        $deadline = (Get-Date).AddSeconds(15)
        $complete = $false
        while (-not $complete -and (Get-Date) -lt $deadline) {
            try {
                $n = $stream.Read($buf, 0, $buf.Length)
            } catch {
                break
            }
            if ($n -le 0) { break }
            for ($i = 0; $i -lt $n; $i++) { $bytes.Add($buf[$i]) }
            $complete = Test-ResponseComplete $bytes.ToArray()
        }
        $raw = $bytes.ToArray()
        if ($raw.Length -eq 0) {
            Write-Host "FAIL: discovery check failed (empty response from $Url)"
            return $false
        }
        $parsed = Convert-HttpResponse $raw
        if (-not $parsed) {
            Write-Host "FAIL: discovery check failed (could not parse the HTTP response from $Url)"
            return $false
        }
        $status = $parsed.Status
        if ($status -ge 300 -and $status -lt 400) {
            $loc = $parsed.Headers["location"]
            Write-Host "FAIL: discovery check failed (redirect (HTTP $status) to $loc — redirects are never followed)"
            return $false
        }
        if ($status -ne 200) {
            Write-Host "FAIL: discovery check failed (HTTP status $status, expected 200)"
            return $false
        }
        if (-not $parsed.Complete) {
            Write-Host "FAIL: discovery check failed (truncated response: $($parsed.TruncationReason))"
            return $false
        }
        $contentType = $parsed.Headers["content-type"]
        $bodyText = [System.Text.Encoding]::UTF8.GetString($parsed.Body)
        if (($contentType -match "text/html") -or $bodyText.TrimStart().StartsWith("<html")) {
            Write-Host "FAIL: discovery check failed (HTML body, expected a JSON discovery document)"
            return $false
        }
        try {
            $doc = $bodyText | ConvertFrom-Json
        } catch {
            Write-Host "FAIL: discovery check failed (body is not valid JSON)"
            return $false
        }
        if (-not $doc.issuer) {
            Write-Host "FAIL: discovery check failed (no 'issuer' field in the discovery document)"
            return $false
        }
        if ([string]$doc.issuer -ne $ExpectedIssuer) {
            Write-Host "FAIL: discovery check failed (issuer mismatch: got '$($doc.issuer)', expected '$ExpectedIssuer')"
            return $false
        }
        Write-Host "discovery: OK issuer=$ExpectedIssuer"
        return $true
    } catch {
        Write-Host "FAIL: discovery check failed ($($_.Exception.Message))"
        return $false
    } finally {
        if ($client) { $client.Dispose() }
    }
}

# Convert-HttpResponse [byte[]] -> hashtable (or $null when the
# head cannot be parsed): Status, Headers (lower-cased keys),
# Body [byte[]], Complete, TruncationReason. Handles Content-Length
# and Transfer-Encoding: chunked exactly like
# scripts/discovery-check.py; a body that ends early is Complete=$false.
function Convert-HttpResponse {
    param([byte[]]$Raw)
    $text = [System.Text.Encoding]::ASCII.GetString($Raw)
    $headEnd = $text.IndexOf("`r`n`r`n")
    if ($headEnd -lt 0) { return $null }
    $head = $text.Substring(0, $headEnd)
    $headLines = $head -split "`r`n"
    $statusLine = $headLines[0]
    $m = [regex]::Match($statusLine, '^HTTP/1\.[01]\s+(\d{3})')
    if (-not $m.Success) { return $null }
    $status = [int]$m.Groups[1].Value
    $headers = @{}
    for ($i = 1; $i -lt $headLines.Count; $i++) {
        $colon = $headLines[$i].IndexOf(":")
        if ($colon -gt 0) {
            $headers[$headLines[$i].Substring(0, $colon).Trim().ToLower()] = $headLines[$i].Substring($colon + 1).Trim()
        }
    }
    $bodyStart = $headEnd + 4
    $bodyLen = $Raw.Length - $bodyStart
    if ($bodyLen -lt 0) { $bodyLen = 0 }
    $bodyRaw = New-Object byte[] $bodyLen
    if ($bodyLen -gt 0) { [Array]::Copy($Raw, $bodyStart, $bodyRaw, 0, $bodyLen) }
    $complete = $true
    $reason = ""
    $body = $bodyRaw
    if ($headers["transfer-encoding"] -match "chunked") {
        $decoded = New-Object System.Collections.Generic.List[byte]
        $pos = 0
        $done = $false
        while ($pos -lt $bodyRaw.Length) {
            $lineEnd = -1
            for ($j = $pos; $j -lt $bodyRaw.Length - 1; $j++) {
                if ($bodyRaw[$j] -eq 13 -and $bodyRaw[$j + 1] -eq 10) { $lineEnd = $j; break }
            }
            if ($lineEnd -lt 0) { break }
            $sizeText = [System.Text.Encoding]::ASCII.GetString($bodyRaw, $pos, $lineEnd - $pos).Trim()
            $size = 0
            if (-not [int]::TryParse($sizeText, [System.Globalization.NumberStyles]::HexNumber, $null, [ref]$size)) {
                $complete = $false; $reason = "malformed chunk size '$sizeText'"; break
            }
            if ($size -eq 0) { $done = $true; break }
            $chunkStart = $lineEnd + 2
            if ($chunkStart + $size -gt $bodyRaw.Length) {
                $complete = $false; $reason = "truncated chunked body"; break
            }
            for ($k = 0; $k -lt $size; $k++) { $decoded.Add($bodyRaw[$chunkStart + $k]) }
            $pos = $chunkStart + $size + 2
        }
        if ($complete -and -not $done) { $complete = $false; $reason = "truncated chunked body" }
        $body = $decoded.ToArray()
    } elseif ($headers["content-length"]) {
        $want = 0
        if (-not [int]::TryParse($headers["content-length"], [ref]$want)) {
            $complete = $false; $reason = "malformed Content-Length '$($headers['content-length'])'"
        } elseif ($bodyRaw.Length -lt $want) {
            $complete = $false; $reason = "truncated response (Content-Length $want, received $($bodyRaw.Length) bytes)"
        } else {
            $body = New-Object byte[] $want
            [Array]::Copy($bodyRaw, 0, $body, 0, $want)
        }
    }
    return @{ Status = $status; Headers = $headers; Body = $body; Complete = $complete; TruncationReason = $reason }
}

# Test-ResponseComplete [byte[]] -> $true when the accumulated bytes
# hold a complete HTTP response (headers + full body per framing),
# so the read loop can stop without waiting for the server to close.
function Test-ResponseComplete {
    param([byte[]]$Raw)
    $parsed = Convert-HttpResponse $Raw
    if (-not $parsed) { return $false }
    return $parsed.Complete
}

# The in-image probe command: the exact healthcheck `test:` value
# from docker-compose.yml (Keycloak service), run inside the
# container. It requires bash + /dev/tcp + grep inside the pinned
# keycloak:26.8.2 image, and BOTH an HTTP 200 status line AND the
# "issuer" field in the discovery body. Single-quoted here so
# PowerShell passes the dollars through untouched; the embedded
# single quotes are doubled (PowerShell '' escape).
$InImageProbe = 'exec 3<>/dev/tcp/127.0.0.1/8080 && printf ''GET /realms/identityforge-lab/.well-known/openid-configuration HTTP/1.1\r\nHost: 127.0.0.1:8080\r\nConnection: close\r\n\r\n'' >&3 && resp=$(cat <&3) && echo "$resp" | grep -qE ''HTTP/1\.[01] 200'' && echo "$resp" | grep -q ''"issuer"'''

$Project = ""
$CleanupNeeded = $false

Write-Host "== IdentityForge Compose healthcheck regression (IF-V4-01) =="

Push-Location $Root
try {
    # --- 1. Static regression -------------------------------------------------
    $PythonExe = Get-PythonWithYaml
    $ConfigOut = Join-Path $LogDir "compose-healthcheck-config.out"
    $ConfigErr = Join-Path $LogDir "compose-healthcheck-config.err"
    $staticDone = $false
    $staticViaDocker = $false
    if ($PythonExe) {
        $checker = Join-Path $Root "scripts\compose-config-check.py"
        & $PythonExe $checker > $ConfigOut 2> $ConfigErr
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "static: no single-`$ trap; resolved healthcheck keeps literal '`$resp' (2x); depends_on service_healthy"
            $script:StaticPassed = $true
        } else {
            $detail = ""
            if (Test-Path $ConfigOut) { $detail = (Get-Content $ConfigOut -Raw -ErrorAction SilentlyContinue) }
            if ([string]::IsNullOrEmpty($detail) -and (Test-Path $ConfigErr)) { $detail = (Get-Content $ConfigErr -Raw -ErrorAction SilentlyContinue) }
            Write-Bad "static: compose-config-check.py failed (see above) $detail"
        }
        $staticDone = $true
        $script:StaticExecuted = $true
    }

    # --- 2. Docker availability (IF-V7.3.1-B) ---------------------------------
    # Three separate gates, so the reason is named exactly (parity with
    # scripts/test-compose-healthcheck.sh IF-V7.2-01 gates 1-3):
    #   1. `docker` CLI present at all;
    #   2. the Compose plugin (`docker compose version` — a CLI can exist
    #      with no Compose plugin);
    #   3. daemon connectivity (`docker info` — `docker compose version`
    #      does NOT contact the daemon, so a CLI can exist while Docker
    #      Desktop is not running; a missing socket must never read as a
    #      passing live probe).
    # Every native docker call below captures $LASTEXITCODE immediately;
    # no result is inferred from exception handling alone.
    $DockerCmd = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $DockerCmd) {
        $script:DockerState = "cli-missing"
        $script:DockerReason = "Docker CLI unavailable in this environment (no 'docker' binary on PATH)"
    } else {
        $versionLog = Join-Path $LogDir "compose-healthcheck-compose-version.log"
        & docker compose version > $versionLog 2>&1
        $versionRc = $LASTEXITCODE
        if ($versionRc -ne 0) {
            $script:DockerState = "compose-missing"
            $script:DockerReason = "Docker Compose plugin unavailable ('docker compose version' failed with exit $versionRc; see $versionLog)"
        } else {
            $script:ComposeOk = $true
            $infoLog = Join-Path $LogDir "compose-healthcheck-docker-info.log"
            & docker info > $infoLog 2>&1
            $infoRc = $LASTEXITCODE
            if ($infoRc -ne 0) {
                $script:DockerState = "daemon-missing"
                $script:DockerReason = "Docker daemon inaccessible ('docker info' failed with exit $infoRc — Docker Desktop may not be running; see $infoLog)"
            } else {
                $script:DaemonOk = $true
                $script:DockerState = "ok"
            }
        }
    }
    $script:DockerOk = $script:ComposeOk -and $script:DaemonOk

    # An explicitly requested Docker mode that cannot run fails HERE, before
    # any `docker compose config` (so a dead daemon never yields a resolved
    # config read as live evidence) and before any up/down/reset. Missing
    # capability stays labelled NOT RUN; it just never yields exit 0.
    if (($WithDocker -or $AgainstRunningProject) -and -not $script:DockerOk) {
        if (-not $staticDone) {
            Write-NotRun "static compose check — needs Python 3 + PyYAML (scripts/compose-config-check.py) or Docker (`docker compose config`); neither is available in this environment"
        }
        Write-NotRun "docker compose config resolved-healthcheck inspection — $($script:DockerReason)"
        Write-NotRun "live Keycloak health state + discovered issuer — $($script:DockerReason)"
        Write-NotRun "backend/frontend healthy after Keycloak healthy — $($script:DockerReason)"
        Write-Summary "(Docker prerequisite failed: $($script:DockerReason))"
        Write-Host "SOURCE FIXED; ACTUAL DOCKER HEALTHCHECK + COMPOSE BOOT NOT RUN — explicitly requested Docker probe could not run, exit 1"
        Write-Host "Docker prerequisite failed: $($script:DockerReason)"
        exit 1
    }

    # Stale per-probe artifacts are cleared BEFORE the live probe writes its
    # own, so a stale success (resolved config, healthy-state JSON,
    # discovery log, exec log) can never be mistaken for this run's
    # evidence when a later step fails or never runs. This runs only in
    # explicit modes, after the Docker preflight passed; the static step
    # below regenerates compose-healthcheck-config.out on every run that
    # reaches it.
    if ($WithDocker -or $AgainstRunningProject) {
        foreach ($stale in @($ConfigOut, $ConfigErr,
            (Join-Path $LogDir "compose-healthcheck-kc-health.json"),
            (Join-Path $LogDir "compose-healthcheck-exec-tools.log"),
            (Join-Path $LogDir "compose-healthcheck-exec.log"),
            (Join-Path $LogDir "compose-healthcheck-discovery.log"),
            (Join-Path $LogDir "compose-healthcheck-up.log"),
            (Join-Path $LogDir "compose-healthcheck-inspect.err"))) {
            Remove-Item -Force -ErrorAction SilentlyContinue $stale
        }
    }

    if (-not $staticDone) {
        if ($script:ComposeOk) {
            # Authoritative resolved check (needs Docker CLI + Compose
            # plugin, no daemon: `docker compose config` is client-side
            # and prints the config AFTER interpolation, so the
            # healthcheck must contain the literal '$resp' (not an empty
            # echo) in the resolved output. IF-V7.1-02: output goes to
            # files in the ALREADY-CREATED log dir, and the command's
            # REAL exit status is captured.
            & docker compose config > $ConfigOut 2> $ConfigErr
            $configRc = $LASTEXITCODE
            if ($configRc -ne 0) {
                Write-Bad "docker compose config failed (exit $configRc; see $ConfigErr)"
            } else {
                $resolved = ""
                if (Test-Path $ConfigOut) { $resolved = Get-Content $ConfigOut -Raw -ErrorAction SilentlyContinue }
                $respCount = ([regex]::Matches("$resolved", '\$resp')).Count
                if (("$resolved".Contains('resp=$(cat <&3)')) -and ($respCount -ge 2) -and (-not "$resolved".Contains('$$resp'))) {
                    Write-Ok "static: docker compose config: resolved healthcheck contains literal '`$resp' (2x) and resp=`$(cat <&3)"
                    $script:StaticPassed = $true
                } else {
                    Write-Bad "docker compose config: resolved healthcheck lost the '`$resp' references (Compose interpolated them away)"
                }
            }
            $staticDone = $true
            $staticViaDocker = $true
            $script:StaticExecuted = $true
        }
    }

    if (-not $staticDone) {
        Write-NotRun "static compose check — needs Python 3 + PyYAML (scripts/compose-config-check.py) or Docker (`docker compose config`); neither is available in this environment"
    }

    # --- 2b. Docker-probed part: default mode reports NOT RUN ------------------
    if (-not $WithDocker -and -not $AgainstRunningProject) {
        Write-NotRun "docker compose config resolved-healthcheck inspection — run: docker compose config | Select-String healthcheck (expect literal '`$resp', 2x)"
        Write-NotRun "live Keycloak health state + discovered issuer — run: .\scripts\test-compose-healthcheck.ps1 -WithDocker (disposable cold-start) or -AgainstRunningProject (read-only, stack running)"
        Write-NotRun "backend/frontend healthy after Keycloak healthy — run: .\scripts\test-compose-healthcheck.ps1 -WithDocker"
        Write-Host "Docker probe NOT RUN — no Docker probe was run in default mode (re-run with -WithDocker or -AgainstRunningProject on a Docker machine)"
        Write-Summary "(Docker probe NOT RUN — re-run with -WithDocker or -AgainstRunningProject on a Docker machine)"
        Write-Host "SOURCE FIXED; ACTUAL DOCKER HEALTHCHECK + COMPOSE BOOT NOT RUN"
        # IF-V7.3.1-A: default mode exits 0 ONLY when a static check
        # actually EXECUTED and passed. Zero static checks performed is
        # ENVIRONMENT NOT READY (exit 1), never a silent 0 — the old
        # code exited 0 here whenever $script:Fail was 0, including
        # with 0 passed / 0 failed / 4 not run.
        if (-not $script:StaticExecuted) {
            Write-Host "ENVIRONMENT NOT READY: no static checker executed — install/launch Docker Desktop for 'docker compose config', or use Python 3 with PyYAML for static source-only checking (scripts/compose-config-check.py); nothing was verified, exit 1" -ForegroundColor Red
            exit 1
        }
        if ($script:Fail -eq 0) { exit 0 } else { exit 1 }
    }

    # From here Docker is available (CLI + Compose plugin + daemon all
    # proved by the preflight above). Resolved-command check (the
    # authoritative one) — skipped when the static step already ran
    # it via Docker above, so `compose config` is not run twice.
    if (-not $staticViaDocker) {
        & docker compose config > $ConfigOut 2> $ConfigErr
        $configRc = $LASTEXITCODE
        if ($configRc -ne 0) {
            Write-Bad "docker compose config failed (exit $configRc; see $ConfigErr)"
            Write-Summary ""
            exit 1
        }
        $resolved = ""
        if (Test-Path $ConfigOut) { $resolved = Get-Content $ConfigOut -Raw -ErrorAction SilentlyContinue }
        $respCount = ([regex]::Matches("$resolved", '\$resp')).Count
        if (("$resolved".Contains('resp=$(cat <&3)')) -and ($respCount -ge 2) -and (-not "$resolved".Contains('$$resp'))) {
            Write-Ok "docker compose config: resolved healthcheck contains literal '`$resp' (2x) and resp=`$(cat <&3)"
        } else {
            Write-Bad "docker compose config: resolved healthcheck lost the '`$resp' references (Compose interpolated them away)"
        }
    }

    if ($AgainstRunningProject) {
        # --- Read-only mode: inspect the EXISTING stack. No `up`, no
        # `down`, no volume ever touches this path; $Project stays
        # empty so no cleanup can delete anything. -------------------
        Write-Host "read-only mode: inspecting the existing stack (nothing will be started, stopped, or deleted)"
        $kcErr = Join-Path $LogDir "compose-healthcheck-ps.err"
        $KcName = (& docker compose ps -q keycloak 2> $kcErr | Out-String).Trim()
        if ([string]::IsNullOrEmpty($KcName)) {
            Write-Bad "read-only: no running keycloak container found (is the lab up? start it with: docker compose up --build -d)"
            Write-Summary ""
            exit 1
        }
        $kcHealth = Get-ContainerHealth $KcName
        $kcHealthFile = Join-Path $LogDir "compose-healthcheck-kc-health.json"
        & docker inspect $KcName --format '{{json .State.Health}}' > $kcHealthFile 2> $null
        if ($kcHealth -eq "healthy") {
            Write-Ok "read-only: Keycloak container is healthy (health state recorded in $kcHealthFile)"
        } else {
            Write-Bad "read-only: Keycloak container health is '$kcHealth' (expected healthy)"
        }
        $toolsLog = Join-Path $LogDir "compose-healthcheck-exec-tools.log"
        & docker compose exec -T keycloak bash -c 'command -v bash grep >/dev/null 2>&1' > $toolsLog 2> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "read-only: in-image tools present (bash + grep in keycloak:26.8.2)"
        } else {
            Write-Bad "read-only: bash/grep missing inside the Keycloak image (see $toolsLog)"
        }
        $execLog = Join-Path $LogDir "compose-healthcheck-exec.log"
        & docker compose exec -T keycloak bash -c $InImageProbe > $execLog 2> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "read-only: in-container probe: discovery 200 + issuer field present ($execLog)"
        } else {
            Write-Bad "read-only: in-container probe failed (see $execLog)"
        }
        $discLog = Join-Path $LogDir "compose-healthcheck-discovery.log"
        $discOk = Test-Discovery $DiscoveryUrl $CanonicalIssuer
        if ($discOk) {
            Write-Ok "read-only: discovered issuer is exactly the canonical issuer ($DiscoveryUrl)"
        } else {
            Write-Bad "read-only: discovery check failed (see above)"
        }
        $beHealth = Get-ContainerHealth ((& docker compose ps -q backend 2> $null | Out-String).Trim())
        $feHealth = Get-ContainerHealth ((& docker compose ps -q frontend 2> $null | Out-String).Trim())
        if (($beHealth -eq "healthy") -and ($feHealth -eq "healthy")) {
            Write-Ok "read-only: backend and frontend are healthy"
        } else {
            Write-Bad "read-only: backend/frontend are not both healthy (backend=$beHealth, frontend=$feHealth)"
        }
        Write-Summary "(read-only mode — nothing was started, stopped, or deleted)"
        if ($script:Fail -eq 0) { exit 0 } else { exit 1 }
    }

    # --- Disposable cold-start mode (-WithDocker) -----------------------------
    # IF-V7.1-04: BEFORE booting, prove the fixed ports are free. If
    # any is occupied, FAIL FAST here — no `compose up` runs, nothing
    # is stopped or killed, and the message prints the exact
    # stop/test/restart sequence (or the read-only alternative).
    $Occupied = @()
    foreach ($port in $CheckPorts) {
        if (-not (Test-PortFree $port)) { $Occupied += $port }
    }
    if ($Occupied.Count -gt 0) {
        Write-Bad "fixed lab port(s) $($Occupied -join ' ') occupied — refusing to boot a disposable project on conflicting ports (no containers were started, nothing was stopped or killed)"
        Write-Host "  The disposable cold-start needs 127.0.0.1:8080, 8000 and 5173 free."
        Write-Host "  If the occupant is this project's running lab, stop it first, run the test, then restart it:"
        Write-Host "    docker compose down"
        Write-Host "    .\scripts\test-compose-healthcheck.ps1 -WithDocker"
        Write-Host "    docker compose up -d"
        Write-Host "  If the occupant is another application, stop that application first —"
        Write-Host "  never change the lab's fixed ports (8080 is part of the issuer identity)."
        Write-Host "  To inspect the EXISTING stack without booting anything, use read-only mode:"
        Write-Host "    .\scripts\test-compose-healthcheck.ps1 -AgainstRunningProject"
        Write-Summary ""
        exit 1
    }
    Write-Ok "port preflight: lab ports ($($CheckPorts -join ' ')) are free (no occupant to disturb)"

    # Unique disposable project: timestamp + PID, so two runs (or a
    # stale project) can never collide, and cleanup can only ever
    # name this run's project.
    $Project = "identityforge-hcprobe-" + (Get-Date).ToUniversalTime().ToString("yyyyMMddHHmmss") + "-" + $PID
    $CleanupNeeded = $true
    try {
        $upLog = Join-Path $LogDir "compose-healthcheck-up.log"
        & docker compose -p $Project up --build -d > $upLog 2> $null
        if ($LASTEXITCODE -ne 0) {
            Write-Bad "docker compose up --build -d failed (see $upLog)"
            Write-Summary ""
            exit 1
        }
        $KcName = (& docker compose -p $Project ps -q keycloak 2> $null | Out-String).Trim()
        $kcHealth = "unknown"
        $waited = 0
        while ($waited -lt 300) {
            $kcHealth = Get-ContainerHealth $KcName
            if ($kcHealth -eq "healthy") { break }
            Start-Sleep -Seconds 5
            $waited += 5
        }
        $kcHealthFile = Join-Path $LogDir "compose-healthcheck-kc-health.json"
        & docker inspect $KcName --format '{{json .State.Health}}' > $kcHealthFile 2> $null
        if ($kcHealth -eq "healthy") {
            Write-Ok "Keycloak container reached healthy (health state recorded in $kcHealthFile)"
        } else {
            Write-Bad "Keycloak container did not reach healthy within 300s (last state: $kcHealth)"
        }
        $toolsLog = Join-Path $LogDir "compose-healthcheck-exec-tools.log"
        & docker compose -p $Project exec -T keycloak bash -c 'command -v bash grep >/dev/null 2>&1' > $toolsLog 2> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "in-image tools present (bash + grep in keycloak:26.8.2)"
        } else {
            Write-Bad "bash/grep missing inside the Keycloak image (see $toolsLog)"
        }
        $execLog = Join-Path $LogDir "compose-healthcheck-exec.log"
        & docker compose -p $Project exec -T keycloak bash -c $InImageProbe > $execLog 2> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "in-container probe: discovery 200 + issuer field present ($execLog)"
        } else {
            Write-Bad "in-container probe failed (see $execLog)"
        }
        if (Test-Discovery $DiscoveryUrl $CanonicalIssuer) {
            Write-Ok "discovered issuer is exactly the canonical issuer ($DiscoveryUrl)"
        } else {
            Write-Bad "discovery check failed (see above)"
        }
        $beHealth = "unknown"; $feHealth = "unknown"
        $waited = 0
        while ($waited -lt 180) {
            $beHealth = Get-ContainerHealth ((& docker compose -p $Project ps -q backend 2> $null | Out-String).Trim())
            $feHealth = Get-ContainerHealth ((& docker compose -p $Project ps -q frontend 2> $null | Out-String).Trim())
            if (($beHealth -eq "healthy") -and ($feHealth -eq "healthy")) { break }
            Start-Sleep -Seconds 5
            $waited += 5
        }
        if (($beHealth -eq "healthy") -and ($feHealth -eq "healthy")) {
            Write-Ok "backend and frontend reached healthy after Keycloak healthy"
        } else {
            Write-Bad "backend/frontend did not both reach healthy (backend=$beHealth, frontend=$feHealth)"
        }
    } finally {
        # Scoped to this run's disposable project ONLY. Never a bare
        # `docker compose down -v` (that would delete the user's
        # running project's volumes) and never any other project's
        # name.
        if ($CleanupNeeded -and $Project -ne "") {
            & docker compose -p $Project down -v > $null 2> $null
        }
    }

    Write-Summary "(disposable project $Project cleaned up)"
    if ($script:Fail -eq 0) { exit 0 } else { exit 1 }
} finally {
    Pop-Location
}
