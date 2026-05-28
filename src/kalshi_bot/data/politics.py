"""Helpers for Kalshi politics markets.

Unlike KXHIGH (deterministic event-ticker schema encoding city + date), Kalshi
politics tickers do not follow a single regular form. Series cover federal
elections (KXPRES, KXSENATE*, KXHOUSE*), Fed policy (KXFED*, KXFOMC*),
nominations, special elections, state ballot measures, court rulings,
international events, and more. So this module focuses on two tagging tasks
the Phase 2 methodology needs:

1. **Federal-election keyword tagging**. The methodology requires reporting
   per-split fraction of federal-election markets (Section 6.6 of
   phase-2-methodology.md) so we can detect election-cycle composition bias.
2. **Binary vs multi-strike detection**. The methodology excludes multi-
   strike markets in Phase 2 (slope-based recalibration is binary-only).
   Multi-strike events have multiple YES contracts that sum to 1; we detect
   them by grouping markets by event_ticker.

Both helpers operate on the market metadata fields visible at
market_open_time, so they do not introduce leakage.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


FEDERAL_ELECTION_KEYWORDS: tuple[str, ...] = (
    "senate",
    "house",
    "congress",
    "congressional",
    "president",
    "presidential",
    "potus",
    "election",
    "midterm",
    "midterms",
    "primary",
    "primaries",
    "caucus",
    "republican",
    "republicans",
    "democrat",
    "democrats",
    "democratic",
    "ballot",
    "electoral",
    "polling",
    "trump",
    "biden",
    "harris",
    "vance",
    "newsom",
    "desantis",
)
"""Case-insensitive SUBSTRING set used by `is_federal_election_text`.

Tuned for the 2024 and 2026 federal election cycles per the methodology's
"federal-election market" definition. Substring matching is intentionally
permissive (e.g., "senate" matches inside "KXSENATEOH2026" tickers and
also matches inside "Senator" or "Senatorial" text). False positives are
corrected by the manual top-50 audit step in the methodology BEFORE the
gate runs - we prefer over-inclusion over under-inclusion at this stage.

Keywords like "vote" and "gop" were deliberately REMOVED from earlier
drafts because "vote" matches benign text like "devote" and "gop" can
match unrelated initialism. The audit catches remaining false positives.
"""


def is_federal_election_text(text: str | None) -> bool:
    """Return True if any FEDERAL_ELECTION_KEYWORDS substring appears in
    text (case-insensitive). Returns False for None and empty strings.

    Uses simple substring matching - intentionally permissive. The
    methodology's pre-gate top-50 manual audit corrects false positives.
    """
    if not text:
        return False
    lowered = text.lower()
    return any(k in lowered for k in FEDERAL_ELECTION_KEYWORDS)


def is_federal_election_market(row: dict[str, object]) -> bool:
    """Return True if any of (ticker, event_ticker, series_ticker, title,
    subtitle, yes_sub_title, category) match a federal-election keyword.

    `row` is a dict-like market record (pre-DataFrame or pre-Pydantic).
    Missing keys are treated as empty strings. The disjunction is permissive
    by design - the manual top-50 audit in the methodology corrects false
    positives.
    """
    fields_to_check = (
        "ticker",
        "event_ticker",
        "series_ticker",
        "title",
        "subtitle",
        "yes_sub_title",
        "category",
    )
    for field in fields_to_check:
        value = row.get(field)
        if isinstance(value, str) and is_federal_election_text(value):
            return True
    return False


def tag_federal_election(df: pd.DataFrame) -> pd.Series:
    """Vectorized federal-election tagger over a markets DataFrame.

    Returns a boolean Series aligned to df.index. Uses the same logic as
    `is_federal_election_market` but operates on the DataFrame columns. Any
    of the standard text columns can match; missing columns are skipped.
    """
    text_cols = [
        c
        for c in ("ticker", "event_ticker", "series_ticker", "title", "subtitle", "yes_sub_title", "category")
        if c in df.columns
    ]
    if not text_cols:
        # No text columns at all; default to False everywhere.
        return df.index.to_series().map(lambda _: False).astype(bool).rename("is_federal_election_market")
    # fillna + explicit str coercion handles columns with NaN / object dtype that
    # astype(str).agg(" ".join, axis=1) trips over (TypeError on NaN floats).
    cleaned = df[text_cols].fillna("").map(str)
    combined = cleaned.apply(lambda row: " ".join(row.values), axis=1)
    return combined.map(is_federal_election_text).astype(bool).rename("is_federal_election_market")


def count_contracts_per_event(df: pd.DataFrame) -> pd.Series:
    """Return a Series counting markets per event_ticker.

    Indexed by event_ticker. Used to detect multi-strike events (count > 1).
    Multi-strike events have multiple YES contracts under one event that
    represent mutually exclusive outcomes (e.g., a 5-candidate primary).
    """
    if "event_ticker" not in df.columns:
        raise ValueError("count_contracts_per_event requires 'event_ticker' column")
    return df.groupby("event_ticker").size().rename("contracts_per_event")


def is_binary_market(df: pd.DataFrame) -> pd.Series:
    """Tag each market as binary (event has exactly 1 contract) or not.

    Returns a boolean Series aligned to df.index. A market is "binary" if
    its event_ticker maps to exactly one contract in the dataset.

    Caveat: this requires the dataset to contain ALL contracts per event.
    If our fetcher excluded some contracts before this runs, a multi-strike
    event could be misclassified as binary. The methodology's pre-data
    fetcher pulls all contracts per series to keep this consistent.
    """
    if "event_ticker" not in df.columns:
        raise ValueError("is_binary_market requires 'event_ticker' column")
    counts = count_contracts_per_event(df)
    return df["event_ticker"].map(counts).eq(1).rename("is_binary_market")
