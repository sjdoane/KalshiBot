"""Critic Test 5 REALISTIC v2: properly account for the fact that the +2c rule needs the ACTUAL ASK
and if the ASK moved with spot, the rule may fire less often.

We use the observed minimum yes-taker print after t as a proxy for the actual ASK at the moment we'd have placed our order.
For contracts with no post-t trade: we don't know what the ASK was, so we drop those (CONSERVATIVE).
"""
import pandas as pd
import numpy as np
from pathlib import Path
import math
import re
import sys
sys.path.insert(0, 'src')


def main():
    master = pd.read_parquet('data/v6/v6_master.parquet')
    preds = pd.read_parquet('data/v7/kronos_predictions.parquet')
    preds_ok = preds[preds.status == 'ok'].copy()
    cb_v6 = pd.read_parquet('data/v6/cache/coinbase_1m.parquet')
    cb_v7 = pd.read_parquet('data/v7/cache/coinbase_1m_v7.parquet')
    cb = pd.concat([cb_v6, cb_v7], ignore_index=True).drop_duplicates('time').sort_values('time').reset_index(drop=True)
    cb['time'] = pd.to_datetime(cb['time'], utc=True).astype('datetime64[ns, UTC]')

    joined = master.merge(
        preds_ok[['ticker', 'horizon_min', 'kronos_p_yes', 'kronos_sigma_close']],
        on=['ticker', 'horizon_min'], how='inner',
    )

    STRIKE_RE = re.compile(r'-T(?P<strike>\d+(\.\d+)?)$')

    def parse_strike(ticker):
        m = STRIKE_RE.search(ticker)
        if not m:
            return float('nan')
        return float(m.group('strike'))

    from scipy.stats import norm
    cb_sorted = cb.sort_values('time').reset_index(drop=True)
    joined['t'] = pd.to_datetime(joined['t'], utc=True).astype('datetime64[ns, UTC]')
    joined_sorted = joined.sort_values('t').reset_index(drop=True)
    joined_sorted = pd.merge_asof(
        joined_sorted,
        cb_sorted[['time', 'close']].rename(columns={'time': 'cb_time', 'close': 'cb_spot_at_t'}),
        left_on='t', right_on='cb_time', direction='backward',
    )
    joined_sorted['strike'] = joined_sorted['ticker'].map(parse_strike)

    def naive_p(row):
        sigma = row['kronos_sigma_close']
        spot = row['cb_spot_at_t']
        strike = row['strike']
        if pd.isna(sigma) or sigma <= 0 or pd.isna(spot) or spot <= 0 or pd.isna(strike) or strike <= 0:
            return float('nan')
        z = (math.log(strike) - math.log(spot)) / sigma
        p = 1.0 - norm.cdf(z)
        return float(np.clip(p, 1e-3, 1.0 - 1e-3))

    joined_sorted['naive_p_yes'] = joined_sorted.apply(naive_p, axis=1)

    df = joined_sorted[joined_sorted.horizon_min == 30].copy().sort_values('close_time').reset_index(drop=True)
    n = len(df)
    train_end = int(round(n * 0.60))
    orth_end = int(round(n * 0.85))
    tcm = df.iloc[train_end - 1]['close_time']
    purge = pd.Timedelta(hours=24)
    orth = df.iloc[train_end:orth_end].copy()
    orth = orth[orth['close_time'] >= tcm + purge].copy()
    orth_b = orth[(orth.kalshi_mid_at_t >= 0.55) & (orth.kalshi_mid_at_t <= 0.80)].copy()
    print(f'orth midband: {len(orth_b)}')

    cache_dir = Path('data/v6/cache')
    def get_post_t_trade_info(row):
        ticker = row.ticker
        t = pd.Timestamp(row.t).tz_convert('UTC')
        close_time = pd.Timestamp(row.close_time).tz_convert('UTC')
        cache_path = cache_dir / f'trades_{ticker}.parquet'
        if not cache_path.exists():
            return None, None, None, None
        trades = pd.read_parquet(cache_path)
        if trades.empty:
            return None, None, None, None
        trades['created_time'] = pd.to_datetime(trades['created_time'], utc=True)
        trades['yes_price_dollars'] = pd.to_numeric(trades['yes_price_dollars'], errors='coerce')
        post = trades[(trades['created_time'] > t) & (trades['created_time'] <= close_time)].copy()
        if post.empty:
            return 0, None, None, None
        post = post.sort_values('created_time')
        yes_taker = post[post.get('taker_outcome_side') == 'yes']
        no_taker = post[post.get('taker_outcome_side') == 'no']
        min_ask = float(yes_taker['yes_price_dollars'].min()) if len(yes_taker) > 0 else None
        max_bid = float(no_taker['yes_price_dollars'].max()) if len(no_taker) > 0 else None
        n_trades = len(post)
        return n_trades, min_ask, max_bid, float(post.iloc[0]['yes_price_dollars'])

    print('computing post-t trade info...')
    info = orth_b.apply(get_post_t_trade_info, axis=1, result_type='expand')
    info.columns = ['n_trades_after_t', 'min_yes_ask_after_t', 'max_yes_bid_after_t', 'first_trade_price']
    orth_b = pd.concat([orth_b.reset_index(drop=True), info.reset_index(drop=True)], axis=1)

    def take_fee(p):
        if pd.isna(p) or p <= 0 or p >= 1:
            return 0.0
        return math.ceil(7 * p * (1 - p)) / 100

    # Strategy 1: STALE-MID model (original simulation, +0.20 lift universe)
    # Strategy 2: REALISTIC - use observed min ask / max bid as proxy for true bid/ask
    # Strategy 3: SUPER REALISTIC - drop contracts with no post-t trades (the actual orderbook is unknown)

    spread_default = 0.02
    naive_fires = []
    real_fires_observed_ask = []
    real_fires_observed_ask_keep_no_trade = []

    for _, row in orth_b.iterrows():
        mp = row.naive_p_yes
        mid = row.kalshi_mid_at_t
        outcome = row.outcome_yes
        if pd.isna(mp) or pd.isna(mid):
            continue
        yes_ask_naive = mid + spread_default/2
        no_ask_naive = 1 - mid + spread_default/2

        # Naive rule
        if (mp >= yes_ask_naive + 0.02) and (yes_ask_naive >= 0.20) and (yes_ask_naive <= 0.85):
            gross = outcome - yes_ask_naive
            pnl = gross - take_fee(yes_ask_naive)
            naive_fires.append({'side':'YES','pnl':pnl,'date':pd.Timestamp(row.close_time).date(),'ticker':row.ticker})
        if ((1-mp) >= no_ask_naive + 0.02) and (no_ask_naive >= 0.20) and (no_ask_naive <= 0.85):
            gross = (1-outcome) - no_ask_naive
            pnl = gross - take_fee(no_ask_naive)
            naive_fires.append({'side':'NO','pnl':pnl,'date':pd.Timestamp(row.close_time).date(),'ticker':row.ticker})

        # Realistic: use observed min ASK (yes-taker prints) as the actual ASK at time t.
        # If no yes-taker print observed, the ASK is unknown.
        # We use the first trade price as a fallback proxy IFF first trade is yes-taker; otherwise drop.
        actual_ask = row.min_yes_ask_after_t if pd.notna(row.min_yes_ask_after_t) else None
        actual_bid = row.max_yes_bid_after_t if pd.notna(row.max_yes_bid_after_t) else None

        # BUY YES: need actual_ask known; rule fires if mp >= actual_ask + 0.02
        if actual_ask is not None:
            if (mp >= actual_ask + 0.02) and (actual_ask >= 0.20) and (actual_ask <= 0.85):
                gross = outcome - actual_ask
                pnl = gross - take_fee(actual_ask)
                real_fires_observed_ask.append({'side':'YES','pnl':pnl,'price':actual_ask,'date':pd.Timestamp(row.close_time).date(),'ticker':row.ticker})
                real_fires_observed_ask_keep_no_trade.append({'side':'YES','pnl':pnl,'price':actual_ask,'date':pd.Timestamp(row.close_time).date(),'ticker':row.ticker})
        else:
            # No yes-taker print observed. ASK is UNKNOWN. Conservative: do not fire.
            # But Strategy 2b: assume ASK = mid+0.01 (stale) and fire if rule says so
            if (mp >= yes_ask_naive + 0.02) and (yes_ask_naive >= 0.20) and (yes_ask_naive <= 0.85):
                # FAKE: we'd be placing an order at mid+0.01 hoping someone is there
                # We have no evidence the ASK was actually at that level
                # Skip from real_fires_observed_ask
                # But keep in real_fires_observed_ask_keep_no_trade as "assume stale ASK"
                gross = outcome - yes_ask_naive
                pnl = gross - take_fee(yes_ask_naive)
                real_fires_observed_ask_keep_no_trade.append({'side':'YES','pnl':pnl,'price':yes_ask_naive,'date':pd.Timestamp(row.close_time).date(),'ticker':row.ticker})

        if actual_bid is not None:
            actual_no_ask = 1 - actual_bid
            if ((1-mp) >= actual_no_ask + 0.02) and (actual_no_ask >= 0.20) and (actual_no_ask <= 0.85):
                gross = (1-outcome) - actual_no_ask
                pnl = gross - take_fee(actual_no_ask)
                real_fires_observed_ask.append({'side':'NO','pnl':pnl,'price':actual_no_ask,'date':pd.Timestamp(row.close_time).date(),'ticker':row.ticker})
                real_fires_observed_ask_keep_no_trade.append({'side':'NO','pnl':pnl,'price':actual_no_ask,'date':pd.Timestamp(row.close_time).date(),'ticker':row.ticker})
        else:
            if ((1-mp) >= no_ask_naive + 0.02) and (no_ask_naive >= 0.20) and (no_ask_naive <= 0.85):
                gross = (1-outcome) - no_ask_naive
                pnl = gross - take_fee(no_ask_naive)
                real_fires_observed_ask_keep_no_trade.append({'side':'NO','pnl':pnl,'price':no_ask_naive,'date':pd.Timestamp(row.close_time).date(),'ticker':row.ticker})

    def cluster_bs(pnls, dates, n_iter=5000, seed=42):
        if not pnls:
            return None,None,None,0
        unique_dates = sorted(set(dates))
        date_to_idx = {d: [i for i,x in enumerate(dates) if x==d] for d in unique_dates}
        n_days = len(unique_dates)
        if n_days < 3:
            return float(np.mean(pnls)), None, None, n_days
        rng = np.random.default_rng(seed)
        means = np.empty(n_iter)
        for i in range(n_iter):
            samp = rng.choice(unique_dates, size=n_days, replace=True)
            idxs = [j for d in samp for j in date_to_idx[d]]
            means[i] = np.mean([pnls[j] for j in idxs])
        return float(np.mean(means)), float(np.percentile(means,2.5)), float(np.percentile(means,97.5)), n_days

    print('\n=== Strategy 1: NAIVE (assume ASK = stale_mid + 1c regardless of orderbook reality) ===')
    fdf = pd.DataFrame(naive_fires)
    if len(fdf) > 0:
        ys = fdf[fdf.side=='YES']; ns = fdf[fdf.side=='NO']
        m, lo, hi, nd = cluster_bs(fdf.pnl.tolist(), fdf.date.tolist())
        print(f'  n_fires={len(fdf)} (YES={len(ys)}, NO={len(ns)})')
        print(f'  mean_pnl={fdf.pnl.mean()*100:.3f}c, CI=[{lo*100:.3f}c, {hi*100:.3f}c], n_days={nd}')

    print('\n=== Strategy 2: REALISTIC observed ASK (drop if no yes-taker print) ===')
    fdf = pd.DataFrame(real_fires_observed_ask)
    if len(fdf) > 0:
        ys = fdf[fdf.side=='YES']; ns = fdf[fdf.side=='NO']
        m, lo, hi, nd = cluster_bs(fdf.pnl.tolist(), fdf.date.tolist())
        print(f'  n_fires={len(fdf)} (YES={len(ys)}, NO={len(ns)})')
        print(f'  mean_pnl={fdf.pnl.mean()*100:.3f}c, CI=[{lo*100 if lo else None}c, {hi*100 if hi else None}c], n_days={nd}')

    print('\n=== Strategy 3: HYBRID - use observed ASK if available, else stale-mid assumption ===')
    fdf = pd.DataFrame(real_fires_observed_ask_keep_no_trade)
    if len(fdf) > 0:
        ys = fdf[fdf.side=='YES']; ns = fdf[fdf.side=='NO']
        m, lo, hi, nd = cluster_bs(fdf.pnl.tolist(), fdf.date.tolist())
        print(f'  n_fires={len(fdf)} (YES={len(ys)}, NO={len(ns)})')
        print(f'  mean_pnl={fdf.pnl.mean()*100:.3f}c, CI=[{lo*100:.3f}c, {hi*100:.3f}c], n_days={nd}')

    # Also: what if we always use OBSERVED ASK +1c as the rule's ASK input, but only fire when matched?
    print('\n=== ASK DELTA-FROM-STALE-MID DISTRIBUTION (where observed) ===')
    obs_yes_ask = orth_b[orth_b.min_yes_ask_after_t.notna()].copy()
    obs_yes_ask['ask_delta_from_mid'] = obs_yes_ask['min_yes_ask_after_t'] - obs_yes_ask['kalshi_mid_at_t']
    print(f'  n with observed yes-taker print: {len(obs_yes_ask)}')
    print(f'  mean ask_delta_from_mid: {obs_yes_ask.ask_delta_from_mid.mean():.4f}')
    print(f'  median: {obs_yes_ask.ask_delta_from_mid.median():.4f}')
    print(f'  std: {obs_yes_ask.ask_delta_from_mid.std():.4f}')
    print(f'  pct of observed asks within 2c of stale mid: {(obs_yes_ask.ask_delta_from_mid.abs() <= 0.02).mean()*100:.1f}%')
    print(f'  pct of observed asks within 5c of stale mid: {(obs_yes_ask.ask_delta_from_mid.abs() <= 0.05).mean()*100:.1f}%')
    print(f'  pct of observed asks moved with spot (|delta| > 0.10): {(obs_yes_ask.ask_delta_from_mid.abs() > 0.10).mean()*100:.1f}%')

    # Save outputs
    orth_b.to_parquet('data/v7/critic_test5_realistic2_orth.parquet', index=False)


if __name__ == '__main__':
    main()
