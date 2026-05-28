"""V10-A pre-flight smoke test 3: FRED API call.

Verifies FRED_API_KEY in .env works for FEDFUNDS / CPIAUCSL / PAYEMS / UNRATE.

Per A2 v2 lock smoke test plan.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"
load_dotenv(ENV_FILE)

FRED_API_KEY = os.environ.get("FRED_API_KEY", "").strip()
if not FRED_API_KEY:
    raise SystemExit("FRED_API_KEY not in .env")

SERIES = ["FEDFUNDS", "CPIAUCSL", "PAYEMS", "UNRATE"]


def fetch_series(series_id: str) -> dict:
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "observation_start": "2023-01-01",
    }
    r = requests.get(url, params=params, timeout=30)
    if r.status_code != 200:
        return {"series": series_id, "status": r.status_code, "body": r.text[:200]}
    js = r.json()
    obs = js.get("observations", [])
    return {
        "series": series_id,
        "status": 200,
        "n_obs": len(obs),
        "first_date": obs[0]["date"] if obs else None,
        "last_date": obs[-1]["date"] if obs else None,
        "last_value": obs[-1]["value"] if obs else None,
    }


def main() -> None:
    print(f"FRED smoke test (API key {'present' if FRED_API_KEY else 'MISSING'})")
    print("=" * 60)
    all_ok = True
    for series in SERIES:
        result = fetch_series(series)
        if result["status"] == 200:
            print(
                f"  {series:12}  n_obs={result['n_obs']:>4}  "
                f"{result['first_date']} to {result['last_date']}  "
                f"last={result['last_value']}"
            )
            if result["n_obs"] < 12:
                print(f"  WARNING: less than 12 obs for {series}")
                all_ok = False
        else:
            print(f"  {series:12}  FAIL status={result['status']}  {result.get('body', '')}")
            all_ok = False
    if all_ok:
        print("\nFRED smoke test PASS")
        sys.exit(0)
    else:
        print("\nFRED smoke test FAIL")
        sys.exit(1)


if __name__ == "__main__":
    main()
