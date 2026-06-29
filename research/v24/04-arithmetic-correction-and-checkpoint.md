# v24 Checkpoint: arithmetic correction + consolidated state (operator direction call)

**Date:** 2026-06-29
**Status:** 3 ideas screened at the plan-critic gate; 0 data screens run; $0
capital. One honesty correction that changes a verdict. Handing back for a
direction call.

---

## 1. The honesty correction (load-bearing)

In killing v24 Idea 2 (weather external-forecast taker), I accepted a plan-critic
arithmetic argument that was WRONG, and I amplified it ("the dispositive catch").
Correcting it.

**The flawed claim:** "KXHIGH trades cheap (median ~0.20); the taker fee
ceil(0.07*P*(1-P)) is a FIXED-cents charge, so at P=0.20 it is 2c = 10pp of the
20c notional, +1c spread = 5pp, hurdle ~15pp, vs a best edge of gross 1.49pp, so
it fails by an order of magnitude."

**Why it is wrong.** Two basis errors:

1. **Fee-as-%-of-capital vs the pp-of-$1 probability-edge hurdle.** A Kalshi edge
   is a probability residual measured in pp of the $1 contract. Expected P&L per
   contract for a YES taker at price p with true prob g is
   `E = (g - p) - fee`, so the edge `(g - p)` must exceed `fee` where the fee is
   in dollars-per-contract = pp of $1. The taker fee `ceil(0.07*P*(1-P))` cents,
   verified against `kalshi_taker_fee_per_contract`, is:

   | price | taker fee (pp of $1) | fee as % of capital |
   |---|---|---|
   | 0.05 | 1.0pp | 20.0% |
   | 0.20 | 2.0pp | 10.0% |
   | 0.50 | 2.0pp | 4.0% |
   | 0.80 | 2.0pp | 2.5% |
   | 0.90 | 1.0pp | 1.1% |

   The pp-of-$1 fee is **1-2pp at every price, and SMALLEST (1pp) at the cheap
   extremes**. The "10-20pp" figures are the fee as a fraction of capital
   deployed, which is a RETURN-ON-CAPITAL / capacity quantity, NOT the hurdle a
   probability edge must clear. Cheap contracts are if anything CAPITAL-EFFICIENT
   (small fee in pp, little capital tied up, so more contracts per dollar).

2. **Broad-average edge vs high-conviction subset.** The 1.49pp it compared
   against is the phase-1.6 BROAD-SHOULDER average. The idea was always the
   HIGH-CONVICTION tail, where phase-1.6 measured +$0.079/contract = ~7.9pp net of
   maker fees. Comparing the %-of-capital hurdle against the broad-average edge was
   doubly inconsistent.

**Corrected arithmetic.** Taker hurdle = fee (1-2pp) + spread (~1pp on a tight
book, more on thin weather books) + margin (~0.5pp) = **~2.5-3.5pp on a tight
book, up to ~5-7pp if the weather spread is 3-5c**. The high-conviction subset
edge (~7.9pp net of maker fees, so ~8.5-8.9pp gross) PLAUSIBLY clears even a wide
spread. **Weather is NOT killed by the fee arithmetic.**

## 2. What the correction changes, and what it does NOT

**Changes (Idea 2 / weather):** prior revised UP from ~6-8% to **~12-15%**;
verdict from "rejected build" to **"PAUSED pending an operator direction call."**
The fee hurdle does not kill it. The binding open questions are now clearly:
- **Capture phantom (primary):** does the live KXHIGH ask at T-1/2d already embed
  the public NBM forecast (weather is a pure public-data game)? If yes, crossing
  the ask captures nothing (the v8-A phantom). This is **$0-testable** with a
  read-scope live-ask-vs-public-forecast probe over ~2 weeks.
- **Is the +7.9pp real and external?** It was measured from a market
  RECALIBRATION (circular: selected on |g(p)-p|>2pp from the same map), not an
  external forecast. The genuine external-NBM-forecast edge is unmeasured and
  could be smaller (or, being independent of the price, could be cleaner).
- **Spread on thin books** (part of what the $0 probe measures).
- **Infra:** `data/weather.py` is single-member (no probability) and has an
  unhandled as-of leakage trap; both must be fixed before any clean screen.

**Does NOT change (Ideas 1 and 3 remain validly killed):**
- **Idea 1 (recalibration):** its arithmetic was already on the CONSISTENT
  pp-of-$1 basis (FLB residual ~1pp under Burgi psi-2025=0.021 vs a ~3pp hurdle).
  A ~1pp edge genuinely does not clear a ~3pp hurdle. Kill stands (also: phase-1.6
  broad-shoulder net -0.51pp; capture phantom; FLB relabeled).
- **Idea 3 (microstructure reversion):** killed because the signal is uncomputable
  on a no-mid dataset (move and "reversion" inseparable from bid-ask bounce
  correlated with taker_side). Independent of any fee arithmetic. Kill stands.

## 3. The corrected impossibility envelope (what the loop has actually established)

The real wall for retail Kalshi taker edges, after 3 ideas, is NOT a brute fee
hurdle (that is modest, ~2-3pp, and kills only SMALL edges like the FLB residual).
It is, in priority order:

1. **The capture phantom (primary, confirmed live as v7-B/v8-A, 8/8 losses
   p~0.004).** For any edge built on PUBLIC information, the MM already prices it
   into the live ask, so crossing the ask captures nothing. This is the binding
   constraint for every "forecast/recalibrate public info" idea, and it is
   resolvable ONLY by a forward shadow at the live ask (not by any Becker screen,
   which shows an edge EXISTED in fills, not that a new order captures it).
2. **F11 / no mid in Becker.** Signals that need the mid (microstructure) are
   uncomputable; Becker is a necessary-not-sufficient screen for everything else.
3. **Modest fee+spread hurdle (~2-3pp tight, more on thin books).** Kills small
   edges (FLB ~1pp); large genuine edges (>~4-5pp) can clear it.
4. **Efficiency on liquid mid-priced markets** (v14 sports taker came in
   borderline-NULL: +$0.15/contract mean but CI straddled zero).
5. **Capacity at ~$200** (caps absolute scale; fine for $1-2 tiny-pilot bets).

The honest implication: a viable retail taker edge needs a **large (>~4-5pp),
capturable** edge, i.e. one on information or a mispricing the MM does NOT already
have in the live ask. The two candidates with any such claim are weather
high-conviction (where the open question is purely capturability, $0-testable) and
thin sports props (where the MM may be too lazy to model an obscure prop).

## 4. Remaining candidate menu, assessed against the corrected envelope

| # | Mechanism | Prior | Blocking issue(s) |
|---|---|---|---|
| 2 | Weather high-conviction external-forecast taker | ~12-15% | Capture phantom (weeks-long $0 probe) + multi-day NBM build + circular +7.9pp |
| A | Sports external projections on thin pre-game props | ~10-12% | Capture phantom (Kalshi tracks sportsbooks; v14 borderline-NULL) + thin-book spread + projection build + leakage |
| B | Smart-money taker-flow follow/fade | ~8% | Takers lose -1.12% avg (follow=neg); fade=maker (dead) or fee-taxed; v14-adjacent |
| C | Manipulation-reversal (Rasooly-Rozzi 60+ day) | ~10% | Sparse events (capacity-dead) + "manipulation" hard to define cleanly |
| D | High-bias-thin-category taker (Media/Entertainment 5-7pp gross) | ~8% | Thin = wide spread + capacity-dead; capture phantom |
| E | Conformal selective prediction | n/a | A multiplier on a base edge; no base edge exists (dead standalone) |
| F | New-listing cold-start taker | ~7% | v22 nulled cold-start (maker); thin early book + capture phantom |

No remaining candidate clearly escapes the envelope. The two least-dead (weather
~12-15%, sports-props ~10-12%) both have the **capture phantom** as their binding
risk, which only a forward shadow resolves, and both require multi-day engineering
before even a Becker screen.

## 5. Recommendation and the direction call

I have rigorously killed 2 ideas (recalibration, microstructure) on sound grounds,
corrected my own error on a third (weather is ~12-15%, not killed), and mapped the
remaining menu against a corrected, well-evidenced impossibility envelope. The
high-prior, cleanly-Becker-screenable space is exhausted; the two least-dead
candidates need multi-day engineering AND a weeks-long forward probe to resolve
their binding risk (the capture phantom), which cannot be completed in one session.

This is the loop's prescribed "hand back for a direction call" point. The genuine
options for the operator:

- **(A) Pursue weather** (operator's stated #1): build the $0 read-scope
  live-ask-vs-public-NBM-forecast probe FIRST (resolves the capture phantom for
  free before any heavy build); only if the ask demonstrably lags the forecast, do
  the NBM-ensemble + as-of-leakage build and a clean external-forecast Becker
  screen. Honest ceiling: small, capacity-bound, ~12-15% it clears.
- **(B) Pursue sports-props:** more capacity, cheaper data libs, but the same
  capture phantom (Kalshi tracks sportsbooks; v14 borderline-NULL) and a
  projection + leakage build. ~10-12%.
- **(C) Stand down:** accept that the loop has established a coherent impossibility
  envelope (retail taker edges on Kalshi need a large, capturable, non-public edge
  that does not appear to exist in the screenable space), keep capital flat, and
  treat the clean null as the deliverable.

My honest lean: **(A) the $0 weather ask-lag probe**, because it is the cheapest
way to resolve the single binding question (capturability) for the
highest-remaining-prior idea before committing any engineering, and a negative
result there would also strongly generalize (if even thin retail weather books
price the public forecast, the capture phantom is near-universal on Kalshi).

*Em-dash and en-dash audit: verified clean after write.*
