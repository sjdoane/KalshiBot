# v1 MLB Favorite-Maker Sweet-Spot Analysis: Methodology Lock

**Date:** 2026-06-01. **Status:** LOCKED before pulling the stratified data.
**Goal:** within KXMLBGAME (the only validated v1 prefix in season now), find
whether the favorite-maker edge concentrates in a sub-condition that is
out-of-sample robust enough to justify v1 tightening its MLB trading for higher
realized EV this season. If not, keep v1 trading the full band.

This reuses the exact v1 regime + Becker + train/OOS + event-cluster-bootstrap
machinery from `scripts/v10a/validate_v1_strategy.py`; only the stratification
and the gate are new, and both are fixed here BEFORE seeing any stratified
result (no post-hoc threshold tuning, no third bite).

## v1 regime (unchanged)

Buy YES as MAKER at yes_px in [0.70, 0.95], hold to settlement. Becker proxy:
trades with `taker_side='no'` (maker on the YES side) and `yes_price` in
[70, 95]. Net P&L per fill = (result==yes ? 1 - yes_px : -yes_px) - maker_fee,
maker_fee = 0.25 * ceil(0.07 * p * (1-p) * 100)/100. Inference is at the
EVENT level (cluster bootstrap by event_ticker), 2.5/97.5 percentile CI.

## Pre-registered strata (fixed; not data-snooped)

- **Price band (favorite degree), 3 bins over [0.70, 0.95]:**
  B1 = [0.70, 0.78), B2 = [0.78, 0.86), B3 = [0.86, 0.95].
- **Time-to-close at fill** (hours between trade.created_time and
  market.close_time, i.e. how long before the game the bid filled):
  T_near < 3h, T_mid in [3h, 12h), T_far >= 12h.
- The 3x3 = 9 joint cells, the 3 band marginals, the 3 time marginals, and the
  KXMLBGAME-overall baseline.

## Split (unchanged from the prior v1 validation)

Train 2024-11-01 to 2025-09-01; OOS 2025-09-01 to 2025-11-25. No new split tuning.

## SWEET-SPOT gate (a cell must pass ALL five)

1. Cell OOS event-mean net P&L > KXMLBGAME-overall OOS event-mean (strictly
   better than just trading the whole band).
2. Cell OOS cluster-bootstrap 95% CI lower bound > 0.
3. Cell TRAIN cluster CI lower bound > 0 (the edge is persistent, not OOS noise).
4. Consistent ranking: the cell is in the TOP-2 by event-mean in BOTH the train
   and the OOS window (the winner must not flip between windows = not overfit).
5. OOS n_events >= 30 (adequate power).

## Pre-registered KILL / NULL (no third bite)

If NO cell passes all five, the KXMLBGAME edge is effectively UNIFORM across
price and time within [0.70, 0.95]: v1 keeps trading the full band, and we do
NOT tighten it on a marginal, train-only, or rank-flipping result. The dual
train-AND-OOS requirement plus the top-2-in-both-windows rule is the
multiple-comparisons guard across the 9 cells + 6 marginals.

## Deployment translation (only if a sweet spot passes)

Propose the exact v1 config change (e.g. raise the MLB favorite floor to a band
boundary, or add an MLB-specific min/max-minutes-to-close), to be deployed ONLY
on operator approval. No live change is made by this analysis.

## Standing caveats (do not relitigate the verdict around these)

- F11: Becker trades are fills that HAPPENED, not what a NEW resting bid would
  have filled at. This edge is an UPPER bound on a new entrant's edge.
- Adverse selection: the live -4.9pp post-fill drift is not captured here; a
  Becker sweet spot must still survive live fill-confirmation before any
  capital scale-up.
- Year-over-year decay (Burgi): 2024-2025 magnitude may compress in 2026.

---

*Em-dash and en-dash audit: verified clean after write.*
