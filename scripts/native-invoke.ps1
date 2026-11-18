# IdentityForge native-invocation helpers (IF-V4-08, v5).
#
# Shared by scripts/test-all.ps1 (file capture via Invoke-Native)
# and the small console wrappers setup.ps1 / start.ps1 / stop.ps1 /
# reset.ps1 (console output via Invoke-NativeConsole).
#
# WHY: in Windows PowerShell 5.1, merging native stderr into the
# success stream (`2>&1`) wraps each stderr line in an ErrorRecord,
# and with $ErrorActionPreference = 'Stop' that can raise a
# terminating NativeCommandError even when the command SUCCEEDED
# (benign progress on stderr, e.g. `docker compose` progress lines).
# Start-Process avoids PowerShell's stream machinery entirely, so
# the behaviour is identical on PS5.1 and PowerShell 7. The exit
# code comes from the process object (Start-Process does not set
# $LASTEXITCODE).
#
# PROVEN under PowerShell 7.4.6 on Linux (scripts/test-ps1-native.sh
# + scripts/test-ps1-preflight.sh). Windows PowerShell 5.1 execution
# remains NOT RUN (5.1 is Windows-only); the 5.1 safety rests on the
# Start-Process mechanism, the documented version-proof way to run
# native commands. First real 5.1 execution is the reviewer's run —
# see docs/REVIEWER_GUIDE.md §7.
function ConvertTo-NativeArgument([string]$Arg) {
    # Quote one argument for a native command line (MSVC rules):
    # wrap in double quotes when it contains whitespace, a quote or
    # a backslash; escape embedded quotes and trailing backslashes.
    if ($Arg -eq "") { return '""' }
    if ($Arg -notmatch '[\s"\\]') { return $Arg }
    $escaped = $Arg -replace '(\\*)"', '$1$1\"'
    if ($escaped -match '\\$') { $escaped += '\' }
    return '"' + $escaped + '"'
}

function Invoke-Native {
    # Runs a native executable with stdout/stderr captured to
    # SEPARATE files (never merged with 2>&1) and returns the exit
    # code. With -NoStderrMerge the stdout file stays pure (the
    # caller needs it parseable, e.g. `npm audit --json`); stderr
    # then lives in "<LogFile>.err". With -TimeoutSeconds set and the
    # process still running at the deadline, the process is killed
    # (whole tree where .NET supports it) and 124 is returned — the
    # same convention as `timeout` in test-all.sh.
    param(
        [string]$Exe,
        [string[]]$Arguments = @(),
        [string]$LogFile = "",
        [int]$TimeoutSeconds = 0,
        [switch]$NoStderrMerge
    )
    if ($LogFile -eq "") { $LogFile = [System.IO.Path]::GetTempFileName() }
    # Resolve against the PowerShell session location, NOT the .NET
    # process working directory: [System.IO.Path]::GetFullPath uses
    # [Environment]::CurrentDirectory, which Set-Location does NOT
    # update (proven 2026-11-11: Set-Location /tmp leaves
    # CurrentDirectory at the launch dir), so a relative log path
    # would silently land in the launch directory instead of the
    # tree test-all.ps1 cd'd into. GetUnresolvedProviderPathFromPSPath
    # resolves against the session location on PS5.1 and PS7.
    $LogFile = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($LogFile)
    $errFile = "$LogFile.err"
    $proc = Start-Process -FilePath $Exe -ArgumentList (($Arguments | ForEach-Object { ConvertTo-NativeArgument $_ }) -join ' ') -NoNewWindow -PassThru -RedirectStandardOutput $LogFile -RedirectStandardError $errFile
    $null = $proc.Handle  # Keep process handle available on Windows PowerShell 5.1
    # Poll HasExited instead of WaitForExit(): WaitForExit() also waits
    # for the redirected-stream readers to drain, so a grandchild
    # holding the pipe open blocks it past the timeout.
    $deadline = $null
    if ($TimeoutSeconds -gt 0) { $deadline = (Get-Date).AddSeconds($TimeoutSeconds) }
    while (-not $proc.HasExited) {
        if ($deadline -and (Get-Date) -ge $deadline) {
            try { $proc.Kill($true) } catch { try { $proc.Kill() } catch {} }
            $killDeadline = (Get-Date).AddSeconds(5)
            while (-not $proc.HasExited -and (Get-Date) -lt $killDeadline) { Start-Sleep -Milliseconds 100 }
            return 124
        }
        Start-Sleep -Milliseconds 100
    }
    Start-Sleep -Milliseconds 200  # let the redirect files flush
    if (-not $NoStderrMerge) {
        if ((Test-Path $errFile) -and ((Get-Item $errFile).Length -gt 0)) {
            Add-Content -Path $LogFile -Value ""
            Add-Content -Path $LogFile -Value "--- stderr ---"
            Get-Content -Path $errFile | Add-Content -Path $LogFile
        }
    }
    return $proc.ExitCode
}

function Invoke-NativeInMemory {
    # Run native commands whose stdout may contain secrets (for example
    # docker compose config). Read both streams asynchronously to prevent
    # pipe deadlocks; never write their contents to disk or to CI logs.
    # Return only the exit code and stdout for in-memory verification.
    # IF-V4-08: same native argument quoting as Invoke-Native, and no
    # PowerShell native stderr redirection (Windows PowerShell 5.1 safe).
    param(
        [string]$Exe,
        [string[]]$Arguments = @(),
        [int]$TimeoutSeconds = 120
    )
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $Exe
    $info.Arguments = (($Arguments | ForEach-Object { ConvertTo-NativeArgument $_ }) -join ' ')
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true

    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $info
    try {
        if (-not $proc.Start()) { return [PSCustomObject]@{ ExitCode = 1; Output = '' } }
        $outTask = $proc.StandardOutput.ReadToEndAsync()
        $errTask = $proc.StandardError.ReadToEndAsync()
        if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
            try { $proc.Kill() } catch {}
            return [PSCustomObject]@{ ExitCode = 124; Output = '' }
        }
        if (-not $outTask.Wait(10000) -or -not $errTask.Wait(10000)) {
            return [PSCustomObject]@{ ExitCode = 124; Output = '' }
        }
        return [PSCustomObject]@{ ExitCode = [int]$proc.ExitCode; Output = [string]$outTask.Result }
    } catch {
        # Never print an error's arguments or native output, which might
        # contain interpolated environment values. Fail the caller closed.
        return [PSCustomObject]@{ ExitCode = 1; Output = '' }
    } finally {
        $proc.Dispose()
    }
}

function Invoke-NativeConsole {
    # Runs a native executable with stdout/stderr inherited from the
    # console (visible to the user, never captured into PowerShell
    # streams) and returns the exit code. For the small console
    # wrappers (setup/start/stop/reset): the user must see docker's
    # progress, and a benign stderr line must never abort the script
    # under $ErrorActionPreference = 'Stop' on PS5.1.
    param(
        [string]$Exe,
        [string[]]$Arguments = @()
    )
    $proc = Start-Process -FilePath $Exe -ArgumentList (($Arguments | ForEach-Object { ConvertTo-NativeArgument $_ }) -join ' ') -NoNewWindow -Wait -PassThru
    return $proc.ExitCode
}
