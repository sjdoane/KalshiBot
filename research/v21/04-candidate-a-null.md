# v21 Candidate A: NULL (killed at Phase 1, pre-registered screen)

**Date:** 2026-06-09
**Verdict:** KILLED at the Phase 1 Becker screen. All three pre-registered
cells fail S-A1a (event-cluster bootstrap 95% CI on train includes zero).
Two cells additionally fail S-A1c, and the Other-replacement cell fails
S-A1d. Per lock section 2.8: no criterion re-tuning, no new-cell scanning,
no forward shadow. Candidate A ends here.

Run: `scripts/v21/becker_screen.py` (code-reviewed pre-run, commit
`8fd1f0f`), frozen allowlists committed pre-screen (`ed972a0`), lock v3
(`d35c1f1`). Full numbers in `research/v21/03-screen-results.json`.

## The result

| Cell | Train net | Train event-CI (95%) | k events | S-A1a | S-A1c (rec) | S-A1d | Verdict |
|---|---|---|---|---|---|---|---|
| Media [0.40,0.60) | +2.06pp | [-0.28, +4.52] | 135 | FAIL | 84 ev / 36 pfx: FAIL | 37.3: pass | KILLED |
| Entertainment [0.40,0.60) | +0.20pp | [-1.45, +1.81] | 604 | FAIL | 151 ev / 27 pfx: FAIL | 31.1: pass | KILLED |
| Other-allowlist [0.60,0.80) | -0.79pp | [-5.63, +3.82] | 167 | FAIL | 191 ev / 58 pfx: FAIL* | 28.1: FAIL | KILLED |

*Other passes the prefix floor (58 >= 30) but fails the event floor
(191 < 200).

Recency-slice points (+9.19, +5.75, +5.03pp) are higher than train, but the
slice overlaps the Round 15b discovery sample (lock: NOT OOS, consistency
only) and S-A1a is the binding gate. The pre-registered rule stands.

## Why this is the expected, healthy outcome

The plan critic (01-plan-critique.md, C1) predicted this exact collapse:
the Round 15b +6.55pp Media pedigree was computed with a TRADE-LEVEL
normal-approximation CI over ~81k correlated trades. The effective sample
was always the EVENT count (135 events in the train window under the
locked population), orders of magnitude smaller. Under honest
event-cluster inference the apparent edges are statistical noise around a
small positive mean, and one cell is negative.

Contributing population honesty (all pre-registered, methodology critic
H-1/H-4): the frozen prefix allowlists (80% volume coverage), the uniform
60-day horizon cap (dropped 14-42% of train trades; the long-dated junk the
live bot could not forward-test anyway), and the post-2024-11-01 train
window. These make the screened population match what a live maker bot
would actually quote; the edge does not survive in that population.

## What died with it

- The "mid-bias non-sports maker cells" angle flagged since Round 15b as
  "combined-side LOCO-robust but never deployed" is now resolved: it was a
  trade-level-CI artifact, not a deployable edge. The flag should not be
  re-surfaced in future rounds without NEW evidence at the event-cluster
  level.
- No forward shadow collector for A is built (saved: the full Phase 2
  engineering + 30-60 days of wall-clock).

## Cost of the kill

One session: lock + two critics + freeze + screen, $0 capital, no live
API calls, local compute only. The critic-mandated ordering (cluster CI
first, as the cheapest kill) did exactly what it was designed to do.

## What remains alive in v21

Candidate C (cumulative-ladder monotonicity locks) continues per the
operator's directive, via the zero-build C0 spot-scan (lock 3.3): live
read-only structural scan, G-C0 >= 3 distinct confirmed net-of-fee locks
in 21 scheduled scans over 7 days, else C is also NULL and v21 closes.
