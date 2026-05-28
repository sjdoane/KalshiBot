# v8-A Live Probe Launch Report

**Date:** 2026-05-26
**Author:** v8-A build agent
**Run start:** 2026-05-26 19:48:46 UTC
**Scheduled end:** 2026-05-26 23:48:46 UTC (4.0 hours)
**Background PID:** 66132
**Output parquet:** `data/v8/live_probe_20260526T194846.parquet`
**Runtime log:** `data/v8/live_probe_runtime.log`
**Heartbeat:** `data/v8/heartbeat.txt`

## Launch status

LAUNCHED SUCCESSFULLY. Iteration 1 completed at 2026-05-26 19:49:39 UTC.

The probe was spawned via `subprocess.Popen` with `DETACHED_PROCESS |
CREATE_NEW_PROCESS_GROUP` Windows creation flags so it survives the parent
shell. The runtime log is written to `data/v8/live_probe_runtime.log` (stdout
+ stderr); the per-iteration heartbeat is written to
`data/v8/heartbeat.txt`; the per-iteration parquet snapshot is appended to
`data/v8/live_probe_20260526T194846.parquet`.

Process verification: `Get-Process -Id 66132` confirms python.exe started
2026-05-26 12:48:45 local (Pacific). The launch wrapper (transient PID
29056) exited after spawning the detached probe, which is expected.

## Configuration

| param | value |
|---|---|
| wall-clock cap | 4.0 hours |
| iter cadence | 300 s (5 min) |
| max_horizon_min | 60 min from close |
| inter-contract sleep | 0.10 s |
| target series | KXBTCD |
| python | `.venv-kronos/Scripts/python.exe` (pandas 3.0.3, numpy 2.4.6, scipy 1.17.0) |

Note on venv choice: the main `.venv` is currently broken (a partial uv sync
left pandas-3.0.3.dist-info coexisting with pandas-2.3.3.dist-info and the
`pandas/__init__.py` file is missing). `.venv-kronos` is intact and contains
all required dependencies (pandas, numpy, scipy, requests, structlog,
tenacity, httpx, pyarrow). The smoke test and launched probe both use it.
This venv issue is pre-existing and unrelated to v8-A; the operator may want
to repair `.venv` after v8-A finishes.

## Iter 1 pilot summary

| metric | value |
|---|---|
| iter_idx | 1 |
| iter_timestamp | 2026-05-26 19:48:46 UTC |
| rows written | 188 |
| open KXBTCD total | 318 |
| near-close subset (0, 60 min] | 188 |
| Coinbase BTC-USD spot | $75,878.39 |
| sigma_1m (last 120 min) | 0.000437 |
| naive_p_yes in [0, 1] | 188 / 188 (100%) |
| yes_bid populated | 86 / 188 (46%) |
| yes_ask populated (derived from no_bid parity) | 107 / 188 (57%) |
| both sides populated | 5 / 188 (3%) |
| trade-mid populated (any trade in last hour) | 19 / 188 (10%) |
| mean book_spread (both-quoted subset, n=5) | 0.0100 (1c) |
| mean |signal_p_yes_minus_book_mid| | 0.0103 (1.03c) |
| strong signals at |signal| >= 0.05 | 2 / 188 |
| strong signals at |signal| >= 0.10 | 1 / 188 |
| iter runtime | 53 s |

The two strong-signal rows in iter 1:

| ticker | mins_to_close | strike | spot | naive_p | yes_bid | yes_ask | book_mid | signal | spread |
|---|---|---|---|---|---|---|---|---|---|
| KXBTCD-26MAY2616-T75799.99 | 11.22 | 75799.99 | 75878.39 | 0.7600 | 0.91 | 0.92 | 0.915 | -0.155 | 0.01 |
| KXBTCD-26MAY2616-T75899.99 | 11.22 | 75899.99 | 75878.39 | 0.4229 | 0.51 | 0.52 | 0.515 | -0.092 | 0.01 |

Interpretation: in both cases naive_p < book_mid, which is a "BUY NO"
candidate (book is pricing the YES higher than spot-implied probability).
The KXBTCD-26MAY2616-T75799.99 row shows the book mid at 0.915 (yes-side
overpriced by 15.5c relative to naive_p of 0.76). This is the v7 critic's
"strong signal" regime that was found at 0/188 in the 2026-05-26 19:16-19:24
UTC snapshot. With one strong signal at 19:48:46 UTC, the question 4 hours
of recording aims to answer is whether such signals are: (a) durable across
T-30 / T-15 / T-0 (suggesting MMs are NOT actively repricing); (b) transient
(MMs catch up within 5 min); or (c) pure noise from one-sided book gaps.

## Schema check

All 23 columns from the brief are present in the parquet:

`iter_idx`, `iter_timestamp`, `ticker`, `event_ticker`, `close_time`,
`time_to_close_min`, `strike`, `coinbase_spot`, `sigma_1m`, `naive_p_yes`,
`kalshi_yes_bid`, `kalshi_yes_ask`, `kalshi_yes_bid_size`,
`kalshi_yes_ask_size`, `kalshi_mid_from_book`, `kalshi_mid_from_trades`,
`time_since_last_trade_min`, `signal_p_yes_minus_book_mid`,
`signal_p_yes_minus_trades_mid`, `book_spread`, `total_depth_yes_bid`,
`total_depth_yes_ask`, `sim_take_fill_yes_ask`.

Note on `kalshi_yes_ask`: the Kalshi `/markets/{ticker}/orderbook` endpoint
returns two arrays `yes_dollars` and `no_dollars` sorted ascending. The best
YES bid is the highest `yes_dollars` price (last element); the best YES ask
is derived via parity as `1.00 - best_no_bid` where `best_no_bid` is the
highest `no_dollars` price (last element). This is why `yes_ask` is
populated (57%) more often than `yes_bid` (46%) - for deep-OTM strikes the
YES side has no resting bids but the NO side often does.

## Operator commands

### Check progress

```powershell
# heartbeat
Get-Content "C:\Users\SamJD\OneDrive\Desktop\AI Projects\Project Kalshi\data\v8\heartbeat.txt"

# tail runtime log
Get-Content "C:\Users\SamJD\OneDrive\Desktop\AI Projects\Project Kalshi\data\v8\live_probe_runtime.log" -Tail 40

# confirm process alive
Get-Process -Id 66132 -ErrorAction SilentlyContinue
```

### Stop the script early

```powershell
# graceful (preferred): triggers SIGTERM handler, finishes current iteration
Stop-Process -Id 66132

# hard kill if graceful does not work
Stop-Process -Id 66132 -Force
```

The probe also catches SIGINT (Ctrl-C in foreground; not applicable since
detached) and SIGTERM. On signal, it finishes the current iteration then
exits. The output parquet is always self-consistent because each iteration
rewrites the full file before continuing.

### After completion (expected ~23:48 UTC)

```powershell
# inspect the run
.\.venv-kronos\Scripts\python.exe -c "import pandas as pd; df=pd.read_parquet('data/v8/live_probe_20260526T194846.parquet'); print(df.iter_idx.value_counts().sort_index()); print(df.signal_p_yes_minus_book_mid.abs().describe())"
```

A 4-hour run at 300s cadence will produce ~48 iterations; with 188 rows
per iteration that is ~9,000 snapshots. Disk footprint should be ~1-2 MB.

## Risk and safety

The script is READ-ONLY against Kalshi (`/markets`,
`/markets/{ticker}/orderbook`, `/markets/trades`) and Coinbase public REST.
It NEVER calls `/portfolio/orders`. v1 production bot is untouched. There is
no interaction with `.env`, `data/live_trades/`, or `data/paper_trades/`.

Rate-limit guard: `inter-contract sleep` of 100 ms between orderbook fetches
gives 188 orderbook fetches + 188 trades fetches + 1 markets paginate +
1 Coinbase spot + 1 Coinbase candles = ~378 Kalshi requests per iteration
over ~50 seconds, well within typical Kalshi token-bucket allowances. The
existing `KalshiClient` retries on 429 with exponential backoff.

## Next step after probe finishes

Once the 4-hour run completes, the next analysis pass should:

1. Compute time-series stability: for each contract that appears in
   multiple iterations, does the book mid track naive_p_yes over time, or
   does it stay stuck at stale levels?
2. Stratify by `time_to_close_min` buckets (0-5, 5-15, 15-30, 30-60) and
   compute mean |signal| and strong-signal count per bucket.
3. Compute fraction of T-N snapshots with |signal_p_yes_minus_book_mid|
   >= 0.10 over time; if it stays at < 1% of two-sided-book contracts,
   confirm the v7 critic's Finding 7.1 (MMs actively reprice; +0.208
   Brier is unmonetizable).
4. If strong signals do appear durably, capture full L2 depth at those
   moments (the script already records `total_depth_yes_bid` and
   `total_depth_yes_ask`) to enable a follow-up +2c-take simulation
   against MEASURED asks rather than stale-mid proxies.

That analysis lives in a Phase 2 v8-A analyst pass, not in this build.
