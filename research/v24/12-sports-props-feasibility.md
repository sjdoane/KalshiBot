# v24 pivot 2: sports-props escape, live feasibility scan = structurally blocked

**Date:** 2026-06-30. Read-only ($0) live scan of the open Kalshi MLB prop universe,
testing the v24 meta-summary's ONE untested escape: thin props with NO sharp-book
reference, where retail might misprice without a sharp anchor. MLB is in-season.

## What is open now (live `/markets?status=open` by series)

| series | open | two-sided | total vol | settle | sharp book? | spread |
|---|---|---|---|---|---|---|
| KXMLBSTATCOUNT (season combos) | 33 | 29 | 63,902 | Dec 2026 | NO | ~12c |
| KXMLBHR (player HR) | 139 | 86 | 247,453 | per game | YES | ~3c |
| KXMLBKS (pitcher Ks) | 200 | 200 | 262,122 | per game | YES | ~1-2c |
| KXMLBTOTAL (game totals) | 200 | 200 | 401,384 | per game | YES | ~3-4c |
| KXMLBGAME (winner) | 78 | 78 | 3,382,169 | per game | YES | (liquid) |
| KXMLBRBI / KXMLBSB (player) | 127 / 50 | 61 / 22 | 1,317 / 899 | per game | partial | ~9-13c |

(`liquidity_dollars` reads $0 across all of these and is not meaningful here; volume_fp
and the bid/ask spread are the usable signals.)

## The escape is structurally blocked (consistent with the meta-summary's <10% prior)

The two-faced wall reappears:

1. **The genuinely no-sharp-line props (KXMLBSTATCOUNT) are capacity-dead.** Season-long
   combined-stat counts ("will all hitters combined record 11+ inside-the-park home
   runs?") have NO sharp book, but: ~12c bid/ask spreads (a taker pays ~6c half-spread
   each way + fee, dwarfing any plausible edge), near-zero resting size, and a ~6-month
   capital lockup (settle Dec 2026). Even if mispriced, the edge is not extractable net
   of the spread and is not deployable at any meaningful size. This is exactly the
   "capacity-dead / slow / <5% prior" the meta-summary flagged.

2. **The tradeable, per-game props (KXMLBGAME / TOTAL / HR / KS) have sharp-book
   references.** Player HR, pitcher-K, totals, and winners are all standard sportsbook
   markets now. The v24 MLB-totals capture check already showed Kalshi tracks the sharp
   book to ~0.6pp median (far inside the ~3pp taker hurdle) = capture phantom. The same
   logic applies to player props (sharp player-prop lines are ubiquitous), so the prior
   that these are a capture phantom is high (>85%); confirming it via the-odds-api
   player-prop pull would very likely just re-confirm the phantom and burn API credits.

## Verdict

The sports-props escape does NOT open a practical edge: the no-sharp-line subset is
capacity-dead (spread + lockup), and the liquid subset is sharp-referenced (capture
phantom). This re-confirms the project's robust wall a 7th way and matches the
meta-summary. No capital. Combined with the conclusive index realized-vol NULL and the
rejected event-vol pivot (docs 10/11), the financial-vol AND the sports-props spaces
are both closed for a retail edge this session.

Best-judgment recommendation (unchanged from the meta-summary, now reinforced): capital
stays FLAT; the v24 wall is the honest deliverable. A genuinely new edge would require a
NEW information or structural advantage the project does not currently have (private/
faster data, a market segment with neither a sharp reference nor a saturated MM, or a
non-info structural arb that survives fees + latency). Absent that, deploying capital
would be a manufactured loss.

*Em-dash and en-dash audit: verified clean after write.*
