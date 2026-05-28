"""Critic Test 4c: deeper next-trade analysis - infer the implied ASK.

For each has-next trade where taker_outcome_side='yes' (taker bought YES, so crossed the ASK),
the trade price IS the ask at trade time. Similarly for 'no' (crossed the bid implied).

So we want: for strong-signal stale-mid contracts that DO have next trades,
what was the ask just after t?
"""
import pandas as pd
import numpy as np


def main():
    df = pd.read_parquet('data/v7/critic_test4_has_next.parquet')
    print(f'n has-next: {len(df)}')
    print(f'taker_side counts: {df.taker_side.value_counts().to_dict()}')
    print()

    # For BUY_YES signals (signal > 0, naive_p > mid):
    # If a trade subsequently fires with taker_side='yes', that means someone took the YES ask
    # The price they paid IS the yes_ask at that time.
    # If a trade fires with taker_side='no', that means someone took the NO ask = (1-yes_bid)
    # So the YES price they printed at is yes_bid (someone sold YES at the bid).

    df['inferred_ask'] = df.apply(
        lambda r: r['next_trade_price'] if r['taker_side'] == 'yes' else float('nan'),
        axis=1,
    )
    df['inferred_bid'] = df.apply(
        lambda r: r['next_trade_price'] if r['taker_side'] == 'no' else float('nan'),
        axis=1,
    )

    # If we observed an ASK at time of next trade and the mid was stale,
    # is the inferred ASK closer to mid (PHANTOM EDGE) or closer to naive_p (REAL EDGE)?

    # Stale + strong BUY_YES
    sy = df[(df.signal >= 0.10)].copy()
    sn = df[(df.signal <= -0.10)].copy()
    print(f'Strong BUY_YES (signal >= 0.10) with next-trade: n={len(sy)}')
    if len(sy) > 0:
        print(f'  mean mid: {sy.mid.mean():.4f}')
        print(f'  mean naive_p: {sy.naive_p.mean():.4f}')
        print(f'  next-trade taker side: {sy.taker_side.value_counts().to_dict()}')
        sy_ask = sy[sy.taker_side == 'yes']
        sy_bid = sy[sy.taker_side == 'no']
        if len(sy_ask) > 0:
            print(f'  inferred-ask (taker=yes) n={len(sy_ask)}: mean ask price = {sy_ask.next_trade_price.mean():.4f}')
            print(f'    delta from stale mid: {(sy_ask.next_trade_price - sy_ask.mid).mean():.4f}')
            print(f'    delta from naive_p: {(sy_ask.next_trade_price - sy_ask.naive_p).mean():.4f}')
        if len(sy_bid) > 0:
            print(f'  inferred-bid (taker=no) n={len(sy_bid)}: mean bid price = {sy_bid.next_trade_price.mean():.4f}')
            print(f'    delta from stale mid: {(sy_bid.next_trade_price - sy_bid.mid).mean():.4f}')
            print(f'    delta from naive_p: {(sy_bid.next_trade_price - sy_bid.naive_p).mean():.4f}')

    print(f'\nStrong BUY_NO (signal <= -0.10) with next-trade: n={len(sn)}')
    if len(sn) > 0:
        print(f'  mean mid: {sn.mid.mean():.4f}')
        print(f'  mean naive_p: {sn.naive_p.mean():.4f}')
        print(f'  next-trade taker side: {sn.taker_side.value_counts().to_dict()}')
        sn_ask = sn[sn.taker_side == 'yes']
        sn_bid = sn[sn.taker_side == 'no']
        if len(sn_ask) > 0:
            print(f'  inferred-ask (taker=yes) n={len(sn_ask)}: mean ask = {sn_ask.next_trade_price.mean():.4f}')
            print(f'    delta from stale mid: {(sn_ask.next_trade_price - sn_ask.mid).mean():.4f}')
            print(f'    delta from naive_p: {(sn_ask.next_trade_price - sn_ask.naive_p).mean():.4f}')
        if len(sn_bid) > 0:
            print(f'  inferred-bid (taker=no) n={len(sn_bid)}: mean bid = {sn_bid.next_trade_price.mean():.4f}')
            print(f'    delta from stale mid: {(sn_bid.next_trade_price - sn_bid.mid).mean():.4f}')
            print(f'    delta from naive_p: {(sn_bid.next_trade_price - sn_bid.naive_p).mean():.4f}')

    # CRITICAL TEST: among strong BUY_YES, what fraction of next-trade ASK prices >= mid + 0.05?
    # If naive_p is huge above mid (signal = 0.20), and ASK is at mid + 0.01 (stale), then +2c rule clears.
    # If ASK has moved up to spot (mid + signal), then it would be at much higher than mid + 0.02.
    print('\n=== Inferred next-trade ASK distribution on strong BUY_YES ===')
    sy_with_ask = df[(df.signal >= 0.10) & (df.taker_side == 'yes')]
    if len(sy_with_ask) > 0:
        # How far above stale mid is the inferred ask?
        ask_above_mid = sy_with_ask.next_trade_price - sy_with_ask.mid
        print(f'  n={len(sy_with_ask)} BUY_YES with taker=yes (inferred ASK)')
        print(f'  ask_above_mid: mean={ask_above_mid.mean():.4f}, median={ask_above_mid.median():.4f}, min={ask_above_mid.min():.4f}, max={ask_above_mid.max():.4f}')
        # Is the ask still within +2c of mid (so +2c-take rule would trigger easily)?
        within_2c = (ask_above_mid <= 0.02).sum()
        within_5c = (ask_above_mid <= 0.05).sum()
        print(f'  fraction within +2c of mid: {within_2c}/{len(sy_with_ask)} = {within_2c/len(sy_with_ask)*100:.1f}%')
        print(f'  fraction within +5c of mid: {within_5c}/{len(sy_with_ask)} = {within_5c/len(sy_with_ask)*100:.1f}%')
        sy_with_ask_details = sy_with_ask[['ticker', 'mid', 'naive_p', 'signal', 'next_trade_price', 'minutes_to_next', 'outcome_yes']].copy()
        sy_with_ask_details['ask_above_mid'] = ask_above_mid
        print('\nfull details:')
        print(sy_with_ask_details.to_string())


if __name__ == '__main__':
    main()
