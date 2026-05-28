# v15 (Round 20) Final Verdict

**Date:** 2026-05-28. **Author:** parallel-context orchestrator.
**Round:** 20. **Lock:** research/v15/01-methodology-lock.md.

## TL;DR

**Both threads NULL. No new SHIP candidate.** The v15 round honestly
kills two hypotheses that emerged from Round 15c residual signals:

- **Thread A (WTA Friday day-of-week lift):** NULL. The +1.31pp
  Friday lift from research/v10a/16-time-of-day-analysis.md was a
  multiple-comparison artifact. Cluster-bootstrap CI on the
  difference includes zero in all three (full, train, OOS) windows.
- **Thread B (ITF spread widens near close):** NULL. OLS slope of
  spread on minutes-to-close is POSITIVE on both KXITFMATCH and
  KXITFWMATCH (spreads narrow slightly toward close), opposite of
  the hypothesis. The 30-min-pre-close subset is empty by probe
  cadence.

The Round 15c ITF SHADOW-CANDIDATE (any-time mean-spread maker)
remains intact and is still pending settlement P&L follow-up around
June 10-11, 2026.

## Cumulative project state after v15

Cumulative across all rounds: 9 NULLs (added 2), 1 PHANTOM, 2 PARTIALs
(v4-A, v5-A live filter), 1 GRANGER-PARTIAL (v11 MLB-night), 1
SHIP-CANDIDATE-borderline (v14 X-only, operator-authorized live trial
in progress).

v15 contributed: zero new candidates, two honest NULLs. The
methodology rigor (pre-registration, cluster bootstrap on the
correct difference, anti-confounder self-critique) caught both
hypothesized lifts as noise. This is the kill-early preference
operating as designed.

## What survives from v15

- **Negative result quality.** Both NULLs are clean: properly
  specified, properly tested, properly reported. Future rounds
  can skip these hypotheses without re-litigating.
- **Methodology template.** scripts/v15/thread_a_wta_friday.py
  shows how to test a day-of-week lift correctly (the
  "Round-15c-style" approach of just checking the cell's own CI
  is a known false-positive source).
- **Negative result on pre-close ITF timing** means the Round 15c
  Track 2C ITF probe recommendation is unchanged (mean-spread
  maker any-time, not pre-close).

## Recommended operator next steps

No new operator actions required from v15.

The existing operator queue (as of v14 live deployment):
1. Watch v14 live trial (in progress, 4-8 week evaluation)
2. Watch v1 live trial (ongoing)
3. Decide settlement P&L follow-up on Round 15c ITF probe after
   June 11, 2026 (existing Round 15c recommendation)

v15 adds nothing new to that queue.

## What was NOT done in v15

- No LLM critic agent was spawned. The methodology lock contained a
  self-critique section enumerating obvious confounders; both
  threads NULL'd before any spawn was warranted.
- No live capital changes. v1 and v14 untouched.
- No code changes to bots or scanner modules. Only new analysis
  scripts in scripts/v15/ and new research docs in research/v15/.
- No A-G5 (round confound stratification). Becker schema lacks
  the data; recorded as INCONCLUSIVE rather than fudged.

## v15 spend summary

| Item | Cost |
|---|---|
| Round 20 orchestrator session (this) | approximately $0.30 LLM |
| External APIs | $0 |
| Capital | $0 (live bots untouched) |
| **v15 total** | **approximately $0.30** |

Cumulative across rounds 1-20 LLM: approximately $15-18 + $0.30 = $15.30-$18.30 of $25 cap.
External APIs: $30 + 0 (the-odds-api credits unchanged from v14).
Capital: $0 backtest, ~$33 live deployed (v1 + v14).

## Why honest NULL is the right outcome

The Round 15c TRack 2D Friday signal looked promising because the
Friday cell's own CI excluded zero. But that's the wrong test. The
right test is the DIFFERENCE-of-means with a paired cluster
bootstrap, which is what v15 Thread A did. The difference CI
includes zero in all three windows. The OOS window even has the
biggest point estimate (+1.95pp) but the widest CI (+/-4pp), which
is exactly what you'd expect from sample noise on n=56 events.

Similarly Thread B's positive-slope finding is the opposite of the
hypothesis. The honest report is "the hypothesized direction is
wrong; ITF spreads narrow slightly toward close, not widen."

Both findings could have been salvaged with selective restatement
of the hypothesis. The v15 lock pre-registered the gates and the
"no third bite" rule applies. NULL is the correct verdict.

## Anti em-dash audit

Verified after writing.
