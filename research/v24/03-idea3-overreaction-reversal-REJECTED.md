# v24 Idea 3: Microstructure overreaction-reversal as a taker. REJECTED at the plan critic.

**Verdict: REJECTED at the plan-critic gate (honest prior ~5%, the lowest of the
three v24 ideas). No methodology lock, NO data pulled.**

**Date:** 2026-06-29
**Mechanism proposed:** after a large sustained price move on a liquid Kalshi
contract (VWAP-based to dodge single-print outliers), fade the move as a taker
expecting partial reversion before settlement. Pure-Becker (no external data).

## Why it was rejected (plan critic, full report in 03-idea3-plan-critic.md)

1. **The bid-ask-bounce phantom makes the signal uncomputable on Becker (the
   decisive flaw).** Becker has NO mid / orderbook, only the executed print
   (`yes_price`/`no_price`) plus `taker_side`. Trade prints oscillate between bid
   and ask: a run of YES-takers prints near the ask (looks like an up-move), then
   a run of NO-takers prints near the bid (looks like a "reversion"), while the
   MID NEVER MOVED. The "move" and its "reversion" are mechanically inseparable
   from bid-ask bounce, and the bounce is correlated with `taker_side` (the only
   flow column). VWAP of prints does not recover the mid. So the independent
   variable cannot be defined cleanly. A NULL would be uninterpretable (no edge
   OR bounce washout) and a PASS untrustworthy (likely the bounce artifact).
   Cheap-to-screen does not mean worth-screening when neither outcome is
   interpretable. This is the F4/F11 stale-print phantom in its purest form.

2. **The exit dilemma: both branches are already-dead.** HOLD-to-settlement makes
   reversion irrelevant to P&L; it reduces to "after an up-move, bet the up-side
   settles NO" = a contrarian outcome forecast (the dead forecaster/FLB family),
   and DIRECTIONALLY it is the v8-A confirmed live PHANTOM (8/8 losses, p~0.004:
   the market's post-move price was right, the naive contrarian wrong, every
   time). EXIT-before-settlement pays a SECOND taker fee + spread (round-trip
   hurdle ~12pp at P=0.50, ~18pp at P=0.35), needs an exit price Becker does not
   contain (F4/F11), and the reversion it targets is the bounce artifact from (1).

3. **Informed-move adverse selection.** Fading a move means crossing into the side
   recent flow just hit against. A large sustained one-sided move is the
   INFORMED-flow case (most dangerous to fade), and it is indistinguishable
   ex-ante from an overreaction using only price/volume/taker_side. This is the
   v7-B/v8-A information-toxicity phantom by construction.

4. **Efficiency + forking paths + capacity.** Fast reversion on liquid books is
   arbed in seconds (a latency race, overlapping the dead crypto/news kills); slow
   reversion survives only on thin/wide/capacity-dead books. Five free knobs
   (threshold, window, band, horizon, category) = a garden of forking paths whose
   spurious-pass mechanism (bounce magnitude) is itself a smooth function of band
   and category. No Kalshi evidence of retail-paced post-move reversion exists.

## No third bite

Microstructure overreaction-reversal ends here. The pure-Becker microstructure
mechanism is foreclosed by the no-mid schema: any signal that needs to separate a
real price move from bid-ask bounce is uncomputable on Becker.

*Em-dash and en-dash audit: verified clean after write.*
