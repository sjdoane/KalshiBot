"""Phase 1 / Agent V4-A: classify v1 live orders with manual-audit-grade labels.

Reads the audit results from data/v4/live_orders_poly_audit.json and the
per-series probe caches, then applies a stricter classification rule based
on inspection findings:

  CONFIRMED       - Polymarket has the exact counterpart, active+open, mid available
  PARTIAL         - Polymarket has the same event-class but the specific market
                    (threshold, side, player) is not on Polymarket
  EVENT_FUTURE    - Polymarket will likely list this once the season nears
                    (NFL 2026-27, NCAAF 2026, etc.) but doesn't yet
  NO MATCH        - Polymarket structurally doesn't list this kind of market

Outputs data/v4/live_orders_classified.parquet with the binding labels.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_V4 = REPO_ROOT / "data" / "v4"

AUDIT = DATA_V4 / "live_orders_poly_audit.json"
OUT = DATA_V4 / "live_orders_classified.parquet"

# Manual classification per ticker based on the audit candidates inspected above.
# Each entry: (status, poly_event_slug_or_kind, note)
# Status legend:
#   CONFIRMED        - Polymarket has exact counterpart now
#   PARTIAL          - same event, different threshold/side on Polymarket
#   EVENT_FUTURE     - Polymarket should list it later, not yet
#   NO MATCH         - structural absence
MANUAL_LABELS: dict[str, tuple[str, str, str]] = {
    # World Cup matches: confirmed via deterministic slug
    "KXWCGAME-26JUN23ENGGHA-ENG": ("CONFIRMED", "fifwc-eng-gha-2026-06-23-eng", "deterministic slug match, mid available"),
    "KXWCGAME-26JUN24SCOBRA-BRA": ("CONFIRMED", "fifwc-sco-bra-2026-06-24-bra", "deterministic slug match"),
    "KXWCGAME-26JUN17AUTJOR-AUT": ("CONFIRMED", "fifwc-aut-jor-2026-06-17-aut", "deterministic slug match"),
    # World Cup squad: event matches but per-player lookup is non-trivial
    "KXWCSQUAD-26ESP-BIGL": ("PARTIAL", "2026-fifa-world-cup-player-to-make-spain-squad",
                              "event found; specific player ('BIGL' = Lamine Yamal?) needs lookup table"),
    # World Cup stage-of-elim: no current Polymarket equivalent for Cape Verde group-stage
    "KXWCSTAGEOFELIM-26CPV-GS": ("PARTIAL", None,
                                  "Polymarket has FIFA WC Group A-L Winner markets, but no exact 'CPV gets eliminated in group stage' market. Closest is implied: 1 - P(CPV wins group)."),
    # NFL Raiders Week 1 QB: confirmed!
    "KXSTARTINGQBWEEK1-W1-26SEP15-LV-KCOU": ("CONFIRMED", "pro-football-raiders-week-1-starting-qb",
                                              "active+open; specific Kalshi market 'Kenny Pickett or Aidan O'Connell' = ('KCOU') maps to Polymarket alternatives"),
    # UFC McGregor vs Holloway July 2026: no specific fight market listed yet
    "KXUFCFIGHT-26JUL11MCGHOL-HOL": ("EVENT_FUTURE", None,
                                      "UFC has 50 active events but no McGregor-Holloway July 2026 specific market"),
    # UFC Holloway vs Lewis June 2026: same
    "KXUFCFIGHT-26JUN14HOKLEW-HOK": ("EVENT_FUTURE", None,
                                      "no specific HOK-LEW June 2026 fight on Polymarket; closest is generic UFC rankings"),
    # Boxing Canelo vs Mbilli Sept 12 2026: no Polymarket fight market
    "KXBOXING-26SEP12CALVARMBILLI-CALVAR": ("EVENT_FUTURE", None,
                                             "Polymarket has 4 active boxing events but none for Canelo-Mbilli Sept 12 2026"),
    # F1 Singapore 2026: 2025 race resolved; 2026 race not yet listed
    "KXFOMEN-26-SIN": ("EVENT_FUTURE", None,
                       "Polymarket lists F1 driver champion etc.; 2026 Singapore GP-specific race winner market not yet listed"),
    # NBA playoff wins counts: structural absence
    "KXNBAPLAYOFFWINS-26SAS-10": ("NO MATCH", None,
                                   "Polymarket does not list 'team wins N games in playoffs' threshold markets"),
    "KXNBAPLAYOFFWINS-26OKC-15": ("NO MATCH", None,
                                   "Polymarket does not list 'team wins N games in playoffs' threshold markets"),
    # CS2 specific event: not listed on Polymarket
    "KXCS2-ASIA26-FAL": ("EVENT_FUTURE", None,
                          "Polymarket CS2 tag has 9 active events; no specific ASIA26 Falcons market"),
    # NFL Sep 13 2026 game: 2026-27 season games not yet listed by Polymarket
    "KXNFLGAME-26SEP13CLEJAC-JAC": ("EVENT_FUTURE", None,
                                     "Polymarket has 47 active NFL events but doesn't yet list Sep 13 2026 Browns-Jaguars (season opens Sep)"),
    # NFL 2026-27 playoffs: not yet listed (current season 2025-26 finishes Feb)
    "KXNFLPLAYOFF-27-SEA": ("EVENT_FUTURE", None,
                             "Polymarket has 2025-26 NFL playoff markets; 2026-27 season Seahawks-playoff market not yet listed"),
    # MLB win totals 2026: Polymarket HAS the event but at different threshold
    "KXMLBWINS-HOU-26-T70": ("PARTIAL", "mlb-2026-regular-season-win-totals",
                              "active+open event exists; Polymarket sets ONE threshold per team (e.g. HOU at 85.5), Kalshi T70 = 70 wins -> different threshold"),
    "KXMLBWINS-ATH-26-T75": ("PARTIAL", "mlb-2026-regular-season-win-totals",
                              "active+open event exists; Polymarket sets ONE threshold per team, Kalshi T75 may not equal Polymarket's"),
    "KXMLBWINS-KC-26-T70": ("PARTIAL", "mlb-2026-regular-season-win-totals",
                             "active+open event exists; threshold mismatch likely"),
    # NCAA-FB 2026 playoff Georgia: 2026 season not yet listed by Polymarket
    "KXNCAAFPLAYOFF-26-UGA": ("EVENT_FUTURE", None,
                               "Polymarket cfb tag has only 1 active event today; 2026 season College Football Playoff markets not yet listed"),
    # MLB stat-count: structural absence
    "KXMLBSTATCOUNT-26IMMACULATE-AP-2": ("NO MATCH", None,
                                          "Polymarket has no per-pitcher immaculate-inning markets"),
    # NFL win totals 2026-27: same as KXNFLPLAYOFF, 2025-26 event closed, 2026-27 not yet listed
    "KXNFLWINS-27DET-8": ("EVENT_FUTURE", None,
                           "Polymarket NFL-win-totals event resolved; 2026-27 season not yet listed (typical listing Aug-Sept 2026)"),
    # NFL next team Pittsburgh -> Atlanta: niche player-trade market
    "KXNEXTTEAMNFL-26KPITTS-ATL": ("PARTIAL", None,
                                    "Polymarket has 'X next team' markets for some players (Aaron Rodgers, Sam Darnold); only matches when that specific player is on Polymarket's hot list"),
    # NBA city expansion: niche
    "KXCITYNBAEXPAND-28JAN01-LV": ("NO MATCH", None,
                                    "Polymarket does not list NBA-expansion-city-specific markets"),
    # NHL next team: similar to NFL
    "KXNEXTTEAMNHL-26AMAT-TOR": ("NO MATCH", None,
                                  "Polymarket does not list 'NHL next team for free agent X' player-specific markets"),
    # WNBA win totals: Polymarket has WNBA awards but no per-team win-totals markets listed
    "KXWNBAWINS-26PHX-20": ("NO MATCH", None,
                             "Polymarket WNBA tag has 44 active events but no per-team win-totals markets"),
}

# Series to coverage class on v1 backtest + v3 inventory (used for weighting)
# Compiled from probe_poly_coverage findings + manual audit
SERIES_COVERAGE: dict[str, str] = {
    # Strong match: same kind of market exists in current Polymarket inventory
    "KXMLBPLAYOFFS": "MATCH",
    "KXMLBALEAST": "MATCH", "KXMLBALCENT": "MATCH", "KXMLBALWEST": "MATCH",
    "KXMLBNLEAST": "MATCH", "KXMLBNLCENT": "MATCH", "KXMLBNLWEST": "MATCH",
    "KXMLBDIVWINNER": "MATCH",
    "KXMLBALCY": "MATCH", "KXMLBNLCY": "MATCH",
    "KXMLBALMVP": "MATCH", "KXMLBNLMVP": "MATCH",
    "KXMLBALROTY": "MATCH", "KXMLBNLROTY": "MATCH",
    "KXNFLPLAYOFF": "MATCH",  # in-season; 2026-27 future
    "KXNFLGAME": "MATCH",  # in-season; off-season is future
    "KXNFLMVP": "MATCH", "KXNFLDPOY": "MATCH", "KXNFLOPOY": "MATCH",
    "KXNFLDROY": "MATCH", "KXNFLOROY": "MATCH",
    "KXNBAMVP": "MATCH", "KXNBADPOY": "MATCH", "KXNBASIXTH": "MATCH",
    "KXNBAMIMP": "MATCH", "KXNBAROTY": "MATCH",
    "KXNBAEAST": "MATCH", "KXNBAWEST": "MATCH",
    "KXNHLPLAYOFF": "MATCH", "KXNHLPRES": "MATCH",
    "KXNHLEAST": "MATCH", "KXNHLWEST": "MATCH",
    "KXNHLHART": "MATCH", "KXNHLVEZINA": "MATCH",
    "KXNHLNORRIS": "MATCH", "KXNHLCONN": "MATCH",
    "KXWNBAROTY": "MATCH", "KXWNBAMVP": "MATCH",
    "KXBALLONDOR": "MATCH",
    "KXIPL": "MATCH", "KXIPLFINAL": "MATCH",
    "KXUCL": "MATCH",
    "KXEPL": "MATCH", "KXEPLGAME": "MATCH",
    "KXFOMEN": "MATCH",
    "KXUFCFIGHT": "MATCH",
    "KXCHESSCANDIDATES": "MATCH", "KXCHESSWORLDCHAMPION": "MATCH",
    "KXMASTERS": "MATCH", "KXOPEN": "MATCH",
    "KXNCAAFMVP": "MATCH",
    "KXWCGAME": "MATCH",
    # Partial: event class exists but Kalshi has narrower threshold / per-side granularity
    "KXMLBWINS": "PARTIAL",  # Polymarket has the event but ONE threshold per team
    "KXNFLWINS": "PARTIAL",  # Same
    "KXNBAWINS": "PARTIAL",  # NBA win totals event on Polymarket but threshold may differ
    "KXWNBAWINS": "PARTIAL",
    "KXNFLAFCNORTH": "PARTIAL", "KXNFLAFCEAST": "PARTIAL",
    "KXNFLAFCSOUTH": "PARTIAL", "KXNFLAFCWEST": "PARTIAL",
    "KXNFLNFCNORTH": "PARTIAL", "KXNFLNFCEAST": "PARTIAL",
    "KXNFLNFCSOUTH": "PARTIAL", "KXNFLNFCWEST": "PARTIAL",
    "KXNBAATLANTIC": "PARTIAL", "KXNBACENTRAL": "PARTIAL", "KXNBASOUTHEAST": "PARTIAL",
    "KXNBANORTHWEST": "PARTIAL", "KXNBAPACIFIC": "PARTIAL", "KXNBASOUTHWEST": "PARTIAL",
    "KXNHLMETROPOLITAN": "PARTIAL", "KXNHLATLANTIC": "PARTIAL",
    "KXNHLCENTRAL": "PARTIAL", "KXNHLPACIFIC": "PARTIAL",
    "KXBOXING": "PARTIAL",  # only major fights on Polymarket
    "KXNCAAFPLAYOFF": "PARTIAL", "KXNCAAFGAME": "PARTIAL",
    "KXNCAAMBACHAMP": "PARTIAL",
    "KXMLSGAME": "PARTIAL",
    "KXMLBGAME": "PARTIAL",
    "KXATPGRANDSLAM": "PARTIAL", "KXATP": "PARTIAL",
    "KXWTAGRANDSLAM": "PARTIAL", "KXWTA": "PARTIAL",
    "KXUCLROUND": "PARTIAL",
    "KXFACUP": "PARTIAL", "KXCOPADELREY": "PARTIAL",
    "KXLALIGA": "PARTIAL", "KXBUNDESLIGA": "PARTIAL",
    "KXSERIEA": "PARTIAL", "KXLIGUE1": "PARTIAL",
    "KXCS2": "PARTIAL", "KXLOL": "PARTIAL",
    "KXPGA": "PARTIAL", "KXLPGA": "PARTIAL",
    "KXWCSQUAD": "PARTIAL",  # event match but per-player needs lookup
    "KXWCSTAGEOFELIM": "PARTIAL",
    "KXLEADERNBAAST": "PARTIAL", "KXLEADERNBAPTS": "PARTIAL", "KXLEADERNBAREB": "PARTIAL",
    "KXNFLTRADE": "PARTIAL",
    "KXNEXTTEAMNFL": "PARTIAL",
    "KXNFLNEXTHC": "PARTIAL", "KXNEWCOACHNO": "PARTIAL",
    # No match: structural absence
    "KXMLBSTATCOUNT": "NO MATCH",
    "KXSTARTINGQBWEEK1": "NO MATCH",  # though one Raiders-specific exists today
    "KXSTARTCLEBROWNS": "NO MATCH",
    "KXNBAPLAYOFFWINS": "NO MATCH",
    "KXCARDPRESENCEUFCWH": "NO MATCH",
    "KXVALORANT": "NO MATCH",
    "KXCHARCOUNTLOLWORLDS": "NO MATCH",
    "KXSWIFTATTEND": "NO MATCH",
    "KXTGL": "NO MATCH", "KXTGLCHAMPION": "NO MATCH",
    "KXFOWMEN": "NO MATCH",
    "KXCITYNBAEXPAND": "NO MATCH",
    "KXNEXTTEAMNHL": "NO MATCH",
}

# Per-series PARTIAL fraction: of Kalshi markets in this series, what fraction
# can plausibly be matched to a Polymarket counterpart? Estimated from manual
# audit findings + structural considerations.
PARTIAL_FRACTION: dict[str, float] = {
    "KXMLBWINS": 0.30,      # Polymarket has event but ONE threshold per team; Kalshi typically has 4 thresholds
    "KXNFLWINS": 0.30,
    "KXNBAWINS": 0.30,
    "KXWNBAWINS": 0.30,
    "KXNFLAFCNORTH": 1.0, "KXNFLAFCEAST": 1.0, "KXNFLAFCSOUTH": 1.0, "KXNFLAFCWEST": 1.0,
    "KXNFLNFCNORTH": 1.0, "KXNFLNFCEAST": 1.0, "KXNFLNFCSOUTH": 1.0, "KXNFLNFCWEST": 1.0,
    "KXNBAATLANTIC": 1.0, "KXNBACENTRAL": 1.0, "KXNBASOUTHEAST": 1.0,
    "KXNBANORTHWEST": 1.0, "KXNBAPACIFIC": 1.0, "KXNBASOUTHWEST": 1.0,
    "KXNHLMETROPOLITAN": 1.0, "KXNHLATLANTIC": 1.0, "KXNHLCENTRAL": 1.0, "KXNHLPACIFIC": 1.0,
    "KXBOXING": 0.30,       # Polymarket lists only "headline" fights
    "KXNCAAFPLAYOFF": 0.50, "KXNCAAFGAME": 0.10,
    "KXNCAAMBACHAMP": 0.30,
    "KXMLSGAME": 0.40,
    "KXMLBGAME": 0.50,
    "KXATPGRANDSLAM": 0.50, "KXATP": 0.30,
    "KXWTAGRANDSLAM": 0.50, "KXWTA": 0.30,
    "KXUCLROUND": 0.50,
    "KXFACUP": 0.20, "KXCOPADELREY": 0.20,
    "KXLALIGA": 0.50, "KXBUNDESLIGA": 0.50,
    "KXSERIEA": 0.50, "KXLIGUE1": 0.50,
    "KXCS2": 0.30, "KXLOL": 0.40,
    "KXPGA": 0.30, "KXLPGA": 0.20,
    "KXWCSQUAD": 0.40,
    "KXWCSTAGEOFELIM": 0.30,
    "KXLEADERNBAAST": 0.30, "KXLEADERNBAPTS": 0.30, "KXLEADERNBAREB": 0.30,
    "KXNFLTRADE": 0.10,
    "KXNEXTTEAMNFL": 0.10,
    "KXNFLNEXTHC": 0.40, "KXNEWCOACHNO": 0.40,
}


def main() -> None:
    with open(AUDIT) as f:
        audit = json.load(f)
    rows = []
    for r in audit:
        ticker = r["kalshi_ticker"]
        if ticker in MANUAL_LABELS:
            status, slug, note = MANUAL_LABELS[ticker]
        else:
            # default to NEEDS_REVIEW
            status, slug, note = ("NEEDS_REVIEW", None, "no manual label set")
        rows.append({
            "kalshi_ticker": ticker,
            "series_prefix": r["series_prefix"],
            "kalshi_market_mid_at_placement": r.get("kalshi_market_mid_at_placement"),
            "match_status": status,
            "poly_event_slug": slug,
            "note": note,
            "match_method": r.get("match_method"),
            "poly_mid_now": r.get("poly_mid_now"),
        })
    df = pd.DataFrame(rows)
    df.to_parquet(OUT, index=False)
    print(f"Wrote {len(df)} classified rows to {OUT}")
    print()
    print("Per-status counts:")
    print(df["match_status"].value_counts())

    # Build per-series coverage fraction
    series_rows = []
    for s, cov in SERIES_COVERAGE.items():
        frac = 1.0 if cov == "MATCH" else (PARTIAL_FRACTION.get(s, 0.5) if cov == "PARTIAL" else 0.0)
        series_rows.append({
            "series_prefix": s,
            "coverage_class": cov,
            "matched_fraction": frac,
        })
    series_df = pd.DataFrame(series_rows)
    series_df.to_parquet(DATA_V4 / "series_coverage_fraction.parquet", index=False)
    print()
    print(f"Wrote series_coverage_fraction.parquet ({len(series_df)} series)")


if __name__ == "__main__":
    main()
