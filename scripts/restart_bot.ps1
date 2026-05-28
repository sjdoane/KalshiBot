# One-command restart for the live Kalshi bot.
#
# Stops any running bot, kills the supervisor, lets Task Scheduler
# re-launch (or starts it explicitly), and polls heartbeat until the
# bot is confirmed up. Prints clear status throughout.
#
# Usage:
#   .\scripts\restart_bot.ps1
#
# Optional flags:
#   -SkipStop      do not stop a running bot first (just start if down)
#   -WaitSeconds N seconds to poll for heartbeat after restart (default 180)
#   -Force         skip confirmation prompt (for unattended use)
#
# Exit codes:
#   0  bot confirmed running after restart
#   1  bot did not come back up within WaitSeconds
#   2  user cancelled

param(
    [switch]$SkipStop,
    [int]$WaitSeconds = 180,
    [switch]$Force,
    [switch]$Rebaseline
)

$ErrorActionPreference = "Stop"

$TaskName = "KalshiLiveBot"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$StateDir = Join-Path $ProjectRoot "data\live_trades"
$HeartbeatFile = Join-Path $StateDir "heartbeat.txt"
$StopFile = Join-Path $StateDir "STOP"
$PidFile = Join-Path $StateDir "bot.pid"

function Write-Step {
    param([string]$Message, [string]$Color = "Cyan")
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor $Color
}

function Get-HeartbeatAgeSeconds {
    if (-not (Test-Path $HeartbeatFile)) { return $null }
    try {
        $content = (Get-Content $HeartbeatFile -ErrorAction Stop).Trim()
        if (-not $content) { return $null }
        $hb = [DateTime]::Parse($content).ToUniversalTime()
        $age = ([DateTime]::UtcNow - $hb).TotalSeconds
        return [int]$age
    } catch {
        return $null
    }
}

function Get-BotPid {
    if (-not (Test-Path $PidFile)) { return $null }
    try {
        $pidStr = (Get-Content $PidFile -ErrorAction Stop).Trim()
        if (-not $pidStr) { return $null }
        return [int]$pidStr
    } catch {
        return $null
    }
}

Write-Host ""
Write-Host "Kalshi bot restart" -ForegroundColor Yellow
Write-Host "===================="
Write-Host "Project: $ProjectRoot"
Write-Host "Task:    $TaskName"
Write-Host ""

# Current status snapshot
$currentPid = Get-BotPid
$currentAge = Get-HeartbeatAgeSeconds
if ($null -ne $currentPid) {
    $procAlive = $null -ne (Get-Process -Id $currentPid -ErrorAction SilentlyContinue)
    Write-Host "Current bot PID: $currentPid (process alive: $procAlive)"
} else {
    Write-Host "Current bot PID: (none)"
}
if ($null -ne $currentAge) {
    Write-Host "Last heartbeat:  $currentAge seconds ago"
} else {
    Write-Host "Last heartbeat:  (none)"
}

if (-not $Force) {
    $confirm = Read-Host "`nProceed with restart? [Y/n]"
    if ($confirm -and $confirm.ToLower() -ne "y" -and $confirm.ToLower() -ne "yes" -and $confirm -ne "") {
        Write-Host "Cancelled." -ForegroundColor Yellow
        exit 2
    }
}

# Ensure the scheduled task exists. If a prior install was lost (system
# reboot wiped the per-user task, manual uninstall, fresh machine,
# etc.), Stop-ScheduledTask + Start-ScheduledTask both error with
# "The system cannot find the file specified." Auto-install rather
# than fail confusingly.
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $task) {
    Write-Step "Scheduled task '$TaskName' not found; installing it now"
    $installScript = Join-Path $PSScriptRoot "install_scheduled_task.ps1"
    if (-not (Test-Path $installScript)) {
        Write-Host "ERROR: cannot find install_scheduled_task.ps1 at $installScript" -ForegroundColor Red
        exit 1
    }
    & $installScript
    # Re-fetch; bail if still missing.
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -eq $task) {
        Write-Host "ERROR: install_scheduled_task.ps1 ran but task still not present." -ForegroundColor Red
        exit 1
    }
    Write-Host "Task installed."
}

# Stage 1: stop
if (-not $SkipStop) {
    Write-Step "Stopping supervisor (creating STOP file)"
    New-Item -ItemType File -Path $StopFile -Force | Out-Null
    Write-Host "STOP file created at $StopFile"

    Write-Step "Stopping Task Scheduler task '$TaskName'"
    try {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction Stop
        Write-Host "Task stopped."
    } catch {
        Write-Host "(Task was not running.)"
    }

    # Kill the bot process if it's still alive (the supervisor's SIGTERM
    # handler would have cancelled resting orders, but on hard stop
    # we ensure it's gone before relaunch). Also kill any orphan bots
    # whose pids we don't know about (defense against the supervisor-
    # spawns-twice bug).
    $OrphanPids = @()
    try {
        $OrphanPids = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'uv.exe'" |
            Where-Object { $_.CommandLine -like "*paper_trade_favorite*--mode*live*" } |
            Select-Object -ExpandProperty ProcessId
    } catch {}

    $AllPidsToStop = @($currentPid) + $OrphanPids | Where-Object { $_ -ne $null } | Sort-Object -Unique
    foreach ($p in $AllPidsToStop) {
        $proc = Get-Process -Id $p -ErrorAction SilentlyContinue
        if ($null -ne $proc) {
            Write-Step "Stopping process PID $p ($($proc.ProcessName))"
            try {
                Stop-Process -Id $p -Force -ErrorAction Stop
                Write-Host "Process $p stopped."
            } catch {
                Write-Host "Could not stop $p : $($_.Exception.Message)" -ForegroundColor Yellow
            }
        }
    }

    # Verify all are gone before proceeding.
    if ($AllPidsToStop.Count -gt 0) {
        Write-Step "Verifying all bot processes are gone"
        $maxWait = 15
        $waited = 0
        while ($waited -lt $maxWait) {
            Start-Sleep -Seconds 1
            $waited += 1
            $stillAlive = $AllPidsToStop | Where-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue }
            if ($stillAlive.Count -eq 0) {
                Write-Host "All bot processes confirmed dead (waited ${waited}s)."
                break
            }
        }
        if ($waited -ge $maxWait) {
            Write-Host "WARNING: some bot processes still alive after ${maxWait}s." -ForegroundColor Yellow
            Write-Host "  Survivors: $($stillAlive -join ', ')"
        }
    }

    # Clean stale lock so the new bot can acquire it.
    $LockFile = Join-Path $StateDir "bot.lock"
    Remove-Item -Path $LockFile -Force -ErrorAction SilentlyContinue
    Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue

    Write-Step "Removing STOP file"
    Remove-Item -Path $StopFile -Force -ErrorAction SilentlyContinue
    Write-Host "STOP file removed; supervisor can re-enter its loop on next launch."
}

# Stage 2: start
if ($Rebaseline) {
    Write-Step "Setting REBASELINE flag for next bot launch"
    $RebaselineFlag = Join-Path $StateDir "REBASELINE"
    New-Item -ItemType File -Path $RebaselineFlag -Force | Out-Null
    Write-Host "REBASELINE flag file created at $RebaselineFlag"
    Write-Host "The bot's supervisor will pass --rebaseline to force a fresh"
    Write-Host "Kalshi balance read, then remove the flag automatically."
}

Write-Step "Starting Task Scheduler task '$TaskName'"
Start-ScheduledTask -TaskName $TaskName
Write-Host "Start command issued. Bot will run preflight + begin trading."

# Stage 3: poll for heartbeat
Write-Step "Waiting for heartbeat (up to $WaitSeconds seconds)"
$startWait = Get-Date
$lastHeartbeatTs = $currentAge

while ($true) {
    Start-Sleep -Seconds 5
    $elapsed = [int]([DateTime]::UtcNow - $startWait.ToUniversalTime()).TotalSeconds
    $age = Get-HeartbeatAgeSeconds
    $newPid = Get-BotPid

    # Heartbeat is "fresh" if its age is less than the time we've been waiting.
    # That means it was updated AFTER we started polling, i.e. the new bot is alive.
    if ($null -ne $age -and $age -lt $elapsed + 10) {
        $procAlive = $null -ne (Get-Process -Id $newPid -ErrorAction SilentlyContinue)
        Write-Host ""
        Write-Host "Bot is UP." -ForegroundColor Green
        Write-Host "  PID:                  $newPid (process alive: $procAlive)"
        Write-Host "  Heartbeat age:        $age seconds"
        Write-Host "  Time to come online:  $elapsed seconds"
        Write-Host ""
        Write-Host "Logs:" -ForegroundColor Gray
        Write-Host "  Get-Content data\live_trades\logs\live.log -Tail 30 -Wait"
        Write-Host "  Get-Content data\live_trades\logs\launcher.log -Tail 30"
        Write-Host ""
        Write-Host "Dashboard:" -ForegroundColor Gray
        Write-Host "  .\scripts\dashboard.ps1"
        exit 0
    }

    if ($elapsed -ge $WaitSeconds) {
        Write-Host ""
        Write-Host "Bot did NOT come up within $WaitSeconds seconds." -ForegroundColor Red
        Write-Host ""
        Write-Host "Last 20 launcher log lines:" -ForegroundColor Gray
        if (Test-Path (Join-Path $StateDir "logs\launcher.log")) {
            Get-Content (Join-Path $StateDir "logs\launcher.log") -Tail 20
        } else {
            Write-Host "(no launcher.log yet)"
        }
        Write-Host ""
        Write-Host "Last 20 bot stderr lines:" -ForegroundColor Gray
        if (Test-Path (Join-Path $StateDir "logs\bot-stderr.log")) {
            Get-Content (Join-Path $StateDir "logs\bot-stderr.log") -Tail 20
        } else {
            Write-Host "(no bot-stderr.log yet)"
        }
        Write-Host ""
        Write-Host "Common causes:"
        Write-Host "  - Preflight failure (clock skew, balance, no orphan check)"
        Write-Host "  - DNS / network not yet up (transient; rerun should succeed)"
        Write-Host "  - .env LIVE_ENABLED is not 'true'"
        Write-Host ""
        Write-Host "Re-run this script to try again, or check Task Scheduler:"
        Write-Host "  .\scripts\install_scheduled_task.ps1 -Status"
        exit 1
    }

    if ($elapsed % 30 -eq 0) {
        Write-Host "  ...waiting ($elapsed/$WaitSeconds seconds elapsed)"
    }
}
