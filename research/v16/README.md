# v16 Lead-Lag Shadow Study: Operator Runbook

This is the end-to-end guide for the v16 effort: measure, F11-free, whether
Kalshi sports prices lag the sportsbook and whether that lag is tradeable at
EXECUTABLE prices. It exists because the prior v14 bot lost money (-27.6%) by
paying the sharp line as a taker, capturing none of the lag (see
`00-DIAGNOSIS-AND-COUNCIL.md`). v16 answers the open question properly before
risking another dollar.

Read `00-DIAGNOSIS-AND-COUNCIL.md` (why) and `01-methodology-lock.md` (the
locked gates) first. This file is the how.

## The pipeline

```
  shadow_logger.py            evaluate_gates.py           passive_fill_probe.py
  (record-only, runs nightly) (read-only, run anytime)    (LIVE, triple-gated)
  entries.parquet      ->     Gate A (lag exists?)   ->   only if Gate A passes:
  snapshots.parquet          Gate B (harvestable?)        tiny 1-contract maker
  (t5/t30/close + tape)      + season verdict             fills, real money
```

Nothing here places an order except `passive_fill_probe.py`, and that is
inert until Gate A passes a full MLB season AND you create a marker file by
hand. Everything else is record-only / read-only and safe alongside live v14.

## 1. Collect data (run all season)

Launch the logger. It loops every 5 minutes during MLB-night active hours
(18:00 to 06:00 UTC), captures the executable Kalshi book vs the sportsbook at
each fire (and near-miss), and re-snapshots at fire+5m, +30m, and close.

```powershell
cd "C:\Users\SamJD\OneDrive\Desktop\AI Projects\Project Kalshi"
uv run python scripts/v16/shadow_logger.py
```

(If you prefer an explicit interpreter, use the one v1 runs on:
`C:\Users\SamJD\.venvs\pit-backtest\Scripts\python.exe scripts\v16\shadow_logger.py`.
The project `.venv` pandas is currently broken and is not needed for this.)

- Output: `data/v16/shadow/entries.parquet`, `snapshots.parquet`,
  `events.jsonl`, `logger_state.json`.
- Stop it cleanly: create `data/v16/shadow/STOP`.
- It is single-instance locked and crash-safe (persisted schedule, no-clobber
  parquet recovery sidecars, auditable `missed`/`late`/`book_empty` statuses).
- Optional: schedule it via Task Scheduler the same way the bots are scheduled
  so it survives reboots.

## 2. Evaluate progress (run anytime)

```powershell
uv run python scripts/v16/evaluate_gates.py
```

It loads the parquet, fetches each fire's Kalshi settlement (cached to
`settlements.json`), and prints Gate A, Gate B, and the verdict, also written
to `data/v16/shadow/gate_report.json`. It will say `UNDERPOWERED` until roughly
120 independent nights are collected; that is expected and not a failure.

## 3. The gates and the verdict

- Gate A (lag exists): per fire, closing-line value = executable exit (yes_bid
  at close) minus executable entry (yes_ask at T0). Passes when the
  night-cluster bootstrap CI lower bound is above zero and the week-cluster CI
  does not oppose it.
- Gate B (harvestable): over fires where Kalshi was lagging cheap (yes_ask at or
  below the sportsbook level, with depth), settlement P&L booked at the stale
  ask, net of the Kalshi taker fee. Passes when its night-cluster CI excludes
  zero.

Verdict codes:

| Code | Meaning | Action |
|---|---|---|
| UNDERPOWERED | fewer than ~120 nights | keep collecting |
| KILL_NO_LAG | full season, Gate A CI upper <= 0 | thesis DEAD, no rebuild, stop |
| CONTINUE_ONE_SEASON | sign-correct but CI straddles zero | one more season |
| LAG_NOT_HARVESTABLE | Gate A passes, Gate B fails | lag real but uncapturable; kill harvestable thesis |
| HARVESTABLE_CONFIRMED | both pass | proceed to step 4 |

This is the pre-registered kill criterion. Do not tune thresholds after seeing
the data; that is the discipline that has kept this project honest across 21
rounds.

## 4. Tiny live confirmation (ONLY if HARVESTABLE_CONFIRMED)

A passing log is necessary but not sufficient: a real order moves the thin
book and may not fill at the logged price. So before any scale-up, place tiny
1-contract passive orders and observe real fills. This is triple-gated:

```powershell
# After the verdict is HARVESTABLE_CONFIRMED, create the marker BY HAND:
New-Item -ItemType File "data\v16\GATE_A_PASSED"
# Then, and only then, the live probe will place orders:
uv run python scripts/v16/passive_fill_probe.py --live ^
    --i-understand-this-places-real-orders --max-orders 5
# Later, reconcile fills/settlements and cancel stale probe orders:
uv run python scripts/v16/passive_fill_probe.py --reconcile
```

Default (no flags) is a DRY RUN that places nothing. The probe uses its own
order tag (prefix `16`) and state file, fully isolated from v1 and v14.

## Honest expectations

At the $100 cap the dollar prize is small either way. The product of this study
is a validated, executable edge (or a clean kill) that could justify a larger
future deployment, not near-term income. If Gate A never clears zero, the
correct outcome is to stop, and that is a win for the kill-early discipline.

## Code map

- `src/kalshi_bot/analysis/lead_lag_shadow.py` - pure logger core (fire
  detection, orderbook parse, snapshot scheduling, trade-tape summary).
- `scripts/v16/shadow_logger.py` - the record-only collection loop.
- `src/kalshi_bot/analysis/lead_lag_gates.py` + `analysis/bootstrap.py`
  (`cluster_bootstrap_mean_ci`) - the gate statistics.
- `scripts/v16/evaluate_gates.py` - the evaluator.
- `scripts/v16/passive_fill_probe.py` - the gated live confirmation.
- Tests: `tests/test_lead_lag_shadow.py`, `tests/test_lead_lag_gates.py`.

---

*Em-dash and en-dash audit: verified clean after write.*
