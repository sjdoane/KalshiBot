# Round 15c: v1 adverse drift, stratified by prefix

**Date:** 2026-05-27 (overnight extension to Round 15)
**Author:** Round 15c orchestrator
**Source:** `scripts/v10a/analyze_v1_live.py` output, post-restart
**Key finding:** the adverse drift in v1 is overwhelmingly concentrated
in OTHER (non-PERSIST) prefixes. The `--allowlist` flag is the bigger
lever; `--cancel-on-drift` is a supplementary safety net.

## Raw breakdown of still-open v1 fills

15 fills are still open and have a fetchable current orderbook mid.
Per-prefix breakdown of (fill_price - current_mid) in percentage
points, sorted from worst to best drift:

| Prefix | Bucket | Tickers in this group | Per-ticker drift (pp) | Group avg drift (pp) |
|---|---|---|---|---|
| KXIPLFINALS | OTHER | 1 ticker | -24.50 | -24.50 |
| KXNBAPLAYOFFWINS | OTHER | 2 tickers | -11.00, -5.00 | -8.00 |
| KXUFCOCCUR | OTHER | 1 ticker | -5.00 | -5.00 |
| KXWNBAWINS | OTHER | 1 ticker | -3.50 | -3.50 |
| KXFOMEN | OTHER (thin Becker NULL) | 1 ticker | -1.00 | -1.00 |
| KXNFLGAME | **PERSIST** | 1 ticker | -0.50 | **-0.50** |
| KXWCGAME | OTHER | 3 tickers | -0.50, -0.50, +0.50 | -0.17 |
| KXUFCFIGHT | OTHER (TRAIN_ONLY) | 2 tickers | -0.50, +0.50 | +0.00 |
| KXNHLDRAFTPICK | OTHER | 1 ticker | +0.00 | +0.00 |
| KXWCSTAGEOFELIM | OTHER | 1 ticker | +2.50 | +2.50 |
| KXBOXING | OTHER (thin Becker NULL) | 1 ticker | +4.00 | +4.00 |

**Overall:** mean adverse drift -2.97pp across all 15 (was -4.93pp at
earlier snapshot; some markets recovered partially).

**PERSIST cell:** only 1 of 15 still-open fills is in a PERSIST
prefix (KXNFLGAME). That fill has drifted -0.50pp; well below the
default `--drift-threshold-cents 3` cancel trigger.

**OTHER cell:** 14 of 15 fills are OTHER prefixes. The worst drifts
are all here: KXIPLFINALS -24.50pp, KXNBAPLAYOFFWINS -11pp,
KXUFCOCCUR -5pp. These are exactly the prefixes Round 15b Phase B
found INSUFFICIENT or thin-data NULL.

## Implication: `--allowlist` is the dominant lever

If v1 had been restricted to the PERSIST allowlist BEFORE these
fills happened:
- 14 of the 15 still-open fills would NOT have been placed.
- The catastrophic -24pp KXIPLFINALS fill would not exist.
- The mean adverse drift among PERSIST-only fills would be ~ -0.5pp.

`--cancel-on-drift` with the default 3c threshold would have caught
the -5pp and worse drifts (KXIPLFINALS, KXNBAPLAYOFFWINS, KXUFCOCCUR,
KXWNBAWINS), saving ~5 fills worth of expected loss. But the
`--allowlist` flag prevents those fills from being placed in the
first place.

## Recommended operator restart configuration

Order of importance:

1. **`--allowlist` (highest priority).** This is the single most
   impactful flag. Restricts v1 to the 5 PERSIST prefixes with
   train+OOS cluster-bootstrap-validated edge.
2. **`--expanded-denylist`.** Belts-and-braces; even if allowlist
   logic somehow bypasses, the denylist catches 12 OOS_NULL prefixes.
3. **`--min-minutes-to-close 60`.** Skip imminent-close adverse window.
4. **`--cancel-on-drift --drift-threshold-cents 3 --drift-min-age-minutes 15`.**
   Residual safety net for in-PERSIST drift. Lower priority because
   in-PERSIST drift is small (-0.5pp on the one observed fill, well
   under threshold). The cancel-on-drift earns its keep when a NEW
   in-PERSIST market starts drifting against the bid (e.g., late
   pitching change announcement, injury news during a tennis match).

## What to do with the 17 still-resting orders

`scripts/v10a/analyze_v1_live.py` shows 17 of 17 still-resting
orders are in OTHER prefixes. When the operator restarts v1 with
`--allowlist`, these resting orders WILL NOT be re-placed (the bot
only fires new orders on PERSIST prefixes), but they will continue
to sit on Kalshi until they fill or are cancelled.

The bot's existing `cancel_stale_resting(max_age_hours=...)` sweep
will clean these up after the configured TTL (default 120 hours
via `STALE_BID_TTL_HOURS`). Operator may want to lower the TTL
temporarily (e.g., set `STALE_BID_TTL_HOURS=24` in `.env` before
restart) to force a faster cleanup of the legacy non-PERSIST
resting orders. The bot's `cancel_all_resting` on SIGTERM will
ALSO clean them up if the operator does a Ctrl-C + restart with
the new flags.

## How to verify the restart worked

After restart, run `scripts/v10a/analyze_v1_live.py` again every
few hours. Expect to see:
- New fills concentrated in PERSIST prefixes (KXMLBGAME, KXATPMATCH,
  KXWTAMATCH; NFL and NCAAF off-season for now).
- Mean post-fill mid drift improving toward zero (or positive) over
  time, since OTHER prefixes are no longer firing.
- Per-fill realized P&L block populating once fills settle. Target
  per-fill mean: +2.5pp to +4.3pp on PERSIST prefixes (matches
  Becker OOS).

## Em-dash audit

(verified after write)
