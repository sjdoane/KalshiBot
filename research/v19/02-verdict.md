# v19 Overreaction Probe: VERDICT NULL (and a credible one)

**Date:** 2026-06-01. Script `scripts/v19/overreaction_probe.py`, data
`01-overreaction-results.json`. Methodology + binding gate (with the
methodology-critic revisions R1/R2/R3) in `00-methodology.md`.

## Result

No prefix shows a capturable reversion edge. The cross-sample fader P&L (the
binding quantity) is consistently NEGATIVE in the mid-life window, OOS, across
all jump thresholds and both bucket sizes:

| Prefix | T | J>=5c mid OOS, CROSS fade (CI) | naive fade |
|---|---|---|---|
| KXMLBGAME | 15 | about -4.3c [-4.8, -3.9] | -4.2c |
| KXMLBGAME | 30 | -4.4c [-5.1, -3.8] | -4.4c |
| KXATPMATCH | 15 | -2.7c [-3.4, -2.0] | -2.7c |
| KXATPMATCH | 30 | -0.8c [-2.0, +0.4] | -0.9c |
| KXWTAMATCH | 15 | -2.1c [-2.8, -1.5] | -2.0c |
| KXWTAMATCH | 30 | -0.7c [-2.0, +0.5] | -0.3c |

A negative fade means: after a sharp jump, the price does NOT revert; it
slightly CONTINUES (momentum). Fading the move loses ~2 to 5c net. The fade gets
more negative as J rises (bigger jumps continue more), the opposite of an
overreaction signal.

## Why this NULL is credible (the disjoint-sample control worked)

The methodology critic's load-bearing worry was that a noisy VWAP jump reverts
mechanically (Galton bias / bid-ask bounce), which would manufacture a fake
reversion edge. The disjoint-sample control (R1) fires the signal on half-A but
takes the entry/follow from the disjoint half-B, so a pure estimation-noise
reversion would collapse the CROSS column toward zero while the NAIVE column
stayed positive.

What actually happened: the CROSS and NAIVE columns are nearly IDENTICAL (e.g.
MLB T=30: cross -4.43c, naive -4.38c). They agree, and both are negative. So the
result is NOT an artifact in either direction: Kalshi sports markets genuinely do
not overreact on these horizons. They mildly continue, consistent with efficient
incorporation of in-game/news information into the price. A maker cannot fade
this, and riding the continuation would require chasing an informed move as a
taker (paying the spread into adverse flow), which is not a retail edge either.

## Verdict and kill

KILL the overreaction/reversion angle. NULL on all three in-season validated
prefixes, both window sizes, all jump thresholds, with the Galton/bounce control
in place. Per the locked methodology (no third bite), the angle ends; do not
relax J, T, or the magnitude floor to hunt for a pass.

This is the kill-early discipline operating as designed, and the rigor adds real
information: it is not "we could not find an edge", it is "we showed, with a
phantom control, that the edge is not there and the markets are efficient on this
axis". The only durable edge in this project remains the favorite-longshot maker
(v1, now with the symmetric NO-underdog arm).

## Reusable artifact

`scripts/v19/overreaction_probe.py` (disjoint-sample reversion tester with
game-day cluster bootstrap) is reusable for any future Kalshi trade-price
autocorrelation study.

---

*Em-dash and en-dash audit: verified clean after write.*
