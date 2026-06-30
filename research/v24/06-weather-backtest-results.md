# v24 weather external-forecast taker: kill-filter backtest RESULTS

**Date:** 2026-06-30
**Script:** `scripts/v24/weather_taker_backtest.py` (project venv DuckDB; forecasts
pre-fetched to scratchpad via PowerShell). Per lock `05` + amendments `05b`.

## Headline: PASS on the optimistic kill-filter, but the edge is LOOK-AHEAD-DOMINATED

The explicitly-optimistic kill-filter does NOT kill weather. Net per contract, net
of WORST-CASE taker fee `ceil(0.07*P*(1-P))` + a conservative 3c spread haircut,
event-clustered by (city, ISO-week):

| Window (locked) | TRAIN | OOS |
|---|---|---|
| net/contract | +14.85pp | +13.29pp |
| 95% CI | [+13.59, +16.07] | [+10.87, +15.65] |
| fills / clusters | 5560 / 294 | 1622 / 98 |
| hit rate | 76.1% | 74.1% |

- 8 cities (NY/CHI/MIA/LAX/DEN/AUS/PHIL/HOU). TRAIN station offsets (grid -> NWS
  settlement, inferred from Becker strike crossings, TRAIN only) are sane:
  NY -0.6F, DEN +1.7, CHI +1.3, HOU +1.4, AUS +1.0, LAX +0.7, MIA +0.7, PHIL +0.5.
- Per strike type (OOS, diagnostic): gt +11.88pp (n=127), lt +18.61pp (n=63),
  band +13.18pp (n=1432, the bulk).
- Discard rate (no slow-window trade) 9%. Capacity ~$16/week at 1 contract/fill.

## The look-ahead diagnostic (decisive): the edge grows with trade lead

Re-running the selection at different trade windows (hours before close), OOS net:

| Trade window (h before close) | OOS net/contract | fills |
|---|---|---|
| 12 to 24 | +8.25pp [+5.61, +10.88] | 1344 |
| 24 to 48 | +13.29pp [+10.83, +15.71] | 1622 |
| 48 to 72 | (no trades; KXHIGH opens ~48h pre-close) | 0 |

The edge GROWS monotonically as the trade window moves EARLIER. The Open-Meteo
historical-forecast forecast is a FIXED ~1-day lead (MAE 2.7F vs realized). So
trading earlier means the forecast is increasingly NEWER than my trade time =
the temporal-mismatch look-ahead the methodology critic predicted. This is the
signature of a look-ahead-driven edge, not a real as-of edge: at 24-48h before
close I am scoring against a market price that had NOT yet seen the ~1-day forecast
I am using.

Even the least-contaminated window (12-24h, where the ~1-day forecast is roughly
contemporaneous with the trade) shows +8.25pp, but that is STILL likely
look-ahead-inflated (the historical-forecast effective lead may be < 1 day), and
+8.25pp net is implausibly large for a real, capturable retail edge.

## Honest verdict

- The kill-filter did NOT kill weather (it passes even at the least-contaminated
  window). Per the lock, a PASS is NECESSARY-not-sufficient.
- But the backtest CANNOT establish a real as-of edge: the magnitude is
  look-ahead-dominated (monotone growth with lead). The true as-of edge (forecast
  pulled at trade time) is unknown and plausibly much smaller than +8.25pp,
  possibly ~0 after the CAPTURE PHANTOM (does the live ask at 24-48h pre-close
  already embed the public forecast?).
- The ONLY clean resolver is the LIVE test (forecast genuinely as-of trade time,
  real ask), per the lock + the operator's standing authorization to deploy live
  rather than ghost-probe.

## Next (live, ramped, per operator authorization + AMEND-D/E)

1. One-shot read-only feasibility check: on CURRENT open KXHIGH markets, pull the
   live ask + current Open-Meteo forecast, compute p_model (frozen TRAIN
   offset+sigma), and check (a) does the locked signal (|g|>=8pp, p in [0.10,0.90])
   fire, and (b) is the live ask already at the forecast (capture phantom)? This is
   a one-shot read, not a multi-week ghost probe.
2. If the signal fires with a crossable gap net of the worst-case fee, deploy a
   SMALL first tranche (~$5, ramp start) as real taker orders, with the
   ask-vs-forecast log running in parallel (free capture-phantom probe), the
   max-concurrent-exposure sub-cap, and the circuit breaker.
3. Ramp toward the 20-30%-of-balance cap only as settled live fills confirm a real
   positive edge (>=30 fills, >=20 distinct settlement days, market-day-clustered
   CI excluding zero, point >= +1.0pp). Else NULL and stand down.

The honest expectation given the look-ahead finding: the real live edge is much
smaller than the backtest, and the capture phantom may take it to ~0. The small
ramped tranche bounds the cost of finding out, which is exactly what the live test
is for.

*Em-dash and en-dash audit: verified clean after write.*
