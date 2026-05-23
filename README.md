# Project Kalshi

A production-quality algorithmic trading bot for Kalshi (CFTC-regulated US
prediction market). Goal: identify a real statistical edge, validate it via
paper trading, then trade up to $100 of real capital autonomously with strict
risk controls.

## Status

**Phase 1: Research.** No production code yet. The make-or-break of this
project is whether a genuine edge exists for a $100 retail account on Kalshi
in 2026. If research says no, the project gets killed here.

| Phase | Description                                       | State        |
|-------|---------------------------------------------------|--------------|
| 1     | Research (API, edges, risk, legal)                | in progress  |
| 2     | Edge selection and strategy design                | pending      |
| 3     | Architecture and plan                             | pending      |
| 4     | Build in vertical slices (M1-M8)                  | pending      |
| 5     | Go-live checklist                                 | pending      |
| 6     | Live trading and monitoring                       | pending      |

## Hard Constraints

- Host: Windows 11 + WSL2 Ubuntu, RTX 5070 Laptop
- Python managed with uv
- $100 maximum capital at risk, code-enforced, starting at $50
- Working kill switch is non-negotiable before live trading
- Paper trading for at least two weeks before any real capital
- Operator is in Washington state, USA
- No em-dashes in code, README, commits, or messages

## Repo Layout (Phase 1)

```
Project Kalshi/
  README.md
  research/
    briefs/                  # one file per research sub-agent
    research-document.md     # synthesized Phase 1 output (pending)
```

Later phases will add `src/`, `tests/`, `data/`, `scripts/`, etc.

## Operating the Bot

Not applicable yet. This section will be filled in before live trading and
will cover: how to start, how to stop, kill switch command, where logs go,
how to read the daily Discord summary, and what to do if something breaks.
