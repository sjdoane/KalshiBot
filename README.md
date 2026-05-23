# Project Kalshi

A production-quality algorithmic trading bot for Kalshi (CFTC-regulated US
prediction market). Goal: validate a real statistical edge, then trade up
to $100 of real capital autonomously with strict risk controls.

## Status

**Phase 1: Research - COMPLETE** (2026-05-22). Synthesis +
[critic pass](research/critic-report.md) found no validated edge candidate.
One hypothesis (KXHIGH weather maker-quoting) survives if it passes an
out-of-sample calibration gate.

**Phase 1.5: Zerve out-of-sample replication - IN PROGRESS.** Train an
isotonic recalibrator on a held-out partition of historical KXHIGH market
data plus contemporaneous NWS forecasts; score on the rest. Pass criteria
in [research-document.md §8](research/research-document.md). If the gate
fails, the project ends.

| Phase | Description                                       | State        |
|-------|---------------------------------------------------|--------------|
| 1     | Research (API, edges, risk, legal)                | complete     |
| 1.5   | Out-of-sample Zerve gate                          | in progress  |
| 2     | Edge selection and strategy design                | gated        |
| 3     | Architecture and plan                             | gated        |
| 4     | Build in vertical slices (M1-M8)                  | gated        |
| 5     | Go-live checklist                                 | gated        |
| 6     | Live trading and monitoring                       | gated        |

## Hard Constraints

- Host: Windows 11 + WSL2 Ubuntu, RTX 5070 Laptop
- Python 3.12 managed with uv
- **$25 initial live cap (not $50)** per post-critic recommendation;
  absolute ceiling $50; checked as a single constant pre-every-order
- Working kill switch is non-negotiable before live trading
- Two weeks of paper trading before any real capital
- Operator domiciled in Washington state; physically in California most
  of the time (CA Kalshi access is being verified)
- No em-dashes anywhere: code, README, commits, messages

## Quick Start

```powershell
# One-time setup
uv sync                          # creates .venv and installs deps
Copy-Item .env.example .env      # then fill in Kalshi keys when generated

# Run Phase 1.5 analysis (scripts to be written in this phase)
uv run python -m scripts.phase_1_5.fetch_weather_archive
uv run python -m scripts.phase_1_5.fetch_kalshi_markets
uv run python -m scripts.phase_1_5.run_calibration_analysis
```

## Repo Layout

```
Project Kalshi/
  pyproject.toml              # uv-managed Python project
  .python-version             # 3.12
  .env.example                # template; real .env is git-ignored
  README.md                   # this file
  src/kalshi_bot/             # main package
    config.py                 # Settings (capital cap, drawdown thresholds)
    data/                     # Kalshi, NWS, Open-Meteo ingestion (TBD)
    analysis/                 # calibration, train/test split, metrics (TBD)
  scripts/phase_1_5/          # one-shot analysis scripts for the gate
  tests/                      # unit tests
  research/                   # Phase 1 + 1.5 deliverables
    briefs/                   # individual sub-agent briefs
    research-document.md      # synthesized Phase 1 doc (post-critic)
    critic-report.md          # research critic attack pass
    phase-1.5-results.md      # Zerve replication writeup (pending)
```

## Phase 1 Deliverables

- [Synthesized Research Document](research/research-document.md)
- [Research Critic report](research/critic-report.md)
- Individual briefs:
  [API/infra](research/briefs/agent-a-api-infra.md),
  [edges](research/briefs/agent-b-edges.md),
  [risk](research/briefs/agent-c-risk.md),
  [legal/tax](research/briefs/agent-d-legal.md)

## Operating the Bot

Not applicable yet. This section will be filled in before live trading and
will cover: how to start, how to stop, kill switch command, where logs go,
how to read the daily Discord summary, and what to do if something breaks.
