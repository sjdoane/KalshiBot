# Project Kalshi v2 Master Plan

**Date:** 2026-05-23
**Status:** Research phase, multi-agent autonomous execution
**Author:** Claude (orchestrator)
**Operator authorization:** "Send an adequate amount of agents to distribute work for each task. Be thorough and deliberate. Plan before taking action, document research findings, have another prevent critique decisions and the code to optimize for the best code, build and test as many of the phases as you can without input from me."

## Why v2

The live bot (Strategy B, favorite-longshot YES-maker) is collecting real data on $32 capital. Documented edge is +1 to +3pp realized per the literature. Operator wants to research whether a richer model can do meaningfully better.

Two parallel research tracks:

1. **Sports prediction ML model**: train on rich free public data (MLB Stats, NBA Stats, nfl-data-py, 538 archives, sports-reference). Predict outcome probability per market. Trade when predicted probability diverges from Kalshi price by more than the structural bias alone. Target: +3 to +8pp net per trade if the model has real signal.

2. **Cross-platform arb scanner**: Polymarket and Kalshi list many of the same events at different prices. Build a scanner that identifies arb opportunities. Target: occasional risk-free spreads minus fees.

## What this is NOT

- Not a replacement for the live bot. v1 keeps running. v2 is research-mode only until validated.
- Not a request to deploy live capital. All v2 work is paper / backtest / simulation only until operator explicitly authorizes.
- Not modifying any live v1 code or state. v2 lives in `src/kalshi_bot_v2/`, `scripts/v2/`, `tests/v2/`, `research/v2/`, `data/v2/`.
- Not changing the `.env` or any shared config. Reads existing Kalshi READ-scope auth.

## Scope of operator-authorized autonomous work

The operator authorized: "Build and test as many of the phases as you can without input from me. Stop only when user input is needed."

What I CAN do autonomously:
- Read/write under `research/v2/`, `src/kalshi_bot_v2/`, `scripts/v2/`, `tests/v2/`, `data/v2/`.
- Run scripts that hit free public APIs (ESPN, MLB Stats, NBA Stats, Polymarket public REST, etc.).
- Run scripts that hit Kalshi READ-scope endpoints (the existing key works).
- Train models, run backtests, write tests.
- Spawn subagents for parallel research.

What I MUST stop and ask for:
- Setting up a Polymarket wallet (requires operator's USDC + Polygon wallet).
- Spending money on paid data sources or tier upgrades.
- Deploying any v2 strategy to live capital.
- Modifying `.env` or shared config.

## Phases and agent assignments

Wave 1 (parallel, agents in foreground):
- **Agent A: Data sources** (Task 26). Catalog free + cheap data sources, validate availability, document at `research/v2/01-data-sources.md`.
- **Agent B: Cross-platform arb** (Task 27). Polymarket API research, settlement-divergence analysis, document at `research/v2/02-polymarket-arb-research.md`.

Wave 2 (parallel, after Wave 1):
- **Agent C: Build joined dataset** (Task 28). Use Agent A findings to pull and join Kalshi historical sports markets with the best free stats source. Output `data/v2/joined_sports_dataset.parquet` + `research/v2/03-dataset-build.md`.
- **Agent D: Arb scanner prototype** (Task 29). Use Agent B findings to build a paper-only Kalshi-vs-Polymarket scanner. Output `scripts/v2/arb_scan.py` + `research/v2/04-arb-prototype.md`.

Wave 3 (after Wave 2):
- **Agent E: Baseline model + backtest** (Task 30). Train gradient-boosted model, time-series CV, gate-style backtest. Output `src/kalshi_bot_v2/` code + `research/v2/05-model-results.md`.

Wave 4:
- **Agent F: Adversarial critic** (Task 31). Review master plan, dataset, model, arb scanner. Match Round 4 critic style. Output `research/v2/06-critic.md`.

Wave 5:
- **Orchestrator synthesis** (Task 32). Read all outputs + critic. Decide which paths to pursue. Identify operator decision points. Output `research/v2/07-decisions.md`.

## Success criteria for the ML model

To replace or augment v1, v2 model must clear the same 5-criteria gate as Strategy B Round 4:

- C1: holdout mean realized P&L > 0
- C2: holdout bootstrap 95% CI lower > 0
- C3: holdout hit rate > 55%
- C4: holdout eligible n >= 15
- C5: 5-fold pooled mean > 0

PLUS one v2-specific criterion:

- C6: v2 model's holdout P&L mean exceeds v1 heuristic's holdout P&L mean by at least +2pp net. Otherwise v2 adds variance without gain and we keep v1.

## Success criteria for the cross-platform arb

To merit further work, the arb scanner must demonstrate:

- A1: At least 5 historical Kalshi-Polymarket event pairs identifiable from public data.
- A2: At least 1 historical instance of price divergence > 5 cents (after fees on both sides).
- A3: Operationally tractable: identification of matched events does not require subjective human judgment per case.

If A3 fails (e.g., we cannot reliably match events programmatically), arb gets archived as "needs more research, not actionable now."

## Conventions

- No em-dashes in any file (project rule). Light enforcement; will run a final sweep.
- All numerical claims cite either a research file or a dataset row.
- Time-series validation only; never random splits (regime drift matters).
- Document failures as honestly as successes.
- If a path proves unworkable, escalate to operator before pivoting; do not silently shift scope.

## Decision log (orchestrator writes this as it goes)

Empty initially. Will accumulate orchestrator decisions and rationale across the run.

- 2026-05-23 evening: project initialized, master plan written, Wave 1 agents spawned in parallel.
