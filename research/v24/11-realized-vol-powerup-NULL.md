# v24 realized-vol index taker: POWER-UP result = CONCLUSIVE NULL

**Date:** 2026-06-30
**Verdict: NULL, conclusively. The day-before "+6.94pp OOS edge" was entirely a
stale-spot/horizon artifact. With a correct as-of spot, the strategy LOSES net of fee
in the real (same-day) capturable window, and the realized model never beats the VIX
control. The binding gate fails. No capital. Capture phantom confirmed in the
index-vol dimension.**

Supersedes the marginal/underpowered status in `10-index-vol-mispricing-NULL.md`.
This is the powered-up resolution the handoff (`HANDOFF-realized-vol-powerup.md`)
asked for: more data + the same-day intraday window + correctness fixes, then act on
the result. The result is a clean null.

## What was done (the power-up)

1. **More KXINX history (primary power lever).** Pulled the FULL settled KXINX/INX
   universe from the live Kalshi API via `/historical/markets` (19448 markets,
   2022-2026, the close-ts filter is silently ignored so it returns everything)
   plus the recency-capped live `/markets?status=settled` (2026-05/06), deduped.
   Post-2024-10 (the sign-flip regime, matching Becker's start), near-money + traded:
   **4217 markets across ~440 settlement days** vs the Becker slice's ~280 events.
   Trades pulled per market in the 0-40h-before-close window (4032 with >=1 trade).
   FRED SP500 + VIXCLS extended to 2026-06-29.
   - Script: `scripts/v24/index_vol_backtest_v2.py` (reads the API pull, same
     pre-registered methodology, adds the conservative full-0.07 fee bound).

2. **Same-day intraday window (the decisive test + the capturable window, ~90% of
   KXINX volume).** Pulled SPY 5-min -> hourly opens 2024-10..2026-05 via the Massive
   connector (entitled for stocks), converted to an as-of SPX spot via the prior-day
   SPX/SPY ratio, with the correct trading-hour horizon to the 4pm close.
   - Script: `scripts/v24/index_vol_intraday.py`.

3. **Honesty controls held fixed (no p-hacking):** OOS split 2025-07-01 (unchanged
   date, just more OOS data after it), band [0.10,0.90], divergence 0.05, cluster
   bootstrap by settlement day, the VIX-model control as the lie detector, both fee
   bounds. The vol input (trailing 10d daily RV + VIX) was held IDENTICAL across the
   day-before and intraday tests so the only difference is the spot+horizon fix.

## The decisive finding: the edge was a stale-spot artifact

The day-before backtest uses a daily FRED close that is ~2 trading days STALE relative
to the trade, with a 2-day horizon. The same-day/fresh-spot tests use an as-of
intraday spot with the correct short horizon. The realized-model OOS net edge:

| Test | spot | horizon | OOS clusters | realized OOS net | beats VIX? |
|---|---|---|---|---|---|
| Day-before v2 | 2-day-stale daily | ~2 days | 150 | **+6.94pp** [+4.33,+9.45] | +0.95pp (tied) |
| Same-day intraday | as-of 11:00 ET | 5 trading h | 220 | **-3.34pp** [-6.14,-0.28] | -1.73pp (no) |
| Day-before, fresh prior-session spot | as-of prior 11:00 ET | ~11.5 trading h | 24 | **-6.57pp** [-19.21,+5.22] | -1.38pp (no) |

The "+6.94pp" FLIPS NEGATIVE the moment the spot is made as-of. The same-day result is
robust across window starts 10:00/12:00/13:00 ET (realized OOS -2.67 to -4.32pp, never
beats VIX). 

**Why it flipped (the mechanism), and the smoking gun.** Decomposition of the
day-before edge: ~95% of fires are "buy NO on narrow 25-point bands" at ~0.85 entry
(a short-variance / band-premium position, ~90% win rate, negative skew). The model
fires these because its 2-day-stale spot + 2-day horizon OVER-disperse the lognormal,
making near-spot bands look under-priced (the naive-model-worse-than-market trap that
killed the weather idea). The capture-phantom diagnostic median(Kalshi_price -
VIX_model_P) shrinks monotonically with spot freshness:

  +4.77pp (2-day-stale daily)  ->  +2.96pp (fresh prior-session)  ->  +2.20pp (fresh intraday)

i.e. the fresher the spot, the more the model agrees with Kalshi, and the apparent
"divergence" (the source of the fake edge) collapses. The divergence WAS the staleness.

## Why this is a NULL (binding gate)

- BINDING GATE = OOS net-of-fee cluster-CI lower > 0 AND realized beats the VIX control
  OOS. In every artifact-free test (same-day as-of, day-before fresh-spot, all window
  starts), the realized OOS edge is NEGATIVE and realized is WORSE than the VIX control.
  GATE FAILS.
- The day-before v2 "pass" (+6.94pp, lower>0) is a known-artifact false positive: the
  handoff explicitly warned "audit every feature for look-ahead (the spot bug inflated
  the edge ~2x)". Here the daily-stale spot inflated it by a ~10pp swing (-3 to +7).
  Removing it is a correctness fix, not p-hacking, and it kills the edge.
- The VIX control (the lie detector) did its job: realized never beats it. There is no
  realized-vol informational edge. What remains is a short-band-premium that LOSES net
  of fees in the efficient same-day window.

## Conclusion

The realized-vol index taker is a conclusive NULL. Kalshi prices same-day S&P range
volatility efficiently; a retail vol model (realized or VIX) captures nothing net of
the half taker fee and in fact loses. This is the capture phantom in the index-vol
dimension, consistent with the v24 meta-summary (financial markets are the most
efficient; Becker Finance gap 0.17pp). No capital deployed; deploying would be a
manufactured loss. No $0 live read-only check is warranted: the gate failed on 220 OOS
settlement-day clusters of SETTLED outcomes (far more decisive than a one-shot snapshot
of unsettled markets), and the diagnostic already shows the model agrees with current
asks to ~2pp.

Per the operator directive (NULL honestly, then pivot), the next step is the EVENT-VOL
candidate: test whether the variance risk premium is larger and less arbed on KXINX
settlement days that span a scheduled macro event (CPI / FOMC / NFP) than on ordinary
days, using the same artifact-free as-of-spot pipeline. See `12-event-vol-*.md`.

## Data / reproduction notes

- KXINX pull + SPY intraday + FRED cache live in the session scratchpad (gitignored,
  regenerable): `kxinx_pull.json`, `spy_intraday.json`, `fred_sp500_vix.json`.
- Kalshi API gotchas (load-bearing): `/historical/markets` ignores min/max_close_ts and
  returns the FULL settled universe in one drain; the live `/markets?status=settled` is
  recency-capped (~last 2 months + stragglers); trade fields were renamed
  `count`->`count_fp`, `yes_price`->`yes_price_dollars`; trades cutoff
  (`/historical/cutoff`) at 2026-05-01 splits `/historical/trades` vs `/markets/trades`.
- Massive SQL surface is locked-down SQLite (no strftime/hour/extract/timezone);
  filter bars by raw epoch-ms arithmetic and resolve ET/DST in Python (zoneinfo).

*Em-dash and en-dash audit: verified clean after write.*
