# One-shot installer for the Windows Task Scheduler task "KalshiV14Bot".
#
# Registers a task that:
# - Runs at user logon
# - Launches scripts\v14\run_v14_bot.ps1 (the supervisor)
# - Restarts on failure (1 minute interval, 99 retries)
# - Runs as the current user (no admin required)
#
# Idempotent: re-running this script unregisters then re-registers the task.
#
# To run:
#   .venv-kronos\Scripts\python.exe (irrelevant - this is pure PS)
#   PowerShell:
#     cd "C:\Users\SamJD\OneDrive\Desktop\AI Projects\Project Kalshi"
#     .\scripts\v14\install_v14_task.ps1
#
# To uninstall:
#   Unregister-ScheduledTask -TaskName "KalshiV14Bot" -Confirm:$false

$ErrorActionPreference = "Stop"
$TaskName = "KalshiV14Bot"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$SupervisorScript = Join-Path $ProjectRoot "scripts\v14\run_v14_bot.ps1"

if (-not (Test-Path $SupervisorScript)) {
    Write-Error "Supervisor script not found: $SupervisorScript"
    exit 2
}

Write-Host "Installing scheduled task: $TaskName"
Write-Host "  Project root: $ProjectRoot"
Write-Host "  Supervisor:   $SupervisorScript"

# Unregister if already exists
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "  Existing task found; unregistering first..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$SupervisorScript`"" `
    -WorkingDirectory $ProjectRoot

$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# Settings: restart on failure, run only when network is available
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 99 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Days 365)

$Principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "v14 MLB-night sportsbook lead-lag bot (auto-restart on crash; reboot survival)"

Write-Host "Task '$TaskName' registered."
Write-Host ""
Write-Host "Verify:"
Write-Host "  Get-ScheduledTask -TaskName '$TaskName' | Select-Object TaskName, State"
Write-Host ""
Write-Host "Start now (also fires at next logon automatically):"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "Stop:"
Write-Host "  New-Item 'data\v14\STOP' -ItemType File   # graceful"
Write-Host "  Stop-ScheduledTask -TaskName '$TaskName'  # immediate"
Write-Host ""
Write-Host "Logs:"
Write-Host "  data\v14\logs\launcher.log   (supervisor events)"
Write-Host "  data\v14\logs\bot-stdout.log (daemon stdout)"
Write-Host "  data\v14\logs\bot-stderr.log (daemon stderr)"
Write-Host "  data\v14\v14_trades.jsonl    (structured event log)"
