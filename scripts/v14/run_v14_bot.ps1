# Persistent launcher for the v14 MLB-night sportsbook lead-lag bot.
#
# Wraps the v14 daemon with:
# - Auto-restart on crash (exponential backoff, capped at 5 min)
# - PID file at data\v14\v14_bot.pid
# - Stop-file mechanism: create data\v14\STOP to gracefully exit
# - Launcher events appended to data\v14\logs\launcher.log
#
# Designed to be invoked by Windows Task Scheduler. Also runnable manually.
#
# Stop instructions:
#   1. Quick stop (supervisor + daemon):
#        New-Item "data\v14\STOP" -ItemType File
#   2. Force kill running daemon:
#        Get-Content "data\v14\v14_bot.pid"
#        Stop-Process -Id <pid>
#
# v14 daemon parameters are baked into src\kalshi_bot_v14\daemon.py (capital
# cap $12.80, X_THRESHOLD 60bp, 15-min loop, etc.). To change parameters,
# edit daemon.py and restart this supervisor.

$ErrorActionPreference = "Continue"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $ProjectRoot

$StateDir = Join-Path $ProjectRoot "data\v14"
$LogDir = Join-Path $StateDir "logs"
$LauncherLog = Join-Path $LogDir "launcher.log"
$BotStderrLog = Join-Path $LogDir "bot-stderr.log"
$BotStdoutLog = Join-Path $LogDir "bot-stdout.log"
$StopFile = Join-Path $StateDir "STOP"
$PidFile = Join-Path $StateDir "v14_bot.pid"

New-Item -ItemType Directory -Path $StateDir -Force | Out-Null
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

function Write-LauncherLog {
    param([string]$Message)
    $ts = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    $line = "[$ts] $Message"
    Add-Content -Path $LauncherLog -Value $line -Encoding utf8
    Write-Host $line
}

function Get-NextBackoffSeconds {
    param([int]$AttemptIndex)
    # Exponential backoff: 30, 60, 120, 240, 300, 300, 300, ...
    $delay = 30 * [Math]::Pow(2, [Math]::Min($AttemptIndex, 4))
    return [Math]::Min($delay, 300)
}

Write-LauncherLog "v14 supervisor starting; ProjectRoot=$ProjectRoot"

# SUPERVISOR DOUBLE-LAUNCH GUARD. Mirrors run_live_bot.ps1. Without this,
# Task Scheduler restart-on-failure + logon triggers spawned MULTIPLE
# concurrent supervisors (observed 2026-05-29), each launching its own
# daemon -> multi-daemon double-placement before the daemon lock existed.
# If another run_v14_bot.ps1 supervisor (different PID) is already alive,
# this one exits immediately. The daemon-level single_instance lock is the
# last line of defense; this guard prevents the wasteful supervisor churn.
$SupervisorPidFile = Join-Path $StateDir "v14_supervisor.pid"
if (Test-Path $SupervisorPidFile) {
    $existing = Get-Content $SupervisorPidFile -ErrorAction SilentlyContinue
    if ($existing) {
        $p = Get-Process -Id ([int]$existing) -ErrorAction SilentlyContinue
        if ($p -and $p.ProcessName -eq 'powershell' -and $p.Id -ne $PID) {
            Write-LauncherLog "Another v14 supervisor already running (PID $existing); exiting."
            exit 0
        }
    }
}
Set-Content -Path $SupervisorPidFile -Value $PID -Encoding ascii

if (Test-Path $StopFile) {
    Write-LauncherLog "STOP file present at launcher start; removing it (operator must re-create to stop)"
    Remove-Item $StopFile -Force
}

$env:PYTHONPATH = Join-Path $ProjectRoot "src"

$ConsecutiveFailures = 0
$MaxConsecutiveFailures = 99
$StartTime = Get-Date

while ($true) {
    if (Test-Path $StopFile) {
        Write-LauncherLog "STOP file detected; exiting supervisor loop"
        break
    }

    Write-LauncherLog "Launching v14 daemon..."
    $PythonExe = Join-Path $ProjectRoot ".venv-kronos\Scripts\python.exe"
    $DaemonScript = Join-Path $ProjectRoot "scripts\v14\v14_daemon.py"

    # Quote the script path because it contains a space ("AI Projects").
    # Without quoting, Start-Process passes split args and Python fails to
    # open the truncated path.
    $QuotedScript = "`"$DaemonScript`""
    $proc = Start-Process -FilePath $PythonExe `
        -ArgumentList "-u $QuotedScript" `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardError $BotStderrLog `
        -RedirectStandardOutput $BotStdoutLog `
        -PassThru `
        -NoNewWindow

    Set-Content -Path $PidFile -Value $proc.Id -Encoding ascii
    Write-LauncherLog "Daemon started; PID=$($proc.Id)"

    # Wait for the daemon to exit OR the STOP file to appear
    while (-not $proc.HasExited) {
        if (Test-Path $StopFile) {
            Write-LauncherLog "STOP file appeared; sending Stop-Process to daemon PID $($proc.Id)"
            try {
                Stop-Process -Id $proc.Id -Force -ErrorAction Stop
            } catch {
                Write-LauncherLog "Stop-Process failed: $_"
            }
            break
        }
        Start-Sleep -Seconds 5
    }

    $exitCode = if ($proc.HasExited) { $proc.ExitCode } else { -1 }
    Write-LauncherLog "Daemon exited; ExitCode=$exitCode"

    if (Test-Path $StopFile) {
        break
    }

    if ($exitCode -eq 0) {
        Write-LauncherLog "Clean exit; restart in 30s"
        $ConsecutiveFailures = 0
        Start-Sleep -Seconds 30
    } else {
        $ConsecutiveFailures++
        if ($ConsecutiveFailures -ge $MaxConsecutiveFailures) {
            Write-LauncherLog "Reached MaxConsecutiveFailures=$MaxConsecutiveFailures; exiting supervisor"
            break
        }
        $backoff = Get-NextBackoffSeconds -AttemptIndex ($ConsecutiveFailures - 1)
        Write-LauncherLog "Crash detected (failure #$ConsecutiveFailures); backing off $backoff s"
        Start-Sleep -Seconds $backoff
    }
}

if (Test-Path $PidFile) {
    Remove-Item $PidFile -Force
}
Write-LauncherLog "v14 supervisor exiting cleanly"
