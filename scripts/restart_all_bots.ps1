# One-shot restart for BOTH bots (v1 + v14).
#
# Equivalent to running these by hand:
#   Remove-Item .\data\live_trades\STOP -Force -ErrorAction SilentlyContinue
#   Remove-Item .\data\v14\STOP -Force -ErrorAction SilentlyContinue
#   .\scripts\restart_bot.ps1 -Force
#   Stop-ScheduledTask -TaskName KalshiV14Bot
#   Start-ScheduledTask -TaskName KalshiV14Bot
#
# After both bots restart the script prints final task state so the
# operator can confirm they're both running.
#
# Usage:
#   .\scripts\restart_all_bots.ps1
#
# This script does NOT add Defender exclusions; that requires an
# admin shell (see CLAUDE.md). Run that separately if needed.

$ErrorActionPreference = "Continue"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "=== $Message ===" -ForegroundColor Cyan
}

Write-Step "Removing STOP files (if present)"
$v1Stop = Join-Path $ProjectRoot "data\live_trades\STOP"
$v14Stop = Join-Path $ProjectRoot "data\v14\STOP"
foreach ($f in @($v1Stop, $v14Stop)) {
    if (Test-Path $f) {
        Remove-Item $f -Force -ErrorAction SilentlyContinue
        Write-Host "Removed: $f"
    }
}

Write-Step "Restarting v1 (KalshiLiveBot)"
& (Join-Path $ProjectRoot "scripts\restart_bot.ps1") -Force

Write-Step "Restarting v14 (KalshiV14Bot)"
try {
    Stop-ScheduledTask -TaskName "KalshiV14Bot" -ErrorAction Stop
    Write-Host "v14 task stop issued"
} catch {
    Write-Host "v14 task was not running"
}
Start-Sleep -Seconds 3
try {
    Start-ScheduledTask -TaskName "KalshiV14Bot" -ErrorAction Stop
    Write-Host "v14 task start issued"
} catch {
    Write-Host "Failed to start v14: $($_.Exception.Message)" -ForegroundColor Yellow
}

Write-Step "Final task state"
Get-ScheduledTask -TaskName "KalshiLiveBot", "KalshiV14Bot" -ErrorAction SilentlyContinue |
    Format-Table TaskName, State

Write-Step "Quick heartbeat check"
$v1Hb = Join-Path $ProjectRoot "data\live_trades\heartbeat.txt"
if (Test-Path $v1Hb) {
    $ts = Get-Content $v1Hb -ErrorAction SilentlyContinue
    Write-Host "v1 last heartbeat: $ts"
} else {
    Write-Host "v1 heartbeat file not yet written (expected on first launch)"
}
$v14Log = Join-Path $ProjectRoot "data\v14\v14_trades.jsonl"
if (Test-Path $v14Log) {
    $last = Get-Content $v14Log -Tail 1 -ErrorAction SilentlyContinue
    if ($last) {
        Write-Host "v14 last jsonl event (truncated):"
        Write-Host "  $($last.Substring(0, [Math]::Min($last.Length, 200)))..."
    }
}

Write-Host ""
Write-Host "Done. Watch Discord for the next heartbeat (~15 min on v1; v14 only during 18:00-06:00 UTC active window)." -ForegroundColor Green
