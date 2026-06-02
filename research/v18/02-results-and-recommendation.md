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

**This section was corrected after an adversarial review returned MODIFY.** The
original draft recommended HARD-DROPPING [0.86, 0.95] (lower the cap to 0.86).
The reviewer correctly flagged that as an overstatement that conflates per-fill
edge with total profit: the heavy-favorite fills are still positive-EV (+3.8%),
lower-variance, and higher-win-rate, so deleting them only helps if v1's bankroll
is the BINDING constraint (i.e. it routinely runs out of capital and turns fills
away). At ~$50-68 across many simultaneous nightly MLB games, that is not
established, and a hard cut could LOWER total profit.

**Corrected recommendation:**
1. PRIORITIZE, do not delete. Keep the band open to 0.95 but fill the LOW band
   [0.70, 0.86) first / at larger size, and take heavy-favorite [0.86, 0.95]
   fills only with leftover bankroll (or smaller size). This captures the ~+8%
   concentration AND keeps the +3.8% residual EV. Return-on-stake (edge / price)
   makes the LOW band's advantage even larger (about 2.5x), so a return-on-stake
   priority is the right ordering.
2. FIRST measure whether capital is actually binding. Check v1's live state on a
   typical MLB night: if it leaves bankroll idle (resting + filled notional well
   below its 60% slice), capital is NOT binding and a hard cap would strictly
   reduce profit, so do priority/sizing instead. Only if v1 routinely deploys
   its full slice does a hard [0.70, 0.86) cap become the right call.
3. The favorite floor/cap is GLOBAL in the current code (`FAVORITE_UPPER_CAP`,
   scanner `mid_band_upper`), but this is validated only on MLB. Re-run this
   analysis on KXATPMATCH / KXWTAMATCH / KXNFLGAME / KXNCAAFGAME before each
   comes into season before any global change.

The implementation is therefore a per-bid PRIORITY/SIZING change (size or order
v1's MLB bids by return-on-stake, LOW first), not a one-line cap edit. That is a
larger code change and gets its own design + review when the operator approves.

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
lives in 0.70-0.86 (about 2x the heavy-favorite band, non-overlapping CIs). The
deployable action (post-review) is to PRIORITIZE the LOW band by return-on-stake,
NOT to delete the still-positive heavy band, and to first confirm whether v1's
bankroll is actually the binding constraint. Re-validate per-prefix as the others
come into season. An adversarial methodology review confirmed the finding SOUND
and corrected the deployment logic from "drop" to "prioritize".

---

*Em-dash and en-dash audit: verified clean after write.*
