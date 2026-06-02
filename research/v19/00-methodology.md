# v19: Kalshi-Internal Overreaction / Mean-Reversion Maker Probe

**Date:** 2026-06-01. **Status:** methodology lock (pre-data). Needs a
methodology critic before any data is pulled.
**Angle:** a self-contained, no-external-data edge. Do Kalshi sports markets
OVERREACT to short price bursts, so that a maker can fade the overshoot and
capture the bounce?

## Hypothesis

After a sharp short-window price move (a "jump", e.g. an in-game swing or a news
spike), Kalshi sports prices systematically REVERT over the next window. A maker
resting a bid on the side the price overshot away from could capture the
reversion. Prior: moderate-low (the project has found Kalshi pricing mostly
efficient, and v6 found crypto microstructure NULL), but this is untested on
sports and free to test.

## The dominant phantom risk: bid-ask bounce

Trade prints mechanically alternate between the bid and the ask, which creates
SPURIOUS negative autocorrelation in consecutive trade prices that LOOKS like
reversion but is NOT capturable (you would be on the wrong side of the bounce).
The Round 11 "stale-price phantom" and the v6/v7 microstructure nulls are in this
family. The methodology MUST control for it, or any apparent reversion is an
artifact.

## Data

Becker trades for the in-season validated prefixes KXMLBGAME, KXATPMATCH,
KXWTAMATCH, post-October-2024. Fields: ticker, yes_price (cents), taker_side,
created_time. No orderbook (F11): this measures trade-print reversion, an
indicator, not a guaranteed executable fill.

## Construction (anti-bounce by design)

Per market, ordered by created_time:
1. Bucket trades into consecutive NON-overlapping T-minute windows (T = 15 min
   default; also report T = 30). Within each bucket compute the VWAP yes_price
   (volume-weighted), which averages out the bid-ask bounce inside the bucket.
2. For bucket b: jump_in = vwap[b] - vwap[b-1]; follow = vwap[b+1] - vwap[b].
   Because buckets are disjoint, jump_in and follow share NO trades (no
   shared-trade autocorrelation).
3. A bucket is a FIRE iff |jump_in| >= J (J = 5 cents default; J must exceed the
   typical 1-3c spread so a jump is a real move, not a single bounce).
4. Fader P&L per fire (the tradeable quantity): fade_pnl = -sign(jump_in) *
   follow. Positive when the price reverts against the jump (a fader profits).
   Reported in cents, then net of a round-trip maker fee (2 * maker fee at the
   entry price).

## Pre-registered gate (locked; no post-hoc tuning)

Chronological train (2024-11 to 2025-09) / OOS (2025-09 to 2025-11), event
(market) cluster bootstrap on the per-event mean fade_pnl.

A prefix CONFIRMS an exploitable overreaction edge iff ALL hold:
1. OOS mean net fade_pnl > 0 with a cluster-bootstrap 95% CI lower bound > 0.
2. TRAIN cluster CI lower bound > 0 (persistent, not OOS noise).
3. Magnitude: OOS mean net fade_pnl >= 1.0 cent (above the noise/spread floor;
   a sub-1c "edge" is not capturable by a retail maker after the spread).
4. Robust to the bucket size: the sign and significance hold at BOTH T=15 and
   T=30 (an artifact that depends on the exact window is not a real edge).
5. n_events OOS >= 30.

## Pre-registered KILL / NULL (no third bite)

If no prefix passes all five, the overreaction edge does not exist (or is
spread-bound / a bounce artifact) on Kalshi sports trade prints. Record the NULL
and stop; do not relax J, T, or the magnitude floor to manufacture a pass. A
sign-correct-but-sub-1c or CI-includes-zero result is a NULL, not a "continue".

## Why a pass would still need more before capital

Even a clean pass is on trade prints (F11): the reversion magnitude is measured
on VWAP, not on what a resting maker bid would fill at. A pass would graduate to
a forward shadow log (like v16) recording the executable book at each fire, NOT
to live capital directly.

## Methodology-critic revisions (ADOPTED as binding, pre-data)

The methodology critic returned REVISE; these three changes are now binding gate
criteria (locked before any data):

- **R1 disjoint-sample (Galton control), THE load-bearing fix.** A measured jump
  is partly true signal, partly VWAP estimation noise; a noisy estimate reverts
  mechanically even with zero true overreaction, and the base gate would confirm
  that artifact. Fix: split each firing bucket's trades into two DISJOINT halves
  by trade index (odd vs even prints). Fire the signal on half-A
  (jump_in_A = vwapA[b] - vwap[b-1]); take the ENTRY from half-B
  (entry = vwapB[b]); measure follow = vwap[b+1] - entry. fade_pnl =
  -sign(jump_in_A) * follow. If the reversion is pure estimation-noise, the
  cross-sample fade collapses to ~0; if it survives, it is a real property of the
  price level. The cross-sample fade (not the naive same-sample one) is the
  binding quantity.
- **R2 time-to-close.** Drop the final K buckets before settlement (K = 2
  buckets / ~last 30 min). Stratify fade_pnl by time-to-close; the gate requires
  the edge to hold in the MIDDLE of market life, not just pooled or near close
  (near-close reversion is settlement convergence, not overreaction).
- **R3 J-robustness.** Sweep J over {3, 5, 7, 10} cents. A real edge is MONOTONE
  increasing in J; a bounce/spread artifact peaks near the spread width (~5c) and
  decays. The gate requires the fade to be non-decreasing from J=5 to J=7.
- **Clustering:** bootstrap by GAME-DAY (calendar date), not by market
  (same-day games share correlated flow; coarser clustering is conservative).
- **Cross-check (reported, not gating):** re-sign the move by taker-side order
  flow; if price-defined and flow-defined fades disagree, the price-defined one
  is likely bounce.

## Falsification value

A NULL is informative and likely: it would confirm Kalshi sports trade-price
reversion is a bounce artifact, not an edge, consistent with the project's
broader finding that the only durable edge is the favorite-longshot maker.

---

*Em-dash and en-dash audit: verified clean after write.*
