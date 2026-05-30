"""Tests for the record-only lead-lag shadow logger core (Round 21 / v16).

Covers the pure, network-free helpers in
kalshi_bot.analysis.lead_lag_shadow:
- home_implied_median (no-vig home implied; degenerate inputs)
- classify_delta (fire / near_miss / None boundaries)
- in_exec_window boundaries
- eastern_date_str night-id across the UTC date boundary
- iso_week_id
- parse_orderbook (full / empty / one-sided books, depth, parity)
- dedup_key
- build_entry_row (home + away side, schema, target_implied, fired)
"""

from __future__ import annotations

from datetime import UTC, datetime

from kalshi_bot.analysis.lead_lag_shadow import (
    ENTRY_COLUMNS,
    NEAR_MISS_THRESHOLD,
    X_THRESHOLD,
    build_entry_row,
    classify_delta,
    dedup_key,
    eastern_date_str,
    home_implied_median,
    in_exec_window,
    iso_week_id,
    parse_orderbook,
)


def _book(home: str, away: str, h_price: float, a_price: float) -> dict:
    return {
        "key": "h2h",
        "outcomes": [
            {"name": home, "price": h_price},
            {"name": away, "price": a_price},
        ],
    }


def test_home_implied_median_no_vig_single_book() -> None:
    game = {
        "home_team": "HOME",
        "away_team": "AWAY",
        "bookmakers": [{"markets": [_book("HOME", "AWAY", 1.5, 2.5)]}],
    }
    # raw: 1/1.5=0.6667, 1/2.5=0.4; no-vig home = 0.6667 / 1.0667 = 0.625
    out = home_implied_median(game)
    assert out is not None
    assert abs(out - 0.625) < 1e-6


def test_home_implied_median_takes_median_across_books() -> None:
    game = {
        "home_team": "HOME",
        "away_team": "AWAY",
        "bookmakers": [
            {"markets": [_book("HOME", "AWAY", 1.5, 2.5)]},  # 0.625
            {"markets": [_book("HOME", "AWAY", 2.0, 2.0)]},  # 0.500
            {"markets": [_book("HOME", "AWAY", 1.25, 5.0)]},  # 0.8/(0.8+0.2)=0.8
        ],
    }
    out = home_implied_median(game)
    assert out is not None
    assert abs(out - 0.625) < 1e-6  # median of {0.5, 0.625, 0.8}


def test_home_implied_median_missing_teams_returns_none() -> None:
    assert home_implied_median({"bookmakers": []}) is None
    assert home_implied_median(
        {"home_team": "H", "away_team": "A", "bookmakers": []}
    ) is None


def test_home_implied_median_ignores_non_h2h_and_bad_prices() -> None:
    game = {
        "home_team": "HOME",
        "away_team": "AWAY",
        "bookmakers": [
            {"markets": [{"key": "spreads", "outcomes": [
                {"name": "HOME", "price": 1.9}, {"name": "AWAY", "price": 1.9}]}]},
            {"markets": [{"key": "h2h", "outcomes": [
                {"name": "HOME", "price": 0}, {"name": "AWAY", "price": 2.0}]}]},
        ],
    }
    # spreads ignored; the h2h has a zero price so it yields no usable pair
    assert home_implied_median(game) is None


def test_classify_delta_boundaries() -> None:
    assert classify_delta(X_THRESHOLD) == "fire"
    assert classify_delta(-X_THRESHOLD) == "fire"
    assert classify_delta(X_THRESHOLD + 0.01) == "fire"
    assert classify_delta(NEAR_MISS_THRESHOLD) == "near_miss"
    assert classify_delta(-NEAR_MISS_THRESHOLD) == "near_miss"
    assert classify_delta(X_THRESHOLD - 1e-9) == "near_miss"
    assert classify_delta(NEAR_MISS_THRESHOLD - 1e-9) is None
    assert classify_delta(0.0) is None


def test_in_exec_window_boundaries() -> None:
    assert in_exec_window(1.0) is True
    assert in_exec_window(3.0) is True
    assert in_exec_window(2.0) is True
    assert in_exec_window(0.99) is False
    assert in_exec_window(3.01) is False


def test_eastern_date_str_crosses_utc_boundary() -> None:
    # 01:30 UTC on May 31 is 21:30 EDT on May 30: same night as a 19:00 game.
    dt = datetime(2026, 5, 31, 1, 30, tzinfo=UTC)
    assert eastern_date_str(dt) == "2026-05-30"
    # 23:00 UTC on May 30 is 19:00 EDT on May 30.
    dt2 = datetime(2026, 5, 30, 23, 0, tzinfo=UTC)
    assert eastern_date_str(dt2) == "2026-05-30"
    # Both games share one night_id despite straddling the UTC date line.
    assert eastern_date_str(dt) == eastern_date_str(dt2)


def test_iso_week_id_format() -> None:
    wid = iso_week_id(datetime(2026, 5, 30, 23, 0, tzinfo=UTC))
    assert wid.startswith("2026-W")
    assert len(wid.split("-W")[1]) == 2


def test_parse_orderbook_full_book() -> None:
    payload = {"orderbook_fp": {
        "yes_dollars": [["0.45", "100"], ["0.48", "50"]],
        "no_dollars": [["0.49", "30"], ["0.50", "200"]],
    }}
    out = parse_orderbook(payload)
    assert out["book_empty"] is False
    assert out["yes_bid"] == 0.48
    assert out["yes_depth"] == 50.0
    assert out["yes_ask"] == 0.50  # 1 - best_no_bid(0.50)
    assert out["no_depth"] == 200.0
    assert out["is_parity_derived"] is True
    assert out["mid"] == 0.49


def test_parse_orderbook_empty() -> None:
    out = parse_orderbook({"orderbook_fp": {"yes_dollars": [], "no_dollars": []}})
    assert out["book_empty"] is True
    assert out["yes_bid"] is None
    assert out["yes_ask"] is None
    assert out["mid"] is None
    assert out["yes_depth"] == 0.0


def test_parse_orderbook_yes_only() -> None:
    out = parse_orderbook({"orderbook_fp": {
        "yes_dollars": [["0.48", "50"]], "no_dollars": []}})
    assert out["book_empty"] is False
    assert out["yes_bid"] == 0.48
    assert out["yes_ask"] is None
    assert out["mid"] == 0.48
    assert out["is_parity_derived"] is False


def test_parse_orderbook_no_only_is_parity_ask() -> None:
    out = parse_orderbook({"orderbook_fp": {
        "yes_dollars": [], "no_dollars": [["0.55", "75"]]}})
    assert out["book_empty"] is False
    assert out["yes_bid"] is None
    assert out["yes_ask"] == 0.45  # 1 - 0.55
    assert out["no_depth"] == 75.0
    assert out["mid"] == 0.45
    assert out["is_parity_derived"] is True


def test_parse_orderbook_malformed_does_not_raise() -> None:
    assert parse_orderbook({})["book_empty"] is True
    assert parse_orderbook({"orderbook_fp": {"yes_dollars": [["bad"]]}})["book_empty"] is True


def test_parse_orderbook_degenerate_no_bid_clamped() -> None:
    # A NO bid at/above 1.00 would imply yes_ask <= 0, which is not a real
    # executable price; it must be discarded, not recorded.
    out = parse_orderbook({"orderbook_fp": {
        "yes_dollars": [], "no_dollars": [["1.00", "10"]]}})
    assert out["book_empty"] is True
    assert out["yes_ask"] is None
    # With a valid yes bid present, the degenerate no bid still yields no ask.
    out2 = parse_orderbook({"orderbook_fp": {
        "yes_dollars": [["0.40", "5"]], "no_dollars": [["1.20", "10"]]}})
    assert out2["yes_bid"] == 0.40
    assert out2["yes_ask"] is None
    assert out2["book_empty"] is False


def test_dedup_key() -> None:
    assert dedup_key("g1", "home", "2026-05-30") == "g1|home|2026-05-30"


def test_build_entry_row_home_side_schema_and_values() -> None:
    captured = datetime(2026, 5, 30, 22, 0, tzinfo=UTC)
    commence = datetime(2026, 5, 31, 0, 0, tzinfo=UTC)  # 2h out
    game = {"id": "g1", "home_team": "HOME", "away_team": "AWAY"}
    book = parse_orderbook({"orderbook_fp": {
        "yes_dollars": [["0.48", "50"]], "no_dollars": [["0.50", "200"]]}})
    row = build_entry_row(
        captured_ts=captured, game=game, delta_sb_home=0.0075,
        p_cur=0.58, p_hist=0.55, odds_snapshot_ts="2026-05-30T19:00:00Z",
        take_home_side=True, classification="fire", ticker="KXMLBGAME-X-HOME",
        commence=commence, close_time="2026-05-31T03:00:00Z", book=book, fire_seq=0,
    )
    assert set(row.keys()) == set(ENTRY_COLUMNS)
    assert row["side"] == "home"
    assert row["fired"] is True
    assert row["book_status"] == "ok"  # default
    assert row["target_implied"] == 0.58  # p_cur for home side
    assert row["ticker"] == "KXMLBGAME-X-HOME"
    assert abs(row["hours_to_commence"] - 2.0) < 1e-6
    assert abs(row["minutes_to_commence"] - 120.0) < 1e-6
    # commence 00:00 UTC May 31 = 20:00 EDT May 30 -> night_id May 30
    assert row["night_id"] == "2026-05-30"
    assert row["yes_ask"] == 0.50


def test_build_entry_row_away_side_target_implied() -> None:
    captured = datetime(2026, 5, 30, 22, 0, tzinfo=UTC)
    commence = datetime(2026, 5, 31, 0, 0, tzinfo=UTC)
    game = {"id": "g2", "home_team": "HOME", "away_team": "AWAY"}
    book = parse_orderbook({"orderbook_fp": {"yes_dollars": [], "no_dollars": []}})
    row = build_entry_row(
        captured_ts=captured, game=game, delta_sb_home=-0.0075,
        p_cur=0.42, p_hist=0.45, odds_snapshot_ts="2026-05-30T19:00:00Z",
        take_home_side=False, classification="fire", ticker="",
        commence=commence, close_time="", book=book, fire_seq=0,
    )
    assert row["side"] == "away"
    # target_implied for away side = 1 - p_cur
    assert abs(row["target_implied"] - 0.58) < 1e-9
    assert row["book_empty"] is True
    assert row["yes_ask"] is None


def test_build_entry_row_book_status_passthrough() -> None:
    captured = datetime(2026, 5, 30, 22, 0, tzinfo=UTC)
    commence = datetime(2026, 5, 31, 0, 0, tzinfo=UTC)
    game = {"id": "g3", "home_team": "HOME", "away_team": "AWAY"}
    book = parse_orderbook({"orderbook_fp": {"yes_dollars": [], "no_dollars": []}})
    row = build_entry_row(
        captured_ts=captured, game=game, delta_sb_home=0.0075,
        p_cur=0.58, p_hist=0.55, odds_snapshot_ts="2026-05-30T19:00:00Z",
        take_home_side=True, classification="fire", ticker="",
        commence=commence, close_time="", book=book, fire_seq=0,
        book_status="no_ticker",
    )
    assert row["book_status"] == "no_ticker"
