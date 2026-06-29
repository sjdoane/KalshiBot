# v24 Idea 2: TAKER on external-forecast-vs-market divergence (KXHIGH). REJECTED at the plan critic.

> **CORRECTION (2026-06-29, see `04-arithmetic-correction-and-checkpoint.md`):**
> point 1 below (the "hurdle ~15pp, fails by an order of magnitude" arithmetic)
> is WRONG. It conflated the taker fee as a FRACTION OF CAPITAL (2c on a 20c
> contract = 10pp) with the pp-of-$1 PROBABILITY-EDGE hurdle (the fee is 1-2pp of
> the $1 contract, and SMALLEST at cheap prices), and compared it against the
> broad-shoulder average edge instead of the high-conviction subset. On the
> correct basis the taker hurdle is ~2-3pp and the high-conviction subset edge
> (~7.9pp net of maker fees) plausibly clears it. Weather is therefore NOT killed
> on arithmetic; its honest prior is ~12-15% and the BINDING question is the
> capture phantom (+ spread on thin books), which is $0-testable. The other kill
> reasons (points 2-5: circular +7.9pp from a recalibration not an external
> forecast, leaky single-member infra, capacity, capture phantom) still stand and
> keep the prior modest, but the verdict downgrades from "rejected build ~6-8%" to
> "PAUSED pending an operator direction call ~12-15%." See the correction doc.

**Verdict: REJECTED as a build at the plan-critic gate (honest prior ~6-8%, below
the ~10% floor). No methodology lock, NO data pulled, NO engineering built.**
A $0 reprieve probe is noted but deferred (see below).

**(SUPERSEDED by the correction above: prior revised to ~12-15%, status PAUSED
not rejected.)**

**Date:** 2026-06-29
**Mechanism proposed:** external NWP/NWS forecast probability of the daily-high
threshold vs the Kalshi price; TAKE the high-divergence tail at 1-2 days to
settlement when the divergence clears worst-case taker fee + spread + margin.

## Why it was rejected (plan critic, full report in 02-idea2-plan-critic.md)

1. **The hurdle arithmetic fails by ~an order of magnitude on the REAL KXHIGH
   price distribution (the dispositive catch).** KXHIGH trades cheap: dataset
   outcome rate 0.213, mid p50 ~0.197, p95 ~0.512 (phase-1.6-results.md). The
   taker fee is a FIXED cents charge, so as a fraction of a cheap notional it is
   punishing: at P=0.20, fee ceil(0.07*0.20*0.80)=2c = 10pp of notional, +1c
   spread = 5pp, total hurdle ~15pp. At p95 (0.51) the hurdle is still ~6pp. The
   best edge on record is gross 1.49pp / net -0.51pp (at maker fees). The generic
   ~3pp favorite hurdle does not apply because KXHIGH is not a favorite market.

2. **The capture phantom is acute, not mitigated.** KXHIGH settles to a public,
   NWP-forecastable number; a competent MM runs the identical NBM/GEFS the bot
   would. At 1-2 days out the forecast is most skillful AND most stable, so an
   intermittently-requoting MM keeps the ask in line with the public forecast.
   Weather is the WORST case for the cross-the-ask phantom (v7-B/v8-A): a pure
   public-data game where the MM has the least excuse to misprice. The "thin/slow
   books" escape is asserted, not evidenced.

3. **The +7.9pp does not transfer.** It is an "Informational (not part of pass
   criteria)" line from phase-1.6, whose headline gate FAILED 4/5. It is
   conditioned on |g(p)-p| > 2pp where g is the isotonic map being validated
   (selection on a price-derived quantity = circular), and it was produced by a
   MARKET RECALIBRATION, not an external forecast. The rising hit rate with
   training size (64% -> 90%) co-occurring with a MORE negative net edge (-0.49pp
   -> -0.81pp) is the signature of a map memorizing the FLB while losing the fee,
   not a stable directional edge.

4. **Existing weather infra is unusable as-is (would manufacture a phantom).**
   `src/kalshi_bot/data/weather.py::fetch_historical_forecast_ensemble` hits the
   free Open-Meteo historical-forecast-api (cheaper than GRIB), BUT (a) it is
   SINGLE-MEMBER (`out[d]=[float(t)] # single-member`), so it cannot produce a
   threshold PROBABILITY, and (b) it has an UNHANDLED as-of leakage trap (no pin
   to the model run issued strictly before trade time), an F11/phase-1.5-class
   leak that would fabricate skill.

5. **Capacity + no-third-bite.** Weather is 6.8% of volume, 5 cities, ~74
   trades/market; the tradable tail is sub-dollar/week. EC-1 weather was killed
   Round 1 and the v24-Idea-1 recalibration was just killed; the carve-out (taker
   on external forecast) is legitimate ONLY if the signal is a genuine as-of NWP
   forecast, which the cheap infra cannot currently deliver without the leakage
   fix + ensemble build.

## The $0 reprieve path (deferred, not pursued now)

The ONE genuine untested escape is whether thin T-1/2d weather books carry a live
ask that demonstrably LAGS the public forecast. That is answerable for $0 with a
read-scope live-ask-vs-public-Open-Meteo-forecast probe over ~2 weeks. It is
DEFERRED: the hurdle arithmetic (point 1) kills the idea even if a modest lag
exists, so the probe would have to surface an implausibly large, persistent
ask-lag to resurrect it. Not worth running ahead of higher-prior ideas.

## Decisive steer from the critic: screen SPORTS-PROPS first

Sports-props-taker dominates weather-taker on prior (~12-18% vs ~6-8%), capacity
(66.7% vs 6.8% of volume), and engineering cost (pip-installable nflverse /
pybaseball / ESPN tabular data, no GRIB, no as-of-NWP leakage audit). The project
also already runs a live taker in the sports family (v14 MLB sportsbook lead-lag),
so the infra and operational pattern are proven. Weather's central virtue
(forecastability) is precisely what makes its MM ask hardest to beat.

## No third bite

Weather-taker (external-forecast divergence) ends here as a build. Given two prior
weather/recalibration kills, this is the genuine last bite on the weather/
recalibration family. v24 pivots to sports-props (idea 3).

*Em-dash and en-dash audit: verified clean after write.*
