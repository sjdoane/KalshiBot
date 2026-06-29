# Kalshi Edge Research: Autonomous Cross-Disciplinary Hunt (NEW DIRECTION)

You are picking up Project Kalshi in a fresh window. The repo CLAUDE.md and the memory files (especially `project_kalshi.md`) have already auto-loaded; read `project_kalshi.md` top entries before doing anything else. This prompt sets your mission and the loop. Honesty is the whole point: a NULL is a SUCCESS here because it saves capital and adds knowledge. Do not manufacture an edge to finish. A long stretch of honest nulls is a legitimate, reportable outcome, not a failure of yours.

## Situation you are inheriting (respect it, do not relitigate it)

- The live bot v1 (deep-favorite YES-maker + NO-underdog maker) is STOPPED. Capital is FLAT. ~$200 bankroll is available but NO live capital goes anywhere until an edge is validated.
- The entire MAKER-quoting family is EXHAUSTED. v1 was break-even live (75-76% win rate == 76% price-implied breakeven, alpha ~0). The v23 Becker train+OOS double-NULL killed the NO-underdog arm and crypto/Other maker. The recurring killer is ADVERSE SELECTION / fill-volume toxicity: a resting maker fills more on exactly the books that move against it (corr(event_nfills, event_mean) = -0.15), so an idealized event-mean backtest (+6.6pp) is a mirage and the fill-weighted truth straddles zero. Read `research/v23/02-direction-b-NULL.md` and `research/v23/01-direction-a-results.md`.
- Project tally so far: ~11 NULLs + 1 confirmed PHANTOM across maker-quoting, ML (LightGBM/TabPFN/Kronos), LLM-as-forecaster, lead-lag/Granger, cross-venue Polymarket, and arbitrage locks.

### Read these FINAL-VERDICT / load-bearing docs FIRST to avoid dead ends

Skim before proposing anything. These tell you what is already dead:
- `research/v23/00-methodology-lock.md`, `01-direction-a-results.md`, `02-direction-b-NULL.md` (maker family exhausted; adverse-selection and worst-case-fee mechanism explained)
- `research/v10a/FINAL-VERDICT.md` (F11 failure mode; Becker schema phantom)
- `research/v9/FINAL-VERDICT.md` (LLM-as-forecaster NULL; gate-regime mismatch)
- `research/v8/FINAL-VERDICT.md` (confirmed live PHANTOM, 8/8 lost)
- `research/v6/FINAL-VERDICT.md`, `research/v5/FINAL-VERDICT.md`, `research/v4/FINAL-VERDICT.md`, `research/v3/FINAL-VERDICT.md` (ML / external-feature / Polymarket-fade NULLs)
- `research/key-findings.md`, `research/lessons-learned.md`, and `research/v22/fee_table.json` + `research/v22/fee_table_research.md` (the dated maker-fee table; fees are series-AND-date specific with a dual-run envelope, do NOT model them from memory)

## The known failure modes you must design around

- **F11 (Dataset Schema Phantom):** the Becker dataset has NO orderbook bid/ask at trade time. A backtest can show an edge EXISTED in realized fills but cannot prove a NEW order would CAPTURE it. Every gate must audit the schema and prefer a TAKER mechanism (you cross the spread on demand at a real marketable price) so capturability is a real marketable order, not a backtest fill a new order cannot reproduce.
- **Stale-price phantom:** using `last_price_dollars` / post-settlement prints as an execution proxy fabricates fake edges. Use real execution prices only.
- **Gate-regime mismatch:** do not borrow a numeric threshold from a paper measured on a different regime (e.g. hard 0.20-0.80 markets) and apply it to confident favorites.
- **Adverse selection / fill toxicity:** the maker killer. Avoid any passive-resting mechanism unless you have a genuinely new, stated reason it escapes this.
- **Overfit at small n / fee underestimate:** never net results against a remembered or assumed fee. The fee is series-AND-date specific (`research/v22/fee_table.json` has FOUR formula variants: zero, flat $0.0025, `ceil(1.75*P*(1-P))` cents, and a possible `ceil(0.875*P*(1-P))` half-multiplier) with a `fee_low`/`fee_high` dual-run envelope and a maker-fees-did-not-exist-before-2025-05-13 cutoff. A NEW retail entrant must be priced at the WORST-CASE applicable fee. Do not assume "flat ~1c"; look up the row for your series and dates and run both envelope ends.
- **Multiple-testing / garden of forking paths:** a loop that tries many ideas WILL eventually pass one by chance. Track how many distinct hypotheses and strata you have screened, and treat a single marginal pass after many tries as suspect. Pre-register the exact strata you will test; do not expand the strata set after seeing data.

## DO NOT re-tread (these are dead; a new idea must differ on TARGET, REGIME, FEATURES, or ROLE)

- The maker-quoting family in any form (deep-favorite, underdog, mid-bias non-sports cells, band inversion, new-listing cold-start, longshot NO-maker which INVERTED to -1.94pp). No more band/cell scans within passive making.
- From-scratch directional outcome forecasters scored on Brier vs the market on liquid efficient-favorite SPORTS contracts (LightGBM, TabPFN, Kronos, NN, LLM-as-forecaster all nulled this exact shape).
- Cross-venue Polymarket-Kalshi arb / fade (nulled; fires were 100% stale cross-listings, median 62pp phantom gap).
- Intra-exchange sum-to-1 / ladder-lock arbitrage for retail capture (commoditized, fee-dead, bot-claimed in seconds).
- Crypto sub-2pp maker edge (real but the fee eats it; HFT latency wall).
- News/sentiment speed-race on politics/mention markets (pure latency race; overlaps killed ML/LLM).
- Mohanty Kalshi-macro -> crypto-vol (reproduces but its venue is Deribit, out of scope).

## The autonomous loop you will run

Run this as a disciplined, honest loop. Use the multi-agent workflow (plan critic before methodology lock; methodology critic after lock, before data pull; code reviewer after each engineering milestone) and an adversarial-critic pattern at the verdict. The critic's job is to KILL your idea; reward yourself for surviving it honestly, not for passing.

1. **PROPOSE** one idea. Cross-disciplinary (quant-finance, ML, external data, or structural). State an explicit HONEST PRIOR (a probability it survives) and ONE line on why it might escape the project's known failure modes (which one, and how). If the prior is below ~10%, say so and prefer a better idea.
2. **LOCK pass criteria BEFORE pulling or inspecting any data.** This is non-negotiable and is what prevents a false positive (the prior nulls + phantom came partly from weak pre-registration). Write a methodology-lock doc under `research/<vNN>/00-methodology-lock.md` that names: the exact target, regime, strata you will test, the binding statistic, the pass/null thresholds, the fee treatment, and the kill rule. Get the plan + methodology critics on it, commit it, THEN pull data. NO PEEKING: do not run exploratory queries on the outcome data before the lock is committed (schema/field-existence audits are fine; outcome-conditioned summaries are not). No post-data criterion tuning. No single-number uncalibrated gates. No expanding the strata set after seeing results.
3. **ANALYZE on real data.** Walk-forward / OOS with purge buffers, event-cluster (not trade-level) confidence intervals, NET of the worst-case applicable dated fee under BOTH envelope ends, post-Oct-2024 only, and F11-aware (prefer taker mechanisms; audit that every field the gate needs exists at the timestamp it needs it). Use real execution prices, never stale prints.
4. **VERDICT: PASS or NULL, no spin.** If the binding CI straddles zero under the worst-case fee, it is a NULL. State the honest ceiling plainly even on a marginal pass, and explicitly note how many hypotheses/strata you have now screened (multiple-testing context).
5. **On NULL: NO THIRD BITE on that idea.** Write the NULL to `research/<vNN>/` (a short FINAL-VERDICT with the killer finding), update `project_kalshi.md` (one-line index entry, detail in the topic file), commit + push. Then either refine to a meaningfully different variant (differ on TARGET, REGIME, FEATURES, or ROLE) or PIVOT to a new idea per the pivot-on-failure rule.
6. **LOOP with an honest budget.** Continue until a genuine edge clears the Becker/OOS screen, OR until you have run a sustained stretch of distinct, well-formed ideas to NULL (as a default, after ~5-6 consecutive honest nulls across genuinely different mechanisms): STOP, write a consolidated meta-summary of the pattern and what it implies about where edge does and does not live, and hand back to the operator for a direction call. Do NOT loop forever forcing a positive, and do NOT lower the bar to escape the loop. A clean stop on nulls is a valid deliverable.

When an edge DOES clear the screen, STAGE it, never straight to live:
- **Becker train+OOS net-of-worst-fee persistence = NECESSARY screen** (it is not sufficient; it cannot resolve F11 capturability).
- **Forward SHADOW / paper trading = capturability proof at ZERO capital.** Log the marketable price you WOULD have taken in real time and compare to realized settlement; run it long enough to accumulate a meaningful event-clustered sample, not a handful of bets.
- **Tiny pilot** only after shadow independently confirms, with fixed $-risk-per-bet and a hard contract cap derived from the ~$200 bankroll (NOT from any backtest peak), plus a per-week drawdown circuit breaker. The pilot must confirm on its own before any scale-up.
- **100% live ONLY on explicit operator approval** after the pilot confirms.

## Starter menu (a STARTING POINT, not a limit)

Distilled from three independent scout reports. The unifying insight: act as a TAKER on a probability you estimate better than the crowd. A taker who crosses on a better forecast is NOT the resting maker who gets adversely selected, and a real marketable order sidesteps F11. That is the single structural reason anything here might escape the project's recurring killer. You are free to propose something off this list if you can argue a higher honest prior.

**Tier 1 (highest honest priors, genuinely different mechanism):**

1. **Weather temperature markets (KXHIGH / KXLOW) traded as a TAKER on an external-model forecast. Prior ~20-30%, the single best candidate but read the caveat.** Settlement is the next-morning NWS Daily Climate Report for one fixed ASOS station per city: a public, model-forecastable number. There is documented behavioral retail mispricing (under-priced forecast uncertainty + station-level NWS bias). Data is FREE, no key (api.weather.gov; HRRR/GFS/NBM GRIB from NOAA). HONEST PRIOR CHECK: a KXHIGH MAKER calibration variant was already screened in `research/phase-1.6-results.md` and FAILED (median OOS ECE improvement 1.44x vs 5x required; shoulder net edge -0.51pp after fees), though the directional signal was real (82% hit rate on >2pp-edge trades, 4-of-5 leave-one-city-out positive). So the bias EXISTS but did not clear a maker net-of-fee bar; your edge must be a DIFFERENT mechanism (taker on model-vs-market divergence, not maker-quoting), and the slow 1-3-day / uncertainty-mispricing variant rather than the heavily-botted same-day model-refresh race. Ceiling is small and capacity-bound. This is the cleanest "information advantage, different failure mode, backtestable on Becker + reconstructable historical NBM" idea, but the phase-1.6 net-negative is a real prior-tempering fact, not a footnote.

2. **Isotonic / Venn-Abers RECALIBRATION of the market price itself, used as a TAKER selection + sizing filter. Prior ~25-30%.** Do not out-forecast the market. Take the mid-price as the base probability, learn a monotone map `p_true = g(p_market)` from settled Becker outcomes conditioned on regime (series, price band, time-to-close, liquidity), and take only the strata where the calibrated gap exceeds the worst-case fee with margin. Different ROLE (recalibrating a strong existing signal, not building a competing forecast), different TARGET (the price's miscalibration residual). Venn-Abers gives a calibrated interval that feeds fractional Kelly directly. Statistically the most conservative idea on the menu; the bar is whether any PRE-REGISTERED stratum's gap clears the worst-case fee out of sample (watch the multiple-testing trap across strata).

**Tier 2 (real but harder; latency or efficiency walls):**

3. **Conformal selective prediction / reject-option as a BET-SELECTION gate layered on top of a base model (Tier-1 #2 or a Tier-2 base). Prior ~20-25%.** Distribution-free abstention: only bet when the calibrated set is tight enough that expected edge clears costs; abstain otherwise, with finite-sample coverage. It does not CREATE edge, it protects you from betting where there is none, so deploy it as a MULTIPLIER on a base signal that already has edge somewhere, not standalone.

4. **Gradient-boosting / elastic-net on a DIFFERENT TARGET (short-horizon price MOVEMENT / gap-to-settlement) on ILLIQUID contracts, traded as a taker. Prior ~15-20%.** Predict price dynamics, not the binary outcome, on slow-moving contracts where public info is slow to price. Elastic-net FIRST as the overfit-control baseline; add nonlinearity only if the linear model already shows signal. Predicted move must exceed spread + worst-case taker fee with margin; capacity is tiny (matches the bankroll).

5. **External sports projections (nflverse / ESPN / pybaseball Statcast) on THIN, slow-to-price PRE-GAME props / totals, as a taker. Prior ~12-18%.** Sports is ~90% of Kalshi volume so capacity lives here, but the edge is NOT on flagship moneylines (Kalshi vig ~0.85% sits inside the sharp books; closing-line-value is already priced in) and in-game is off-limits (you lose to Sportradar-fed MMs). Only pre-game thin props. The project has a sports-fade NULL (v5 sportsbook_fade, n=90), so the bar is separating a real projection edge from "thin because unforecastable."

**Explicitly low-prior / mostly for completeness:** external-buzz tennis value-betting (Google-Trends "Betting on a buzz"; has a published correction study tempering the original claim, and tennis is the project's most-efficient universe), crypto spot/on-chain/funding (HFT latency war, already nulled), Polymarket cross-venue (nulled phantom), news/sentiment (latency race, overlaps killed ML/LLM). Fractional-Kelly sizing and HMM regime-routers are NOT edges; they are required overlays / routers to apply ON TOP of a real Tier-1 edge, never the edge itself.

The honest meta-prior from all three scouts: ML's genuine value here is in CALIBRATION and BET-SELECTION/SIZING, plus EXTERNAL-DATA information advantage traded as a taker, NOT in out-forecasting an efficient market. None of these priors is high; all are honest small-edge-or-null bets. If you spend ONE screen first, the scouts converge on weather (#1) or recalibration (#2) as the most likely to survive an honest screen, with #2 being the statistically cleaner test.

## Resources available

- **Becker dataset:** 72M+ trades (~85GB) at `C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi/prediction-market-analysis/`. Schema has NO orderbook at trade time (the F11 constraint). 67.9M trades post-Oct-2024.
- **Operator offers their ML coursework** (calibration, ensemble post-processing, conformal) on request; it maps directly onto ideas 1, 2, and 3. Ask for it if you go that route.
- **Operator authorizes acquiring free/cheap external data** (NOAA/NWS, pybaseball/nflverse/ESPN, FRED/BLS, etc.). No purchase without flagging it first.

## Binding rules (hard, non-negotiable)

- **NO em-dashes anywhere** (U+2014, U+2013) in code, docs, commits, or chat. After any file write, verify: `Select-String -Path <file> -Pattern '[\u2014\u2013]'` returns nothing.
- **Windows / PowerShell, absolute paths.** All commands must work in PowerShell.
- **Use the project venv python DIRECTLY:** `C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi/.venv/Scripts/python.exe`. Do NOT use `uv run` (`UV_PROJECT_ENVIRONMENT` points at a forbidden pit-backtest venv). That `.venv` has a BROKEN pandas (`module 'pandas' has no attribute '__version__'`), so use **duckdb** for parquet and the **json** module for jsonl; do not rely on pandas. When checking tests, audit the failure tracebacks explicitly because ~75 pandas-AttributeError failures MASK real regressions in the failure count.
- **Net every economic result against the WORST-CASE applicable dated fee** from `research/v22/fee_table.json` (series-AND-date specific, four formula variants, run both `fee_low`/`fee_high` envelope ends); never model the fee schedule from memory and never assume "flat ~1c"; for live P&L the real per-fill `fee_cost` is on `/portfolio/fills`.
- **Git:** commit per meaningful unit, push to `origin/main` after each commit, with a `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer. NEVER commit secrets, `.env`, `*.pem`, `data/**`, or `prediction-market-analysis/` (all gitignored). Verify no secrets staged before every push.
- **No live capital** until an edge clears Becker/OOS -> forward shadow -> tiny pilot, and only then 100% live on explicit operator approval with sizing caps + a drawdown circuit breaker.
- **No secrets in chat.** Treat any pasted key as already exposed.

Begin by reading `project_kalshi.md` (top entries) and the FINAL-VERDICT docs listed above, then PROPOSE your first idea with its honest prior and the one-line reason it escapes a known failure mode. Lock criteria before any data, do not peek, and screen against the worst-case fee. Be motivating but honesty-first: the goal is a real edge or a clean null, never a manufactured positive.
