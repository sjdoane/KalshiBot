# v20: Capital-deployment levers (per-bid size + stale-bid TTL)

Date: 2026-06-03. v1 = KalshiLiveBot (sole live bot; v14 removed 2026-06-01).
Measured from `data/live_trades/state.json`, `kill_state.json`,
`logs/live.log`, and two read-only live-API probes (`scripts/v20/`).

## TL;DR

1. **The binding constraint is ELIGIBLE-FILL AVAILABILITY, not capital.**
   Proven three independent ways (below). v1 leaves ~75% of bankroll idle
   because few markets pass its filters at any moment (4 to 20 of ~24,000
   scanned Sports markets per loop), NOT because per-bid size is too small or
   capital is locked in stale orders.

2. **Lever 1 (per-bid size): the knob is currently DEAD, and that is the real
   finding.** `V1_PER_BID_FRACTION` only affects sizing when
   `V1_BANKROLL_FRACTION < 1.0`. v1 has been at `1.0` since v14 was removed
   (2026-06-01), so per-bid sizing silently fell back to the fixed
   `LIVE_PER_TRADE_USD = $0.95`, which produces exactly **1 contract on every
   order regardless of the fraction** (confirmed: 273 of 273 orders all-time
   are 1 contract). Raising `V1_PER_BID_FRACTION` as an env var alone would
   have done NOTHING. The fix is a small code change to compute v1's bankroll
   slice at `fraction == 1.0` too. With the fix, the existing conservative
   `0.03` fraction yields ~2 contracts (~quarter-Kelly on the conservative
   edge), roughly doubling per-fill deployment safely.

3. **Lever 2 (stale-bid TTL): KEEP 6h. Do not shorten.** Faster recycling
   solves a problem v1 does not have (capital is not the constraint), it risks
   cancelling soon-to-fill bids on liquid markets, and `--cancel-on-drift`
   already handles the real risk (adverse staleness). No change.

4. **Neither lever materially fixes the idle bankroll.** The idle capital is an
   availability problem. The highest-value future work is expanding *validated*
   eligible availability (more in-season validated prefixes / time-of-day
   coverage), not sizing or recycling. That is out of scope here and needs its
   own validation.

## 1. Measurement (2026-06-03 ~07:00 UTC)

### 1.1 Current deployment (the capital question)

`budget_snapshot` (live.log, every loop, stable for hours):
```
cash_usd=39.63  resting_exposure_usd=2.52  headroom_usd=36.33
```
- Resting orders: 3, all 1 contract, $2.52 total.
- Open filled positions: 19, all 1 contract, ~$14 entry notional.
- `max_concurrent` resolved = **54-55** (= bankroll / $0.95); only ~22
  positions are open. The concurrency cap is not close to binding.
- The per-loop budget gate (`resting + new <= cash`) has **$36 of headroom**.
  It has never bound.

`kill_state.json`: `starting_bankroll_usd=68.19` (stale), `tripped=false`, P&L
history arrays empty (post `reset_v1_kill --full-history`). `state.json` (the
LiveOrderManager) has a DIFFERENT baseline `starting_bankroll_usd=52.28` and
`realized_pnl_total_usd=-2.93`. The bot's DrawdownMonitor re-baselines to the
live read on each restart, is not tripped, and is actively placing, so drawdown
is not binding. IMPORTANT (council H3): the -$2.93 realized loss is entirely
from OLD broad-universe series settled 2026-05-24 to 30 (KXNBAPLAYOFFWINS,
KXCS2, KXIPLFINALS, KXPGATOP20, KXNCAABBPLAYOFFS, etc.), NONE of which are in
the 5-prefix allowlist. It is the broad-universe dilution the allowlist was
built to stop. The NEW allowlist+bands+NO-arm+step-in-front config has ~zero
settled trades, so it is UNPROVEN live, not proven-negative. Treat the size
increase as modest and gate any further increase on positive settled P&L of the
new config.

### 1.2 Eligible-fill funnel (the availability question)

`scan_done` (live.log): each loop scans **n_raw ~= 24,000** open Sports markets
across **n_series = 2,088**, and only **n_candidates = 4 to 20** pass all
filters (favorite band, volume >= 50, lifetime[0,21], minutes_to_close >= 60,
allowlist, denylist). After dedup against already-resting orders, only a
handful of NEW orders are placeable per loop.

Read-only probe of the 5 allowlist series (`scripts/v20/probe_eligible_universe.py`,
2026-06-03 07:05 UTC):

| Series | open | pass band+vol | pass ALL filters |
|---|---|---|---|
| KXATPMATCH | 6 | 2 | **2** (1 match, closes 16d out) |
| KXWTAMATCH | 6 | 2 | **2** (1 match, closes 14d out) |
| KXMLBGAME | 78 | 0 | **0** |
| KXNCAAFGAME | 30 | 14 | **0** |
| KXNFLGAME | 32 | 6 | **0** |

So at this hour exactly **4 markets** are eligible (2 tennis matches, both
sides), matching `n_candidates=4`.

Why the big in-season series contribute 0 right now
(`scripts/v20/diagnose_mlb_football.py`):
- **KXMLBGAME: 78 open, mids 0.35 to 0.65, ZERO >= 0.70.** No current MLB game
  has a clear favorite, so none enters the favorite band. This is partly
  time-of-day (the June 3 slate has not started; lines firm up near game time)
  and partly structural (baseball favorites are usually 0.55 to 0.68, rarely
  >= 0.70).
- **KXNCAAFGAME / KXNFLGAME: open->close SPAN 103 to 124 days** (Aug/Sep season
  openers). They are correctly excluded by `lifetime[0,21]`. The lifetime fix
  IS working. (The 15 football futures that were placed at 00:03 and TTL-cancelled
  at 06:10 were from an OLDER bot instance running the prior `[30,180]` window,
  which admitted 110-day spans; the 6h TTL cleaned them up.)

### 1.3 Per-order size: always 1 contract

`per-order contract sizes (all-time): {1: 273}`. Every single order v1 has ever
placed is 1 contract. Root cause in 1.3 / Section 3.

### 1.4 Fill timing (for the TTL question)

Time-to-fill for orders that filled:
- all-time: median 6.7h, p75 12h, p90 34h (n=19). **But this is OLD
  back-of-queue data on illiquid markets and is not representative.**
- new step-in-front config: n=2, both ~1.9h (far too small to conclude).

Age-at-cancel for never-filled cancels: median **6.1h** (tight cluster at 6h).
The 6h stale TTL is the dominant cancel path, and it is currently clearing
mostly far-dated futures that never fill.

## 2. Binding constraint: AVAILABILITY, not capital

Three independent proofs that capital / budget / concurrency are NOT binding:
1. Budget gate headroom is $36 of $39.63 cash; resting exposure is $2.52.
2. `max_concurrent` = 54 vs ~22 positions open.
3. Only 4 to 20 of ~24,000 scanned markets pass the filters per loop; the
   live probe shows exactly 4 eligible right now.

v1 is idle because the eligible universe is small and sport/time-of-day
dependent (off-hours: tennis only; MLB needs a >=0.70 favorite at game time;
football season openers are excluded as far-dated). More capital cannot be
deployed onto markets that do not exist or do not fill.

## 3. Lever 1: per-bid size

### 3.1 The dead-knob gating regression (root cause of "always 1 contract")

`scripts/paper_trade_favorite.py::one_loop_favorite_live`:
- `v1_cap_total` is initialized to `None` and only assigned inside
  `if bankroll_fraction < 1.0:` (the partial-slice block written when v14
  existed and v1 had 60%).
- `v1_per_bid_contracts(...)` uses `per_bid_fraction * v1_cap_total` only when
  `v1_cap_total is not None`; otherwise it uses `fallback_usd = per_trade_usd =
  LIVE_PER_TRADE_USD = $0.95`.
- v1 went to `V1_BANKROLL_FRACTION = 1.0` on 2026-06-01 (v14 removed). So
  `bankroll_fraction < 1.0` is False, `v1_cap_total` stays `None`, and per-bid
  budget = `$0.95` => `int(0.95 / ~0.78) = 1` contract on every order.

So the 2026-05-30 council's dynamic per-bid sizing (scale with live bankroll)
has been silently disabled in the 100%-bankroll regime. `V1_PER_BID_FRACTION`
is inert until this is fixed.

**Fix:** compute `v1_cap_total = bankroll_fraction * (cash + positions)` for
EVERY fraction (at 1.0 it is the full bankroll). Apply the effective-cash
RESTRICTION only for a partial slice (`< 1.0`); at 1.0 v1 may use all cash, so
the budget gate is unchanged. Extracted into a pure, unit-tested helper
`resolve_v1_cap_and_cash`.

With the fix, at the current ~$54 bankroll: per-bid budget = `0.03 * 54 =
$1.62` => 2 contracts at ~$0.78 (LOW band multiplier 1.3 keeps it ~2). Per-fill
deployment roughly doubles (1 -> 2 contracts), still within prudent Kelly.

### 3.2 Kelly bound (justifying the number, not guessing)

Validated edge (research/v18, v10a): moderate favorites LOW band [0.70,0.86)
~+6 to +8% net return-on-stake OOS (cross-sport MLB/ATP/WTA, CIs exclude 0);
heavy band [0.86,0.95] ~+2 to +4% (marginal); symmetric NO-underdog mirror.

For a binary maker buy at price p, win prob q, edge e = (q - p)/p:
full Kelly fraction f* = q - (1 - q) * p / (1 - p).
- LOW p=0.78, optimistic e=0.07 -> f* ~= 25%; conservative e=0.04 -> f* ~= 14%.
- heavy p=0.90, optimistic e=0.03 -> f* ~= 27%; conservative e=0.015 -> f* ~= 13%.

CORRECTION (council QUANT H1): the v18 edges (+6 to +8% LOW etc.) are NET
per-contract P&L on $1 face, NOT `(q - p)/p`. Backing out the implied win prob
and running proper Kelly, full Kelly on the conservative-CI edge is ~28-53% LOW
and ~37-74% heavy (HIGHER than a naive read). Full Kelly is large for favorites
(low loss probability), but the absolute edge LEVEL carries F11 phantom risk
(the relative LOW>heavy finding is robust; the level is not bullet-proof), so a
fractional-Kelly posture is mandatory.

Effective per-position fractions (fraction x band multiplier):
- `0.03 * 1.3 = 3.9%` LOW, `0.03 * 0.8 = 2.4%` heavy.

These are roughly **one-eighth Kelly on the conservative edge** (QUANT verified),
i.e. conservative with substantial headroom below quarter-Kelly. So `0.03` is
the RIGHT (conservative) scale for an F11-flagged edge; the only thing wrong was
the gate bug pinning it to 1 contract. Do NOT raise it to "use the idle 75%":
that would require ~4x (toward/past full Kelly) and availability caps it anyway. **Recommendation: fix the gate, keep `V1_PER_BID_FRACTION=0.03`**
(now made explicit and live in the launcher). Do NOT raise it further; a 4x
bump to "use the idle 75%" would push past full Kelly = over-betting a +5-8%
edge, exactly what we must avoid (and availability would cap it anyway).

Optional future tunables (documented, NOT applied now; enable after observing
real fills): sharpen band multipliers toward the 2:1 edge ratio
(`V1_BAND_M_LOW=1.5`, `V1_BAND_M_HIGH=0.7`) and/or `V1_PER_BID_FRACTION=0.04`
(toward one-third-Kelly) once a settled-P&L-by-band sample confirms the level.

### 3.3 Risk guards (all respected)

- Per-position size ~$1.6 to $2.7 is well under 10% of even a $40 bankroll
  ($4), so it cannot false-trip `KILL_LOSS_DOLLAR_FALLBACK_PCT` (0.10 before 20
  winners). The 20% drawdown kill (`KILL_DRAWDOWN_PCT`) and YES-rate kill
  (0.70) remain armed.
- Aggregate is gated by the budget gate (`resting + new <= cash`) and
  `max_concurrent`. Per-bid size is a target, not a bypass.
- Scales sanely toward the $100 cap: `0.03 * 100 = $3` -> 3-4 contracts.

## 4. Lever 2: stale-bid TTL

Current `STALE_BID_TTL_HOURS = 6` (code default 120h). Trade-offs:
- **Shorter TTL** recycles local budget faster and lets v1 re-step in front at
  fresh prices, BUT (a) capital is NOT the constraint (Section 2), so there is
  nothing to recycle for; (b) the current eligible markets are liquid tennis
  matches that close 14-16 days out, so a resting maker bid may legitimately
  wait many hours for a counterparty to lift it; a short TTL would cancel and
  re-place repeatedly, churning API calls and risking a cancel just before a
  fill; (c) the all-time data (median 6.7h to fill) says a sub-6h TTL would
  pre-empt >50% of fills, though that sample is old back-of-queue and the
  new step-in-front config has too few fills (n=2) to recalibrate yet.
- **Longer TTL** lets liquid long-dated bids rest and fill, but raises adverse-
  selection risk for stale bids -- which `--cancel-on-drift` (3c drift, 30-min
  min age) already manages.

**Verdict: keep 6h.** There is no capital pressure to recycle, cancel-on-drift
covers staleness, and we lack representative new-config fill-timing data to
justify a change. Revisit only after ~30+ new-config fills give a real
time-to-fill distribution (then a per-series TTL could be considered).

## 5. Recommendation and staged changes

**SHIP (Lever 1): the gate fix + explicit launcher env vars.** Reversible.
- Code: `paper_trade_favorite.py` computes `v1_cap_total` at all fractions
  (helper `resolve_v1_cap_and_cash`, unit-tested).
- Launcher `scripts/run_live_bot.ps1`: set `V1_PER_BID_FRACTION=0.03`,
  `V1_BAND_M_LOW=1.3`, `V1_BAND_M_HIGH=0.8` explicitly (now live + tunable).

**NO CHANGE (Lever 2):** `STALE_BID_TTL_HOURS` stays 6 (documented).

**Operator restart (do NOT let the agent restart):**
```
Stop-ScheduledTask -TaskName KalshiLiveBot
.\scripts\restart_bot.ps1 -Force
```
Then verify in live.log that `v1_bankroll_fraction_cap` now logs a non-null
`v1_cap_total` and `live_favorite_order_placed` shows `contracts=2` on LOW-band
fills.

## 6. Caveats

- F11 (Becker has no orderbook-ask-at-trade-time): the edge LEVEL is not
  phantom-proof; sizing stays conservative (~one-eighth Kelly).
- Bigger positions = more variance per name; the kills are the backstop.
- The deployment gain is bounded by availability; expect modestly larger fills,
  not a jump from 25% to 100% utilization.

## 7. Council review and resolutions

A Quant member, a Risk/Realist member, and a post-implementation code reviewer
reviewed this (per session rules). Findings and how each was resolved:

- **C1 (Risk, CRITICAL): the NO-underdog arm rested a bid on BOTH sibling
  tickers of one head-to-head event** (live proof: KXATPMATCH-MENZVE filled
  NO-MEN @77 + resting YES-ZVE @77, both bet ZVE; KXWTAMATCH-SABSHN both bet
  SAB). Dedup was ticker-only. The per-bid size increase would compound this
  ~2x event-doubling to ~4x. RESOLVED: added `event_identity` + event-level
  dedup so v1 rests at most one favorite bid per event (all allowlist prefixes
  are head-to-head, so siblings are the same directional bet). This also makes
  the net per-event change a strict risk improvement: one correctly-sized
  position per event instead of two correlated 1-contract positions.
- **H2 (Quant, HIGH): band multipliers were applied AFTER the floor-divide**
  (`round(base * mult)`), so at small bankroll (base=1) they were inert/lumpy.
  RESOLVED: fold the multiplier into the budget BEFORE the floor-divide
  (`effective_fraction = fraction * band_mult`), so band sizing actually
  functions and is consistent (LOW 2 / heavy 1 at the current bankroll).
- **H1 (Quant, HIGH): the Kelly label was wrong** (the v18 edges are net per
  contract, not (q-p)/p). RESOLVED: corrected in Section 3.2; `0.03` is
  ~one-eighth Kelly (conservative), confirmed SAFE to ship.
- **H3 (Risk, HIGH): the bot is realized-negative (-$2.93).** RESOLVED via
  verification: the loss is entirely OLD broad-universe (non-allowlist) series;
  the new config is unproven, not proven-negative (Section 1.1). Mitigation:
  keep the increase modest (0.03) and gate further increases on positive
  settled P&L of the new config.
- **M3 (Quant, MEDIUM): is the 20% drawdown kill armed in live?** VERIFIED yes:
  `paper_trade_favorite.py` live path builds
  `DrawdownThresholds(kill=settings.KILL_DRAWDOWN_PCT, halt=TOTAL_DD_HALT_PCT)`.
- **Lever 2 reasoning (Risk H1): keep 6h, but for the right reason.** RESOLVED:
  the correct reason is that `--cancel-on-drift` (3c, 30-min) already owns the
  adverse-staleness case on a 15-min cadence, so the 6h timer only touches
  non-drifted (still-good) bids; the fill-timing data (n=2 new-config) is too
  thin to retune and if anything leans slightly toward LENGTHENING for liquid
  14-16d tennis. Keep 6h; revisit per-series after ~30 new-config fills.

Both council members and the code reviewer returned SHIP / SAFE on the final set.

### Final shipped set (staged; operator restart applies)

- Code (`scripts/paper_trade_favorite.py`): `resolve_v1_cap_and_cash` (gate fix,
  per-bid sizing live at fraction 1.0); `event_identity` + event-level dedup
  (C1); band multiplier folded pre-floor (H2). 59 targeted tests pass (6 new).
- Launcher (`scripts/run_live_bot.ps1`): `V1_PER_BID_FRACTION=0.03`,
  `V1_BAND_M_LOW=1.3`, `V1_BAND_M_HIGH=0.8` set explicitly; `STALE_BID_TTL_HOURS`
  kept at 6 (Lever 2 unchanged).
- Net effect at ~$52 bankroll: LOW-band fills go 1 -> 2 contracts, one position
  per event (was up to two), heavy fills stay 1. Modest, within Kelly, kills and
  budget gate intact.

### Out of scope (flagged, not fixed here)

Two PRE-EXISTING test failures, unrelated to this change, both confirmed to
reproduce on HEAD with these edits stashed:
- `test_live_modes_in_argparse_choices`: the v19 `--step-in-front` help string
  has a bare `%` (`+5-8%`) that breaks argparse `--help` formatting. One-char
  fix (`%%`). Does NOT affect the running bot (supervisor never calls --help).
- `test_resolve_starting_bankroll_live_auto_uses_state_when_present`: stale vs
  the bidirectional auto-rebaseline feature; needs a decision on intended
  behavior.
