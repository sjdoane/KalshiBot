# Persistent launcher for the LIVE Kalshi bot.
#
# Wraps `uv run python -m scripts.paper_trade_favorite --mode live ...` with:
# - Auto-restart on crash (exponential backoff, capped at 5 min)
# - PID file at data/live_trades/bot.pid for easy stop
# - Stop-file mechanism: create data/live_trades/STOP to gracefully exit
#   the supervisor loop (the bot itself still gets SIGTERM and runs its
#   cancel-all-resting handler)
# - All bot stdout/stderr append to data/live_trades/logs/launcher.log
#
# Designed to be invoked by Windows Task Scheduler. Also runnable manually.
#
# Defaults (operator-authorized post-go-live, 2026-05-23):
#   - Bankroll:        auto-read from Kalshi at startup (2026-05-24 change).
#                       The supervisor no longer hardcodes a value; the bot
#                       calls /portfolio/balance at startup and adds the
#                       notional value of any open positions. Persists to
#                       state.json so drawdown calc is stable across
#                       restarts. Use `--rebaseline` to force re-read
#                       after deposits/withdrawals.
#   - Max concurrent:  auto (2026-05-24 dynamic-cap change). The bot
#                       computes the cap each loop from
#                       (cash_balance + open_positions_notional) /
#                       FAVORITE_UPPER_CAP. At $32 bankroll with $0.95
#                       per-trade ceiling this lands around 33-34 when
#                       no positions are deployed, and drops smoothly
#                       as positions consume bankroll. As wins
#                       accumulate and bankroll grows past $32, the
#                       cap auto-raises. As losses occur, it
#                       auto-shrinks. Self-sizing.
#   - Preflight buffer: BALANCE_PREFLIGHT_MULTIPLIER=1.0 (was hardcoded 2.0
#                       per the live-mode critic). Operator explicit risk
#                       acceptance "willing to lose all $32" overrides
#                       the 2x safety buffer. The KILL trigger at 20%
#                       drawdown remains armed as the primary stop-loss.
#   - Shadow-mode:     SHADOW_MODE_ENABLED=true; v5 Track A combined
#                       filter logs decisions to
#                       data/live_trades/v5_filter_shadow_log.jsonl.
#   - Live filter:     LIVE_FILTER_ENABLED=true (2026-05-24); the v5
#                       filter SKIPS candidates when it says fade. v1's
#                       trade behavior IS changed for the first time:
#                       trades v1 would have made are dropped if the
#                       filter has confident-fade signal from Polymarket
#                       or sportsbook. Failure mode is safe (filter
#                       abstains -> v1 normal logic).
#   - Min net edge:    $0.01 per contract
#   - Cadence:         900 seconds (15 min)
#   - Max lifetime:    180 days. Per research/time-scale-analysis.md,
#                       sub-180d eligible markets have 100% YES rate
#                       across n=39 with bootstrap CI [+10.33pp,
#                       +14.63pp]. Above 180d the CI includes zero and
#                       holds the single -81pp catastrophic loss in
#                       the dataset. Capital efficiency is also ~8x
#                       higher (130% annualized at 30-90d vs 16% at
#                       180-365d).
#
# Stop instructions:
#   1. Quick stop (just supervisor; bot keeps running):
#        New-Item "data\live_trades\STOP" -ItemType File
#   2. Full stop (supervisor + bot):
#        # find PID:
#        Get-Content "data\live_trades\bot.pid"
#        # then:
#        Stop-Process -Id <pid>
#      The bot's SIGTERM handler will attempt cancel-all-resting before exit.

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$StateDir = Join-Path $ProjectRoot "data\live_trades"
$LogDir = Join-Path $StateDir "logs"
$LauncherLog = Join-Path $LogDir "launcher.log"
# Bot stderr goes here (separate from launcher.log to avoid file-lock
# races: Start-Process -RedirectStandardError holds the target file
# open exclusively for the lifetime of the bot subprocess, so the
# launcher cannot Add-Content to the same file while bot is running).
$BotStderrLog = Join-Path $LogDir "bot-stderr.log"
$StopFile = Join-Path $StateDir "STOP"
$PidFile = Join-Path $StateDir "bot.pid"

New-Item -ItemType Directory -Path $StateDir -Force | Out-Null
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

function Write-LauncherLog {
    param([string]$Message)
    $ts = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    $line = "[$ts] $Message"
    Add-Content -Path $LauncherLog -Value $line -Encoding utf8
}

# Stop-file path: if it exists at launcher startup, refuse to start.
# (Operator must delete it to resume.)
if (Test-Path $StopFile) {
    Write-LauncherLog "STOP file present at $StopFile; refusing to start. Delete it to resume."
    exit 1
}

# Don't double-launch: if PID file exists and process is alive, exit.
if (Test-Path $PidFile) {
    $existingPid = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($existingPid -and (Get-Process -Id $existingPid -ErrorAction SilentlyContinue)) {
        Write-LauncherLog "Bot already running with PID $existingPid; exiting."
        exit 0
    }
}

Write-LauncherLog "Launcher starting. ProjectRoot=$ProjectRoot"

$BackoffSeconds = 5
$MaxBackoff = 300

while ($true) {
    if (Test-Path $StopFile) {
        Write-LauncherLog "STOP file detected; exiting launcher loop."
        break
    }

    # Enable v5 Track A shadow-mode + active filter (operator-authorized
    # 2026-05-24 for live testing). The v5 combined filter (Polymarket +
    # sportsbook + cross-market consistency) logs decisions to JSONL AND
    # actively skips v1 candidates when it says fade. v1's trade
    # behavior IS changed; the filter is the active overlay.
    # Failure mode: if any fetcher misses or the filter cannot evaluate,
    # the candidate falls through to v1's normal eligibility logic.
    $env:SHADOW_MODE_ENABLED = "true"
    $env:LIVE_FILTER_ENABLED = "true"
    # Preflight balance buffer multiplier. Default in code is 1.0 (was
    # hardcoded 2.0 per the live-mode critic; lowered 2026-05-24 per
    # operator's "willing to lose all $32" risk acceptance). Set
    # explicitly here for clarity even though 1.0 is the new default.
    $env:BALANCE_PREFLIGHT_MULTIPLIER = "1.0"

    # Dynamic 60/40 capital split: v1 deploys at most 60% of live Kalshi
    # total bankroll (cash + positions). v14 controls the other 40% via
    # V14_BANKROLL_FRACTION env in its own supervisor. The fraction is
    # applied each loop against the LIVE Kalshi balance, so deposits and
    # withdrawals scale both bots' caps automatically.
    $env:V1_BANKROLL_FRACTION = "0.60"

    # Rotate stale resting orders every 6 hours (default in code is 120h).
    # Faster rotation keeps capital fluid for new fills.
    $env:STALE_BID_TTL_HOURS = "6"

    # Check for the REBASELINE flag (created by restart_bot.ps1
    # -Rebaseline). If present, pass --rebaseline to the bot so it
    # re-reads Kalshi balance instead of using the persisted state.
    # The flag is single-shot: we remove it after consuming so the
    # NEXT supervisor cycle (auto-restart after a crash) doesn't
    # rebaseline again.
    $RebaselineFlag = Join-Path $StateDir "REBASELINE"
    $BotArgs = @(
        "run", "python", "-m", "scripts.paper_trade_favorite",
        "--mode", "live", "--yes-i-authorize",
        "--cadence", "900",
        "--max-concurrent", "auto",
        "--min-net-edge", "0.01",
        "--max-lifetime-days", "180",
        # Enable cancel-on-drift: rotate v1 resting bids if the
        # underlying market drifts materially since placement. Defaults
        # in paper_trade_favorite.py CLI are conservative (3c drift
        # threshold, 30-min min order age before considering).
        "--cancel-on-drift",
        # Round 21 (v16) council decision (2026-05-30): restrict v1 to the
        # 5 Becker train+OOS validated PERSIST prefixes (KXMLBGAME,
        # KXATPMATCH, KXNFLGAME, KXNCAAFGAME, KXWTAMATCH), add the expanded
        # OOS-NULL denylist (spreads/totals/wins/EPL/UCL), and skip the
        # final-hour adverse-selection window. The broad universe diluted
        # v1's validated edge to ~0 aggregate OOS, and 14 of 15 adverse-
        # drift fills were in non-validated prefixes. See
        # research/v16/00-DIAGNOSIS-AND-COUNCIL.md and
        # research/v10a/20-v1-drift-by-prefix.md.
        "--allowlist",
        "--expanded-denylist",
        "--min-minutes-to-close", "60"
    )
    if (Test-Path $RebaselineFlag) {
        Write-LauncherLog "REBASELINE flag detected; passing --rebaseline to bot."
        $BotArgs += "--rebaseline"
        Remove-Item -Path $RebaselineFlag -Force -ErrorAction SilentlyContinue
    }

    # Single-instance check: if bot.lock exists and points to a live
    # process, refuse to launch. The bot itself enforces this too
    # (acquire_live_lock raises SystemExit), but checking here avoids
    # the spawn-and-die cycle that wastes restart-backoff time.
    $LockFile = Join-Path $StateDir "bot.lock"
    if (Test-Path $LockFile) {
        try {
            $lockData = Get-Content $LockFile -Raw | ConvertFrom-Json
            $lockPid = [int]$lockData.pid
            $lockProc = Get-Process -Id $lockPid -ErrorAction SilentlyContinue
            if ($lockProc -and ($lockProc.ProcessName -in @('python', 'uv'))) {
                Write-LauncherLog "Bot already running (lock holder PID $lockPid); skipping launch this iteration."
                Start-Sleep -Seconds 30
                continue
            }
        } catch {
            Write-LauncherLog "Stale lock file detected; will overwrite."
        }
    }

    Write-LauncherLog "Starting bot process (shadow logging + active filter enabled)..."
    $startTs = Get-Date
    try {
        $proc = Start-Process -FilePath "uv" `
            -ArgumentList $BotArgs `
            -WorkingDirectory $ProjectRoot `
            -PassThru `
            -NoNewWindow `
            -RedirectStandardError $BotStderrLog
        # NOTE: the bot itself writes bot.pid (and bot.lock) via
        # acquire_live_lock at startup. We do not write $PidFile here
        # to avoid racing the bot's own write.
        Write-LauncherLog "Bot started with PID $($proc.Id)"
        $proc.WaitForExit()
        $exitCode = $proc.ExitCode
        $runtime = (Get-Date) - $startTs
        Write-LauncherLog "Bot exited (PID=$($proc.Id), exit=$exitCode, runtime=$($runtime.ToString()))"
    } catch {
        Write-LauncherLog "Launch failed: $($_.Exception.Message)"
        $exitCode = -1
    } finally {
        if (Test-Path $PidFile) { Remove-Item $PidFile -Force }
    }

    if (Test-Path $StopFile) {
        Write-LauncherLog "STOP file detected after exit; not restarting."
        break
    }

    # Exponential backoff on crash; reset on long-runs.
    $runtime = (Get-Date) - $startTs
    if ($runtime.TotalSeconds -gt 600) {
        $BackoffSeconds = 5
    } else {
        $BackoffSeconds = [Math]::Min($BackoffSeconds * 2, $MaxBackoff)
    }
    Write-LauncherLog "Backing off ${BackoffSeconds}s before restart"
    Start-Sleep -Seconds $BackoffSeconds
}

Write-LauncherLog "Launcher exiting cleanly"
