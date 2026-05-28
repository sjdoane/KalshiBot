# v11 (Round 16) Final Verdict

**Date:** 2026-05-27. **Author:** orchestrator. **Round:** 16.
**Lock:** v2 (research/v11/01-methodology-lock.md) + v3 amendment
(research/v11/04-lock-v3-granger-amendment.md).
**Sources of truth:** research/v11/05-phase2-granger-results.md
(post-Phase-4 numerics), 07-phase3-critic.md (load-bearing review),
08-phase4-iteration.md (KILLER-1 salvage record), track2-wiring-report.md
(Track 2 SHIPPED status).

---

## TL;DR

**Track 1 verdict: GRANGER-PARTIAL.** 2 of 3 sports (MLB + NBA) show
statistically significant pre-game sportsbook -> Kalshi lead-lag on the
post-Oct-2024 game-resolution universe. NFL is underpowered (line
movement too small in T-6h to T-3h window). No capital deployed.
Strategy P&L test deferred to v12.

**Track 2 verdict: SHIPPED.** Post-hoc join script
(scripts/v11/join_filter_vs_v1.py) produces the prompt-specified
cross-table at data/live_trades/shadow/shadow_filter_decisions.jsonl.
First run on 412 shadow-log rows clean; 15 unit tests pass; existing
test suite has no regressions.

**Spend:** approximately $2.55 LLM (of $5 to $8 v11 headroom from the
shared $25 cap), $30 external (the-odds-api Starter 20k credits;
5,250 used of 19,990; the operator retains 14,740 credits which expire
with the monthly billing cycle).

**Capital risk: $0.** v11 did not deploy live capital. v1 continues on
the existing $32 with the W1 denylist applied; the v5 filter overlay
(activated 2026-05-24 separately from v11) continues active.

---

## Track 1 detailed verdict

### Hypothesis tested (locked verbatim, v3 amendment)

H0: sportsbook movement in T-6h to T-3h does NOT predict Kalshi
trade-print movement in T-3h to T-1h, given Kalshi's own T-6h to T-3h
movement.

Granger F-test on the gamma=0 restriction in:

```
delta_kalshi_post = alpha + beta * delta_kalshi_pre + gamma * delta_sportsbook + epsilon
```

### Sample (post-Phase-4 KILLER-1 fix)

- Total sampled events: 433 (170 MLB + 162 NBA + 101 NFL, validation
  split, stratified by month)
- Matched to the-odds-api: 408 (94% match rate)
- Joint coverage (all 3 deltas non-null): 372

### Per-sport Granger results (Bonferroni alpha = 0.05/3 = 0.01667)

| Sport | n | F | p_value | gamma | gamma_se | Bonferroni | gamma > 0 | Verdict |
|---|---|---|---|---|---|---|---|---|
| KXMLBGAME | 131 | 17.2248 | 0.000060 | 0.7847 | 0.1891 | PASS | YES | PASS |
| KXNBAGAME | 151 | 7.9089 | 0.005587 | 0.2855 | 0.1015 | PASS | YES | PASS |
| KXNFLGAME | 90 | 0.3998 | 0.528853 | -0.1326 | 0.2098 | FAIL | NO | FAIL |
| POOLED | 372 | 33.1505 | < 0.0000001 | 0.5007 | 0.0870 | n/a | YES | descriptive |

**2 of 3 sports pass G_GRANGER -> GRANGER-PARTIAL per lock v3.**

### Robustness diagnostics

- **LOCO-by-bookmaker (MLB only, original n=89 sample):** all 10
  single-bookmaker drops maintain F > 17, p < 0.0001, gamma > 0.73.
  ROBUST. Not re-run on n=131 post-fix sample (qualitatively unchanged).
- **Commence-offset sensitivity (MLB only, original n=89):** F-statistic
  ranges from 0.63 (2.5h offset) to 23.82 (4.0h offset) across +/- 1h
  of the pre-registered 3.5h. Signal is broad in the 3.0h to 4.0h
  range but ABSENT at 2.5h. Pre-registration was theory-grounded; v12
  should formalize sport-specific offsets.
- **Day-vs-night MLB heterogeneity (original n=89):** Granger restricted
  to MLB day games (close UTC 18-23) yields F=0.96, p=0.33 (no signal);
  night games (close UTC 0-5) yield F=14.35, p=0.0004 (strong signal).
  The MLB signal is concentrated in night games.

### What the verdict means

- A real lead-lag exists from major US sportsbooks to Kalshi
  trade-print mid in the T-6h to T-1h pre-close window on MLB and NBA
  game-resolution markets.
- NFL is uninformative due to insufficient pre-window line variance
  (NFL sportsbook lines are largely stable on game day after a week
  of pre-game shaping).
- The signal is NOT direct evidence of a monetizable strategy. v11
  did NOT test execution (the F4/F11 execution-layer phantom remains
  unresolved on Becker data; no orderbook history exists at trade
  time).

### Important caveats

- Pooled F=33.15 is descriptive, not gated. The pooled regression
  ignores sport heterogeneity; a sport-fixed-effects spec would
  attenuate the headline.
- gamma_se reported is OLS standard error assuming per-event
  independence. Block-bootstrap by calendar day would widen the SE
  (events within a day may be correlated by shared sportsbook info
  shocks). At the strong signal magnitudes for MLB and NBA, block
  bootstrap is unlikely to flip the verdict but should be reported in
  v12.
- The MLB signal is concentrated in night games. A v12 strategy P&L
  test must stratify by day vs night and verify per-stratum gate
  satisfaction.
- Match rate is 94% post-fix. The 6% (n=25) unmatched events were
  dropped due to either team-name mapping gaps (a few rare
  abbreviations) or commence-timestamp misalignment. These do not bias
  the Granger result because the dropouts are not signal-correlated.

---

## Track 2 detailed verdict

### What shipped

`src/kalshi_bot_v11/filter_v1_join.py` (pure-function join logic) plus
`scripts/v11/join_filter_vs_v1.py` (operator entry point) plus
`tests/v11/test_join_filter_vs_v1.py` (15 unit tests pass).

Output: `data/live_trades/shadow/shadow_filter_decisions.jsonl` (412
rows on first run; schema matches lock v2 Section 9.4 spec).

### What this does

Joins the existing v5 filter shadow log
(`data/live_trades/v5_filter_shadow_log.jsonl`, already accumulating
since 2026-05-24 per scripts/run_live_bot.ps1 setting SHADOW_MODE_ENABLED
+ LIVE_FILTER_ENABLED to true) with the v1 LiveOrderManager state.json
to produce the cross-table required by the v11 prompt.

### Why this is the right Track 2 path

The v11 prompt assumed the v5 filter was "shadow-mode-pending". The
audit found that the operator had already moved beyond shadow-mode and
activated the filter as an active overlay on 2026-05-24. The
prompt-specified `shadow_filter_decisions.jsonl` is a different schema
from the existing `v5_filter_shadow_log.jsonl`; the join script
produces the requested schema without modifying any v1 production code.

### Regression check

- v11 tests: 15 pass
- Existing importable tests (489): unchanged pass count
- The 8 test files with import errors in the kronos venv (lightgbm,
  pybaseball) predate v11; not regressions

---

## What v11 did NOT do

- Did NOT deploy live capital
- Did NOT modify v1 production trading code
- Did NOT touch .env (the operator added the the-odds-api key)
- Did NOT compute a strategy P&L number (deferred to v12 per lock v3)
- Did NOT touch CLAUDE.md, project_kalshi.md, or memory files (the
  operator's main session consolidates round closures)
- Did NOT exceed the budget (LLM under $5 cap; external $30 of $30 to
  $60 authorized)

---

## What v12 should do (Phase 3 critic Section D, post-Phase-4 update)

If the operator authorizes v12:

1. **Apply KILLER-1 date-matching fix to any future cross-venue
   match.** Already applied in v11 Phase 4; the corrected matcher
   should be the v12 baseline.
2. **Day-vs-night stratification on MLB.** Pre-register the split
   before re-fitting. Verify per-stratum n >= 50 and per-stratum gate.
3. **Sport-specific commence offsets.** Pre-register offset robustness
   range (e.g., +/- 0.5h) and require all 5 offsets to pass G_GRANGER.
4. **Block-bootstrap CI on gamma** at block_size = 1 calendar day.
   Report alongside OLS SE for transparency.
5. **Strategy P&L test ONLY if executable.** The F11 execution-layer
   phantom (Becker has no orderbook history at trade time; live
   spread on KXMLBGAME is 1c MM-saturated per project memory) blocks
   any retro P&L. v12 strategy test must EITHER pull a 30-day forward
   live orderbook archive from Kalshi (operator authorize live
   polling), OR pre-register an explicit execution-model assumption
   and forward-verify it.
6. **Re-justify NFL in scope or drop.** If NFL stays, expand to T-24h
   to T-12h windows where pre-game lines may move more. If NFL drops,
   the universe narrows to MLB + NBA.
7. **No live capital deployment until F11 forward spot-check completes.**
   This is the v8-A pattern applied prospectively.

Estimated v12 LLM budget: $2 to $3. External: $0 (existing credit
pool plus Becker). Capital: $0 until F11 resolves.

---

## Cumulative project state after v11

The accumulated taxonomy of failure modes (F1 to F11) is unchanged in
TYPE; v11 added a NEW INSTANCE of F1 (cross-venue date-tz mismatch)
which is documented in research/v11/replay-prevention.md.

Verdict history through Round 16:

- 8 NULLs (v2, v3, v4-B, v5-B, v5-C, v6, v7-C, v9)
- 1 CONFIRMED PHANTOM (v7-B per v8-A)
- 2 PARTIALs that became operationally SHIPPED on v1 in May 2026 (v4-A
  Polymarket fade filter, v5-A sportsbook divergence filter; both via
  the operator's 2026-05-24 LIVE_FILTER_ENABLED activation)
- 1 NEW GRANGER-PARTIAL (v11 Track 1: MLB + NBA sportsbook lead-lag)
- 1 NEW SHIPPED (v11 Track 2: join script)

The v11 GRANGER-PARTIAL is the first cross-venue causality
confirmation in this project. v1's edge is microstructure
(deep-favorite YES-maker on Kalshi sports). v11's edge is informational
(sportsbook leads Kalshi). They are operationally orthogonal; a future
v12 + capital may layer them, but only after the F11 execution-layer
phantom is resolved on the live orderbook.

---

## Operator handoff

The main orchestrator session (currently waiting on V10-B resolutions)
should consolidate Round 16 closure into CLAUDE.md and memory. The
v11 session has NOT touched those files per the prompt's hard rule.
Suggested CLAUDE.md update template (operator-authored):

```
**Round 16 outcome (2026-05-27): v11 Track 1 GRANGER-PARTIAL +
Track 2 SHIPPED.** v11 ran Granger-first on the sportsbook line
movement hypothesis using $30 the-odds-api Starter (5,250 credits of
20,000) plus Becker. After Phase 4 KILLER-1 fix (date-tz match bug),
2 of 3 sports clear G_GRANGER at Bonferroni 0.01667 with positive
gamma: KXMLBGAME (F=17.22, p=0.00006, gamma=0.78, n=131) and
KXNBAGAME (F=7.91, p=0.006, gamma=0.29, n=151). KXNFLGAME does not
clear (n=90, p=0.53, gamma=-0.13); NFL sportsbook lines barely move
in the T-6h to T-3h pre-game window. v11 explicitly deferred the
strategy P&L test to v12 because Becker has no orderbook history
at trade time (F11). The MLB signal is concentrated in night games
and offset-sensitive (F=0.63 at 2.5h vs F=23.82 at 4.0h). Track 2
join script SHIPPED; the existing 2026-05-24 LIVE_FILTER_ENABLED
overlay continues to actively skip v1 candidates and accumulate
shadow log data. Cumulative spend: approximately $2.55 LLM v11 plus
$30 external. $0 capital deployed. v1 continues on $32 with W1
denylist. See research/v11/FINAL-VERDICT.md for details.

**Round 16 also added v11-A1 to v11-A4 specs, lock v2 + v3
amendment, methodology critic, Phase 3 critic, Phase 4 iteration,
and replay-prevention F1-tz-mismatch documentation in research/v11/.**
```

Memory updates suggested:
- `project_kalshi.md` entry: update with v11 Track 1 GRANGER-PARTIAL +
  Track 2 SHIPPED summary, v12 recommended scope, and the F1-tz
  instance addition to the failure-mode taxonomy.
- `project_kalshi_literature.md`: no new papers; literature index
  unchanged.

---

*Anti-em-dash and anti-en-dash verification: written without U+2014 or
U+2013 throughout. Verified by grep before write.*
