# IdentityForge test-all (PowerShell) — Docker test profile, Option A (P0-02).
#
# All tests execute inside purpose-built Docker test containers via
# compose profiles, run SEQUENTIALLY to conserve RAM on an 8 GB laptop.
# The host needs Docker Desktop + PowerShell only (no host Python/Node).
#
#   .\scripts\test-all.ps1               # offline gates in containers
#   .\scripts\test-all.ps1 -Full -Strict # + disposable cold-start,
#                                        #   live Keycloak gates, browser E2E
#   .\scripts\test-all.ps1 -Help         # usage
#
# Parameters: -Offline (default), -Full, -Strict, -Help.
# Exit codes: 0 = all required gates PASS; 1 = a required gate FAILED
# or was NOT RUN under -Full/-Strict, or the Docker preflight failed;
# 2 = usage error (-Offline and -Full together, or an unknown argument).
#
# Gates (same IDs as scripts/test-all.sh):
#   OFFLINE_UNIT, OFFLINE_SCENARIOS, DOCS_CONTRACT, DOCS_CONTRACT_PATHS,
#   VERSION_CONTRACT, FRONTEND_TYPECHECK,
#   FRONTEND_UNIT, FRONTEND_BUILD, PYTHON_DEPENDENCY_AUDIT,
#   NPM_FULL_LOCKFILE_AUDIT, GHSA_DIRECT_FALLBACK, COMPOSE_CONFIG,
#   CLEAN_COMPOSE_BUILD_BOOT, LIVE_PROVIDER_PYTEST, REAL_KEYCLOAK_LOGIN,
#   REAL_SECURITY_NEGATIVES, REAL_LAB_RESET, PLAYWRIGHT_E2E, RESPONSIVE_QA
# (19 gates: 12 offline + 7 full. DOCS_CONTRACT is new in v5, IF-V4-06;
# DOCS_CONTRACT_PATHS + VERSION_CONTRACT are new in v6, IF-V5-01/05;
# LIVE_PROVIDER_PYTEST is new in v8.0.3 (ps1 parity with test-all.sh
# --full, IF-V8.0.2-B follow-up): the four provider-dependent pytest
# tests, marked live_keycloak, run only in -Full against the
# cold-started disposable Keycloak.)
#
# P0-03 (v4): -Full needs ports 8080/8000/5173 free for its disposable
# cold-start stack. If they are busy, the preflight detects whether
# the occupant is this project's lab and prints the exact stop ->
# test -> restart sequence; it never kills anything. Workflow:
# docker compose up -d (review) -> docker compose down (stop, keeps
# data) -> .\scripts\test-all.ps1 -Full -Strict -> docker compose up -d.
#
# IF-V4-08 (v5): native-command audit — every native `docker` call
# goes through Invoke-Native (Start-Process with stdout/stderr
# redirected to SEPARATE files). In Windows PowerShell 5.1, merging
# native stderr into the success stream (`2>&1`) wraps each stderr
# line in an ErrorRecord, and with $ErrorActionPreference = 'Stop'
# that can raise a terminating NativeCommandError even when the
# command SUCCEEDED (benign progress on stderr). Start-Process
# avoids PowerShell's stream machinery entirely, so the behaviour is
# identical on PS5.1 and PowerShell 7; the exit code comes from the
# process object (Start-Process does not set $LASTEXITCODE). A
# timeout kills the process and returns 124 (the `timeout`
# convention in test-all.sh). Docker args are passed as arrays
# (Invoke-Compose) or quoted strings, so repo paths with spaces work.
# PROVEN under PowerShell 7.4.6 on Linux (scripts/test-ps1-native.sh
# + scripts/test-ps1-preflight.sh). Windows PowerShell 5.1 execution
# remains NOT RUN (5.1 is Windows-only); the wrapper's 5.1 safety
# rests on the Start-Process mechanism, the documented version-proof
# way to capture native output. First real 5.1 execution is the
# reviewer's run — see docs/REVIEWER_GUIDE.md §7.
#
# Dependency gates (P0-03) are deliberately separate — the GHSA direct
# fallback NEVER satisfies the full npm audit. A clean fallback leaves
# NPM_FULL_LOCKFILE_AUDIT NOT RUN, and a strict/full run FAILS CLOSED.
# When the full npm audit executed (clean or with findings), the
# fallback is NOT APPLICABLE: it did not run, and a PASS there would be
# a phantom (P1-05, v4) — a PASS must mean the named gate actually ran
# and satisfied its check. NOT APPLICABLE never counts as NOT RUN for
# strictness: the gate was superseded, not skipped.
#
# Results are written machine-readable to test-results/gates.json and
# printed as a human table. A green run never implies a gate that was
# NOT RUN: the summary lists every NOT RUN gate by name.
#
# Status vocabulary (IF-V5-10, v6): a gate's status in
# test-results/gates.json is exactly one of PASS / FAIL / NOT RUN /
# NOT APPLICABLE. NOT RUN means the gate did not execute — it is never
# a pass, never "skipped", and never interchangeable with NOT
# APPLICABLE (superseded by a covering gate, P1-05) or FAIL (the gate
# ran and its check did not hold). "Skipped" is a word test suites use
# internally for an individual check inside a suite; it is NEVER a
# gate status and never appears in gates.json. A -Full or -Strict run
# fails closed (exit 1) when any required gate is FAIL or NOT RUN.
#
# POWERSHELL EXECUTION (v4): PowerShell 7.4.6 executed in the build
# sandbox on Linux (preflight/help/arg-parsing/ports paths, with a stub
# `docker` on PATH — see scripts/test-ps1-preflight.sh). Windows
# PowerShell 5.1 execution remains NOT RUN (5.1 is Windows-only).
# Reviewer commands on Windows (5.1 AND 7): -Offline, -Full -Strict,
# -Help, invalid parameters, missing daemon, occupied ports, blocked
# audit endpoint, failing test, run from a path with spaces — see
# docs/REVIEWER_GUIDE.md §7. First real 5.1 execution is the
# reviewer's run — report any failure with the full output, do not
# work around it silently. Static presence/parameter check:
# scripts/verify-release.sh (gate TEST_ALL_PS1).
#
# LIVE_PROVIDER_PYTEST (v8.0.3): the four provider-dependent pytest
# tests (marked live_keycloak in backend/tests/adversarial/
# test_ws1_v8_oidc.py) run ONLY in -Full, gate LIVE_PROVIDER_PYTEST,
# against the cold-started disposable Keycloak — never in the offline
# profile, never against the user's persistent stack. The arrangement
# is container-based (this script's premise: the host needs Docker
# Desktop + PowerShell only, no host Python): the tests run in the
# backend-test container on the disposable project's network
# (`-p $ColdProject run --rm backend-test`), joined to the same
# identityforge-net as the cold-started keycloak service, so the
# service DNS name `keycloak` resolves. The test app builds its
# Settings from pydantic defaults (fixture: Settings(), NOT env), so
# its transport base is the loopback default http://127.0.0.1:8080 —
# an -e IDENTITYFORGE_IDP_TRANSPORT_BASE override would NOT reach it.
# Reachability therefore comes from a loopback forwarder INSIDE the
# test container (scripts/loopback-forwarder.py, stdlib-only, same
# concept as the socat forwarders in the frontend-e2e entrypoint):
# 127.0.0.1:8080 -> keycloak:8080, a pure TCP proxy. The backend
# fetches discovery through it, validates the discovery issuer
# against the CANONICAL issuer http://127.0.0.1:8080/realms/
# identityforge-lab (unchanged), and the redirect URLs the tests
# assert stay canonical. No mocked issuer, no stub provider, no
# product-code change. The gate waits (curl, 30s) for a 200 discovery
# document THROUGH the forwarder before running pytest, then runs
# `python -m pytest -v -m live_keycloak` (pytest.ini forces -q,
# which in pytest 9 prints no "N passed" count line, and -v restores
# the summary line the gate checks; -v also avoids the embedded
# double quotes `-o addopts=""` would need inside the sh -c string)
# and passes ONLY when pytest exits 0 AND
# the log contains "4 passed" — positive proof the four tests really
# executed. If the cold-start boot failed there is no disposable
# provider, so the gate is honestly NOT RUN (never PASS). Docker
# execution of this gate is NOT RUN in the build sandbox (no Docker
# there) — reviewer acceptance on Windows: run
# .\scripts\test-all.ps1 -Full -Strict and confirm LIVE_PROVIDER_PYTEST
# PASS with "4 passed" in test-results\live-provider-pytest.log.
#
# QUOTING (OFFLINE_UNIT, v8.0.3): the `-m "not live_keycloak"`
# selection must arrive at pytest as ONE argument. The command
# travels PowerShell double-quoted string -> Invoke-Native
# (ConvertTo-NativeArgument, MSVC quoting) -> docker CLI argv ->
# container `sh -c` -> pytest. Inner DOUBLE quotes would need
# PowerShell backtick escaping (`") and are fragile, so the ps1
# uses SINGLE quotes inside the double-quoted string:
# `-m 'not live_keycloak'`. Single quotes are literal in a
# PowerShell double-quoted string, survive ConvertTo-NativeArgument
# (no embedded double quote to escape), and sh strips them, giving
# pytest exactly `-m` + `not live_keycloak`. Proved by
# scripts/test-ps1-selection.sh (static + stub-docker argv probe +
# real pytest collect-only split 516/4). The LIVE gate's sh -c
# string contains $ variables ($!, $?, $FORWARDER_PID, $RC), so it
# is a PowerShell SINGLE-quoted string instead (no interpolation);
# it contains no single quotes of its own.
#
# RAM note: the E2E image is ~1-1.5 GB (Chromium + system deps) and
# Keycloak needs ~1 GB on first boot. Everything runs sequentially;
# the preflight warns if Docker has less than 4 GB allocated.
param(
    [switch]$Offline,
    [switch]$Full,
    [switch]$Strict,
    [switch]$Help
)

# P1-07: PowerShell silently collects unknown named arguments into
# $args (e.g. a mistyped switch) and would otherwise run the wrong
# profile. Fail loudly instead — a release gate must never silently
# run non-strict because of a typo. (Unambiguous prefixes like
# -Stric for -Strict still bind normally; that is standard behavior.)
if ($args.Count -gt 0) {
    Write-Host "Usage error: unknown argument(s): $($args -join ' '). Valid switches: -Offline, -Full, -Strict, -Help." -ForegroundColor Red
    exit 2
}

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path) | Out-Null
Set-Location ..

if ($Help) {
    Write-Host "Usage: .\scripts\test-all.ps1 [-Offline|-Full] [-Strict] [-Help]"
    Write-Host ""
    Write-Host "  -Offline   offline gates only (default); live gates reported NOT RUN."
    Write-Host "  -Full      every gate is required; any FAIL or NOT RUN fails the run."
    Write-Host "  -Strict    additionally fail if any gate REQUIRED BY the profile was NOT RUN."
    Write-Host "  -Help      show this usage and exit 0."
    Write-Host ""
    Write-Host "Requires Docker Desktop (daemon running). No host Python/Node needed:"
    Write-Host "all tests run inside Docker test containers (Option A)."
    Write-Host ""
    Write-Host "Workflow (P0-03): start the lab, review it, stop it, then run -Full"
    Write-Host "-Strict, then start the lab again. -Full needs ports 8080/8000/5173"
    Write-Host "free for its disposable cold-start stack:"
    Write-Host "  docker compose up -d              # start the lab (review it)"
    Write-Host "  docker compose down               # stop it first — keeps your data"
    Write-Host "  .\scripts\test-all.ps1 -Full -Strict"
    Write-Host "  docker compose up -d              # start the lab again"
    Write-Host "If the ports are busy, this script refuses and prints the same"
    Write-Host "stop-first sequence instead of killing anything."
    exit 0
}
if ($Offline -and $Full) {
    Write-Host "Usage error: -Offline and -Full cannot be combined." -ForegroundColor Red
    exit 2
}
$ProfileName = "offline"
if ($Full) { $ProfileName = "full" }
$StrictMode = [bool]$Strict

New-Item -ItemType Directory -Force -Path "test-results" | Out-Null
$StartedAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$ResultsTsv = "test-results\gates.tsv"
Set-Content -Path $ResultsTsv -Value "" -NoNewline
$GateRows = New-Object System.Collections.ArrayList

function Add-GateRow($Id, $RequiredBy, $Status, $Detail) {
    $at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    $row = [PSCustomObject]@{
        id = $Id; required_by = $RequiredBy; status = $Status; at = $at; detail = $Detail
    }
    [void]$GateRows.Add($row)
    $line = "$Id`t$RequiredBy`t$Status`t$at`t$Detail"
    Add-Content -Path $ResultsTsv -Value $line
}

function Invoke-Gate($Id, $RequiredBy, $Label, [scriptblock]$Check) {
    Write-Host ""
    Write-Host "===== [$Id] $Label (required by: $RequiredBy) ====="
    $ok = $false
    try { $ok = & $Check } catch { Write-Host "gate error: $_" -ForegroundColor Red; $ok = $false }
    if ($ok) {
        Write-Host "PASS: $Id" -ForegroundColor Green
        Add-GateRow $Id $RequiredBy "PASS" $script:GateDetail
    } else {
        Write-Host "FAIL: $Id" -ForegroundColor Red
        Add-GateRow $Id $RequiredBy "FAIL" $script:GateDetail
    }
    $script:GateDetail = ""
}

function Skip-Gate($Id, $RequiredBy, $Label, $Reason) {
    Write-Host ""
    Write-Host "===== [$Id] $Label (required by: $RequiredBy) ====="
    Write-Host "NOT RUN: $Id — $Reason" -ForegroundColor Yellow
    Add-GateRow $Id $RequiredBy "NOT RUN" $Reason
}

function Add-NotApplicableGate($Id, $RequiredBy, $Label, $Reason) {
    # P1-05: status NOT APPLICABLE — the gate did not run because a
    # superseding gate already covered it (GHSA fallback when the full
    # npm audit executed). This is not a PASS and not a NOT RUN: the
    # strictness check below only counts FAIL and NOT RUN, so a
    # superseded gate can never fail or pass a release on its own.
    Write-Host ""
    Write-Host "===== [$Id] $Label (required by: $RequiredBy) ====="
    Write-Host "NOT APPLICABLE: $Id — $Reason" -ForegroundColor Cyan
    Add-GateRow $Id $RequiredBy "NOT APPLICABLE" $Reason
}

$script:GateDetail = ""

# Native invocation (IF-V4-08): Start-Process capture, no 2>&1 merge.
. "$PSScriptRoot\native-invoke.ps1"

# --- BEGIN NPM AUDIT CLASSIFIER (IF-V4-09) ---
# PowerShell mirror of scripts/npm-audit-classify.py (same
# classification table). Tested by scripts/test-ps1-native.sh, which
# extracts the text between these markers.
function Get-NpmAuditClassification([string]$LogFile, [string]$ErrFile, [int]$Rc) {
    # PowerShell mirror of scripts/npm-audit-classify.py (same
    # classification table: CLEAN / VULNERABILITIES_FOUND /
    # NOT_RUN:<reason> / CHECK_FAILED). Returns a hashtable with
    # Status and Reason. The npm audit JSON report must stay pure
    # JSON, so callers pass Invoke-Native -NoStderrMerge and the
    # separate .err file here.
    if ($Rc -eq 124) {
        return @{ Status = "NOT_RUN"; Reason = "NOT_RUN:TIMEOUT npm audit timed out (120s bound)" }
    }
    $stdoutText = ""
    if (Test-Path $LogFile) { $stdoutText = Get-Content $LogFile -Raw -ErrorAction SilentlyContinue }
    if (-not $stdoutText) { $stdoutText = "" }
    $stderrText = ""
    if ($ErrFile -and (Test-Path $ErrFile)) { $stderrText = Get-Content $ErrFile -Raw -ErrorAction SilentlyContinue }
    if (-not $stderrText) { $stderrText = "" }
    $combined = "$stdoutText`n$stderrText"
    $data = $null
    $jsonOk = $true
    try { $data = $stdoutText | ConvertFrom-Json -ErrorAction Stop } catch { $jsonOk = $false }
    if (-not $jsonOk) {
        foreach ($marker in @("policy_denied", "403 Forbidden", "audit endpoint returned an error", "E403")) {
            if ($combined.Contains($marker)) { return @{ Status = "NOT_RUN"; Reason = "NOT_RUN:BLOCKED npm audit endpoint blocked ($marker)" } }
        }
        foreach ($marker in @("ENOTFOUND", "EAI_AGAIN", "getaddrinfo")) {
            if ($combined.Contains($marker)) { return @{ Status = "NOT_RUN"; Reason = "NOT_RUN:DNS npm audit DNS failure ($marker)" } }
        }
        foreach ($marker in @("E429", "429 Too Many Requests", "rate limit")) {
            if ($combined.Contains($marker)) { return @{ Status = "NOT_RUN"; Reason = "NOT_RUN:RATE_LIMIT npm audit rate-limited ($marker)" } }
        }
        foreach ($marker in @("ETIMEDOUT", "ESOCKETTIMEDOUT", "network timeout", "timed out")) {
            if ($combined.Contains($marker)) { return @{ Status = "NOT_RUN"; Reason = "NOT_RUN:TIMEOUT npm audit timed out ($marker)" } }
        }
        foreach ($marker in @("ECONNREFUSED", "ENETUNREACH", "offline")) {
            if ($combined.Contains($marker)) { return @{ Status = "NOT_RUN"; Reason = "NOT_RUN:OFFLINE npm audit could not reach the registry ($marker)" } }
        }
        if ($combined -match '(\d+) vulnerabilities?\s*\(([^)]*)\)') {
            $counts = $Matches[2]
            $high = 0
            foreach ($m in [regex]::Matches($counts, '(\d+)\s+(low|moderate|high|critical)')) {
                if ($m.Groups[2].Value -eq "high" -or $m.Groups[2].Value -eq "critical") { $high += [int]$m.Groups[1].Value }
            }
            if ($high -gt 0) { return @{ Status = "VULNERABILITIES_FOUND"; Reason = "text audit report: $($Matches[0])" } }
            return @{ Status = "CLEAN"; Reason = "text audit report: $($Matches[0])" }
        }
        return @{ Status = "CHECK_FAILED"; Reason = "CHECK_FAILED npm audit output was not valid JSON (rc=$Rc); cannot confirm findings or cleanliness" }
    }
    if ($null -ne $data.error) {
        $code = [string]$data.error.code
        $detail = [string]($data.error.detail)
        if (-not $detail) { $detail = [string]($data.error.summary) }
        if (-not $detail) { $detail = $code }
        $text = "$code $detail $combined"
        if ($text.Contains("policy_denied") -or $text.Contains("403 Forbidden") -or $text.Contains("E403")) {
            return @{ Status = "NOT_RUN"; Reason = "NOT_RUN:BLOCKED npm audit error ${code}: $detail" }
        }
        if ($text.Contains("ENOTFOUND") -or $text.Contains("EAI_AGAIN") -or $text.Contains("getaddrinfo")) {
            return @{ Status = "NOT_RUN"; Reason = "NOT_RUN:DNS npm audit error ${code}: $detail" }
        }
        if ($text.Contains("E429") -or $text.Contains("429 Too Many Requests")) {
            return @{ Status = "NOT_RUN"; Reason = "NOT_RUN:RATE_LIMIT npm audit error ${code}: $detail" }
        }
        if ($text.Contains("ETIMEDOUT") -or $text.Contains("ESOCKETTIMEDOUT")) {
            return @{ Status = "NOT_RUN"; Reason = "NOT_RUN:TIMEOUT npm audit error ${code}: $detail" }
        }
        if ($text.Contains("ECONNREFUSED") -or $text.Contains("ENETUNREACH")) {
            return @{ Status = "NOT_RUN"; Reason = "NOT_RUN:OFFLINE npm audit error ${code}: $detail" }
        }
        return @{ Status = "CHECK_FAILED"; Reason = "CHECK_FAILED npm audit returned error ${code}: $detail" }
    }
    if ($null -eq $data.metadata -or $null -eq $data.metadata.vulnerabilities) {
        return @{ Status = "CHECK_FAILED"; Reason = "CHECK_FAILED npm audit JSON has no metadata.vulnerabilities; cannot confirm findings or cleanliness" }
    }
    $high = [int]$data.metadata.vulnerabilities.high + [int]$data.metadata.vulnerabilities.critical
    if ($high -gt 0) {
        if ($Rc -eq 0) {
            return @{ Status = "CHECK_FAILED"; Reason = "CHECK_FAILED npm audit rc=0 but metadata reports $high high/critical vulnerabilities — contradictory report" }
        }
        return @{ Status = "VULNERABILITIES_FOUND"; Reason = "npm audit found $high high/critical vulnerabilities" }
    }
    if ($Rc -eq 1) {
        return @{ Status = "CHECK_FAILED"; Reason = "CHECK_FAILED npm audit rc=1 but metadata reports 0 high/critical vulnerabilities — contradictory report" }
    }
    return @{ Status = "CLEAN"; Reason = "npm audit clean at --audit-level=high (JSON metadata, 0 high/critical)" }
}
# --- END NPM AUDIT CLASSIFIER (IF-V4-09) ---

function Invoke-Compose([string[]]$ComposeArgs, [string]$LogFile) {
    # Runs `docker compose ...` with output to a log file; returns $true
    # only on exit code 0. Arguments are passed as an array so paths
    # containing spaces need no manual quoting. Native capture goes
    # through Invoke-Native (IF-V4-08): no 2>&1 merge, exit code from
    # the process object.
    $all = @("compose") + $ComposeArgs
    $rc = Invoke-Native -Exe $script:DockerExe -Arguments $all -LogFile $LogFile
    if ($rc -eq 0) { return $true }
    Write-Host "docker compose failed (exit $rc); see $LogFile" -ForegroundColor Red
    return $false
}

function Test-PortFree([int]$Port) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient("127.0.0.1", $Port)
        $client.Close()
        return $false  # something answered: port is busy
    } catch {
        return $true
    }
}

# --- Preflight: Docker Desktop + daemon + ports + disk + memory ------------
Write-Host "== IdentityForge test-all (PowerShell, Docker profile) =="
Write-Host "Profile: $ProfileName, Strict: $StrictMode"
Write-Host ""
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Docker is not available. Install Docker Desktop for Windows" -ForegroundColor Red
    Write-Host "and make sure the Docker daemon is running, then re-run this script."
    exit 1
}
$script:DockerExe = (Get-Command docker).Source
$infoRc = Invoke-Native -Exe $script:DockerExe -Arguments @("info") -LogFile "test-results\docker-info.log"
if ($infoRc -ne 0) {
    Write-Host "ERROR: Docker daemon is not running (docker info failed)." -ForegroundColor Red
    Write-Host "Start Docker Desktop and wait until it reports running, then re-run."
    exit 1
}
Write-Host "OK   Docker daemon running"
$memLog = "test-results\docker-mem.log"
$null = Invoke-Native -Exe $script:DockerExe -Arguments @("info", "--format", "{{.MemTotal}}") -LogFile $memLog
$memText = ""
if (Test-Path $memLog) { $memText = (Get-Content $memLog -TotalCount 1 -ErrorAction SilentlyContinue) }
$memBytes = 0
if (([long]::TryParse("$memText".Trim(), [ref]$memBytes)) -and ($memBytes -gt 0)) {
    $memGB = [math]::Round($memBytes / 1GB, 1)
    if ($memBytes -lt 4GB) {
        Write-Host "WARN Docker memory is ${memGB} GB (under 4 GB): Keycloak + Chromium may be slow or fail on 8 GB hardware. Close other apps and consider raising Docker Desktop memory to 4 GB." -ForegroundColor Yellow
    } else {
        Write-Host "OK   Docker memory ${memGB} GB"
    }
} else {
    Write-Host "WARN Could not determine Docker memory allocation; Keycloak + Chromium need ~2 GB together." -ForegroundColor Yellow
}
$driveLetter = (Get-Location).Path.Substring(0, 1)
$drive = Get-PSDrive -Name $driveLetter -ErrorAction SilentlyContinue
if ($drive -and $drive.Free -ne $null) {
    $freeGB = [math]::Round($drive.Free / 1GB, 1)
    if ($drive.Free -lt 10GB) {
        Write-Host "WARN Only ${freeGB} GB free on drive ${driveLetter}: (test images need several GB; docker may fail mid-build)." -ForegroundColor Yellow
    } else {
        Write-Host "OK   Disk free ${freeGB} GB on drive ${driveLetter}"
    }
}
if ($ProfileName -eq "full") {
    $busy = @()
    foreach ($port in 8080, 8000, 5173) {
        if (-not (Test-PortFree $port)) { $busy += $port }
    }
    if ($busy.Count -gt 0) {
        # P0-03 (v4): stop-first workflow. A disposable Compose project
        # name cannot fix HOST-level port conflicts, so the cold-start
        # gate needs 8080/8000/5173 free. Detect whether the occupant
        # is this project's lab (running containers in this folder's
        # default project) and print the exact copy-pasteable
        # stop -> test -> restart sequence. Never silently kill an
        # arbitrary process or another user's containers.
        $runningServices = @()
        try {
            $psLog = "test-results\docker-ps-preflight.log"
            $null = Invoke-Native -Exe $script:DockerExe -Arguments @("compose", "ps", "--format", "json") -LogFile $psLog
            $psLines = @()
            if (Test-Path $psLog) { $psLines = Get-Content $psLog -ErrorAction SilentlyContinue }
            foreach ($line in $psLines) {
                if ($line.Trim() -eq "" -or -not $line.Trim().StartsWith("{")) { continue }
                $c = $line | ConvertFrom-Json
                if ($c.State -eq "running") { $runningServices += "$($c.Service) ($($c.Name))" }
            }
        } catch { $runningServices = @() }
        Write-Host "ERROR: ports $($busy -join ', ') are already in use — the cold-start gate publishes 8080/8000/5173." -ForegroundColor Red
        if ($runningServices.Count -gt 0) {
            Write-Host "These ports belong to the IdentityForge lab in this folder ($($runningServices -join ', '))."
            Write-Host "A disposable test project cannot share host ports with the running lab."
            Write-Host ""
            Write-Host "Stop the main lab first (keeps your data and volumes):"
            Write-Host "    docker compose down"
            Write-Host ""
            Write-Host "Then re-run this test:"
            Write-Host "    .\scripts\test-all.ps1 -Full -Strict"
            Write-Host ""
            Write-Host "When the test finishes, start the lab again:"
            Write-Host "    docker compose up -d"
            Write-Host ""
            Write-Host "Nothing was stopped or deleted by this check — run the commands above yourself."
        } else {
            Write-Host "These ports do NOT belong to this project's lab (no running IdentityForge containers found in this folder)."
            Write-Host "Free the ports first — stop whatever is using $($busy -join ', ') — then re-run this test."
            Write-Host "This script never kills other processes or containers for you."
        }
        exit 1
    }
    Write-Host "OK   Ports 8080/8000/5173 free"
}

$ComposeTest = @("-f", "docker-compose.yml", "-f", "docker-compose.test.yml", "--profile", "test")
$ComposeE2E = @("-f", "docker-compose.yml", "-f", "docker-compose.test.yml", "--profile", "test-e2e")

# --- Build the test images (sequential; first run downloads layers) --------
Write-Host ""
Write-Host "Building test images (backend-test, frontend-test) ..."
if (-not (Invoke-Compose ($ComposeTest + @("build", "backend-test")) "test-results\build-backend-test.log")) { exit 1 }
if (-not (Invoke-Compose ($ComposeTest + @("build", "frontend-test")) "test-results\build-frontend-test.log")) { exit 1 }

# --- Offline gates (required by both profiles) ------------------------------
# IF-V8.0.2-B (v8.0.2, ps1 parity v8.0.3): OFFLINE_UNIT runs the OFFLINE
# selection only (`-m 'not live_keycloak'`, single quotes — see the
# QUOTING note in the header). The four provider-dependent pytest
# tests (marked live_keycloak in backend/tests/adversarial/
# test_ws1_v8_oidc.py) need a live Keycloak and fail with 503
# PROVIDER_UNAVAILABLE without one, so an unfiltered run here
# mislabels a missing provider as a product failure (reproduced
# v8.0.3: unfiltered `pytest -q` with no provider -> rc=1, exactly
# the 4 marked tests FAILED). They run in -Full only, gate
# LIVE_PROVIDER_PYTEST, against the cold-started disposable Keycloak.
Invoke-Gate "OFFLINE_UNIT" "offline" "backend: ruff lint + format + pytest (container, offline selection -m 'not live_keycloak')" {
    Invoke-Compose ($ComposeTest + @("run", "--rm", "backend-test", "sh", "-c", "python -m ruff check src tests && python -m ruff format --check src tests && python -m pytest -q -m 'not live_keycloak'")) "test-results\offline-unit.log"
}
Invoke-Gate "OFFLINE_SCENARIOS" "offline" "backend: scenario CLI verify-all (container)" {
    Invoke-Compose ($ComposeTest + @("run", "--rm", "backend-test", "python", "-m", "identityforge.cli", "verify-all")) "test-results\offline-scenarios.log"
}
# IF-V4-06 (v5): docs-contract — reason codes / report fields in docs,
# example reports and UI copy must match the source exactly. Runs in
# backend-test (the repo docs/scripts are mounted read-only there; see
# docker-compose.test.yml). The container scan covers docs, README,
# SECURITY, example-reports and scripts; the full-tree scan (including
# frontend/src) runs in test-all.sh / CI.
Invoke-Gate "DOCS_CONTRACT" "offline" "docs: reason codes + report fields match source (container)" {
    Invoke-Compose ($ComposeTest + @("run", "--rm", "backend-test", "python", "scripts/validate-docs-contract.py", "--root", "/app", "--scan", "docs", "README.md", "SECURITY.md", "example-reports", "scripts")) "test-results\docs-contract.log"
}
# IF-V5-01 (v6): docs-contract path independence — the checker must
# behave identically when the tree is checked out under a `data/`
# ancestor or a path with spaces (v5 failed with 104 false violations
# under a `data/` ancestor). Runs in a throwaway python:3.12-slim
# container with the repo mounted (GHSA pattern) — no host Python
# needed, no test-image build; the script needs only bash + python3
# + mktemp. 15 checks: clean docs PASS + stale-code / below-root
# exclusion / symlink-escape / empty-scan negatives in all 3 paths.
$repoPath = (Get-Location).Path
Invoke-Gate "DOCS_CONTRACT_PATHS" "offline" "docs-contract: path-independent (normal / data ancestor / spaces)" {
    (Invoke-Native -Exe $script:DockerExe -Arguments @("run", "--rm", "-v", "${repoPath}:/repo", "-w", "/repo", "python:3.12-slim", "bash", "scripts/test-docs-contract-paths.sh") -LogFile "test-results\docs-contract-paths.log") -eq 0
}
# IF-V5-05 (v6): version contract — every authoritative version value
# (release manifest, backend pyproject + __init__ + FastAPI + health,
# frontend package.json + lockfile; UI reads the version from the
# health endpoint) must equal the release version 1.8.5. Same
# throwaway-container pattern; reads the live tree. Fails until the
# owning sources are bumped together (backend: WS1; frontend package
# files: via npm so the lockfile stays in sync).
Invoke-Gate "VERSION_CONTRACT" "offline" "release version 1.8.5 agrees everywhere (manifest, backend, frontend, health)" {
    (Invoke-Native -Exe $script:DockerExe -Arguments @("run", "--rm", "-v", "${repoPath}:/repo", "-w", "/repo", "python:3.12-slim", "python3", "scripts/check-version-contract.py") -LogFile "test-results\version-contract.log") -eq 0
}
Invoke-Gate "FRONTEND_TYPECHECK" "offline" "frontend: typecheck (container)" {
    Invoke-Compose ($ComposeTest + @("run", "--rm", "frontend-test", "npm", "run", "typecheck")) "test-results\frontend-typecheck.log"
}
Invoke-Gate "FRONTEND_UNIT" "offline" "frontend: unit/component tests (container)" {
    Invoke-Compose ($ComposeTest + @("run", "--rm", "frontend-test", "npm", "test", "--", "--run")) "test-results\frontend-unit.log"
}
Invoke-Gate "FRONTEND_BUILD" "offline" "frontend: production build (container)" {
    Invoke-Compose ($ComposeTest + @("run", "--rm", "frontend-test", "npm", "run", "build")) "test-results\frontend-build.log"
}

# --- Dependency audits: three separate gates (P0-03) ------------------------
# PYTHON_DEPENDENCY_AUDIT: pip-audit is installed AT BUILD TIME in
# the backend image (backend/Dockerfile installs the pinned auditor
# from backend/requirements-audit.txt into the system site-packages
# — IF-V8-42, v8.0.5). It MUST NOT be installed at gate time: the
# audit runs as the non-root app user (UID 10001), which cannot
# write system site-packages, and a gate-time install would also
# re-download the auditor on every run instead of using the pinned
# build-time copy. The gate therefore only verifies the tool and
# runs the scan; the classification below is unchanged (IF-V4-09):
# the scan exit code counts as "vulnerabilities found" ONLY when
# the log names the findings — any other rc=1 is CHECK_FAILED
# (NOT RUN), and a missing module is TOOL_UNAVAILABLE (NOT RUN,
# fail-closed under -Strict: a missing tool means a broken image,
# never a silent clean).
$pyAuditLog = "test-results\audit-backend.log"
$pyRc = Invoke-Native -Exe $script:DockerExe -Arguments (@("compose") + $ComposeTest + @("run", "--rm", "backend-test", "sh", "-c", "python -m pip_audit --version; python -m pip_audit -r requirements-freeze.txt")) -LogFile $pyAuditLog
$pyLogText = ""
if (Test-Path $pyAuditLog) { $pyLogText = Get-Content $pyAuditLog -Raw -ErrorAction SilentlyContinue }
if ($pyRc -eq 0) {
    Invoke-Gate "PYTHON_DEPENDENCY_AUDIT" "offline" "pip-audit over backend/requirements-freeze.txt (full pinned runtime set)" { return $true }
} elseif ($pyRc -eq 1 -and $pyLogText -match "Found [0-9]+ known vulnerabilities? in") {
    $script:GateDetail = "pip-audit found vulnerabilities — see test-results\audit-backend.log"
    Invoke-Gate "PYTHON_DEPENDENCY_AUDIT" "offline" "pip-audit over backend/requirements-freeze.txt (full pinned runtime set)" { return $false }
} elseif ($pyRc -eq 1 -and $pyLogText -match "No module named pip_audit") {
    Skip-Gate "PYTHON_DEPENDENCY_AUDIT" "offline" "pip-audit over backend/requirements-freeze.txt (full pinned runtime set)" "TOOL_UNAVAILABLE: pip-audit could not be installed or verified inside the container — see test-results\audit-backend.log"
} elseif ($pyRc -eq 1) {
    Skip-Gate "PYTHON_DEPENDENCY_AUDIT" "offline" "pip-audit over backend/requirements-freeze.txt (full pinned runtime set)" "CHECK_FAILED: pip-audit exited rc=1 without a recognizable vulnerability report — see test-results\audit-backend.log"
} else {
    Skip-Gate "PYTHON_DEPENDENCY_AUDIT" "offline" "pip-audit over backend/requirements-freeze.txt (full pinned runtime set)" "CHECK_FAILED: pip-audit could not run here (rc=$pyRc — see test-results\audit-backend.log)"
}

# NPM_FULL_LOCKFILE_AUDIT: npm audit over the resolved lockfile tree.
# IF-V4-09: runs with --json and a 120s bound; the JSON report is
# classified by Get-NpmAuditClassification (the PowerShell mirror of
# scripts/npm-audit-classify.py). DNS / proxy / 403 / 429 / offline /
# timeout / malformed results are NOT RUN, never findings. The audit
# log is kept as pure JSON (-NoStderrMerge) so the classifier can
# parse it; stderr lives in audit-frontend.log.err.
$npmAuditLog = "test-results\audit-frontend.log"
$npmRc = Invoke-Native -Exe $script:DockerExe -Arguments (@("compose") + $ComposeTest + @("run", "--rm", "frontend-test", "sh", "-c", "timeout 120 npm audit --audit-level=high --json")) -LogFile $npmAuditLog -NoStderrMerge -TimeoutSeconds 150
$npmCls = Get-NpmAuditClassification -LogFile $npmAuditLog -ErrFile "$npmAuditLog.err" -Rc $npmRc
$ghsaNeeded = $false
if ($npmCls.Status -eq "CLEAN") {
    Invoke-Gate "NPM_FULL_LOCKFILE_AUDIT" "offline" "npm audit over the resolved lockfile tree (package-lock.json)" { return $true }
    # P1-05: the full audit executed clean, so the fallback is NOT
    # APPLICABLE — it did not run. A PASS here would be a phantom.
    Add-NotApplicableGate "GHSA_DIRECT_FALLBACK" "offline" "GHSA direct-dependency fallback (informational, direct deps only)" "not applicable — npm audit executed clean; full lockfile coverage subsumes the direct-only fallback, which did not run"
} elseif ($npmCls.Status -eq "VULNERABILITIES_FOUND") {
    $script:GateDetail = "npm audit found vulnerabilities — see test-results\audit-frontend.log"
    Invoke-Gate "NPM_FULL_LOCKFILE_AUDIT" "offline" "npm audit over the resolved lockfile tree (package-lock.json)" { return $false }
    # P1-05: the full audit executed (and found things), so the
    # fallback is NOT APPLICABLE — it did not run and must never be
    # marked PASS alongside a failed full audit.
    Add-NotApplicableGate "GHSA_DIRECT_FALLBACK" "offline" "GHSA direct-dependency fallback (informational, direct deps only)" "not applicable — npm audit executed and found vulnerabilities; the direct-only fallback did not run"
} elseif ($npmCls.Status -eq "NOT_RUN") {
    Skip-Gate "NPM_FULL_LOCKFILE_AUDIT" "offline" "npm audit over the resolved lockfile tree (package-lock.json)" "$($npmCls.Reason) — see test-results\audit-frontend.log; run on a machine with registry access"
    $ghsaNeeded = $true
} else {
    Skip-Gate "NPM_FULL_LOCKFILE_AUDIT" "offline" "npm audit over the resolved lockfile tree (package-lock.json)" "$($npmCls.Reason) — see test-results\audit-frontend.log"
    $ghsaNeeded = $true
}
if ($ghsaNeeded) {
    # GHSA direct fallback (informational only) in a throwaway Python
    # container with the repo mounted — the host has no Python by design.
    $repoPath = (Get-Location).Path
    $ghsaRc = Invoke-Native -Exe $script:DockerExe -Arguments @("run", "--rm", "-v", "${repoPath}:/repo", "-w", "/repo", "python:3.12-slim", "python3", "scripts/npm-advisory-check.py") -LogFile "test-results\audit-frontend-ghsa.log"
    if ($ghsaRc -eq 0) {
        $script:GateDetail = "direct dependencies only — transitive advisories NOT checked; NPM_FULL_LOCKFILE_AUDIT remains NOT RUN (see test-results\audit-frontend-ghsa.json)"
        Invoke-Gate "GHSA_DIRECT_FALLBACK" "offline" "GHSA direct-dependency fallback (informational, direct deps only)" { return $true }
    } elseif ($ghsaRc -eq 1) {
        $script:GateDetail = "GHSA found high/critical advisories affecting direct deps — see test-results\audit-frontend-ghsa.json"
        Invoke-Gate "GHSA_DIRECT_FALLBACK" "offline" "GHSA direct-dependency fallback (informational, direct deps only)" { return $false }
    } else {
        Skip-Gate "GHSA_DIRECT_FALLBACK" "offline" "GHSA direct-dependency fallback (informational, direct deps only)" "advisory source unreachable or rate-limited (rc=$ghsaRc); npm audit also unavailable"
    }
}

# --- Compose config (real `docker compose config`, not YAML-only) ------------
# IF-V4-01: after `config -q` passes, the RESOLVED config is also
# inspected: it must contain the literal Keycloak healthcheck shell
# variable '$resp' (2x) and 'resp=$(cat <&3)' — if Compose had
# interpolated a single-dollar '$resp' away, the resolved text would
# show empty 'echo ""' instead.
if (Invoke-Compose @("config", "-q") "test-results\compose-config.log") {
    # The rendered configuration contains the Keycloak admin password.
    # Validate it in memory; never create a resolved-config file in test-results.
    $cfg = Invoke-NativeInMemory -Exe $script:DockerExe -Arguments @("compose", "config")
    $resolvedText = [string]$cfg.Output
    $plainOk = $resolvedText.Contains('resp=$(cat <&3)') -and ([regex]::Matches($resolvedText, '(?<!\$)\$resp')).Count -ge 2
    $escapedOk = [regex]::IsMatch($resolvedText, 'resp=\$\$\(cat\s+<&3\)') -and ([regex]::Matches($resolvedText, '\$\$resp')).Count -ge 2
    $resolvedOk = ($cfg.ExitCode -eq 0) -and ($plainOk -or $escapedOk)
    $resolvedText = $null
    $cfg = $null
    if ($resolvedOk) {
        Invoke-Gate "COMPOSE_CONFIG" "offline" "docker compose config validates (resolved healthcheck keeps literal '`$resp')" { return $true }
    } else {
        $script:GateDetail = "docker compose resolved-healthcheck verification failed (IF-V4-01; expanded config intentionally not saved)"
        Invoke-Gate "COMPOSE_CONFIG" "offline" "docker compose config validates (resolved healthcheck keeps literal '`$resp')" { return $false }
    }
} else {
    Invoke-Gate "COMPOSE_CONFIG" "offline" "docker compose config validates" { return $false }
}

# --- Live gates (required only by -Full) --------------------------------------
# P1-13: a health check of already-running containers is NOT a cold-start
# proof. -Full always boots a DISPOSABLE project namespace from a fresh
# build, runs the live gates against it, and tears it down (down -v) —
# never touching the user's own stack or volumes.
$ColdProject = ""
if ($ProfileName -eq "full") {
    $ColdProject = "identityforge-coldstart-" + (Get-Date).ToUniversalTime().ToString("yyyyMMddHHmmss")
    # IF-V7.1-01 (v7.2): fresh disposable-project marker for this run.
    # The backend reports it via /api/v1/lab/status; live-gate.py reset
    # refuses to run unless its --disposable-project-id flag matches the
    # value the backend itself reports. A new UUID per run, so a stale
    # marker from an earlier run can never authorise a reset. Set in the
    # process environment so `docker compose up` interpolates it into
    # the disposable backend service (docker-compose.yml).
    $DisposableProjectId = [guid]::NewGuid().ToString()
    $env:IDENTITYFORGE_DISPOSABLE_PROJECT_ID = $DisposableProjectId
    New-Item -ItemType Directory -Force -Path "test-results\coldstart" | Out-Null
    Write-Host ""
    Write-Host "Cold-starting the lab in disposable namespace $ColdProject ..."
    try {
        # IF-V4-08: use the same native helper family without native
        # stderr stream merging. -q preserves strict Compose validation,
        # but never serializes expanded credentials into test-results.
        $configCheck = Invoke-NativeInMemory -Exe $script:DockerExe -Arguments @("compose", "-p", $ColdProject, "config", "-q")
        $configOk = ($configCheck.ExitCode -eq 0)
        $configCheck = $null
        $bootOk = $false
        if ($configOk) {
            $upRc = Invoke-Native -Exe $script:DockerExe -Arguments @("compose", "-p", $ColdProject, "up", "--build", "-d") -LogFile "test-results\coldstart\up.log"
            if ($upRc -eq 0) {
                $null = Invoke-Native -Exe $script:DockerExe -Arguments @("compose", "-p", $ColdProject, "ps", "--format", "json") -LogFile "test-results\coldstart\containers.json"
                $waited = 0
                $ready = $false
                while ($waited -lt 360) {
                    # doctor.ps1 is PowerShell, not native: stdout and
                    # stderr to separate files (no 2>&1 merge).
                    $doctorLog = "test-results\coldstart\doctor.log"
                    & .\scripts\doctor.ps1 > $doctorLog 2> "$doctorLog.err"
                    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
                    Start-Sleep -Seconds 10
                    $waited += 10
                }
                if ($ready) { $bootOk = $true }
                else { $script:GateDetail = "doctor never became READY within 360s — see test-results\coldstart\doctor.log" }
            } else {
                $script:GateDetail = "docker compose up --build -d failed — see test-results\coldstart\up.log"
            }
        } else {
            $script:GateDetail = "docker compose config -q failed for the disposable project (expanded config not logged)"
        }
        if ($bootOk) {
            Invoke-Gate "CLEAN_COMPOSE_BUILD_BOOT" "full" "cold-start: compose up --build -d + doctor READY in disposable namespace" { return $true }
        } else {
            Invoke-Gate "CLEAN_COMPOSE_BUILD_BOOT" "full" "cold-start: compose up --build -d + doctor READY in disposable namespace" { return $false }
        }
        # IF-V8.0.2-B follow-up (v8.0.3): the four provider-dependent
        # pytest tests (marked live_keycloak) run HERE, in the
        # backend-test container on the disposable project's network,
        # against the cold-started disposable Keycloak — never in the
        # offline profile, never against the user's persistent stack.
        # See the LIVE_PROVIDER_PYTEST header note for the arrangement
        # (loopback forwarder inside the container: the fixture builds
        # Settings() from defaults, so no env override can reroute the
        # test app's transport). Runs only when the cold-start boot
        # succeeded (BOOT_OK); otherwise NOT RUN honestly, and -Full /
        # -Strict fails closed. PASS requires BOTH pytest rc 0 AND
        # "4 passed" in the log — positive proof the four tests really
        # executed (pytest.ini forces -q, which prints no count line,
        # so the run uses -v; a 0-test collection exits 5 and fails
        # the gate anyway).
        if ($bootOk) {
            Invoke-Gate "LIVE_PROVIDER_PYTEST" "full" "backend: provider-dependent pytest in container (live Keycloak, -m live_keycloak, loopback forwarder)" {
                $liveOk = Invoke-Compose ($ComposeTest + @("-p", $ColdProject, "run", "--rm", "backend-test", "sh", "-c", 'python /app/scripts/loopback-forwarder.py 127.0.0.1:8080 keycloak:8080 > /tmp/forwarder.log 2>&1 & FORWARDER_PID=$!; READY=0; I=0; while [ $I -lt 30 ]; do if curl -fsS http://127.0.0.1:8080/realms/identityforge-lab/.well-known/openid-configuration > /dev/null 2>&1; then READY=1; break; fi; sleep 1; I=$((I+1)); done; if [ $READY -ne 1 ]; then echo LIVE_PROVIDER_PYTEST loopback forwarder never became ready; cat /tmp/forwarder.log; kill $FORWARDER_PID 2>/dev/null; exit 1; fi; python -m pytest -v -m live_keycloak; RC=$?; kill $FORWARDER_PID 2>/dev/null; exit $RC')) "test-results\live-provider-pytest.log"
                $liveLog = ""
                if (Test-Path "test-results\live-provider-pytest.log") { $liveLog = Get-Content "test-results\live-provider-pytest.log" -Raw -ErrorAction SilentlyContinue }
                if (-not $liveOk) { $script:GateDetail = "provider pytest failed or the forwarder never became ready — see test-results\live-provider-pytest.log" }
                elseif ($liveLog -notmatch "4 passed") { $script:GateDetail = "pytest exited 0 but the log shows no '4 passed' — the four live tests did not all execute; see test-results\live-provider-pytest.log" }
                return ($liveOk -and ($liveLog -match "4 passed"))
            }
        } else {
            Skip-Gate "LIVE_PROVIDER_PYTEST" "full" "backend: provider-dependent pytest (live Keycloak)" "cold-start boot failed; no disposable provider for the marked tests"
        }
        Invoke-Gate "REAL_KEYCLOAK_LOGIN" "full" "real Keycloak login (student + officer, logout, stale 401)" {
            Invoke-Compose ($ComposeTest + @("-p", $ColdProject, "run", "--rm", "live-gate", "python3", "/scripts/live-gate.py", "login")) "test-results\live-login.log"
        }
        Invoke-Gate "REAL_SECURITY_NEGATIVES" "full" "real Keycloak negatives (binding, replay, K2, K3)" {
            $a = Invoke-Compose ($ComposeTest + @("-p", $ColdProject, "run", "--rm", "live-gate", "python3", "/scripts/live-gate.py", "binding")) "test-results\live-binding.log"
            $b = $false
            if ($a) {
                $b = Invoke-Compose ($ComposeTest + @("-p", $ColdProject, "run", "--rm", "live-gate", "python3", "/scripts/live-gate.py", "negatives")) "test-results\live-negatives.log"
            }
            return ($a -and $b)
        }
        # P1-13: disposable real-Keycloak reset test. Runs ONLY in this
        # cold-start namespace (never against the user's persistent lab):
        # creates a synthetic run, proves unauthenticated/student reset
        # cannot delete it, proves officer + CSRF + explicit confirmation
        # can, and proves the stale officer cookie is 401 afterwards.
        # Runs before the browser E2E so the E2E starts from a clean lab.
        # The reset is DESTRUCTIVE, so unlike the login/negatives gates
        # it runs ONLY when the cold-start boot succeeded (BOOT_OK):
        # with no disposable stack there is nothing safe to reset.
        if ($bootOk) {
            Invoke-Gate "REAL_LAB_RESET" "full" "real Keycloak reset in the disposable namespace (synthetic run, unauthenticated/student denied, officer reset, stale cookies 401)" {
                Invoke-Compose ($ComposeTest + @("-p", $ColdProject, "run", "--rm", "live-gate", "python3", "/scripts/live-gate.py", "reset", "--disposable-project-id", $DisposableProjectId)) "test-results\live-reset.log"
            }
        } else {
            Skip-Gate "REAL_LAB_RESET" "full" "real Keycloak reset in the disposable namespace" "cold-start boot failed; no disposable stack for the reset test"
        }
        # Browser E2E runs ALONE (other test containers have stopped by
        # now — `run --rm` removes them). Build the E2E image first:
        # it is the largest image (~1-1.5 GB) and only needed for -Full.
        # IF-V4-10 (v5): the Playwright exit code alone is NOT the E2E
        # verdict. The stale report is deleted first (freshness), the
        # run is bound to this disposable project via
        # IDENTITYFORGE_E2E_TARGET (recorded in the report's
        # config.metadata.target — the compose file maps it into the
        # E2E container), and the JSON report is parsed by
        # scripts/validate-playwright-report.py — run inside the
        # stdlib-only live-gate container against the host
        # test-results/ mount — IMMEDIATELY after the E2E run and
        # BEFORE the screenshots run, which overwrites the same
        # report file. Each gate passes only when its run AND its
        # validator both succeed.
        Write-Host ""
        Write-Host "Building the E2E image (frontend-e2e; Chromium + system deps) ..."
        if (Invoke-Compose ($ComposeE2E + @("build", "frontend-e2e")) "test-results\build-frontend-e2e.log") {
            $env:IDENTITYFORGE_E2E_TARGET = $ColdProject
            Remove-Item "test-results\playwright-report.json" -ErrorAction SilentlyContinue
            $e2eStart = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
            Invoke-Gate "PLAYWRIGHT_E2E" "full" "browser E2E (real Keycloak, JSON evidence validated)" {
                $e2eOk = Invoke-Compose ($ComposeE2E + @("-p", $ColdProject, "run", "--rm", "frontend-e2e")) "test-results\playwright-e2e.log"
                $valOk = Invoke-Compose ($ComposeTest + @("-p", $ColdProject, "run", "--rm", "live-gate", "python3", "/scripts/validate-playwright-report.py", "--report", "/test-results/playwright-report.json", "--target", $ColdProject, "--since-epoch", "$e2eStart")) "test-results\playwright-validate.log"
                return ($e2eOk -and $valOk)
            }
            $shotsStart = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
            Invoke-Gate "RESPONSIVE_QA" "full" "responsive screenshots (320/390/768/1440/1920)" {
                $shotsOk = Invoke-Compose ($ComposeE2E + @("-p", $ColdProject, "run", "--rm", "frontend-e2e", "npm", "run", "test:screenshots")) "test-results\responsive-qa.log"
                $valOk = Invoke-Compose ($ComposeTest + @("-p", $ColdProject, "run", "--rm", "live-gate", "python3", "/scripts/validate-playwright-report.py", "--report", "/test-results/playwright-report.json", "--target", $ColdProject, "--profile", "screenshots", "--since-epoch", "$shotsStart")) "test-results\screenshots-validate.log"
                return ($shotsOk -and $valOk)
            }
        } else {
            Invoke-Gate "PLAYWRIGHT_E2E" "full" "browser E2E (real Keycloak, JSON evidence validated)" { return $false }
            Invoke-Gate "RESPONSIVE_QA" "full" "responsive screenshots (320/390/768/1440/1920)" { return $false }
        }
        $null = Invoke-Native -Exe $script:DockerExe -Arguments @("compose", "-p", $ColdProject, "logs", "--no-log-prefix") -LogFile "test-results\coldstart\compose.log"
        $null = Invoke-Native -Exe $script:DockerExe -Arguments @("compose", "-p", $ColdProject, "ps", "--format", "json") -LogFile "test-results\coldstart\containers-final.json"
    } finally {
        if ($ColdProject -ne "") {
            Write-Host "Tearing down the disposable cold-start namespace ($ColdProject) ..."
            $null = Invoke-Native -Exe $script:DockerExe -Arguments @("compose", "-p", $ColdProject, "down", "-v") -LogFile "test-results\coldstart\down.log"
            Remove-Item Env:IDENTITYFORGE_DISPOSABLE_PROJECT_ID -ErrorAction SilentlyContinue
        }
    }
} else {
    Skip-Gate "CLEAN_COMPOSE_BUILD_BOOT" "full" "cold-start: compose up --build -d + doctor READY in disposable namespace" "offline profile — opt in with -Full"
    Skip-Gate "LIVE_PROVIDER_PYTEST" "full" "backend: provider-dependent pytest (live Keycloak)" "offline profile — opt in with -Full"
    Skip-Gate "REAL_KEYCLOAK_LOGIN" "full" "real Keycloak login" "offline profile — opt in with -Full"
    Skip-Gate "REAL_SECURITY_NEGATIVES" "full" "real Keycloak negatives" "offline profile — opt in with -Full"
    Skip-Gate "REAL_LAB_RESET" "full" "real Keycloak reset in the disposable namespace" "offline profile — opt in with -Full"
    Skip-Gate "PLAYWRIGHT_E2E" "full" "browser E2E (real Keycloak)" "offline profile — opt in with -Full"
    Skip-Gate "RESPONSIVE_QA" "full" "responsive screenshots" "offline profile — opt in with -Full"
}

# --- Machine-readable report + summary --------------------------------------
$summary = @{ "PASS" = 0; "FAIL" = 0; "NOT RUN" = 0; "NOT APPLICABLE" = 0 }
foreach ($row in $GateRows) { $summary[$row.status] += 1 }
$doc = [ordered]@{
    profile = $ProfileName
    started_at = $StartedAt
    gates = @($GateRows)
    summary = $summary
}
$doc | ConvertTo-Json -Depth 4 | Set-Content -Path "test-results\gates.json"

Write-Host ""
Write-Host "===== test-all summary (profile: $ProfileName) ====="
foreach ($row in $GateRows) {
    $id = $row.id.PadRight(28)
    $status = $row.status.PadRight(8)
    Write-Host "$id $status $($row.detail)"
}
Write-Host ""
Write-Host "Machine-readable report: test-results\gates.json"

$requiredFailed = 0
$requiredNotRun = 0
foreach ($row in $GateRows) {
    $required = ($row.required_by -eq $ProfileName) -or (($ProfileName -eq "full") -and ($row.required_by -eq "offline"))
    if ($required -and ($row.status -eq "FAIL")) { $requiredFailed += 1 }
    if ($required -and ($row.status -eq "NOT RUN")) { $requiredNotRun += 1 }
}
if ($requiredFailed -gt 0) {
    Write-Host "$requiredFailed required gate(s) FAILED. See the output above; fix and re-run." -ForegroundColor Red
    exit 1
}
# A required gate that was skipped/unavailable fails the run when the
# profile demands it (-Full always) or when -Strict is set. Without
# -Strict, an offline run still passes but the banner below names the
# missing gates — a NOT RUN gate is never silently read as a pass.
if (($requiredNotRun -gt 0) -and (($ProfileName -eq "full") -or $StrictMode)) {
    Write-Host "GATE FAILED: $requiredNotRun required gate(s) NOT RUN (profile: $ProfileName, strict: $StrictMode)." -ForegroundColor Red
    Write-Host "A full release gate must not pass while a required gate was skipped or unavailable."
    exit 1
}
if ($ProfileName -eq "offline") {
    Write-Host "All required offline gates passed. LIVE E2E NOT RUN in this profile"
    Write-Host "(CLEAN_COMPOSE_BUILD_BOOT, LIVE_PROVIDER_PYTEST, REAL_KEYCLOAK_LOGIN,"
    Write-Host "REAL_SECURITY_NEGATIVES, REAL_LAB_RESET, PLAYWRIGHT_E2E, RESPONSIVE_QA)"
    Write-Host "— re-run with -Full to execute them."
} else {
    Write-Host "All required gates passed (profile: full)."
}
exit 0
