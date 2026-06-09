# v21 Plan Critique (Plan Critic Report)

**Reviewer:** independent plan-critic agent (adversarial review of
`research/v21/00-methodology-lock.md` v1 draft, pre-data)
**Date:** 2026-06-09
**Verdict:** PROCEED-WITH-REVISIONS on Candidate A (must-fix C1, C2, C3, H1,
H3, H4, M1). KILL-C as an edge bet; downgrade to a NULL-expected zero-build
spot-scan. Operator subsequently directed "Continue executing on A + C. Be
thorough", so C continues via the critic's own recommended cheap path (H5).

All findings below were addressed in the v2 revision of the lock (see the lock's
change log) BEFORE any outcome data was pulled.

---

## CRITICAL

### C1. The lock claims to "reuse" v10a's CI, but actually swaps in a stricter test the cells never passed

`scripts/v10a/becker_combined_side_loco.py` computes a TRADE-LEVEL
normal-approximation CI (`1.96 * sqrt(pooled_var / total_n)`, lines 88-90),
not an event-cluster bootstrap. The +6.55pp Media pedigree rests on ~81k
highly correlated trades treated as independent; the effective sample is the
event count, which is orders of magnitude smaller. The three cells have NEVER
passed the event-cluster CI the lock pre-registers.

**Fix:** state G-A1a honestly as a NEW, STRICTER inference, not a re-test of
an established result. Run the event-cluster bootstrap on the TRAIN window
FIRST; it is the cheapest possible kill. If +6.55pp Media does not survive its
own cluster CI, all of Candidate A collapses for free, today, with no forward
work.

### C2. The "OOS / recency slice" is not OOS

The 2025-09-01 to 2025-11-25 slice OVERLAPS the Round 15b discovery sample
(Round 15b swept the full post-Oct-2024 Becker range, which includes that
slice). Calling it OOS launders in-sample data through an out-of-sample label.

**Fix:** demote the recency slice to an internal CONSISTENCY CHECK (useful for
the compression guard, fact 4). The ONLY real OOS for Candidate A is the
forward shadow. Remove the OOS label everywhere.

### C3. Bonferroni/3 is dishonest given the 168-cell discovery sweep

The three cells are SURVIVORS of a 168-cell Round 15b sweep. Dividing alpha by
3 prices in none of that selection. A correct correction (168 cells, or a
selective-inference procedure) is impractical here.

**Fix:** drop the inferential pretense entirely. Phase 1 is a NON-INFERENTIAL
SCREEN with pre-registered numeric cut-offs; ALL inferential weight moves to
the forward shadow, which is genuinely untouched by selection.

---

## HIGH

### H1. Phase 2 may be un-fundable (fill starvation)

Media mid-band is ~0.6M trades/yr across 138 prefixes; a realistic passive
maker fill rate is 1-5%, not the 15% gate. At 2% the cell may produce single
digit fills in 45 days, making G-A2b (>= 30 fills) unreachable regardless of
edge.

**Fix:** add a POWER PRE-CHECK before committing to the shadow: project
modeled fills over 45 days at a conservative 3% fill assumption from observed
posting opportunities; if projected fills < 30, the cell is dropped as
un-fundable. Add a hard stop: < 10 modeled fills by day 30 kills the cell.

### H2. The fill model has survivorship optimism

Conditioning P&L on modeled fills ignores the bids that never fill because the
book died (no adverse print, no settlement exposure, but also no edge). The
fill-conditional P&L is an UPPER BOUND on strategy P&L.

**Fix:** log the dead-book denominator (posted bids that expire unfilled with
the market closing) and state explicitly that fill-conditional P&L is an upper
bound; the gate applies to it as such.

### H3. The "Other" cell is a junk-drawer category

"Other" is the fallback when no SUBCATEGORY_PATTERNS substring matches
(`prediction-market-analysis/src/analysis/kalshi/util/categories.py`). Its
1,087 prefixes are whatever the classifier could not place; the cell is not a
tradable definition (a live bot cannot subscribe to "whatever fails to match").

**Fix:** drop the Other cell, or replace it with an explicit enumerated prefix
list frozen pre-data. (Resolution: replaced with a frozen top-prefix allowlist
built from STRUCTURAL fields only; see lock v2 section 2.1.)

### H4. The category mapper may not survive contact with the live API

`get_group`/`get_hierarchy` are substring-pattern maps built against the
Becker-era ticker universe. Kalshi has re-branded series since; live tickers
may map differently or not at all, silently changing cell membership between
the screen and the shadow.

**Fix:** validate the mapper against a CURRENT live `/markets` pull; freeze an
explicit per-cell series-prefix ALLOWLIST at lock time, and run both the screen
and the shadow on the allowlist, not on the mapper.

### H5. Candidate C likely reproduces v17's null at full engineering cost

v17 found 0 net-of-fee locks across 2,791 mutually-exclusive groups; ladders
are the same arb family. Building `ladder.py` + tests + a collector plugin
before observing a single violation risks a week of engineering for a
predictable null.

**Fix:** run a one-week ZERO-BUILD spot-scan first: reuse
`dutchbook.parse_market_quote` plus ~20 lines of ordering logic in a
throwaway script against the live API; count raw monotonicity violations and
their gross margins. Only if the spot-scan shows non-zero candidate locks does
the full module + persistence scan get built. (The ladder lock math itself was
VERIFIED correct by this review.)

---

## MEDIUM

### M1. G-A2d's +/- 3pp band is wider than the edges it polices

A +2.2pp cell could come in at -0.8pp forward and still "pass" the no-phantom
gate. **Fix:** replace with an absolute gate: forward cluster-CI lower bound
> 0 AND forward point estimate >= 1pp.

### M2. Reframing: the screen's job is ordering cells by survivable evidence,
not proving an edge. (Subsumed by C3's fix.)

### M3. G-C1c's 30s persistence is too loose for a 2-leg residential execution.
**Fix:** tighten to 60-90s, measured as JOINT both-legs-bindable depth across
consecutive re-snapshots, not single-leg quote survival.

### M4. The C scan never measures naked-leg risk. **Fix:** record how often
one leg fills-able depth vanishes while the other persists (the naked-leg
frequency); pre-register it as a reported diagnostic with a qualitative gate at
the execution-bot design step.

---

## LOW

- **L1:** lock the exact audit numbers (row counts, fetch window) in the doc
  so the schema audit is reproducible. (Already done in v1.)
- **L2:** add an annualized-return floor to G-C1b (a 1-cent margin locked for
  6 months is negative-carry vs the $100 bankroll).
- **L3:** add a fill-starvation kill trigger to Phase 3 (live bot that cannot
  get filled should stand down, not idle forever).

---

## Closing instruction (verbatim intent)

Single most important fix: C1. Run the event-cluster bootstrap on the three
Candidate A cells on the train window FIRST. If the +6.55pp Media edge does
not survive its own cluster CI, the whole of Candidate A collapses for free,
today, with no data pull beyond what is already on disk and no capital.
