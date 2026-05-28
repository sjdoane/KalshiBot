"""Critic LIVE probe: for currently-open KXBTCD contracts about to close, sample naive_p_yes
and compare to LIVE Kalshi ask. Tests whether the ASK tracks spot or stays stale.

This is the most direct test of the central question.
"""
import sys
import time
import math
import re
sys.path.insert(0, 'src')
import pandas as pd
import numpy as np
import requests
from scipy.stats import norm
from kalshi_bot.config import Settings
from kalshi_bot.data.kalshi_client import KalshiClient


def parse_strike(ticker):
    m = re.search(r'-T(?P<strike>\d+(\.\d+)?)$', ticker)
    if not m:
        return float('nan')
    return float(m.group('strike'))


def get_coinbase_spot():
    """Current Coinbase BTC-USD price."""
    r = requests.get('https://api.exchange.coinbase.com/products/BTC-USD/ticker', timeout=20)
    return float(r.json()['price'])


def get_coinbase_1m_window(end_ts, minutes=120):
    """Get 1m candles ending at end_ts."""
    end_iso = end_ts.isoformat()
    start_iso = (end_ts - pd.Timedelta(minutes=minutes)).isoformat()
    r = requests.get(
        'https://api.exchange.coinbase.com/products/BTC-USD/candles',
        params={'start': start_iso, 'end': end_iso, 'granularity': 60},
        timeout=30,
    )
    candles = r.json()
    if not candles:
        return pd.DataFrame()
    df = pd.DataFrame(candles, columns=['time', 'low', 'high', 'open', 'close', 'volume'])
    df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
    return df.sort_values('time').reset_index(drop=True)


def main():
    settings = Settings()
    now = pd.Timestamp.now('UTC')
    print(f'now: {now}')

    spot = get_coinbase_spot()
    print(f'spot BTC: ${spot:,.2f}')

    # Get recent 120 min of 1m candles for sigma estimate
    candles = get_coinbase_1m_window(now, 120)
    print(f'candles: {len(candles)}')
    if len(candles) < 60:
        print('insufficient candles')
        return
    log_returns = np.diff(np.log(candles['close'].to_numpy()))
    sigma_1m = float(np.std(log_returns, ddof=1))
    print(f'sigma_1m (last 120 min): {sigma_1m:.5f}')

    with KalshiClient(settings) as c:
        all_markets = []
        cursor = None
        for _ in range(5):
            params = {'series_ticker': 'KXBTCD', 'status': 'open', 'limit': 200}
            if cursor:
                params['cursor'] = cursor
            resp = c.get('/markets', **params)
            all_markets.extend(resp.get('markets', []))
            cursor = resp.get('cursor')
            if not cursor:
                break

        df = pd.DataFrame(all_markets)
        df['close_time_dt'] = pd.to_datetime(df['close_time'], utc=True)
        df['mins_to_close'] = (df['close_time_dt'] - now).dt.total_seconds() / 60
        for c2 in ['last_price_dollars', 'yes_ask_dollars', 'yes_bid_dollars']:
            df[c2] = pd.to_numeric(df[c2], errors='coerce')

        # Focus on contracts closing within 0-60 min (this is the T-30/T-15 regime)
        df['strike'] = df['ticker'].map(parse_strike)
        candidates = df[(df.mins_to_close > 0) & (df.mins_to_close <= 60) & df.strike.notna()].copy()
        # Filter to those with valid ask/bid
        candidates = candidates[candidates.yes_ask_dollars.notna() & candidates.yes_bid_dollars.notna()].copy()
        candidates['mid'] = (candidates.yes_ask_dollars + candidates.yes_bid_dollars) / 2

        # Compute naive_p_yes
        def compute_naive_p(row):
            horizon = float(row['mins_to_close'])
            sigma = sigma_1m * math.sqrt(horizon)
            spot_close = spot
            strike = row['strike']
            if sigma <= 0 or spot_close <= 0 or strike <= 0:
                return float('nan')
            z = (math.log(strike) - math.log(spot_close)) / sigma
            return float(np.clip(1.0 - norm.cdf(z), 1e-3, 1.0 - 1e-3))

        candidates['naive_p'] = candidates.apply(compute_naive_p, axis=1)
        # Compute signal vs MID and vs ASK
        candidates['signal_vs_mid'] = candidates['naive_p'] - candidates['mid']
        candidates['signal_vs_ask'] = candidates['naive_p'] - candidates.yes_ask_dollars
        candidates['signal_vs_no_ask'] = (1 - candidates['naive_p']) - (1 - candidates.yes_bid_dollars)  # NO ask = 1 - yes_bid

        print(f'\n{len(candidates)} candidates closing in 0-60 min with valid quotes')
        print('Top 20 by abs signal:')
        candidates = candidates.sort_values('signal_vs_mid', key=lambda x: x.abs(), ascending=False)
        cols = ['ticker', 'mins_to_close', 'strike', 'last_price_dollars', 'yes_bid_dollars', 'yes_ask_dollars', 'mid', 'naive_p', 'signal_vs_mid', 'signal_vs_ask', 'signal_vs_no_ask']
        print(candidates[cols].head(20).to_string())

        # Key question: among contracts where |signal_vs_mid| >= 0.10, does the ASK lag with mid or is it tighter?
        strong_yes = candidates[candidates.signal_vs_mid >= 0.10]
        strong_no = candidates[candidates.signal_vs_mid <= -0.10]

        print(f'\nSTRONG BUY YES (naive_p - mid >= 0.10): n={len(strong_yes)}')
        if len(strong_yes) > 0:
            print(f'  mean signal vs mid: {strong_yes.signal_vs_mid.mean():.4f}')
            print(f'  mean signal vs ask (after +2c rule needed): {strong_yes.signal_vs_ask.mean():.4f}')
            print(f'  fraction with signal_vs_ask >= +0.02 (i.e. +2c rule fires): {(strong_yes.signal_vs_ask >= 0.02).mean():.2f}')
            print(f'  fraction where ASK <= mid + 0.02 (stale-ask hypothesis): {((strong_yes.yes_ask_dollars - strong_yes.mid) <= 0.02).mean():.2f}')

        print(f'\nSTRONG BUY NO (naive_p - mid <= -0.10): n={len(strong_no)}')
        if len(strong_no) > 0:
            print(f'  mean signal vs mid: {strong_no.signal_vs_mid.mean():.4f}')
            print(f'  mean signal vs NO ask: {strong_no.signal_vs_no_ask.mean():.4f}')
            print(f'  fraction with NO signal >= +0.02 (i.e. +2c rule fires for BUY_NO): {(strong_no.signal_vs_no_ask >= 0.02).mean():.2f}')

        # Save for inspection
        candidates.to_parquet('data/v7/critic_live_probe.parquet', index=False)
        print('Saved data/v7/critic_live_probe.parquet')


if __name__ == '__main__':
    main()
