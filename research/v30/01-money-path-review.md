# v30 live_pilot.py money-path review (2026-07-03)

Reviewer: money-path code review agent. Scope: scripts/v30/live_pilot.py against
kalshi_client.py, v29/arb_sentinel.py, v28/live_rt_read.py, and the verified V2
order facts from live v1 trading (June 2026). Verdict at bottom.

## Side and price mapping traces (hunt item 1)

All five call paths traced. The V2 mapping itself is CORRECT in all five. The
defects are in rounding, caps accounting, and failure handling, not in the
bid/ask translation.

(a) armA YES leg: scan_event leg "YES TK@0.44" carries the YES ask. Code sends
side "bid" at 0.44 (place_ioc line 101). BUY YES = bid at YES price. Correct.
IOC at the detected ask crosses.

(b) armA NO leg: scan_event leg "NO TK@0.51" carries the NO ASK (no_ask_dollars,
arb_sentinel line 87), i.e. the NO cost. Code sends side "ask" at
round(1 - 0.51, 2) = 0.49. BUY NO = ask at YES-equivalent price. Correct
mapping. round(1 - 0.51, 2) = 0.49 exactly (float error ~1e-16, below the
rounding boundary), so plain 2-decimal inputs are safe. Subpenny inputs are NOT
safe: see finding H2.

(c) armA unwind: excess on the YES leg gives sell_side "no", priced at
yes_bid_dollars; place_ioc maps "no" to side "ask" at the bid. On the V2
events/orders book there is no sell action, only bid/ask on the YES side, and
Kalshi nets YES and NO positions per market: buying NO at YES-equivalent
yes_bid while holding YES collapses the pair to $1 collateral, netting receipt
of yes_bid per contract. This EXITS the position (it cannot double it; the
signed position decreases). Symmetrically, excess NO gives sell_side "yes" =
side "bid" at yes_ask, which nets against the held NO. Both directions correct
and both cross (ask priced at the standing bid, bid priced at the standing
ask).

(d) armB YES fire: decided YES, ask <= 0.94, sends side "bid" at the ask.
Correct, crosses.

(e) armB NO fire: cost = 1 - yes_bid, yes_px = round(1 - cost, 2) = bid, sends
side "ask" at the bid. The question "should it price at the NO ask equivalent
instead of derived-from-bid" resolves cleanly: on a complementary two-sided
book the NO ask equals 1 minus the YES bid by identity, so derived-from-bid IS
the NO ask equivalent. An IOC ask at the standing bid crosses and fills at the
resting price. The double negation round-trips: for 2-decimal bids
round(1-(1-bid), 2) == bid exactly. For subpenny bids (0.075) the round goes
DOWN (0.07), which is the aggressive direction for an ask: still crosses,
still fills at the resting 0.075. Safe.

## IOC price semantics (hunt item 2)

Side bid: price is the max YES price paid; pricing at the detected ask crosses
and fills at the resting ask (price-time priority pays the resting price).
Side ask: price is the YES floor; 1 - max NO cost; pricing at the detected bid
crosses. Every fire in the file prices to cross at detection time. The only
rest/miss risk is the rounding defect (H2) and normal market movement between
detect and send, both of which produce a miss (no fill), not a worse fill.
IOC limit semantics bound the damage: a fill can only be at the limit or
better.

## Findings

### C1 (CRITICAL): spent_today reconstruction undercounts NO buys by up to 13x, daily $60 cap is not enforced

main() lines 270-278 rebuilds spent_today as fill_count * body["price"]. The
body price is the YES price. For any NO buy (side "ask") the actual cash out
per contract is 1 - price, not price. Example: an armB NO fire at yes_bid 0.07
(cost 0.93), 32 contracts = $29.76 actual new exposure, reconstructed as
32 * 0.07 = $2.24. On a NO-heavy day the $60 daily cap admits roughly $60/0.07
= ~$800 of real exposure before halting. The within-run accumulators (arm_a
line 169, arm_b line 257) are correct in cost terms; only the cross-run
reconstruction is wrong, and it is the one that enforces the daily cap across
the 5-minute schedule.

FIX: log the true per-contract cost on every order row (e.g. add
"cost_per_contract": yes_price if buy_side == "yes" else round(1 - yes_price, 2)
and "buy_side": buy_side to the row in place_ioc), and reconstruct
spent_today from fill_count * cost_per_contract. Exclude tag "armA_unwind"
rows (those are exits, not new exposure; today they overcount spend, which is
conservative but wrong in the other direction).

### C2 (CRITICAL): any exception between leg1 fill and the unwind leaves a naked leg with no record and no retry

Three unprotected windows:

1. place_ioc line 113: cli.post can raise (KalshiHTTPError, httpx timeout,
   network). If leg1 filled and leg2's post raises, the exception propagates
   out of arm_a and main crashes: no unwind attempt, no order_ack row logged
   for leg2 (the row is only written after a successful post), and the next
   run has no idea leg1 is naked.
2. arm_a line 176: the unwind market fetch ab.get_json is NOT inside a
   try/except (the only try in arm_a wraps the series scan at line 137). A
   fetch failure crashes the script after both legs are placed, skipping the
   unwind entirely.
3. Timeout-after-accept: httpx timeout is 30s; if the exchange accepts the
   order but the response times out, the order EXISTS but nothing is logged,
   so caps, basket counts, and fired sets all miss it. client_order_id is
   never used for reconciliation. (The tenacity retry is 429-only and re-sends
   the same client_order_id, so 429 retries are idempotent and fine.)

Max bounded loss per naked leg: the excess contracts settle worthless, up to
the full one-leg cost, bounded by basket sizing at roughly $40; with 2 baskets
per day, roughly $80/day worst case, silently.

FIX: (i) in place_ioc, log the order_intent row BEFORE posting and log an
order_error row on exception; (ii) wrap each leg placement and the unwind
fetch in try/except inside arm_a; treat a leg exception as fills-unknown, then
reconcile via GET /portfolio/orders or /portfolio/fills filtered by the known
client_order_id before deciding fill counts; (iii) never let an exception skip
the unwind branch once any leg has been sent.

### C3 (CRITICAL): the unwind is fire-and-forget; a missed unwind IOC leaves the leg naked forever

arm_a line 181 places the unwind IOC and never checks its ack. If the market
moved or the fallback price (0.01/0.99 on a missing quote) does not cross, the
IOC fills 0, Discord still reports "UNWIND", nothing is written to the
positions LEDGER for arm A at all, and no subsequent run retries. Same bounded
loss as C2 (up to ~$40 per event). Also the unwound-excess cost paid on the
overfilled leg is never added to spent (line 169 counts only min(f1, f2)), so
the daily cap misses that real exposure.

FIX: check fill_count on the unwind ack; if unwound < excess, write a
"armA_naked" row to LEDGER with ticker, side, remaining count; at the top of
every run, before scanning, re-attempt unwind of any armA_naked remainder at
the fresh bid/ask (bounded retries, then Discord CRITICAL alert). Add the
excess leg cost to spent.

### H1 (HIGH): arm B bricks itself; dry-run rows poison both the concurrent count and the one-fire-per-market set

arm_b lines 189-192: open_ct counts ALL armB_open rows ever, closed counts
armB_settled rows, and NOTHING in this script (or any other) ever writes
armB_settled. After 3 armB_open rows exist, arm B is disabled for the life of
the file. Worse, line 253 "if got > 0 or dry" logs an armB_open row on EVERY
dry trigger with n=0, and dry is the DEFAULT (no LIVE_ARMED file). So the
pilot can permanently consume all 3 concurrent slots and mark markets as fired
before a single live order is placed. Fails closed (no money lost) but
violates the charter and silently kills the strategy; also "one fire per
market lifetime" is consumed by dry rows, so a live fire on a genuinely
decided market is blocked.

FIX: filter dry rows out of both fired and open_ct (r.get("dry") is not True),
and count concurrency from truth instead of a settled row nobody writes:
GET /portfolio/positions and count nonzero KXRT positions, or treat an
armB_open row as closed once its market's close_time has passed (fetchable
from the trigger row or a market GET).

### H2 (HIGH): price rounding and f"{x:.2f}" formatting can un-cross an IOC; in arm A that converts directly into unwind churn

Two layers:
1. round(1 - px, 2) with subpenny inputs rounds in an unpredictable direction:
   round(1 - 0.485, 2) = 0.52 (true 0.515), an ask floor ABOVE the crossable
   level, so the NO leg IOC misses. Subpenny quotes are real on this book (the
   v28 band constant is 0.955).
2. f"{yes_price:.2f}" uses round-half-even on the binary float:
   f"{0.955:.2f}" = "0.95", a bid BELOW a 0.955 ask, IOC miss.

A miss alone loses nothing (IOC limit semantics). But in arm A a one-leg miss
plus a one-leg fill forces an unwind: pay the spread plus taker fee on the
filled leg, repeatable up to 2 baskets/day. It also burns the daily basket
budget on non-fills (see L4).

FIX: do all price math in integer cents. For side "bid" send
ceil(price_cents)/100 (rounding a bid UP is safe: it fills at the resting
ask). For side "ask" send floor(price_cents)/100 (rounding an ask DOWN is
safe: it fills at the resting bid). Format from the integer:
f"{cents//100}.{cents%100:02d}" or f"{cents/100:.2f}" after integer rounding.

### M1 (MEDIUM): no concurrency guard across scheduled runs

A 5-minute schedule plus a slow run (arm_a walks 8 series over the network,
each with retries up to 60s backoff on 429) can overlap. Two processes both
read orders.jsonl before either writes, both see the same spent_today and
basket count, and both fire: daily cap and basket cap can double. FIX: a
lockfile in data/v30 (O_CREAT|O_EXCL, stale after ~10 min) or set the
scheduled task to "do not start a new instance".

### M2 (MEDIUM): self_trade_prevention_type value "taker_at_cross" is unverified

The verified facts say the field is REQUIRED but do not pin the accepted enum.
If the value is rejected, every live order 400s (fails closed, zero fills,
strategy silently dead; the KalshiHTTPError also triggers C2 crash paths).
FIX: before arming, confirm the exact value against a recorded working v1
order body, or place one 1-contract probe order at a non-crossing price via
the same code path and inspect the response.

### M3 (MEDIUM): one corrupt line in orders.jsonl halts the pilot permanently

today_rows/all_rows json.loads every line with no guard. A crash mid-append (a
real possibility given C2) leaves a partial line that raises
JSONDecodeError in main() line 271 on every subsequent run, forever. Fails
closed, but the pilot silently stops while positions may still need the C3
unwind retry. FIX: wrap per-line parse in try/except, log and skip bad lines.

### M4 (MEDIUM): balance and caps are not refreshed between arms and reconstruction trusts limit price, not fills

arm_b receives the pre-armA balance (main line 295 passes bal fetched before
arm_a spent), overstating 15 pct-of-balance headroom slightly. Reconstruction
also uses the limit price rather than average_fill_price from the ack (fills
can be better than limit); for the cap this is the conservative direction, so
LOW impact, noted for completeness. FIX (optional): use average_fill_price
when present.

### L1 (LOW): ES/fee edge condition verified OK

At the 0.94 boundary: taker fee = ceil(0.07 * 100 * 0.94 * 0.06)/100 = $0.01
per contract; net-if-right = 1 - 0.94 - 0.01 = +$0.05 >= +2c. The charter
claim holds at the worst admitted price; at lower prices the fee grows slower
than the gross. Arm A's edge >= 0.02 gate already embeds worst-case per-leg
taker fees via scan_event's taker_fee (per-contract ceil, conservative). No
change needed.

### L2 (LOW): Settings() and .env are re-loaded on every Discord call

discord() constructs Settings() per message. Wasteful, and a transient .env
read failure suppresses the alert (caught blind). Cache the webhook URL once
at startup.

### L3 (LOW): relative paths depend on cwd

sys.path inserts, data/v30, and the ARMED/STOP sentinels are cwd-relative. A
scheduled task started with the wrong working directory quietly runs DRY
(ARMED not found) and writes ledgers to the wrong place. Fails safe, but set
the task working directory explicitly and consider anchoring paths to
os.path.dirname(__file__).

### L4 (LOW): a zero-fill basket attempt consumes one of the 2 daily baskets

baskets_today counts armA_leg1 order_ack rows regardless of fill_count.
Conservative (caps exposure), but combined with H2 misses it can spend the
daily budget on nothing. Optional: count only rows whose ack fill_count > 0.

### L5 (LOW): EXPIRY and daily bucketing mix date.today() (local) with ET dates

Harmless on a machine in US time zones; note only.

## Verdict (superseded by re-review below)

NOT SAFE TO ARM. Blocking: C1, C2, C3, H1, H2. M2 must be verified (one probe
order) before the first live fire. M1 and M3 should ship in the same patch.
The V2 side/price mapping itself, including the unwind direction and the
armB NO double negation, is correct on all five paths.

---

# Re-review of the rewrite (2026-07-03)

Scope: verify each original finding is genuinely fixed in the rewritten
live_pilot.py and hunt for NEW money-losing defects introduced by the rewrite.

## Finding-by-finding verification

C1 spent accounting: FIXED. cost_per_contract_c is the buyer's own-side cost
on every path (armA legs pass c, the raw side cost; armB passes cost_c; the
unwind passes 100-bid or ask but armA_unwind is excluded from the sum, which
is correct since unwinds are exits, not new exposure). spent_today_cents()
reconstructs fill_count x cost_per_contract_c from order_ack rows only, and
both arms re-read it from the file immediately before sizing, so within-run
acks are counted. Excess leg fills that later get unwound remain counted as
gross new exposure: conservative and correct.

C2 intent-before-POST and wrapped calls: PARTIALLY FIXED. Intent rows now
precede the POST, the POST and the unwind fetch are wrapped, and ambiguous
failures write reconcile_needed rows with the client_order_id. But the
reconciliation is LOG-ONLY and the code then PROCEEDS AS IF FILLS WERE ZERO.
That residual gap is blocker B2 below.

C3 unwind verification and retry: MOSTLY FIXED, but the fix introduced a new
partial-fill defect that can OPEN A REVERSED POSITION. Blocker B1 below.

H1 arm B counting: FIXED. fired and concurrency read only non-dry armB_open
rows with n > 0; dry mode no longer writes armB_open at all (got is 0 on the
dry stub and the log is gated on got > 0). Concurrency counts rows whose
market status is not settled/finalized via a live fetch, unknown counts as
open (conservative). Rows are never pruned so the per-run status fetches grow
with lifetime fires, bounded and acceptable for a pilot.

H2 integer-cent math: FIXED for exact-cent quotes; residual subpenny nuance
noted as M-R1 below. The price string f"{yes_cents/100:.2f}" round-trips
exactly for all integer cents 1..99. The 1..99 clamp in place_ioc is sane.
All five mapping paths re-traced on the rewrite: armA YES leg (bid at c),
armA NO leg (ask at 100-c), armB YES (bid at ask_c), armB NO (ask at bid_c),
unwind both directions (held YES: ask at bid_c, cost 100-bid; held NO: bid at
ask_c). All correct and all price to cross.

M1 lock: FIXED (9-minute staleness, removed in finally, the early-return on a
fresh lock happens before the try so it cannot delete the other instance's
lock). The create is not O_EXCL so two simultaneous starts have a tiny
check-then-write race; negligible at a 5-minute cadence (L-R3).

M2 self_trade_prevention_type: VERIFIED INDEPENDENTLY. "taker_at_cross" is
the exact value in v1's live-working order body,
src/kalshi_bot/strategy/live_order_manager.py lines 43 and 408, with an
in-code note that the field is required and taker_at_cross is the documented
default. Cleared.

M3 tolerant jsonl reads: FIXED (rows() skips undecodable lines).

M4 (stale balance between arms): unchanged, still LOW, acceptable.

## NEW blockers introduced or remaining

### B1 (CRITICAL, new): partial unwind fill over-unwinds on retry and opens a REVERSED position

unwind_leg returns fill_count(ack) >= count. On a PARTIAL fill (say excess 5,
IOC fills 3) it returns False and the caller logs armA_naked with the FULL
count 5, while the true residual is 2. retry_naked then fires unwind_leg for
5 again. Holding 2 YES and buying 5 NO nets through zero into a NEW 3-lot NO
position that nothing tracks: if that retry fills 5, unwind_leg returns True,
armA_naked_resolved is logged, and the reversed 3-lot position is invisible
forever. Its cost is also excluded from spent (armA_unwind tag). Same defect
fires on the first attempt inside arm_a (naked row logged with full excess
after a partial unwind). Bounded per event by the excess size, but it is a
silent directional position taken with real money.

FIX: make unwind_leg return the filled count (int). Callers compute
remaining = count - filled and log armA_naked only with the remaining count.
retry_naked: filled = unwind_leg(...); if filled >= count log resolved; elif
filled > 0 log resolved for the old row plus a fresh armA_naked with the
remainder; never re-submit more than the tracked remainder.

### B2 (HIGH, residual of C2): reconcile_needed is log-only; the code assumes zero fills and acts on that assumption

Three concrete money paths when a POST raises after the exchange accepted
(timeout-after-accept, 5xx-after-write):

1. armA: the errored leg's real fill is invisible, fill treated as 0. If the
   other leg filled, the code unwinds the OTHER (healthy) leg, leaving the
   errored leg's REAL position naked and unrecorded: the protection logic
   actively creates the naked leg it was built to prevent.
2. armB: an errored-but-filled fire writes no armB_open row, so the market is
   NOT in fired; the next run can fire the SAME market again: double
   exposure, one-fire-per-lifetime violated, and neither fill is in spent.
3. spent_today_cents misses every such fill, weakening the daily cap.

FIX (fail-closed, small): in main, before trading, scan ORDERS for
reconcile_needed rows with no matching reconcile_resolved row (match on
client_order_id); if any exist, Discord-alert and return 0, placing no new
orders until resolved (operator resolves manually, or a reconciler queries
GET /portfolio/fills for the client_order_id and writes reconcile_resolved
with the true fill count, feeding it into spent and, for armA, into the
naked-leg ledger). Additionally in arm_a: if either leg ack contains
"error": True, skip the automatic unwind decision entirely and log an
armA_reconcile row; unwinding on assumed-zero is worse than waiting one
operator cycle.

## Non-blocking notes on the rewrite

M-R1 (MEDIUM): cents() rounds subpenny quotes to the NEAREST cent, not
directionally. Subpenny levels exist on this book (the v28 0.955 band). A
buy-side round-down (e.g. 0.045 to 4c against a 4.5c ask) un-crosses the IOC:
no fill, and in arm A a one-leg miss now routes through the unwind/naked
machinery, so the cost is bounded churn (spread plus fee), not an untracked
naked leg. Preferred: ceil the crossing price for bids and floor the
YES-equivalent for asks; taker fills execute at the resting price, so the
directional rounding costs nothing.

L-R2: retry_naked runs only in live mode. While disarmed or under --dry, a
real naked position from a prior live run sits unmanaged (one Discord alert
at creation). Acceptable, but the operator should know disarming freezes
naked-leg recovery, not just new fires.

L-R3: lock file check-then-write race (no O_EXCL). Negligible at this
cadence.

L-R4: bal_c fetched once; arm B sizes against pre-armA balance. Bounded by
the caps, LOW.

## Re-review verdict

NOT SAFE TO ARM YET. Two blockers, both small patches:
B1 (partial unwind over-unwind reverses the position) and B2 (unresolved
reconcile_needed must fail closed and must suppress the assumed-zero unwind).
Everything else from the original review is genuinely fixed, M2 is verified
against v1's live body, and no other new defect was found. With B1 and B2
patched, this file is safe to arm within the charter caps.
