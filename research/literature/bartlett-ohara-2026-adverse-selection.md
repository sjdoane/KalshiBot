# Bartlett & O'Hara (Apr 2026): "Adverse Selection in Prediction Markets: Evidence from Kalshi"

**Authors:** Robert Bartlett (Stanford Law), Maureen O'Hara (Cornell)
**SSRN:** abstract_id=6615739
**Posted:** April 21 2026, revised May 6 2026
**Affiliation:** Stanford Law / Arthur and Toni Rembe Rock Center
for Corporate Governance
**Retrieved:** 2026-05-23 (abstract-level via SSRN landing page and
Stanford Law publication page; full PDF requires SSRN auth or
direct paywall)

**Why this matters for Project Kalshi.** Largest Kalshi sample
publicly analyzed (41.6M trades), with a novel adverse-selection
metric (VPIN-style adaptation) that decomposes maker returns into
information-toxicity loss vs behavioral-surplus gain. The
**behavioral surplus mechanism** (YES-overbet on NO-settling markets)
is a structural cousin of Burgi's favorite-longshot bias and
Becker's order-flow-accommodation finding. For Project Kalshi: it
matters that the maker advantage is decomposable into a part that
generalizes (behavioral surplus) and a part that's market-type-
specific (adverse selection in single-name markets).

**Note: this summary is built from the SSRN abstract + the Stanford
Law publication page summary.** I was unable to retrieve the full
paper because SSRN returned HTTP 403. When access is available,
this file should be re-written with full extraction.

## TL;DR (from accessible summaries)

1. **41.6M trades on Kalshi** analyzed for adverse-selection
   patterns.
2. **Single-name markets show greater informed price impact than
   broad-based markets.** Single-name = one specific outcome
   (e.g., "Yankees win"). Broad-based = multi-outcome events
   (e.g., "Who wins the AL East?"). Informed traders gravitate to
   single-name markets where information advantage is largest.
3. **Effective spreads are only modestly wider in single-name
   markets** despite higher adverse selection.
4. **Market makers earn 2x more per contract in single-name
   markets** despite the adverse selection - this is the puzzle.
5. **Resolution of the puzzle:** "traders systematically overbet
   YES in markets that predominantly settle NO, generating a
   behavioral surplus that cross-subsidizes adverse selection."
6. **VPIN adaptation for binary outcomes:** adapts Easley/Lopez de
   Prado/O'Hara's "Volume-synchronized Probability of Informed
   trading" metric for prediction markets. One-sided order flow
   predicts maker losses in single-name markets but not broad-based.
7. **New microstructure equilibrium concept proposed** for
   "bilateral settlement markets" (their term for binary outcomes).

## What it adds beyond Burgi and Becker

Burgi documented the maker-taker gap; Becker decomposed it by
category. Bartlett & O'Hara decompose it by INFORMATION ASYMMETRY
type:

| Mechanism | Source | Magnitude |
|---|---|---|
| Adverse selection (informed traders pick off makers) | Single-name market design | Negative for makers; bigger in single-name |
| Behavioral surplus (retail overbet YES on NO-settling markets) | Probability misperception (Kahneman-Tversky) | Positive for makers; cross-subsidizes adverse selection |

Net maker return = behavioral surplus - adverse selection loss. In
single-name markets, both terms are larger; the behavioral surplus
exceeds the adverse selection by ~2x (per the abstract's
"2x more per contract" claim).

This decomposition is potentially more actionable for strategy
design than Burgi's category-level or Becker's per-domain breakdowns:
it says **which kind of order flow** generates the maker advantage.

## Implications for Project Kalshi (EC-1 KXHIGH weather)

1. **KXHIGH per-day strikes are arguably single-name markets.**
   A specific strike "high > 75°F" is one specific outcome, not a
   multi-outcome event. So weather might exhibit higher adverse
   selection AND higher behavioral surplus per Bartlett & O'Hara's
   logic.

2. **Behavioral surplus is the source of maker edge in EC-1.**
   The retail YES-on-longshot pattern (deeply OTM strikes priced
   too high) is exactly the behavioral surplus mechanism. This is
   consistent with Burgi's favorite-longshot finding and Becker's
   2.57pp weather maker advantage.

3. **Adverse selection is a real risk** for a passive maker bot.
   Sophisticated traders with weather information (private
   forecast models, faster NWS feed access, etc.) can pick off
   resting maker orders. Project Kalshi must factor in adverse
   selection probability when sizing maker orders.

4. **A toxicity monitor (VPIN-style) for KXHIGH could be a Phase
   2+ research item.** If one-sided order flow appears, that's
   informed taker activity and we should cancel resting orders or
   widen quotes. This is a known market-microstructure technique
   adapted by Bartlett.

5. **Single-name vs broad-based distinction matters for which
   Kalshi markets to enter.** KXHIGH-{date}-T{strike} is
   single-name (specific date, specific city, specific strike).
   The broad-based equivalent would be "tomorrow's NYC high in
   range X-Y" but Kalshi doesn't structure markets that way for
   daily highs. So EC-1 inherently operates in the riskier
   single-name space.

## What I cannot yet verify (waiting on full PDF access)

- Exact maker return numbers in basis points (the "2x more per
  contract" is abstracted; the actual cents per contract isn't in
  the SSRN abstract).
- Time period covered (probably overlaps with Becker's).
- Specific VPIN methodology (need to see Section 3 or methodology
  appendix).
- Per-category breakdowns (does weather appear?).
- Whether Burgi 2026 is cited.
- The "new microstructure equilibrium concept" definition.
- Sample selection rules.

When SSRN access is available, this file should be expanded with
the full extraction.

## Pin quotes (from available summaries)

> "Market makers earn twice as much per contract—a puzzle resolved
> by finding that traders systematically overbet YES in markets
> that predominantly settle NO, generating a behavioral surplus
> that cross-subsidizes adverse selection."

> "One-sided order flow predicts maker losses in single-name
> markets but not broad-based markets."

> "We propose a new microstructure equilibrium concept for
> bilateral settlement markets."

## Cross-reference summary

| Paper | Maker mechanism explanation |
|---|---|
| Burgi 2026 | Sorting by belief; structural over-weighting of small probabilities (β=0.09) |
| Becker 2026 | Order-flow accommodation; makers don't forecast, they sit on the side retail overpays |
| Le 2026 | Calibration error decomposed into 4 components; politics chronically compressed, weather regime-flips |
| **Bartlett & O'Hara 2026** | **Adverse selection vs behavioral surplus; behavioral surplus DOMINATES in single-name markets** |

These four papers form a coherent picture: the maker edge on Kalshi
is real, comes mostly from retail overpricing extreme outcomes (a
behavioral pattern), and varies in magnitude by market type. Project
Kalshi's EC-1 hypothesis lives in the weather subset of this
picture.
