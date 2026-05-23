# Archived: EC-1 KXHIGH Weather Maker-Quoting Scripts

These scripts ran the Phase 1.5 and Phase 1.6 out-of-sample
calibration gates for the EC-1 hypothesis (maker-quoting on KXHIGH
daily-high temperature markets). **The hypothesis was killed at the
Phase 1.6 gate on 2026-05-23.** See
[../../../research/phase-1.6-results.md](../../../research/phase-1.6-results.md).

These scripts are preserved as a reference for any future Kalshi work
because they document:
- How to chain `/markets` and `/historical/markets` endpoints to get
  pre-cutoff history (`fetch_kxhigh_markets.py`)
- How to chain `/markets/trades` and `/historical/trades` for a
  specified time window (`fetch_kxhigh_trades.py`)
- How to build a per-market VWAP dataset from market metadata and
  trade tape (`build_dataset.py`)
- How to run the locked walk-forward / LOCO calibration gate
  (`run_gate.py` - this one is general, used by future projects too)
- One-off endpoint probes (`probe_*.py`)

**Do NOT re-run these on KXHIGH without explicit operator
authorization.** The EC-1 hypothesis is dead. The scripts work
correctly; the data they produced just didn't show edge.

The general-purpose modules in `src/kalshi_bot/` are NOT archived
and remain in active use:
- `data/auth.py`, `data/kalshi_client.py`, `data/kxhigh.py`
- `analysis/calibration.py`, `analysis/dataset.py`,
  `analysis/gate.py`, `analysis/metrics.py`,
  `analysis/train_test_split.py`
- `alerts/discord.py`
- `config.py`, `logging.py`
