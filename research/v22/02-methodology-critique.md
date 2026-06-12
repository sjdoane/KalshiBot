# v22 Methodology Critique (verbatim critic report, 2026-06-11)

Verdict: LOCK-WITH-EDITS. All must-do edits incorporated in lock v2
(`00-methodology-lock.md` change log). Highlights: C-1 cell construction
underdefined (TTE/price bands not enumerated, unmatched-cell and
self-matching rules missing); C-2 forward probe arithmetically self-killing
(half-effect powering needs ~780-2,180 events vs 200 reachable only at
fill rate 1.0; starvation threshold and cluster unit undefined); H-1 CI
treated aged comparators as known constants (joint two-sample cluster
bootstrap required); H-2 price-band composition confound (favorite-longshot
leakage) + within-market paired diagnostic; H-3 the 300-event floor
unverified (structural pre-count required BEFORE the screen); H-4 fee
schedule not verified WITHIN the Becker window (dated per-series fee table
or dual-fee conservative gate); H-5 category-map construction rule missing;
H-6 probe quoting rule unregistered (screen-to-probe forking path); M-1
graveyard cells in/out ambiguity (resolved: EXCLUDED from pooled estimand);
M-2 P2a within-category median + ORIENTED imbalance (signed toward the
print's taker side, not net-YES/NO); M-3 P3 mechanics locked (fill volume =
contracts; unweighted p-bar; one-sided lower-tail binomial; Hoeffding
conservativeness VERIFIED correct); M-4 v21 Section 2.2 incorporated by
reference; M-5 timestamp definitions; M-6 2025-only effect feeds probe
power; M-7 probe ceiling is $20 at current v1 balance, bankroll-capped
skips logged/excluded with 20pct selection-bias flag; M-8 screen verdict
shelf life 2026-10-01; L-1 VOID precision; L-2 two-sided; L-3
the contrast of two F11 upper bounds is not itself signed (honesty line);
L-4 NOT-list extensions.

The full critic text is preserved in the session transcript; this file
records the findings actioned and their resolutions. F11 schema audit:
PASS (every field needed exists at the needed timestamp).
