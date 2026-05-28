"""Critic Test 4b: deeper next-trade analysis.

Loosen the |naive_p - mid| threshold to get a bigger sample.
Also compute the proper next-trade-direction relative to naive_p.
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
    joined30 = joined[joined.horizon_min == 30].copy().sort_values('close_time').reset_index(drop=True)
    n = len(joined30)
    train_end = int(round(n * 0.60))
    orth_end = int(round(n * 0.85))
    tcm = joined30.iloc[train_end - 1]['close_time']
    purge = pd.Timedelta(hours=24)
    orth = joined30.iloc[train_end:orth_end].copy()
    orth = orth[orth['close_time'] >= tcm + purge].copy()
    orth_b = orth[(orth.kalshi_mid_at_t >= 0.55) & (orth.kalshi_mid_at_t <= 0.80)].copy()

    STRIKE_RE = re.compile(r'-T(?P<strike>\d+(\.\d+)?)$')

    def parse_strike(ticker):
        m = STRIKE_RE.search(ticker)
        if not m:
            return float('nan')
        return float(m.group('strike'))

    from scipy.stats import norm

    orth_b['t'] = pd.to_datetime(orth_b['t'], utc=True).astype('datetime64[ns, UTC]')
    orth_b_sorted = orth_b.sort_values('t').reset_index(drop=True)
    cb_sorted = cb.sort_values('time').reset_index(drop=True)
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
    orth_b_sorted['signal_strength'] = orth_b_sorted['naive_p_yes'] - orth_b_sorted['kalshi_mid_at_t']

    # Look at ALL orth contracts (with kronos so naive_p computable), not just |signal| >= 0.10
    cache_dir = Path('data/v6/cache')
    results = []
    for _, row in orth_b_sorted.iterrows():
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

        sub_next = trades[
            (trades['created_time'] > t) & (trades['created_time'] <= close_time)
        ].sort_values('created_time')
        if sub_next.empty:
            results.append({
                'ticker': ticker, 'mid': row.kalshi_mid_at_t, 'naive_p': row.naive_p_yes,
                'signal': row.signal_strength, 'tslt': row.time_since_last_trade_at_t,
                'next_trade_price': None, 'minutes_to_next': None,
                'no_next_trade': True, 'outcome_yes': row.outcome_yes,
                'n_trades_after_t': 0,
            })
            continue
        next_trade = sub_next.iloc[0]
        next_price = float(next_trade['yes_price_dollars'])
        minutes_to_next = (next_trade['created_time'] - t).total_seconds() / 60.0
        results.append({
            'ticker': ticker, 'mid': row.kalshi_mid_at_t, 'naive_p': row.naive_p_yes,
            'signal': row.signal_strength, 'tslt': row.time_since_last_trade_at_t,
            'next_trade_price': next_price,
            'minutes_to_next': minutes_to_next,
            'no_next_trade': False, 'outcome_yes': row.outcome_yes,
            'taker_side': next_trade.get('taker_outcome_side', None),
            'n_trades_after_t': len(sub_next),
        })

    resdf = pd.DataFrame(results)
    n_total = len(resdf)
    print(f'Orth midband total probed: {n_total}')
    print(f'Has next trade: {(~resdf.no_next_trade).sum()} ({(~resdf.no_next_trade).mean()*100:.1f}%)')
    print(f'No next trade: {resdf.no_next_trade.sum()} ({(resdf.no_next_trade).mean()*100:.1f}%)')

    # By tslt status
    print('\nFresh vs stale split:')
    fresh = resdf[resdf.tslt < 5]
    stale = resdf[resdf.tslt >= 5]
    print(f'  Fresh (tslt < 5): n={len(fresh)}, has-next: {(~fresh.no_next_trade).sum()} ({(~fresh.no_next_trade).mean()*100:.1f}%)')
    print(f'  Stale (tslt >= 5): n={len(stale)}, has-next: {(~stale.no_next_trade).sum()} ({(~stale.no_next_trade).mean()*100:.1f}%)')

    # By signal strength bucket
    print('\nBy abs signal strength (|naive_p - mid|) - has-next-trade rate:')
    for lo, hi in [(0, 0.05), (0.05, 0.10), (0.10, 0.20), (0.20, 0.50), (0.50, 1.0)]:
        s = resdf[(resdf.signal.abs() >= lo) & (resdf.signal.abs() < hi)]
        if len(s) == 0:
            continue
        has = (~s.no_next_trade).sum()
        print(f'  |signal| in [{lo:.2f}, {hi:.2f}): n={len(s)}, has-next: {has} ({has/len(s)*100:.1f}%)')

    # Now zoom into has-next: how does next-trade price relate to mid vs naive_p?
    has_next = resdf[~resdf.no_next_trade].copy()
    has_next['mid_to_next'] = has_next['next_trade_price'] - has_next['mid']
    # ratio of move from mid that's toward naive_p
    has_next['frac_move_explained'] = has_next.apply(
        lambda r: ((r.next_trade_price - r.mid) / (r.naive_p - r.mid)) if abs(r.naive_p - r.mid) > 1e-6 else float('nan'),
        axis=1,
    )

    # Cap ratio at -2 to 2 for sanity in averaging
    print('\nNext-trade price analysis (has-next only):')
    for lo, hi in [(0, 0.05), (0.05, 0.10), (0.10, 0.20), (0.20, 1.0)]:
        s = has_next[(has_next.signal.abs() >= lo) & (has_next.signal.abs() < hi)]
        if len(s) < 3:
            continue
        capped = s.frac_move_explained.clip(-2, 2)
        print(f'  |signal| [{lo}, {hi}): n={len(s)}, mean(next-mid)={s.mid_to_next.mean():.4f}, mean(frac_move_explained capped)={capped.mean():.3f}, median={s.frac_move_explained.median():.3f}')

    # All has-next regardless of signal
    print(f'\nALL has-next n={len(has_next)}:')
    capped = has_next.frac_move_explained.clip(-2, 2)
    print(f'  mean(next-mid)={has_next.mid_to_next.mean():.4f}')
    print(f'  mean frac_move_explained capped: {capped.mean():.3f}')
    print(f'  median frac_move_explained: {has_next.frac_move_explained.median():.3f}')

    # Critically: in the has-next subset where |signal| is strong, what's the distribution of next-trade?
    strong = has_next[has_next.signal.abs() >= 0.10]
    print(f'\n=== STRONG SIGNAL has-next n={len(strong)} ===')
    print(f'  mean signal: {strong.signal.mean():.4f}')
    print(f'  mean next price: {strong.next_trade_price.mean():.4f}')
    print(f'  mean mid: {strong.mid.mean():.4f}')
    print(f'  mean naive_p: {strong.naive_p.mean():.4f}')
    print(f'  mean (next - mid): {strong.mid_to_next.mean():.4f}')
    print(f'  if next stayed exactly at mid: mid_to_next = 0')
    print(f'  if next moved fully to naive_p: mid_to_next = mean(signal) = {strong.signal.mean():.4f}')
    print(f'  observed mid_to_next as fraction of signal: {(strong.mid_to_next.mean() / strong.signal.mean()):.3f}')

    # Save and dump all has-next for inspection
    has_next.to_parquet('data/v7/critic_test4_has_next.parquet', index=False)
    resdf.to_parquet('data/v7/critic_test4_all.parquet', index=False)
    print('\nSaved data/v7/critic_test4_has_next.parquet and critic_test4_all.parquet')


if __name__ == '__main__':
    main()
