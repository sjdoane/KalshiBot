# v7 Phase 3 Adversarial Critic: naive_p_yes adjudication

**Date:** 2026-05-26
**Author:** Agent v7-Critic (independent adversarial pass over v7 Angle B diagnostic finding)
**Status:** Read-only review. No modifications to v7 source, dataset, or v6 source.
**Predecessor reads:** `03-kronos-methodology.md`, `05-kronos-results.md`, v6 `phase-1.5-methodology.md`, v6 `09-critic.md`, v6 `03-kalshi-crypto-profile.md` (Agent C), v5 `07-critic.md`, `data/v6/v6_master.parquet`, `data/v7/kronos_predictions.parquet`, `data/v7/kronos_orthogonality.json`, `src/kalshi_bot_v7/kronos_features.py`, `src/kalshi_bot_v6/v6_features.py`, `scripts/v6/build_v6_master.py`, `scripts/v7/run_kronos.py`, `scripts/v7/run_kronos_orthogonality.py`. Live probes of /markets and Coinbase BTC-USD at 2026-05-26 19:16-19:24 UTC.

---

## Executive summary

**VERDICT: PARTIAL.** The +0.20842 Brier improvement of `naive_p_yes` over `kalshi_mid_at_t` reproduces exactly to 5 decimal places and is a REAL predictive signal. The Brier baseline is the legitimate AS-OF horizon-time last-traded price, NOT the v5-B `last_price_dollars` post-settlement phantom. At T-30 min, BTC spot vs strike with vol-scaled Normal-CDF predicts hourly Kalshi outcomes with 100% accuracy on 126 of 154 midband orth contracts where the model is high-conviction.

BUT the signal is largely UNMONETIZABLE for two compounding reasons. First, 73% of midband orth contracts have zero trades between t and close_time, so most "obvious" signals never see a counterparty. Second, when trades DO fire, the observed yes-taker print ASK is on AVERAGE 18.7c BELOW stale mid: the orderbook ASK updates even when no trade-print refreshes `kalshi_mid_at_t`. Of 37 observed-ASK cases, 62% have ASK closer to stale mid and 38% have ASK closer to naive_p. The +2c-take rule simulated against actual observed ASKs fires only 19 times (vs naive simulation 147) at +54.6c per fire vs naive's +32.2c. Live snapshot of currently-open midband KXBTCD shows the orderbook is ACTIVELY UPDATED (mean |signal_vs_mid| = 0.5c, 0 of 188 contracts have strong signals), strongly suggesting the naive simulation over-fires.

Recommended next step: do NOT ship the +2c-take rule directly; v8 Angle B should build prospective sampling of /markets orderbook snapshots at T-30 / T-15 to measure the true ASK-mid relationship and re-run the simulation against measured ASKs over 60-90 days. Without prospective data, claiming a +32c per-contract edge is unsupported and replays the v5-B phantom-edge pattern more subtly.

---

## Test 1: Independent reproduction of +0.20842 lift

Loaded all data, independently parsed strike, computed naive_p_yes from spot at t and stored Kronos sigma. Applied 60/25/15 chronological split with 24h purge, midband [0.55, 0.80] filter, C=10 logit, seed 42.

| feature | my lift | reported lift |
|---|---|---|
| naive_p_yes | +0.20842 | +0.20842 |
| spot_minus_strike | +0.20781 | +0.20781 |
| kronos_p_yes | +0.20217 | +0.20217 |

**Finding 1.1: Minor (verification).** Matches to 5 decimals. No methodology bug.

---

## Test 2: kalshi_mid_at_t source verification (v5-B phantom-edge analog)

Read `v6_features.py:kalshi_mid_at_t` and `build_v6_master.py`. Sampled 20 random stale-mid rows (tslt >= 10 min); for each, loaded `data/v6/cache/trades_{ticker}.parquet`, found last trade <= t, compared its yes_price_dollars to stored kalshi_mid_at_t; verified last trade time is strictly before close_time.

- 20/20 rows: stored mid matches actual last-trade price to 4 decimals.
- 20/20 rows: last trade is BEFORE close_time. No post-settlement reads.
- Source: `kalshi_mid_at_t` returns `last yes_price_dollars at most recent trade <= t`. Fetch window is `[close - 60min, close + 2min]`.

**Finding 2.1: Important.** The baseline is NOT the v5-B Killer 2c phantom. v7 correctly inherits v6 Section 11 hygiene. The +0.208 improvement is a real comparison against a legitimate (if stale) Kalshi price signal.

---

## Test 3: Stale-mid prevalence

On 154 orth midband: mean tslt 14.98 min, median 15.4, p25 4.5, p75 26.3. **Fraction with tslt >= 5 min: 114/154 = 74.0%** matches the v7 report claim exactly.

**Finding 3.1: Minor.** Consistent with v6 Agent C's profile (median 1 trade in T-30, 0 in T-5).

---

## Test 4: ACTUAL ASK at sample time (CENTRAL TEST)

For each of 154 orth midband contracts, extracted ALL trades in (t, close_time]. `taker_outcome_side='yes'` means taker crossed YES ask (trade price IS yes_ask at that moment). Computed `min_yes_ask_after_t` per contract.

- Has any trade after t: 41/154 (26.6%).
- Has yes-taker print (observed ASK): 37/154 (24.0%).
- Fresh subset (tslt < 5): has next trade 77.5%.
- **Stale subset (tslt >= 5): has next trade 8.8%.**

Among 37 observed-ASK cases:
- mean ASK - stale_mid: -0.187 (observed ASK 18.7c BELOW stale mid on average)
- mean ASK - naive_p: -0.038
- fraction where ASK is closer to stale mid: 62.2%
- fraction where ASK is closer to naive_p: 37.8%
- fraction with |ASK - stale_mid| > 10c: 48.6%

Case-by-case (37 rows): ~14 have ASK at stale mid +/- 2c (real stale-orderbook); ~12 have ASK moved 20-70c toward naive_p (MMs updated); ~11 partway.

**Finding 4.1: Killer (the central question).** The orderbook ASK is NOT uniformly at stale mid + 1c. 38-50% of observed cases show ASK has materially moved toward spot-implied price. The +0.208 Brier IS real against the stale mid baseline, but the +2c-take rule simulated against `kalshi_mid_at_t + 0.01` overstates the actual extractable edge.

**Finding 4.2: Important.** Selection bias: 73% of stale-mid signals have NO post-t trade and no observable ASK. We cannot directly verify the ASK for the majority of contracts where the rule fires.

---

## Test 5: +2c-take rule on naive_p_yes (3 simulations)

Per v6 Section 6.1. Three variants:
- **NAIVE**: assume yes_ask = kalshi_mid_at_t + 0.01.
- **REALISTIC observed-only**: only fire when a yes-taker (or no-taker for BUY NO) print exists in (t, close]; use observed price as ASK.
- **HYBRID**: observed ASK when available; else fall back to stale-mid + 1c.

| Strategy | n_fires | mean PnL | 95% CI | n_days |
|---|---|---|---|---|
| NAIVE | 147 | +32.2c | [+25.8, +38.5] | 57 |
| REALISTIC observed | 19 | +54.7c | [+46.2, +63.1] | 18 |
| HYBRID | 143 | +40.0c | [+34.0, +46.3] | 55 |

NAIVE on FINAL holdout (n=91): 85 fires, +34.5c, CI [+27.4, +41.5]. Reproduces.

Spread sensitivity (NAIVE): 2c -> 147 fires +32.2c; 3c -> 146 fires +32.1c; 4c -> 145 fires +31.4c; 5c -> 144 fires +31.3c. Spread is not the binding constraint.

**Finding 5.1: Killer.** Under NAIVE assumptions, the rule blows through every v6 gate: n_fires >> 200/1% C4b floor, bootstrap CI strictly positive, FINAL reproduces. Per the LOCKED methodology this would be unambiguous SHIP. But NAIVE is contradicted by Test 4: the actual ASK is NOT uniformly at stale mid + 1c. The REALISTIC subset (only confirmed-fillable observations) yields +54.6c on n=19, which FAILS C4b's 200-fire floor. HYBRID at +40c is the most defensible operational estimate IF the stale-mid assumption holds for the 124 unobserved contracts.

**Finding 5.2: Important.** Per-side breakdown is YES n=85 hit rate 97.6% mean +22.0c, NO n=62 hit rate 14.5% mean +46.3c. Both directions confirm naive_p correctly predicts outcomes.

---

## Test 6: Maker-quote rule on naive_p_yes

Per v6 Section 6.2: BUY YES if naive_p - mid >= 0.04, 0.30 <= mid <= 0.85, quote at mid - 0.01. Mirror for BUY NO. 15% fill rate, maker fee.

| fill rate | n_fires | mean ex-PnL | conditional |
|---|---|---|---|
| 0.15 | 138 | +5.56c | +37.1c |
| 0.10 | 138 | +3.71c | +37.1c |
| 0.05 | 138 | +1.85c | +37.1c |

**Finding 6.1: Important.** At v6's 15% fill assumption, maker-quote yields +5.6c per fired contract with strictly positive CI. Inherits the same orderbook assumption: if the actual mid is closer to naive_p than to stale-print mid, the maker quote at `mid - 0.01` is deeply uncompetitive and the 15% fill assumption collapses.

---

## Test 7: Live-snapshot orderbook reality check

At 2026-05-26 19:16-19:24 UTC, pulled live /markets?series_ticker=KXBTCD&status=open. Got 188 contracts closing in 0-60 min with two-sided live quotes. Pulled live Coinbase spot ($75,716-$75,754) and 120 min of 1m candles for sigma estimate. Computed naive_p_yes per contract.

- Mean live spread: 0.0100 (tighter than Agent C's 2c).
- Distribution of |naive_p - mid|: mean 0.0053, p75 0.0040, max 0.0462.
- **Number of strong-signal contracts (|naive_p - mid| >= 0.10): 0 of 188.**
- Live midband (mid in [0.55, 0.80]): 2 contracts. Mean spread 1c, mean abs signal 3.6c.

**Finding 7.1: Killer (calls the diagnostic into question).** Currently the Kalshi orderbook is TIGHTLY ALIGNED WITH SPOT. The historical +0.208 Brier improvement is computed against the last TRADE PRINT, but live evidence strongly suggests MMs actively maintain orderbook quotes against spot independent of whether trades fire. **The trade-print mid is stale; the orderbook quote mid is current.** The Brier improvement is fundamentally measuring how stale the trade-print is vs the orderbook, not vs the truth.

**Finding 7.2: Important.** v6 critic flagged this exact gap (Finding 6.1): the build script does not pull /markets snapshots at horizon time, only /historical/trades. v7 inherited the same limitation and discovered an improvement over a stale-trade-print baseline that may not survive against an orderbook-mid baseline.

---

## Test 8: Survivorship bias on Kronos drops

51 of 971 inferences (5%) returned non-ok (45 nan_window, 6 no_context). Drop rate by month: distributed evenly. By mid band: midband 4.8%, low-mid 0%. All drops trace to Coinbase 1m cache gaps.

**Finding 8.1: Minor.** Structural, not biased toward winners. +0.208 lift is not survivorship-inflated.

---

## Test 9: Information dynamics

Combined live (Test 7), regression of observed ASK on (kalshi_mid_at_t, naive_p_yes) in Test 4, and direct measurement of ASK behavior.

- Live snapshot: orderbook actively aligned with spot, 0 strong signals on 188 currently-open.
- Historical observed-ASK cases (n=37): mean |ASK - stale_mid| = 0.213, mean |ASK - naive_p| = 0.346; but the conditional mean ask_delta_from_mid (signed) is -18.7c, consistent with "when spot moved against stale mid, MMs cancel stale ask and post lower."
- 62% of observed cases closer to stale mid by raw distance; 38% closer to naive_p.

**Finding 9.1: Killer.** Market microstructure picture: (a) when spot has not moved (naive_p ~ mid), orderbook stays at stale mid, no edge; (b) when spot has moved meaningfully, orderbook updates toward naive_p quickly, MMs reprice, and a +2c-take rule against stale mid either (i) does not fill because the visible ask has moved or (ii) fills at the new updated ask which is no longer profitable. The +0.208 Brier is what you'd EXPECT from any feature that tracks the true orderbook mid better than the last-trade-print does, even though that feature has no tradeable edge.

**Finding 9.2: Important.** This is the v7 analog of v5-B Killer 2c. v5-B used `last_price_dollars` (post-settlement). v7 used `kalshi_mid_at_t` (legitimate AS-OF horizon-time last-trade). Both proxies systematically diverge from the true transactable ASK in regimes where no trade has happened recently. The v7 diagnostic is more refined but the operational claim is unsupported.

---

## Test 10: Salvage paths

**S1: Prospective orderbook-snapshot collection (PRIOR 40%, COST: 60-90 days + ~$1 API).**

Re-run `scripts/v6/probe_kxbtcd_microstructure.py` hourly for 60-90 days, capturing yes_ask_dollars / yes_bid_dollars / size_fp at multiple T-N marks. Compute naive_p_yes against the REAL orderbook ASK at horizon-t. Re-run +2c-take rule against measured ASKs. If the +0.208 Brier survives against ORDERBOOK mid (not trade-print mid), the signal is monetizable. If not (most likely per Test 7), v7-B closes.

**S2: Tighter execution rule (PRIOR 15%).**

If S1 confirms ASK matches spot in fresh-orderbook regimes, the residual edge is in stale-orderbook regimes only. Filter: fire only when (a) tslt >= 10 min AND (b) top-of-book size_fp has not changed since last trade (indicates stale resting order). Sample size may collapse below C4b. Could be a real edge but probably too narrow.

**NOT recommended.**
- Take v7-B straight to live. Replays v5-B and v3-W1 failure mode (apparent +5.98c per contract from stale-price proxy, killed on realistic-spread audit).
- Fine-tune Kronos. Kronos contributes -0.00148 over naive (Stage B3 D-A).
- Restrict to fresh-mid subset. Lift drops to +0.11 on n=40; orth bootstrap collapses.

---

## Findings summary

| # | Finding | Severity | Test |
|---|---|---|---|
| 1.1 | +0.20842 reproduces to 5 decimals | Minor | 1 |
| 2.1 | kalshi_mid_at_t is legitimate AS-OF last-trade, NOT post-settlement; v5-B phantom absent | Important | 2 |
| 3.1 | 74% stale-mid prevalence reproduces | Minor | 3 |
| 4.1 | Observed ASK NOT uniformly at stale mid + 1c; 38-50% have moved toward naive_p | Killer | 4 |
| 4.2 | 73% of stale signals have NO post-t trade; ASK unobserved in majority | Important | 4 |
| 5.1 | NAIVE +2c = +32.2c (147 fires); REALISTIC = +54.7c (19 fires, fails C4b); HYBRID = +40c (143); truth uncertain in this range | Killer | 5 |
| 5.2 | Per-side breakdown confirms direction; spread 2c-5c insensitive | Important | 5 |
| 6.1 | Maker-quote +5.56c at 15% fill, inherits same orderbook assumption | Important | 6 |
| 7.1 | LIVE: 0 of 188 currently-open contracts have strong signal; orderbook actively aligned with spot | Killer | 7 |
| 7.2 | v6 critic flagged this data gap; build script never fetched /markets snapshot at horizon | Important | 7 |
| 8.1 | 5% Kronos drop is structural, not biased | Minor | 8 |
| 9.1 | MMs DO watch spot; +0.208 is improvement over stale TRADE PRINT, not stale ORDERBOOK | Killer | 9 |
| 9.2 | v7-B is v5-B Killer 2c analog with more legitimate baseline but same operational gap | Important | 9 |

**4 KILLER, 7 IMPORTANT, 3 MINOR.** Killers do not refute the +0.208 Brier improvement; they sharpen its interpretation from "tradeable edge" to "improvement over stale trade-print of unknown operational value."

---

## Verdict on v7 Angle B naive_p_yes: PARTIAL

**The diagnostic is REAL.** Kalshi midband contracts at T-30 are predictable to 95-100% accuracy in 82% of cases using just current spot vs strike. v6 missed this by constructing Coinbase features as returns rather than as price levels.

**The operational extraction is UNCERTAIN.** The +0.208 Brier is against a stale TRADE-PRINT baseline. The actual orderbook ASK is mixed (some fraction stale, some updated). Live evidence at 2026-05-26 19:24 UTC strongly suggests MMs actively maintain orderbook alignment with spot. Test 5 simulations span +32c (NAIVE) to +54c (REALISTIC) per fired contract; without prospective orderbook data, the P&L cannot be pinned within that range. The most-conservative simulation (n=19 over 18 day clusters) fails v6 C4b 200-fire floor.

**Recommended next step: build v8 Angle B with prospective orderbook collection.**

1. Wire `scripts/v6/probe_kxbtcd_microstructure.py` to run hourly for 60-90 days. Capture yes_ask_dollars, yes_bid_dollars, size_fp at every cron iteration. Cost ~50k snapshots, < $1 API spend.
2. After 30 days, recompute `kalshi_mid_at_t_orderbook` from snapshots. Recompute the +0.208 Brier comparison against orderbook mid. If improvement collapses below +0.005, v7-B is CLOSED as a stale-trade-print phantom; v8-B project ends NULL.
3. If improvement survives at orderbook mid, simulate +2c-take against measured ASK. If clears C3a (CI > 0) and C4b (>= 200 fires), v8-B SHIP.
4. NO LIVE CAPITAL until step 3 confirms.

**Operator capital remains at $32 unchanged.** v1 continues with W1 denylist applied. The discovered diagnostic is preserved as a v7 cache artifact for v8 prospective study.

**Replay-prevention note for future rounds:** "Stale trade-print mid as Brier baseline can produce huge but unmonetizable Brier improvements when the orderbook is more up-to-date than the last trade print. Always validate bid/ask snapshot at horizon time against the actual orderbook before claiming a tradeable edge." This is the v7-B analog of v5-B Killer 2c with one critical difference: v5-B used a post-settlement field; v7-B uses a legitimate pre-close trade print. The CATEGORY is the same: stale-price-proxy as ASK proxy.
