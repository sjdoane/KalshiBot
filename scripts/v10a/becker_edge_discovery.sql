-- ========================================================================
-- Becker edge discovery SQL queries (reference only; Python scripts run them)
-- ========================================================================
-- Driver: scripts/v10a/becker_edge_discovery.py (Phases 1+2)
--         scripts/v10a/becker_loco_phase3.py (Phase 3 SQL aggregate + Python LOCO)
--         scripts/v10a/becker_combined_side_loco.py (Phase 4 combined-side)
--         scripts/v10a/becker_sanity_resolution_balance.py (resolution-balance sanity)
--
-- Paths in queries:
--   markets glob: prediction-market-analysis/data/kalshi/markets/*.parquet
--   trades glob: prediction-market-analysis/data/kalshi/trades/*.parquet
--   category_sql: prediction-market-analysis/src/analysis/kalshi/util/categories.py:CATEGORY_SQL
--
-- All queries restrict to:
--   - status = 'finalized' AND result IN ('yes', 'no')
--   - trade.created_time >= '2024-10-01' (post-flip per Becker)
--   - yes_price + no_price = 100 (sanity: filters out null prices and edge cases)
--   - count > 0

-- ------------------------------------------------------------------------
-- Phase 1: per-category maker vs taker excess return
-- ------------------------------------------------------------------------
WITH resolved AS (
    SELECT ticker, event_ticker, result
    FROM '<MARKETS_GLOB>'
    WHERE status='finalized' AND result IN ('yes','no')
),
joined AS (
    SELECT
        t.taker_side, t.yes_price, t.no_price, t.count, m.result,
        CASE
            WHEN m.event_ticker IS NULL OR m.event_ticker = '' THEN 'independent'
            WHEN regexp_extract(m.event_ticker, '^([A-Z0-9]+)', 1) = '' THEN 'independent'
            ELSE regexp_extract(m.event_ticker, '^([A-Z0-9]+)', 1)
        END AS category
    FROM '<TRADES_GLOB>' t
    INNER JOIN resolved m ON t.ticker = m.ticker
    WHERE t.created_time >= TIMESTAMP '2024-10-01'
      AND t.yes_price IS NOT NULL AND t.no_price IS NOT NULL
      AND t.yes_price + t.no_price = 100
      AND t.count > 0
),
taker AS (
    SELECT category,
        AVG((CASE WHEN taker_side='yes' THEN yes_price ELSE no_price END)/100.0) AS avg_price,
        AVG(CASE WHEN taker_side=result THEN 1.0 ELSE 0.0 END) AS win_rate,
        AVG(
            (CASE WHEN taker_side=result THEN 1.0 ELSE 0.0 END)
            - (CASE WHEN taker_side='yes' THEN yes_price ELSE no_price END)/100.0
        ) AS excess,
        STDDEV(
            (CASE WHEN taker_side=result THEN 1.0 ELSE 0.0 END)
            - (CASE WHEN taker_side='yes' THEN yes_price ELSE no_price END)/100.0
        ) AS sd,
        COUNT(*) AS n, SUM(count) AS contracts
    FROM joined GROUP BY category
),
maker AS (
    SELECT category,
        AVG((CASE WHEN taker_side='yes' THEN no_price ELSE yes_price END)/100.0) AS avg_price,
        AVG(CASE WHEN taker_side!=result THEN 1.0 ELSE 0.0 END) AS win_rate,
        AVG(
            (CASE WHEN taker_side!=result THEN 1.0 ELSE 0.0 END)
            - (CASE WHEN taker_side='yes' THEN no_price ELSE yes_price END)/100.0
        ) AS excess,
        STDDEV(
            (CASE WHEN taker_side!=result THEN 1.0 ELSE 0.0 END)
            - (CASE WHEN taker_side='yes' THEN no_price ELSE yes_price END)/100.0
        ) AS sd,
        COUNT(*) AS n, SUM(count) AS contracts
    FROM joined GROUP BY category
)
SELECT 'taker' AS role, * FROM taker
UNION ALL
SELECT 'maker' AS role, * FROM maker;

-- ------------------------------------------------------------------------
-- Phase 2: (category, role, side, price_band) aggregates with mean and SD
-- ------------------------------------------------------------------------
-- Pre-filter to selected top groups via WHERE category IN (...)
WITH resolved AS (
    SELECT ticker, event_ticker, result
    FROM '<MARKETS_GLOB>'
    WHERE status='finalized' AND result IN ('yes','no')
),
joined AS (
    SELECT
        t.ticker, t.taker_side, t.yes_price, t.no_price, t.count, m.result,
        '<CATEGORY_SQL>' AS category   -- substituted via Python
    FROM '<TRADES_GLOB>' t
    INNER JOIN resolved m ON t.ticker = m.ticker
    WHERE t.created_time >= TIMESTAMP '2024-10-01'
      AND t.yes_price IS NOT NULL AND t.no_price IS NOT NULL
      AND t.yes_price + t.no_price = 100
      AND t.count > 0
),
taker AS (
    SELECT category, taker_side AS side, count,
        (CASE WHEN taker_side='yes' THEN yes_price ELSE no_price END)/100.0 AS price,
        (CASE WHEN taker_side=result THEN 1.0 ELSE 0.0 END) AS won
    FROM joined
),
maker AS (
    SELECT category,
        CASE WHEN taker_side='yes' THEN 'no' ELSE 'yes' END AS side,
        count,
        (CASE WHEN taker_side='yes' THEN no_price ELSE yes_price END)/100.0 AS price,
        (CASE WHEN taker_side!=result THEN 1.0 ELSE 0.0 END) AS won
    FROM joined
),
combined AS (
    SELECT 'taker' AS role, * FROM taker UNION ALL SELECT 'maker' AS role, * FROM maker
),
with_band AS (
    SELECT role, category, side, price, won, count,
        CASE
            WHEN price < 0.05 THEN '[0,0.05)'
            WHEN price < 0.20 THEN '[0.05,0.20)'
            WHEN price < 0.40 THEN '[0.20,0.40)'
            WHEN price < 0.60 THEN '[0.40,0.60)'
            WHEN price < 0.80 THEN '[0.60,0.80)'
            WHEN price < 0.95 THEN '[0.80,0.95)'
            ELSE '[0.95,1]'
        END AS price_band,
        CASE
            WHEN role='taker' THEN CEIL(0.07 * price * (1-price) * 100) / 100.0
            ELSE CEIL(0.0175 * price * (1-price) * 100) / 100.0
        END AS fee
    FROM combined
)
SELECT role, category, side, price_band,
    COUNT(*) AS n, SUM(count) AS contracts,
    AVG(price) AS avg_price, AVG(fee) AS avg_fee,
    AVG(won - price) AS gross_mean, STDDEV(won - price) AS gross_sd,
    AVG(won - price - fee) AS net_mean, STDDEV(won - price - fee) AS net_sd,
    AVG(won) AS win_rate
FROM with_band
GROUP BY role, category, side, price_band;

-- ------------------------------------------------------------------------
-- Phase 3: per (series_prefix, category, role, side, price_band) aggregate
-- ------------------------------------------------------------------------
-- Same as Phase 2 but adds split_part(ticker, '-', 1) as series_prefix in GROUP BY.
-- Output saved to research/v10a/05-phase3-prefix-agg.parquet for use by combined-side LOCO.

-- ------------------------------------------------------------------------
-- Resolution-balance sanity check
-- ------------------------------------------------------------------------
WITH active_markets AS (
    SELECT DISTINCT m.ticker, m.event_ticker, m.result
    FROM '<MARKETS_GLOB>' m
    WHERE m.status = 'finalized' AND m.result IN ('yes','no')
      AND m.ticker IN (
          SELECT DISTINCT ticker FROM '<TRADES_GLOB>'
          WHERE created_time >= TIMESTAMP '2024-10-01'
      )
)
SELECT
    '<CATEGORY_SQL>' AS category,
    COUNT(*) AS n_markets,
    SUM(CASE WHEN result = 'yes' THEN 1 ELSE 0 END) AS n_yes,
    SUM(CASE WHEN result = 'no' THEN 1 ELSE 0 END) AS n_no,
    AVG(CASE WHEN result = 'yes' THEN 1.0 ELSE 0.0 END) AS yes_frac
FROM active_markets
GROUP BY category;
