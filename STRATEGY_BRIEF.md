# Project Kalshi: Strategy Selection Brief

This document is the formal mission for the current phase of
Project Kalshi. It is the answer to "what is the new context window
trying to accomplish?"

## Mission

**Pick ONE Kalshi trading strategy with a defensible positive net
EV for a $25-$50 retail account, validate it through an
out-of-sample gate, paper-trade it for two weeks, then go live with
strict risk controls.**

This is round two of Project Kalshi. The first attempt (EC-1 KXHIGH
weather maker-quoting) was killed at the Phase 1.6 out-of-sample
gate on 2026-05-23. The methodology was sound and detected the
non-viability; the engineering survives intact.

## Constraints (do not negotiate)

- **Capital cap: $50 absolute, $25 initial.** Enforced in code via
  `src/kalshi_bot/config.py` (`CAPITAL_CAP_USD`).
- **Methodology lock-in.** Pass criteria for any OOS gate are
  decided BEFORE the gate is run. No post-data tuning. If the gate
  fails on a strategy, that strategy ends. No third bite.
- **No em-dashes** anywhere: code, README, commits, messages.
- **Jurisdiction: California.** Operator is a CA resident; WA is
  not in scope.
- **No live capital until the methodology says go.** Two weeks of
  paper trading is non-negotiable. CPA + CA attorney consult is
  required (per methodology) but the operator deferred this until
  scale matters (>$5k bankroll).

## What you are starting with

Read in this order:

1. **[CLAUDE.md](CLAUDE.md)** - orientation; what's been done, what's
   reusable, operating principles.
2. **[research/key-findings.md](research/key-findings.md)** - the
   four facts every strategy must respect plus the
   Phase-1.5-vs-1.6 meta-lesson.
3. **[research/strategy-comparison.md](research/strategy-comparison.md)** -
   the candidate (category, strategy) matrix with three pre-fleshed
   candidates. **Start your strategy selection here.**
4. **[research/literature/INDEX.md](research/literature/INDEX.md)** -
   7-paper literature corpus, full extractions one file per paper.
5. **[research/phase-1.5-methodology.md](research/phase-1.5-methodology.md)** -
   the methodology lock-in pattern you will adapt for your chosen
   strategy. Sections 7 and 9 are non-negotiable rules.
6. **[research/phase-1.6-results.md](research/phase-1.6-results.md)** -
   the example of how a gate is reported with PASS / FAIL detail.
7. **[research/research-document.md](research/research-document.md)** -
   the Phase 1 synthesis if you want the full background context.

## The decision framework

Your strategy selection must answer, in writing, each of:

1. **Which (category, strategy) pair?** Cite the row in
   [strategy-comparison.md](research/strategy-comparison.md). If you
   propose one not in the matrix, justify why the matrix was
   incomplete with explicit literature citations.

2. **Why does it survive fees?** Show the round-trip maker fee in
   the price range you'll trade. Show the gross edge per Becker /
   Bürgi / Le for that category at that horizon. Net should be > 0
   with a buffer for slippage and adverse selection.

3. **Why does it survive the 2024 sign flip?** Confirm the
   mechanism (Maker > Taker, behavioral surplus, calibration
   regime, etc.) is documented in post-October-2024 data, not just
   the full sample.

4. **Why does it survive variance?** Bürgi's 33% per-trade SD on
   the maker-profitable subpopulation is the baseline. Your
   strategy's sizing + drawdown breakers must handle that variance.
   Specifically: at $25 bankroll with N concurrent positions of $1
   each, what's the 95th-percentile drawdown over 100 trades?

5. **What's the OOS gate?** Lock the criteria BEFORE pulling
   any new data. Adapt
   [phase-1.5-methodology.md](research/phase-1.5-methodology.md)
   into a methodology doc for your strategy. Cover: data window,
   train/test split design, pass thresholds, "no third bite"
   commitment.

6. **What does the critic say?** Spawn an adversarial critic
   sub-agent on your locked methodology before running the gate.
   Address every weak assumption it identifies.

## The required process

```
1. READ research/key-findings.md + strategy-comparison.md
2. PROPOSE one strategy with the 6-question framework filled in
3. CRITIC-PASS the proposal via a sub-agent
4. LOCK methodology doc (research/phase-2-methodology.md)
5. CRITIC-PASS the methodology
6. PULL data per the locked plan
7. RUN the OOS gate
8. REPORT results (research/phase-2-results.md)
9. If GATE FAILS: stop. Project ends or operator authorizes pivot.
10. If GATE PASSES:
    a. Design live strategy with risk controls
    b. CRITIC-PASS the strategy design
    c. Two weeks of paper trading on real Kalshi prod data,
       zero capital
    d. COMPARE paper P&L to backtest expectations
    e. If consistent: present go-live readiness report
    f. Operator explicit go-live approval required
    g. Deploy with $25 initial cap
```

## Best practices the new context must follow

### Research grounding

Every claim about Kalshi economics must cite a paper file from
`research/literature/`. Do not assert numbers from memory; pull
the exact figure from the extraction. If you make a claim that
isn't in any of the 7 papers, mark it as a hypothesis to be
empirically tested.

### Review-agent pattern

At three critical decision points, spawn an adversarial sub-agent:

- **Plan critic** (after strategy proposal, before methodology lock).
  Job: identify weak assumptions, find counter-evidence to the
  proposed edge, flag what's not yet known.
- **Methodology critic** (after methodology lock-in, before data
  pull). Job: stress-test the train/test split for leakage,
  challenge the pass criteria, check the purge buffer.
- **Code reviewer** (after each milestone of strategy code, before
  it can produce a decision). Job: silent failures, race
  conditions, off-by-one in P&L math, secrets leakage, deviations
  from the plan.

### Maintain context as you go

When you discover a new fact or change a decision, write it down
in the right place IMMEDIATELY:

- New paper studied: add extraction to `research/literature/`,
  append TLDR to `research/literature/INDEX.md` AND
  `~/.claude/.../memory/project_kalshi_literature.md`.
- New strategy decision: amend
  `research/phase-2-methodology.md` (or whatever the active doc
  is). Don't keep decisions in chat only.
- Phase result: write
  `research/phase-2-results.md` with the full per-split table.
- Project state change: update the memory file
  `~/.claude/.../memory/project_kalshi.md`.

Per the operator's request: "ensure files are set up to update to
pick up with all info whenever I start new context window."

### Methodology discipline

Reread `research/phase-1.5-methodology.md` Section 7 ("What we will
NOT do"):

> We will NOT change the pass criteria after seeing initial results.
> If the numbers look promising but a criterion fails, we report
> the partial result honestly and the gate fails.

This applies to your strategy too. Lock criteria pre-data. No
exceptions.

### Honest assessment over enthusiasm

The first attempt was killed cleanly. That's the discipline working.
The second attempt may also fail; that's fine. The point is to find
a real strategy or honestly conclude there isn't one, not to ship a
strategy because effort was invested.

### What is reusable

- `src/kalshi_bot/data/auth.py` - RSA-PSS signing, tested
- `src/kalshi_bot/data/kalshi_client.py` - rate-limited HTTP client
- `src/kalshi_bot/data/kxhigh.py` - parser (rename / adapt if you
  pick a non-weather category)
- `src/kalshi_bot/analysis/` - calibration, splits, metrics, gate
- `src/kalshi_bot/alerts/discord.py` - Discord webhook (tested)
- `src/kalshi_bot/config.py` - capital cap and drawdown thresholds
- `scripts/test_discord.py` - smoke check for Discord
- `scripts/archive/ec1_kxhigh/run_gate.py` - the gate runner is
  data-agnostic; you can copy it to `scripts/phase_2/` and reuse

## What is not reusable

- `scripts/archive/ec1_kxhigh/fetch_kxhigh_*.py` - KXHIGH-specific.
  Copy the pattern for your category but you'll write a new
  `fetch_<your_category>_*.py`.
- `scripts/archive/ec1_kxhigh/probe_*.py` - one-off explorations
  for EC-1. Adapt the pattern if you need to probe a new endpoint.

## When the new context concludes a phase

The deliverable for each phase is:

1. A methodology doc locked pre-data.
2. A results doc with full per-split tables, criteria pass/fail,
   and PASS / KILL verdict.
3. Updates to memory and CLAUDE.md reflecting new state.
4. A clean commit per phase boundary.

When the project finishes (live trading working, or definitively
killed), update CLAUDE.md to reflect the terminal state for the
next context window.
