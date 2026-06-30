# v24 weather-taker lock: methodology-critic findings + AMENDMENTS

**Date:** 2026-06-30
**Methodology critic verdict:** REJECT as written, convertible to
APPROVE-WITH-CHANGES with 6 BLOCKING fixes. The KILL branch of the screen is
sound; the PASS-to-live-capital branch was not defensible as written because the
backtest optimism is stacked and unbounded (lead look-ahead, too-tight spread,
station bias, each ~the trade margin).

## Critic's load-bearing findings (preserved)

1. **Forecast-lead leakage (biggest defect).** `weather.py::
   fetch_historical_forecast_ensemble` passes forecast_days=0/past_days=0 with NO
   issue-date/lead pin and SILENTLY IGNORES its `lead_hours` arg; it returns a
   single deterministic point as a 1-element list. The Open-Meteo
   historical-forecast lead is uncontrolled (~0-1 day, optimistic for a 1-2 day
   strategy). A ~1-day fresher forecast shrinks sigma enough to swing p_model ~7pp
   near the money = the size of the whole 8pp threshold. So an optimistic-backtest
   PASS can be manufactured entirely by the lead. The lock described a pinned
   1-2-day forecast the code cannot produce.
2. **Spread haircut too tight.** 1c on thin weather books understates the real
   lift-the-ask cost (doc 04's own range is 3-5c), inflating the backtest ~2-4pp.
3. **Settlement-station bias.** KXHIGH settles on a specific NWS ASOS station; the
   `CITIES` grid coords (e.g. NY Central Park, an urban microclimate) can differ
   from the Open-Meteo grid cell by 1-2F SYSTEMATICALLY, manufacturing a persistent
   fake edge that survives TRAIN/OOS AND loses live (live p_model inherits the same
   coord). W-4 (forecast beats climatology) does NOT catch this.
4. **Single annual Gaussian sigma is mis-specified** (season/lead/skew), and the
   mis-specification CONCENTRATES in the |g|>=8pp tail, so the strategy preferentially
   fires on model-bust days (signal adverse selection, the taker analog of fill
   toxicity).
5. **The $0 ask-lag probe (capture phantom) was skipped.** The screen is silent on
   the project's CONFIRMED killer (v7-B/v8-A). The live read of the ask is free, so
   the capture-phantom test should run in parallel with the first live capital.
6. **Worst-case loss mis-stated.** The -20% rolling-7-day breaker bounds ADDITIONAL
   entries, not first-window loss; the real max is the full deployed 20-30% ($40-60)
   because many positions can open before the first settlements. Ramp in.

IMPORTANT (should-fix): the "5pp margin" claim is overstated (under a 3-5c spread
the hurdle is ~6-7pp, margin ~1-2pp); re-add a capacity gate; (city,date) clusters
are serially correlated across adjacent days (block/weekly bootstrap or document
anti-conservatism); report the slow-window discard rate + per-city CIs (no
one-city carry); pre-register strike selection within a city-day; require a
minimum number of distinct live market-days (not just >=30 fills); fix the code
(`lead_hours`, single-point-vs-ensemble); caveat the single-season (fall) OOS.

## AMENDMENTS (these supersede the conflicting parts of 05-...-lock.md)

**AMEND-A (reframe, resolves BLOCKING 1+2 honestly).** The Becker backtest is an
EXPLICITLY-OPTIMISTIC KILL-FILTER ONLY. Its forecast lead is uncontrolled
(documented optimistic) and it uses a CONSERVATIVE spread haircut of 3 cents
(lift-the-ask) so it is not doubly optimistic. Decision rule: if the optimistic
backtest FAILS (W-2/W-3 CI lower bound not > 0 net of worst-case fee + 3c spread),
weather is KILLED (it cannot win even with look-ahead). A PASS is NECESSARY but
does NOT alone authorize full capital; it only earns the live ramp. This removes
the need for a heavy GEFS-reforecast build: the clean test is live (lead + spread
optimism vanish by construction).

**AMEND-B (station correction, resolves BLOCKING 3).** Estimate a per-city
forecast/observed offset on TRAIN ONLY: compare the Open-Meteo grid daily-high to
a Becker-inferred settlement high (the band between the highest YES-settling strike
and the lowest NO-settling strike per city-day, from markets.result), freeze the
median offset per city, and add it to f before computing p_model on OOS and live.
Drop any city whose TRAIN offset std is so large the high is not localizable. This
is leakage-clean (offset from TRAIN only).

**AMEND-C (sigma, resolves BLOCKING 4).** Fit sigma stratified by city x season
(meteorological quarter) on TRAIN only. Report the adverse-selection diagnostic:
on |g|>=8pp selected trades, the realized hit rate of p_model (does the model bust
disproportionately on selected days?). If selected days are model-bust-dominated,
that is a kill signal.

**AMEND-D (capture phantom, resolves BLOCKING 5).** When live, log for every
candidate market the live ask vs the live public-forecast p_model and compute the
ask-vs-forecast lag/gap; this $0 probe runs IN PARALLEL with the ramped live
capital (not instead of it, per the operator directive; not before it as a
multi-week ghost probe). If the live ask already tracks the forecast (no crossable
gap beyond the hurdle), stop.

**AMEND-E (ramp + exposure cap, resolves BLOCKING 6).** Live deployment RAMPS:
start at a small initial tranche (~$5), with a max-concurrent-open-exposure
sub-cap, and scale toward the 20-30%-of-balance CAP only as settled live fills +
the ask-lag probe confirm a real capturable edge. The real max loss before the
first validation tranche settles is the initial tranche, not $40-60.

**AMEND-F (capacity gate, IMPORTANT).** Pre-register a minimum expected net
$/week at $1-2 notional; if the surviving tradable universe (slow window x band x
8pp threshold) is sub-$0.50/week, NULL as capacity-bound regardless of CI.

**AMEND-G (inference, IMPORTANT).** Cluster the bootstrap by (city, ISO-week) to
absorb day-to-day weather serial correlation (not (city, date), which is
anti-conservative). Report per-city CIs and the slow-window discard rate; the
pooled pass must not be carried by one city.

**AMEND-H (frozen DoF, IMPORTANT).** Universe = the 8 Becker KXHIGH cities with
station coords (add AUS/PHIL/HOU to CITIES); BOTH strike types handled (T:
p=1-Phi((S-f)/sigma); B-band [Lo,Hi]: p=Phi((Hi-f)/sigma)-Phi((Lo-f)/sigma)),
reported combined (gate) with T-only/B-only diagnostics. Strike selection within a
city-day: ALL strikes that have a slow-window trade and fall in the [0.10,0.90]
price band (no nearest-to-forecast cherry-pick). Live verdict requires >=30 fills
AND >=20 distinct settlement days. Margin claim corrected: under a 3c+ spread the
hurdle is ~5-6pp and the 8pp threshold margin is ~2-3pp (not 5pp).

## Net effect

The backtest is now an honest, conservative KILL-FILTER (optimistic lead but
conservative 3c spread + station-corrected + stratified sigma + week-clustered CI).
If it fails, weather dies cheaply. If it survives, live capital ramps in (the
leakage-free real test) with the capture-phantom probe running for free alongside.
This satisfies all 6 BLOCKING items without a GEFS-reforecast build and honors the
operator's deploy-live-not-ghost-probe directive via a ramp rather than a probe.

*Em-dash and en-dash audit: verified clean after write.*
