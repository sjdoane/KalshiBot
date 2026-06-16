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

    # v1 deploys 100% of the live Kalshi total bankroll (cash + positions).
    # v14 was removed 2026-06-01 (negative-EV; see research/v16), so v1 is the
    # only live trading bot and gets the full balance until another bot is
    # added (operator decision 2026-06-01). The fraction is applied each loop
    # against the LIVE Kalshi balance, so deposits and withdrawals scale the
    # cap automatically. If a second bot is re-introduced, re-split this.
    $env:V1_BANKROLL_FRACTION = "1.0"

    # Rotate stale resting orders every 6 hours (default in code is 120h).
    # KEPT AT 6h per research/v20: v1 is NOT capital-constrained (only ~$2.5 of
    # ~$40 cash is in resting bids), so faster recycling solves a non-problem,
    # and --cancel-on-drift already handles adverse staleness. Shortening it
    # would churn cancels and risk cancelling a liquid bid just before it fills.
    $env:STALE_BID_TTL_HOURS = "6"

    # Per-bid sizing (research/v20). V1_PER_BID_FRACTION sets each bid to
    # fraction * v1's live bankroll slice (v1_cap_total), floored at 1 contract;
    # the aggregate budget gate (resting <= cash) and max_concurrent cap total
    # exposure separately. 0.05 puts a LOW-band [0.70,0.86) position at ~6% of
    # bankroll (~4 contracts at ~$52) and heavy [0.86,0.95] at ~3.4% (~2 contracts),
    # which is ~one-fifth Kelly on the conservative validated edge. Operator-
    # approved 2026-06-03, raised from 0.03 (~1/8 Kelly) to deploy more idle
    # capital on the validated edge. Quarter-Kelly ~= 0.06 is the ceiling at this
    # bankroll (a 3-loss LOW streak ~$11.7 would near the 20% drawdown kill); do
    # NOT exceed it while the new-config live edge is still unproven (F11). The
    # fraction is only live after the v20 gate fix (was a dead knob at
    # V1_BANKROLL_FRACTION=1.0). V1_BAND_M_LOW/HIGH weight bids by the favorite-
    # price band (LOW [0.70,0.86) ~2x the edge of heavy [0.86,0.95]).
    $env:V1_PER_BID_FRACTION = "0.05"
    $env:V1_BAND_M_LOW = "1.3"
    $env:V1_BAND_M_HIGH = "0.8"

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
        # Lifetime window [0, 21] days (was [30, 180]). FIX 2026-06-02: the old
        # 30d floor excluded the in-season GAME-RESULT markets where the
        # validated edge + the liquidity live (MLB ~6d, tennis ~15.5d lifetime),
        # and the 180d ceiling admitted dead season FUTURES (NFL/NCAAF ~120d
        # lifetime, no live trading), which is why v1 placed bids that never
        # filled. 21d keeps tennis (15.5d) and MLB (6d), excludes futures (120d).
        # See research/v19/03-fill-rate-diagnosis.md.
        "--min-lifetime-days", "0",
        "--max-lifetime-days", "21",
        # 2026-06-16: lower the scanner liquidity floor 50 -> 10 so v1 quotes
        # thinner / earlier tennis + MLB markets and places more often (operator
        # wants more deployment). Tradeoff: thin-market maker bids fill less
        # reliably. Raise back toward 50 if too many bids sit unfilled.
        "--min-volume", "10",
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
        "--min-minutes-to-close", "60",
        # v18 (2026-06-01): NO-underdog arm + return-on-stake band sizing.
        # --enable-no-underdog adds the symmetric arm (buy NO maker on moderate
        # underdogs; the favorite-longshot bias is symmetric, validated
        # cross-sport in research/v18/06), roughly doubling the eligible universe
        # and using v1's idle bankroll. --band-sizing weights bids by the
        # favorite-price band (LOW [0.70,0.86) larger, heavy smaller; research/
        # v18/02+04). Multipliers tunable via V1_BAND_M_LOW (1.3) / V1_BAND_M_HIGH
        # (0.8). Both reviewed (0 Critical; High+Medium fixed). Remove either
        # flag to disable that piece.
        "--enable-no-underdog",
        "--band-sizing",
        # v18/v19 (2026-06-02): step one tick IN FRONT of the best bid so v1 is
        # the best bid and sellers fill it first (fill-rate boost), capped below
        # the ask so it stays a maker and re-checked for edge. Trades ~1c of the
        # +5-8% edge for a large fill-rate gain. Tick env V1_STEP_TICK_CENTS (1).
        "--step-in-front",
        # OPERATOR OVERRIDE (2026-06-16): bypass the soft pause + ALL kill/stop
        # guardrails (edge, win-rate, catastrophic single-loss, 14-day-negative,
        # 20% drawdown). v1 keeps placing regardless of recent results; the
        # operator stops it manually. The hard $100 capital ceiling + per-trade
        # sizing + max-open-positions still apply. Remove this line to re-enable
        # the automated stops.
        "--disable-stop-guardrails"
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
