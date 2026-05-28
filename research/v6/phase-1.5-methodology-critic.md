# v6 Phase 1.5 Methodology Critic

**Date:** 2026-05-25
**Author:** Methodology critic agent (adversarial, pre-data pull)
**Status:** Read-only review. Findings frame either a lock-ready confirmation or a required-revision list before Phase 2.
**Predecessor reads:** `00-master-plan.md`, `01-microstructure-literature.md`, `02-data-feasibility.md`, `03-kalshi-crypto-profile.md`, `04-v5c-novelty-audit.md`, `05-phase-1-synthesis.md`, `phase-1.5-methodology.md`, `research/v5/07-critic.md`, `src/kalshi_bot_v5/crypto_features.py`. Spot-checked `data/v6/kxbtcd_sample_trades.parquet` schema and `data/v6/kxbtcd_live_orderbook_snapshot.parquet` for bid/ask convention.

## Executive summary

The methodology is close to lock-ready but ships with one **Killer** finding that must be corrected before any feature is computed: the CVD sign convention in section 2 (`+1 if ask, -1 if bid`) cross-references the Phase 1 synthesis claim that "ask = taker bought yes" but the actual `/historical/trades` schema shows the inverse, `taker_book_side='ask'` co-occurs PERFECTLY with `taker_outcome_side='no'` (n=9446 in `data/v6/kxbtcd_sample_trades.parquet`, zero off-diagonal). The doc's verbal description of the signal direction is inverted. Four **Important** findings cover self-reference framing, the C4 magnitude gate being too lenient against v5-B-style failure, maker-vs-taker mission misalignment in the binding gate, and a kalshi_price_drift phantom-edge analog. Five **Minor** findings round out the audit. Verdict: **NEEDS REVISION**.

## Findings

### Killer Finding 1: CVD sign convention is inverted vs Phase 1 synthesis claim

**What's wrong.** Methodology section 2 row F1: `sign = +1 if 'ask', -1 if 'bid'. Aggressive YES buys vs aggressive YES sells.` Phase 1 synthesis line 26: `ask = +1 (taker bought yes, signed buy), bid = -1`. Direct query of `data/v6/kxbtcd_sample_trades.parquet` (n=9,446 trades):

```
taker_book_side x taker_outcome_side:
            no    yes
ask       4397      0
bid          0   5049
```

`taker_book_side='ask'` ALWAYS means `taker_outcome_side='no'` (taker bought NO, bearish on YES settling). `taker_book_side='bid'` ALWAYS means `taker_outcome_side='yes'` (taker bought YES, bullish). The doc's verbal interpretation (`ask = taker bought yes`) is the OPPOSITE of the data, so as written `kalshi_cvd_15min > 0` would mean "many bearish NO buys recently" not "many bullish YES buys." Live orderbook snapshot confirms `yes_ask + no_bid = 1` exact across 318 markets, so `taker_book_side` and `taker_outcome_side` carry the same info; the doc transcribed the relationship backwards.

**Why it matters.** Sign-flipped features are a v5-B failure-mode analog. The model can still fit (LogReg coefficient flips sign), but every interpretive statement is backwards, downstream sign-constraint checks (if any) will reject the feature, and the verdict text written from this lock doc will be inverted. This is exactly the kind of "verbal claim that didn't survive contact with data" that produced v4's wrong-cutoff bug and v5-B's `last_price_dollars` confusion. The methodology must pin sign conventions to a verified data probe.

**What would have to change.** Section 2 row F1 must restate F1 as `+1 if taker_outcome_side='yes' (bullish), -1 if 'no'`, OR `+1 if taker_book_side='bid', -1 if 'ask'` (equivalent on data). Align Phase 1 synthesis line 26 to match. Add a section 11 entry test: "kalshi_cvd direction must be verified against `taker_outcome_side` ground truth before any trainer runs."

This is a 5-minute fix, not a v6 NULL, but the lock is invalid as written.

### Important Finding 2: Self-reference framing under-specifies what F1 orthogonality is testing

**What's wrong.** Section 3.3's correlation pre-screen handles raw collinearity but F1 (kalshi_cvd) and kalshi_mid are correlated by construction (the trades USED to compute CVD also moved the mid). The orthogonality lift then has a subtly different interpretation than in v5-C: it tests not "external signal beats Kalshi price" but "F1 carries info beyond what last-traded-price has absorbed at time t." For 80% of contracts (median 0 trades in T-15, 1 in T-30 per Agent C), the mid is stale-by-construction; for the rest, it isn't.

**Why it matters.** F1 may pass C1 only because the mid is stale in 80% of contracts. The model then learns "the mid is stale, CVD is the live price reading," which is a regime-conditional artifact, not a generic alpha. This is v5-B's "model anchors on price" mode running in reverse.

**What would have to change.** Add section 3.5 self-reference diagnostic: compute pairwise correlation of F1 with kalshi_mid conditional on `time_since_last_trade < 5min` vs `>= 5min`. If F1's orthogonality lift concentrates in the stale-mid subset, label as contract-state-conditioned. Optionally use a forward-recorded synthetic mid as the baseline; if unavailable, document the limit.

### Important Finding 3: C4 magnitude gate at 5% / 0.03 is too lenient vs v5-B failure mode

**What's wrong.** C4 requires "5% of holdout observations have `|model_prob - mid| >= 0.03`." This catches v5-B's "shrinkage to 0.5" mode where deltas are bounded under 0.025. But a model with `|delta| >= 0.03` on 5% of observations can still fire the +2c-rule only 50 times across 5000 contract-days if those 5% sit on one side of mid or in low-fire-eligibility contracts. C3's cluster-bootstrap CI is computed on PER-CONTRACT P&L without a minimum fire-count, so tail-luck on 50 fires can pass.

**Why it matters.** The brief explicitly flags this: "+2c rule fires < 100 times across 5000 contract-day clusters." A Brier-positive model with 50 wins concentrated on one cluster day can pass C2 and C3 on bootstrap variance alone.

**What would have to change.** Add C4b: "+2c-rule must fire at least 200 times on final holdout midband (or 1% of holdout n, whichever is lower)." Without this floor, v6 inherits v5-B's "model has signal but cannot extract" failure mode without detection.

### Important Finding 4: Maker-mission misalignment in binding gate

**What's wrong.** Section 6.1 binding rule is taker (+2c-rule, fill at ask). Section 6.2 maker-quote rule is "sensitivity only, NOT primary gate." Per CLAUDE.md, the operator mission is higher-frequency MAKER fills, and `research/key-findings.md` fact 1 is "Makers > Takers structurally." Per `01-microstructure-literature.md` section 5, taker economics at T-30/T-15 are dominated by adverse selection in a way maker economics are NOT. So a v6 NULL on +2c-rule could mean "no signal" OR "signal exists but taker eats it"; the methodology cannot distinguish.

**Why it matters.** The taker-side gate evaluates a strategy the operator does not intend to deploy. The maker rule has different thresholds (>= 0.04 vs +2c), different fill economics (38% fill, 15% effective), different range (0.30 to 0.85 vs 0.20 to 0.85). It is an independent rule, not a perturbation.

**What would have to change.** Either elevate section 6.2 maker-quote rule to a second binding criterion (both must pass for full SHIP), OR document explicitly that v6 has scoped to taker-side and write the verdict to say "maker-side untested in v6 scope" if C3 fails. The current text inherits both framings and produces an ambiguous NULL.

### Important Finding 5: kalshi_price_drift phantom-edge analog at first-trade contracts

**What's wrong.** F4 is `last_traded_price(t) - last_traded_price(t - N min)`. Per Agent C, median KXBTCD contract has 0 trades in T-15 and 1 in T-30. At T-30 for many contracts, `last_traded_price(t-30)` is the single trade of the entire contract lifetime; at T-15, it's the same trade. Drift will be exactly 0 by construction for these.

The build risk: if the implementation reads `last_traded_price(t-N)` by sliding back through OTHER tickers' trade prints, or by carrying a stale value across the contract boundary, F4 becomes a phantom-drift signal whose magnitude correlates with contract-traded-vs-untraded state, not with forward information. Orthogonality passes (kalshi_mid is also stale on those contracts) but the model learns "untraded contracts have drift = 0, traded contracts have nonzero drift, traded contracts have asymmetric outcomes."

**Why it matters.** This is the v5-B `last_price_dollars` pattern at a different layer: a feature that looks predictive in-sample but encodes contract-state, not signal. The doc's section 6.3 disclaim ("v5-B failure mode structurally impossible") is true for kalshi_mid baseline; F4 needs its own guard.

**What would have to change.** Add to section 11: "kalshi_price_drift must be NaN when `time_since_last_trade > N min` OR when `t - N` falls before contract open_time. Unit test rejects cross-contract lookups." Add K1b: "If F4's orthogonality lift comes from contracts where drift is 0 by construction (no second trade in window), F4 is a contract-state artifact, drop."

### Minor Finding 6: Funding-delta epoch-boundary concern is structurally absent

Deribit `interest_1h` is rolling-1h, not per-epoch funding payments (vs Binance/Bybit 8h-epoch payments). Per `02-data-feasibility.md` section 4, the delta over 4h is smooth across Deribit's funding update cadence. The brief's epoch-jump concern doesn't apply to the chosen data source. Add a single-line note to F5 in section 2.

### Minor Finding 7: Orthogonality holdout cluster count is comparable to v5-B at low-n end

At midband-low-end (10k contracts post-eligibility), 25% ortho holdout = 2,500 contracts across ~100 daily clusters. Cluster-bootstrap precision is O(1/sqrt(100)), comparable to v5-B's 43-cluster regime. Manageable but not tight. Add a single-line note to section 4.2.

### Minor Finding 8: Coinbase 1m candle dropout in announcement windows

Coinbase's `/products/BTC-USD/candles` can return NaN for zero-volume minutes. If the 30-bar realized-vol calculation runs on fewer than 30 bars, the read is mildly biased; if NaN is forward-filled as 0, realized vol reads as 0 during announcement minutes. Effect is small (~1-2 missing bars per CPI/FOMC event, ~10 events per year out of 8,000 hourly samples). Add to section 11: "Coinbase 1m candles must be checked for NaN gaps; missing-bar count must be flagged as `nan_pct_in_window` and reported alongside realized_vol."

### Minor Finding 9: DVOL stale-print risk is structurally absent

DVOL is an index value, not a tradeable contract; no settlement event. The Deribit `get_volatility_index_data` endpoint returns hourly OHLC computed at fixed hourly boundaries from the option chain. No v5-B `last_price_dollars` analog applies. Optionally add a one-line note to section 6.3.

### Minor Finding 10: K1 should classify widerband-only orthogonality passes as tail-asymmetry

K1 fires when 0 features pass on midband AND widerband. A widerband-only pass is most likely the wider sample picking up extreme-tail asymmetry (yes_rate near 0.98 leaves Brier headroom under +0.001 per v5-C2). Add to K1: "Any widerband-only pass must be explicitly traced to a tail-asymmetry mechanism in Section 4.2; if so, label as null."

## What is structurally sound

- 60/25/15 chronological split with 24h purge is appropriate for hourly-cadence KXBTCD. Adjacent-hour contracts share BTC events (e.g., Fed announcement at 14:00 affects contracts at 14:00, 15:00, 16:00) but a 24h buffer comfortably separates train-end from ortho-start. Multi-day events are rare for 1h-lifetime KXBTCD.
- The funding-delta amendment in section 3.2 (residualize delta net of level) is exactly the Agent D recommendation, correctly applied.
- C2 BSS >= +0.01 on FINAL holdout, with the holdout reserved until end of Phase 2, is correctly walled off.
- Sample-size guards in section 3.4 (train YES/NO >= 50, test YES/NO >= 30) directly address v5-C2's single-class trap.
- Section 9 "what we will NOT do" inherits the v5 lessons cleanly (no last_price_dollars, no pre-Oct-2024, no narrow [0.70, 0.95], no post-hoc tuning). Load-bearing.
- Section 12 reproducibility manifest would have caught v5-B's `last_price_dollars` substitution if v5-B had used one.

## Verdict

**NEEDS REVISION.**

Required revisions list:

1. **(Killer) Fix the CVD sign convention in section 2 row F1.** Re-anchor to verified `taker_outcome_side` data, not the Phase 1 synthesis verbal description. Update Phase 1 synthesis line 26 to match. Add section 11 entry test: "CVD direction verified against `taker_outcome_side` ground truth before trainer runs."
2. **(Important) Add section 3.5 self-reference diagnostic.** Correlation of F1 with kalshi_mid conditioned on `time_since_last_trade < 5min` vs `>= 5min`. Label F1 as contract-state-conditioned if lift concentrates in stale-mid subset.
3. **(Important) Add C4b minimum fire-count floor.** "+2c-rule fires at least 200 times on final holdout midband (or 1% of n, whichever is lower)."
4. **(Important) Resolve maker-vs-taker primary gate.** Elevate section 6.2 to a second binding criterion, OR explicitly scope v6 to taker-side and write the verdict accordingly.
5. **(Important) Phantom-drift guard for F4.** kalshi_price_drift NaN when `time_since_last_trade > N min` or `t - N` pre-dates contract open_time. Unit test for cross-contract lookups. Add K1b kill condition.
6. **(Minor) Notes:** Deribit interest_1h rolling-not-epoch (F6); midband cluster count ~100 days at low-n end (F7); Coinbase 1m gap handling (F8); K1 widerband-only pass labeled as tail-asymmetry (F10).

After these revisions, the methodology should be re-locked and a SECOND methodology critic pass run to confirm the Killer is resolved. The other Important findings and Minor notes are diagnostic additions and do not require re-critic if (1) is fixed cleanly.

**Modal expected outcome of v6 unchanged.** Revisions sharpen the methodology but do not change Phase 1 synthesis's 80% NULL prior. The Killer is a 5-minute lock-doc fix, not a v6 NULL. Finding 5's phantom-drift guard is engineered to catch the v5-B mode at sub-hour scale during Phase 2.
