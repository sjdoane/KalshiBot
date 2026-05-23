# Project Kalshi - Claude Instructions

This file is auto-loaded by Claude Code when working in this project
directory. It is your orientation document.

## What this project is

A retail Kalshi quant trading project for a $25-$50 starting bankroll
(operator: California resident, USC). The mission is to pick ONE
defensible-positive-EV strategy, validate it out-of-sample, paper-
trade it, and go live with strict risk controls.

## Where this project stands

**Round 1 outcome (2026-05-23):** EC-1 KXHIGH weather maker-quoting
hypothesis was tested and KILLED at the Phase 1.6 out-of-sample
calibration gate. Methodology was sound; weather just has too small
a bias for retail to extract after fees. No live capital was
deployed.

**Round 2 status:** Strategy-selection phase. The current context
window's job is to pick a new (category, strategy) pair, validate
it through the same methodology pattern, and take it through to
live trading. The full research foundation (7 academic / community
papers, Phase 1 sub-agent briefs, critic pass, two completed
empirical gates) is preserved and discoverable.

## The five files to read first, in order

1. **[STRATEGY_BRIEF.md](STRATEGY_BRIEF.md)** - the formal mission
   for this phase. Decision framework, required process, best
   practices.
2. **[research/key-findings.md](research/key-findings.md)** - distilled
   research lessons. The four facts every strategy must respect.
3. **[research/strategy-comparison.md](research/strategy-comparison.md)** -
   the candidate (category, strategy) matrix. **Pick your strategy
   from here, or justify additions.**
4. **[research/literature/INDEX.md](research/literature/INDEX.md)** -
   index of the 7 papers studied with TLDR each. Pull full
   extractions from `research/literature/{paper}.md` as needed.
5. **[research/phase-1.5-methodology.md](research/phase-1.5-methodology.md)** -
   the methodology lock-in pattern. Sections 7 ("what we will NOT
   do") and 9 (kill-on-fail) are non-negotiable rules you will
   inherit.

If you only have time to read one, read STRATEGY_BRIEF.md.

## Operating principles

### Research grounding

Every numerical claim about Kalshi economics must cite a paper file
from `research/literature/`. Do not assert numbers from memory. If
you make a claim that isn't in any of the 7 papers, mark it as a
hypothesis to be empirically tested.

The four load-bearing facts (from research/key-findings.md):

1. **Makers > Takers structurally** (Whelan, confirmed by Bürgi,
   Becker, Bartlett). Default to maker-side strategies.
2. **Per-category bias magnitudes vary by 40x** (Becker: Finance
   0.17pp gap, World Events 7.32pp). Higher-bias categories are
   thinner; the sweet spot is mid-bias, mid-liquidity.
3. **The 2024 sign flip** (Becker): pre-October-2024 takers won,
   makers now win. Use only post-flip data for modeling.
4. **Bias shrinks each year** (Bürgi 2025 ψ half of 2024).
   Discount historical numbers for further compression.

### Methodology discipline (non-negotiable)

- **Lock pass criteria BEFORE pulling any data.** Adapt
  `research/phase-1.5-methodology.md` into a phase-2 methodology
  doc.
- **No post-data criterion tuning.** If the gate fails, report
  honestly. No "but this one criterion almost passed" rationalizing.
- **No third bite.** Per the locked methodology section 7: if a
  strategy fails its gate, the strategy ends. Operator must
  authorize any pivot.
- **Walk-forward and LOCO splits with purge buffers.** Simple
  holdout is insufficient. Anti-leakage matters.
- **Distinguish trading window from measurement window.** Phase
  1.5's 9pp shoulder edge was an artifact of measuring post-
  resolution prices in a window no bot could trade in. Validate
  your window represents trades the bot could realistically place.

### Review agents (spawn at three decision points)

Subagent pattern from Phase 1:

- **Plan critic** after strategy proposal, before methodology lock.
  Identify weak assumptions, find counter-evidence, flag unknowns.
- **Methodology critic** after methodology lock, before data pull.
  Stress-test split design, challenge criteria, check purge buffer.
- **Code reviewer** after each engineering milestone, before
  decisions depend on output. Silent failures, race conditions,
  off-by-one P&L, secrets leakage, deviations from plan.

Use the same approach: spawn via Agent tool with a thorough,
self-contained brief that includes the project context. Bring
findings back into the project docs, not just chat.

### Maintaining context as you work

When you discover a new fact or change a decision, write it down
in the right place IMMEDIATELY:

- **New literature studied:** extraction to `research/literature/`,
  TLDR to `research/literature/INDEX.md` AND
  `~/.claude/.../memory/project_kalshi_literature.md`.
- **Strategy decisions:** update the active methodology doc. Don't
  leave decisions in chat only.
- **Phase results:** write `research/phase-N-results.md`.
- **Project state change:** update
  `~/.claude/.../memory/project_kalshi.md`.

Per operator request: "ensure files are set up to update to pick
up with all info whenever I start new context window."

### Other inherited rules

- **No em-dashes** anywhere. Code, README, commits, messages. Run
  `grep -P '[\x{2014}\x{2013}]'` after any file write to verify
  (matches both em-dash U+2014 and en-dash U+2013).
- **Kill early** rather than ship something broken (operator
  feedback memory `feedback_kill_early.md`).
- **California jurisdiction.** WA is NOT in scope. Operator is
  USC student physically in CA most of the year. Kalshi KYC
  registered with CA address.

## What's reusable

Engineering is mostly category-agnostic and survives the EC-1
kill. 62/62 tests pass, ruff is clean.

- `src/kalshi_bot/data/auth.py` - RSA-PSS signing
- `src/kalshi_bot/data/kalshi_client.py` - rate-limited HTTP
- `src/kalshi_bot/data/kxhigh.py` - KXHIGH ticker parser (template
  for other series parsers)
- `src/kalshi_bot/analysis/calibration.py` - isotonic wrapper
- `src/kalshi_bot/analysis/train_test_split.py` - time-based splits
  with purge + leave-one-X-out
- `src/kalshi_bot/analysis/metrics.py` - ECE, edge, hit rate,
  realized P&L, Kalshi fee formulas (verified)
- `src/kalshi_bot/analysis/gate.py` - the 5-criteria evaluator
  (adapt thresholds per strategy)
- `src/kalshi_bot/analysis/dataset.py` - market+trade join with
  VWAP computation
- `src/kalshi_bot/alerts/discord.py` - tested webhook client
- `src/kalshi_bot/config.py` - capital cap and drawdown constants
- `scripts/test_discord.py` - one-shot webhook smoke test
- `scripts/extract_pdf.py` - pypdf extractor for new papers
- `scripts/archive/ec1_kxhigh/run_gate.py` - the gate runner. Copy
  to `scripts/phase_2/` and adapt window labels.

## What is NOT reusable (archived)

- `scripts/archive/ec1_kxhigh/fetch_kxhigh_*.py` - KXHIGH-specific
  data pulls. Copy the pattern but write a new fetcher for your
  category.
- `scripts/archive/ec1_kxhigh/probe_*.py` - one-off endpoint
  explorations.

These stay in the repo as reference but should not be re-run
without explicit operator authorization.

## Operational facts the operator has confirmed

- Discord webhook works (configured in `.env`, tested in commits
  92fe168 and ddf2c63).
- Kalshi production API key (READ scope only) is in `.env`,
  pointing to a PEM at `%LOCALAPPDATA%\KalshiBot\kalshi_prod_read.pem`.
- Smoke check passes: `uv run python -m scripts.test_discord` and
  `uv run python -m scripts.archive.ec1_kxhigh.check_kalshi` both
  return OK.
- WSL2 clock-skew check is documented but not yet implemented in
  the operator's environment (this is needed before live trading;
  the operator runs Windows + WSL2 + uv).

## Memory files that auto-load

In `C:\Users\SamJD\.claude\projects\C--Users-SamJD-OneDrive-Desktop-AI-Projects\memory\`:

- `MEMORY.md` - global index (loaded every session)
- `user_basics.md` - operator is in CA, .usc.edu
- `feedback_no_em_dashes.md` - the em-dash rule
- `feedback_kill_early.md` - kill-early principle
- `project_kalshi.md` - project state (Round 1 KILLED; Round 2
  active)
- `project_kalshi_literature.md` - 7-paper index with TLDRs

When you start a new context window, these load automatically and
give you the foundation. Project files in this directory are
discovered via the path references in those memory files.

## How a phase concludes

Each strategy attempt produces:

1. **Locked methodology doc** (`research/phase-N-methodology.md`)
2. **Results doc** (`research/phase-N-results.md`) with PASS / KILL
   verdict
3. **Memory and CLAUDE.md updates** reflecting the new state
4. **A clean commit per phase boundary**

When the project finishes (live trading working, or definitively
killed), update this file to reflect the terminal state for the
next context window to pick up cleanly.
