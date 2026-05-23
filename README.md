# Project Kalshi

A retail quant trading project for the Kalshi prediction market
($25-$50 initial bankroll, $100 hard ceiling, California operator).

**Status: Round 2 in progress.** Round 1 (EC-1 KXHIGH weather
maker-quoting) was tested through Phase 1.6 and killed cleanly at
the out-of-sample calibration gate on 2026-05-23. Round 2 is
strategy-selection across all Kalshi categories. Start at
[STRATEGY_BRIEF.md](STRATEGY_BRIEF.md).

## Status

**PROJECT KILLED at Phase 1.6 gate (2026-05-23).** The EC-1 KXHIGH
weather maker-quoting hypothesis is not viable for a $25-$50 retail
account on Kalshi in 2026. The methodology lock-in's "no third bite"
commitment was honored; no live capital was deployed. Engineering
artifacts retained as a reference implementation.

The honest outcome:

| Phase | Description                                       | State                 |
|-------|---------------------------------------------------|-----------------------|
| 1     | Research (API, edges, risk, legal)                | complete              |
| 1.5   | OOS Zerve gate (close-window)                     | failed C1 narrowly    |
| 1.6   | OOS Zerve gate (pre-resolution window)            | **FAILED CLEANLY**    |
| 2     | Edge selection and strategy design                | not reached (killed)  |
| 3+    | Architecture, build, go-live                      | not reached (killed)  |

### Why the gate failed

Phase 1.5 (close-window) showed a misleading 9pp shoulder edge, but
that was an artifact of measuring post-resolution prices on
near-settled markets. Phase 1.6 with a proper pre-resolution window
([open+1h, open+13h]) showed only 1.5pp gross edge and -0.5pp net
edge after maker fees. Both gates failed multiple locked criteria.

The literature predicted this: Bürgi 2026 finds weather has smaller
bias than the cross-category average; Becker 2026 measures a 2.57pp
per-trade maker-taker gap in weather (gross of fees); Le 2026 shows
weather is underconfident at long horizons (the regime we'd actually
trade in), with even smaller bias to exploit. Our empirical OOS gate
confirms all three. See [research/phase-1.6-results.md](research/phase-1.6-results.md).

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

## Deliverables

- [Synthesized Research Document](research/research-document.md) - Phase 1 synthesis with critic pass
- [Research Critic report](research/critic-report.md) - adversarial review
- [Phase 1.5 methodology lock-in](research/phase-1.5-methodology.md) - includes the Phase 1.6 amendment
- [Phase 1.5 results](research/phase-1.5-results.md) - close-window gate (misleading 9pp edge)
- [Phase 1.6 results](research/phase-1.6-results.md) - pre-resolution gate (clean kill)
- Research briefs:
  [API/infra](research/briefs/agent-a-api-infra.md),
  [edges](research/briefs/agent-b-edges.md),
  [risk](research/briefs/agent-c-risk.md),
  [legal/tax (WA)](research/briefs/agent-d-legal.md),
  [legal/tax (CA addendum)](research/briefs/agent-d-legal-ca-addendum.md)
- [Literature corpus](research/literature/INDEX.md) - 7 papers studied with full extractions

## Reusable engineering

What's still in the repo and works:

- `src/kalshi_bot/data/auth.py` - RSA-PSS signing for Kalshi API, 8 unit tests
- `src/kalshi_bot/data/kalshi_client.py` - rate-limit-aware HTTP client with cursor pagination, 6 unit tests
- `src/kalshi_bot/data/kxhigh.py` - KXHIGH event-ticker parser with legacy-format support, 14 unit tests
- `src/kalshi_bot/analysis/` - calibration, train/test splits with anti-leakage purge, metrics including fee math
- `src/kalshi_bot/alerts/discord.py` - tested Discord webhook client
- `scripts/phase_1_5/*` - one-shot data acquisition and analysis pipeline
- 62/62 unit tests pass; ruff clean

If you want to start a related Kalshi project, these are reusable
without modification. See [CLAUDE.md](CLAUDE.md) for guidance.
