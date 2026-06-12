# v22 verdict: NULL across the slate (killed at the pre-registered screen)

**Date:** 2026-06-11. Full numbers: `04-screen-results.json` (screen run
once, gates evaluated mechanically; no re-runs, no tuning).

## P1 new-listing cold-start maker premium: KILLED (K-P1)

- Pooled cold-minus-aged contrast: +4.33pp, but the joint two-sample
  event-cluster 95pct CI **includes zero** ([-0.19, +8.38], 497 included
  events, both fee modes agree). K-P1 fails on the CI clause.
- **The Whelan decay guard fired:** the 2025-only contrast (markets listed
  2025+) is NEGATIVE: -0.91pp, CI [-5.05, +2.44], 365 events. The pooled
  positive lives entirely in 2024Q4 listings. probe_required_N = None by
  construction; no probe could have launched even on a pooled pass.
- **The within-event paired diagnostic is NEGATIVE: -2.69pp (SE 1.38, 509
  events).** Holding the market fixed, cold fills underperformed aged
  fills. The pooled +4.33pp was COMPOSITION (cold fills are 78pct Politics
  prints; aged comparators draw differently), exactly the H-2 confound the
  methodology critic forced into the design. Had K-P1 passed, this
  diagnostic would have blocked auto-promotion anyway.
- Honest scope notes: realized MDE 2.74pp pooled / 3.36pp on the 2025
  slice (a sub-3pp cold-start premium was not detectable); fill-class
  populations after matching exclude 584 cold trades in 26 events
  (reported by group in the JSON); after-close dropped share 0.0044pct.
- Becker-print caveat stands (lock L-3): this contrast is not an upper
  bound on the live premium; but with the 2025 effect negative and the
  paired diagnostic negative, no forward case exists.

## P3 affirmation tax (longshot NO-maker): KILLED (K-P3), informative

Realized YES rate at the selected 3-8c legs is **6.34pct vs 5.40pct
implied** (n = 31,416 events): longshots in the surviving (non-graveyard)
categories settled YES MORE often than priced. NO-side excess net of the
conservative flat fee: **-1.94pp** (event CI [-2.22, -1.68]; prefix-cluster
sensitivity [-2.92, -1.13], k = 699; 2025-only -1.83pp). One-sided binomial
p = 1.0 (the deviation is in the WRONG tail entirely). The classic
favorite-longshot harvest is not merely decayed here; it is inverted:
selling lottery tickets at these prices LOSES money in this population.
Consistent with the v18 heavy-underdog-weak prior and Whelan's 2025 decay.
Do not revisit longshot NO-maker on Becker-era data without NEW evidence.

## P2a flow-toxicity overlay: report-only, weak/no signal at this cut

Oriented-imbalance halves differ little in Sports (+1.09 vs +1.10pp gross)
and Crypto (+1.17 vs +1.13pp); Politics shows the high-imbalance half
BETTER (+0.72 vs +3.16pp), opposite the toxicity hypothesis. No group was
skipped. The overlay earns no priority for v23; the accumulating
v1-own-fills diagnostic (P2b, read at >= 200 settled fills) remains the
clean future test.

## Round disposition

All slate members dead or report-only; no probe launches; no capital was
ever at risk; the C0 branch table's v22 rows are moot. v22 closes NULL at
a cost of one day, five reviewed artifacts, and ~0 dollars. Per the
no-third-bite rule the slate is not re-tuned. What survives the round:
the archived dated fee table (`fee_table.json` + research note, reusable
by every future Becker screen), the frozen category map, the joint
two-sample cluster-bootstrap implementation (harness-verified), and two
sharpened priors: cold-start premia are composition artifacts at this
venue, and the longshot tail is no longer (if it ever was) a maker
harvest. v21 Candidate C (ladder locks) remains the live thread, verdict
by 2026-06-23.
