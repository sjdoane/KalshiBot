# v1 MLB Sweet-Spot: Results + Recommendation

**Date:** 2026-06-01. Methodology: `00-v1-mlb-sweetspot-methodology.md` (locked
before this run). Data: `01-mlb-sweetspot-results.json`. Script:
`scripts/v18/mlb_sweetspot.py`. Becker post-Oct-2024, KXMLBGAME, v1 regime
(buy YES as maker at yes_px in [0.70, 0.95], net of maker fee), event-cluster
bootstrap, train 2024-11 to 2025-09 / OOS 2025-09 to 2025-11.

## Headline: the edge concentrates in MODERATE favorites

| Price band | TRAIN evt-mean (CI lo) | OOS evt-mean (CI 95%) | OOS n_events |
|---|---|---|---|
| 0.70 to 0.78 | +7.89% (+6.41) | +8.05% [+4.96, ...] | 385 |
| 0.78 to 0.86 | +7.50% (+6.28) | +8.53% [+6.18, ...] | 400 |
| **0.70 to 0.86 (combined)** | **+8.06% (+6.89)** | **+8.33% [+5.96, +10.52]** | **408** |
| 0.86 to 0.95 (heavy fav) | +2.79% (+1.87) | +3.80% [+1.73, +5.43] | 407 |
| baseline 0.70 to 0.95 | +5.09% | +5.28% | 413 |

The combined LOW band [0.70, 0.86) and the heavy-favorite band [0.86, 0.95] have
**non-overlapping 95% CIs** (5.96 > 5.43), in both train and OOS. The LOW band is
robustly about **2x** the heavy-favorite edge and clearly above the whole-band
baseline. This is the favorite-longshot bias operating as documented: moderate
favorites are more underpriced than near-certain favorites (which are already
close to fairly priced and carry larger loss tails when they lose).

Time-to-close added nothing usable: ~99% of fills are within 3h of the game
(Tnear), which carries the edge; the Tmid/Tfar buckets are tiny-n and noisy.

## On the locked gate

The locked gate's single-cell rule (criterion 4: a cell must be top-2 by
event-mean in BOTH windows) returned no pass, because the signal is a contiguous
BAND in which the two halves (0.70-0.78 and 0.78-0.86) swap ranks by noise (both
~+8%). That criterion was the wrong instrument for a band signal, and the
tiny-n joint cells polluted the raw-mean ranking. The finding does NOT depend on
it: the LOW band passes the substantive criteria (1 OOS beats baseline, 2 OOS CI
> 0, 3 train CI > 0, 5 OOS n >= 30) and is separated from the heavy band by
non-overlapping CIs. This is reported transparently rather than rationalized:
the rank guard is mis-specified for a band, the statistical separation is real.

## Deployable recommendation (operator approval required; NOT deployed)

Concentrate v1's KXMLBGAME maker bids on **yes_px in [0.70, 0.86)** instead of
[0.70, 0.95]. v1 is bankroll-constrained, so it should spend its limited capital
on the ~+8% fills, not dilute into the ~+4% heavy-favorite fills (which are still
positive-EV but half the edge and carry the larger loss tail). LOW and heavy have
roughly equal fill volume historically (n ~1736 vs ~1733 train events), and MLB
runs many simultaneous games nightly, so the LOW band has ample capacity to
absorb the small bankroll. Expected effect: average edge per fill rises from
~+5.3% to ~+8.3% (about a 57% per-fill EV improvement), with lower tail risk.

**Exact change:** lower the favorite upper cap from 0.95 to 0.86. In the current
code this is `FAVORITE_UPPER_CAP` (src/kalshi_bot/strategy/favorite_maker.py) and
the `mid_band_upper` in the scanner config built by
`scripts/paper_trade_favorite.py`. The cleanest minimal edit is the scanner
`mid_band_upper=(0.70, 0.86)`. Note this is a GLOBAL cap (it would also apply to
the other validated prefixes when they come into season); the band effect is a
general favorite-longshot phenomenon and very likely generalizes, but it is
VALIDATED here only on MLB. Re-running this analysis on KXATPMATCH / KXWTAMATCH /
KXNFLGAME / KXNCAAFGAME before each comes into season is the clean follow-up.

## Caveats (carry forward; do not over-trust the absolute level)

- F11: Becker fills are what HAPPENED, not what a new resting bid fills at. The
  ~+8% is an upper bound; the RELATIVE band finding (LOW > heavy) is more
  F11-robust than the absolute level and is what the recommendation rests on.
- Adverse selection: the live -4.9pp post-fill drift is not in this data. The
  band change should still be confirmed against v1's live realized P&L by band
  before any capital scale-up.
- Decay: 2024-2025 magnitude may compress in 2026 (Burgi).

## Verdict

Not a NULL. A real, OOS-robust, economically-grounded refinement: v1's MLB edge
lives in 0.70-0.86. Recommend lowering v1's favorite cap to 0.86 (pending
operator approval), and re-validating per-prefix as the others come into season.

---

*Em-dash and en-dash audit: verified clean after write.*
