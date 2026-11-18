# IdentityForge reset (PowerShell) — DESTRUCTIVE for synthetic lab data only.
# Removes the Compose containers AND the named Keycloak volume, so the next
# start re-imports the realm and synthetic users from
# keycloak/realm-import/identityforge-lab-realm.json.
# It deletes NO user files, NO real data, and nothing outside this lab:
# the only volume removed is the synthetic Keycloak volume.
# Refuses to run without the explicit switch:  .\scripts\reset.ps1 -Confirm
#
# IF-V4-08: the native docker call goes through Invoke-NativeConsole
# (scripts/native-invoke.ps1) so benign stderr progress output cannot
# abort the script under $ErrorActionPreference = 'Stop' on Windows
# PowerShell 5.1.
param([switch]$Confirm)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path) | Out-Null
Set-Location ..
. "$PSScriptRoot\native-invoke.ps1"

if (-not $Confirm) {
    Write-Host "Refusing to reset without confirmation."
    Write-Host "This destroys the SYNTHETIC Keycloak data volume (realm + test users"
    Write-Host "will be re-imported on next start; backend session/evidence state is"
    Write-Host "also recreated). Nothing else is touched."
    Write-Host ""
    Write-Host "To proceed, run:  .\scripts\reset.ps1 -Confirm"
    exit 1
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Docker / 'docker compose' is not available."
    exit 1
}

Write-Host "Resetting IdentityForge lab (synthetic data only)..."
$DockerExe = (Get-Command docker).Source
if ((Invoke-NativeConsole -Exe $DockerExe -Arguments @("compose", "down", "-v")) -ne 0) { Write-Error "docker compose down -v failed — see the output above."; exit 1 }
Write-Host "Reset complete. Synthetic Keycloak data removed."
Write-Host "Start again with:  .\scripts\start.ps1"
