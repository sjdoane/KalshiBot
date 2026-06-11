# v21 Methodology Lock (Pre-Data), v3

**Author:** Project Kalshi research workflow
**Date:** 2026-06-09 (v3, post methodology-critic revision)
**Status:** LOCKED. Both critics complete (plan critic: `01-plan-critique.md`;
methodology critic: `02-methodology-critique.md`, verdict LOCK-WITH-EDITS, all
must-do edits incorporated below). Locked BEFORE any outcome data is pulled.
The Becker schema audit below reads column names and structural row counts only
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
  finds non-zero confirmed violations.

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
   ceiling as the trade-off (and gating on it: see the S-A1d power pre-check).
3. The 2024 maker sign-flip. ALL Becker analysis uses post-October-2024 data
   only.
4. Bias shrinks yearly. Becker ends ~2025-11-25, now ~6.5 months stale. The
   screen adds an explicit recency consistency slice + a compression guard,
   and the forward shadow is the only evidence that counts (Section 2.6).

Failure modes this design must avoid (documented in CLAUDE.md):
- **F11 (Dataset Schema Phantom):** see the audit in Section 1. Becker has NO
  orderbook bid/ask at trade time. Confirmed below. No A gate may depend on a
  Becker entry price OR any other field Becker does not carry (the methodology
  critic caught an F11 recurrence inside the v2 power pre-check; fixed in
  S-A1d). The forward shadow is the only F11-free validation.
- **F4 (stale-price phantom):** never use `last_price` or the single terminal
  markets snapshot as an execution price. For C, never count a violation
  computed across non-simultaneous leg quotes (stale-pair cousin of F4; see
  the confirm-read rule in Section 3.3).
- **F9 (gate-regime mismatch):** gates are derived for THIS regime (mid-band
  non-sports maker; ladder locks), not copied from elsewhere. The methodology
  critic caught an F9 violation inside v2 itself (the 15% fill-rate bar was a
  Round 15b/c hand-me-down drafted for liquid sports/crypto); fixed in G-A2a.

**Selection honesty (plan critic C1/C2/C3, binding):**
- The three Round 15b cells were measured with a TRADE-LEVEL
  normal-approximation CI (`becker_combined_side_loco.py` lines 88-91), which
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
- **95% `finalized`** (7,320,904 of 7,682,445); only 328,865 `active` (which
  carry no usable `result` and are excluded from all outcome work).

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
explicit prefix allowlist. **Freeze rule (locked, methodology critic H-4):**
for EACH cell, the allowlist = the top prefixes by in-band trade count covering
>= 80% of the cell's band trade volume, OR the top 30 prefixes by band trade
count, WHICHEVER SET IS LARGER. Ranking uses STRUCTURAL fields only (prefix,
band, trade count, contract count; no outcomes, no excess returns). Procedure
(methodology critic L-1): a small freeze script loads ONLY those columns,
writes the three allowlist files, and is committed BEFORE the screen script
exists; the commit hash is the freeze proof. The screen and all forward work
run on the frozen allowlists; the live shadow subscribes to the ALLOWLIST,
never to the category mapper (plan critic H4).

These three cells were DISCOVERED in Round 15b on the whole sample after a
168-cell sweep. v21 Phase 1 is a stricter SCREEN of exactly these three
pre-registered cells, NOT a fresh discovery sweep. We will NOT scan for a 4th
cell.

### 2.2 "Combined-side maker excess" definition (locked)

**Pipeline (methodology critic M-3):** the v10a script
`becker_combined_side_loco.py` consumes a prefix-level aggregate (no
event_ticker, no per-trade values) and CANNOT be reused for cluster inference.
The v21 screen builds per-trade observations DIRECTLY from the trades/markets
parquets: maker side = the non-taker side from `taker_side`; settlement from
the markets `result` joined on `ticker` (definitive 0/1; void/unsettled/active
excluded, never imputed); maker entry price = the printed trade price on the
maker side; fee = `ceil(0.0175*P*(1-P)*100)/100` per contract (Kalshi maker
fee; the live fee schedule per series is re-verified at Phase 1.5 per
methodology critic L-2 and the SAME schedule is applied in Phase 2 and 3).
The new screen script gets the session-rules code review BEFORE its output is
read.

Per-trade maker net excess per $1 notional = (settlement payoff to the maker
side) - (maker entry price) - fee. We aggregate COMBINED across YES-maker and
NO-maker fills, weighting each trade equally (trade-count weighting) within
the cell. This is the side-agnostic level (a maker bot cannot choose its fill
side); per-side cells are a base-rate selection artifact and are NOT used.

**Acknowledged upper-bound caveats (methodology critic M-1, reported in the
screen write-up):** (1) incumbent-maker fills are filtered by incumbents'
placement/cancel decisions; a naive best-bid joiner inherits a worse fill mix;
(2) trade-count weighting approximates a 1-lot bot. A CONTRACT-WEIGHTED excess
is computed as a mandatory reported diagnostic next to the gate number.

**CI (exact call, methodology critic L-5):** `cluster_bootstrap_mean_ci`
(`src/kalshi_bot/analysis/bootstrap.py`) with cluster unit = `event_ticker`,
`n_resamples=5000, ci=0.95, rng_seed=42`. This is a NEW stricter test than
Round 15b's trade-level CI (plan critic C1); it runs FIRST as the cheapest
kill. **Sensitivity (methodology critic M-2, REPORT-ONLY, decided now):** a
series-prefix-clustered CI (same call, cluster unit = series prefix) is a
mandatory reported sensitivity; it does NOT gate, but if it includes zero that
fact goes verbatim into the go/no-go council packet (cross-event dependence in
Media/Entertainment: same film across weekly box-office events, award season,
franchises).

### 2.3 Windows (locked)

- **Train:** 2024-11-01 to 2025-09-01 (post-flip, 10 months).
- **Recency consistency slice (NOT OOS, plan critic C2):** 2025-09-01 to
  2025-11-25. Overlaps the Round 15b discovery sample; used only for the
  compression guard. The forward shadow is the only OOS.
- Chronological, no shuffle.
- **Population rule (methodology critic H-1, uniform across BOTH windows):**
  keep a trade only if (a) its market's `close_time` falls inside the same
  window as the trade (no cross-window settlement leakage), AND (b) the
  market's horizon `(close_time - created_time) <= 60 days`. The uniform
  horizon cap makes train and recency like-for-like (otherwise the 2.8-month
  recency slice mechanically excludes long-horizon markets that train admits,
  confounding S-A1b with composition) and matches the population Phase 2 can
  actually observe (Section 2.6). The dropped long-horizon share per cell is
  REPORTED so the estimand narrowing is explicit.

### 2.4 Pre-registered Phase 1 screen (per cell; NON-INFERENTIAL)

Phase 1 is a SCREEN with pre-registered numeric cut-offs (plan critic C3).
Passing it proves nothing about a live edge; it only earns a cell the right to
a forward shadow test. A cell SURVIVES if ALL hold:

- **S-A1a (cluster-robust sign):** combined-side net excess > 0 with the
  event-cluster bootstrap 95% CI excluding zero on the TRAIN window. (Run
  FIRST; per plan critic C1 this is the cheapest kill: the cells have never
  faced event-clustered inference.)
- **S-A1b (compression guard):** recency-slice point estimate >= 50% of the
  train point estimate, and recency-slice point estimate > 0. (Fact 4. The
  slice is in-sample for discovery, so this is a consistency check only; the
  Section 2.3 horizon cap removes the composition confound.)
- **S-A1c (diversification / anti-F7):** >= 200 distinct events AND >= 30
  distinct allowlist prefixes contributing in the recency slice. (The 2.1
  freeze rule guarantees every allowlist has >= 30 prefixes, so this gate is
  satisfiable by construction for every cell.)
- **S-A1d (power pre-check, plan critic H1; definition per methodology critic
  H-3, observable fields only):** posting opportunities = distinct (market,
  day) pairs in the recency slice with >= 1 trade PRINTING inside the cell's
  band. Project modeled fills over 45 days at a 3% fill rate on that
  opportunity count (scaled to per-day). If projected fills < 30, the cell is
  dropped as un-fundable regardless of edge. KNOWN BIAS, stated now: this
  denominator excludes days where a quote sat in-band but nothing traded, so
  it UNDERCOUNTS live posting opportunities and the realized Phase 2 episode
  fill rate will mechanically come in BELOW the 3% planning rate computed on
  this proxy. The 3% planning number and the G-A2a bar are the same number by
  construction (methodology critic C-1).

KILL: any cell failing S-A1a/b/c/d is dropped. If ALL cells fail, candidate A
is KILLED at Phase 1, NULL written, no forward work.

### 2.5 Phase 1.5: live allowlist validation (plan critic H4)

Before the shadow starts: pull current live `/markets` (read-only), map each
frozen allowlist prefix to live series; record coverage (how many prefixes
still exist / have active markets). If < 50% of a surviving cell's allowlist
volume maps to live active series, the cell is dropped as structurally stale
(Kalshi re-brands series; the Becker-era mapper does not bind live). Also
verified here (methodology critic L-2): the live maker-fee schedule for each
allowlist series (Kalshi levies maker fees only on designated series); the
verified schedule is applied identically in Phase 2 P&L and Phase 3 sizing.
The surviving allowlists are FROZEN as the shadow's subscription list.

### 2.6 Phase 2: forward shadow logger (the real, F11-free test)

For each surviving cell, run a RECORD-ONLY forward logger (adapted from
`src/kalshi_bot/analysis/lead_lag_shadow.py` + `scripts/v16/shadow_logger.py`;
single-instance lock; writes its own parquet; NEVER places orders). The
adaptation is a real build (the harness is MLB/odds-API-specific) and gets the
session-rules code review before launch.

**Posting universe (methodology critic H-2):** the shadow posts hypothetical
bids ONLY on allowlist markets with `close_time <= shadow_end - 5 days` (and
horizon <= 60 days, matching Section 2.3). Every posted bid can therefore both
fill AND settle inside the gate window; all four gates share one population.

**Bid lifecycle (locked, methodology critic C-2):**
- Snapshot cadence: every 5 minutes during the collector's run window.
- ONE hypothetical bid per market at a time, size 1 contract.
- A bid-EPISODE opens only when the market's best bid on the maker side lies
  INSIDE the cell's price band (the screened population; no out-of-band
  fills). Spread at post time is logged so pathological-spread fills are
  auditable.
- The episode bid rests at the then-current best bid; queue position = behind
  the full displayed depth at that price (back of queue).
- If the best bid MOVES, the episode is closed unfilled and a new episode
  opens at the new best bid (if still in-band), with queue position reset;
  the re-peg event is logged.
- An episode ends by: FILL, RE-PEG, or MARKET CLOSE (a dead-book row,
  methodology critic/plan critic H2: logged in the denominator).
- FILL rule: cumulative taker volume printing at-or-through our price since
  episode open must be `>= depth_ahead_at_open + 1` (strictly exhausts the
  queue ahead plus our contract; a print that exactly exhausts the queue
  ahead does NOT fill us).
- Net P&L per fill = settlement payoff - our bid - maker fee (live schedule
  per Phase 1.5).
- **Fill rate = filled episodes / total episodes.** Episodes, not snapshots,
  are the denominator; the logging cadence cannot move the gate.

**Upper-bound honesty (plan critic H2):** fill-conditional P&L ignores
dead-book episodes (no loss, no edge) and is an UPPER BOUND on strategy-level
P&L. The gates apply to it as such: failing on the upper bound is decisive;
passing is an upper-bound pass, reported as such to the council.

**Pre-registered Phase 2 gates (per surviving cell). Verdict evaluated ONCE at
day 60 (methodology critic M-4.2); the ONLY earlier action is the day-30 hard
stop. No early passes.**
- **G-A2a (fill rate, derived for THIS regime per methodology critic C-1):**
  episode fill rate >= 3%. Derivation: v1's live maker fill rate in LIQUID
  sports was ~11% pre-fix; thin non-sports books at back-of-queue best-bid
  join must be expected materially lower; 3% is the same number S-A1d plans
  on, so a cell that performs exactly to plan passes. The edge burden sits on
  G-A2c/d, not on fill rate; G-A2a exists to kill books too dead to trade.
- **G-A2b (sample):** >= 30 settled modeled fills by day 60. **Hard stop
  (plan critic H1):** < 10 modeled fills by day 30 kills the cell as
  un-fundable; do not wait to day 60.
- **G-A2c (net edge):** mean net-of-fee P&L per settled fill > 0 with
  cluster bootstrap 95% CI excluding zero; cluster unit = MARKET-DAY
  (methodology critic M-4.1: one event can produce serially correlated fills
  across days; market-day is the locked unit, `rng_seed=42`).
- **G-A2d (absolute edge floor, plan critic M1):** forward cluster-CI lower
  bound > 0 AND forward point estimate >= +1.0pp net of fees.

PASS all four -> Phase 3 candidate. Otherwise kill per the day-60 verdict.

### 2.7 Phase 3: tiny live

Only after Phase 2 passes AND a 3-4 member council + verifier go/no-go AND
operator approval: a ~$5 live slice (a separate bot, own strategy module, own
state file, intent-id prefix distinct from v1's, own scheduled task, own kill
triggers: 20% drawdown, 5-consecutive-loss, edge-compression, and a
FILL-STARVATION trigger per plan critic L3: < 3 live fills in any rolling 14
days stands the bot down pending operator review). Re-split the $100-ceiling
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
ladders, "BTC >= $X by date D" ladders). Probability is monotone:
P(X >= k_i) >= P(X >= k_{i+1}). So YES prices MUST be non-increasing:
p_1 >= p_2 >= ... A violation is an adjacent pair with p_i < p_{i+1}.

**NOT ladders (methodology critic C-3, binding):** range-bracket families
("3,500 to 3,999", "4,000 to 4,499") are mutually exclusive, NOT nested; their
YES prices are legitimately bell-shaped across strikes, and the lock basket on
them is NOT risk-free (X landing in bracket i+1 zeroes both legs). Misreading
a range family as a ladder manufactures phantom "free money", the exact
failure this project has died on twice. Range markets are hard-excluded by the
identification rule in 3.3.

**The lock (risk-free, structural; math VERIFIED by the plan critic).** On a
violation: buy "X>=k_i YES" at ask a_i and buy "X>=k_{i+1} NO" at ask
(1 - b_{i+1}) where b_{i+1} is the yes_bid of leg i+1. If X >= k_{i+1}: YES_i
pays $1, NO_{i+1} pays $0 -> $1. If X < k_{i+1}: NO_{i+1} pays $1, and if also
X >= k_i, YES_i pays $1 too (the bracket k_i <= X < k_{i+1} pays $2). Since
k_i < k_{i+1}, every outcome pays AT LEAST $1. Cost = a_i + (1 - b_{i+1}).
When prices violate monotonicity the cost can fall below $1, giving a
guaranteed >= $0 margin plus bracket upside. This is the ladder analog of the
v17 dutch-book underround, on a structural axis v17 did not scan.

This is a TAKER arbitrage (both legs marketable). TAKER FEES (2 legs) plus the
2-leg spread plus depth are the binding constraint and the primary kill risk.
v17 found mutually-exclusive groups arbed to ~1 (residual 1.3c gross, below
fee+capital cost). Honest prior: LOW (~10-15%); most likely kill is
"violations exist but do not survive fees/depth," a v17 repeat. The plan
critic recommended killing C outright on this prior; the operator directed
continued execution, so C proceeds via the critic's own minimal-cost path
(H5): a zero-build spot-scan gates ALL further engineering.

### 3.2 Why forward-only, record-only

No historical Kalshi orderbook exists for settled markets (confirmed across
rounds; `/markets/{ticker}/orderbook` is empty for settled markets and `?ts=`
is ignored), and Becker's markets snapshot is a single terminal post-settlement
frame (Section 1). So C CANNOT be backtested. The pre-registered forward scan
IS the gate. No capital is ever at risk during the scan.

### 3.3 Phase C0: zero-build spot-scan (plan critic H5; gates ALL further C work)

ONE WEEK, throwaway script, NO new module, NO collector plugin. Reuse
`dutchbook.parse_market_quote` (`src/kalshi_bot/analysis/dutchbook.py`) plus
minimal ordering logic against the live read-only API.

**Ladder identification (locked, methodology critic C-3.1, structured fields
ONLY; v3.1 day-1 amendment):** candidate ladder legs must have `strike_type`
in the whitelist {`greater`, `greater_or_equal`}, no `cap_strike`, ordered by
`floor_strike`, and grouped by (event_ticker, ticker family, strike-token
alpha prefix). The alpha-prefix sub-key is the v3.1 amendment: the day-1
probe found spread families (e.g. KXWNBASPREAD-...-CHI6 vs -IND9) where the
UNDERLIER (which team's margin) is encoded in the strike token; treating
them as one ladder manufactured 14 false "locks" out of 15. 'CHI6' and
'IND9' split into separate ladders; 'T6.75' and 'T7.00' share 'T' and stay
together. This is ticker structure, never subtitle text, and tightens
(never loosens) the detector. Hard-excluded: `between` (range brackets),
`less`/`less_or_equal` (reversed monotonicity; excluded from C0 entirely
rather than handled), custom or functional strike types, anything missing
`floor_strike`. Subtitle text is NEVER the classifier; at most a logged
cross-check.

**Net margin in integer cents (v3.1 day-1 amendment):** the lock condition
"net > 0" is evaluated as net_cents = round(net x 100) >= 1. The probe
"confirmed" a basket on a 2e-18 float residue of an exactly-$0.00 margin;
real money is cent-quantized and a sub-cent "lock" is not a lock.

**G-C0 counting procedure (v3.1):** counts only run_kind=scheduled records
carrying the v3.1 schema marker (`n_families_split_multi_underlier`
present), and each confirmed lock's TWO market titles must pass a manual
nested-threshold check (same underlying quantity) before it counts. The
residual identification risk (two underliers sharing an alpha prefix within
one family) is conservative-auditable, not silently countable.

**Confirm read (locked, methodology critic C-3.2, anti-F4):** a raw violation
seen in a paginated `/markets` sweep is only a CANDIDATE (leg quotes are
non-simultaneous). Before counting toward G-C0, re-read BOTH legs back-to-back
via the orderbook endpoint (which also provides real depth) and require the
net-of-2x-taker-fee violation to persist on the confirm read with bindable
depth >= 1 on both legs. **Distinctness:** one count per (ladder, adjacent
pair) per calendar day.

**Depth fields (methodology critic C-3.3):** before day 1, verify which size
fields the live payload carries (`parse_market_quote` silently returns size
0.0 when `*_ask_size_fp` is absent). Pre-registered: the confirm-read
ORDERBOOK depth is the bindable-depth source of record.

**Schedule (locked, methodology critic M-4.3):** scans at 09:00, 14:00, and
20:00 PT daily for 7 days (21 scans, scheduled invocations; no opportunistic
extra scans).

- **G-C0 (build gate):** >= 3 DISTINCT confirmed net-of-fee-positive
  executable locks across the week. If fewer, C is KILLED at C0 with a NULL
  write-up at near-zero engineering cost. **Honesty note (methodology critic
  L-4):** 21 snapshots cannot bound sub-minute lock frequency; the NULL claim
  is "no ladder locks persistent enough to catch at residential scan cadence
  survive fees/depth," NOT "ladder violations do not exist." That is the
  tradable question. If passed, Phase C1 is built.

### 3.4 Phase C1: module + persistence scan (only if G-C0 passes)

`dutchbook.analyze_group` handles mutually-exclusive groups ONLY, not nested
ladders. Phase C1 builds a NEW pure module `src/kalshi_bot/analysis/ladder.py`:
- `group_ladders(markets) -> list[Ladder]`: identify cumulative ladders within
  an event using the SAME structured-field whitelist as C0 (strike_type +
  floor_strike; never subtitle parsing). Log and skip everything excluded.
- `analyze_ladder(legs) -> list[LadderLock]`: for each adjacent pair, detect
  the monotonicity violation, compute the lock cost (a_i + 1 - b_{i+1}), net of
  2x Kalshi taker fee, and the min bindable depth across the two legs.
Pure, network-free, unit-tested (golden cases: clean monotone ladder = 0
locks; constructed violation = 1 lock with correct margin; a range-bracket
family = 0 ladders identified; fee math verified against `metrics.py`).
Code-reviewed per session rules.

The record-only scanner (reusing the shadow-logger harness + lock) snapshots
open ladders on a cadence, runs `analyze_ladder`, logs every detected lock with
cost, net margin, bindable depth, timestamp. **Burst mode (methodology critic
M-4.4):** on lock detection, re-snapshot BOTH legs every 15-20 seconds for 3
minutes; the default 5-minute cadence cannot measure a 60-second persistence
median (every observation would be censored).

**Pre-registered Phase C1 gates (record-only scan, ~2-3 weeks):**
- **G-C1a (frequency):** >= 20 DISTINCT executable ladder locks observed
  (distinctness per 3.3). Executable = both legs marketable at the recorded
  ask with bindable depth >= 1 contract, AND net guaranteed margin (after 2x
  taker fee) > 0, on a confirm read.
- **G-C1b (size + carry):** median net guaranteed margin per executable lock
  >= $0.01 AND median bindable depth >= 1 contract, AND (plan critic L2)
  median annualized return on locked capital >= 10% (net margin / cost,
  annualized by days-to-latest-leg-close via `dutchbook.annualized_return`;
  None returns from degenerate inputs are excluded from the median and logged
  per methodology critic L-3).
- **G-C1c (persistence, plan critic M3):** median lock survives >= 60 seconds
  measured as JOINT both-legs-bindable depth across burst-mode re-snapshots
  (not single-leg quote survival), so a non-co-located retail order can
  realistically execute both legs.
- **Diagnostic (plan critic M4, reported not gated):** naked-leg frequency:
  how often one leg's bindable depth vanishes while the other persists within
  a lock's lifetime. Reported to the execution-bot design step.

KILL: fail any of G-C1a/b/c -> candidate C KILLED, NULL written.

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
| S-A1b | A | Becker screen | Recency-slice estimate >= 50% of train AND > 0 (consistency, NOT OOS; uniform 60d horizon cap) | else drop cell |
| S-A1c | A | Becker screen | >= 200 events AND >= 30 allowlist prefixes in recency slice | else drop cell |
| S-A1d | A | Becker screen | Projected 45-day fills >= 30 at 3% on in-band trade-print opportunity days | else drop cell |
| (all cells fail S-A1) | A | Becker screen | -- | KILL A, NULL |
| Phase 1.5 | A | Live validation | >= 50% of cell allowlist volume maps to live active series; fee schedule verified | else drop cell |
| G-A2a | A | Forward shadow | Episode fill rate >= 3% (episodes per locked lifecycle; same number as S-A1d plan) | else kill cell |
| G-A2b | A | Forward shadow | >= 30 settled fills by day 60; HARD STOP < 10 by day 30 | else kill cell |
| G-A2c | A | Forward shadow | Mean net P&L/settled fill > 0, market-day-cluster CI excl 0 (upper bound) | else kill cell |
| G-A2d | A | Forward shadow | Forward CI lower > 0 AND point >= +1.0pp | else kill cell |
| G-A3 | A | Tiny live | All G-A2 pass at day-60 verdict + council/verifier + operator approval | -- |
| G-C0 | C | Zero-build spot-scan | >= 3 distinct CONFIRMED net-of-fee executable locks in 21 scheduled scans / 7 days | KILL C, NULL |
| G-C1a | C | Record scan | >= 20 distinct confirmed executable locks | KILL C, NULL |
| G-C1b | C | Record scan | Median net margin >= $0.01, depth >= 1, annualized >= 10% | KILL C, NULL |
| G-C1c | C | Record scan | Median JOINT persistence >= 60s (burst-mode measured) | KILL C, NULL |

---

## 6. What we will NOT do (locked)

- NOT change any gate threshold after seeing results.
- NOT scan for a 4th candidate-A cell (pre-registered to the three Round 15b
  cells only; new-cell discovery is a separate pre-registered exercise).
- NOT claim inferential validity for the Phase 1 screen (the cells survived a
  168-cell sweep; the screen is non-inferential by construction).
- NOT label the recency slice OOS (it overlaps the discovery sample).
- NOT use any Becker entry price for candidate A (F11; Section 1), nor define
  any gate on a field Becker does not carry.
- NOT use `last_price` or the terminal markets snapshot as an execution price
  (F4), nor count a C violation without a synchronized confirm read.
- NOT identify ladders from subtitle text (structured strike fields only).
- NOT build the ladder module before the zero-build spot-scan passes G-C0.
- NOT trade candidate C live on the strength of this document (record-only scan
  first; execution bot is a separate gated build).
- NOT touch v1: no edits to its strategy module, scheduled task, state, or
  bankroll until a validated second edge earns a re-split, and even then only by
  operator-initiated restart.
- The outcome-data pull may begin: both critics are complete and their must-do
  edits are incorporated in this v3.

---

## 7. Capital, spend, review plan

- **Capital:** $0 at risk through Phase 1 (both candidates), A-Phase 2, and
  C0/C1. First live exposure is a ~$5 A slice only after G-A2 passes + council
  + operator approval, inside the shared $100 ceiling, re-split from v1's
  fraction.
- **Spend:** Phase 1 is local compute (`.venv-kronos` DuckDB) + minimal LLM for
  critics. No external paid data.
- **Reviews (session_rules.md, non-negotiable):** plan critic (DONE,
  `01-plan-critique.md`); methodology critic (DONE, `02-methodology-critique.md`,
  LOCK-WITH-EDITS, edits incorporated); code reviewer on the allowlist freeze
  script + Becker screen script BEFORE their outputs are read, on the ladder
  primitive (if G-C0 passes), and on the collector harness; post-impl reviewer
  + green pytest + green mypy + em-dash sweep before any live-money code. A
  3-4 member council + verifier at the go/no-go to live.

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
- 2026-06-09 v3: Methodology-critic revision (`02-methodology-critique.md`,
  LOCK-WITH-EDITS). C-1: G-A2a re-derived for this regime at 3%, aligned with
  S-A1d (the 15% was an F9 hand-me-down). C-2: full bid-lifecycle spec
  (episode-based denominator, in-band posting, re-peg rule, depth_ahead + 1
  fill arithmetic). C-3: ladder identification from structured
  strike_type/floor_strike whitelist; range brackets hard-excluded;
  synchronized confirm read before counting any lock; orderbook depth as
  source of record. H-1: uniform 60-day horizon cap in both Becker windows.
  H-2: shadow posts only on markets settling inside the gate window. H-3:
  S-A1d redefined on observable in-band trade prints with stated bias. H-4:
  allowlist freeze = max(80% volume coverage, top 30 prefixes). M-1:
  contract-weighted diagnostic. M-2: prefix-clustered CI sensitivity,
  report-only. M-3: new trade-level pipeline stated; code review before
  reading output. M-4: G-A2c cluster unit = market-day; single day-60
  verdict; fixed C0 scan schedule + distinctness; C1 burst mode. L-1 freeze
  script procedure, L-2 fee schedule verification, L-3 annualized None
  handling, L-4 C0 NULL honesty note, L-5 exact CI call locked
  (n_resamples=5000, ci=0.95, rng_seed=42). LOCK COMPLETE; data pull
  authorized.
- 2026-06-09 v3.1 (day-1 C0 instrument amendments, BEFORE any scheduled
  gate scan; gate thresholds unchanged; both fixes tighten the detector).
  The pre-registered day-1 probe (run_kind=probe, excluded from G-C0)
  caught two false-positive defects: (1) spread families encode the
  underlier in the strike token, so 14/15 probe "locks" were cross-team
  non-nested baskets; fixed by the strike-token alpha-prefix sub-key.
  (2) a 2e-18 float residue passed "net > 0" on an exactly-zero margin;
  fixed by integer-cent evaluation (net_cents >= 1). G-C0 counting now
  requires the v3.1 schema marker + a manual title check per confirmed
  lock. Re-reviewed (SHIP); re-probe run to validate. Candidate A section
  outcome: NULL at Phase 1 (see 04-candidate-a-null.md); A gates are
  retired, not amended.
- 2026-06-11 v3.2 (coverage amendments after operator wifi outage; gate
  threshold and per-scan procedure UNCHANGED). Of the first 5 scheduled
  slots, 3 were lost to a network outage (the script failed fast with no
  record). Amendments, decided before the gate evaluation: (1) in-slot
  retry: a scan retries transient network failures every 2 minutes for up
  to 30 minutes within its slot, keeping the fixed cadence (no off-slot
  catch-up runs, unchanged from review L-5); a slot that never recovers
  logs an explicit status=failed record for coverage transparency.
  (2) failed slots do not consume the 21-scan budget; the collection
  window EXTENDS until 21 successful scheduled scans accumulate, hard cap
  2026-06-23 (day 14), at which point the verdict is final on however
  many scans ran. Rationale: the budget is 21 data collections, not 21
  calendar slots; extension restores pre-registered power without
  loosening any threshold. Interim observation note: the single completed
  scheduled scan (2026-06-10 20:00 PT) logged 1 confirmed lock
  (KXCPICOREYOY-26SEP T2.7/T2.8, net 2c, depths 6/2, manual title check
  PASSES: same quantity, nested); recorded here for transparency, counted
  only by the final evaluator run.
