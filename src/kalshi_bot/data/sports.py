"""Helpers for Kalshi sports markets.

Like politics.py, this module focuses on two tagging tasks the
sports-longhorizon methodology needs:

1. **League tagging** (Section 4 diversity requirement and Section 5.2
   leave-one-league-out check). Major leagues: NFL, NBA, MLB, NHL,
   NCAA-FB, NCAA-BB, MLS, PGA, F1, BOXING, UFC, TENNIS, CRICKET, F1,
   NASCAR. Plus a "OTHER" catch-all.

2. **Binary vs multi-strike detection** (Section 2.2 binary-only filter).
   Same definition as politics: exactly 1 contract per event_ticker.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


# League keyword -> canonical league code mapping. Substrings are matched
# case-insensitively against ticker, event_ticker, series_ticker, title,
# subtitle, yes_sub_title, category. First match wins (order matters; put
# more specific patterns first).
LEAGUE_KEYWORDS: tuple[tuple[str, str], ...] = (
    # NFL and related
    ("kxnfl", "NFL"),
    ("nfl", "NFL"),
    ("super bowl", "NFL"),
    ("superbowl", "NFL"),
    # NCAA football vs basketball; check football keywords first
    ("ncaaf", "NCAA-FB"),
    ("college football", "NCAA-FB"),
    ("cfp", "NCAA-FB"),
    ("ncaab", "NCAA-BB"),
    ("march madness", "NCAA-BB"),
    ("ncaa", "NCAA-OTHER"),
    # NBA
    ("kxnba", "NBA"),
    ("nba", "NBA"),
    # MLB
    ("kxmlb", "MLB"),
    ("mlb", "MLB"),
    ("world series", "MLB"),
    # NHL
    ("kxnhl", "NHL"),
    ("nhl", "NHL"),
    ("stanley cup", "NHL"),
    # Soccer
    ("kxmls", "MLS"),
    ("mls", "MLS"),
    ("premier league", "EPL"),
    ("epl", "EPL"),
    ("la liga", "LALIGA"),
    ("bundesliga", "BUNDES"),
    ("champions league", "UEFA-CL"),
    ("world cup", "FIFA-WC"),
    # Golf
    ("pga", "PGA"),
    ("masters", "PGA"),
    ("liv golf", "LIV"),
    # Motor
    ("kxf1", "F1"),
    ("formula 1", "F1"),
    ("formula one", "F1"),
    ("nascar", "NASCAR"),
    ("indycar", "INDYCAR"),
    # Combat
    ("ufc", "UFC"),
    ("mma", "MMA"),
    ("boxing", "BOXING"),
    # Tennis
    ("tennis", "TENNIS"),
    ("wimbledon", "TENNIS"),
    ("us open", "TENNIS"),
    ("french open", "TENNIS"),
    ("australian open", "TENNIS"),
    # Olympics
    ("olympic", "OLYMPICS"),
    # Cricket
    ("ipl", "CRICKET"),
    ("cricket", "CRICKET"),
)


def classify_league(text: str | None) -> str | None:
    """Return canonical league code for the first matching keyword, or
    None if no league pattern matches.

    Substring matching is case-insensitive. Intentionally permissive;
    manual top-N audit corrects false positives per methodology Section
    4 pre-commitment.
    """
    if not text:
        return None
    lowered = text.lower()
    for keyword, league in LEAGUE_KEYWORDS:
        if keyword in lowered:
            return league
    return None


def classify_market_league(row: dict[str, object]) -> str:
    """Return league code by inspecting standard market metadata fields.
    Returns "OTHER" if no league pattern matches any field."""
    fields = (
        "ticker", "event_ticker", "series_ticker",
        "title", "subtitle", "yes_sub_title", "category",
    )
    for field in fields:
        value = row.get(field)
        if isinstance(value, str):
            league = classify_league(value)
            if league is not None:
                return league
    return "OTHER"


def tag_league(df: pd.DataFrame) -> pd.Series:
    """Vectorized league tagger over a sports markets DataFrame.

    Returns a Series of canonical league codes aligned to df.index. Uses
    classify_market_league per-row. Defaults to "OTHER" when no field
    matches.
    """
    text_cols = [
        c for c in
        ("ticker", "event_ticker", "series_ticker", "title", "subtitle", "yes_sub_title", "category")
        if c in df.columns
    ]
    if not text_cols:
        return df.index.to_series().map(lambda _: "OTHER").rename("league")
    cleaned = df[text_cols].fillna("").map(str)

    def _row_league(row: object) -> str:
        for field in text_cols:
            v = row[field]
            league = classify_league(v) if v else None
            if league is not None:
                return league
        return "OTHER"

    return cleaned.apply(_row_league, axis=1).rename("league")


def count_contracts_per_event(df: pd.DataFrame) -> pd.Series:
    """Same as politics.count_contracts_per_event."""
    if "event_ticker" not in df.columns:
        raise ValueError("count_contracts_per_event requires 'event_ticker' column")
    return df.groupby("event_ticker").size().rename("contracts_per_event")


def is_binary_market(df: pd.DataFrame) -> pd.Series:
    """Strict binary: 1 contract per event. Kept for backward-compat with
    politics build_dataset (which locked this definition)."""
    if "event_ticker" not in df.columns:
        raise ValueError("is_binary_market requires 'event_ticker' column")
    counts = count_contracts_per_event(df)
    return df["event_ticker"].map(counts).eq(1).rename("is_binary_market")


# Per Round 3 sports methodology revision (operator-authorized
# methodology design pivot after both Round 2 compression-maker gates
# failed mechanically): markets are tagged into three structural tiers
# based on their event's contract count. The "tradable" filter accepts
# tiers 1-3 (events with up to 10 sibling contracts). Tier 4 (large
# multi-strike like NCAA tournament brackets) is excluded.

TIER_THRESHOLD_BROAD = 10  # contracts per event; up to and including
TIER_THRESHOLD_TRADABLE = 10  # same; alias for clarity


def market_tier(df: pd.DataFrame) -> pd.Series:
    """Tag each market with a structural tier label based on its event's
    contract count.

    - "single_name": exactly 1 contract per event (pure binary)
    - "two_way": exactly 2 contracts per event (e.g., NFL game with two
      mutually-exclusive YES contracts; coherent two-way)
    - "small_multi": 3 to 10 contracts per event (small championships,
      small primary fields)
    - "large_multi": > 10 contracts (large brackets; excluded by the
      Round 3 tradable filter)
    """
    if "event_ticker" not in df.columns:
        raise ValueError("market_tier requires 'event_ticker' column")
    counts = df["event_ticker"].map(count_contracts_per_event(df))

    def _tag(n: int) -> str:
        if n == 1:
            return "single_name"
        if n == 2:
            return "two_way"
        if n <= TIER_THRESHOLD_TRADABLE:
            return "small_multi"
        return "large_multi"

    return counts.map(_tag).rename("market_tier")


def is_tradable_event_size(df: pd.DataFrame) -> pd.Series:
    """Round 3 tradable filter: events with <= TIER_THRESHOLD_TRADABLE
    contracts. Excludes large brackets (> 10 contracts) where
    per-contract isotonic calibration on multi-strike incoherent
    structure is most problematic."""
    if "event_ticker" not in df.columns:
        raise ValueError("is_tradable_event_size requires 'event_ticker' column")
    counts = df["event_ticker"].map(count_contracts_per_event(df))
    return counts.le(TIER_THRESHOLD_TRADABLE).rename("is_tradable_event_size")
