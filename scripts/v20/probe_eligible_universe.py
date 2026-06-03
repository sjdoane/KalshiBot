"""READ-ONLY probe of v1's eligible universe in the 5 PERSIST allowlist series.

Confirms (against the live Kalshi API) the binding-constraint and lifetime-filter
findings before any tuning:
  - How many OPEN markets each allowlist series has, and how many pass v1's
    live filters (favorite band, volume>=50, lifetime[0,21], minutes_to_close>=60).
  - For each passing market: lifetime_days (close-open span) vs days_to_close.
    The hypothesis is that far-future game markets (close months out) pass the
    21-day LIFETIME gate because their open->close SPAN is short, i.e. the gate
    bounds span, not time-to-close.

STRICTLY READ-ONLY: issues only GET /markets?series_ticker=... It never places,
cancels, or mutates any order, and never acquires the live lock. Safe to run
alongside the live bot. Scoped to 5 series to add negligible API load.

Run (Windows):
  PYTHONPATH=src C:\\...\\.venv-kronos\\Scripts\\python.exe -m scripts.v20.probe_eligible_universe
"""

from __future__ import annotations

import pandas as pd

from kalshi_bot.config import load_settings
from kalshi_bot.data.kalshi_client import KalshiClient
from kalshi_bot.strategy.market_scanner import PERSIST_SERIES_ALLOWLIST, parse_snapshot

MIN_VOLUME = 50.0
MIN_LIFETIME_DAYS = 0
MAX_LIFETIME_DAYS = 21
MIN_MINUTES_TO_CLOSE = 60
# v1 with --enable-no-underdog passes both bands; favorite is whichever side >=0.70
BANDS = [(0.05, 0.30), (0.70, 0.95)]


def in_band(mid: float) -> bool:
    return any(lo <= mid <= hi for lo, hi in BANDS)


def main() -> None:
    settings = load_settings()
    now = pd.Timestamp.now(tz="UTC")
    print(f"now = {now.isoformat()}")
    print(f"series = {sorted(PERSIST_SERIES_ALLOWLIST)}")
    print("=" * 100)

    with KalshiClient(settings) as client:
        for series in sorted(PERSIST_SERIES_ALLOWLIST):
            try:
                markets = list(
                    client.paginate(
                        "/markets",
                        item_key="markets",
                        series_ticker=series,
                        status="open",
                        limit=200,
                        max_pages=20,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                print(f"{series}: FETCH FAILED: {exc}")
                continue

            n_open = len(markets)
            passing = []
            band_vol_ok = 0
            for m in markets:
                snap = parse_snapshot(m)
                if snap is None or snap.yes_bid <= 0 or snap.yes_ask <= 0:
                    continue
                mid = (snap.yes_bid + snap.yes_ask) / 2.0
                if not in_band(mid) or snap.volume < MIN_VOLUME:
                    continue
                band_vol_ok += 1
                try:
                    open_t = pd.Timestamp(snap.open_time)
                    close_t = pd.Timestamp(snap.close_time)
                except (TypeError, ValueError):
                    continue
                lifetime_days = (close_t - open_t).total_seconds() / 86400.0
                days_to_close = (close_t - now).total_seconds() / 86400.0
                minutes_to_close = (close_t - now).total_seconds() / 60.0
                passes_lifetime = MIN_LIFETIME_DAYS <= lifetime_days <= MAX_LIFETIME_DAYS
                passes_close = minutes_to_close >= MIN_MINUTES_TO_CLOSE
                if passes_lifetime and passes_close:
                    passing.append(
                        {
                            "ticker": snap.ticker,
                            "mid": round(mid, 2),
                            "vol": int(snap.volume),
                            "life_d": round(lifetime_days, 1),
                            "to_close_d": round(days_to_close, 1),
                        }
                    )

            print(f"\n### {series}: {n_open} open | band+vol ok={band_vol_ok} | PASS all filters={len(passing)}")
            if passing:
                tc = sorted(p["to_close_d"] for p in passing)
                print(
                    f"    days_to_close of passers: min={tc[0]} median={tc[len(tc)//2]} max={tc[-1]}"
                )
                far = [p for p in passing if p["to_close_d"] > 21]
                print(
                    f"    passers closing >21 days out (far-future, won't fill soon): {len(far)} of {len(passing)}"
                )
                for p in sorted(passing, key=lambda x: x["to_close_d"])[:8]:
                    print(
                        f"      {p['ticker']:42} mid={p['mid']:.2f} vol={p['vol']:>6} "
                        f"life_span={p['life_d']:>6}d  to_close={p['to_close_d']:>6}d"
                    )


if __name__ == "__main__":
    main()
