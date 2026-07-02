# v26 PROPOSAL: window-aggregate markets (TSA weekly average + monthly rain totals)

**Date:** 2026-07-02. Status: PROPOSAL (pre-lock, pre-critic). Supersedes the
00-proposal-draft.md sketch with verified universe facts. No outcome-conditioned
Kalshi analysis has been run. Hypothesis family ~#26.

## One-line idea

Trade Kalshi window-aggregate ladders as a TAKER when the arithmetic of the
already-published partial window plus an empirical remainder distribution diverges
from the market price: the settlement value becomes progressively PINNED by public
daily observations, and the claim under test is that thin ladders lag that pinning.

## Two registered hypotheses (closed set)

- **H-A (TSA weekly average):** KXTSAW settles on the weekly average of daily TSA
  checkpoint screenings (week ending Sunday), published daily next-morning by TSA.
  By late week, 4-6 of 7 days are published facts; the remainder is a stable
  day-of-week-seasonal quantity (holiday effects aside). Signal: P(avg > K) from
  partial sum + empirical remainder distribution (day-of-week + trend conditioned,
  built walk-forward from TSA history). Universe verified: 48 settled weekly events
  May 2025 - Apr 2026 via the historical endpoint (plus ~9 more via live settled),
  1.35M contracts total volume, quadratic x1 fee.
- **H-B (monthly rain totals):** KXRAIN{NYC,CHI,SEA,HOU,MIA,AUS,DEN,LAX,DAL,SFO}M
  settle on the NWS CLI monthly total precipitation at a fixed station. Month-to-date
  precip is a published daily fact; the remainder is day-of-year climatology
  (empirical, from 30+ years of ACIS daily data, walk-forward). Universe verified:
  NYC 26 monthly events back to Mar 2024 (2.07M contracts); 9 more cities with ~6-7
  events each since Dec 2025 (0.3-1.4M contracts each; ~85 city-month events total).

## Why this differs from everything dead (including v25)

- v25's signal was a MODEL of a smooth series' drift; its null was model
  overconfidence. Here the dominant signal component is ARITHMETIC: the partial
  window is settled fact, and late-window probabilities are dominated by the pinned
  component, not by any forecast. The model content (remainder distribution) is
  empirical climatology, not a fitted dynamic system: nothing to go degenerate.
- TARGET: physical count/aggregate series with no sharp reference book, no options
  surface, no wholesale feed. REGIME: within-window convergence on thin Economics/
  Climate ladders. ROLE: pricing a partially-determined outcome. FEATURES: public
  daily partial sums + climatology.
- Known counter-prior honestly stated: the MLB post-determination NULL showed Kalshi
  converges instantly AT determination on its most liquid series; and any
  weather-adjacent forecast content risks the NWP capture phantom. The escape is
  narrow and specific: these are GRADUAL determinations on thin ladders, the signal
  needs no weather FORECAST (climatological remainder only, deliberately
  forecast-free), and the late-window sub-case approaches arithmetic certainty where
  the capture phantom cannot apply (there is nothing to forecast).

## Honest prior: ~10-12 percent

Tempering: family #26 of a project whose every informational idea died; anyone can
read TSA/CLI numbers; the most liquid moments may still be MM-covered; rain
remainders are fat-tailed (one storm can cross a strike), so "near-pinned" arrives
later than intuition suggests; TSA weekly has only ~57 clusters.
Supporting: real volumes (1.3M + 8.6M contracts lifetime); the signal's core is
arithmetic, immune to the v25 failure mode; two INDEPENDENT underlyings give the
family two shots under one honest ledger; all data free and (per scout, pending)
verifiable against the exact settlement source.

## Locked-test sketch (details to the lock doc)

- Reuse the v25 machinery and E-edit template wholesale: taker prints only, one
  position per market per ET day, binding +3c haircut run, side-matched +1c reported,
  worst-case quadratic taker fee, ISO-week (H-A) / calendar-month (H-B) clusters plus
  month-block and shock-window guards, power floors, verdict lattice, no third bite.
- Signal: P_agg = P(partial + remainder > K) with remainder from the empirical
  conditional distribution (H-A: day-of-week-adjusted daily screenings, trailing-year
  level-scaled, walk-forward; H-B: day-of-year climatological remainder sums from 30+
  years, walk-forward through the settled months). Divergence threshold from fee
  arithmetic (0.08 default, 0b decision rule as in v25).
- CONTROL (honesty detector): the same machinery with the partial-window information
  REMOVED (whole-window unconditional distribution). The claim is precisely that the
  market underweights the pinned component; if the no-partial-info control also
  clears, the pass is a general-miscalibration claim, not the pinning edge, and H
  fails its gate per the v25 gate-3 pattern.
- As-of discipline: TSA day t publishes next morning (~9am ET; scout verifying);
  CLI month-to-date publishes daily in the morning CLI product; both enter with
  next-day-09:00-ET availability and zero-staleness NO-FIRE on gaps; publication
  timing facts from the scout go in the lock verbatim.
- Settlement truth: Kalshi result field only. Settlement-key audit (v25 pattern):
  verify sum(daily source) reproduces the settled bracket on all testable markets;
  unexplained mismatch = KILL.

## Data plan (free; scout verifying now)

TSA daily history (tsa.gov passenger-volumes, all years); ACIS daily precip for the
11 mapped stations + 30-year climatology; Kalshi historical+live markets and trades
via the existing v25 pullers (series list swapped).

## Kill risks invited at plan critic

1. Fire concentration: pinning fires may cluster in the last 2-3 days of each window
   only, shrinking effective clusters below the floor (0b projection must check).
2. The market may already track the partial sums tightly (market-matches-arithmetic
   NULL; cheap and honest to find).
3. TSA revisions or CLI-vs-daily-sum mismatches poisoning the as-of series (scout
   consistency checks are kill switches).
4. Holiday weeks (TSA) and trace/rounding conventions (rain) as silent biases.
5. Cluster correlation: 10 rain cities share large-scale weather in a month; the lock
   must cluster conservatively (month clusters across ALL cities, not city-months).

*Em-dash audit: clean (verified after write).*
