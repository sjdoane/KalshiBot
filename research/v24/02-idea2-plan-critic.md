# v24 Idea 2 plan critic (adversarial). Verdict: KILL, prior ~6-8%. Screen sports-props first.

Adversarial plan critic on "TAKER on external-forecast-vs-market divergence in
KXHIGH" before any lock, data pull, or engineering. Load-bearing findings preserved.

## Killing chain

1. **Capture phantom is acute, not mitigated.** KXHIGH settles to a public
   NWP-forecastable number; at 1-2 days out NBM/GEFS skill is high and stable, so
   an intermittently-requoting MM keeps the ask in line with the public forecast.
   Weather is a PURE public-data game = the worst case for the v7-B/v8-A
   cross-the-ask phantom (the MM runs the identical model). The "thin/slow books"
   escape is asserted, not evidenced, and is a $0 read-scope probe away.

2. **+7.9pp is a subset-mined artifact from a FAILED gate, wrong mechanism.**
   phase-1.6 headline failed 4/5 (C1 1.44x, C2 1.49pp, C3 0/22, C5 -0.51pp). The
   +7.9pp is an informational non-gate line, conditioned on |g(p)-p|>2pp where g
   is the isotonic map being validated (circular selection), produced by a market
   recalibration NOT an external forecast. Hit rate rising 64%->90% with training
   size WHILE net edge falls -0.49pp->-0.81pp = a map memorizing the FLB and
   losing the fee. The external-forecast result it needs does not exist anywhere.

3. **Hurdle arithmetic on the REAL price distribution (near-dispositive).**
   KXHIGH outcome rate 0.213, mid p50 0.197, p95 0.512. Worst-case taker fee
   ceil(0.07*P*(1-P)) cents is a FIXED-cents charge, brutal on cheap notional:

   | Price P | Taker fee | Fee as pp of notional | +1c spread pp | Total hurdle (+0.5pp margin) |
   |---|---|---|---|---|
   | 0.05 | 1c | 20.0 | 20.0 | ~40pp |
   | 0.20 (p50) | 2c | 10.0 | 5.0 | ~15.5pp |
   | 0.35 | 2c | 5.7 | 2.9 | ~9pp |
   | 0.51 (p95) | 2c | 3.9 | 2.0 | ~6.4pp |

   The generic ~3pp favorite hurdle assumes ~0.80; KXHIGH does not trade there.
   The bulk of the distribution needs a 6-15pp net edge; the record is gross
   1.49pp. Fails by ~an order of magnitude.

4. **Existing infra unusable + leaky.** `data/weather.py::
   fetch_historical_forecast_ensemble` uses the free Open-Meteo
   historical-forecast-api (no GRIB), BUT it is SINGLE-MEMBER (line 162
   `out[d]=[float(t)] # single-member`) so it cannot produce a threshold
   probability, AND it has an unimplemented as-of pin (lines 144-147) = a
   phase-1.5-class leakage trap that would fabricate skill (a forecast that saw
   post-trade-time runs).

5. **Capacity + no-third-bite.** 6.8% of volume, 5 cities, ~74 trades/market,
   sub-dollar/week tradable tail. EC-1 weather killed Round 1; recalibration just
   killed (v24 idea 1). The taker-on-external-forecast carve-out is legitimate
   only with a genuine as-of NWP signal, which the cheap infra cannot deliver
   without the leakage fix + ensemble build.

## Head-to-head: weather-taker vs sports-props-taker

| Axis | Weather (Idea 2) | Sports-props (alternative) |
|---|---|---|
| Honest prior | ~6-8% | ~12-18% |
| Capacity | 6.8% volume, thin, sub-$1/wk | 66.7% volume; capacity lives here |
| Engineering | Medium: ensemble fetch + leakage audit (~2-3d) | Lower: pip tabular (nflverse/pybaseball/ESPN), no GRIB |
| Capture phantom | Severe (pure public data) | Lower on thin props (MM staleness more credible) |
| Prior negatives | EC-1 killed; recalibration killed; phase-1.6 net -0.51pp | v5 sportsbook_fade NULL n=90; but v14 MLB taker is LIVE |

Decisive asymmetry: weather's forecastability (its selling point) is exactly why
the MM ask is hardest to beat. Sports-props edge lives in props thin enough that
the MM has not modeled them, a more credible source of staleness. On
prior x capacity / engineering cost, sports-props wins on all three terms.
**Screen sports-props first.** Hold weather behind the $0 ask-lag probe.

## Verdict: KILL (prior ~6-8%); reprieve only if a $0 live-ask-lag probe surprises.

## Must-have constraints (carried forward to any taker idea)

1. **$0 pre-build capture probe (gating)** before any fetcher engineering:
   read-scope snapshot live ask vs current public forecast at T-1/2d; KILL if the
   ask already tracks the forecast.
2. **As-of leakage pin (BLOCKING):** any historical forecast pinned to the run
   issued strictly before trade time; assert-fail otherwise.
3. **Real ensemble -> real probability**, not a deterministic point dressed as a
   probability.
4. **Pre-register the breakeven inequality on the REAL price distribution**
   (price-specific hurdle, not a generic 3pp), worst-case taker fee + >=1c spread
   + >=0.5pp margin; refuse to run if it fails on paper.
5. **External-only signal; no recalibration/proxy fallback** (else no-third-bite).
6. **One frozen decision rule, one binding statistic:** aggregate OOS net P&L,
   event-cluster bootstrap (seed 42), no per-band/per-city rescue; LOCO/WF as
   diagnostics only.
7. **Signal-adverse-selection guard:** check whether large divergences are
   disproportionately days the model is WRONG (taker analog of fill toxicity).
8. **Forward shadow crosses the REAL live ask** (not the print mid): >=30 settled
   fills, net/fill>0 with market-day-clustered CI excluding 0 and point >=+1.0pp,
   day-30 hard stop if <10.
9. **Capacity gate:** pre-register min net $/week at $1-2 notional; NULL a
   thin-tail survivor regardless of CI.
10. **No third bite.**
