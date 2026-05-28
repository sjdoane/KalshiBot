# v10 Phase 0 Synthesis and Angle Proposal

**Date:** 2026-05-26
**Author:** v10 orchestrator (post 3-agent Phase 0)
**Predecessor docs:** `01-market-universe.md`, `02a-data-scout.md`, `02b-literature-delta.md`, `03-methodology-meta.md`
**Status:** Phase 0 complete. Operator picks v10 primary angle before Phase 1 methodology lock.

---

## What changed since v9 closed

Three updates between v9 NULL (this morning) and now:

1. **v8-A live probe closed at iter 33, killed early.** v7-B is CONFIRMED PHANTOM. 8 of 8 settled strong-signal contracts LOST, mean -$0.20 per $1 bet, binomial p ~ 0.004. v7-B drops off the v10 candidate list permanently. The naive_p_yes feature was real improvement over stale TRADE PRINT mid, zero improvement over the live ASK that MMs maintain continuously.

2. **TimeSeek paper (arXiv 2604.04220, April 2026)** is the FIRST AND ONLY published evaluation specifically on CFTC-regulated Kalshi binary markets at scale (10 frontier models, 150 markets, 15,000 forecasts). Headline finding: LLMs are competitive **EARLY in market life on HIGH-UNCERTAINTY markets**, and "much less competitive near resolution and on strong-consensus markets." This is third-party empirical confirmation of the v9 Phase 3 critic's design-layer kill: v1's confident-favorite regime (0.70-0.95) is the worst LLM regime. The same paper's positive implication: a regime-matched LLM angle (early lifecycle, uncertain price) is the design that has empirical support on Kalshi specifically.

3. **Prediction Arena (arXiv 2604.07355, April 2026)** ran 6 frontier models at $10k each on Kalshi for 57 days. **All 6 lost between -16% and -30.8%** on Kalshi. Same models did better on Polymarket (-1.1% average, one +6.02%). This is the first published LIVE CAPITAL evidence that autonomous LLM trading on Kalshi loses money even at the frontier. Implies: any LLM-as-trader angle on Kalshi requires structural edge beyond just running a frontier model.

4. **Kim et al. arXiv 2602.07048 (Feb 2026)** is the ONLY published positive Kalshi-specific 2026 result. Granger causality identifies statistical lead-lag pairs across Kalshi Economics markets (KXFEDFUNDS, KXCPI, KXNFP, KXUNRATE); an LLM semantic filter removes economically implausible directions. Win rate 51.4% to 54.5% (+3.1pp absolute), average loss magnitude $649 to $347. This is a direct-replication target.

5. **Multi-LLM ensemble at near-zero incremental cost is now feasible.** Gemini 2.5 Flash (1,500 req/day free, no card), DeepSeek V4 Flash (5M free signup tokens), Groq Llama-3.1-70B (1,000 req/day free), Tavily Search (1,000 req/mo free) form a complete 3-vendor LLM + 1 retrieval roster at $0 within free-tier envelopes. v9's $0.10/forecast cost projection drops to under $0.03/forecast if v10 uses these as the LLM tier instead of Opus 4.7.

## Untested Kalshi market discoveries

Agent v10-S1 confirmed via live trade stream at 2026-05-26 22:45 UTC (200 most recent trades). The following series are ACTIVE TONIGHT with non-zero trade flow and have **zero prior Project Kalshi coverage** (v2 through v9 never touched them):

- KXMLBTOTAL (MLB total runs over/under): 8 trades in last-200
- KXMLBF5 (MLB first-5-innings result): 7 trades
- KXMLBRFI, KXMLBKS, KXMLBHIT, KXMLBSPREAD (MLB props variants)
- KXNBASPREAD (NBA point spread): 4 trades
- KXNBATOTAL (NBA total points): 3 trades
- KXMVESPORTSMULTIGAMEEXTENDED (Esports multi-game props): **21 trades**
- KXMVECROSSCATEGORY (Esports cross-category): 5 trades
- KXVALORANTGAME (Valorant match-level): 3 trades
- KXITFWMATCH (ITF Women's tennis match): 18 trades
- KXATPCHALLENGERMATCH (ATP Challenger): 5 trades
- KXCONMEBOLLIBGAME (Copa Libertadores match): 6 trades
- KXCONMEBOLSUDGAME (Copa Sudamericana match): 3 trades

The two-line headline: same-day-resolving MLB props are the largest untested market class by volume. Esports is the highest-novelty untested category (21 trades of KXMVESPORTSMULTIGAMEEXTENDED in 200-trade window).

## Ranked v10 angle proposals

Three primary candidates emerge after Phase 0 synthesis. They are complementary, not mutually exclusive, and use largely disjoint data sources.

### V10-A: Kalshi Economics LLM Lead-Lag Replication (arXiv 2602.07048)

| Field | Value |
|---|---|
| Hypothesis | Granger causality identifies statistical lead-lag pairs across Kalshi Economics markets (KXFEDFUNDS, KXCPI, KXNFP, KXUNRATE); an LLM semantic filter removes economically implausible directions; the resulting taker strategy lifts win rate by 3pp+ |
| Target | KXFEDFUNDS, KXCPI, KXNFP, KXUNRATE markets, monthly resolution events |
| Methodology | Direct replication of Kim et al. 2602.07048; Granger causality on Kalshi probability time series, LLM filter for transmission plausibility, paper-trade verification with fee model and CI |
| Pre-registered gate | Bootstrap 95% CI of win-rate delta over baseline strictly excludes zero AND mean P&L per trade after Kalshi fees is positive (paper reports 54.5% win, but does NOT explicitly publish net-of-fee P&L) |
| Data | Kalshi historical trades + FRED API (free with key) for series-level macro context |
| Cost | $3-5 LLM (Opus or cheap-tier multi-LLM) + $0 data |
| Wall-clock | 5-10 days (data pull 1-2d, Granger 1d, LLM filter 1-2d, backtest 1d, critic 1-2d) |
| Prior | **20-30%** (strongest evidence base in literature; direct paper claim on Kalshi; tempered by Diercks 2026 macro-efficiency finding) |
| Failure modes survived (per F1-F10 v10-S3 taxonomy) | F1 (Kalshi historical trades available without orderbook ceiling), F8 (gate matched to paper's reported regime), F9 (macro is year-round) |
| Failure modes risked | F2 (monthly frequency, n < 200 across all pairs over 2 years), F10 (LOO fragility if signal concentrates in CPI vs NFP), fee-model audit risk (paper's net-of-fee P&L not published) |
| Novelty | FRESH-SLICE-OF-KNOWN-NULL (v2 macro path was Round 2 KILLED at OOS gate; this is a different method with stronger evidence) |
| Session-final verdict? | YES |

### V10-B: Multi-LLM Regime-Matched Ensemble on Uncertain Kalshi Props

| Field | Value |
|---|---|
| Hypothesis | A multi-LLM ensemble (Opus + Gemini + DeepSeek + Groq Llama) with Tavily retrieval, Platt scaling, 67/33 market/AI weight, on Kalshi MARKETS WITH MID IN 0.30 TO 0.70 AND CLOSE TIME WITHIN 30 DAYS extracts the AIA-documented +0.014 Brier lift the v9 design-layer kill predicted was unfirable in v1's confident regime |
| Target | KXMLBTOTAL, KXMLBF5, KXNBASPREAD, KXNBATOTAL, KXMVESPORTSMULTIGAMEEXTENDED, KXVALORANTGAME, KXITFWMATCH, KXATPCHALLENGERMATCH, KXCONMEBOLLIBGAME (same-day or short-horizon markets in 0.30-0.70 band) |
| Methodology | v9's locked recipe spec at `research/v9/02-recipe-methodology.md` is reusable verbatim; sub-agent count is now 3 to 4 cheap LLMs instead of 3 Opus; supervisor pass on disagreement spread > 0.15; foreknowledge audit via Haiku judge; baseline is REAL orderbook mid at forecast time per v7-B prevention |
| Pre-registered gate | n >= 80 resolved markets, Brier_delta >= 0.014, 95% bootstrap CI strictly positive; sport-stratified breakdown to detect sports-LLM topic weakness (Janna Lu 2025: o3 sports Brier 0.165 vs politics 0.120, so sport breakdown is load-bearing) |
| Data | Kalshi /markets/{ticker}/orderbook (real-time), Tavily Search, ESPN site.api, the-odds-api (already keyed in .env, 477 credits left), Gemini + DeepSeek + Groq APIs |
| Cost | $2-5 LLM (Opus only as orchestrator + judge; sub-agents on free tiers; ~$0.03/forecast) + $0 data |
| Wall-clock | Forecast batch 1 session (today / tomorrow); first MLB resolutions 1 day; full batch verdict 2-3 weeks |
| Prior | **15-25%** (TimeSeek confirms regime fit on Kalshi specifically, but sports remains weakest LLM topic; props are harder than game-winners for LLM) |
| Failure modes survived (per F1-F10) | F4 (real orderbook mid, not stale print), F7 (avoid sports-topic worst case by mixing in esports/soccer where LLM-weakness varies), F8 (regime-matched gate; 0.30-0.70 IS where AIA measured +0.014), F9 (props are year-round on rolling basis) |
| Failure modes risked | F2 (achieving n >= 80 requires ~ 2-3 week prospective; could underrun budget), F7 partial (sports remains weakest LLM topic per Janna Lu 2025), F10 (LOO fragility if signal concentrates in one sport or one model) |
| Novelty | NEW. v4-B was bare LLM confident sports (wrong tools, wrong regime, wrong topic mix). v9 was agentic Opus confident sports (wrong regime). v10-B is multi-LLM agentic UNCERTAIN regime + mixed-sport topic. Three changes simultaneously, each fixing a documented failure. |
| Session-final verdict? | Partial / pilot in 2-3 weeks |

### V10-C: Sportsbook Dynamic Line Movement on Game-Resolution Sports

| Field | Value |
|---|---|
| Hypothesis | When a major sportsbook moves a game-result line by >= 3 basis points in the T-6h to T-1h window before a Kalshi game-resolution market closes, Kalshi mid lags by 3-5pp; a taker at the stale Kalshi mid captures the adjustment |
| Target | KXMLBGAME, KXNBAGAME (and intraday game props like KXMLBTOTAL, KXNBASPREAD; overlaps with V10-B target list) |
| Methodology | the-odds-api Starter historical pull (5+ seasons NFL/NBA/MLB), join to Kalshi historical trades and mid via existing v6 build pattern; compute sportsbook line change over T-6h to T-1h; orthogonality screen on whether line-change magnitude predicts Kalshi mid change |
| Pre-registered gate | n >= 100 qualified game-resolution events with >= 3bp sportsbook move; bootstrap CI on taker P&L (following sportsbook direction) excludes zero; LOO-robust at k=10 sport-stratification |
| Data | the-odds-api Starter ($30 one-month buy, within $30-60 authorized budget) + Kalshi historical trades |
| Cost | $30 external one-time + $0 LLM |
| Wall-clock | 5-8 days |
| Prior | **15-22%** (v9-A3 Candidate 9 prior; partially backed by v5-A static divergence finding; dynamic version is distinct test) |
| Failure modes survived | F4 (sportsbook price is the feature, Kalshi mid is the outcome target; if backtest uses Kalshi trades as proxy for mid, replays F4 risk; if uses Kalshi orderbook history -- which is unavailable per v9 finding -- cannot run), F7 (no LLM), F8 (no borrowed gate) |
| Failure modes risked | F1 (Kalshi historical orderbook gap means baseline reconstruction uses trade-print as proxy; this risks REPLAYING v7-B phantom; methodology must explicitly address), F3 (NFL dominates sample), F10 (LOO fragility if signal concentrates in single bookmaker) |
| Novelty | FRESH-SLICE (v5-A static; this is dynamic) |
| Session-final verdict? | YES |

### V10-D: Honorable mention -- LLM-reads-BLS-CPI on release day (latency edge)

Cost $0, prior 8-15% per agent v10-S1. NOT recommended as a primary v10 angle because the latency window may be sub-second (Kalshi MMs likely faster than retail). Worth a one-shot probe on the June 10 CPI release if the operator wants a free zero-time-investment test.

## Recommendation

The operator's directive is "thorough", "interesting markets using interesting data", "new approaches", "grounded in research".

**Primary recommendation: V10-A + V10-B in parallel.**

Reasoning:
- V10-A has the strongest published evidence base (Kim 2602.07048 is the only Kalshi-specific 2026 positive result; direct replication is the gold standard for "grounded in research")
- V10-B is the most novel angle and directly addresses v9's design-layer kill (TimeSeek confirms this is the regime where LLMs work on Kalshi)
- They use disjoint markets (V10-A is macro, V10-B is sports props) and largely disjoint data sources
- Combined cost is $5-10 LLM + $0 data, within remaining budget of approximately $4-6 LLM ($25 cap minus ~$19-21 cumulative)
- Each can produce a session-relevant verdict on different timelines (V10-A: 5-10 days, V10-B: 2-3 weeks for full but partial in 1-3 days)

**Secondary: V10-C if operator authorizes $30 the-odds-api Starter buy.**

V10-C is a session-final verdict at the highest fan-out per dollar. The $30 buys 5+ seasons of historical odds. But V10-C requires reconstruction of Kalshi mid from trade history (no orderbook history), which puts it in F4 (v7-B phantom risk territory) unless the methodology critic clears a specific approach.

**Honest down-weighting:**
- Cumulative state remains 8 NULLs + 1 PHANTOM + 2 shadow-mode PARTIALs in 9-10 attempts. No v10 angle is priced above 30%.
- All three V10 proposals together do not produce a >50% prior of finding a monetizable edge. They produce a 40-55% prior of producing ONE OR MORE clean verdicts (PASS or definitive NULL) that meaningfully reduce the remaining-edge surface area.

## API keys and data sources to add

The following are all free or near-free, no credit card required, instant signup. The operator's prior question "Let me know if there's any data sources or API keys you want me to add" - here is the concrete list, ordered by which v10 angle each enables.

### For V10-A (Kalshi Economics replication) and V10-B (multi-LLM ensemble)

| Service | Cost | Free tier | Signup time | Used by |
|---|---|---|---|---|
| **Google AI Studio (Gemini API key)** | Free | 1,500 req/day Gemini 2.5 Flash, no card | 2 min via aistudio.google.com | V10-B (sub-agent) |
| **DeepSeek API key** | 5M free tokens at signup | 5M tokens free, no card | 5 min via platform.deepseek.com | V10-B (sub-agent), V10-A (cheap option) |
| **Groq API key** | Free | 1,000 req/day Llama-3.1-70B, no card | 2 min via console.groq.com | V10-B (sub-agent) |
| **Tavily Search API key** | Free | 1,000 req/month, no card | 2 min via tavily.com | V10-B (retrieval tool) |
| **FRED API key** | Free | No documented limit | 2 min via fredaccount.stlouisfed.org/apikeys | V10-A (macro context) |

If the operator can drop these five keys into `.env` as `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `GROQ_API_KEY`, `TAVILY_API_KEY`, `FRED_API_KEY` (5 to 15 minutes total), v10 has the full data stack for both V10-A and V10-B.

### For V10-C (sportsbook line movement)

| Service | Cost | Notes |
|---|---|---|
| **the-odds-api Starter** | $30/month one-time | Already authorized in $30-60 budget. Buy ONE month, drain historical, cancel. Historical data persists locally after cancellation. |

This is operator-action; the agent cannot buy it. The existing the-odds-api free-tier key (already in `.env`, 477 credits left) handles live odds for V10-B but does NOT include historical odds.

### Skipping for now

- OpenAI API key (no free tier; calibration of gpt-4o-mini is unmeasured)
- Brave Search (free tier eliminated early 2026)
- Polygon.io (relevant only if v10 targets equity-linked Kalshi markets)
- Bluesky / Reddit / X (thin signal vs ESPN; some require auth)

## Phase 1 plan after operator selects angle

For whichever angle(s) the operator approves, Phase 1 proceeds per the inherited protocol:

1. **Phase 1**: 2-3 parallel sub-agents per angle for (a) data probe + reproducibility, (b) recipe methodology lock, (c) prior-art / replay-prevention scope
2. **Phase 1.5**: Methodology lock document + methodology critic agent + revision to v2 if material flaws
3. **Phase 2**: Build + baseline + orthogonality screen + first-pass result
4. **Phase 3**: Adversarial critic with reproduction + salvage attempts
5. **Phase 4**: Iterate on critic findings (no third-bite on methodology lock)
6. **Phase 5**: FINAL-VERDICT.md, CLAUDE.md, memory updates

All paths v10-only: `src/kalshi_bot_v10/`, `scripts/v10/`, `tests/v10/`, `data/v10/`, `research/v10/`. v8-A is closed; v1 production unchanged.
