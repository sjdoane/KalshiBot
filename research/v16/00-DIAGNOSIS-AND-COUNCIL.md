# Round 21 (v16): Live-Edge Diagnosis + Council Decision

**Date:** 2026-05-30. **Author:** diagnosis orchestrator (read-only audit + 4-member council + verifier).
**Scope:** Audit both live bots (v1, v14), resolve the v14 execution-price question from real fills, and decide the highest-EV allocation of effort and the ~$100 cap over the next 4 to 8 weeks.
**Status of live behavior:** NOTHING was changed. No trades placed, no bot restarted, no config edited. This document is a diagnosis and a proposed plan that needs operator sign-off on the live-behavior items.

---

## 1. Bottom line: per-bot recommendation

| Bot | Verdict | Reason | Capital action |
|---|---|---|---|
| **v14** (MLB lead-lag taker) | **Negative-EV as built; keep running per operator directive, but do NOT add capital** | Pays the sharp line on immediate taker fills, captures none of the lag, fails its own gates G3/G4, live -27.6%. Its own 20%-of-cap drawdown kill will likely arm soon and auto-flatten it. | No new capital. Let the kill fire. |
| **v14 thesis** (Kalshi lags sharp books) | **UNPROVEN, not yet disproven; measure it F11-free** | The daemon never recorded the Kalshi book at entry, so the lag was never measured. Worth a cheap forward shadow test before any rebuild. | $0 (record-only logger). |
| **v1** (deep-favorite YES maker) | **Real but diluted edge; restrict to validated universe, then forward-confirm before scaling** | Validated on 5 sports prefixes; live it trades the broad universe (allowlist OFF), where aggregate OOS edge is ~0 and adverse drift concentrates in non-validated prefixes. | Restrict to allowlist; treat first ~$60 as forward fill-confirmation. |

The council was unanimous on the substance. The only tension is the operator directive "keep v14 running," which we honor while being transparent that the council views live v14 as negative-EV.

---

## 2. v14 execution-price diagnosis (definitive, from real fills)

The v14 backtest measured edge entering at the **Kalshi trade-print mid at T-3h** (a lagging price). The live daemon prices entry off the **sportsbook**-implied probability instead:

```
daemon.py:794-796
  target_implied = p_cur            # sportsbook consensus median, NOT Kalshi
  target_price   = target_implied + HAIRCUT(0.0007) + SAFETY_BUFFER(0.005)
```

The real Kalshi `yes_ask` is fetched only for drift-cancel (`daemon.py:290`), never for entry. `market_mid_at_placement` is set to `target_implied` (`daemon.py:843`), so the daemon does not even record the Kalshi book at entry. It is structurally blind to the lag it bets on.

Every real fill in `data/v14/v14_state.json` confirms the consequence:

| Evidence | Value |
|---|---|
| Fills at exactly `target_price` (= sportsbook+0.57c) | 14 of 14 (100%) |
| Fills showing price improvement (lag captured) | 0 |
| Placed-to-filled latency | ~90 ms (immediate marketable taker fills) |
| Settled bets | 14 (5 W / 9 L) |
| Live win rate | 35.7% (backtest projected 64.3%) |
| Realized P&L | -$3.53 on $12.80 cap (-27.6%) |
| Per-contract (41 contracts) | -8.6c (backtest projected +15c) |

**Mechanism, plainly:** v14 places a marketable limit at the sharp line + 0.57c, fills instantly as a taker at the sharp line, then holds to game settlement. That is a directional settlement bet at the sharpest available price plus a buffer plus fees. It is negative-EV by construction. The gap between the lagging Kalshi price and the sharp line was the entire claimed edge, and the daemon pays it away on entry. The live result is what that looks like.

Note: n=14 is small, so the statistics are weak, but the mechanism finding (zero price improvement on 14/14 fills, Kalshi book never read at entry) is a structural code defect, not a noisy sample.

---

## 3. v1 audit finding

- v1 buys YES at the market `yes_bid` in the 0.70 to 0.95 band as a passive maker and holds to settlement (`favorite_maker.decide`). This is a genuinely executable price. The phantom is the backtest's 100%-fill assumption (failure mode F11; the Becker dataset has no orderbook ask).
- The live launcher (`run_live_bot.ps1:152-164`) passes neither `--allowlist` nor `--expanded-denylist`. So v1 trades the broad Sports universe minus only a 10-prefix denylist. The 5-prefix validated allowlist is OFF, exactly as suspected.
- Validated edge (Becker post-Oct-2024 cluster bootstrap, train + OOS CIs exclude zero) exists ONLY on KXMLBGAME, KXATPMATCH, KXNFLGAME, KXNCAAFGAME, KXWTAMATCH. Full-universe aggregate OOS edge is ~0 (-0.23pp, CI spans zero).
- `research/v10a/20-v1-drift-by-prefix.md` is decisive: of 15 still-open fills, 14 were in non-validated prefixes, carrying the worst adverse drift (KXIPLFINALS -24.5pp, KXNBAPLAYOFFWINS -11pp). Only 1 fill was in a validated prefix (KXNFLGAME, -0.5pp). The allowlist would have prevented the catastrophic fills outright.
- v1 live realized P&L is -$0.47 (roughly flat) on ~$68.

**Read:** v1's edge is real on its validated universe but is being diluted to ~0 by trading everything. The fix (allowlist) is a one-line CLI flag already wired in, but it is a live-behavior change requiring operator-approved restart.

---

## 4. Council + verifier decision

Four-member council (Realist, Quant, Builder, Growth) plus a verifier, per the session rule for key multi-option decisions.

**Convergent decision:**
1. **Do NOT fund the current v14 taker.** All four agree it is negative-EV by construction (confirmed broken execution, not a test of the thesis).
2. **Measure the lag F11-free with a record-only shadow logger** on the existing v14 daemon. This is the cheap, high-value move that answers the one question 21 rounds never measured: does Kalshi lag the sportsbook, and is the lag capturable at executable prices.
3. **Restrict v1 toward its validated allowlist** as the live carry, with a forward fill-confirmation gate before scaling past the cap.
4. **Do NOT rebuild v14 as a passive maker (yet).** It is 16 to 30 hours of engineering on an unvalidated edge, and the passive-fill mechanics are adverse (see below). Build it only if the shadow data shows a persistent, executable gap.

**Verifier caught a real error:** the Growth member overstated a fifth "ITF tennis" lane. The cited `research/v10a/19-itf-fill-analysis.md` is a NULL-pending probe: its +0.9c/+1.9c per-fill figures assume a synthetic 100% fill rate (the doc itself flags 30 to 50% real-world), have zero realized P&L (settlement ~June 10), and ignore adverse selection at the 0.48 to 0.50 entry band where it bites hardest. ITF is the same F11 family, demoted to an optional shadow lane only, re-evaluated after its June 11 settlement follow-up. (Round 20 / v15 already NULL'd the related ITF-spread-near-close hypothesis.)

**Verifier refinement on passive-harvest mechanics (load-bearing for the rebuild path):** A Kalshi buy-limit at price P fills against the resting ask if ask <= P, else it rests. To harvest the lag you must buy YES cheap before Kalshi reprices up. Two cases dominate and both are bad: (1) if Kalshi's ask already sits at/below the sharp line, any bid that captures the move crosses and you are a taker paying the move away (v14's exact failure); (2) if you rest a bid below the current ask, you only fill when a seller crosses down to you, which in a rising-fair-value window is adverse flow. The one genuine exception: a stale-and-slow Kalshi book where the resting **ask itself lags** the sharp line, so a fast marketable bid at new fair value crosses the stale ask and captures the gap. That is a liquidity-taking fill against a slow market maker, fleeting (seconds), and is exactly what the shadow logger must measure. So a RESTING passive quote cannot reliably harvest the lag; only fast marketable execution against a momentarily stale ask can, if it exists at all.

---

## 5. Why there is no retrospective backtester for this

Task 3 asked for a minimum point-in-time replay backtester. It cannot resolve the executable-price question, because:
- The Becker dataset has no orderbook ask at trade time (F11).
- Historical Kalshi orderbook is unavailable for settled markets (the API returns an empty book and silently ignores `?ts=`).

So there is no historical source of the executable Kalshi price at the moment a sportsbook move fired. The **forward shadow logger is the minimum viable replay**: it captures, point-in-time and going forward, exactly the executable prices a retrospective replay would need. This is the honest substitute and the only F11-free path.

---

## 6. Pre-registered gates (DRAFT, pending methodology critic)

These are the shadow-logger gates. They are DRAFT until a methodology critic signs off (next step), and they are locked BEFORE any data is collected, per project discipline. No threshold may be selected and evaluated on the same sample.

At each v14 fire (T0), log: Kalshi yes_bid, yes_ask, mid, top-of-book depth, `book_empty` flag; sportsbook home-implied prob; the 3h delta in bp; side; series prefix; game_id; **night_id (cluster key)**; fire timestamp (UTC). Re-snapshot Kalshi yes_bid/yes_ask at T0+5m, +30m, and at `close_time - 2min` (before finalization, since settled-market books return empty). Record settlement outcome.

- **Gate A (CLV):** mean (Kalshi mid at +30m minus executable entry at T0) > 0, with a **night-cluster-robust** bootstrap CI that excludes zero. "Executable entry" = yes_ask if taking, yes_bid if posting passively. Measures whether the lag is real.
- **Gate B (settlement EV):** realized P&L per fire at the **passive fill price**, with realistic fill-or-no-fill modeling (log a fill flag at each re-snapshot), > 0, with a night-cluster-robust CI that excludes zero. Measures whether the lag is harvestable at executable prices.

Both must pass. The fill-or-no-fill flag is the single most important field; without it, Gate B is unmeasurable and we re-run v14's mistake. Cluster unit is the **night** (same-night MLB games share weather, lineup, and line-move shocks). Minimum sample ~50 to 60 independent nights, which at 1 to 2 fires/night is roughly 8 to 12 weeks, likely running past the MLB regular season. This is a season-length research project, not a 4-week one.

---

## 7. Value-per-dollar data shopping list

| Item | Cost | Value | Verdict |
|---|---|---|---|
| Forward Kalshi shadow logging (own API READ key) | $0 | The only F11-free measurement of the lag | DO IT |
| the-odds-api free tier (current + hourly /historical) | $0 (~13.5k credits left, ~22 months) | Already feeds v14; sufficient for the sportsbook reference | KEEP |
| the-odds-api paid tier (more books, finer granularity) | $-- /mo | Marginal; free tier already gives a consensus median | DEFER until lag is confirmed real |
| Becker parquet (research) | $0 (owned) | No orderbook ask (F11); cannot price executable entry | RESEARCH ONLY |
| Any paid historical Kalshi orderbook feed | unknown | Would enable a true retrospective backtest | INVESTIGATE COST ONLY IF lag confirmed |

No paid subscription is justified until the free shadow logger shows the lag exists.

---

## 8. Exact changes required before risking more money

- **v14:** do not add capital. No code change needed to keep it running per the operator directive; its drawdown kill is the safety mechanism. A rebuild to passive-maker entry is NOT authorized and is not recommended until shadow data justifies it.
- **v1 (needs operator-approved restart):** restart with `--allowlist` (and `--expanded-denylist` as belts-and-braces), keeping `--cancel-on-drift`. Add `--min-minutes-to-close 60` per the drift analysis. After restart, do NOT scale past the current cap until a forward fill-confirmation gate passes: over ~30 to 40 settled allowlist fills, per-fill realized mean must land in the +2.5pp to +4.3pp band (Becker OOS) with adverse drift no worse than the -4.9pp already observed. Only then scale toward $100.

---

## 9. Honest reasons this might still fail

- **The lag may not exist at executable prices.** Kalshi market makers may already track the sharp line before retail can passively enter. If so, Gate A fails and the lead-lag thesis is dead (the v7-B / F11 phantom family, hit 8+ times on this project).
- **The lag may be real but uncapturable.** It may live only in fleeting marketable fills against a stale ask, with adverse selection eating it (you fill the losers, miss the winners). Gate B is designed to catch exactly this.
- **v1's validated edge is F11-suspect.** The +3 to +4% is what historical fills earned, not necessarily what a new retail bid fills at. The live -4.9pp adverse drift is the warning sign. The forward fill-confirmation gate exists because the backtest alone is not sufficient.
- **At $100, no option's dollar profit is material.** v1 at best yields single-dollar amounts per month. The real product of the next 8 weeks is a validated, executable edge that could justify a larger future deployment, not near-term income.

---

## 10. Sequenced action plan

1. **SHIP FIRST (engineering, ~4 to 6 hours, no live change, record-only):** the v14 shadow logger. Separate module, separate state file (`data/v16/shadow/*.parquet`), separate ~5-min poller process for the +5m/+30m/close re-snapshots (NOT an in-loop timer; v14 sleeps off-hours). Record `book_empty` so dropped rows are auditable, never silently NaN. Reuse `src/kalshi_bot_v10/kalshi_orderbook.py` (already parses both sides).
2. **LOCK GATES (methodology critic) before any data is used:** run a plan critic on the architecture and a methodology critic on the Gate A / Gate B design above.
3. **OPERATOR DECISION (live behavior):** approve the v1 allowlist restart. This is the highest-EV use of the ~$100 now.
4. **KEEP RUNNING per directive:** v14 stays live until its own drawdown kill arms. Do not manually kill. Shadow logger keeps collecting through and past it.
5. **DO NOT BUILD:** the v14 passive-maker rebuild. Revisit only if shadow data clears Gate A.
6. **ITF:** optional 5th shadow lane only; re-evaluate after its ~June 11 realized-P&L follow-up.

---

*Em-dash and en-dash audit: verified clean after write (no U+2014 or U+2013).*
