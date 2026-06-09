# v21 Methodology Lock (Pre-Data), v2

**Author:** Project Kalshi research workflow
**Date:** 2026-06-09 (v2, post plan-critic revision)
**Status:** REVISED per plan critic (`research/v21/01-plan-critique.md`),
pending methodology critic. Locked BEFORE any outcome data is pulled. The
Becker schema audit below reads column names and structural row counts only
(no trade outcomes); that is legitimate pre-registration work, not peeking.

This document pre-registers the methodology, the data windows, the pass/fail
gates, the F11 schema audit, and the kill criteria for two candidate
SECOND-BOT strategies that this project has not tried:

- **Candidate A:** non-sports mid-bias maker cells (Media midprice,
  Entertainment mid-band, plus a frozen-prefix replacement for the former
  "Other" cell). Flagged in Round 15b
  (`research/v10a/05-becker-edge-discovery.md`) but NEVER deployed.
- **Candidate C:** cross-market cumulative-ladder monotonicity locks. A
  structural axis the v17 dutch-book scan did NOT cover (v17 scanned
  mutually-exclusive groups only). Per the plan critic, C proceeds via a
  ZERO-BUILD spot-scan first; the full module is built only if the spot-scan
  finds non-zero raw violations.

The mission is a SEPARATE second live bot running alongside v1, with its own
strategy module, state file, intent-id prefix, scheduled task, bankroll slice,
and kill triggers. This round does NOT modify or disrupt v1. Most angles null;
that is the expected outcome.

---

## 0. Calibration: what we are NOT assuming

Per the 2026-06-08 P&L reality check (`memory/project_kalshi.md`): v1 is roughly
BREAK-EVEN live despite a ~79% win rate; its per-bet bootstrap CI straddles zero;
MLB is net negative. A clean backtest CI excluding zero is NECESSARY BUT NOT
SUFFICIENT for a live edge. v1/MLB is the standing proof: a maker-excess number
that looks real on historical fills can be break-even-or-worse live (F11 / adverse
selection / payoff asymmetry). Every gate below is designed around that fact.

The four load-bearing facts this design respects (`research/key-findings.md`):
1. Makers > takers structurally. Candidate A is maker-side. Candidate C is a
   risk-free lock (the maker/taker preference does not bind on a true arbitrage,
   but fees do, which is C's primary kill risk).
2. Per-category bias varies ~40x. Candidate A deliberately targets thin
   NON-sports cells where pro MM presence is lowest, accepting the liquidity
   ceiling as the trade-off (and gating on it: see the H1 power pre-check).
3. The 2024 maker sign-flip. ALL Becker analysis uses post-October-2024 data
   only.
4. Bias shrinks yearly. Becker ends ~2025-11-25, now ~6.5 months stale. The
   screen adds an explicit recency consistency slice + a compression guard,
   and the forward shadow is the only evidence that counts (Section 2.6).

Failure modes this design must avoid (documented in CLAUDE.md):
- **F11 (Dataset Schema Phantom):** see the audit in Section 1. Becker has NO
  orderbook bid/ask at trade time. Confirmed below. No A gate may depend on a
  Becker entry price; the forward shadow is the only F11-free validation.
- **F4 (stale-price phantom):** never use `last_price` or the single terminal
  markets snapshot as an execution price.
- **F9 (gate-regime mismatch):** gates are derived for THIS regime (mid-band
  non-sports maker; ladder locks), not copied from a paper measured elsewhere.

**Selection honesty (plan critic C1/C2/C3, binding):**
- The three Round 15b cells were measured with a TRADE-LEVEL
  normal-approximation CI (`becker_combined_side_loco.py` lines 88-90), which
  treats ~81k correlated trades as independent. They have NEVER passed an
  event-cluster CI. Phase 1 applies the cluster bootstrap as a NEW, STRICTER
  test, not a re-confirmation.
- The cells are SURVIVORS of a 168-cell discovery sweep. No per-3 Bonferroni
  can price that selection in. Phase 1 is therefore a NON-INFERENTIAL SCREEN
  with pre-registered numeric cut-offs. All inferential weight sits on the
  forward shadow (Phase 2), which is untouched by the selection.
- The 2025-09-01+ "recency slice" OVERLAPS the Round 15b discovery sample. It
  is NOT out-of-sample and is never labeled OOS in this document. It serves
  only as the recency CONSISTENCY check for the compression guard.

---

## 1. The Becker schema audit (F11 gate, done pre-data)

Inspected `prediction-market-analysis/data/kalshi/{markets,trades}` with
`.venv-kronos` DuckDB. Column names and structural row counts only.

**trades** (7,214 parquet files): `trade_id, ticker, count, yes_price, no_price,
taker_side, created_time, _fetched_at`. NO orderbook. The only price per trade is
the executed print.

**markets** (769 parquet files): `ticker, event_ticker, market_type, title,
yes_sub_title, no_sub_title, status, yes_bid, yes_ask, no_bid, no_ask, last_price,
volume, volume_24h, open_interest, result, created_time, open_time, close_time,
_fetched_at`. It DOES carry bid/ask, BUT:

- **One row per ticker** (7,682,445 rows == 7,682,445 distinct tickers).
- **All fetched in a single ~8-hour window** (`_fetched_at` min 2025-11-23
  18:51, max 2025-11-24 02:40, 2 distinct fetch-dates).
- **95% `finalized`** (7,320,904 of 7,682,445); only 328,865 `active`.

CONCLUSION: the markets bid/ask is a one-time TERMINAL snapshot taken at Becker's
data-pull date, mostly post-settlement. It is useless as an entry-price proxy at
the time of any historical trade. **There is no orderbook-at-trade-time anywhere
in Becker.** F11 is confirmed for candidate A. The implication is baked into the
A design: Phase 1 is a SCREEN on the incumbent maker's realized excess (necessary,
not sufficient); the forward shadow logger (Phase 2) is the real, F11-free test.

For candidate C: no historical orderbook means no backtest is possible at all. C
is forward-only, record-only from day one. The pre-registered scan IS the gate.

---

## 2. Candidate A: non-sports mid-bias maker cells

### 2.1 Hypothesis and pre-registered cells

In NON-sports categories with thin professional-MM presence, a side-agnostic
maker quoting in the mid-price band captures a positive combined-side excess
return after fees, because retail order flow is accommodated by makers and pros
are not thick enough to compete the bias to zero. Round 15b flagged
(combined-side, trade-level CI, full post-Oct-2024 Becker):
- Media maker midprice [0.40, 0.60): +6.55pp net (138 prefixes)
- Other maker [0.60, 0.80): +2.40pp net (1,087 prefixes)
- Entertainment maker [0.40, 0.60): +2.22pp net

Per plan critic H3, the "Other" cell as a category label is DROPPED: "Other" is
the classifier's fallback bucket (whatever fails to match
`SUBCATEGORY_PATTERNS`), not a tradable definition. It is REPLACED by a frozen
explicit prefix allowlist: before any outcome data is read, we enumerate the
series prefixes that the v10a run placed in Other [0.60,0.80), rank them by
STRUCTURAL fields only (trade count in the band; no outcomes, no excess
returns), and freeze the top prefixes covering >= 80% of the cell's trade
volume as `cell3_prefix_allowlist`. The screen and any forward work run on that
frozen list. The same freeze is done for Media and Entertainment (H4): each
cell gets an explicit prefix allowlist locked pre-data, and the live shadow
subscribes to the ALLOWLIST, never to the category mapper.

These three cells were DISCOVERED in Round 15b on the whole sample after a
168-cell sweep. v21 Phase 1 is a stricter SCREEN of exactly these three
pre-registered cells, NOT a fresh discovery sweep. We will NOT scan for a 4th
cell.

### 2.2 "Combined-side maker excess" definition (locked)

Aggregation per `scripts/v10a/becker_combined_side_loco.py` and
`research/v10a/05-becker-edge-discovery.md`; INFERENCE upgraded per critic C1.
A maker fill is the non-taker side of a printed trade. For each trade we compute
the maker's net excess return per $1 notional = (settlement payoff to the maker
side) - (maker entry price) - (Kalshi maker fee,
`ceil(0.0175*P*(1-P)*100)/100` per contract). We aggregate COMBINED across
YES-maker and NO-maker fills, weighting each side by its trade count within the
cell. This is the side-agnostic level (a maker bot cannot choose its fill
side); per-side cells are a base-rate selection artifact and are NOT used.

Settlement comes from the markets table `result` field joined on `ticker`
(definitive 0/1; void/unsettled excluded, never imputed).

CI: `cluster_bootstrap_mean_ci` (`src/kalshi_bot/analysis/bootstrap.py`),
cluster unit = `event_ticker`, n_resamples=5000, seed=42, ci=0.95. This is a
NEW stricter test than Round 15b's trade-level CI (critic C1); surviving it is
the cheapest possible kill check and runs FIRST.

### 2.3 Windows (locked)

- **Train:** 2024-11-01 to 2025-09-01 (post-flip, 10 months).
- **Recency consistency slice (NOT OOS, critic C2):** 2025-09-01 to
  2025-11-25. Overlaps the Round 15b discovery sample; used only for the
  compression guard. The forward shadow is the only OOS.
- Chronological, no shuffle. Purge: trades are point events resolving at their
  market's `close_time`; we additionally require the trade's market
  `close_time` to fall within the same window as the trade (drop trades whose
  market resolves after the window end) so no cross-window settlement leakage.

### 2.4 Pre-registered Phase 1 screen (per cell; NON-INFERENTIAL)

Phase 1 is a SCREEN with pre-registered numeric cut-offs (critic C3). Passing
it proves nothing about a live edge; it only earns a cell the right to a
forward shadow test. A cell SURVIVES if ALL hold:

- **S-A1a (cluster-robust sign):** combined-side net excess > 0 with the
  event-cluster bootstrap 95% CI excluding zero on the TRAIN window. (Run
  FIRST; per critic C1 this is the cheapest kill: the cells have never faced
  event-clustered inference.)
- **S-A1b (compression guard):** recency-slice point estimate >= 50% of the
  train point estimate, and recency-slice point estimate > 0. (Fact 4. The
  slice is in-sample for discovery, so this is a consistency check only.)
- **S-A1c (diversification / anti-F7):** >= 200 distinct events AND >= 30
  distinct allowlist prefixes contributing in the recency slice (no
  single-entity artifact).
- **S-A1d (power pre-check, critic H1):** projected forward fills must make
  Phase 2 fundable. From the recency slice, compute posting opportunities/day
  for the cell (distinct market-days with mid-band quotes and >= 1 trade);
  project modeled fills over 45 days at a CONSERVATIVE 3% fill rate. If
  projected fills < 30, the cell is dropped as un-fundable regardless of edge.

KILL: any cell failing S-A1a/b/c/d is dropped. If ALL cells fail, candidate A
is KILLED at Phase 1, NULL written, no forward work.

### 2.5 Phase 1.5: live allowlist validation (critic H4)

Before the shadow starts: pull current live `/markets` (read-only), map each
frozen allowlist prefix to live series; record coverage (how many prefixes
still exist / have active markets). If < 50% of a surviving cell's allowlist
volume maps to live active series, the cell is dropped as structurally stale
(Kalshi re-brands series; the Becker-era mapper does not bind live). The
surviving allowlists are FROZEN as the shadow's subscription list.

### 2.6 Phase 2: forward shadow logger (the real, F11-free test)

For each surviving cell, run a RECORD-ONLY forward logger (adapted from
`src/kalshi_bot/analysis/lead_lag_shadow.py` + `scripts/v16/shadow_logger.py`;
single-instance lock; writes its own parquet; NEVER places orders) that, on a
fixed cadence, snapshots the live orderbook of allowlist markets in the cell
and records a HYPOTHETICAL resting maker bid plus, on each later snapshot,
whether that bid would have filled and at what settlement outcome.

**Fill model (locked, conservative):** our hypothetical bid rests at the current
best bid on the maker side. A fill is recorded only when a subsequent trade prints
that crosses AT OR THROUGH our resting price on our side, AND we conservatively
assume we are at the BACK of the queue at our price level (we only count the fill
once cumulative taker volume at our price since we posted exceeds the depth that
was ahead of us at post time). Net P&L per fill = settlement payoff - our bid -
maker fee. Every assumption (queue position, partial fills) is logged so the
realized number can be re-derived.

**Upper-bound honesty (critic H2):** the logger also records the DEAD-BOOK
denominator: posted hypothetical bids that expire unfilled at market close.
Fill-conditional P&L ignores those (no loss, but no edge either) and is
therefore an UPPER BOUND on strategy-level P&L. The gates below apply to it
as an upper bound: failing them on the upper bound is decisive; passing them
is still only an upper-bound pass, reported as such to the go/no-go council.

**Pre-registered Phase 2 gates (per surviving cell), measured over 30-60
calendar days:**
- **G-A2a (fill rate):** modeled fill rate >= 15% of posted hypothetical bids.
- **G-A2b (sample):** >= 30 modeled fills. **Hard stop (critic H1):** < 10
  modeled fills by day 30 kills the cell as un-fundable; do not wait to day 60.
- **G-A2c (net edge):** mean net-of-fee P&L per fill > 0 with event/day-cluster
  bootstrap 95% CI excluding zero.
- **G-A2d (absolute edge floor, critic M1):** forward cluster-CI lower bound
  > 0 AND forward point estimate >= +1.0pp net of fees. (Replaces the old
  "+/- 3pp of the screen" band, which was wider than the edges it policed. A
  large negative screen-vs-forward divergence is the F11/adverse-selection
  signature that killed v7-B/v14; with this absolute floor it fails
  automatically.)

PASS all four -> Phase 3 candidate. Otherwise stay in shadow or kill per the
30-60 day verdict. The fill-rate gate is the single most important field (a
backtest edge at 2% fill rate is not a business).

### 2.7 Phase 3: tiny live

Only after Phase 2 passes AND a 3-4 member council + verifier go/no-go AND
operator approval: a ~$5 live slice (a separate bot, own strategy module, own
state file, intent-id prefix distinct from v1's, own scheduled task, own kill
triggers: 20% drawdown, 5-consecutive-loss, edge-compression, and a
FILL-STARVATION trigger per critic L3: < 3 live fills in any rolling 14 days
stands the bot down pending operator review). Re-split the $100-ceiling
bankroll fraction between v1 and the new bot at that point. Forward shadow
continues alongside live as the monitor. The operator initiates the live
restart; this round only stages and recommends.

### 2.8 No third bite

If candidate A kills at Phase 1 OR Phase 2, it ends. No criterion re-tuning, no
new-cell scanning to rescue it. NULL write-up under `research/v21/`.

---

## 3. Candidate C: cumulative-ladder monotonicity locks

### 3.1 The structure

A cumulative ladder is a set of nested threshold markets on the same underlying
quantity X: "X >= k_1", "X >= k_2", ... with k_1 < k_2 < ... (e.g. team season-win
ladders, "BTC >= $X by date D" ladders, range ladders). Probability is monotone:
P(X >= k_i) >= P(X >= k_{i+1}). So YES prices MUST be non-increasing:
p_1 >= p_2 >= ... A violation is an adjacent pair with p_i < p_{i+1}.

**The lock (risk-free, structural; math VERIFIED by the plan critic).** On a
violation: buy "X>=k_i YES" at ask a_i and buy "X>=k_{i+1} NO" at ask
(1 - b_{i+1}) where b_{i+1} is the yes_bid of leg i+1. If X >= k_{i+1}: YES_i
pays $1, NO_{i+1} pays $0 -> $1. If X < k_{i+1}: NO_{i+1} pays $1, and if also
X >= k_i, YES_i pays $1 too (the bracket k_i <= X < k_{i+1} pays $2). Since
k_i < k_{i+1}, every outcome pays AT LEAST $1. Cost = a_i + (1 - b_{i+1}).
When prices violate monotonicity the cost can fall below $1, giving a
guaranteed >= $0 margin plus bracket upside. This is the ladder analog of the
v17 dutch-book underround, on a structural axis v17 did not scan.

This is a TAKER arbitrage (both legs marketable). The maker>taker preference
does not bind on a true lock (no directional exposure), but TAKER FEES (2 legs)
plus the 2-leg spread plus depth are the binding constraint and the primary
kill risk. v17 found mutually-exclusive groups arbed to ~1 (residual 1.3c
gross, below fee+capital cost). Honest prior: LOW (~10-15%); most likely kill
is "violations exist but do not survive fees/depth," a v17 repeat. The plan
critic recommended killing C outright on this prior; the operator directed
continued execution, so C proceeds via the critic's own minimal-cost path
(H5): a zero-build spot-scan gates ALL further engineering.

### 3.2 Why forward-only, record-only

No historical Kalshi orderbook exists for settled markets (confirmed across
rounds; `/markets/{ticker}/orderbook` is empty for settled markets and `?ts=`
is ignored), and Becker's markets snapshot is a single terminal post-settlement
frame (Section 1). So C CANNOT be backtested. The pre-registered forward scan
IS the gate. No capital is ever at risk during the scan.

### 3.3 Phase C0: zero-build spot-scan (critic H5; gates ALL further C work)

ONE WEEK, throwaway script, NO new module, NO collector plugin. Reuse
`dutchbook.parse_market_quote` (`src/kalshi_bot/analysis/dutchbook.py`) plus
~20 lines of ordering logic: pull live open events (read-only API), identify
candidate ladders by parsing ordered numeric thresholds out of
`yes_sub_title`/strike fields within an event (conservative: skip anything
ambiguous), and for each adjacent pair record p_i vs p_{i+1} at the executable
quotes (a_i, b_{i+1}), the gross lock margin, the net margin after 2x taker
fee, and bindable depth. Run the spot-scan ~3x/day for 7 days (manual or loose
scheduled invocations; no infrastructure).

- **G-C0 (build gate):** >= 3 DISTINCT net-of-fee-positive executable locks
  (both legs marketable, depth >= 1) observed across the week. If fewer, C is
  KILLED at C0 with a NULL write-up: "ladder violations do not survive fees/
  depth at observable frequency," at near-zero engineering cost. If passed,
  Phase C1 (the real module + persistence scan) is built.

### 3.4 Phase C1: module + persistence scan (only if G-C0 passes)

`dutchbook.analyze_group` handles mutually-exclusive groups ONLY, not nested
ladders. Phase C1 builds a NEW pure module `src/kalshi_bot/analysis/ladder.py`:
- `group_ladders(markets) -> list[Ladder]`: identify cumulative ladders within
  an event (markets whose `yes_sub_title`/strike parse to an ordered threshold
  on a common quantity). Conservative: only group markets we can confidently
  order; log and skip ambiguous structures.
- `analyze_ladder(legs) -> list[LadderLock]`: for each adjacent pair, detect
  the monotonicity violation, compute the lock cost (a_i + 1 - b_{i+1}), net of
  2x Kalshi taker fee, and the min bindable depth across the two legs.
Pure, network-free, unit-tested (golden cases: clean monotone ladder = 0
locks; constructed violation = 1 lock with correct margin; fee math verified
against `metrics.py`). Code-reviewed per session rules.

The record-only scanner (reusing the shadow-logger harness + lock) snapshots
open ladders on a cadence, runs `analyze_ladder`, logs every detected lock with
cost, net margin, bindable depth, timestamp, and re-snapshots to measure
persistence and naked-leg behavior.

**Pre-registered Phase C1 gates (record-only scan, ~2-3 weeks):**
- **G-C1a (frequency):** >= 20 DISTINCT executable ladder locks observed.
  Executable = both legs marketable at the recorded ask with bindable depth
  >= 1 contract, AND net guaranteed margin (after 2x taker fee) > 0.
- **G-C1b (size + carry):** median net guaranteed margin per executable lock
  >= $0.01 AND median bindable depth >= 1 contract, AND (critic L2) median
  annualized return on locked capital >= 10% (net margin / cost, annualized by
  days-to-latest-leg-close via `dutchbook.annualized_return`; a 1-cent margin
  locked for 6 months is negative-carry vs the bankroll).
- **G-C1c (persistence, critic M3):** median lock survives >= 60 seconds
  measured as JOINT both-legs-bindable depth across consecutive re-snapshots
  (not single-leg quote survival), so a non-co-located retail order can
  realistically execute both legs.
- **Diagnostic (critic M4, reported not gated):** naked-leg frequency: how
  often one leg's bindable depth vanishes while the other persists within a
  lock's lifetime. Reported to the execution-bot design step, where it gates
  the simultaneous-or-cancel design qualitatively.

KILL: fail any of G-C1a/b/c -> candidate C KILLED, NULL written. A true lock
needs no direction gate (risk-free by construction); the gate is purely
frequency + size + carry + executability + persistence.

If C1 passes, the two-leg execution bot (leg-risk handling,
simultaneous-or-cancel logic, intent-id prefix, kill triggers) is designed as a
SEPARATE gated step with its own plan critic and code review before any live
capital. No live C trading is authorized by this document.

### 3.5 No third bite

If C kills at C0 or C1, it ends. NULL write-up.

---

## 4. Shared collector harness (engineering efficiency)

A-Phase 2 (forward maker-fill shadow on non-sports cells) and C-Phase C1
(record-only ladder scan, IF C0 passes) share ONE collector built once: the
`lead_lag_shadow`/`shadow_logger` record-only harness (single-instance lock,
parquet append with recovery sidecars, scheduled snapshot loop, NEVER places
orders, own state file). Two strategy plugins (maker-fill model; ladder scan)
feed the same loop. One engineering build + one code review covers both
forward validations. C0 deliberately does NOT use this harness (zero-build).

---

## 5. Pre-registered gate summary

| Gate | Candidate | Phase | Pass condition | Kill |
|---|---|---|---|---|
| S-A1a | A | Becker screen | Combined-side net excess > 0, event-cluster 95% CI excl 0, TRAIN (new stricter test; runs first) | else drop cell |
| S-A1b | A | Becker screen | Recency-slice estimate >= 50% of train AND > 0 (consistency, NOT OOS) | else drop cell |
| S-A1c | A | Becker screen | >= 200 events AND >= 30 allowlist prefixes in recency slice | else drop cell |
| S-A1d | A | Becker screen | Projected 45-day fills >= 30 at 3% fill assumption | else drop cell |
| (all cells fail S-A1) | A | Becker screen | -- | KILL A, NULL |
| Phase 1.5 | A | Live validation | >= 50% of cell allowlist volume maps to live active series | else drop cell |
| G-A2a | A | Forward shadow | Modeled fill rate >= 15% | else stay/kill |
| G-A2b | A | Forward shadow | >= 30 modeled fills; HARD STOP < 10 by day 30 | else kill cell |
| G-A2c | A | Forward shadow | Mean net P&L/fill > 0, cluster CI excl 0 (upper bound per H2) | else stay/kill |
| G-A2d | A | Forward shadow | Forward CI lower > 0 AND point >= +1.0pp | else kill cell |
| G-A3 | A | Tiny live | All G-A2 pass + council/verifier + operator approval | -- |
| G-C0 | C | Zero-build spot-scan | >= 3 distinct net-of-fee executable locks in 7 days | KILL C, NULL |
| G-C1a | C | Record scan | >= 20 executable locks | KILL C, NULL |
| G-C1b | C | Record scan | Median net margin >= $0.01, depth >= 1, annualized >= 10% | KILL C, NULL |
| G-C1c | C | Record scan | Median JOINT persistence >= 60s | KILL C, NULL |

---

## 6. What we will NOT do (locked)

- NOT change any gate threshold after seeing results.
- NOT scan for a 4th candidate-A cell (pre-registered to the three Round 15b
  cells only; new-cell discovery is a separate pre-registered exercise).
- NOT claim inferential validity for the Phase 1 screen (the cells survived a
  168-cell sweep; the screen is non-inferential by construction).
- NOT label the recency slice OOS (it overlaps the discovery sample).
- NOT use any Becker entry price for candidate A (F11; Section 1).
- NOT use `last_price` or the terminal markets snapshot as an execution price (F4).
- NOT build the ladder module before the zero-build spot-scan passes G-C0.
- NOT trade candidate C live on the strength of this document (record-only scan
  first; execution bot is a separate gated build).
- NOT touch v1: no edits to its strategy module, scheduled task, state, or
  bankroll until a validated second edge earns a re-split, and even then only by
  operator-initiated restart.
- NOT pull outcome data until the methodology critic clears this revision.

---

## 7. Capital, spend, review plan

- **Capital:** $0 at risk through Phase 1 (both candidates), A-Phase 2, and
  C0/C1. First live exposure is a ~$5 A slice only after G-A2 passes + council
  + operator approval, inside the shared $100 ceiling, re-split from v1's
  fraction.
- **Spend:** Phase 1 is local compute (`.venv-kronos` DuckDB) + minimal LLM for
  critics. No external paid data.
- **Reviews (session_rules.md, non-negotiable):** plan critic on the v1 lock
  (DONE; `01-plan-critique.md`); methodology critic on THIS revision, before
  the outcome-data pull; code reviewer after the Becker screen script, after
  the ladder primitive (if G-C0 passes), and after the collector harness;
  post-impl reviewer + green pytest + green mypy + em-dash sweep before any
  live-money code. A 3-4 member council + verifier at the go/no-go to live.

## 8. Change log

- 2026-06-09 v1: Initial draft, pre-data. Becker F11 schema audit completed
  (Section 1) and baked into the A design.
- 2026-06-09 v2: Plan-critic revision (`01-plan-critique.md`). C1: S-A1a is an
  honestly-framed NEW event-cluster test, run first as the cheapest kill. C2:
  recency slice demoted from OOS to consistency check. C3: Phase 1 reframed as
  a non-inferential screen; Bonferroni pretense dropped. H1: S-A1d power
  pre-check + day-30 hard stop added. H2: dead-book denominator + upper-bound
  framing. H3: "Other" cell replaced by a frozen structural prefix allowlist.
  H4: Phase 1.5 live allowlist validation added. H5: C restructured around a
  zero-build spot-scan (G-C0) gating all engineering. M1: G-A2d replaced with
  an absolute floor. M3: persistence tightened to 60s JOINT. M4: naked-leg
  diagnostic. L2: annualized carry floor in G-C1b. L3: fill-starvation
  stand-down in Phase 3. Operator override recorded: critic said KILL-C;
  operator directed continued A + C execution, honored via the C0 path.
