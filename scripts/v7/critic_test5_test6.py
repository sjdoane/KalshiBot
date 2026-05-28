"""Critic Tests 5, 6, 7: +2c-take rule and maker-quote rule simulation on naive_p_yes.

Per v6 Section 6.1 / 6.2 / 6.3.
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
    ocm = df.iloc[orth_end - 1]['close_time']
    purge = pd.Timedelta(hours=24)
    train = df.iloc[:train_end].copy()
    orth = df.iloc[train_end:orth_end].copy()
    orth = orth[orth['close_time'] >= tcm + purge].copy()
    final = df.iloc[orth_end:].copy()
    final = final[final['close_time'] >= ocm + purge].copy()
    print(f'n_train_all={len(train)}, n_orth_all={len(orth)}, n_final_all={len(final)}')

    train_b = train[(train.kalshi_mid_at_t >= 0.55) & (train.kalshi_mid_at_t <= 0.80)].copy()
    orth_b = orth[(orth.kalshi_mid_at_t >= 0.55) & (orth.kalshi_mid_at_t <= 0.80)].copy()
    final_b = final[(final.kalshi_mid_at_t >= 0.55) & (final.kalshi_mid_at_t <= 0.80)].copy()
    print(f'midband: train={len(train_b)}, orth={len(orth_b)}, final={len(final_b)}')

    # Kalshi fee formula (taker): ceil(0.07 * C * P * (1-P))
    # Per v1 metrics module typically. Per-contract = 1 contract.
    def take_fee(price):
        return math.ceil(7 * price * (1 - price)) / 100  # cents, contract=1

    def maker_fee(price):
        return math.ceil(1.75 * price * (1 - price)) / 100

    def simulate_take_rule(df, spread=0.02, name='+2c'):
        """v6 Section 6.1 +2c-take rule. naive_p_yes is the model_prob."""
        results = []
        for _, row in df.iterrows():
            mp = row['naive_p_yes']
            mid = row['kalshi_mid_at_t']
            outcome = row['outcome_yes']
            if pd.isna(mp) or pd.isna(mid):
                continue
            yes_ask = mid + spread / 2
            yes_bid = mid - spread / 2
            no_ask = 1 - yes_bid  # = 1 - mid + spread/2
            # BUY YES: model_prob >= yes_ask + 0.02, 0.20 <= yes_ask <= 0.85
            buy_yes_signal = (mp >= yes_ask + 0.02) and (yes_ask >= 0.20) and (yes_ask <= 0.85)
            # BUY NO: (1 - model_prob) >= no_ask + 0.02, 0.20 <= no_ask <= 0.85
            buy_no_signal = ((1 - mp) >= no_ask + 0.02) and (no_ask >= 0.20) and (no_ask <= 0.85)
            if buy_yes_signal:
                # pay yes_ask, receive 1 if outcome == 1 else 0
                gross = outcome - yes_ask
                fee = take_fee(yes_ask)
                pnl = gross - fee
                results.append({'side': 'YES', 'price': yes_ask, 'gross': gross, 'fee': fee, 'pnl': pnl, 'outcome': outcome, 'date': pd.Timestamp(row['close_time']).date()})
            if buy_no_signal:
                gross = (1 - outcome) - no_ask
                fee = take_fee(no_ask)
                pnl = gross - fee
                results.append({'side': 'NO', 'price': no_ask, 'gross': gross, 'fee': fee, 'pnl': pnl, 'outcome': outcome, 'date': pd.Timestamp(row['close_time']).date()})
        return pd.DataFrame(results)

    def simulate_maker_rule(df, fill_rate=0.15, name='+4c'):
        """v6 Section 6.2 maker-quote rule."""
        results = []
        for _, row in df.iterrows():
            mp = row['naive_p_yes']
            mid = row['kalshi_mid_at_t']
            outcome = row['outcome_yes']
            if pd.isna(mp) or pd.isna(mid):
                continue
            # BUY YES if mp - mid >= 0.04 and 0.30 <= mid <= 0.85; quote at mid-0.01
            buy_yes = (mp - mid >= 0.04) and (mid >= 0.30) and (mid <= 0.85)
            buy_no = ((1 - mp) - (1 - mid) >= 0.04) and ((1 - mid) >= 0.30) and ((1 - mid) <= 0.85)
            if buy_yes:
                quote = mid - 0.01
                gross = outcome - quote
                fee = maker_fee(quote)
                pnl_filled = gross - fee
                ex_pnl = fill_rate * pnl_filled
                results.append({'side': 'YES', 'quote': quote, 'gross_conditional': gross, 'fee': fee, 'pnl_filled': pnl_filled, 'ex_pnl': ex_pnl, 'outcome': outcome, 'date': pd.Timestamp(row['close_time']).date()})
            if buy_no:
                quote = (1 - mid) - 0.01
                gross = (1 - outcome) - quote
                fee = maker_fee(quote)
                pnl_filled = gross - fee
                ex_pnl = fill_rate * pnl_filled
                results.append({'side': 'NO', 'quote': quote, 'gross_conditional': gross, 'fee': fee, 'pnl_filled': pnl_filled, 'ex_pnl': ex_pnl, 'outcome': outcome, 'date': pd.Timestamp(row['close_time']).date()})
        return pd.DataFrame(results)

    def cluster_bootstrap(pnls, dates, n_iter=5000, seed=42):
        unique_dates = sorted(set(dates))
        date_to_idx = {d: [i for i, x in enumerate(dates) if x == d] for d in unique_dates}
        n_days = len(unique_dates)
        rng = np.random.default_rng(seed)
        means = np.empty(n_iter)
        for i in range(n_iter):
            sampled = rng.choice(unique_dates, size=n_days, replace=True)
            idxs = [j for d in sampled for j in date_to_idx[d]]
            means[i] = np.mean([pnls[j] for j in idxs])
        return float(np.mean(means)), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)), n_days

    print('\n=== Test 5: +2c-TAKE RULE ON naive_p_yes (orth holdout) ===')
    for spread in [0.02, 0.03, 0.04, 0.05]:
        fires = simulate_take_rule(orth_b, spread=spread)
        if len(fires) == 0:
            print(f'  spread={spread:.2f}: 0 fires')
            continue
        mean_pnl = fires['pnl'].mean() * 100  # cents
        ci_mean, ci_lo, ci_hi, ndays = cluster_bootstrap(fires['pnl'].tolist(), fires['date'].tolist())
        ci_lo *= 100
        ci_hi *= 100
        ci_mean *= 100
        print(f'  spread={spread:.2f}: n_fires={len(fires)} mean_pnl={mean_pnl:.3f}c bootstrap_mean={ci_mean:.3f}c CI=[{ci_lo:.3f}c, {ci_hi:.3f}c] n_days={ndays}')
        # breakdown by side
        for side in ['YES', 'NO']:
            s = fires[fires.side == side]
            if len(s) > 0:
                print(f'    {side}: n={len(s)}, mean_pnl={s.pnl.mean()*100:.3f}c, mean_gross={s.gross.mean()*100:.3f}c, hit_rate={s.outcome.mean():.3f}')

    print('\n=== Test 5 also on FINAL HOLDOUT ===')
    fires_f = simulate_take_rule(final_b, spread=0.02)
    if len(fires_f) > 0:
        ci_mean, ci_lo, ci_hi, ndays = cluster_bootstrap(fires_f['pnl'].tolist(), fires_f['date'].tolist())
        print(f'  FINAL spread=0.02: n_fires={len(fires_f)} mean_pnl={fires_f.pnl.mean()*100:.3f}c bootstrap_mean={ci_mean*100:.3f}c CI=[{ci_lo*100:.3f}c, {ci_hi*100:.3f}c] n_days={ndays}')

    print('\n=== Test 6: MAKER-QUOTE RULE ON naive_p_yes (orth holdout) ===')
    for fill in [0.15, 0.10, 0.05]:
        fires = simulate_maker_rule(orth_b, fill_rate=fill)
        if len(fires) == 0:
            print(f'  fill={fill}: 0 fires')
            continue
        mean_ex = fires['ex_pnl'].mean() * 100
        ci_mean, ci_lo, ci_hi, ndays = cluster_bootstrap(fires['ex_pnl'].tolist(), fires['date'].tolist())
        ci_mean *= 100
        ci_lo *= 100
        ci_hi *= 100
        print(f'  fill_rate={fill}: n_fires={len(fires)} mean_ex_pnl={mean_ex:.3f}c CI=[{ci_lo:.3f}c, {ci_hi:.3f}c] n_days={ndays}')
        # Also conditional pnl (if filled)
        mean_cond = fires['pnl_filled'].mean() * 100
        print(f'    conditional pnl (if filled): {mean_cond:.3f}c per fill')


if __name__ == '__main__':
    main()
