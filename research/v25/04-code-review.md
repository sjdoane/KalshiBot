# v25 Code Review (review-before-results)

Reviewer scope: verify scripts/v25/{gas_model.py, backtest.py, prelock_audits.py,
pull_aaa_history.py, pull_kalshi_trades.py} and src/kalshi_bot/analysis/bootstrap.py
against research/v25/02-methodology-lock.md (v3, sections 2-9). Full backtest NOT run
(no settlement-conditioned quantity computed). Synthetic arithmetic checks and
outcome-blind schema scans were run with .venv python; details inline.

Verdict: SAFE-TO-RUN AFTER FIXES. C1 is a hard blocker; H1-H3 must be fixed or
explicitly dispositioned before the locking commit. The core as-of machinery, fee and
P&L arithmetic, fire logic, and bootstrap wiring are faithful to the lock (verified
list at the bottom).

## CRITICAL

### C1. AAA daily series is incomplete; running now silently destroys the study
- File: data/v25/aaa_daily.json (guards missing in scripts/v25/prelock_audits.py
  main() at line 158 and scripts/v25/backtest.py main() at line 127).
- Measured: 184 dates spanning 2024-08-31 to 2025-04-14, with 38 interior gap runs
  (43 missing days). The market universe runs to 2026-06-30 and the binding window is
  [2025-01-01, 2026-06-30].
- Consequence: every trade after 2025-04-14 hits the zero-staleness gate
  (gas_model.py line 350) and silently cannot fire. Audit 0b would compute the LOCKED
  E8 threshold decision, projected fire counts, and the H2 feasibility decision on a
  fraction of the data; the backtest would emit a fabricated UNDERPOWERED-NULL. Audit
  0a would likewise test only pre-2025-04 markets.
- Fix: finish the Wayback pull (it is visibly mid-run), then add a hard assertion in
  BOTH prelock_audits.main() and backtest.main(): min(aaa) <= 2024-10-01, max(aaa) >=
  2026-06-30, and coverage >= some sane floor (e.g. 90 percent of days in range);
  abort with a loud message otherwise. Do not rely on the stale counter alone.

## HIGH

### H1. trades.jsonl contains 21,231 duplicate prints (2.9 percent), 619 of 850 tickers
- File: data/v25/trades.jsonl; root cause scripts/v25/pull_kalshi_trades.py lines
  98-109.
- Measured: 21,231 exact duplicate lines. Duplication is partial per ticker (e.g.
  KXAAAGASM-25APR30-3.15 has 702 dup lines of 6766), which means the
  historical/live endpoint date split assumed in the docstring (before/after
  2026-05-01) is FALSE: April 2025 tickers are duplicated, so both endpoints return
  overlapping trades and the per-ticker dedup key (trade_id, else a tuple missing
  taker_side) fails across endpoints (trade_id absent or differing between them).
- Consequence: fire selection and P&L are unaffected (duplicates are identical
  prints; one position per market per ET day). But audit 0b's H2 feasibility print
  counts and the divergence-distribution weights, which feed LOCKED decisions, are
  inflated ~3 percent, unevenly by ticker; funnel counts are inflated too.
- Fix: before any audit runs, dedupe the file on the full tuple (ticker,
  created_time, yes_price_dollars, count_fp, taker_side). Note the residual risk that
  two genuinely distinct trades share all five fields (sub-second timestamps make
  this rare); the conservative direction for 0b is to dedupe. For future pulls, write
  trade_id into the jsonl and dedupe on it.

### H2. H2 verdict path omits the 7a/7b regime guards required by the lock
- File: scripts/v25/backtest.py lines 168-181.
- Lock sections 6 and 8: H2 "inherits regime guard 7a and the E11 lattice"; "H2 gate
  (if kept): ...; LOCO; guards 7a/7b."
- Consequence: the code can label H2 "PASS" when the month-block or shock-window
  guard would demote it to FRAGILE-PASS or SHOCK-WINDOW PASS. Those verdict classes
  route differently (stage-1 read only), so this can upgrade an H2 outcome.
- Fix: apply ci_of(h2_rows, key="month") and the ex-shock filter exactly as in
  gates_h1(), and extend the H2 verdict lattice accordingly.

### H3. H2 keep/drop decision is neither recorded nor enforced
- Files: scripts/v25/prelock_audits.py lines 123-127 (decision json has only the
  threshold), scripts/v25/backtest.py line 169 (H2 runs unconditionally).
- Lock 0b (E7): if the feasibility rule fails, H2 is DROPPED at the locking commit
  and the ledger records ONE hypothesis. Computing and printing a settlement-
  conditioned H2 verdict for a dropped hypothesis fabricates output for an
  unregistered stratum and invites a post-data upgrade, which section 9 forbids.
- Fix: write "h2_keep": true/false into audit_0b_decision.json at lock time (the
  keep/drop call is made against the floor 30 fires / 8 clusters per E7); backtest
  reads it and either skips H2 or tags all H2 output "NON-REGISTERED, informational".

## MEDIUM

### M1. Ten settled in-window markets silently dropped (floor_strike is None)
- File: scripts/v25/gas_model.py lines 332-334; data: markets_all.json.
- Measured: 10 markets (4 weekly 2025-01/02, 6 monthly 25JAN31) use the old ticker
  format with the strike only in the ticker suffix (e.g. KXAAAGASW-25FEB10-US-3.098)
  and have strike_type=None, floor_strike=None. They are skipped with NO funnel
  counter, so the drop is invisible. Lock section 1 says all strikes in-window.
- Fix: either parse the strike from the ticker suffix for these 10, or add an
  explicit excluded-markets counter plus a line in the verdict doc naming the 10.
  Audit 0a skips them the same way; same disposition applies there.

### M2. E4 fallback activation rule is not wired
- File: scripts/v25/gas_model.py (Model(fallback=True) exists, line 140) but nothing
  measures the share of trade dates where the primary is degenerate under the clamp,
  and neither prelock_audits.py nor backtest.py can trigger the fallback.
- Lock section 3: fallback runs ONLY if the primary is degenerate on more than 20
  percent of trade dates; all its output labeled FALLBACK.
- Fix: count distinct evaluable trade dates where path() returned None due to the
  clamp (split the current n["fit"] counter into clamp vs insufficient-rows) and
  report the ratio; if > 20 percent, rerun with fallback=True and label everything.

### M3. path() fills dR with 0.0 when R(t0-1) is missing
- File: scripts/v25/gas_model.py lines 208-209.
- E2 bans fills anywhere; valid_rows requires R(s-1) for a regression row, but the
  firing path quietly substitutes dR=0 on a gap day. This is an implicit fill in the
  point forecast on exactly the staleness-adjacent days the lock is paranoid about.
- Fix: return None (NO FIRE) when r_m1 is None. This is the reading consistent with
  zero-staleness; if the team prefers dR=0, it must be written into the lock BEFORE
  the locking commit, not discovered after.

### M4. E7 unexecutable-print counting duty unimplemented
- File: scripts/v25/gas_model.py lines 336-340.
- Lock section 6: H2 prints outside the feasibility band are "counted UNEXECUTABLE,
  never scored". The code never scores them (correct) but also never counts them, so
  the reporting duty cannot be met.
- Fix: add funnel counter n["h2_unexec"] incremented when mode=="h2" and the print is
  outside both bands (before the continue).

### M5. Trade puller resume can re-append tickers (second duplication channel)
- File: scripts/v25/pull_kalshi_trades.py lines 90-126 (.done checkpoint every 25
  markets, file opened in append mode).
- A crash between checkpoints re-fetches and re-appends up to 24 tickers' full trade
  sets on resume. Combined with H1 this is why 2.9 percent of the file is duplicated.
- Fix: update .done per ticker (cheap json write), or make iter_trades()/the H1
  dedupe pass the canonical entry point for all consumers.

### M6. Markets merge prefers the possibly-stale scratchpad drain object
- File: scripts/v25/pull_kalshi_trades.py lines 66-83.
- The historical drain object is loaded first and the live settled endpoint only
  setdefault()s. A market that was unsettled at drain time keeps the drain copy
  (result missing) and is then dropped by the settled filter even though the live
  endpoint has its result. Systematic drop of markets settling between drain and
  pull.
- Fix: let the live settled object win (or merge result/close_time onto the drain
  object). Then re-verify the 851 count.

### M7. Threshold-alt sensitivity is not a true 0.12 run when the binding threshold is 0.08
- File: scripts/v25/backtest.py lines 154-157.
- Filtering the 0.08 fire set by |div| >= 0.12 is not the same as running
  evaluate_fires(threshold=0.12): first-qualifying-print selection differs (a print
  that qualifies at 0.08 but not 0.12 fires and dedups the whole market-day, hiding a
  later print that would have qualified at 0.12). Non-binding stratum, but the lock
  names it, so it should be computed correctly.
- Fix: always re-run evaluate_fires at the alternate threshold (the else branch
  already does exactly this).

### M8. Memory footprint of the trade sort
- File: scripts/v25/gas_model.py line 329.
- sorted(iter_trades()) materializes ~734k dicts (roughly 0.5-1 GB) and backtest.py
  does this 5+ times sequentially (H1, control, possible alt, H2, d3). Each list is
  freed between calls so peak is one copy; workable on a 16 GB box but tight.
- Fix (optional): parse once into a list of tuples of only the needed fields, sort
  once, and pass it into evaluate_fires.

## LOW

- L1. load_data(lag) ignores its lag argument (gas_model.py line 281); the d3
  sensitivity gets its lag solely from Model(lag=3) (backtest.py line 164), which is
  correct, but the dead parameter at the call site load_data(3) invites a future bug.
  Remove the parameter or plumb it through.
- L2. created_time sub-second formats vary (27/26/25/24/23 chars, all Z-suffixed;
  measured). Lexicographic sort can misorder within a single second (".12Z" sorts
  after ".1234Z"). Verified on a 737-trade sample that second-level string order
  matches parsed order; t0 keying and dedup are date-level, so no material effect.
- L3. Empty binding fire set prints UNDERPOWERED-NULL (backtest.py line 95) instead
  of the lock section 9 named "market-matches-model NULL". Naming duty for the
  verdict doc.
- L4. Two lock-named non-binding sensitivities are absent from backtest.py:
  DGASUSGULF / DCOILWTICO regressor sensitivities and the subsampled-error
  sensitivity (lock section 6). Either implement or state "not run" explicitly in the
  verdict doc; silence would look like post-data pruning.
- L5. One market (KXAAAGASW-25APR21-3.184) has a mid-day close_time
  2025-04-21T13:56:16.96835Z (early determination). All [:10]/[:7] slicing handles
  it; same-day trades get h=0 and are excluded by the h>=1 gate. No action.
- L6. The settlement key is hardcoded as the close-date-D print (h = D - t0,
  gas_model.py lines 357-358). This matches the lock's stated assumption, but there
  is no code switch if audit 0a were to find key D-1; the lock's kill-on-ambiguity
  covers this, so just confirm 0a = D before running.
- L7. pull_aaa_history resume keys done days by AS-OF date but filters the todo list
  by SNAPSHOT UTC date (lines 64-65): an early-day-X snapshot carrying as-of X-1 is
  skipped forever once as-of X exists. With 43 interior gap days currently missing,
  some may be recoverable only from early-next-day snapshots the resume now skips.
  Also, "later dates win" on duplicate as-of keys is nondeterministic under the
  thread pool (harmless only because the page value is same-day constant).
- L8. GasData/Model caches: _err_cache eviction to 2 entries is safe because t0 is
  non-decreasing under the created_time sort (verified reasoning: the hour>=9 / [0,3)
  keying is monotone in ET time); across evaluate_fires calls the cache just cold-
  starts. _fit_cache/_path_cache are keyed by t0 within a single (data, lag) Model
  instance, and the d3 run uses a separate instance, so no cross-lag contamination.

## Verified clean (checked, not just read)

- taker_fee: ceil(7 p (1-p)) cents with the 1e-12 guard is EXACT on the entire cent
  grid including +1c/+3c/+5c haircut costs (synthetic sweep, zero mismatches);
  ceil(1.75)=2c at p=0.50; p=0.30 -> 2c; the guard can never round down because
  7k(100-k)/10000 is never an integer for k in 1..99. Fee is computed on p_exec
  (post-haircut cost), matching the lock's worst-case wording.
- P&L identity win - p_exec - fee; BUY NO cost 1 - p_print + haircut; side/result
  compared on the Kalshi result field only. Band-edge closure holds: H1 max cost
  0.95 (0.92 print + 3c), H2 max cost 0.985 both sides, so the unexecutable
  assertion in pnl_rows is unreachable on legitimate fires.
- As-of discipline: valid_rows takes rows s with s+1 <= t0 and R(t0) is known at
  trade time by construction (the 09:00 ET keying plus the r(t0) staleness gate), so
  no leak; w_asof implements obs date <= d - 5 inclusive (bisect_right verified
  synthetically on the boundary); margin(s) looks back only; errors_at collects
  pairs with u+h <= t0 only, and model-error paths are walk-forward fits at u.
- ET keying: zoneinfo conversion verified on both DST transition days; 08:59:59 ET
  excluded, 09:00:00 fires; ambiguity window is exactly [03:00, 09:00); t0 mapping
  d / d-1 per the lock.
- Fire logic: threshold applied as >= (abs(div) < thr rejects); bands inclusive on
  both ends; one position per market per ET calendar date of the TRADE, first
  qualifying print; h = (UTC close date - t0).days in [1, 35]; H2 requires both
  P_model and P_control past the 0.995/0.005 floor with 200 errors in both
  distributions.
- Stability clamp: the Jacobian [[1-th, rho], [-th, rho]] is the correct per-regime
  companion matrix for dR' = a + th (Weq - R) + rho dR, R' = R + dR'; checked for
  both th_up and th_dn; degenerate -> path None -> NO FIRE; forecast cap 3x the max
  in-window 35-day move on the 35-day point forecast.
- Error distribution: errors stored as err/sqrt(h_source), used via need =
  (K - point)/sqrt(h_trade), which is the lock's normalize-then-rescale, and
  p_above's interpolated CDF with 0.5/n clamps is monotone (synthetic sweep).
  Control error set is a superset of the model error set (control needs no path), so
  the shared min-40 gate binds only through the model side.
- Control run: signal_control fires on P_control divergence with every other rule
  identical (same gates, same haircut, same fee); gate 3 vacuous-satisfaction and
  power-floor logic in gates_h1 match lock section 8.
- Bootstrap: cluster_bootstrap_mean_ci resamples whole clusters, pooled mean,
  percentile CI; called with 10,000 resamples, fixed seed 25, ISO-week-UTC cluster
  key (isocalendar handles year boundaries) and calendar-month key from
  close_time[:7]; LOCO drops the best cluster by summed pnl then recomputes the CI;
  ci_of guards every empty-set path (no ValueError, no None subscript); attrition
  guarded when rows empty; json serialization uses plain dicts (default=str unused
  in practice).
- Verdict lattice ordering in gates_h1 matches lock sections 8-9 (power -> CI ->
  control -> LOCO/MARGINAL -> month/FRAGILE -> shock/SHOCK-WINDOW -> PASS).
- Firewalls: gas_model.py never reads the result field; prelock 0a reduces result to
  booleans and rates only; 0b is outcome-blind (prints, model, bands only).
- FRED file: DGASNYH 869 obs 2023-01-03..2026-06-29, zero non-numeric values;
  weekend/holiday carry falls out of the bisect design.

Em-dash audit: clean (verified after write).
