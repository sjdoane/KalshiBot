# Regenerate the v1 performance dashboard + CSV (read-only). Invoked by the
# KalshiPerfDashboard scheduled task every 20 min and at logon. Safe to run
# alongside the live bot: it only READS data/live_trades/state.json and writes
# data/live_trades/perf_dashboard.html + perf_log.csv (no bot state touched).
$Root = "C:\Users\SamJD\OneDrive\Desktop\AI Projects\Project Kalshi"
Set-Location $Root
$LogDir = Join-Path $Root "data\live_trades\logs"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$Log = Join-Path $LogDir "perf_dashboard.log"
$ts = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
& "$Root\.venv-kronos\Scripts\python.exe" -m scripts.v20.perf_dashboard *>> $Log
Add-Content -Path $Log -Value "[$ts] regenerated (exit $LASTEXITCODE)" -Encoding utf8
