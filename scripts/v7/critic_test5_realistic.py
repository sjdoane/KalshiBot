"""Critic Test 5 REALISTIC: re-run the +2c-take simulation but ONLY fire on contracts where:
- the simulated taker order would have been filled
- proxy: only consider rows where there is at least one trade after t (in [t, close_time]) at a price <= mid + spread/2 + 0.02

This intersects the simulation with empirical fill evidence.
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

    # For each row, find the lowest YES ask print between t and close_time (proxy for actual ASK)
    cache_dir = Path('data/v6/cache')
    # Take ALL trades between t and close, look at the minimum yes-side ask print
    # (taker_outcome_side='yes' means someone hit the YES ASK; price IS the yes_ask at that moment)
    def get_post_t_trade_info(row):
        ticker = row.ticker
        t = pd.Timestamp(row.t).tz_convert('UTC')
        close_time = pd.Timestamp(row.close_time).tz_convert('UTC')
        cache_path = cache_dir / f'trades_{ticker}.parquet'
        if not cache_path.exists():
            return None, None, None, None, None
        trades = pd.read_parquet(cache_path)
        if trades.empty:
            return None, None, None, None, None
        trades['created_time'] = pd.to_datetime(trades['created_time'], utc=True)
        trades['yes_price_dollars'] = pd.to_numeric(trades['yes_price_dollars'], errors='coerce')
        post = trades[(trades['created_time'] > t) & (trades['created_time'] <= close_time)].copy()
        if post.empty:
            return 0, None, None, None, None
        post = post.sort_values('created_time')
        # Lowest YES-ask print (any trade where taker=yes means the print = ask at time)
        yes_taker = post[post.get('taker_outcome_side') == 'yes']
        no_taker = post[post.get('taker_outcome_side') == 'no']
        min_ask = float(yes_taker['yes_price_dollars'].min()) if len(yes_taker) > 0 else None
        max_bid = float(no_taker['yes_price_dollars'].max()) if len(no_taker) > 0 else None  # NO taker = trade at bid for YES
        n_trades = len(post)
        first_trade_price = float(post.iloc[0]['yes_price_dollars'])
        return n_trades, min_ask, max_bid, first_trade_price, len(yes_taker)

    print('computing post-t trade info per row...')
    info = orth_b.apply(get_post_t_trade_info, axis=1, result_type='expand')
    info.columns = ['n_trades_after_t', 'min_yes_ask_after_t', 'max_yes_bid_after_t', 'first_trade_price', 'n_yes_taker_trades']
    orth_b = pd.concat([orth_b.reset_index(drop=True), info.reset_index(drop=True)], axis=1)

    # Now: realistic-fill simulation
    # BUY_YES: would have been filled if min_yes_ask_after_t <= our limit price
    #          our limit price = kalshi_mid_at_t + 0.01 (the assumed +2c-take ask)
    #          BUT: the +2c rule says BUY YES if naive_p >= yes_ask + 0.02
    #          we'd post a TAKER order at yes_ask (no slippage worse than +1c, per Agent C)
    #          fill happens iff someone's ask matches our taker buy

    def take_fee(p):
        if pd.isna(p) or p <= 0 or p >= 1:
            return 0.0
        return math.ceil(7 * p * (1 - p)) / 100

    fires_naive = []
    fires_realistic_yes_taker = []  # only count if there's at least one yes-taker trade we could match
    fires_realistic_first_trade = []  # use the FIRST trade after t as the price we'd actually pay

    spread = 0.02
    for _, row in orth_b.iterrows():
        mp = row.naive_p_yes
        mid = row.kalshi_mid_at_t
        outcome = row.outcome_yes
        if pd.isna(mp) or pd.isna(mid):
            continue
        yes_ask_assumed = mid + spread/2
        # +2c-take: BUY YES if mp >= yes_ask + 0.02, 0.20 <= yes_ask <= 0.85
        buy_yes_signal = (mp >= yes_ask_assumed + 0.02) and (yes_ask_assumed >= 0.20) and (yes_ask_assumed <= 0.85)
        # BUY NO if (1-mp) >= no_ask + 0.02
        no_ask_assumed = 1 - mid + spread/2
        buy_no_signal = ((1-mp) >= no_ask_assumed + 0.02) and (no_ask_assumed >= 0.20) and (no_ask_assumed <= 0.85)

        if buy_yes_signal:
            # Naive: assume fill at assumed ask
            gross = outcome - yes_ask_assumed
            pnl = gross - take_fee(yes_ask_assumed)
            fires_naive.append({'side':'YES', 'pnl':pnl, 'price':yes_ask_assumed, 'date':pd.Timestamp(row.close_time).date()})

            # Realistic v1: only count if there's a YES-taker trade we could match
            if row.n_yes_taker_trades and row.n_yes_taker_trades > 0:
                # Pay actual min ask observed
                actual_ask = row.min_yes_ask_after_t
                gross_r = outcome - actual_ask
                pnl_r = gross_r - take_fee(actual_ask)
                fires_realistic_yes_taker.append({'side':'YES', 'pnl':pnl_r, 'price':actual_ask, 'date':pd.Timestamp(row.close_time).date()})

            # Realistic v2: use FIRST trade price (whoever crossed first, that's the level our order would have filled at)
            if row.n_trades_after_t and row.n_trades_after_t > 0:
                actual_ask2 = row.first_trade_price
                gross_r2 = outcome - actual_ask2
                pnl_r2 = gross_r2 - take_fee(actual_ask2)
                fires_realistic_first_trade.append({'side':'YES', 'pnl':pnl_r2, 'price':actual_ask2, 'date':pd.Timestamp(row.close_time).date()})

        if buy_no_signal:
            # BUY NO at assumed no_ask = 1 - mid + 0.01
            gross = (1 - outcome) - no_ask_assumed
            pnl = gross - take_fee(no_ask_assumed)
            fires_naive.append({'side':'NO', 'pnl':pnl, 'price':no_ask_assumed, 'date':pd.Timestamp(row.close_time).date()})

            # Realistic: BUY NO is equivalent to SELL YES at bid. We pay (1 - yes_bid).
            # Observed YES bid prices come from NO-taker trades (taker sold YES at the bid).
            # We need a NO-taker print to confirm bid level.
            if row.max_yes_bid_after_t is not None:
                actual_no_ask = 1 - row.max_yes_bid_after_t
                gross_r = (1 - outcome) - actual_no_ask
                pnl_r = gross_r - take_fee(actual_no_ask)
                fires_realistic_yes_taker.append({'side':'NO', 'pnl':pnl_r, 'price':actual_no_ask, 'date':pd.Timestamp(row.close_time).date()})

            if row.n_trades_after_t and row.n_trades_after_t > 0:
                # If first trade is NO-taker: bid at first price. NO_ask = 1 - first_price
                # If first trade is YES-taker: ask at first price. NO_ask = 1 - (first_price - 0.01) (approx bid)
                # Use the first trade price as midpoint estimate
                actual_no_ask2 = 1 - row.first_trade_price  # conservative
                gross_r2 = (1 - outcome) - actual_no_ask2
                pnl_r2 = gross_r2 - take_fee(actual_no_ask2)
                fires_realistic_first_trade.append({'side':'NO', 'pnl':pnl_r2, 'price':actual_no_ask2, 'date':pd.Timestamp(row.close_time).date()})

    def cluster_bs(pnls, dates, n_iter=5000, seed=42):
        if not pnls: return None,None,None,0
        unique_dates = sorted(set(dates))
        date_to_idx = {d: [i for i,x in enumerate(dates) if x==d] for d in unique_dates}
        n_days = len(unique_dates)
        rng = np.random.default_rng(seed)
        means = np.empty(n_iter)
        for i in range(n_iter):
            samp = rng.choice(unique_dates, size=n_days, replace=True)
            idxs = [j for d in samp for j in date_to_idx[d]]
            means[i] = np.mean([pnls[j] for j in idxs])
        return float(np.mean(means)), float(np.percentile(means,2.5)), float(np.percentile(means,97.5)), n_days

    print('\n=== NAIVE (assumed ASK = mid + 1c) ===')
    fdf = pd.DataFrame(fires_naive)
    if len(fdf) > 0:
        m, lo, hi, nd = cluster_bs(fdf.pnl.tolist(), fdf.date.tolist())
        print(f'  n_fires={len(fdf)}, mean_pnl={fdf.pnl.mean()*100:.3f}c, cluster-bootstrap CI=[{lo*100:.3f}c, {hi*100:.3f}c], n_days={nd}')

    print('\n=== REALISTIC v1: only count if matched yes-taker / no-taker observed (use observed price) ===')
    fdf = pd.DataFrame(fires_realistic_yes_taker)
    if len(fdf) > 0:
        m, lo, hi, nd = cluster_bs(fdf.pnl.tolist(), fdf.date.tolist())
        print(f'  n_fires={len(fdf)}, mean_pnl={fdf.pnl.mean()*100:.3f}c, cluster-bootstrap CI=[{lo*100:.3f}c, {hi*100:.3f}c], n_days={nd}')

    print('\n=== REALISTIC v2: use FIRST trade price as proxy for actual fill price ===')
    fdf = pd.DataFrame(fires_realistic_first_trade)
    if len(fdf) > 0:
        m, lo, hi, nd = cluster_bs(fdf.pnl.tolist(), fdf.date.tolist())
        print(f'  n_fires={len(fdf)}, mean_pnl={fdf.pnl.mean()*100:.3f}c, cluster-bootstrap CI=[{lo*100:.3f}c, {hi*100:.3f}c], n_days={nd}')

    # Also: just report on how often there's a trade after t for contracts where the +2c rule fires
    naive_fired_yes_count = sum(1 for f in fires_naive if f['side']=='YES')
    naive_fired_no_count = sum(1 for f in fires_naive if f['side']=='NO')
    print(f'\nNAIVE total fires: {len(fires_naive)} (YES={naive_fired_yes_count}, NO={naive_fired_no_count})')
    print(f'realistic v2 fires (any trade after t): {len(fires_realistic_first_trade)} ({len(fires_realistic_first_trade)/max(1,len(fires_naive))*100:.1f}% of naive)')
    print(f'realistic v1 fires (matched taker side): {len(fires_realistic_yes_taker)} ({len(fires_realistic_yes_taker)/max(1,len(fires_naive))*100:.1f}% of naive)')

if __name__ == '__main__':
    main()
