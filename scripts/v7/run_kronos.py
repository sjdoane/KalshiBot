"""Run v7 Angle B Kronos zero-shot inference on KXBTCD-1h contracts.

Per research/v7/03-kronos-methodology.md.

Pipeline:
1. Load data/v6/v6_master.parquet and data/v6/cache/coinbase_1m.parquet.
2. Filter to v6 eligibility (post-Oct-2024, lifetime 0.5-4h, has trades, settled).
   v6_master is already filtered; we additionally restrict to midband if requested.
3. For each (ticker, horizon) sample, build 120-min Coinbase OHLCV context ending
   at t = close_time - horizon_min, call Kronos to predict the next horizon_min
   1-min bars, and compute kronos_p_yes via deterministic mode (default) or MC.
4. Cache predictions to data/v7/kronos_predictions.parquet. Re-runs skip already
   cached (ticker, horizon, mode) keys.

Usage:
    .venv-kronos/Scripts/python.exe -m scripts.v7.run_kronos --help
    .venv-kronos/Scripts/python.exe -m scripts.v7.run_kronos \\
        --mode det --sample-count 10 --batch-size 8 --band midband --horizons 30
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Kronos is a sibling vendored repo
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "vendor" / "Kronos"))

warnings.filterwarnings("ignore")

DATA_DIR = REPO_ROOT / "data" / "v7"
DATA_DIR.mkdir(parents=True, exist_ok=True)
V6_MASTER = REPO_ROOT / "data" / "v6" / "v6_master.parquet"
COINBASE_V6_CACHE = REPO_ROOT / "data" / "v6" / "cache" / "coinbase_1m.parquet"
COINBASE_V7_CACHE = DATA_DIR / "cache" / "coinbase_1m_v7.parquet"
CACHE_PATH = DATA_DIR / "kronos_predictions.parquet"
PROGRESS_PATH = DATA_DIR / "kronos_run_progress.json"

SEED = 42


def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] [kronos] {msg}", flush=True)


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    master = pd.read_parquet(V6_MASTER)
    cb_v6 = pd.read_parquet(COINBASE_V6_CACHE)
    cb_v6["time"] = pd.to_datetime(cb_v6["time"], utc=True)
    if COINBASE_V7_CACHE.exists():
        cb_v7 = pd.read_parquet(COINBASE_V7_CACHE)
        cb_v7["time"] = pd.to_datetime(cb_v7["time"], utc=True)
        coinbase = pd.concat([cb_v6, cb_v7], ignore_index=True)
        coinbase = (
            coinbase.drop_duplicates("time").sort_values("time").reset_index(drop=True)
        )
        log(f"  loaded v6+v7 coinbase caches: "
            f"{len(cb_v6)} + {len(cb_v7)} = {len(coinbase)} unique bars")
    else:
        coinbase = cb_v6
        log(f"  v7 supp coinbase cache missing; using v6 only: {len(coinbase)} bars")
    return master, coinbase


def select_samples(
    master: pd.DataFrame,
    band: str,
    horizons: list[int],
    subsample: int | None,
    rng_seed: int,
) -> pd.DataFrame:
    """Apply band filter + horizon filter + optional subsample. Returns the
    sample frame with at minimum: ticker, close_time, horizon_min, outcome_yes,
    kalshi_mid_at_t.
    """
    mid_lo, mid_hi = {
        "midband": (0.55, 0.80),
        "widerband": (0.55, 0.95),
        "all": (0.0, 1.0),
    }[band]
    df = master[
        (master["kalshi_mid_at_t"] >= mid_lo)
        & (master["kalshi_mid_at_t"] <= mid_hi)
        & (master["horizon_min"].isin(horizons))
    ].copy()
    df = df.sort_values("close_time").reset_index(drop=True)
    log(f"selected band={band}: {len(df)} rows across horizons={horizons}")
    if subsample is not None and len(df) > subsample:
        # Chronological stratified subsample: keep first N/2 and last N/2 by close_time
        # to preserve both train and orth holdout coverage.
        rng = np.random.default_rng(rng_seed)
        idx = rng.choice(len(df), size=subsample, replace=False)
        idx.sort()
        df = df.iloc[idx].reset_index(drop=True)
        log(f"random-subsampled to {len(df)} rows (seed={rng_seed})")
    return df


def load_cache() -> pd.DataFrame:
    if CACHE_PATH.exists():
        cache = pd.read_parquet(CACHE_PATH)
        log(f"loaded cache: {len(cache)} predictions")
        return cache
    return pd.DataFrame(
        columns=[
            "ticker", "horizon_min", "strike", "mode", "kronos_p_yes",
            "kronos_mean_close", "kronos_sigma_close", "n_samples",
            "nan_pct_in_window", "status", "error_message",
        ],
    )


def append_cache(cache: pd.DataFrame, new_rows: list[dict]) -> pd.DataFrame:
    if not new_rows:
        return cache
    add = pd.DataFrame(new_rows)
    out = pd.concat([cache, add], ignore_index=True)
    return out


def save_cache(cache: pd.DataFrame) -> None:
    tmp = CACHE_PATH.with_suffix(".parquet.tmp")
    cache.to_parquet(tmp, index=False)
    os.replace(tmp, CACHE_PATH)


def needs_prediction(
    cache: pd.DataFrame,
    ticker: str,
    horizon: int,
    mode: str,
) -> bool:
    if cache.empty:
        return True
    matched = cache[
        (cache["ticker"] == ticker)
        & (cache["horizon_min"] == horizon)
        & (cache["mode"] == mode)
    ]
    return matched.empty


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["det", "mc"], default="det",
                        help="Kronos -> p_yes mode. det = average + Normal-CDF; mc = empirical")
    parser.add_argument("--sample-count", type=int, default=10,
                        help="Kronos sample_count for det mode")
    parser.add_argument("--n-mc-paths", type=int, default=30,
                        help="Kronos MC path count for mc mode")
    parser.add_argument("--batch-size", type=int, default=8,
                        help="predict_batch B size (number of contracts per Kronos call)")
    parser.add_argument("--band", choices=["midband", "widerband", "all"],
                        default="midband")
    parser.add_argument("--horizons", type=int, nargs="+", default=[30, 15])
    parser.add_argument("--subsample", type=int, default=None,
                        help="If set, random-subsample to this many rows total")
    parser.add_argument("--limit", type=int, default=None,
                        help="If set, stop after this many predictions this run")
    parser.add_argument("--context-min", type=int, default=120)
    parser.add_argument("--T", type=float, default=1.0)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--nan-pct-max", type=float, default=0.20)
    args = parser.parse_args()

    log(f"args: {vars(args)}")

    import torch
    torch.manual_seed(SEED)
    np.random.seed(SEED)

    from model import Kronos, KronosTokenizer, KronosPredictor  # noqa: E402
    from kalshi_bot_v7.kronos_features import (  # noqa: E402
        build_context_window, build_y_timestamps, clip_p_yes, parse_strike,
        kronos_to_p_yes_det, kronos_to_p_yes_mc,
    )

    log("loading Kronos model and tokenizer")
    t0 = time.time()
    tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
    model = Kronos.from_pretrained("NeoQuasar/Kronos-base")
    predictor = KronosPredictor(model, tokenizer, device="cpu", max_context=512)
    log(f"  loaded in {time.time()-t0:.1f}s")

    log("loading data")
    master, coinbase = load_data()
    samples = select_samples(
        master, args.band, args.horizons, args.subsample, SEED,
    )
    cache = load_cache()

    # Filter samples by what's not already cached for this mode
    needs: list[pd.Series] = []
    for _, row in samples.iterrows():
        if needs_prediction(cache, row["ticker"], int(row["horizon_min"]), args.mode):
            needs.append(row)
    log(f"need to predict: {len(needs)} of {len(samples)} samples (mode={args.mode})")

    if args.limit is not None:
        needs = needs[: args.limit]
        log(f"capped by --limit to {len(needs)}")

    if not needs:
        log("nothing to do; exiting")
        return 0

    # Bucket by horizon so we batch contracts of same pred_len
    by_horizon: dict[int, list[pd.Series]] = {}
    for row in needs:
        by_horizon.setdefault(int(row["horizon_min"]), []).append(row)

    new_rows: list[dict] = []
    total_succeed = 0
    total_fail = 0
    t_start = time.time()

    for horizon, group in by_horizon.items():
        log(f"=== horizon T-{horizon} : {len(group)} contracts ===")
        # Pre-build all context windows so we can bucket by context length.
        prepared: list[dict] = []
        for row in group:
            ticker = row["ticker"]
            close_time = pd.Timestamp(row["close_time"])
            t = close_time - pd.Timedelta(minutes=horizon)
            try:
                strike = parse_strike(ticker)
            except ValueError as e:
                new_rows.append({
                    "ticker": ticker,
                    "horizon_min": horizon,
                    "strike": float("nan"),
                    "mode": args.mode,
                    "kronos_p_yes": float("nan"),
                    "kronos_mean_close": float("nan"),
                    "kronos_sigma_close": float("nan"),
                    "n_samples": 0,
                    "nan_pct_in_window": float("nan"),
                    "status": "bad_ticker",
                    "error_message": str(e),
                })
                total_fail += 1
                continue
            df_ctx, x_ts, nan_pct = build_context_window(
                coinbase, t, args.context_min,
            )
            if df_ctx.empty or nan_pct > args.nan_pct_max:
                new_rows.append({
                    "ticker": ticker,
                    "horizon_min": horizon,
                    "strike": strike,
                    "mode": args.mode,
                    "kronos_p_yes": float("nan"),
                    "kronos_mean_close": float("nan"),
                    "kronos_sigma_close": float("nan"),
                    "n_samples": 0,
                    "nan_pct_in_window": nan_pct,
                    "status": "no_context" if df_ctx.empty else "nan_window",
                    "error_message": f"nan_pct={nan_pct:.3f}",
                })
                total_fail += 1
                continue
            y_ts = build_y_timestamps(t, horizon)
            prepared.append({
                "ticker": ticker,
                "strike": strike,
                "horizon": horizon,
                "df": df_ctx,
                "x_ts": x_ts,
                "y_ts": y_ts,
                "ctx_len": len(df_ctx),
            })

        # Bucket by ctx_len, then batch within bucket.
        buckets: dict[int, list[dict]] = {}
        for p in prepared:
            buckets.setdefault(p["ctx_len"], []).append(p)
        log(f"  prepared {len(prepared)}, context-length buckets: "
            f"{ {k: len(v) for k, v in buckets.items()} }")

        for ctx_len, bucket in sorted(buckets.items(), reverse=True):
            log(f"  bucket ctx_len={ctx_len}: {len(bucket)} contracts")
            i = 0
            while i < len(bucket):
                batch_prepared = bucket[i : i + args.batch_size]
                i += args.batch_size

                batch_dfs = [p["df"] for p in batch_prepared]
                batch_x_ts = [p["x_ts"] for p in batch_prepared]
                batch_y_ts = [p["y_ts"] for p in batch_prepared]
                batch_meta = [
                    {"ticker": p["ticker"], "strike": p["strike"], "horizon": p["horizon"]}
                    for p in batch_prepared
                ]

                if not batch_dfs:
                    continue

                batch_t0 = time.time()
                try:
                    preds_list = predictor.predict_batch(
                        batch_dfs, batch_x_ts, batch_y_ts,
                        pred_len=horizon,
                        T=args.T, top_p=args.top_p,
                        sample_count=args.sample_count if args.mode == "det" else 1,
                        verbose=False,
                    )
                except Exception as e:  # noqa: BLE001
                    log(f"  predict_batch error: {e!r}")
                    for meta in batch_meta:
                        new_rows.append({
                            "ticker": meta["ticker"],
                            "horizon_min": meta["horizon"],
                            "strike": meta["strike"],
                            "mode": args.mode,
                            "kronos_p_yes": float("nan"),
                            "kronos_mean_close": float("nan"),
                            "kronos_sigma_close": float("nan"),
                            "n_samples": 0,
                            "nan_pct_in_window": float("nan"),
                            "status": "kronos_error",
                            "error_message": repr(e)[:200],
                        })
                        total_fail += 1
                    continue
                batch_elapsed = time.time() - batch_t0

                # For MC mode, re-run predict_batch n_mc_paths times.
                if args.mode == "mc":
                    mc_finals: dict[str, list[float]] = {
                        meta["ticker"]: [] for meta in batch_meta
                    }
                    for meta, pred in zip(batch_meta, preds_list, strict=False):
                        mc_finals[meta["ticker"]].append(
                            float(pred["close"].iloc[-1]),
                        )
                    for _ in range(args.n_mc_paths - 1):
                        try:
                            more = predictor.predict_batch(
                                batch_dfs, batch_x_ts, batch_y_ts,
                                pred_len=horizon,
                                T=args.T, top_p=args.top_p,
                                sample_count=1, verbose=False,
                            )
                            for meta, pred in zip(batch_meta, more, strict=False):
                                mc_finals[meta["ticker"]].append(
                                    float(pred["close"].iloc[-1]),
                                )
                        except Exception as e:  # noqa: BLE001
                            log(f"  mc extra-path error: {e!r}")
                            break
                    for meta in batch_meta:
                        finals = np.array(mc_finals[meta["ticker"]])
                        mu = float(np.mean(finals))
                        sigma = (
                            float(np.std(finals, ddof=1)) if len(finals) > 1 else 0.0
                        )
                        p_yes = clip_p_yes(
                            kronos_to_p_yes_mc(finals, meta["strike"]),
                        )
                        new_rows.append({
                            "ticker": meta["ticker"],
                            "horizon_min": meta["horizon"],
                            "strike": meta["strike"],
                            "mode": "mc",
                            "kronos_p_yes": p_yes,
                            "kronos_mean_close": mu,
                            "kronos_sigma_close": sigma,
                            "n_samples": len(finals),
                            "nan_pct_in_window": 0.0,
                            "status": "ok",
                            "error_message": "",
                        })
                        total_succeed += 1
                else:
                    # det mode: sigma from HISTORICAL context vol, not predicted window
                    import math
                    for meta, pred, hist_df in zip(
                        batch_meta, preds_list, batch_dfs, strict=False,
                    ):
                        mu_final = float(pred["close"].iloc[-1])
                        hist_closes = hist_df["close"].to_numpy()
                        hist_log_ret = np.diff(np.log(np.clip(hist_closes, 1.0, None)))
                        if len(hist_log_ret) >= 2:
                            sigma_1m = float(np.std(hist_log_ret, ddof=1))
                        else:
                            sigma_1m = 0.0
                        sigma_h = sigma_1m * math.sqrt(max(meta["horizon"], 1))
                        p_yes = clip_p_yes(
                            kronos_to_p_yes_det(mu_final, sigma_h, meta["strike"]),
                        )
                        new_rows.append({
                            "ticker": meta["ticker"],
                            "horizon_min": meta["horizon"],
                            "strike": meta["strike"],
                            "mode": "det",
                            "kronos_p_yes": p_yes,
                            "kronos_mean_close": mu_final,
                            "kronos_sigma_close": sigma_h,
                            "n_samples": args.sample_count,
                            "nan_pct_in_window": 0.0,
                            "status": "ok",
                            "error_message": "",
                        })
                        total_succeed += 1

                done_overall = total_succeed + total_fail
                tot_elapsed = time.time() - t_start
                avg = tot_elapsed / max(done_overall, 1)
                remain = (len(needs) - done_overall) * avg
                log(
                    f"  h{horizon} ctx={ctx_len} batch n={len(batch_dfs)} "
                    f"elapsed={batch_elapsed:.1f}s | "
                    f"done {done_overall}/{len(needs)} | avg {avg:.2f}s/contract | "
                    f"~{remain/60:.1f}min remaining",
                )

                # Save cache every 4 batches
                if (i // args.batch_size) % 4 == 0:
                    cache = append_cache(cache, new_rows)
                    save_cache(cache)
                    new_rows = []
                    with open(PROGRESS_PATH, "w") as f:
                        json.dump({
                            "total_succeed": total_succeed,
                            "total_fail": total_fail,
                            "total_remaining": len(needs) - total_succeed - total_fail,
                            "elapsed_sec": time.time() - t_start,
                            "mode": args.mode,
                        }, f, indent=2)

    # Final save
    if new_rows:
        cache = append_cache(cache, new_rows)
        save_cache(cache)
    log(f"=== done. succeeded={total_succeed} failed={total_fail} ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
