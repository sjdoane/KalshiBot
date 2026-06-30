# HANDOFF: Power up the realized-vol index taker (v24) until the CI is conclusive

You are picking up Project Kalshi in a fresh window. Read
`~/.claude/.../memory/project_kalshi.md` (top entries) and the repo CLAUDE.md
first. This prompt is your mission. Operator standing authorization is ACTIVE:
choose the best decision yourself, do NOT pause to ask, you have FULL authorization
to live-test and to pivot, be creative, and continue the loop.

## The one rule that overrides the operator's excitement: HONESTY

The operator is (rightly) excited about a positive-looking signal and wants the
confidence interval to become positive. Legitimate ways to get there: MORE DATA
(power), correctness fixes, better features validated out of sample. FORBIDDEN:
tuning thresholds/windows/bands until the CI crosses zero (p-hacking). A clean NULL
is a success. The binding honesty guardrail is the VIX CONTROL (below): a real
realized-vol edge must BEAT the VIX-model control out of sample; if they stay
equal, there is no realized-vol edge, only a small general VRP/skew that any vol
model catches (and the only question is whether it clears the fee).

## Connectors / data sources: do NOT ask the operator to add anything upfront

The decisive power-up needs NOTHING new. You already have: the Kalshi API (key in
.env; for more KXINX history), FRED (SP500 + VIXCLS, free), and the Massive Market
Data connector ENTITLED for stocks (SPY, incl. 5-min intraday) + crypto. That is
enough to: extend the history, run the same-day intraday window, and build a better
realized-vol forecast. Proceed on these. Do NOT pause to request connectors.

A short-dated SPX/SPY options-IV source (Massive 403s on options + indices) would
only sharpen the capture-phantom DIAGNOSTIC (right-tenor implied vol vs 30d VIX); it
does NOT improve the forecast (using IV as a feature re-imports the market's answer =
capture phantom) and most likely just confirms the phantom more precisely. So it is
NOT worth adding to decide whether an edge exists.

CONDITIONAL connector instruction (the only time to involve the operator): IF the
powered-up strategy CLEARS THE BINDING GATE (OOS cluster-CI lower > 0 net of fee AND
realized beats the VIX control) and you are staging to LIVE, AND a short-dated
options-IV benchmark (or another specific data source) would MATERIALLY improve live
vol-benchmarking/execution, THEN stop and give the operator concrete, step-by-step
setup directions for that specific connector (e.g., upgrade the massive.com plan to
entitle Options + Indices, or add a Polygon.io options MCP: name the exact plan/MCP,
the auth/key steps, and the exact endpoints/tickers you will use, e.g. short-dated
SPX/SPY option-chain IV). Until that bar is met, add nothing.

## What the strategy is

Kalshi lists S&P 500 range/threshold markets (series KXINX: "S&P above/below/between
X at [date] 4pm"). They have a HALF taker fee (0.035 vs the normal 0.07), which
halves the hurdle to ~2pp. Thesis: harvest the variance risk premium / vol
mispricing -> forecast the S&P settlement-price distribution (sigma), and TAKE
(cross the ask) when the model-implied P(strike) diverges from the Kalshi price.
This is a VOLATILITY play (forecastable), NOT directional (unforecastable + priced;
the capture phantom that killed every other v24 idea).

## Current state (what is built and what it shows)

Script: `scripts/v24/index_vol_backtest.py` (run with the project venv:
`C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi/.venv/Scripts/python.exe
scripts/v24/index_vol_backtest.py [RV_WINDOW]`). It uses Becker KXINX (settled
markets + day-before-window VWAP) + FRED SP500 (the actual index, 4pm-aligned to
settlement) + FRED VIXCLS, with a clean no-look-ahead spot, the actual trading-day
horizon, drift, the HALF taker fee, and event-clustered bootstrap CIs by settlement
day. FRED data is cached at
`<scratchpad>/fred_sp500_vix.json` (regenerate via the PowerShell FRED pull, key in
.env as FRED_API_KEY; series SP500 + VIXCLS).

Current result (corrected, clean spot): realized-vol strategy OOS +2.3pp
CI[-3.7,+8.7] (straddles 0), TRAIN +3.3pp (not significant); VIX control OOS +1.8pp
(straddles 0). The realized-vs-VIX wedge is tiny (~0.2-0.4pp). So: MARGINAL +
UNDERPOWERED (only ~30 OOS settlement-day clusters). Not a pass, not a clean null.
NOTE: an earlier version showed +4.7pp OOS but that was partly a spot look-ahead;
the clean version is smaller. Do not regress to the look-ahead.

## Your mission: power it up until the CI is conclusive (positive or null)

Priority order (biggest power lever first):

1. **MORE KXINX HISTORY (the primary power lever).** Becker ends 2025-11-28
   (~280 events). Pull the recent settled KXINX markets Dec-2025 through now via the
   LIVE Kalshi API (read key in .env; client at `src/kalshi_bot/data/kalshi_client.py`,
   `c.get("/markets", series_ticker="KXINX", status="settled", ...)` paginated; for
   each market's day-before price you need its historical trades -- use the Kalshi
   trades endpoint; mind rate limits ~10/s). Extend FRED SP500/VIXCLS to now (FRED
   updates daily). This roughly DOUBLES the sample and is the cleanest way to tighten
   the CI without p-hacking. Network is PowerShell-only (Bash sandbox has no network).

2. **THE SAME-DAY INTRADAY WINDOW (10x the data).** KXINX trades are ~90% same-day
   (42k trades in 0-12h before the 4pm close vs ~3k in the day-before window). The
   same-day window has far more data but needs an intraday spot (FRED is daily). The
   Massive Market Data connector IS entitled for STOCKS, so pull SPY 5-min bars
   (SPY approx SPX/10) for the intraday spot + intraday realized vol, and run the
   same-day version (horizon = hours to the 4pm close). This is the biggest single
   data expansion. Caveat: same-day S&P is the most MM-saturated = strongest capture
   phantom, so the VIX control is even more important there.

3. **CLEANER VOL FORECAST (validated, not stacked).** HAR-RV (multi-horizon realized
   vol) is the standard and is hard to beat; test it AGAINST the simple trailing RV
   and AGAINST VIX out of sample (Brier/log-loss vs the actual settlement outcome).
   Add a feature ONLY if it beats the baseline OOS (orthogonality protocol). Do NOT
   build a 6-feature stack (overfit). The key question is forecast SKILL vs VIX, not
   model complexity.

4. **PROPER SHORT-DATED IMPLIED VOL (the right VRP benchmark).** VIXCLS is 30-day;
   the KXINX horizon is ~1-3 days. The correct implied-vol benchmark is SHORT-DATED
   SPX/SPY options IV. The Massive connector currently 403s on options + indices
   (entitled for stocks + crypto only). If the operator adds an options-IV source
   (see MCP recommendations), use the ~1-3 day SPY/SPX IV as the VIX control instead
   of 30d VIX -- a much sharper capture-phantom test.

## The binding tests (pre-registered; do not move them)

- BINDING GATE: realized-vol strategy OOS net-of-HALF-fee + spread, event-clustered
  (cluster = settlement day) bootstrap 95% CI LOWER BOUND > 0, AND the realized
  model must BEAT the VIX control OOS (otherwise it is not a realized-vol edge).
- If it passes powered-up: STAGE to live per the standing authorization (deploy live,
  ramped, sized off 20-30% of the live Kalshi balance, fixed $-risk/bet, hard
  contract cap from balance, per-week drawdown breaker; the read-only-first live
  check on current open KXINX -- model P vs the live ask -- resolves capturability
  for $0 before scaling). The operator has authorized live capital.
- If it stays underpowered/straddling after the full power-up, or the VIX control
  matches the realized model: NULL it honestly and pivot (see creative pivots).

## Creative pivots (full authorization to pursue if the index leg stalls)

- EVENT-VOL: the VRP/vol-FLB is LARGER and less-arbed around scheduled events
  (CPI, Fed, jobs, earnings). Kalshi has macro/event markets. Selling the
  overpriced event move (the realized move < the priced move) may have a bigger,
  less-MM'd edge than the always-on S&P range. Strong creative candidate.
- VOL TERM-STRUCTURE / cross-horizon: relative mispricing between same-asset
  different-horizon Kalshi markets.
- Single-name or thinner-index vol where retail mispricing is larger than on the
  hyper-efficient S&P.

## Known failure modes (do not re-create)

- CAPTURE PHANTOM (the project's killer, 5 live confirmations): the market prices
  PUBLIC info into the ask; a taker captures nothing unless it has info the market
  lacks. The VIX control is your detector.
- LOOK-AHEAD: the spot/feature must be strictly as-of the trade time (the spot bug
  above inflated the edge ~2x). Audit every feature's timing.
- NAIVE-MODEL-WORSE-THAN-MARKET: a model that is just worse than the market shows
  fake "divergence" (this killed the weather idea). The VIX control + OOS Brier-vs-
  market guard against it.
- OVERFIT at small n: few hundred daily events; keep the model simple, validate OOS.

## Binding rules (hard)

- NO em-dashes (U+2014/U+2013) anywhere; verify after every write with a
  Select-String regex built from [char]0x2014 and [char]0x2013 returning nothing.
- Windows/PowerShell, absolute paths. Network = PowerShell only. Project venv python
  directly (NOT uv; venv pandas is broken -> use duckdb + json). Becker at
  `prediction-market-analysis/` (gitignored, 85GB).
- Net every result vs the WORST-CASE applicable fee (KXINX taker = the reduced 0.035
  quadratic; re-verify in research/v22/fee_table.json; if the 0.035 entitlement is
  ambiguous, also run the full 0.07 as the conservative bound).
- No secrets in chat or git (.env, *.pem). Commit per unit, push to origin/main with
  the Co-Authored-By: Claude Opus 4.8 (1M context) trailer.
- Update project_kalshi.md + the v24 docs after each work block.

## Files / artifacts

- `scripts/v24/index_vol_backtest.py` (the backtest; realized + VIX control).
- `scripts/v24/weather_live_feasibility.py` + `mlb_props_capture_check.py` (live
  read-only patterns to reuse for the $0 live KXINX capture check).
- `research/v24/10-index-vol-mispricing-NULL.md` (the prior writeup; update it as
  the result evolves), `research/v24/08-META-SUMMARY.md` (the capture-phantom wall).
- FRED cache + the Massive Market Data connector (entitled: stocks SPY + crypto;
  403: indices/VIX/options).

Begin by extending the data (steps 1-2), re-run the binding tests, and act on the
result (live-stage if it passes, pivot if it stalls). Do not pause; you have full
authorization.

*Em-dash and en-dash audit: verify clean after write.*
