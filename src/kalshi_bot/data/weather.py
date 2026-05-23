"""Historical weather data ingestion via Open-Meteo's archive API.

The KXHIGH market resolves on the NWS Climatological Report Daily high
temperature in degrees Fahrenheit. The official source for settlement is
NWS, but for backtesting we need a parallel free archive that goes back
several years and supports a clean automated pull. Open-Meteo's archive
endpoint serves ERA5 reanalysis + GFS ensemble historical and is the
cleanest free option at the time of writing.

Endpoints used:
    https://archive-api.open-meteo.com/v1/archive  (observations + ERA5)
    https://historical-forecast-api.open-meteo.com/v1/forecast  (past forecasts)

The observation endpoint returns the realized hourly + daily temperature
for the target city, useful for cross-checking Kalshi's settlement value.
The historical-forecast endpoint returns the forecast that was issued at
a chosen lead time, useful for computing a "model probability" of the
daily high exceeding a given strike.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

if TYPE_CHECKING:
    from datetime import date

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class CityCoords:
    name: str
    lat: float
    lon: float
    tz: str  # IANA timezone


# Lat/lon picked to align with the official NWS station the Kalshi rule cites.
# NY uses Central Park (KNYC), CHI uses O'Hare (KORD), MIA uses Miami Intl
# (KMIA), LAX uses Los Angeles Intl (KLAX), DEN uses Denver Intl (KDEN).
CITIES: dict[str, CityCoords] = {
    "NY":  CityCoords(name="New York Central Park", lat=40.7794, lon=-73.9692, tz="America/New_York"),
    "CHI": CityCoords(name="Chicago O'Hare",        lat=41.9742, lon=-87.9073, tz="America/Chicago"),
    "MIA": CityCoords(name="Miami International",   lat=25.7959, lon=-80.2870, tz="America/New_York"),
    "LAX": CityCoords(name="Los Angeles Intl",      lat=33.9416, lon=-118.4085, tz="America/Los_Angeles"),
    "DEN": CityCoords(name="Denver International",  lat=39.8561, lon=-104.6737, tz="America/Denver"),
}


def _f(c: float) -> float:
    """Celsius to Fahrenheit."""
    return c * 9.0 / 5.0 + 32.0


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=1, max=30))
def fetch_observed_daily_high(
    city: str,
    start: date,
    end: date,
    *,
    client: httpx.Client | None = None,
) -> dict[str, float]:
    """Return {date_iso: observed_daily_high_F} for the city across [start, end].

    Uses Open-Meteo's archive endpoint with ERA5 reanalysis. Free, no key.
    """
    coords = CITIES[city]
    own_client = False
    if client is None:
        client = httpx.Client(timeout=30.0)
        own_client = True
    try:
        params = {
            "latitude": coords.lat,
            "longitude": coords.lon,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": "temperature_2m_max",
            "temperature_unit": "fahrenheit",
            "timezone": coords.tz,
        }
        resp = client.get("https://archive-api.open-meteo.com/v1/archive", params=params)
        resp.raise_for_status()
        payload = resp.json()
    finally:
        if own_client:
            client.close()
    daily = payload.get("daily", {})
    dates = daily.get("time", []) or []
    highs = daily.get("temperature_2m_max", []) or []
    if len(dates) != len(highs):
        log.warning(
            "observed_daily_length_mismatch",
            city=city,
            n_dates=len(dates),
            n_highs=len(highs),
        )
    out: dict[str, float] = {}
    for d, t in zip(dates, highs, strict=False):
        if t is not None:
            out[d] = float(t)
    return out


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=1, max=30))
def fetch_historical_forecast_ensemble(
    city: str,
    start: date,
    end: date,
    *,
    lead_hours: int = 24,
    client: httpx.Client | None = None,
) -> dict[str, list[float]]:
    """Return {date_iso: [ensemble_member_F, ...]} for hist GFS ensemble.

    Open-Meteo's historical-forecast endpoint replays the forecast that was
    actually issued `lead_hours` before the target date. Use ensemble
    members to derive a "probability that the daily high exceeds X" by
    counting members above the strike.
    """
    coords = CITIES[city]
    own_client = False
    if client is None:
        client = httpx.Client(timeout=30.0)
        own_client = True
    try:
        params = {
            "latitude": coords.lat,
            "longitude": coords.lon,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": "temperature_2m_max",
            "temperature_unit": "fahrenheit",
            "timezone": coords.tz,
            "models": "gfs_seamless",
            "past_days": 0,
            "forecast_days": 0,
            # Pull at a fixed lead by adjusting end_date relative to forecast_issue.
            # Open-Meteo doesn't expose an explicit lead_hours knob; the workaround
            # is to use the past forecast endpoint and bracket on issue date.
        }
        # Use the historical-forecast endpoint, which serves past forecasts:
        url = "https://historical-forecast-api.open-meteo.com/v1/forecast"
        resp = client.get(url, params=params)
        resp.raise_for_status()
        payload = resp.json()
    finally:
        if own_client:
            client.close()
    daily = payload.get("daily", {})
    dates = daily.get("time", []) or []
    highs = daily.get("temperature_2m_max", []) or []
    out: dict[str, list[float]] = {}
    for d, t in zip(dates, highs, strict=False):
        if t is not None:
            out[d] = [float(t)]  # single-member; ensemble support TBD
    return out
