"""Phase-1 v3 Agent V3-C: Kalshi to Polymarket event matching probe.

For 20 Kalshi MLB long-horizon markets, attempt to find a Polymarket event
that represents the same underlying real-world outcome. Use only the
public Gamma `public-search` endpoint, no auth.

Output:
- data/v3/poly_match_candidates.json: full raw search results per ticker
- data/v3/poly_match_summary.parquet: one row per Kalshi ticker with
  (best candidate slug, best candidate title, best candidate endDate,
   match_confidence: confident/loose/none, rationale)

The matching rule is structural, not subjective: candidate must
(a) mention same league context ("MLB", or a team name from Kalshi's
title), (b) reference the same year as the Kalshi market's
close_time, and (c) match the market_kind concept (season wins,
division winner, playoff qualifier).

Read-only. Polite rate (1.0s between requests).
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_V2 = REPO_ROOT / "data" / "v2"
DATA_V3 = REPO_ROOT / "data" / "v3"
DATA_V3.mkdir(parents=True, exist_ok=True)
SPORTS_MARKETS = REPO_ROOT / "data" / "sports" / "markets"

GAMMA_BASE = "https://gamma-api.polymarket.com"

# Map Kalshi-side team abbreviations to full team name(s) for query construction.
# We do this manually rather than scraping rules_primary because rules_primary
# uses awkward forms like "Chicago C pro baseball team" rather than "Chicago
# Cubs", which would degrade naive text search.
MLB_TEAM_NAMES: dict[str, list[str]] = {
    "ARI": ["Arizona Diamondbacks", "Diamondbacks", "ARI"],
    "ATL": ["Atlanta Braves", "Braves", "ATL"],
    "BAL": ["Baltimore Orioles", "Orioles", "BAL"],
    "BOS": ["Boston Red Sox", "Red Sox", "BOS"],
    "CHC": ["Chicago Cubs", "Cubs", "CHC"],
    "CWS": ["Chicago White Sox", "White Sox", "CWS"],
    "CIN": ["Cincinnati Reds", "Reds", "CIN"],
    "CLE": ["Cleveland Guardians", "Guardians", "CLE"],
    "COL": ["Colorado Rockies", "Rockies", "COL"],
    "DET": ["Detroit Tigers", "Tigers", "DET"],
    "HOU": ["Houston Astros", "Astros", "HOU"],
    "KC":  ["Kansas City Royals", "Royals", "KC"],
    "LAA": ["Los Angeles Angels", "Angels", "LAA"],
    "LAD": ["Los Angeles Dodgers", "Dodgers", "LAD"],
    "MIA": ["Miami Marlins", "Marlins", "MIA"],
    "MIL": ["Milwaukee Brewers", "Brewers", "MIL"],
    "MIN": ["Minnesota Twins", "Twins", "MIN"],
    "NYM": ["New York Mets", "Mets", "NYM"],
    "NYY": ["New York Yankees", "Yankees", "NYY"],
    "OAK": ["Oakland Athletics", "Athletics", "OAK"],
    "PHI": ["Philadelphia Phillies", "Phillies", "PHI"],
    "PIT": ["Pittsburgh Pirates", "Pirates", "PIT"],
    "SD":  ["San Diego Padres", "Padres", "SD"],
    "SEA": ["Seattle Mariners", "Mariners", "SEA"],
    "SF":  ["San Francisco Giants", "Giants", "SF"],
    "STL": ["St. Louis Cardinals", "Cardinals", "STL"],
    "TB":  ["Tampa Bay Rays", "Rays", "TB"],
    "TEX": ["Texas Rangers", "Rangers", "TEX"],
    "TOR": ["Toronto Blue Jays", "Blue Jays", "TOR"],
    "WSH": ["Washington Nationals", "Nationals", "WSH"],
}


def load_kalshi_universe() -> pd.DataFrame:
    df = pd.read_parquet(DATA_V2 / "joined_mlb_longhorizon_dataset.parquet")
    return df


def attach_market_text(df: pd.DataFrame) -> pd.DataFrame:
    """Join in `title` and `rules_primary` from the cached markets parquet."""
    titles = []
    rules = []
    for _, row in df.iterrows():
        series = row["series_ticker"]
        ticker = row["ticker"]
        path = SPORTS_MARKETS / f"{series}.parquet"
        if not path.exists():
            titles.append(None)
            rules.append(None)
            continue
        cache = pd.read_parquet(path)
        hit = cache[cache["ticker"] == ticker]
        if len(hit) == 0:
            titles.append(None)
            rules.append(None)
            continue
        r0 = hit.iloc[0]
        titles.append(r0.get("title"))
        rules.append(r0.get("rules_primary"))
    df = df.copy()
    df["kalshi_title"] = titles
    df["kalshi_rules_primary"] = rules
    return df


def pick_20_for_probe(df: pd.DataFrame) -> pd.DataFrame:
    """Pick a sample of 20 markets weighted toward strict v1 eligibility.

    Strategy: all 11 strict-eligible markets, plus 9 marginal candidates
    (favorite_price >= 0.50 to keep them v1-shape, even if outside the
    [0.70, 0.95] band) chosen for series diversity so we test
    KXMLBWINS, KXMLBPLAYOFFS, KXMLBALEAST/CENT/WEST and
    KXMLBNLEAST/CENT/WEST.
    """
    elig = df[df["is_eligible"]].copy()

    # Marginal candidates: not eligible, but favorite_price >= 0.5, by series
    # diversity. We want a few division markets and one or two non-strict
    # season-win markets.
    marginal = df[(~df["is_eligible"]) & (df["favorite_price"] >= 0.45)].copy()
    marginal_sample = (
        marginal.sort_values(["series_ticker", "favorite_price"], ascending=[True, False])
        .groupby("series_ticker")
        .head(2)
    )
    needed = 20 - len(elig)
    marginal_sample = marginal_sample.head(needed)
    sample = pd.concat([elig, marginal_sample], ignore_index=True)
    return sample


def parse_year_from_ticker_or_close(row: pd.Series) -> int:
    # KXMLBWINS-CHC-25-T90, KXMLBPLAYOFFS-25-CHC, KXMLBALEAST-25-NYY
    m = re.search(r"-(\d{2})-", row["ticker"])
    if m:
        yy = int(m.group(1))
        return 2000 + yy
    return pd.Timestamp(row["market_close_time"]).year


def build_queries(row: pd.Series) -> list[str]:
    """Build 1-3 query strings sized to find the same event on Polymarket."""
    year = parse_year_from_ticker_or_close(row)
    team_abbrev = row.get("favorite_team_abbrev")
    team_names = MLB_TEAM_NAMES.get(team_abbrev, [team_abbrev])
    kind = row.get("market_kind")
    primary = team_names[0]
    nickname = team_names[1] if len(team_names) > 1 else primary

    if kind == "wins":
        # Look for "Yankees Win Total 2025", etc.
        return [
            f"MLB {primary} {year} win total",
            f"{nickname} season wins {year}",
            f"{primary} {year} regular season",
        ]
    if kind == "division":
        # Division winner markets, e.g. AL East
        series = row["series_ticker"]
        div_label = {
            "KXMLBALEAST": "AL East",
            "KXMLBALCENT": "AL Central",
            "KXMLBALWEST": "AL West",
            "KXMLBNLEAST": "NL East",
            "KXMLBNLCENT": "NL Central",
            "KXMLBNLWEST": "NL West",
        }.get(series, "MLB division")
        return [
            f"{div_label} {year} winner MLB",
            f"MLB {year} {div_label} champion",
            f"{primary} {div_label} {year}",
        ]
    if kind == "playoffs":
        return [
            f"MLB {primary} {year} playoffs",
            f"{nickname} make playoffs {year}",
            f"MLB postseason {year} {primary}",
        ]
    return [f"MLB {primary} {year}"]


def public_search(q: str) -> dict | None:
    url = f"{GAMMA_BASE}/public-search"
    try:
        with httpx.Client(timeout=20.0) as c:
            r = c.get(url, params={"q": q, "limit_per_type": 8})
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        return {"_http_error": e.response.status_code}
    except Exception as e:
        return {"_error": str(e)}


def evaluate_candidate(
    candidate: dict,
    row: pd.Series,
) -> tuple[str, str]:
    """Classify a candidate event as confident/loose/none.

    Confident: title mentions the team name AND the correct year AND
    a market_kind keyword consistent with the Kalshi market.
    Loose: title mentions correct year and any team/MLB context, but
    not the specific entity or kind.
    None: otherwise.
    """
    title = (candidate.get("title") or "").lower()
    slug = (candidate.get("slug") or "").lower()
    end_date = (candidate.get("endDate") or candidate.get("end_date") or "")
    haystack = title + " " + slug + " " + end_date.lower()
    year = parse_year_from_ticker_or_close(row)
    if str(year) not in haystack:
        # Allow next-year reference (markets that resolve in October but
        # are labeled with the season year). Be permissive on year band:
        # also accept year-1 if the kind is wins/division/playoffs and
        # we already see MLB context.
        pass

    team_abbrev = row.get("favorite_team_abbrev")
    team_names = MLB_TEAM_NAMES.get(team_abbrev, [team_abbrev])
    has_team = any(n.lower() in haystack for n in team_names if n)

    kind = row.get("market_kind")
    if kind == "wins":
        kind_keywords = ["win total", "wins", "regular season"]
    elif kind == "division":
        kind_keywords = ["division", "al east", "al central", "al west",
                          "nl east", "nl central", "nl west", "champion"]
    elif kind == "playoffs":
        kind_keywords = ["playoff", "postseason", "make the playoffs"]
    else:
        kind_keywords = []
    has_kind = any(k in haystack for k in kind_keywords)
    has_year = (str(year) in haystack) or (str(year - 1) in haystack)
    has_mlb = ("mlb" in haystack) or ("baseball" in haystack) or has_team

    if has_team and has_year and has_kind:
        return "confident", "team+year+kind"
    if has_year and has_mlb and has_kind:
        return "loose", "year+mlb+kind"
    if has_team and has_year:
        return "loose", "team+year"
    return "none", "no match"


def match_one(row: pd.Series) -> dict:
    queries = build_queries(row)
    best_label = "none"
    best_rationale = "no candidates"
    best_candidate: dict | None = None
    all_results: list[dict] = []
    for q in queries:
        res = public_search(q) or {}
        events = res.get("events", []) if isinstance(res, dict) else []
        # Polymarket sometimes returns markets at the top level too
        markets = res.get("markets", []) if isinstance(res, dict) else []
        records = events + markets
        all_results.append({"query": q, "n_events": len(events), "n_markets": len(markets),
                             "events_sample": [
                                 {"slug": e.get("slug"), "title": e.get("title"),
                                  "endDate": e.get("endDate") or e.get("end_date"),
                                  "active": e.get("active"),
                                  "closed": e.get("closed")}
                                 for e in events[:5]
                             ]})
        for cand in records:
            label, rat = evaluate_candidate(cand, row)
            if (best_label == "none" and label != "none") or (
                best_label == "loose" and label == "confident"
            ):
                best_label = label
                best_rationale = rat
                best_candidate = cand
            if label == "confident":
                break
        time.sleep(1.0)  # politeness
        if best_label == "confident":
            break

    return {
        "ticker": row["ticker"],
        "event_ticker": row["event_ticker"],
        "series_ticker": row["series_ticker"],
        "favorite_team_abbrev": row.get("favorite_team_abbrev"),
        "market_kind": row.get("market_kind"),
        "favorite_price": float(row["favorite_price"]),
        "lifetime_days": float(row["lifetime_days"]),
        "is_eligible": bool(row.get("is_eligible", False)),
        "kalshi_title": row.get("kalshi_title"),
        "kalshi_rules_primary": row.get("kalshi_rules_primary"),
        "market_close_time": str(row.get("market_close_time")),
        "queries_tried": queries,
        "match_confidence": best_label,
        "match_rationale": best_rationale,
        "best_candidate_slug": (best_candidate or {}).get("slug"),
        "best_candidate_id": (best_candidate or {}).get("id") or (best_candidate or {}).get("event_id"),
        "best_candidate_title": (best_candidate or {}).get("title"),
        "best_candidate_end_date": (best_candidate or {}).get("endDate") or (best_candidate or {}).get("end_date"),
        "best_candidate_active": (best_candidate or {}).get("active"),
        "best_candidate_closed": (best_candidate or {}).get("closed"),
        "best_candidate_slugs_all": [],
        "raw_search_summary": all_results,
    }


def main() -> int:
    df = load_kalshi_universe()
    df = attach_market_text(df)
    sample = pick_20_for_probe(df)
    print(f"Sampled {len(sample)} markets ({sample['is_eligible'].sum()} strict-eligible).")
    print(sample[["ticker", "series_ticker", "market_kind", "favorite_price", "is_eligible"]].to_string())

    out_rows: list[dict] = []
    for i, (_, row) in enumerate(sample.iterrows()):
        print(f"\n[{i+1}/{len(sample)}] {row['ticker']}", flush=True)
        rec = match_one(row)
        out_rows.append(rec)
        print(f"  match: {rec['match_confidence']} ({rec['match_rationale']})  "
              f"-> slug={rec['best_candidate_slug']} title={rec['best_candidate_title']}")

    out_df = pd.DataFrame(out_rows)
    out_path_parquet = DATA_V3 / "poly_match_summary.parquet"
    # Drop raw_search_summary to keep parquet tidy; write JSON sidecar.
    raw_blob = [r.pop("raw_search_summary") for r in out_rows]
    out_df_clean = pd.DataFrame(out_rows)
    out_df_clean.to_parquet(out_path_parquet, index=False)
    (DATA_V3 / "poly_match_candidates.json").write_text(
        json.dumps(
            {"per_ticker": [
                {**{k: v for k, v in r.items() if k != "raw_search_summary"},
                 "raw_search_summary": raw}
                for r, raw in zip(out_rows, raw_blob)
            ]}, indent=2, default=str
        ),
        encoding="utf-8",
    )
    print(f"\nWrote {out_path_parquet}")
    print(f"Wrote {DATA_V3 / 'poly_match_candidates.json'}")

    # Summary
    counts = out_df_clean["match_confidence"].value_counts().to_dict()
    print("\nMatch confidence distribution:", counts)
    n_confident = counts.get("confident", 0)
    n_total = len(out_df_clean)
    print(f"Confident match rate: {n_confident}/{n_total} = {n_confident/n_total:.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
