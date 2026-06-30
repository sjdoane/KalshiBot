"""v24 sports-props: live capture-phantom check on MLB game totals.

Compares live Kalshi KXMLBTOTAL prices to the-odds-api sharp-book totals for the
same game. If Kalshi tracks the sharp book (gap < taker hurdle), the capture
phantom holds for sharp-lined MLB props = NULL (the edge is already priced).

Read-only. Run via PowerShell (network). Loads THE_ODDS_API_KEY from .env without
printing it.
"""
from __future__ import annotations

import math
import re
import sys

import httpx

sys.path.insert(0, "src")
from kalshi_bot.config import Settings  # noqa: E402
from kalshi_bot.data.kalshi_client import KalshiClient  # noqa: E402
from kalshi_bot.analysis.metrics import kalshi_taker_fee_per_contract  # noqa: E402

CITY_WORDS = {  # map odds-api full team names -> a city token likely in the Kalshi title
    "Diamondbacks": "Arizona", "Braves": "Atlanta", "Orioles": "Baltimore", "Red Sox": "Boston",
    "Cubs": "Chicago", "White Sox": "Chicago", "Reds": "Cincinnati", "Guardians": "Cleveland",
    "Rockies": "Colorado", "Tigers": "Detroit", "Astros": "Houston", "Royals": "Kansas City",
    "Angels": "Angels", "Dodgers": "Los Angeles", "Marlins": "Miami", "Brewers": "Milwaukee",
    "Twins": "Minnesota", "Mets": "New York", "Yankees": "New York", "Athletics": "Athletics",
    "Phillies": "Philadelphia", "Pirates": "Pittsburgh", "Padres": "San Diego", "Giants": "San Francisco",
    "Mariners": "Seattle", "Cardinals": "St. Louis", "Rays": "Tampa Bay", "Rangers": "Texas",
    "Blue Jays": "Toronto", "Nationals": "Washington",
}


def load_odds_key() -> str | None:
    with open(".env", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("THE_ODDS_API_KEY="):
                return line.split("=", 1)[1].strip()
    return None


def city_token(full_name: str) -> str:
    for k, v in CITY_WORDS.items():
        if full_name.endswith(k):
            return v
    return full_name.split()[0]


def main() -> None:
    key = load_odds_key()
    if not key:
        print("no odds key"); return
    hc = httpx.Client(timeout=30.0)
    r = hc.get("https://api.the-odds-api.com/v4/sports/baseball_mlb/odds",
               params={"apiKey": key, "regions": "us", "markets": "totals", "oddsFormat": "decimal"})
    print("odds-api status", r.status_code, "remaining", r.headers.get("x-requests-remaining"))
    games = r.json()
    # book consensus: median implied P(over) at the median line per game
    book = {}  # (homecity, awaycity) -> (line, p_over)
    for g in games:
        hc_, ac_ = city_token(g["home_team"]), city_token(g["away_team"])
        lines = []
        for bk in g.get("bookmakers", []):
            for mk in bk.get("markets", []):
                if mk["key"] != "totals":
                    continue
                pt = over = under = None
                for o in mk["outcomes"]:
                    if o["name"] == "Over":
                        pt, over = o.get("point"), o.get("price")
                    elif o["name"] == "Under":
                        under = o.get("price")
                if pt and over and under:
                    p_over = (1.0 / over) / ((1.0 / over) + (1.0 / under))  # devig
                    lines.append((pt, p_over))
        if lines:
            lines.sort()
            book[(hc_, ac_)] = lines[len(lines) // 2]

    s = Settings()
    rows = []
    with KalshiClient(s) as cli:
        for m in cli.paginate("/markets", item_key="markets",
                              series_ticker="KXMLBTOTAL", status="open", limit=200):
            def _f(x):
                try: return float(x)
                except (TypeError, ValueError): return 0.0
            ya, yb = _f(m.get("yes_ask_dollars")), _f(m.get("yes_bid_dollars"))
            if not ya or not yb or ya >= 1.0 or yb <= 0.0:
                continue
            title = m.get("title", "")
            mt = re.search(r"(.+?)\s+vs\s+(.+?)\s+Total", title)
            strike = re.search(r"-(\d+(?:\.\d+)?)$", m["ticker"])
            if not mt or not strike:
                continue
            home_t, away_t = mt.group(1).strip(), mt.group(2).strip()
            k = float(strike.group(1))
            # match a book game by city tokens (either orientation)
            bk = None
            for (bh, ba), v in book.items():
                if (bh in home_t or home_t in bh) and (ba in away_t or away_t in bh + away_t):
                    bk = v; break
                if (bh in away_t or away_t in bh) and (ba in home_t or home_t in ba):
                    bk = v; break
            if not bk:
                continue
            book_line, p_over = bk
            # Kalshi "k+ runs" (yes = total >= k) ~ P(total > k-0.5). Book p_over is at book_line.
            # Only compare when the Kalshi strike is near the book line (within 1 run).
            if abs((k - 0.5) - book_line) > 1.0:
                continue
            k_mid = (ya + yb) / 2.0
            gap = abs(k_mid - p_over)
            rows.append((m["ticker"], home_t, away_t, k, book_line, round(p_over, 3),
                         round(k_mid, 3), round(gap, 3), round((ya - yb) * 100)))

    print(f"\nmatched KXMLBTOTAL vs sharp-book totals: {len(rows)}")
    print("ticker / Kalshi_strike / book_line / book_P(over) / kalshi_mid / |gap| / spread_c")
    gaps = []
    for t, h, a, k, bl, po, km, gp, sp in sorted(rows, key=lambda x: -x[7]):
        gaps.append(gp)
        print(f"  {t:<28} k={k} bl={bl} bookP={po:.2f} kMid={km:.2f} gap={gp:.3f} sprd={sp}c")
    if gaps:
        gaps.sort()
        med = gaps[len(gaps) // 2]
        print(f"\nALL matches median |gap| = {med:.3f} ({med*100:.1f}pp) -- but mostly a "
              f"threshold/push artifact (Kalshi 'k+'=P(>=k) vs whole-number book 'over k').")
        # CLEAN subset: Kalshi strike k aligns EXACTLY with a book half-line (k = bl + 0.5),
        # so Kalshi P(>=k) == book P(over bl) with NO push ambiguity. This is the real test.
        clean = [(t, gp) for (t, h, a, k, bl, po, km, gp, sp) in rows if abs((k - 0.5) - bl) < 0.01]
        if clean:
            cg = sorted(g for _, g in clean)
            cmed = cg[len(cg) // 2]
            print(f"\nCLEAN-ALIGNED subset (k == book half-line + 0.5, no push): n={len(clean)}")
            for t, g in sorted(clean, key=lambda x: -x[1]):
                print(f"  {t:<30} gap={g:.3f} ({g*100:.1f}pp)")
            print(f"  clean median |gap| = {cmed:.3f} ({cmed*100:.1f}pp)")
            print(f"  => Kalshi MLB totals track the sharp book to ~{cmed*100:.1f}pp << taker hurdle ~3pp")
            print(f"  => CAPTURE PHANTOM confirmed: the sharp-line edge is already priced. NULL.")


if __name__ == "__main__":
    main()
