# Blocker 01: Polymarket-to-Kalshi matching gap for KXMLBWINS

**Status:** Partial blocker. Not fatal to v3.
**Affected:** 5 of 11 strict-v1-eligible markets in the 2025 sample (all KXMLBWINS season-win-total markets).
**Severity:** Medium. Match rate on the rest (KXMLBPLAYOFFS, KXMLB{AL,NL}{EAST,CENT,WEST}) is 100%.

## What failed

For the 2025 MLB season Polymarket did not list per-team regular-season win-total markets. We attempted four slug variants for the umbrella event:

- `mlb-2025-regular-season-win-totals`
- `2025-mlb-regular-season-win-totals`
- `mlb-2025-win-totals`
- `mlb-regular-season-win-totals`

All returned HTTP 404 from `gamma-api.polymarket.com/events/slug/{slug}`. Public-search returned related events (e.g. `mlb-team-to-win-100-games`, `mlb-team-to-have-longest-win-streak`) but none target the same threshold structure as Kalshi's KXMLBWINS-{TEAM}-25-T{N}.

For 2026 Polymarket DOES list `mlb-2026-regular-season-win-totals` with 30 per-team sub-markets at thresholds chosen by Polymarket (e.g. NYY at 86.5, BOS at 85.5). Even when both platforms list the same team, the thresholds differ: Kalshi's KXMLBWINS-CHC-25-T90 (over 90) vs Polymarket's likely 86.5 or 88.5 for the same team. A direct match would require both threshold and team alignment.

## Why this is not fatal

- Match rate is 65% (13 of 20) at the eligible-band sample, well above the 50% blocker threshold from the master plan.
- The 6 KXMLBPLAYOFFS markets (a major v1-eligible series) all matched 100% deterministically.
- The 6 KXMLB-division markets all matched 100% deterministically (each of the six divisions has its own Polymarket event with per-team sub-markets).
- v3 can train a model with Polymarket features available for ~65% of rows and use a missing-feature indicator for the remaining 35%. Not ideal, but workable.

## What it would take to lift this

1. **Manual mapping**: hand-curate a Kalshi-T{N} threshold to Polymarket-X.5 threshold table per season. Labor-intensive. Polymarket also offers ~6 thresholds per team per season for some markets, so this could yield N=4-5 thresholds per Kalshi market.
2. **Threshold-difference accommodation**: instead of requiring exact threshold match, compute the implied probability differential at the OBSERVED threshold gap. This requires a distributional assumption on regular-season wins (binomial or skellam). Adds modeling cost.
3. **Pivot to playoffs/division markets only**: v1's eligible universe is dominated by KXMLBPLAYOFFS and division-winner markets anyway in the long-horizon band. Excluding KXMLBWINS would drop us from n=11 eligible to n=6 eligible in 2025 - structurally too small for C4 (>=15) without multi-season pull.

## Recommendation

Defer the KXMLBWINS matching question until Phase 2 dataset design. If the v3 model uses Polymarket as ONE feature among many, the rows where the feature is missing can be handled with imputation or a missing-feature flag. If the v3 model uses Polymarket as the PRIMARY input, KXMLBWINS rows must be dropped, which forces a multi-season pull (2023, 2024, 2025) to recover sample size.
