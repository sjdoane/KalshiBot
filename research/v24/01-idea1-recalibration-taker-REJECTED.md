# v24 Idea 1: Market-price recalibration as a TAKER. REJECTED at the plan critic.

**Verdict: REJECTED at the plan-critic gate (honest prior ~7%, below the ~10%
"prefer a better idea" floor). No methodology lock written, NO data pulled.**

**Date:** 2026-06-29
**Mechanism proposed:** take the market's executed price p as the base
probability; learn a monotone calibration map g(p) = P(outcome=yes | price=p,
regime) on settled Becker trains; TAKE (cross the spread) when g(p)-p clears the
worst-case taker fee + spread + margin; hold to settlement. Claimed escapes:
adverse selection (taker chooses when to cross) and F11 (fills at real executed
taker prices).

## Why it was rejected (plan critic, full report in 01-idea1-plan-critic.md)

1. **It is the favorite-longshot bias (FLB) relabeled.** A monotone map of
   price-alone against outcome can only rediscover the FLB curve; the residual
   g(p)-p IS the FLB, stratified. No new information is introduced.

2. **The nearest precedent already failed, at LOWER fees.** phase-1.6
   (`research/phase-1.6-results.md`) is structurally identical: an isotonic
   calibration map traded on its residual with `realized_pnl_per_contract`. It
   NULLed: C5 shoulder net edge -0.51pp, C2 gross 1.49pp (< 2pp required), C1 ECE
   1.44x (< 5x). That was at MAKER fees. The taker version pays ~4x the fee plus
   the bid-ask spread, so the average trade is strictly more negative.

3. **The economics fail on the arithmetic.** Liquid-favorite (P ~ 0.70-0.85)
   taker hurdle = taker fee ceil(0.07*P*(1-P)) cents (1-2pp) + half-spread (~1pp)
   + margin (0.5pp) ~ 2.5 to 3.5pp net. Available gross FLB residual under Burgi
   psi 2025 = 0.021 (half of 2024) is sub-1pp to ~1pp at liquid prices; v1's deep
   diagnosis independently found favorites in [0.70, 0.95] FAIRLY priced at the
   fill. The inequality is not close. The only place the gross gap exceeds the
   hurdle is the thin high-bias tails (Media 0.6M trades, World Events 0.2M),
   which are capacity-dead at a ~$1-notional bankroll.

4. **The F11 escape is real for accounting but hollow for capture.** A real
   Becker taker-side print proves liquidity existed ONCE for someone crossing that
   side at that instant. It does not prove a NEW taker, firing on g(p)-p>cost,
   captures the same price before the MM reprices. The proposal therefore inherits
   the CONFIRMED v7-B/v8-A cross-the-ask phantom (8/8 live losses, p~0.004; the
   +0.208 Brier vs stale print was unmonetizable against the live ask MMs maintain
   continuously), not only the v23 fill-volume phantom. A taker is immune to
   fill-VOLUME toxicity but fully exposed to INFORMATION toxicity (it crosses into
   a price the informed side just set).

5. **Capacity + staleness + forking paths** all compound: the surviving cell
   would be a thin tail (capacity-bound), Becker is ~7 months stale with psi
   halving yearly, and the strata are survivors of prior sweeps so no Bonferroni
   correction prices in the selection.

## The one load-bearing thing this rejection SURFACED (motivates idea 2)

phase-1.6's headline gate failed on the SHOULDER AVERAGE (-0.51pp), but its
informational lines show the HIGH-CONVICTION subset monetized: on trades with
> 2pp model-vs-market edge, median realized P&L per contract was +$0.079 AFTER
maker fees with an 82% hit rate, and 4 of 5 leave-one-city-out folds positive.
That is ~+7.9pp realized on the high-divergence subset, well above the ~3pp taker
hurdle. The killed idea averaged over all trades (doomed); the high-divergence
TAIL on weather is a genuinely different, larger-edge cell. This is the scouts'
Tier-1 #1 (weather as a taker on model-vs-market divergence), and it is the basis
for v24 Idea 2. It differs from idea 1 on REGIME (high-divergence tail, not the
average), FEATURES (an external NWP model forecast, not a market recalibration),
and is grounded in a DOCUMENTED real directional signal rather than the FLB.

## No third bite

Idea 1 (generic, category-agnostic price recalibration traded as a taker on the
average trade) ends here. Idea 2 is a meaningfully different mechanism (external
weather model, high-divergence tail, slow-to-price multi-day horizon), not a
re-tuning of idea 1.

*Em-dash and en-dash audit: verified clean after write.*
