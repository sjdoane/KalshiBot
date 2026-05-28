"""V4-D: widened Manifold coverage probe with looser queries.

First pass had 0/5 matches; this tries 2-3 query variants per Kalshi ticker
to give Manifold every fair chance.

Output: data/v4/manifold_widened_probe.json
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT = REPO_ROOT / "data" / "v4" / "manifold_widened_probe.json"

# Multiple query variants per v1 ticker. We pivot per the operator's rule
# (don't declare a venue dead at first 404).
SAMPLE = [
    {
        "kalshi_ticker": "KXWCSQUAD-26ESP-BIGL",
        "league": "Soccer-WC",
        "queries": [
            "Spain World Cup squad",
            "Lamine Yamal World Cup",
            "Spain 2026 World Cup",
            "World Cup roster Spain",
        ],
    },
    {
        "kalshi_ticker": "KXSTARTINGQBWEEK1-W1-26SEP15-LV-KCOU",
        "league": "NFL",
        "queries": [
            "Raiders starting QB",
            "Kenny Pickett",
            "NFL week 1 starting quarterback",
            "Raiders 2026",
        ],
    },
    {
        "kalshi_ticker": "KXWCGAME-26JUN23ENGGHA-ENG",
        "league": "Soccer-WC",
        "queries": [
            "England Ghana World Cup",
            "England World Cup 2026",
            "World Cup group stage",
            "England Ghana",
        ],
    },
    {
        "kalshi_ticker": "KXUFCFIGHT-26JUL11MCGHOL-HOL",
        "league": "UFC-MMA",
        "queries": [
            "Holloway McGregor",
            "Holloway UFC",
            "Max Holloway",
            "UFC July 2026",
        ],
    },
    {
        "kalshi_ticker": "KXWNBAWINS-26PHX-20",
        "league": "WNBA",
        "queries": [
            "Phoenix Mercury 2026",
            "Mercury WNBA",
            "WNBA Phoenix",
            "WNBA 2026 win total",
        ],
    },
    {
        "kalshi_ticker": "KXNBAPLAYOFFWINS-26SAS-10",
        "league": "NBA",
        "queries": [
            "San Antonio Spurs playoffs",
            "Spurs 2026 playoffs",
            "Wembanyama playoffs",
            "Spurs NBA",
        ],
    },
    {
        "kalshi_ticker": "KXNBAPLAYOFFWINS-26OKC-15",
        "league": "NBA",
        "queries": [
            "Oklahoma City Thunder NBA",
            "Thunder Finals",
            "OKC playoffs",
            "Thunder 2026",
        ],
    },
    {
        "kalshi_ticker": "KXCS2-ASIA26-FAL",
        "league": "CS2-Esports",
        "queries": [
            "FaZe Clan CS2 Asia",
            "CS2 Asia 2026",
            "Counter Strike Asia",
            "Falcons CS2",
        ],
    },
]


def fetch(client: httpx.Client, term: str, limit: int = 5) -> Any:
    try:
        r = client.get(
            "https://api.manifold.markets/v0/search-markets",
            params={"term": term, "limit": limit},
            timeout=15.0,
        )
        if r.status_code != 200:
            return {"status_code": r.status_code, "body": r.text[:200]}
        return {"status_code": 200, "body": r.json()}
    except Exception as exc:
        return {"status_code": None, "error": str(exc)}


def main() -> None:
    out: list = []
    with httpx.Client(headers={"User-Agent": "kalshi-bot-v4-research/1.0"}) as client:
        for sample in SAMPLE:
            row: dict = {
                "kalshi_ticker": sample["kalshi_ticker"],
                "league": sample["league"],
                "queries": [],
            }
            for q in sample["queries"]:
                time.sleep(0.6)
                r = fetch(client, q, limit=5)
                qrow = {"q": q, "status_code": r.get("status_code")}
                if r.get("status_code") == 200:
                    body = r["body"]
                    qrow["n_results"] = len(body) if isinstance(body, list) else 0
                    qrow["matches"] = []
                    for m in body if isinstance(body, list) else []:
                        qrow["matches"].append({
                            "question": m.get("question"),
                            "slug": m.get("slug"),
                            "isResolved": m.get("isResolved"),
                            "mechanism": m.get("mechanism"),
                            "volume": m.get("volume"),
                            "totalLiquidity": m.get("totalLiquidity"),
                            "uniqueBettorCount": m.get("uniqueBettorCount"),
                            "token": m.get("token"),
                            "probability": m.get("probability"),
                            "closeTime": m.get("closeTime"),
                        })
                else:
                    qrow["error"] = r.get("body") or r.get("error")
                row["queries"].append(qrow)
            out.append(row)

    with open(OUTPUT, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"Wrote {OUTPUT}")
    # quick summary
    total_q = sum(len(r["queries"]) for r in out)
    nonempty = sum(1 for r in out for q in r["queries"] if q.get("n_results", 0) > 0)
    print(f"\nQueries with >=1 result: {nonempty}/{total_q}")
    for r in out:
        any_hit = any(q.get("n_results", 0) > 0 for q in r["queries"])
        print(f"  {r['kalshi_ticker']}: any_hit={any_hit}")


if __name__ == "__main__":
    main()
