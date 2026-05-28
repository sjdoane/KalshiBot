"""V5-C2 PIVOT 2: midband [0.55, 0.80].

The first pivot widerband [0.55, 0.95] still ended up with all NOs
in the test portion (NOs concentrate in late-2025+ when BTC was
choppy). This midband [0.55, 0.80] has uniform NO rate ~0.24, with
more even temporal distribution.

n=500. Train (350) should have ~85 NOs. Sufficient for non-degenerate
LogReg with bootstrap CI.

Saves to data/v5/v5c_pivot_midband_data.parquet.

Run: uv run python -m scripts.v5.build_v5c_pivot_midband
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "v5"))

from scripts.v5 import build_v5c_orthogonality_dataset as base

OUT_DIR = REPO_ROOT / "data" / "v5"
DATA_PATH = OUT_DIR / "v5c_pivot_midband_data.parquet"
META_PATH = OUT_DIR / "v5c_pivot_midband_meta.json"

SAMPLE_SIZE = int(__import__("os").environ.get("V5C_PIVOT_SAMPLE_SIZE", "500"))
SEED = 42
PRICE_LO = 0.55
PRICE_HI = 0.80
THROTTLE_SEC = 0.35


def log(msg: str) -> None:
    print(f"[{pd.Timestamp.now(tz='UTC').isoformat()}] {msg}", flush=True)


def sample_markets_midband() -> pd.DataFrame:
    df = pd.read_parquet(OUT_DIR / "crypto_full_KXBTCD.parquet")
    df["last_price"] = pd.to_numeric(df["last_price_dollars"], errors="coerce")
    df["outcome"] = (df["result"] == "yes").astype(int)
    df["threshold"] = df["ticker"].apply(
        lambda t: float(base.THRESHOLD_PATTERN.search(t).group(1))
        if base.THRESHOLD_PATTERN.search(t)
        else None,
    )
    mid = df[
        (df["last_price"] >= PRICE_LO)
        & (df["last_price"] <= PRICE_HI)
        & (df["lifetime_hours"] >= 0.9)
        & (df["lifetime_hours"] <= 1.1)
    ].copy()
    log(f"Midband [{PRICE_LO}, {PRICE_HI}] 1h KXBTCD: {len(mid):,}")

    mid["close_date"] = mid["close_time"].dt.date
    rng = np.random.default_rng(SEED)
    grouped = mid.groupby("close_date")
    if len(grouped) >= SAMPLE_SIZE:
        dates = list(grouped.groups.keys())
        rng.shuffle(dates)
        chosen_idx: list[int] = []
        for d in dates[:SAMPLE_SIZE]:
            grp = grouped.get_group(d)
            pick = rng.choice(grp.index.tolist())
            chosen_idx.append(pick)
        sample = mid.loc[chosen_idx].copy()
    else:
        # Not enough distinct dates; oversample dates
        sample = mid.sample(n=min(SAMPLE_SIZE, len(mid)), random_state=SEED).copy()

    sample = sample.sort_values("close_time").reset_index(drop=True)
    log(f"Sampled n={len(sample)} across {sample['close_date'].nunique()} dates")
    log(f"Sample yes_rate: {sample['outcome'].mean():.4f}")
    log(f"NOs in sample: {(sample['outcome']==0).sum()}")
    return sample


def main() -> int:
    log("Building V5-C2 PIVOT 2 (midband [0.55, 0.80]) dataset")
    sample = sample_markets_midband()
    sample = base.derive_brti_bracket(sample)
    base.get_cm_active_addr()
    base.get_dxy_series()
    base.get_hashrate_series()

    rows: list[dict[str, Any]] = []
    n = len(sample)
    t_start = time.time()
    for i, row in sample.iterrows():
        open_time = row["open_time"]
        close_time = row["close_time"]
        f1 = base.f1_realized_vol_1h(open_time)
        time.sleep(THROTTLE_SEC)
        f2 = base.f2_vwap_dev_1h(open_time)
        time.sleep(THROTTLE_SEC)
        f3 = base.f3_spot_futures_basis(open_time)
        time.sleep(THROTTLE_SEC)
        f4 = base.f4_funding_rate(open_time)
        time.sleep(THROTTLE_SEC)
        f6 = base.f6_active_addr_delta(open_time)
        f7 = base.f7_dxy_24h_change(open_time)
        f8 = base.f8_hashrate_24h_change(open_time)
        coinbase_at_open = base.coinbase_spot_at(open_time)
        time.sleep(THROTTLE_SEC)
        coinbase_at_close = base.coinbase_spot_at_close(close_time)
        time.sleep(THROTTLE_SEC)
        rows.append({
            "ticker": row["ticker"],
            "event_ticker": row["event_ticker"],
            "open_time": open_time,
            "close_time": close_time,
            "threshold": row["threshold"],
            "favorite_price": float(row["last_price"]),
            "outcome": int(row["outcome"]),
            "brti_lower": row["brti_lower"],
            "brti_upper": row["brti_upper"],
            "brti_estimate": row["brti_estimate"],
            "coinbase_at_open": coinbase_at_open,
            "coinbase_at_close": coinbase_at_close,
            "f1_realized_vol_1h": f1,
            "f2_vwap_dev_1h": f2,
            "f3_spot_futures_basis": f3,
            "f4_funding_rate_1h": f4,
            "f6_active_addr_delta": f6,
            "f7_dxy_24h_change": f7,
            "f8_hashrate_24h_change": f8,
        })
        if (i + 1) % 50 == 0:
            elapsed = time.time() - t_start
            eta = elapsed / (i + 1) * (n - i - 1)
            log(f"  progress {i + 1}/{n} elapsed={elapsed:.0f}s eta={eta:.0f}s")
            # Save intermediate
            pd.DataFrame(rows).to_parquet(DATA_PATH, index=False)

    out_df = pd.DataFrame(rows)
    out_df.to_parquet(DATA_PATH, index=False)
    log(f"Wrote {DATA_PATH} (n={len(out_df)})")
    feat_cols = [c for c in out_df.columns if c.startswith("f")]
    coverage = {c: int(out_df[c].notna().sum()) for c in feat_cols}
    meta = {
        "sample_size": len(out_df),
        "yes_rate": float(out_df["outcome"].mean()),
        "price_band": [PRICE_LO, PRICE_HI],
        "date_range": [str(out_df["close_time"].min()), str(out_df["close_time"].max())],
        "feature_coverage": coverage,
    }
    with open(META_PATH, "w") as f:
        json.dump(meta, f, indent=2, default=str)
    log(f"Wrote {META_PATH}")
    log(f"Total elapsed: {time.time() - t_start:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
