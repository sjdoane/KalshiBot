"""v7 Angle B Kronos feature extraction.

Per research/v7/03-kronos-methodology.md.

Extracts `kronos_p_yes` for each (ticker, horizon) sample by feeding 120-min
Coinbase 1m OHLCV context into Kronos-base, producing a price-distribution
forecast for the next `horizon_min` minutes, and integrating the predicted
final-bar close above the contract strike.

Two modes for converting Kronos output into p_yes:

1. MC mode (preferred when CPU latency permits): call predictor.predict() with
   sample_count=1 multiple times to collect independent sample paths. Empirical
   p_yes = fraction of paths where pred_close_at_close_time > strike.

2. Deterministic mode (fallback): call predictor.predict() once with
   sample_count=K (default 10), use the mean predicted final-bar close as mu
   and stdev of the 1-min log returns over the predicted window as sigma.
   p_yes = 1 - Phi((log strike - log mu) / sigma).

Mode is selected by the caller per the methodology Section 5.1 latency budget.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd
from scipy.stats import norm


STRIKE_RE = re.compile(r"-T(?P<strike>\d+(\.\d+)?)$")


def parse_strike(ticker: str) -> float:
    """Parse the strike from a KXBTCD ticker.

    Ticker format: KXBTCD-{YYMMMDDHH}-T{strike}, e.g. KXBTCD-24DEC1209-T100749.99.
    Returns strike as a float in USD.

    Raises ValueError if the format does not match.
    """
    m = STRIKE_RE.search(ticker)
    if not m:
        raise ValueError(f"cannot parse strike from ticker {ticker!r}")
    return float(m.group("strike"))


def build_context_window(
    coinbase_1m: pd.DataFrame,
    t: pd.Timestamp,
    context_min: int = 120,
    min_context_min: int = 60,
) -> tuple[pd.DataFrame, pd.Series, float]:
    """Build a context-min OHLCV window ending at `t`.

    Returns (df, x_timestamp, nan_pct).

    Preferred length is `context_min`. If Coinbase cache starts after
    `t - context_min`, fall back to whatever is available, provided at least
    `min_context_min` minutes are present. Below that floor, return empty.

    df has columns open, high, low, close, volume, amount where amount is
    synthesized as volume * close.
    x_timestamp is a Series of pandas Timestamps for the bars in df.
    nan_pct is the fraction of bars that were missing within the window
    actually used (post-truncation). Caller may drop if nan_pct > 0.20.
    """
    available_start = coinbase_1m["time"].min()
    requested_start = t - pd.Timedelta(minutes=context_min)
    effective_start = max(requested_start, available_start)
    # actual length we will request, in minutes
    effective_min = int((t - effective_start).total_seconds() // 60)
    if effective_min < min_context_min:
        return pd.DataFrame(), pd.Series(dtype="datetime64[ns, UTC]"), 1.0
    effective_min = min(effective_min, context_min)

    expected_times = pd.date_range(
        end=t.floor("1min"),
        periods=effective_min,
        freq="1min",
        tz="UTC",
    )
    mask = (coinbase_1m["time"] >= expected_times[0]) & (
        coinbase_1m["time"] <= expected_times[-1]
    )
    sub = coinbase_1m.loc[mask].sort_values("time").reset_index(drop=True)
    sub = sub.set_index("time").reindex(expected_times)
    sub.index.name = "time"
    n_total = len(expected_times)
    n_present = int(sub["close"].notna().sum())
    nan_pct = 1.0 - (n_present / n_total) if n_total else 1.0

    for col in ("open", "high", "low", "close", "volume"):
        if col in sub.columns:
            sub[col] = sub[col].ffill().bfill()
    if sub["close"].isna().any():
        return pd.DataFrame(), pd.Series(dtype="datetime64[ns, UTC]"), nan_pct

    sub["volume"] = sub["volume"].fillna(0.0)
    sub["amount"] = sub["volume"] * sub["close"]
    df = sub[["open", "high", "low", "close", "volume", "amount"]].reset_index(
        drop=True,
    )
    x_timestamp = pd.Series(expected_times).reset_index(drop=True)
    return df, x_timestamp, nan_pct


def build_y_timestamps(
    t: pd.Timestamp,
    horizon_min: int,
) -> pd.Series:
    """Future timestamps for the horizon_min prediction window.

    Returns horizon_min 1-min timestamps from t+1min to t+horizon_min.
    """
    start = t + pd.Timedelta(minutes=1)
    times = pd.date_range(
        start=start.floor("1min"),
        periods=horizon_min,
        freq="1min",
        tz="UTC",
    )
    return pd.Series(times).reset_index(drop=True)


@dataclass
class KronosPrediction:
    ticker: str
    horizon_min: int
    strike: float
    mode: Literal["mc", "det"]
    kronos_p_yes: float
    kronos_mean_close: float
    kronos_sigma_close: float
    n_samples: int
    nan_pct_in_window: float
    status: str  # 'ok', 'nan_window', 'kronos_error', 'no_context'
    error_message: str = ""


def kronos_predict_mc(
    predictor: Any,
    df: pd.DataFrame,
    x_timestamp: pd.Series,
    y_timestamp: pd.Series,
    pred_len: int,
    n_paths: int,
    T: float = 1.0,
    top_p: float = 0.9,
) -> tuple[np.ndarray, float, float]:
    """Run predictor.predict() n_paths times with sample_count=1 each.

    Returns (final_closes_array, mean_final_close, sigma_final_close).
    """
    finals: list[float] = []
    for _ in range(n_paths):
        pred = predictor.predict(
            df=df,
            x_timestamp=x_timestamp,
            y_timestamp=y_timestamp,
            pred_len=pred_len,
            T=T,
            top_p=top_p,
            sample_count=1,
            verbose=False,
        )
        finals.append(float(pred["close"].iloc[-1]))
    arr = np.array(finals)
    return arr, float(np.mean(arr)), float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0


def kronos_predict_det(
    predictor: Any,
    df: pd.DataFrame,
    x_timestamp: pd.Series,
    y_timestamp: pd.Series,
    pred_len: int,
    sample_count: int = 10,
    T: float = 1.0,
    top_p: float = 0.9,
) -> tuple[pd.DataFrame, float, float]:
    """Deterministic-mode prediction: average over sample_count internally.

    Returns (full_pred_df, mean_final_close, sigma_log_return_per_horizon).

    sigma_log_return_per_horizon is the stdev of the 1-min log returns within
    the HISTORICAL context window, scaled by sqrt(horizon_min). This is the
    noise estimate for the Normal CDF integration of p_yes.

    Why context-based sigma (not predicted-window sigma): Kronos's internal
    averaging over sample_count smooths the predicted path so the predicted
    log-return stdev under-estimates the realized BTC vol by 10x or more.
    Using the HISTORICAL 120-min log-return stdev anchors sigma to actual BTC
    behavior the model observed.
    """
    pred = predictor.predict(
        df=df,
        x_timestamp=x_timestamp,
        y_timestamp=y_timestamp,
        pred_len=pred_len,
        T=T,
        top_p=top_p,
        sample_count=sample_count,
        verbose=False,
    )
    # historical context sigma (1-min log return stdev) over input window
    hist_closes = df["close"].to_numpy()
    hist_log_returns = np.diff(np.log(np.clip(hist_closes, 1.0, None)))
    if len(hist_log_returns) >= 2:
        sigma_1m_hist = float(np.std(hist_log_returns, ddof=1))
    else:
        sigma_1m_hist = 0.0
    sigma_horizon = sigma_1m_hist * math.sqrt(max(pred_len, 1))
    return pred, float(pred["close"].iloc[-1]), sigma_horizon


def kronos_to_p_yes_mc(
    sample_finals: np.ndarray,
    strike: float,
) -> float:
    """Empirical p_yes from MC sample paths."""
    if len(sample_finals) == 0:
        return float("nan")
    return float((sample_finals > strike).sum() / len(sample_finals))


def kronos_to_p_yes_det(
    mu_final_close: float,
    sigma_log_return: float,
    strike: float,
) -> float:
    """Normal-CDF p_yes from deterministic point forecast + sigma."""
    if sigma_log_return <= 0 or mu_final_close <= 0 or strike <= 0:
        return float("nan")
    # log-normal: ln(price) ~ Normal(ln(mu), sigma)
    z = (math.log(strike) - math.log(mu_final_close)) / sigma_log_return
    return float(1.0 - norm.cdf(z))


def clip_p_yes(p: float, lo: float = 1e-3, hi: float = 1.0 - 1e-3) -> float:
    if not (p == p):  # NaN
        return float("nan")
    return float(min(max(p, lo), hi))


def predict_contract(
    predictor: Any,
    ticker: str,
    close_time: pd.Timestamp,
    horizon_min: int,
    coinbase_1m: pd.DataFrame,
    mode: Literal["mc", "det"] = "det",
    n_paths_mc: int = 30,
    n_samples_det: int = 10,
    context_min: int = 120,
    T: float = 1.0,
    top_p: float = 0.9,
    nan_pct_max: float = 0.20,
) -> KronosPrediction:
    """Top-level: predict kronos_p_yes for one (ticker, horizon)."""
    try:
        strike = parse_strike(ticker)
    except ValueError as e:
        return KronosPrediction(
            ticker=ticker,
            horizon_min=horizon_min,
            strike=float("nan"),
            mode=mode,
            kronos_p_yes=float("nan"),
            kronos_mean_close=float("nan"),
            kronos_sigma_close=float("nan"),
            n_samples=0,
            nan_pct_in_window=float("nan"),
            status="bad_ticker",
            error_message=str(e),
        )

    t = close_time - pd.Timedelta(minutes=horizon_min)
    df_ctx, x_ts, nan_pct = build_context_window(coinbase_1m, t, context_min)
    if df_ctx.empty:
        return KronosPrediction(
            ticker=ticker,
            horizon_min=horizon_min,
            strike=strike,
            mode=mode,
            kronos_p_yes=float("nan"),
            kronos_mean_close=float("nan"),
            kronos_sigma_close=float("nan"),
            n_samples=0,
            nan_pct_in_window=nan_pct,
            status="no_context",
            error_message="context window has no usable Coinbase data",
        )
    if nan_pct > nan_pct_max:
        return KronosPrediction(
            ticker=ticker,
            horizon_min=horizon_min,
            strike=strike,
            mode=mode,
            kronos_p_yes=float("nan"),
            kronos_mean_close=float("nan"),
            kronos_sigma_close=float("nan"),
            n_samples=0,
            nan_pct_in_window=nan_pct,
            status="nan_window",
            error_message=f"nan_pct={nan_pct:.3f} > {nan_pct_max}",
        )

    y_ts = build_y_timestamps(t, horizon_min)

    try:
        if mode == "mc":
            sample_finals, mu, sigma_finals = kronos_predict_mc(
                predictor, df_ctx, x_ts, y_ts, horizon_min,
                n_paths=n_paths_mc, T=T, top_p=top_p,
            )
            p_yes_raw = kronos_to_p_yes_mc(sample_finals, strike)
            n_samples = n_paths_mc
            sigma_out = sigma_finals
        else:
            pred_df, mu, sigma_log_h = kronos_predict_det(
                predictor, df_ctx, x_ts, y_ts, horizon_min,
                sample_count=n_samples_det, T=T, top_p=top_p,
            )
            p_yes_raw = kronos_to_p_yes_det(mu, sigma_log_h, strike)
            n_samples = n_samples_det
            sigma_out = sigma_log_h
    except Exception as e:  # noqa: BLE001
        return KronosPrediction(
            ticker=ticker,
            horizon_min=horizon_min,
            strike=strike,
            mode=mode,
            kronos_p_yes=float("nan"),
            kronos_mean_close=float("nan"),
            kronos_sigma_close=float("nan"),
            n_samples=0,
            nan_pct_in_window=nan_pct,
            status="kronos_error",
            error_message=repr(e)[:200],
        )

    p_yes = clip_p_yes(p_yes_raw)

    return KronosPrediction(
        ticker=ticker,
        horizon_min=horizon_min,
        strike=strike,
        mode=mode,
        kronos_p_yes=p_yes,
        kronos_mean_close=float(mu),
        kronos_sigma_close=float(sigma_out),
        n_samples=n_samples,
        nan_pct_in_window=nan_pct,
        status="ok",
        error_message="",
    )
