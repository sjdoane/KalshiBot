# V10-A Strategic Synthesis (post lit-scout, pre-inventory)

**Date:** 2026-05-27
**Author:** V10-A orchestrator (this session)
**Inputs:** A2 v2 methodology lock, 01-lit-delta.md (v10A-2 scout), 06-v10a-revival-probe.md, Diercks 2026, Becker 2026

---

## Bottom line

V10-A has a **high prior of NULL** at retail scale, justified by three converging pieces of evidence:

1. Kim arXiv 2602.07048v2 reports +3.1pp win rate improvement WITHOUT fees, bid-ask, or slippage in P&L. This is idealized execution.
2. Becker 2026 documents Kalshi Finance category gross excess return of approximately +/-0.08% per trade on 4.4M trades. Essentially zero gross.
3. Diercks et al. 2026 (Federal Reserve) documents Kalshi macro markets as efficient against Bloomberg consensus and FRBNY Survey of Market Expectations. Institutional MMs (Susquehanna) make these markets tightly.

The convergence: Kim's apparent edge is GROSS-IDEALIZED on a market category that is GROSS-ZERO empirically and PRICED-EFFICIENTLY by institutions. The edge is structurally fragile.

## Why we proceed anyway

Despite the bearish prior, V10-A is worth running for three reasons:

1. **First-mover fee-net analysis.** No 2026 paper (including Kim itself) publishes net-of-fee P&L on Kim's method on Kalshi. A clean fee-net replication produces a useful answer whether PASS or NULL.

2. **Becker data layer is intact.** Unlike v1 lock which killed at data layer, the Becker dataset gives us the historical macro tickers Kim used (CPI, PAYROLLS, U3, FED prefix). The cost of running is now bounded mainly by my time.

3. **The kill-early principle requires a clean kill, not a speculative one.** If we don't actually run the replication, we cannot say "Kim does not work at retail." We must produce the evidence.

## What we expect to find

Pre-registered prediction: **NULL on Gate G1.** Specifically:

- Granger pair tests will find some significant pairs (likely 1 to 3 of 12 will be Bonferroni-significant at n ~16 to 60 events)
- LLM filter will pass ~50 to 80% of significant pairs (because economic plausibility is broad for macro relationships)
- The surviving signal will fire ~5 to 30 trades in OOS
- Gross win rate will be in the 45 to 60% range (consistent with Kim's idealized result)
- NET of Kalshi fees (1 to 4c per contract), the win rate breakeven of ~52% will be either marginally cleared or marginally missed
- The 95% bootstrap CI on win rate at n=5 to 30 will be too wide to exclude breakeven

The verdict will almost certainly be PARTIAL or NULL, not PASS.

## What COULD make V10-A PASS

For V10-A to PASS Gate G1 + G2 + G3 + G4:

- n_OOS_trades >= 100 (multi-strike expansion would help)
- Mean per-trade net P&L > $0 with bootstrap CI excluding zero
- LOCO holds across all 4 series

A pre-data-pull power estimate: at n=100 net trades and a true edge of +2pp, the CI half-width is approximately 9.8 percentage points. The CI [-7.8pp, +11.8pp] easily includes zero. To get a CI half-width of 2pp (gate-firable), we need n approximately 2400 trades. This is far beyond what 13 months of Becker data on 4 macro series can produce.

**The gate is mathematically unfirable at the available n, unless either:**
- (a) the true edge is so large that even an n=30 to 100 sample produces a sharp result (Kim implies edge approximately 3pp gross, so this is unlikely net), or
- (b) we expand to a finer trade granularity that produces correlated trades (multi-strike per event), which inflates the apparent sample but reduces statistical independence.

Option (b) is pre-registered in the v2 methodology lock with the explicit caveat that strike-level trades within an event are NOT independent. The honest interpretation requires the effective sample size to be the event count, which puts us back at n approximately 16 to 60.

## Possible pivots if V10-A NULLs

Per the lit scout's findings:

| Pivot | Source | Note |
|---|---|---|
| Mohanty pivot: Kalshi macro leads crypto vol on Deribit | arXiv 2604.01431 | OUT OF SCOPE for current project (different venue) |
| Transfer entropy alternative to Granger | Wang et al. (Paper I) | First-mover; better at small n nonlinear; defer to round 16 |
| Cross-venue Polymarket-Kalshi macro lead-lag | extends Ng/Peng 2026 | First-mover; defer to round 16 |
| Fee-net replication of Kim (this round) | this V10-A | RUNNING NOW |

If V10-A NULLs, the recommendation will be to close the round NULL and document the fee-net analysis as a first contribution. Pivots to round 16 require separate operator authorization.

## What this synthesis adds beyond the v2 methodology lock

The v2 lock is the procedure. This synthesis is the prior on the outcome. Reading the lock without this synthesis would suggest we expect a 50/50 PASS or NULL; reading this synthesis sets expectations to roughly 80/20 NULL/PASS.

The honest documentation matters: when the methodology critic reads the v2 lock, it should know we expect a NULL. Otherwise, the critic may write findings that anticipate a PASS verdict and fail to stress-test the NULL-prediction reasoning.

---

## Anti em-dash verification

No em-dashes (U+2014) or en-dashes (U+2013) used. All separations use commas, semicolons, or "to" / "vs".
