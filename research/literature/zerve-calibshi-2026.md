# Zerve CalibShi Study (March 2026)

**URL:** https://www.zerve.ai/gallery/85cce830-f612-4b23-8b78-34d7da65a2c6
**Author:** "umbreonseele" (anonymous community user)
**Date:** 2026-03-22
**Venue:** Zerve Gallery (community notebook hosting, NOT peer-reviewed)
**Retrieved:** 2026-05-23

**Why this matters for Project Kalshi.** This is the SOLE source of the
"14.8x ECE improvement" headline that the original Phase 1 research
brief identified as the basis of EC-1 (KXHIGH weather maker-quoting).
Our Phase 1.5 / 1.6 gate exists specifically to validate whether this
finding survives an honest out-of-sample test, because Zerve did NOT
disclose one.

## TL;DR for future Claude

**The Zerve study is methodologically thin and should NOT be trusted
as a stand-alone basis for risking real capital.** It is a community
calibration notebook, not a research paper. The headline 14.8x ECE
ratio is almost certainly an in-sample artifact. Project Kalshi's
Phase 1.5 (close-window) showed the gap between Zerve's claim and
honest OOS is large; Phase 1.6 (open-window) tests whether ANY signal
generalizes.

## What Zerve actually documents

| Claim | Detail | Trust |
|---|---|---|
| Sample size | 8,494 settled KXHIGHNY markets | OK |
| Series | KXHIGHNY (NYC daily high) only | OK |
| Cities | Only NYC; no cross-city work | Single-city limitation |
| Date range | Not disclosed | UNKNOWN |
| Volume filter | Not disclosed | UNKNOWN |
| Liquidity filter | Not disclosed | UNKNOWN |
| Baseline ECE | 0.01624 | OK on the number |
| Calibrated ECE | 0.00109 | OK on the number |
| Ratio | 0.01624 / 0.00109 = 14.9x | Math checks |
| In-sample vs OOS | **Not stated** | CRITICAL GAP |
| Models tested | Isotonic, Platt scaling, Beta calibration | OK |
| Input feature | Not stated (price? mid? last trade?) | CRITICAL GAP |
| Snapshot timing | Not stated (close? early?) | CRITICAL GAP |
| Train/test partition | Not stated | CRITICAL GAP |
| CV strategy | "cross-validation" mentioned, no detail | UNCLEAR |
| Per-strike breakdown | None | LIMITATION |
| P&L / hit rate | None - calibration only | LIMITATION |
| Peer review | None - community notebook | LIMITATION |
| Author affiliation | None - anonymous handle | LIMITATION |

## The single most important deficiency

Isotonic regression fit AND scored on the same dataset is, by
construction, near-perfectly calibrated. The 14.8x figure is
**mathematically expected** if the fit and evaluation are the same
data. Without a held-out test set or walk-forward CV, the result
proves nothing about generalization to new markets.

This is exactly the trap our methodology was designed to avoid - and
which the Research Critic flagged as "the central analytical mistake"
of the pre-critic Phase 1 synthesis.

## What Project Kalshi's gates do that Zerve does not

Phase 1.5 and Phase 1.6 gates apply:
- 180-day train / 30-day test walk-forward splits with 7-day purge
- Leave-one-city-out across 5 cities
- Fee model (round-trip maker fees subtracted from edge)
- Realized P&L computation, not just calibration improvement
- Hit-rate above 2pp edge filter

These together produce a defensible OOS result. If our gate FAILS,
the Zerve 14.8x was likely in-sample noise. If our gate PASSES with
similar magnitude, Zerve's result generalizes.

## What's worth retaining

Despite the validity gaps, the Zerve study contributes:
1. Confirmation that KXHIGHNY *can* be analyzed via Kalshi's public
   API (no paid data feed needed).
2. The observation that isotonic, Platt, and Beta calibration all
   apply to this kind of binary-outcome series.
3. A specific calibration-error reduction number (14.8x) that, if
   our OOS gate produces a similar order of magnitude, would
   strongly support the claim - and if our number is materially
   smaller, would indicate Zerve was overfitting.

## Pin facts

- **Zerve is community-hosted, not peer-reviewed.** Do not cite as
  authoritative.
- **The 14.8x number is in-sample-likely.** Treat as an upper bound
  on what OOS could possibly show.
- **No P&L analysis.** Even if calibration is real, Zerve does not
  show it translates to maker profit.
- **Anonymous author.** No reputation to anchor on.

## Implications for Project Kalshi

1. **Phase 1.6 verdict is the load-bearing test.** Whatever our OOS
   median ECE ratio comes back as, that IS the trustworthy number.
   Phase 1.5's 4.77x was a close-window artifact (post-resolution
   prices); Phase 1.6 measures the actual tradable signal.

2. **If Phase 1.6 also fails C1, EC-1 is dead.** The methodology
   lock-in committed to "no third bite." Zerve's 14.8x was the only
   reason to entertain EC-1 in the first place; if a clean OOS gate
   on real data cannot reproduce a meaningful fraction of it, the
   hypothesis was never real.

3. **Do not cite Zerve in any future plan or strategy doc** as
   evidence of edge. Cite Burgi/Deng/Whelan 2026 (peer-reviewed,
   transaction-level data, real economic model) for any structural
   claims about Kalshi maker economics. Zerve is, at best, a
   hypothesis-generating prior.

4. **Phase 2 (if it happens) should design strategies that survive
   independent of Zerve.** Build the model on a defensible
   foundation (the Burgi findings + our OOS gate results), not on
   the community-notebook number.
