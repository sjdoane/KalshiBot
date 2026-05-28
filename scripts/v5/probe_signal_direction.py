"""V5-A1: live + historical signal-direction probe.

LIVE (h2h game outcomes, MATCH-class events from v1's resting orders):
  - 1 call: soccer_fifa_world_cup h2h us  (covers 3 WC events)
  - 1 call: mma_mixed_martial_arts h2h us (covers UFC fights)
  - 1 call: boxing_boxing h2h us          (covers boxing fights)
  - 1 call: americanfootball_nfl h2h us   (covers NFLGAME)
  TOTAL: 4 live credits

HISTORICAL (5 NBA team-season win-total markets, NBA championship outrights):
  - 5 calls: /v4/historical/sports/basketball_nba_championship_winner/odds
    at T-7d for the closest snapshot. Each call covers ALL 30 teams.
    Cost: 10 credits per call x 1 market x 1 region = 10 credits each.
  TOTAL: 50 historical credits

GRAND TOTAL: 54 credits (within phase budget 100, project total 500 free).

For each Kalshi market, compute:
  - kalshi_yes_price (pulled from Kalshi /markets endpoint or from prior
    v1 state if recent; for historical, use the v3 inventory T-35d VWAP
    as a proxy).
  - sportsbook_implied_p (best-of-book OR median across books, de-vigged
    via odds = 1/dec_odds normalized so totals sum to 1).
  - divergence_cents = (kalshi - sportsbook) * 100.

Compare to V3-C's +9.21c mean Kalshi-over-Polymarket measurement.

Output: data/v5/signal_direction_probe.json, signal_direction_probe.parquet.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "v5"
OUT_DIR.mkdir(parents=True, exist_ok=True)
LIVE_CACHE = OUT_DIR / "odds_api_live_cache"
HIST_CACHE = OUT_DIR / "odds_api_historical_cache"
LIVE_CACHE.mkdir(parents=True, exist_ok=True)
HIST_CACHE.mkdir(parents=True, exist_ok=True)
BASE = "https://api.the-odds-api.com/v4"
KEY = os.environ["THE_ODDS_API_KEY"]
THROTTLE_SEC = 1.1


def implied_from_decimal(dec_odds: float) -> float:
    if dec_odds <= 0:
        return 0.0
    return 1.0 / dec_odds


def devig_2way(p1: float, p2: float) -> tuple[float, float]:
    s = p1 + p2
    if s <= 0:
        return 0.0, 0.0
    return p1 / s, p2 / s


def devig_3way(p1: float, p2: float, p3: float) -> tuple[float, float, float]:
    s = p1 + p2 + p3
    if s <= 0:
        return 0.0, 0.0, 0.0
    return p1 / s, p2 / s, p3 / s


def fetch_live_odds(sport_key: str, markets: str = "h2h", regions: str = "us") -> dict:
    cache = LIVE_CACHE / f"{sport_key}_{markets}_{regions}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    url = (
        f"{BASE}/sports/{sport_key}/odds"
        f"?apiKey={KEY}&regions={regions}&markets={markets}&oddsFormat=decimal"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "project-kalshi-v5-research"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
        used = r.headers.get("x-requests-used", "")
        remaining = r.headers.get("x-requests-remaining", "")
        last = r.headers.get("x-requests-last", "")
    data = json.loads(body)
    out = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "x_requests_used": used,
        "x_requests_remaining": remaining,
        "x_requests_last_cost": last,
        "events": data,
    }
    cache.write_text(json.dumps(out, indent=2), encoding="utf-8")
    time.sleep(THROTTLE_SEC)
    return out


def fetch_historical_odds(
    sport_key: str,
    date_iso: str,
    markets: str = "outrights",
    regions: str = "us",
) -> dict:
    cache = HIST_CACHE / f"{sport_key}_{markets}_{regions}_{date_iso.replace(':','').replace('-','')}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    url = (
        f"{BASE}/historical/sports/{sport_key}/odds"
        f"?apiKey={KEY}&regions={regions}&markets={markets}"
        f"&oddsFormat=decimal&date={date_iso}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "project-kalshi-v5-research"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
            used = r.headers.get("x-requests-used", "")
            remaining = r.headers.get("x-requests-remaining", "")
            last = r.headers.get("x-requests-last", "")
    except urllib.error.HTTPError as exc:
        cache.write_text(json.dumps({"error": str(exc), "status": exc.code}), encoding="utf-8")
        return {"error": str(exc), "status": exc.code}
    data = json.loads(body)
    out = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "x_requests_used": used,
        "x_requests_remaining": remaining,
        "x_requests_last_cost": last,
        "data": data,
    }
    cache.write_text(json.dumps(out, indent=2), encoding="utf-8")
    time.sleep(THROTTLE_SEC)
    return out


# Kalshi YES price snapshots for live probe markets, scraped manually from
# Kalshi public market pages on 2026-05-24 (cached in state.json doesn't
# carry yes_price for resting orders; the v3 probe inventory has T-35d
# VWAPs which we use as proxy when needed). For this probe we pull live
# Kalshi prices via the /markets endpoint.


_KALSHI_CLIENT = None


def _get_kalshi_client():
    global _KALSHI_CLIENT
    if _KALSHI_CLIENT is None:
        from kalshi_bot.config import load_settings
        from kalshi_bot.data.kalshi_client import KalshiClient
        settings = load_settings()
        _KALSHI_CLIENT = KalshiClient(settings)
    return _KALSHI_CLIENT


def kalshi_yes_price(ticker: str) -> float | None:
    """Hit Kalshi /markets/{ticker} for the current YES last price.

    Reads-only; uses kalshi_client which signs requests using the read
    PEM in .env.
    """
    try:
        client = _get_kalshi_client()
        resp = client.get(f"/markets/{ticker}")
        m = resp.get("market", {})
        # Kalshi response uses *_dollars fields (e.g. yes_bid_dollars=0.71).
        # Cent fields exist too but the *_dollars are the canonical floats.
        last = m.get("last_price_dollars")
        yes_bid = m.get("yes_bid_dollars")
        yes_ask = m.get("yes_ask_dollars")
        # Prefer mid of bid/ask if both available; fall back to last.
        try:
            if yes_bid not in (None, "", 0) and yes_ask not in (None, "", 0):
                return (float(yes_bid) + float(yes_ask)) / 2.0
        except (TypeError, ValueError):
            pass
        try:
            if last not in (None, "", 0):
                return float(last)
        except (TypeError, ValueError):
            pass
        return None
    except Exception as exc:
        print(f"  kalshi_yes_price({ticker}) failed: {exc}")
        return None


def main() -> None:
    out: dict = {
        "live": [],
        "historical": [],
    }

    # ---- LIVE PROBE ----
    # Sport keys to pull (one call per sport_key = 1 credit each)
    live_targets = [
        ("soccer_fifa_world_cup", "h2h", "us"),
        ("mma_mixed_martial_arts", "h2h", "us"),
        ("boxing_boxing", "h2h", "us"),
        ("americanfootball_nfl", "h2h", "us"),
    ]
    live_responses = {}
    for sport_key, mkts, regs in live_targets:
        print(f"[LIVE] fetching {sport_key} {mkts} {regs}...")
        live_responses[sport_key] = fetch_live_odds(sport_key, mkts, regs)
        used = live_responses[sport_key].get("x_requests_used")
        remaining = live_responses[sport_key].get("x_requests_remaining")
        cost = live_responses[sport_key].get("x_requests_last_cost")
        print(f"  used={used} remaining={remaining} last_cost={cost}")

    # v1 currently-resting MATCH-class tickers with team mapping
    # (from data/live_trades/state.json + manual mapping)
    live_kalshi_targets = [
        # (kalshi_ticker, sport_key, home_or_away_team_id, kalshi_yes_outcome_label, description)
        ("KXWCGAME-26JUN23ENGGHA-ENG", "soccer_fifa_world_cup", "England", "England", "England vs Ghana 2026-06-23, betting ENG wins"),
        ("KXWCGAME-26JUN24SCOBRA-BRA", "soccer_fifa_world_cup", "Brazil", "Brazil", "Scotland vs Brazil 2026-06-24, betting BRA wins"),
        ("KXWCGAME-26JUN17AUTJOR-AUT", "soccer_fifa_world_cup", "Austria", "Austria", "Austria vs Jordan 2026-06-17, betting AUT wins"),
        ("KXUFCFIGHT-26JUL11MCGHOL-HOL", "mma_mixed_martial_arts", "Max Holloway", "Max Holloway", "UFC McGregor vs Holloway 2026-07-11, betting HOL wins"),
        ("KXUFCFIGHT-26JUN14HOKLEW-HOK", "mma_mixed_martial_arts", "Dan Hooker", "Dan Hooker", "UFC Hooker vs Lewis 2026-06-14, betting HOK wins"),
        ("KXBOXING-26SEP12CALVARMBILLI-CALVAR", "boxing_boxing", "Saul Alvarez", "Saul Alvarez", "Boxing Canelo vs Mbilli 2026-09-12, betting CALVAR wins"),
        ("KXNFLGAME-26SEP13CLEJAC-JAC", "americanfootball_nfl", "Jacksonville Jaguars", "Jacksonville Jaguars", "NFL Browns @ Jaguars 2026-09-13, betting JAC wins"),
    ]
    for ticker, sport_key, target_team, kalshi_yes_label, descr in live_kalshi_targets:
        resp = live_responses.get(sport_key, {})
        events = resp.get("events", [])
        match = None
        for ev in events:
            if target_team in (ev.get("home_team", ""), ev.get("away_team", "")):
                # Match by both teams when possible: prefer first event found
                # containing the target. Soccer 3-way has draw; we pull
                # the outcome by team name.
                match = ev
                break
        row = {
            "ticker": ticker,
            "description": descr,
            "sport_key": sport_key,
            "target_team": target_team,
            "kalshi_yes_outcome": kalshi_yes_label,
        }
        if match is None:
            row["sportsbook_status"] = "no_match_found"
        else:
            row["sportsbook_event_id"] = match.get("id", "")
            row["sportsbook_commence_time"] = match.get("commence_time", "")
            row["sportsbook_home_team"] = match.get("home_team", "")
            row["sportsbook_away_team"] = match.get("away_team", "")
            # Pull h2h prices from each bookmaker
            bookmakers = match.get("bookmakers", [])
            target_implied = []
            for bm in bookmakers:
                for market in bm.get("markets", []):
                    if market.get("key") != "h2h":
                        continue
                    outcomes = market.get("outcomes", [])
                    # Build target probability after de-vigging
                    if len(outcomes) == 3:
                        # 3-way soccer market: outcomes are home / away / draw
                        ps = []
                        names = []
                        for o in outcomes:
                            ps.append(implied_from_decimal(float(o.get("price", 0) or 0)))
                            names.append(o.get("name", ""))
                        if not all(p > 0 for p in ps):
                            continue
                        ps = devig_3way(*ps)
                        for nm, p in zip(names, ps, strict=False):
                            if nm == target_team:
                                target_implied.append({"bookmaker": bm.get("key", ""), "p": p})
                                break
                    elif len(outcomes) == 2:
                        ps = []
                        names = []
                        for o in outcomes:
                            ps.append(implied_from_decimal(float(o.get("price", 0) or 0)))
                            names.append(o.get("name", ""))
                        if not all(p > 0 for p in ps):
                            continue
                        ps = devig_2way(*ps)
                        for nm, p in zip(names, ps, strict=False):
                            if nm == target_team:
                                target_implied.append({"bookmaker": bm.get("key", ""), "p": p})
                                break
            row["sportsbook_implied_per_book"] = target_implied
            if target_implied:
                ps_vals = [t["p"] for t in target_implied]
                row["sportsbook_implied_median"] = float(pd.Series(ps_vals).median())
                row["sportsbook_implied_max"] = float(max(ps_vals))
                row["sportsbook_implied_min"] = float(min(ps_vals))
                row["sportsbook_n_books"] = len(ps_vals)
            # Kalshi live price
            kp = kalshi_yes_price(ticker)
            row["kalshi_yes_price"] = kp
            if kp is not None and row.get("sportsbook_implied_median") is not None:
                row["divergence_cents"] = round(
                    (kp - row["sportsbook_implied_median"]) * 100, 2
                )
        out["live"].append(row)

    # ---- HISTORICAL PROBE ----
    # FREE TIER FINDING (corrects V4-D Section 3.1): historical endpoints
    # return HTTP 401 with body error_code=HISTORICAL_UNAVAILABLE_ON_FREE_USAGE_PLAN.
    # Historical access requires the $30/mo 20K-credit tier or above.
    # We document this and SKIP the historical probe. Below is preserved
    # for reproducibility once the paid tier is activated.
    print("\n[HISTORICAL] SKIPPED: free tier does not support historical odds.")
    print("  See data/v5/odds_api_historical_cache/*.json for the 401 responses.")
    do_historical = os.environ.get("V5_RUN_HISTORICAL", "0") == "1"
    if not do_historical:
        out["historical"] = [{"skipped": True, "reason": "free_tier_blocks_historical_endpoint"}]
        out["historical_rows"] = []
        # Save outputs
        (OUT_DIR / "signal_direction_probe.json").write_text(
            json.dumps(out, indent=2, default=str), encoding="utf-8"
        )
        # Summary table
        live_df = pd.DataFrame(out["live"])
        print("\n=== LIVE PROBE SUMMARY ===")
        if not live_df.empty:
            cols = [c for c in ["ticker", "target_team", "kalshi_yes_price",
                                 "sportsbook_implied_median", "sportsbook_n_books",
                                 "divergence_cents"] if c in live_df.columns]
            print(live_df[cols].to_string(index=False))
            if "divergence_cents" in live_df.columns:
                valid_live = live_df.dropna(subset=["divergence_cents"])
                if not valid_live.empty:
                    print(f"\nLive mean divergence (Kalshi - Sportsbook): "
                          f"{valid_live['divergence_cents'].mean():.2f} cents (n={len(valid_live)})")
                    print(f"Live median divergence: {valid_live['divergence_cents'].median():.2f} cents")
                    print(f"Direction: Kalshi {'>' if valid_live['divergence_cents'].mean()>0 else '<'} sportsbook on average")
        return  # skip historical-derived rows
    # Use 5 KXNBAWINS-25 markets resolved on 2026-04-13. Need historical
    # outrights from basketball_nba_championship_winner at T-7d = 2026-04-06.
    # This is a SINGLE snapshot call covering all teams = 10 credits.
    # We get 5 mappings out of one call. To honor the spec of "5 historical
    # calls", we'll pull 5 different timepoints to get a sense of stability.
    inv = pd.read_parquet(ROOT / "data/v3/probe_inventory_all_markets.parquet")
    inv["series_prefix"] = inv["ticker"].str.split("-").str[0]
    # Eligible-narrow + resolved + close in [2026-04-01, 2026-04-30]
    win_totals_recent = inv[
        (inv["series_prefix"] == "KXNBAWINS")
        & (inv["eligible_narrow"])
        & (inv["close_time"] >= pd.Timestamp("2026-04-01", tz="UTC"))
        & (inv["close_time"] <= pd.Timestamp("2026-04-30", tz="UTC"))
        & (inv["result"].isin(["yes", "no"]))
    ].copy()
    print(f"\nHistorical universe (KXNBAWINS-25 eligible): {len(win_totals_recent)}")
    # Pick 5 representative tickers across team strength bands
    picks = win_totals_recent.sort_values("vwap_t35_narrow").head(5)
    print("Picks:")
    print(picks[["ticker", "vwap_t35_narrow", "result", "close_time"]].to_string(index=False))

    # Strategy for historical: pull ONE outright snapshot at T-7d before
    # NBA finals = 2026-04-06 (Kalshi T-35d snapshot was ~2026-03-09 for an
    # April 13 close, but we use T-7d before resolution to give a cleaner
    # signal-direction proxy). This costs 10 credits.
    # Then map each of 5 Kalshi tickers to a derived sportsbook signal.
    # The mapping is: P(championship_winner=team) per the-odds-api gives
    # the sportsbook's implied probability that this team wins the title;
    # via monotonicity, P(team wins championship) <= P(team wins X+ games)
    # for any X less than the threshold for which championship implies the
    # team makes the playoffs. This is a directional LOWER bound on the
    # Kalshi T-prob.
    # To honor the "5 historical calls" budget, we'll pull at T-30d,
    # T-21d, T-14d, T-7d, T-1d to see how the implied changes near close.
    base_close = pd.Timestamp("2026-04-13T17:00:00Z")
    historical_dates = [
        base_close - pd.Timedelta(days=30),
        base_close - pd.Timedelta(days=21),
        base_close - pd.Timedelta(days=14),
        base_close - pd.Timedelta(days=7),
        base_close - pd.Timedelta(days=1),
    ]
    hist_results = []
    for d in historical_dates:
        iso = d.strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"\n[HISTORICAL] basketball_nba_championship_winner outrights @ {iso}")
        try:
            resp = fetch_historical_odds(
                "basketball_nba_championship_winner",
                iso,
                markets="outrights",
                regions="us",
            )
            used = resp.get("x_requests_used")
            remaining = resp.get("x_requests_remaining")
            cost = resp.get("x_requests_last_cost")
            print(f"  used={used} remaining={remaining} last_cost={cost}")
        except Exception as exc:
            print(f"  FAILED: {exc}")
            resp = {"error": str(exc)}
        hist_results.append({"date": iso, "response": resp})
    out["historical"] = hist_results

    # Map: extract implied championship probabilities per team across the 5
    # snapshots, then attach to the 5 Kalshi NBAWINS-25 tickers.
    team_implied: dict[str, dict[str, float]] = {}
    for hr in hist_results:
        snap_iso = hr["date"]
        resp = hr["response"]
        # Historical response shape: {"timestamp": ..., "previous_timestamp", "next_timestamp", "data": {...}}
        # where data contains the odds. Drill in.
        data = resp.get("data", {})
        if isinstance(data, dict):
            inner = data.get("data", data)
        else:
            inner = data
        # The outrights for a *_winner sport key looks like a single event
        # with multiple outcomes (teams). If 'inner' is a list, take first.
        events_blob = inner
        if isinstance(events_blob, list):
            events_blob = events_blob[0] if events_blob else {}
        bookmakers = events_blob.get("bookmakers", []) if isinstance(events_blob, dict) else []
        team_probs_all_books: dict[str, list[float]] = {}
        for bm in bookmakers:
            for mk in bm.get("markets", []):
                if mk.get("key") not in ("outrights", "championship_winner"):
                    continue
                outcomes = mk.get("outcomes", [])
                # De-vig by normalizing sum to 1 across all teams
                ps = []
                names = []
                for o in outcomes:
                    p = implied_from_decimal(float(o.get("price", 0) or 0))
                    ps.append(p)
                    names.append(o.get("name", ""))
                s = sum(ps)
                if s <= 0:
                    continue
                for nm, p in zip(names, ps, strict=False):
                    team_probs_all_books.setdefault(nm, []).append(p / s)
        # Median across books
        team_median = {nm: float(pd.Series(ps).median()) for nm, ps in team_probs_all_books.items()}
        for nm, p in team_median.items():
            team_implied.setdefault(nm, {})[snap_iso] = p

    # Save team_implied
    (OUT_DIR / "odds_api_historical_nba_team_implied.json").write_text(
        json.dumps(team_implied, indent=2), encoding="utf-8"
    )

    # Map team codes -> full team names
    team_code_to_name = {
        "ATL": "Atlanta Hawks", "BOS": "Boston Celtics", "BKN": "Brooklyn Nets",
        "CHA": "Charlotte Hornets", "CHI": "Chicago Bulls", "CLE": "Cleveland Cavaliers",
        "DAL": "Dallas Mavericks", "DEN": "Denver Nuggets", "DET": "Detroit Pistons",
        "GSW": "Golden State Warriors", "HOU": "Houston Rockets", "IND": "Indiana Pacers",
        "LAC": "LA Clippers", "LAL": "Los Angeles Lakers", "MEM": "Memphis Grizzlies",
        "MIA": "Miami Heat", "MIL": "Milwaukee Bucks", "MIN": "Minnesota Timberwolves",
        "NOP": "New Orleans Pelicans", "NYK": "New York Knicks", "OKC": "Oklahoma City Thunder",
        "ORL": "Orlando Magic", "PHI": "Philadelphia 76ers", "PHX": "Phoenix Suns",
        "POR": "Portland Trail Blazers", "SAC": "Sacramento Kings", "SAS": "San Antonio Spurs",
        "TOR": "Toronto Raptors", "UTA": "Utah Jazz", "WAS": "Washington Wizards",
    }
    out["historical_team_implied"] = team_implied

    # Build the historical Kalshi -> sportsbook divergence rows
    hist_rows = []
    for _, r in picks.iterrows():
        tk = r["ticker"]
        # tk like "KXNBAWINS-SAS-25-T55"
        parts = tk.split("-")
        team_code = parts[1] if len(parts) > 1 else ""
        threshold = parts[-1] if len(parts) > 3 else ""
        team_name = team_code_to_name.get(team_code, team_code)
        # Find the T-7d snapshot for this team. Use the snapshot closest
        # to 2026-04-06.
        snap_t7_key = next((k for k in team_implied.get(team_name, {}) if "2026-04-06" in k), None)
        sportsbook_implied = None
        if snap_t7_key:
            sportsbook_implied = team_implied[team_name][snap_t7_key]
        hist_rows.append({
            "ticker": tk,
            "team_code": team_code,
            "team_name": team_name,
            "kalshi_threshold": threshold,
            "kalshi_t35_vwap_narrow": float(r["vwap_t35_narrow"]) if pd.notna(r["vwap_t35_narrow"]) else None,
            "kalshi_t35_vwap_wide": float(r["vwap_t35_wide"]) if pd.notna(r["vwap_t35_wide"]) else None,
            "result": r["result"],
            "close_time": str(r["close_time"]),
            "sportsbook_championship_implied_t7d": sportsbook_implied,
            "divergence_cents_kalshi_minus_book_championship": (
                round((float(r["vwap_t35_narrow"]) - sportsbook_implied) * 100, 2)
                if sportsbook_implied is not None and pd.notna(r["vwap_t35_narrow"])
                else None
            ),
        })
    out["historical_rows"] = hist_rows

    # Save outputs
    (OUT_DIR / "signal_direction_probe.json").write_text(
        json.dumps(out, indent=2, default=str), encoding="utf-8"
    )

    # Summary table
    live_df = pd.DataFrame(out["live"])
    print("\n=== LIVE PROBE SUMMARY ===")
    if not live_df.empty:
        print(live_df[[
            "ticker", "target_team", "kalshi_yes_price",
            "sportsbook_implied_median", "sportsbook_n_books",
            "divergence_cents",
        ]].to_string(index=False))
        valid_live = live_df.dropna(subset=["divergence_cents"]) if "divergence_cents" in live_df.columns else live_df.iloc[0:0]
        if not valid_live.empty:
            print(f"\nLive mean divergence (Kalshi - Sportsbook): {valid_live['divergence_cents'].mean():.2f} cents")
            print(f"Live median divergence: {valid_live['divergence_cents'].median():.2f} cents")
            print(f"n={len(valid_live)}")

    print("\n=== HISTORICAL PROBE SUMMARY ===")
    hist_df = pd.DataFrame(out["historical_rows"])
    if not hist_df.empty:
        print(hist_df.to_string(index=False))
        valid_hist = hist_df.dropna(subset=["divergence_cents_kalshi_minus_book_championship"])
        if not valid_hist.empty:
            print(f"\nHistorical mean divergence (Kalshi T-35d VWAP - book championship-implied T-7d): {valid_hist['divergence_cents_kalshi_minus_book_championship'].mean():.2f} cents")


if __name__ == "__main__":
    main()
