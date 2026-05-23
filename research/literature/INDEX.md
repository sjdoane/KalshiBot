# Project Kalshi Literature Index

7 academic / community papers studied for Project Kalshi, organized
by load-bearing-ness for our specific EC-1 hypothesis (KXHIGH
weather maker-quoting). Each file is a thorough extraction with
data, methodology, findings, pin quotes, and explicit "implications
for Project Kalshi" sections.

Maintenance: when a new paper is added, copy the structure of an
existing file (any of the 7 below is fine), then append a TLDR to
this index and to the memory file
`project_kalshi_literature.md`.

## The four-fact summary

1. **Makers > Takers on Kalshi.** Whelan's equilibrium model
   predicts it; Burgi's data confirms (-9.64% vs -31.46%); Becker
   confirms (+1.12% vs -1.12% post-2024); Bartlett decomposes it
   into adverse-selection-loss + behavioral-surplus-gain.
2. **Weather has small bias.** Burgi ψ 0.031 (vs 0.034 cross-cat
   avg); Becker 2.57pp per-trade gross gap; Le finds it's
   overconfident at short horizons, underconfident at long.
3. **2024 sign flip.** Pre-October-2024 takers won; post-flip
   makers win. Only use post-flip data for modeling.
4. **Bias is shrinking.** Burgi ψ dropped from 0.048*** (2024) to
   0.021* (2025) as institutional MMs entered.

## Papers

| # | File | First author | Year | Venue | Status |
|---|---|---|---|---|---|
| 1 | [burgi-deng-whelan-2025.md](burgi-deng-whelan-2025.md) | Burgi/Deng/Whelan | Jan 2026 | UCD WP / CEPR DP20631 | Peer-reviewable academic |
| 2 | [becker-2026-microstructure.md](becker-2026-microstructure.md) | Becker | Early 2026 | jbecker.dev | Personal research, 72M trades |
| 3 | [le-2026-crowd-wisdom.md](le-2026-crowd-wisdom.md) | Le | Feb 2026 | arXiv 2602.19520 | Preprint, uses Becker's data |
| 4 | [bartlett-ohara-2026-adverse-selection.md](bartlett-ohara-2026-adverse-selection.md) | Bartlett / O'Hara | Apr 2026 | SSRN / Stanford Law | Working paper, partial extraction |
| 5 | [whelan-2026-betfair.md](whelan-2026-betfair.md) | Whelan | Jan 2026 | CEPR DP20633 | Theoretical foundation (Betfair) |
| 6 | [diercks-katz-wright-2026-feds.md](diercks-katz-wright-2026-feds.md) | Diercks/Katz/Wright | Feb 2026 | Fed FEDS 2026-010 | Fed working paper, macro focus |
| 7 | [zerve-calibshi-2026.md](zerve-calibshi-2026.md) | "umbreonseele" (pseudonym) | Mar 2026 | Zerve Gallery | Community notebook, NOT peer-reviewed |

## One-paragraph TLDRs

### #1 Burgi, Deng, Whelan 2026 - the empirical foundation
First academic paper with transaction-level Kalshi data (313k
prices, 2021 - April 2025). Showed maker -9.64%, taker -31.46%
average returns (pre-2025 fees). Makers profitable on contracts
>= 50c (+2.6%, 33% SD). Weather has SMALLER favorite-longshot
bias than the cross-category average. Bias attributable to
Kahneman-Tversky probability over-weighting (β = 0.09) plus modest
disagreement.

### #2 Becker 2026 - the biggest sample
72.1M trades through November 2025. Per-category maker-taker gaps
in basis points; weather gap is 2.57pp per trade (mid-tier).
Documents the 2024 sign flip - pre-October-2024 takers won +2.0%,
makers now win +2.5%. Mechanism is order-flow accommodation, not
forecasting (Cohen's d = 0.02 between maker YES vs NO returns).

### #3 Le 2026 - calibration regime structure
Decomposes prediction market calibration into 4 components (87.3%
of variance). The load-bearing finding for Project Kalshi: weather
is OVERCONFIDENT at short horizons (prices too extreme), but
UNDERCONFIDENT at long horizons (prices compressed toward 0.5).
This explains why Phase 1.5 (close-window) showed 9pp edge while
Phase 1.6 (pre-resolution) showed only 1.5pp - opposite regimes.

### #4 Bartlett & O'Hara 2026 - adverse selection vs behavioral surplus
41.6M trades. VPIN-adapted adverse-selection metric. Single-name
markets have higher informed price impact but makers earn 2x more
per contract because traders systematically overbet YES on
NO-settling markets, generating a behavioral surplus that
cross-subsidizes adverse selection. KXHIGH per-day strikes are
single-name markets (higher both effects). Full PDF inaccessible
without SSRN auth; extraction is abstract-level.

### #5 Whelan 2026 - the theoretical foundation
The model Burgi 2026 adapted for Kalshi. Maker/Taker sort by
subjective belief into 5 actions. Predicts Maker > Taker returns
and nonlinearly worse Taker losses on longshots. Multiple
equilibria (thick vs thin). Empirical Betfair work on 200k+ soccer
matches confirms predictions pre-match; "Yogi Berra effect"
emerges late in-play (bettors overestimate late comebacks).

### #6 Diercks/Katz/Wright 2026 - Fed macro paper
Validates Kalshi macro markets (CPI, NFP, FOMC) as accurate as
Bloomberg consensus and FRBNY Survey of Market Expectations.
Kalshi beats fed funds futures for day-before-FOMC fed funds rate
mode forecast. Confirms macro is NOT a retail edge (institutions
make these markets efficiently). Doesn't analyze weather.

### #7 Zerve CalibShi 2026 - community origin of EC-1
Anonymous community notebook. Source of the "14.8x ECE improvement
on 8,494 KXHIGHNY markets via isotonic regression" claim that
originally motivated EC-1. CRITICAL: no in-sample-vs-OOS partition
disclosed. The 14.8x figure is almost certainly in-sample. Our
Phase 1.6 OOS gate (which Zerve never did) shows the true number
is 1.44x and below the tradable threshold after fees. **Do not
cite as evidence of edge in any future plan.**

## Convention for new entries

When you add a new paper:
1. Write the full extraction following the existing file structure
   at the same level of detail.
2. Add a row to the table above (preserve the alphabetical-by-
   importance ordering).
3. Add a one-paragraph TLDR in the order matching the table.
4. Update the count at the top of this file.
5. Append the same TLDR to
   `~/.claude/projects/.../memory/project_kalshi_literature.md`.
6. If the new paper adds a 5th-or-greater "must remember" fact,
   add it to the four-fact summary section at the top.
