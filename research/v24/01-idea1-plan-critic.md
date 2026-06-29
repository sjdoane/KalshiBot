# v24 Idea 1 plan critic (adversarial). Verdict: KILL, prior ~7%.

Adversarial plan critic run before any methodology lock or data pull on the
"market-price recalibration as a taker" idea. Full reasoning preserved.

## Executive summary

The idea is the favorite-longshot bias (FLB) wearing a taker costume. It adds no
new information: g(p) is by construction a monotone re-mapping of the price, so
the only thing it can discover is the FLB and its category/horizon strata, already
killed as a maker (v23, v18) and as a directional forecaster (phase-1.6). The
taker framing makes the economics strictly worse (pays ~4x the fee plus the
spread to harvest the same small, shrinking bias). The single most damning number
in the repo is phase-1.6: an 82% directional hit rate that still nets -0.51pp
after fees, which is this exact mechanism. The F11 escape reverses sign under
scrutiny: a real taker print proves liquidity existed for someone hitting that
side, but the rule wants to trade against that flow, i.e. lift the ask precisely
when the realized taker was buying for a reason (information toxicity).

## Attacks

1. **Re-tread (yes).** A monotone calibration of price against outcome IS the FLB
   curve; the residual is the FLB. The strata are Le's calibration-regime
   structure, already catalogued. Closest prior null is phase-1.6 (not v23): it
   learned an isotonic map (the repo ships `analysis/calibration.py`), traded the
   residual on the buy-cheaper rule (`realized_pnl_per_contract`), and failed
   (C5 net -0.51pp, C2 gross 1.49pp, 82% hit rate that did not monetize). The
   proposal differs only by using TAKER fees (worse) and all categories (no
   escape). ROLE/TARGET/MECHANISM differentiation is cosmetic: g(p) IS an outcome
   forecast whose only input is price; "taker not maker" is a cost increase, not
   an edge source.

2. **Economic viability (central kill).** Required: g(P)-P > taker_fee(P) +
   half_spread + margin. At liquid favorites P~0.70-0.85: taker fee
   ceil(0.07*P*(1-P)) cents = 1-2pp; half-spread ~1pp; margin ~0.5pp; hurdle
   ~2.5-3.5pp net. Available gross under psi 2025 = 0.021 is sub-1pp to ~1pp at
   liquid prices (v1 found favorites fairly priced; phase-1.6 gross 1.49pp on
   weather). The inequality fails on its face in the liquid band. It clears only
   in thin high-bias tails (Entertainment 4.79pp, Media 7.28pp, World Events
   7.32pp gross gap) which are capacity-dead. The claim "adverse-selection cost
   the maker ate exceeds the taker's extra fee+spread" is unsupported: the maker
   avoids fill toxicity for FREE by not resting a bid, while ALSO not paying the
   2-4pp taker premium. Paying the premium buys nothing the no-trade option does
   not already give.

3. **F11 hollow for capture.** (a) Conditioning on taker_side=='yes' over-samples
   YES-buying pressure / informed flow, biasing the fill price low. (b) Cleared
   price < true marketable ask; using the bare cleared price is an F4 stale-print
   phantom (killed twice: W2, v5 Track B). Only cleared-price-plus-haircut may be
   tested. (c) Market impact negligible at $1-2/contract (the one bull win). (d)
   Sign-reversing: a real taker trade proves liquidity existed ONCE for someone
   crossing; the bot's rule does not get to choose that moment. If the flow is
   informed, the edge is gone by the time a new taker arrives (the v7-B/v8-A
   confirmed phantom: 8/8 live losses). A taker is immune to fill-VOLUME toxicity
   but exposed to INFORMATION toxicity.

4. **Recalibration statistics.** Isotonic overfits at sparse extremes, exactly the
   deep-favorite / thin-tail prices the bull case needs; the step function there
   is binning noise. Venn-Abers is more conservative and should be mandated.
   Effective DoF scales with distinct price levels x strata = not low-parameter.
   Monotone bakes in the FLB answer; you can read psi off Burgi and compute that
   0.021-intensity FLB does not clear the taker fee without fitting anything.

5. **Multiple testing / forking paths.** Strata are sweep survivors; no Bonferroni
   prices that in. Correct discipline: ONE frozen uniform map, applied uniformly,
   AGGREGATE OOS net P&L as the single binding statistic (cluster bootstrap, seed
   42, cluster=event_ticker), no per-band rescue. This removes the only place the
   idea could find an edge (the thin tails).

6. **Circularity + confound.** In-sample residual is mechanically ~0 (isotonic is
   the projection that minimizes it); OOS residual equals OOS FLB persistence
   (decaying). Confound: price level correlates with category mix / time-to-close
   / liquidity, so a pooled g(p) reads a COMPOSITION effect as a calibration
   residual (the v10a single-inferred-spot trap). Stratifying to fix it
   re-introduces sparse-extreme overfit + forking paths. Pincer.

7. **Capacity.** ~$1 notional; sub-1pp net = sub-$0.01/bet. The tails where the
   gap clears the fee are the thinnest (World Events 0.2M). Capacity-to-triviality
   death, like the v23 crypto sub-2pp cell.

8. **Staleness + decay.** Becker ends 2025-11-25 (~7 months stale); psi halving
   yearly implies ~0.010-0.015 intensity in 2026, deepening the shortfall. The
   in-Becker A-5/B-5 decay guard is too weak (both windows are inside stale data);
   only a forward shadow is 2026-valid.

9. **Prior.** ~25% is too high. Calibrated ~7%: nearest precedent (phase-1.6)
   failed net at lower fees with 82% hit rate; the arithmetic is not close in the
   liquid band; project base rate is 11 NULLs + 1 phantom, 0 confirmed edges;
   honest 40% priors (v23-A) came in NULL. Residual ~7% kept by the genuine
   fill-toxicity escape and a thin chance one liquid mid-bias category (Crypto
   2.69pp gross gap) clears under a pre-committed uniform map.

## Verdict: KILL (prior ~7%).

## If overridden, the lock MUST incorporate (carried forward as constraints for any taker idea)

1. ONE frozen uniform map, ONE binding statistic (aggregate OOS net P&L,
   cluster bootstrap, no per-band rescue, non-inferential screen).
2. Net against WORST-CASE taker fee ceil(0.07*P*(1-P)) cents AND a >= 1c spread
   haircut (lift-the-ask) AND a >= 0.5pp margin; bare-cleared-price disqualified.
3. Pre-register the breakeven inequality; refuse to run if 0.021-intensity FLB
   does not clear ~2.5-3.5pp on paper (the Kim "unfirable gate" discipline).
4. Mandate Venn-Abers or isotonic-with-min-bin-mass; exclude sparse-extreme bins;
   report effective DoF.
5. Freeze strata pre-data; report price->category-mix correlation (confound).
6. Aggressive decay guard (clear ~1.5x the fee+spread, not barely); only the
   forward shadow is 2026-valid.
7. Forward shadow for a TAKER must measure REAL crossed (or live-ask
   shadow-crossed) net P&L, not modeled resting fills (the cross-the-ask phantom
   is the relevant capture risk): >= 30 settled fills, net/fill > 0 with a
   market-day-clustered CI excluding zero and point >= +1.0pp, day-30 hard stop
   if < 10.
8. Capacity gate: pre-register minimum expected net $/week at $1 notional; NULL a
   thin-tail survivor regardless of CI.
9. No third bite: a kill at the breakeven check, the screen, or the shadow ends it.
