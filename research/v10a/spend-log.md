# V10-A Spend Log

Tracks LLM API and external data spend for V10-A Round 15. Budget: approximately $5 to $10 LLM headroom of $25/round shared with V10-B (other window).

## Cumulative

| Date | Item | Service | Spend USD | Notes |
|---|---|---|---|---|
| 2026-05-27 | Becker dataset download | jbecker.dev R2 (free) | $0.00 | 36 GB compressed; one-time cost is bandwidth, no API spend |
| 2026-05-27 | Becker uv sync (deps) | local | $0.00 | n/a |
| 2026-05-27 | V10A-2 lit scout agent | Anthropic API (orchestrator-injected) | ~$0.50 | 92.7k tokens, 38 tool uses, 5.4 min wall clock |
| 2026-05-27 | V10A methodology critic agent | Anthropic API | ~$0.40 | 129k tokens, 15 tool uses, 4.9 min wall clock; KILL verdict with three KILLERs |
| 2026-05-27 | Smoke tests (FRED, Granger, Gemini) | local + Gemini free tier | ~$0.00 | All three PASS |
| 2026-05-27 | Orchestrator reads + writes | Anthropic API (this session) | approximately $0.60 | CLAUDE.md, v10 prior research, v2 lock draft, FINAL-VERDICT.md |
| **TOTAL V10-A core (round 15a, NULL closed)** | | | **approximately $1.50** | Under $8 cap with $6.50 buffer |
| 2026-05-27 | Becker dataset extraction | local Python zstandard | $0.00 | 46 GB extracted from 36 GB compressed; sentinel written |
| 2026-05-27 | Becker macro inventory run | local duckdb | $0.00 | 7983 Kalshi parquets indexed; 16 post-flip Kim events confirmed (matches critic KILLER-2) |
| 2026-05-27 | Mohanty pivot feasibility agent | Anthropic API | ~$1 budgeted; running | Background; investigates whether Kalshi macro to BTC vol can execute on Kalshi BTC products |
| 2026-05-27 | Becker empirical edge discovery agent | Anthropic API | ~$2 budgeted; running | Background; reproduces Becker maker/taker by category, finds promising sub-cells, gates with bootstrap CI + LOCO |
| **Round 15b/c estimated total** | | | **approximately $5 to $7** | Operator opened budget; staying well under $15 |
| 2026-05-27 | Live universe + spread probes | local + Kalshi API | $0.00 | Confirmed 1c MM spreads on top candidates; KXMLBGAME wide-spread persists |
| 2026-05-27 | v1 validation on Becker | local duckdb | $0.00 | n=2998 events, 5 PERSIST prefixes confirmed train+OOS |
| 2026-05-27 | v1 live state analysis | local | $0.00 | 19 fills, 18 in OTHER prefixes, mean -4.93pp adverse drift |
| 2026-05-27 | Phase A engineering (allowlist + adverse-selection monitor + pre-close cutoff) | local | $0.00 | 17 new tests, 223 total tests pass |
| 2026-05-27 | Phase B OTHER-prefix validation agent | Anthropic API | ~$0.50 | Tested 24 OTHER prefixes; ZERO meet PERSIST gate |
| **Round 15b/c TOTAL spend** | | | **approximately $6 LLM** | Within operator's expanded budget |

## Estimated remaining LLM budget cap for V10-A
Approximately $5 to $10 (assumed V10-B uses $3 to $5 of remaining $8 to $10 round cap).

## Stop-trigger
If approaching $8 LLM spend, stop and report.

## Round 15c overnight extension (2026-05-27)

Budget: $10 to $15 LLM overnight per operator. Stop-trigger raised to $13.

| Date | Item | Service | Spend USD | Notes |
|---|---|---|---|---|
| 2026-05-27 | Round 15c orchestrator (engineering + analysis writes) | Anthropic API | approximately $1.50 | Track 1 wiring + all 5 Track 2 sub-tracks, memory updates, ROUND-15C-FINAL.md |
| 2026-05-27 | Polymarket-Kalshi lead-lag (40k parquet scan) | local DuckDB | $0 | 6 of 7 pairs analyzed; NULL verdict |
| 2026-05-27 | KXBTCD off-money (4.5M trades) | local DuckDB | $0 | NULL verdict (spot-bucketing artifact) |
| 2026-05-27 | Time-of-day analysis on PERSIST | local DuckDB | $0 | NULL verdict (no band-level lift) |
| 2026-05-27 | ITF forward-record probe (background) | local + Kalshi API | $0 | 8-hour collector, output parquets in data/v10a/ |
| 2026-05-27 | Tavily news lead-lag feasibility snapshot | Tavily free tier | $0 | 16 of 1000 monthly calls used; T0+6h follow-up deferred |
| **Round 15c TOTAL** | | | **approximately $1.50** | Well under $13 stop-trigger and $15 nightly budget |
| **Cumulative Round 15 (a+b+c)** | | | **approximately $7.50** | |

