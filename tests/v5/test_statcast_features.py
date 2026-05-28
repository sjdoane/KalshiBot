"""Smoke tests for v5-b Statcast feature engineering primitives."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from kalshi_bot_v5.statcast_features import (
    _normalize_name,
    _safe_float,
    build_player_id_lookup,
    compute_statcast_features_as_of,
    extract_player_and_date,
    get_feature_column_names,
)


def test_normalize_name_basic() -> None:
    assert _normalize_name("Aaron Judge") == "aaron judge"
    # Diacritics get stripped.
    assert _normalize_name("José Ramírez") == "jose ramirez"
    # Punctuation.
    assert _normalize_name("J.P. Crawford") == "jp crawford"


def test_safe_float_handles_pd_na() -> None:
    assert np.isnan(_safe_float(pd.NA))
    assert np.isnan(_safe_float(None))
    assert _safe_float(1.5) == 1.5
    assert _safe_float("not a number") != _safe_float("not a number")  # NaN


def test_extract_player_and_date() -> None:
    row = {"player": "Aaron Judge",
           "game_date_parsed": pd.Timestamp("2026-04-15")}
    name, gd = extract_player_and_date(row)
    assert name == "Aaron Judge"
    assert gd == pd.Timestamp("2026-04-15")


def test_compute_statcast_features_empty_history() -> None:
    """When a player has no Statcast history, features are NaN but the
    schema is consistent."""
    bat_groups: dict[int, pd.DataFrame] = {}
    out = compute_statcast_features_as_of(
        12345, "2026-04-15",
        statcast_batter_grouped=bat_groups, is_pitcher=False,
    )
    # n_pitches should be 0, others NaN.
    assert out["bat30_n_pitches"] == 0.0
    assert np.isnan(out["bat30_xba"])
    assert np.isnan(out["bat7_xba"])


def test_compute_statcast_features_no_leak() -> None:
    """Strict less-than as-of cutoff: same-day rows excluded."""
    history = pd.DataFrame({
        "game_date": pd.to_datetime([
            "2026-04-14", "2026-04-15", "2026-04-15", "2026-04-16",
        ]),
        "events": ["single", "single", "field_out", "home_run"],
        "launch_speed": [95.0, 100.0, 80.0, 110.0],
        "launch_angle": [15.0, 20.0, 10.0, 25.0],
        "estimated_ba_using_speedangle": [0.8, 0.7, 0.2, 0.95],
        "estimated_woba_using_speedangle": [0.9, 0.8, 0.1, 1.2],
        "release_speed": [90.0, 91.0, 92.0, 93.0],
        "game_pk": [1, 2, 2, 3],
    })
    bat_groups = {12345: history}
    # As-of 2026-04-15: only the 04-14 row counts.
    out = compute_statcast_features_as_of(
        12345, "2026-04-15",
        statcast_batter_grouped=bat_groups, is_pitcher=False,
    )
    # Long window (30d back from 04-15) should include only 04-14.
    assert out["bat30_n_pitches"] == 1.0
    # As-of 2026-04-16: includes 04-14 AND 04-15 (both 04-15 rows).
    out_after = compute_statcast_features_as_of(
        12345, "2026-04-16",
        statcast_batter_grouped=bat_groups, is_pitcher=False,
    )
    assert out_after["bat30_n_pitches"] == 3.0


def test_get_feature_column_names_no_duplicates() -> None:
    cols = get_feature_column_names()
    assert len(cols) == len(set(cols)), "feature columns must be unique"
    # Has both batter and pitcher prefixes.
    assert any(c.startswith("bat30_") for c in cols)
    assert any(c.startswith("pit30_") for c in cols)


def test_player_id_lookup_smoke() -> None:
    """Basic player-name match via chadwick_register. Slow only on
    first invocation per session.
    """
    pytest.importorskip("pybaseball")
    result = build_player_id_lookup(["Aaron Judge", "definitely_not_a_player"])
    assert "Aaron Judge" in result
    assert result["Aaron Judge"] == 592450  # canonical MLBAM id
    assert "definitely_not_a_player" not in result
