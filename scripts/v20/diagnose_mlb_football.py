"""READ-ONLY: why do KXMLBGAME / KXNCAAFGAME / KXNFLGAME markets fail v1 filters?

Distinguishes a time-of-day artifact (no favorites priced >=0.70 right now /
thin volume) from a structural problem (markets never qualify), and confirms
the far-future game markets fail on the 21-day lifetime SPAN gate.

STRICTLY READ-ONLY (GET /markets only).
"""

from __future__ import annotations

from collections import Counter

import pandas as pd

from kalshi_bot.config import load_settings
from kalshi_bot.data.kalshi_client import KalshiClient
from kalshi_bot.strategy.market_scanner import parse_snapshot

SERIES = ["KXMLBGAME", "KXNCAAFGAME", "KXNFLGAME"]
BANDS = [(0.05, 0.30), (0.70, 0.95)]


def in_band(mid: float) -> bool:
    return any(lo <= mid <= hi for lo, hi in BANDS)


def main() -> None:
    settings = load_settings()
    now = pd.Timestamp.now(tz="UTC")
    print(f"now = {now.isoformat()}\n")
    with KalshiClient(settings) as client:
        for series in SERIES:
            markets = list(
                client.paginate(
                    "/markets", item_key="markets", series_ticker=series,
                    status="open", limit=200, max_pages=20,
                )
            )
            reasons: Counter = Counter()
            mids = []
            vols = []
            spans = []
            for m in markets:
                snap = parse_snapshot(m)
                if snap is None or snap.yes_bid <= 0 or snap.yes_ask <= 0:
                    reasons["no_quote"] += 1
                    continue
                mid = (snap.yes_bid + snap.yes_ask) / 2.0
                mids.append(mid)
                vols.append(snap.volume)
                if not in_band(mid):
                    reasons["out_of_band(0.30-0.70 dead zone)"] += 1
                    continue
                if snap.volume < 50:
                    reasons["low_volume(<50)"] += 1
                    continue
                try:
                    span = (pd.Timestamp(snap.close_time) - pd.Timestamp(snap.open_time)).total_seconds() / 86400.0
                    spans.append(span)
                except (TypeError, ValueError):
                    reasons["bad_timestamps"] += 1
                    continue
                if span > 21:
                    reasons["lifetime_span>21d"] += 1
                    continue
                mins_to_close = (pd.Timestamp(snap.close_time) - now).total_seconds() / 60.0
                if mins_to_close < 60:
                    reasons["too_close(<60min)"] += 1
                    continue
                reasons["PASSES_ALL"] += 1

            print(f"### {series}: {len(markets)} open")
            if mids:
                mids_s = sorted(mids)
                vols_s = sorted(vols)
                print(f"    mid:    min={mids_s[0]:.2f} median={mids_s[len(mids_s)//2]:.2f} max={mids_s[-1]:.2f}")
                print(f"    volume: min={vols_s[0]:.0f} median={vols_s[len(vols_s)//2]:.0f} max={vols_s[-1]:.0f}")
                n_fav = sum(1 for x in mids if x >= 0.70)
                n_dog = sum(1 for x in mids if x <= 0.30)
                print(f"    in favorite band(>=0.70): {n_fav} | in underdog band(<=0.30): {n_dog}")
            if spans:
                sp = sorted(spans)
                print(f"    open->close SPAN (days) for in-band+vol mkts: min={sp[0]:.1f} median={sp[len(sp)//2]:.1f} max={sp[-1]:.1f}")
            print(f"    failure/pass reasons: {dict(reasons)}\n")


if __name__ == "__main__":
    main()
