# Persistent launcher for the v16 lead-lag SHADOW LOGGER (record-only).
#
# Wraps scripts\v16\shadow_logger.py with:
# - Auto-restart on crash (exponential backoff, capped at 5 min)
# - Supervisor double-launch guard + daemon single-instance lock
# - PID file at data\v16\shadow\shadow_bot.pid
# - Stop-file mechanism: create data\v16\shadow\STOP to gracefully exit
# - Launcher events appended to data\v16\shadow\logs\launcher.log
#
# Designed to be invoked by Windows Task Scheduler (KalshiShadowLogger). Also
# runnable manually. The logger places NO orders; it only reads odds + Kalshi
# orderbooks and appends record rows. It is safe to run alongside v1.
#
# Runs on .venv-kronos (the one fully-intact venv; the project .venv pandas and
# the pit-backtest venv pydantic_core are both currently damaged by interrupted
# uv syncs). .venv-kronos has pandas + pydantic + httpx + cryptography all
# working, which is exactly what the logger imports.
#
# Stop instructions:
#   1. Graceful: New-Item "data\v16\shadow\STOP" -ItemType File
#   2. Force:    Stop-Process -Id (Get-Content "data\v16\shadow\shadow_bot.pid")

$ErrorActionPreference = "Continue"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $ProjectRoot

$StateDir = Join-Path $ProjectRoot "data\v16\shadow"
$LogDir = Join-Path $StateDir "logs"
$LauncherLog = Join-Path $LogDir "launcher.log"
$BotStderrLog = Join-Path $LogDir "bot-stderr.log"
$BotStdoutLog = Join-Path $LogDir "bot-stdout.log"
$StopFile = Join-Path $StateDir "STOP"
$PidFile = Join-Path $StateDir "shadow_bot.pid"
$SupervisorPidFile = Join-Path $StateDir "shadow_supervisor.pid"

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
    $delay = 30 * [Math]::Pow(2, [Math]::Min($AttemptIndex, 4))
    return [Math]::Min($delay, 300)
}

Write-LauncherLog "shadow-logger supervisor starting; ProjectRoot=$ProjectRoot"

# Supervisor double-launch guard (mirrors run_v14_bot.ps1). If another
# run_shadow_logger.ps1 supervisor (different PID) is alive, this one exits.
if (Test-Path $SupervisorPidFile) {
    $existing = Get-Content $SupervisorPidFile -ErrorAction SilentlyContinue
    if ($existing) {
        $p = Get-Process -Id ([int]$existing) -ErrorAction SilentlyContinue
        if ($p -and $p.ProcessName -eq 'powershell' -and $p.Id -ne $PID) {
            Write-LauncherLog "Another shadow supervisor already running (PID $existing); exiting."
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

while ($true) {
    if (Test-Path $StopFile) {
        Write-LauncherLog "STOP file detected; exiting supervisor loop"
        break
    }

    Write-LauncherLog "Launching shadow logger..."
    $PythonExe = Join-Path $ProjectRoot ".venv-kronos\Scripts\python.exe"
    $LoggerScript = Join-Path $ProjectRoot "scripts\v16\shadow_logger.py"
    $QuotedScript = "`"$LoggerScript`""

    $proc = Start-Process -FilePath $PythonExe `
        -ArgumentList "-u $QuotedScript" `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardError $BotStderrLog `
        -RedirectStandardOutput $BotStdoutLog `
        -PassThru `
        -NoNewWindow

    Set-Content -Path $PidFile -Value $proc.Id -Encoding ascii
    Write-LauncherLog "Logger started; PID=$($proc.Id)"

    while (-not $proc.HasExited) {
        if (Test-Path $StopFile) {
            Write-LauncherLog "STOP file appeared; sending Stop-Process to logger PID $($proc.Id)"
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
    Write-LauncherLog "Logger exited; ExitCode=$exitCode"

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
Write-LauncherLog "shadow-logger supervisor exiting cleanly"
