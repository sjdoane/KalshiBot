# Registers (or re-registers) the KalshiC0LadderScan scheduled task: the v21
# Candidate C zero-build ladder spot-scan (READ-ONLY, never places orders).
# Lock 3.3 schedule: 09:00 / 14:00 / 20:00 local (PT on this machine), daily.
# The G-C0 gate counts the first 21 scheduled runs (7 days); after the day-7
# scan the task can be removed with:
#   Unregister-ScheduledTask -TaskName KalshiC0LadderScan -Confirm:$false
# Idempotent: unregisters any existing task of the same name first. Run once.

$ErrorActionPreference = "Stop"
$TaskName = "KalshiC0LadderScan"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$PythonExe = Join-Path $ProjectRoot ".venv-kronos\Scripts\python.exe"
$ScanScript = Join-Path $ProjectRoot "scripts\v21\c0_ladder_spotscan.py"

if (-not (Test-Path $PythonExe)) { throw "Python not found: $PythonExe" }
if (-not (Test-Path $ScanScript)) { throw "Scan script not found: $ScanScript" }

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Removing existing $TaskName task..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$Action = New-ScheduledTaskAction -Execute $PythonExe `
    -Argument "`"$ScanScript`" --scheduled" `
    -WorkingDirectory $ProjectRoot

$Triggers = @(
    (New-ScheduledTaskTrigger -Daily -At 9:00am),
    (New-ScheduledTaskTrigger -Daily -At 2:00pm),
    (New-ScheduledTaskTrigger -Daily -At 8:00pm)
)

$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited

# No -StartWhenAvailable (review L-5): a scan missed while logged out is
# simply missed, keeping the pre-registered fixed cadence honest instead of
# running hours off-schedule and still counting toward the 21.
# 60-minute limit: the day-1 probe measured ~20 minutes just to paginate
# 1.17M open markets through the rate-limited client, plus confirm reads.
$Settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 60) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Triggers `
    -Principal $Principal -Settings $Settings `
    -Description "v21 C0 ladder monotonicity spot-scan (read-only, no orders; 21 scans / 7 days per lock 3.3)" | Out-Null

Write-Host "Registered $TaskName (daily 09:00 / 14:00 / 20:00 local)."
$t = Get-ScheduledTask -TaskName $TaskName
"$TaskName state: $($t.State)"
