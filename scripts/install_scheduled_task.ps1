# Install/uninstall a Windows Scheduled Task that runs the LIVE Kalshi
# bot's persistent launcher (run_live_bot.ps1) automatically.
#
# Task properties:
# - Runs at user logon
# - Hidden window (no popup)
# - Restart on failure (every 1 min, up to 99 retries)
# - Does NOT require admin (per-user scheduled task)
# - Stop with: schtasks /End /TN "KalshiLiveBot"
# - Disable with: .\scripts\install_scheduled_task.ps1 -Uninstall
#
# Usage:
#   .\scripts\install_scheduled_task.ps1            # install (default)
#   .\scripts\install_scheduled_task.ps1 -Uninstall # remove the task
#   .\scripts\install_scheduled_task.ps1 -Start     # start it now without waiting for logon
#   .\scripts\install_scheduled_task.ps1 -Status    # show task state

param(
    [switch]$Uninstall,
    [switch]$Start,
    [switch]$Status
)

$ErrorActionPreference = "Stop"

$TaskName = "KalshiLiveBot"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LauncherPath = Join-Path $ProjectRoot "scripts\run_live_bot.ps1"

if ($Status) {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -eq $task) {
        Write-Host "Task '$TaskName' is NOT installed."
        exit 0
    }
    Write-Host "Task '$TaskName' state: $($task.State)"
    $info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($info) {
        Write-Host "  Last run:    $($info.LastRunTime)"
        Write-Host "  Last result: $($info.LastTaskResult)"
        Write-Host "  Next run:    $($info.NextRunTime)"
    }
    exit 0
}

if ($Uninstall) {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -eq $task) {
        Write-Host "Task '$TaskName' not installed; nothing to remove."
        exit 0
    }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Task '$TaskName' uninstalled."
    exit 0
}

if (-not (Test-Path $LauncherPath)) {
    Write-Host "ERROR: launcher script not found at $LauncherPath"
    exit 1
}

# Build the task definition.
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$LauncherPath`"" `
    -WorkingDirectory $ProjectRoot

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# Wake up to repeat every 5 minutes "if not already running" via secondary trigger;
# the launcher itself handles double-launch via PID file.
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 99 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 1825) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive

$task = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description "Auto-restart launcher for Project Kalshi live trading bot. See scripts/run_live_bot.ps1."

# Replace any existing task.
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}
Register-ScheduledTask -TaskName $TaskName -InputObject $task | Out-Null
Write-Host "Task '$TaskName' installed."
Write-Host "Launcher path: $LauncherPath"
Write-Host "Project root:  $ProjectRoot"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  Start now:           .\scripts\install_scheduled_task.ps1 -Start"
Write-Host "  Status check:        .\scripts\install_scheduled_task.ps1 -Status"
Write-Host "  Uninstall:           .\scripts\install_scheduled_task.ps1 -Uninstall"
Write-Host "  Pause bot only:      New-Item data\live_trades\STOP -ItemType File"
Write-Host "  Resume bot:          Remove-Item data\live_trades\STOP"

if ($Start) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host ""
    Write-Host "Task '$TaskName' started."
}
