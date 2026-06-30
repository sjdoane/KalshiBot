# v24 Idea 2 (weather external-forecast taker): NULL. Capture phantom confirmed live.

**Verdict: NULL. No capital deployed (correctly). Resolved for $0 via a read-only
live check.**

**Date:** 2026-06-30
**Scripts:** `scripts/v24/weather_taker_backtest.py`,
`scripts/v24/weather_live_feasibility.py`,
`scripts/v24/weather_station_offset_check.py`.

## The full chain of evidence

1. **Optimistic kill-filter backtest PASSED but is look-ahead-dominated** (doc 06):
   OOS +13.29pp net of worst-case taker fee + 3c spread, BUT the edge grows
   monotonically with trade lead (+8.25pp at 12-24h before close -> +13.29pp at
   24-48h), and the fitted forecast sigma is ~1F (near-analysis), both signatures
   of the Open-Meteo historical-forecast being NEWER than the trade time. So the
   backtest could not establish a real as-of edge; the live test was the resolver.

2. **Live read: the signal fires hugely, but one-directionally.** On 65 current
   open KXHIGH markets, 29 candidates fire (|g| >= 8pp), almost all "buy NO",
   because my forecast is systematically 2-6F HOTTER than the settlement-anchored
   market across ALL 8 cities. Real edges are 1-5pp; these are 30-59pp = a
   forecast-vs-market artifact, not a mispricing.

3. **Station bias RULED OUT.** Calibrated on RECENT real NWS settlements (inferred
   from recently-settled Kalshi markets) vs the grid, the per-city offset is only
   ~±1F (NY -1.3, CHI +0.2, DEN +1.2, LAX +1.2, MIA +1.0, PHIL +1.6, AUS +0.8).
   Applying the correct offset barely changes firing (29 -> 27-29). The grid
   forecast ~ the NWS settlement on average; station bias is NOT the driver.

4. **Sigma RULED OUT.** Firing does not collapse with larger sigma (29 at sigma=3
   -> 32 at sigma=6; max|g| 0.48 -> 0.55). The divergence is in the forecast POINT,
   not a tunable-parameter artifact.

5. **The real cause: the market beats my naive forecast (capture phantom).**
   - For markets closing in ~12-15h (TODAY's high, nearly realized), the market
     sees the realizing temperature and is near-truth; my day-old forecast is
     simply less informed. Those "edges" are phantom.
   - For ~36h markets (tomorrow), both rely on the public forecast. The market
     correctly DISCOUNTS NWP's over-predicted extreme heat (e.g. my raw forecast
     says NY 99.8F tomorrow; the market implies ~94F and is very likely right, as
     NWP routinely over-predicts extremes). My naive model (raw NWP point + a
     Gaussian) takes the extreme at face value; the market calibrates it. The
     market is the better probabilistic estimate of the public forecast.

This is the project's recurring killer, confirmed AGAIN: for a PUBLIC-information
signal, the market/MM already prices it (better than a naive model), so a taker
crossing the ask captures nothing. It is the same mechanism as the confirmed live
v7-B/v8-A phantom (8/8 losses: market right, naive model wrong).

## Why no capital was deployed (this honors the operator authorization, not defies it)

The standing authorization is to deploy live on REAL potential, and to "ensure we
do not already have the data" first. The read-only live check (real data, NOT a
multi-week ghost probe) gave the answer for $0: there is NO real potential here:
the divergence is a naive-forecast-vs-better-informed-market artifact, and the
market wins. Deploying capital would be a MANUFACTURED loss (betting a naive model
against a market that provably beats it), which the operator explicitly does not
want ("a real edge or a clean null, never a manufactured positive"). The
best-potential action is therefore NULL + conserve capital for a genuinely
promising idea. (If the operator nonetheless wants a tiny confirmatory live test,
it is a few $1 bets on the 36h markets; my honest expectation is it loses.)

## What would be required for a real weather edge (and why it is not worth it)

To beat the market I would need a forecast model BETTER-CALIBRATED than the market
(proper ensemble probabilities, extreme-bust correction, station-specific
calibration). But the market already does this with the same public forecast, so a
better model would at best CATCH UP to the market, not beat it = the capture
phantom. Weather is a pure public-data game where the market has no excuse to
misprice, exactly as the idea-2 plan critic argued. NULL.

## No third bite

Weather taker (external-forecast divergence) is NULL. Combined with the killed
weather MAKER (EC-1) and the killed price-recalibration (idea 1), the entire
weather/recalibration family is exhausted. v24 continues to the next idea
(sports-props) per the loop.

*Em-dash and en-dash audit: verified clean after write.*
