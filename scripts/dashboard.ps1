# Quick-launch the Kalshi bot monitor dashboard.
#
# Read-only Streamlit app. Reads the bot's state.json, kill_state.json,
# heartbeat.txt, live.log, and v5_filter_shadow_log.jsonl. Does NOT
# modify any of the bot's state. Safe to run alongside the live bot.
#
# Default port: 8501. Opens in your default browser.
#
# Usage:
#   .\scripts\dashboard.ps1
#
# Stop with Ctrl-C.

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "Starting Kalshi Bot Monitor dashboard..."
Write-Host "Default URL: http://localhost:8501"
Write-Host "Stop with Ctrl-C."
Write-Host ""

& uv run streamlit run scripts/dashboard.py --server.headless false --server.runOnSave false
