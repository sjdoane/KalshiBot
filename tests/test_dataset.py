"""Tests for the analysis dataset builder.

Synthetic markets + trades go in, an analysis-ready dataframe with VWAP and
filtered outcomes comes out. We do not test against real Kalshi files here;
that's the job of running the full pipeline end-to-end.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
import pytest

from kalshi_bot.analysis import dataset as ds

if TYPE_CHECKING:
    from pathlib import Path


def _market_row(
    *,
    ticker: str,
    event_ticker: str,
    open_t: str,
    close_t: str,
    floor_strike: int,
    result: str,
    expiration_value: str = "70.00",
    volume_fp: str = "1000.00",
) -> dict:
    return {
        "ticker": ticker,
        "event_ticker": event_ticker,
        "open_time": open_t,
        "close_time": close_t,
        "floor_strike": floor_strike,
        "result": result,
        "expiration_value": expiration_value,
        "volume_fp": volume_fp,
    }


def _trade_row(*, ticker: str, price: str, count: str, ts: str) -> dict:
    return {
        "ticker": ticker,
        "yes_price_dollars": price,
        "count_fp": count,
        "no_price_dollars": "1.0000",
        "created_time": ts,
        "trade_id": f"id-{ticker}-{ts}",
    }


def _setup_fixtures(tmp_path: Path) -> None:
    markets_dir = tmp_path / "data/raw/kalshi/markets"
    trades_dir = tmp_path / "data/raw/kalshi/trades"
    markets_dir.mkdir(parents=True)
    trades_dir.mkdir(parents=True)
    ds.RAW_MARKETS_DIR = markets_dir
    ds.RAW_TRADES_DIR = trades_dir
    ds.PROCESSED_DIR = tmp_path / "data/processed"

    # 3 NY markets: one binary YES, one binary NO, one scalar (excluded).
    markets = pd.DataFrame(
        [
            _market_row(
                ticker="KXHIGHNY-26APR28-T66",
                event_ticker="KXHIGHNY-26APR28",
                open_t="2026-04-27T14:00:00Z",
                close_t="2026-04-29T04:59:00Z",
                floor_strike=66,
                result="no",
                expiration_value="65.00",
            ),
            _market_row(
                ticker="KXHIGHNY-26APR28-T55",
                event_ticker="KXHIGHNY-26APR28",
                open_t="2026-04-27T14:00:00Z",
                close_t="2026-04-29T04:59:00Z",
                floor_strike=55,
                result="yes",
                expiration_value="65.00",
            ),
            _market_row(
                ticker="KXHIGHNY-26APR28-S",
                event_ticker="KXHIGHNY-26APR28",
                open_t="2026-04-27T14:00:00Z",
                close_t="2026-04-29T04:59:00Z",
                floor_strike=70,
                result="scalar",
                expiration_value="65.00",
            ),
        ]
    )
    markets.to_parquet(markets_dir / "KXHIGHNY.parquet")

    # Trades only for the two binary markets, in the methodology window
    # (close - 90m to close - 30m = 2026-04-29T03:29 to 2026-04-29T04:29).
    trades = pd.DataFrame(
        [
            _trade_row(
                ticker="KXHIGHNY-26APR28-T66",
                price="0.0500",
                count="100.00",
                ts="2026-04-29T03:45:00Z",
            ),
            _trade_row(
                ticker="KXHIGHNY-26APR28-T66",
                price="0.0700",
                count="300.00",
                ts="2026-04-29T04:00:00Z",
            ),
            _trade_row(
                ticker="KXHIGHNY-26APR28-T55",
                price="0.9000",
                count="500.00",
                ts="2026-04-29T04:10:00Z",
            ),
        ]
    )
    trades.to_parquet(trades_dir / "KXHIGHNY.parquet")


def test_build_for_series_filters_and_joins(tmp_path: Path) -> None:
    _setup_fixtures(tmp_path)
    out = ds.build_for_series("KXHIGHNY")

    # Three markets in: T66 (binary), T55 (binary), -S (scalar, excluded).
    assert len(out) == 2
    by_ticker = out.set_index("ticker")

    # T66: VWAP = (0.05*100 + 0.07*300) / 400 = 26 / 400 = 0.065
    assert by_ticker.loc["KXHIGHNY-26APR28-T66", "mid_price_at_T"] == pytest.approx(0.065)
    assert by_ticker.loc["KXHIGHNY-26APR28-T66", "outcome"] == 0
    assert by_ticker.loc["KXHIGHNY-26APR28-T66", "n_trades_in_window"] == 2
    assert by_ticker.loc["KXHIGHNY-26APR28-T66", "volume_in_window"] == pytest.approx(400.0)

    # T55: single trade -> VWAP equals that price
    assert by_ticker.loc["KXHIGHNY-26APR28-T55", "mid_price_at_T"] == pytest.approx(0.90)
    assert by_ticker.loc["KXHIGHNY-26APR28-T55", "outcome"] == 1

    # Required columns are present
    expected_cols = {
        "ticker",
        "series_ticker",
        "city",
        "occurrence_date",
        "market_open_time",
        "market_close_time",
        "strike_F",
        "observed_high_F",
        "outcome",
        "mid_price_at_T",
        "n_trades_in_window",
        "volume_in_window",
    }
    assert set(out.columns) == expected_cols
    assert (out["city"] == "NY").all()


def test_build_for_series_handles_missing_trades(tmp_path: Path) -> None:
    _setup_fixtures(tmp_path)
    # Delete the trades parquet
    (tmp_path / "data/raw/kalshi/trades/KXHIGHNY.parquet").unlink()
    out = ds.build_for_series("KXHIGHNY")
    # All rows should be filtered out because mid_price_at_T is NaN.
    assert out.empty
