"""Parsing helpers for KXHIGH (daily-high-temperature) market identifiers.

A KXHIGH market ticker looks like `KXHIGHNY-26APR28-T66`:
  - series_ticker: KXHIGHNY (city = NY)
  - event_ticker: KXHIGHNY-26APR28 (date the high temperature was measured)
  - strike suffix: -T66 (greater than 66 F)

The historical-endpoint response omits the `occurrence_datetime` field, so
we derive the occurrence date from the event_ticker as the canonical source.
"""

from __future__ import annotations

import re
from datetime import date

_MONTH_ABBR_TO_NUM = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

# Event ticker format: [KX]HIGH<CITY>-<YY><MMM><DD>. Kalshi renamed the
# series from HIGH<X> to KXHIGH<X> in late 2024; older event_tickers retain
# the legacy prefix. We treat both as the same series and always return the
# canonical KX-prefixed series_ticker.
_EVENT_TICKER_RE = re.compile(r"^(?:KX)?(HIGH[A-Z]+)-(\d{2})([A-Z]{3})(\d{2})$")

# Map series_ticker to city short code used everywhere in the analysis.
SERIES_TO_CITY = {
    "KXHIGHNY": "NY",
    "KXHIGHCHI": "CHI",
    "KXHIGHMIA": "MIA",
    "KXHIGHLAX": "LAX",
    "KXHIGHDEN": "DEN",
}


def parse_event_ticker(event_ticker: str | None) -> tuple[str, date] | None:
    """Return (series_ticker, occurrence_date) parsed from an event_ticker.

    Returns None if the input is None, empty, or does not match the expected
    shape. Year is interpreted as 20YY (Kalshi launched 2021; no contracts
    span the 21st-22nd century boundary).
    """
    if not event_ticker:
        return None
    m = _EVENT_TICKER_RE.match(event_ticker)
    if not m:
        return None
    high_part, yy, mmm, dd = m.groups()
    series_ticker = "KX" + high_part  # canonical, always KX-prefixed
    month = _MONTH_ABBR_TO_NUM.get(mmm)
    if month is None:
        return None
    try:
        return series_ticker, date(2000 + int(yy), month, int(dd))
    except ValueError:
        return None


def parse_occurrence_date(event_ticker: str | None) -> date | None:
    """Just the date portion. Convenience wrapper for DataFrame .apply."""
    parsed = parse_event_ticker(event_ticker)
    return parsed[1] if parsed else None


def city_from_series(series_ticker: str) -> str | None:
    return SERIES_TO_CITY.get(series_ticker)
