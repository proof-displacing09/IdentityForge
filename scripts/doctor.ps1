# IdentityForge doctor (PowerShell) — honest loopback health checks.
# Exits 0 only when each service proves its identity (P1-21) AND the
# backend can actually reach the IdP with the canonical issuer (P0-05):
# a bare HTTP 200 from any process on the port is NOT enough, and a
# healthy-looking host is NOT enough if the backend cannot contact
# Keycloak.
#   - Keycloak: discovery JSON must carry the canonical issuer exactly.
#   - Backend: /api/v1/health must name service identityforge-backend.
#   - Frontend: the HTML must contain the IdentityForge app root.
#   - Readiness: /api/v1/lab/status must report idp.reachable=true
#     AND idp.issuer_matches=true (measured from the BACKEND).
#   .\scripts\doctor.ps1 [-Brief]   -Brief prints one line: READY or
#   NOT READY: <reasons>, with the same exit code.
param([switch]$Brief)

$ErrorActionPreference = "Continue"
$ok = $true
$reasons = New-Object System.Collections.ArrayList

function Get-Json($Url) {
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 10
        if ($r.StatusCode -ne 200) { return $null }
        return ($r.Content | ConvertFrom-Json)
    } catch { return $null }
}

function Say($Text) {
    if (-not $Brief) { Write-Host $Text }
}

function Fail($Reason) {
    $script:ok = $false
    [void]$script:reasons.Add($Reason)
}

Say "== IdentityForge doctor =="

$kc = Get-Json "http://127.0.0.1:8080/realms/identityforge-lab/.well-known/openid-configuration"
if ($kc -and $kc.issuer -eq "http://127.0.0.1:8080/realms/identityforge-lab") {
    Say "OK   Keycloak OIDC discovery  (issuer exactly http://127.0.0.1:8080/realms/identityforge-lab)"
} else {
    Say "FAIL Keycloak OIDC discovery  (no discovery JSON with the canonical issuer on 127.0.0.1:8080)"
    Fail "keycloak-discovery"
}

$be = Get-Json "http://127.0.0.1:8000/api/v1/health"
if ($be -and $be.service -eq "identityforge-backend" -and $be.status -eq "ok") {
    Say "OK   Backend health  (service identityforge-backend, status ok)"
} else {
    Say "FAIL Backend health  (no identityforge-backend health JSON on 127.0.0.1:8000)"
    Fail "backend-health"
}

try {
    $fe = Invoke-WebRequest -Uri "http://127.0.0.1:5173/" -UseBasicParsing -TimeoutSec 10
    if ($fe.StatusCode -eq 200 -and $fe.Content -match 'id="root"') {
        Say "OK   Frontend  (IdentityForge app root served on 127.0.0.1:5173)"
    } else {
        Say "FAIL Frontend  (no IdentityForge app root on 127.0.0.1:5173)"
        Fail "frontend"
    }
} catch {
    Say "FAIL Frontend  (no IdentityForge app root on 127.0.0.1:5173)"
    Fail "frontend"
}

# Readiness (P0-05): the BACKEND must be able to reach the IdP and see
# the canonical issuer — measured from the backend's point of view,
# not from this host. The host can reach Keycloak while the container
# cannot (transport problem); the doctor must not call that READY.
$lab = Get-Json "http://127.0.0.1:8000/api/v1/lab/status"
if ($lab) {
    Say "Measured lab status:"
    Say ("  IdP reachable: {0}  issuer matches: {1}  reason: {2}" -f $lab.idp.reachable, $lab.idp.issuer_matches, $lab.idp.reason)
    if ($lab.last_verified_login) {
        Say ("  Last verified real login: {0} user={1}" -f $lab.last_verified_login.at, $lab.last_verified_login.username)
    } else {
        Say "  Last verified real login: NONE YET (no real login verified by this backend process)"
    }
    if (($lab.idp.reachable -eq $true) -and ($lab.idp.issuer_matches -eq $true)) {
        Say "OK   IdP readiness  (backend reaches Keycloak, issuer matches)"
    } else {
        Say "FAIL IdP readiness  (backend cannot reach Keycloak with the canonical issuer — see idp.reason above)"
        Fail "idp-not-ready"
    }
} else {
    Say "FAIL IdP readiness  (no /api/v1/lab/status from the backend)"
    Fail "idp-unknown"
}

if ($Brief) {
    if ($ok) {
        Write-Host "READY"
        exit 0
    }
    Write-Host ("NOT READY: " + ($reasons -join " "))
    exit 1
}

if ($ok) {
    Write-Host "All services healthy and identified. Portal: http://127.0.0.1:5173"
    Write-Host "(Healthy services are not proof of a real login: run .\scripts\test-all.ps1 -Full.)"
    exit 0
}
Write-Host "Some services are NOT healthy."
Write-Host "Troubleshooting: see README.md 'Troubleshooting' and docs/WINDOWS_SETUP.md. Common causes:"
Write-Host "  - Keycloak needs 60-120 s on first boot; wait and re-run .\scripts\doctor.ps1."
Write-Host "  - If the host can reach Keycloak but the BACKEND cannot (IdP readiness FAIL above),"
Write-Host "    that is a backend-to-Keycloak TRANSPORT problem (Compose service DNS / network), not a"
Write-Host "    'wait longer' problem — check the backend logs and the IDENTITYFORGE_IDP_TRANSPORT_BASE route (keycloak:8080)."
exit 1
