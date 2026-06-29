# v24 Idea 3 plan critic (adversarial). Verdict: KILL, prior ~5%.

Adversarial plan critic on "microstructure overreaction-reversal as a taker"
(pure-Becker) before any lock or data pull. Load-bearing findings preserved.

## Executive summary

The dead forecaster/FLB family in a microstructure costume, with a fatal
data-layer defect on top. It collapses into two branches, both already-killed,
and its core signal is uncomputable cleanly on a dataset with no mid.

## Attacks

1. **Efficiency / cell-existence vise.** A slow, retail-paced reversion must
   survive BOTH arbitrage AND the taker hurdle. Liquid mid-priced books (low
   hurdle) are exactly where HFT/MMs arb fast reversals in seconds (a latency race
   = the dead crypto/news kills). Thin/slow books (reversion might persist) are
   wide-spread + capacity-dead. No published Kalshi evidence of retail-paced
   post-move reversion; the only analog (Rasooly-Rozzi manipulation reversal) is
   sparse events, still hypothesis.

2. **The bid-ask-bounce phantom (the kill).** Becker columns are the executed
   print + `taker_side`, NO mid/orderbook. Prints oscillate bid<->ask: a run of
   yes-takers prints near the ask ("up-move"), a run of no-takers prints near the
   bid ("reversion"), mid unchanged. The move and its reversion are mechanically
   inseparable from bounce, and bounce is correlated with `taker_side` (the only
   flow column). VWAP of prints does not recover the mid. The independent variable
   cannot be defined cleanly. A "sustained move" filter selects the informed-flow
   case (attack 4), so the de-bounce filter selects the lose-case. Pincer.

3. **Exit dilemma, both branches dead.** Hold-to-settlement: reversion irrelevant;
   reduces to a contrarian outcome forecast (dead family) and is DIRECTIONALLY the
   v8-A confirmed phantom (8/8 losses p~0.004). Exit-early: second taker fee +
   spread (round-trip ~12pp at P=0.50, ~18pp at P=0.35), no exit price in Becker
   (F4/F11), and the reversion target is the bounce artifact.

4. **Informed-move adverse selection.** Fading = crossing into the side flow just
   hit; large+sustained+one-sided = informed flow (most dangerous), inseparable
   ex-ante from overreaction via price/volume/taker_side. The v7-B/v8-A
   information-toxicity phantom by construction.

5. **Forking paths.** Five free knobs (threshold, window, band, horizon,
   category); the spurious-pass mechanism (bounce magnitude) is a smooth function
   of band/category, so a sweep finds an artifact cell a bootstrap will not flag.

6. **Capacity.** Surviving cells are thin-tail-trivial (~$0.02-0.04/bet), the
   v23-crypto / Idea-1-2 thin-tail death.

## Verdict: KILL (prior ~5%).

Not worth screening despite being cheap/pure-Becker: because the signal cannot be
separated from bid-ask bounce on a no-mid dataset, a NULL is uninformative and a
PASS is untrustworthy (bounce false positive that would burn a live probe
re-confirming the v8-A phantom). A screen that cannot distinguish edge from
artifact in either outcome is not worth running.

## Constraints if overridden (carried forward)

1. Define the move WITHOUT the mid and PROVE it is not bounce (show it predicts a
   settlement-outcome shift, which bounce cannot fake) before any data pull.
2. Pick ONE version (hold = single-leg fee + acknowledge it is a directional
   forecast; exit = round-trip fee + no synthesized exit price).
3. Pre-register the price-specific breakeven inequality; refuse if reversion does
   not clear ~1.5x the (single/round-trip) hurdle on paper.
4. Demonstrate informed-vs-overreaction separation ex-ante, no outcome peeking.
5. ONE frozen spec, ONE binding statistic (aggregate OOS net P&L, event-cluster
   bootstrap seed 42, purged, post-Oct-2024, no per-cell rescue).
6. Post-flip only, clear ~1.5x hurdle (2026 decay).
7. Capacity gate pre-registered.
8. No live probe on a bounce-contaminated PASS; forward shadow crosses the REAL
   live ask (round-trip if exit version).
9. No third bite.
