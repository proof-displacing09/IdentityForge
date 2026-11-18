#!/usr/bin/env bash
# IdentityForge ps1 native-invocation tests (IF-V4-08 + IF-V4-09).
#
# Drives the REAL scripts/native-invoke.ps1 (Invoke-Native,
# Invoke-NativeConsole, ConvertTo-NativeArgument) and the REAL
# Get-NpmAuditClassification from scripts/test-all.ps1 (extracted
# between its IF-V4-09 markers) under PowerShell 7.4.6, with a fake
# native executable on PATH. $ErrorActionPreference = 'Stop' is set
# in the test script: the old `2>&1` form would raise a terminating
# error on benign stderr under Windows PowerShell 5.1, so any throw
# here fails the case outright.
#
# Cases (directive IF-V4-08):
#   1 exit 0 + stderr warning -> rc 0, stdout in log, stderr under
#     the marker, no terminating error
#   2 exit 1 + stderr -> rc 1, stderr captured
#   3 exit 2 + no output -> rc 2, empty logs
#   4 timed-out command -> rc 124, killed within the bound
#   5 path with spaces + Unicode arg -> arrives intact, unsplit
#   6 JSON + newlines on stdout -> verbatim in the log
#   7 -NoStderrMerge -> stdout log stays pure JSON, stderr in .err
#   8 Invoke-NativeConsole exit 0 + stderr warning -> rc 0
#   9 Invoke-NativeConsole exit 1 -> rc 1
#  10-16 Get-NpmAuditClassification: clean / vuln / blocked / DNS /
#     malformed / contradictory rc=0 / timeout rc=124
#  17 test-all.ps1 -Help still exits 0 (dot-source wiring intact)
#  18 relative -LogFile resolves against the PowerShell session
#     location, not the .NET process cwd: pwsh launched from a
#     DIFFERENT directory than the tree must still write the log
#     into the tree's test-results/ (regression for the 2026-11-11
#     preflight failure where logs leaked into the launch dir).
#
# Windows PowerShell 5.1 execution remains NOT RUN (5.1 is
# Windows-only); these runs prove the 7.4.6 paths only. The 5.1
# safety rests on the Start-Process mechanism — see
# scripts/native-invoke.ps1 and docs/REVIEWER_GUIDE.md §7.
#
# Usage: bash scripts/test-ps1-native.sh
# Requires: pwsh (~/workspace/.pwsh/pwsh in this sandbox, or on PATH).
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PASSED=0; FAILED=0; SKIPPED=0
ok()   { PASSED=$((PASSED+1)); echo "PASS: $1"; }
bad()  { FAILED=$((FAILED+1)); echo "FAIL: $1"; }
skip() { SKIPPED=$((SKIPPED+1)); echo "SKIP: $1"; }

PWSH=""
if [ -x "$HOME/workspace/.pwsh/pwsh" ]; then PWSH="$HOME/workspace/.pwsh/pwsh";
elif command -v pwsh >/dev/null 2>&1; then PWSH="$(command -v pwsh)"; fi
if [ -z "$PWSH" ]; then
  skip "pwsh not found — install PowerShell 7.4+ and re-run; Windows reviewer commands are in docs/REVIEWER_GUIDE.md §7"
  echo "ps1-native: $PASSED passed, $FAILED failed, $SKIPPED skipped"
  exit 0
fi
echo "pwsh: $PWSH ($("$PWSH" -NoProfile -Command '$PSVersionTable.PSVersion.ToString()'))"

WORK="$(mktemp -d)"
export IF_WORK="$WORK"

# --- Fake native executable (modes via FAKE_MODE) ---------------------------
cat > "$WORK/fakenative.sh" <<'FAKE'
#!/usr/bin/env bash
case "${FAKE_MODE:-ok-warn}" in
  ok-warn) echo '{"ok":true,"n":1}'; echo "WARNING: benign progress on stderr" >&2; exit 0 ;;
  fail1) echo "some stdout"; echo "real error text" >&2; exit 1 ;;
  fail2) exit 2 ;;
  slow) sleep 30; exit 0 ;;
  echoargs) i=0; for a in "$@"; do echo "arg[$i]=$a"; i=$((i+1)); done; exit 0 ;;
  json) printf '{\n  "auditReportVersion": 2,\n  "vulnerabilities": {},\n  "metadata": {"vulnerabilities": {"high": 0, "critical": 0}}\n}\n'; echo "npm warn: progress on stderr" >&2; exit 0 ;;
esac
FAKE
chmod +x "$WORK/fakenative.sh"

# --- Classifier fixtures -----------------------------------------------------
cat > "$WORK/clean.json" <<'EOF'
{"auditReportVersion":2,"vulnerabilities":{},"metadata":{"vulnerabilities":{"info":0,"low":0,"moderate":0,"high":0,"critical":0,"total":0}}}
EOF
cat > "$WORK/vuln.json" <<'EOF'
{"auditReportVersion":2,"vulnerabilities":{"lru-cache":{"name":"lru-cache","severity":"high"}},"metadata":{"vulnerabilities":{"info":0,"low":1,"moderate":0,"high":1,"critical":0,"total":2}}}
EOF
cat > "$WORK/blocked.json" <<'EOF'
{"error":{"code":"E403","summary":"403 Forbidden","detail":"audit endpoint returned an error policy_denied"}}
EOF
cat > "$WORK/dns.json" <<'EOF'
{"error":{"code":"ENOTFOUND","summary":"request failed","detail":"getaddrinfo ENOTFOUND registry.npmjs.org"}}
EOF
echo "npm error: something unexpected broke (not JSON at all)" > "$WORK/malformed.txt"
: > "$WORK/empty.err"

# --- Extract the classifier region from test-all.ps1 -------------------------
python3 - "$ROOT/scripts/test-all.ps1" "$WORK/classifier.ps1" <<'PY'
import sys
text = open(sys.argv[1]).read()
start = text.index("# --- BEGIN NPM AUDIT CLASSIFIER (IF-V4-09) ---")
end = text.index("# --- END NPM AUDIT CLASSIFIER (IF-V4-09) ---")
open(sys.argv[2], "w").write(text[start:end])
print("classifier region extracted")
PY

# --- The PowerShell test script ----------------------------------------------
cat > "$WORK/native-test.ps1" <<'PS1'
$ErrorActionPreference = "Stop"
$Work = $env:IF_WORK
. "$env:IF_ROOT/scripts/native-invoke.ps1"
. "$Work/classifier.ps1"
$Exe = "$Work/fakenative.sh"
$script:Passed = 0
$script:Failed = 0
function Check($Desc, [bool]$Cond) {
    if ($Cond) { $script:Passed++; Write-Host "PASS: $Desc" }
    else { $script:Failed++; Write-Host "FAIL: $Desc" }
}

# 1. exit 0 + stderr warning: rc 0, stdout in log, stderr under marker, no throw
$env:FAKE_MODE = "ok-warn"
$rc = Invoke-Native -Exe $Exe -Arguments @("compose", "ps", "--format", "json") -LogFile "$Work/c1.log"
$log = Get-Content "$Work/c1.log" -Raw
Check "1 exit 0 + stderr warning returns rc 0" ($rc -eq 0)
Check "1 stdout JSON is in the log" ($log -match '\{"ok":true,"n":1\}')
Check "1 stderr warning is in the log under the marker" (($log -match '--- stderr ---') -and ($log -match 'benign progress on stderr'))

# 2. exit 1 + stderr
$env:FAKE_MODE = "fail1"
$rc = Invoke-Native -Exe $Exe -Arguments @() -LogFile "$Work/c2.log"
$log = Get-Content "$Work/c2.log" -Raw
Check "2 exit 1 + stderr returns rc 1 with stderr captured" (($rc -eq 1) -and ($log -match 'real error text') -and ($log -match 'some stdout'))

# 3. exit 2 + no output
$env:FAKE_MODE = "fail2"
$rc = Invoke-Native -Exe $Exe -Arguments @() -LogFile "$Work/c3.log"
Check "3 exit 2 + no output returns rc 2" ($rc -eq 2)
Check "3 stdout log is empty" ((Get-Item "$Work/c3.log").Length -eq 0)

# 4. timed-out command
$env:FAKE_MODE = "slow"
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$rc = Invoke-Native -Exe $Exe -Arguments @() -LogFile "$Work/c4.log" -TimeoutSeconds 2
$sw.Stop()
Check "4 timed-out command returns rc 124" ($rc -eq 124)
Check "4 timeout kills within the bound (elapsed $([math]::Round($sw.Elapsed.TotalSeconds,1))s < 10s)" ($sw.Elapsed.TotalSeconds -lt 10)

# 5. path with spaces + Unicode + JSON arg arrive intact
$env:FAKE_MODE = "echoargs"
$rc = Invoke-Native -Exe $Exe -Arguments @("C:\path with spaces\repo", "ünïcode arg", '{"a": 1}', "plain") -LogFile "$Work/c5.log"
$log = Get-Content "$Work/c5.log" -Raw
Check "5 spaces/Unicode/JSON args arrive intact and unsplit" (($rc -eq 0) -and ($log -match 'arg\[0\]=C:\\path with spaces\\repo') -and ($log -match 'arg\[1\]=ünïcode arg') -and ($log -match 'arg\[2\]=\{"a": 1\}') -and ($log -match 'arg\[3\]=plain'))

# 6. JSON + newlines on stdout, verbatim
$env:FAKE_MODE = "json"
$rc = Invoke-Native -Exe $Exe -Arguments @() -LogFile "$Work/c6.log"
$log = Get-Content "$Work/c6.log" -Raw
Check "6 multi-line JSON stdout is verbatim in the log" (($rc -eq 0) -and ($log -match '"auditReportVersion": 2') -and ($log -match '"high": 0'))

# 7. -NoStderrMerge keeps the stdout log pure
$env:FAKE_MODE = "json"
$rc = Invoke-Native -Exe $Exe -Arguments @() -LogFile "$Work/c7.log" -NoStderrMerge
$log = Get-Content "$Work/c7.log" -Raw
$err = Get-Content "$Work/c7.log.err" -Raw
Check "7 -NoStderrMerge: stdout log has no stderr marker" (($rc -eq 0) -and ($log -notmatch '--- stderr ---') -and ($log -notmatch 'npm warn'))
Check "7 -NoStderrMerge: stderr lives in the .err file" ($err -match 'npm warn: progress on stderr')
Check "7 -NoStderrMerge: stdout log parses as JSON" (($log | ConvertFrom-Json).auditReportVersion -eq 2)

# 8-9. Invoke-NativeConsole
$env:FAKE_MODE = "ok-warn"
$rc = Invoke-NativeConsole -Exe $Exe -Arguments @("compose", "ps")
Check "8 Invoke-NativeConsole exit 0 + stderr warning returns rc 0" ($rc -eq 0)
$env:FAKE_MODE = "fail1"
$rc = Invoke-NativeConsole -Exe $Exe -Arguments @()
Check "9 Invoke-NativeConsole exit 1 returns rc 1" ($rc -eq 1)

# 10-16. Get-NpmAuditClassification
$c = Get-NpmAuditClassification -LogFile "$Work/clean.json" -ErrFile "$Work/empty.err" -Rc 0
Check "10 classifier: clean JSON rc 0 -> CLEAN" ($c.Status -eq "CLEAN")
$c = Get-NpmAuditClassification -LogFile "$Work/vuln.json" -ErrFile "$Work/empty.err" -Rc 1
Check "11 classifier: vuln JSON rc 1 -> VULNERABILITIES_FOUND" ($c.Status -eq "VULNERABILITIES_FOUND")
$c = Get-NpmAuditClassification -LogFile "$Work/blocked.json" -ErrFile "$Work/empty.err" -Rc 1
Check "12 classifier: blocked JSON rc 1 -> NOT_RUN/BLOCKED" (($c.Status -eq "NOT_RUN") -and ($c.Reason -match "BLOCKED"))
$c = Get-NpmAuditClassification -LogFile "$Work/dns.json" -ErrFile "$Work/empty.err" -Rc 1
Check "13 classifier: DNS JSON rc 1 -> NOT_RUN/DNS" (($c.Status -eq "NOT_RUN") -and ($c.Reason -match "DNS"))
$c = Get-NpmAuditClassification -LogFile "$Work/malformed.txt" -ErrFile "$Work/empty.err" -Rc 1
Check "14 classifier: malformed output rc 1 -> CHECK_FAILED" ($c.Status -eq "CHECK_FAILED")
$c = Get-NpmAuditClassification -LogFile "$Work/vuln.json" -ErrFile "$Work/empty.err" -Rc 0
Check "15 classifier: vuln JSON rc 0 -> CHECK_FAILED (contradiction)" ($c.Status -eq "CHECK_FAILED")
$c = Get-NpmAuditClassification -LogFile "$Work/clean.json" -ErrFile "$Work/empty.err" -Rc 124
Check "16 classifier: rc 124 -> NOT_RUN/TIMEOUT" (($c.Status -eq "NOT_RUN") -and ($c.Reason -match "TIMEOUT"))

Write-Host ""
Write-Host "ps1-native (pwsh): $($script:Passed) passed, $($script:Failed) failed"
if ($script:Failed -gt 0) { exit 1 }
exit 0
PS1

export IF_ROOT="$ROOT"
"$PWSH" -NoProfile -File "$WORK/native-test.ps1" > "$WORK/out.txt" 2>&1
RC=$?
cat "$WORK/out.txt"
if [ "$RC" -eq 0 ]; then
  ok "native wrapper + classifier cases pass under pwsh 7.4.6 (see output above)"
else
  bad "native wrapper + classifier cases failed under pwsh (rc=$RC)"
fi

# --- 17. test-all.ps1 -Help still exits 0 (dot-source wiring intact) --------
"$PWSH" -NoProfile -File "$ROOT/scripts/test-all.ps1" -Help > "$WORK/help.txt" 2>&1
RC=$?
if [ "$RC" -eq 0 ] && grep -q "Usage:" "$WORK/help.txt"; then
  ok "17 test-all.ps1 -Help exits 0 (native-invoke.ps1 dot-source intact)"
else
  bad "17 test-all.ps1 -Help should exit 0 (rc=$RC)"
fi

# --- 18. Relative -LogFile lands in the session location, not the cwd -------
# Regression: [System.IO.Path]::GetFullPath uses the .NET process cwd,
# which Set-Location does NOT update, so a relative log path leaked
# into the launch directory when pwsh was started elsewhere (the
# 2026-11-11 ps1-preflight busy-ports failure). Invoke-Native must
# resolve against the PowerShell session location instead.
mkdir -p "$WORK/tree/test-results" "$WORK/launch"
cat > "$WORK/tree/rel-test.ps1" <<'PS1'
$ErrorActionPreference = "Stop"
. "$env:IF_ROOT/scripts/native-invoke.ps1"
Set-Location "$env:IF_TREE"
$env:FAKE_MODE = "ok-warn"
$rc = Invoke-Native -Exe "$env:IF_WORK/fakenative.sh" -Arguments @() -LogFile "test-results\rel.log"
if ($rc -ne 0) { exit 2 }
exit 0
PS1
export IF_TREE="$WORK/tree"
(cd "$WORK/launch" && "$PWSH" -NoProfile -File "$WORK/tree/rel-test.ps1" > "$WORK/rel-out.txt" 2>&1)
RC=$?
if [ "$RC" -eq 0 ] && [ -f "$WORK/tree/test-results/rel.log" ] \
    && grep -q '"ok":true' "$WORK/tree/test-results/rel.log" \
    && [ ! -e "$WORK/launch/test-results/rel.log" ]; then
  ok "18 relative -LogFile resolves to the session location (tree test-results/), not the launch dir"
else
  bad "18 relative -LogFile must land in the tree test-results/ (rc=$RC)"; cat "$WORK/rel-out.txt" 2>/dev/null; ls -R "$WORK/launch" "$WORK/tree/test-results" 2>/dev/null
fi

echo ""
echo "NOTE: Windows PowerShell 5.1 execution remains NOT RUN (5.1 is Windows-only);"
echo "these runs prove the PowerShell 7.4.6 paths only — see docs/REVIEWER_GUIDE.md §7."
rm -rf "$WORK"
echo ""
echo "ps1-native: $PASSED passed, $FAILED failed, $SKIPPED skipped"
[ "$FAILED" -eq 0 ]
