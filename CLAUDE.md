# Project Kalshi - Claude Instructions

This file is auto-loaded by Claude Code when working in this project
directory. It gives you the context to pick up where prior sessions
left off.

## TL;DR project status (as of 2026-05-23)

**PROJECT KILLED at Phase 1.6 gate.** EC-1 KXHIGH weather maker-
quoting hypothesis is not viable for a $25-$50 retail account on
Kalshi in 2026. The methodology lock-in's "no third bite"
commitment was honored; no live capital deployed.

Engineering artifacts remain in the repo as reference. Tests still
pass. The Kalshi auth client, dataset builder, gate evaluator,
calibration analysis, and Discord webhook all work and are
re-usable for any future Kalshi project.

## What you need to read first

1. **[research/research-document.md](research/research-document.md)** -
   the synthesized Phase 1 research doc with critic pass and CA
   addendum. The conceptual frame for the whole project.

2. **[research/phase-1.5-methodology.md](research/phase-1.5-methodology.md)** -
   the locked methodology, including the Phase 1.6 amendment with
   the pre-resolution window correction.

3. **[research/phase-1.5-results.md](research/phase-1.5-results.md)** -
   Phase 1.5 results (close window). Misleading 9pp shoulder edge
   was an artifact of post-resolution prices.

4. **[research/phase-1.6-results.md](research/phase-1.6-results.md)** -
   Phase 1.6 results (open window, the actual tradable signal).
   Gate FAILS cleanly. This is the load-bearing outcome.

5. **[research/critic-report.md](research/critic-report.md)** -
   adversarial review of the Phase 1 synthesis. Caught what would
   have been a fatal error.

6. **[research/literature/](research/literature/)** - extractions
   of 7 papers on Kalshi prediction markets. Index in memory at
   `project_kalshi_literature.md`. Cite these (not Zerve) for any
   structural claim about Kalshi economics.

7. **[README.md](README.md)** - public-facing project overview.

## Memory files that will be auto-loaded

Your global memory at
`C:\Users\SamJD\.claude\projects\C--Users-SamJD-OneDrive-Desktop-AI-Projects\memory\`
should give you:
- `user_basics.md` - operator is in CA, USC student, .usc.edu
- `feedback_no_em_dashes.md` - hard ban on em-dashes everywhere
- `feedback_kill_early.md` - operator prefers killing at research
  rather than deploying flawed strategies
- `project_kalshi.md` - this project's current state (KILLED)
- `project_kalshi_literature.md` - one-line summary per paper with
  pointers to full extractions in this repo

## Operating principles for any future Kalshi work

1. **EC-1 is killed.** Do not re-open without explicit operator
   authorization.
2. **If the operator wants to start a new Kalshi project**, the
   reusable assets are:
   - `src/kalshi_bot/` (auth, client, analysis, alerts modules)
   - `tests/` (62 passing tests covering the components)
   - The literature corpus
   - The methodology lock-in pattern (locking criteria pre-data is
     the right discipline)
3. **Don't cite Zerve as evidence of edge.** It's an unvalidated
   community notebook. Cite Burgi, Becker, Le, Bartlett.
4. **No em-dashes anywhere.** Code, README, commits, messages.
5. **Trading window matters massively.** The Phase 1.5 vs 1.6
   contrast showed that the same calibration analysis on different
   windows produces wildly different apparent edges. Future work
   must justify window choice with reference to Le's regime
   structure (weather: overconfident short / underconfident long).
6. **Maker fees, not just taker fees.** Post-April-2025 Kalshi
   charges maker fees too. Burgi's +2.6% maker number is from the
   zero-maker-fee era; subtract ~1pp for current regime.
7. **The 2024 sign flip (Becker)** means pre-October-2024 Kalshi
   data is structurally different from current markets. Use only
   post-flip data for any future modeling.

## Stack

- Windows 11 + WSL2 Ubuntu
- Python 3.12 managed with uv
- `uv.toml` pins `link-mode = "copy"` (OneDrive blocks hardlinks)
- RTX 5070 Laptop GPU (unused by this project; not needed)

## Operator

- California resident (USC, .usc.edu); CA is the operative
  jurisdiction for legal/tax. WA is NOT in scope.
- Kalshi account exists; API READ-only key in `.env`
  (gitignored), PEM at `%LOCALAPPDATA%\KalshiBot\kalshi_prod_read.pem`.
- Discord webhook is configured in `.env`. Tested working.

## How to extend the literature corpus

When a new Kalshi-relevant paper appears:

1. Save the extraction at
   `research/literature/{firstauthor-year-topic}.md`. Match the
   structure of existing files: front matter, TLDR, dataset,
   methodology, findings, implications for Project Kalshi,
   limitations, pin quotes.
2. Append a TLDR entry in
   `~/.claude/projects/.../memory/project_kalshi_literature.md`.
3. Update the count in the index.
4. Commit both files together. Run tests and ruff before commit.

## How to extend the engineering

If the operator wants to revisit Project Kalshi or start a
sister project:
- Don't add new code paths until you've read this CLAUDE.md
  end-to-end and the methodology + results files.
- Reuse `src/kalshi_bot/data/auth.py` (RSA-PSS signing, tested).
- Reuse `src/kalshi_bot/data/kalshi_client.py` (rate-limited HTTP
  with cursor pagination).
- Reuse `src/kalshi_bot/analysis/` (calibration, metrics, splits).
- The phase scripts in `scripts/phase_1_5/` are one-shots; new
  phases get new directories under `scripts/`.

## What is in `.gitignore` (don't accidentally commit)

- `.env` (Kalshi keys, Discord webhook)
- `.venv/` (uv-managed)
- `data/raw/`, `data/processed/`, `data/*.log`, `data/*.parquet`,
  `data/*.txt` (data is reproducible from API; do not bloat the repo)
- `*.pem`, `kalshi_key*` (any private key file)
