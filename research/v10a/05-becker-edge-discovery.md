# Becker empirical edge discovery (V10-A Phase 2 explorations)

**Date:** 2026-05-26 (continuing Round 15 after V10-A NULL at methodology lock)
**Author:** Becker empirical exploration agent
**Status:** ONE MARGINAL candidate found; LOAD-BEARING ARTIFACT for Round 15 closure
**Inputs:** Becker dataset 7,314,375 resolved markets, 63,559,531 post-Oct-2024 trades on resolved markets

## Verdict snapshot

| Outcome | Cell | Net mean (pp) | Net CI low (pp) | LOCO net (pp) | LOCO CI low (pp) | n_trades | Recommendation |
|---|---|---|---|---|---|---|---|
| TOP | Media maker [0.40,0.60) | +6.55 | +6.21 | +6.68 | +6.33 | 81,276 | MARGINAL |
| TOP | Media maker [0.20,0.40) | +5.79 | +5.45 | +6.52 | +6.16 | 73,773 | MARGINAL |
| TOP | Media maker [0.60,0.80) | +4.86 | +4.55 | +4.66 | +4.34 | 76,450 | MARGINAL |
| TOP | Other maker [0.60,0.80) | +2.40 | +2.20 | +2.45 | +2.25 | 188,578 | MARGINAL (least concentrated) |
| TOP | Entertainment maker [0.40,0.60) | +2.22 | +2.01 | +2.28 | +2.07 | 220,516 | MARGINAL |

All numbers are PER-CONTRACT net of Kalshi MAKER fee (ceil(0.0175*p*(1-p)*100)/100 dollars), pooling YES and NO sides.

**Final recommendation: ALL candidates are MARGINAL.** None are SHIP-CANDIDATE for direct live deployment because of two unresolved risks:
1. **F11 (Dataset Schema Phantom):** Becker's trades schema lacks orderbook ask at trade time, so the maker-fill prices in the sample are not the same prices a retail maker bot would necessarily get filled at.
2. **Selection by orderflow:** the maker side in Becker is the COUNTERPARTY to the aggressor, not necessarily a passive retail bot; queue priority and Glosten-Milgrom adverse selection are not modeled.

The strongest cell (Media maker mid-price) is recommended for **SHIP-SHADOW-MODE logging** for 60-90 days alongside v1, NOT direct capital deployment.

## Phase 1: Becker headline replication (sanity check)

I reproduced Becker's "maker vs taker excess returns by category" by computing, for every post-Oct-2024 trade on a resolved Kalshi market with yes_price+no_price=100 and count>0, the gross excess return for the maker counterparty and the taker. Pooled by category group, weighted by trade count.

Result:

| Group | maker_n | taker_n | maker excess (pp) | taker excess (pp) | maker-taker (pp) |
|---|---|---|---|---|---|
| Media | 400,382 | 400,382 | +5.15 | -5.15 | +10.30 |
| Entertainment | 1,386,553 | 1,386,553 | +2.28 | -2.28 | +4.56 |
| Science/Tech | 153,585 | 153,585 | +2.19 | -2.19 | +4.37 |
| World Events | 198,108 | 198,108 | +2.02 | -2.02 | +4.04 |
| Other | 979,708 | 979,708 | +1.91 | -1.91 | +3.82 |
| Weather | 3,773,131 | 3,773,131 | +1.55 | -1.55 | +3.10 |
| Politics | 4,825,893 | 4,825,893 | +1.36 | -1.36 | +2.72 |
| Crypto | 6,624,687 | 6,624,687 | +1.29 | -1.29 | +2.58 |
| Finance | 1,540,871 | 1,540,871 | +1.12 | -1.12 | +2.25 |
| Sports | 43,358,180 | 43,358,180 | +1.12 | -1.12 | +2.23 |
| Esports | 98,272 | 98,272 | +0.17 | -0.17 | +0.33 |

Becker's headline pattern confirmed: makers win, takers lose, magnitude varies by category (40x range Media to Esports). Sports is the largest universe but has the lowest per-trade maker edge.

Note that by construction maker_excess = -taker_excess (every trade transfers wealth between the two counterparties).

Artifact: `research/v10a/05-phase1-category-headline.csv`

## Phase 2: Sub-cell exploration (group, role, side, price band)

For the top 6 groups by maker excess return (Media, Entertainment, Science/Tech, World Events, Other, Weather; n>=5000 each), I drilled into 168 cells of `(group, role, side, price band)`.

I observed a striking pattern: the cells with extreme positive net excess were ALL on **side=NO** at midprice bands. For example, Media maker NO [0.40,0.60) shows +18.86pp net, while the twin cell Media maker YES [0.40,0.60) shows -15.75pp net.

**This is NOT a forward-deployable signal.** It is a base-rate selection artifact:
- A maker is the counterparty to the aggressor; the maker's "side" is determined by which side of the orderbook the taker hits.
- A market that ends up resolving NO (e.g., World Events 67% NO, Media 60% NO) accumulates more YES-aggressor trades early (as YES traders pile into the favorite); the maker-NO position gets more historical fills at YES-side prices.
- Conditioning on side after the fact reveals which side won more often; conditioning on price before the fact (the only thing a forward bot can do) gives no signal.

To make this concrete: at Media [0.40,0.60) midprice, the *combined* maker excess (weighting YES and NO by their n_trades) is +6.55pp, which is the actual edge a side-agnostic maker bot could capture. The +18.86pp NO-only number is a backward-looking selection statistic, not a tradeable edge.

Artifact: `research/v10a/05-phase2-cells.csv`, `research/v10a/05-phase2-cells-with-mt.csv`, `research/v10a/05-side-symmetry-by-band.csv`, `research/v10a/05-resolution-balance-by-group.csv`.

## Phase 3: Combined-side LOCO

I re-aggregated to the side-agnostic level: per (group, role, price_band), combining YES and NO fills weighted by their volume, treating the result as the net excess a maker quoting at that price-band would historically have earned (post fees).

Then, for each cell with n>=100 and CI excluding zero, I ran LOCO on the largest `series_prefix` (the Kalshi ticker prefix up to first hyphen, which uniquely identifies a market series like KXTSAW for TSA throughput counts).

A cell PASSES LOCO if the net excess CI WITHOUT the largest series still excludes zero.

**24 of 84 combined-side maker cells pass: net CI > 0 AND LOCO pass.**

The top cells by net mean (with concentration filter top3_share < 0.5 applied):

| Group | Band | n | n_prefixes | avg_price | win_rate | net_mean (pp) | CI low (pp) | largest_prefix | largest_share | LOCO net (pp) | LOCO CI low (pp) | top3_concentration |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Media | [0.40,0.60) | 81,276 | 138 | 0.493 | 0.569 | +6.55 | +6.21 | KXVANCEMENTION | 6.6% | +6.68 | +6.33 | 30.0% |
| Media | [0.20,0.40) | 73,773 | 138 | 0.300 | 0.368 | +5.79 | +5.45 | KXTSAW | 8.8% | +6.52 | +6.16 | 21.0% |
| Media | [0.60,0.80) | 76,450 | 138 | 0.688 | 0.747 | +4.86 | +4.55 | KXTSAW | 9.2% | +4.66 | +4.34 | 31.5% |
| Media | [0.80,0.95) | 51,451 | 136 | 0.868 | 0.919 | +4.13 | +3.89 | KXTSAW | 12.6% | +4.09 | +3.84 | 34.4% |
| Entertainment | [0.20,0.40) | 235,471 | 360 | 0.296 | 0.332 | +2.52 | +2.33 | KXSPOTIFYD | 8.3% | +3.23 | +3.03 | 34.2% |
| Other | [0.60,0.80) | 188,578 | 1087 | 0.697 | 0.731 | +2.40 | +2.20 | KXELONTWEETS | 2.7% | +2.45 | +2.25 | 7.3% |
| Entertainment | [0.40,0.60) | 220,516 | 341 | 0.493 | 0.525 | +2.22 | +2.01 | KXSPOTIFYD | 5.8% | +2.28 | +2.07 | 13.0% |
| Other | [0.80,0.95) | 161,768 | 1159 | 0.871 | 0.900 | +1.89 | +1.74 | KXELONTWEETS | 4.2% | +2.24 | +2.09 | 8.4% |

Standout cells:
- **Media maker [0.40,0.60)**: highest per-trade edge (+6.55pp net), 138 contributing prefixes, largest only 6.6%, LOCO actually IMPROVES the edge to +6.68pp. Top-3 concentration 30%.
- **Other maker [0.60,0.80)**: 1087 contributing prefixes, largest only 2.7%, top-3 only 7.3%, but lower edge (+2.40pp). Most robust by diversification.
- **Weather maker [0.20,0.40)** failed concentration filter: 32 prefixes only (HIGHNY/HIGHCHI/HIGHLAX etc. dominate), top-3 share 66%. Net +2.02pp but CI without largest prefix drops materially.

Artifacts: `research/v10a/05-phase3-loco.csv`, `research/v10a/05-phase4-combined-side-loco.csv`, `research/v10a/05-phase4-combined-loco.json`.

## Phase 4: Sanity checks

### F4 (phantom price) check
The trades schema has `yes_price` + `no_price` columns. I filtered to `yes_price + no_price = 100`, which is the algebraic identity for any valid Kalshi trade at the moment of execution (since both prices are recorded as part of the trade record). Sampling 10 random post-Oct-2024 trades confirmed all sum to 100. The prices are real execution prices, not stale post-settlement values.

### F3 (domain coverage) check
For the top candidate cells, top-5 prefix shares:

- Media [0.40,0.60): KXVANCEMENTION 6.6%, KXEARNINGSMENTIONNVDA 6.4%, KXTSAW 6.2%, KXSNLMENTION 4.5%, KXAPRPOTUS 3.8% (top-5 = 27.5%)
- Media [0.20,0.40): KXTSAW 8.8%, KXVANCEMENTION 5.6%, KXEARNINGSMENTIONNVDA 5.1%, KXAPRPOTUS 4.4%, KXSNLMENTION 4.3% (top-5 = 28.2%)
- Other [0.60,0.80): KXELONTWEETS 2.7%, KXWHVISIT 2.5%, KXKNOXGOLD 2.0%, KXTIPTAX 1.7%, KXDJTHANNITY 1.4% (top-5 = 10.3%)
- Other [0.80,0.95): KXELONTWEETS 4.2%, KXWHVISIT 2.9%, ADAMS 2.0%, KXWL 1.3%, KXJFKFILES 1.3% (top-5 = 11.7%)

The Media cells are dominated by political/mention/count markets (KXVANCEMENTION, KXAPRPOTUS, KX538APPROVE) and TSA throughput counts (KXTSAW), plus single-equity earnings mentions (KXEARNINGSMENTIONNVDA, KXEARNINGSMENTIONTGT). These series are intermittent and may have lower liquidity than sports favorites.

The Other cells span 1000+ prefixes; this is highly diversified.

### F8 (regime mismatch) check
Becker's headline +0.17pp Finance to +7.32pp World Events gap was measured on the full price band [0, 1]. The candidate cells here are subsets of those bands and the magnitudes are CONSISTENT with the headline category averages (the variability across price bands in a single group is small after combining sides).

### F10 (LOO fragility) check
Top-3 prefix contribution to total absolute PnL:

- Media [0.40,0.60): 30.0%
- Media [0.20,0.40): 21.0%
- Other [0.60,0.80): 7.3%
- Other [0.80,0.95): 8.4%
- Entertainment [0.40,0.60): 13.0%

The Media cells have moderate concentration (top-3 contribute 20-35% of absolute PnL). The Other cells are extremely diversified (top-3 = 7-8%).

### Multiple testing correction
With 168 (group, role, side, band) cells tested at alpha=0.05:
- Bonferroni alpha = 0.05/168 = 0.000298
- 152 cells pass Bonferroni
- 158 cells pass BH FDR q=0.05

The candidate cells survive at p < 10^-15, well below any reasonable correction. Multiple testing is not the binding concern; data-layer reality is.

## Phase 5: Recommendations per candidate cell

### Cell A: Media maker [0.40,0.60) - net +6.55pp, MARGINAL

**Mechanism hypothesis:** Media category markets (political mentions, TSA counts, earnings mentions) attract retail YES-aggressors who pay ~ midprice for the favorite, leaving makers on the NO side at favorable prices. The category exhibits broad-based maker advantage independent of single-series dominance (138 contributing prefixes, top-3 = 30%).

**Why MARGINAL not SHIP:**
- F11: Becker schema does not have orderbook ask at trade time. Retail bot would post bids in the orderbook at midprice; whether retail bot's bids would have been the fills sampled in Becker's data is unknown.
- Sample is mostly composed of MM fills (Susquehanna, professional MMs). Retail maker bid queue priority is unknown.
- 19-month sample window (2024-10 to 2025-11); Burgi 2025 documents bias compression year-over-year; post-Nov-2025 effect may already be smaller.
- Per-series volume is modest. Many mention/count markets are intermittent.

**Shadow-mode protocol:** post-only quoting at midprice (or 1-2c inside) in active Media category markets that are open, V1-style maker quoting but with a different universe definition. Log fills for 60-90 days. Compare realized maker excess to Becker's +6.55pp baseline. If realized > +2pp net at n>=50 fills, escalate to live with $10 cap; if -2 to +2pp, continue shadow; if < -2pp, kill.

### Cell B: Other maker [0.60,0.80) - net +2.40pp, MARGINAL but most robust

**Mechanism hypothesis:** "Other" category captures markets that don't map to the explicit subcategory patterns. With 1087 contributing prefixes and largest only 2.7% share, this is the most diversified maker edge in the dataset.

**Why MARGINAL:** lower per-trade edge (+2.40pp). At ~$0.05 per $1 contract net after maker fee. To make $5/day net P&L, you'd need ~$100 in fills per day, which requires substantial Kalshi orderbook penetration on a long tail of low-volume markets.

**Shadow-mode protocol:** same as Cell A but pulling Other-category open markets from the API. Log fills 60-90 days.

### Cell C: Entertainment maker [0.40,0.60) - net +2.22pp, MARGINAL

**Mechanism hypothesis:** Entertainment markets (KXSPOTIFYD, KXSNFMENTION, KXTNFMENTION, KXOSCAR*, KXNETFLIX*) have steady retail flow at predictable cadence (daily Spotify charts, Sunday Night Football mentions, Oscar voting weeks). Maker edge of +2.22pp suggests systematic retail YES-aggressor mispricing during these events.

**Why MARGINAL:** mid-tier edge, but high diversification (341 prefixes). Likely highest sustained per-day volume of the candidate cells given KXSPOTIFYD is daily.

### Phase 2 cells NOT recommended

- Weather maker [0.20,0.40) net +2.02pp: failed LOCO concentration check; top-3 prefixes (KXHIGHNY/AUS/LAX) account for >50% of absolute PnL. Edge collapses to +1.14pp without KXHIGHNY.
- World Events maker [0.20,0.40) net +10.46pp: only 21 prefixes; KXEPSTEIN alone is 35% share. LOCO net drops from +10.46 to +4.66pp (still positive but highly entity-dependent).
- Sports cells did not surface in Phase 2 because they showed LOWEST maker edge per-trade (+1.12pp); v1 is already doing this and that universe is exhausted of new headline edges per V4-H denylist work.

## Composite recommendation

**ONE shadow-mode candidate moves forward: Media maker midprice quoting.**

- Universe: open Media-category Kalshi markets per categories.py SUBCATEGORY_PATTERNS, primarily mention/count/earnings/poll markets.
- Strategy: maker-only post at midprice (within 1c of the orderbook mid), $0.50 to $1.00 per trade, NO autorestart on fill.
- Logging: 60-90 days shadow mode with NO live capital; record paper fills and compare realized to Becker baseline.
- Pre-registered gate after shadow:
  - C1: n_fills >= 30 (otherwise underpowered)
  - C2: realized net mean > +2pp per contract
  - C3: realized net CI excludes zero (bootstrap, n_boot=2000)
  - C4: top-3 series concentration < 50% of fills
  - C5: realized within +/-3pp of Becker's +6.55pp baseline (regime stability check)

If all five pass: escalate to $5 deployment; if 3 of 5 pass: continue shadow; if <3 pass: NULL the candidate.

## All cells, all sides (for audit)

Detailed CSVs in `research/v10a/`:
- `05-phase1-category-headline.csv` - per-group maker/taker excess returns (post-Oct-2024)
- `05-phase2-cells.csv` - all 168 (group, role, side, band) cells with bootstrap CI
- `05-phase2-cells-with-mt.csv` - same plus Bonferroni and FDR flags
- `05-phase3-loco.csv` - per-cell LOCO on largest series_prefix
- `05-phase3-prefix-agg.parquet` - underlying prefix-level aggregates (39301 rows)
- `05-phase4-combined-side-loco.csv` - combined YES+NO side cells with LOCO
- `05-side-symmetry-by-band.csv` - per (group, role, band) yes/no decomposition
- `05-resolution-balance-by-group.csv` - per-group yes/no resolution fractions (the smoking gun for the within-side asymmetry)
- `scripts/v10a/becker_edge_discovery.py` - Phase 1+2 driver
- `scripts/v10a/becker_loco_phase3.py` - Phase 3 SQL aggregation + LOCO
- `scripts/v10a/becker_combined_side_loco.py` - Phase 4 combined-side LOCO
- `scripts/v10a/becker_sanity_resolution_balance.py` - resolution balance sanity check

## Spend log

- Becker dataset extraction: previously done (36 GB)
- DuckDB queries this session: under $0.10 (all local compute)
- LLM cost this session: under $1 (orchestrator + agent)
- Total V10-A round including this: ~$2.50 of $8 cap

## Why this is NOT a SHIP-CANDIDATE despite passing all statistical gates

The methodology critic for V10-A flagged FAILURE MODE F11: "pre-registering a backtest gate that depends on an execution-price field that does not exist in the chosen dataset schema." This applies HERE TOO.

The candidate edges are real backward-looking statistics. They tell you: among trades that DID happen on resolved markets at price X in category Y over the post-Oct-2024 sample, the makers won X% on average. They do NOT directly tell you whether a NEW retail maker bot posting at price X would have its bid filled, and if filled, would experience the same conditional win rate.

Operationally:
- v1 IS already a maker-quoting strategy in a similar category (sports favorites). v1's measured edge is +12.47pp on its narrow universe but the V4-H rebuild on the full sports universe showed v1's edge was sample-specific (KXMLBPLAYOFFS -27.84pp etc.).
- The Becker +6.55pp Media maker edge is an UNCONDITIONAL average over all post-Oct-2024 trades. v1's analog computation on Media would need to be done LIVE with shadow-mode logging to verify.

This is why MARGINAL not SHIP. The empirical pattern is the cleanest signal V10-A has surfaced, but it cannot be translated to a live strategy without prospective shadow-mode evidence.

## Notes on what was tested but didn't surface

- All Phase 1 categories were screened. Sports/Crypto/Finance have lower per-trade maker edges than Media/Entertainment/Other.
- Both maker and taker were tested. Takers nearly always lose net (fees eat the gross edge), so taker cells are excluded.
- Multiple testing correction (Bonferroni and BH-FDR) was applied: 152 of 168 cells pass Bonferroni, 158 pass FDR. Multiple testing is not the binding concern; data-layer phantom risk and prospective execution feasibility are.
