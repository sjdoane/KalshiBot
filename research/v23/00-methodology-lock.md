# v23 Methodology Lock (Pre-Data, Pre-Registration)

**Author:** Project Kalshi research workflow
**Date:** 2026-06-28
**Status:** LOCKED. Written BEFORE any outcome backtesting. The Becker
inspection below reads schema, ticker structure, and event-cluster COUNTS
only (no P&L, no win rate, no edge statistic computed). Per the operator
decision of 2026-06-28: v1 STOPPED (no live capital at risk), research-mode
until an HONEST net-of-fee edge is found, then deploy.

This document pre-registers, from first principles plus the distilled prior
docs and the literature, the exact universe, the chronological train/OOS
split with purge buffer, the firable pass criteria, the F11 staged path, and
the kill rule for two operator-chosen directions:

- **DIRECTION A:** NO-underdog MODERATE-band maker arm on tennis singles
  (combined-side), excluding the toxic ATP-NO cell.
- **DIRECTION B:** crypto daily/range maker (KXBTCD / KXETHD / KXBTC range)
  plus the diversified "Other" category maker, both combined-side.

The project has 9 NULLs plus 1 confirmed phantom, all traceable to either
skipping pre-registration or to F11 (the Becker dataset has no orderbook at
trade time). This lock exists so v23 cannot repeat either failure.

---

## 0. Calibration: what this lock refuses to assume

The single standing proof that a clean backtest CI excluding zero is
NECESSARY BUT NOT SUFFICIENT for a live edge is v1 itself: v1 ran a ~75-76%
live win rate that is almost exactly its price-implied breakeven (~76%), with
a per-bet bootstrap CI straddling zero; the -$58.59 was a sizing artifact, not
an edge (2026-06-20 deep diagnosis, reproduced twice). Every gate below is
designed around that fact: a Becker pass earns a FORWARD SHADOW test, never
live capital.

The four load-bearing facts respected (research/key-findings.md):

1. **Makers > takers structurally** (Whelan, Burgi, Becker, Bartlett). Both
   directions are maker-side.
2. **Per-category bias varies ~40x** (Becker). Direction A targets the
   moderate-degree tennis sweet spot; Direction B targets crypto (the broadest
   PERSIST signal in the prior Becker sweep) and the diversified Other tail.
3. **The 2024 maker sign-flip** (Becker). ALL Becker analysis uses
   post-October-2024 data only.
4. **Bias shrinks yearly** (Burgi: psi 2025 = half of 2024). Becker ends
   2025-11-25, now ~7 months stale. Every direction carries an explicit
   recency / decay guard, and the forward shadow is the only evidence that
   counts.

Failure modes this lock must avoid (from CLAUDE.md and this project's history):

- **F11 (Dataset Schema Phantom).** Confirmed again below (Section 1): the
  Becker trades table has NO orderbook bid/ask at trade time, only the executed
  print. A Becker screen shows an edge EXISTED in realized fills; it CANNOT
  prove a NEW resting maker bid would CAPTURE it. No gate may depend on a field
  Becker does not carry at the timestamp the strategy needs it. The forward
  shadow is the only F11-free validation. Becker is therefore a NECESSARY SCREEN,
  not a sufficient go-live.
- **F4 (stale-price phantom).** Never use `last_price` or the single terminal
  `markets` snapshot as an execution price. The maker entry price is the printed
  trade price on the maker side at `created_time`.
- **F9 (gate-regime mismatch).** Gates are derived for THESE regimes (moderate
  tennis NO-maker; crypto and Other combined-side maker), never copied from a
  benchmark measured in a different regime.
- **Side-selection base-rate artifact** (v10a Phase 2, binding). A per-side cell
  ("NO wins X% at price p") is a backward-looking selection statistic, because a
  maker bot cannot choose which side it gets filled on. ALL inference here is
  COMBINED-SIDE (YES-maker and NO-maker pooled within a cell), the only level a
  forward bot can act on. The one exception is Direction A, which is
  intrinsically a single-side arm (NO-maker on underdog-framed markets); its
  "combined-side" requirement is handled in Section 2.2 by pooling across the
  ATP and WTA legs and across the two framings of each match so the estimand is
  not a one-tournament base-rate artifact.

**Selection honesty (binding).** The cells named below are SURVIVORS of prior
discovery sweeps (v10a 13-prefix sweep; v10a 168-cell category sweep; v18
sweet-spot strata). No Bonferroni correction can price in that prior selection.
The Becker screen is therefore a NON-INFERENTIAL pre-registered SCREEN with
fixed numeric cut-offs that earns a survivor the right to a forward shadow.
All inferential weight sits on the forward shadow, which is untouched by the
historical selection.

---

## 1. Becker schema + layout audit (F11 gate, done pre-data)

Inspected `prediction-market-analysis/data/kalshi/{trades,markets}` with the
project `.venv` DuckDB (import duckdb; NOT pandas, which is broken in that venv).
Column names, ticker structure, and event COUNTS only.

**trades** (7,214 parquet files): `trade_id, ticker, count, yes_price,
no_price, taker_side, created_time, _fetched_at`. NO orderbook. The only price
per trade is the executed print. `created_time` is the trade timestamp (tz-aware,
America/Los_Angeles in the stored values). `taker_side` is 'yes' or 'no'; the
MAKER side is the opposite.

**markets** (769 parquet files): `ticker, event_ticker, market_type, title,
yes_sub_title, no_sub_title, status, yes_bid, yes_ask, no_bid, no_ask,
last_price, volume, volume_24h, open_interest, result, created_time, open_time,
close_time, _fetched_at`. Carries bid/ask BUT it is a one-time TERMINAL snapshot
(one row per ticker, all `_fetched_at` in a single ~8h window 2025-11-23/24,
~95% finalized). Per the v21 audit, the markets bid/ask is useless as an
entry-price-at-trade-time proxy. There is NO orderbook-at-trade-time anywhere in
Becker. F11 is confirmed.

**Settlement** comes from `markets.result` joined on `ticker`: values are
'yes', 'no', or '' (empty = unsettled/active). Empty-result rows are EXCLUDED
from all outcome work and never imputed.

**Event-cluster key (locked).** The independent unit is `event_ticker`. For a
tennis match the two market legs (one per player) share an event_ticker
(e.g. KXATPMATCH-25NOV16ALCSIN groups ...-SIN and ...-ALC). For a crypto daily
the entire strike ladder shares an event_ticker (e.g. KXBTCD-25NOV1717 groups
all -T##### strikes). `event_ticker` is therefore the correct level to break the
multi-strike / two-leg dependence that a trade-level CI would understate. The
trades table has no event_ticker column; it is derived as
`regexp_replace(ticker, '-[^-]*$', '')` (strip the final dash segment), verified
to reproduce the markets `event_ticker` on tennis and crypto samples.

**Inference primitive (locked, exact callable).**
`src/kalshi_bot/analysis/bootstrap.py::cluster_bootstrap_mean_ci(values,
cluster_ids, n_resamples=5000, ci=0.95, rng_seed=42)`. Resamples whole
event-clusters with replacement, pools, takes the mean; returns
`(sample_mean, lower, upper, n_clusters)`. Cluster unit = `event_ticker`.
This is the binding inference; a trade-level CI is NEVER the gate.

**Fee (locked).** Kalshi maker fee = `ceil(1.75 * P * (1-P))` cents per
contract, where P is the maker entry price in dollars (so the integer-cent
ceiling is over `1.75 * P * (1-P)` with P in [0,1] giving cents directly:
implemented as `ceil(0.0175 * P * (1-P) * 100) / 100` dollars). Subtracted on
EVERY modeled fill. One fill per held-to-settlement maker position; settlement
is not a trade, so there is NO exit fee (the v1 fee fix of 2026-06-13 confirmed
the round-trip-`2.0` model was conceptually wrong for a held maker).

**Fee-schedule reality (load-bearing, v22 fee_table.json).** Maker fees did NOT
exist before 2025-05-13; they were flat $0.0025/contract on 29 designated
series from then, and the quadratic `ceil_175` schedule applies only from
2025-07-08 on a GROWING list of series. KXATPMATCH / KXWTAMATCH = ZERO maker fee
for the whole window (since 2025-07-13 designation they remained zero per the
table). To stay conservative and to avoid a fee-underestimate phantom, the
binding gate is evaluated under BOTH fee modes and must pass under BOTH:
(a) the ZERO-fee mode where the dated table says the series was fee-free, and
(b) the WORST-CASE `ceil_175` mode applied to every fill regardless of date.
A cell that passes only under the favorable fee mode is reported as fee-fragile
and does NOT fire. The dated table at `research/v22/fee_table.json` is the
source of record for mode (a).

---

## 2. DIRECTION A: NO-underdog moderate-band tennis maker (combined-side)

### 2.1 Hypothesis and exact universe

Thesis (three independent 2026 papers plus this project's own data): takers
systematically overbet YES (the favorite), so the structural maker edge is being
the NO maker who accommodates them. v1 only ever placed YES maker bids on
favorites at yes_px >= 0.70; it left the mirror (NO maker on the underdog
framing) entirely on the table. v18 measured the symmetric NO-underdog edge and
found it REAL on the MODERATE band [0.70, 0.86) of no_px (cross-sport, OOS CI
excluding zero), while heavy underdogs (no_px 0.86-0.95) were weak. v22
SEPARATELY found that the DEEP longshot tail (3-8c, i.e. no_px ~0.92-0.97 on the
other side) INVERTED to -1.94pp net and must not be revisited on Becker-era
data. These are DIFFERENT cells. Direction A is the MODERATE band only; the deep
tail is hard-excluded by the price filter.

**Maker-NO definition (Becker proxy).** A NO maker is the counterparty to a
YES taker: `taker_side = 'yes'`. The maker's NO entry price is `no_price / 100`
dollars. Per-fill net P&L per $1 notional =
`(result == 'no' ? 1 - no_px : -no_px) - maker_fee`.

**Price band (locked).** `no_price` in [70, 86) cents (the moderate underdog
sweet spot; matches v18 LOW band). Trades with `no_price` in [86, 95] (heavy
underdog) and the deep tail are EXCLUDED. Trades with `no_price < 70` are not
NO-underdog markets and are excluded.

**Series universe (locked).** Tennis singles-match series ONLY:
`KXATPMATCH-%` and `KXWTAMATCH-%`. Rationale from the Becker layout: these are
the two flat singles-match series with consistent, dense coverage in the post-
flip window; they are the exact series v1's live NO arm would trade. The
tournament-specific tennis prefixes (KXATPMIA, KXATPMAD, KXWTAMAD, KXATPIWO,
etc.) are EXCLUDED from the binding universe (they are intermittent once-a-year
tournaments that confound recency and would let tournament composition drive the
estimate); they may appear only as a report-only robustness extension, never in
the gate.

**Toxic-cell exclusion (locked, the operator's explicit carve-out).** The
ATP-NO cell is excluded from the COMBINED Direction A estimate as a gate input.
Concretely: Direction A's binding gate is computed on the WTA-NO moderate band
alone (KXWTAMATCH, taker_side='yes', no_px in [70,86)), and the ATP-NO moderate
band is reported as a SEPARATE diagnostic, never pooled into the gate number.
Rationale: v1's live experience flagged ATP-NO as the toxic cell; v18 showed WTA
full-NO was marginal but WTA LOW-NO was clean, and ATP-NO LOW was the larger
historical number but is the cell the live arm distrusts. Pooling ATP+WTA would
let the historically-larger-but-distrusted ATP number carry a combined pass.
The gate fires on WTA-NO moderate band; ATP-NO is a watch-only comparator.

### 2.2 "Combined-side" handling for a single-side arm

Direction A is intrinsically one-sided (NO-maker on underdog-framed markets), so
the v10a side-selection artifact (which arises from conditioning on which side a
maker happened to be filled on) is handled differently here. The estimand is the
NO-maker net excess in the moderate band, pooled across BOTH legs of every
match (each match contributes the underdog-framed leg's NO fills) and across all
matches in the window. Because the cluster unit is `event_ticker` (the match),
no single match and no single tournament can dominate via repeated correlated
fills. The reported number is the event-clustered mean over matches, which is
the quantity a side-agnostic underdog-NO bot would experience. A per-tournament
or per-player concentration diagnostic (largest-event-ticker-family share of
absolute P&L) is reported alongside; it does not gate but goes verbatim into the
go/no-go packet.

### 2.3 Chronological split + purge buffer (locked)

Becker layout finding (load-bearing, overrides the v10a-era "Nov 2024 to Sep
2025" tennis window): the flat `KXATPMATCH` / `KXWTAMATCH` series exist in Becker
only from 2025-06-18 to 2025-11-16. There is no Nov-2024-to-mid-2025 tennis flat-
series data; the earlier v10a tennis counts came from a different aggregation. So
the split is set from the REAL span:

- **Train:** 2025-06-18 to 2025-09-08 (assigned by the event's FIRST trade
  `created_time`).
- **Purge buffer:** 2025-09-08 to 2025-09-15 (7 calendar days). All events whose
  first trade falls inside the buffer are DROPPED from both windows. The buffer
  exceeds the maximum tennis-market horizon (a singles match resolves within
  days of listing), so no train event's settlement can leak into the OOS window.
- **OOS:** 2025-09-15 to 2025-12-01 (the data ends 2025-11-16, so the upper bound
  is a harmless cap).
- Assignment is by event first-trade time, chronological, no shuffle. An event
  is wholly in one window; a market's settlement is inside the same window as its
  first trade given the tennis horizon, so no cross-window settlement leakage.

**Powering (event-cluster counts, measured pre-data, no outcomes).** On the
flat tennis series, combined ATP+WTA: train (to 2025-09-08) = 1,469 events; OOS
(2025-09-15+) = 896 events. WTA alone (the gate universe) is roughly half of
each (the monthly split is ~50/50 ATP/WTA), giving on the order of ~600-700 WTA
train events and ~350-450 WTA OOS events before the no_px [70,86) and settlement
filters. That is comfortably above the minimum-n floor (Section 2.4) even after
band filtering removes the majority of fills. ATP-NO (diagnostic) is similarly
powered. These counts are the layout justification for the split; no P&L was
computed.

### 2.4 Firable pass criteria (Becker screen, NON-INFERENTIAL; per the gate
universe = WTA-NO moderate band)

Direction A SURVIVES the Becker screen and earns a forward shadow only if ALL of:

- **A-1 (powered minimum-n):** >= 60 distinct settled events in BOTH the train
  AND the OOS window after the no_px [70,86) and definitive-settlement filters.
  (60 is the project's standing "hard kill at n=60" floor for the NO arm; below
  it the cell is underpowered and dropped, not rationalized.)
- **A-2 (train sign, event-cluster):** combined WTA-NO moderate-band net excess
  > 0 with the `cluster_bootstrap_mean_ci` 95% CI LOWER BOUND > 0 on TRAIN.
- **A-3 (OOS sign, event-cluster):** same, CI LOWER BOUND > 0 on OOS. (The
  binding requirement: the cluster-bootstrap CI EXCLUDES ZERO on BOTH windows.)
- **A-4 (net-of-fee under both fee modes):** A-2 and A-3 hold under BOTH the
  dated-zero-fee mode and the worst-case ceil_175 mode (Section 1). Fee-fragile
  passes do not fire.
- **A-5 (decay guard):** OOS event-mean >= 50% of the TRAIN event-mean and OOS
  event-mean > 0 (Fact 4; the edge must not have decayed to noise across the
  ~3-month gap).
- **A-6 (concentration):** the largest single event-ticker-family (player or
  tournament token) contributes < 50% of the absolute P&L in each window
  (anti-F7; reported, and binding at the 50% line).

KILL: if A-1 through A-6 do not ALL hold on the WTA-NO moderate band,
Direction A is KILLED at the Becker screen, NULL written, no forward work. The
ATP-NO diagnostic CANNOT rescue a WTA-NO failure (it is the distrusted toxic
cell by construction).

### 2.5 F11 caveat and the staged path (locked)

A Becker screen pass is an UPPER BOUND on a new entrant's edge: Becker fills are
what HAPPENED to incumbent makers, not what a NEW resting NO bid would fill at,
and the live arm already showed adverse-selection drift. So the staged path is:

1. **Becker screen (this lock).** Necessary, not sufficient. Zero capital.
2. **Forward shadow + tiny pilot.** A record-only forward logger posts ONE
   hypothetical 1-lot NO bid at the live best NO bid when it is in-band, episode-
   based (re-peg on best-bid move, back-of-queue fill rule, dead-book episodes in
   the denominator), 5-minute snapshot cadence, single-instance lock, NEVER
   places orders. Reuse the v21 shared collector harness pattern. Fill rate and
   fill-conditional net P&L are measured forward. Pre-registered forward gates:
   episode fill rate >= 3% (kills books too dead to trade), >= 30 settled modeled
   fills (hard stop < 10 by day 30), and net P&L per settled fill > 0 with a
   MARKET-DAY-clustered 95% CI excluding zero AND point estimate >= +1.0pp net.
   A ~$1-per-bet tiny live pilot may run alongside the shadow ONLY after the
   shadow clears, to confirm real fills match the shadow. Zero capital in the
   shadow; tiny capital in the pilot.
3. **Full live.** Only a shadow-confirmed (and pilot-confirmed) edge is wired
   into a sized live arm, on operator approval, with the sizing fix (fixed
   dollar-risk-per-bet plus a hard contract cap derived from bankroll, not the
   backtest peak) and a per-week realized-drawdown circuit breaker in place
   first.

### 2.6 Kill rule (no third bite)

If Direction A kills at the Becker screen OR at the forward shadow, it ends. No
criterion re-tuning, no band re-scanning to rescue it, no pooling the ATP-NO cell
back in. A NULL write-up is filed under `research/v23/`. The honest prior is
~40% (likely flat-to-barely-positive); a kill is the expected, acceptable
outcome.

---

## 3. DIRECTION B: crypto daily/range + Other-category maker (combined-side)

Scoped per the operator to crypto plus Other only (NOT sports, NOT the full
category sweep).

### 3.1 Hypothesis and exact universe

**B-crypto.** Crypto daily/range markets were the BROADEST PERSIST signal in the
prior Becker sweep (v10a: KXBTCD, KXETHD, KXBTC range all passed train+OOS
cluster CIs, though with OOS decay). Thesis: crypto retail over-reacts to spot
moves and the maker absorbs it at the resting quote. Universe (locked, three
sub-cells tested independently, NOT pooled):
- `KXBTCD-%` (Bitcoin daily)
- `KXETHD-%` (Ethereum daily)
- `KXBTC-%` (Bitcoin range; the hyphen excludes KXBTCD via the explicit prefix)

**Combined-side maker definition.** For each crypto sub-cell, pool YES-maker and
NO-maker fills (the side-agnostic level). Maker side = opposite of `taker_side`.
Maker entry price = the printed maker-side price / 100. Per-fill net per $1 =
`(maker side wins ? 1 - entry : -entry) - maker_fee`, where the maker wins when
`result` equals the maker's side. **Price band (locked):** maker entry price in
[0.30, 0.70] (the uncertain mid-band where crowd mispricing is documented; the
v10a crypto edges were measured in this band). Strikes priced outside [0.30,0.70]
are excluded.

**B-Other.** The diversified "Other" category maker. Universe (locked) = the
FROZEN v21 outcome-blind allowlist at
`research/v21/allowlists/other_060_080.json` (369 structural prefixes covering
80% of the cell's band trade volume; built from structural fields only, committed
pre-screen, no outcomes). A trade is in B-Other if
`regexp_extract(event_ticker, '^([A-Z0-9]+)', 1)` is in that allowlist.
**Price band (locked):** maker entry price in [0.60, 0.80) (the v21/v10a Other
cell band). Combined-side, same maker-net definition as B-crypto.

**Binding prior on B-Other (load-bearing, honest).** The v21 Candidate A screen
ALREADY tested this exact frozen Other allowlist under an event-cluster bootstrap
and it was NEGATIVE on train: -0.79pp, CI [-5.63, +3.82], k=167 events. The
prior +2.40pp Other number was a TRADE-LEVEL-CI artifact over correlated trades.
So B-Other enters this lock with a LOW prior and is expected to fail A-equivalent
gate B-2/B-3; it is tested honestly because the operator scoped it in, but it
will NOT be rescued by any trade-level statistic.

### 3.2 Chronological split + purge buffer (locked)

Becker layout finding: crypto daily/range series exist from 2024-10-24 to
2025-11-23 (the full post-flip window). Other-allowlist series span the full
post-Oct-2024 window. So the split uses the full window:

- **Train:** 2024-11-01 to 2025-08-15 (post-flip; first-trade-time assignment).
- **Purge buffer:** 2025-08-15 to 2025-08-22 (7 calendar days). Crypto daily
  markets resolve within 24h and range within days, and the Other population is
  capped at a 60-day horizon (below), so 7 days exceeds the max settlement
  horizon for crypto and bounds Other leakage; events whose first trade is in
  the buffer are dropped from both windows.
- **OOS:** 2025-08-22 to 2025-12-01 (data ends 2025-11-23; upper bound is a
  harmless cap).
- **Population rule for B-Other (uniform across both windows, anti-composition):**
  keep an Other trade only if its market's horizon `(close_time - created_time)
  <= 60 days` AND its `close_time` is in the same window as its first trade. The
  uniform 60-day cap makes train and OOS like-for-like (the OOS window is shorter,
  so without the cap it would mechanically exclude long-horizon markets train
  admits). The dropped long-horizon share is reported. Crypto daily/range are
  intrinsically short-horizon so the cap is non-binding there but applied
  uniformly for consistency.

**Powering (event-cluster counts, measured pre-data, no outcomes).** Distinct
events post-Oct-2024 with the split above:
- KXBTCD: full 5,417; train (to 2025-08-15) 3,811; OOS (2025-08-22+) 1,494.
- KXETHD: full 5,016; train 3,443; OOS 1,461.
- KXBTC range: full 5,391; train 3,792; OOS 1,487.
All three crypto sub-cells are very well-powered (thousands of events per
window) even after the [0.30,0.70] band filter. B-Other: the frozen allowlist's
band-trade volume (295k trades over the full window) spreads over many events;
the binding floor (B-1, >= 60 events per window) is satisfiable, but the v21
result warns the edge sign is the risk, not the count. These counts justify the
split; no P&L was computed.

### 3.3 Firable pass criteria (Becker screen, per sub-cell; NON-INFERENTIAL)

Each of the FOUR sub-cells (KXBTCD, KXETHD, KXBTC-range, Other) is evaluated
INDEPENDENTLY. A sub-cell SURVIVES and earns a forward shadow only if ALL of:

- **B-1 (powered minimum-n):** >= 60 distinct settled events in BOTH windows
  after the band and definitive-settlement filters.
- **B-2 (train sign, event-cluster):** combined-side net excess > 0 with
  `cluster_bootstrap_mean_ci` 95% CI LOWER BOUND > 0 on TRAIN.
- **B-3 (OOS sign, event-cluster):** same, CI LOWER BOUND > 0 on OOS. (Binding:
  cluster CI EXCLUDES ZERO on BOTH windows.)
- **B-4 (net-of-fee under both fee modes):** B-2 and B-3 hold under BOTH the
  dated-zero-fee mode and the worst-case ceil_175 mode. (Crypto daily series did
  carry fees in parts of the window; the dated table governs which. The
  worst-case mode is the conservative binding check.)
- **B-5 (decay guard):** OOS event-mean >= 50% of TRAIN event-mean and OOS
  event-mean > 0 (Fact 4; crypto showed material OOS decay historically, so this
  guard is load-bearing here).
- **B-6 (concentration):** the largest single event-ticker-family contributes
  < 50% of absolute P&L in each window. For Other this is binding (a single
  prefix dominating = the v10a Weather/World-Events failure pattern); for crypto
  daily it is naturally satisfied (thousands of independent daily events).

KILL: a sub-cell failing any of B-1 through B-6 is dropped. If ALL FOUR sub-cells
fail, Direction B is KILLED at the Becker screen, NULL written, no forward work.
Surviving sub-cells (if any) proceed to the staged path.

### 3.4 F11 caveat and the staged path (locked)

Identical structure to Direction A Section 2.5: the Becker screen is a NECESSARY
UPPER-BOUND screen; surviving crypto/Other sub-cells go to a record-only forward
shadow (combined-side: post a hypothetical 1-lot bid on whichever side the live
best bid is in-band, episode-based, 5-min cadence, dead-book denominator, never
places orders), with the SAME pre-registered forward gates (episode fill rate
>= 3%, >= 30 settled modeled fills with the day-30 hard stop, net per fill > 0
with a MARKET-DAY-clustered CI excluding zero and point >= +1.0pp net), then a
~$1-per-bet tiny pilot, then full live only on operator approval with the sizing
fix and drawdown breaker in place. Crypto's known F11 risk is especially acute
because pro HFT makers maintain crypto quotes continuously against spot, so a new
retail maker bid faces severe queue and adverse-selection competition; the
forward shadow's fill rate is the decisive crypto test.

### 3.5 Kill rule (no third bite)

If a Direction B sub-cell kills at the Becker screen OR at the forward shadow, it
ends. No criterion re-tuning, no band re-scanning, no re-pooling, no re-surfacing
the Other cell on a trade-level statistic. A NULL write-up is filed under
`research/v23/`. Honest priors: crypto is the strongest of the four (broadest
prior PERSIST), Other is low (v21 already killed it at event-cluster level).

---

## 4. Pre-registered gate summary

| Gate | Direction | Universe (gate input) | Window | Pass condition | Kill |
|---|---|---|---|---|---|
| A-1 | A | WTA-NO no_px[70,86) | both | >= 60 settled events each window | drop |
| A-2 | A | WTA-NO no_px[70,86) | train | event-cluster 95% CI lower > 0 | drop |
| A-3 | A | WTA-NO no_px[70,86) | OOS | event-cluster 95% CI lower > 0 | drop |
| A-4 | A | WTA-NO no_px[70,86) | both | A-2 and A-3 hold under BOTH fee modes | drop |
| A-5 | A | WTA-NO no_px[70,86) | both | OOS mean >= 50% train mean and OOS mean > 0 | drop |
| A-6 | A | WTA-NO no_px[70,86) | both | largest event-family < 50% abs P&L | drop |
| (A fails) | A | -- | -- | -- | KILL A, NULL |
| B-1 | B | each of {BTCD,ETHD,BTC-range,Other} | both | >= 60 settled events each window | drop sub-cell |
| B-2 | B | each sub-cell | train | event-cluster 95% CI lower > 0 | drop sub-cell |
| B-3 | B | each sub-cell | OOS | event-cluster 95% CI lower > 0 | drop sub-cell |
| B-4 | B | each sub-cell | both | B-2 and B-3 hold under BOTH fee modes | drop sub-cell |
| B-5 | B | each sub-cell | both | OOS mean >= 50% train mean and OOS mean > 0 | drop sub-cell |
| B-6 | B | each sub-cell | both | largest event-family < 50% abs P&L | drop sub-cell |
| (all B sub-cells fail) | B | -- | -- | -- | KILL B, NULL |
| Forward | A,B | survivors | forward shadow | fill rate >= 3%, >= 30 fills (stop <10 by d30), net/fill > 0 with market-day-cluster CI excl 0 and point >= +1.0pp | kill survivor |

Crypto band = maker entry [0.30,0.70]; Other band = maker entry [0.60,0.80);
Other universe = frozen v21 allowlist. All inference uses
`cluster_bootstrap_mean_ci(..., n_resamples=5000, ci=0.95, rng_seed=42)`,
cluster = event_ticker, on post-October-2024 data only, net of the
`ceil(1.75*P*(1-P))`-cent maker fee, combined-side (A pools across legs/matches;
B pools YES and NO maker fills).

---

## 5. What v23 will NOT do (locked)

- NOT change any gate threshold after seeing outcomes (no post-data tuning).
- NOT pool the toxic ATP-NO cell into Direction A's gate (it is watch-only).
- NOT pool crypto sub-cells together or Other into crypto (each tested alone).
- NOT use any Becker entry price as a forward-fill guarantee (F11), nor
  `last_price` / the terminal markets snapshot as an execution price (F4).
- NOT use a trade-level CI as a gate (event-cluster only); NOT rescue a cell on
  a trade-level statistic (the v21 Other lesson).
- NOT use any per-side base-rate cell as forward evidence (combined-side / pooled
  only).
- NOT claim inferential validity for the Becker screen (the cells are survivors
  of prior sweeps; the screen is a non-inferential pre-registered filter; all
  inferential weight is on the forward shadow).
- NOT go to live capital on the strength of any Becker pass (forward shadow +
  tiny pilot first; full live only on operator approval with the sizing fix and
  drawdown breaker in place).
- NOT propose ML / LLM / sentiment / Granger angles (9 NULLs plus 1 phantom
  already; all sub-12% priors).
- NOT take a third bite: a kill at the screen or the shadow ends the direction.

---

## 6. Honest priors and expected outcome

- Direction A (WTA-NO moderate band): ~40%, likely flat-to-barely-positive; the
  symmetric-bias thesis is real but Burgi decay and the live arm's straddling-CI
  experience pull the prior down.
- Direction B crypto: the strongest of all sub-cells (broadest prior PERSIST),
  but with documented OOS decay and acute HFT competition that the forward
  shadow's fill rate will adjudicate.
- Direction B Other: LOW (already killed at event-cluster level in v21); tested
  honestly per operator scope, expected NULL.

A NULL across both directions is an acceptable, expected outcome consistent with
the kill-early principle. The next action after this lock is to run the Becker
backtest mechanically against these criteria, exactly once, no re-runs, no
tuning.

---

*Em-dash and en-dash audit: verified clean after write.*
