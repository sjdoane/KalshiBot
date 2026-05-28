"""Critic Test 4: does the next trade after t print at the stale mid or at spot-implied price?

This is the CENTRAL test. If next trade prints near spot-implied: phantom edge.
If next trade prints near stale mid: real edge.
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
    cb['time'] = pd.to_datetime(cb['time'], utc=True)

    joined = master.merge(
        preds_ok[['ticker', 'horizon_min', 'kronos_p_yes', 'kronos_sigma_close']],
        on=['ticker', 'horizon_min'], how='inner',
    )
    joined30 = joined[joined.horizon_min == 30].copy().sort_values('close_time').reset_index(drop=True)
    n = len(joined30)
    train_end = int(round(n * 0.60))
    orth_end = int(round(n * 0.85))
    tcm = joined30.iloc[train_end - 1]['close_time']
    purge = pd.Timedelta(hours=24)
    orth = joined30.iloc[train_end:orth_end].copy()
    orth = orth[orth['close_time'] >= tcm + purge].copy()
    orth_b = orth[(orth.kalshi_mid_at_t >= 0.55) & (orth.kalshi_mid_at_t <= 0.80)].copy()
    print(f'orth midband: {len(orth_b)}')

    STRIKE_RE = re.compile(r'-T(?P<strike>\d+(\.\d+)?)$')

    def parse_strike(ticker):
        m = STRIKE_RE.search(ticker)
        if not m:
            return float('nan')
        return float(m.group('strike'))

    from scipy.stats import norm
    cb_sorted = cb.sort_values('time').reset_index(drop=True)

    orth_b['t'] = pd.to_datetime(orth_b['t'], utc=True)
    orth_b['t'] = orth_b['t'].astype('datetime64[ns, UTC]')
    cb_sorted['time'] = cb_sorted['time'].astype('datetime64[ns, UTC]')
    orth_b_sorted = orth_b.sort_values('t').reset_index(drop=True)
    orth_b_sorted = pd.merge_asof(
        orth_b_sorted,
        cb_sorted[['time', 'close']].rename(columns={'time': 'cb_time', 'close': 'cb_spot_at_t'}),
        left_on='t', right_on='cb_time', direction='backward',
    )

    orth_b_sorted['strike'] = orth_b_sorted['ticker'].map(parse_strike)

    def naive_p(row):
        sigma = row['kronos_sigma_close']
        spot = row['cb_spot_at_t']
        strike = row['strike']
        if pd.isna(sigma) or sigma <= 0 or pd.isna(spot) or spot <= 0 or pd.isna(strike) or strike <= 0:
            return float('nan')
        z = (math.log(strike) - math.log(spot)) / sigma
        p = 1.0 - norm.cdf(z)
        return float(np.clip(p, 1e-3, 1.0 - 1e-3))

    orth_b_sorted['naive_p_yes'] = orth_b_sorted.apply(naive_p, axis=1)

    critical_yes = orth_b_sorted[
        (orth_b_sorted['time_since_last_trade_at_t'] >= 5)
        & (orth_b_sorted['naive_p_yes'] - orth_b_sorted['kalshi_mid_at_t'] >= 0.10)
    ].copy()
    critical_no = orth_b_sorted[
        (orth_b_sorted['time_since_last_trade_at_t'] >= 5)
        & ((1 - orth_b_sorted['naive_p_yes']) - (1 - orth_b_sorted['kalshi_mid_at_t']) >= 0.10)
    ].copy()
    print(f'BUY_YES candidates (naive_p - mid >= 0.10, stale): {len(critical_yes)}')
    print(f'BUY_NO candidates ((1-naive_p) - (1-mid) >= 0.10, stale): {len(critical_no)}')

    critical_all = pd.concat([
        critical_yes.assign(signal='BUY_YES'),
        critical_no.assign(signal='BUY_NO'),
    ], ignore_index=True)
    print(f'total: {len(critical_all)}')

    cache_dir = Path('data/v6/cache')
    results = []
    for _, row in critical_all.iterrows():
        ticker = row.ticker
        t = pd.Timestamp(row.t).tz_convert('UTC')
        close_time = pd.Timestamp(row.close_time).tz_convert('UTC')
        cache_path = cache_dir / f'trades_{ticker}.parquet'
        if not cache_path.exists():
            continue
        trades = pd.read_parquet(cache_path)
        if trades.empty:
            continue
        trades['created_time'] = pd.to_datetime(trades['created_time'], utc=True)
        trades['yes_price_dollars'] = pd.to_numeric(trades['yes_price_dollars'], errors='coerce')

        sub_next = trades[(trades['created_time'] > t) & (trades['created_time'] <= close_time)].sort_values('created_time')
        if sub_next.empty:
            results.append({
                'ticker': ticker, 'signal': row.signal, 'mid': row.kalshi_mid_at_t,
                'naive_p': row.naive_p_yes, 'next_trade_price': None,
                'minutes_to_next': None, 'taker_side': None, 'no_next_trade': True,
                'outcome_yes': row.outcome_yes,
            })
            continue
        next_trade = sub_next.iloc[0]
        next_price = float(next_trade['yes_price_dollars'])
        minutes_to_next = (next_trade['created_time'] - t).total_seconds() / 60.0
        taker_side = next_trade.get('taker_outcome_side', None)
        results.append({
            'ticker': ticker, 'signal': row.signal, 'mid': row.kalshi_mid_at_t,
            'naive_p': row.naive_p_yes, 'next_trade_price': next_price,
            'minutes_to_next': minutes_to_next, 'taker_side': taker_side,
            'no_next_trade': False,
            'outcome_yes': row.outcome_yes,
        })

    resdf = pd.DataFrame(results)
    print(f'\nTotal probed: {len(resdf)}; has next trade after t: {(~resdf.no_next_trade).sum()}, no next: {resdf.no_next_trade.sum()}')

    has_next = resdf[~resdf.no_next_trade].copy()
    has_next['mid_to_next'] = has_next['next_trade_price'] - has_next['mid']
    has_next['naive_to_next'] = has_next['next_trade_price'] - has_next['naive_p']
    has_next['signal_size'] = has_next['naive_p'] - has_next['mid']

    print()
    print('=== Test 4: NEXT TRADE BEHAVIOR ===')
    print(f'  Has-next n={len(has_next)}')
    print(f'  Mean mid_to_next (delta from stale mid): {has_next.mid_to_next.mean():.4f}')
    print(f'  Mean naive_to_next (residual unaccounted by spot): {has_next.naive_to_next.mean():.4f}')
    print(f'  Mean signal_size (naive_p - mid): {has_next.signal_size.mean():.4f}')
    print(f'  Median minutes to next trade: {has_next.minutes_to_next.median():.2f}')

    print('\nBy signal direction:')
    for sig in ['BUY_YES', 'BUY_NO']:
        s = has_next[has_next.signal == sig]
        if len(s) == 0:
            continue
        print(f'  {sig} n={len(s)}: mean mid_to_next={s.mid_to_next.mean():.4f}, mean naive_to_next={s.naive_to_next.mean():.4f}, mean signal={s.signal_size.mean():.4f}')
        if sig == 'BUY_YES':
            ratio_series = (s.next_trade_price - s.mid) / (s.naive_p - s.mid)
            ratio = ratio_series.replace([np.inf, -np.inf], np.nan).dropna()
            print(f'    BUY_YES: (next-mid)/(naive_p-mid) ratio: mean={ratio.mean():.3f}, median={ratio.median():.3f}, frac >= 0.5: {(ratio >= 0.5).mean():.3f}')
        else:
            ratio_series = (s.mid - s.next_trade_price) / (s.mid - s.naive_p)
            ratio = ratio_series.replace([np.inf, -np.inf], np.nan).dropna()
            print(f'    BUY_NO: (mid-next)/(mid-naive_p) ratio: mean={ratio.mean():.3f}, median={ratio.median():.3f}, frac >= 0.5: {(ratio >= 0.5).mean():.3f}')

    print('\nOutcome rates (does naive_p_yes correctly predict?):')
    for sig in ['BUY_YES', 'BUY_NO']:
        s = resdf[resdf.signal == sig]
        if len(s) == 0:
            continue
        print(f'  {sig} n={len(s)}: outcome_yes rate = {s.outcome_yes.mean():.3f}')
        s_naive_pred_yes = s[s.signal == 'BUY_YES']
        if sig == 'BUY_YES':
            # The signal says BUY YES because naive_p_yes >> mid. Did YES happen?
            print(f'    BUY_YES expects YES outcomes; got {s.outcome_yes.mean():.3f}')
        else:
            print(f'    BUY_NO expects NO outcomes; got 1-{s.outcome_yes.mean():.3f}={(1-s.outcome_yes.mean()):.3f}')

    print('\nFirst 15 BUY_YES examples:')
    ex = has_next[has_next.signal == 'BUY_YES'].head(15)
    print(ex[['ticker', 'mid', 'naive_p', 'next_trade_price', 'minutes_to_next', 'taker_side', 'outcome_yes']].to_string())
    print('\nFirst 15 BUY_NO examples:')
    ex = has_next[has_next.signal == 'BUY_NO'].head(15)
    print(ex[['ticker', 'mid', 'naive_p', 'next_trade_price', 'minutes_to_next', 'taker_side', 'outcome_yes']].to_string())

    # Save for later use
    resdf.to_parquet('data/v7/critic_test4_results.parquet', index=False)


if __name__ == '__main__':
    main()
