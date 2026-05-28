# v6 Phase 1 Synthesis

**Date:** 2026-05-25
**Inputs:** `01-microstructure-literature.md`, `02-data-feasibility.md`, `03-kalshi-crypto-profile.md`, `04-v5c-novelty-audit.md`.
**Status:** Phase 1 complete. Major scope pivot required before Phase 1.5 methodology lock.

## TL;DR

Phase 1 killed three of the five originally proposed v6 feature families on data, literature, or microstructure-realism grounds. The surviving feature surface is narrower than the original plan and centers on a different signal source (Kalshi internal orderflow) than the original plan (Binance external orderbook). The operator should confirm the pivot before Phase 1.5 methodology lock.

## What survived, what died

| Originally proposed v6 feature | Phase 1 finding | Status |
|---|---|---|
| Binance L5/L20 orderbook imbalance | Binance.com geo-blocked from US (HTTP 451 verified). Binance.US has no perpetuals. ccxt has no historical L2. Tardis.dev $350+/mo (6x to 22x over budget). | DROP from backtest. Forward-record only. |
| Cumulative Volume Delta (CVD) on external venues | Coinbase `/trades` has only ~4 min lookback. CVD is mathematically integrated OFI (Agent A) so collapses into OFI category anyway. Kalshi `/historical/trades` HAS `taker_book_side`, enabling Kalshi-internal CVD. | DROP external, KEEP Kalshi-internal. |
| Deribit 25-delta options skew | Da Fonseca and Wang 2024 (Op Research Letters) explicit null: BTC IV skew slopes "lack predictive capability for returns." Plus historical 25d RR requires manual Black-Scholes inversion across hundreds of option OHLCVs (~6 hours engineering). Free DVOL is a partial substitute but does not capture skew direction. | DROP. |
| Funding rate DELTA (vs level) | Deribit `interest_1h` is free and deep (1h granularity matches v6). Agent D confirms funding-delta is genuinely new and distinct from v5-C's funding-level test. Literature thin so prior is low. | KEEP, residualize against level. |
| Sub-hour horizons (T-30 / T-15 / T-5) | Agent C: 80% of KXBTCD contracts have ZERO trades in T-5; median is 0. T-30 has median 1 trade, T-15 has 0. Spread is 2c median across all bands (good). Depth is 1000 to 7000 contracts (great for retail). | KEEP T-30 and T-15 as primary; DEMOTE T-5 to secondary. |
| Kalshi own orderbook (spread, depth) | No historical endpoint. Forward-record only. | DEFER to v7 / shadow-mode. |

## What's genuinely new and backtestable

After Phase 1, the v6 backtestable feature surface is:

1. **Kalshi-internal CVD** (NEW per Agent D, available per Agent B): reconstructed from `/historical/trades`. CVD over T-N min = sum(count_fp * sign(taker_outcome_side)) where `yes` = +1 (taker bought YES, bullish), `no` = -1 (taker bought NO, bearish). Verified empirically against `data/v6/kxbtcd_sample_trades.parquet` (n=9446): `taker_outcome_side='yes'` always co-occurs with `taker_book_side='bid'`; `taker_outcome_side='no'` always co-occurs with `taker_book_side='ask'`. The original draft of this synthesis (and the methodology v1) had the sign inverted via `taker_book_side`; corrected by methodology critic.
2. **Kalshi trade momentum**: signed trade velocity, count of trades, time-since-last-trade, in T-N windows.
3. **Kalshi last-trade-price drift**: trajectory in T-60 to T-30 and T-30 to T-15. Distinct from level (which v5-C indirectly captured via raw mid).
4. **Funding rate delta** (NEW transformation, NEW horizon): Deribit `interest_1h` change over preceding 1h to 4h.
5. **Coinbase realized vol at T-30, T-15** (re-test with new horizons; v5-C tested at T-1h and failed).
6. **Coinbase VWAP deviation at T-30, T-15** (re-test with new horizons).
7. **DVOL term-structure delta** (Deribit `get_volatility_index_data`; v5-C did NOT test this).
8. **Spot-futures basis delta** (vs v5-C's basis level).

So 8 candidate features at 2 horizons (T-30, T-15) = 16 feature-horizon combinations. Plus the orthogonality screen will likely drop most.

## What this means for the v6 thesis

**Original v6 thesis**: external crypto microstructure (Binance OFI, Deribit options skew) at sub-hour horizons predicts KXBTCD settlement.

**Revised v6 thesis**: **Kalshi internal orderflow at sub-hour horizons (T-30, T-15) predicts settlement beyond what is already in the Kalshi mid.** Specifically, signed taker-flow imbalance and recent trade momentum on Kalshi's own book carry information that the Kalshi mid-price has not yet absorbed.

This is actually closer to the operator's listed angle 1 (Kalshi's own order book microstructure) than to angle 3 (external crypto microstructure). The pivot moves the signal source from "Binance leads Kalshi" to "Kalshi orderflow predicts its own settlement."

## Prior on outcome, revised

Original (pre-Phase-1) prior: P(SHIP-clean) ~5%, P(PARTIAL) ~25%, P(NULL) ~70%.

After Phase 1, considering:
- Most of the external-microstructure angle is unavailable (data or budget)
- Literature null on options skew confirmed before testing
- The surviving angle (Kalshi internal orderflow) is data-limited: median 1 trade in T-30, 0 in T-15
- Self-referential risk: Kalshi-internal CVD over T-N can be correlated with current Kalshi mid (the trades MOVED the mid). Orthogonality will likely drop CVD for this reason.

Revised prior: P(SHIP-clean) ~3%, P(PARTIAL) ~17%, P(NULL) ~80%.

The angle is still worth running because:
1. It closes the "have we tried Kalshi-internal microstructure?" frontier the operator mission requires.
2. Kalshi-own-orderflow is genuinely new (Agent D verified).
3. Sample is large (300k post-flip contracts, median 1 T-30 trade = maybe 30k feature rows).
4. Cost is minimal ($0 spend, modest agent-clock).
5. The Phase 1 findings themselves are a contribution (documenting that external microstructure is not retail-tradable from the US).

## Adversarial reading

Greediest interpretation that would CONTINUE TO KILL v6 even after the pivot:

- "Kalshi-internal CVD is by definition information already in the price, because Kalshi takers MOVED the price to get there. Sub-hour CVD is just a noisy reading of the same price the model is conditioning on. Orthogonality drops it for high correlation with raw_mid; no surviving features; null at Phase 1.5."

This is a defensible prior. v5-B exhibited this exact failure mode at 1000x scale (model anchored on price). The orthogonality screen is designed precisely to catch it; if v6 features all drop at orthogonality, v6 ends honestly at Phase 1.5 without burning Phase 2 budget.

## Recommended pivot for operator approval

**Option A: Continue v6 with pivoted scope.** Lock Phase 1.5 methodology around Kalshi-internal orderflow at T-30 / T-15, with Coinbase realized-vol and Deribit funding-delta as supporting features. Expected outcome distribution: 3% SHIP, 17% PARTIAL, 80% NULL. Cost: minimal (~$0 external, low LLM spend).

**Option B: Kill v6 at Phase 1.** Declare: literature plus data feasibility plus market profile already show the external angle is not retail-tradable from US, and the internal angle is at high prior of self-referential null. Write v6 final verdict as NULL at Phase 1 with the four Phase 1 docs as supporting evidence. Move on to v7 (different angle entirely) or to engineering improvements on v1.

**Option C: Pivot v6 to forward-record only.** Spin up Phase 2 as a forward-recording infrastructure (Kalshi own orderbook + Binance.US current L2 + Deribit Greeks) to collect 60-90 days of data, then re-evaluate. v6 becomes a setup project for v7; no verdict in this session.

## Open question for the operator

Which option? My honest recommendation is **Option A with a tight methodology lock** that will kill cleanly at Phase 1.5 if orthogonality drops everything. This is the cheapest way to either (a) close the frontier honestly, or (b) catch the small probability that Kalshi-internal CVD has marginal information.

But if the operator's clock is tight and "external microstructure not retail-tradable from US" is enough of an answer, Option B is also defensible. The kill-early principle endorses it.

## What the Phase 1 docs already contribute regardless

Even if v6 closes at Phase 1.5 NULL, Phase 1 produced:
- `01-microstructure-literature.md`: definitive literature null on Deribit 25d RR, confirmation that OFI alpha is sub-minute (not sub-hour).
- `02-data-feasibility.md`: definitive list of what's available free, what costs $29 to $350+, what's geo-blocked. Anyone proposing a future crypto angle starts here.
- `03-kalshi-crypto-profile.md`: KXBTCD median spread 2c, median 0 trades in T-5, depth 1k to 7k. Anyone proposing a Kalshi crypto strategy starts here.
- `04-v5c-novelty-audit.md`: precise list of what v5-C tested vs not, so future v7+ rounds don't accidentally re-test.
