# IdentityForge setup (PowerShell) — Docker-only path, no Git Bash needed.
# Checks Docker + Compose, copies .env.example to .env, boots the lab.
#
# IF-V4-08: native docker calls go through Invoke-NativeConsole
# (scripts/native-invoke.ps1): under $ErrorActionPreference = 'Stop',
# a bare `docker compose ...` can abort on benign stderr progress
# output in Windows PowerShell 5.1. Start-Process inherits the
# console, so the user still sees docker's output, but no
# ErrorRecord is ever created.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path) | Out-Null
Set-Location ..
. "$PSScriptRoot\native-invoke.ps1"
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Write-Error "Docker is not on PATH. Install Docker Desktop and restart PowerShell."; exit 1 }
$DockerExe = (Get-Command docker).Source
if ((Invoke-NativeConsole -Exe $DockerExe -Arguments @("compose", "version")) -ne 0) { Write-Error "docker compose is not working."; exit 1 }
if (-not (Test-Path .env)) {
    $template = [System.IO.File]::ReadAllText((Resolve-Path '.env.example').Path)
    $pattern = '(?m)^KEYCLOAK_ADMIN_PASSWORD=.*$'

    if ([regex]::Matches($template, $pattern).Count -ne 1) {
        throw 'Expected admin password setting not found exactly once.'
    }

    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }

    $password = [BitConverter]::ToString($bytes).Replace('-', '')
    $content = [regex]::Replace(
        $template,
        $pattern,
        'KEYCLOAK_ADMIN_PASSWORD=' + $password
    )

    [System.IO.File]::WriteAllText(
        (Join-Path (Get-Location).Path '.env'),
        $content,
        (New-Object System.Text.UTF8Encoding($false))
    )

    Write-Host 'Created private .env with a unique random admin password.'
}
if ((Invoke-NativeConsole -Exe $DockerExe -Arguments @("compose", "config", "-q")) -ne 0) { Write-Error "docker compose config failed — fix the Compose files and re-run."; exit 1 }
if ((Invoke-NativeConsole -Exe $DockerExe -Arguments @("compose", "up", "--build", "-d")) -ne 0) { Write-Error "docker compose up failed — see the output above."; exit 1 }
Write-Host "Lab booting. Run .\scripts\doctor.ps1 until all services are healthy (Keycloak needs 60-120 s on first boot)."
Write-Host "Portal: http://127.0.0.1:5173"
