# Round 21 (v16): Shadow-Logger Methodology Lock

**Date:** 2026-05-30. **Status:** LOCKED before any data collection.
**Authors:** diagnosis orchestrator + plan critic + methodology critic.
**Supersedes:** the DRAFT gates in `00-DIAGNOSIS-AND-COUNCIL.md` section 6. Where they differ, THIS document binds.

This locks the pass/fail design for the forward shadow study that measures whether Kalshi lags the sportsbook and whether the lag is harvestable at executable prices. It is the only F11-free test available (Becker has no orderbook ask; historical Kalshi orderbook is unavailable for settled markets). The gates are locked now, before any data, per project discipline (no threshold selected and evaluated on the same sample; no future-information feature before the simulated decision time).

## Question and decision

- **Q1 (lag exists?):** at a v14 fire (sportsbook home-implied moved >= 60bp over 3h), is the executable Kalshi price meaningfully better than the eventual closing line, i.e. does Kalshi lag?
- **Q2 (harvestable?):** can that lag be captured at an executable Kalshi price after fees, accounting for fills and adverse selection?

## Critic-driven changes from the draft

1. **Gate A reference is the CLOSING executable price, not +30m mid.** You cannot sell at mid, and the +30m mid double-counts the same settlement drift Gate B scores. (Methodology critic C1.)
2. **Gate B is restricted to the marketable-stale-ask mechanism.** Passive-maker fill P&L is NOT honestly computable from record-only book snapshots (it manufactures phantom fills on winners, the F11 trap). Resting-maker fills are logged but excluded from the binding gate. The only record-only-measurable harvest is a fast marketable bid that crosses a momentarily stale ask. (Methodology critic C2; plan critic C1.)
3. **Fill detection uses the trade tape, not point snapshots.** A passive bid fills only if the market traded at/through it between snapshots; a 5-minute point sample misses intra-interval touches. (Plan + methodology critics.)
4. **Minimum sample is a full MLB season (~120 nights), not 50-60.** At the live per-fire P&L variance (SD ~$1.0 to $1.5), 50-60 nights can only detect a LARGE edge; a true small edge would fail to clear zero and must be ruled UNDERPOWERED, not NULL. (Methodology critic H1.)
5. **night_id is the US/Eastern game date, not UTC.** A 22:00 ET game is the next UTC day; UTC bucketing would split a single night across clusters and inflate effective n. (Plan critic H3.)

## Logged fields

At each fire (T0): `yes_bid`, `yes_ask`, depth-at-touch (both sides), `book_empty` (explicit bool; a missing price is NEVER a silent NaN), `is_parity_derived`, sportsbook home-implied prob, the actual odds-snapshot timestamp (the-odds-api floors to the hour), 3h delta in bp, side, series prefix, game_id, `night_id` (US/Eastern game date), `week_id`, `minutes_to_commence`, fire UTC timestamp, `fire_seq` (dedup key on `(game_id, side, night_id)`; log first fire only as binding, later fires versioned).

Re-snapshots at T0+5m, +30m, and `close_time - 2min` (scheduled off each ticker's actual `close_time`, recorded at T0; NOT a fixed cadence, so the pre-finalization book is captured before settled-market books go empty). At each re-snapshot also record `last_price` / trade-tape touches in the interval, `minutes_to_commence` (assert > 0; drop post-commence rows), and `snapshot_status` in {done, missed, book_empty}.

Also log near-misses (|delta| >= 30bp with a `fired` flag) so the 60bp threshold can be re-evaluated later WITHOUT a second season of waiting. Storage is trivial.

## Locked gates

**Gate A (lag exists; binding).** Per fire, CLV = (executable exit at `close_time - 2min`) minus (executable entry at T0). Executable entry = `yes_ask` at T0 (the price a marketable taker pays). Executable exit = `yes_bid` at close (the price you could hit). Mid is banned on both legs. Require mean CLV > 0 with a **night-cluster** bootstrap 95% CI excluding zero AND a **week-cluster** CI that does not oppose it.

**Gate B (harvestable at executable price; binding, marketable-only).** A fire is "fillable" iff at T0 `yes_ask <= entry_limit` AND `depth-at-ask >= position size`. P&L is booked at the actual stale `yes_ask` paid, held to settlement, net of Kalshi fees. Require mean realized P&L over fillable fires > 0 with a night-cluster CI excluding zero. Resting-maker fills are logged but EXCLUDED from this gate (uncomputable unbiased record-only).

Both gates must pass.

## Sample, threshold, anti-leakage

- **Minimum N:** a full MLB regular season, target ~120 independent nights. A sign-correct CI straddling zero at season end is UNDERPOWERED-CONTINUE (one more season), not a pass and not a kill.
- **Threshold frozen:** the 60bp fire threshold was set on prior v12 data and is reused unchanged (leak-free on the disjoint forward sample). No threshold, side rule, or fill rule may be selected AND evaluated on the same forward nights. Any future threshold re-tuning requires a chronological split with a >= 1-night purge buffer.
- **No future-information feature** (closing odds, final score, settled status, post-T0 movement) may enter the T0 decision row.

## Pre-registered KILL (no third bite)

At full season end (n >= ~120 nights): if **Gate A's night-cluster CI upper bound <= 0** (the closing executable price is at or below the executable entry, i.e. no lag exists at executable prices), the lead-lag thesis is **DEAD**. Record-only logging stops, the v14 passive-maker rebuild is never built, and no further bite is authorized. A sign-correct-but-zero-straddling Gate A is the ONLY result that earns a second season. If Gate A passes but Gate B's marketable-fill gate fails, the HARVESTABLE thesis is dead permanently (lag is real but not capturable, the F11/v7-B phantom family).

## Smallest live confirmation after the gates pass (bridge the v14 taker never had)

If both gates pass, do NOT scale on the logged distribution alone (a real order moves the thin Kalshi book and may never fill at the logged price). Pre-registered next step: rest 1-contract real shadow orders at the logged limits for ~15 to 20 fires, log the actual fill flag + fill price, and require realized fill rate and per-fill P&L to land within the logged distribution before any capital past $5. This tiny-live-resting-order step is the only honest test of passive-maker harvestability and is deferred until Gate A passes.

## Staged build (decision-grade data fastest)

1. **Phase 1: entry-capture only.** Record the T0 book + sportsbook + delta + close snapshot, joined against v14's existing settlement records. This answers Gate A (does the lag exist) with minimal machinery.
2. **Phase 2: +5m/+30m re-snapshots + trade-tape touch detection.** Adds the marketable Gate B and convergence path.
3. **Phase 3 (only if Gate A passes):** the tiny-live-resting-order confirmation above.

## Coexistence with live v14 (record-only, no conflict)

The logger NEVER opens `LiveOrderManager` on the v14 state path and NEVER calls `place_live_order`. It writes its own `data/v16/shadow/*.parquet`, reads the same odds + orderbook endpoints, and runs as a SEPARATE process. The re-snapshot poller is a short-lived, idempotent, crash-safe "sweep due snapshots" script launched by Windows Task Scheduler off a persisted per-ticker schedule (NOT a long-lived in-loop timer; v14 sleeps off-hours). Reuse `src/kalshi_bot_v10/kalshi_orderbook.py` (handles one-sided books and parity derivation) rather than the daemon's thinner helper.

---

*Em-dash and en-dash audit: verified clean after write (no U+2014 or U+2013).*
