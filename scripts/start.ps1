# IdentityForge start (PowerShell).
#
# IF-V4-08: the native docker call goes through Invoke-NativeConsole
# (scripts/native-invoke.ps1) so benign stderr progress output cannot
# abort the script under $ErrorActionPreference = 'Stop' on Windows
# PowerShell 5.1.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path) | Out-Null
Set-Location ..
. "$PSScriptRoot\native-invoke.ps1"
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Write-Error "Docker is not on PATH. Install Docker Desktop and restart PowerShell."; exit 1 }
$DockerExe = (Get-Command docker).Source
if ((Invoke-NativeConsole -Exe $DockerExe -Arguments @("compose", "up", "-d")) -ne 0) { Write-Error "docker compose up failed — see the output above."; exit 1 }
.\scripts\doctor.ps1
