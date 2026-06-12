# v22 Methodology Lock (Pre-Data), v1

**Date:** 2026-06-11
**Status:** LOCKED after the full selection chain (2 scouts -> 3-member
council -> data-grounded verifier whose NO-GO amendments are all
incorporated; see `01-selection-process.md`). Pending one methodology critic
pass before the screen runs. No outcome data has been read for any v22 axis;
the data scout and verifier ran STRUCTURAL queries only (timing
distributions, counts) plus v1's own perf log.

Operator authorization (2026-06-11): research and test another potential
bot, creative and cross-disciplinary, while v21 Candidate C collects.

## 0. Calibration and inheritance

Everything inherited from v21 lock v3.2 section 0 applies: F11 (no
historical orderbook; print screens are necessary-not-sufficient upper
bounds via incumbent-maker selection), F4, F9, event-cluster inference
mandatory, post-Oct-2024 only, no v1 changes, kill-early, no third bite.
Additional inherited lesson (v16 lock, re-surfaced by the verifier): a
passive-MAKER hypothesis cannot be validated record-only; fill-or-no-fill
is unobservable without a real resting order. The forward test for v22 is
therefore live 1-lot probes, not a phantom-fill shadow.

## 1. The slate (pre-registered; screens are RANKERS, not tests)

### P1 (lead; the ONLY promotable candidate): new-listing cold-start maker premium

Frame: Glosten-Milgrom learning phase. Hypothesis: in the first hours after
listing, before MM competition arrives, maker fills earn excess return above
the same market's mature-life maker fills.

**Screen estimand (locked):** event-clustered mean net maker excess per $1
(settlement payoff to the maker side minus maker print price minus
ERA-CORRECT maker fee) for COLD fills (trade age since open_time < 6h) minus
AGED fills (age > 3d AND time-to-close > 3d), within (category x TTE band)
cells, pooled by cold-fill trade count across cells. Population: post
2024-11-01, market lifetime (close_time - open_time) >= 10 days, after-close
prints dropped (share reported), final censored month (2025-11) excluded,
markets with close_time > 2028 excluded, frozen rebrand-unified
prefix-to-category map committed BEFORE the screen runs, v21-graveyard
cells (Media/Entertainment/Other mid-band series) LABELED and reported
separately, KXMVE excluded from inference (descriptive table only; its
parlay legs share games across events so event_ticker clustering is invalid
there). CI: `cluster_bootstrap_mean_ci`, cluster = event_ticker,
n_resamples=5000, ci=0.95, rng_seed=42, on the cold-fill population's
cell-matched excess-over-aged values; era-correct fee =
ceil(1.75*P*(1-P)) cents (the schedule in force during the Becker window).

- **K-P1 (kill):** pooled cold-minus-aged contrast <= 0, OR its event-cluster
  95% CI includes zero, OR fewer than 300 qualifying events contribute cold
  fills. Expected qualifying volume ~130 settled events/month (verifier
  ground truth), football-dominated; the screen pools the full 12-month
  window.
- Diagnostics (report-only): per-category contrasts; contract-weighted
  version; 2024Q4-vs-2025 stability split; KXMVE descriptive table with
  game-level grouping caveat.

### P2 (overlay; NOT promotable; no gate module this round): flow toxicity

Two pre-registered pieces, both report-only this round:
- **P2a Becker screen:** maker net excess by trailing signed taker-imbalance
  half (median split; imbalance = signed taker contract sum over the prior
  60 minutes in the same market, strictly before each print; window frozen
  now, no scanning), within category, activity-matched (imbalance computed
  only where >= 5 prior prints exist). Event-clustered. Purpose: does
  high-imbalance flow predict worse maker outcomes (loss-conditioning, NOT
  the dead directional-CVD use)?
- **P2b v1-own-fills diagnostic (the clean one, accumulating):** for each v1
  settled fill, compute the same trailing-imbalance signal causally from the
  public tape; compare net P&L across the median split. READ ONLY when v1
  has >= 200 settled fills AND >= 60 event-day clusters (currently 83
  fills: noise; not read this round). Escapes incumbent selection because
  the fills are our own.
- No kill (overlay informs future hosts); no gate module is built until a
  host strategy exists.

### P3 (screen only; NON-PROMOTABLE, funding veto pre-registered): affirmation tax

Frame: prospect-theory probability weighting at the longshot tail.
**Screen estimand (locked, verifier's fix):** one leg per event (the leg
with max fill volume among legs printing 3-8c YES), indicator = that leg
settles YES; compare realized YES frequency to the leg's own fill-weighted
implied probability via a Poisson-binomial test (Binomial(n, p-bar) as the
conservative bound) PLUS the standard event-cluster bootstrap on per-event
excess as robustness. Population: post-2024-11-01, EXCLUDING the dead
Media/Entertainment/Other cells; mandatory 2024Q4-vs-2025 decay split
(Whelan); v18 heavy-underdog-weak prior registered.
- **K-P3 (kill):** NO-side excess <= +2pp net of era-correct fee, or
  conservative-bound p > 0.05, or the 2025 split shows the edge below +1pp.
- **Funding veto (locked):** P3 cannot receive capital or probes this round
  regardless of screen outcome (capital efficiency ~95c locked per <= 6c
  gross; correlated same-game settlements are the realistic ruin path).

### Excluded (recorded so future rounds do not re-litigate blind)

- Hazard-clock decay: UNIDENTIFIED on prints (stale-print confound is the
  observable); excluded for collector cost on forward data. Not graveyard;
  revisit only with a purpose-built high-frequency collector.
- Cross-horizon coherence map: killed (maintenance rot, unbounded researcher
  degrees of freedom, adjacent to the 0-in-2,791 dutch-book null).
- Ladder-shape RV: deferred zero-cost read of the accumulating C0 JSONL,
  read date = G-C0 verdict day + 7 (see branch table); no build before then.

## 2. Selection and forward-test structure

- Screens are non-inferential rankers. The forward slot belongs to P1 IFF P1
  survives K-P1. P2/P3 inform v23 only. (The council's "largest effect
  wins" rule was vacuous: P1 is the only fundable candidate; verifier
  finding 12.)
- **Forward test = live 1-lot maker probes** (v16 lesson; record-only cannot
  measure maker fills): separate bot identity, own intent-id prefix (NOT
  v1's), own state file, own scheduled task, triple kill (20pct drawdown of
  its slice, 5-consecutive-loss, fill-starvation stand-down), quotes only on
  P1-qualifying newly-listed markets. Powered at HALF the screen effect
  against the CURRENT (Feb-2026) fee schedule in integer cents; alpha 0.05;
  minimum 200 events / 30 effective clusters before the CI is read; named
  starvation kill date set at launch (+8 weeks); economic floor = CI lower
  bound > 0 AND point >= +1.0pp net.
- **Season-aware start:** the qualifying universe is NCAAF/NFL/EPL-heavy and
  out of season in July; the probe phase starts no earlier than the Jun-23
  C0 branch decision and its starvation clock is set acknowledging the
  August season turn-on.
- **External VOID kill:** if sports event contracts become restricted for CA
  accounts mid-round (active multi-state litigation), the round is VOID, not
  null.

## 3. Capital and C0 branch table (Jun-23)

Shared $100 operator ceiling; v1 currently holds ~$80 at fraction 1.0.
ANY new live deployment (ladder executor or P1 probes) requires the
operator to restore a v1 bankroll fraction split and restart v1: explicit
operator action, never done by a session unprompted.

| Branch | Candidate C | v22 |
|---|---|---|
| G-C0 PASS (>= 3 locks) | C takes the build slot + first capital claim (execution bot design, own plan critic) | Screens complete; P1 probe deferred until C's build decision lands; P1 survives as the next-in-line candidate |
| G-C0 FAIL | C NULL, v21 closes; KalshiC0LadderScan task kept ALIVE 7 more days solely to feed the ladder-shape deferred read, then unregistered | P1 probe phase may start (operator approval + fraction split first); Stage-C ceiling = min($40, $100 minus v1 balance at promotion) |

## 4. What we will NOT do (locked)

- NOT read any outcome data before the methodology critic clears this lock.
- NOT change buckets, windows, fee math, or kill thresholds after results.
- NOT promote P2 or P3 this round under any screen outcome.
- NOT run KXMVE inference on event_ticker clusters.
- NOT start live probes without operator approval, a v1 fraction split, and
  the C0 branch decision.
- NOT touch v1 (the P2b diagnostic READS its perf log only).

## 5. Review plan

Selection chain DONE (scouts -> council x3 -> verifier, all on record in
`01-selection-process.md`). NEXT: one methodology critic on THIS lock before
the screen script runs; code review of the screen script before its output
is read; if P1 survives: plan critic + code review + post-impl review on the
probe bot before any live order; council + verifier at the go/no-go.

## 6. Change log

- 2026-06-11 v1: initial lock, incorporating all 12 verifier amendments
  (TTE-matched comparator, lifetime >= 10d, ~130 events/month ground truth,
  KXMVE demoted to descriptive, era-correct vs current fee split, capital
  branch table, live-probe forward test per the v16 lesson, season-aware
  start, P2 reframed as accumulating diagnostic, P3 one-leg Poisson-binomial
  + funding veto, VOID kill, C0 branch table).
